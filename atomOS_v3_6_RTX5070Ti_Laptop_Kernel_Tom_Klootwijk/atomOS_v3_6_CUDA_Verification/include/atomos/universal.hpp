#pragma once
// Tom Klootwijk atomOS: explicit optional U machine, source M1 pp. 31-32.
// A finite allocation executes a checked prefix of the logical tape machine.
#include "atomos/core.hpp"
#include <charconv>
#include <filesystem>
#include <fstream>
#include <limits>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace atomos { namespace universal {
using i64=std::int64_t;
using Cells=std::map<i64,u32>;
enum class Stop:u32 {running=0,halted=1,missing_rule=2,tape_range=3,invalid=4};
struct Rule {u32 next=0,write=0;int move=0;u32 defined=0;};
struct Machine {u32 control=0;i64 head=0;};
struct Step {
 u32 control_before=0,control_after=0,read=0,write=0;
 i64 head_before=0,head_after=0;
 std::int32_t move=0;
};
static_assert(sizeof(Rule)==16 && sizeof(Machine)==16 && sizeof(Step)==40,"U machine ABI");
struct PackedTapeView {u32*words=nullptr;u64 cells=0;i64 origin=0;u32 bits=0,alphabet=0;};

AO_HD inline bool valid_extent(i64 origin,u64 cells){
 return cells!=0 && cells-1<=u64(INT64_MAX)-u64(origin);
}
AO_HD inline bool contains(const PackedTapeView&t,i64 position){
 return position>=t.origin && u64(position)-u64(t.origin)<t.cells;
}
AO_HD inline u32 symbol_mask(u32 bits){return bits==32?0xffffffffu:(u32(1)<<bits)-1;}
AO_HD inline bool packed_read(const PackedTapeView&t,i64 position,u32&symbol){
 if(!t.words||!contains(t,position)||!t.alphabet||!t.bits||t.bits>32)return false;
 const u64 index=u64(position)-u64(t.origin);
 if(index>UINT64_MAX/t.bits)return false;
 const u64 offset=index*t.bits,word=offset>>5;
 const u32 shift=u32(offset&31);
 u32 value=t.words[word]>>shift;
 if(shift+t.bits>32)value|=(t.words[word+1]&symbol_mask(shift+t.bits-32))<<(32-shift);
 value&=symbol_mask(t.bits);
 if(value>=t.alphabet)return false;
 symbol=value;return true;
}
AO_HD inline bool packed_write(const PackedTapeView&t,i64 position,u32 symbol){
 if(!t.words||!contains(t,position)||!t.alphabet||symbol>=t.alphabet||!t.bits||t.bits>32)return false;
 const u64 index=u64(position)-u64(t.origin);
 if(index>UINT64_MAX/t.bits)return false;
 const u64 offset=index*t.bits,word=offset>>5;
 const u32 shift=u32(offset&31),mask=symbol_mask(t.bits)<<shift;
 t.words[word]=(t.words[word]&~mask)|((symbol<<shift)&mask);
 if(shift+t.bits>32){
  const u32 high_mask=symbol_mask(shift+t.bits-32);
  t.words[word+1]=(t.words[word+1]&~high_mask)|((symbol>>(32-shift))&high_mask);
 }
 return true;
}
inline u32 symbol_bits(u32 alphabet){
 if(!alphabet)throw std::invalid_argument("U alphabet must contain blank symbol zero");
 u32 bits=0;for(u32 largest=alphabet-1;largest;largest>>=1)++bits;
 return bits?bits:1;
}
struct Tape {
 std::vector<u32> words;
 i64 origin=0;u64 cells=0;u32 alphabet=0,bits=0;
 Tape(u32 symbols,i64 first,u64 count):origin(first),cells(count),alphabet(symbols),bits(symbol_bits(symbols)){
  if(!valid_extent(origin,cells))throw std::invalid_argument("U tape extent exceeds signed address range or is empty");
  if(cells>(UINT64_MAX-31)/bits)throw std::length_error("U tape bit count overflow");
  const u64 count_words=(cells*bits+31)/32;
  if(count_words>words.max_size())throw std::length_error("U tape exceeds host vector capacity");
  words.assign(std::size_t(count_words),0);
 }
 PackedTapeView view(){return {words.data(),cells,origin,bits,alphabet};}
 u32 get(i64 position)const{
  PackedTapeView t{const_cast<u32*>(words.data()),cells,origin,bits,alphabet};u32 symbol=0;
  if(!packed_read(t,position,symbol))throw std::out_of_range("U tape read outside extent or invalid symbol");
  return symbol;
 }
 void set(i64 position,u32 symbol){
  if(!packed_write(view(),position,symbol))throw std::out_of_range("U tape write outside extent or alphabet");
 }
 Cells nonzero_cells()const{
  Cells result;i64 position=origin;
  for(u64 i=0;i<cells;++i){const u32 value=get(position);if(value)result.emplace(position,value);if(i+1<cells)++position;}
  return result;
 }
};

struct Program {
 u32 states=0,alphabet=0,initial_state=0;i64 initial_head=0;
 std::vector<u32> halt;
 std::vector<Rule> rules;
 Cells initial_cells;
 void validate()const{
  if(!states||!alphabet)throw std::invalid_argument("U states and alphabet must be positive");
  if(initial_state>=states)throw std::invalid_argument("U initial state is outside declared states");
  if(halt.size()!=states||u64(rules.size())!=u64(states)*alphabet)throw std::invalid_argument("U halt/rule table dimensions disagree");
  for(u32 flag:halt)if(flag>1)throw std::invalid_argument("U halt flag must be zero or one");
  for(const Rule&r:rules){
   if(r.defined>1)throw std::invalid_argument("U rule defined flag must be zero or one");
   if(r.defined&&(r.next>=states||r.write>=alphabet||r.move< -1||r.move>1))throw std::invalid_argument("U rule is outside state/alphabet/move domains");
  }
  for(const auto&cell:initial_cells)if(cell.second>=alphabet)throw std::invalid_argument("U initial symbol is outside alphabet");
 }
};
struct TableResourceRefused:std::length_error {using std::length_error::length_error;};
inline u64 checked_table_bytes(u32 states,u32 alphabet,u64 maximum=UINT64_MAX){
 const u64 rule_count=u64(states)*alphabet,halt_bytes=u64(states)*sizeof(u32);
 if(rule_count>(UINT64_MAX-halt_bytes)/sizeof(Rule))throw TableResourceRefused("U table byte count overflow");
 const u64 bytes=rule_count*sizeof(Rule)+halt_bytes;
 if(bytes>maximum)throw TableResourceRefused("U table exceeds selected memory budget");
 return bytes;
}
namespace detail {
template<class T>inline T integer(const std::string&s){
 T value{};const auto result=std::from_chars(s.data(),s.data()+s.size(),value,10);
 if(result.ec!=std::errc()||result.ptr!=s.data()+s.size())throw std::invalid_argument("invalid decimal integer: "+s);
 return value;
}
inline void arity(const std::vector<std::string>&tokens,std::size_t expected){
 if(tokens.size()!=expected)throw std::invalid_argument("wrong number of fields for "+tokens.front());
}
}
inline Program parse_program(std::istream&stream,u64 max_table_bytes=UINT64_MAX){
 Program p;bool header=false,have_states=false,have_alphabet=false,have_start=false;
 struct Pending {u32 control,read;Rule rule;};std::vector<Pending> pending;std::vector<u32> halts;
 std::string line;u64 line_number=0;
 while(std::getline(stream,line)){
  ++line_number;const auto comment=line.find('#');if(comment!=std::string::npos)line.resize(comment);
  std::istringstream input(line);std::vector<std::string> tokens;std::string token;
  while(input>>token)tokens.push_back(token);if(tokens.empty())continue;
  try{
   if(!header){if(tokens.size()!=2||tokens[0]!="atomos-universal"||tokens[1]!="1")throw std::invalid_argument("expected atomos-universal 1 header");header=true;continue;}
   if(tokens[0]=="states"){
    detail::arity(tokens,2);if(have_states)throw std::invalid_argument("duplicate states declaration");have_states=true;p.states=detail::integer<u32>(tokens[1]);
   }else if(tokens[0]=="alphabet"){
    detail::arity(tokens,2);if(have_alphabet)throw std::invalid_argument("duplicate alphabet declaration");have_alphabet=true;p.alphabet=detail::integer<u32>(tokens[1]);
   }else if(tokens[0]=="start"){
    detail::arity(tokens,3);if(have_start)throw std::invalid_argument("duplicate start declaration");have_start=true;p.initial_state=detail::integer<u32>(tokens[1]);p.initial_head=detail::integer<i64>(tokens[2]);
   }else if(tokens[0]=="halt"){
    if(tokens.size()<2)throw std::invalid_argument("halt requires at least one state");
    for(std::size_t i=1;i<tokens.size();++i)halts.push_back(detail::integer<u32>(tokens[i]));
   }else if(tokens[0]=="cell"){
    detail::arity(tokens,3);const auto inserted=p.initial_cells.emplace(detail::integer<i64>(tokens[1]),detail::integer<u32>(tokens[2]));
    if(!inserted.second)throw std::invalid_argument("duplicate initial cell");
   }else if(tokens[0]=="rule"){
    detail::arity(tokens,6);int move=0;
    if(tokens[5]=="L")move=-1;else if(tokens[5]=="R")move=1;else if(tokens[5]!="S")throw std::invalid_argument("move must be L, S or R");
    pending.push_back({detail::integer<u32>(tokens[1]),detail::integer<u32>(tokens[2]),{detail::integer<u32>(tokens[3]),detail::integer<u32>(tokens[4]),move,1}});
   }else throw std::invalid_argument("unknown U directive: "+tokens[0]);
  }catch(const std::exception&e){throw std::invalid_argument("U program line "+std::to_string(line_number)+": "+e.what());}
 }
 if(stream.bad())throw std::runtime_error("cannot read U program");
 if(!header||!have_states||!have_alphabet||!have_start)throw std::invalid_argument("U program is missing required declarations");
 if(!p.states||!p.alphabet)throw std::invalid_argument("U states and alphabet must be positive");
 const u64 rule_count=u64(p.states)*p.alphabet;
 checked_table_bytes(p.states,p.alphabet,max_table_bytes);
 if(rule_count>p.rules.max_size()||p.states>p.halt.max_size())throw TableResourceRefused("U table exceeds host vector capacity");
 p.rules.resize(std::size_t(rule_count));p.halt.assign(p.states,0);
 for(u32 q:halts){if(q>=p.states)throw std::invalid_argument("U halt state outside declared states");if(p.halt[q])throw std::invalid_argument("duplicate U halt state");p.halt[q]=1;}
 for(const auto&entry:pending){
  if(entry.control>=p.states||entry.read>=p.alphabet)throw std::invalid_argument("U rule key outside declared domains");
  Rule&slot=p.rules[std::size_t(u64(entry.control)*p.alphabet+entry.read)];
  if(slot.defined)throw std::invalid_argument("duplicate U rule");slot=entry.rule;
 }
 p.validate();return p;
}
inline Program load_program(const std::filesystem::path&path,u64 max_table_bytes=UINT64_MAX){
 std::ifstream stream(path);if(!stream)throw std::runtime_error("cannot open U program: "+path.string());return parse_program(stream,max_table_bytes);
}
inline bool equal_machine(const Machine&a,const Machine&b){return a.control==b.control&&a.head==b.head;}
inline bool equal_step(const Step&a,const Step&b){
 return a.control_before==b.control_before&&a.control_after==b.control_after&&a.read==b.read&&a.write==b.write&&a.head_before==b.head_before&&a.head_after==b.head_after&&a.move==b.move;
}
inline Cells normalized_cells(const Cells&cells){Cells result;for(const auto&entry:cells)if(entry.second)result.insert(entry);return result;}
inline bool equal_cells(const Cells&a,const Cells&b){return normalized_cells(a)==normalized_cells(b);}
inline const char*stop_name(Stop stop){
 switch(stop){case Stop::running:return "running";case Stop::halted:return "halted";case Stop::missing_rule:return "missing_rule";case Stop::tape_range:return "tape_range";default:return "invalid";}
}
struct ReferenceRun {Machine machine;Cells cells;std::vector<Step> trace;Stop stop=Stop::running;};
// Independent sparse-map transition: no packed read/write helper is used here.
inline Stop reference_step(const Program&p,Machine&machine,Cells&cells,Step&step,i64 origin,u64 extent){
 step=Step{};
 if(!valid_extent(origin,extent))return Stop::invalid;
 if(machine.control>=p.states||p.halt.size()!=p.states||!p.alphabet)return Stop::invalid;
 if(machine.head<origin||u64(machine.head)-u64(origin)>=extent)return Stop::tape_range;
 if(p.halt[machine.control])return Stop::halted;
 const auto found=cells.find(machine.head);const u32 read=found==cells.end()?0:found->second;
 if(read>=p.alphabet)return Stop::invalid;
 const u64 index=u64(machine.control)*p.alphabet+read;if(index>=p.rules.size())return Stop::invalid;
 const Rule rule=p.rules[std::size_t(index)];if(!rule.defined)return Stop::missing_rule;
 if(rule.defined!=1||rule.next>=p.states||rule.write>=p.alphabet||rule.move< -1||rule.move>1)return Stop::invalid;
 if((rule.move<0&&machine.head==INT64_MIN)||(rule.move>0&&machine.head==INT64_MAX))return Stop::tape_range;
 const i64 destination=machine.head+rule.move;
 if(destination<origin||u64(destination)-u64(origin)>=extent)return Stop::tape_range;
 step={machine.control,rule.next,read,rule.write,machine.head,destination,rule.move};
 if(rule.write)cells[machine.head]=rule.write;else cells.erase(machine.head);
 machine={rule.next,destination};return p.halt[machine.control]?Stop::halted:Stop::running;
}
inline ReferenceRun reference_run(const Program&p,Machine initial,const Cells&initial_cells,u64 budget,i64 origin,u64 extent){
 p.validate();ReferenceRun result{initial,normalized_cells(initial_cells),{},Stop::running};
 if(!valid_extent(origin,extent)){result.stop=Stop::invalid;return result;}
 if(initial.control>=p.states){result.stop=Stop::invalid;return result;}
 if(initial.head<origin||u64(initial.head)-u64(origin)>=extent){result.stop=Stop::tape_range;return result;}
 for(const auto&entry:initial_cells){
  if(entry.second>=p.alphabet){result.stop=Stop::invalid;return result;}
  if(entry.first<origin||u64(entry.first)-u64(origin)>=extent){result.stop=Stop::tape_range;return result;}
 }
 if(p.halt[initial.control]){result.stop=Stop::halted;return result;}
 for(u64 i=0;i<budget;++i){
  Step step;const Stop stop=reference_step(p,result.machine,result.cells,step,origin,extent);
  if(stop==Stop::running||stop==Stop::halted)result.trace.push_back(step);
  result.stop=stop;if(stop!=Stop::running)break;
 }
 return result;
}
inline ReferenceRun reference_run(const Program&p,u64 budget,i64 origin,u64 extent){
 return reference_run(p,{p.initial_state,p.initial_head},p.initial_cells,budget,origin,extent);
}
}}
