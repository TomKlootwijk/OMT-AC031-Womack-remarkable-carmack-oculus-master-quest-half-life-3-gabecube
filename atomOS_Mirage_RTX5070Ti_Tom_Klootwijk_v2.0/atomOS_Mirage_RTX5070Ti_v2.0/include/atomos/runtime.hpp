#pragma once
#include "core.hpp"
#include "sha256.hpp"
#include <vector>
#include <string>
#include <memory>
namespace atomos {
struct Tables {std::vector<Vec2> angles;std::vector<std::uint32_t> mask,jitter;
    HostTables view()const{return{angles.data(),mask.data(),jitter.data()};}};
struct Program {std::uint32_t states=2,halt=1;std::vector<std::uint32_t> words;};
void validate_config(const Config& c);
Node root_node(const Digest&,const Config&);
Tables make_tables(const Config& c);
std::vector<std::uint32_t> make_jitter(const std::vector<Node>& in,const Digest& root,std::uint64_t tick,unsigned threshold);
std::vector<Node> propagate_cpu(const std::vector<Node>& in,const Config& c,const Tables& tables);
void vm_cpu(std::vector<VMState>& state,std::vector<std::uint32_t>& tape,std::uint32_t tape_bits,const Program& p,unsigned budget);
Program load_program(const std::string& path);
Program unary_program();
std::string node_json(const Node& n);
class GPUBackend {
public:
    GPUBackend(const Config&,const Tables&,bool use_texture,int device);
    ~GPUBackend();
    GPUBackend(const GPUBackend&)=delete;GPUBackend& operator=(const GPUBackend&)=delete;
    std::vector<Node> propagate(const std::vector<Node>&,const std::vector<std::uint32_t>& jitter,unsigned repeats=1);
    void universal(std::vector<VMState>&,std::vector<std::uint32_t>&,std::uint32_t tape_bits,const Program&,unsigned budget);
    double last_kernel_ms()const;std::string device_description()const;
private:struct Impl;std::unique_ptr<Impl> impl_;
};
}
