#pragma once
#include "nav.hpp"
#include <array>
#include <cstddef>
#include <string>
#include <vector>
namespace ao {
struct Frame {Epoch epoch{};std::array<Observation,max_sats> obs{};};
struct BatchResult {std::vector<Solution> solutions;std::vector<Diagnostic> diagnostics;double compute_ms=0;std::string device;};
std::vector<Frame> load_csv(const std::string& epochs,const std::string& observations);
void write_csv(const std::string& output,const std::vector<Frame>& frames,const BatchResult& result);
BatchResult cpu_run(const std::vector<Frame>& frames,const SolveConfig& cfg,const GeoConfig& geo);
#ifdef AO_CUDA
BatchResult cuda_run(const std::vector<Frame>& frames,const SolveConfig& cfg,const GeoConfig& geo,bool texture,std::size_t chunk,std::size_t budget_bytes);
std::string cuda_probe();
#endif
}
