#include "atomos/resident_kernels.cuh"
#include <stdexcept>

namespace atomos {
namespace {
constexpr float kFilterPad = 0x1p-14f;
static_assert(sizeof(ResidentNode)==48,"resident node texture layout");
static_assert(sizeof(ResidentQuery)==32,"resident query texture layout");
static_assert(sizeof(Point)==32,"resident point texture layout");

template<bool Texture>
__device__ ResidentNode read_node(ResidentDeviceView view,uint32_t i){
  if(!Texture)return view.nodes[i];
  const uint4 a=tex1Dfetch<uint4>(view.node_texture,int(3*i));
  const uint4 b=tex1Dfetch<uint4>(view.node_texture,int(3*i+1));
  const uint4 c=tex1Dfetch<uint4>(view.node_texture,int(3*i+2));
  ResidentNode n;
  n.lower[0]=__uint_as_float(a.x);n.lower[1]=__uint_as_float(a.y);n.lower[2]=__uint_as_float(a.z);n.left=a.w;
  n.upper[0]=__uint_as_float(b.x);n.upper[1]=__uint_as_float(b.y);n.upper[2]=__uint_as_float(b.z);n.right=b.w;
  n.begin=c.x;n.count=c.y;n.escape=c.z;n.axis=c.w;return n;
}
template<bool Texture>
__device__ Point read_point(ResidentDeviceView view,uint32_t i){
  if(!Texture)return view.points[i];
  const uint4 a=tex1Dfetch<uint4>(view.point_texture,int(2*i));
  const uint4 b=tex1Dfetch<uint4>(view.point_texture,int(2*i+1));
  return {__hiloint2double(a.y,a.x),__hiloint2double(a.w,a.z),
          __hiloint2double(b.y,b.x),uint64_t(b.z)|(uint64_t(b.w)<<32)};
}
template<bool Texture>
__device__ ResidentQuery read_query(ResidentDeviceView view,uint32_t i){
  if(!Texture)return view.queries[i];
  const uint4 a=tex1Dfetch<uint4>(view.query_texture,int(2*i));
  const uint4 b=tex1Dfetch<uint4>(view.query_texture,int(2*i+1));
  return {__hiloint2double(a.y,a.x),__hiloint2double(a.w,a.z),
          __hiloint2double(b.y,b.x),__hiloint2double(b.w,b.z)};
}
__device__ bool same_coordinate(double a,double b){
  const uint64_t aa=uint64_t(__double_as_longlong(a)),bb=uint64_t(__double_as_longlong(b));
  return aa==bb || ((aa|bb)&0x7fffffffffffffffull)==0;
}
__device__ float box_lower(const ResidentNode& n,float x,float y,float z){
  const float dx=fmaxf(fmaxf(n.lower[0]-x,x-n.upper[0]),0.f);
  const float dy=fmaxf(fmaxf(n.lower[1]-y,y-n.upper[1]),0.f);
  const float dz=fmaxf(fmaxf(n.lower[2]-z,z-n.upper[2]),0.f);
  return (dx*dx+dy*dy)+dz*dz;
}

template<bool Texture,bool Selected>
__global__ void resident_radius_kernel(ResidentDeviceView view,const uint64_t* selectors,
 uint32_t stride,uint32_t lanes){
  const uint32_t lane=blockIdx.x*blockDim.x+threadIdx.x;
  if(lane>=lanes)return;
  const uint32_t qi=Selected?2*lane+uint32_t(selectors[uint64_t(lane)*stride]&1):lane;
  const ResidentQuery q=read_query<Texture>(view,qi);
  ResidentCount result{};
  // This is an exact normalized-direction domain certificate, not a rounded
  // chord-distance shortcut. Every valid direction lies within chord^2=4.
  if(q.radius2==4.0){result.definite_inside=view.point_count;view.counts[lane]=result;return;}
  const float qx=float(q.x),qy=float(q.y),qz=float(q.z);
  const float filter_radius=__double2float_ru(q.radius2)+kFilterPad;
  const double inside_limit=q.radius2-kResidentDistanceMargin;
  const double outside_limit=q.radius2+kResidentDistanceMargin;
  uint32_t node=0;
  while(node<view.node_count){
    const ResidentNode n=read_node<Texture>(view,node);
    if(box_lower(n,qx,qy,qz)>filter_radius){node=n.escape;continue;}
    if(!n.count){node=n.left;continue;}
    for(uint32_t i=n.begin;i<n.begin+n.count;++i){
      const Point p=read_point<Texture>(view,i);
      if(same_coordinate(p.x,q.x)&&same_coordinate(p.y,q.y)&&same_coordinate(p.z,q.z)){
        ++result.definite_inside;continue;
      }
      const double dx=p.x-q.x,dy=p.y-q.y,dz=p.z-q.z;
      const double d2=(dx*dx+dy*dy)+dz*dz;
      if(d2<=inside_limit)++result.definite_inside;
      else if(!(d2>outside_limit))++result.unresolved;
    }
    node=n.escape;
  }
  view.counts[lane]=result;
}
}

void launch_resident_radius(ResidentDeviceView view,bool texture_fetch){
  if(!view.query_count)return;
  const unsigned blocks=unsigned((uint64_t(view.query_count)+127)/128);
  if(texture_fetch)resident_radius_kernel<true,false><<<blocks,128>>>(view,nullptr,0,view.query_count);
  else resident_radius_kernel<false,false><<<blocks,128>>>(view,nullptr,0,view.query_count);
}
void launch_resident_selected(ResidentDeviceView view,bool texture_fetch,
 const uint64_t* selector_words,uint32_t stride_words,uint32_t lanes){
  if(lanes>view.query_count/2||!stride_words||(lanes&&!selector_words))
    throw std::invalid_argument("selected resident query requires paired alternatives and valid selector stride");
  if(!lanes)return;
  const unsigned blocks=unsigned((uint64_t(lanes)+127)/128);
  if(texture_fetch)resident_radius_kernel<true,true><<<blocks,128>>>(view,selector_words,stride_words,lanes);
  else resident_radius_kernel<false,true><<<blocks,128>>>(view,selector_words,stride_words,lanes);
}
} // namespace atomos
