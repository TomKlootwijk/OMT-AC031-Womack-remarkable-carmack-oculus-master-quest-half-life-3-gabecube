#include "atomos/universal.hpp"
#include <algorithm>
#include <iostream>
using namespace atomos;
using namespace atomos::universal;
static u64 assertions=0;
static void require(bool condition,const char*message){++assertions;if(!condition)throw std::runtime_error(message);}
template<class F>static void rejects(F function){bool rejected=false;try{function();}catch(const std::exception&){rejected=true;}require(rejected,"expected invalid U input to reject");}
static Program parse(const std::string&text){std::istringstream stream(text);return parse_program(stream);}
static void packed_tests(){
 for(u32 alphabet:{1u,2u,3u,5u,33u,257u,65537u,0xffffffffu}){
  Tape tape(alphabet,-47,139);std::fill(tape.words.begin(),tape.words.end(),0xa5a5a5a5u);
  auto expected=tape.words;
  // Independent single-bit packer preserves every bit outside the written field.
  const auto write_reference=[&](u64 index,u32 symbol){for(u32 bit=0;bit<tape.bits;++bit){const u64 address=index*tape.bits+bit;const u32 mask=1u<<u32(address%32);if((symbol>>bit)&1u)expected[std::size_t(address/32)]|=mask;else expected[std::size_t(address/32)]&=~mask;}};
  for(u64 i=0;i<tape.cells;++i){tape.set(tape.origin+i64(i),0);write_reference(i,0);}
  for(u32 i=0;i<2000;++i){const u64 index=mix32(i+53)%tape.cells;const u32 symbol=mix32(i+199)%alphabet;tape.set(tape.origin+i64(index),symbol);write_reference(index,symbol);require(tape.words==expected,"packed crossword write changed a neighbor/padding bit");require(tape.get(tape.origin+i64(index))==symbol,"packed symbol did not roundtrip");}
  for(u64 i=0;i<tape.cells;++i){u32 value=0;for(u32 bit=0;bit<tape.bits;++bit){const u64 address=i*tape.bits+bit;value|=((expected[std::size_t(address/32)]>>u32(address%32))&1u)<<bit;}require(tape.get(tape.origin+i64(i))==value,"independent bit read differs");}
  const auto before=tape.words;require(!packed_write(tape.view(),-48,0),"left out-of-range write accepted");require(!packed_write(tape.view(),92,0),"right out-of-range write accepted");require(!packed_write(tape.view(),0,alphabet),"invalid symbol accepted");require(tape.words==before,"failed packed write changed tape");
  u32 untouched=123;require(!packed_read(tape.view(),-48,untouched)&&untouched==123,"failed read changed output");
 }
 Tape low(5,INT64_MIN,3);low.set(INT64_MIN,4);low.set(INT64_MIN+2,3);require(low.get(INT64_MIN)==4&&low.get(INT64_MIN+2)==3,"minimum signed origin");
 Tape high(5,INT64_MAX-2,3);high.set(INT64_MAX,4);require(high.get(INT64_MAX)==4,"maximum signed cell");
 rejects([]{Tape t(0,0,2);});rejects([]{Tape t(2,0,0);});rejects([]{Tape t(2,INT64_MAX,2);});rejects([]{Tape t(0xffffffffu,INT64_MIN,UINT64_MAX);});
}
static void parser_tests(){
 const std::string prefix="atomos-universal 1\nstates 2\nalphabet 3\nstart 0 -1\nhalt 1\n";
 Program p=parse(prefix+"# editable program\ncell -1 2\nrule 0 2 1 1 S\n");require(p.initial_head==-1&&p.rules[2].defined&&p.rules[2].write==1,"parse program fields");p.validate();
 for(const std::string&suffix:{"states 2\n","alphabet 3\n","start 0 0\n","halt 1\n","cell 0 1\ncell 0 0\n","rule 0 0 0 0 S\nrule 0 0 1 0 S\n","rule 0 0 2 0 S\n","rule 0 0 0 3 S\n","rule 0 0 0 0 X\n","rule 2 0 0 0 S\n","rule 0 3 0 0 S\n","cell 9223372036854775808 0\n","cell +1 0\n","unknown 0\n"})rejects([&]{parse(prefix+suffix);});
 rejects([]{parse("states 2\n");});rejects([]{parse("atomos-universal 1\nstates 0\nalphabet 2\nstart 0 0\n");});
 rejects([]{parse("atomos-universal 1\nstates 1\nalphabet 0\nstart 0 0\n");});
 p.rules[2].move=2;rejects([&]{p.validate();});
 // Admission happens before either dense vector allocation, including huge
 // declarations which must not attempt to allocate their requested table.
 const auto limited=[&](const std::string&text,u64 budget){std::istringstream stream(text);return parse_program(stream,budget);};
 const u64 table_bytes=6*sizeof(Rule)+2*sizeof(u32);
 require(limited(prefix,table_bytes).rules.size()==6,"table exactly at selected budget refused");
 const auto resource_refused=[&](const std::string&text,u64 budget){bool refused=false;try{limited(text,budget);}catch(const TableResourceRefused&){refused=true;}require(refused,"table allocation was not refused by its resource bound");};
 resource_refused(prefix,table_bytes-1);
 resource_refused("atomos-universal 1\nstates 2000000000\nalphabet 2\nstart 0 0\n",1024);
 resource_refused("atomos-universal 1\nstates 4294967295\nalphabet 4294967295\nstart 0 0\n",UINT64_MAX);
}
static void transition_tests(){
 const auto unary=parse("atomos-universal 1\nstates 2\nalphabet 2\nstart 0 -1\nhalt 1\ncell -1 1\ncell 0 1\ncell 1 1\nrule 0 1 0 1 R\nrule 0 0 1 1 S\n");
 const auto inc=reference_run(unary,16,-8,32);require(inc.stop==Stop::halted&&inc.trace.size()==4&&inc.machine.head==2&&inc.machine.control==1,"unary increment did not halt correctly");require(inc.cells==Cells({{-1,1},{0,1},{1,1},{2,1}}),"unary increment tape");
 const auto walker=parse("atomos-universal 1\nstates 1\nalphabet 1\nstart 0 -1\nrule 0 0 0 0 R\n");
 auto run=reference_run(walker,7,-8,32);require(run.stop==Stop::running&&run.trace.size()==7&&run.machine.head==6,"finite budget was mistaken for halting");
 auto zero=reference_run(walker,0,-8,32);require(zero.stop==Stop::running&&zero.trace.empty()&&zero.machine.head==-1,"zero budget mutated machine");
 const auto missing=parse("atomos-universal 1\nstates 1\nalphabet 2\nstart 0 0\ncell 0 1\n");
 Machine machine{0,0};Cells cells{{0,1}},before=cells;Step step;
 require(reference_step(missing,machine,cells,step,-1,3)==Stop::missing_rule,"missing rule status");require(equal_machine(machine,{0,0})&&cells==before,"missing rule mutated state");
 const auto left=parse("atomos-universal 1\nstates 1\nalphabet 2\nstart 0 0\nrule 0 0 0 1 L\n");
 machine={0,0};cells.clear();require(reference_step(left,machine,cells,step,0,1)==Stop::tape_range,"destination range status");require(cells.empty()&&equal_machine(machine,{0,0}),"range failure wrote before validation");
 machine={0,INT64_MIN};require(reference_step(left,machine,cells,step,INT64_MIN,1)==Stop::tape_range,"head subtraction overflow accepted");require(machine.head==INT64_MIN&&cells.empty(),"head overflow changed state");
 Program halted=left;halted.halt[0]=1;auto initial_halt=reference_run(halted,100,-2,5);require(initial_halt.stop==Stop::halted&&initial_halt.trace.empty(),"initial halt executed a rule");
 Program outside=walker;outside.initial_cells[100]=0;require(reference_run(outside,0,-8,32).stop==Stop::tape_range,"explicit out-of-range blank was lost");
 const auto resumed=reference_run(walker,run.machine,run.cells,5,-8,32);const auto joined=reference_run(walker,12,-8,32);require(equal_machine(resumed.machine,joined.machine)&&equal_cells(resumed.cells,joined.cells),"prefix composition failed");
}
int main(int argc,char**argv){try{
 packed_tests();parser_tests();transition_tests();
 const auto folder=argc>1?std::filesystem::path(argv[1]):std::filesystem::path(__FILE__).parent_path().parent_path()/"examples"/"universal";
 for(const char*name:{"unary_increment.atomos","erase.atomos","left_cross_origin.atomos","nonhalting_walker.atomos","missing_rule.atomos"}){const Program p=load_program(folder/name);p.validate();++assertions;}
 std::cout<<"RESULT universal: "<<assertions<<" assertions passed\n";return 0;
}catch(const std::exception&e){std::cerr<<"FAIL universal: "<<e.what()<<" after "<<assertions<<" assertions\n";return 1;}}
