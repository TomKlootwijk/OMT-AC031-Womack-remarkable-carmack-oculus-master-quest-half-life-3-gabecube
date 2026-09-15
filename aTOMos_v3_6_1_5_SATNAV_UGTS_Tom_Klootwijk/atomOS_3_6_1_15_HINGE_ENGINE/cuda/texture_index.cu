#include "atomos/gpu_kernels.cuh"
namespace atomos {
namespace {
constexpr float kFilterPad=0x1p-14f;
// One 64x64 bit transpose block is 64 machine words. This is an involution.
__global__ void expand_words(cudaTextureObject_t packed,uint64_t* words,size_t count) {
  const size_t i=blockIdx.x*blockDim.x+threadIdx.x;
  if(i>=count)return;
  const size_t block=i/64, column=i%64;
  uint64_t word=0;
  for(unsigned bit=0;bit<64;++bit){
    const size_t k=block*64+bit;
    const uint4 v=tex1Dfetch<uint4>(packed,int(k/2));
    const uint64_t plane=(k&1)?(uint64_t(v.z)|(uint64_t(v.w)<<32)):
                                      (uint64_t(v.x)|(uint64_t(v.y)<<32));
    word|=((plane>>column)&1ull)<<bit;
  }
  words[i]=word;
}

template<bool UseTexture>
__device__ GpuNode read_node(cudaTextureObject_t tex,const GpuNode* nodes,uint32_t i){
  if(!UseTexture)return nodes[i];
  const uint4 a=tex1Dfetch<uint4>(tex,int(3*i));
  const uint4 b=tex1Dfetch<uint4>(tex,int(3*i+1));
  const uint4 c=tex1Dfetch<uint4>(tex,int(3*i+2));
  GpuNode n;
  n.lo[0]=__uint_as_float(a.x);n.lo[1]=__uint_as_float(a.y);n.lo[2]=__uint_as_float(a.z);n.left=a.w;
  n.hi[0]=__uint_as_float(b.x);n.hi[1]=__uint_as_float(b.y);n.hi[2]=__uint_as_float(b.z);n.right=b.w;
  n.begin=c.x;n.count=c.y;n.escape=c.z;n.axis=c.w;return n;
}
template<bool UseTexture>
__device__ float3 read_point(cudaTextureObject_t tex,const Point* points,uint32_t i){
  if(!UseTexture)return make_float3(float(points[i].x),float(points[i].y),float(points[i].z));
  const uint4 a=tex1Dfetch<uint4>(tex,int(2*i));
  const uint4 b=tex1Dfetch<uint4>(tex,int(2*i+1));
  return make_float3(float(__hiloint2double(a.y,a.x)),
                    float(__hiloint2double(a.w,a.z)),float(__hiloint2double(b.y,b.x)));
}
__device__ float lower_distance(const GpuNode& n,const GpuQuery& q){
  const float x=fmaxf(fmaxf(n.lo[0]-q.x,q.x-n.hi[0]),0.f);
  const float y=fmaxf(fmaxf(n.lo[1]-q.y,q.y-n.hi[1]),0.f);
  const float z=fmaxf(fmaxf(n.lo[2]-q.z,q.z-n.hi[2]),0.f);
  return x*x+y*y+z*z;
}
template<bool UseTexture>
__global__ void radius_kernel(cudaTextureObject_t nt,cudaTextureObject_t pt,
 const GpuNode* nodes,const Point* points,uint32_t node_count,const GpuQuery* queries,
 uint32_t query_count,uint32_t capacity,uint32_t* candidates,uint32_t* counts){
  const uint32_t qi=blockIdx.x*blockDim.x+threadIdx.x;if(qi>=query_count)return;
  const GpuQuery q=queries[qi];uint32_t n=0,count=0;
  // Preorder escape links avoid local traversal stacks and texture writes.
  while(n<node_count){
    const GpuNode box=read_node<UseTexture>(nt,nodes,n);
    if(lower_distance(box,q)>q.radius+kFilterPad){n=box.escape;continue;}
    if(box.count==0){n=box.left;continue;}
    for(uint32_t j=box.begin;j<box.begin+box.count;++j){
      const float3 p=read_point<UseTexture>(pt,points,j);
      const float dx=p.x-q.x,dy=p.y-q.y,dz=p.z-q.z;
      if(dx*dx+dy*dy+dz*dz<=q.radius+kFilterPad){
        if(count<capacity)candidates[size_t(qi)*capacity+count]=j;
        ++count;
      }
    }
    n=box.escape;
  }
  counts[qi]=count;
}
__device__ uint64_t table(uint32_t lut,uint64_t q,uint64_t a,uint64_t mask){
  uint64_t out=0;
  if(lut&1)out|=~q&~a;if(lut&2)out|=q&~a;
  if(lut&4)out|=~q&a;if(lut&8)out|=q&a;
  return out&mask;
}
__global__ void hinge_kernel(HingeState* states,const HingeInput* inputs,uint32_t count,WordProfile p){
  const uint32_t i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=count)return;
  HingeState s=states[i];const HingeInput in=inputs[i];
  if(!in.valid){s.status=1;states[i]=s;return;}
  if(s.accepted && in.event<=s.last_event){
    s.status=(in.event==s.last_event && in.drive==s.last_drive)?0:2;
    states[i]=s;return;
  }
  const uint64_t old=s.q, d=in.drive&p.valid_mask;
  uint64_t y=table(p.x_lut,old,d,p.valid_mask)&p.a0&p.n0;
  if(y&p.b0)y=0;
  y&=p.a1&p.n1;if(y&p.b1)y=0;
  const uint64_t j=table(p.j_lut,old,y,p.valid_mask), k=table(p.k_lut,old,y,p.valid_mask);
  s.q=((j&~old)|(~k&old))&p.valid_mask;
  // This API consumes explicit accepted hinge events, not repeated levels.
  s.parity^=1;s.orientation^=(in.reversing&1);
  s.last_event=in.event;s.last_drive=in.drive;s.accepted=1;s.status=0;states[i]=s;
}

}
void launch_expand(cudaTextureObject_t packed,uint64_t* words,size_t count){
  expand_words<<<unsigned((count+127)/128),128>>>(packed,words,count);
}
void launch_radius(bool texture_fetch,cudaTextureObject_t nt,cudaTextureObject_t pt,
 const GpuNode* nodes,const Point* points,uint32_t node_count,const GpuQuery* queries,
 uint32_t query_count,uint32_t capacity,uint32_t* candidates,uint32_t* counts){
  if(texture_fetch)radius_kernel<true><<<unsigned((query_count+127)/128),128>>>(nt,pt,nodes,points,node_count,queries,query_count,capacity,candidates,counts);
  else radius_kernel<false><<<unsigned((query_count+127)/128),128>>>(nt,pt,nodes,points,node_count,queries,query_count,capacity,candidates,counts);
}
void launch_hinges(HingeState* states,const HingeInput* inputs,uint32_t count,WordProfile profile){
  hinge_kernel<<<unsigned((count+127)/128),128>>>(states,inputs,count,profile);
}
}
