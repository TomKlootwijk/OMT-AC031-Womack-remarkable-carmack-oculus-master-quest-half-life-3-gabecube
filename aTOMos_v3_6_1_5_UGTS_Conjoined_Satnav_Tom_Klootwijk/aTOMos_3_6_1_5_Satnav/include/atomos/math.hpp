#pragma once
#include <cmath>
#include <cstdint>
#include <limits>
#ifdef __CUDACC__
#define AO_HD __host__ __device__
#else
#define AO_HD
#endif
namespace ao {
constexpr double pi=3.141592653589793238462643383279502884, tau=2*pi;
constexpr double light_speed=299792458.0;
AO_HD inline bool finite(double x) { return x==x && x<=1.7976931348623157e308 && x>=-1.7976931348623157e308; }
AO_HD inline double bad() {
#ifdef __CUDA_ARCH__
 return __longlong_as_double(0x7ff8000000000000LL);
#else
 return std::numeric_limits<double>::quiet_NaN();
#endif
}
AO_HD inline double sq(double x){return x*x;}
AO_HD inline double clamp(double v,double a,double b){return v<a?a:v>b?b:v;}
AO_HD inline double wrap(double x,double period=tau){
 double v=::fmod(x,period);if(v>=period/2)v-=period;if(v< -period/2)v+=period;return v==0?0:v;
}
AO_HD inline unsigned popcount(std::uint32_t x){
#ifdef __CUDA_ARCH__
 return __popc(x);
#else
 x=x-((x>>1)&0x55555555u);x=(x&0x33333333u)+((x>>2)&0x33333333u);
 x=(x+(x>>4))&0x0f0f0f0fu;return (x*0x01010101u)>>24;
#endif
}
struct Vec3 {double x,y,z;};
AO_HD inline Vec3 add(Vec3 a,Vec3 b){return {a.x+b.x,a.y+b.y,a.z+b.z};}
AO_HD inline Vec3 sub(Vec3 a,Vec3 b){return {a.x-b.x,a.y-b.y,a.z-b.z};}
AO_HD inline Vec3 scale(Vec3 a,double k){return {a.x*k,a.y*k,a.z*k};}
AO_HD inline double dot(Vec3 a,Vec3 b){return a.x*b.x+a.y*b.y+a.z*b.z;}
AO_HD inline double norm(Vec3 a){return ::sqrt(dot(a,a));}
AO_HD inline double segment_distance(double q,double z,double ax,double az,double bx,double bz){
 double dx=bx-ax,dz=bz-az;double t=clamp(((q-ax)*dx+(z-az)*dz)/(dx*dx+dz*dz),0,1);
 return ::hypot(q-(ax+t*dx),z-(az+t*dz));
}
struct Cone {Vec3 apex,axis;double slant,half_angle;};
AO_HD inline double cone_sdf(Vec3 x,const Cone& c){
 const double h=c.slant*::cos(c.half_angle),r=c.slant*::sin(c.half_angle);
 Vec3 p=sub(x,c.apex);double z=dot(c.axis,p),q=norm(sub(p,scale(c.axis,z)));
 double d1=segment_distance(q,z,0,0,r,h),d2=segment_distance(q,z,r,h,-r,h),d3=segment_distance(q,z,-r,h,0,0);
 double d=::fmin(d1,::fmin(d2,d3));bool inside=z>=0&&z<=h&&q*h<=z*r;return inside?-d:d;
}
AO_HD inline double sphere_sdf(Vec3 x,Vec3 centre,double radius){return norm(sub(x,centre))-radius;}
struct Interval {double lo,hi;};
AO_HD inline Interval sweep_interval(Vec3 x,const Cone& cone,Vec3 translation,unsigned samples){
 if(samples<2)return {bad(),bad()};
 double m=1.7976931348623157e308;
 for(unsigned i=0;i<samples;++i)m=::fmin(m,cone_sdf(sub(x,scale(translation,double(i)/(samples-1))),cone));
 return {m-norm(translation)/(2*(samples-1)),m};
}
AO_HD inline int relation(Interval a,double margin){
 if(!finite(a.lo)||!finite(a.hi)||a.lo>a.hi)return 2;
 return a.hi < -margin?-1:a.lo>margin?1:0; // interior, unresolved band, exterior
}
AO_HD inline std::uint32_t low_mask(unsigned n){return n>=32?0xffffffffu:n==0?0u:(1u<<n)-1u;}
struct CoreWord {std::uint32_t asa,na,hits,output;};
AO_HD inline CoreWord asa_word(std::uint32_t x,std::uint32_t a,std::uint32_t n,std::uint32_t b,std::uint32_t valid){
 CoreWord r{};r.asa=x&a&valid;r.na=r.asa&n;r.hits=popcount(r.na&b);r.output=r.hits?0:r.na;return r;
}
AO_HD inline unsigned jk(unsigned q,unsigned j,unsigned k){return (j&(q^1u))|((k^1u)&q);}
AO_HD inline unsigned blend(unsigned n,unsigned a,unsigned b){return n^a^b;}
struct Quantized {std::uint32_t rho,theta,time,phi;};
AO_HD inline std::uint64_t pack_contiguous(Quantized q){return (std::uint64_t(q.rho)<<44)|(std::uint64_t(q.theta)<<26)|(std::uint64_t(q.time)<<12)|q.phi;}
AO_HD inline Quantized unpack_contiguous(std::uint64_t k){return {std::uint32_t(k>>44),std::uint32_t((k>>26)&0x3ffffu),std::uint32_t((k>>12)&0x3fffu),std::uint32_t(k&0xfffu)};}
AO_HD inline std::uint64_t pack_morton(Quantized q){
 const int widths[4]={20,18,14,12};const std::uint32_t f[4]={q.rho,q.theta,q.time,q.phi};std::uint64_t k=0;
 for(int depth=0;depth<20;++depth)for(int j=0;j<4;++j)if(depth<widths[j])k=(k<<1)|((f[j]>>(widths[j]-1-depth))&1u);
 return k;
}
AO_HD inline Quantized unpack_morton(std::uint64_t k){
 const int widths[4]={20,18,14,12};std::uint32_t f[4]={0,0,0,0};int bit=63;
 for(int depth=0;depth<20;++depth)for(int j=0;j<4;++j)if(depth<widths[j]){f[j]=(f[j]<<1)|std::uint32_t((k>>bit)&1u);--bit;}
 return {f[0],f[1],f[2],f[3]};
}
AO_HD inline unsigned periodic_index(double a,unsigned count){double v=::fmod(a,tau);if(v<0)v+=tau;unsigned q=unsigned(::floor(v/tau*count));return q>=count?0:q;}
AO_HD inline Quantized quantize(double rho,double theta,std::uint64_t tick,double phi){
 return {std::uint32_t(::floor((rho+20)/20*1048575.0+.5)),periodic_index(theta,262144),std::uint32_t(tick&16383u),periodic_index(phi,4096)};
}
// Chart-only maps; never applied to ECEF position estimates.
struct Wrapped {double rho,theta,phi;int orientation;long long wraps;};
AO_HD inline Wrapped topology_wrap(double rho,double theta,double phi,int orientation,bool klein){
 const auto w=static_cast<long long>(::floor((rho+20)/20));rho-=20*w;
 if(w%2!=0){theta=klein?pi-theta:theta+pi;phi=-phi;orientation=-orientation;}
 return {rho,wrap(theta),wrap(phi),orientation,w};
}
AO_HD inline Vec3 ecef_from_geodetic(double lat,double lon,double height){
 constexpr double a=6378137.0,f=1.0/298.257223563,e2=f*(2-f);double s=::sin(lat),c=::cos(lat),N=a/::sqrt(1-e2*s*s);
 return {(N+height)*c*::cos(lon),(N+height)*c*::sin(lon),(N*(1-e2)+height)*s};
}
struct GeoConfig {
 Vec3 origin,east,north,up; double r0,core_radius,axis_angle,relation_margin;Cone cone;Vec3 sphere_l,sphere_r;double sphere_radius;
};
inline GeoConfig make_geo(double lat=52*pi/180,double lon=5*pi/180,double height=20){
 GeoConfig g{};g.origin=ecef_from_geodetic(lat,lon,height);g.east={-::sin(lon),::cos(lon),0};
 g.north={-::cos(lon)*::sin(lat),-::sin(lon)*::sin(lat),::cos(lat)};g.up={::cos(lon)*::cos(lat),::sin(lon)*::cos(lat),::sin(lat)};
 g.r0=10000;g.core_radius=.01;g.axis_angle=15*pi/180;g.relation_margin=.001;
 g.cone={{0,0,-100},{0,0,1},1000,pi/3};g.sphere_l={0,0,0};g.sphere_r={200,0,0};g.sphere_radius=500;return g;
}
AO_HD inline Vec3 enu(Vec3 x,const GeoConfig& g){Vec3 d=sub(x,g.origin);return {dot(d,g.east),dot(d,g.north),dot(d,g.up)};}
}
