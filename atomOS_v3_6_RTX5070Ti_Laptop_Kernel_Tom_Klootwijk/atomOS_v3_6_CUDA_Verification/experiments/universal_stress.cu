// Hardware-capacity exercise for the Tom Klootwijk atomOS U interpreter.
// A finite, independently checked collection of machine prefixes, not a proof
// of all programs or a claim of physically unbounded tape.
#include <cuda_runtime.h>
#include "atomos/host.hpp"
#include "atomos/universal.hpp"
#include <algorithm>
#include <chrono>
#include <iomanip>
#include <iostream>
#include <memory>
#include <set>
using namespace atomos;
using namespace atomos::universal;
namespace {
void check(cudaError_t status,const char*operation){if(status!=cudaSuccess)throw std::runtime_error(std::string(operation)+": "+cudaGetErrorString(status));}
#define U_CUDA(operation) check((operation),#operation)
template<class T>struct DeviceBuffer {
 T*data=nullptr;u64 count=0;
 explicit DeviceBuffer(u64 n):count(n){if(n>SIZE_MAX/sizeof(T))throw std::length_error("device byte count overflow");if(n)U_CUDA(cudaMalloc(reinterpret_cast<void**>(&data),std::size_t(n*sizeof(T))));}
 ~DeviceBuffer(){if(data)cudaFree(data);}DeviceBuffer(const DeviceBuffer&)=delete;
};
struct Event {cudaEvent_t value{};Event(){U_CUDA(cudaEventCreate(&value));}~Event(){cudaEventDestroy(value);}};
struct DeviceMachine {u32 control;Stop stop;i64 head;u64 steps;};
struct SeedCell {i64 address;u32 symbol;};
struct StressTape {u32*words;u64 machines,cells,words_per_machine;i64 origin;u32 bits,alphabet;};
// Word-major storage: equal word positions from neighboring machines are
// adjacent. Each thread owns its column, including both sides of a split field.
__device__ bool read_symbol(const StressTape&t,u64 machine,i64 position,u32&symbol){
 if(position<t.origin||u64(position)-u64(t.origin)>=t.cells)return false;
 const u64 offset=(u64(position)-u64(t.origin))*t.bits,word=offset/32;
 const u32 shift=u32(offset%32);u32 value=t.words[word*t.machines+machine]>>shift;
 if(shift+t.bits>32)value|=(t.words[(word+1)*t.machines+machine]&symbol_mask(shift+t.bits-32))<<(32-shift);
 value&=symbol_mask(t.bits);if(value>=t.alphabet)return false;symbol=value;return true;
}
__device__ void write_symbol(const StressTape&t,u64 machine,i64 position,u32 symbol){
 const u64 offset=(u64(position)-u64(t.origin))*t.bits,word=offset/32;
 const u32 shift=u32(offset%32),mask=symbol_mask(t.bits)<<shift;
 u32&low=t.words[word*t.machines+machine];low=(low&~mask)|((symbol<<shift)&mask);
 if(shift+t.bits>32){const u32 high_mask=symbol_mask(shift+t.bits-32);u32&high=t.words[(word+1)*t.machines+machine];high=(high&~high_mask)|((symbol>>(32-shift))&high_mask);}
}
__global__ void initialize_machines(StressTape tape,DeviceMachine*machines,u32 initial_control,i64 initial_head,u32 groups,const SeedCell*seed,u64 seed_count){
 const u64 machine=u64(blockIdx.x)*blockDim.x+threadIdx.x;if(machine>=tape.machines)return;
 machines[machine]={groups>1?u32(machine%groups):initial_control,Stop::running,initial_head,0};
 for(u64 i=0;i<seed_count;++i)write_symbol(tape,machine,seed[i].address,seed[i].symbol);
}
__global__ void run_machines(StressTape tape,DeviceMachine*machines,const Rule*rules,const u32*halt,u32 states,u32 steps_per_launch){
 const u64 index=u64(blockIdx.x)*blockDim.x+threadIdx.x;if(index>=tape.machines)return;
 DeviceMachine machine=machines[index];
 if(machine.stop!=Stop::running)return;
 for(u32 step=0;step<steps_per_launch;++step){
  if(machine.control>=states){machine.stop=Stop::invalid;break;}
  if(machine.head<tape.origin||u64(machine.head)-u64(tape.origin)>=tape.cells){machine.stop=Stop::tape_range;break;}
  if(halt[machine.control]){machine.stop=Stop::halted;break;}
  u32 symbol=0;if(!read_symbol(tape,index,machine.head,symbol)){machine.stop=Stop::invalid;break;}
  const Rule rule=rules[u64(machine.control)*tape.alphabet+symbol];
  if(!rule.defined){machine.stop=Stop::missing_rule;break;}
  if(rule.defined!=1||rule.next>=states||rule.write>=tape.alphabet||rule.move< -1||rule.move>1){machine.stop=Stop::invalid;break;}
  if((rule.move<0&&machine.head==INT64_MIN)||(rule.move>0&&machine.head==INT64_MAX)){machine.stop=Stop::tape_range;break;}
  const i64 next_head=machine.head+rule.move;
  if(next_head<tape.origin||u64(next_head)-u64(tape.origin)>=tape.cells){machine.stop=Stop::tape_range;break;}
  write_symbol(tape,index,machine.head,rule.write);machine.control=rule.next;machine.head=next_head;++machine.steps;
  if(halt[machine.control]){machine.stop=Stop::halted;break;}
 }
 machines[index]=machine;
}
struct Options {
 int device=0;double fraction=.85;u64 reserve=512ull<<20,machines=0;u32 steps=256,rounds=4,alphabet=5,states=7;
 std::string program,out;
};
u64 unsigned_integer(const std::string&text){return detail::integer<u64>(text);}
u32 unsigned32(const std::string&text){return detail::integer<u32>(text);}
Options options(int argc,char**argv){
 Options o;
 for(int i=1;i<argc;++i){const std::string key=argv[i];
  if(key=="--help"){std::cout<<"atomos_universal_stress [--device N] [--memory-fraction 0.85] [--reserve-mib 512] [--machines N] [--steps-per-launch 256] [--rounds 4] [--alphabet 3|5] [--states 7] [--program FILE.atomos] [--out FILE.json]\n";std::exit(0);}
  if(i+1==argc)throw std::invalid_argument("missing value for "+key);const std::string value=argv[++i];
  if(key=="--device")o.device=detail::integer<int>(value);
  else if(key=="--memory-fraction"){std::size_t end=0;o.fraction=std::stod(value,&end);if(end!=value.size())throw std::invalid_argument("invalid memory fraction");}
  else if(key=="--reserve-mib"){const u64 mib=unsigned_integer(value);if(mib>UINT64_MAX/(1ull<<20))throw std::invalid_argument("reserve overflow");o.reserve=mib<<20;}
  else if(key=="--machines")o.machines=unsigned_integer(value);
  else if(key=="--steps-per-launch")o.steps=unsigned32(value);
  else if(key=="--rounds")o.rounds=unsigned32(value);
  else if(key=="--alphabet")o.alphabet=unsigned32(value);
  else if(key=="--states")o.states=unsigned32(value);
  else if(key=="--program")o.program=value;
  else if(key=="--out")o.out=value;
  else throw std::invalid_argument("unknown option "+key);
 }
 if(!std::isfinite(o.fraction)||o.fraction<=0||o.fraction>=1)throw std::invalid_argument("memory fraction must be between zero and one");
 if(!o.steps||!o.rounds)throw std::invalid_argument("steps and rounds must be positive");
 if(!o.out.empty()&&std::filesystem::exists(o.out))throw std::invalid_argument("output already exists");return o;
}
Program default_program(u32 states,u32 alphabet,u64 max_table_bytes){
 if(!states||alphabet<2)throw std::invalid_argument("default write/walk program needs positive states and at least two symbols");
 checked_table_bytes(states,alphabet,max_table_bytes);
 Program p;p.states=states;p.alphabet=alphabet;p.halt.assign(states,0);
 const u64 count=u64(states)*alphabet;if(count>p.rules.max_size())throw std::length_error("rule table too large");p.rules.resize(std::size_t(count));
 for(u32 state=0;state<states;++state)for(u32 read=0;read<alphabet;++read)p.rules[std::size_t(u64(state)*alphabet+read)]={(state+1)%states,1+state%(alphabet-1),1,1};
 p.validate();return p;
}
struct GroupReference {Machine machine;Cells cells;Stop stop=Stop::running;u64 steps=0;std::set<i64> touched;};
// Independent bit-by-bit reference packing, without CUDA/read_symbol or the
// core packed helper. Maps retain only words with nonzero expected bits.
std::map<u64,u32> expected_words(const Cells&cells,i64 origin,u32 bits){
 std::map<u64,u32> result;
 for(const auto&cell:cells){const u64 offset=(u64(cell.first)-u64(origin))*bits;for(u32 bit=0;bit<bits;++bit)if((cell.second>>bit)&1u){const u64 address=offset+bit;result[address/32]|=1u<<u32(address%32);}}
 return result;
}
}
int main(int argc,char**argv){try{
 const auto wall_start=std::chrono::steady_clock::now();const Options o=options(argc,argv);
 U_CUDA(cudaSetDevice(o.device));U_CUDA(cudaFree(nullptr));cudaDeviceProp prop{};U_CUDA(cudaGetDeviceProperties(&prop,o.device));
 std::size_t free_before=0,total=0;U_CUDA(cudaMemGetInfo(&free_before,&total));
 if(o.reserve>=free_before)throw std::runtime_error("free VRAM is below requested reserve");
 const u64 budget=std::min(u64(double(free_before)*o.fraction),u64(free_before)-o.reserve);
 const u64 machines=o.machines?o.machines:u64(prop.multiProcessorCount)*prop.maxThreadsPerMultiProcessor;
 if(!machines||machines>u64(prop.maxGridSize[0])*256)throw std::invalid_argument("machine count exceeds one-dimensional launch capacity");
 Program program=o.program.empty()?default_program(o.states,o.alphabet,budget):load_program(o.program,budget);
 const u32 bits=symbol_bits(program.alphabet),groups=o.program.empty()?program.states:1;
 const u64 table_bytes=u64(program.rules.size())*sizeof(Rule)+u64(program.halt.size())*sizeof(u32);
 if(machines>UINT64_MAX/sizeof(DeviceMachine))throw std::length_error("machine state byte overflow");
 const u64 state_bytes=machines*sizeof(DeviceMachine),seed_bytes=u64(program.initial_cells.size())*sizeof(SeedCell);
 if(table_bytes>UINT64_MAX-state_bytes||table_bytes+state_bytes>UINT64_MAX-seed_bytes)throw std::length_error("device overhead byte overflow");
 const u64 overhead=table_bytes+state_bytes+seed_bytes;
 if(overhead>=budget||machines>(budget-overhead)/sizeof(u32))throw std::runtime_error("memory budget cannot hold machine state and one packed word per tape");
 u64 words_per_machine=(budget-overhead)/(machines*sizeof(u32));
 if(words_per_machine>UINT64_MAX/32)throw std::length_error("tape bit count overflow");
 // Whole words are physical allocation units; the final partial symbol is
 // excluded and its unused bits must remain zero during full-allocation audit.
 u64 cells=(words_per_machine*32)/bits;
 if(!cells||cells>u64(INT64_MAX))throw std::length_error("tape allocation cannot be represented by signed addresses");
 const u64 requested_words_per_machine=words_per_machine;
 DeviceBuffer<Rule> rules(program.rules.size());DeviceBuffer<u32> halt(program.halt.size());DeviceBuffer<DeviceMachine> state(machines);DeviceBuffer<SeedCell> seed(program.initial_cells.size());
 U_CUDA(cudaMemcpy(rules.data,program.rules.data(),std::size_t(u64(program.rules.size())*sizeof(Rule)),cudaMemcpyHostToDevice));
 U_CUDA(cudaMemcpy(halt.data,program.halt.data(),std::size_t(u64(program.halt.size())*sizeof(u32)),cudaMemcpyHostToDevice));
 std::vector<SeedCell> seeds;for(const auto&entry:program.initial_cells)seeds.push_back({entry.first,entry.second});
 if(!seeds.empty())U_CUDA(cudaMemcpy(seed.data,seeds.data(),std::size_t(seed_bytes),cudaMemcpyHostToDevice));
 u32 allocation_attempts=0;u32*tape_ptr=nullptr;
 while(words_per_machine){
  ++allocation_attempts;const auto status=cudaMalloc(reinterpret_cast<void**>(&tape_ptr),std::size_t(words_per_machine*machines*sizeof(u32)));
  if(status==cudaSuccess)break;
  if(status!=cudaErrorMemoryAllocation)check(status,"allocate packed machine tapes");
  cudaGetLastError();const u64 smaller=words_per_machine*9/10;words_per_machine=smaller<words_per_machine?smaller:words_per_machine-1;
 }
 if(!tape_ptr)throw std::runtime_error("could not allocate one packed word per machine");
 const auto free_tape=[](u32*pointer){if(pointer)cudaFree(pointer);};std::unique_ptr<u32,decltype(free_tape)> tape_owner(tape_ptr,free_tape);
 cells=(words_per_machine*32)/bits;const u64 tape_words=words_per_machine*machines,tape_bytes=tape_words*sizeof(u32);
 const u64 total_step_budget=u64(o.steps)*o.rounds;
 i64 origin=0;
 if(o.program.empty()){
  origin=-i64(std::min(cells/2,total_step_budget/2));program.initial_head=origin;
 }else{
  const u64 left=std::min(cells/2,u64(program.initial_head)-u64(INT64_MIN));origin=program.initial_head-i64(left);
  if(!valid_extent(origin,cells))origin=INT64_MAX-i64(cells-1);
 }
 if(!valid_extent(origin,cells)||program.initial_head<origin||u64(program.initial_head)-u64(origin)>=cells)throw std::runtime_error("initial head outside allocated tape extent");
 for(const auto&cell:program.initial_cells)if(cell.first<origin||u64(cell.first)-u64(origin)>=cells)throw std::runtime_error("initial cell outside allocated tape extent");
 StressTape tape{tape_ptr,machines,cells,words_per_machine,origin,bits,program.alphabet};
 U_CUDA(cudaMemset(tape_ptr,0,std::size_t(tape_bytes)));
 const u32 block=256,grid=u32((machines+block-1)/block);
 initialize_machines<<<grid,block>>>(tape,state.data,program.initial_state,program.initial_head,groups,seed.data,seeds.size());U_CUDA(cudaGetLastError());U_CUDA(cudaDeviceSynchronize());
 std::size_t free_after=0,total_after=0;U_CUDA(cudaMemGetInfo(&free_after,&total_after));
 cudaFuncAttributes attributes{};U_CUDA(cudaFuncGetAttributes(&attributes,run_machines));int active_blocks=0;U_CUDA(cudaOccupancyMaxActiveBlocksPerMultiprocessor(&active_blocks,run_machines,block,0));
 std::vector<GroupReference> references(groups);
 for(u32 group=0;group<groups;++group)references[group]={{groups>1?group:program.initial_state,program.initial_head},normalized_cells(program.initial_cells),Stop::running,0};
 if(machines>std::vector<DeviceMachine>().max_size())throw std::length_error("host machine metadata exceeds vector capacity");
 std::vector<DeviceMachine> actual(std::size_t(machines),DeviceMachine{});std::vector<double> times;std::vector<u64> executed_each_round;
 Event start,stop;u64 previous_steps=0,machine_comparisons=0;
 for(u32 round=0;round<o.rounds;++round){
  U_CUDA(cudaEventRecord(start.value));run_machines<<<grid,block>>>(tape,state.data,rules.data,halt.data,program.states,o.steps);U_CUDA(cudaGetLastError());U_CUDA(cudaEventRecord(stop.value));U_CUDA(cudaEventSynchronize(stop.value));
  float milliseconds=0;U_CUDA(cudaEventElapsedTime(&milliseconds,start.value,stop.value));times.push_back(milliseconds);
  U_CUDA(cudaMemcpy(actual.data(),state.data,std::size_t(state_bytes),cudaMemcpyDeviceToHost));
  for(auto&reference:references)if(reference.stop==Stop::running){
   auto expected=reference_run(program,reference.machine,reference.cells,o.steps,origin,cells);
   for(const auto&transition:expected.trace)reference.touched.insert(transition.head_before);
   reference.machine=expected.machine;reference.cells=std::move(expected.cells);reference.stop=expected.stop;reference.steps+=expected.trace.size();
  }
  u64 cumulative=0;
  for(u64 machine=0;machine<machines;++machine){const auto&expected=references[std::size_t(machine%groups)];const auto&value=actual[std::size_t(machine)];
   if(value.control!=expected.machine.control||value.head!=expected.machine.head||value.stop!=expected.stop||value.steps!=expected.steps)throw std::runtime_error("GPU machine metadata differs from map reference at round "+std::to_string(round)+", machine "+std::to_string(machine));
   if(value.steps>UINT64_MAX-cumulative)throw std::overflow_error("aggregate transition count overflow");cumulative+=value.steps;++machine_comparisons;
  }
  executed_each_round.push_back(cumulative-previous_steps);previous_steps=cumulative;
  std::cerr<<"verified launch "<<(round+1)<<'/'<<o.rounds<<": "<<machines<<" machine states, "<<executed_each_round.back()<<" transitions, "<<milliseconds<<" ms\n";
 }
 const auto verify_start=std::chrono::steady_clock::now();std::vector<std::map<u64,u32>> expected(groups);
 for(u32 group=0;group<groups;++group)expected[group]=expected_words(references[group].cells,origin,bits);
 const u64 buffer_words=std::min(tape_words,(64ull<<20)/sizeof(u32));std::vector<u32> chunk(std::size_t(buffer_words),0),pattern(groups,0);u64 words_verified=0,current_word=UINT64_MAX;
 for(u64 base=0;base<tape_words;base+=buffer_words){
  const u64 count=std::min(buffer_words,tape_words-base);U_CUDA(cudaMemcpy(chunk.data(),tape_ptr+base,std::size_t(count*sizeof(u32)),cudaMemcpyDeviceToHost));
  u64 offset=0;
  while(offset<count){const u64 word=(base+offset)/machines,first_machine=(base+offset)%machines;
   if(word!=current_word){current_word=word;for(u32 group=0;group<groups;++group){const auto found=expected[group].find(word);pattern[group]=found==expected[group].end()?0:found->second;}}
   const u64 span=std::min(count-offset,machines-first_machine);
   for(u64 i=0;i<span;++i)if(chunk[std::size_t(offset+i)]!=pattern[std::size_t((first_machine+i)%groups)])throw std::runtime_error("GPU packed tape differs at word "+std::to_string(word)+", machine "+std::to_string(first_machine+i));
   words_verified+=span;offset+=span;
  }
 }
 const double verify_seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-verify_start).count();
 u64 touched_cells=0,touched_words=0;
 for(u32 group=0;group<groups;++group){
  const u64 group_machines=machines/groups+(group<machines%groups?1:0);std::set<u64> positions;
  for(i64 position:references[group].touched){const u64 offset=(u64(position)-u64(origin))*bits;positions.insert(offset/32);positions.insert((offset+bits-1)/32);}
  touched_cells+=group_machines*references[group].touched.size();touched_words+=group_machines*positions.size();
 }
 u64 status_counts[5]={};for(const auto&value:actual)++status_counts[u32(value.stop)];
 double kernel_ms=0;for(double value:times)kernel_ms+=value;
 const double wall_seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-wall_start).count();
 std::ostringstream json;json<<std::setprecision(17)<<"{\n\"schema\":\"atomos-universal-stress-v1\",\n\"concept_author\":\"Tom Klootwijk\",\n\"status\":\"passed\",\n\"scope\":\"finite GPU prefixes; generic table interpreter; all physical tape words verified; no unbounded-hardware claim\",\n"
  <<"\"device\":{\"name\":"<<json_string(prop.name)<<",\"ordinal\":"<<o.device<<",\"cc_major\":"<<prop.major<<",\"cc_minor\":"<<prop.minor<<",\"multiprocessors\":"<<prop.multiProcessorCount<<",\"max_threads_per_sm\":"<<prop.maxThreadsPerMultiProcessor<<",\"total_bytes\":"<<total<<",\"free_before_bytes\":"<<free_before<<",\"free_after_allocation_bytes\":"<<free_after<<"},\n"
  <<"\"allocation\":{\"memory_fraction\":"<<o.fraction<<",\"reserve_bytes\":"<<o.reserve<<",\"budget_bytes\":"<<budget<<",\"actual_allocated_bytes\":"<<tape_bytes+overhead<<",\"tape_bytes\":"<<tape_bytes<<",\"state_bytes\":"<<state_bytes<<",\"rule_and_halt_bytes\":"<<table_bytes<<",\"seed_bytes\":"<<seed_bytes<<",\"allocation_attempts\":"<<allocation_attempts<<",\"requested_words_per_machine\":"<<requested_words_per_machine<<",\"actual_words_per_machine\":"<<words_per_machine<<",\"host_download_buffer_bytes\":"<<buffer_words*sizeof(u32)<<"},\n"
  <<"\"program\":{\"source\":"<<json_string(o.program.empty()?"generated dense write/walk control-cycle table":o.program)<<",\"states\":"<<program.states<<",\"alphabet\":"<<program.alphabet<<",\"bits_per_symbol\":"<<bits<<",\"initial_head\":"<<program.initial_head<<",\"initial_control_groups\":"<<groups<<",\"rules\":[";
 for(std::size_t i=0;i<program.rules.size();++i){if(i)json<<',';const auto&rule=program.rules[i];json<<'['<<i/program.alphabet<<','<<i%program.alphabet<<','<<rule.next<<','<<rule.write<<','<<rule.move<<','<<rule.defined<<']';}
 json<<"],\"halt\":[";for(std::size_t i=0;i<program.halt.size();++i){if(i)json<<',';json<<program.halt[i];}json<<"]},\n"
  <<"\"execution\":{\"machines\":"<<machines<<",\"cells_per_machine\":"<<cells<<",\"origin\":"<<origin<<",\"layout\":\"coalesced word-major machine columns\",\"rounds\":"<<o.rounds<<",\"steps_per_launch\":"<<o.steps<<",\"executed_transitions\":"<<previous_steps<<",\"kernel_ms\":"<<kernel_ms<<",\"transitions_per_second\":"<<(kernel_ms>0?double(previous_steps)*1000/kernel_ms:0)<<",\"block_size\":"<<block<<",\"registers_per_thread\":"<<attributes.numRegs<<",\"local_bytes_per_thread\":"<<attributes.localSizeBytes<<",\"active_blocks_per_sm_limit\":"<<active_blocks<<",\"launches\":[";
 for(std::size_t i=0;i<times.size();++i){if(i)json<<',';json<<"{\"kernel_ms\":"<<times[i]<<",\"executed_transitions\":"<<executed_each_round[i]<<",\"machine_states_verified\":"<<machines<<'}';}json<<"]},\n"
  <<"\"verification\":{\"reference\":\"independent sparse-map interpreter and single-bit host packer\",\"machine_comparisons\":"<<machine_comparisons<<",\"packed_words_verified\":"<<words_verified<<",\"packed_bytes_verified\":"<<words_verified*sizeof(u32)<<",\"distinct_transition_cells\":"<<touched_cells<<",\"distinct_transition_words\":"<<touched_words<<",\"program_touched_tape_bytes\":"<<touched_words*sizeof(u32)<<",\"all_written_symbols\":true,\"untouched_blanks\":true,\"unused_padding_bits\":true,\"full_tape_check_seconds\":"<<verify_seconds<<",\"final_stop_counts\":{\"running\":"<<status_counts[0]<<",\"halted\":"<<status_counts[1]<<",\"missing_rule\":"<<status_counts[2]<<",\"tape_range\":"<<status_counts[3]<<",\"invalid\":"<<status_counts[4]<<"},\"final_control_groups\":[";
 for(u32 group=0;group<groups;++group){if(group)json<<',';const auto&r=references[group];json<<"{\"group\":"<<group<<",\"control\":"<<r.machine.control<<",\"head\":"<<r.machine.head<<",\"steps\":"<<r.steps<<",\"stop\":"<<json_string(stop_name(r.stop))<<'}';}
 json<<"]},\n\"wall_seconds\":"<<wall_seconds<<"\n}\n";
 if(!o.out.empty()){const auto path=std::filesystem::path(o.out);if(!path.parent_path().empty())std::filesystem::create_directories(path.parent_path());std::ofstream output(path,std::ios::binary);if(!output)throw std::runtime_error("cannot create output JSON");output<<json.str();output.flush();if(!output)throw std::runtime_error("cannot write output JSON");}
 std::cout<<json.str();return 0;
}catch(const std::exception&e){std::cerr<<"universal stress failed: "<<e.what()<<'\n';return 1;}}
