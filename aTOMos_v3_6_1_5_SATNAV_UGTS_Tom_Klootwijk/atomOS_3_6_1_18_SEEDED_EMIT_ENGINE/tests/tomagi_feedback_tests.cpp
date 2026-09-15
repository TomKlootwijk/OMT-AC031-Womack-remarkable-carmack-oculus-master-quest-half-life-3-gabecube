#include "atomos/tomagi_feedback.hpp"
#include <array>
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>
namespace vm=atomos::tomagi;
using U32=std::uint32_t;using U64=std::uint64_t;
namespace {
unsigned checks=0;
void check(bool yes,const std::string& why){++checks;if(!yes)throw std::runtime_error(why);}
std::vector<std::uint8_t> read_file(const char* path){
    std::ifstream in(path,std::ios::binary);if(!in)throw std::runtime_error(std::string("cannot read ")+path);
    return {std::istreambuf_iterator<char>(in),std::istreambuf_iterator<char>()};
}
U32 read32(const std::vector<std::uint8_t>& b,std::size_t i){
    return U32(b.at(i))|(U32(b.at(i+1))<<8)|(U32(b.at(i+2))<<16)|(U32(b.at(i+3))<<24);
}
U64 read64(const std::vector<std::uint8_t>& b,std::size_t i){return read32(b,i)|(U64(read32(b,i+4))<<32);}
void put(std::vector<std::uint8_t>& b,std::size_t at,U32 w){for(unsigned k=0;k<4;++k)b.at(at+k)=std::uint8_t(w>>(8*k));}
std::vector<std::uint8_t> program(const std::vector<vm::Cell48>& cells){
    std::vector<std::uint8_t> out(128+48*cells.size());const char magic[8]={'T','O','M','A','G','I','1',0};
    std::memcpy(out.data(),magic,8);put(out,8,0x10000);put(out,16,U32(cells.size()));
    put(out,24,19900710);put(out,28,24);put(out,32,48);put(out,36,64);
    for(std::size_t i=0;i<cells.size();++i)for(unsigned j=0;j<12;++j)put(out,128+48*i+4*j,cells[i].words[j]);
    return out;
}
vm::Cell48 cell(U32 key,U32 op,U32 payload=0,U32 next=0,U32 flags=0){
    vm::Cell48 c{};c.words[1]=key;c.words[2]=op;c.words[3]=flags;
    c.words[8]=c.words[9]=next;c.words[10]=payload;return c;
}
atomos::WordProfile copy_profile(){atomos::WordProfile p;p.valid_mask=0xffffffffu;p.x_lut=12;return p;}
std::array<U64,8> words(vm::WordState s){std::array<U64,8> w{};std::memcpy(w.data(),&s,sizeof(s));return w;}
template<class F> void rejects(F f,const char* why){bool rejected=false;try{f();}catch(const std::exception&){rejected=true;}check(rejected,why);}

void reference_fixture(const std::vector<std::uint8_t>& binary,const std::vector<std::uint8_t>& expected,bool texture){
    check(expected.size()>=16&&std::memcmp(expected.data(),"R16FBR1\0",8)==0,"Python reference header");
    const U32 steps=read32(expected,8);check(read32(expected,12)==1&&expected.size()==16+std::size_t(steps)*128,"Python reference size");
    vm::VM machine(binary,1);vm::WordFeedback feedback(machine,copy_profile());
    for(U32 n=0;n<steps;++n){
        feedback.run_steps(1,texture);const auto state=machine.read_states().at(0);const auto word=words(feedback.readback().at(0));
        for(unsigned k=0;k<16;++k)check(state.words[k]==read32(expected,16+128*n+4*k),"VM matches independent Python at each coupled transition");
        for(unsigned k=0;k<8;++k)check(word[k]==read64(expected,16+128*n+64+8*k),"word feedback at step "+std::to_string(n+1)+" field "+std::to_string(k)+" actual "+std::to_string(word[k])+" expected "+std::to_string(read64(expected,16+128*n+64+8*k)));
    }
    const auto before=words(feedback.readback().at(0));feedback.recommit_last();
    check(words(feedback.readback().at(0))==before,"same executed-EMIT identity cannot commit twice");
    vm::VM batch(binary,1);batch.set_states(std::vector<vm::State64>(257,batch.entry_state()));
    vm::WordFeedback batched(batch,copy_profile());batched.run_steps(steps,texture);
    for(auto w:batched.readback())check(words(w)==before,"257 lanes agree after one device-only batched phase");
}

// Scalar per-bit reference uses Boolean truth table indexes rather than the
// native broadword minterm implementation. ASA absorption remains whole-word.
U64 table(U32 t,U64 q,U64 d,U64 mask){U64 result=0;for(unsigned i=0;i<64;++i){
    unsigned index=unsigned((q>>i)&1)+2*unsigned((d>>i)&1);if((t>>index)&1)result|=U64(1)<<i;}return result&mask;
}
U64 reference_word(U64 q,U64 d,const atomos::WordProfile& p){
    U64 y=table(p.x_lut,q,d,p.valid_mask)&p.a0&p.n0;if(y&p.b0)y=0;
    y&=p.a1&p.n1;if(y&p.b1)y=0;
    U64 j=table(p.j_lut,q,y,p.valid_mask),k=table(p.k_lut,q,y,p.valid_mask),result=0;
    for(unsigned bit=0;bit<64;++bit){bool old=(q>>bit)&1;bool next=(((j>>bit)&1)&&!old)||(!((k>>bit)&1)&&old);
        if(next)result|=U64(1)<<bit;}
    return result&p.valid_mask;
}
void event_and_mask_cases(){
    auto emit=cell(0,14,0x80000001u,1),nop=cell(1,0,0,1);
    vm::VM machine(program({emit,nop}));vm::WordFeedback feedback(machine,copy_profile(),vm::WordBinding::None);
    feedback.run_steps(7);auto result=feedback.readback().at(0);
    check(result.hinges==1&&result.q==0x80000001u&&result.parity==1,"sticky EMIT on later NOP is not a new event");
    check(machine.read_states().at(0).words[15]&8,"fixture retained sticky EMIT status");
    check(machine.read_receipts().at(0).emitted==0,"receipt identifies actual NOP execution");
    vm::VM halted(program({cell(0,14,7,0,1)}));vm::WordFeedback halt_feedback(halted,copy_profile());
    halt_feedback.run_steps(5);check(halt_feedback.readback().at(0).hinges==1&&halt_feedback.readback().at(0).q==7,"EMIT-and-HALT commits its final emitted word once");
    auto bad=cell(0,10);bad.words[4]=64;vm::VM invalid(program({bad}));vm::WordFeedback invalid_feedback(invalid,copy_profile(),vm::WordBinding::None);
    invalid_feedback.run_steps(2);auto refused=invalid_feedback.readback().at(0);
    check(refused.hinges==0&&refused.q==0&&refused.status==1,"refused VM transition cannot drive word state");
    for(unsigned mode=0;mode<4;++mode){
        atomos::WordProfile p;p.x_lut=6;p.j_lut=12;p.k_lut=3;
        if(mode==1){p.a0=0xfedcba9876543210ULL;p.n1=0x8fffffffffffffffULL;}
        if(mode==2)p.b0=1;if(mode==3)p.b1=0x80000000u;
        const U64 initial=0x123456789abcdef0ULL;U64 reference=initial;
        vm::VM loops(program({cell(0,14,0x80000001u)}));
        vm::WordFeedback loop(loops,p,vm::WordBinding::None,{initial});
        for(unsigned n=0;n<9;++n){reference=reference_word(reference,0x80000001u,p);loop.run_steps(1,n%2==0);
            auto s=loop.readback().at(0);check(s.q==reference&&s.hinges==n+1&&s.parity==((n+1)&1),"64-bit masks/JK and repeated fresh identical emissions");}
    }
    vm::VM injection(program({cell(0,0)}));const U64 full=0x89abcdef76543210ULL;
    atomos::WordProfile all;vm::WordFeedback inject(injection,all,vm::WordBinding::RhoAndVrho,{full});inject.run_steps(1);
    auto raw=injection.read_states().at(0);check(raw.words[0]==U32(full)&&raw.words[4]==U32(full>>32),"injection preserves every low/high word bit");
    vm::VM reset(program({cell(0,0)}));vm::WordFeedback borrowed(reset,copy_profile());
    reset.set_states({reset.entry_state()});rejects([&]{borrowed.run_steps(1);},"generation change cannot hide behind epoch reset");
    vm::VM external(program({cell(0,0)}));vm::WordFeedback exclusive(external,copy_profile());external.run_steps(1);
    rejects([&]{exclusive.recommit_last();},"external VM advance invalidates exclusive feedback phase");
    auto profile=copy_profile();profile.x_lut=16;
    rejects([&]{vm::WordFeedback rejected(external,profile);},"invalid Boolean table refused");
    rejects([&]{vm::WordFeedback rejected(external,copy_profile(),vm::WordBinding::None,{U64(1)<<40});},"initial word mask checked");
}
}
int main(int argc,char** argv){try{
    if(argc!=3)throw std::runtime_error("usage: tomagi_feedback_tests PROGRAM.tmg EXPECTED.bin");
    auto binary=read_file(argv[1]),expected=read_file(argv[2]);
    reference_fixture(binary,expected,true);reference_fixture(binary,expected,false);event_and_mask_cases();
    std::cout<<"tomagi_feedback_tests: "<<checks<<" checks passed; Python-matched 24-step feedback, both fetch paths, 257 lanes\n";return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
