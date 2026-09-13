#include "asa/io.hpp"
#include <functional>
#include <set>
#include <random>
using namespace asa;
static u64 assertions=0,groups=0;
void require(bool b,const char* what){++assertions;if(!b)throw std::runtime_error(what);}
void group(const char* name,const std::function<void()>& f){f();++groups;std::cout<<"PASS "<<name<<'\n';}
bool near(double a,double b,double e=1e-10){return ::fabs(a-b)<e;}
int main(){try{
 group("record ABI",[]{require(sizeof(Sample)==16,"sample");require(sizeof(Result)==32,"result");require(sizeof(Warp)==8,"warp");});
 group("published Morton bit order",[]{require(morton6(1,0)==1,"radial low bit");require(morton6(0,1)==2,"phi low bit");require(morton6(7,7)==63,"tile corner");});
 group("all tile positions unique",[]{std::set<u32>s;for(u32 r=0;r<8;++r)for(u32 p=0;p<8;++p)s.insert(morton6(r,p));require(s.size()==64,"bijection");});
 group("rectangular swizzle round trip",[]{for(u32 h:{8u,16u,40u})for(u32 w:{8u,24u,64u}){Config c;c.rho_bins=h;c.phi_bins=w;std::set<u32>s;for(u32 r=0;r<h;++r)for(u32 p=0;p<w;++p){auto a=storage_index(r,p,c);u32 rr,pp;decode_storage(a,c,rr,pp);require(rr==r&&pp==p,"inverse");s.insert(a);}require(s.size()==h*w&&*s.rbegin()==h*w-1,"dense permutation");}});
 group("linear layout round trip",[]{Config c;c.layout=Layout::Linear;for(u32 k=0;k<c.rho_bins*c.phi_bins;k+=251){u32 r,p;decode_storage(k,c,r,p);require(storage_index(r,p,c)==k,"linear inverse");}});
 group("whole word popcount",[]{for(u32 k=0;k<=65535;++k){u32 n=0;for(u32 b=0;b<16;++b)n+=(k>>b)&1u;require(popcount(k)==n,"popcount");}});
 group("nullifier all bit positions",[]{for(u32 k=0;k<32;++k){u32 b=1u<<k;require(nullifier(b,b)==0,"absorb bit");require(nullifier(b,~b)==b,"clear bit");}});
 group("portal pair is involution",[]{for(u32 i=0;i<256;++i)require(portal_swap(portal_swap(i,32,160,32),32,160,32)==i,"portal inverse");});
 group("wrap and antipode convention",[]{require(wrap(tau)==0,"tau wraps");require(near(wrap(-.1),tau-.1),"negative wrap");require(signed_angle(pi)==-pi,"antipode");});
 group("configuration validation",[]{Config c;c.rho_bins=9;bool e=false;try{validate(c);}catch(const std::invalid_argument&){e=true;}require(e,"bad dimension rejected");});
 group("numerical aperture conversion",[]{require(near(alpha_from_na(.5,1),pi/6),"asin law");require(near(alpha_from_na(1,1),pi/2),"NA limit");});
 group("numerical aperture domain",[]{for(double a:{-1.,1.1}){bool e=false;try{alpha_from_na(a,1);}catch(...){e=true;}require(e,"invalid NA");}});
 group("memory calculation",[]{Config c;require(required_bytes(c,65536)==3690496,"default bytes");require(required_bytes(c,0)==544768,"empty batch bytes");});
 group("memory cap input",[]{Config c;bool e=false;try{required_bytes(c,4194305);}catch(...){e=true;}require(e,"sample cap");});
 group("lens table even odd symmetry",[]{Config c;Fixture f(c);for(u32 j=1;j<c.warp_bins/2;++j){require(f.warp[j].radial==f.warp[c.warp_bins-j].radial,"even radial");require(f.warp[j].angular==-f.warp[c.warp_bins-j].angular,"odd phase");}});
 group("lens interpolation reflection",[]{Config c;Fixture f(c);for(int k=1;k<100;++k){double d=k*.013;auto a=warp_lookup(d,c,f.access()),b=warp_lookup(-d,c,f.access());require(near(a.radial,b.radial,1e-12),"reflection radial");require(near(a.angular,-b.angular,1e-12),"reflection phase");}});
 group("identity lens",[]{Config c;c.radial_warp=0;c.angular_warp=0;Fixture f(c);auto a=warp_lookup(.8,c,f.access());require(a.radial==0&&a.angular==0,"zero lens");});
 group("bilateral aperture accepts center",[]{Config c;c.hinge=0;Fixture f(c,true);auto r=evaluate(Sample{1,0},c,f.access());require(r.flags==7,"two valid sides");require(r.left==r.right&&r.mean==r.left,"center blend");});
 group("aperture upper radial bound excluded",[]{Config c;Fixture f(c,true);auto r=evaluate(Sample{c.pupil_max,0},c,f.access());require(r.flags==0,"pupil half open");});
 group("aperture lower radial bound included",[]{Config c;c.hinge=0;Fixture f(c,true);auto r=evaluate(Sample{c.pupil_min,0},c,f.access());require(r.flags==7,"lower included");});
 group("NA rejects outside wedge",[]{Config c;c.hinge=0;Fixture f(c,true);auto r=evaluate(Sample{1,c.alpha+.01},c,f.access());require(r.flags==0&&r.mean==0,"angular stop");});
 group("lens chart escape",[]{Config c;c.pupil_max=c.rho_max;c.hinge=0;c.radial_warp=1;Fixture f(c,true);auto r=evaluate(Sample{3.99,1.1},c,f.access());require(r.flags==0,"warped out of chart");});
 group("invalid sample is isolated",[]{Config c;Fixture f(c);auto r=evaluate(Sample{1,std::numeric_limits<double>::quiet_NaN()},c,f.access());require(r.flags==InputInvalid&&r.left_cell==invalid_index,"nan guard");});
 group("finite extreme phase remains finite",[]{Config c;Fixture f(c);auto r=evaluate(Sample{1,std::numeric_limits<double>::max()},c,f.access());require(!(r.flags&InputInvalid)&&asa::finite(r.mean),"huge phase");});
 group("all mask bits force zero output",[]{Config c;Fixture f(c);for(auto&w:f.mask)w=~u32(0);auto r=evaluate(Sample{1,0},c,f.access());require(r.flags==0&&r.mean==0,"full matte");require(r.left_cell!=invalid_index,"queried cell preserved");});
 group("linear and Morton field equivalence",[]{Config a;Config b=a;b.layout=Layout::Linear;Fixture fa(a),fb(b);auto z=make_samples(8192,a);auto x=cpu_run(a,fa,z),y=cpu_run(b,fb,z);compare(x,y,0);require(x.size()==8192,"complete comparison");});
 group("sides exchange on reflected input",[]{Config c;c.hinge=0;Fixture f(c);for(int k=1;k<80;++k){double d=k*.013;auto a=evaluate(Sample{1.01,d},c,f.access()),b=evaluate(Sample{1.01,-d},c,f.access());require(a.left_cell==b.right_cell&&a.right_cell==b.left_cell,"cell reflection");require(a.mean==b.mean,"mean reflection");}});
 group("fixture restart is deterministic",[]{Config c;Fixture a(c),b(c);require(a.image==b.image&&a.mask==b.mask,"fixture repeat");auto x=make_samples(128,c),y=make_samples(128,c);for(u32 i=0;i<128;++i)require(x[i].rho==y[i].rho&&x[i].phi==y[i].phi,"sample repeat");});
 group("empty batch",[]{Config c;Fixture f(c);require(cpu_run(c,f,{}).empty(),"empty output");});
 group("strict index differential",[]{Result a{1,1,1,0,7,10,11,0},b=a;b.left_cell=12;bool e=false;try{compare({a},{b});}catch(...){e=true;}require(e,"index mismatch cannot pass tolerance");});
 std::cout<<"RESULT "<<groups<<" groups / "<<assertions<<" assertions passed\n";return 0;
}catch(const std::exception&e){std::cerr<<"FAIL group "<<groups<<": "<<e.what()<<'\n';return 1;}}
