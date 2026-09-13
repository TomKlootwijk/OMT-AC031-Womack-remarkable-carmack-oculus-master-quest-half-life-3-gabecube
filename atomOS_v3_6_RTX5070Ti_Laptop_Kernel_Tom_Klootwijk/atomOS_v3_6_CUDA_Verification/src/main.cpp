#include "atomos/host.hpp"
#include <filesystem>
#include <fstream>
#include <iostream>
namespace fs=std::filesystem;
using namespace atomos;
namespace {
u32 number(const std::string&s){if(s.empty()||s[0]=='-')throw std::invalid_argument("unsigned integer required");std::size_t pos=0;auto x=std::stoull(s,&pos);if(pos!=s.size()||x>0xffffffffull)throw std::invalid_argument("uint32 overflow or invalid number");return u32(x);}
std::ofstream open(const fs::path&p){std::ofstream f;f.exceptions(std::ios::failbit|std::ios::badbit);f.open(p,std::ios::binary);return f;}
void text(const fs::path&p,const std::string&s){auto f=open(p);f<<s;}
void binary(const fs::path&p,const std::vector<u32>&v){auto f=open(p);for(u32 x:v)for(u32 b=0;b<4;b++)f.put(char((x>>(8*b))&255));}
void inputs(const fs::path&dir,const Fixture&f){
 const std::array<std::string,4> names={"asa.u32le","na.u32le","boundary.u32le","fringe.u32le"};for(u32 i=0;i<4;i++)binary(dir/names[i],f.masks[i]);
 auto out=open(dir/"inputs.csv");out<<std::setprecision(17)<<"lane,initial_word,initial_q,jitter,j,k,north,axis,kinematic,blend_known,dr,dp,alpha,interval,profile,axis_known,frame_known,increment_known\n";
 for(std::size_t i=0;i<f.lanes.size();i++){const auto&l=f.lanes[i];const auto&a=l.angle;out<<i<<','<<l.initial_word<<','<<f.initial[i].q<<','<<l.jitter<<','<<l.j<<','<<l.k<<','<<l.north<<','<<l.axis<<','<<l.kinematic<<','<<l.blend_known<<','<<a.dr<<','<<a.dp<<','<<a.alpha<<','<<a.interval<<','<<a.profile<<','<<a.axis_known<<','<<a.frame_known<<','<<a.increment_known<<'\n';}
}
void trace_header(std::ostream&o){o<<"epoch,lane,input_word,q_before,produced,asa,na,hits,output,q_after,blend,blend_known,beta_status,angle_status,beta,raw,principal,line";for(const char*c:{"R","W","P","S","F","V"})o<<','<<c<<"_state,"<<c<<"_reason,"<<c<<"_error";o<<'\n';}
void row(std::ostream&o,u32 epoch,std::size_t lane,const State&before,const Result&r){const auto&w=r.word;const auto&a=r.angle;
 o<<epoch<<','<<lane<<','<<before.word<<','<<before.q<<','<<w.produced<<','<<w.asa<<','<<w.na<<','<<w.hits<<','<<w.output<<','<<w.q_after<<','<<w.blend<<','<<w.blend_known<<','<<a.beta_status<<','<<a.status<<',';
 if(a.beta_status==0)o<<a.beta;
 o<<',';if(a.status==0)o<<a.raw;
 o<<',';if(a.status==0)o<<a.principal;
 o<<',';if(a.status==0)o<<a.line;
 for(const auto&c:r.checks){o<<','<<c.state<<','<<c.reason<<',';if(c.state!=2)o<<c.error;}o<<'\n';
}
}
int main(int argc,char**argv){fs::path staging;try{
 u32 rows=128,angles=1024,epochs=4,seed=130,device=0,budget_mib=512,reserve_mib=1536,block_size=256;bool fringe=false,texture=true,packed=false,max_l1=false,probe=false;
 Layout layout=Layout::morton8;Producer producer=Producer::recurrent;std::string mode="recurrent",profile="mixed",outdir;
 for(int i=1;i<argc;i++){const std::string a=argv[i];
  if(a=="--help"){std::cout<<"atomOS v3.6 K1 / Tom Klootwijk\n--rows N --angles N --epochs N --seed N --out NEW_DIR\n--layout linear|morton8 --read texture|texture-packed|global --mode provided|recurrent|shift-xor|shift-or\n--cache default|max-l1 --block-size 64|128|256\n--profile source|directed|mixed --fringe on|off --device N --budget-mib N --reserve-mib N --probe\n";return 0;}
  if(a=="--probe"){probe=true;continue;}if(++i>=argc)throw std::invalid_argument("missing value for "+a);const std::string v=argv[i];
  if(a=="--rows")rows=number(v);else if(a=="--angles")angles=number(v);else if(a=="--epochs")epochs=number(v);else if(a=="--seed")seed=number(v);else if(a=="--device")device=number(v);else if(a=="--budget-mib")budget_mib=number(v);else if(a=="--reserve-mib")reserve_mib=number(v);else if(a=="--out")outdir=v;
  else if(a=="--layout"){if(v=="linear")layout=Layout::linear;else if(v=="morton8")layout=Layout::morton8;else throw std::invalid_argument("unknown layout");}
  else if(a=="--read"){if(v!="texture"&&v!="global"&&v!="texture-packed")throw std::invalid_argument("unknown read mode");texture=v!="global";packed=v=="texture-packed";}
  else if(a=="--cache"){if(v!="default"&&v!="max-l1")throw std::invalid_argument("unknown cache preference");max_l1=v=="max-l1";}
  else if(a=="--block-size"){block_size=number(v);if(block_size!=64&&block_size!=128&&block_size!=256)throw std::invalid_argument("block size must be 64, 128 or 256");}
  else if(a=="--fringe"){if(v!="on"&&v!="off")throw std::invalid_argument("fringe must be on or off");fringe=v=="on";}
  else if(a=="--profile")profile=v;
  else if(a=="--mode"){mode=v;if(v=="provided")producer=Producer::provided;else if(v=="recurrent")producer=Producer::recurrent;else if(v=="shift-xor")producer=Producer::shift_xor;else if(v=="shift-or")producer=Producer::shift_or;else throw std::invalid_argument("unknown producer");}
  else throw std::invalid_argument("unknown option "+a);
 }
 if(!epochs||epochs>16||device>1024||!budget_mib||budget_mib>8192||reserve_mib>65536)throw std::invalid_argument("epoch/device/budget range");
#ifdef ATOMOS_WITH_CUDA
 if(probe){std::cout<<probe_cuda(int(device))<<'\n';return 0;}const std::string backend="cuda";
#else
 if(probe)throw std::runtime_error("CUDA probe requested from CPU-only executable");
 const std::string backend="cpu";
#endif
 const auto s=shape(rows,angles);if(logical(s)*epochs>(u64(1)<<20))throw std::invalid_argument("review record cap: 2^20 lane-epochs");const u64 budget=u64(budget_mib)<<20;
 if(plan(s)>budget)throw std::invalid_argument("planned payload exceeds explicit budget");
 if(!outdir.empty()&&fs::exists(outdir))throw std::invalid_argument("output directory must not already exist");
 Fixture fixture(Config{s,layout,producer,u32(fringe)},seed,profile);std::unique_ptr<Backend> executor;
#ifdef ATOMOS_WITH_CUDA
 executor=make_cuda_backend(fixture,int(device),texture,budget,u64(reserve_mib)<<20,packed,max_l1,block_size);
#else
 executor=std::make_unique<CpuBackend>(fixture);
#endif
 std::ofstream trace;u64 counts[3]={};u64 committed_rows=0;std::vector<double> times;auto state=fixture.initial;
 if(!outdir.empty()){staging=fs::path(outdir+".partial_"+std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));fs::create_directories(staging);inputs(staging,fixture);trace=open(staging/"trace.csv");trace<<std::setprecision(17);trace_header(trace);}
 for(u32 epoch=0;epoch<epochs;epoch++){
  auto candidate=executor->propose(state);times.push_back(executor->last_ms());
  // Validate ALL candidate lanes before state mutation or publishing this epoch.
  verify_results(fixture,state,candidate);std::vector<State> next;next.reserve(state.size());
  for(std::size_t i=0;i<candidate.size();i++){const auto&r=candidate[i];if(trace.is_open())row(trace,epoch,i,state[i],r);for(const auto&c:r.checks)counts[c.state]++;next.push_back({r.word.output,r.word.q_after});committed_rows++;}
  state.swap(next);
 }
 if(trace.is_open())trace.close();
 std::ostringstream summary;summary<<std::setprecision(17)<<"{\n\"schema\":\"atomOS-v3.6-K1-run\",\n\"chart\":{\"r_min\":0.25,\"r_max\":64,\"angular_sampling\":\"periodic_nodes\"},\n\"backend\":"<<json_string(backend)<<",\n\"device\":"<<executor->device_json()<<",\n\"rows\":"<<rows<<",\"angles\":"<<angles<<",\"words\":"<<s.words<<",\"padded_rows\":"<<s.padded_rows<<",\"padded_words\":"<<s.padded_words<<",\n\"epochs\":"<<epochs<<",\"seed\":"<<seed<<",\"layout\":"<<json_string(layout==Layout::linear?"linear":"morton8")<<",\"read\":"<<json_string(backend=="cpu"?"host":packed?"texture-packed":texture?"texture":"global")<<",\n\"mode\":"<<json_string(mode)<<",\"profile\":"<<json_string(profile)<<",\"fringe\":"<<(fringe?"true":"false")<<",\n\"payload_bytes\":"<<payload(s)<<",\"planned_bytes\":"<<plan(s)<<",\"committed_lane_epochs\":"<<committed_rows<<",\n\"checks_pass\":"<<counts[0]<<",\"checks_fail\":"<<counts[1]<<",\"checks_undefined\":"<<counts[2]<<",\n\"candidate_verification\":\"passed\",\"compute_ms\":[";
 for(std::size_t i=0;i<times.size();i++)summary<<(i?",":"")<<times[i];
 summary<<"]\n}\n";
 if(!outdir.empty()){
  auto final=open(staging/"final_state.csv");final<<"lane,word,q\n";for(std::size_t i=0;i<state.size();i++)final<<i<<','<<state[i].word<<','<<state[i].q<<'\n';final.close();text(staging/"summary.json",summary.str());text(staging/"COMMITTED","All candidate epochs passed local conformance checks before publication.\n");
  if(fs::exists(outdir))throw std::runtime_error("output path appeared during run; refusing replacement");
  fs::rename(staging,outdir);staging.clear();
 }
 std::cout<<summary.str();return 0;
}catch(const std::exception&e){std::cerr<<"atomOS error: "<<e.what()<<'\n';if(!staging.empty())std::cerr<<"Uncommitted diagnostic files retained at "<<staging.string()<<'\n';return 1;}}
