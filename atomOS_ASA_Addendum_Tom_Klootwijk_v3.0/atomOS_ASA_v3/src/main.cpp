#include "asa/io.hpp"
#include <chrono>
int main(int argc,char**argv){try{
    const auto o=asa::options(argc,argv);if(o.help){asa::help();return 0;}
    if(o.device_only){std::cout<<"{\"backend\":\"CPU\",\"gpu_executed\":false}\n";return 0;}
    if(o.warmup!=0||o.repeat!=1)throw std::invalid_argument("warmup and repeat timing options require the CUDA executable");
    if(o.block_size!=256)throw std::invalid_argument("nondefault block size requires the CUDA executable");
    if(o.l2_policy!="normal")throw std::invalid_argument("persist-image L2 policy requires the CUDA executable");
    const asa::Fixture fixture(o.config);const auto z=asa::make_samples(o.samples,o.config);
    asa::RunInfo info;info.sample_order=o.sample_order;asa::SampleSchedule schedule;
    if(o.sample_order=="locality") {
        const auto start=std::chrono::steady_clock::now();schedule=asa::make_locality_schedule(z,o.config);
        info.reorder_ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
    }
    const auto& input=o.sample_order=="locality"?schedule.ordered:z;
    const auto start=std::chrono::steady_clock::now();auto out=asa::cpu_run(o.config,fixture,input);
    info.milliseconds=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
    if(o.sample_order=="locality") {
        const auto restore_start=std::chrono::steady_clock::now();asa::restore_sample_order(out,schedule);
        info.restore_ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-restore_start).count();
    }
    asa::write_run(o.out,o.config,fixture,z,out,info);
    std::cout<<"PASS CPU: "<<z.size()<<" samples; payload "<<asa::required_bytes(o.config,z.size())<<" bytes; "<<o.out.string()<<'\n';return 0;
}catch(const std::exception&e){std::cerr<<"ASA: "<<e.what()<<'\n';return 1;}}
