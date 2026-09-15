#pragma once
#include "atomos/tomagi_vm.hpp"
#include <cuda_runtime.h>

// One canonical finite-word body, shared by launch-per-step and fused paths.
// The supplied state is the instruction input (including any prior injection).
// Refusal preserves it; receipt is freshly initialized for every logical epoch.
namespace atomos { namespace tomagi { namespace detail {
using U32=std::uint32_t;using U64=std::uint64_t;using I64=long long;
constexpr U32 HALT=1u,ZERO=2u,WRAP=4u,EMIT=8u,CONE=16u,SPHERE=32u,MISS=64u,PHI_WRAP=128u;
constexpr U32 RHO_N=1u<<20,THETA_N=1u<<18,TIME_N=1u<<14,PHI_N=1u<<12,REKEY=1u<<31;
__host__ __device__ inline int signed_word(U32 w){return w<=0x7fffffffu?static_cast<int>(w):-1-static_cast<int>(~w);}
__device__ inline U32 mix(U32 x){x^=x>>16;x*=0x7feb352du;x^=x>>15;x*=0x846ca68bu;return x^(x>>16);}
__device__ inline U32 rotate(U32 x,unsigned r){r&=31;return(x<<r)|(x>>((32-r)&31));}
__device__ inline U32 wrap(I64 x){return static_cast<U32>(static_cast<unsigned long long>(x));}
// Exact signed division by 2^shift, truncated toward zero; shift is 0..30.
// Unsigned magnitude/sign restoration also preserves the INT_MIN bit pattern.
__device__ inline U32 trunc_shift_word(U32 raw,unsigned shift){
    const bool negative=(raw&0x80000000u)!=0;
    const U32 magnitude=negative?0u-raw:raw;
    const U32 quotient=magnitude>>shift;
    return negative?0u-quotient:quotient;
}
__device__ inline I64 floor_div(I64 x,U32 n){I64 q=x/I64(n);return x%I64(n)<0?q-1:q;}
__device__ inline int norm(I64 x,U32 n){I64 r=x%I64(n);return static_cast<int>(r<0?r+n:r);}
__device__ inline I64 magnitude(int x){return x<0?-I64(x):I64(x);}
__device__ inline int delta(int x,int center,U32 n){int d=norm(I64(x)-center,n);return d>=int(n/2)?d-int(n):d;}
__device__ inline void normalize(State64& s){s.words[1]&=THETA_N-1;s.words[2]&=TIME_N-1;s.words[3]&=PHI_N-1;s.words[8]&=1;s.words[10]&=1;}
__device__ inline void key(const State64& s,U32& hi,U32& lo){
    U32 r=s.words[0]&(RHO_N-1),t=s.words[1]&(THETA_N-1),x=s.words[2]&(TIME_N-1),p=s.words[3]&(PHI_N-1);
    hi=(r<<12)|(t>>6);lo=((t&63)<<26)|(x<<12)|p;
}
template<bool Tex>__device__ inline uint4 cell_texel(DeviceView v,U32 cell,unsigned texel){
    ProgramBank b=v.banks[cell>>v.bank_shift];U32 local=cell&v.bank_mask;
    if constexpr(Tex)return tex1Dfetch<uint4>(static_cast<cudaTextureObject_t>(b.texture),int(local*3+texel));
    else return reinterpret_cast<const uint4*>(b.cells)[local*3+texel];
}
template<bool Tex>__device__ inline Cell48 get_cell(DeviceView v,U32 index){
    Cell48 c;
    for(unsigned k=0;k<3;++k){uint4 x=cell_texel<Tex>(v,index,k);c.words[k*4]=x.x;c.words[k*4+1]=x.y;c.words[k*4+2]=x.z;c.words[k*4+3]=x.w;}
    return c;
}
__device__ inline int compare(U32 ah,U32 al,U32 bh,U32 bl){return ah<bh?-1:ah>bh?1:al<bl?-1:al>bl?1:0;}
template<bool Tex>__device__ inline bool find_key(DeviceView v,U32 hi,U32 lo,U32& found){
    U32 left=0,right=v.cell_count;
    while(left<right){U32 mid=left+(right-left)/2;uint4 h=cell_texel<Tex>(v,mid,0);
        if(compare(h.x,h.y,hi,lo)<0)left=mid+1;else right=mid;}
    if(left<v.cell_count){uint4 h=cell_texel<Tex>(v,left,0);if(compare(h.x,h.y,hi,lo)==0){found=left;return true;}}
    return false;
}
template<bool Tex>__device__ inline void transition(DeviceView v,State64& state,U32& fault,Receipt& receipt){
    State64 s=state;receipt=Receipt{};receipt.epoch=v.epoch;receipt.cell_before=s.words[11];receipt.branch_after=s.words[10];
    if(fault){receipt.error=fault;return;}
    if(s.words[15]&HALT){return;}
    U32 ci=s.words[11],error=0;
    if(ci>=v.cell_count){error=U32(Error::BadCell);receipt.error=error;fault=error;return;}
    Cell48 c=get_cell<Tex>(v,ci);U32 op=c.words[2],flags=c.words[3],hi,lo;key(s,hi,lo);
    receipt.opcode=op;receipt.flags=flags;receipt.payload=c.words[10];
    int a0=signed_word(c.words[4]),a1=signed_word(c.words[5]),a2=signed_word(c.words[6]),a3=signed_word(c.words[7]);
    switch(op){
    case 0:break;
    case 1:s.words[flags&15]=c.words[4];break;
    case 2:{U32 h=mix(v.seed^hi^rotate(lo,13)^s.words[2]^c.words[11]);U32 bit=__popc(h)&1u;
        s.words[10]=bit;U32 d=bit?c.words[4]:0u-c.words[4];s.words[flags&15]+=d;break;}
    case 3:for(unsigned k=0;k<4;++k){s.words[4+k]+=c.words[4+k];s.words[k]+=s.words[4+k];}break;
    case 4:{I64 raw=I64(signed_word(s.words[3]))+a0,w=floor_div(raw,PHI_N);s.words[3]=U32(raw-w*PHI_N);
        if((U32(w)&1u)&&(flags&(1u<<4)))s.words[8]^=1;
        if(w)s.words[15]|=PHI_WRAP;else s.words[15]&=~PHI_WRAP;
        s.words[10]=(flags&(1u<<5))?(s.words[3]>>11)&1u:U32(w)&1u;break;}
    case 5:{I64 raw=I64(signed_word(s.words[2]))+a0,w=floor_div(raw,TIME_N);s.words[2]=U32(raw-w*TIME_N);s.words[10]=U32(w)&1u;
        if(w)s.words[12]=mix(s.words[12]^U32(w)^c.words[11]);break;}
    case 6:s.words[14]=0;s.words[15]|=ZERO;s.words[10]=1;break;
    case 7:{int rho=int(s.words[0]&(RHO_N-1)),theta=int(s.words[1]&(THETA_N-1));
        I64 r0=I64(a0)-rho,r1=I64(rho)-a1,radial=r0>r1?r0:r1;
        I64 angular=magnitude(delta(theta,norm(a2,THETA_N),THETA_N))-magnitude(a3);
        s.words[14]=wrap(radial>angular?radial:angular);bool inside=signed_word(s.words[14])<=0;s.words[10]=inside;
        if(inside)s.words[15]|=CONE;else s.words[15]&=~CONE;break;}
    case 8:{int rho=int(s.words[0]&(RHO_N-1)),phi=int(s.words[3]&(PHI_N-1));I64 radial=I64(rho)-a0;
        if(radial<0)radial=-radial;radial-=magnitude(a1);
        if(a3>=0){I64 angular=magnitude(delta(phi,norm(a2,PHI_N),PHI_N))-magnitude(a3);if(angular>radial)radial=angular;}
        s.words[14]=wrap(radial);bool inside=signed_word(s.words[14])<=0;s.words[10]=inside;
        if(inside)s.words[15]|=SPHERE;else s.words[15]&=~SPHERE;break;}
    case 9:{I64 rho=signed_word(s.words[0]),w=floor_div(rho,RHO_N);s.words[0]=U32(rho-w*RHO_N);U32 odd=U32(w)&1u;
        if(odd){I64 theta=signed_word(s.words[1]);s.words[1]=U32(norm((flags&1)?theta+THETA_N/2:I64(THETA_N/2)-theta,THETA_N));
            s.words[3]=U32(norm(-I64(signed_word(s.words[3])),PHI_N));s.words[8]^=1;if(flags&2)s.words[9]^=1;s.words[15]|=WRAP;
        }else s.words[15]&=~WRAP;s.words[10]=odd;normalize(s);break;}
    case 10:if(a0<0||a0>=64)error=U32(Error::BadRadix);else s.words[10]=a0<32?(lo>>unsigned(a0))&1u:(hi>>unsigned(a0-32))&1u;break;
    case 11:if(s.words[10]&1u){for(unsigned k=0;k<4;++k)s.words[k]+=c.words[4+k];if(flags&1)s.words[8]^=1;if(flags&2)s.words[9]^=1;normalize(s);}break;
    case 12:{int sh=a1<0?0:a1>30?30:a1;I64 chirality=(s.words[8]&1u)?-1:1,turn=(s.words[10]&1u)?1:-1;
        s.words[3]=U32(norm(I64(signed_word(s.words[3]))+chirality*turn*I64(a0),PHI_N));
        for(unsigned k=4;k<8;++k)s.words[k]=trunc_shift_word(s.words[k],unsigned(sh));break;}
    case 13:s.words[13]=c.words[10];break;
    case 14:s.words[13]=c.words[10];s.words[15]|=EMIT;if(flags&1)s.words[15]|=HALT;break;
    case 15:s.words[15]|=HALT;break;
    default:error=U32(Error::BadOpcode);break;
    }
    if(error){receipt.error=error;fault=error;return;}
    normalize(s);s.words[12]=mix(s.words[12]^c.words[10]^c.words[11]^hi^rotate(lo,7)^s.words[10]^ci);
    if(!(s.words[15]&HALT)){
        U32 successor=(s.words[10]&1u)?c.words[9]:c.words[8];
        if(flags&REKEY){U32 nh,nl,found;key(s,nh,nl);if(find_key<Tex>(v,nh,nl,found)){s.words[15]&=~MISS;successor=found;}else s.words[15]|=MISS;}
        s.words[11]=successor;
    }
    state=s;receipt.executed=1;receipt.emitted=op==14;receipt.branch_after=s.words[10];
}
}}} // namespace atomos::tomagi::detail
