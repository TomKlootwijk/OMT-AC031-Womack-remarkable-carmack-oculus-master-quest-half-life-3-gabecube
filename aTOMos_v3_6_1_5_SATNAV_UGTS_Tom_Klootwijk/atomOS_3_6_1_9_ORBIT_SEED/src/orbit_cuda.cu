#include "orbit_backend.hpp"
#include <cuda_runtime.h>
#include <limits>
#include <sstream>
#include <stdexcept>
namespace orbit { namespace {
void check(cudaError_t error,const char* where){if(error!=cudaSuccess)throw std::runtime_error(std::string(where)+": "+cudaGetErrorString(error));}
template<class T>struct Buffer {T* p{};explicit Buffer(std::size_t count){if(count>std::numeric_limits<std::size_t>::max()/sizeof(T))throw std::length_error("CUDA size overflow");if(count)check(cudaMalloc(reinterpret_cast<void**>(&p),count*sizeof(T)),"cudaMalloc");}~Buffer(){if(p)cudaFree(p);}Buffer(const Buffer&)=delete;Buffer& operator=(const Buffer&)=delete;};
struct Event {cudaEvent_t value{};Event(){check(cudaEventCreate(&value),"cudaEventCreate");}~Event(){if(value)cudaEventDestroy(value);}Event(const Event&)=delete;Event& operator=(const Event&)=delete;};
__global__ void propagate(Model model,const double* times,std::size_t count,Query* result){const std::size_t i=static_cast<std::size_t>(blockIdx.x)*blockDim.x+threadIdx.x;if(i<count)result[i]=from_epoch(model,times[i]);}
__global__ void word_kernel(Words words,WordTrace* result){if(blockIdx.x==0&&threadIdx.x==0)*result=transition(words);}
std::string device_info(int device){cudaDeviceProp property{};check(cudaGetDeviceProperties(&property,device),"device properties");int driver=0,runtime=0;check(cudaDriverGetVersion(&driver),"driver version");check(cudaRuntimeGetVersion(&runtime),"runtime version");cudaFuncAttributes attributes{};check(cudaFuncGetAttributes(&attributes,propagate),"orbit kernel attributes");std::size_t stack=0;check(cudaDeviceGetLimit(&stack,cudaLimitStackSize),"device stack limit");std::ostringstream out;out<<"{\"index\":"<<device<<",\"name\":\"";for(const char* p=property.name;*p;++p){if(*p=='"'||*p=='\\')out<<'\\';out<<*p;}out<<"\",\"capability_major\":"<<property.major<<",\"capability_minor\":"<<property.minor<<",\"runtime_version\":"<<runtime<<",\"driver_version\":"<<driver<<",\"query_mode\":\"independent_from_epoch\",\"kernel_registers_per_thread\":"<<attributes.numRegs<<",\"kernel_local_bytes_per_thread\":"<<attributes.localSizeBytes<<",\"kernel_static_shared_bytes\":"<<attributes.sharedSizeBytes<<",\"device_stack_limit_bytes\":"<<stack<<",\"model_parameter_bytes\":"<<sizeof(Model)<<"}";return out.str();}
}
Run cuda_queries(const HostModel& host,const std::vector<double>& times,int device){if(times.empty())throw std::invalid_argument("empty CUDA orbit batch");check(cudaSetDevice(device),"set device");Run out;out.device_json=device_info(device);out.queries.resize(times.size());
 Buffer<Segment> q(host.q.size()),sun(host.sun.size()),moon(host.moon.size()),eop(host.eop.size());
 if(!host.q.empty())check(cudaMemcpy(q.p,host.q.data(),host.q.size()*sizeof(Segment),cudaMemcpyHostToDevice),"copy Q");
 if(!host.sun.empty())check(cudaMemcpy(sun.p,host.sun.data(),host.sun.size()*sizeof(Segment),cudaMemcpyHostToDevice),"copy Sun");
 if(!host.moon.empty())check(cudaMemcpy(moon.p,host.moon.data(),host.moon.size()*sizeof(Segment),cudaMemcpyHostToDevice),"copy Moon");
 if(!host.eop.empty())check(cudaMemcpy(eop.p,host.eop.data(),host.eop.size()*sizeof(Segment),cudaMemcpyHostToDevice),"copy EOP");
 Model model=host.model;model.q.segments=q.p;model.sun.segments=sun.p;model.moon.segments=moon.p;model.eop.segments=eop.p;
 Buffer<double> input(times.size());Buffer<Query> result(times.size());check(cudaMemcpy(input.p,times.data(),times.size()*sizeof(double),cudaMemcpyHostToDevice),"copy times");
 Event begin,end;check(cudaEventRecord(begin.value),"start event");propagate<<<static_cast<unsigned>((times.size()+127)/128),128>>>(model,input.p,times.size(),result.p);check(cudaGetLastError(),"orbit kernel launch");check(cudaEventRecord(end.value),"end event");check(cudaEventSynchronize(end.value),"orbit kernel completion");float elapsed=0;check(cudaEventElapsedTime(&elapsed,begin.value,end.value),"elapsed time");out.kernel_ms=elapsed;
 check(cudaMemcpy(out.queries.data(),result.p,times.size()*sizeof(Query),cudaMemcpyDeviceToHost),"copy orbit queries");return out;
}
WordTrace cuda_transition(const Words& words,int device){check(cudaSetDevice(device),"set device");Buffer<WordTrace> result(1);word_kernel<<<1,1>>>(words,result.p);check(cudaGetLastError(),"word kernel launch");WordTrace out;check(cudaMemcpy(&out,result.p,sizeof(out),cudaMemcpyDeviceToHost),"copy word trace");return out;}
}
