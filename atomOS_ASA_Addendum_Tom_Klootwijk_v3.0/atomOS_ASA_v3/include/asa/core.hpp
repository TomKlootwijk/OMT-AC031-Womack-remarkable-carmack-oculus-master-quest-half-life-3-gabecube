#pragma once
// ASA v3.0. Concept attribution: Tom Klootwijk. Numerical image operators only.
#include <cstdint>
#include <cmath>
#if defined(__CUDACC__)
#define ASA_HD __host__ __device__
#else
#define ASA_HD
#endif
namespace asa {
using u32=std::uint32_t;
using u64=std::uint64_t;
constexpr double pi=3.1415926535897932384626433832795;
constexpr double tau=2*pi;
constexpr u32 invalid_index=0xffffffffu;
enum class Layout : u32 { Linear=0, Morton8=1 };
struct Warp { float radial, angular; };
struct Sample { double rho, phi; };
struct Config {
    u32 rho_bins=256,phi_bins=512,warp_bins=512;
    Layout layout=Layout::Morton8;
    double rho_min=0.,rho_max=4.;
    double pupil_min=.20,pupil_max=3.80;
    double axis=0.,hinge=.035,alpha=1.20;
    double radial_warp=.08,angular_warp=.12;
};
// Each output is an image-sample result, not an actuator or external-system command.
struct Result {
    float left,right,mean,reserved;
    u32 flags,left_cell,right_cell,pad;
};
static_assert(sizeof(Warp)==8 && sizeof(Sample)==16 && sizeof(Result)==32,"ABI size");
enum Flags : u32 { LeftValid=1, RightValid=2, PairValid=4, InputInvalid=8 };
ASA_HD inline bool finite(double x) { return x==x && x<=1.7976931348623157e308 && x>=-1.7976931348623157e308; }
ASA_HD inline double wrap(double x) {
    double v=::fmod(x,tau);
    if(v<0)v+=tau;
    return v>=tau?0.:v;
}
ASA_HD inline double signed_angle(double x) {
    const double v=wrap(x);
    return v>=pi?v-tau:v;
}
// Source bit order: radial bits in even places, phi bits in odd places.
ASA_HD inline u32 spread3(u32 x) { return (x&1u)|((x&2u)<<1)|((x&4u)<<2); }
ASA_HD inline u32 compact3(u32 x) { return (x&1u)|((x>>1)&2u)|((x>>2)&4u); }
ASA_HD inline u32 morton6(u32 r,u32 p) { return spread3(r)|(spread3(p)<<1); }
ASA_HD inline u32 storage_index(u32 r,u32 p,const Config& c) {
    if(c.layout==Layout::Linear)return r*c.phi_bins+p;
    const u32 tile=(r>>3)*(c.phi_bins>>3)+(p>>3);
    return tile*64u+morton6(r&7u,p&7u);
}
ASA_HD inline void decode_storage(u32 k,const Config& c,u32 &r,u32 &p) {
    if(c.layout==Layout::Linear){r=k/c.phi_bins;p=k%c.phi_bins;return;}
    const u32 tile=k>>6,local=k&63u;
    r=(tile/(c.phi_bins>>3))*8+compact3(local);
    p=(tile%(c.phi_bins>>3))*8+compact3(local>>1);
}
ASA_HD inline u32 popcount(u32 x) {
#ifdef __CUDA_ARCH__
    return __popc(x);
#else
    x-=(x>>1)&0x55555555u;
    x=(x&0x33333333u)+((x>>2)&0x33333333u);
    return (((x+(x>>4))&0x0f0f0f0fu)*0x01010101u)>>24;
#endif
}
ASA_HD inline bool clamp_clear(u32 word,u32 mask) { return (word&mask)==0; }
ASA_HD inline u32 nullifier(u32 word,u32 mask) { return clamp_clear(word,mask)?word:0u; }
// Equal-size, disjoint block exchange; caller validates range/disjointness.
ASA_HD inline u32 portal_swap(u32 k,u32 a,u32 b,u32 length) {
    if(k>=a && k-a<length)return b+(k-a);
    if(k>=b && k-b<length)return a+(k-b);
    return k;
}
struct HostData {
    const float* image;
    const u32* mask;
    const Warp* warp;
    ASA_HD float value(u32 k)const{return image[k];}
    ASA_HD u32 maskword(u32 k)const{return mask[k];}
    ASA_HD Warp lens(u32 k)const{return warp[k];}
};
struct Offset { double radial,angular; };
template<class Access>
ASA_HD Offset warp_lookup(double delta,const Config& c,const Access& data) {
    const double position=wrap(delta)/tau*double(c.warp_bins);
    u32 i=u32(position);
    if(i>=c.warp_bins)i=c.warp_bins-1;
    const double f=position-double(i);
    const Warp a=data.lens(i),b=data.lens((i+1)%c.warp_bins);
    return {double(a.radial)+f*(double(b.radial)-a.radial),
            double(a.angular)+f*(double(b.angular)-a.angular)};
}
struct Side {float value;u32 valid,cell;};
template<class Access>
ASA_HD Side sample_side(double rho,double delta,const Config& c,const Access& data) {
    // NA is applied AFTER the ASA branch coordinates have been constructed.
    if(rho<c.pupil_min || rho>=c.pupil_max || ::fabs(delta)>c.alpha)
        return {0.f,0,invalid_index};
    const Offset w=warp_lookup(delta,c,data);
    const double r=rho+w.radial,phi=wrap(c.axis+delta+w.angular);
    if(!finite(r)||!finite(phi)||r<c.rho_min||r>=c.rho_max)
        return {0.f,0,invalid_index};
    u32 ir=u32((r-c.rho_min)/(c.rho_max-c.rho_min)*double(c.rho_bins));
    u32 ip=u32(phi/tau*double(c.phi_bins));
    if(ir>=c.rho_bins)ir=c.rho_bins-1;
    if(ip>=c.phi_bins)ip=c.phi_bins-1;
    const u32 address=storage_index(ir,ip,c),cell=ir*c.phi_bins+ip;
    if((data.maskword(address>>5)>>(address&31u))&1u)
        return {0.f,0,cell};
    return {data.value(address),1,cell};
}
template<class Access>
ASA_HD Result evaluate(Sample z,const Config& c,const Access& data) {
    if(!finite(z.rho)||!finite(z.phi))return {0,0,0,0,InputInvalid,invalid_index,invalid_index,0};
    // Reduce before subtraction: finite external phase cannot overflow the sum.
    const double delta=signed_angle(wrap(z.phi)-c.axis+c.hinge);
    const Side left=sample_side(z.rho,delta,c,data),right=sample_side(z.rho,-delta,c,data);
    const bool pair=left.valid&&right.valid;
    return {left.value,right.value,pair?float((double(left.value)+right.value)*.5):0.f,0.f,
            (left.valid?LeftValid:0u)|(right.valid?RightValid:0u)|(pair?PairValid:0u),
            left.cell,right.cell,0};
}
} // namespace asa
