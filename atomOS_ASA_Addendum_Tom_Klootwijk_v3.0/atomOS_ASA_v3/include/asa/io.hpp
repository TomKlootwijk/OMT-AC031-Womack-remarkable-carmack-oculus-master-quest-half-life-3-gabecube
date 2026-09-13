#pragma once
#include "fixture.hpp"
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
namespace asa {
inline std::string quoted(const std::string& s) {
    std::ostringstream out;out<<'"';
    for(unsigned char c:s){if(c=='"'||c=='\\')out<<'\\'<<char(c);else if(c<32)out<<"\\u"<<std::hex<<std::setw(4)<<std::setfill('0')<<unsigned(c)<<std::dec;else out<<char(c);}
    return out.str()+'"';
}
inline u32 parse_uint(const std::string& s) {
    if(s.empty()||s[0]=='-')throw std::invalid_argument("expected unsigned integer");
    std::size_t n=0;const unsigned long long v=std::stoull(s,&n,10);
    if(n!=s.size()||v>std::numeric_limits<u32>::max())throw std::invalid_argument("invalid uint32");
    return u32(v);
}
inline void save_bytes(const std::filesystem::path& path,const void* p,std::size_t bytes) {
    std::ofstream f(path,std::ios::binary);f.exceptions(std::ios::badbit|std::ios::failbit);
    if(bytes)f.write(static_cast<const char*>(p),std::streamsize(bytes));
}
inline std::string config_json(const Config& c) {
    std::ostringstream s;s<<std::setprecision(17)<<"{\"rho_bins\":"<<c.rho_bins<<",\"phi_bins\":"<<c.phi_bins
      <<",\"warp_bins\":"<<c.warp_bins<<",\"layout\":"<<u32(c.layout)<<",\"rho_min\":"<<c.rho_min<<",\"rho_max\":"<<c.rho_max
      <<",\"pupil_min\":"<<c.pupil_min<<",\"pupil_max\":"<<c.pupil_max<<",\"axis\":"<<c.axis<<",\"hinge\":"<<c.hinge
      <<",\"alpha\":"<<c.alpha<<",\"radial_warp\":"<<c.radial_warp<<",\"angular_warp\":"<<c.angular_warp<<'}';return s.str();
}
struct RunInfo {std::string backend="CPU",device="host";double milliseconds=0;u64 total_vram=0,free_vram=0;bool gpu=false;};
inline void write_run(const std::filesystem::path& dir,const Config& c,const Fixture& f,
                      const std::vector<Sample>& z,const std::vector<Result>& out,const RunInfo& info) {
    std::filesystem::create_directories(dir);
    const u32 one=1;if(*reinterpret_cast<const unsigned char*>(&one)!=1)throw std::runtime_error("binary file format requires little-endian host");
    save_bytes(dir/"image.f32",f.image.data(),f.image.size()*sizeof(float));
    save_bytes(dir/"mask.u32",f.mask.data(),f.mask.size()*sizeof(u32));
    save_bytes(dir/"warp.f32x2",f.warp.data(),f.warp.size()*sizeof(Warp));
    save_bytes(dir/"samples.f64x2",z.data(),z.size()*sizeof(Sample));
    save_bytes(dir/"results.bin",out.data(),out.size()*sizeof(Result));
    std::ofstream csv(dir/"results.csv");csv.exceptions(std::ios::badbit|std::ios::failbit);
    csv<<"index,rho,phi,left,right,mean,flags,left_cell,right_cell\n"<<std::setprecision(17);
    u64 pairs=0,left=0,right=0;for(std::size_t i=0;i<out.size();++i){const auto&r=out[i];
        pairs+=bool(r.flags&PairValid);left+=bool(r.flags&LeftValid);right+=bool(r.flags&RightValid);
        csv<<i<<','<<z[i].rho<<','<<z[i].phi<<','<<r.left<<','<<r.right<<','<<r.mean<<','<<r.flags<<','<<r.left_cell<<','<<r.right_cell<<'\n';}
    std::ofstream meta(dir/"run.json");meta.exceptions(std::ios::badbit|std::ios::failbit);
    meta<<std::setprecision(17)<<"{\n\"schema\":\"atomOS.ASA.v3.run\",\n\"config\":"<<config_json(c)<<",\n\"samples\":"<<z.size()
        <<",\n\"left_valid\":"<<left<<",\n\"right_valid\":"<<right<<",\n\"pair_valid\":"<<pairs
        <<",\n\"backend\":"<<quoted(info.backend)<<",\n\"device\":"<<quoted(info.device)<<",\n\"gpu_executed\":"<<(info.gpu?"true":"false")
        <<",\n\"compute_ms\":"<<info.milliseconds<<",\n\"payload_bytes\":"<<required_bytes(c,z.size())
        <<",\n\"device_total_bytes\":"<<info.total_vram<<",\n\"device_free_before_bytes\":"<<info.free_vram<<"\n}\n";
}
struct Options { Config config;u32 samples=65536,budget_mib=256,device=0;std::filesystem::path out="asa_run";bool help=false,device_only=false; };
inline Options options(int argc,char**argv) {
    Options o;
    for(int i=1;i<argc;++i){const std::string a=argv[i];
        if(a=="--help"){o.help=true;continue;}if(a=="--device-info"){o.device_only=true;continue;}
        if(i+1>=argc)throw std::invalid_argument("missing value for "+a);
        const std::string v=argv[++i];
        if(a=="--samples")o.samples=parse_uint(v);
        else if(a=="--rho-bins")o.config.rho_bins=parse_uint(v);
        else if(a=="--phi-bins")o.config.phi_bins=parse_uint(v);
        else if(a=="--budget-mib")o.budget_mib=parse_uint(v);
        else if(a=="--device")o.device=parse_uint(v);
        else if(a=="--out")o.out=v;
        else if(a=="--layout"){if(v!="linear"&&v!="morton")throw std::invalid_argument("layout must be linear or morton");o.config.layout=v=="linear"?Layout::Linear:Layout::Morton8;}
        else throw std::invalid_argument("unknown option "+a);
    }
    if(o.help||o.device_only)return o;
    if(o.budget_mib<1||o.budget_mib>2048)throw std::invalid_argument("budget must be 1..2048 MiB");
    if(required_bytes(o.config,o.samples)>u64(o.budget_mib)*1048576)throw std::runtime_error("payload exceeds configured memory budget");
    if(std::filesystem::exists(o.out)&&(!std::filesystem::is_directory(o.out)||!std::filesystem::is_empty(o.out)))
        throw std::runtime_error("output directory must be new or empty");
    return o;
}
inline void help() {std::cout<<"ASA v3 numerical image operator\n--samples N --rho-bins N --phi-bins N --layout linear|morton\n--budget-mib N --out NEW_DIRECTORY --device N --device-info\n";}
}
