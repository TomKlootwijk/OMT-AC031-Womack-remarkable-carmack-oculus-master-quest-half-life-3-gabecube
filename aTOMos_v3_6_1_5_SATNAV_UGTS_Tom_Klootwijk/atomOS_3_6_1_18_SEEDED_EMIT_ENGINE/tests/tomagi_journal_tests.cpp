#include "atomos/tomagi_feedback.hpp"
#include "atomos/tomagi_journal.hpp"
#include "tomagi.h" // Original C transition, compiled separately and unchanged.
#include <cuda_runtime_api.h>
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace vm = atomos::tomagi;
using U32 = std::uint32_t;
using U64 = std::uint64_t;

namespace {
U64 checks=0, state_words=0, receipt_words=0, feedback_words=0, event_fields=0, output_bytes=0;
constexpr U32 Seed=0x715eeda9u;

void require(bool value,const std::string& why) {
    ++checks; if(!value) throw std::runtime_error(why);
}
template<class F> void rejects(F&& action,const std::string& why) {
    bool refused=false; try { action(); } catch(const std::exception&) { refused=true; }
    require(refused,why);
}
int signed_word(U32 x) { return x<=0x7fffffffu?int(x):-1-int(~x); }
TomagiState to_c(const vm::State64& x) {
    return {signed_word(x.words[0]),signed_word(x.words[1]),signed_word(x.words[2]),signed_word(x.words[3]),
            signed_word(x.words[4]),signed_word(x.words[5]),signed_word(x.words[6]),signed_word(x.words[7]),
            x.words[8],x.words[9],x.words[10],x.words[11],x.words[12],x.words[13],signed_word(x.words[14]),x.words[15]};
}
vm::State64 from_c(const TomagiState& x) {
    return {{U32(x.rho),U32(x.theta),U32(x.tick),U32(x.phi),U32(x.vrho),U32(x.vtheta),U32(x.vtick),U32(x.vphi),
             x.orientation,x.sheet,x.branch,x.cell,x.lineage,x.output,U32(x.residual),x.status}};
}
TomagiCell to_c(const vm::Cell48& x) {
    return {x.words[0],x.words[1],x.words[2],x.words[3],signed_word(x.words[4]),signed_word(x.words[5]),
            signed_word(x.words[6]),signed_word(x.words[7]),x.words[8],x.words[9],x.words[10],x.words[11]};
}
void put(std::vector<std::uint8_t>& out,std::size_t offset,U32 word) {
    for(unsigned k=0;k<4;++k) out.at(offset+k)=std::uint8_t(word>>(8*k));
}
std::vector<std::uint8_t> encode(const std::vector<vm::Cell48>& cells) {
    std::vector<std::uint8_t> out(128+48*cells.size());
    const char magic[8]={'T','O','M','A','G','I','1',0}; std::memcpy(out.data(),magic,8);
    put(out,8,0x10000); put(out,12,3); put(out,16,U32(cells.size()));
    put(out,24,Seed); put(out,28,263); put(out,32,48); put(out,36,64);
    for(std::size_t i=0;i<cells.size();++i) for(unsigned k=0;k<12;++k) put(out,128+48*i+4*k,cells[i].words[k]);
    return out;
}
vm::Cell48 cell(U32 key,U32 opcode,U32 next=0) {
    vm::Cell48 c{}; c.words[1]=key; c.words[2]=opcode; c.words[8]=c.words[9]=next;
    c.words[10]=0x89abcdefu; c.words[11]=0xfedc1234u^(key*0x98765431u); return c;
}
U32 rng(U32& x) { x^=x<<13; x^=x>>17; x^=x<<5; return x; }

// Independent Boolean truth table and per-bit JK, with whole-word absorption.
U64 truth(U32 lut,U64 q,U64 drive,U64 mask) {
    U64 result=0;
    for(unsigned bit=0;bit<64;++bit) {
        const unsigned index=unsigned((q>>bit)&1)+2*unsigned((drive>>bit)&1);
        if((lut>>index)&1) result|=U64(1)<<bit;
    }
    return result&mask;
}
U64 scalar_word(U64 q,U64 drive,const atomos::WordProfile& p) {
    U64 y=truth(p.x_lut,q,drive,p.valid_mask)&p.a0&p.n0;
    if(y&p.b0) y=0;
    y&=p.a1&p.n1; if(y&p.b1) y=0;
    const U64 j=truth(p.j_lut,q,y,p.valid_mask),k=truth(p.k_lut,q,y,p.valid_mask);
    U64 result=0;
    for(unsigned bit=0;bit<64;++bit) {
        const bool old=((q>>bit)&1)!=0;
        if((((j>>bit)&1)&&!old)||(!((k>>bit)&1)&&old)) result|=U64(1)<<bit;
    }
    return result&p.valid_mask;
}

// This event record belongs only to the independent test oracle. The native
// journal is compared field by field, never by a digest or raw struct padding.
struct Event {
    U64 epoch; U32 lane,cell_before,flags,payload,lineage,cell_after,branch_after,status_after;
};
struct Oracle {
    std::vector<TomagiCell> cells;
    std::vector<vm::State64> states;
    std::vector<U32> errors;
    std::vector<vm::Receipt> receipts;
    std::vector<vm::WordState> words;
    std::vector<Event> events;
    U64 epoch=0;
    Oracle(const std::vector<vm::Cell48>& program,const std::vector<vm::State64>& initial,
           const std::vector<U64>& q={}) : states(initial),errors(initial.size()),receipts(initial.size()),words(initial.size()) {
        for(const auto& c:program) cells.push_back(to_c(c));
        for(std::size_t lane=0;lane<q.size();++lane) words.at(lane).q=q[lane];
    }
    void advance(U32 ticks,const atomos::WordProfile* profile=nullptr,vm::WordBinding binding=vm::WordBinding::None) {
        TomagiProgram program{}; program.cells=cells.data(); program.cell_count=U32(cells.size()); program.seed=Seed;
        for(U32 tick=0;tick<ticks;++tick,++epoch) for(U32 lane=0;lane<states.size();++lane) {
            auto& state=states[lane]; auto& word=words[lane];
            if(profile&&binding==vm::WordBinding::RhoAndVrho&&!errors[lane]&&!(state.words[15]&TOMAGI_STATUS_HALT)&&!word.status) {
                state.words[0]=U32(word.q); state.words[4]=U32(word.q>>32);
            }
            vm::Receipt receipt{}; receipt.epoch=epoch; receipt.cell_before=state.words[11]; receipt.branch_after=state.words[10];
            if(errors[lane]) receipt.error=errors[lane];
            else if(!(state.words[15]&TOMAGI_STATUS_HALT)) {
                if(state.words[11]>=cells.size()) receipt.error=errors[lane]=U32(vm::Error::BadCell);
                else {
                    const auto& c=cells[state.words[11]];
                    receipt.opcode=c.opcode; receipt.flags=c.flags; receipt.payload=c.payload;
                    auto next=to_c(state);
                    if(!tomagi_step(&program,&next)) receipt.error=errors[lane]=c.opcode>TOMAGI_OP_HALT?U32(vm::Error::BadOpcode):U32(vm::Error::BadRadix);
                    else {
                        state=from_c(next); receipt.executed=1; receipt.emitted=c.opcode==TOMAGI_OP_EMIT; receipt.branch_after=next.branch;
                        if(receipt.emitted) events.push_back({epoch,lane,receipt.cell_before,c.flags,c.payload,next.lineage,next.cell,next.branch,next.status});
                    }
                }
            }
            receipts[lane]=receipt;
            if(!profile) continue;
            if(receipt.error||errors[lane]) { word.status=1; continue; }
            if(!receipt.executed||!receipt.emitted||word.status) continue;
            if(word.initialized&&receipt.epoch<=word.last_epoch) {
                if(receipt.epoch<word.last_epoch) word.status=2; continue;
            }
            if(word.hinges==~U64(0)) { word.status=3; continue; }
            word.q=scalar_word(word.q,receipt.payload,*profile);
            word.parity^=1; ++word.hinges; word.initialized=1; word.last_epoch=receipt.epoch; word.last_drive=receipt.payload;
        }
    }
};

template<class T,class W,std::size_t N> std::array<W,N> raw_words(const T& value) {
    static_assert(sizeof(T)==sizeof(W)*N,"complete value words");
    std::array<W,N> out{}; std::memcpy(out.data(),&value,sizeof(value)); return out;
}
void same_vm(vm::VM& actual,const Oracle& expected,const std::string& label) {
    const auto state=actual.read_states(); const auto errors=actual.read_errors(); const auto receipts=actual.read_receipts();
    require(state.size()==expected.states.size()&&errors.size()==state.size()&&receipts.size()==state.size(),label+" lane count");
    require(actual.epoch()==expected.epoch,label+" epoch");
    for(std::size_t lane=0;lane<state.size();++lane) {
        for(unsigned k=0;k<16;++k) { ++state_words; require(state[lane].words[k]==expected.states[lane].words[k],label+" State64 lane "+std::to_string(lane)+" word "+std::to_string(k)); }
        require(errors[lane]==expected.errors[lane],label+" error lane "+std::to_string(lane));
        const auto a=raw_words<vm::Receipt,U32,10>(receipts[lane]),e=raw_words<vm::Receipt,U32,10>(expected.receipts[lane]);
        for(unsigned k=0;k<10;++k) { ++receipt_words; require(a[k]==e[k],label+" Receipt40 lane "+std::to_string(lane)+" word "+std::to_string(k)); }
    }
}
void same_words(vm::WordFeedback& actual,const Oracle& expected,const std::string& label) {
    const auto words=actual.readback(); require(words.size()==expected.words.size(),label+" feedback lanes");
    for(std::size_t lane=0;lane<words.size();++lane) {
        const auto a=raw_words<vm::WordState,U64,8>(words[lane]),e=raw_words<vm::WordState,U64,8>(expected.words[lane]);
        for(unsigned k=0;k<8;++k) { ++feedback_words; require(a[k]==e[k],label+" WordState64 lane "+std::to_string(lane)+" word "+std::to_string(k)); }
    }
}

// Independently state the source materializer's low-count-byte rule. Big-endian
// chooses the low n bytes, then reverses their order; it is not the high prefix.
std::vector<std::uint8_t> decoded(U32 flags,U32 payload) {
    const U32 count=(flags>>TOMAGI_FLAG_EMIT_COUNT_SHIFT)&7u;
    if(count<1||count>4) throw std::invalid_argument("oracle EMIT count");
    std::vector<std::uint8_t> bytes;
    for(U32 i=0;i<count;++i) {
        const U32 offset=(flags&TOMAGI_FLAG_EMIT_BIG_ENDIAN)?count-1-i:i;
        bytes.push_back(std::uint8_t(payload>>(8*offset)));
    }
    return bytes;
}

std::vector<vm::Cell48> event_program() {
    std::vector<vm::Cell48> cells;
    for(U32 i=0;i<13;++i) cells.push_back(cell(i,TOMAGI_OP_NOP,(i+1)%7));
    for(U32 i:{0u,2u,4u,5u,6u,7u,11u,12u}) {
        cells[i].words[2]=TOMAGI_OP_EMIT;
        cells[i].words[3]=((i%4)+1)<<TOMAGI_FLAG_EMIT_COUNT_SHIFT;
        if(i&1) cells[i].words[3]|=TOMAGI_FLAG_EMIT_BIG_ENDIAN;
    }
    cells[0].words[3]=1u<<8;
    cells[2].words[3]=(2u<<8)|TOMAGI_FLAG_EMIT_BIG_ENDIAN;
    cells[3].words[2]=TOMAGI_OP_SET; cells[3].words[4]=0x80000001u;
    cells[4].words[3]=3u<<8;
    cells[5].words[3]=(4u<<8)|TOMAGI_FLAG_EMIT_BIG_ENDIAN;
    // Cells5 and6 deliberately emit the same payload at consecutive epochs.
    cells[6].words[3]=4u<<8;
    cells[7].words[3]=(1u<<8)|TOMAGI_FLAG_EMIT_HALT;
    cells[8].words[2]=TOMAGI_OP_HALT;
    cells[9].words[2]=TOMAGI_OP_RADIX; cells[9].words[4]=64;
    cells[10].words[8]=cells[10].words[9]=10; // Forever no new EMIT.
    cells[11].words[8]=cells[11].words[9]=9; // Emit exactly once, then fault.
    cells[12].words[8]=cells[12].words[9]=7; // Emit, then EMIT-HALT.
    cells[12].words[3]=(3u<<8)|TOMAGI_FLAG_EMIT_BIG_ENDIAN;
    return cells;
}
std::vector<vm::State64> event_states(U32 count=29) {
    std::vector<vm::State64> states(count); U32 random=0x1a9e128du;
    for(U32 lane=0;lane<count;++lane) {
        for(auto& word:states[lane].words) word=rng(random);
        states[lane].words[10]=lane%4; states[lane].words[11]=lane%13;
        states[lane].words[15]=(rng(random)&~U32(TOMAGI_STATUS_HALT))|TOMAGI_STATUS_EMIT;
    }
    if(count>=3) {
        states[count-1].words[11]=100000; states[count-1].words[15]|=TOMAGI_STATUS_HALT;
        states[count-2].words[11]=100000;
        states[count-3].words[11]=10;
    }
    return states;
}
void oracle_byte_anchors() {
    require(decoded(1u<<8,0x89abcdefu)==std::vector<std::uint8_t>{0xef},"one-byte low payload");
    require(decoded(2u<<8,0x89abcdefu)==std::vector<std::uint8_t>({0xef,0xcd}),"two-byte little endian");
    require(decoded((2u<<8)|TOMAGI_FLAG_EMIT_BIG_ENDIAN,0x89abcdefu)==std::vector<std::uint8_t>({0xcd,0xef}),"two-byte big endian uses low bytes");
    require(decoded((3u<<8)|TOMAGI_FLAG_EMIT_BIG_ENDIAN,0x89abcdefu)==std::vector<std::uint8_t>({0xab,0xcd,0xef}),"three-byte big endian uses low bytes");
    require(decoded((4u<<8)|TOMAGI_FLAG_EMIT_BIG_ENDIAN,0x89abcdefu)==std::vector<std::uint8_t>({0x89,0xab,0xcd,0xef}),"four-byte big endian");
    for(U32 count:{0u,5u,6u,7u}) rejects([&]{decoded(count<<8,0);},"oracle rejects invalid byte count");
}

void same_states(const std::vector<vm::State64>& actual,const std::vector<vm::State64>& expected,const std::string& label) {
    require(actual.size()==expected.size(),label+" lanes");
    for(std::size_t lane=0;lane<actual.size();++lane) for(unsigned k=0;k<16;++k) {
        ++state_words; require(actual[lane].words[k]==expected[lane].words[k],label+" lane "+std::to_string(lane)+" word "+std::to_string(k));
    }
}
void same_word_values(const std::vector<vm::WordState>& actual,const std::vector<vm::WordState>& expected,const std::string& label) {
    require(actual.size()==expected.size(),label+" lanes");
    for(std::size_t lane=0;lane<actual.size();++lane) {
        const auto a=raw_words<vm::WordState,U64,8>(actual[lane]),e=raw_words<vm::WordState,U64,8>(expected[lane]);
        for(unsigned k=0;k<8;++k) { ++feedback_words; require(a[k]==e[k],label+" lane "+std::to_string(lane)+" word "+std::to_string(k)); }
    }
}
void same_profile(const atomos::WordProfile& a,const atomos::WordProfile& e,const std::string& label) {
    require(a.valid_mask==e.valid_mask&&a.a0==e.a0&&a.n0==e.n0&&a.b0==e.b0&&a.a1==e.a1&&a.n1==e.n1&&a.b1==e.b1
            &&a.x_lut==e.x_lut&&a.j_lut==e.j_lut&&a.k_lut==e.k_lut,label+" exact profile fields");
}
void same_chunk(const vm::EmitJournalChunk& actual,const Oracle& before,const Oracle& after,
                const std::vector<std::uint8_t>& binary,U64 generation,const std::string& label,
                const atomos::WordProfile* profile=nullptr,vm::WordBinding binding=vm::WordBinding::None) {
    require(actual.source&&actual.source->owner_id!=0,label+" retained source owner");
    require(actual.source->canonical_tmg==binary,label+" full exact canonical program bytes");
    require(actual.generation==generation,label+" source generation");
    require(actual.start_epoch==before.epoch&&actual.end_epoch==after.epoch,label+" exact epoch interval");
    require(actual.lanes==after.states.size(),label+" lane count");
    require(actual.execution==(profile?vm::JournalExecution::WordFeedback:vm::JournalExecution::Pure),label+" execution kind");
    require(actual.binding==binding,label+" injection binding");
    if(profile) {
        same_profile(actual.word_profile,*profile,label);
        same_word_values(actual.initial_words,before.words,label+" initial word snapshot");
        same_word_values(actual.final_words,after.words,label+" final word snapshot");
    } else require(actual.initial_words.empty()&&actual.final_words.empty(),label+" pure has no word-state claim");
    same_states(actual.initial_states,before.states,label+" initial State64 snapshot");
    same_states(actual.final_states,after.states,label+" final State64 snapshot");
    require(actual.initial_errors==before.errors&&actual.errors==after.errors,label+" complete fault snapshots");
    require(actual.final_receipts.size()==after.receipts.size(),label+" final receipt lanes");
    for(std::size_t lane=0;lane<after.receipts.size();++lane) {
        const auto a=raw_words<vm::Receipt,U32,10>(actual.final_receipts[lane]),e=raw_words<vm::Receipt,U32,10>(after.receipts[lane]);
        for(unsigned k=0;k<10;++k) { ++receipt_words; require(a[k]==e[k],label+" final receipt word"); }
    }
    bool fault=false,halt=true;
    for(std::size_t lane=0;lane<after.states.size();++lane) {
        fault|=after.errors[lane]!=0||(profile&&after.words[lane].status!=0);
        halt&=(after.states[lane].words[15]&TOMAGI_STATUS_HALT)!=0;
    }
    const auto status=fault?vm::JournalStatus::Faulted:(halt?vm::JournalStatus::Complete:vm::JournalStatus::Prefix);
    require(actual.status==status,label+" complete/prefix/fault status");
    std::vector<Event> ordered;
    std::vector<U64> offsets{0};
    for(U32 lane=0;lane<after.states.size();++lane) {
        for(const auto& event:after.events)
            if(event.lane==lane&&event.epoch>=before.epoch&&event.epoch<after.epoch) ordered.push_back(event);
        offsets.push_back(ordered.size());
    }
    require(actual.lane_offsets==offsets,label+" exact lane-major offsets including empty lanes");
    require(actual.events.size()==ordered.size(),label+" every fresh event retained exactly once");
    for(std::size_t i=0;i<ordered.size();++i) {
        const auto& a=actual.events[i]; const auto& e=ordered[i];
        const U64 av[]={a.epoch,a.lane,a.cell_before,a.flags,a.payload,a.lineage,a.cell_after,a.branch_after,a.status_after};
        const U64 ev[]={e.epoch,e.lane,e.cell_before,e.flags,e.payload,e.lineage,e.cell_after,e.branch_after,e.status_after};
        for(unsigned field=0;field<9;++field) { ++event_fields; require(av[field]==ev[field],label+" event "+std::to_string(i)+" field "+std::to_string(field)); }
        const auto bytes=vm::decode_emit_payload(a.flags,a.payload),expected=decoded(e.flags,e.payload);
        require(bytes.size()==expected.size(),label+" event byte count");
        for(std::size_t j=0;j<bytes.size();++j) { ++output_bytes; require(bytes[j]==expected[j],label+" exact emitted byte "+std::to_string(j)); }
    }
}

void payload_decoder() {
    oracle_byte_anchors();
    U32 random=0xb17b1a9eu;
    for(U32 count=1;count<=4;++count) for(bool big:{false,true}) for(U32 i=0;i<67;++i) {
        const U32 flags=(count<<8)|(big?TOMAGI_FLAG_EMIT_BIG_ENDIAN:0)|(i&1?TOMAGI_FLAG_EMIT_HALT:0)|0x70000000u;
        const U32 payload=i==0?0u:i==1?~U32(0):rng(random);
        const auto actual=vm::decode_emit_payload(flags,payload),expected=decoded(flags,payload);
        require(actual==expected,"source-compatible payload decoder all lengths/orders/random bytes"); output_bytes+=actual.size();
    }
    for(U32 count:{0u,5u,6u,7u}) for(bool big:{false,true})
        rejects([&]{vm::decode_emit_payload((count<<8)|(big?TOMAGI_FLAG_EMIT_BIG_ENDIAN:0),0x89abcdefu);},"native decoder rejects invalid count");
}

void pure_journal_cases() {
    const auto cells=event_program(); const auto initial=event_states();
    const auto binary=encode(cells);
    for(bool texture:{false,true}) for(bool fused:{false,true}) for(U32 chunk:{1u,7u,32u,256u}) {
        vm::VM machine(binary,2); machine.set_states(initial); Oracle expected(cells,initial);
        const U64 generation=machine.state_generation();
        vm::EmitJournalChunk previous; bool have_previous=false;
        std::vector<std::vector<std::uint8_t>> retained_bytes(initial.size());
        for(U32 done=0;done<263;) {
            const U32 count=std::min(chunk,263-done); const Oracle before=expected; expected.advance(count);
            const auto result=machine.run_journal_chunk(count,texture,fused);
            const auto label="pure "+std::to_string(U32(fused))+" chunk "+std::to_string(chunk);
            same_chunk(result,before,expected,binary,generation,label);
            same_vm(machine,expected,label);
            if(have_previous) { vm::require_journal_continuation(previous,result); ++checks; }
            for(const auto& event:result.events) {
                const auto bytes=vm::decode_emit_payload(event.flags,event.payload);
                retained_bytes[event.lane].insert(retained_bytes[event.lane].end(),bytes.begin(),bytes.end());
            }
            previous=result; have_previous=true; done+=count;
        }
        for(U32 lane=0;lane<initial.size();++lane) {
            std::vector<std::uint8_t> expected_bytes;
            for(const auto& event:expected.events) if(event.lane==lane) {
                const auto bytes=decoded(event.flags,event.payload); expected_bytes.insert(expected_bytes.end(),bytes.begin(),bytes.end());
            }
            require(retained_bytes[lane]==expected_bytes,"full per-lane artifact bytes across chunk boundaries"); output_bytes+=expected_bytes.size();
        }
        const auto zero=machine.run_journal_chunk(0,!texture,!fused,1);
        same_chunk(zero,expected,expected,binary,generation,"pure zero after work");
        vm::require_journal_continuation(previous,zero); ++checks;
        same_vm(machine,expected,"pure zero identity");
    }
}

void coupled_journal_cases() {
    const auto cells=event_program(); const auto initial=event_states(17);
    const auto binary=encode(cells);
    for(U32 variant=0;variant<3;++variant) {
        atomos::WordProfile profile; profile.x_lut=6; profile.j_lut=variant==2?9:12; profile.k_lut=variant==2?5:3;
        if(variant==1) { profile.valid_mask=0x7fff01234567ffffULL; profile.a0=0xf7ffffffffffefffULL; profile.n1=0xfffff0ffffffffffULL; profile.b0=0x1000000000000ULL; }
        if(variant==2) profile.b1=0x80000000ULL;
        U32 random=0x10cafea0u+variant; std::vector<U64> q(initial.size());
        for(auto& word:q) { const U64 hi=rng(random); word=((hi<<32)|rng(random))&profile.valid_mask; }
        for(auto binding:{vm::WordBinding::None,vm::WordBinding::RhoAndVrho})
        for(bool texture:{false,true}) for(U32 chunk:{1u,7u,32u,256u}) {
            vm::VM machine(binary,2); machine.set_states(initial);
            vm::WordFeedback feedback(machine,profile,binding,q); Oracle expected(cells,initial,q);
            const U64 generation=machine.state_generation(); vm::EmitJournalChunk previous; bool have_previous=false;
            U32 block=0;
            for(U32 done=0;done<263;++block) {
                const U32 count=std::min(chunk,263-done); const Oracle before=expected; expected.advance(count,&profile,binding);
                // Alternate retained reference and fused chunks under the same owner.
                const bool fused=(block&1)==0;
                const auto result=feedback.run_journal_chunk(count,texture,fused);
                const auto label="coupled variant "+std::to_string(variant)+" chunk "+std::to_string(chunk);
                same_chunk(result,before,expected,binary,generation,label,&profile,binding);
                same_vm(machine,expected,label); same_words(feedback,expected,label);
                if(have_previous) { vm::require_journal_continuation(previous,result); ++checks; }
                previous=result; have_previous=true; done+=count;
            }
            feedback.recommit_last(); same_words(feedback,expected,"journal final receipt recommit holds");
            const auto zero=feedback.run_journal_chunk(0,!texture,false,1);
            same_chunk(zero,expected,expected,binary,generation,"coupled zero identity",&profile,binding);
            vm::require_journal_continuation(previous,zero); ++checks;
        }
    }
}

void terminal_and_no_event_cases() {
    auto emit=cell(0,TOMAGI_OP_EMIT,1); emit.words[3]=4u<<8;
    auto final_emit=cell(1,TOMAGI_OP_EMIT,1); final_emit.words[3]=(2u<<8)|TOMAGI_FLAG_EMIT_HALT;
    const std::vector<vm::Cell48> cells{emit,final_emit}; const auto binary=encode(cells);
    std::vector<vm::State64> initial(3); initial[1].words[11]=1; initial[2].words[15]=TOMAGI_STATUS_HALT;
    atomos::WordProfile profile; profile.x_lut=12;
    for(bool texture:{false,true}) for(bool fused:{false,true}) {
        vm::VM machine(binary,1); machine.set_states(initial); vm::WordFeedback feedback(machine,profile,vm::WordBinding::None);
        Oracle expected(cells,initial); const Oracle before=expected; expected.advance(256,&profile);
        const auto complete=feedback.run_journal_chunk(256,texture,fused);
        same_chunk(complete,before,expected,binary,machine.state_generation(),"EMIT-HALT exact completion",&profile);
        require(complete.status==vm::JournalStatus::Complete&&complete.events.size()==3,"all lanes halt after exactly three fresh emissions");
        require(complete.final_receipts[0].epoch==255&&!complete.final_receipts[0].emitted,"complete journal survives nonemitting final receipt");
        const Oracle terminal_before=expected; expected.advance(7,&profile);
        const auto terminal=feedback.run_journal_chunk(7,!texture,!fused);
        same_chunk(terminal,terminal_before,expected,binary,machine.state_generation(),"after HALT no journal duplicates",&profile);
        vm::require_journal_continuation(complete,terminal); ++checks;
        require(terminal.events.empty()&&terminal.status==vm::JournalStatus::Complete,"terminal continuation is complete empty stream");
    }
    auto nop=cell(0,TOMAGI_OP_NOP); const std::vector<vm::Cell48> no_cells{nop}; const auto no_binary=encode(no_cells);
    for(bool fused:{false,true}) {
        vm::VM no_event(no_binary); std::vector<vm::State64> one(1); one[0].words[15]=TOMAGI_STATUS_EMIT; no_event.set_states(one);
        Oracle expected(no_cells,one); const Oracle before=expected; expected.advance(256);
        const auto result=no_event.run_journal_chunk(256,true,fused);
        same_chunk(result,before,expected,no_binary,no_event.state_generation(),"sticky EMIT status on NOP is not an event");
        require(result.events.empty()&&result.status==vm::JournalStatus::Prefix,"nonterminal no-event execution remains prefix");
    }
    auto repeated=cell(0,TOMAGI_OP_EMIT); repeated.words[3]=1u<<8;
    vm::VM repeat(encode({repeated})); const auto a=repeat.run_journal_chunk(256),b=repeat.run_journal_chunk(7);
    require(a.events.size()==256&&b.events.size()==7,"263 equal payloads retained as 263 events");
    require(a.events.back().epoch==255&&b.events.front().epoch==256&&b.events.back().epoch==262,"repeat payload epochs are never deduplicated");
    vm::require_journal_continuation(a,b); ++checks;
}

void refusals_and_continuation() {
    const auto cells=event_program(); const auto initial=event_states(5); const auto binary=encode(cells);
    vm::VM machine(binary,2); machine.set_states(initial); Oracle expected(cells,initial);
    const U64 generation=machine.state_generation();
    for(bool fused:{false,true}) {
        rejects([&]{machine.run_journal_chunk(7,true,fused,34);},"capacity below lanes*ticks refuses before pure execution");
        same_vm(machine,expected,"pure capacity refusal identity");
        rejects([&]{machine.run_journal_chunk(257,true,fused);},"journal ticks257 refused");
        same_vm(machine,expected,"oversize journal refusal identity");
    }
    const Oracle initial_expected=expected; expected.advance(7);
    const auto first=machine.run_journal_chunk(7,true,true,35);
    same_chunk(first,initial_expected,expected,binary,generation,"exact admitted capacity");
    rejects([&]{machine.run_journal_chunk(7,false,false,1);},"capacity refusal after committed prefix");
    same_vm(machine,expected,"refusal preserves committed prefix state and receipts");
    const Oracle middle=expected; expected.advance(7);
    const auto second=machine.run_journal_chunk(7,false,false,~U64(0));
    same_chunk(second,middle,expected,binary,generation,"large capacity limit does not allocate the limit itself");
    vm::require_journal_continuation(first,second); ++checks;
    rejects([&]{vm::require_journal_continuation(second,first);},"reversed epoch continuation rejected");
    rejects([&]{vm::require_journal_continuation(first,first);},"duplicated nonzero chunk rejected");
    auto changed=second; ++changed.start_epoch;
    rejects([&]{vm::require_journal_continuation(first,changed);},"changed epoch boundary rejected");
    changed=second; ++changed.generation;
    rejects([&]{vm::require_journal_continuation(first,changed);},"changed generation rejected");
    changed=second; ++changed.lanes;
    rejects([&]{vm::require_journal_continuation(first,changed);},"changed lane count rejected");
    changed=second; changed.initial_states[0].words[12]^=1;
    rejects([&]{vm::require_journal_continuation(first,changed);},"changed boundary lineage rejected");
    changed=second; changed.initial_errors[0]^=1;
    rejects([&]{vm::require_journal_continuation(first,changed);},"changed boundary error rejected");
    changed=second; changed.execution=vm::JournalExecution::WordFeedback;
    rejects([&]{vm::require_journal_continuation(first,changed);},"changed execution profile rejected");
    vm::VM unrelated(binary,2); unrelated.set_states(initial); unrelated.run_journal_chunk(7);
    const auto other=unrelated.run_journal_chunk(7);
    require(other.source->owner_id!=first.source->owner_id,"identical source bytes have distinct live owner identities");
    rejects([&]{vm::require_journal_continuation(first,other);},"unrelated owner rejected even with equal program/epoch");
    machine.set_states(initial); machine.run_journal_chunk(7); const auto reset=machine.run_journal_chunk(7);
    require(reset.source==first.source&&reset.generation!=first.generation,"reset retains source but changes generation");
    rejects([&]{vm::require_journal_continuation(first,reset);},"reset generation cannot continue old output");

    atomos::WordProfile profile; profile.x_lut=6;
    vm::VM coupled(binary,2); coupled.set_states(initial); vm::WordFeedback feedback(coupled,profile);
    Oracle word_expected(cells,initial);
    for(bool fused:{false,true}) {
        rejects([&]{feedback.run_journal_chunk(7,true,fused,34);},"coupled capacity refusal precedes q injection");
        same_vm(coupled,word_expected,"coupled capacity VM identity"); same_words(feedback,word_expected,"coupled capacity word identity");
        rejects([&]{feedback.run_journal_chunk(257,false,fused);},"coupled oversized journal refused");
        same_vm(coupled,word_expected,"coupled oversized VM identity"); same_words(feedback,word_expected,"coupled oversized word identity");
    }
    const auto word_first=feedback.run_journal_chunk(7,true,true,35); word_expected.advance(7,&profile,vm::WordBinding::RhoAndVrho);
    const Oracle word_middle=word_expected; const auto word_second=feedback.run_journal_chunk(7,false,false); word_expected.advance(7,&profile,vm::WordBinding::RhoAndVrho);
    same_chunk(word_second,word_middle,word_expected,binary,coupled.state_generation(),"coupled continuation snapshots",&profile,vm::WordBinding::RhoAndVrho);
    vm::require_journal_continuation(word_first,word_second); ++checks;
    changed=word_second; changed.binding=vm::WordBinding::None;
    rejects([&]{vm::require_journal_continuation(word_first,changed);},"changed word binding rejected");
    changed=word_second; changed.word_profile.a0^=1;
    rejects([&]{vm::require_journal_continuation(word_first,changed);},"changed ASA profile rejected");
    changed=word_second; changed.initial_words[0].q^=1;
    rejects([&]{vm::require_journal_continuation(word_first,changed);},"changed boundary q rejected");
    coupled.enqueue_step();
    rejects([&]{feedback.run_journal_chunk(0);},"external advance invalidates zero-work journal borrower");
    rejects([&]{feedback.run_journal_chunk(1);},"external advance invalidates journal borrower");
    coupled.set_states(initial);
    rejects([&]{feedback.run_journal_chunk(0);},"reset invalidates even zero-work journal borrower");
}

void lifetime_and_ordinary_composition() {
    auto emit=cell(0,TOMAGI_OP_EMIT); emit.words[3]=4u<<8;
    const std::vector<vm::Cell48> cells{emit}; const auto binary=encode(cells);
    vm::EmitJournalChunk retained;
    {
        vm::VM source(binary); retained=source.run_journal_chunk(7);
        require(retained.source==source.journal_source(),"chunk retains actual source object");
    }
    require(retained.source&&retained.source->canonical_tmg==binary&&retained.events.size()==7,"journal and exact program survive VM destruction");
    require(vm::decode_emit_payload(retained.events.back().flags,retained.events.back().payload)==decoded(emit.words[3],emit.words[10]),"retained event remains materializable after source destruction");
    vm::VM original(binary); const auto first=original.run_journal_chunk(7);
    vm::VM moved(std::move(original)); const auto second=moved.run_journal_chunk(7,false,false);
    require(first.source==second.source,"VM move preserves immutable journal source identity");
    vm::require_journal_continuation(first,second); ++checks;

    std::vector<vm::State64> initial(1); Oracle expected(cells,initial);
    vm::VM machine(binary); machine.enqueue_batch(13); expected.advance(13);
    const Oracle before=expected; expected.advance(7);
    const auto journal=machine.run_journal_chunk(7,false,true);
    same_chunk(journal,before,expected,binary,machine.state_generation(),"journal begins at nonzero ordinary epoch");
    machine.run_steps(3,false); expected.advance(3);
    const Oracle gap_before=expected; expected.advance(1);
    const auto after_gap=machine.run_journal_chunk(1,true,false);
    same_chunk(after_gap,gap_before,expected,binary,machine.state_generation(),"journal after ordinary reference gap");
    rejects([&]{vm::require_journal_continuation(journal,after_gap);},"unrecorded ordinary steps cannot be called a contiguous complete journal");

    atomos::WordProfile profile; profile.x_lut=6;
    std::vector<U64> q{0x1234567800000042ULL}; vm::WordFeedback feedback(machine,profile,vm::WordBinding::RhoAndVrho,q);
    expected.words[0].q=q[0];
    feedback.run_steps_fused(7); expected.advance(7,&profile,vm::WordBinding::RhoAndVrho);
    const Oracle coupled_before=expected; expected.advance(3,&profile,vm::WordBinding::RhoAndVrho);
    const auto coupled=feedback.run_journal_chunk(3,true,true);
    same_chunk(coupled,coupled_before,expected,binary,machine.state_generation(),"journal after ordinary fused feedback",&profile,vm::WordBinding::RhoAndVrho);
    feedback.run_steps(1,false); expected.advance(1,&profile,vm::WordBinding::RhoAndVrho);
    const Oracle coupled_gap_before=expected; expected.advance(1,&profile,vm::WordBinding::RhoAndVrho);
    const auto coupled_gap=feedback.run_journal_chunk(1,false,false);
    same_chunk(coupled_gap,coupled_gap_before,expected,binary,machine.state_generation(),"journal after ordinary reference feedback",&profile,vm::WordBinding::RhoAndVrho);
    rejects([&]{vm::require_journal_continuation(coupled,coupled_gap);},"unrecorded feedback step cannot be hidden in stream continuation");
    same_vm(machine,expected,"mixed ordinary/journal VM"); same_words(feedback,expected,"mixed ordinary/journal words");

    vm::VM empty(binary); empty.set_states({}); Oracle empty_expected(cells,{});
    rejects([&]{empty.run_journal_chunk(7);},"journal profile refuses zero lanes before execution");
    same_vm(empty,empty_expected,"zero-lane refusal preserves epoch");
}

} // namespace

int main() {
    try {
        payload_decoder(); pure_journal_cases(); coupled_journal_cases(); terminal_and_no_event_cases();
        refusals_and_continuation(); lifetime_and_ordinary_composition();
        std::cout<<"tomagi_journal_tests: "<<checks<<" checks passed; State64 words "<<state_words
                 <<", Receipt40 words "<<receipt_words<<", WordState64 words "<<feedback_words
                 <<", event fields "<<event_fields<<", materialized bytes "<<output_bytes
                 <<"; original C transitions plus independent per-bit ASA/NA/JK; full ordered EMIT journals; both fetch paths; reference/fused chunks1/7/32/256\n";
        return 0;
    } catch(const std::exception& error) {
        std::cerr<<"tomagi_journal_tests: "<<error.what()<<'\n'; return 1;
    }
}
