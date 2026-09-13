#include <cuda_runtime.h>
#include "atomos/host.hpp"
#include <climits>
namespace atomos {namespace {
void cuda_check(cudaError_t c,const char*what){if(c!=cudaSuccess)throw std::runtime_error(std::string(what)+": "+cudaGetErrorString(c));}
#define AO_CUDA(x) cuda_check((x),#x)
template<class T> class Buffer {
 T*p_=nullptr;std::size_t count_;
public:
 explicit Buffer(std::size_t n):count_(n){if(n)AO_CUDA(cudaMalloc(reinterpret_cast<void**>(&p_),n*sizeof(T)));}
 ~Buffer(){if(p_)cudaFree(p_);}Buffer(const Buffer&)=delete;Buffer&operator=(const Buffer&)=delete;
 T*get()const{return p_;}void upload(const T*src){if(count_)AO_CUDA(cudaMemcpy(p_,src,count_*sizeof(T),cudaMemcpyHostToDevice));}
 void download(T*dst){if(count_)AO_CUDA(cudaMemcpy(dst,p_,count_*sizeof(T),cudaMemcpyDeviceToHost));}
};
class Texture {
 cudaTextureObject_t handle_=0;
public:
 template<class T> Texture(T*data,std::size_t count){cudaResourceDesc r{};r.resType=cudaResourceTypeLinear;r.res.linear.devPtr=data;r.res.linear.desc=cudaCreateChannelDesc<T>();r.res.linear.sizeInBytes=count*sizeof(T);
  cudaTextureDesc t{};t.readMode=cudaReadModeElementType;t.filterMode=cudaFilterModePoint;t.normalizedCoords=0;t.addressMode[0]=cudaAddressModeClamp;AO_CUDA(cudaCreateTextureObject(&handle_,&r,&t,nullptr));}
 ~Texture(){if(handle_)cudaDestroyTextureObject(handle_);}Texture(const Texture&)=delete;Texture&operator=(const Texture&)=delete;cudaTextureObject_t get()const{return handle_;}
};
class Event {cudaEvent_t event_{};public:Event(){AO_CUDA(cudaEventCreate(&event_));}~Event(){cudaEventDestroy(event_);}Event(const Event&)=delete;Event&operator=(const Event&)=delete;cudaEvent_t get()const{return event_;}};
struct Device {cudaDeviceProp prop{};std::size_t free=0,total=0;int runtime=0,driver=0;};
Device inspect(int ordinal){int n=0;AO_CUDA(cudaGetDeviceCount(&n));if(ordinal<0||ordinal>=n)throw std::invalid_argument("CUDA device ordinal unavailable");AO_CUDA(cudaSetDevice(ordinal));AO_CUDA(cudaFree(nullptr));Device d;AO_CUDA(cudaGetDeviceProperties(&d.prop,ordinal));AO_CUDA(cudaMemGetInfo(&d.free,&d.total));AO_CUDA(cudaRuntimeGetVersion(&d.runtime));AO_CUDA(cudaDriverGetVersion(&d.driver));return d;}
std::string device_record(const Device&d){std::ostringstream s;s<<"{\"name\":"<<json_string(d.prop.name)<<",\"cc_major\":"<<d.prop.major<<",\"cc_minor\":"<<d.prop.minor<<",\"total_bytes\":"<<d.total<<",\"free_bytes_at_start\":"<<d.free<<",\"runtime\":"<<d.runtime<<",\"driver\":"<<d.driver<<",\"max_texture_1d_linear\":"<<d.prop.maxTexture1DLinear<<"}";return s.str();}
__global__ void atomos_epoch_texture(Config c,const State*state,const Lane*input,cudaTextureObject_t asa,cudaTextureObject_t na,cudaTextureObject_t boundary,cudaTextureObject_t fringe,Result*out){
 const u32 i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=c.shape.rows*c.shape.words)return;
 const u32 r=i/c.shape.words,w=i%c.shape.words,k=address(c.shape,r,w,c.layout);
 out[i]=epoch_word(state[i],input[i],tex1Dfetch<unsigned int>(asa,int(k)),tex1Dfetch<unsigned int>(na,int(k)),tex1Dfetch<unsigned int>(boundary,int(k)),tex1Dfetch<unsigned int>(fringe,int(k)),valid_mask(c.shape,w),c.producer,c.fringe);
}
__global__ void atomos_epoch_global(Config c,const State*state,const Lane*input,const u32*asa,const u32*na,const u32*boundary,const u32*fringe,Result*out){
 const u32 i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=c.shape.rows*c.shape.words)return;
 const u32 r=i/c.shape.words,w=i%c.shape.words,k=address(c.shape,r,w,c.layout);
 out[i]=epoch_word(state[i],input[i],asa[k],na[k],boundary[k],fringe[k],valid_mask(c.shape,w),c.producer,c.fringe);
}
__global__ void atomos_epoch_packed(Config c,const State*state,const Lane*input,cudaTextureObject_t masks,Result*out){
 const u32 i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=c.shape.rows*c.shape.words)return;
 const u32 r=i/c.shape.words,w=i%c.shape.words,k=address(c.shape,r,w,c.layout);
 const uint4 m=tex1Dfetch<uint4>(masks,int(k));
 out[i]=epoch_word(state[i],input[i],m.x,m.y,m.z,m.w,valid_mask(c.shape,w),c.producer,c.fringe);
}
class CudaBackend final:public Backend {
 const Fixture&fixture_;Device device_;bool texture_,packed_,max_l1_;u32 block_size_;double ms_=0;cudaFuncAttributes attributes_{};int active_blocks_=0;
 // Members are destroyed in reverse order: texture objects before backing buffers.
 std::unique_ptr<Buffer<u32>> am_,nm_,bm_,fm_;
 std::unique_ptr<Buffer<uint4>> packed_masks_;
 std::unique_ptr<Buffer<Lane>> input_;std::unique_ptr<Buffer<State>> state_;std::unique_ptr<Buffer<Result>> output_;
 std::unique_ptr<Texture> ta_,tn_,tb_,tf_,tp_;std::unique_ptr<Event> start_,stop_;
 void launch(){const auto c=fixture_.config;const u32 blocks=(u32(logical(c.shape))+block_size_-1)/block_size_;
  if(packed_)atomos_epoch_packed<<<blocks,block_size_>>>(c,state_->get(),input_->get(),tp_->get(),output_->get());
  else if(texture_)atomos_epoch_texture<<<blocks,block_size_>>>(c,state_->get(),input_->get(),ta_->get(),tn_->get(),tb_->get(),tf_->get(),output_->get());
  else atomos_epoch_global<<<blocks,block_size_>>>(c,state_->get(),input_->get(),am_->get(),nm_->get(),bm_->get(),fm_->get(),output_->get());
  AO_CUDA(cudaGetLastError());}
public:
 CudaBackend(const Fixture&f,int id,bool tex,u64 budget,u64 reserve,bool packed,bool max_l1,u32 block_size):fixture_(f),device_(inspect(id)),texture_(tex),packed_(packed),max_l1_(max_l1),block_size_(block_size){
  if((packed&&!tex)||(block_size!=64&&block_size!=128&&block_size!=256))throw std::invalid_argument("invalid CUDA read/block configuration");
  const auto n=std::size_t(stored(f.config.shape)),l=std::size_t(logical(f.config.shape));
  if(!allowed(plan(f.config.shape),device_.free,device_.total,budget,reserve))throw std::runtime_error("device-memory budget refused before allocation");
  if(n>std::size_t(INT_MAX)||(tex&&n>std::size_t(device_.prop.maxTexture1DLinear)))throw std::runtime_error("texture index/length limit exceeded");
  if(packed){
   std::vector<uint4> masks(n);for(std::size_t k=0;k<n;++k)masks[k]=make_uint4(f.masks[0][k],f.masks[1][k],f.masks[2][k],f.masks[3][k]);
   packed_masks_=std::make_unique<Buffer<uint4>>(n);packed_masks_->upload(masks.data());tp_=std::make_unique<Texture>(packed_masks_->get(),n);
  }else{
   am_=std::make_unique<Buffer<u32>>(n);nm_=std::make_unique<Buffer<u32>>(n);bm_=std::make_unique<Buffer<u32>>(n);fm_=std::make_unique<Buffer<u32>>(n);
   am_->upload(f.masks[0].data());nm_->upload(f.masks[1].data());bm_->upload(f.masks[2].data());fm_->upload(f.masks[3].data());
   if(tex){ta_=std::make_unique<Texture>(am_->get(),n);tn_=std::make_unique<Texture>(nm_->get(),n);tb_=std::make_unique<Texture>(bm_->get(),n);tf_=std::make_unique<Texture>(fm_->get(),n);}
  }
  input_=std::make_unique<Buffer<Lane>>(l);state_=std::make_unique<Buffer<State>>(l);output_=std::make_unique<Buffer<Result>>(l);
  input_->upload(f.lanes.data());
  const void* kernel=packed?reinterpret_cast<const void*>(atomos_epoch_packed):tex?reinterpret_cast<const void*>(atomos_epoch_texture):reinterpret_cast<const void*>(atomos_epoch_global);
  AO_CUDA(cudaFuncSetAttribute(kernel,cudaFuncAttributePreferredSharedMemoryCarveout,max_l1?cudaSharedmemCarveoutMaxL1:cudaSharedmemCarveoutDefault));
  AO_CUDA(cudaFuncGetAttributes(&attributes_,kernel));
  AO_CUDA(cudaOccupancyMaxActiveBlocksPerMultiprocessor(&active_blocks_,kernel,int(block_size_),0));
  start_=std::make_unique<Event>();stop_=std::make_unique<Event>();
  state_->upload(f.initial.data());launch();AO_CUDA(cudaDeviceSynchronize()); // uncommitted warm-up
 }
 std::vector<Result> propose(const std::vector<State>&s)override{
  if(s.size()!=fixture_.lanes.size())throw std::invalid_argument("state length mismatch");
  for(std::size_t i=0;i<s.size();++i)validate_lane(fixture_.lanes[i],s[i]);
  state_->upload(s.data());AO_CUDA(cudaEventRecord(start_->get()));launch();AO_CUDA(cudaEventRecord(stop_->get()));AO_CUDA(cudaEventSynchronize(stop_->get()));
  float ms=0;AO_CUDA(cudaEventElapsedTime(&ms,start_->get(),stop_->get()));ms_=ms;
  std::vector<Result> result(s.size());output_->download(result.data());return result;
 }
 double last_ms()const override{return ms_;}std::string device_json()const override{
  auto base=device_record(device_);base.pop_back();std::ostringstream s;s<<base<<",\"multiprocessors\":"<<device_.prop.multiProcessorCount<<",\"l2_bytes\":"<<device_.prop.l2CacheSize
   <<",\"kernel\":{\"name\":"<<json_string(packed_?"atomos_epoch_packed":texture_?"atomos_epoch_texture":"atomos_epoch_global")
   <<",\"block_size\":"<<block_size_<<",\"grid_blocks\":"<<(logical(fixture_.config.shape)+block_size_-1)/block_size_
   <<",\"registers_per_thread\":"<<attributes_.numRegs<<",\"local_bytes_per_thread\":"<<attributes_.localSizeBytes<<",\"static_shared_bytes\":"<<attributes_.sharedSizeBytes
   <<",\"preferred_shared_carveout\":"<<attributes_.preferredShmemCarveout<<",\"max_l1_requested\":"<<(max_l1_?"true":"false")
   <<",\"active_blocks_per_sm_limit\":"<<active_blocks_<<",\"mask_bytes\":"<<16*stored(fixture_.config.shape)<<"}}";return s.str();}
};
}
std::unique_ptr<Backend> make_cuda_backend(const Fixture&f,int id,bool texture,u64 budget,u64 reserve,bool packed,bool max_l1,u32 block_size){return std::make_unique<CudaBackend>(f,id,texture,budget,reserve,packed,max_l1,block_size);}
std::string probe_cuda(int device){return device_record(inspect(device));}
}
