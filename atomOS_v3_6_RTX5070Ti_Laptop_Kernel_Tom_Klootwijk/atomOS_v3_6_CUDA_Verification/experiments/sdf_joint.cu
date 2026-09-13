// New finite joint realization of Tom Klootwijk's atomOS: one immutable SDF
// texture drives both a compiled NOR controller and a lineage/word/JK machine.
// Reuse frozen NOR support without changing its standalone entry point/source.
#define main atomos_sdf_nor_standalone_entry
#include "sdf_universal.cu"
#undef main
#include "atomos/sdf_lineage.hpp"

namespace L=atomos::sdf_lineage;
namespace joint_detail {
using namespace sdf_detail;
enum class Stop:u32 {running=0,halted=1,missing_rule=2,tape_range=3,invalid=4,frontier_cap=5,lineage_overflow=6,hinge_overflow=7};
const char* stop_name(Stop s){switch(s){case Stop::running:return "running";case Stop::halted:return "halted";case Stop::missing_rule:return "missing_rule";case Stop::tape_range:return "tape_range";case Stop::frontier_cap:return "frontier_cap";case Stop::lineage_overflow:return "lineage_overflow";case Stop::hinge_overflow:return "hinge_overflow";default:return "invalid";}}
struct WordTrace {u32 emitted=0,q_before=0,texel=0,asa_mask=0,na_mask=0,boundary_mask=0,fringe_mask=0;WordResult word{};};
struct SearchTrace {u64 key=0;u32 found=UINT32_MAX,visits=0,overflow=0;u32 path[33]{};};
struct StepTrace {Evaluation evaluation{};U::Step transition{};u32 applied=0;Stop stop=Stop::running;u32 before_count=0,after_count=0,children=0,phi_steps=0,searches=0;};
struct ResultTrace {U::Machine machine{};u32 steps=0,evaluations=0;Stop stop=Stop::running;u32 frontier_count=0,sm_before=0,sm_after=0;uint4 warm{},reread{};};
static_assert(sizeof(WordTrace)==60&&sizeof(SearchTrace)==152&&sizeof(StepTrace)==120&&sizeof(ResultTrace)==80,"joint trace ABI");

AO_HD inline L::Diagnostic observation(double phi,u32 profile,double interval){L::Diagnostic d{};const AngleInput input{0,phi,0,interval,profile,1,1,1};d.angle=observe(input);invariant_bank(input,d.angle,d.checks);return d;}
AO_HD inline SearchTrace binary_search(const L::Leaf*sorted,u32 count,u64 key){
 SearchTrace trace{};trace.key=key;for(u32&i:trace.path)i=UINT32_MAX;
 u32 lower=0,upper=count;
 while(lower<upper){
  if(trace.visits>=33){trace.overflow=1;return trace;}
  const u32 middle=lower+(upper-lower)/2;trace.path[trace.visits++]=middle;
  if(sorted[middle].id==key){trace.found=middle;return trace;}
  if(sorted[middle].id<key)lower=middle+1;else upper=middle;
 }
 return trace;
}

__global__ void atomos_sdf_joint(CircuitView circuit,Shape s,Layout layout,cudaTextureObject_t texture,
 u32 budget,u32 cap,u32 initial_count,U::Machine initial,i64 origin,u64 cells,u64 tape_words,u32 bits,
 u32 base_phi,u32 j,u32 k,u32 profile,double interval,u32 inject,
 u32*wires,u32*tape_snapshots,State*bank_snapshots,L::Leaf*frontier_snapshots,
 GateTrace*gate_trace,StepTrace*step_trace,L::Branch*branch_trace,L::Diagnostic*diagnostic_trace,
 u32*admission_trace,WordTrace*word_trace,SearchTrace*search_trace,ResultTrace*out){
 if(blockIdx.x||threadIdx.x)return;
 ResultTrace result{};result.machine=initial;result.frontier_count=initial_count;result.sm_before=sm_id();
 result.warm=texture_sweep(texture,s.padded_rows*s.padded_words);const u64 word_count=u64(s.rows)*s.words;
 U::PackedTapeView first_tape{tape_snapshots,cells,origin,bits,circuit.alphabet};
 if(initial.control>=circuit.states)result.stop=Stop::invalid;
 else if(!U::contains(first_tape,initial.head))result.stop=Stop::tape_range;
 else do {
  StepTrace record{};record.before_count=record.after_count=result.frontier_count;
  U::PackedTapeView current_tape{tape_snapshots+u64(result.steps)*tape_words,cells,origin,bits,circuit.alphabet};
  u32 symbol=0;if(!U::packed_read(current_tape,result.machine.head,symbol)){result.stop=Stop::invalid;break;}
  for(u32 bit=0;bit<circuit.qb;++bit)wires[bit]=(result.machine.control>>bit)&1u;
  for(u32 bit=0;bit<circuit.sb;++bit)wires[circuit.qb+bit]=(symbol>>bit)&1u;wires[circuit.input_count-1]=0;
  const u64 gate_base=u64(result.evaluations)*circuit.gate_count;
  for(u32 gate=0;gate<circuit.gate_count;++gate){
   const auto wire=circuit.gates[gate];const u32 a=wires[wire.left],b=wires[wire.right];const auto site=gate_site(s,gate);
   const u32 texel=address(s,site.row,site.angle/32,layout);const uint4 masks=tex1Dfetch<uint4>(texture,int(texel));
   u32 value=N::source_gate(a,b,masks.x,masks.y,masks.z,masks.w);if(inject==1&&result.evaluations==0&&gate==0)value^=1u;
   wires[circuit.input_count+gate]=value;gate_trace[gate_base+gate]={a,b,value,texel,site.parity,masks.x,masks.y,masks.z,masks.w};
  }
  const auto decoded=N::decode(wires,circuit.outputs,circuit.qb,circuit.sb);record.evaluation={result.machine,symbol,decoded};
  Stop refusal=Stop::running;i64 destination=result.machine.head;u64 phi=0;
  const auto*before_frontier=frontier_snapshots+u64(result.steps)*cap;
  if(decoded.halt_current)refusal=Stop::halted;
  else if(result.steps>=budget)refusal=Stop::running;
  else if(!decoded.defined)refusal=Stop::missing_rule;
  else if(decoded.next>=circuit.states||decoded.write>=circuit.alphabet||decoded.move< -1||decoded.move>1)refusal=Stop::invalid;
  else if((decoded.move<0&&destination==INT64_MIN)||(decoded.move>0&&destination==INT64_MAX))refusal=Stop::tape_range;
  else {
   destination+=decoded.move;
   if(!U::contains(current_tape,destination))refusal=Stop::tape_range;
   else {
    phi=u64(base_phi)*(u64(decoded.write)+1);
    if(phi>UINT32_MAX)refusal=Stop::hinge_overflow;
    else {
     for(u32 i=0;i<result.frontier_count;++i)if(before_frontier[i].id>UINT64_MAX/2){refusal=Stop::lineage_overflow;break;}
     if(refusal==Stop::running&&result.frontier_count>cap/2)refusal=Stop::frontier_cap;
    }
   }
  }
  if(decoded.halt_current||result.steps>=budget||refusal!=Stop::running){
   record.stop=refusal;step_trace[result.evaluations++]=record;result.stop=refusal;break;
  }
  // All representability/capacity checks precede writes to a new joint snapshot.
  record.phi_steps=u32(phi);record.children=2*result.frontier_count;record.applied=1;
  const u64 child_base=u64(result.steps)*cap,word_base=u64(result.steps)*word_count;
  const auto*before_bank=bank_snapshots+word_base;auto*after_bank=bank_snapshots+word_base+word_count;
  auto*after_frontier=frontier_snapshots+u64(result.steps+1)*cap;
  for(u64 i=0;i<word_count;++i)word_trace[word_base+i]=WordTrace{};
  for(u32 child=0;child<record.children;++child){
   const auto parent=before_frontier[child/2];const u32 branch=child&1u;
   const auto cell=klein::canonical(parent.row,i64(parent.angle)+(branch?-i64(phi):i64(phi)),s.rows,s.angles);
   const double delta=(branch?-1.0:1.0)*TAU*double(phi)/double(s.angles);const auto diagnostic=observation(delta,profile,interval);
   branch_trace[child_base+child]={parent.id*2+branch,parent.id,branch,cell.row,cell.angle,cell.parity,delta,1,diagnostic.angle.status};
   diagnostic_trace[child_base+child]=diagnostic;word_trace[word_base+u64(cell.row)*s.words+cell.angle/32].emitted|=u32(1)<<(cell.angle&31);
  }
  for(u32 row=0;row<s.rows;++row)for(u32 word=0;word<s.words;++word){
   const u64 index=u64(row)*s.words+word;const u32 emitted=word_trace[word_base+index].emitted,texel=address(s,row,word,layout);
   const uint4 masks=tex1Dfetch<uint4>(texture,int(texel));Lane lane{};lane.initial_word=emitted;lane.j=j;lane.k=k;
   auto value=word_step(emitted,masks.x,masks.y,masks.z,valid_mask(s,word),masks.w,before_bank[index],lane);
   if(inject==2&&result.steps==0&&index==0)value.output^=1u;
   word_trace[word_base+index]={emitted,before_bank[index].q,texel,masks.x,masks.y,masks.z,masks.w,value};
   after_bank[index]={value.output,value.q_after};
  }
  u32 next_count=0;
  for(u32 child=0;child<record.children;++child){const auto value=branch_trace[child_base+child];
   const u32 yes=(after_bank[u64(value.row)*s.words+value.angle/32].word>>(value.angle&31))&1u;admission_trace[child_base+child]=yes;
   if(yes)after_frontier[next_count++]={value.id,value.row,value.angle};
  }
  record.after_count=next_count;record.searches=record.children+2;
  // Children of sorted distinct positive IDs remain sorted after stable admission.
  // Midpoint lookup is an actual implicit balanced BST, with no host-built index.
  for(u32 query=0;query<record.searches;++query){const u64 key=query<record.children?branch_trace[child_base+query].id:query==record.children?0:UINT64_MAX;
   search_trace[u64(result.steps)*(u64(cap)+2)+query]=binary_search(after_frontier,next_count,key);
  }
  auto*next_tape=tape_snapshots+u64(result.steps+1)*tape_words;for(u64 word=0;word<tape_words;++word)next_tape[word]=current_tape.words[word];
  U::PackedTapeView next_view{next_tape,cells,origin,bits,circuit.alphabet};
  if(!U::packed_write(next_view,result.machine.head,decoded.write)){result.stop=Stop::invalid;break;}
  record.transition={result.machine.control,decoded.next,symbol,decoded.write,result.machine.head,destination,decoded.move};
  result.machine={decoded.next,destination};result.frontier_count=next_count;++result.steps;
  record.stop=decoded.halt_after?Stop::halted:Stop::running;step_trace[result.evaluations++]=record;result.stop=record.stop;
  if(result.stop==Stop::halted)break;
 }while(result.steps<budget);
 result.reread=texture_sweep(texture,s.padded_rows*s.padded_words);result.sm_after=sm_id();*out=result;
}

bool same_diagnostic(const L::Diagnostic&a,const L::Diagnostic&b){
 if(a.angle.status!=b.angle.status||a.angle.beta_status!=b.angle.beta_status)return false;
 if(b.angle.beta_status==0&&!near(a.angle.beta,b.angle.beta))return false;
 if(b.angle.status==0&&(!near(a.angle.raw,b.angle.raw)||!near(a.angle.principal,b.angle.principal)||!near(a.angle.line,b.angle.line)))return false;
 for(u32 i=0;i<6;++i)if(a.checks[i].state!=b.checks[i].state||a.checks[i].reason!=b.checks[i].reason||(b.checks[i].state!=2&&!near(a.checks[i].error,b.checks[i].error)))return false;return true;
}
struct Download {std::vector<u32> tapes,admitted;std::vector<State> banks;std::vector<L::Leaf> frontiers;std::vector<GateTrace> gates;std::vector<StepTrace> steps;std::vector<L::Branch> branches;std::vector<L::Diagnostic> diagnostics;std::vector<WordTrace> words;std::vector<SearchTrace> searches;ResultTrace result{};};
struct Audit {bool passed=true;u64 checks=0,gates=0,words=0,children=0,searches=0;Stop stop=Stop::running;u32 applied=0,evaluations=0;void test(bool value){++checks;if(!value)passed=false;}};
Audit verify_joint(const Download&gpu,const U::Program&program,const N::Circuit&circuit,const Fixture&fixture,const std::vector<uint4>&packed,
 const U::Tape&initial_tape,const std::vector<L::Leaf>&initial_frontier,const std::vector<State>&initial_bank,
 u32 budget,u32 cap,u32 base_phi,u32 j,u32 k,u32 profile,double interval,u32 fill){
 Audit audit{};const auto&s=fixture.config.shape;const u64 n=logical(s),tape_words=initial_tape.words.size();
 U::Machine machine{program.initial_state,program.initial_head};U::Cells cells=U::normalized_cells(program.initial_cells);
 auto frontier=initial_frontier;auto bank=initial_bank;
 const auto snapshot=[&](u32 number){
  const auto tape=encode(program.alphabet,initial_tape.origin,initial_tape.cells,cells,fill);
  for(u64 i=0;i<tape_words;++i)audit.test(gpu.tapes[u64(number)*tape_words+i]==tape.words[i]);
  for(u64 i=0;i<n;++i){const auto actual=gpu.banks[u64(number)*n+i];audit.test(actual.word==bank[i].word&&actual.q==bank[i].q);}
  for(std::size_t i=0;i<frontier.size();++i)audit.test(L::equal_leaf(gpu.frontiers[u64(number)*cap+i],frontier[i]));
 };
 snapshot(0);
 const bool in_extent=machine.head>=initial_tape.origin&&u64(machine.head)-u64(initial_tape.origin)<initial_tape.cells;
 if(!in_extent)audit.stop=Stop::tape_range;
 else do {
  const auto found=cells.find(machine.head);const u32 symbol=found==cells.end()?0:found->second;
  const auto decoded=N::table_oracle(program,machine.control,symbol);const auto wires=N::evaluate(circuit,machine.control,symbol);
  if(audit.evaluations>=gpu.result.evaluations){audit.test(false);break;}
  const auto&actual=gpu.steps[audit.evaluations];audit.test(U::equal_machine(actual.evaluation.machine,machine)&&actual.evaluation.read==symbol&&N::equal_decoded(actual.evaluation.decoded,decoded));
  audit.test(actual.before_count==frontier.size());
  for(u32 gate=0;gate<circuit.gates.size();++gate){const auto&g=gpu.gates[u64(audit.evaluations)*circuit.gates.size()+gate];const auto wiring=circuit.gates[gate];
   const u64 site=u64(gate)%n;const u32 row=u32(site/s.words),word=u32(site%s.words),parity=gate%3==1?0:1;
   const u32 texel=address(s,parity?s.rows-1-row:row,word,fixture.config.layout);const auto masks=packed[texel];
   audit.test(g.a==wires[wiring.left]&&g.b==wires[wiring.right]&&g.output==wires[circuit.input_count+gate]&&g.texel==texel&&g.parity==parity&&g.asa==masks.x&&g.na==masks.y&&g.boundary==masks.z&&g.fringe==masks.w);++audit.gates;
  }
  Stop refusal=Stop::running;u64 phi=0;U::Machine next_machine=machine;U::Cells next_cells=cells;U::Step transition{};
  if(decoded.halt_current)refusal=Stop::halted;
  else if(audit.applied>=budget)refusal=Stop::running;
  else {
   const auto ustop=U::reference_step(program,next_machine,next_cells,transition,initial_tape.origin,initial_tape.cells);
   if(ustop!=U::Stop::running&&ustop!=U::Stop::halted)refusal=static_cast<Stop>(u32(ustop));
   else {phi=u64(base_phi)*(u64(decoded.write)+1);if(phi>UINT32_MAX)refusal=Stop::hinge_overflow;
    else {const auto resource=L::can_expand(frontier,cap);if(resource==L::Resource::lineage_overflow)refusal=Stop::lineage_overflow;else if(resource==L::Resource::frontier_cap)refusal=Stop::frontier_cap;}}
  }
  ++audit.evaluations;
  if(decoded.halt_current||audit.applied>=budget||refusal!=Stop::running){
   audit.test(actual.applied==0&&actual.stop==refusal&&actual.after_count==frontier.size()&&actual.children==0&&actual.phi_steps==0&&actual.searches==0&&U::equal_step(actual.transition,U::Step{}));audit.stop=refusal;break;
  }
  audit.test(actual.applied==1&&actual.phi_steps==phi&&U::equal_step(actual.transition,transition));
  const auto children=L::propose_reference(frontier,s,cap,profile,u32(phi));const auto emitted=L::emit(L::branch_leaves(children),s);
  const auto filtered=L::filter_reference(emitted,fixture);const auto next_frontier=L::admit_reference(children,filtered,s);
  const u64 child_base=u64(audit.applied)*cap,word_base=u64(audit.applied)*n;
  audit.test(actual.children==children.size()&&actual.after_count==next_frontier.size()&&actual.searches==children.size()+2);
  for(std::size_t i=0;i<children.size();++i){const auto&child=children[i];audit.test(L::equal_branch(gpu.branches[child_base+i],child));
   audit.test(same_diagnostic(gpu.diagnostics[child_base+i],observation(child.delta_phi,profile,interval)));
   const u32 yes=(filtered[u64(child.row)*s.words+child.angle/32]>>(child.angle&31))&1u;audit.test(gpu.admitted[child_base+i]==yes);++audit.children;
  }
  for(u32 row=0;row<s.rows;++row)for(u32 word=0;word<s.words;++word){const u64 i=u64(row)*s.words+word;const auto&v=gpu.words[word_base+i];const u32 texel=address(s,row,word,fixture.config.layout);const auto masks=packed[texel];
   // Independent set operations, per-cell filter and JK truth equation.
   const u32 asa=emitted[i]&masks.x&valid_mask(s,word)&masks.w,na=asa&masks.y;
   const u32 q_after=(j&&bank[i].q==0)||(!k&&bank[i].q!=0);
   audit.test(v.emitted==emitted[i]&&v.q_before==bank[i].q&&v.texel==texel&&v.asa_mask==masks.x&&v.na_mask==masks.y&&v.boundary_mask==masks.z&&v.fringe_mask==masks.w);
   audit.test(v.word.produced==emitted[i]&&v.word.asa==asa&&v.word.na==na&&v.word.hits==popcount(na&masks.z)&&v.word.output==filtered[i]&&v.word.q_after==q_after&&v.word.blend==0&&v.word.blend_known==0);
   bank[i]={filtered[i],q_after};++audit.words;
  }
  for(u32 query=0;query<children.size()+2;++query){const u64 key=query<children.size()?children[query].id:query==children.size()?0:UINT64_MAX;const auto&v=gpu.searches[u64(audit.applied)*(u64(cap)+2)+query];
   u32 expected=UINT32_MAX;for(u32 i=0;i<next_frontier.size();++i)if(next_frontier[i].id==key){expected=i;break;}
   audit.test(v.key==key&&v.found==expected&&v.overflow==0&&v.visits<=32);
   u32 lo=0,hi=u32(next_frontier.size()),visits=0;while(lo<hi){const u32 mid=lo+(hi-lo)/2;audit.test(visits<33&&v.path[visits]==mid);++visits;if(next_frontier[mid].id==key)break;if(next_frontier[mid].id<key)lo=mid+1;else hi=mid;}
   audit.test(v.visits==visits);for(u32 i=visits;i<33;++i)audit.test(v.path[i]==UINT32_MAX);++audit.searches;
  }
  machine=next_machine;cells.swap(next_cells);frontier=next_frontier;++audit.applied;snapshot(audit.applied);
  audit.stop=decoded.halt_after?Stop::halted:Stop::running;audit.test(actual.stop==audit.stop);if(audit.stop==Stop::halted)break;
 }while(audit.applied<budget);
 audit.test(gpu.result.steps==audit.applied&&gpu.result.evaluations==audit.evaluations&&gpu.result.stop==audit.stop&&gpu.result.frontier_count==frontier.size()&&U::equal_machine(gpu.result.machine,machine));
 uint4 checksum{};for(const auto&v:packed){checksum.x^=v.x;checksum.y^=v.y;checksum.z^=v.z;checksum.w^=v.w;}
 audit.test(equal_checksum(checksum,gpu.result.warm)&&equal_checksum(checksum,gpu.result.reread)&&gpu.result.sm_before==gpu.result.sm_after);
 return audit;
}
} // joint_detail

namespace joint_detail {
void snapshot_data_files(const fs::path&dir,const std::string&prefix,const u32*tape_data,const State*bank_data,const L::Leaf*frontier_data,u32 count,u64 n,u64 tape_words){
 auto tape=file(dir/(prefix+"_tape.u32le"));for(u64 i=0;i<tape_words;++i){const u32 value=tape_data[i];for(u32 byte=0;byte<4;++byte)tape.put(char(value>>(byte*8)));}
 auto leaves=file(dir/(prefix+"_frontier.csv"));leaves<<"id,row,angle\n";for(u32 i=0;i<count;++i){const auto&v=frontier_data[i];leaves<<v.id<<','<<v.row<<','<<v.angle<<'\n';}
 auto bank=file(dir/(prefix+"_words.csv"));bank<<"lane,word,q\n";for(u64 i=0;i<n;++i){const auto&v=bank_data[i];bank<<i<<','<<v.word<<','<<v.q<<'\n';}
}
void snapshot_files(const fs::path&dir,const std::string&prefix,const Download&data,u32 snapshot,u32 count,u64 n,u64 tape_words,u32 cap){
 snapshot_data_files(dir,prefix,data.tapes.data()+u64(snapshot)*tape_words,data.banks.data()+u64(snapshot)*n,data.frontiers.data()+u64(snapshot)*cap,count,n,tape_words);
}
std::string decoded_json(const N::Decoded&d){std::ostringstream s;s<<"{\"next\":"<<d.next<<",\"write\":"<<d.write<<",\"move\":"<<d.move<<",\"defined\":"<<d.defined<<",\"halt_current\":"<<d.halt_current<<",\"halt_after\":"<<d.halt_after<<'}';return s.str();}
std::string transition_json(const U::Step&t){std::ostringstream s;s<<"{\"control_before\":"<<t.control_before<<",\"control_after\":"<<t.control_after<<",\"read\":"<<t.read<<",\"write\":"<<t.write<<",\"head_before\":"<<t.head_before<<",\"head_after\":"<<t.head_after<<",\"move\":"<<t.move<<'}';return s.str();}
void export_step(const fs::path&dir,const Download&data,u32 evaluation,u32 snapshot,u32 gates,u32 cap,u64 n,u64 tape_words,double interval){
 fs::create_directory(dir);const auto&record=data.steps[evaluation];const auto&ev=record.evaluation;
 snapshot_files(dir,"before",data,snapshot,record.before_count,n,tape_words,cap);
 snapshot_files(dir,"candidate",data,snapshot+record.applied,record.after_count,n,tape_words,cap);
 std::ostringstream meta;meta<<std::setprecision(17)<<"{\"evaluation\":"<<evaluation<<",\"step\":"<<snapshot<<",\"applied\":"<<(record.applied?"true":"false")<<",\"status\":"<<json_string(stop_name(record.stop))
  <<",\"machine\":"<<machine_json(ev.machine)<<",\"read\":"<<ev.read<<",\"decoded\":"<<decoded_json(ev.decoded)<<",\"transition\":"<<(record.applied?transition_json(record.transition):"null")
  <<",\"before_count\":"<<record.before_count<<",\"after_count\":"<<record.after_count<<",\"children\":"<<record.children<<",\"phi_steps\":"<<record.phi_steps<<",\"searches\":"<<record.searches
  <<",\"time_before\":"<<double(snapshot)*interval<<",\"time_candidate\":"<<double(snapshot+record.applied)*interval<<"}\n";
 text_file(dir/"step.json",meta.str());
 {auto out=file(dir/"gate_trace.csv");out<<"evaluation,gate,a,b,output,texel,parity,asa,na,boundary,fringe\n";for(u32 i=0;i<gates;++i){const auto&g=data.gates[u64(evaluation)*gates+i];out<<evaluation<<','<<i<<','<<g.a<<','<<g.b<<','<<g.output<<','<<g.texel<<','<<g.parity<<','<<g.asa<<','<<g.na<<','<<g.boundary<<','<<g.fringe<<'\n';}}
 {auto out=file(dir/"branches.csv");out<<std::setprecision(17)<<"id,parent,branch,row,angle,parity,delta_phi,live,diagnostic_status,admitted\n";for(u32 i=0;i<record.children;++i){const auto&v=data.branches[u64(snapshot)*cap+i];out<<v.id<<','<<v.parent<<','<<v.branch<<','<<v.row<<','<<v.angle<<','<<v.parity<<','<<v.delta_phi<<','<<v.live<<','<<v.diagnostic_status<<','<<data.admitted[u64(snapshot)*cap+i]<<'\n';}}
 {auto out=file(dir/"diagnostics.csv");out<<std::setprecision(17)<<"id,delta_rho,delta_phi,alpha,interval,status,beta_status,beta,raw,principal,line";for(u32 i=0;i<6;++i)out<<",check"<<i<<"_state,check"<<i<<"_reason,check"<<i<<"_error";out<<'\n';
  for(u32 i=0;i<record.children;++i){const auto&b=data.branches[u64(snapshot)*cap+i];const auto&d=data.diagnostics[u64(snapshot)*cap+i];const auto&a=d.angle;out<<b.id<<",0,"<<b.delta_phi<<",0,"<<interval<<','<<a.status<<','<<a.beta_status<<',';if(a.beta_status==0)out<<a.beta;out<<',';if(a.status==0)out<<a.raw;out<<',';if(a.status==0)out<<a.principal;out<<',';if(a.status==0)out<<a.line;for(const auto&c:d.checks){out<<','<<c.state<<','<<c.reason<<',';if(c.state!=2)out<<c.error;}out<<'\n';}}
 {auto out=file(dir/"words.csv");out<<"lane,emitted,q_before,texel,asa_mask,na_mask,boundary_mask,fringe_mask,produced,asa,na,hits,output,q_after,blend,blend_known\n";
  if(record.applied)for(u64 i=0;i<n;++i){const auto&v=data.words[u64(snapshot)*n+i];const auto&w=v.word;out<<i<<','<<v.emitted<<','<<v.q_before<<','<<v.texel<<','<<v.asa_mask<<','<<v.na_mask<<','<<v.boundary_mask<<','<<v.fringe_mask<<','<<w.produced<<','<<w.asa<<','<<w.na<<','<<w.hits<<','<<w.output<<','<<w.q_after<<','<<w.blend<<','<<w.blend_known<<'\n';}}
 {auto out=file(dir/"search.csv");out<<"index,key,found,visits,overflow";for(u32 i=0;i<33;++i)out<<",path"<<i;out<<'\n';for(u32 i=0;i<record.searches;++i){const auto&v=data.searches[u64(snapshot)*(u64(cap)+2)+i];out<<i<<','<<v.key<<','<<v.found<<','<<v.visits<<','<<v.overflow;for(u32 p:v.path)out<<','<<p;out<<'\n';}}
}
} // joint_detail

int main(int argc,char**argv){fs::path staging;try{
 using namespace joint_detail;
 fs::path program_path,atlas_path,out_path;u32 steps=8,cap=4096,device_id=0,memory_mib=256,reserve_mib=512;
 u32 base_phi=0,j=0,k=0,q=0,profile=0,seed_live=1;double interval=1;bool base_set=false,origin_set=false,cells_set=false;
 i64 origin=-128,seed_row=0,seed_angle=0;u64 cells=256,seed_id=1;Layout layout=Layout::linear;
 std::string layout_name="linear",profile_name="source",injection="none";const u32 fill=0xa5a5a5a5u;
 for(int i=1;i<argc;++i){const std::string key=argv[i];if(key=="--help"){
  std::cout<<"atomOS finite joint SDF/NOR + Klein lineage profile\n--program FILE --atlas FILE --out NEW_DIR --steps N --max-frontier N\n--origin SIGNED --cells N --base-phi-steps N (default angular period)\n--seed-id N --seed-row SIGNED --seed-angle SIGNED --seed-live 0|1 --q 0|1 --j 0|1 --k 0|1 --interval POSITIVE\n--layout linear|morton8 --diagnostic-profile source|directed --memory-mib N --reserve-mib N --device N --inject none|gate|word\n";return 0;}
  if(++i>=argc)throw std::invalid_argument("missing option value");const std::string value=argv[i];
  if(key=="--program")program_path=value;else if(key=="--atlas")atlas_path=value;else if(key=="--out")out_path=value;
  else if(key=="--steps")steps=number32(value);else if(key=="--max-frontier")cap=number32(value);
  else if(key=="--origin"){origin=signed_number(value);origin_set=true;}else if(key=="--cells"){cells=number64(value);cells_set=true;}
  else if(key=="--base-phi-steps"){base_phi=number32(value);base_set=true;}else if(key=="--q")q=number32(value);else if(key=="--j")j=number32(value);else if(key=="--k")k=number32(value);
  else if(key=="--interval"){std::size_t used=0;interval=std::stod(value,&used);if(used!=value.size())throw std::invalid_argument("invalid diagnostic interval");}
  else if(key=="--seed-id")seed_id=number64(value);else if(key=="--seed-row")seed_row=signed_number(value);else if(key=="--seed-angle")seed_angle=signed_number(value);else if(key=="--seed-live")seed_live=number32(value);
  else if(key=="--device")device_id=number32(value);else if(key=="--memory-mib")memory_mib=number32(value);else if(key=="--reserve-mib")reserve_mib=number32(value);
  else if(key=="--layout"){layout_name=value;if(value=="linear")layout=Layout::linear;else if(value=="morton8")layout=Layout::morton8;else throw std::invalid_argument("unknown layout");}
  else if(key=="--diagnostic-profile"){profile_name=value;if(value=="source")profile=0;else if(value=="directed")profile=1;else throw std::invalid_argument("unknown diagnostic profile");}
  else if(key=="--inject"){injection=value;if(value!="none"&&value!="gate"&&value!="word")throw std::invalid_argument("unknown injection");}
  else throw std::invalid_argument("unknown option: "+key);
 }
 if(program_path.empty()||atlas_path.empty()||out_path.empty()||!cap||cap>UINT32_MAX-2||!memory_mib||!seed_id||seed_live>1||j>1||k>1||q>1||!finite(interval)||interval<=0||!finite(double(steps)*interval)||origin_set!=cells_set||!U::valid_extent(origin,cells))throw std::invalid_argument("invalid required input, extent, explicit bit, interval or frontier capacity");
 if(fs::exists(out_path))throw std::invalid_argument("output directory already exists");
 const auto device=inspect(int(device_id));const u64 reserve=u64(reserve_mib)<<20;if(device.free<=reserve)throw std::runtime_error("resource_refused: device reserve unavailable");
 const u64 budget=std::min(u64(memory_mib)<<20,u64(device.free)-reserve);const U::Program program=U::load_program(program_path,budget/4);
 const N::Circuit circuit=N::compile(program,std::max<u64>(1,budget/128),budget);const auto dimensions=atlas_dimensions(atlas_path);
 if(dimensions.first<2||dimensions.second<32||dimensions.second%32)throw std::invalid_argument("joint NOR profile needs at least two rows and full angular words");
 const Shape s=shape(dimensions.first,dimensions.second,u64(1)<<20);if(!base_set)base_phi=s.angles;
 const u64 n=logical(s),atlas=stored(s),tape_words=checked_add(checked_multiply(cells,U::symbol_bits(program.alphabet)),31)/32;
 const u64 evaluations=std::max<u64>(1,steps),snapshots=checked_add(steps,1);
 const u64 tape_count=checked_multiply(snapshots,tape_words),bank_count=checked_multiply(snapshots,n),frontier_count=checked_multiply(snapshots,cap);
 const u64 gate_count=checked_multiply(evaluations,circuit.gates.size()),child_count=checked_multiply(steps,cap),word_count=checked_multiply(steps,n),search_count=checked_multiply(steps,u64(cap)+2);
 u64 required=sizeof(ResultTrace);
 for(const auto bytes:{checked_multiply(atlas,16),checked_multiply(circuit.gates.size(),sizeof(N::Gate)),checked_multiply(circuit.outputs.size(),4),checked_multiply(circuit.wire_count(),4),
  checked_multiply(tape_count,4),checked_multiply(bank_count,sizeof(State)),checked_multiply(frontier_count,sizeof(L::Leaf)),checked_multiply(gate_count,sizeof(GateTrace)),checked_multiply(evaluations,sizeof(StepTrace)),
  checked_multiply(child_count,sizeof(L::Branch)+sizeof(L::Diagnostic)+4),checked_multiply(word_count,sizeof(WordTrace)),checked_multiply(search_count,sizeof(SearchTrace))})required=checked_add(required,bytes);
 const u64 host_geometry=checked_add(checked_multiply(atlas,48),checked_multiply(n,sizeof(Lane)+sizeof(State)));
 if(required>budget||checked_add(required,host_geometry)>budget)throw std::runtime_error("resource_refused: complete joint snapshots/traces and geometry exceed selected memory ceiling");
 if(atlas>u64(INT_MAX)||atlas>u64(device.prop.maxTexture1DLinear))throw std::length_error("joint texture addressing capacity");
 Fixture fixture(Config{s,layout,Producer::provided,1},130,"source",u64(1)<<20);const auto atlas_info=load_packed_atlas(atlas_path,fixture);
 std::vector<uint4> packed(static_cast<std::size_t>(atlas));for(u32 r=0;r<s.padded_rows;++r)for(u32 w=0;w<s.padded_words;++w){
  const u32 at=address(s,r,w,layout);const auto v=make_uint4(fixture.masks[0][at],fixture.masks[1][at],fixture.masks[2][at],fixture.masks[3][at]);
  if(r<s.rows&&w<s.words){if(v.x!=7||v.y!=7||v.z!=6||v.w!=7)throw std::invalid_argument("joint atlas is not the compiled NOR-site predicate profile");}
  else if(v.x||v.y||v.z||v.w)throw std::invalid_argument("nonzero joint atlas padding");packed[at]=v;
 }
 const U::Tape initial_tape=encode(program.alphabet,origin,cells,program.initial_cells,fill);const auto seed=klein::canonical(seed_row,seed_angle,s.rows,s.angles);
 std::vector<L::Leaf> initial_frontier;if(seed_live)initial_frontier.push_back({seed_id,seed.row,seed.angle});const auto initial_emission=L::emit(initial_frontier,s);
 std::vector<State> initial_bank(static_cast<std::size_t>(n));for(u64 i=0;i<n;++i)initial_bank[i]={initial_emission[i],q};
 Download data;data.tapes.resize(static_cast<std::size_t>(tape_count));data.banks.resize(static_cast<std::size_t>(bank_count));data.frontiers.resize(static_cast<std::size_t>(frontier_count));
 data.gates.resize(static_cast<std::size_t>(gate_count));data.steps.resize(static_cast<std::size_t>(evaluations));data.branches.resize(static_cast<std::size_t>(child_count));data.diagnostics.resize(static_cast<std::size_t>(child_count));
 data.admitted.resize(static_cast<std::size_t>(child_count));data.words.resize(static_cast<std::size_t>(word_count));data.searches.resize(static_cast<std::size_t>(search_count));
 std::copy(initial_tape.words.begin(),initial_tape.words.end(),data.tapes.begin());std::copy(initial_bank.begin(),initial_bank.end(),data.banks.begin());std::copy(initial_frontier.begin(),initial_frontier.end(),data.frontiers.begin());
 Buffer<uint4> masks(packed.size());masks.upload(packed.data());Texture texture(masks.get(),packed.size());
 Buffer<N::Gate> gates(circuit.gates.size());gates.upload(circuit.gates.data());Buffer<u32> outputs(circuit.outputs.size());outputs.upload(circuit.outputs.data());Buffer<u32>wires(circuit.wire_count());
 Buffer<u32> tapes(data.tapes.size());tapes.upload(data.tapes.data());Buffer<State> banks(data.banks.size());banks.upload(data.banks.data());Buffer<L::Leaf> frontiers(data.frontiers.size());frontiers.upload(data.frontiers.data());
 Buffer<GateTrace> gate_records(data.gates.size());Buffer<StepTrace> step_records(data.steps.size());Buffer<L::Branch> branches(data.branches.size());Buffer<L::Diagnostic> diagnostics(data.diagnostics.size());
 Buffer<u32> admitted(data.admitted.size());Buffer<WordTrace> words(data.words.size());Buffer<SearchTrace> searches(data.searches.size());Buffer<ResultTrace> result(1);
 gate_records.upload(data.gates.data());step_records.upload(data.steps.data());branches.upload(data.branches.data());diagnostics.upload(data.diagnostics.data());admitted.upload(data.admitted.data());words.upload(data.words.data());searches.upload(data.searches.data());
 const CircuitView view{gates.get(),outputs.get(),u32(circuit.gates.size()),circuit.input_count,circuit.control_bits,circuit.symbol_bits,program.states,program.alphabet};
 AO_CUDA(cudaFuncSetAttribute(atomos_sdf_joint,cudaFuncAttributePreferredSharedMemoryCarveout,cudaSharedmemCarveoutMaxL1));cudaFuncAttributes attributes{};AO_CUDA(cudaFuncGetAttributes(&attributes,atomos_sdf_joint));
 Event begin,end;AO_CUDA(cudaEventRecord(begin.get()));
 atomos_sdf_joint<<<1,32>>>(view,s,layout,texture.get(),steps,cap,u32(initial_frontier.size()),{program.initial_state,program.initial_head},origin,cells,tape_words,initial_tape.bits,
  base_phi,j,k,profile,interval,injection=="gate"?1:injection=="word"?2:0,wires.get(),tapes.get(),banks.get(),frontiers.get(),gate_records.get(),step_records.get(),branches.get(),diagnostics.get(),admitted.get(),words.get(),searches.get(),result.get());
 AO_CUDA(cudaGetLastError());AO_CUDA(cudaEventRecord(end.get()));AO_CUDA(cudaEventSynchronize(end.get()));float kernel_ms=0;AO_CUDA(cudaEventElapsedTime(&kernel_ms,begin.get(),end.get()));
 result.download(&data.result);if(data.result.steps>steps||data.result.evaluations>evaluations||data.result.frontier_count>cap)throw std::runtime_error("joint GPU counters exceed allocated extents");
 tapes.download(data.tapes.data());banks.download(data.banks.data());frontiers.download(data.frontiers.data());gate_records.download(data.gates.data());step_records.download(data.steps.data());
 branches.download(data.branches.data());diagnostics.download(data.diagnostics.data());admitted.download(data.admitted.data());words.download(data.words.data());searches.download(data.searches.data());
 for(u32 i=0;i<data.result.evaluations;++i){const auto&r=data.steps[i];if(r.applied>1||r.before_count>cap||r.after_count>cap||r.children>cap||r.searches>u64(cap)+2)throw std::runtime_error("joint GPU trace count exceeds allocation");}
 const Audit audit=verify_joint(data,program,circuit,fixture,packed,initial_tape,initial_frontier,initial_bank,steps,cap,base_phi,j,k,profile,interval,fill);
 const auto stop=data.result.stop;const bool completed=stop==Stop::running||stop==Stop::halted;
 const bool resource=stop==Stop::frontier_cap||stop==Stop::lineage_overflow||stop==Stop::hinge_overflow;
 const std::string status=!audit.passed?"rejected_verification":completed?"passed":resource?"resource_refused":"program_refused";
 const u32 committed_steps=audit.passed?data.result.steps:0,committed_count=audit.passed?data.result.frontier_count:u32(initial_frontier.size());
 const U::Machine committed_machine=audit.passed?data.result.machine:U::Machine{program.initial_state,program.initial_head};
 staging=out_path;staging+=std::string(".partial_")+std::to_string(std::chrono::steady_clock::now().time_since_epoch().count());if(!fs::create_directories(staging))throw std::runtime_error("staging directory exists");
 fs::copy_file(program_path,staging/"program.atomos");fs::copy_file(atlas_path,staging/"operators.atlas");auto manifest=atlas_path;manifest.replace_extension(".json");if(fs::is_regular_file(manifest))fs::copy_file(manifest,staging/"operators.json");circuit_file(staging/"circuit.json",circuit);
 snapshot_data_files(staging,"before",initial_tape.words.data(),initial_bank.data(),initial_frontier.data(),u32(initial_frontier.size()),n,tape_words);
 snapshot_files(staging,"candidate",data,data.result.steps,data.result.frontier_count,n,tape_words,cap);
 if(audit.passed)snapshot_files(staging,"committed",data,committed_steps,committed_count,n,tape_words,cap);
 else snapshot_data_files(staging,"committed",initial_tape.words.data(),initial_bank.data(),initial_frontier.data(),u32(initial_frontier.size()),n,tape_words);
 u32 snapshot=0;for(u32 i=0;i<data.result.evaluations;++i){export_step(staging/("step_"+std::to_string(i)),data,i,snapshot,u32(circuit.gates.size()),cap,n,tape_words,interval);snapshot+=data.steps[i].applied;}
 if(snapshot!=data.result.steps)throw std::runtime_error("joint trace does not bind to final snapshot");
 std::ostringstream summary;summary<<std::setprecision(17)<<"{\"schema\":\"atomOS-sdf-joint-v1\",\"concept_author\":\"Tom Klootwijk\",\"profile\":\"new-finite-NOR-controlled-Klein-lineage-v1\",\"status\":"<<json_string(status)
  <<",\"candidate_verified\":"<<(audit.passed?"true":"false")<<",\"run_completed\":"<<(audit.passed&&completed?"true":"false")<<",\"program_stop\":"<<json_string(stop_name(stop))<<",\"reference_stop\":"<<json_string(stop_name(audit.stop))
  <<",\"steps_budget\":"<<steps<<",\"executed_steps\":"<<data.result.steps<<",\"evaluations\":"<<data.result.evaluations<<",\"committed_steps\":"<<committed_steps<<",\"max_frontier\":"<<cap
  <<",\"before\":"<<machine_json({program.initial_state,program.initial_head})<<",\"candidate\":"<<machine_json(data.result.machine)<<",\"committed\":"<<machine_json(committed_machine)
  <<",\"before_frontier_count\":"<<initial_frontier.size()<<",\"candidate_frontier_count\":"<<data.result.frontier_count<<",\"committed_frontier_count\":"<<committed_count
  <<",\"rows\":"<<s.rows<<",\"angles\":"<<s.angles<<",\"words\":"<<s.words<<",\"padded_rows\":"<<s.padded_rows<<",\"padded_words\":"<<s.padded_words<<",\"layout\":"<<json_string(layout_name)
  <<",\"atlas_file_bytes\":"<<atlas_info.file_bytes<<",\"atlas_texture_bytes\":"<<16*atlas<<",\"topology\":\"klein_m1_angular_twist\",\"operator_source\":\"loaded-SDF-predicate-atlas\",\"runtime_rule_table\":false"
  <<",\"controller_coupling\":\"phi_steps = base_phi_steps * (1 + decoded.write)\",\"base_phi_steps\":"<<base_phi<<",\"empty_frontier_policy\":\"continue controller and every word JK update\""
  <<",\"seed\":{\"id\":"<<seed_id<<",\"live\":"<<seed_live<<",\"lifted_row\":"<<seed_row<<",\"lifted_angle\":"<<seed_angle<<",\"row\":"<<seed.row<<",\"angle\":"<<seed.angle<<",\"parity\":"<<seed.parity<<'}'
  <<",\"q_initial\":"<<q<<",\"j\":"<<j<<",\"k\":"<<k<<",\"interval\":"<<interval<<",\"time_before\":0,\"time_candidate\":"<<double(data.result.steps)*interval<<",\"time_committed\":"<<double(committed_steps)*interval
  <<",\"diagnostic_profile\":"<<json_string(profile_name)<<",\"origin\":"<<origin<<",\"cells\":"<<cells<<",\"tail_fill\":"<<fill<<",\"control_bits\":"<<circuit.control_bits<<",\"symbol_bits\":"<<circuit.symbol_bits<<",\"circuit_gates\":"<<circuit.gates.size()<<",\"circuit_wires\":"<<circuit.wire_count()
  <<",\"search_organization\":\"sorted-array binary search / implicit balanced BST\",\"child_ids\":\"2*positive_parent_id+branch\",\"collision_policy\":\"admit every child ID whose packed cell survives\",\"commit_scope\":\"all verified earlier joint steps as one candidate prefix; verification failure restores initial state\",\"injection\":"<<json_string(injection)
  <<",\"verification\":{\"passed\":"<<(audit.passed?"true":"false")<<",\"checks\":"<<audit.checks<<",\"gates_checked\":"<<audit.gates<<",\"words_checked\":"<<audit.words<<",\"children_checked\":"<<audit.children<<",\"searches_checked\":"<<audit.searches<<'}'
  <<",\"device\":"<<device_record(device)<<",\"device_payload_bytes\":"<<required<<",\"host_geometry_bytes\":"<<host_geometry<<",\"memory_budget_bytes\":"<<budget<<",\"reserve_bytes\":"<<reserve
  <<",\"kernel_launches\":1,\"active_threads\":1,\"block_threads\":32,\"kernel_ms\":"<<kernel_ms<<",\"timing_scope\":\"one CUDA kernel: full TEX warm, sequential coupled controller/lineage/word/JK/tape/search steps with complete snapshots, full TEX reread; excludes transfers, CPU verification and export\""
  <<",\"texture_reads\":{\"warm\":"<<atlas<<",\"gates\":"<<u64(data.result.evaluations)*circuit.gates.size()<<",\"filter\":"<<u64(data.result.steps)*n<<",\"reread\":"<<atlas<<",\"total\":"<<2*atlas+u64(data.result.evaluations)*circuit.gates.size()+u64(data.result.steps)*n<<'}'
  <<",\"sm_before\":"<<data.result.sm_before<<",\"sm_after\":"<<data.result.sm_after<<",\"warm_checksum\":"<<checksum_json(data.result.warm)<<",\"reread_checksum\":"<<checksum_json(data.result.reread)
  <<",\"registers_per_thread\":"<<attributes.numRegs<<",\"local_bytes_per_thread\":"<<attributes.localSizeBytes<<",\"static_shared_bytes\":"<<attributes.sharedSizeBytes
  <<",\"cache_residency\":\"requires hardware counters for this joint kernel\",\"universality_scope\":\"separate programmable-controller embedding theorem; this run is a finite resource-bounded demonstration\",\"tape_addressing\":\"nonaliasing signed logical addresses separate from immutable operator texture\""
  <<",\"abi\":{\"gate\":"<<sizeof(N::Gate)<<",\"gate_trace\":"<<sizeof(GateTrace)<<",\"step_trace\":"<<sizeof(StepTrace)<<",\"result_trace\":"<<sizeof(ResultTrace)<<",\"word_trace\":"<<sizeof(WordTrace)<<",\"search_trace\":"<<sizeof(SearchTrace)<<",\"leaf\":"<<sizeof(L::Leaf)<<",\"branch\":"<<sizeof(L::Branch)<<",\"diagnostic\":"<<sizeof(L::Diagnostic)<<",\"state\":"<<sizeof(State)<<"}}\n";
 text_file(staging/"summary.json",summary.str());text_file(staging/(audit.passed?(completed?"COMMITTED":"PREFIX_VERIFIED"):"REJECTED"),audit.passed?"The complete proposed joint prefix was independently verified before commit.\n":"Verification rejected the complete proposal; all committed state is the initial state.\n");
 if(fs::exists(out_path))throw std::runtime_error("output path appeared before publication");fs::rename(staging,out_path);staging.clear();std::cout<<summary.str();return !audit.passed?2:completed?0:resource?3:2;
 }catch(const std::exception&e){std::cerr<<"atomOS joint error: "<<e.what()<<'\n';if(!staging.empty())std::cerr<<"Uncommitted records: "<<staging.string()<<'\n';return dynamic_cast<const std::length_error*>(&e)||std::string(e.what()).find("resource_refused")!=std::string::npos?3:1;}}
