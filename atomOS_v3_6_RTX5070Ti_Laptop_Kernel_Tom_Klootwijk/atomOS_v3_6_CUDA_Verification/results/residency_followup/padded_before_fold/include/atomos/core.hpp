#pragma once
// atomOS v3.6 K1: the mathematical word-epoch core, shared by CPU and CUDA.
#include <cmath>
#include <cstdint>
#include <cfloat>
#if defined(__CUDACC__)
#define AO_HD __host__ __device__
#else
#define AO_HD
#endif
namespace atomos {
using u32=std::uint32_t;using u64=std::uint64_t;
constexpr double PI=3.1415926535897932384626433832795,TAU=2*PI,INVARIANT_TOL=1e-10;
enum class Layout:u32 {linear=0,morton8=1};
enum class Producer:u32 {provided=0,recurrent=1,shift_xor=2,shift_or=3};
enum class Profile:u32 {source_ratio=0,directed_completion_1=1};
enum class Status:u32 {defined=0,zero_increment=1,ratio_undefined=2,nonfinite_input=3,numerical_range=4,axis_unspecified=5,frame_unspecified=6,increment_policy_unspecified=7};
enum class CheckState:u32 {pass=0,fail=1,undefined=2};
struct Shape {u32 rows,angles,words,padded_rows,padded_words;};
struct State {u32 word,q;};
struct AngleInput {double dr,dp,alpha,interval;u32 profile,axis_known,frame_known,increment_known;};
struct Lane {u32 initial_word,jitter,j,k,north,axis,kinematic,blend_known;AngleInput angle;};
struct WordResult {u32 asa,na,hits,output,q_after,blend,blend_known,produced;};
struct AngleResult {double beta,raw,principal,line;u32 status,beta_status;};
struct Check {double error;u32 state,reason;};
struct Result {WordResult word;AngleResult angle;Check checks[6];};
struct Config {Shape shape;Layout layout;Producer producer;u32 fringe;};
static_assert(sizeof(State)==8&&sizeof(AngleInput)==48&&sizeof(Lane)==80,"input ABI");
static_assert(sizeof(WordResult)==32&&sizeof(AngleResult)==40&&sizeof(Check)==16&&sizeof(Result)==168,"result ABI");
AO_HD inline bool finite(double x){
#ifdef __CUDA_ARCH__
 return ::isfinite(x);
#else
 return std::isfinite(x);
#endif
}
AO_HD inline double absd(double x){return x<0?-x:x;}
AO_HD inline double wrap(double x,double period=TAU){
 double v=::fmod(x,period);if(v>=period/2)v-=period;if(v< -period/2)v+=period;return v==0?0.0:v;
}
AO_HD inline u32 spread3(u32 x){return (x&1u)|((x&2u)<<1u)|((x&4u)<<2u);}
AO_HD inline u32 compact3(u32 x){return (x&1u)|((x>>1u)&2u)|((x>>2u)&4u);}
AO_HD inline u32 address(const Shape&s,u32 r,u32 w,Layout layout){
 if(layout==Layout::linear)return r*s.padded_words+w;
 return 64u*((r>>3u)*(s.padded_words>>3u)+(w>>3u))+spread3(r&7u)+(spread3(w&7u)<<1u);
}
AO_HD inline u32 valid_mask(const Shape&s,u32 w){const u32 t=s.angles&31u;return w+1u==s.words&&t?((u32(1)<<t)-1u):0xffffffffu;}
AO_HD inline u32 popcount(u32 x){
#ifdef __CUDA_ARCH__
 return __popc(x);
#else
 x-=((x>>1u)&0x55555555u);x=(x&0x33333333u)+((x>>2u)&0x33333333u);x=(x+(x>>4u))&0x0f0f0f0fu;return (x*0x01010101u)>>24u;
#endif
}
AO_HD inline u32 mix32(u32 x){x^=x>>16u;x*=0x7feb352du;x^=x>>15u;x*=0x846ca68bu;return x^(x>>16u);}
AO_HD inline u32 jk(u32 q,u32 j,u32 k){return (j&(q^1u))|((k^1u)&q);}
AO_HD inline u32 produce(const State&s,const Lane&lane,Producer p){
 if(p==Producer::provided)return lane.initial_word;
 if(p==Producer::recurrent)return s.word;
 if(s.word==0)return 0; // source's 0->0 guard, before word jitter
 const u32 left=s.word<<1u,right=s.word>>1u;
 return ((p==Producer::shift_or)?(left|right):(left^right))^lane.jitter;
}
AO_HD inline WordResult word_step(u32 x,u32 am,u32 nm,u32 bm,u32 vm,u32 fm,const State&s,const Lane&lane){
 WordResult o{};o.produced=x;o.asa=x&am&vm&fm;o.na=o.asa&nm;o.hits=popcount(o.na&bm);o.output=o.hits?0:o.na;
 o.q_after=jk(s.q,lane.j,lane.k);o.blend_known=lane.blend_known;o.blend=lane.blend_known?(lane.north^lane.axis^lane.kinematic):0;return o;
}
AO_HD inline AngleResult angle_unavailable(Status status){AngleResult o{};o.status=o.beta_status=u32(status);return o;}
AO_HD inline AngleResult observe(const AngleInput&a){
 AngleResult o{};
 if(!finite(a.dr)||!finite(a.dp))return angle_unavailable(Status::nonfinite_input);
 if(a.dr==0&&a.dp==0)return angle_unavailable(Status::zero_increment);
 double beta=0;
 if(a.profile==u32(Profile::source_ratio)){
  if(a.dr==0)return angle_unavailable(Status::ratio_undefined);
  const double ratio=a.dp/a.dr;
  if(!finite(ratio)||(a.dp!=0&&ratio==0))return angle_unavailable(Status::numerical_range);
  beta=::atan(ratio);
 }else beta=wrap(::atan2(a.dp,a.dr));
 o.beta=beta==0?0:beta;o.beta_status=u32(Status::defined);
 if(!a.increment_known){o.status=u32(Status::increment_policy_unspecified);return o;}
 if(!a.frame_known){o.status=u32(Status::frame_unspecified);return o;}
 if(!a.axis_known){o.status=u32(Status::axis_unspecified);return o;}
 if(!finite(a.alpha)){o.status=u32(Status::nonfinite_input);return o;}
 const double raw=o.beta-a.alpha;if(!finite(raw)){o.status=u32(Status::numerical_range);return o;}
 o.raw=raw;o.principal=wrap(raw);o.line=wrap(raw,PI);o.status=u32(Status::defined);return o;
}
AO_HD inline Check unavailable(u32 reason){return {0,u32(CheckState::undefined),reason};}
AO_HD inline Check compare_angle(double actual,double expected,u32 space){
 const double d=actual-expected;if(!finite(actual)||!finite(expected)||!finite(d))return unavailable(u32(Status::numerical_range));
 const double e=absd(space==0?d:wrap(d,space==1?PI:TAU));return {e,u32(e<=INVARIANT_TOL?CheckState::pass:CheckState::fail),0};
}
AO_HD inline Check probe(const AngleInput&t,const AngleResult&base,u32 space=0){
 const AngleResult x=observe(t);if(x.status!=u32(Status::defined))return unavailable(x.status);
 return compare_angle(space==0?x.raw:(space==1?x.line:x.principal),space==0?base.raw:(space==1?base.line:base.principal),space);
}
AO_HD inline void invariant_bank(const AngleInput&a,const AngleResult&base,Check*out){
 for(u32 i=0;i<6;++i)out[i]=unavailable(base.status);
 if(base.status!=u32(Status::defined))return;
 AngleInput t=a;
 // K1 fixed probe parameters: synthetic baselines .75/.25, offsets 1.25/.75,
 // positive scale 3, joint log-tangent frame rotation .4 radians.
 t.dr=((.75+a.dr)+1.25)-(.75+1.25);out[0]=probe(t,base);
 t=a;if(!finite(a.interval)||a.interval<=0)out[1]=unavailable(100);
 else {t.dr=a.dr/a.interval;t.dp=a.dp/a.interval;
  out[1]=((a.dr!=0&&t.dr==0)||(a.dp!=0&&t.dp==0))?unavailable(u32(Status::numerical_range)):probe(t,base);}
 t=a;t.dp=((.25+a.dp)+.75)-(.25+.75);out[2]=probe(t,base);
 t=a;t.dr=a.dr*3;t.dp=a.dp*3;out[3]=((a.dr!=0&&t.dr==0)||(a.dp!=0&&t.dp==0))?unavailable(u32(Status::numerical_range)):probe(t,base);
 t=a;const double c=::cos(.4),s=::sin(.4);t.dr=c*a.dr-s*a.dp;t.dp=s*a.dr+c*a.dp;t.alpha=a.alpha+.4;
 if(a.profile==u32(Profile::source_ratio)&&absd(t.dr)<=64*DBL_EPSILON*::hypot(a.dr,a.dp))out[4]=unavailable(101);
 else out[4]=probe(t,base,a.profile==u32(Profile::source_ratio)?1u:2u);
 t=a;t.dr=-a.dr;t.dp=-a.dp;const AngleResult rev=observe(t);
 if(rev.beta_status!=u32(Status::defined))out[5]=unavailable(rev.beta_status);
 else out[5]=a.profile==u32(Profile::source_ratio)?compare_angle(rev.beta,base.beta,0):compare_angle(wrap(rev.beta-base.beta),-PI,2);
}
AO_HD inline Result epoch_word(const State&s,const Lane&lane,u32 am,u32 nm,u32 bm,u32 fm,u32 valid,Producer producer,u32 fringe){
 Result out{};out.word=word_step(produce(s,lane,producer),am,nm,bm,valid,fringe?fm:valid,s,lane);
 out.angle=observe(lane.angle);invariant_bank(lane.angle,out.angle,out.checks);return out;
}
}
