#pragma once
#include "self_reference.hpp"
#include <string>
#include <vector>
namespace selfref {
struct Run {
 std::vector<Step> trace;
 double kernel_ms{};
 std::string backend,device_json{"null"};
};
Run cpu_run(const std::vector<Job>& jobs,std::size_t trace_rows);
#ifdef SATNAV_HAS_CUDA
Run cuda_run(const std::vector<Job>& jobs,std::size_t trace_rows,int device);
#endif
} // namespace selfref
