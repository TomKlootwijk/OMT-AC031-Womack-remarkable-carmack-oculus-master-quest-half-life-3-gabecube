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
}
