#include "atomos/batch.hpp"
#include <algorithm>
#include <iostream>
#include <stdexcept>
#include <random>
#include <cstring>
#include <vector>
#include <functional>
#include <limits>
using namespace ao;
std::uint64_t assertions=0;unsigned groups=0;
void check(bool value,const char* msg="assertion"){++assertions;if(!value)throw std::runtime_error(msg);}
void near(double x,double y,double tol=1e-10){check(ao::finite(x)&&ao::finite(y)&&::fabs(x-y)<=tol,"numeric mismatch");}
void group(const char* name,std::function<void()> fn){fn();++groups;std::cout<<"PASS "<<name<<'\n';}
Frame sample(){Frame f{};auto g=make_geo();f.epoch.id=1;f.epoch.tick_ms=1000;f.epoch.count=12;f.epoch.asa_mask=f.epoch.na_mask=0xffffffffu;f.epoch.j=1;f.epoch.hinge=.35;
 Vec3 truth=add(g.origin,add(scale(g.east,150),add(scale(g.north,-75),scale(g.up,12))));
 f.epoch.initial[0]=truth.x+80;f.epoch.initial[1]=truth.y-50;f.epoch.initial[2]=truth.z+25;
 const double az[12]={0,31,65,100,142,178,210,245,278,309,337,355},el[12]={16,53,32,70,24,45,12,60,35,20,76,40};
 for(unsigned i=0;i<12;++i){double a=az[i]*pi/180,h=el[i]*pi/180,r=21e6+i*12000;Vec3 pos=add(g.origin,add(scale(g.east,r*::sin(a)*::cos(h)),add(scale(g.north,r*::cos(a)*::cos(h)),scale(g.up,r*::sin(h)))));
 f.obs[i]={pos.x,pos.y,pos.z,norm(sub(pos,truth))+23000,.7+.1*i};}return f;}
Solution run(const Frame& f){return solve(LocalReader{f.obs.data()},f.epoch,default_solver());}
int main(){try{
 group("JK and encoded blend",[]{for(unsigned q=0;q<2;++q){check(jk(q,0,0)==q);check(jk(q,1,0)==1);check(jk(q,0,1)==0);check(jk(q,1,1)==1-q);}for(unsigned a=0;a<2;++a)for(unsigned b=0;b<2;++b)for(unsigned c=0;c<2;++c)check(blend(a,b,c)==(a+b+c)%2);});
 group("uint32 population counts",[]{for(unsigned i=0;i<65536;++i){unsigned n=0;for(unsigned j=0;j<16;++j)n+=(i>>j)&1u;check(popcount(i)==n);}check(popcount(0xffffffffu)==32);});
 group("core absorption not per-bit clearing",[]{auto c=asa_word(255,255,255,128,255);check(c.asa==255&&c.na==255&&c.hits==1&&c.output==0);check(asa_word(3,1,3,2,3).output==1);check(low_mask(0)==0&&low_mask(32)==0xffffffffu);});
 group("exhaustive small word idempotence",[]{for(unsigned x=0;x<16;++x)for(unsigned a=0;a<16;++a)for(unsigned n=0;n<16;++n)for(unsigned b=0;b<16;++b){auto r=asa_word(x,a,n,b,15);check((r.output&~x)==0);check(asa_word(r.output,a,n,b,15).output==r.output);}});
 group("SCLP reference exact key pair",[]{Quantized q{949111,0,1920,227};check(pack_contiguous(q)==0xe7b77000007800e3ull);check(pack_morton(q)==0x88823bb88099128bull);});
 group("both key codecs random round trips",[]{std::mt19937 r(3615);for(int i=0;i<10000;++i){Quantized q{std::uint32_t(r()&0xfffffu),std::uint32_t(r()&0x3ffffu),std::uint32_t(r()&0x3fffu),std::uint32_t(r()&0xfffu)};for(auto x:{unpack_contiguous(pack_contiguous(q)),unpack_morton(pack_morton(q))})check(q.rho==x.rho&&q.theta==x.theta&&q.time==x.time&&q.phi==x.phi);}});
 group("quantizer ends and periodic values",[]{check(quantize(-20,0,0,0).rho==0);check(quantize(0,0,16384,tau).rho==1048575);check(quantize(0,0,16384,tau).time==0);check(periodic_index(-pi,262144)==131072);});
 group("half-turn and Klein differ",[]{auto h=topology_wrap(.25,.2,.35,1,false),k=topology_wrap(.25,.2,.35,1,true);near(h.rho,-19.75);check(h.wraps==1&&h.orientation==-1);near(h.theta,wrap(.2+pi));near(k.theta,wrap(pi-.2));check(h.theta!=k.theta);});
 group("cone exact reference point",[]{Cone c{{0,0,0},{0,0,1},2,pi/6};near(cone_sdf({.15,0,.6},c),-.1700961894323342);near(cone_sdf({0,0,0},c),0);near(cone_sdf({0,0,2},c),2-std::sqrt(3.));check(cone_sdf({2,0,.5},c)>0);});
 group("cone translation invariance",[]{Cone c{{0,0,0},{0,0,1},2,pi/6};auto c2=c;c2.apex={3,-2,5};near(cone_sdf({.15,0,.6},c),cone_sdf({3.15,-2,5.6},c2));});
 group("cone Lipschitz finite cases",[]{Cone c{{0,0,0},{0,0,1},2,pi/6};std::mt19937 r(66);std::uniform_real_distribution<double>d(-2,2);for(int i=0;i<1000;++i){Vec3 a{d(r),d(r),d(r)},b{d(r),d(r),d(r)};check(::fabs(cone_sdf(a,c)-cone_sdf(b,c))<=norm(sub(a,b))+1e-12);}});
 group("sweep interval contains denser minimum",[]{Cone c{{0,0,0},{0,0,1},2,pi/6};Vec3 x{.15,0,.6},path{.75,0,0};auto fine=sweep_interval(x,c,path,4097);for(unsigned n:{3u,5u,9u,17u,65u}){auto a=sweep_interval(x,c,path,n);check(fine.hi>=a.lo-1e-12&&fine.hi<=a.hi+1e-12);}auto zero=sweep_interval(x,c,{0,0,0},2);near(zero.lo,zero.hi);});
 group("sphere and three-valued relation",[]{near(sphere_sdf({1,0,0},{0,0,0},1),0);check(relation({-.2,-.1},.001)==-1);check(relation({.1,.2},.001)==1);check(relation({-.1,.1},.001)==0);});
 group("WGS84 equator and ENU orthonormal",[]{auto p=ecef_from_geodetic(0,0,0);near(p.x,6378137.0);near(p.y,0);near(p.z,0);auto g=make_geo();near(dot(g.east,g.north),0);near(dot(g.up,g.north),0);near(norm(g.up),1);auto local=enu(add(g.origin,add(scale(g.east,20),scale(g.up,5))),g);near(local.x,20,1e-9);near(local.y,0,1e-9);near(local.z,5,1e-9);});
 group("weighted solution recovers known four-state",[]{auto f=sample();auto s=run(f);check(s.status==ok&&s.used==12);auto p=enu({s.state[0],s.state[1],s.state[2]},make_geo());near(p.x,150,1e-6);near(p.y,-75,1e-6);near(p.z,12,1e-6);near(s.state[3],23000,1e-6);check(s.rms_m<1e-6);for(double v:s.formal_sigma)check(ao::finite(v)&&v>0);});
 group("clock-shift equivariance",[]{auto f=sample();auto a=run(f);for(unsigned i=0;i<f.epoch.count;++i)f.obs[i].code+=1000;auto b=run(f);for(int k=0;k<3;++k)near(a.state[k],b.state[k],1e-6);near(b.state[3]-a.state[3],1000,1e-6);});
 group("common sigma scale preserves estimate",[]{auto f=sample();auto a=run(f);for(auto& o:f.obs)o.sigma*=7;auto b=run(f);for(int k=0;k<4;++k){near(a.state[k],b.state[k],1e-6);near(b.formal_sigma[k]/a.formal_sigma[k],7,1e-8);}});
 group("explicit measurement permutation",[]{auto f=sample();auto a=run(f);std::reverse(f.obs.begin(),f.obs.begin()+f.epoch.count);auto b=run(f);for(int k=0;k<4;++k)near(a.state[k],b.state[k],1e-6);});
 group("ASA selection and whole-group disposition",[]{auto f=sample();f.epoch.asa_mask=7;check(run(f).status==insufficient);f.epoch.asa_mask=0xffffffffu;f.epoch.boundary_mask=1;auto s=run(f);check(s.status==absorbed&&s.output_mask==0&&s.q_after==1);});
 group("singular geometry",[]{auto f=sample();for(auto& o:f.obs)o=f.obs[0];check(run(f).status==rank_deficient);});
 group("invalid observation and initial state",[]{auto f=sample();f.obs[0].sigma=0;check(run(f).status==invalid_input);f=sample();f.epoch.initial[0]=bad();check(run(f).status==invalid_input);f=sample();f.epoch.count=33;check(run(f).status==invalid_input);});
 group("iteration-limit status distinct from converged",[]{auto f=sample();auto c=default_solver();c.max_iterations=1;auto s=solve(LocalReader{f.obs.data()},f.epoch,c);check(s.status==iteration_limit);});
 group("corrected observations fixed while nonlinear iterate moves",[]{auto f=sample();auto a=run(f);auto g=make_geo();f.epoch.initial[0]=g.origin.x;f.epoch.initial[1]=g.origin.y;f.epoch.initial[2]=g.origin.z;auto b=run(f);check(a.status==ok&&b.status==ok);for(int k=0;k<4;++k)near(a.state[k],b.state[k],1e-6);});
 group("conjoined enrichment and independent height",[]{auto f=sample();auto s=run(f);auto d=enrich(s,f.epoch,nullptr,nullptr,make_geo());check(d.chart_status==0&&d.otan_status==1);near(d.up,12,1e-6);check(d.key_contiguous!=d.key_morton);auto a=unpack_contiguous(d.key_contiguous),b=unpack_morton(d.key_morton);check(a.rho==b.rho&&a.theta==b.theta&&a.time==b.time&&a.phi==b.phi);});
 group("enrichment does not mutate position or JK",[]{auto f=sample();auto s=run(f),before=s;auto g=make_geo();g.axis_angle=2;auto d=enrich(s,f.epoch,&s,&f.epoch,g);(void)d;check(std::memcmp(&s,&before,sizeof(s))==0);});
 group("full time survives modular alias",[]{auto q=quantize(-4,.3,1920,.35),r=quantize(-4,.3,1920+16384,.35);check(pack_contiguous(q)==pack_contiguous(r));});
 std::cout<<"RESULT groups="<<groups<<" assertions="<<assertions<<" passed\n";return 0;
 }catch(const std::exception& e){std::cerr<<"FAIL after "<<assertions<<": "<<e.what()<<'\n';return 1;}}
