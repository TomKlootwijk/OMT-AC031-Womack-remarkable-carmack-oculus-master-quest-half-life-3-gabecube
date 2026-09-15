#include "coupled_backend.hpp"
#include <cuda_runtime.h>
#include <limits>
#include <sstream>
#include <stdexcept>
namespace coupled {
namespace {
void check(cudaError_t code,const char* context){if(code!=cudaSuccess)throw std::runtime_error(std::string(context)+": "+cudaGetErrorString(code));}
template<class T> struct Buffer {
 T* data{};explicit Buffer(std::size_t count){if(count>std::numeric_limits<std::size_t>::max()/sizeof(T))throw std::length_error("CUDA byte count overflow");check(cudaMalloc(reinterpret_cast<void**>(&data),count*sizeof(T)),"cudaMalloc");}
 ~Buffer(){if(data)cudaFree(data);}Buffer(const Buffer&)=delete;Buffer& operator=(const Buffer&)=delete;
};
struct Event {cudaEvent_t value{};Event(){check(cudaEventCreate(&value),"cudaEventCreate");}~Event(){if(value)cudaEventDestroy(value);}Event(const Event&)=delete;Event& operator=(const Event&)=delete;};
__global__ void coupled_trajectories(const Job* jobs,std::size_t count,const Sample* samples,Step* trace) {
 const std::size_t index=static_cast<std::size_t>(blockIdx.x)*blockDim.x+threadIdx.x;if(index>=count)return;
 const Job& job=jobs[index];State state=initial_state(job);
 for(std::uint64_t tick=0;tick<job.steps;++tick){const auto row=static_cast<std::size_t>(job.offset+tick);trace[row]=transition(job,samples[row],state);}
}
}
Run cuda_run(const std::vector<Job>& jobs,const std::vector<Sample>& samples,int device) {
 if(jobs.empty()||samples.empty())throw std::invalid_argument("empty CUDA coupled workload");
 check(cudaSetDevice(device),"cudaSetDevice");check(cudaFree(nullptr),"CUDA context");cudaDeviceProp prop{};check(cudaGetDeviceProperties(&prop,device),"cudaGetDeviceProperties");
 const std::size_t blocks=jobs.size()/128+(jobs.size()%128!=0);if(blocks>static_cast<std::size_t>(prop.maxGridSize[0]))throw std::length_error("trajectory count exceeds device grid");
 const auto maximum=std::numeric_limits<std::size_t>::max();
 if(samples.size()>maximum/(sizeof(Sample)+sizeof(Step)))throw std::length_error("sample/trace bytes overflow");
 const auto sample_bytes=samples.size()*sizeof(Sample),trace_bytes=samples.size()*sizeof(Step);
 if(jobs.size()>(maximum-sample_bytes-trace_bytes)/sizeof(Job))throw std::length_error("combined CUDA bytes overflow");
 const auto job_bytes=jobs.size()*sizeof(Job),allocation=job_bytes+sample_bytes+trace_bytes;
 std::size_t free_bytes=0,total_bytes=0;check(cudaMemGetInfo(&free_bytes,&total_bytes),"cudaMemGetInfo");if(allocation>free_bytes)throw std::runtime_error("coupled workload exceeds currently free device memory");
 int runtime=0,driver=0;check(cudaRuntimeGetVersion(&runtime),"cudaRuntimeGetVersion");check(cudaDriverGetVersion(&driver),"cudaDriverGetVersion");
 Run run;run.backend="cuda";run.trace.resize(samples.size());std::ostringstream info;info<<"{\"index\":"<<device<<",\"name\":\"";
 for(const char* c=prop.name;*c;++c){if(*c=='"'||*c=='\\')info<<'\\';info<<*c;}
 info<<"\",\"capability_major\":"<<prop.major<<",\"capability_minor\":"<<prop.minor<<",\"driver_version\":"<<driver<<",\"runtime_version\":"<<runtime<<",\"nvcc_major\":"<<__CUDACC_VER_MAJOR__<<",\"nvcc_minor\":"<<__CUDACC_VER_MINOR__<<",\"free_bytes_before_allocation\":"<<free_bytes<<",\"total_bytes\":"<<total_bytes<<",\"allocation_bytes\":"<<allocation<<",\"threads_per_block\":128,\"blocks\":"<<blocks<<'}';run.device_json=info.str();
 Buffer<Job> d_jobs(jobs.size());Buffer<Sample> d_samples(samples.size());Buffer<Step> d_trace(samples.size());
 check(cudaMemcpy(d_jobs.data,jobs.data(),job_bytes,cudaMemcpyHostToDevice),"copy jobs");check(cudaMemcpy(d_samples.data,samples.data(),sample_bytes,cudaMemcpyHostToDevice),"copy samples");
 Event start,end;check(cudaEventRecord(start.value),"start event");coupled_trajectories<<<static_cast<unsigned>(blocks),128>>>(d_jobs.data,jobs.size(),d_samples.data,d_trace.data);check(cudaGetLastError(),"coupled kernel launch");check(cudaEventRecord(end.value),"end event");check(cudaEventSynchronize(end.value),"coupled kernel synchronize");float milliseconds=0;check(cudaEventElapsedTime(&milliseconds,start.value,end.value),"kernel elapsed time");run.kernel_ms=milliseconds;
 check(cudaMemcpy(run.trace.data(),d_trace.data,trace_bytes,cudaMemcpyDeviceToHost),"copy trace");return run;
}
}
