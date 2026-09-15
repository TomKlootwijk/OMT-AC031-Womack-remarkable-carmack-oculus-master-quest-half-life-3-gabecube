#pragma once
#include "atomos/texture_index.hpp"
#include <cuda_runtime.h>
namespace atomos {
struct GpuNode { float lo[3]; uint32_t left; float hi[3]; uint32_t right;
                 uint32_t begin,count,escape,axis; };
struct GpuQuery { float x,y,z,radius; };
void launch_expand(cudaTextureObject_t packed,uint64_t* words,size_t count);
void launch_radius(bool texture_fetch,cudaTextureObject_t nt,cudaTextureObject_t pt,
  const GpuNode* nodes,const Point* points,uint32_t node_count,const GpuQuery* queries,
  uint32_t query_count,uint32_t capacity,uint32_t* candidates,uint32_t* counts);
void launch_compact_candidates(const uint32_t* candidates,const uint64_t* offsets,
  uint32_t query_count,uint32_t capacity,uint32_t* compacted);
void launch_hinges(HingeState* states,const HingeInput* inputs,uint32_t count,WordProfile profile);
}
