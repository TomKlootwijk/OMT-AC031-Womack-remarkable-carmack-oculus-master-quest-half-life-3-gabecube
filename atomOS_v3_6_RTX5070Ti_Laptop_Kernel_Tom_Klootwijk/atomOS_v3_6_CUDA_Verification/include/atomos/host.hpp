#pragma once
#include "atomos/core.hpp"
#include <algorithm>
#include <array>
#include <chrono>
#include <iomanip>
#include <limits>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
namespace atomos {
inline u64 stored(const Shape&s){return u64(s.padded_rows)*s.padded_words;}
inline u64 logical(const Shape&s){return u64(s.rows)*s.words;}
inline Shape shape(u32 rows,u32 angles,u64 atlas_limit=(u64(1)<<18)){
 if(!rows||!angles||rows>65536||angles>65536)throw std::invalid_argument("dimensions must be 1..65536");
 if(atlas_limit<(u64(1)<<18)||atlas_limit>(u64(1)<<20))throw std::invalid_argument("atlas limit must be 2^18..2^20 stored words per plane");
 const u32 w=(angles+31)/32;Shape s{rows,angles,w,(rows+7)/8*8,(w+7)/8*8};
 if(stored(s)>atlas_limit)throw std::invalid_argument("selected atlas cap exceeded");
 return s;
}
inline std::array<u32,2> inverse(const Shape&s,u32 k,Layout l){
 if(k>=stored(s))throw std::out_of_range("atlas address");
 if(l==Layout::linear)return {k/s.padded_words,k%s.padded_words};
 const u32 tile=k/64,t=k%64;return {(tile/(s.padded_words/8))*8+compact3(t),(tile%(s.padded_words/8))*8+compact3(t>>1)};
}
inline u64 payload(const Shape&s){return 16*stored(s)+(sizeof(Lane)+sizeof(State)+sizeof(Result))*logical(s);}
inline u64 plan(const Shape&s){return payload(s)+(u64(64)<<20);}
inline bool allowed(u64 required,u64 free,u64 total,u64 budget,u64 reserve){
 // Existing allocations count against the reserve: leave it in currently free VRAM.
 return total>reserve&&free>=reserve&&required<=std::min({budget,(free/10)*7,total-reserve,free-reserve});
}
inline std::string json_string(const std::string&s){std::ostringstream o;o<<'"';for(unsigned char c:s){if(c=='"'||c=='\\')o<<'\\'<<char(c);else if(c<32)o<<"\\u00"<<std::hex<<std::setw(2)<<std::setfill('0')<<unsigned(c);else o<<char(c);}o<<'"';return o.str();}
inline void validate_lane(const Lane&l,const State&s){
 for(u32 b:{s.q,l.j,l.k,l.north,l.axis,l.kinematic,l.blend_known,l.angle.axis_known,l.angle.frame_known,l.angle.increment_known})if(b>1)throw std::invalid_argument("state/encoder flags must be bits");
 if(l.angle.profile>1)throw std::invalid_argument("unknown OTAN2 profile");
}
struct Fixture {
 Config config;u32 seed;std::string angle_profile;std::array<std::vector<u32>,4> masks;std::vector<Lane> lanes;std::vector<State> initial;
 Fixture(Config c,u32 root=130,const std::string&p="mixed",u64 atlas_limit=(u64(1)<<18)):config(c),seed(root),angle_profile(p){
  const Shape verified=shape(c.shape.rows,c.shape.angles,atlas_limit);
  if(c.shape.words!=verified.words||c.shape.padded_rows!=verified.padded_rows||c.shape.padded_words!=verified.padded_words||u32(c.layout)>1||u32(c.producer)>3||c.fringe>1)
   throw std::invalid_argument("invalid configuration or padded dimensions");
  if(p!="source"&&p!="directed"&&p!="mixed")throw std::invalid_argument("profile must be source, directed or mixed");
  for(auto&m:masks)m.assign(std::size_t(stored(c.shape)),0);
  lanes.resize(std::size_t(logical(c.shape)));initial.resize(lanes.size());
  for(u32 r=0;r<c.shape.rows;r++)for(u32 w=0;w<c.shape.words;w++){
   const u32 i=r*c.shape.words+w,k=address(c.shape,r,w,c.layout),v=valid_mask(c.shape,w),z=mix32(root^i*0x9e3779b9u);
   masks[0][k]=(mix32(z+1)|mix32(z+7))&v;masks[1][k]=(mix32(z+11)|mix32(z+19))&v;
   masks[2][k]=(mix32(z+31)&mix32(z+37)&mix32(z+41)&mix32(z+43))&v;masks[3][k]=mix32(z+53)&v;
   Lane l{};l.initial_word=mix32(z+71)&v;l.jitter=mix32(z+73);l.j=i&1;l.k=(i>>1)&1;l.north=i&1;l.axis=(i>>1)&1;l.kinematic=(i>>2)&1;l.blend_known=i%31?1:0;
   l.angle={double(int(z%63)-31)/8,double(int((z>>8)%63)-31)/8,double(int((z>>16)%31)-15)/8,.125, p=="mixed"?(i&1):u32(p=="directed"),1,1,1};
   if(i%29==0){l.angle.dr=0;l.angle.dp=0;}else if(i%29==1){l.angle.dr=0;l.angle.dp=1;}else if(i%29==2){l.angle.dr=-1;l.angle.dp=0;}
   if(i%97==4)l.angle.axis_known=0;
   if(i%97==5)l.angle.frame_known=0;
   if(i%97==6)l.angle.increment_known=0;
   if(i%97==7)l.angle.interval=0;
   lanes[i]=l;initial[i]={l.initial_word,(i>>2)&1u};validate_lane(l,initial[i]);
  }
 }
};
inline std::vector<Result> cpu_propose(const Fixture&f,const std::vector<State>&state){
 if(state.size()!=f.lanes.size())throw std::invalid_argument("state length mismatch");
 std::vector<Result> out(state.size());const auto&s=f.config.shape;
 for(u32 r=0;r<s.rows;r++)for(u32 w=0;w<s.words;w++){const u32 i=r*s.words+w,k=address(s,r,w,f.config.layout);validate_lane(f.lanes[i],state[i]);out[i]=epoch_word(state[i],f.lanes[i],f.masks[0][k],f.masks[1][k],f.masks[2][k],f.masks[3][k],valid_mask(s,w),f.config.producer,f.config.fringe);}
 return out;
}
inline WordResult bit_oracle(u32 x,u32 a,u32 n,u32 b,u32 v,u32 f,const Lane&l,const State&s){
 WordResult out{};out.produced=x;
 for(u32 bit=0;bit<32;bit++){const u32 mask=u32(1)<<bit;
  if((x&mask)&&(a&mask)&&(v&mask)&&(f&mask)){out.asa|=mask;if(n&mask){out.na|=mask;if(b&mask)out.hits++;}}}
 out.output=out.hits?0:out.na;
 out.q_after= l.j?(l.k?1-s.q:1):(l.k?0:s.q);out.blend_known=l.blend_known;out.blend=l.blend_known?((l.north+l.axis+l.kinematic)%2):0;return out;
}
inline bool exact_word(const WordResult&a,const WordResult&b){return a.asa==b.asa&&a.na==b.na&&a.hits==b.hits&&a.output==b.output&&a.q_after==b.q_after&&a.blend==b.blend&&a.blend_known==b.blend_known&&a.produced==b.produced;}
inline bool near(double a,double b,double tol=2e-11){return finite(a)&&finite(b)&&absd(a-b)<=tol;}
inline void verify_results(const Fixture&f,const std::vector<State>&state,const std::vector<Result>&actual){
 const auto expected=cpu_propose(f,state);if(actual.size()!=expected.size())throw std::runtime_error("result length mismatch");const auto&s=f.config.shape;
 for(std::size_t i=0;i<actual.size();i++){
  const u32 r=u32(i)/s.words,w=u32(i)%s.words,k=address(s,r,w,f.config.layout);const auto&a=actual[i];const auto&e=expected[i];
  const auto oracle=bit_oracle(e.word.produced,f.masks[0][k],f.masks[1][k],f.masks[2][k],valid_mask(s,w),f.config.fringe?f.masks[3][k]:valid_mask(s,w),f.lanes[i],state[i]);
  if(!exact_word(a.word,oracle))throw std::runtime_error("integer result mismatch at lane "+std::to_string(i));
  if(a.angle.status!=e.angle.status||a.angle.beta_status!=e.angle.beta_status)throw std::runtime_error("OTAN2 status mismatch at lane "+std::to_string(i));
  if(e.angle.beta_status==0&&!near(a.angle.beta,e.angle.beta))throw std::runtime_error("OTAN2 beta mismatch");
  if(e.angle.status==0&&(!near(a.angle.raw,e.angle.raw)||!near(a.angle.principal,e.angle.principal)||!near(a.angle.line,e.angle.line)))throw std::runtime_error("OTAN2 residual mismatch");
  for(u32 j=0;j<6;j++)if(a.checks[j].state!=e.checks[j].state||a.checks[j].reason!=e.checks[j].reason||(e.checks[j].state!=2&&!near(a.checks[j].error,e.checks[j].error)))throw std::runtime_error("invariant mismatch at lane "+std::to_string(i));
 }
}
inline void commit_verified(const Fixture&f,std::vector<State>&state,const std::vector<Result>&candidate){
 verify_results(f,state,candidate);std::vector<State> next;next.reserve(state.size());for(const auto&r:candidate)next.push_back({r.word.output,r.word.q_after});state.swap(next);
}
class Backend {public:virtual ~Backend()=default;virtual std::vector<Result> propose(const std::vector<State>&)=0;virtual double last_ms()const=0;virtual std::string device_json()const=0;};
class CpuBackend final:public Backend {const Fixture&f;double ms=0;public:explicit CpuBackend(const Fixture&x):f(x){}std::vector<Result> propose(const std::vector<State>&s)override{const auto t=std::chrono::steady_clock::now();auto out=cpu_propose(f,s);ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-t).count();return out;}double last_ms()const override{return ms;}std::string device_json()const override{return "null";}};
std::unique_ptr<Backend> make_cuda_backend(const Fixture&,int device,bool texture,u64 budget,u64 reserve,bool packed=false,bool max_l1=false,u32 block_size=256);
std::string probe_cuda(int device);
}
