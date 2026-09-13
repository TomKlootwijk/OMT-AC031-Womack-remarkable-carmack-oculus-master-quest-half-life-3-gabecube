#include "atomos/runtime.hpp"
#include <iostream>
#include <random>
#include <cmath>
#include <stdexcept>
#include <functional>
#include <algorithm>
using namespace atomos;
namespace {
std::uint64_t checks=0;unsigned groups=0;
void require(bool ok,const char*msg){++checks;if(!ok)throw std::runtime_error(msg);}
void test(const char*name,const std::function<void()>&f){f();++groups;std::cout<<"PASS "<<name<<'\n';}
void expect_error(const std::function<void()>&f){bool seen=false;try{f();}catch(const std::exception&){seen=true;}require(seen,"exception expected");}
Tables clear_tables(const Config&c,std::size_t candidates=2){auto t=make_tables(c);std::fill(t.mask.begin(),t.mask.end(),0);t.jitter.assign((candidates+31)/32,0);return t;}
}
int main(){try{
 test("SHA-256 known vectors",[]{
  require(hex(sha256(std::string()))=="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","empty hash");
  require(hex(sha256(std::string("abc")))=="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad","abc hash");
  require(hex(sha256(std::string("abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq")))=="248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1","multi-block hash");
  require(hex(sha256(std::string(1000000,'a')))=="cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0","million-byte hash");
 });
 test("identity-seeded log-polar projection",[]{Config c;auto d=sha256("atomOS:synthetic:mirage:v2:46");auto n=root_node(d,c);
    require(n.alive&&n.branch==1,"root live seed");require(std::fabs(n.rho-(-.6116561889648438f))<1e-6f,"seed rho");
    require(std::fabs(n.phi-.774228865785656f)<1e-6f,"seed phi");require(n.cell<c.n_rho*c.n_phi,"seed cell range");
 });
 test("word XOR and OR are different",[]{require(word_step(5,0,0)==8,"XOR collision cancellation");require(word_step(5,0,0,true)==10,"OR union");require(word_step(0,0xffffffff,0)==0,"word zero absorbing");require(word_step(1,0,2)==0,"whole register absorption");});
 test("unsigned shifts / mask properties",[]{std::mt19937 gen(142);for(int k=0;k<10000;++k){std::uint32_t p=gen(),j=gen(),m=gen();
    auto b=((p<<1)^(p>>1))^j;auto expected=p&&!(b&m)?b:0;require(word_step(p,j,m)==expected,"word reference");require(popcount32(m)<=32,"popcount bound");}});
 test("rotation boundaries",[]{for(unsigned k=0;k<64;++k){auto x=rotl32(0x12345678u,k);require(rotl32(x,32-(k%32))==0x12345678u,"rotation inverse");}require(rotl32(1,32)==1,"no shift-by-word-size UB");});
 test("coordinate words are indices",[]{for(unsigned i:{0u,1u,32768u,65535u})for(unsigned j:{0u,1u,31u,65535u}){auto c=pack_coordinate(i,j);require((c>>16)==i&&(c&65535u)==j,"coordinate packing");}});
 test("configuration validation",[]{Config c;validate_config(c);auto d=c;d.n_phi=7;expect_error([&]{validate_config(d);});d=c;d.dt=NAN;expect_error([&]{validate_config(d);});d=c;d.rho_max=d.rho_min;expect_error([&]{validate_config(d);});d=c;d.substeps=0;expect_error([&]{validate_config(d);});d=c;d.n_phi=65536;d.n_rho=65536;expect_error([&]{validate_config(d);});});
 test("annular half-open domain",[]{Config c;Node n;n.rho=c.rho_min;n.phi=-tau;require(normalize(n,c)==Status::Active,"min valid");require(n.cell<c.n_rho*c.n_phi,"cell range");n.rho=c.rho_max;require(normalize(n,c)==Status::RadialSink,"max excluded");n.rho=NAN;require(normalize(n,c)==Status::NumericFault,"NaN rejected");});
 test("Klein positive and negative wraps",[]{Config c;c.topology=Topology::Klein;float L=c.rho_max-c.rho_min;for(int k=-7;k<=7;++k){Node n;n.rho=c.rho_min+0.25f*L+k*L;n.phi=0.5f;require(normalize(n,c)==Status::Active,"Klein normalizes");require(std::fabs(n.rho-(c.rho_min+.25f*L))<1e-6f,"Klein radial wrap");require(n.orientation==unsigned(k%2!=0),"Klein parity");auto p=(k%2)?tau-0.5f:0.5f;require(std::fabs(n.phi-p)<1e-6f,"Klein reflection");}});
 test("Klein vector-field symmetry",[]{Config c;c.topology=Topology::Klein;auto t=clear_tables(c);for(float p:{0.0f,0.3f,1.2f,2.3f,tau*.5f}){auto a=rhs({0,p},c,t.view()),b=rhs({0,-p},c,t.view());require(std::fabs(a.x-b.x)<1e-6f,"even radial field");require(std::fabs(a.y+b.y)<1e-6f,"odd angular field");}});
 test("LUT phase error bound",[]{Config c;auto t=clear_tables(c);for(int k=0;k<2000;++k){float p=-5.0f+float(k)/137;auto cs=angle_components(p,c,t.view());require(std::fabs(cs.x-std::cos(p))<tau/(2*c.n_phi)+2e-6f,"cos LUT bound");require(std::fabs(cs.y-std::sin(p))<tau/(2*c.n_phi)+2e-6f,"sin LUT bound");}});
 test("distinct child identifiers and hinge",[]{Config c;c.growth=c.omega=c.wind_x=c.wind_y=0;auto t=clear_tables(c);Node n;n.branch=7;n.phi=1;
  auto l=propagate_child(n,0,0,c,t.view()),r=propagate_child(n,1,1,c,t.view());require(l.branch==14&&r.branch==15,"lineage children");require(l.alive&&r.alive,"children alive");require(l.phi>n.phi&&r.phi<n.phi,"opposite hinges");});
 test("lineage overflow guarded",[]{Config c;auto t=clear_tables(c);Node n;n.branch=0x8000000000000000ull;auto z=propagate_child(n,0,0,c,t.view());require(z.status==Status::LineageOverflow&&!z.alive,"overflow is not truncation");expect_error([&]{make_jitter({n},sha256("x"),0,32);});});
 test("inactive state cannot be revived",[]{Config c;auto t=clear_tables(c);t.jitter[0]=0xffffffff;Node n;n.alive=0;auto z=propagate_child(n,0,0,c,t.view());require(z.status==Status::InactiveParent&&!z.alive,"no revival");});
 test("jitter veto is one bit per candidate",[]{Config c;auto t=clear_tables(c);t.jitter[0]=2;Node n;auto a=propagate_child(n,0,0,c,t.view()),b=propagate_child(n,1,1,c,t.view());require(a.alive==1,"unvetoed child");require(b.alive==0&&b.status==Status::JitterVeto,"vetoed child");});
 test("jitter endpoints and repeatability",[]{auto root=sha256("test");for(unsigned c=2;c<202;++c){require(jitter_bit(root,0,c,0)==0,"zero veto probability");require(jitter_bit(root,0,c,256)==1,"unit veto probability");require(jitter_bit(root,7,c)==jitter_bit(root,7,c),"repeatable jitter");}expect_error([&]{jitter_bit(root,0,2,257);});});
 test("obstacle sink preserves identity",[]{Config c;c.growth=c.omega=c.wind_x=c.wind_y=0;auto t=clear_tables(c);std::fill(t.mask.begin(),t.mask.end(),0xffffffffu);Node n;auto z=propagate_child(n,0,0,c,t.view());require(z.branch==2&&!z.alive&&z.status==Status::ObstacleSink,"sink and identity");});
 test("radial absorption",[]{Config c;c.growth=1;c.wind_x=c.wind_y=0;auto t=clear_tables(c);Node n;n.rho=1.99f;auto z=propagate_child(n,0,0,c,t.view());require(!z.alive&&z.status==Status::RadialSink,"outbound sink");});
 test("RK4 constant log-field exactness",[]{Config c;c.wind_x=c.wind_y=0;auto t=clear_tables(c);auto y=rk4({0.3f,1.0f},0.125f,c,t.view());require(std::fabs(y.x-(.3f+.125f*c.growth))<1e-6f,"constant rho integration");require(std::fabs(y.y-(1+.125f*c.omega))<1e-6f,"constant phi integration");});
 test("frontier shape validation",[]{Config c;auto t=clear_tables(c);t.jitter.clear();expect_error([&]{propagate_cpu({Node{}},c,t);});});
 test("VM unary batch and independent tapes",[]{auto p=unary_program();std::vector<VMState>s(64);std::vector<std::uint32_t>t(128,0);for(unsigned i=0;i<64;++i){s[i].head=16;for(unsigned j=0;j<i%8;++j)t[i*2]|=1u<<(16+j);}vm_cpu(s,t,64,p,128);
    for(unsigned i=0;i<64;++i){auto n=i%8;require(s[i].status==VMStatus::Halted,"unary halt");require(s[i].steps==n+1,"unary step count");require(s[i].head==int(16+n),"unary head");require(t[i*2]==(((1u<<(n+1))-1u)<<16),"unary append");}});
 test("VM continuation under bounded launch budgets",[]{auto p=unary_program();std::vector<VMState>a(1),b(1);std::vector<std::uint32_t>x{255},y{255};vm_cpu(a,x,32,p,100);for(int k=0;k<20;++k)vm_cpu(b,y,32,p,1);require(x==y&&a[0].steps==b[0].steps&&a[0].head==b[0].head&&a[0].status==b[0].status,"budget continuation");});
 test("VM out-of-range is no-commit",[]{auto p=unary_program();p.words[0]=encode_instruction(0,1,-1);std::uint32_t tape=0;VMState s;vm_step(s,&tape,32,p.states,p.halt,HostProgram{p.words.data()});require(s.status==VMStatus::TapeExhausted&&s.steps==0&&tape==0,"write/move atomic bound");});
 test("VM invalid encoding is no-commit",[]{auto p=unary_program();for(auto bad:{0u,0xffffffffu,encode_instruction(0,1,0)|0x10u,encode_instruction(9,1,0)}){p.words[0]=bad;VMState s;std::uint32_t t=0;vm_step(s,&t,32,p.states,p.halt,HostProgram{p.words.data()});require(s.status==VMStatus::BadProgram&&t==0&&s.steps==0,"bad instruction");}});
 test("VM invalid head and halted states",[]{auto p=unary_program();std::uint32_t t=0;VMState s;s.head=-1;vm_step(s,&t,32,p.states,p.halt,HostProgram{p.words.data()});require(s.status==VMStatus::TapeExhausted,"negative head");s=VMState{};s.state=1;vm_step(s,&t,32,p.states,p.halt,HostProgram{p.words.data()});require(s.status==VMStatus::Halted&&s.steps==0,"already halted");});
 test("VM 32-bit word boundary",[]{auto p=unary_program();std::vector<VMState>s(1);s[0].head=31;std::vector<std::uint32_t>t{0x80000000u,0};vm_cpu(s,t,64,p,10);require(t[0]==0x80000000u&&t[1]==1&&s[0].head==32,"cross-word transition");});
 std::cout<<"RESULT groups="<<groups<<" assertions="<<checks<<" passed\n";return 0;
}catch(const std::exception&e){std::cerr<<"FAIL after "<<checks<<" assertions: "<<e.what()<<'\n';return 1;}}
