#include <cuda_runtime.h>
#include "atomos/batch.hpp"
#include <algorithm>
#include <climits>
#include <sstream>
#include <stdexcept>
#include <vector>
namespace ao {
namespace {
void checked(cudaError_t e,const char* where){if(e!=cudaSuccess)throw std::runtime_error(std::string(where)+": "+cudaGetErrorString(e));}
struct Allocation {void* p=nullptr;explicit Allocation(std::size_t n){checked(cudaMalloc(&p,n),"cudaMalloc");}~Allocation(){if(p)cudaFree(p);}Allocation(const Allocation&)=delete;Allocation&operator=(const Allocation&)=delete;};
struct Event {cudaEvent_t e{};Event(){checked(cudaEventCreate(&e),"cudaEventCreate");}~Event(){cudaEventDestroy(e);}};
struct Texture {cudaTextureObject_t t=0;Texture(double* p,std::size_t bytes,bool create){if(!create)return;cudaResourceDesc r{};r.resType=cudaResourceTypeLinear;r.res.linear.devPtr=p;r.res.linear.desc=cudaCreateChannelDesc<int2>();r.res.linear.sizeInBytes=bytes;
 cudaTextureDesc d{};d.readMode=cudaReadModeElementType;checked(cudaCreateTextureObject(&t,&r,&d,nullptr),"cudaCreateTextureObject");}~Texture(){if(t)cudaDestroyTextureObject(t);}};
struct GlobalReader {const double* p;std::size_t stride,index;__device__ double v(unsigned component,unsigned slot)const{return p[(component*max_sats+slot)*stride+index];}__device__ Observation get(unsigned slot)const{return {v(0,slot),v(1,slot),v(2,slot),v(3,slot),v(4,slot)};}};
struct TextureReader {cudaTextureObject_t t;std::size_t stride,index;__device__ double v(unsigned component,unsigned slot)const{int2 bits=tex1Dfetch<int2>(t,int((component*max_sats+slot)*stride+index));return __hiloint2double(bits.y,bits.x);}__device__ Observation get(unsigned slot)const{return {v(0,slot),v(1,slot),v(2,slot),v(3,slot),v(4,slot)};}};
__global__ void solve_global(const double* p,const Epoch* e,Solution* out,std::size_t n,SolveConfig cfg){std::size_t i=std::size_t(blockIdx.x)*blockDim.x+threadIdx.x;if(i<n)out[i]=solve(GlobalReader{p,n,i},e[i],cfg);}
__global__ void solve_texture(cudaTextureObject_t t,const Epoch* e,Solution* out,std::size_t n,SolveConfig cfg){std::size_t i=std::size_t(blockIdx.x)*blockDim.x+threadIdx.x;if(i<n)out[i]=solve(TextureReader{t,n,i},e[i],cfg);}
__global__ void decorate(const Solution* s,const Epoch* e,Diagnostic* out,std::size_t n,GeoConfig geo,bool has_prev,Solution previous,Epoch pe){std::size_t i=std::size_t(blockIdx.x)*blockDim.x+threadIdx.x;if(i<n){const Solution* p=i?&s[i-1]:has_prev?&previous:nullptr;const Epoch* pmeta=i?&e[i-1]:has_prev?&pe:nullptr;out[i]=enrich(s[i],e[i],p,pmeta,geo);}}
}
std::string cuda_probe(){int id=0;checked(cudaGetDevice(&id),"cudaGetDevice");cudaDeviceProp p{};checked(cudaGetDeviceProperties(&p,id),"cudaGetDeviceProperties");std::size_t free=0,total=0;checked(cudaMemGetInfo(&free,&total),"cudaMemGetInfo");int driver=0,runtime=0;checked(cudaDriverGetVersion(&driver),"driver version");checked(cudaRuntimeGetVersion(&runtime),"runtime version");std::ostringstream o;o<<"device="<<p.name<<" cc="<<p.major<<'.'<<p.minor<<" free_bytes="<<free<<" total_bytes="<<total<<" max_linear_texture_elements="<<p.maxTexture1DLinear<<" driver="<<driver<<" runtime="<<runtime;return o.str();}
BatchResult cuda_run(const std::vector<Frame>& f,const SolveConfig& cfg,const GeoConfig& geo,bool texture,std::size_t chunk,std::size_t budget){
 if(f.empty()||!chunk||!budget)throw std::runtime_error("empty batch or zero allocation request");BatchResult r;r.device=cuda_probe();r.solutions.resize(f.size());r.diagnostics.resize(f.size());
 int id=0;checked(cudaGetDevice(&id),"cudaGetDevice");cudaDeviceProp prop{};checked(cudaGetDeviceProperties(&prop,id),"cudaGetDeviceProperties");
 const std::size_t bytes_per=5*max_sats*sizeof(double)+sizeof(Epoch)+sizeof(Solution)+sizeof(Diagnostic);
 bool warmed=false;
 for(std::size_t start=0;start<f.size();){std::size_t free=0,total=0;checked(cudaMemGetInfo(&free,&total),"cudaMemGetInfo");std::size_t available=std::min(budget,(free/10)*6);std::size_t n=std::min({chunk,f.size()-start,available/bytes_per});
  if(texture)n=std::min(n,std::size_t(std::min(prop.maxTexture1DLinear,INT_MAX))/(5*max_sats));if(!n)throw std::runtime_error("insufficient free memory or texture address range for one epoch");
  std::vector<double> packed(5*max_sats*n,0);std::vector<Epoch> meta(n);
  for(std::size_t i=0;i<n;++i){meta[i]=f[start+i].epoch;for(unsigned j=0;j<meta[i].count;++j){auto o=f[start+i].obs[j];const double v[5]={o.x,o.y,o.z,o.code,o.sigma};for(unsigned k=0;k<5;++k)packed[(k*max_sats+j)*n+i]=v[k];}}
  Allocation input(packed.size()*sizeof(double)),epochs(n*sizeof(Epoch)),output(n*sizeof(Solution)),diagnostic(n*sizeof(Diagnostic));
  checked(cudaMemcpy(input.p,packed.data(),packed.size()*sizeof(double),cudaMemcpyHostToDevice),"upload observations");checked(cudaMemcpy(epochs.p,meta.data(),n*sizeof(Epoch),cudaMemcpyHostToDevice),"upload epochs");
  Texture tex(static_cast<double*>(input.p),packed.size()*sizeof(double),texture);unsigned blocks=unsigned((n+127)/128);
  auto launch=[&](){if(texture)solve_texture<<<blocks,128>>>(tex.t,static_cast<Epoch*>(epochs.p),static_cast<Solution*>(output.p),n,cfg);else solve_global<<<blocks,128>>>(static_cast<double*>(input.p),static_cast<Epoch*>(epochs.p),static_cast<Solution*>(output.p),n,cfg);checked(cudaGetLastError(),"solve launch");};
  if(!warmed){launch();checked(cudaDeviceSynchronize(),"warm-up synchronize");warmed=true;}
  Event begin,end;checked(cudaEventRecord(begin.e),"record start");launch();Solution previous{};Epoch pe{};if(start){previous=r.solutions[start-1];pe=f[start-1].epoch;}
  decorate<<<blocks,128>>>(static_cast<Solution*>(output.p),static_cast<Epoch*>(epochs.p),static_cast<Diagnostic*>(diagnostic.p),n,geo,start>0,previous,pe);checked(cudaGetLastError(),"enrich launch");checked(cudaEventRecord(end.e),"record end");checked(cudaEventSynchronize(end.e),"complete kernels");float ms=0;checked(cudaEventElapsedTime(&ms,begin.e,end.e),"event timing");r.compute_ms+=ms;
  checked(cudaMemcpy(r.solutions.data()+start,output.p,n*sizeof(Solution),cudaMemcpyDeviceToHost),"copy solutions");checked(cudaMemcpy(r.diagnostics.data()+start,diagnostic.p,n*sizeof(Diagnostic),cudaMemcpyDeviceToHost),"copy diagnostics");start+=n;
 }
 return r;
}
}
