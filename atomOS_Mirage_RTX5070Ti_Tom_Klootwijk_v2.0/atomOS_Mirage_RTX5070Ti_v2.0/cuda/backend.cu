#include "atomos/runtime.hpp"
#include "kernels.cuh"
#include <cuda_runtime.h>
#include <limits>
#include <stdexcept>
#include <sstream>
#include <utility>
namespace atomos {
namespace {
void check(cudaError_t e,const char* what){if(e!=cudaSuccess)throw std::runtime_error(std::string(what)+": "+cudaGetErrorString(e));}
struct Buffer {
    void* p=nullptr;std::size_t bytes=0;
    ~Buffer(){if(p)cudaFree(p);} // destructors never throw
    void allocate(std::size_t n){
        if(n==bytes)return;
        if(p){check(cudaFree(p),"cudaFree");p=nullptr;bytes=0;}
        if(n){check(cudaMalloc(&p,n),"cudaMalloc");bytes=n;}
    }
    template<class T> T* as(){return static_cast<T*>(p);}
    template<class T> void upload(const std::vector<T>& v){allocate(v.size()*sizeof(T));if(bytes)check(cudaMemcpy(p,v.data(),bytes,cudaMemcpyHostToDevice),"upload");}
    template<class T> void download(std::vector<T>& v){if(v.size()*sizeof(T)!=bytes)throw std::runtime_error("download size mismatch");if(bytes)check(cudaMemcpy(v.data(),p,bytes,cudaMemcpyDeviceToHost),"download");}
};
struct Texture {
    cudaTextureObject_t handle=0;
    ~Texture(){if(handle)cudaDestroyTextureObject(handle);}
    void reset(){if(handle){check(cudaDestroyTextureObject(handle),"destroy texture");handle=0;}}
    void bind(Buffer& b,cudaChannelFormatDesc format,std::size_t elements,int device,std::size_t alignment){
        reset();
        // Query the limit for this concrete format; maxTexture1DLinear is deprecated.
        std::size_t max_elements=0;
        check(cudaDeviceGetTexture1DLinearMaxWidth(&max_elements,&format,device),"linear texture limit");
        if(!elements||elements>max_elements||elements>std::size_t(std::numeric_limits<int>::max()))
            throw std::runtime_error("linear texture element limit");
        if(!b.p||!alignment||reinterpret_cast<std::uintptr_t>(b.p)%alignment)
            throw std::runtime_error("linear texture allocation alignment");
        cudaResourceDesc r{};r.resType=cudaResourceTypeLinear;r.res.linear.devPtr=b.p;r.res.linear.desc=format;r.res.linear.sizeInBytes=b.bytes;
        cudaTextureDesc t{};t.readMode=cudaReadModeElementType;t.normalizedCoords=0;t.filterMode=cudaFilterModePoint;t.addressMode[0]=cudaAddressModeClamp;
        // Linear-resource addressing/filter modes are ignored. All indices are explicitly bounded.
        check(cudaCreateTextureObject(&handle,&r,&t,nullptr),"create texture");
    }
};
struct Events {cudaEvent_t begin=nullptr,end=nullptr;
    Events(){check(cudaEventCreate(&begin),"event begin");auto e=cudaEventCreate(&end);if(e!=cudaSuccess){cudaEventDestroy(begin);begin=nullptr;check(e,"event end");}}
    ~Events(){if(begin)cudaEventDestroy(begin);if(end)cudaEventDestroy(end);}
};
}
struct GPUBackend::Impl {
    Config c;bool texture;int device;cudaDeviceProp prop{};double last_ms=0;
    // Textures are destroyed before their backing allocations (reverse member destruction order).
    Buffer angles,mask,jitter,input,output,states,tapes,program;
    Texture angle_tex,mask_tex,jitter_tex,program_tex;
    Impl(const Config& cfg,const Tables&t,bool tex,int dev):c(cfg),texture(tex),device(dev){
        validate_config(c);check(cudaSetDevice(dev),"select device");check(cudaGetDeviceProperties(&prop,dev),"device properties");
        if(prop.major!=12||prop.minor!=0)throw std::runtime_error("this package targets compute capability 12.0; rebuild and review before retargeting");
        if(t.angles.size()!=c.n_phi||t.mask.size()!=(std::uint64_t(c.n_rho)*c.n_phi+31)/32)throw std::runtime_error("table shape mismatch");
        angles.upload(t.angles);mask.upload(t.mask);
        if(texture){angle_tex.bind(angles,cudaCreateChannelDesc<float2>(),t.angles.size(),device,prop.textureAlignment);
                    mask_tex.bind(mask,cudaCreateChannelDesc<unsigned>(),t.mask.size(),device,prop.textureAlignment);}
    }
};
GPUBackend::GPUBackend(const Config&c,const Tables&t,bool tex,int dev):impl_(new Impl(c,t,tex,dev)){}
GPUBackend::~GPUBackend()=default;
std::vector<Node> GPUBackend::propagate(const std::vector<Node>& in,const std::vector<std::uint32_t>& j,unsigned repeats){
    auto&p=*impl_;check(cudaSetDevice(p.device),"select device");
    if(in.empty()){p.last_ms=0;return{};}
    if(in.size()>(1u<<19)||j.size()<(in.size()*2+31)/32||repeats<1||repeats>10000)throw std::invalid_argument("GPU budget or jitter shape");
    // No texture backing storage is changed while a kernel that reads it is in flight.
    p.jitter_tex.reset();p.input.upload(in);p.output.allocate(2*in.size()*sizeof(Node));p.jitter.upload(j);
    if(p.texture)p.jitter_tex.bind(p.jitter,cudaCreateChannelDesc<unsigned>(),j.size(),p.device,p.prop.textureAlignment);
    const auto n=std::uint32_t(in.size()*2),blocks=(n+255)/256;
    auto launch=[&](){
        if(p.texture)mitosis_texture<<<blocks,256>>>(p.input.as<Node>(),p.output.as<Node>(),n,p.c,TextureTables{p.angle_tex.handle,p.mask_tex.handle,p.jitter_tex.handle});
        else mitosis_global<<<blocks,256>>>(p.input.as<Node>(),p.output.as<Node>(),n,p.c,HostTables{p.angles.as<Vec2>(),p.mask.as<std::uint32_t>(),p.jitter.as<std::uint32_t>()});
        check(cudaGetLastError(),"launch mitosis");};
    // One warm-up launch, then repeat the SAME input batch. This is not simulated extra time.
    launch();check(cudaDeviceSynchronize(),"warm-up synchronization");Events e;check(cudaEventRecord(e.begin),"record begin");
    for(unsigned k=0;k<repeats;++k)launch();
    check(cudaEventRecord(e.end),"record end");check(cudaEventSynchronize(e.end),"kernel synchronization");
    float ms=0;check(cudaEventElapsedTime(&ms,e.begin,e.end),"elapsed time");p.last_ms=ms/repeats;
    std::vector<Node> out(in.size()*2);p.output.download(out);return out;
}
void GPUBackend::universal(std::vector<VMState>& s,std::vector<std::uint32_t>& tape,std::uint32_t bits,const Program&prog,unsigned budget){
    auto&p=*impl_;check(cudaSetDevice(p.device),"select device");
    if(s.empty())return;
    const std::size_t stride=(std::uint64_t(bits)+31)/32;
    if(!bits||bits>0x7fffffffu||s.size()>(1u<<20)||tape.size()!=s.size()*stride||budget<1||budget>100000
      ||prog.states<1||prog.states>65536||prog.halt>=prog.states||prog.words.size()!=std::size_t(prog.states)*2)throw std::invalid_argument("invalid GPU VM shape or budget");
    p.program_tex.reset();p.states.upload(s);p.tapes.upload(tape);p.program.upload(prog.words);
    if(p.texture)p.program_tex.bind(p.program,cudaCreateChannelDesc<unsigned>(),prog.words.size(),p.device,p.prop.textureAlignment);
    Events e;check(cudaEventRecord(e.begin),"VM begin");const auto n=std::uint32_t(s.size()),blocks=(n+127)/128;
    if(p.texture)universal_texture<<<blocks,128>>>(p.states.as<VMState>(),p.tapes.as<std::uint32_t>(),n,bits,prog.states,prog.halt,budget,p.program_tex.handle);
    else universal_global<<<blocks,128>>>(p.states.as<VMState>(),p.tapes.as<std::uint32_t>(),n,bits,prog.states,prog.halt,budget,p.program.as<std::uint32_t>());
    check(cudaGetLastError(),"launch universal");check(cudaEventRecord(e.end),"VM end");check(cudaEventSynchronize(e.end),"VM synchronization");float ms=0;
    check(cudaEventElapsedTime(&ms,e.begin,e.end),"VM time");p.last_ms=ms;p.states.download(s);p.tapes.download(tape);
}
double GPUBackend::last_kernel_ms()const{return impl_->last_ms;}
std::string GPUBackend::device_description()const{std::ostringstream s;const auto&p=impl_->prop;s<<p.name<<"; CC "<<p.major<<'.'<<p.minor<<"; VRAM "<<p.totalGlobalMem<<" bytes; "<<(impl_->texture?"texture":"global")<<" reads";return s.str();}
}
