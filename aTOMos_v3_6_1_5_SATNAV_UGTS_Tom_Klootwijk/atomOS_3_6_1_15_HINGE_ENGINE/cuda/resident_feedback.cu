#include "atomos/resident_feedback.hpp"
#include "atomos/resident_kernels.cuh"
#include <cuda_runtime.h>
#include <chrono>
#include <limits>
#include <stdexcept>
#include <string>
namespace atomos {
namespace {
void checked(cudaError_t error){if(error!=cudaSuccess)throw std::runtime_error(cudaGetErrorString(error));}
__device__ uint64_t lut(uint32_t table,uint64_t q,uint64_t d,uint64_t mask){
  uint64_t v=0;
  if(table&1)v|=~q&~d;if(table&2)v|=q&~d;
  if(table&4)v|=~q&d;if(table&8)v|=q&d;
  return v&mask;
}
__global__ void commit_feedback(FeedbackState* states,const ResidentCount* counts,
                               uint32_t lanes,uint64_t epoch,WordProfile profile){
  const uint32_t i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=lanes)return;
  FeedbackState s=states[i];
  // Replayed epochs are a hold even though the immutable query selector can
  // now point at another alternative; that recomputed count is never committed.
  if(s.initialized&&epoch<=s.last_epoch){s.status=epoch==s.last_epoch?0:2;states[i]=s;return;}
  if(counts[i].unresolved){s.status=1;states[i]=s;return;}
  const uint64_t drive=counts[i].definite_inside?1:0;
  const bool hinge=!s.initialized||drive!=s.last_drive; // explicit pulse-on-first profile
  if(hinge&&s.hinges==~uint64_t(0)){s.status=3;states[i]=s;return;}
  if(hinge){
    const uint64_t old=s.q;
    uint64_t y=lut(profile.x_lut,old,drive,profile.valid_mask)&profile.a0&profile.n0;
    if(y&profile.b0)y=0;y&=profile.a1&profile.n1;if(y&profile.b1)y=0;
    const uint64_t j=lut(profile.j_lut,old,y,profile.valid_mask);
    const uint64_t k=lut(profile.k_lut,old,y,profile.valid_mask);
    s.q=((j&~old)|(~k&old))&profile.valid_mask;
    s.parity^=1;++s.hinges;
  }
  s.last_epoch=epoch;s.last_drive=drive;s.initialized=1;s.status=0;
  // This profile has a fixed chart. No geometric seam reversal is inferred.
  states[i]=s;
}
}
struct ResidentFeedback::Impl {
  ResidentIndex& source;ResidentDeviceView view;WordProfile profile;
  FeedbackState* states=nullptr;cudaEvent_t start=nullptr,stop=nullptr;
  FeedbackStats timing;
  void release()noexcept{if(start)cudaEventDestroy(start);if(stop)cudaEventDestroy(stop);cudaFree(states);}
  Impl(ResidentIndex& index,const WordProfile& p):source(index),view(index.device_view()),profile(p){
    try {
      if(!view.query_count||view.query_count%2)throw std::invalid_argument("nonempty paired immutable query table required");
      if(p.x_lut>15||p.j_lut>15||p.k_lut>15||!(p.valid_mask&1))
        throw std::invalid_argument("valid one-bit selector and Boolean LUT profile required");
      timing.lanes=view.query_count/2;
      checked(cudaMalloc(reinterpret_cast<void**>(&states),size_t(timing.lanes)*sizeof(FeedbackState)));
      checked(cudaMemset(states,0,size_t(timing.lanes)*sizeof(FeedbackState)));
      checked(cudaEventCreate(&start));checked(cudaEventCreate(&stop));
    }catch(...){release();throw;}
  }
  ~Impl(){release();}
};
static_assert(sizeof(FeedbackState)==8*sizeof(uint64_t),"feedback selector stride");
ResidentFeedback::ResidentFeedback(ResidentIndex& source,const WordProfile& p):impl_(new Impl(source,p)){}
ResidentFeedback::~ResidentFeedback()=default;
const FeedbackStats& ResidentFeedback::stats()const{return impl_->timing;}
void ResidentFeedback::run_epochs(uint64_t first,uint32_t count,bool texture_fetch){
  auto& p=*impl_;p.timing.epochs=count;p.timing.device_ms=0;p.timing.wall_ms=0;
  if(!count)return;
  if(first>std::numeric_limits<uint64_t>::max()-(uint64_t(count)-1))
    throw std::invalid_argument("logical epoch range overflows");
  const auto wall=std::chrono::steady_clock::now();
  // Invalidate ordinary count-result ownership before entering selected mode.
  p.view=p.source.device_view();
  checked(cudaEventRecord(p.start));
  for(uint32_t step=0;step<count;++step){
    launch_resident_selected(p.view,texture_fetch,reinterpret_cast<const uint64_t*>(p.states),8,p.timing.lanes);
    checked(cudaGetLastError());
    commit_feedback<<<unsigned((uint64_t(p.timing.lanes)+127)/128),128>>>(p.states,p.view.counts,p.timing.lanes,first+step,p.profile);
    checked(cudaGetLastError());
  }
  checked(cudaEventRecord(p.stop));checked(cudaEventSynchronize(p.stop));float measured=0;
  checked(cudaEventElapsedTime(&measured,p.start,p.stop));p.timing.device_ms=measured;
  p.timing.wall_ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-wall).count();
}
std::vector<FeedbackState> ResidentFeedback::readback()const{
  const auto& p=*impl_;std::vector<FeedbackState> states(p.timing.lanes);
  checked(cudaMemcpy(states.data(),p.states,states.size()*sizeof(FeedbackState),cudaMemcpyDeviceToHost));return states;
}
}
