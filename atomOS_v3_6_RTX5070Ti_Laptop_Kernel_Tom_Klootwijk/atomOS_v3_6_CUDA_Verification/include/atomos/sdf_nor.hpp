#pragma once
// Tom Klootwijk atomOS, new explicit SDF/NOR controller compilation profile.
// Program tables are compiler inputs. Only NOR wiring is supplied to the GPU.
#include "atomos/universal.hpp"
#include <array>
#include <map>

namespace atomos { namespace sdf_nor {
struct Gate {u32 left=0,right=0;};
static_assert(sizeof(Gate)==8,"NOR wire ABI");
struct Decoded {u32 next=0,write=0;int move=0;u32 defined=0,halt_current=0,halt_after=0;};

// The actual source whole-word absorption computes this gate, rather than a
// separate Boolean opcode. Candidate assembly supplies the constant output token.
AO_HD inline u32 source_gate(u32 a,u32 b,u32 am,u32 nm,u32 boundary,u32 fringe){
 const u32 candidate=1u|(a<<1u)|(b<<2u);Lane lane{};State state{};
 return word_step(candidate,am,nm,boundary,0xffffffffu,fringe,state,lane).output&1u;
}
struct Circuit {
 u32 states=0,alphabet=0,control_bits=0,symbol_bits=0,input_count=0;
 std::vector<Gate> gates;
 // next-control bits, write-symbol bits, left,right,defined,halt-current,halt-after.
 std::vector<u32> outputs;
 u32 wire_count()const{
  if(gates.size()>UINT32_MAX-input_count)throw std::length_error("NOR signal index overflow");
  return input_count+u32(gates.size());
 }
 void validate()const{
  if(!states||!alphabet||control_bits!=universal::symbol_bits(states)||symbol_bits!=universal::symbol_bits(alphabet)||
     input_count!=control_bits+symbol_bits+1||outputs.size()!=control_bits+symbol_bits+5||gates.empty())
   throw std::invalid_argument("invalid NOR controller metadata");
  const auto count=wire_count();
  for(std::size_t i=0;i<gates.size();++i)if(gates[i].left>=input_count+i||gates[i].right>=input_count+i)
   throw std::invalid_argument("NOR circuit contains a forward/cyclic wire");
  for(u32 output:outputs)if(output>=count)throw std::invalid_argument("NOR output outside circuit");
 }
};

class Builder {
 Circuit circuit_;
 std::map<std::pair<u32,u32>,u32> shared_;
 u64 limit_;
public:
 u32 zero,one;
 Builder(u32 states,u32 alphabet,u64 max_gates):limit_(max_gates){
  circuit_.states=states;circuit_.alphabet=alphabet;
  circuit_.control_bits=universal::symbol_bits(states);circuit_.symbol_bits=universal::symbol_bits(alphabet);
  circuit_.input_count=circuit_.control_bits+circuit_.symbol_bits+1;
  zero=circuit_.input_count-1;one=nor(zero,zero);
 }
 u32 nor(u32 left,u32 right){
  if(left>=circuit_.wire_count()||right>=circuit_.wire_count())throw std::invalid_argument("NOR input not yet defined");
  if(right<left)std::swap(left,right);const auto key=std::make_pair(left,right);
  const auto existing=shared_.find(key);if(existing!=shared_.end())return existing->second;
  if(circuit_.gates.size()>=limit_||circuit_.gates.size()>=UINT32_MAX-circuit_.input_count)
   throw std::length_error("compiled NOR controller exceeds declared gate/storage budget");
  const u32 result=circuit_.wire_count();circuit_.gates.push_back({left,right});shared_.emplace(key,result);return result;
 }
 u32 invert(u32 a){return nor(a,a);}
 u32 either(u32 a,u32 b){return invert(nor(a,b));}
 u32 both(u32 a,u32 b){return nor(invert(a),invert(b));}
 u32 any(std::vector<u32> signals){
  if(signals.empty())return zero;
  while(signals.size()>1){std::vector<u32> next;next.reserve((signals.size()+1)/2);
   for(std::size_t i=0;i<signals.size();i+=2)next.push_back(i+1<signals.size()?either(signals[i],signals[i+1]):signals[i]);
   signals.swap(next);
  }return signals[0];
 }
 u32 equal_bits(u32 first,u32 count,u32 value){
  std::vector<u32> mismatch;mismatch.reserve(count);
  for(u32 bit=0;bit<count;++bit)mismatch.push_back((value>>bit)&1u?invert(first+bit):first+bit);
  // Bind predicate truth to the explicitly computed NOR constant signal too.
  return both(invert(any(std::move(mismatch))),one);
 }
 Circuit finish(std::vector<u32> outputs){circuit_.outputs=std::move(outputs);circuit_.validate();return std::move(circuit_);}
};

inline Circuit compile(const universal::Program&program,u64 max_gates,u64 temporary_budget=UINT64_MAX){
 program.validate();
 const u32 qb=universal::symbol_bits(program.states),sb=universal::symbol_bits(program.alphabet);
 // Count every output-list entry before allocating compiler scratch storage.
 // Dense tables were separately admitted by the program loader. The 128 bytes
 // per gate is a conservative implementation budget for wires and map nodes;
 // allocation failure remains an explicit pre-execution error.
 std::vector<u64> term_counts(qb+sb+5,0);
 const u32 left=qb+sb,right=left+1,defined=left+2,halt_current=left+3,halt_after=left+4;
 for(u32 q=0;q<program.states;++q){
  if(program.halt[q]){++term_counts[halt_current];continue;}
  for(u32 a=0;a<program.alphabet;++a){const auto&rule=program.rules[std::size_t(u64(q)*program.alphabet+a)];if(!rule.defined)continue;
   ++term_counts[defined];for(u32 bit=0;bit<qb;++bit)if((rule.next>>bit)&1u)++term_counts[bit];
   for(u32 bit=0;bit<sb;++bit)if((rule.write>>bit)&1u)++term_counts[qb+bit];
   if(rule.move<0)++term_counts[left];if(rule.move>0)++term_counts[right];if(program.halt[rule.next])++term_counts[halt_after];
  }
 }
 u64 total_terms=0;for(u64 count:term_counts){if(count>UINT64_MAX-total_terms)throw std::length_error("NOR compiler term count overflow");total_terms+=count;}
 const u64 other_scratch=(u64(program.states)+program.alphabet)*4+u64(qb+sb+5)*64;
 if(total_terms>(UINT64_MAX-other_scratch)/8)throw std::length_error("NOR compiler scratch byte overflow");
 const u64 fixed_scratch=other_scratch+total_terms*8;
 if(fixed_scratch>temporary_budget||temporary_budget-fixed_scratch<128)throw std::length_error("NOR compiler scratch exceeds declared memory budget");
 max_gates=std::min(max_gates,(temporary_budget-fixed_scratch)/128);
 Builder builder(program.states,program.alphabet,max_gates);
 std::vector<u32> controls(program.states),symbols(program.alphabet);
 for(u32 q=0;q<program.states;++q)controls[q]=builder.equal_bits(0,qb,q);
 for(u32 a=0;a<program.alphabet;++a)symbols[a]=builder.equal_bits(qb,sb,a);
 std::vector<std::vector<u32>> terms(qb+sb+5);
 for(std::size_t i=0;i<terms.size();++i){if(term_counts[i]>terms[i].max_size())throw std::length_error("NOR compiler output-list capacity");terms[i].reserve(std::size_t(term_counts[i]));}
 for(u32 q=0;q<program.states;++q){
  if(program.halt[q]){terms[halt_current].push_back(controls[q]);continue;}
  for(u32 a=0;a<program.alphabet;++a){
   const auto&rule=program.rules[std::size_t(u64(q)*program.alphabet+a)];if(!rule.defined)continue;
   const u32 active=builder.both(controls[q],symbols[a]);terms[defined].push_back(active);
   for(u32 bit=0;bit<qb;++bit)if((rule.next>>bit)&1u)terms[bit].push_back(active);
   for(u32 bit=0;bit<sb;++bit)if((rule.write>>bit)&1u)terms[qb+bit].push_back(active);
   if(rule.move<0)terms[left].push_back(active);if(rule.move>0)terms[right].push_back(active);
   if(program.halt[rule.next])terms[halt_after].push_back(active);
  }
 }
 std::vector<u32> outputs;outputs.reserve(terms.size());
 for(auto&set:terms)outputs.push_back(builder.any(std::move(set)));
 return builder.finish(std::move(outputs));
}

inline std::vector<u32> evaluate(const Circuit&circuit,u32 control,u32 symbol){
 circuit.validate();if(control>=circuit.states||symbol>=circuit.alphabet)throw std::invalid_argument("NOR controller input domain");
 std::vector<u32> values(circuit.wire_count(),0);
 for(u32 bit=0;bit<circuit.control_bits;++bit)values[bit]=(control>>bit)&1u;
 for(u32 bit=0;bit<circuit.symbol_bits;++bit)values[circuit.control_bits+bit]=(symbol>>bit)&1u;
 // Independent Boolean gate oracle: no masks, packed atlas or source word helper.
 for(std::size_t i=0;i<circuit.gates.size();++i){const auto&gate=circuit.gates[i];values[circuit.input_count+i]=(values[gate.left]||values[gate.right])?0u:1u;}
 return values;
}

AO_HD inline Decoded decode(const u32*values,const u32*outputs,u32 qb,u32 sb){
 Decoded result{};
 for(u32 bit=0;bit<qb;++bit)result.next|=values[outputs[bit]]<<bit;
 for(u32 bit=0;bit<sb;++bit)result.write|=values[outputs[qb+bit]]<<bit;
 const u32 offset=qb+sb,left=values[outputs[offset]],right=values[outputs[offset+1]];
 result.move=left&&right?2:int(right)-int(left);result.defined=values[outputs[offset+2]];
 result.halt_current=values[outputs[offset+3]];result.halt_after=values[outputs[offset+4]];return result;
}
inline Decoded evaluate_decoded(const Circuit&circuit,u32 control,u32 symbol){
 const auto values=evaluate(circuit,control,symbol);return decode(values.data(),circuit.outputs.data(),circuit.control_bits,circuit.symbol_bits);
}
inline bool equal_decoded(const Decoded&a,const Decoded&b){
 return a.next==b.next&&a.write==b.write&&a.move==b.move&&a.defined==b.defined&&a.halt_current==b.halt_current&&a.halt_after==b.halt_after;
}
inline Decoded table_oracle(const universal::Program&p,u32 control,u32 symbol){
 if(control>=p.states||symbol>=p.alphabet)throw std::invalid_argument("table oracle input domain");
 Decoded result{};result.halt_current=p.halt[control];if(result.halt_current)return result;
 const auto&rule=p.rules[std::size_t(u64(control)*p.alphabet+symbol)];if(!rule.defined)return result;
 result.next=rule.next;result.write=rule.write;result.move=rule.move;result.defined=1;result.halt_after=p.halt[rule.next];return result;
}
}} // atomos::sdf_nor
