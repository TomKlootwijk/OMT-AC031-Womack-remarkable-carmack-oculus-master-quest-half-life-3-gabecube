#pragma once
#include "coupled_kernel.hpp"
#include <string>
#include <vector>
#include <chrono>
namespace coupled {
struct Run {std::vector<Step> trace;double kernel_ms{};std::string backend,device_json{"null"};};
inline Run cpu_run(const std::vector<Job>& jobs,const std::vector<Sample>& samples) {
 Run run;run.backend="cpu";run.trace.resize(samples.size());
 const auto begin=std::chrono::steady_clock::now();
 for(const auto& job:jobs){State state=initial_state(job);for(std::uint64_t tick=0;tick<job.steps;++tick){const auto index=static_cast<std::size_t>(job.offset+tick);run.trace[index]=transition(job,samples[index],state);}}
 run.kernel_ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-begin).count();
 return run;
}
#ifdef SATNAV_HAS_CUDA
Run cuda_run(const std::vector<Job>& jobs,const std::vector<Sample>& samples,int device);
#endif
}
