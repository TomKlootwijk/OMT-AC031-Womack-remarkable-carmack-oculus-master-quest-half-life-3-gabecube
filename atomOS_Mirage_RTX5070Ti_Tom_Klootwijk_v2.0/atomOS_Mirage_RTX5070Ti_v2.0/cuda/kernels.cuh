#pragma once
#include <cuda_runtime.h>
#include "atomos/core.hpp"
namespace atomos {
struct TextureTables {
    cudaTextureObject_t angles,mask,jitter;
    __device__ Vec2 angle(std::uint32_t j)const{auto x=tex1Dfetch<float2>(angles,int(j));return{x.x,x.y};}
    __device__ std::uint32_t mask_word(std::uint32_t j)const{return tex1Dfetch<unsigned>(mask,int(j));}
    __device__ std::uint32_t jitter_word(std::uint32_t j)const{return tex1Dfetch<unsigned>(jitter,int(j));}
};
struct TextureProgram {cudaTextureObject_t program;
    __device__ std::uint32_t fetch(std::uint32_t i)const{return tex1Dfetch<unsigned>(program,int(i));}};
__global__ void mitosis_texture(const Node*,Node*,std::uint32_t,Config,TextureTables);
__global__ void mitosis_global(const Node*,Node*,std::uint32_t,Config,HostTables);
__global__ void universal_texture(VMState*,std::uint32_t*,std::uint32_t,std::uint32_t,std::uint32_t,std::uint32_t,std::uint32_t,cudaTextureObject_t);
__global__ void universal_global(VMState*,std::uint32_t*,std::uint32_t,std::uint32_t,std::uint32_t,std::uint32_t,std::uint32_t,const std::uint32_t*);
__global__ void word_texture(const std::uint32_t*,std::uint32_t*,std::uint32_t,cudaTextureObject_t,cudaTextureObject_t,bool);
}
