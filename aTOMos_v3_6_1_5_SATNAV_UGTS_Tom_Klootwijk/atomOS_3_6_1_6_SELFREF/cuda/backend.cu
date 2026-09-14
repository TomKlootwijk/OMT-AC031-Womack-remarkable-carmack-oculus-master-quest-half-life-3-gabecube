#include "backend.hpp"
#include <cuda_runtime.h>
#include <algorithm>
#include <sstream>
#include <stdexcept>
#include <limits>
#include <cstring>
#include <memory>
namespace satnav {
namespace {
void check(cudaError_t s,const char* where){if(s!=cudaSuccess)throw std::runtime_error(std::string(where)+": "+cudaGetErrorString(s));}
template<class T> struct Buffer {
 T* p{};explicit Buffer(std::size_t n){check(cudaMalloc(reinterpret_cast<void**>(&p),n*sizeof(T)),"cudaMalloc");}
 ~Buffer(){if(p)cudaFree(p);}Buffer(const Buffer&)=delete;Buffer& operator=(const Buffer&)=delete;
};
struct Event {cudaEvent_t value{};Event(){check(cudaEventCreate(&value),"cudaEventCreate");}~Event(){if(value)cudaEventDestroy(value);}Event(const Event&)=delete;};
struct Texture {
 cudaTextureObject_t value{};
 Texture(double* ptr,std::size_t elements){
  cudaResourceDesc r{};r.resType=cudaResourceTypeLinear;r.res.linear.devPtr=ptr;
  r.res.linear.desc=cudaCreateChannelDesc<int2>();r.res.linear.sizeInBytes=elements*sizeof(double);
  cudaTextureDesc t{};t.readMode=cudaReadModeElementType;t.filterMode=cudaFilterModePoint;t.normalizedCoords=0;
  check(cudaCreateTextureObject(&value,&r,&t,nullptr),"cudaCreateTextureObject");
 }
 ~Texture(){if(value)cudaDestroyTextureObject(value);}Texture(const Texture&)=delete;
};
struct TextureReader {
 cudaTextureObject_t data;std::size_t epochs;
 SAT_HD double get(std::size_t epoch,int ch,int field)const{
#ifdef __CUDA_ARCH__
  const auto index=(std::size_t(ch)*FIELDS+field)*epochs+epoch;
  const int2 pair=tex1Dfetch<int2>(data,static_cast<int>(index));return __hiloint2double(pair.y,pair.x);
#else
  (void)epoch;(void)ch;(void)field;
  throw std::logic_error("TextureReader is a device-only data source");
#endif
 }
};
template<class Reader> __global__ void pvt_kernel(const Epoch* epochs,std::size_t count,Reader observations,Config config,Result* output){
 const std::size_t e=std::size_t(blockIdx.x)*blockDim.x+threadIdx.x;
 if(e<count)output[e]=solve_epoch(epochs[e],observations,e,config);
}
std::string device_report(int device){
 cudaDeviceProp p{};check(cudaGetDeviceProperties(&p,device),"cudaGetDeviceProperties");
 std::size_t free=0,total=0;check(cudaMemGetInfo(&free,&total),"cudaMemGetInfo");
 int driver=0,runtime=0;check(cudaDriverGetVersion(&driver),"cudaDriverGetVersion");check(cudaRuntimeGetVersion(&runtime),"cudaRuntimeGetVersion");
 std::ostringstream o;o<<"{\"name\":\"";
 for(const char* c=p.name;*c;++c){if(*c=='"'||*c=='\\')o<<'\\';o<<*c;}
 o<<"\",\"capability_major\":"<<p.major<<",\"capability_minor\":"<<p.minor
 <<",\"free_bytes\":"<<free<<",\"total_bytes\":"<<total<<",\"driver_version\":"<<driver
 <<",\"runtime_version\":"<<runtime<<",\"linear_texture_texels\":"<<p.maxTexture1DLinear<<"}";return o.str();
}
}
std::string cuda_probe(int device){check(cudaSetDevice(device),"cudaSetDevice");check(cudaFree(nullptr),"CUDA context");return device_report(device);}
Run cuda_run(const Data& data,const Config& config,int device,bool use_texture,std::size_t budget,std::size_t reserve){
 if(data.epochs.empty())throw std::invalid_argument("empty epoch list");
 check(cudaSetDevice(device),"cudaSetDevice");check(cudaFree(nullptr),"CUDA context");
 cudaDeviceProp prop{};check(cudaGetDeviceProperties(&prop,device),"cudaGetDeviceProperties");
 if(prop.major!=12||prop.minor!=0)throw std::runtime_error("This build targets SM120; rebuild CUDA_ARCHITECTURES for a different device");
 Run run;run.backend=use_texture?"cuda_texture":"cuda_global";run.device_json=device_report(device);run.results.resize(data.epochs.size());
 std::size_t free=0,total=0;check(cudaMemGetInfo(&free,&total),"cudaMemGetInfo");
 constexpr std::size_t margin=64u*1024u*1024u;
 if(total<=reserve||free<=margin||budget<=margin)throw std::runtime_error("Insufficient budget/free VRAM for planned reserve and margin");
 const std::size_t allowed=std::min(budget,std::min((free/10)*7,total-reserve));
 if(allowed<=margin)throw std::runtime_error("No usable allocation budget after planning margin");
 constexpr std::size_t per=CHANNELS*FIELDS*sizeof(double)+sizeof(Epoch)+sizeof(Result);
 std::size_t capacity=std::min(data.epochs.size(),(allowed-margin)/per);
 capacity=std::min(capacity,std::size_t(65536));
 if(use_texture){capacity=std::min(capacity,std::size_t(prop.maxTexture1DLinear)/(CHANNELS*FIELDS));capacity=std::min(capacity,std::size_t(std::numeric_limits<int>::max())/(CHANNELS*FIELDS));}
 if(capacity==0)throw std::runtime_error("Budget cannot fit one independent epoch");
 Buffer<Epoch> epochs(capacity);Buffer<double> observations(capacity*CHANNELS*FIELDS);Buffer<Result> output(capacity);
 // Resource destroyed before its buffer. Texels are bitwise int2 representations of FP64.
 std::unique_ptr<Texture> texture;
 if(use_texture)texture=std::make_unique<Texture>(observations.p,capacity*CHANNELS*FIELDS);
 Event start,stop;std::vector<double> packed(capacity*CHANNELS*FIELDS);
 const std::size_t total_epochs=data.epochs.size();
 for(std::size_t first=0;first<total_epochs;first+=capacity){
  const std::size_t count=std::min(capacity,total_epochs-first);
  for(int f=0;f<CHANNELS*FIELDS;++f)std::copy_n(data.observations.data()+std::size_t(f)*total_epochs+first,count,packed.data()+std::size_t(f)*count);
  check(cudaMemcpy(epochs.p,data.epochs.data()+first,count*sizeof(Epoch),cudaMemcpyHostToDevice),"copy epochs");
  check(cudaMemcpy(observations.p,packed.data(),count*CHANNELS*FIELDS*sizeof(double),cudaMemcpyHostToDevice),"copy observations");
  const unsigned blocks=static_cast<unsigned>((count+127)/128);
  auto launch=[&](){if(use_texture)pvt_kernel<<<blocks,128>>>(epochs.p,count,TextureReader{texture->value,count},config,output.p);else pvt_kernel<<<blocks,128>>>(epochs.p,count,GlobalReader{observations.p,count},config,output.p);check(cudaGetLastError(),"pvt kernel launch");};
  if(first==0){launch();check(cudaDeviceSynchronize(),"warmup synchronize");}
  check(cudaEventRecord(start.value),"start event");launch();check(cudaEventRecord(stop.value),"stop event");check(cudaEventSynchronize(stop.value),"kernel synchronize");
  float elapsed=0;check(cudaEventElapsedTime(&elapsed,start.value,stop.value),"event elapsed");run.kernel_ms+=elapsed;
  check(cudaMemcpy(run.results.data()+first,output.p,count*sizeof(Result),cudaMemcpyDeviceToHost),"copy results");
 }
 return run;
}
}
