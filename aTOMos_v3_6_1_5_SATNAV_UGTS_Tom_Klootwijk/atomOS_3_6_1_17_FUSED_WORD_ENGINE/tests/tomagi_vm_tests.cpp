#include "atomos/tomagi_vm.hpp"
#include "tomagi.h" // unmodified, separately compiled C99 oracle
#include <algorithm>
#include <cstdint>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace vm=atomos::tomagi;
using U32=std::uint32_t;using U64=std::uint64_t;
namespace {
unsigned assertions=0;
void check(bool value,const std::string& text){++assertions;if(!value)throw std::runtime_error(text);}
int signed_word(U32 x){return x<=0x7fffffffu?int(x):-1-int(~x);}
TomagiState to_c(vm::State64 w){TomagiState s{};
    s.rho=signed_word(w.words[0]);s.theta=signed_word(w.words[1]);s.tick=signed_word(w.words[2]);s.phi=signed_word(w.words[3]);
    s.vrho=signed_word(w.words[4]);s.vtheta=signed_word(w.words[5]);s.vtick=signed_word(w.words[6]);s.vphi=signed_word(w.words[7]);
    s.orientation=w.words[8];s.sheet=w.words[9];s.branch=w.words[10];s.cell=w.words[11];s.lineage=w.words[12];s.output=w.words[13];
    s.residual=signed_word(w.words[14]);s.status=w.words[15];return s;}
vm::State64 from_c(TomagiState s){return{{U32(s.rho),U32(s.theta),U32(s.tick),U32(s.phi),U32(s.vrho),U32(s.vtheta),U32(s.vtick),U32(s.vphi),
    s.orientation,s.sheet,s.branch,s.cell,s.lineage,s.output,U32(s.residual),s.status}};}
TomagiCell to_c(vm::Cell48 c){return{c.words[0],c.words[1],c.words[2],c.words[3],signed_word(c.words[4]),signed_word(c.words[5]),
    signed_word(c.words[6]),signed_word(c.words[7]),c.words[8],c.words[9],c.words[10],c.words[11]};}
void write(std::vector<std::uint8_t>& b,std::size_t at,U32 w){for(unsigned i=0;i<4;++i)b[at+i]=std::uint8_t(w>>(8*i));}
U32 read(const std::vector<std::uint8_t>& b,std::size_t at){return U32(b[at])|(U32(b[at+1])<<8)|(U32(b[at+2])<<16)|(U32(b[at+3])<<24);}
std::vector<std::uint8_t> encode(const std::vector<vm::Cell48>& cells,vm::State64 initial={},U32 entry=0){
    std::vector<std::uint8_t> b(128+48*cells.size());const char magic[8]={'T','O','M','A','G','I','1',0};std::copy(magic,magic+8,b.begin());
    write(b,8,0x10000);write(b,12,0x80000003u);write(b,16,U32(cells.size()));write(b,20,entry);write(b,24,0x93ab71cdu);
    write(b,28,7);write(b,32,48);write(b,36,64);
    for(unsigned i=0;i<16;++i)write(b,64+i*4,initial.words[i]);
    for(std::size_t i=0;i<cells.size();++i)for(unsigned j=0;j<12;++j)write(b,128+48*i+j*4,cells[i].words[j]);return b;
}
vm::Cell48 cell(U32 op){vm::Cell48 c{};c.words[2]=op;c.words[10]=0xfedcba98u;c.words[11]=0x87654321u;return c;}
void same(vm::State64 a,vm::State64 b,const std::string& label){for(unsigned i=0;i<16;++i)check(a.words[i]==b.words[i],label+" word"+std::to_string(i));}
void roundtrip(vm::VM& instance,const std::vector<std::uint8_t>& bytes){auto words=instance.read_program_words();check(words.size()*4==bytes.size(),"device program length");
    for(std::size_t i=0;i<words.size();++i)check(words[i]==read(bytes,i*4),"packed header/cell word survives actual texture roundtrip");}

void compare_case(const std::string& label,const std::vector<vm::Cell48>& cells,const std::vector<vm::State64>& initial,U32 steps,U32 bank_cap=0){
    auto bytes=encode(cells,initial.front());vm::VM texture(bytes,bank_cap),global(bytes,bank_cap);texture.set_states(initial);global.set_states(initial);
    roundtrip(texture,bytes);roundtrip(global,bytes);
    std::vector<TomagiCell> cc;for(auto c:cells)cc.push_back(to_c(c));
    TomagiProgram p{};p.cells=cc.data();p.cell_count=U32(cc.size());p.seed=0x93ab71cdu;
    std::vector<TomagiState> oracle;for(auto s:initial)oracle.push_back(to_c(s));std::vector<U32> faults(initial.size(),0);
    for(U32 step=0;step<steps;++step){
        std::vector<bool> executed(initial.size()),emitted(initial.size());std::vector<U32> previous(initial.size());
        for(std::size_t k=0;k<oracle.size();++k){previous[k]=oracle[k].cell;bool was_halted=(oracle[k].status&1)!=0;
            if(faults[k])continue;int ok=tomagi_step(&p,&oracle[k]);
            if(!ok){faults[k]=previous[k]>=p.cell_count?U32(vm::Error::BadCell):U32(vm::Error::BadRadix);continue;}
            executed[k]=!was_halted;emitted[k]=executed[k]&&cells[previous[k]].words[2]==14;
        }
        texture.run_steps(1,true,true);global.run_steps(1,false,true);
        auto ts=texture.read_states(),gs=global.read_states();auto te=texture.read_errors(),ge=global.read_errors();
        auto tr=texture.read_receipts(),gr=global.read_receipts();auto trace=texture.read_trace();
        check(trace.size()==initial.size(),label+" rectangular trace size");
        for(std::size_t k=0;k<initial.size();++k){same(ts[k],from_c(oracle[k]),label+" texture/C");same(gs[k],from_c(oracle[k]),label+" global/C");
            check(te[k]==faults[k]&&ge[k]==faults[k],label+" exact sidecar errors");
            check(tr[k].executed==U32(executed[k])&&gr[k].executed==U32(executed[k]),label+" executed receipt");
            check(tr[k].emitted==U32(emitted[k])&&gr[k].emitted==U32(emitted[k]),label+" actual opcode EMIT receipt");
            check(tr[k].epoch==step&&gr[k].epoch==step&&trace[k].epoch==step,label+" dispatch epoch");
            check(tr[k].cell_before==previous[k]&&tr[k].error==faults[k],label+" receipt PC/error");
            check(tr[k].branch_after==ts[k].words[10]&&gr[k].branch_after==gs[k].words[10],label+" receipt final branch");
            check(gr[k].cell_before==tr[k].cell_before&&gr[k].error==tr[k].error&&gr[k].opcode==tr[k].opcode&&
                  gr[k].flags==tr[k].flags&&gr[k].payload==tr[k].payload,label+" both fetch modes expose identical receipts");
            if(executed[k]){const auto& c=cells[previous[k]];check(tr[k].opcode==c.words[2]&&tr[k].flags==c.words[3]&&tr[k].payload==c.words[10],label+" executed literal metadata");}
        }
    }
    check(texture.epoch()==steps&&global.epoch()==steps,label+" VM epoch counter");
}
std::vector<vm::State64> extremes(){std::vector<vm::State64> s(4);
    for(unsigned i=0;i<4;++i)s[i]={{i&1?0xffffffffu:1u<<20,i&1?0x80000000u:0x7fffffffu,0x7fffffffu,
        i==0?1u:i==1?0xffffffffu:i==2?0x80000000u:0x7fffffffu,
        0xfffffffdu,0x80000000u,0xffffffffu,0x7fffffffu,i,0xf0000000u+i,i,0,0x12345678u,0xabcdef01u,0x80000000u,0x3eu}};
    return s;}
void all_opcodes(){
    for(U32 op=0;op<16;++op){auto c=cell(op);c.words[4]=0x7fffffffu;c.words[5]=0x80000000u;c.words[6]=0x80000000u;c.words[7]=0xffffffffu;
        if(op==1)c.words[3]=13;
        if(op==2){c.words[3]=4;c.words[4]=0x80000000u;}
        if(op==4)c.words[3]=(1u<<4)|(1u<<5);
        if(op==7||op==8){c.words[4]=0x80000000u;c.words[5]=op==7?0x7fffffffu:0u;}
        if(op==9||op==11)c.words[3]=3;
        if(op==10)c.words[4]=63;
        if(op==12)c.words[5]=1;
        if(op==14)c.words[3]=(3u<<8)|(1u<<11);
        compare_case("opcode"+std::to_string(op),{c},extremes(),3);
    }
    auto c=cell(9);c.words[3]=0;compare_case("reflective negative/multiple Klein wraps",{c},extremes(),2);
    for(U32 shift:{0xfffffffdu,30u,31u}){c=cell(12);c.words[4]=0x80000000u;c.words[5]=shift;compare_case("LSYS clamped shift",{c},extremes(),2);}
    for(U32 bit:{0u,31u,32u,63u}){c=cell(10);c.words[4]=bit;compare_case("RADIX boundary bit",{c},extremes(),1);}
    for(U32 op:{1u,2u})for(U32 target=0;target<16;++target){c=cell(op);c.words[3]=target;c.words[4]=0x80000001u;
        compare_case("SET/JIT1 all raw target aliases",{c},extremes(),2);}
    // Full raw-state preservation: branch2 MUST NOT activate HINGE.
    c=cell(11);c.words[4]=1;vm::State64 s{};s.words[10]=2;compare_case("CL branch2 regression",{c},{s},1);
    // Source residual wraps before classification: this positive wide radial
    // residual becomes INT32_MIN and the legacy machine takes inside=true.
    c=cell(8);c.words[4]=0x80000000u;c.words[7]=0xffffffffu;compare_case("wrapped sphere relation",{c},{vm::State64{}},1);
}
void rekey_and_banks(){std::vector<vm::Cell48> cells;
    for(U32 i=0;i<9;++i){auto c=cell(0);c.words[1]=i;c.words[3]=i&1?0x80000000u:0;c.words[8]=(i+1)%9;c.words[9]=(i+2)%9;
        c.words[10]^=i;c.words[11]^=i<<27;cells.push_back(c);}
    cells[0].words[2]=1;cells[0].words[3]=0x80000003u;cells[0].words[4]=4;
    std::vector<vm::State64> initial(10);
    for(U32 i=0;i<10;++i){initial[i].words[11]=i%9;initial[i].words[3]=i==9?31:(i+3)%9;initial[i].words[10]=i&1;}
    initial[9].words[11]=1;initial[1].words[15]=0x40u;
    compare_case("banked rekey hits/misses and direct successors",cells,initial,5,2);
    vm::VM machine(encode(cells),2);auto view=machine.device_view();check(view.bank_shift==1&&view.bank_mask==1,"explicit small banks exercise real boundary mapping");
}
void receipts_and_faults(){
    auto emit=cell(14),nop=cell(0),halt=cell(14);emit.words[1]=0;emit.words[8]=emit.words[9]=1;
    nop.words[1]=1;nop.words[8]=nop.words[9]=2;halt.words[1]=2;halt.words[3]=1;halt.words[8]=halt.words[9]=2;
    auto bytes=encode({emit,nop,halt});vm::VM m(bytes,1);m.run_steps(5,true,true);auto trace=m.read_trace();
    compare_case("sticky EMIT and emit-halt canonical chain",{emit,nop,halt},{vm::State64{}},5,1);
    check(trace.size()==5,"full rectangular multi-step trace");
    for(unsigned i=0;i<5;++i){check(trace[i].emitted==U32(i==0||i==2),"sticky EMIT does not fabricate new emissions");check(trace[i].executed==U32(i<3),"halt stops canonical execution");}
    check((m.read_states()[0].words[15]&9)==9,"emit-halt retains final output and flags");
    auto raw=m.header_state();raw.words[11]=99;m.set_states({raw});m.enqueue_step(false);m.synchronize();
    check(m.read_errors()[0]==U32(vm::Error::BadCell),"bad PC has explicit error");same(m.read_states()[0],raw,"bad PC atomic state");
    raw.words[15]=1;m.set_states({raw});m.run_steps(1);check(m.read_errors()[0]==0&&m.read_receipts()[0].executed==0,"already-halted invalid PC is a source-compatible no-op");
    for(U32 bad:{64u,0xffffffffu}){auto c=cell(10);c.words[4]=bad;compare_case("invalid RADIX atomic sticky fault",{c},extremes(),2);}
    auto generation=m.state_generation();m.set_states({});
    check(m.state_generation()==generation+1&&m.device_view().generation==generation+1&&m.epoch()==0,"reset invalidates borrowers even when epoch/pointers could repeat");
    m.run_steps(3,true,true);check(m.read_states().empty()&&m.read_trace().empty(),"empty batch");
    auto initial=vm::State64{};initial.words[11]=77;vm::VM fresh(encode({cell(0)},initial));
    check(fresh.header_state().words[11]==77&&fresh.entry_state().words[11]==0&&fresh.read_states()[0].words[11]==0,"fresh entry versus exact header checkpoint semantics");
}
void malformed(){auto valid=encode({cell(0)});
    auto rejects=[&](std::vector<std::uint8_t> b){bool failed=false;try{vm::VM bad(b);}catch(const std::exception&){failed=true;}check(failed,"malformed .tmg rejected");};
    auto b=valid;b[0]^=1;rejects(b);b=valid;b.pop_back();rejects(b);
    for(auto at:{8u,32u,36u,40u}){b=valid;write(b,at,123);rejects(b);}
    b=valid;write(b,16,0);rejects(b);b=valid;write(b,20,1);rejects(b);b=valid;write(b,136,16);rejects(b);b=valid;write(b,160,1);rejects(b);
    rejects(encode({cell(0),cell(0)}));auto a=cell(0),c=cell(0);a.words[1]=2;c.words[1]=1;rejects(encode({a,c}));
}
} // namespace
int main(){try{all_opcodes();rekey_and_banks();receipts_and_faults();malformed();std::cout<<"tomagi_vm_tests: "<<assertions<<" assertions passed against C oracle on CUDA\n";return 0;}
    catch(const std::exception& e){std::cerr<<"tomagi_vm_tests: "<<e.what()<<'\n';return 1;}}
