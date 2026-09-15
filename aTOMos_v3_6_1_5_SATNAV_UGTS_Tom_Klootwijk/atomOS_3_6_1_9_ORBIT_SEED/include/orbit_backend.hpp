#pragma once
#include "orbit_core.hpp"
#include <string>
#include <vector>
namespace orbit {
struct HostModel {
 Model model{};std::vector<Segment> q,sun,moon,eop;
 void bind(){model.q={q.data(),static_cast<int>(q.size()),9};model.sun={sun.data(),static_cast<int>(sun.size()),3};model.moon={moon.data(),static_cast<int>(moon.size()),3};model.eop={eop.data(),static_cast<int>(eop.size()),3};}
};
struct Run {std::vector<Query> queries;double kernel_ms{};std::string device_json="null";};
#ifdef SATNAV_HAS_CUDA
Run cuda_queries(const HostModel& model,const std::vector<double>& times,int device);
WordTrace cuda_transition(const Words& words,int device);
#endif
}
