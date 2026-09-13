#include "kernels.cuh"
namespace atomos {
__global__ void mitosis_texture(const Node* in,Node* out,std::uint32_t candidates,Config c,TextureTables t){
    const auto k=blockIdx.x*blockDim.x+threadIdx.x;
    if(k<candidates)out[k]=propagate_child(in[k>>1],k&1u,k,c,t);
}
__global__ void mitosis_global(const Node* in,Node* out,std::uint32_t candidates,Config c,HostTables t){
    const auto k=blockIdx.x*blockDim.x+threadIdx.x;
    if(k<candidates)out[k]=propagate_child(in[k>>1],k&1u,k,c,t);
}
__global__ void universal_texture(VMState* s,std::uint32_t* tapes,std::uint32_t count,std::uint32_t bits,
  std::uint32_t states,std::uint32_t halt,std::uint32_t budget,cudaTextureObject_t prog){
    const auto i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=count)return;
    const std::size_t stride=(std::uint64_t(bits)+31)/32;
    auto local=s[i];auto* tape=tapes+std::size_t(i)*stride;
    for(std::uint32_t k=0;k<budget&&local.status==VMStatus::Running;++k)vm_step(local,tape,bits,states,halt,TextureProgram{prog});
    s[i]=local; // one thread owns all words of this machine; no inter-machine races
}
__global__ void universal_global(VMState* s,std::uint32_t* tapes,std::uint32_t count,std::uint32_t bits,
  std::uint32_t states,std::uint32_t halt,std::uint32_t budget,const std::uint32_t* prog){
    const auto i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=count)return;
    const std::size_t stride=(std::uint64_t(bits)+31)/32;
    auto local=s[i];auto* tape=tapes+std::size_t(i)*stride;
    for(std::uint32_t k=0;k<budget&&local.status==VMStatus::Running;++k)vm_step(local,tape,bits,states,halt,HostProgram{prog});
    s[i]=local;
}
__global__ void word_texture(const std::uint32_t* in,std::uint32_t* out,std::uint32_t n,
  cudaTextureObject_t jitter,cudaTextureObject_t mask,bool merge_or){
    const auto i=blockIdx.x*blockDim.x+threadIdx.x;if(i<n)
      out[i]=word_step(in[i],tex1Dfetch<unsigned>(jitter,int(i)),tex1Dfetch<unsigned>(mask,int(i)),merge_or);
}
}
