#include "atomos/sdf_nor.hpp"
#include <iostream>
using namespace atomos;
namespace U=atomos::universal;
namespace N=atomos::sdf_nor;
static u64 assertions=0;
static void require(bool value,const char*message){++assertions;if(!value)throw std::runtime_error(message);}
template<class F>static void rejects(F action){bool rejected=false;try{action();}catch(const std::exception&){rejected=true;}require(rejected,"invalid NOR circuit was accepted");}
static U::Program program(const std::string&text){std::istringstream stream(text);return U::parse_program(stream);}
static void exhaustive_controller(const U::Program&p){
 const auto circuit=N::compile(p,1000000);circuit.validate();require(!circuit.gates.empty(),"no NOR gates compiled");
 require(circuit.gates[0].left==circuit.input_count-1&&circuit.gates[0].right==circuit.input_count-1,"constant marker gate missing");
 for(u32 q=0;q<p.states;++q)for(u32 symbol=0;symbol<p.alphabet;++symbol){
  const auto wires=N::evaluate(circuit,q,symbol);const auto decoded=N::decode(wires.data(),circuit.outputs.data(),circuit.control_bits,circuit.symbol_bits);
  require(N::equal_decoded(decoded,N::table_oracle(p,q,symbol)),"compiled NOR controller differs from supplied finite transition function");
  for(std::size_t index=0;index<circuit.gates.size();++index){const auto&gate=circuit.gates[index];
   require(wires[circuit.input_count+index]==N::source_gate(wires[gate.left],wires[gate.right],7,7,6,7),"source ASA gate differs from independent NOR oracle");
  }
 }
 rejects([&]{N::evaluate(circuit,p.states,0);});rejects([&]{N::evaluate(circuit,0,p.alphabet);});
 auto bad=circuit;bad.gates[0].left=bad.input_count;rejects([&]{bad.validate();});
 bad=circuit;bad.outputs[0]=bad.wire_count();rejects([&]{bad.validate();});
 rejects([&]{N::compile(p,1);});
 rejects([&]{N::compile(p,1000000,127);});
}
int main(int argc,char**argv){try{
 for(u32 a=0;a<2;++a)for(u32 b=0;b<2;++b){
  require(N::source_gate(a,b,7,7,6,7)==u32(!(a||b)),"whole-word ASA does not implement NOR");
  const u32 x=1u|(a<<1u)|(b<<2u);Lane lane{};State state{};
  const auto word=word_step(x,7,7,6,0xffffffffu,7,state,lane);
  require(word.output==u32(!(a||b)),"NOR gate leaves unintended output support");
 }
 require(N::source_gate(1,0,7,7,0,7)==1,"removing SDF blocking predicate did not change gate");
 require(N::source_gate(0,0,6,7,6,7)==0,"removing SDF output marker did not change gate");
 {const auto p=program("atomos-universal 1\nstates 2\nalphabet 2\nstart 0 0\nhalt 1\nrule 0 0 1 1 S\n");
  const auto circuit=N::compile(p,100000);auto values=N::evaluate(circuit,0,0);
  require(N::decode(values.data(),circuit.outputs.data(),circuit.control_bits,circuit.symbol_bits).defined==1,"declared rule not selected");
  for(std::size_t i=0;i<circuit.gates.size();++i){const auto&g=circuit.gates[i];values[circuit.input_count+i]=(values[g.left]||values[g.right])?0u:1u;if(i==0)values[circuit.input_count+i]^=1u;}
  require(N::decode(values.data(),circuit.outputs.data(),circuit.control_bits,circuit.symbol_bits).defined==0,"changed NOR operator did not affect transition selection");
 }
 for(u32 alphabet:{1u,2u,3u,5u,33u})for(u32 seed=0;seed<5;++seed){
  U::Program p;p.states=7;p.alphabet=alphabet;p.initial_state=0;p.initial_head=-3;
  p.halt.assign(p.states,0);p.halt[6]=1;p.rules.resize(std::size_t(p.states)*alphabet);
  for(u32 q=0;q<p.states;++q)for(u32 symbol=0;symbol<alphabet;++symbol){
   const u32 hash=mix32(seed*0x9e3779b9u+q*3911u+symbol*17u);
   p.rules[std::size_t(q)*alphabet+symbol]={hash%p.states,mix32(hash)%alphabet,int((hash>>9)%3)-1,u32(hash%11!=0)};
  }p.validate();exhaustive_controller(p);
 }
 const auto examples=argc>1?std::filesystem::path(argv[1]):std::filesystem::path(__FILE__).parent_path().parent_path()/"examples"/"universal";
 for(const char*name:{"binary_increment.atomos","replace_symbol.atomos","unary_increment.atomos","erase.atomos","left_cross_origin.atomos","nonhalting_walker.atomos","missing_rule.atomos","bounded_oscillator.atomos"})
  exhaustive_controller(U::load_program(examples/name));
 std::cout<<"RESULT sdf_nor: "<<assertions<<" assertions passed\n";return 0;
}catch(const std::exception&e){std::cerr<<"FAIL sdf_nor after "<<assertions<<" assertions: "<<e.what()<<'\n';return 1;}}
