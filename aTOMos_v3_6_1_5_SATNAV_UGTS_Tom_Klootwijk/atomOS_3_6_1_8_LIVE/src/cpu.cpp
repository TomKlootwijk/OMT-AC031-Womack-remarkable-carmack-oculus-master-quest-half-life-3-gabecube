#include "backend.hpp"
#include <chrono>
namespace satnav {
Run cpu_run(const Data& data,const Config& config){
 Run run;run.backend="cpu";run.device_json="null";run.results.resize(data.epochs.size());
 const GlobalReader reader{data.observations.data(),data.epochs.size()};
 const auto begin=std::chrono::steady_clock::now();
 for(std::size_t e=0;e<data.epochs.size();++e)run.results[e]=solve_epoch(data.epochs[e],reader,e,config);
 run.kernel_ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-begin).count();return run;
}
}
