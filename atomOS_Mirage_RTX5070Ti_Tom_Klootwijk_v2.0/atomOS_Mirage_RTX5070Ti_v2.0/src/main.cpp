#include "atomos/runtime.hpp"
#include <algorithm>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <cstring>
#include <cstdlib>
#include <sstream>
#include <iomanip>
#include <locale>
#include <stdexcept>
#include <map>
using namespace atomos;
namespace {
std::string quote(const std::string& text){std::ostringstream s;s<<'"';for(unsigned char c:text){
    if(c=='"'||c=='\\')s<<'\\'<<c;else if(c=='\n')s<<"\\n";else if(c=='\r')s<<"\\r";else if(c=='\t')s<<"\\t";
    else if(c<32)s<<"\\u"<<std::hex<<std::setw(4)<<std::setfill('0')<<unsigned(c)<<std::dec;else s<<c;}return s.str()+'"';}
unsigned number(const std::string& x,unsigned max){if(x.empty()||x[0]=='-')throw std::invalid_argument("expected nonnegative integer");std::size_t end=0;auto n=std::stoull(x,&end,0);if(end!=x.size()||n>max)throw std::invalid_argument("integer outside option range");return unsigned(n);}
float real(const std::string& x){std::size_t end=0;float v=std::stof(x,&end);if(end!=x.size()||!finite(v))throw std::invalid_argument("invalid real value");return v;}
struct Options {
    Config c;std::string mode="propagate",backend="cpu",out="run_results",seed="atomOS:synthetic:mirage:v2:46",program,tape;
    unsigned generations=10,threshold=32,repeats=1,machines=64,bits=256,budget=128,launches=1,device=0;
    bool verify=false,obstacles=true;
};
void help(){std::cout<<
"atomOS Mirage / Ring Edition 2.0\n"
"Local synthetic simulation; no OS elevation, game injection, network or actuator integration.\n\n"
"  --mode propagate|universal       Default propagate\n"
"  --backend cpu|texture|global     CUDA backends require the atomos_gpu build\n"
"  --out DIR                       Output folder (existing run files are replaced)\n"
"  --verify                        Compare GPU results against CPU semantics\n"
"  --device N                      CUDA device ordinal, default 0\n"
"Propagation: --generations 0..18 --topology annulus|klein --n-rho N\n"
"  --n-phi N --phi-step N --substeps N --dt VALUE --no-wind --no-obstacles\n"
"  --seed TEXT --jitter-threshold 0..256 --repeats 1..10000\n"
"  repeats times the same GPU batch, excluding upload/download; it does not advance time.\n"
"Universal: --program FILE --tape BINARY --machines N --tape-bits N\n"
"  --budget 1..100000 --launches 1..1000\n"
"  Default program appends a 1 to a unary string; each machine owns its packed tape.\n";}
Options parse(int argc,char**argv){Options o;
#ifdef ATOMOS_GPU_AVAILABLE
    o.backend="texture";
#endif
    for(int i=1;i<argc;++i){std::string a=argv[i];auto value=[&](){if(++i>=argc)throw std::invalid_argument("missing value for "+a);return std::string(argv[i]);};
        if(a=="--help"){help();std::exit(0);}else if(a=="--mode")o.mode=value();else if(a=="--backend")o.backend=value();
        else if(a=="--out")o.out=value();else if(a=="--seed")o.seed=value();else if(a=="--program")o.program=value();else if(a=="--tape")o.tape=value();
        else if(a=="--generations")o.generations=number(value(),18);else if(a=="--jitter-threshold")o.threshold=number(value(),256);
        else if(a=="--repeats")o.repeats=number(value(),10000);else if(a=="--machines")o.machines=number(value(),65536);
        else if(a=="--tape-bits")o.bits=number(value(),1048576);else if(a=="--budget")o.budget=number(value(),100000);
        else if(a=="--launches")o.launches=number(value(),1000);else if(a=="--device")o.device=number(value(),1024);
        else if(a=="--n-rho")o.c.n_rho=number(value(),65536);else if(a=="--n-phi")o.c.n_phi=number(value(),65536);
        else if(a=="--phi-step")o.c.phi_step=number(value(),65535);else if(a=="--substeps")o.c.substeps=number(value(),256);
        else if(a=="--dt")o.c.dt=real(value());else if(a=="--verify")o.verify=true;else if(a=="--no-obstacles")o.obstacles=false;
        else if(a=="--no-wind")o.c.wind_x=o.c.wind_y=0;
        else if(a=="--topology"){auto v=value();if(v=="annulus")o.c.topology=Topology::Annulus;else if(v=="klein")o.c.topology=Topology::Klein;else throw std::invalid_argument("unknown topology");}
        else throw std::invalid_argument("unknown option: "+a);
    }
    if(o.mode!="propagate"&&o.mode!="universal")throw std::invalid_argument("mode must be propagate or universal");
    if(o.backend!="cpu"&&o.backend!="texture"&&o.backend!="global")throw std::invalid_argument("unknown backend");
#ifndef ATOMOS_GPU_AVAILABLE
    if(o.backend!="cpu")throw std::invalid_argument("this executable is CPU-only; build atomos_gpu with CUDA 12.8 or newer");
#endif
    if(!o.repeats||!o.machines||o.bits<32||!o.budget||!o.launches||o.out.empty())throw std::invalid_argument("zero/empty resource argument");
    if(std::uint64_t(o.machines)*((o.bits+31ull)/32)*4>(256ull<<20))throw std::invalid_argument("VM tape budget exceeds 256 MiB");
    if(o.tape.size()>o.bits/2||o.tape.find_first_not_of("01")!=std::string::npos)throw std::invalid_argument("tape must be binary and fit in second half of allocation");
    validate_config(o.c);return o;
}
std::ofstream file(const std::filesystem::path&p){std::ofstream f(p,std::ios::binary);if(!f)throw std::runtime_error("cannot write "+p.string());f.exceptions(std::ios::badbit|std::ios::failbit);f.imbue(std::locale::classic());return f;}
void append_float(std::vector<std::uint8_t>& out,float v){std::uint32_t u;std::memcpy(&u,&v,4);append_u32(out,u);}
std::string manifest(const Options&o,const Tables&t,const Digest&root){
    std::vector<std::uint8_t>b;for(auto x:t.angles){append_float(b,x.x);append_float(b,x.y);}auto ah=hex(sha256(b));b.clear();for(auto x:t.mask)append_u32(b,x);
    const auto&c=o.c;std::ostringstream s;s.imbue(std::locale::classic());s<<std::setprecision(9);
    s<<"{\"version\":\"2.0\",\"root_sha256\":\""<<hex(root)<<"\",\"backend\":"<<quote(o.backend)
      <<",\"topology\":"<<quote(c.topology==Topology::Annulus?"annulus":"klein")
      <<",\"n_rho\":"<<c.n_rho<<",\"n_phi\":"<<c.n_phi<<",\"phi_step\":"<<c.phi_step<<",\"substeps\":"<<c.substeps
      <<",\"rho_min\":"<<c.rho_min<<",\"rho_max\":"<<c.rho_max<<",\"dt\":"<<c.dt<<",\"growth\":"<<c.growth
      <<",\"omega\":"<<c.omega<<",\"wind_x\":"<<c.wind_x<<",\"wind_y\":"<<c.wind_y<<",\"jitter_threshold\":"<<o.threshold
      <<",\"angle_sha256\":\""<<ah<<"\",\"mask_sha256\":\""<<hex(sha256(b))<<"\"}";return s.str();
}
void compare(const std::vector<Node>&a,const std::vector<Node>&b){if(a.size()!=b.size())throw std::runtime_error("CPU/GPU output size differs");
    for(std::size_t i=0;i<a.size();++i){const auto&x=a[i];const auto&y=b[i];
        bool mismatch=x.branch!=y.branch||x.alive!=y.alive||x.cell!=y.cell||x.status!=y.status||x.orientation!=y.orientation;
        if(finite(x.rho)!=finite(y.rho)||finite(x.phi)!=finite(y.phi))mismatch=true;
        if(finite(x.rho)&&std::fabs(x.rho-y.rho)>3e-5f*(1+std::fabs(y.rho)))mismatch=true;
        if(finite(x.phi)&&std::fabs(x.phi-y.phi)>3e-5f*(1+std::fabs(y.phi)))mismatch=true;
        if(mismatch)throw std::runtime_error("CPU/GPU mismatch at candidate "+std::to_string(i)+"; boundary classification is not waived");
    }
}
void frame(std::ostream&f,unsigned generation,const std::vector<Node>&v){f<<"{\"generation\":"<<generation<<",\"nodes\":[";for(std::size_t i=0;i<v.size();++i){if(i)f<<',';f<<node_json(v[i]);}f<<"]}";}
}
int main(int argc,char**argv){try{
    const auto o=parse(argc,argv);auto tables=make_tables(o.c);if(!o.obstacles)std::fill(tables.mask.begin(),tables.mask.end(),0);
    const auto root=sha256(o.seed);std::filesystem::create_directories(o.out);const std::filesystem::path out=o.out;
    std::string device="CPU reference";
#ifdef ATOMOS_GPU_AVAILABLE
    std::unique_ptr<GPUBackend> gpu;if(o.backend!="cpu"){gpu.reset(new GPUBackend(o.c,tables,o.backend=="texture",o.device));device=gpu->device_description();}
#endif
    const auto began=std::chrono::steady_clock::now();
    if(o.mode=="universal"){
        auto p=o.program.empty()?unary_program():load_program(o.program);const std::size_t stride=(o.bits+31)/32;
        std::vector<VMState>s(o.machines);std::vector<std::uint32_t>t(o.machines*stride,0);
        for(unsigned i=0;i<o.machines;++i){s[i].head=std::int32_t(o.bits/2);const auto seed=o.tape.empty()?std::string(i%8,'1'):o.tape;
            for(std::size_t j=0;j<seed.size();++j)if(seed[j]=='1'){auto h=std::size_t(s[i].head)+j;t[i*stride+(h>>5)]|=1u<<(h&31);}}
        double kernel_ms=0;for(unsigned launch=0;launch<o.launches;++launch){auto expected_s=s;auto expected_t=t;
#ifdef ATOMOS_GPU_AVAILABLE
            if(gpu){gpu->universal(s,t,o.bits,p,o.budget);kernel_ms+=gpu->last_kernel_ms();}
            else
#endif
            vm_cpu(s,t,o.bits,p,o.budget);
            if(o.verify){vm_cpu(expected_s,expected_t,o.bits,p,o.budget);if(t!=expected_t||s.size()!=expected_s.size())throw std::runtime_error("VM tape mismatch");
                for(std::size_t i=0;i<s.size();++i)if(s[i].state!=expected_s[i].state||s[i].head!=expected_s[i].head||s[i].steps!=expected_s[i].steps||s[i].status!=expected_s[i].status)throw std::runtime_error("VM state mismatch");}
        }
        unsigned halted=0;std::uint64_t steps=0;auto csv=file(out/"machines.csv");csv<<"machine,state,head,status,steps\n";
        for(unsigned i=0;i<o.machines;++i){halted+=s[i].status==VMStatus::Halted;steps+=s[i].steps;csv<<i<<','<<s[i].state<<','<<s[i].head<<','<<unsigned(s[i].status)<<','<<s[i].steps<<'\n';}
        auto raw=file(out/"tapes.u32le");for(auto w:t)for(unsigned j=0;j<4;++j)raw.put(char(w>>(8*j)));
        std::ostringstream r;r<<"{\"mode\":\"universal\",\"backend\":"<<quote(o.backend)<<",\"device\":"<<quote(device)
          <<",\"machines\":"<<o.machines<<",\"halted\":"<<halted<<",\"transitions\":"<<steps<<",\"tape_bits_per_machine\":"<<o.bits
          <<",\"verification_requested\":"<<(o.verify?"true":"false")<<",\"kernel_ms\":";
        if(o.backend=="cpu")r<<"null";else r<<kernel_ms;r<<"}";file(out/"summary.json")<<r.str()<<'\n';std::cout<<r.str()<<'\n';return 0;
    }
    const auto m=manifest(o,tables,root);auto bytes=domain("atomOS:genesis:v2");bytes.insert(bytes.end(),root.begin(),root.end());bytes.insert(bytes.end(),m.begin(),m.end());
    auto head=sha256(bytes);const auto genesis=head;
    auto journal=file(out/"journal.jsonl"),csv=file(out/"nodes.csv"),frames=file(out/"frames.json"),timing=file(out/"timings.csv");
    csv<<"generation,branch,rho,phi,alive,cell,status,orientation\n";csv<<std::setprecision(9);
    timing<<"generation,candidates,active,kernel_ms\n";
    Node n=root_node(root,o.c);if(n.status!=Status::Active)throw std::runtime_error("invalid root");
    std::vector<Node>frontier{n};frames<<"{\"edition\":\"Mirage / Ring\",\"synthetic\":true,\"manifest\":"<<m<<",\"frames\":[";frame(frames,0,frontier);
    std::uint64_t candidates=0;unsigned completed=0;double kernel_total=0;
    for(unsigned tick=0;tick<o.generations&&!frontier.empty();++tick){
        // Budget is checked before a generation; existing committed journals remain inspectable on failure.
        tables.jitter=make_jitter(frontier,root,tick,o.threshold);std::vector<Node>next;double kernel=0;
#ifdef ATOMOS_GPU_AVAILABLE
        if(gpu){next=gpu->propagate(frontier,tables.jitter,o.repeats);kernel=gpu->last_kernel_ms();kernel_total+=kernel;}
        else
#endif
        next=propagate_cpu(frontier,o.c,tables);
        if(o.verify)compare(next,propagate_cpu(frontier,o.c,tables));
        std::vector<Node>accepted;for(const auto&v:next){
            auto event="{\"generation\":"+std::to_string(tick+1)+",\"node\":"+node_json(v)+"}";
            auto b=domain("atomOS:event:v2");b.insert(b.end(),head.begin(),head.end());b.insert(b.end(),event.begin(),event.end());auto h=sha256(b);
            journal<<"{\"previous\":\""<<hex(head)<<"\",\"hash\":\""<<hex(h)<<"\",\"event_json\":"<<quote(event)<<"}\n";head=h;
            csv<<tick+1<<','<<v.branch<<','<<v.rho<<','<<v.phi<<','<<v.alive<<','<<v.cell<<','<<unsigned(v.status)<<','<<v.orientation<<'\n';
            if(v.alive)accepted.push_back(v);
        }
        candidates+=next.size();frontier=std::move(accepted);completed=tick+1;
        timing<<completed<<','<<next.size()<<','<<frontier.size()<<',';if(o.backend!="cpu")timing<<kernel;timing<<'\n';
        frames<<',';frame(frames,completed,frontier);
    }
    frames<<"]}\n";const auto wall=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-began).count();
    file(out/"provenance.json")<<"{\"root_sha256\":\""<<hex(root)<<"\",\"manifest_json\":"<<quote(m)<<",\"genesis\":\""<<hex(genesis)<<"\",\"head\":\""<<hex(head)<<"\",\"events\":"<<candidates<<"}\n";
    std::ostringstream r;r<<"{\"mode\":\"propagate\",\"backend\":"<<quote(o.backend)<<",\"device\":"<<quote(device)
      <<",\"generations\":"<<completed<<",\"candidates\":"<<candidates<<",\"active\":"<<frontier.size()<<",\"wall_ms\":"<<wall
      <<",\"verification_requested\":"<<(o.verify?"true":"false")<<",\"kernel_ms_sum\":";
    if(o.backend=="cpu")r<<"null";else r<<kernel_total;r<<",\"ledger_head\":\""<<hex(head)<<"\"}";
    file(out/"summary.json")<<r.str()<<'\n';std::cout<<r.str()<<'\n';return 0;
}catch(const std::exception&e){std::cerr<<"atomOS: "<<e.what()<<'\n';return 1;}}
