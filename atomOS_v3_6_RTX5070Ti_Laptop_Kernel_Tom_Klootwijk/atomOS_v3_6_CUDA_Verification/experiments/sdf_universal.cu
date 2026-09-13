// Tom Klootwijk atomOS: explicit SDF/NOR programmable controller profile.
// The GPU has NOR wires and immutable SDF predicate textures, never a Rule table.
#include "../cuda/kernel.cu"
#include "atomos/sdf_nor.hpp"
#include "atomos/klein.hpp"
#include "atomos/packed_atlas.hpp"
#include <fstream>
#include <iostream>

using namespace atomos;
namespace U=atomos::universal;
namespace N=atomos::sdf_nor;
namespace fs=std::filesystem;
namespace sdf_detail {
using i64=std::int64_t;
struct GateTrace {u32 a,b,output,texel,parity,asa,na,boundary,fringe;};
struct Evaluation {U::Machine machine;u32 read;N::Decoded decoded;};
struct KernelResult {
 U::Machine machine;u32 steps=0,evaluations=0;U::Stop stop=U::Stop::running;
 u32 sm_before=0,sm_after=0;uint4 warm{},reread{};
};
struct CircuitView {const N::Gate*gates;const u32*outputs;u32 gate_count,input_count,qb,sb,states,alphabet;};
static_assert(sizeof(GateTrace)==36,"SDF/NOR gate trace ABI");
static_assert(sizeof(N::Decoded)==24&&sizeof(Evaluation)==48&&sizeof(KernelResult)==80&&sizeof(U::Step)==40,"SDF/NOR record ABI");
AO_HD inline klein::Canonical gate_site(const Shape&s,u32 gate){
 const u64 site=u64(gate)%(u64(s.rows)*s.words);
 const i64 row=i64(site/s.words),angle=i64(site%s.words)*32+(i64(gate%3)-1)*s.angles;
 return klein::canonical(row,angle,s.rows,s.angles);
}
__device__ inline u32 sm_id(){u32 value;asm volatile("mov.u32 %0, %%smid;":"=r"(value));return value;}
__device__ inline uint4 texture_sweep(cudaTextureObject_t texture,u32 stored_words){
 uint4 total=make_uint4(0,0,0,0);
 for(u32 i=0;i<stored_words;++i){const uint4 value=tex1Dfetch<uint4>(texture,int(i));total.x^=value.x;total.y^=value.y;total.z^=value.z;total.w^=value.w;}
 return total;
}
__global__ void atomos_sdf_nor_machine(CircuitView circuit,Shape shape,Layout layout,cudaTextureObject_t operators,
 U::PackedTapeView tape,U::Machine initial,u32 budget,u32 inject_gate,
 u32*wires,GateTrace*gate_trace,Evaluation*evaluations,U::Step*steps,KernelResult*out){
 if(blockIdx.x||threadIdx.x)return;
 KernelResult result{};result.machine=initial;result.sm_before=sm_id();
 result.warm=texture_sweep(operators,shape.padded_rows*shape.padded_words);
 if(initial.control>=circuit.states)result.stop=U::Stop::invalid;
 else if(!U::contains(tape,initial.head))result.stop=U::Stop::tape_range;
 else {
  // Zero budget still evaluates the current halt predicate through the NOR bank.
  do {
   u32 symbol=0;
   if(!U::packed_read(tape,result.machine.head,symbol)){result.stop=U::Stop::invalid;break;}
   for(u32 bit=0;bit<circuit.qb;++bit)wires[bit]=(result.machine.control>>bit)&1u;
   for(u32 bit=0;bit<circuit.sb;++bit)wires[circuit.qb+bit]=(symbol>>bit)&1u;
   wires[circuit.input_count-1]=0;
   const u64 base=u64(result.evaluations)*circuit.gate_count;
   for(u32 gate=0;gate<circuit.gate_count;++gate){
    const auto wiring=circuit.gates[gate];const u32 a=wires[wiring.left],b=wires[wiring.right];
    const auto site=gate_site(shape,gate);const u32 index=address(shape,site.row,site.angle/32,layout);
    const uint4 masks=tex1Dfetch<uint4>(operators,int(index));
    u32 signal=N::source_gate(a,b,masks.x,masks.y,masks.z,masks.w);
    if(inject_gate&&result.evaluations==0&&gate==0)signal^=1u;
    wires[circuit.input_count+gate]=signal;
    gate_trace[base+gate]={a,b,signal,index,site.parity,masks.x,masks.y,masks.z,masks.w};
   }
   const auto decoded=N::decode(wires,circuit.outputs,circuit.qb,circuit.sb);
   evaluations[result.evaluations++]={result.machine,symbol,decoded};
   if(decoded.halt_current){result.stop=U::Stop::halted;break;}
   if(result.steps>=budget){result.stop=U::Stop::running;break;}
   if(!decoded.defined){result.stop=U::Stop::missing_rule;break;}
   if(decoded.next>=circuit.states||decoded.write>=circuit.alphabet||decoded.move< -1||decoded.move>1){result.stop=U::Stop::invalid;break;}
   const i64 before=result.machine.head;
   if((decoded.move<0&&before==(-9223372036854775807LL-1))||(decoded.move>0&&before==9223372036854775807LL)){
    result.stop=U::Stop::tape_range;break;
   }
   const i64 after=before+decoded.move;
   if(!U::contains(tape,after)){result.stop=U::Stop::tape_range;break;}
   if(!U::packed_write(tape,before,decoded.write)){result.stop=U::Stop::invalid;break;}
   U::Step transition{};transition.control_before=result.machine.control;transition.control_after=decoded.next;
   transition.read=symbol;transition.write=decoded.write;transition.move=decoded.move;
   transition.head_before=before;transition.head_after=after;steps[result.steps++]=transition;
   result.machine={decoded.next,after};
   if(decoded.halt_after){result.stop=U::Stop::halted;break;}
  }while(result.steps<budget);
 }
 result.reread=texture_sweep(operators,shape.padded_rows*shape.padded_words);
 result.sm_after=sm_id();*out=result;
}

u64 checked_add(u64 a,u64 b){if(b>UINT64_MAX-a)throw std::length_error("resource byte sum overflow");return a+b;}
u64 checked_multiply(u64 a,u64 b){if(a&&b>UINT64_MAX/a)throw std::length_error("resource byte product overflow");return a*b;}
u64 number64(const std::string&text){u64 value=0;const auto parsed=std::from_chars(text.data(),text.data()+text.size(),value);if(parsed.ec!=std::errc()||parsed.ptr!=text.data()+text.size())throw std::invalid_argument("unsigned decimal required");return value;}
u32 number32(const std::string&text){const auto value=number64(text);if(value>UINT32_MAX)throw std::invalid_argument("uint32 overflow");return u32(value);}
i64 signed_number(const std::string&text){i64 value=0;const auto parsed=std::from_chars(text.data(),text.data()+text.size(),value);if(parsed.ec!=std::errc()||parsed.ptr!=text.data()+text.size())throw std::invalid_argument("signed decimal required");return value;}
std::ofstream file(const fs::path&path){std::ofstream out;out.exceptions(std::ios::failbit|std::ios::badbit);out.open(path,std::ios::binary);return out;}
void text_file(const fs::path&path,const std::string&value){auto out=file(path);out<<value;}
void words_file(const fs::path&path,const std::vector<u32>&words){auto out=file(path);for(u32 value:words)for(u32 byte=0;byte<4;++byte)out.put(char(value>>(byte*8)));}
void tape_file(const fs::path&path,const U::Cells&cells){auto out=file(path);out<<"address,symbol\n";for(const auto&entry:cells)if(entry.second)out<<entry.first<<','<<entry.second<<'\n';}
std::string machine_json(U::Machine value){return "{\"control\":"+std::to_string(value.control)+",\"head\":"+std::to_string(value.head)+"}";}
std::string checksum_json(uint4 value){return "["+std::to_string(value.x)+","+std::to_string(value.y)+","+std::to_string(value.z)+","+std::to_string(value.w)+"]";}
bool equal_checksum(uint4 a,uint4 b){return a.x==b.x&&a.y==b.y&&a.z==b.z&&a.w==b.w;}
U::Tape encode(u32 alphabet,i64 origin,u64 count,const U::Cells&cells,u32 fill){
 U::Tape tape(alphabet,origin,count);std::fill(tape.words.begin(),tape.words.end(),fill);
 i64 position=origin;for(u64 i=0;i<count;++i){tape.set(position,0);if(i+1<count)++position;}
 for(const auto&entry:cells){if(entry.first<origin||u64(entry.first)-u64(origin)>=count)throw std::invalid_argument("explicit initial tape cell outside selected extent");if(entry.second)tape.set(entry.first,entry.second);}
 return tape;
}
std::pair<u32,u32> atlas_dimensions(const fs::path&path){
 std::ifstream stream(path,std::ios::binary);if(!stream)throw std::runtime_error("cannot read operator atlas");
 char magic[8]{};stream.read(magic,8);const char expected[8]={'A','O','S','D','F','0','1','\n'};
 if(stream.gcount()!=8||!std::equal(magic,magic+8,expected))throw std::invalid_argument("operator atlas encoding");
 const u32 rows=packed_atlas_detail::read_u32(stream),angles=packed_atlas_detail::read_u32(stream);return {rows,angles};
}
void circuit_file(const fs::path&path,const N::Circuit&circuit){
 auto out=file(path);out<<"{\"schema\":\"atomOS-sdf-nor-circuit-v1\",\"states\":"<<circuit.states<<",\"alphabet\":"<<circuit.alphabet
  <<",\"control_bits\":"<<circuit.control_bits<<",\"symbol_bits\":"<<circuit.symbol_bits<<",\"input_count\":"<<circuit.input_count<<",\"gates\":[";
 for(std::size_t i=0;i<circuit.gates.size();++i)out<<(i?",":"")<<'['<<circuit.gates[i].left<<','<<circuit.gates[i].right<<']';
 out<<"],\"outputs\":[";for(std::size_t i=0;i<circuit.outputs.size();++i)out<<(i?",":"")<<circuit.outputs[i];out<<"]}\n";
}
struct Verification {
 bool gates=true,controller=true,machine=true,transitions=true,tape=true,texture=true;
 u64 gates_checked=0,gate_mismatches=0,odd_seam_gates=0;
 bool passed()const{return gates&&controller&&machine&&transitions&&tape&&texture;}
};
Verification verify(const N::Circuit&circuit,const U::Program&program,const Shape&shape,Layout layout,
 const std::vector<uint4>&intended,const std::vector<uint4>&uploaded,const U::Tape&before,const U::Tape&candidate,
 const KernelResult&result,const std::vector<GateTrace>&gates,const std::vector<Evaluation>&evaluations,
 const std::vector<U::Step>&transitions,u32 budget,u32 fill,U::ReferenceRun&reference){
 Verification check{};reference=U::reference_run(program,{program.initial_state,program.initial_head},program.initial_cells,budget,before.origin,before.cells);
 check.machine=U::equal_machine(reference.machine,result.machine)&&reference.stop==result.stop;
 check.transitions=reference.trace.size()==transitions.size();
 if(check.transitions)for(std::size_t i=0;i<transitions.size();++i)if(!U::equal_step(reference.trace[i],transitions[i]))check.transitions=false;
 const auto expected_tape=encode(program.alphabet,before.origin,before.cells,reference.cells,fill);
 check.tape=expected_tape.words==candidate.words;
 const bool initial_in_extent=program.initial_head>=before.origin&&u64(program.initial_head)-u64(before.origin)<before.cells;
 u64 expected_evaluations=0;
 if(initial_in_extent){
  expected_evaluations=reference.trace.size();
  if(budget==0||(reference.stop==U::Stop::halted&&reference.trace.empty())||
     reference.stop==U::Stop::missing_rule||reference.stop==U::Stop::tape_range)++expected_evaluations;
 }
 if(evaluations.size()!=expected_evaluations)check.controller=false;
 for(std::size_t e=0;e<evaluations.size();++e){
  const auto&value=evaluations[e];std::vector<u32> wires;
  if(e>=expected_evaluations){check.controller=false;check.gates=false;continue;}
  U::Machine expected_machine{};u32 expected_symbol=0;
  if(e<reference.trace.size()){const auto&transition=reference.trace[e];expected_machine={transition.control_before,transition.head_before};expected_symbol=transition.read;}
  else {expected_machine=reference.machine;const auto found=reference.cells.find(reference.machine.head);expected_symbol=found==reference.cells.end()?0:found->second;}
  if(!U::equal_machine(value.machine,expected_machine)||value.read!=expected_symbol)check.controller=false;
  wires=N::evaluate(circuit,expected_machine.control,expected_symbol);
  if(!N::equal_decoded(value.decoded,N::table_oracle(program,expected_machine.control,expected_symbol)))check.controller=false;
  for(u32 index=0;index<circuit.gates.size();++index){
   const auto&actual=gates[e*circuit.gates.size()+index];const auto&wiring=circuit.gates[index];
   // Independent placement arithmetic for the three declared seam representations.
   const u64 logical_site=u64(index)%(u64(shape.rows)*shape.words);
   const u32 row=u32(logical_site/shape.words),word=u32(logical_site%shape.words),parity=index%3==1?0u:1u;
   const u32 expected_index=address(shape,parity?shape.rows-1-row:row,word,layout);
   const auto masks=intended[expected_index];
   const bool same=actual.a==wires[wiring.left]&&actual.b==wires[wiring.right]&&actual.output==wires[circuit.input_count+index]&&
    actual.texel==expected_index&&actual.parity==parity&&actual.asa==masks.x&&actual.na==masks.y&&actual.boundary==masks.z&&actual.fringe==masks.w;
   ++check.gates_checked;if(parity)++check.odd_seam_gates;if(!same){check.gates=false;++check.gate_mismatches;}
  }
 }
 uint4 checksum=make_uint4(0,0,0,0);for(const auto&value:uploaded){checksum.x^=value.x;checksum.y^=value.y;checksum.z^=value.z;checksum.w^=value.w;}
 check.texture=equal_checksum(result.warm,checksum)&&equal_checksum(result.reread,checksum)&&result.sm_before==result.sm_after;
 return check;
}
} // sdf_detail

int main(int argc,char**argv){fs::path staging;try{
 using namespace sdf_detail;
 fs::path program_path,atlas_path,out_path;u32 steps=64,device=0,memory_mib=256,reserve_mib=512;
 u64 cells=256;i64 origin=-128;bool origin_set=false,cells_set=false;Layout layout=Layout::linear;
 std::string layout_name="linear",injection="none";const u32 tail_fill=0xa5a5a5a5u;
 for(int i=1;i<argc;++i){const std::string key=argv[i];
  if(key=="--help"){std::cout<<"Tom Klootwijk atomOS SDF/NOR machine\n--program FILE.atomos --atlas FILE --steps N --origin SIGNED --cells N --layout linear|morton8 --out NEW_DIR\n--memory-mib N --reserve-mib N --device N --inject none|texture|gate\nAll transitions execute a compiled acyclic NOR controller through Klein-addressed SDF predicate texture reads.\n";return 0;}
  if(++i>=argc)throw std::invalid_argument("missing option value");const std::string value=argv[i];
  if(key=="--program")program_path=value;else if(key=="--atlas")atlas_path=value;else if(key=="--out")out_path=value;
  else if(key=="--steps")steps=number32(value);else if(key=="--device")device=number32(value);
  else if(key=="--memory-mib")memory_mib=number32(value);else if(key=="--reserve-mib")reserve_mib=number32(value);
  else if(key=="--origin"){origin=signed_number(value);origin_set=true;}
  else if(key=="--cells"){cells=number64(value);cells_set=true;}
  else if(key=="--inject"){if(value!="none"&&value!="texture"&&value!="gate")throw std::invalid_argument("unknown injection");injection=value;}
  else if(key=="--layout"){layout_name=value;if(value=="linear")layout=Layout::linear;else if(value=="morton8")layout=Layout::morton8;else throw std::invalid_argument("unknown layout");}
  else throw std::invalid_argument("unknown option: "+key);
 }
 if(program_path.empty()||atlas_path.empty()||out_path.empty()||!memory_mib||origin_set!=cells_set||!U::valid_extent(origin,cells))throw std::invalid_argument("required program/atlas/output and valid memory extent");
 if(fs::exists(out_path))throw std::invalid_argument("output directory already exists");
 const auto actual_device=inspect(int(device));const u64 reserve=u64(reserve_mib)<<20;
 if(actual_device.free<=reserve)throw std::runtime_error("resource_refused: reserve exceeds available device memory");
 const u64 budget=std::min(u64(memory_mib)<<20,u64(actual_device.free)-reserve);
 const U::Program program=U::load_program(program_path,budget/4);
 const N::Circuit circuit=N::compile(program,std::max<u64>(1,budget/128),budget);
 const auto dims=atlas_dimensions(atlas_path);
 if(dims.second%32||dims.second<32||dims.first<2)throw std::invalid_argument("NOR geometry requires full 32-cell groups and at least two radial rows");
 const Shape s=shape(dims.first,dims.second,u64(1)<<20);
 const u64 host_geometry_bytes=checked_add(checked_multiply(stored(s),48),checked_multiply(logical(s),sizeof(Lane)+sizeof(State)));
 if(host_geometry_bytes>budget)throw std::runtime_error("resource_refused: atlas fixture and upload copies exceed selected host geometry budget");
 Fixture fixture(Config{s,layout,Producer::provided,1},130,"mixed",u64(1)<<20);
 const auto atlas_info=load_packed_atlas(atlas_path,fixture);
 const u64 stored_words=stored(s);
 if(stored_words>u64(INT_MAX)||stored_words>u64(actual_device.prop.maxTexture1DLinear))throw std::length_error("operator texture exceeds device addressing capacity");
 std::vector<uint4> intended(static_cast<std::size_t>(stored_words));
 for(u32 r=0;r<s.padded_rows;++r)for(u32 w=0;w<s.padded_words;++w){
  const u32 index=address(s,r,w,layout);const auto value=make_uint4(fixture.masks[0][index],fixture.masks[1][index],fixture.masks[2][index],fixture.masks[3][index]);
  if(r<s.rows&&w<s.words){if(value.x!=7||value.y!=7||value.z!=6||value.w!=7)throw std::invalid_argument("operator atlas is not the verified NOR-site SDF profile");}
  else if(value.x||value.y||value.z||value.w)throw std::invalid_argument("nonzero atlas padding");
  intended[index]=value;
 }
 const u64 evaluations_limit=std::max<u64>(1,steps),gate_records=checked_multiply(evaluations_limit,circuit.gates.size());
 const u64 tape_words=checked_add(checked_multiply(cells,U::symbol_bits(program.alphabet)),31)/32;
 u64 required=checked_multiply(stored_words,sizeof(uint4));
 for(const auto bytes:{checked_multiply(circuit.gates.size(),sizeof(N::Gate)),checked_multiply(circuit.outputs.size(),sizeof(u32)),
    checked_multiply(circuit.wire_count(),sizeof(u32)),checked_multiply(gate_records,sizeof(GateTrace)),
    checked_multiply(evaluations_limit,sizeof(Evaluation)),checked_multiply(steps,sizeof(U::Step)),
    checked_multiply(tape_words,sizeof(u32)),u64(sizeof(KernelResult))})required=checked_add(required,bytes);
 if(required>budget)throw std::runtime_error("resource_refused: exact NOR trace/tape/texture payload exceeds selected budget");
 U::Tape before=encode(program.alphabet,origin,cells,program.initial_cells,tail_fill),candidate=before;
 auto uploaded=intended;
 if(injection=="texture"){const auto site=gate_site(s,0);uploaded[address(s,site.row,site.angle/32,layout)].x&=~1u;}
 Buffer<uint4> masks(uploaded.size());masks.upload(uploaded.data());Texture texture(masks.get(),uploaded.size());
 Buffer<N::Gate> gate_buffer(circuit.gates.size());gate_buffer.upload(circuit.gates.data());
 Buffer<u32> outputs(circuit.outputs.size());outputs.upload(circuit.outputs.data());Buffer<u32> wires(circuit.wire_count());
 Buffer<u32> tape(before.words.size());tape.upload(before.words.data());
 Buffer<GateTrace> gate_trace(static_cast<std::size_t>(gate_records));Buffer<Evaluation> evaluation_buffer(static_cast<std::size_t>(evaluations_limit));
 Buffer<U::Step> transition_buffer(steps);Buffer<KernelResult> result_buffer(1);
 const CircuitView view{gate_buffer.get(),outputs.get(),u32(circuit.gates.size()),circuit.input_count,circuit.control_bits,circuit.symbol_bits,program.states,program.alphabet};
 const U::PackedTapeView tape_view{tape.get(),cells,origin,before.bits,program.alphabet};
 AO_CUDA(cudaFuncSetAttribute(atomos_sdf_nor_machine,cudaFuncAttributePreferredSharedMemoryCarveout,cudaSharedmemCarveoutMaxL1));
 cudaFuncAttributes attributes{};AO_CUDA(cudaFuncGetAttributes(&attributes,atomos_sdf_nor_machine));
 Event start,stop;AO_CUDA(cudaEventRecord(start.get()));
 atomos_sdf_nor_machine<<<1,32>>>(view,s,layout,texture.get(),tape_view,{program.initial_state,program.initial_head},steps,injection=="gate",wires.get(),gate_trace.get(),evaluation_buffer.get(),transition_buffer.get(),result_buffer.get());
 AO_CUDA(cudaGetLastError());AO_CUDA(cudaEventRecord(stop.get()));AO_CUDA(cudaEventSynchronize(stop.get()));
 float kernel_ms=0;AO_CUDA(cudaEventElapsedTime(&kernel_ms,start.get(),stop.get()));
 KernelResult result{};result_buffer.download(&result);tape.download(candidate.words.data());
 if(result.steps>steps||result.evaluations>evaluations_limit)throw std::runtime_error("GPU counters exceed allocated trace extent");
 std::vector<GateTrace> gates(static_cast<std::size_t>(gate_records));gate_trace.download(gates.data());gates.resize(std::size_t(result.evaluations)*circuit.gates.size());
 std::vector<Evaluation> evaluations(static_cast<std::size_t>(evaluations_limit));evaluation_buffer.download(evaluations.data());evaluations.resize(result.evaluations);
 std::vector<U::Step> transitions(steps);transition_buffer.download(transitions.data());transitions.resize(result.steps);
 U::ReferenceRun reference{};const auto verification=verify(circuit,program,s,layout,intended,uploaded,before,candidate,result,gates,evaluations,transitions,steps,tail_fill,reference);
 const bool accepted=verification.passed()&&(result.stop==U::Stop::running||result.stop==U::Stop::halted);
 const auto committed_machine=accepted?result.machine:U::Machine{program.initial_state,program.initial_head};
 const auto&committed=accepted?candidate:before;
 // No authoritative state is published until all gate/controller/tape checks above.
 staging=out_path;staging+=std::string(".partial_")+std::to_string(std::chrono::steady_clock::now().time_since_epoch().count());
 if(!fs::create_directories(staging))throw std::runtime_error("staging directory exists");
 fs::copy_file(program_path,staging/"program.atomos");fs::copy_file(atlas_path,staging/"operators.atlas");
 fs::path manifest=atlas_path;manifest.replace_extension(".json");if(fs::is_regular_file(manifest))fs::copy_file(manifest,staging/"operators.json");
 circuit_file(staging/"circuit.json",circuit);
 words_file(staging/"before.u32le",before.words);words_file(staging/"candidate.u32le",candidate.words);words_file(staging/"committed.u32le",committed.words);
 tape_file(staging/"before_tape.csv",before.nonzero_cells());tape_file(staging/"candidate_tape.csv",candidate.nonzero_cells());tape_file(staging/"committed_tape.csv",committed.nonzero_cells());
 {auto out=file(staging/"gate_trace.csv");out<<"evaluation,gate,a,b,output,texel,parity,asa,na,boundary,fringe\n";
  for(std::size_t i=0;i<gates.size();++i){const auto&g=gates[i];out<<i/circuit.gates.size()<<','<<i%circuit.gates.size()<<','<<g.a<<','<<g.b<<','<<g.output<<','<<g.texel<<','<<g.parity<<','<<g.asa<<','<<g.na<<','<<g.boundary<<','<<g.fringe<<'\n';}}
 {auto out=file(staging/"evaluations.csv");out<<"evaluation,control,head,read,next,write,move,defined,halt_current,halt_after\n";
  for(std::size_t i=0;i<evaluations.size();++i){const auto&e=evaluations[i];const auto&d=e.decoded;out<<i<<','<<e.machine.control<<','<<e.machine.head<<','<<e.read<<','<<d.next<<','<<d.write<<','<<d.move<<','<<d.defined<<','<<d.halt_current<<','<<d.halt_after<<'\n';}}
 {auto out=file(staging/"transitions.csv");out<<"step,control_before,head_before,read,write,move,control_after,head_after\n";
  for(std::size_t i=0;i<transitions.size();++i){const auto&t=transitions[i];out<<i<<','<<t.control_before<<','<<t.head_before<<','<<t.read<<','<<t.write<<','<<t.move<<','<<t.control_after<<','<<t.head_after<<'\n';}}
 std::ostringstream report;report<<std::setprecision(17)<<"{\"schema\":\"atomOS-sdf-nor-universal-v1\",\"concept_author\":\"Tom Klootwijk\",\"status\":"
  <<json_string(accepted?"passed":verification.passed()?"rejected_program":"rejected_verification")<<",\"accepted\":"<<(accepted?"true":"false")
  <<",\"profile\":\"new-compiled-SDF-NOR-controller-v1\",\"topology\":\"klein_m1_angular_twist\",\"operator_source\":\"loaded-SDF-predicate-atlas\""
  <<",\"runtime_rule_table\":false,\"gate_operation\":\"source-whole-word-ASA-NOR\",\"injection\":"<<json_string(injection)
  <<",\"device\":"<<device_record(actual_device)<<",\"layout\":"<<json_string(layout_name)<<",\"rows\":"<<s.rows<<",\"angles\":"<<s.angles<<",\"words\":"<<s.words
  <<",\"padded_rows\":"<<s.padded_rows<<",\"padded_words\":"<<s.padded_words<<",\"atlas_file_bytes\":"<<atlas_info.file_bytes<<",\"atlas_texture_bytes\":"<<stored_words*16
  <<",\"states\":"<<program.states<<",\"alphabet\":"<<program.alphabet<<",\"control_bits\":"<<circuit.control_bits<<",\"symbol_bits\":"<<circuit.symbol_bits<<",\"circuit_gates\":"<<circuit.gates.size()<<",\"circuit_wires\":"<<circuit.wire_count()
  <<",\"steps_budget\":"<<steps<<",\"executed_steps\":"<<result.steps<<",\"evaluations\":"<<result.evaluations<<",\"program_stop\":"<<json_string(U::stop_name(result.stop))
  <<",\"reference_stop\":"<<json_string(U::stop_name(reference.stop))<<",\"origin\":"<<origin<<",\"cells\":"<<cells<<",\"tail_fill\":"<<tail_fill
  <<",\"before\":"<<machine_json({program.initial_state,program.initial_head})<<",\"candidate\":"<<machine_json(result.machine)<<",\"committed\":"<<machine_json(committed_machine)
  <<",\"verification\":{\"passed\":"<<(verification.passed()?"true":"false")<<",\"gates\":"<<(verification.gates?"true":"false")<<",\"controller\":"<<(verification.controller?"true":"false")
  <<",\"machine\":"<<(verification.machine?"true":"false")<<",\"transitions\":"<<(verification.transitions?"true":"false")<<",\"tape\":"<<(verification.tape?"true":"false")
  <<",\"texture_sweeps\":"<<(verification.texture?"true":"false")<<",\"gates_checked\":"<<verification.gates_checked<<",\"gate_mismatches\":"<<verification.gate_mismatches<<",\"odd_seam_gate_evaluations\":"<<verification.odd_seam_gates<<'}'
  <<",\"kernel_ms\":"<<kernel_ms<<",\"timing_scope\":\"single CUDA kernel including full texture warm, NOR work, complete gate tracing and full texture reread; transfers, CPU verification and exports excluded\""
  <<",\"texture_reads\":{\"warm\":"<<stored_words<<",\"gates\":"<<u64(result.evaluations)*circuit.gates.size()<<",\"reread\":"<<stored_words<<",\"total\":"<<2*stored_words+u64(result.evaluations)*circuit.gates.size()<<'}'
  <<",\"sm_before\":"<<result.sm_before<<",\"sm_after\":"<<result.sm_after<<",\"warm_checksum\":"<<checksum_json(result.warm)<<",\"reread_checksum\":"<<checksum_json(result.reread)
  <<",\"memory_budget_bytes\":"<<budget<<",\"reserve_bytes\":"<<reserve<<",\"device_payload_bytes\":"<<required<<",\"host_geometry_bytes\":"<<host_geometry_bytes
  <<",\"abi\":{\"gate\":"<<sizeof(N::Gate)<<",\"gate_trace\":"<<sizeof(GateTrace)<<",\"evaluation\":"<<sizeof(Evaluation)<<",\"transition\":"<<sizeof(U::Step)<<",\"kernel_result\":"<<sizeof(KernelResult)<<",\"u32\":4,\"texture_texel\":16}"
  <<",\"registers_per_thread\":"<<attributes.numRegs<<",\"local_bytes_per_thread\":"<<attributes.localSizeBytes<<",\"static_shared_bytes\":"<<attributes.sharedSizeBytes
  <<",\"cache_residency\":\"requires-hardware-counter-measurement-for-this-kernel\",\"tape_addressing\":\"nonaliasing-signed-logical-addresses-separate-from-immutable-operator-atlas\"}\n";
 text_file(staging/"summary.json",report.str());
 text_file(staging/(accepted?"COMMITTED":"REJECTED"),accepted?"Every proposed NOR gate, transition and tape word verified before commit.\n":"The complete proposed epoch was rejected; committed state remains the input state.\n");
 if(fs::exists(out_path))throw std::runtime_error("output path appeared before publication");fs::rename(staging,out_path);staging.clear();std::cout<<report.str();return accepted?0:2;
}catch(const std::exception&e){std::cerr<<"atomOS SDF/NOR error: "<<e.what()<<'\n';if(!staging.empty())std::cerr<<"Uncommitted records: "<<staging.string()<<'\n';return 1;}}
