#pragma once
#include <cuda_runtime.h>
#include "asa/core.hpp"
#include <stdexcept>
#include <string>
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
class Stream {
    cudaStream_t stream_=nullptr;
public:
    Stream(){ASA_CUDA(cudaStreamCreateWithFlags(&stream_,cudaStreamNonBlocking));}
    ~Stream(){if(stream_){cudaStreamSynchronize(stream_);cudaStreamDestroy(stream_);}}
    Stream(const Stream&)=delete;Stream&operator=(const Stream&)=delete;
    cudaStream_t get()const{return stream_;}
    void close(){if(stream_){ASA_CUDA(cudaStreamSynchronize(stream_));ASA_CUDA(cudaStreamDestroy(stream_));stream_=nullptr;}}
};
// Supported performance hints for an L2 address window, not cache pinning.
class L2AccessPolicy {
    cudaStream_t stream_;
    std::size_t previous_limit_=0;
    bool limit_changed_=false,window_set_=false,reset_needed_=false;
public:
    std::size_t requested_bytes=0,accepted_bytes=0,window_bytes=0;
    std::uintptr_t window_base_address=0;
    int hit_property=0,miss_property=0;float hit_ratio=0;bool active=false;
    explicit L2AccessPolicy(cudaStream_t stream):stream_(stream){}
    ~L2AccessPolicy(){
        if(window_set_||reset_needed_)cudaStreamSynchronize(stream_);
        if(window_set_){cudaStreamAttrValue normal{};cudaStreamSetAttribute(stream_,cudaStreamAttributeAccessPolicyWindow,&normal);}
        if(reset_needed_)cudaCtxResetPersistingL2Cache();
        if(limit_changed_)cudaDeviceSetLimit(cudaLimitPersistingL2CacheSize,previous_limit_);
    }
    L2AccessPolicy(const L2AccessPolicy&)=delete;L2AccessPolicy&operator=(const L2AccessPolicy&)=delete;
    void enable(void* image,std::size_t image_bytes,const cudaDeviceProp& prop){
        if(limit_changed_||window_set_)throw std::logic_error("L2 policy is already configured");
        if(prop.persistingL2CacheMaxSize<=0||prop.accessPolicyMaxWindowSize<=0)
            throw std::runtime_error("device does not expose a persisting L2 access window");
        const std::size_t window=std::min(image_bytes,std::size_t(prop.accessPolicyMaxWindowSize));
        requested_bytes=std::min(window,std::size_t(prop.persistingL2CacheMaxSize));
        ASA_CUDA(cudaDeviceGetLimit(&previous_limit_,cudaLimitPersistingL2CacheSize));
        ASA_CUDA(cudaDeviceSetLimit(cudaLimitPersistingL2CacheSize,requested_bytes));limit_changed_=true;
        ASA_CUDA(cudaDeviceGetLimit(&accepted_bytes,cudaLimitPersistingL2CacheSize));
        if(!accepted_bytes||!window)return;
        cudaStreamAttrValue attribute{};
        attribute.accessPolicyWindow.base_ptr=image;attribute.accessPolicyWindow.num_bytes=window;
        attribute.accessPolicyWindow.hitRatio=float(std::min(1.,double(accepted_bytes)/double(window)));
        attribute.accessPolicyWindow.hitProp=cudaAccessPropertyPersisting;
        attribute.accessPolicyWindow.missProp=cudaAccessPropertyNormal;
        ASA_CUDA(cudaStreamSetAttribute(stream_,cudaStreamAttributeAccessPolicyWindow,&attribute));
        window_set_=true;reset_needed_=true;
        cudaStreamAttrValue observed{};
        ASA_CUDA(cudaStreamGetAttribute(stream_,cudaStreamAttributeAccessPolicyWindow,&observed));
        const auto& actual=observed.accessPolicyWindow;
        const auto image_address=reinterpret_cast<std::uintptr_t>(image);
        const auto actual_address=reinterpret_cast<std::uintptr_t>(actual.base_ptr);
        if(!finite(actual.hitRatio)||actual.hitRatio<0||actual.hitRatio>1||
           int(actual.hitProp)<0||int(actual.hitProp)>2||int(actual.missProp)<0||int(actual.missProp)>1)
            throw std::runtime_error("invalid L2 access-policy readback");
        if(actual.num_bytes&&(actual_address<image_address||actual_address-image_address>image_bytes||
           actual.num_bytes>image_bytes-(actual_address-image_address)))
            throw std::runtime_error("L2 access-policy readback exceeds image allocation");
        window_bytes=actual.num_bytes;window_base_address=actual_address;hit_ratio=actual.hitRatio;
        hit_property=int(actual.hitProp);miss_property=int(actual.missProp);
        active=window_bytes&&hit_ratio>0&&actual.hitProp==cudaAccessPropertyPersisting&&actual.missProp==cudaAccessPropertyNormal;
    }
    void close(){
        if(window_set_||reset_needed_)ASA_CUDA(cudaStreamSynchronize(stream_));
        if(window_set_){cudaStreamAttrValue normal{};ASA_CUDA(cudaStreamSetAttribute(stream_,cudaStreamAttributeAccessPolicyWindow,&normal));window_set_=false;}
        if(reset_needed_){ASA_CUDA(cudaCtxResetPersistingL2Cache());reset_needed_=false;}
        if(limit_changed_){ASA_CUDA(cudaDeviceSetLimit(cudaLimitPersistingL2CacheSize,previous_limit_));limit_changed_=false;}
        active=false;
    }
};
}
