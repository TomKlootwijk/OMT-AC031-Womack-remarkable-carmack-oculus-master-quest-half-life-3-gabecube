#include "atomos/host.hpp"
#include "atomos/log_polar.hpp"
#include <bitset>
#include <cstring>
#include <functional>
#include <iostream>
#include <limits>
#include <set>
using namespace atomos;
static u64 assertions=0;static u32 groups=0;
void require(bool x,const char*msg){assertions++;if(!x)throw std::runtime_error(msg);}
void group(const char*name,const std::function<void()>&f){f();groups++;std::cout<<"PASS "<<name<<'\n';}
template<class F>void must_throw(F f){bool thrown=false;try{f();}catch(const std::exception&){thrown=true;}require(thrown,"expected exception");}
static u64 double_bits(double x){u64 bits;std::memcpy(&bits,&x,sizeof bits);return bits;}
static double from_double_bits(u64 bits){double x;std::memcpy(&x,&bits,sizeof x);return x;}
static double legacy_wrap(double x,double period){
 double v=::fmod(x,period);if(v>=period/2)v-=period;if(v< -period/2)v+=period;return v==0?0.0:v;
}
static void require_legacy_wrap(double x,double period){
 require(double_bits(wrap(x,period))==double_bits(legacy_wrap(x,period)),"wrap differs from legacy binary64 result");
}
int main(){try{
 group("fixed data ABI",[]{require(sizeof(Result)==168,"output size");require(sizeof(Lane)==80,"lane size");require(sizeof(State)==8,"state size");});
 group("all JK triples",[]{for(u32 q=0;q<2;q++){require(jk(q,0,0)==q,"hold");require(jk(q,1,0)==1,"set");require(jk(q,0,1)==0,"reset");require(jk(q,1,1)==1-q,"toggle");}});
 group("all blend triples",[]{Lane l{};l.blend_known=1;for(u32 n=0;n<2;n++)for(u32 a=0;a<2;a++)for(u32 b=0;b<2;b++){l.north=n;l.axis=a;l.kinematic=b;require(word_step(0,0,0,0,0,0,{0,0},l).blend==(n+a+b)%2,"blend parity");}});
 group("population count exhaustive 16 bit",[]{for(u32 i=0;i<65536;i++)require(popcount(i)==std::bitset<32>(i).count(),"popcount");});
 group("high-bit population count",[]{require(popcount(0x80000000)==1,"top bit");require(popcount(0xffffffff)==32,"all bits");});
 group("whole-word absorption is not bit clearing",[]{Lane l{};auto r=word_step(255,255,255,128,255,255,{255,0},l);require(r.hits==1&&r.output==0,"group disposition");});
 group("independent 32-bit oracle",[]{Lane l{};u32 z=91;for(u32 i=0;i<20000;i++){z=mix32(z+i);l.j=i&1;l.k=(i>>1)&1;State s{z,(i>>2)&1};u32 a=mix32(z+1),n=mix32(z+2),b=mix32(z+3),v=mix32(z+4),f=mix32(z+5);require(exact_word(word_step(z,a,n,b,v,f,s,l),bit_oracle(z,a,n,b,v,f,l,s)),"word oracle");}});
 group("neutral fringe and final idempotence",[]{Lane l{};for(u32 i=0;i<5000;i++){u32 x=mix32(i),a=mix32(i+7),n=mix32(i+11),b=mix32(i+17),v=mix32(i+23);auto r=word_step(x,a,n,b,v,v,{x,0},l);require(r.output==(word_step(r.output,a,n,b,v,v,{x,0},l).output),"idempotence");require((r.output&~x)==0,"support");}});
 group("mask nonmonotonicity witness",[]{Lane l{};require(word_step(3,3,3,2,3,3,{3,0},l).output==0,"original absorbed");require(word_step(3,3,3,2,3,1,{3,0},l).output==1,"narrower retains");});
 group("Morton tile bijection inverse",[]{std::set<u32> used;auto s=shape(8,256);for(u32 r=0;r<8;r++)for(u32 w=0;w<8;w++){u32 k=address(s,r,w,Layout::morton8);used.insert(k);auto p=inverse(s,k,Layout::morton8);require(p[0]==r&&p[1]==w,"tile inverse");}require(used.size()==64,"tile bijection");});
 group("padded atlas roundtrips",[]{for(u32 r:{1u,7u,9u,17u,64u})for(u32 a:{1u,31u,33u,257u,1024u}){auto s=shape(r,a);for(auto l:{Layout::linear,Layout::morton8})for(u32 k=0;k<stored(s);k++){auto p=inverse(s,k,l);require(address(s,p[0],p[1],l)==k,"atlas inverse");}}});
 group("tail masks and dimensions",[]{for(u32 a=1;a<100;a++){auto s=shape(1,a);require(popcount(valid_mask(s,s.words-1))==(a%32?a%32:32),"tail bits");}must_throw([]{shape(0,1);});must_throw([]{shape(65536,65536);});must_throw([]{inverse(shape(1,1),64,Layout::linear);});});
 group("zero padding in all planes",[]{Fixture f({shape(17,257),Layout::morton8,Producer::provided,1});auto s=f.config.shape;for(u32 r=0;r<s.padded_rows;r++)for(u32 w=0;w<s.padded_words;w++){u32 k=address(s,r,w,f.config.layout);for(const auto&m:f.masks){if(r>=s.rows||w>=s.words)require(m[k]==0,"padding");else require((m[k]&~valid_mask(s,w))==0,"tail");}}});
 group("cross-layout and profile exact integer conformance",[]{for(auto p:{Producer::provided,Producer::recurrent,Producer::shift_xor,Producer::shift_or})for(u32 f=0;f<2;f++){Config c{shape(17,257),Layout::linear,p,f};Fixture a(c);c.layout=Layout::morton8;Fixture b(c);auto x=a.initial,y=b.initial;for(u32 e=0;e<4;e++){auto ra=cpu_propose(a,x),rb=cpu_propose(b,y);for(std::size_t i=0;i<x.size();i++)require(exact_word(ra[i].word,rb[i].word),"layout output");commit_verified(a,x,ra);commit_verified(b,y,rb);}}});
 group("failed epoch preserves state",[]{Fixture f({shape(9,33),Layout::linear,Producer::recurrent,0});auto state=f.initial,before=state;auto result=cpu_propose(f,state);result.back().word.output^=1;must_throw([&]{commit_verified(f,state,result);});for(std::size_t i=0;i<state.size();i++)require(state[i].word==before[i].word&&state[i].q==before[i].q,"atomic host state");});
 group("diagnostic-only axis changes do not affect core",[]{Config c{shape(17,257),Layout::linear,Producer::recurrent,0};Fixture f(c),g(c);for(auto&l:g.lanes)l.angle.alpha+=.75;auto a=cpu_propose(f,f.initial),b=cpu_propose(g,g.initial);for(std::size_t i=0;i<a.size();i++)require(exact_word(a[i].word,b[i].word),"no implicit angular feedback");});
 group("invalid JK inputs rejected",[]{Lane l{};State s{};l.j=2;must_throw([&]{validate_lane(l,s);});l.j=0;s.q=2;must_throw([&]{validate_lane(l,s);});});
 group("shift merge variants and zero guard",[]{Lane l{};require(produce({5,0},l,Producer::shift_xor)==8,"xor");require(produce({5,0},l,Producer::shift_or)==10,"or");l.jitter=~u32(0);require(produce({0,0},l,Producer::shift_xor)==0,"zero guard");});
 group("literal OTAN2 and raw residual",[]{AngleInput a{1,1,4,.125,0,1,1,1};auto r=observe(a);require(near(r.beta,PI/4),"source equation");require(near(r.raw,PI/4-4),"raw not wrapped");require(r.principal>0,"auxiliary view");});
 group("quadrants and literal reversal alias",[]{AngleInput a{-1,1,0,.125,0,1,1,1};require(near(observe(a).beta,-PI/4),"literal quadrant");a.profile=1;require(near(observe(a).beta,3*PI/4),"completion quadrant");a.dr=-1;a.dp=0;require(near(observe(a).beta,-PI),"negative endpoint");});
 group("zero and denominator statuses",[]{AngleInput a{0,1,0,.125,0,1,1,1};require(observe(a).status==u32(Status::ratio_undefined),"literal singular");a.profile=1;require(near(observe(a).beta,PI/2),"explicit completion");a.dp=0;require(observe(a).status==u32(Status::zero_increment),"zero remains undefined");});
 group("missing optional fields",[]{AngleInput a{1,1,0,.125,0,0,1,1};auto r=observe(a);require(r.status==u32(Status::axis_unspecified)&&r.beta_status==0,"missing axis");a.axis_known=1;a.frame_known=0;require(observe(a).status==u32(Status::frame_unspecified),"frame");a.frame_known=1;a.increment_known=0;require(observe(a).status==u32(Status::increment_policy_unspecified),"increment");});
 group("nonfinite and ratio range",[]{AngleInput a{1,std::numeric_limits<double>::infinity(),0,.125,0,1,1,1};require(observe(a).status==u32(Status::nonfinite_input),"finite contract");a.dr=DBL_MIN;a.dp=DBL_MAX;require(observe(a).status==u32(Status::numerical_range),"ratio overflow");a.dr=DBL_MAX;a.dp=DBL_MIN;require(observe(a).status==u32(Status::numerical_range),"ratio underflow");});
 group("periodic views and seam",[]{require(wrap(PI)==-PI,"principal endpoint");require(near(wrap((1-359)*PI/180),2*PI/180),"seam");for(int i=-100;i<=100;i++){double v=i*.125;require(near(wrap(wrap(v)),wrap(v)),"wrap idempotence");}});
 group("wrap exact legacy seams and exceptional periods",[]{
  const double inf=std::numeric_limits<double>::infinity(),nan=std::numeric_limits<double>::quiet_NaN();
  const double tiny=std::numeric_limits<double>::denorm_min();
  // Exercise the branch boundary separately from the half-period output seam.
  // Invalid/custom periods retain the old behavior; this does not declare them
  // valid angle units or turn NaNs into defined diagnostic values.
  for(double period:{PI,TAU,.125,1.0,10.0,DBL_MIN,tiny,DBL_MAX,inf,-PI,-TAU,0.0,-0.0,nan,-inf}){
   for(double x:{0.0,-0.0,tiny,-tiny,DBL_MIN,-DBL_MIN,DBL_MAX,-DBL_MAX,PI/2,-PI/2,PI,-PI,TAU,-TAU,inf,-inf,nan})require_legacy_wrap(x,period);
   for(double seam:{period/2,-period/2,period,-period}){
    require_legacy_wrap(seam,period);
    require_legacy_wrap(std::nextafter(seam,inf),period);
    require_legacy_wrap(std::nextafter(seam,-inf),period);
   }
  }
  require(double_bits(wrap(-0.0))==double_bits(0.0),"wrap still canonicalizes negative zero");
 });
 group("wrap exact legacy random binary64 inputs",[]{
  u64 rng=0xd1b54a32d192ed03ull;
  const auto next=[&](){rng^=rng<<13; rng^=rng>>7; rng^=rng<<17; return rng;};
  for(u32 i=0;i<25000;++i){
   const double x=from_double_bits(next()),period=from_double_bits(next());
   require_legacy_wrap(x,PI);require_legacy_wrap(x,TAU);
   require_legacy_wrap(x,period);require_legacy_wrap(x,absd(period));
   // Dense ordinary angles supplement exponent-wide random bit patterns.
   require_legacy_wrap((double(i)-12500.0)/1024.0,(i&1)?PI:TAU);
  }
 });
 group("six invariant laws on bounded inputs",[]{for(int dr=-16;dr<=16;dr++)for(int dp=-16;dp<=16;dp++)for(u32 p=0;p<2;p++){AngleInput a{dr/8.0,dp/8.0,.2,.125,p,1,1,1};auto o=observe(a);Check c[6];invariant_bank(a,o,c);for(auto&x:c)require(o.status==0?x.state==0:x.state==2,"bank status");}});
 group("fixed rotation preserves singularity and profile semantics",[]{
  // Independently rounded sin/cos(binary64 .4) put the rotated radial component at zero.
  for(double sign:{-1.0,1.0})for(u32 p=0;p<2;p++){
   AngleInput a{sign*0x1.8ec3ae92b676bp-2,sign*0x1.d7954e7dba2f8p-1,.2,.125,p,1,1,1};
   auto base=observe(a);Check c[6];invariant_bank(a,base,c);
   require(base.status==u32(Status::defined),"rotation base is defined");
   require(p?c[4].state==u32(CheckState::pass):(c[4].state==u32(CheckState::undefined)&&c[4].reason==101),"literal rotated singularity differs from directed profile");
   a.dr+=1e-10;invariant_bank(a,observe(a),c);
   require(c[4].state==u32(CheckState::pass),"rotation away from singularity remains available");
  }
 });
 group("W precondition does not invalidate orientation",[]{AngleInput a{1,1,0,0,0,1,1,1};auto r=observe(a);Check c[6];invariant_bank(a,r,c);require(r.status==0,"angle independent of W");for(u32 i=0;i<6;i++)require(c[i].state==(i==1?2u:0u),"local W status");});
 group("memory and 12 GiB capacity scenario",[]{auto s=shape(128,1024);u64 mb=u64(1)<<20,gb=u64(1)<<30;require(payload(s)==1114112,"payload arithmetic");require(allowed(plan(s),8*gb,12*gb,512*mb,1536*mb),"default admission");require(!allowed(plan(s),16*mb,12*gb,512*mb,1536*mb),"free-memory refusal");require(!allowed(1,8*gb,gb,512*mb,1536*mb),"reserve subtraction guard");});
 group("device reserve survives existing VRAM use",[]{u64 mb=u64(1)<<20,gb=u64(1)<<30;
  require(!allowed(65*mb,gb,12*gb,512*mb,1536*mb),"already below free-memory reserve");
  require(!allowed(65*mb,1536*mb,12*gb,512*mb,1536*mb),"reserve leaves no allocation room");
  require(!allowed(65*mb,1600*mb,12*gb,512*mb,1536*mb),"allocation would consume reserve");
  require(allowed(64*mb,1600*mb,12*gb,512*mb,1536*mb),"allocation exactly preserves reserve");
  require(!allowed(71*mb,100*mb,12*gb,512*mb,0),"free-memory fraction remains enforced");
  require(!allowed(513*mb,8*gb,12*gb,512*mb,1536*mb),"explicit budget remains enforced");
 });
 group("log-polar dictionary roundtrips",[]{LogPolarChart c;for(u32 i=0;i<c.rows;i+=5)for(u32 j=0;j<c.angles;j+=17){auto n=c.node(i,j);auto p=c.quantize(std::exp(n[0]),n[1]);require(p[0]==i&&p[1]==j,"chart roundtrip");}});
 group("log-polar domain and wrap",[]{LogPolarChart c;must_throw([&]{c.quantize(0,0);});must_throw([&]{c.quantize(c.r_max,0);});auto a=c.quantize(1,-.2),b=c.quantize(1,TAU-.2);require(a==b,"phase chart wrap");});
 group("JSON safe string escaping",[]{require(json_string("a\"b\n") == "\"a\\\"b\\u000a\"","escape");});
 std::cout<<"RESULT "<<groups<<" groups; "<<assertions<<" assertions passed\n";return 0;
}catch(const std::exception&e){std::cerr<<"FAIL: "<<e.what()<<" after "<<groups<<" groups\n";return 1;}}
