#include "atomos/resident_index.hpp"
#include "atomos/resident_kernels.cuh"
#include "atomos/spatial_index.hpp"
#include <algorithm>
#include <cfenv>
#include <chrono>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace atomos {
namespace {
using Clock=std::chrono::steady_clock;
double elapsed(Clock::time_point start){return std::chrono::duration<double,std::milli>(Clock::now()-start).count();}
void check(cudaError_t e){if(e!=cudaSuccess)throw std::runtime_error(cudaGetErrorString(e));}
void nearest_mode(){if(std::fegetround()!=FE_TONEAREST)throw std::runtime_error("resident source/predicate contract requires FE_TONEAREST");}
float lower_float(double x){float f=float(x);return double(f)>x?std::nextafter(f,-INFINITY):f;}
float upper_float(double x){float f=float(x);return double(f)<x?std::nextafter(f,INFINITY):f;}
cudaTextureObject_t make_texture(void* pointer,size_t bytes){
  if(!bytes)return 0;
  int device=0;cudaDeviceProp props{};check(cudaGetDevice(&device));check(cudaGetDeviceProperties(&props,device));
  if(bytes%sizeof(uint4)||bytes/sizeof(uint4)>size_t(props.maxTexture1DLinear)||bytes/sizeof(uint4)>size_t(INT32_MAX))
    throw std::length_error("resident texture exceeds device/signed texel-index capacity");
  cudaResourceDesc resource{};resource.resType=cudaResourceTypeLinear;
  resource.res.linear.devPtr=pointer;resource.res.linear.desc=cudaCreateChannelDesc<uint4>();resource.res.linear.sizeInBytes=bytes;
  cudaTextureDesc desc{};desc.readMode=cudaReadModeElementType;desc.filterMode=cudaFilterModePoint;desc.normalizedCoords=0;
  cudaTextureObject_t texture=0;check(cudaCreateTextureObject(&texture,&resource,&desc,nullptr));return texture;
}
}

struct ResidentIndex::Impl {
  SpatialIndex host;
  ResidentStats timing;
  ResidentDeviceView view;
  ResidentNode* nodes=nullptr;
  Point* points=nullptr;
  ResidentQuery* queries=nullptr;
  ResidentCount* counts=nullptr;
  cudaEvent_t start=nullptr,end=nullptr;
  std::vector<ResidentRadiusRequest> host_queries;
  std::vector<ResidentCount> cache;
  bool uploaded=false,evaluated=false,cache_valid=false;

  void release() noexcept {
    if(view.node_texture)cudaDestroyTextureObject(view.node_texture);
    if(view.point_texture)cudaDestroyTextureObject(view.point_texture);
    if(view.query_texture)cudaDestroyTextureObject(view.query_texture);
    cudaFree(nodes);cudaFree(points);cudaFree(queries);cudaFree(counts);
    if(start)cudaEventDestroy(start);if(end)cudaEventDestroy(end);
  }
  ~Impl(){release();}
  explicit Impl(const SpatialIndex& source):host(source){
    try{
      nearest_mode();const auto began=Clock::now();
      std::vector<ResidentNode> flat;flat.reserve(host.nodes().size());
      for(const auto& n:host.nodes()){
        ResidentNode item{};
        for(int a=0;a<3;++a){item.lower[a]=lower_float(n.lower[a]);item.upper[a]=upper_float(n.upper[a]);}
        item.left=n.left;item.right=n.right;item.begin=n.begin;item.count=n.count;item.axis=n.axis;flat.push_back(item);
      }
      if(!flat.empty()){
        auto escape=[&](auto&& self,uint32_t i,uint32_t successor)->void{
          flat[i].escape=successor;
          if(!flat[i].count){self(self,flat[i].left,flat[i].right);self(self,flat[i].right,successor);}
        };escape(escape,0,uint32_t(flat.size()));
      }
      const size_t node_bytes=flat.size()*sizeof(ResidentNode),point_bytes=host.size()*sizeof(Point);
      if(node_bytes){check(cudaMalloc(reinterpret_cast<void**>(&nodes),node_bytes));check(cudaMemcpy(nodes,flat.data(),node_bytes,cudaMemcpyHostToDevice));}
      if(point_bytes){check(cudaMalloc(reinterpret_cast<void**>(&points),point_bytes));check(cudaMemcpy(points,host.points().data(),point_bytes,cudaMemcpyHostToDevice));}
      view.nodes=nodes;view.points=points;view.node_count=uint32_t(flat.size());view.point_count=uint32_t(host.size());
      view.node_texture=make_texture(nodes,node_bytes);view.point_texture=make_texture(points,point_bytes);
      check(cudaEventCreate(&start));check(cudaEventCreate(&end));
      timing.source_resident_bytes=node_bytes+point_bytes;timing.source_upload_ms=elapsed(began);
    }catch(...){release();throw;}
  }
  void capture(){
    if(!evaluated)throw std::logic_error("evaluate the ordinary resident query epoch before readback");
    const auto began=Clock::now();cache.resize(view.query_count);
    if(!cache.empty())check(cudaMemcpy(cache.data(),counts,cache.size()*sizeof(ResidentCount),cudaMemcpyDeviceToHost));
    for(const auto& count:cache)
      if(count.definite_inside>view.point_count||count.unresolved>view.point_count-count.definite_inside)
        throw std::runtime_error("resident result violates count partition");
    timing.readback_bytes=cache.size()*sizeof(ResidentCount);timing.readback_ms=elapsed(began);cache_valid=true;
  }
};

ResidentIndex::ResidentIndex(const SpatialIndex& source):impl_(new Impl(source)){}
ResidentIndex::~ResidentIndex()=default;
ResidentIndex::ResidentIndex(ResidentIndex&&) noexcept=default;
ResidentIndex& ResidentIndex::operator=(ResidentIndex&&) noexcept=default;
const ResidentStats& ResidentIndex::stats()const{return impl_->timing;}

void ResidentIndex::upload_queries(const std::vector<ResidentRadiusRequest>& input){
  nearest_mode();auto& p=*impl_;
  if(p.uploaded)throw std::logic_error("resident query table is immutable; create a new epoch object");
  if(input.size()>size_t(INT32_MAX)||input.size()>SIZE_MAX/sizeof(ResidentQuery))
    throw std::length_error("resident query table exceeds address contract");
  const auto began=Clock::now();
  std::vector<ResidentRadiusRequest> copy=input;
  std::vector<ResidentQuery> records;records.reserve(input.size());
  for(const auto& r:input){
    SpatialIndex::validate_point(r.point);
    if(!std::isfinite(r.chord_radius2)||r.chord_radius2<0||r.chord_radius2>4)
      throw std::invalid_argument("resident squared chord radius must lie in [0,4]");
    records.push_back({r.point.x,r.point.y,r.point.z,r.chord_radius2});
  }
  ResidentQuery* queries=nullptr;ResidentCount* counts=nullptr;cudaTextureObject_t texture=0;
  try{
    if(!records.empty()){
      check(cudaMalloc(reinterpret_cast<void**>(&queries),records.size()*sizeof(ResidentQuery)));
      check(cudaMalloc(reinterpret_cast<void**>(&counts),records.size()*sizeof(ResidentCount)));
      check(cudaMemcpy(queries,records.data(),records.size()*sizeof(ResidentQuery),cudaMemcpyHostToDevice));
      texture=make_texture(queries,records.size()*sizeof(ResidentQuery));
    }
  }catch(...){if(texture)cudaDestroyTextureObject(texture);cudaFree(queries);cudaFree(counts);throw;}
  p.host_queries.swap(copy);p.queries=queries;p.counts=counts;
  p.view.queries=queries;p.view.counts=counts;p.view.query_texture=texture;p.view.query_count=uint32_t(input.size());
  p.timing.query_resident_bytes=records.size()*(sizeof(ResidentQuery)+sizeof(ResidentCount));
  p.timing.query_upload_ms=elapsed(began);p.uploaded=true;
}

double ResidentIndex::evaluate(bool texture_fetch,uint32_t repetitions){
  auto& p=*impl_;if(!p.uploaded)throw std::logic_error("upload the immutable query table first");
  if(!repetitions)throw std::invalid_argument("resident repetitions must be positive");
  if(p.view.query_count&&repetitions>UINT64_MAX-p.timing.launches)throw std::overflow_error("resident launch epoch overflow");
  const auto began=Clock::now();p.evaluated=false;p.cache_valid=false;
  p.timing.readback_ms=0;p.timing.readback_bytes=0;p.timing.fallback_ms=0;
  p.timing.fallback_queries=0;p.timing.fallback_predicate_calls=0;
  float milliseconds=0;
  if(p.view.query_count){
    check(cudaEventRecord(p.start));
    for(uint32_t i=0;i<repetitions;++i)launch_resident_radius(p.view,texture_fetch);
    check(cudaGetLastError());check(cudaEventRecord(p.end));check(cudaEventSynchronize(p.end));
    check(cudaEventElapsedTime(&milliseconds,p.start,p.end));
  }
  if(p.view.query_count)p.timing.launches+=repetitions;
  p.timing.kernel_total_ms=milliseconds;
  p.timing.kernel_per_launch_ms=double(milliseconds)/repetitions;
  p.timing.evaluate_wall_ms=elapsed(began);p.evaluated=true;return p.timing.kernel_per_launch_ms;
}

std::vector<ResidentCount> ResidentIndex::readback_counts(){impl_->capture();return impl_->cache;}
std::vector<uint64_t> ResidentIndex::resolve_exact(){
  nearest_mode();auto& p=*impl_;if(!p.cache_valid)p.capture();
  const auto began=Clock::now();std::vector<uint64_t> exact;exact.reserve(p.cache.size());
  p.timing.fallback_queries=0;p.timing.fallback_predicate_calls=0;
  for(size_t i=0;i<p.cache.size();++i){
    const auto count=p.cache[i];
    if(!count.unresolved){exact.push_back(count.definite_inside);continue;}
    QueryStats stats;
    const uint64_t resolved=p.host.radius_count(p.host_queries[i].point,p.host_queries[i].chord_radius2,&stats);
    if(resolved<count.definite_inside||resolved>count.definite_inside+count.unresolved)
      throw std::runtime_error("exact fallback contradicts resident count certificate");
    exact.push_back(resolved);++p.timing.fallback_queries;p.timing.fallback_predicate_calls+=stats.predicate_calls;
  }
  p.timing.fallback_ms=elapsed(began);return exact;
}
ResidentDeviceView ResidentIndex::device_view(){
  auto& p=*impl_;if(!p.uploaded)throw std::logic_error("upload immutable query alternatives first");
  p.evaluated=false;p.cache_valid=false;return p.view;
}
} // namespace atomos
