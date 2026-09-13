#include "../cuda/asa_device.cuh"
#include "asa/io.hpp"

namespace {
using namespace asa;
struct Case { std::string name; Config config; };

void adjacent(std::vector<Sample>& samples,double rho,double phi,bool radial) {
    const double value=radial?rho:phi;
    for(double v:{std::nextafter(value,-std::numeric_limits<double>::infinity()),value,
                  std::nextafter(value,std::numeric_limits<double>::infinity())})
        samples.push_back(radial?Sample{v,phi}:Sample{rho,v});
}

std::vector<Sample> boundary_samples(const Config& c) {
    auto samples=make_samples(257,c);
    const double mid=c.pupil_min+(c.pupil_max-c.pupil_min)*.5;
    const double center=c.axis-c.hinge;
    samples.push_back({1.,center});
    for(double rho:{c.rho_min,c.rho_max,c.pupil_min,c.pupil_max,mid}) {
        adjacent(samples,rho,center,true);
        adjacent(samples,rho,center+c.alpha*.5,true);
    }
    for(double d:{0.,-0.,c.alpha,-c.alpha,pi/2,-pi/2,pi,-pi,tau,-tau})
        adjacent(samples,mid,center+d,false);
    // Both sides of the periodic lens seam and selected LUT cell boundaries.
    for(u32 j:{0u,1u,2u,c.warp_bins/4,c.warp_bins/2,c.warp_bins-1}) {
        const double d=tau*double(j)/c.warp_bins;
        adjacent(samples,mid,center+d,false);
        adjacent(samples,mid,center-d,false);
    }
    // Quantization boundaries in the image chart, including their neighbours.
    for(u32 r:{0u,1u,c.rho_bins/2,c.rho_bins-1,c.rho_bins}) {
        const double rho=c.rho_min+(c.rho_max-c.rho_min)*(double(r)/c.rho_bins);
        adjacent(samples,rho,center,true);
    }
    for(u32 p:{0u,1u,c.phi_bins/2,c.phi_bins-1,c.phi_bins})
        adjacent(samples,mid,tau*double(p)/c.phi_bins-c.hinge,false);
    const double inf=std::numeric_limits<double>::infinity();
    const double nan=std::numeric_limits<double>::quiet_NaN();
    for(double v:{nan,inf,-inf}) {
        samples.push_back({v,center});samples.push_back({mid,v});
    }
    for(double v:{std::numeric_limits<double>::max(),-std::numeric_limits<double>::max(),
                  std::numeric_limits<double>::denorm_min(),-std::numeric_limits<double>::denorm_min()}) {
        samples.push_back({v,center});samples.push_back({mid,v});
    }
    return samples;
}

std::vector<Case> cases() {
    std::vector<Case> all;
    Config c;
    all.push_back({"default",c});
    c.hinge=0;c.alpha=0;all.push_back({"zero_aperture",c});
    c.axis=1.25;all.push_back({"zero_aperture_nonzero_axis",c});
    c=Config{};c.hinge=0;c.alpha=pi/2;all.push_back({"inclusive_half_pi",c});
    c.axis=1.125;c.hinge=.3;all.push_back({"nonzero_axis",c});
    c.axis=std::nextafter(tau,0.);c.hinge=-.2;all.push_back({"axis_seam",c});
    for(double h:{pi,-pi}) {c=Config{};c.axis=.5;c.hinge=h;all.push_back({h>0?"hinge_plus_pi":"hinge_minus_pi",c});}
    for(double radial:{-1.,1.})for(double angular:{-.75,.75}) {
        c=Config{};c.hinge=0;c.alpha=pi/2;c.radial_warp=radial;c.angular_warp=angular;
        all.push_back({std::string("warp_")+(radial<0?"negative":"positive")+"_"+(angular<0?"negative":"positive"),c});
    }
    c=Config{};c.hinge=0;c.alpha=pi/2;c.radial_warp=0;c.angular_warp=0;
    c.pupil_min=c.rho_min;c.pupil_max=c.rho_max;all.push_back({"identity_full_pupil",c});
    c.rho_bins=8;c.phi_bins=24;c.warp_bins=8;all.push_back({"small_rectangular_min_lut",c});
    c.rho_bins=40;c.phi_bins=64;c.warp_bins=65536;all.push_back({"rectangular_max_lut",c});
    c=Config{};c.hinge=0;c.rho_min=-2;c.rho_max=2;c.pupil_min=-2;c.pupil_max=2;
    all.push_back({"shifted_radial_chart",c});
    c.radial_warp=0;c.angular_warp=0;c.rho_min=0;c.rho_max=std::numeric_limits<double>::min();
    c.pupil_min=c.rho_min;c.pupil_max=c.rho_max;all.push_back({"tiny_radial_chart",c});
    c.rho_min=-1e308;c.rho_max=1e307;c.pupil_min=c.rho_min;c.pupil_max=c.rho_max;
    all.push_back({"large_finite_radial_chart",c});
    return all;
}

void check_semantic_edges(const std::string& name,const Config& c,
                          const std::vector<Sample>& samples,const std::vector<Result>& results) {
    auto expect=[&](double rho,double phi,u32 flags,u32 left_cell,u32 right_cell,const char* label) {
        const auto sample=std::find_if(samples.begin(),samples.end(),[&](Sample value){return value.rho==rho&&value.phi==phi;});
        if(sample==samples.end())throw std::runtime_error(std::string("missing explicit edge sample: ")+label);
        const Result& result=results[std::size_t(sample-samples.begin())];
        if(result.flags!=flags||result.left_cell!=left_cell||result.right_cell!=right_cell||
           (flags==0&&(result.left!=0||result.right!=0||result.mean!=0)))
            throw std::runtime_error(std::string("explicit edge expectation failed: ")+label);
    };
    if(name=="identity_full_pupil") {
        const double mid=c.pupil_min+(c.pupil_max-c.pupil_min)*.5;
        const u32 row=(c.rho_bins/2)*c.phi_bins;
        expect(c.rho_min,0,7,0,0,"lower radial edge included");
        expect(c.rho_max,0,0,invalid_index,invalid_index,"upper radial edge excluded");
        expect(mid,0,7,row,row,"identity center cells");
        expect(mid,pi/2,7,row+c.phi_bins/4,row+3*c.phi_bins/4,"positive angular equality included");
        expect(mid,-pi/2,7,row+3*c.phi_bins/4,row+c.phi_bins/4,"negative angular equality included");
        expect(mid,std::nextafter(pi/2,std::numeric_limits<double>::infinity()),0,invalid_index,invalid_index,
               "positive adjacent angle outside aperture rejected");
    }
    if(name=="zero_aperture") {
        const double mid=c.pupil_min+(c.pupil_max-c.pupil_min)*.5;
        const u32 row=(c.rho_bins/4)*c.phi_bins;
        expect(1.,0,7,row,row,"zero aperture accepts exact center");
        expect(mid,pi/2,0,invalid_index,invalid_index,"zero aperture rejects off-axis sample");
    }
}

std::vector<Result> run_case(const Config& c,const std::vector<Sample>& samples,
                             const cudaDeviceProp& prop,const std::filesystem::path& output,const std::string& order) {
    const u64 bytes=required_bytes(c,samples.size());
    std::size_t free_bytes=0,total_bytes=0;
    ASA_CUDA(cudaMemGetInfo(&free_bytes,&total_bytes));
    if(!gpu_payload_admitted(bytes,free_bytes))
        throw std::runtime_error("insufficient free VRAM for boundary case");
    const Fixture fixture(c);
    const auto cpu=cpu_run(c,fixture,samples);
    for(std::size_t i=0;i<samples.size();++i)
        if((!asa::finite(samples[i].rho)||!asa::finite(samples[i].phi))&&cpu[i].flags!=InputInvalid)
            throw std::runtime_error("nonfinite input must have flag 8");
    RunInfo info;info.backend="CUDA focused boundary texture + global differential";
    info.device=prop.name;info.gpu=!samples.empty();info.total_vram=total_bytes;info.free_vram=free_bytes;
    info.sample_order=order;info.compute_statistic="not timed (focused boundary validation)";
    SampleSchedule schedule;
    if(order=="locality") {
        const auto start=std::chrono::steady_clock::now();schedule=make_locality_schedule(samples,c);
        info.reorder_ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
    }
    const auto& execution_samples=order=="locality"?schedule.ordered:samples;
    Buffer<float> image(fixture.image.size());Buffer<u32> mask(fixture.mask.size());Buffer<Warp> warp(fixture.warp.size());
    Buffer<Sample> input(samples.size());Buffer<Result> output_buffer(samples.size());
    image.upload(fixture.image.data(),fixture.image.size());mask.upload(fixture.mask.data(),fixture.mask.size());
    warp.upload(fixture.warp.data(),fixture.warp.size());input.upload(execution_samples.data(),execution_samples.size());
    Texture image_texture(image.get(),fixture.image.size()*sizeof(float),cudaCreateChannelDesc<float>(),fixture.image.size(),prop);
    Texture mask_texture(mask.get(),fixture.mask.size()*sizeof(u32),cudaCreateChannelDesc<unsigned int>(),fixture.mask.size(),prop);
    Texture warp_texture(warp.get(),fixture.warp.size()*sizeof(Warp),cudaCreateChannelDesc<float2>(),fixture.warp.size(),prop);
    std::vector<Result> texture(samples.size()),global(samples.size());
    auto restore=[&](std::vector<Result>& result) {
        if(order=="locality") {
            const auto start=std::chrono::steady_clock::now();restore_sample_order(result,schedule);
            info.restore_ms+=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
        }
    };
    if(!samples.empty()) {
        const u32 n=u32(samples.size()),blocks=(n+255u)/256u;
        asa_texture_kernel<<<blocks,256>>>(input.get(),output_buffer.get(),n,c,{image_texture.get(),mask_texture.get(),warp_texture.get()});
        ASA_CUDA(cudaGetLastError());ASA_CUDA(cudaDeviceSynchronize());
        output_buffer.download(texture.data(),texture.size());restore(texture);compare(texture,cpu);
        asa_global_kernel<<<blocks,256>>>(input.get(),output_buffer.get(),n,c,{image.get(),mask.get(),warp.get()});
        ASA_CUDA(cudaGetLastError());ASA_CUDA(cudaDeviceSynchronize());
        output_buffer.download(global.data(),global.size());restore(global);compare(global,cpu);compare(texture,global);
    }
    if(!output.empty()) {
        write_run(output,c,fixture,samples,texture,info);
    }
    return texture;
}
}

int main(int argc,char** argv) {try {
    std::filesystem::path output;
    if(argc==3&&std::string(argv[1])=="--out")output=argv[2];
    else if(argc!=1)throw std::invalid_argument("usage: asa_cuda_tests [--out NEW_DIRECTORY]");
    if(!output.empty()&&std::filesystem::exists(output)&&
       (!std::filesystem::is_directory(output)||!std::filesystem::is_empty(output)))
        throw std::runtime_error("output directory must be new or empty");
    int devices=0;ASA_CUDA(cudaGetDeviceCount(&devices));
    if(!devices)throw std::runtime_error("no CUDA device available for boundary tests");
    ASA_CUDA(cudaSetDevice(0));cudaDeviceProp prop{};ASA_CUDA(cudaGetDeviceProperties(&prop,0));
    std::size_t case_index=0,total_samples=0;
    for(const auto& test:cases()) {
        const auto samples=boundary_samples(test.config);
        std::vector<Result> first;
        for(Layout layout:{Layout::Linear,Layout::Morton8}) {
            Config config=test.config;config.layout=layout;validate(config);
            for(const std::string order:{"natural","locality"}) {
            std::ostringstream name;name<<"case_"<<std::setw(3)<<std::setfill('0')<<case_index;
            try {
                const auto result=run_case(config,samples,prop,output.empty()?std::filesystem::path{}:output/name.str(),order);
                check_semantic_edges(test.name,config,samples,result);
                if(first.empty())first=result;else compare(first,result,0.);
            } catch(const std::exception& error) {
                throw std::runtime_error(test.name+" / "+(layout==Layout::Linear?"linear":"morton")+" / "+order+": "+error.what());
            }
            ++case_index;total_samples+=samples.size();
            std::cout<<"PASS "<<name.str()<<' '<<test.name<<' '<<(layout==Layout::Linear?"linear":"morton")
                     <<' '<<order<<" samples="<<samples.size()<<'\n';
            }
        }
    }
    std::cout<<"RESULT "<<case_index<<" CUDA boundary cases / "<<total_samples<<" samples; texture/global/CPU agree\n";
    return 0;
}catch(const std::exception& error){std::cerr<<"FAIL CUDA boundary: "<<error.what()<<'\n';return 1;}}
