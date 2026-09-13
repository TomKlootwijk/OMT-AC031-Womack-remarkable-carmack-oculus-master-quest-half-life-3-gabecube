#include "atomos/runtime.hpp"
#include <algorithm>
#include <fstream>
#include <sstream>
#include <iomanip>
#include <locale>
#include <stdexcept>
#include <set>
namespace atomos {
void validate_config(const Config& c){
    if(c.n_rho<2||c.n_phi<4||(c.n_phi&(c.n_phi-1))||c.n_rho>65536||c.n_phi>65536||std::uint64_t(c.n_rho)*c.n_phi>(1ull<<28))
        throw std::invalid_argument("chart limits: rho 2..65536, phi power-of-two 4..65536, <=2^28 cells");
    if(!finite(c.rho_min)||!finite(c.rho_max)||c.rho_min>=c.rho_max||c.rho_min< -20||c.rho_max>20)
        throw std::invalid_argument("finite ordered rho bounds required within [-20,20]");
    if(!finite(c.dt)||c.dt<=0||c.dt>1||!c.substeps||c.substeps>256||c.phi_step>=c.n_phi)
        throw std::invalid_argument("dt in (0,1], substeps in [1,256], phi_step<n_phi required");
    for(float v:{c.growth,c.omega,c.wind_x,c.wind_y})if(!finite(v)||std::fabs(v)>10)
        throw std::invalid_argument("field coefficients must be finite with magnitude <=10");
    if(c.topology!=Topology::Annulus&&c.topology!=Topology::Klein)throw std::invalid_argument("invalid topology");
}
Node root_node(const Digest& root,const Config& c){
    validate_config(c);
    const auto i=(unsigned(root[0])<<8)|root[1];
    const auto j=(unsigned(root[16])<<8)|root[17];
    Node n;
    n.rho=float(double(c.rho_min)+(double(c.rho_max)-c.rho_min)*(double(i)+0.5)/65536.0);
    n.phi=float(6.2831853071795864769*(double(j)+0.5)/65536.0);
    n.status=normalize(n,c);n.alive=n.status==Status::Active;
    return n;
}
Tables make_tables(const Config& c){
    validate_config(c);Tables t;t.angles.resize(c.n_phi);
    for(std::uint32_t j=0;j<c.n_phi;++j){double p=6.2831853071795864769*double(j)/c.n_phi;t.angles[j]={float(std::cos(p)),float(std::sin(p))};}
    t.mask.assign((std::uint64_t(c.n_rho)*c.n_phi+31)/32,0u);
    // Synthetic obstacles in two annular sectors: not any location or subject.
    for(std::uint32_t i=0;i<c.n_rho;++i)for(std::uint32_t j=0;j<c.n_phi;++j){
        const bool block=(i>c.n_rho*3/5&&i<c.n_rho*4/5&&j<c.n_phi/7)
             ||(i>c.n_rho/4&&i<c.n_rho/2&&j>c.n_phi/6&&j<c.n_phi/3);
        if(block){auto q=i*c.n_phi+j;t.mask[q>>5]|=1u<<(q&31);}}
    return t;
}
std::vector<std::uint32_t> make_jitter(const std::vector<Node>& in,const Digest& root,std::uint64_t tick,unsigned threshold){
    if(in.size()>(1u<<19))throw std::length_error("candidate budget > 2^20");
    std::vector<std::uint32_t> out((2*in.size()+31)/32,0);
    for(std::size_t i=0;i<in.size();++i){
        if(!in[i].alive||!in[i].branch||in[i].branch>0x7fffffffffffffffull)throw std::invalid_argument("invalid live lineage before generation");
        for(unsigned b=0;b<2;++b){const auto k=2*i+b;if(jitter_bit(root,tick,(in[i].branch<<1)|b,threshold))out[k>>5]|=1u<<(k&31);}}
    return out;
}
std::vector<Node> propagate_cpu(const std::vector<Node>& in,const Config& c,const Tables& t){
    validate_config(c);if(in.size()>(1u<<19)||t.jitter.size()<(2*in.size()+31)/32||t.angles.size()!=c.n_phi
      ||t.mask.size()!=(std::uint64_t(c.n_rho)*c.n_phi+31)/32)throw std::invalid_argument("invalid table sizes or budget");
    std::vector<Node> out(in.size()*2);for(std::size_t k=0;k<out.size();++k)out[k]=propagate_child(in[k>>1],k&1,std::uint32_t(k),c,t.view());return out;
}
void vm_cpu(std::vector<VMState>& s,std::vector<std::uint32_t>& t,std::uint32_t bits,const Program&p,unsigned budget){
    if(!bits||bits>0x7fffffffu||!p.states||p.states>0xffffff||p.halt>=p.states||p.words.size()!=std::size_t(p.states)*2||budget>100000)
        throw std::invalid_argument("invalid VM dimensions or budget");
    std::size_t stride=(std::uint64_t(bits)+31)/32;
    if(t.size()!=s.size()*stride)throw std::invalid_argument("incorrect VM tape allocation");
    for(std::size_t i=0;i<s.size();++i)for(unsigned k=0;k<budget&&s[i].status==VMStatus::Running;++k)
      vm_step(s[i],t.data()+i*stride,bits,p.states,p.halt,HostProgram{p.words.data()});
}
Program unary_program(){Program p;p.words={encode_instruction(1,1,0),encode_instruction(0,1,1),0,0};return p;}
Program load_program(const std::string& path){
    std::ifstream f(path);if(!f)throw std::runtime_error("cannot read program: "+path);
    Program p;std::string line;bool header=false;std::set<unsigned> seen;
    while(std::getline(f,line)){
        line=line.substr(0,line.find('#'));std::istringstream s(line);s>>std::ws;if(s.eof())continue;
        if(!header){std::string a,b,extra;long long n,h;
            if(!(s>>a>>n>>b>>h)||a!="states"||b!="halt"||n<1||n>65536||h<0||h>=n||(s>>extra))throw std::runtime_error("expected: states N halt H (N<=65536)");
            p.states=std::uint32_t(n);p.halt=std::uint32_t(h);p.words.assign(p.states*2,0);header=true;continue;}
        long long q,read,write,move,next;std::string extra;
        if(!(s>>q>>read>>write>>move>>next)||(s>>extra)||q<0||q>=p.states||read<0||read>1||write<0||write>1||move< -1||move>1||next<0||next>=p.states)
            throw std::runtime_error("invalid program row: state read write move next");
        auto i=unsigned(2*q+read);if(!seen.insert(i).second)throw std::runtime_error("duplicate transition");
        p.words[i]=encode_instruction(std::uint32_t(next),unsigned(write),int(move));
    }
    if(!header)throw std::runtime_error("missing program header");
    return p;
}
std::string node_json(const Node& n){
    std::ostringstream s;s.imbue(std::locale::classic());s<<std::setprecision(9);
    s<<"{\"branch\":\""<<n.branch<<"\",\"rho\":";
    if(finite(n.rho))s<<n.rho;else s<<"null";
    s<<",\"phi\":";if(finite(n.phi))s<<n.phi;else s<<"null";
    s<<",\"alive\":"<<n.alive<<",\"cell\":"<<n.cell<<",\"status\":"<<unsigned(n.status)<<",\"orientation\":"<<n.orientation<<"}";return s.str();
}
}
