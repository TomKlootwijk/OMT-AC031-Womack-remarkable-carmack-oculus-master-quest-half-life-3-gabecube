#pragma once
#include "core.hpp"
#include <vector>
#include <string>
#include <stdexcept>
#include <limits>
#include <algorithm>
#include <array>
namespace asa {
inline void validate(const Config& c) {
    if(!c.rho_bins||!c.phi_bins||c.rho_bins%8||c.phi_bins%8||c.rho_bins>8192||c.phi_bins>8192)
        throw std::invalid_argument("rho/phi bins must be multiples of 8 in 8..8192");
    if(c.warp_bins<8||c.warp_bins>65536||c.warp_bins%2)
        throw std::invalid_argument("warp bins must be even in 8..65536");
    if(c.layout!=Layout::Linear&&c.layout!=Layout::Morton8)throw std::invalid_argument("invalid layout");
    for(double x:{c.rho_min,c.rho_max,c.pupil_min,c.pupil_max,c.axis,c.hinge,c.alpha,c.radial_warp,c.angular_warp})
        if(!finite(x))throw std::invalid_argument("nonfinite configuration");
    if(c.rho_min>=c.rho_max||!finite(c.rho_max-c.rho_min)||
       c.pupil_min<c.rho_min||c.pupil_max>c.rho_max||c.pupil_min>=c.pupil_max||
       c.axis<0||c.axis>=tau||::fabs(c.hinge)>pi||c.alpha<0||c.alpha>pi/2||
       ::fabs(c.radial_warp)>1||::fabs(c.angular_warp)>.75)
        throw std::invalid_argument("invalid chart, aperture, or warp profile");
}
inline double alpha_from_na(double na,double refractive_index) {
    if(!finite(na)||!finite(refractive_index)||refractive_index<=0||na<0||na>refractive_index)
        throw std::invalid_argument("NA requires 0 <= NA <= refractive_index and refractive_index > 0");
    return std::asin(na/refractive_index);
}
inline u64 required_bytes(const Config& c,u64 samples) {
    validate(c);
    if(samples>4194304)throw std::invalid_argument("sample count exceeds 4194304");
    const u64 cells=u64(c.rho_bins)*c.phi_bins;
    return 4*cells+4*((cells+31)/32)+8*u64(c.warp_bins)+samples*(sizeof(Sample)+sizeof(Result));
}
inline bool gpu_payload_admitted(u64 bytes,u64 free_bytes) {
    constexpr u64 reserve=512ull*1048576;
    return free_bytes>reserve && bytes<=free_bytes-reserve && bytes<=free_bytes/2;
}
inline u32 mix(u32 x) { x^=x>>16;x*=0x7feb352du;x^=x>>15;x*=0x846ca68bu;return x^(x>>16); }
struct Fixture {
    std::vector<float> image;
    std::vector<u32> mask;
    std::vector<Warp> warp;
    Fixture(const Config& c,bool blank_mask=false) {
        validate(c);const u32 cells=c.rho_bins*c.phi_bins;
        image.resize(cells);mask.assign((cells+31u)/32u,0u);warp.resize(c.warp_bins);
        // D4 test image: independently identified facets, not external observations.
        for(u32 r=0;r<c.rho_bins;++r)for(u32 p=0;p<c.phi_bins;++p) {
            const u32 k=storage_index(r,p,c),facet=(p*12u)/c.phi_bins;
            const u32 value=(r*13u+p*7u+facet*211u)%4096u;
            image[k]=float(value)/4095.f;
            const bool blocked=!blank_mask&&(r>c.rho_bins/3&&r<c.rho_bins/2&&((p/16u)%5u==2u));
            if(blocked)mask[k>>5]|=1u<<(k&31u);
        }
        // Construct even radial and odd angular samples by exact reflection.
        for(u32 j=0;j<=c.warp_bins/2;++j) {
            const double d=tau*double(j)/c.warp_bins;
            Warp w{float(c.radial_warp*(1-std::cos(d))),
                   (j==0||j==c.warp_bins/2)?0.f:float(c.angular_warp*std::sin(d))};
            warp[j]=w;
            if(j && j<c.warp_bins/2)warp[c.warp_bins-j]={w.radial,-w.angular};
        }
    }
    HostData access()const{return {image.data(),mask.data(),warp.data()};}
};
inline std::vector<Sample> make_samples(u32 count,const Config& c,u32 seed=130) {
    std::vector<Sample> z(count);
    for(u32 i=0;i<count;++i) {
        const double a=(double(mix(i^seed))+.5)/4294967296.;
        const double b=(double(mix(i+0x9e3779b9u+seed))+.5)/4294967296.;
        z[i]={c.rho_min+(c.rho_max-c.rho_min)*a,tau*b};
    }
    return z;
}
// This is a scheduling hint only. evaluate() still computes every result from
// the original coordinates; no chart, lens or aperture semantics change.
inline u32 locality_key(Sample sample,const Config& c) {
    if(!finite(sample.rho)||!finite(sample.phi))return invalid_index;
    const double delta=::fabs(signed_angle(wrap(sample.phi)-c.axis+c.hinge));
    if(sample.rho<c.pupil_min||sample.rho>=c.pupil_max||delta>c.alpha)return invalid_index;
    u32 r=u32((sample.rho-c.rho_min)/(c.rho_max-c.rho_min)*double(c.rho_bins));
    u32 p=u32(delta/tau*double(c.phi_bins));
    if(r>=c.rho_bins)r=c.rho_bins-1;
    if(p>=c.phi_bins)p=c.phi_bins-1;
    return storage_index(r,p,c);
}
struct SampleSchedule {
    std::vector<Sample> ordered;
    std::vector<u32> original_indices;
};
inline SampleSchedule make_locality_schedule(const std::vector<Sample>& samples,const Config& c) {
    required_bytes(c,samples.size());
    struct Entry {u32 key,index;};
    std::vector<Entry> entries(samples.size()),scratch(samples.size());
    for(std::size_t i=0;i<samples.size();++i)entries[i]={locality_key(samples[i],c),u32(i)};
    // Four stable byte-radix passes avoid expensive coordinate calculations
    // inside a comparison sort and leave equal keys in original order.
    for(u32 shift=0;shift<32;shift+=8) {
        std::array<std::size_t,256> offsets{};
        for(const Entry& entry:entries)++offsets[(entry.key>>shift)&255u];
        std::size_t next=0;
        for(auto& count:offsets){const std::size_t size=count;count=next;next+=size;}
        for(const Entry& entry:entries)scratch[offsets[(entry.key>>shift)&255u]++]=entry;
        entries.swap(scratch);
    }
    SampleSchedule schedule;schedule.ordered.resize(samples.size());schedule.original_indices.resize(samples.size());
    for(std::size_t i=0;i<entries.size();++i){schedule.original_indices[i]=entries[i].index;schedule.ordered[i]=samples[entries[i].index];}
    return schedule;
}
inline void restore_sample_order(std::vector<Result>& results,const SampleSchedule& schedule) {
    if(results.size()!=schedule.original_indices.size())throw std::invalid_argument("schedule length mismatch");
    std::vector<Result> restored(results.size());std::vector<bool> seen(results.size(),false);
    for(std::size_t i=0;i<results.size();++i) {
        const u32 original=schedule.original_indices[i];
        if(original>=results.size()||seen[original])throw std::invalid_argument("schedule is not a permutation");
        seen[original]=true;restored[original]=results[i];
    }
    results.swap(restored);
}
inline std::vector<Result> cpu_run(const Config& c,const Fixture& f,const std::vector<Sample>& samples) {
    std::vector<Result> out(samples.size());
    for(std::size_t i=0;i<samples.size();++i)out[i]=evaluate(samples[i],c,f.access());
    return out;
}
inline void compare(const std::vector<Result>& a,const std::vector<Result>& b,double tolerance=2e-6) {
    if(a.size()!=b.size())throw std::runtime_error("output length mismatch");
    for(std::size_t i=0;i<a.size();++i) {
        if(a[i].flags!=b[i].flags||a[i].left_cell!=b[i].left_cell||a[i].right_cell!=b[i].right_cell||
           !finite(a[i].left)||!finite(a[i].right)||!finite(a[i].mean)||
           !finite(b[i].left)||!finite(b[i].right)||!finite(b[i].mean)||
           ::fabs(a[i].left-b[i].left)>tolerance||::fabs(a[i].right-b[i].right)>tolerance||::fabs(a[i].mean-b[i].mean)>tolerance)
            throw std::runtime_error("differential mismatch at sample "+std::to_string(i));
    }
}
}
