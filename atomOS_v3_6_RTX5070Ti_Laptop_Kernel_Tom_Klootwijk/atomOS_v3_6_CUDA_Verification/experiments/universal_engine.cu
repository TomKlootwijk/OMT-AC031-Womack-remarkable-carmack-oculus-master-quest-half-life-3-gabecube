// Tom Klootwijk atomOS: integrated word + programmable-machine epoch profile.
// The CUDA interpreter executes supplied rules as data, one ordered machine
// transition at a time. Its tape is writable global memory, never a texture.
#if defined(_WIN32)
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#ifdef near
#undef near // Win32 compatibility macro conflicts with atomos::near comparator.
#endif
#endif
#include "../cuda/kernel.cu"
#include "atomos/universal.hpp"
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>

using namespace atomos;
namespace U=atomos::universal;
namespace fs=std::filesystem;
namespace engine_detail {
using i64=std::int64_t;
constexpr u32 MAX_STEPS=65536;
struct ResourceRefused:std::runtime_error {using std::runtime_error::runtime_error;};
struct MemoryPolicy {u64 budget,reserve,k1_payload;int device;};
u64 available_host_memory(){
#if defined(_WIN32)
 MEMORYSTATUSEX state{};state.dwLength=sizeof(state);
 if(GlobalMemoryStatusEx(&state))return u64(state.ullAvailPhys);
#endif
 return 0; // Unknown, rather than a fabricated available-byte count.
}
struct MachineResult {U::Machine machine;u32 steps;U::Stop stop;};

__global__ void atomos_universal_propose(const U::Rule*rules,const u32*halt,
 u32 states,U::PackedTapeView tape,U::Machine initial,u32 budget,
 U::Step*trace,MachineResult*out){
 if(blockIdx.x||threadIdx.x)return;
 MachineResult result{initial,0,U::Stop::running};
 if(initial.control>=states){result.stop=U::Stop::invalid;*out=result;return;}
 if(!U::contains(tape,initial.head)){result.stop=U::Stop::tape_range;*out=result;return;}
 if(halt[initial.control]){result.stop=U::Stop::halted;*out=result;return;}
 for(u32 step=0;step<budget;step++){
  u32 symbol=0;
  if(!U::packed_read(tape,result.machine.head,symbol)){
   result.stop=U::Stop::tape_range;break;
  }
  if(symbol>=tape.alphabet){result.stop=U::Stop::invalid;break;}
  const U::Rule rule=rules[u64(result.machine.control)*tape.alphabet+symbol];
  if(!rule.defined){result.stop=U::Stop::missing_rule;break;}
  if(rule.next>=states||rule.write>=tape.alphabet||rule.move< -1||rule.move>1){
   result.stop=U::Stop::invalid;break;
  }
  const i64 before=result.machine.head;
  if((rule.move<0&&before==(-9223372036854775807LL-1))||
     (rule.move>0&&before==9223372036854775807LL)){
   result.stop=U::Stop::tape_range;break;
  }
  const i64 after=before+rule.move;
  // Validate the complete transition before changing even the candidate tape.
  if(!U::contains(tape,after)){result.stop=U::Stop::tape_range;break;}
  if(!U::packed_write(tape,before,rule.write)){result.stop=U::Stop::invalid;break;}
  U::Step record{};
  record.control_before=result.machine.control;record.control_after=rule.next;
  record.read=symbol;record.write=rule.write;record.move=rule.move;
  record.head_before=before;record.head_after=after;
  trace[result.steps++]=record;
  result.machine={rule.next,after};
  if(halt[rule.next]){result.stop=U::Stop::halted;break;}
 }
 *out=result;
}

u32 number(const std::string&s){
 if(s.empty()||s.front()=='-')throw std::invalid_argument("unsigned integer required");
 std::size_t used=0;const auto value=std::stoull(s,&used);
 if(used!=s.size()||value>0xffffffffull)throw std::invalid_argument("invalid uint32");
 return u32(value);
}
u64 wide_number(const std::string&s){
 if(s.empty()||s.front()=='-')throw std::invalid_argument("unsigned integer required");
 std::size_t used=0;const auto value=std::stoull(s,&used);
 if(used!=s.size())throw std::invalid_argument("invalid uint64");return u64(value);
}
i64 signed_number(const std::string&s){
 std::size_t used=0;const auto value=std::stoll(s,&used);
 if(used!=s.size())throw std::invalid_argument("invalid signed address");return i64(value);
}
double positive(const std::string&s){
 std::size_t used=0;const auto value=std::stod(s,&used);
 if(used!=s.size()||!std::isfinite(value)||value<=0)throw std::invalid_argument("interval must be finite and positive");
 return value;
}
std::ofstream open_file(const fs::path&p){
 std::ofstream f;f.exceptions(std::ios::failbit|std::ios::badbit);f.open(p,std::ios::binary);return f;
}
void write_text(const fs::path&p,const std::string&s){auto f=open_file(p);f<<s;}
void write_binary(const fs::path&p,const std::vector<u32>&words){
 auto f=open_file(p);for(u32 x:words)for(u32 byte=0;byte<4;byte++)f.put(char((x>>(byte*8))&255));
}
std::string machine_json(U::Machine machine){
 return "{\"control\":"+std::to_string(machine.control)+",\"head\":"+std::to_string(machine.head)+"}";
}
void cells_file(const fs::path&p,const U::Cells&cells){
 auto f=open_file(p);f<<"address,symbol\n";for(const auto&cell:cells)if(cell.second)f<<cell.first<<','<<cell.second<<'\n';
}
void state_file(const fs::path&p,const std::vector<State>&state){
 auto f=open_file(p);f<<"lane,word,q\n";for(std::size_t i=0;i<state.size();i++)f<<i<<','<<state[i].word<<','<<state[i].q<<'\n';
}
void inputs(const fs::path&dir,const Fixture&fixture){
 const std::array<std::string,4> names={"asa.u32le","na.u32le","boundary.u32le","fringe.u32le"};
 for(u32 i=0;i<4;i++)write_binary(dir/names[i],fixture.masks[i]);
 auto f=open_file(dir/"inputs.csv");f<<std::setprecision(17)
  <<"lane,initial_word,initial_q,jitter,j,k,north,axis,kinematic,blend_known,dr,dp,alpha,interval,profile,axis_known,frame_known,increment_known\n";
 for(std::size_t i=0;i<fixture.lanes.size();i++){
  const auto&l=fixture.lanes[i];const auto&a=l.angle;
  f<<i<<','<<l.initial_word<<','<<fixture.initial[i].q<<','<<l.jitter<<','<<l.j<<','<<l.k<<','<<l.north<<','<<l.axis<<','<<l.kinematic<<','<<l.blend_known
   <<','<<a.dr<<','<<a.dp<<','<<a.alpha<<','<<a.interval<<','<<a.profile<<','<<a.axis_known<<','<<a.frame_known<<','<<a.increment_known<<'\n';
 }
}
void core_header(std::ostream&f){
 f<<"epoch,lane,input_word,q_before,produced,asa,na,hits,output,q_after,blend,blend_known,beta_status,angle_status,beta,raw,principal,line";
 for(const char*name:{"R","W","P","S","F","V"})f<<','<<name<<"_state,"<<name<<"_reason,"<<name<<"_error";f<<'\n';
}
void core_row(std::ostream&f,u32 epoch,std::size_t index,const State&before,const Result&result){
 const auto&w=result.word;const auto&a=result.angle;
 f<<epoch<<','<<index<<','<<before.word<<','<<before.q<<','<<w.produced<<','<<w.asa<<','<<w.na<<','<<w.hits<<','<<w.output<<','<<w.q_after
  <<','<<w.blend<<','<<w.blend_known<<','<<a.beta_status<<','<<a.status<<',';
 if(a.beta_status==0)f<<a.beta;
 f<<',';if(a.status==0)f<<a.raw;f<<',';if(a.status==0)f<<a.principal;f<<',';if(a.status==0)f<<a.line;
 for(const auto&check:result.checks){f<<','<<check.state<<','<<check.reason<<',';if(check.state!=2)f<<check.error;}f<<'\n';
}
U::Tape encode(u32 alphabet,i64 origin,u64 count,const U::Cells&cells,u32 fill){
 U::Tape tape(alphabet,origin,count);
 std::fill(tape.words.begin(),tape.words.end(),fill);
 // Initialize all logical cells; unused high bits keep a nonzero sentinel.
 for(u64 i=0;i<count;i++)tape.set(origin+i64(i),0);
 for(const auto&cell:cells)if(cell.second)tape.set(cell.first,cell.second);
 return tape;
}
std::pair<i64,u64> extent(U::Machine machine,const U::Cells&cells,u32 budget){
 const i64 lo_limit=std::numeric_limits<i64>::min(),hi_limit=std::numeric_limits<i64>::max();
 i64 lo=machine.head<lo_limit+i64(budget)?lo_limit:machine.head-i64(budget);
 i64 hi=machine.head>hi_limit-i64(budget)?hi_limit:machine.head+i64(budget);
 for(const auto&cell:cells)if(cell.second){lo=std::min(lo,cell.first);hi=std::max(hi,cell.first);}
 const u64 count=u64(hi)-u64(lo)+1;
 if(!count)throw ResourceRefused("full signed tape domain cannot be represented by this finite allocation");
 return {lo,count};
}
u64 add_bytes(u64 a,u64 b){
 if(a>std::numeric_limits<u64>::max()-b)throw ResourceRefused("U allocation byte count overflow");return a+b;
}
u64 multiply_bytes(u64 a,u64 b){
 if(b&&a>std::numeric_limits<u64>::max()/b)throw ResourceRefused("U allocation byte count overflow");return a*b;
}
u64 preflight(const U::Program&program,u64 cells,u32 steps,const MemoryPolicy&policy){
 const u64 bits=multiply_bytes(cells,U::symbol_bits(program.alphabet));
 const u64 words=add_bytes(bits,31)/32;
 u64 bytes=multiply_bytes(words,sizeof(u32));
 bytes=add_bytes(bytes,multiply_bytes(program.rules.size(),sizeof(U::Rule)));
 bytes=add_bytes(bytes,multiply_bytes(program.halt.size(),sizeof(u32)));
 bytes=add_bytes(bytes,multiply_bytes(steps,sizeof(U::Step)));
 bytes=add_bytes(bytes,sizeof(MachineResult));
 const auto available=inspect(policy.device);
 if(policy.budget<policy.k1_payload||bytes>policy.budget-policy.k1_payload||
    available.free<policy.reserve||bytes>available.free-policy.reserve)
  throw ResourceRefused("U resource_refused before tape allocation: requested "+std::to_string(bytes)+
   " GPU bytes; combined budget "+std::to_string(policy.budget)+", currently free "+std::to_string(available.free)+
   ", reserve "+std::to_string(policy.reserve));
 return bytes;
}
struct Proposal {U::Tape tape;MachineResult result;std::vector<U::Step> trace;float milliseconds;u64 payload;};
Proposal propose(const U::Program&program,U::Machine before,const U::Tape&input,u32 budget,const MemoryPolicy&policy){
 const u64 bytes=preflight(program,input.cells,budget,policy);
 U::Tape candidate=input;
 Buffer<u32> tape(input.words.size()),halt(program.halt.size());
 Buffer<U::Rule> rules(program.rules.size());Buffer<U::Step> trace(budget);Buffer<MachineResult> result(1);
 tape.upload(input.words.data());halt.upload(program.halt.data());rules.upload(program.rules.data());
 U::PackedTapeView view=candidate.view();view.words=tape.get();
 Event start,stop;AO_CUDA(cudaEventRecord(start.get()));
 atomos_universal_propose<<<1,1>>>(rules.get(),halt.get(),program.states,view,before,budget,trace.get(),result.get());
 AO_CUDA(cudaGetLastError());AO_CUDA(cudaEventRecord(stop.get()));AO_CUDA(cudaEventSynchronize(stop.get()));
 float elapsed=0;AO_CUDA(cudaEventElapsedTime(&elapsed,start.get(),stop.get()));
 MachineResult value{};result.download(&value);tape.download(candidate.words.data());
 if(value.steps>budget)throw std::runtime_error("GPU transition count exceeds budget");
 std::vector<U::Step> records(value.steps);
 if(value.steps)AO_CUDA(cudaMemcpy(records.data(),trace.get(),records.size()*sizeof(U::Step),cudaMemcpyDeviceToHost));
 return {std::move(candidate),value,std::move(records),elapsed,bytes};
}
void verify(const U::Program&program,U::Machine before,const U::Cells&cells,u32 budget,
 const U::Tape&input,const Proposal&candidate,u32 fill,U::ReferenceRun&reference){
 reference=U::reference_run(program,before,cells,budget,input.origin,input.cells);
 if(!U::equal_machine(reference.machine,candidate.result.machine)||reference.stop!=candidate.result.stop||
    reference.trace.size()!=candidate.trace.size())throw std::runtime_error("U GPU/reference machine, status or transition count mismatch");
 for(std::size_t i=0;i<reference.trace.size();i++)if(!U::equal_step(reference.trace[i],candidate.trace[i]))
  throw std::runtime_error("U GPU/reference transition mismatch at step "+std::to_string(i));
 const auto expected=encode(program.alphabet,input.origin,input.cells,reference.cells,fill);
 if(candidate.tape.words!=expected.words)throw std::runtime_error("U GPU packed tape differs, including untouched cells/tail bits");
}
} // namespace engine_detail

int main(int argc,char**argv){fs::path staging;try{
 using namespace engine_detail;
 u32 rows=17,angles=257,epochs=3,seed=130,budget=64,device=0,tail_fill=0xa5a5a5a5u;
 u32 memory_mib=0,reserve_mib=512;
 double interval=1;Layout layout=Layout::linear;Producer producer=Producer::recurrent;
 std::string mode="recurrent",profile="mixed",program_path,outdir;bool fringe=true;
 bool have_origin=false,have_cells=false;i64 fixed_origin=0;u64 fixed_cells=0;
 for(int i=1;i<argc;i++){
  const std::string key=argv[i];
  if(key=="--help"){
   std::cout<<"Tom Klootwijk atomOS integrated word + programmable U engine\n"
    <<"--program FILE.atomos --out NEW_DIR --steps-per-epoch 0..65536 --epochs POSITIVE_UINT32\n"
    <<"--interval POSITIVE --rows N --angles N --layout linear|morton8 --seed N\n"
    <<"--mode provided|recurrent|shift-xor|shift-or --fringe on|off --profile source|directed|mixed\n"
    <<"--device N --memory-mib N --reserve-mib N --origin SIGNED --cells N --tape-tail-fill UINT32\n"
    <<"Default memory budget: min(85% currently free VRAM, free VRAM minus reserve).\n"
    <<"Tape grows between epochs by default. Paired origin/cells select a fixed finite window.\n"
    <<"Budget exhaustion is RUNNING; missing rules/range errors reject the combined epoch.\n";return 0;
  }
  if(++i>=argc)throw std::invalid_argument("missing option value");const std::string value=argv[i];
  if(key=="--program")program_path=value;else if(key=="--out")outdir=value;
  else if(key=="--steps-per-epoch"||key=="--budget")budget=number(value);
  else if(key=="--epochs")epochs=number(value);else if(key=="--rows")rows=number(value);
  else if(key=="--angles")angles=number(value);else if(key=="--seed")seed=number(value);
  else if(key=="--device")device=number(value);else if(key=="--interval")interval=positive(value);
  else if(key=="--memory-mib")memory_mib=number(value);else if(key=="--reserve-mib")reserve_mib=number(value);
  else if(key=="--origin"){fixed_origin=signed_number(value);have_origin=true;}
  else if(key=="--cells"){fixed_cells=wide_number(value);have_cells=true;}
  else if(key=="--tape-tail-fill")tail_fill=number(value);
  else if(key=="--layout"){
   if(value=="linear")layout=Layout::linear;else if(value=="morton8")layout=Layout::morton8;else throw std::invalid_argument("unknown layout");
  }else if(key=="--mode"){
   mode=value;if(value=="provided")producer=Producer::provided;else if(value=="recurrent")producer=Producer::recurrent;
   else if(value=="shift-xor")producer=Producer::shift_xor;else if(value=="shift-or")producer=Producer::shift_or;else throw std::invalid_argument("unknown word producer");
  }else if(key=="--fringe"){
   if(value!="on"&&value!="off")throw std::invalid_argument("fringe must be on or off");fringe=value=="on";
  }else if(key=="--profile")profile=value;else throw std::invalid_argument("unknown option "+key);
 }
 if(program_path.empty()||outdir.empty())throw std::invalid_argument("program and new output directory are required");
 if(!epochs||budget>MAX_STEPS||device>1024||have_origin!=have_cells||
    (have_cells&&!fixed_cells))throw std::invalid_argument("epoch/budget/device/tape range");
 if(!std::isfinite(interval*epochs))throw std::invalid_argument("global time would become nonfinite");
 if(fs::exists(outdir))throw std::invalid_argument("output directory must not already exist");
 // Resolve resource limits before the parser materializes its dense table.
 // Device inspection creates no candidate kernel or state transition.
 const auto initial_device=inspect(int(device));const u64 reserve=u64(reserve_mib)<<20;
 if(initial_device.free<=reserve)throw ResourceRefused("available VRAM does not exceed requested reserve");
 const u64 memory_budget=memory_mib?u64(memory_mib)<<20:
  std::min(u64(initial_device.free)-reserve,(u64(initial_device.free)/100)*85);
 if(memory_budget>u64(initial_device.free)-reserve)
  throw ResourceRefused("requested memory budget exceeds currently free VRAM after reserve");
 const u64 host_available=available_host_memory();
 const u64 table_budget=host_available?std::min(memory_budget,(host_available/100)*85):memory_budget;
 U::Program program;
 try{program=U::load_program(program_path,table_budget);}
 catch(const U::TableResourceRefused&e){throw ResourceRefused(e.what());}
 if(have_cells){
  if(!U::valid_extent(fixed_origin,fixed_cells))throw std::invalid_argument("fixed tape extent exceeds signed address domain");
  for(const auto&cell:program.initial_cells)
   if(cell.first<fixed_origin||u64(cell.first)-u64(fixed_origin)>=fixed_cells)
    throw std::invalid_argument("explicit initial cell is outside the supplied fixed tape window");
 }
 const Shape s=shape(rows,angles);
 Fixture fixture(Config{s,layout,producer,u32(fringe)},seed,profile);
 const MemoryPolicy memory{memory_budget,reserve,payload(s),int(device)};
 auto backend=make_cuda_backend(fixture,int(device),true,memory_budget,reserve,true,true,128);
 auto core_state=fixture.initial;U::Machine machine{program.initial_state,program.initial_head};
 U::Cells cells=program.initial_cells;for(auto it=cells.begin();it!=cells.end();)if(!it->second)it=cells.erase(it);else++it;
 staging=fs::path(outdir+".partial_"+std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
 if(!fs::create_directories(staging))throw std::runtime_error("staging directory already exists");
 fs::copy_file(program_path,staging/"program.atomos");inputs(staging,fixture);
 auto core_trace=open_file(staging/"trace.csv");core_trace<<std::setprecision(17);core_header(core_trace);
 auto u_trace=open_file(staging/"u_trace.csv");
 u_trace<<"epoch,step,control_before,head_before,read,write,move,control_after,head_after\n";
 auto ledger=open_file(staging/"epochs.jsonl");u32 attempted=0,committed=0;
 bool rejected=false;double time=0;U::Stop last_stop=U::Stop::running;
 u64 verified_steps=0,committed_steps=0,verified_lanes=0;u64 max_u_payload=0;
 for(u32 epoch=0;epoch<epochs;epoch++){
  const auto range=have_cells?std::make_pair(fixed_origin,fixed_cells):extent(machine,cells,budget);
  preflight(program,range.second,budget,memory); // before allocating any host tape
  U::Tape before_tape=encode(program.alphabet,range.first,range.second,cells,tail_fill);
  const auto before_machine=machine;const auto before_cells=cells;const auto before_core=core_state;
  auto proposed_core=backend->propose(core_state);
  auto candidate=propose(program,machine,before_tape,budget,memory);
  U::ReferenceRun reference{};verify(program,machine,cells,budget,before_tape,candidate,tail_fill,reference);
  verify_results(fixture,core_state,proposed_core);
  std::vector<State> next_core;next_core.reserve(proposed_core.size());
  for(const auto&value:proposed_core)next_core.push_back({value.word.output,value.word.q_after});
  const bool accepted=candidate.result.stop==U::Stop::running||candidate.result.stop==U::Stop::halted;
  const double before_time=time;
  if(accepted&&!std::isfinite(time+interval))throw std::runtime_error("next committed global time would be nonfinite");
  if(accepted){
   // All allocations and checks precede these no-throw state swaps/assignments.
   // Neither projection becomes committed when the other projection rejects.
   core_state.swap(next_core);cells.swap(reference.cells);machine=candidate.result.machine;
   time+=interval;committed++;committed_steps+=candidate.result.steps;
  }else rejected=true;
  last_stop=candidate.result.stop;verified_steps+=candidate.result.steps;verified_lanes+=proposed_core.size();
  max_u_payload=std::max(max_u_payload,candidate.payload);
  const auto candidate_cells=candidate.tape.nonzero_cells();
  const auto committed_tape=accepted?candidate.tape:before_tape;
  const std::string stem="epoch_"+std::to_string(epoch);
  cells_file(staging/(stem+"_u_before.csv"),before_cells);
  cells_file(staging/(stem+"_u_candidate.csv"),candidate_cells);
  cells_file(staging/(stem+"_u_committed.csv"),cells);
  write_binary(staging/(stem+"_u_before.u32le"),before_tape.words);
  write_binary(staging/(stem+"_u_candidate.u32le"),candidate.tape.words);
  write_binary(staging/(stem+"_u_committed.u32le"),committed_tape.words);
  state_file(staging/(stem+"_core_before.csv"),before_core);
  std::vector<State> candidate_core;candidate_core.reserve(proposed_core.size());
  for(const auto&value:proposed_core)candidate_core.push_back({value.word.output,value.word.q_after});
  state_file(staging/(stem+"_core_candidate.csv"),candidate_core);
  state_file(staging/(stem+"_core_committed.csv"),core_state);
  for(std::size_t i=0;i<proposed_core.size();i++)core_row(core_trace,epoch,i,before_core[i],proposed_core[i]);
  for(std::size_t i=0;i<candidate.trace.size();i++){
   const auto&t=candidate.trace[i];u_trace<<epoch<<','<<i<<','<<t.control_before<<','<<t.head_before<<','<<t.read<<','<<t.write<<','<<t.move<<','<<t.control_after<<','<<t.head_after<<'\n';
  }
  std::ostringstream record;record<<std::setprecision(17)<<"{\"epoch\":"<<epoch<<",\"time_before\":"<<before_time<<",\"time_after\":"<<time
   <<",\"accepted\":"<<(accepted?"true":"false")<<",\"status\":"<<json_string(U::stop_name(candidate.result.stop))
   <<",\"steps\":"<<candidate.result.steps<<",\"origin\":"<<before_tape.origin<<",\"cells\":"<<before_tape.cells
   <<",\"packed_bits\":"<<before_tape.bits<<",\"packed_words\":"<<before_tape.words.size()<<",\"tail_fill\":"<<tail_fill
   <<",\"u_before\":"<<machine_json(before_machine)<<",\"u_candidate\":"<<machine_json(candidate.result.machine)<<",\"u_committed\":"<<machine_json(machine)
   <<",\"candidate_verification\":\"passed\",\"packed_tape_verification\":\"passed\",\"k1_verification\":\"passed\""
   <<",\"k1_ms\":"<<backend->last_ms()<<",\"u_ms\":"<<candidate.milliseconds<<",\"u_payload_bytes\":"<<candidate.payload<<'}';
  ledger<<record.str()<<'\n';ledger.flush();attempted++;
  if(rejected){write_text(staging/"rejection.json",record.str()+"\n");break;}
 }
 core_trace.close();u_trace.close();ledger.close();
 cells_file(staging/"final_tape.csv",cells);state_file(staging/"final_state.csv",core_state);
 write_text(staging/"machine_state.json",machine_json(machine)+"\n");
 std::ostringstream summary;summary<<std::setprecision(17)
  <<"{\"schema\":\"atomOS-word-U-engine-v1\",\"author\":\"Tom Klootwijk\",\"status\":"<<json_string(rejected?"rejected":"passed")
  <<",\"backend\":\"cuda\",\"device\":"<<backend->device_json()<<",\"execution_profile\":\"word-plus-U-v1\""
  <<",\"geometry_profile\":\"disabled\",\"ledger_profile\":\"verified-local-epoch-records-v1\",\"cache_residency\":\"not_measured_for_combined_profile\""
  <<",\"program\":\"program.atomos\",\"states\":"<<program.states<<",\"alphabet\":"<<program.alphabet
  <<",\"requested_epochs\":"<<epochs<<",\"attempted_epochs\":"<<attempted<<",\"committed_epochs\":"<<committed
  <<",\"steps_per_epoch\":"<<budget<<",\"interval\":"<<interval<<",\"time\":"<<time<<",\"tape_growth\":"<<json_string(have_cells?"fixed_explicit_window":"between_epochs_to_cover_prefix")
  <<",\"memory_budget_bytes\":"<<memory_budget<<",\"reserve_bytes\":"<<reserve<<",\"maximum_steps_per_launch\":"<<MAX_STEPS
  <<",\"requested_memory_mib\":"<<memory_mib<<",\"requested_reserve_mib\":"<<reserve_mib
  <<",\"initial_free_vram_bytes\":"<<initial_device.free<<",\"initial_available_host_bytes\":"<<host_available<<",\"host_table_budget_bytes\":"<<table_budget
  <<",\"tail_fill\":"<<tail_fill<<",\"u_status\":"<<json_string(U::stop_name(last_stop))
  <<",\"verified_u_steps\":"<<verified_steps<<",\"committed_u_steps\":"<<committed_steps<<",\"verified_k1_lanes\":"<<verified_lanes
  <<",\"k1_payload_bytes\":"<<payload(s)<<",\"maximum_u_payload_bytes\":"<<max_u_payload
  <<",\"rows\":"<<rows<<",\"angles\":"<<angles<<",\"words\":"<<s.words<<",\"padded_rows\":"<<s.padded_rows<<",\"padded_words\":"<<s.padded_words
  <<",\"layout\":"<<json_string(layout==Layout::linear?"linear":"morton8")<<",\"mode\":"<<json_string(mode)<<",\"profile\":"<<json_string(profile)
  <<",\"fringe\":"<<(fringe?"true":"false")<<",\"seed\":"<<seed<<",\"read\":\"texture-packed\""
  <<",\"u_initial\":"<<machine_json({program.initial_state,program.initial_head})<<",\"u_final\":"<<machine_json(machine)
  <<",\"candidate_verification\":\"passed\",\"timing_scope\":\"separate CUDA kernel events; host transfers, verification and file output excluded\"";
 auto engine_file=open_file(staging/"engine.json");engine_file<<summary.str()<<",\"epochs\":[";
 std::ifstream ledger_input(staging/"epochs.jsonl");std::string record;u32 records_written=0;
 while(std::getline(ledger_input,record))engine_file<<(records_written++?",":"")<<record;
 if(ledger_input.bad()||records_written!=attempted)throw std::runtime_error("epoch ledger publication count mismatch");
 engine_file<<"]}\n";engine_file.close();ledger_input.close();
 write_text(staging/(rejected?"PREFIX_VERIFIED":"COMMITTED"),rejected?
  "The attempted epoch was rejected; exported committed state is the verified accepted prefix.\n":
  "All requested combined word/U epochs were independently verified before commitment.\n");
 if(fs::exists(outdir))throw std::runtime_error("output path appeared during run; refusing replacement");
 fs::rename(staging,outdir);staging.clear();
 std::cout<<summary.str()<<",\"engine_file\":"<<json_string((fs::path(outdir)/"engine.json").string())<<"}\n";
 return rejected?2:0;
}catch(const engine_detail::ResourceRefused&e){
 std::cerr<<"atomOS engine resource_refused: "<<e.what()<<'\n';
 std::cout<<"{\"status\":\"resource_refused\",\"failed_attempt_committed\":false,\"reason\":"<<atomos::json_string(e.what())<<"}\n";
 if(!staging.empty()){
  try{engine_detail::write_text(staging/"resource_status.json","{\"status\":\"resource_refused\",\"reason\":"+atomos::json_string(e.what())+"}\n");}catch(...){}
  std::cerr<<"Verified prefix records, if any, retained at "<<staging.string()<<'\n';
 }
 return 3;
}catch(const std::exception&e){
 std::cerr<<"atomOS engine error: "<<e.what()<<'\n';
 if(!staging.empty())std::cerr<<"Uncommitted diagnostic files retained at "<<staging.string()<<'\n';return 1;
}}
