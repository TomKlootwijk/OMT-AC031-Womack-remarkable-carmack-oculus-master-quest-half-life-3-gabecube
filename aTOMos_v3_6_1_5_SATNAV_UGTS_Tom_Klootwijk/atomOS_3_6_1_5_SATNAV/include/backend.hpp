#pragma once
#include "satnav_core.hpp"
#include <vector>
#include <string>
namespace satnav {
struct Data {std::vector<Epoch> epochs;std::vector<double> observations;};
struct Run {std::vector<Result> results;double kernel_ms{};std::string backend;std::string device_json;};
Run cpu_run(const Data&,const Config&);
#ifdef SATNAV_HAS_CUDA
Run cuda_run(const Data&,const Config&,int device,bool texture,std::size_t budget_bytes,std::size_t reserve_bytes);
std::string cuda_probe(int device);
#endif
}
