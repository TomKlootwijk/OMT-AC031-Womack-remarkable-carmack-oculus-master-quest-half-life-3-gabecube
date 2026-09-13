#include "asa/io.hpp"
#include <chrono>
int main(int argc,char**argv){try{
    const auto o=asa::options(argc,argv);if(o.help){asa::help();return 0;}
    if(o.device_only){std::cout<<"{\"backend\":\"CPU\",\"gpu_executed\":false}\n";return 0;}
    const asa::Fixture fixture(o.config);const auto z=asa::make_samples(o.samples,o.config);
    const auto start=std::chrono::steady_clock::now();const auto out=asa::cpu_run(o.config,fixture,z);
    asa::RunInfo info;info.milliseconds=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
    asa::write_run(o.out,o.config,fixture,z,out,info);
    std::cout<<"PASS CPU: "<<z.size()<<" samples; payload "<<asa::required_bytes(o.config,z.size())<<" bytes; "<<o.out.string()<<'\n';return 0;
}catch(const std::exception&e){std::cerr<<"ASA: "<<e.what()<<'\n';return 1;}}
