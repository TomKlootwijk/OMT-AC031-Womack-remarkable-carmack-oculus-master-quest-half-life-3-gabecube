#include "atomos/tomagi_feedback.hpp"
#include <cuda_runtime.h>
#include <chrono>
#include <limits>
#include <stdexcept>
#include <string>

namespace atomos { namespace tomagi { namespace {
void cu(cudaError_t e){if(e!=cudaSuccess)throw std::runtime_error(cudaGetErrorString(e));}
__device__ std::uint64_t table(std::uint32_t t,std::uint64_t q,std::uint64_t d,std::uint64_t mask){
    std::uint64_t out=0;
    if(t&1)out|=~q&~d;if(t&2)out|=q&~d;if(t&4)out|=~q&d;if(t&8)out|=q&d;
    return out&mask;
}
__global__ void inject_words(DeviceView vm,const WordState* words){
    const std::uint64_t lane=std::uint64_t(blockIdx.x)*blockDim.x+threadIdx.x;
    if(lane>=vm.state_count)return;const std::uint32_t i=std::uint32_t(lane);
    if(vm.errors[i]||(vm.states[i].words[15]&1u)||words[i].status)return;
    const std::uint64_t q=words[i].q;
    vm.states[i].words[0]=std::uint32_t(q);
    vm.states[i].words[4]=std::uint32_t(q>>32);
}
__global__ void commit_words(DeviceView vm,WordState* words,atomos::WordProfile profile){
    const std::uint64_t lane=std::uint64_t(blockIdx.x)*blockDim.x+threadIdx.x;
    if(lane>=vm.state_count)return;const std::uint32_t i=std::uint32_t(lane);
    WordState s=words[i];const Receipt r=vm.receipts[i];
    if(vm.errors[i]||r.error){s.status=1;words[i]=s;return;}
    if(!r.executed||!r.emitted)return;
    if(s.initialized&&r.epoch<=s.last_epoch){
        if(r.epoch<s.last_epoch){s.status=2;words[i]=s;}return;
    }
    if(s.status)return;
    if(s.hinges==~std::uint64_t(0)){s.status=3;words[i]=s;return;}
    const std::uint64_t q=s.q,d=r.payload;
    std::uint64_t y=table(profile.x_lut,q,d,profile.valid_mask)&profile.a0&profile.n0;
    if(y&profile.b0)y=0;y&=profile.a1&profile.n1;if(y&profile.b1)y=0;
    const std::uint64_t j=table(profile.j_lut,q,y,profile.valid_mask);
    const std::uint64_t k=table(profile.k_lut,q,y,profile.valid_mask);
    s.q=((j&~q)|(~k&q))&profile.valid_mask;
    s.parity^=1;++s.hinges;s.initialized=1;s.last_epoch=r.epoch;s.last_drive=d;
    words[i]=s;
}
}

struct WordFeedback::Impl {
    VM& source;atomos::WordProfile profile;WordBinding binding;
    WordState* words=nullptr;cudaEvent_t start=nullptr,stop=nullptr;
    std::uint64_t generation=0,expected_epoch=0;std::uint32_t lanes=0;
    bool poisoned=false;WordFeedbackStats timing;
    void release()noexcept{cudaFree(words);if(start)cudaEventDestroy(start);if(stop)cudaEventDestroy(stop);}
    Impl(VM& vm,const atomos::WordProfile& p,WordBinding b,const std::vector<std::uint64_t>& initial)
        :source(vm),profile(p),binding(b){
        if(!p.valid_mask||p.x_lut>15||p.j_lut>15||p.k_lut>15)
            throw std::invalid_argument("nonempty word mask and four-entry Boolean tables required");
        if(b!=WordBinding::None&&b!=WordBinding::RhoAndVrho)throw std::invalid_argument("unknown word binding");
        source.synchronize();const auto view=source.device_view();lanes=view.state_count;
        if(!lanes)throw std::invalid_argument("feedback requires at least one VM state");
        if(!initial.empty()&&initial.size()!=lanes)throw std::invalid_argument("initial word count mismatch");
        std::vector<WordState> host(lanes);
        for(std::size_t i=0;i<initial.size();++i){
            if(initial[i]&~p.valid_mask)throw std::invalid_argument("initial word exceeds declared valid mask");
            host[i].q=initial[i];
        }
        generation=source.state_generation();expected_epoch=source.epoch();timing.lanes=lanes;
        try{
            cu(cudaMalloc(reinterpret_cast<void**>(&words),std::size_t(lanes)*sizeof(WordState)));
            cu(cudaMemcpy(words,host.data(),host.size()*sizeof(WordState),cudaMemcpyHostToDevice));
            cu(cudaEventCreate(&start));cu(cudaEventCreate(&stop));
        }catch(...){release();throw;}
    }
    ~Impl(){release();}
    DeviceView checked_view()const{
        if(poisoned)throw std::runtime_error("feedback phase previously failed");
        if(source.state_generation()!=generation||source.epoch()!=expected_epoch)
            throw std::logic_error("borrowed VM was reset or advanced outside this feedback phase");
        auto view=source.device_view();
        if(view.state_count!=lanes)throw std::logic_error("borrowed VM lane count changed");
        return view;
    }
};
WordFeedback::WordFeedback(VM& source,const atomos::WordProfile& profile,WordBinding binding,
                           const std::vector<std::uint64_t>& initial)
    :impl_(new Impl(source,profile,binding,initial)){}
WordFeedback::~WordFeedback()=default;
const WordFeedbackStats& WordFeedback::stats()const{return impl_->timing;}
void WordFeedback::run_steps(std::uint32_t count,bool texture){
    auto& p=*impl_;auto view=p.checked_view();
    p.timing.device_ms=p.timing.wall_ms=0;p.timing.steps=count;
    if(!count)return;
    if(count>std::numeric_limits<std::uint64_t>::max()-p.expected_epoch)
        throw std::invalid_argument("feedback epoch range overflows");
    const auto begin=std::chrono::steady_clock::now();
    const unsigned blocks=unsigned((std::uint64_t(p.lanes)+127)/128);
    try{
        cu(cudaEventRecord(p.start));
        for(std::uint32_t i=0;i<count;++i){
            view=p.source.device_view();
            if(p.binding==WordBinding::RhoAndVrho){inject_words<<<blocks,128>>>(view,p.words);cu(cudaGetLastError());}
            p.source.enqueue_step(texture);p.expected_epoch=p.source.epoch();
            commit_words<<<blocks,128>>>(p.source.device_view(),p.words,p.profile);cu(cudaGetLastError());
        }
        cu(cudaEventRecord(p.stop));cu(cudaEventSynchronize(p.stop));float ms=0;
        cu(cudaEventElapsedTime(&ms,p.start,p.stop));p.timing.device_ms=ms;
        p.timing.wall_ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-begin).count();
    }catch(...){p.poisoned=true;throw;}
}
void WordFeedback::recommit_last(){
    auto& p=*impl_;const auto view=p.checked_view();
    commit_words<<<unsigned((std::uint64_t(p.lanes)+127)/128),128>>>(view,p.words,p.profile);
    cu(cudaGetLastError());p.source.synchronize();
}
std::vector<WordState> WordFeedback::readback()const{
    const auto& p=*impl_;p.checked_view();std::vector<WordState> host(p.lanes);
    cu(cudaMemcpy(host.data(),p.words,host.size()*sizeof(WordState),cudaMemcpyDeviceToHost));return host;
}
}} // namespace atomos::tomagi
