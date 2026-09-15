#include "atomos/texture_index.hpp"
#include "atomos/spatial_index.hpp"
#include "atomos/worker_pool.hpp"
#include "atomos/gpu_kernels.cuh"
#include <cuda_runtime.h>
#include "s2/s2predicates.h"
#include "s2/s1chord_angle.h"
#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cfenv>
#include <cmath>
#include <cstring>
#include <limits>
#include <stdexcept>
#include <string>

namespace atomos {
namespace {
void check(cudaError_t e) { if (e != cudaSuccess) throw std::runtime_error(cudaGetErrorString(e)); }
double elapsed(std::chrono::steady_clock::time_point begin) {
  return std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-begin).count();
}
static_assert(sizeof(GpuNode)==48,"node texture layout");
static_assert(sizeof(Point)==32,"point texture layout");
cudaTextureObject_t texture_for(void* ptr, size_t bytes) {
  int device=0;cudaDeviceProp properties{};check(cudaGetDevice(&device));
  check(cudaGetDeviceProperties(&properties,device));
  if(bytes%sizeof(uint4)||bytes/sizeof(uint4)>size_t(properties.maxTexture1DLinear)||
     bytes/sizeof(uint4)>size_t(INT32_MAX))
    throw std::length_error("linear texture exceeds device or signed texel-index limit");
  cudaResourceDesc resource{};
  resource.resType=cudaResourceTypeLinear;
  resource.res.linear.devPtr=ptr;
  resource.res.linear.desc=cudaCreateChannelDesc<uint4>();
  resource.res.linear.sizeInBytes=bytes;
  cudaTextureDesc desc{};
  desc.readMode=cudaReadModeElementType;
  desc.filterMode=cudaFilterModePoint;
  desc.normalizedCoords=0;
  cudaTextureObject_t result=0;
  check(cudaCreateTextureObject(&result,&resource,&desc,nullptr));
  return result;
}

float down_float(double x){float f=float(x);if(double(f)>x)f=std::nextafter(f,-INFINITY);return f;}
float up_float(double x){float f=float(x);if(double(f)<x)f=std::nextafter(f,INFINITY);return f;}
}

struct TextureIndex::Impl {
  SpatialIndex host;
  WorkerPool refinement_pool;
  TextureStats timing;
  uint32_t capacity;
  uint64_t* packed=nullptr;uint64_t* words=nullptr;size_t word_count=0,padded_words=0;
  GpuNode* nodes=nullptr;Point* points=nullptr;Point* point_storage=nullptr;
  cudaTextureObject_t packed_tex=0,node_tex=0,point_tex=0;
  GpuQuery* query=nullptr;uint32_t* candidates=nullptr;uint32_t* counts=nullptr;size_t query_capacity=0;
  uint64_t* candidate_offsets=nullptr;
  uint32_t* compact_candidates=nullptr;size_t compact_capacity=0;
  cudaEvent_t event_start=nullptr,event_end=nullptr;
  HingeState* states=nullptr;HingeInput* inputs=nullptr;size_t state_capacity=0;
  std::vector<HingeInput> last_inputs;
  WordProfile bound_profile{};bool profile_bound=false;
  void release() noexcept {
    if(packed_tex)cudaDestroyTextureObject(packed_tex);
    if(node_tex)cudaDestroyTextureObject(node_tex);if(point_tex)cudaDestroyTextureObject(point_tex);
    cudaFree(point_storage);cudaFree(packed);cudaFree(words);cudaFree(query);cudaFree(candidates);cudaFree(counts);
    cudaFree(candidate_offsets);cudaFree(compact_candidates);
    if(event_start)cudaEventDestroy(event_start);if(event_end)cudaEventDestroy(event_end);
    cudaFree(states);cudaFree(inputs);
  }
  ~Impl(){release();}
  explicit Impl(const SpatialIndex& s,uint32_t cap):host(s),
      refinement_pool(std::max(1u,std::min(20u,std::thread::hardware_concurrency()))),capacity(cap){
    try {
    if(!cap)throw std::invalid_argument("candidate capacity must be positive");
    const auto start=std::chrono::steady_clock::now();
    std::vector<GpuNode> ns;
    for(const auto& n:s.nodes()){
      GpuNode g{};for(int d=0;d<3;++d){g.lo[d]=down_float(n.lower[d]);g.hi[d]=up_float(n.upper[d]);}
      g.left=n.left;g.right=n.right;g.begin=n.begin;g.count=n.count;g.axis=n.axis;ns.push_back(g);
    }
    if(!ns.empty()){
      // Recursively assign the successor outside each subtree, no data changes.
      auto assign=[&](auto&& self,uint32_t i,uint32_t successor)->void{
        ns[i].escape=successor;
        if(!ns[i].count){self(self,ns[i].left,ns[i].right);self(self,ns[i].right,successor);}
      };assign(assign,0,uint32_t(ns.size()));
    }
    const size_t node_bytes=ns.size()*sizeof(GpuNode);
    const size_t point_bytes=s.points().size()*sizeof(Point);
    word_count=(node_bytes+point_bytes)/8;
    padded_words=std::max<size_t>(64,((word_count+63)/64)*64);
    std::vector<uint64_t> plain(padded_words,0),planes(padded_words,0);
    if(node_bytes)std::memcpy(plain.data(),ns.data(),node_bytes);
    if(point_bytes)std::memcpy(reinterpret_cast<char*>(plain.data())+node_bytes,s.points().data(),point_bytes);
    for(size_t block=0;block<padded_words;block+=64)
      for(unsigned bit=0;bit<64;++bit)
        for(unsigned lane=0;lane<64;++lane)planes[block+bit]|=((plain[block+lane]>>bit)&1ull)<<lane;
    check(cudaMalloc(reinterpret_cast<void**>(&packed),padded_words*8));
    check(cudaMalloc(reinterpret_cast<void**>(&words),padded_words*8));
    check(cudaMemcpy(packed,planes.data(),padded_words*8,cudaMemcpyHostToDevice));
    packed_tex=texture_for(packed,padded_words*8);
    timing.upload_ms=elapsed(start);
    check(cudaEventCreate(&event_start));check(cudaEventCreate(&event_end));check(cudaEventRecord(event_start));
    launch_expand(packed_tex,words,padded_words);
    check(cudaGetLastError());check(cudaEventRecord(event_end));check(cudaEventSynchronize(event_end));float ms=0;
    check(cudaEventElapsedTime(&ms,event_start,event_end));timing.expansion_ms=ms;
    nodes=reinterpret_cast<GpuNode*>(words);
    points=reinterpret_cast<Point*>(reinterpret_cast<char*>(words)+node_bytes);
    // Linear texture resources require aligned base addresses. Bind the entire
    // expanded buffer and use a separate point allocation only if its offset is
    // unaligned; current node blocks need not align to device textureAlignment.
    if(node_bytes)node_tex=texture_for(nodes,node_bytes);
    if(point_bytes){
      check(cudaMalloc(reinterpret_cast<void**>(&point_storage),point_bytes));
      check(cudaMemcpy(point_storage,points,point_bytes,cudaMemcpyDeviceToDevice));points=point_storage;
      point_tex=texture_for(points,point_bytes);
    }
    timing.resident_bytes=2*padded_words*8+point_bytes;
    } catch(...) { release(); throw; }
  }
  void reserve_queries(size_t n){
    if(n<=query_capacity)return;
    if(n>size_t(INT32_MAX)||n>SIZE_MAX/size_t(capacity)/4||
       n>SIZE_MAX/sizeof(GpuQuery)||n>SIZE_MAX/sizeof(uint64_t)-1)
      throw std::length_error("query allocation exceeds kernel address contract");
    GpuQuery* nq=nullptr;uint32_t* nc=nullptr;uint32_t* nn=nullptr;uint64_t* no=nullptr;
    try {
      check(cudaMalloc(reinterpret_cast<void**>(&nq),n*sizeof(GpuQuery)));
      check(cudaMalloc(reinterpret_cast<void**>(&nn),n*4));
      check(cudaMalloc(reinterpret_cast<void**>(&nc),n*size_t(capacity)*4));
      check(cudaMalloc(reinterpret_cast<void**>(&no),(n+1)*sizeof(uint64_t)));
    } catch(...) {cudaFree(nq);cudaFree(nc);cudaFree(nn);cudaFree(no);throw;}
    cudaFree(query);cudaFree(candidates);cudaFree(counts);cudaFree(candidate_offsets);
    query=nq;candidates=nc;counts=nn;candidate_offsets=no;query_capacity=n;
  }
  void reserve_compact(size_t n){
    if(n<=compact_capacity)return;
    if(n>SIZE_MAX/sizeof(uint32_t))throw std::length_error("compacted candidates exceed address contract");
    uint32_t* next=nullptr;
    check(cudaMalloc(reinterpret_cast<void**>(&next),n*sizeof(uint32_t)));
    cudaFree(compact_candidates);compact_candidates=next;compact_capacity=n;
  }
};
TextureIndex::TextureIndex(const SpatialIndex& s,uint32_t cap):impl_(new Impl(s,cap)){}
TextureIndex::~TextureIndex()=default;
TextureIndex::TextureIndex(TextureIndex&&) noexcept=default;
TextureIndex& TextureIndex::operator=(TextureIndex&&) noexcept=default;
const TextureStats& TextureIndex::stats()const{return impl_->timing;}
std::vector<uint64_t> TextureIndex::seed_words()const{
  std::vector<uint64_t> out(impl_->word_count);
  if(!out.empty())check(cudaMemcpy(out.data(),impl_->words,out.size()*8,cudaMemcpyDeviceToHost));return out;
}
std::vector<std::vector<uint64_t>> TextureIndex::radius_batch(const std::vector<RadiusRequest>& qs,bool texture_fetch){
  if(std::fegetround()!=FE_TONEAREST)throw std::runtime_error("FE_TONEAREST required for exact predicate refinement");
  auto& p=*impl_;const auto start=std::chrono::steady_clock::now();
  std::vector<std::vector<uint64_t>> out(qs.size());
  if(qs.empty()){
    p.timing.kernel_ms=0;p.timing.refinement_ms=0;p.timing.compaction_ms=0;p.timing.refinement_threads=1;
    p.timing.candidate_readback_bytes=0;p.timing.candidate_offset_upload_bytes=0;
    p.timing.candidate_count=0;p.timing.exact_refinements=0;p.timing.overflow_queries=0;
    p.timing.candidate_count_is_lower_bound=false;p.timing.query_wall_ms=elapsed(start);return out;
  }
  p.reserve_queries(qs.size());std::vector<GpuQuery> query;query.reserve(qs.size());
  for(const auto& q:qs){
    if(!std::isfinite(q.chord_radius2)||q.chord_radius2<0||q.chord_radius2>4)
      throw std::invalid_argument("radius squared must lie in [0,4]");
    SpatialIndex::validate_point(q.point);
    query.push_back({float(q.point.x),float(q.point.y),float(q.point.z),up_float(q.chord_radius2)});
  }
  check(cudaMemcpy(p.query,query.data(),query.size()*sizeof(GpuQuery),cudaMemcpyHostToDevice));
  check(cudaEventRecord(p.event_start));
  launch_radius(texture_fetch,p.node_tex,p.point_tex,p.nodes,p.points,uint32_t(p.host.nodes().size()),p.query,uint32_t(qs.size()),p.capacity,p.candidates,p.counts);
  check(cudaGetLastError());check(cudaEventRecord(p.event_end));check(cudaEventSynchronize(p.event_end));float ms=0;
  check(cudaEventElapsedTime(&ms,p.event_start,p.event_end));p.timing.kernel_ms=ms;
  std::vector<uint32_t> counts(qs.size());
  check(cudaMemcpy(counts.data(),p.counts,counts.size()*4,cudaMemcpyDeviceToHost));
  // Only complete candidate intervals are retained. Prefix offsets are 64-bit
  // and overflow intervals have zero length, so no saturated prefix is ever
  // mistaken for a complete radius answer.
  std::vector<uint64_t> offsets(qs.size()+1,0);
  p.timing.candidate_count=0;p.timing.exact_refinements=0;p.timing.overflow_queries=0;
  for(size_t i=0;i<counts.size();++i){
    const auto count=counts[i];
    p.timing.candidate_count+=count;
    if(count>p.capacity)++p.timing.overflow_queries;
    const uint64_t retained=count<=p.capacity?count:0;
    if(retained>uint64_t(SIZE_MAX/sizeof(uint32_t))-offsets[i])
      throw std::length_error("compacted candidate offset overflow");
    offsets[i+1]=offsets[i]+retained;
  }
  p.timing.candidate_count_is_lower_bound=p.timing.overflow_queries!=0;
  const size_t retained=size_t(offsets.back());
  std::vector<uint32_t> candidates(retained);
  p.timing.candidate_readback_bytes=uint64_t(retained)*sizeof(uint32_t);
  p.timing.candidate_offset_upload_bytes=0;p.timing.compaction_ms=0;
  if(retained){
    p.reserve_compact(retained);
    p.timing.candidate_offset_upload_bytes=uint64_t(offsets.size())*sizeof(uint64_t);
    check(cudaMemcpy(p.candidate_offsets,offsets.data(),size_t(p.timing.candidate_offset_upload_bytes),cudaMemcpyHostToDevice));
    check(cudaEventRecord(p.event_start));
    launch_compact_candidates(p.candidates,p.candidate_offsets,uint32_t(qs.size()),p.capacity,p.compact_candidates);
    check(cudaGetLastError());check(cudaEventRecord(p.event_end));check(cudaEventSynchronize(p.event_end));
    check(cudaEventElapsedTime(&ms,p.event_start,p.event_end));p.timing.compaction_ms=ms;
    check(cudaMemcpy(candidates.data(),p.compact_candidates,size_t(p.timing.candidate_readback_bytes),cudaMemcpyDeviceToHost));
  }
  const auto refinement_start=std::chrono::steady_clock::now();
  // Parallelize only when there is useful independent work. Ordinary batches
  // allow one worker per 64 queries; high candidate counts or full-query
  // fallbacks can justify more workers even for a smaller batch.
  const uint64_t desired=std::max<uint64_t>(1,std::max<uint64_t>((qs.size()+63)/64,
      std::max<uint64_t>((p.timing.candidate_count+2047)/2048,p.timing.overflow_queries)));
  const unsigned threads=unsigned(std::min<uint64_t>(p.refinement_pool.size(),
      std::min<uint64_t>(qs.size(),desired)));
  p.timing.refinement_threads=threads;
  struct alignas(64) LocalStats { uint64_t predicates=0; };
  std::array<LocalStats,20> local{};
  std::atomic<size_t> next{0};
  const size_t chunk=(qs.size()<64||p.timing.overflow_queries)?1:8;
  p.refinement_pool.run(qs.size(),threads,[&](unsigned worker,size_t,size_t){
    // WorkerPool verifies this worker's rounding mode before invoking us.
    // Dynamic chunks balance expensive fallbacks without changing query order.
    for(;;){
      const size_t first=next.fetch_add(chunk,std::memory_order_relaxed);
      if(first>=qs.size())break;
      const size_t end=std::min(qs.size(),first+chunk);
      for(size_t i=first;i<end;++i){
        if(counts[i]>p.capacity){
          QueryStats fallback_stats;
          out[i]=p.host.radius(qs[i].point,qs[i].chord_radius2,&fallback_stats);
          local[worker].predicates+=fallback_stats.predicate_calls;
        }else{
          const S2Point q(qs[i].point.x,qs[i].point.y,qs[i].point.z);
          const S1ChordAngle limit=S1ChordAngle::FromLength2(qs[i].chord_radius2);
          out[i].reserve(counts[i]);
          for(uint32_t k=0;k<counts[i];++k){
            const Point& v=p.host.points()[candidates[size_t(offsets[i])+k]];
            ++local[worker].predicates;
            if(s2pred::CompareDistance(q,S2Point(v.x,v.y,v.z),limit)<=0)out[i].push_back(v.id);
          }
        }
        std::sort(out[i].begin(),out[i].end());
      }
    }
  });
  for(unsigned worker=0;worker<threads;++worker)p.timing.exact_refinements+=local[worker].predicates;
  p.timing.refinement_ms=elapsed(refinement_start);
  p.timing.query_wall_ms=elapsed(start);return out;
}
std::vector<HingeState> TextureIndex::step_hinges(const std::vector<HingeInput>& inputs,const WordProfile& profile){
  auto& p=*impl_;if(inputs.empty())return {};
  if(inputs.size()>size_t(INT32_MAX))throw std::length_error("hinge batch exceeds kernel index limit");
  for(const auto& input:inputs)if(input.valid>1||input.reversing>1)
    throw std::invalid_argument("hinge valid and reversing fields must be Boolean");
  const auto same_profile=[](const WordProfile& a,const WordProfile& b){
    return a.valid_mask==b.valid_mask&&a.a0==b.a0&&a.n0==b.n0&&a.b0==b.b0&&
      a.a1==b.a1&&a.n1==b.n1&&a.b1==b.b1&&a.x_lut==b.x_lut&&a.j_lut==b.j_lut&&a.k_lut==b.k_lut;
  };
  if(p.profile_bound&&!same_profile(p.bound_profile,profile))throw std::invalid_argument("active hinge profile is immutable");
  if(profile.x_lut>15||profile.j_lut>15||profile.k_lut>15)throw std::invalid_argument("four-entry Boolean LUT required");
  for(size_t i=0;i<std::min(inputs.size(),p.last_inputs.size());++i){
    const auto& a=inputs[i];const auto& b=p.last_inputs[i];
    if(a.valid&&b.valid&&a.event==b.event&&(a.drive!=b.drive||a.reversing!=b.reversing))
      throw std::invalid_argument("same hinge event identity has changed payload");
  }
  if(inputs.size()>p.state_capacity){
    HingeState* next=nullptr;HingeInput* next_inputs=nullptr;
    try {
      check(cudaMalloc(reinterpret_cast<void**>(&next),inputs.size()*sizeof(HingeState)));
      check(cudaMalloc(reinterpret_cast<void**>(&next_inputs),inputs.size()*sizeof(HingeInput)));
      check(cudaMemset(next,0,inputs.size()*sizeof(HingeState)));
      if(p.state_capacity)check(cudaMemcpy(next,p.states,p.state_capacity*sizeof(HingeState),cudaMemcpyDeviceToDevice));
    } catch(...) {cudaFree(next);cudaFree(next_inputs);throw;}
    cudaFree(p.states);cudaFree(p.inputs);p.states=next;p.inputs=next_inputs;
    p.state_capacity=inputs.size();
  }
  check(cudaMemcpy(p.inputs,inputs.data(),inputs.size()*sizeof(HingeInput),cudaMemcpyHostToDevice));
  launch_hinges(p.states,p.inputs,uint32_t(inputs.size()),profile);
  check(cudaGetLastError());std::vector<HingeState> out(inputs.size());
  check(cudaMemcpy(out.data(),p.states,out.size()*sizeof(HingeState),cudaMemcpyDeviceToHost));
  p.bound_profile=profile;p.profile_bound=true;
  p.last_inputs.resize(p.state_capacity);
  for(size_t i=0;i<inputs.size();++i)if(inputs[i].valid&&out[i].status==0)p.last_inputs[i]=inputs[i];
  return out;
}
}
