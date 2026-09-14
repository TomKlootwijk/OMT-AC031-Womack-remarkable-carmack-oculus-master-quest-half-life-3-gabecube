#include "self_reference_backend.hpp"
#include <cuda_runtime.h>
#include <limits>
#include <sstream>
#include <stdexcept>

namespace selfref {
namespace {
void check(cudaError_t status,const char* where) {
 if(status!=cudaSuccess)throw std::runtime_error(std::string(where)+": "+cudaGetErrorString(status));
}
template<class T> struct Buffer {
 T* data{};
 explicit Buffer(std::size_t count) {
  if(count>std::numeric_limits<std::size_t>::max()/sizeof(T))throw std::length_error("CUDA allocation size overflow");
  check(cudaMalloc(reinterpret_cast<void**>(&data),count*sizeof(T)),"cudaMalloc");
 }
 ~Buffer(){if(data)cudaFree(data);}
 Buffer(const Buffer&)=delete;Buffer& operator=(const Buffer&)=delete;
};
struct Event {
 cudaEvent_t value{};
 Event(){check(cudaEventCreate(&value),"cudaEventCreate");}
 ~Event(){if(value)cudaEventDestroy(value);}
 Event(const Event&)=delete;Event& operator=(const Event&)=delete;
};
__global__ void feedback_kernel(const Job* jobs,std::size_t count,Step* trace) {
 const std::size_t index=static_cast<std::size_t>(blockIdx.x)*blockDim.x+threadIdx.x;
 if(index>=count)return;
 const Job job=jobs[index];std::uint32_t q=job.q0;
 // Persistent trajectory state: each tick consumes the preceding tick's result.
 for(std::uint64_t tick=0;tick<job.steps;++tick) {
  const Step next=transition(q,job);
  trace[static_cast<std::size_t>(job.offset+tick)]=next;q=next.after;
 }
}
}
Run cuda_run(const std::vector<Job>& jobs,std::size_t trace_rows,int device) {
 if(jobs.empty()||!trace_rows)throw std::invalid_argument("empty CUDA trajectory workload");
 check(cudaSetDevice(device),"cudaSetDevice");check(cudaFree(nullptr),"CUDA context");
 cudaDeviceProp prop{};check(cudaGetDeviceProperties(&prop,device),"cudaGetDeviceProperties");
 const std::size_t blocks=jobs.size()/128+(jobs.size()%128!=0);
 if(blocks>static_cast<std::size_t>(prop.maxGridSize[0]))throw std::length_error("trajectory count exceeds this CUDA device's launch grid");
 const auto maximum=std::numeric_limits<std::size_t>::max();
 if(trace_rows>maximum/sizeof(Step))throw std::length_error("CUDA trace byte count overflow");
 const auto trace_bytes=trace_rows*sizeof(Step);
 if(jobs.size()>(maximum-trace_bytes)/sizeof(Job))throw std::length_error("CUDA combined byte count overflow");
 const auto job_bytes=jobs.size()*sizeof(Job);
 std::size_t free=0,total=0;check(cudaMemGetInfo(&free,&total),"cudaMemGetInfo");
 if(job_bytes+trace_bytes>free)throw std::runtime_error("trajectory trace and jobs exceed currently free device memory");
 int driver=0,runtime=0;check(cudaDriverGetVersion(&driver),"cudaDriverGetVersion");check(cudaRuntimeGetVersion(&runtime),"cudaRuntimeGetVersion");
 Run run;run.backend="cuda";run.trace.resize(trace_rows);
 std::ostringstream info;info<<"{\"index\":"<<device<<",\"name\":\"";
 for(const char* c=prop.name;*c;++c){if(*c=='"'||*c=='\\')info<<'\\';info<<*c;}
 info<<"\",\"capability_major\":"<<prop.major<<",\"capability_minor\":"<<prop.minor
  <<",\"driver_version\":"<<driver<<",\"runtime_version\":"<<runtime
  <<",\"free_bytes_before_allocation\":"<<free<<",\"total_bytes\":"<<total
  <<",\"allocation_bytes\":"<<job_bytes+trace_bytes<<",\"threads_per_block\":128}";
 run.device_json=info.str();
 Buffer<Job> device_jobs(jobs.size());Buffer<Step> device_trace(trace_rows);
 check(cudaMemcpy(device_jobs.data,jobs.data(),job_bytes,cudaMemcpyHostToDevice),"copy trajectory jobs");
 Event begin,end;check(cudaEventRecord(begin.value),"start event");
 feedback_kernel<<<static_cast<unsigned>(blocks),128>>>(device_jobs.data,jobs.size(),device_trace.data);
 check(cudaGetLastError(),"self-reference kernel launch");
 check(cudaEventRecord(end.value),"end event");check(cudaEventSynchronize(end.value),"self-reference kernel synchronize");
 float elapsed=0;check(cudaEventElapsedTime(&elapsed,begin.value,end.value),"kernel elapsed time");run.kernel_ms=elapsed;
 check(cudaMemcpy(run.trace.data(),device_trace.data,trace_bytes,cudaMemcpyDeviceToHost),"copy trajectory trace");
 return run;
}
} // namespace selfref
