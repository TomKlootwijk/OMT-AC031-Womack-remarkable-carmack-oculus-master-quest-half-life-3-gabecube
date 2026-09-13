#include "asa_device.cuh"
#include "asa/io.hpp"
int main(int argc,char**argv){try{
    const auto o=asa::options(argc,argv,true);if(o.help){asa::help(true);return 0;}
    int count=0;ASA_CUDA(cudaGetDeviceCount(&count));
    if(o.device>=unsigned(count))throw std::runtime_error("selected CUDA device not available");
    ASA_CUDA(cudaSetDevice(int(o.device)));cudaDeviceProp prop{};ASA_CUDA(cudaGetDeviceProperties(&prop,int(o.device)));
    std::size_t free_bytes=0,total_bytes=0;ASA_CUDA(cudaMemGetInfo(&free_bytes,&total_bytes));
    int driver=0,runtime=0;ASA_CUDA(cudaDriverGetVersion(&driver));ASA_CUDA(cudaRuntimeGetVersion(&runtime));
    if(o.device_only){
        std::cout<<"{\"name\":"<<asa::quoted(prop.name)<<",\"cc_major\":"<<prop.major<<",\"cc_minor\":"<<prop.minor
            <<",\"total_bytes\":"<<total_bytes<<",\"free_bytes\":"<<free_bytes<<",\"driver\":"<<driver
            <<",\"runtime\":"<<runtime<<",\"max_texture_1d_linear\":"<<prop.maxTexture1DLinear
            <<",\"max_threads_per_block\":"<<prop.maxThreadsPerBlock
            <<",\"l2_cache_bytes\":"<<prop.l2CacheSize<<",\"persisting_l2_max_bytes\":"<<prop.persistingL2CacheMaxSize
            <<",\"access_policy_max_window_bytes\":"<<prop.accessPolicyMaxWindowSize<<"}\n";return 0;
    }
    if(o.block_size>unsigned(prop.maxThreadsPerBlock)||o.block_size>unsigned(prop.maxThreadsDim[0]))
        throw std::runtime_error("requested block size exceeds CUDA device limits");
    // Budget rule: <= configured budget, <= half of currently free VRAM,
    // and at least 512 MiB remains outside this run's payload.
    const asa::u64 bytes=asa::required_bytes(o.config,o.samples);
    if(!asa::gpu_payload_admitted(bytes,free_bytes))
        throw std::runtime_error("insufficient free VRAM for payload plus reserve");
    const asa::Fixture f(o.config);const auto samples=asa::make_samples(o.samples,o.config);
    const auto cpu=asa::cpu_run(o.config,f,samples);
    asa::RunInfo info;info.backend="CUDA texture + global differential";info.device=prop.name;info.gpu=(o.samples!=0);
    info.sample_order=o.sample_order;info.compute_statistic="mean texture kernel CUDA event time";
    info.total_vram=total_bytes;info.free_vram=free_bytes;
    info.l2_policy=o.l2_policy;info.l2_cache_bytes=prop.l2CacheSize;
    info.persisting_l2_max_bytes=prop.persistingL2CacheMaxSize;info.access_policy_max_window_bytes=prop.accessPolicyMaxWindowSize;
    asa::SampleSchedule schedule;
    if(o.sample_order=="locality") {
        const auto start=std::chrono::steady_clock::now();schedule=asa::make_locality_schedule(samples,o.config);
        info.reorder_ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
    }
    const auto& input=o.sample_order=="locality"?schedule.ordered:samples;
    asa::Buffer<float> image(f.image.size());asa::Buffer<asa::u32> mask(f.mask.size());asa::Buffer<asa::Warp> warp(f.warp.size());
    asa::Buffer<asa::Sample> in(samples.size());asa::Buffer<asa::Result> out(samples.size());
    image.upload(f.image.data(),f.image.size());mask.upload(f.mask.data(),f.mask.size());warp.upload(f.warp.data(),f.warp.size());
    in.upload(input.data(),input.size());
    // Finish uploads on the default stream before a nonblocking owned stream reads them.
    ASA_CUDA(cudaStreamSynchronize(nullptr));
    asa::Texture ti(image.get(),f.image.size()*4,cudaCreateChannelDesc<float>(),f.image.size(),prop);
    asa::Texture tm(mask.get(),f.mask.size()*4,cudaCreateChannelDesc<unsigned int>(),f.mask.size(),prop);
    asa::Texture tw(warp.get(),f.warp.size()*8,cudaCreateChannelDesc<float2>(),f.warp.size(),prop);
    asa::Stream stream;asa::L2AccessPolicy policy(stream.get());
    if(o.samples&&o.l2_policy=="persist-image") {
        policy.enable(image.get(),f.image.size()*sizeof(float),prop);
        info.l2_requested_bytes=policy.requested_bytes;info.l2_accepted_bytes=policy.accepted_bytes;
        info.l2_window_bytes=policy.window_bytes;info.l2_hit_ratio=policy.hit_ratio;info.l2_policy_active=policy.active;
        info.l2_window_base_address=policy.window_base_address;info.l2_hit_property=policy.hit_property;info.l2_miss_property=policy.miss_property;
    }
    std::vector<asa::Result> texture(samples.size()),global(samples.size());
    if(o.samples){
        const asa::u32 blocks=(o.samples+o.block_size-1u)/o.block_size;asa::Event start,end;
        info.block_size=o.block_size;
        info.warmup_runs_per_path=o.warmup;info.timed_runs_per_path=o.repeat;
        auto measure=[&](auto launch,double& mean,double& minimum) {
            for(asa::u32 i=0;i<o.warmup;++i){launch();ASA_CUDA(cudaGetLastError());}
            if(o.warmup)ASA_CUDA(cudaStreamSynchronize(stream.get()));
            double total=0;minimum=std::numeric_limits<double>::max();
            for(asa::u32 i=0;i<o.repeat;++i) {
                ASA_CUDA(cudaEventRecord(start.get(),stream.get()));launch();ASA_CUDA(cudaGetLastError());
                ASA_CUDA(cudaEventRecord(end.get(),stream.get()));ASA_CUDA(cudaEventSynchronize(end.get()));
                float ms=0;ASA_CUDA(cudaEventElapsedTime(&ms,start.get(),end.get()));
                total+=ms;minimum=std::min(minimum,double(ms));
            }
            mean=total/o.repeat;
        };
        auto restore=[&](std::vector<asa::Result>& results) {
            if(o.sample_order=="locality") {
                const auto restore_start=std::chrono::steady_clock::now();asa::restore_sample_order(results,schedule);
                info.restore_ms+=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-restore_start).count();
            }
        };
        measure([&]{asa::asa_texture_kernel<<<blocks,o.block_size,0,stream.get()>>>(in.get(),out.get(),o.samples,o.config,{ti.get(),tm.get(),tw.get()});},
                info.texture_mean_ms,info.texture_min_ms);
        info.milliseconds=info.texture_mean_ms;
        out.download(texture.data(),texture.size());restore(texture);asa::compare(texture,cpu);
        measure([&]{asa::asa_global_kernel<<<blocks,o.block_size,0,stream.get()>>>(in.get(),out.get(),o.samples,o.config,{image.get(),mask.get(),warp.get()});},
                info.global_mean_ms,info.global_min_ms);
        out.download(global.data(),global.size());restore(global);
        asa::compare(global,cpu);asa::compare(texture,global);
    }
    // Checked normal cleanup; destructors remain fallbacks for exceptional exits.
    policy.close();stream.close();
    asa::write_run(o.out,o.config,f,samples,texture,info);
    std::cout<<"PASS CUDA: "<<prop.name<<" CC "<<prop.major<<'.'<<prop.minor<<"; "<<o.samples<<" samples match CPU/global\n";
    return 0;
}catch(const std::exception&e){std::cerr<<"ASA CUDA: "<<e.what()<<'\n';return 1;}}
