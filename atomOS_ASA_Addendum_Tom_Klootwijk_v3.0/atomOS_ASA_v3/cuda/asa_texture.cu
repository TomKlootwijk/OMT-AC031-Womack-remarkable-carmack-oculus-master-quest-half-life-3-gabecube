#include <cuda_runtime.h>
#include "asa/io.hpp"
#include <algorithm>
namespace asa {
inline void check_cuda(cudaError_t e,const char* expression) {
    if(e!=cudaSuccess)throw std::runtime_error(std::string(expression)+": "+cudaGetErrorString(e));
}
#define ASA_CUDA(expr) ::asa::check_cuda((expr),#expr)
struct TextureData {
    cudaTextureObject_t image,mask,warp;
    __device__ float value(u32 k)const{return tex1Dfetch<float>(image,int(k));}
    __device__ u32 maskword(u32 k)const{return tex1Dfetch<unsigned int>(mask,int(k));}
    __device__ Warp lens(u32 k)const{const float2 v=tex1Dfetch<float2>(warp,int(k));return {v.x,v.y};}
};
__global__ void asa_texture_kernel(const Sample* in,Result* out,u32 count,Config config,TextureData data) {
    const u32 i=blockIdx.x*blockDim.x+threadIdx.x;
    if(i<count)out[i]=evaluate(in[i],config,data);
}
__global__ void asa_global_kernel(const Sample* in,Result* out,u32 count,Config config,HostData data) {
    const u32 i=blockIdx.x*blockDim.x+threadIdx.x;
    if(i<count)out[i]=evaluate(in[i],config,data);
}
template<class T>class Buffer {
    T* ptr_=nullptr;std::size_t capacity_=0;
public:
    explicit Buffer(std::size_t n):capacity_(n){if(n)ASA_CUDA(cudaMalloc(reinterpret_cast<void**>(&ptr_),n*sizeof(T)));}
    ~Buffer(){if(ptr_)cudaFree(ptr_);}
    Buffer(const Buffer&)=delete;Buffer&operator=(const Buffer&)=delete;
    T* get()const{return ptr_;}
    void upload(const T* p,std::size_t n){if(n>capacity_)throw std::runtime_error("upload size");if(n)ASA_CUDA(cudaMemcpy(ptr_,p,n*sizeof(T),cudaMemcpyHostToDevice));}
    void download(T* p,std::size_t n){if(n>capacity_)throw std::runtime_error("download size");if(n)ASA_CUDA(cudaMemcpy(p,ptr_,n*sizeof(T),cudaMemcpyDeviceToHost));}
};
class Texture {
    cudaTextureObject_t object_=0;
public:
    Texture(void* ptr,std::size_t bytes,cudaChannelFormatDesc desc,std::size_t texels,const cudaDeviceProp& prop){
        if(texels>std::size_t(prop.maxTexture1DLinear))throw std::runtime_error("linear texture exceeds device limit");
        if(reinterpret_cast<std::uintptr_t>(ptr)%prop.textureAlignment)throw std::runtime_error("texture alignment mismatch");
        cudaResourceDesc resource{};resource.resType=cudaResourceTypeLinear;
        resource.res.linear.devPtr=ptr;resource.res.linear.desc=desc;resource.res.linear.sizeInBytes=bytes;
        cudaTextureDesc texture{};texture.readMode=cudaReadModeElementType;
        texture.filterMode=cudaFilterModePoint;texture.normalizedCoords=0;
        ASA_CUDA(cudaCreateTextureObject(&object_,&resource,&texture,nullptr));
    }
    ~Texture(){if(object_)cudaDestroyTextureObject(object_);}
    Texture(const Texture&)=delete;Texture&operator=(const Texture&)=delete;
    cudaTextureObject_t get()const{return object_;}
};
class Event {
    cudaEvent_t e_{};
public:
    Event(){ASA_CUDA(cudaEventCreate(&e_));}~Event(){cudaEventDestroy(e_);}
    Event(const Event&)=delete;Event&operator=(const Event&)=delete;
    cudaEvent_t get()const{return e_;}
};
}
int main(int argc,char**argv){try{
    const auto o=asa::options(argc,argv);if(o.help){asa::help();return 0;}
    int count=0;ASA_CUDA(cudaGetDeviceCount(&count));
    if(o.device>=unsigned(count))throw std::runtime_error("selected CUDA device not available");
    ASA_CUDA(cudaSetDevice(int(o.device)));cudaDeviceProp prop{};ASA_CUDA(cudaGetDeviceProperties(&prop,int(o.device)));
    std::size_t free_bytes=0,total_bytes=0;ASA_CUDA(cudaMemGetInfo(&free_bytes,&total_bytes));
    int driver=0,runtime=0;ASA_CUDA(cudaDriverGetVersion(&driver));ASA_CUDA(cudaRuntimeGetVersion(&runtime));
    if(o.device_only){
        std::cout<<"{\"name\":"<<asa::quoted(prop.name)<<",\"cc_major\":"<<prop.major<<",\"cc_minor\":"<<prop.minor
            <<",\"total_bytes\":"<<total_bytes<<",\"free_bytes\":"<<free_bytes<<",\"driver\":"<<driver
            <<",\"runtime\":"<<runtime<<",\"max_texture_1d_linear\":"<<prop.maxTexture1DLinear<<"}\n";return 0;
    }
    // Budget rule: <= configured budget, <= half of currently free VRAM,
    // and at least 512 MiB remains outside this run's payload.
    const asa::u64 bytes=asa::required_bytes(o.config,o.samples),reserve=512ull*1048576;
    if(free_bytes<=reserve||bytes>free_bytes-reserve||bytes>free_bytes/2)
        throw std::runtime_error("insufficient free VRAM for payload plus reserve");
    const asa::Fixture f(o.config);const auto samples=asa::make_samples(o.samples,o.config);
    const auto cpu=asa::cpu_run(o.config,f,samples);
    asa::Buffer<float> image(f.image.size());asa::Buffer<asa::u32> mask(f.mask.size());asa::Buffer<asa::Warp> warp(f.warp.size());
    asa::Buffer<asa::Sample> in(samples.size());asa::Buffer<asa::Result> out(samples.size());
    image.upload(f.image.data(),f.image.size());mask.upload(f.mask.data(),f.mask.size());warp.upload(f.warp.data(),f.warp.size());
    in.upload(samples.data(),samples.size());
    asa::Texture ti(image.get(),f.image.size()*4,cudaCreateChannelDesc<float>(),f.image.size(),prop);
    asa::Texture tm(mask.get(),f.mask.size()*4,cudaCreateChannelDesc<unsigned int>(),f.mask.size(),prop);
    asa::Texture tw(warp.get(),f.warp.size()*8,cudaCreateChannelDesc<float2>(),f.warp.size(),prop);
    std::vector<asa::Result> texture(samples.size()),global(samples.size());
    asa::RunInfo info;info.backend="CUDA texture + global differential";info.device=prop.name;info.gpu=true;
    info.total_vram=total_bytes;info.free_vram=free_bytes;
    if(o.samples){
        const asa::u32 blocks=(o.samples+255u)/256u;asa::Event start,end;
        ASA_CUDA(cudaEventRecord(start.get()));
        asa::asa_texture_kernel<<<blocks,256>>>(in.get(),out.get(),o.samples,o.config,{ti.get(),tm.get(),tw.get()});
        ASA_CUDA(cudaGetLastError());ASA_CUDA(cudaEventRecord(end.get()));ASA_CUDA(cudaEventSynchronize(end.get()));
        float ms=0;ASA_CUDA(cudaEventElapsedTime(&ms,start.get(),end.get()));info.milliseconds=ms;
        out.download(texture.data(),texture.size());asa::compare(texture,cpu);
        asa::asa_global_kernel<<<blocks,256>>>(in.get(),out.get(),o.samples,o.config,{image.get(),mask.get(),warp.get()});
        ASA_CUDA(cudaGetLastError());ASA_CUDA(cudaDeviceSynchronize());out.download(global.data(),global.size());
        asa::compare(global,cpu);asa::compare(texture,global);
    }
    asa::write_run(o.out,o.config,f,samples,texture,info);
    std::cout<<"PASS CUDA: "<<prop.name<<" CC "<<prop.major<<'.'<<prop.minor<<"; "<<o.samples<<" samples match CPU/global\n";
    return 0;
}catch(const std::exception&e){std::cerr<<"ASA CUDA: "<<e.what()<<'\n';return 1;}}
