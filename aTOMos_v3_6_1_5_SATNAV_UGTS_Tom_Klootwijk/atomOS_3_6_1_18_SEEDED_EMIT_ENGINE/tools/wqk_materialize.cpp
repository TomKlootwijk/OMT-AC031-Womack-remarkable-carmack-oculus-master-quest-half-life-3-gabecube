#include "atomos/tomagi_journal.hpp"
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace vm=atomos::tomagi;
using U32=std::uint32_t;using U64=std::uint64_t;
using Clock=std::chrono::steady_clock;
namespace {
void need(bool ok,const std::string& why){if(!ok)throw std::invalid_argument(why);}
double ms(Clock::time_point a,Clock::time_point b){return std::chrono::duration<double,std::milli>(b-a).count();}
U32 number(const std::string& s){
    need(!s.empty(),"empty integer");U64 n=0;
    for(char c:s){need(c>='0'&&c<='9',"expected decimal uint32");n=n*10+U32(c-'0');need(n<=0xffffffffULL,"integer exceeds uint32");}
    return U32(n);
}
std::string quoted(const std::string& s){
    std::ostringstream out;out<<'"';
    for(unsigned char c:s){if(c=='"'||c=='\\')out<<'\\'<<char(c);else if(c<32)out<<"\\u"<<std::hex<<std::setw(4)<<std::setfill('0')<<unsigned(c)<<std::dec;else out<<char(c);}
    out<<'"';return out.str();
}
struct Options{std::filesystem::path program,output,report;U32 steps=0,chunk=32;bool has_steps=false,texture=true,fused=true;};
bool aliases(const std::filesystem::path& a,const std::filesystem::path& b){
    if(std::filesystem::absolute(a).lexically_normal()==std::filesystem::absolute(b).lexically_normal())return true;
    return std::filesystem::exists(a)&&std::filesystem::exists(b)&&std::filesystem::equivalent(a,b);
}
Options parse(int argc,char** argv){
    Options o;std::set<std::string> seen;
    for(int i=1;i<argc;++i){const std::string key=argv[i];need(seen.insert(key).second,"duplicate option");need(i+1<argc,"missing option value");const std::string value=argv[++i];
        if(key=="--program")o.program=value;else if(key=="--output")o.output=value;else if(key=="--report")o.report=value;
        else if(key=="--steps"){o.steps=number(value);o.has_steps=true;}
        else if(key=="--chunk"){o.chunk=number(value);need(o.chunk>=1&&o.chunk<=256,"chunk must be 1..256");}
        else if(key=="--fetch"){need(value=="texture"||value=="global","fetch must be texture or global");o.texture=value=="texture";}
        else if(key=="--dispatch"){need(value=="fused"||value=="reference","dispatch must be fused or reference");o.fused=value=="fused";}
        else throw std::invalid_argument("unknown option: "+key);
    }
    need(!o.program.empty()&&!o.output.empty(),"--program and --output are required");
    need(!aliases(o.program,o.output),"artifact output aliases source program");
    if(!o.report.empty()){need(!aliases(o.program,o.report),"report aliases source program");need(!aliases(o.output,o.report),"report aliases artifact output");}
    return o;
}
std::vector<std::uint8_t> read(const std::filesystem::path& path){
    std::ifstream in(path,std::ios::binary|std::ios::ate);need(bool(in),"cannot open source program");
    const auto end=in.tellg();need(end>=std::streampos(128),"source shorter than header");
    const U64 count=U64(static_cast<std::streamoff>(end));
    need(count<=std::numeric_limits<std::size_t>::max()&&count<=U64(std::numeric_limits<std::streamsize>::max()),"source exceeds host size limits");
    std::vector<std::uint8_t> bytes(static_cast<std::size_t>(count));in.seekg(0);
    in.read(reinterpret_cast<char*>(bytes.data()),std::streamsize(bytes.size()));need(bool(in),"incomplete source read");return bytes;
}
void write(const std::filesystem::path& path,const char* bytes,std::size_t count){
    need(count<=std::size_t(std::numeric_limits<std::streamsize>::max()),"output exceeds stream size");
    if(!path.parent_path().empty())std::filesystem::create_directories(path.parent_path());
    std::ofstream out(path,std::ios::binary|std::ios::trunc);need(bool(out),"cannot open output");
    if(count)out.write(bytes,std::streamsize(count));out.flush();need(bool(out),"output write failed");
}
}
int main(int argc,char** argv){
    try{
        if(argc==2&&std::string(argv[1])=="--help"){
            std::cout<<"wqk_materialize --program FILE.tmg --output FILE.bin [--report FILE.json] [--steps N] [--chunk 1..256] [--fetch texture|global] [--dispatch fused|reference]\n"
                     <<"Canonical one-lane seeded byte materialization. Steps default to the source horizon. Complete requires HALT with no fault; prefix/fault reports do not write artifact bytes. All requested epochs run, including held slots after HALT.\n";return 0;
        }
        const auto o=parse(argc,argv);const auto begin=Clock::now();const auto bytes=read(o.program);
        vm::VM machine(bytes);need((machine.program_flags()&3u)==3u,"materialization requires seeded profile and emitted-byte flags");
        const U32 steps=o.has_steps?o.steps:machine.default_ticks();
        std::vector<vm::EmitEvent> events;need(U64(steps)<=events.max_size(),"event capacity exceeds host range");events.reserve(steps);
        std::vector<std::uint8_t> artifact;need(U64(steps)*4<=artifact.max_size(),"artifact capacity exceeds host range");artifact.reserve(std::size_t(U64(steps)*4));
        const auto source=machine.journal_source();need(source->canonical_tmg==bytes,"GPU-expanded program bytes differ from input");
        const auto prepared=Clock::now();vm::EmitJournalChunk previous,last;bool have_previous=false;U64 chunks=0;
        for(U32 done=0;done<steps;){
            const U32 n=std::min(o.chunk,steps-done);auto next=machine.run_journal_chunk(n,o.texture,o.fused);
            if(have_previous)vm::require_journal_continuation(previous,next);
            need(next.lanes==1&&next.source==source,"unexpected journal source or lane count");
            for(const auto& e:next.events){
                need(e.lane==0,"unexpected materializer lane");const auto payload=vm::decode_emit_payload(e.flags,e.payload);
                events.push_back(e);artifact.insert(artifact.end(),payload.begin(),payload.end());
            }
            done+=n;++chunks;previous=std::move(next);have_previous=true;
        }
        if(have_previous)last=std::move(previous);else last=machine.run_journal_chunk(0,o.texture,o.fused);
        const auto executed=Clock::now();const bool complete=last.status==vm::JournalStatus::Complete;
        const char* status=complete?"complete":last.status==vm::JournalStatus::Faulted?"faulted":"prefix";
        need(!complete||!events.empty(),"completed source trace contains no EMIT records");
        if(complete)write(o.output,reinterpret_cast<const char*>(artifact.data()),artifact.size());
        const auto persisted=Clock::now();std::ostringstream out;out<<std::setprecision(10);
        out<<"{\n  \"profile\":\"ATOMOS-EMIT-JOURNAL-R1\",\n  \"status\":"<<quoted(status)
           <<",\n  \"owner_id\":"<<source->owner_id<<", \"generation\":"<<last.generation
           <<",\n  \"start_epoch\":0, \"end_epoch\":"<<last.end_epoch<<", \"error\":"<<last.errors.at(0)
           <<",\n  \"program_flags\":"<<machine.program_flags()<<", \"program_bytes\":"<<bytes.size()
           <<", \"expanded_source_bytes_equal_input\":true,\n  \"event_count\":"<<events.size()<<", \"output_bytes\":"<<artifact.size()
           <<", \"artifact_written\":"<<(complete?"true":"false")
           <<",\n  \"dispatch\":"<<quoted(o.fused?"fused":"reference")<<", \"fetch\":"<<quoted(o.texture?"texture":"global")
           <<", \"chunk\":"<<o.chunk<<", \"chunks\":"<<chunks
#ifdef ATOMOS_WIDE_PHASE_REFERENCE
           <<", \"phase_lowering\":\"R17 signed-wide reference\""
#else
           <<", \"phase_lowering\":\"exact bounded 32-bit phase and seam\""
#endif
           <<",\n  \"timings_ms\":{\"setup\":"<<ms(begin,prepared)<<", \"journal_wall\":"<<ms(prepared,executed)
           <<", \"artifact_write\":"<<ms(executed,persisted)<<", \"host_through_artifact\":"<<ms(begin,persisted)<<"},\n"
           <<"  \"timing_scope\":\"Host wall time includes journal allocation, execution, transfers, compaction and decoding; no device-only timing claim. JSON encoding/report output are excluded.\",\n"
           <<"  \"source_execution_scope\":\"Native Cell48 execution and ordered emitted-byte materialization; host formal.evaluate is not evaluated on the GPU.\",\n"
           <<"  \"final_state_words\":[";
        for(unsigned i=0;i<16;++i){if(i)out<<',';out<<last.final_states.at(0).words[i];}out<<"],\n  \"events\":[\n";
        for(std::size_t i=0;i<events.size();++i){const auto& e=events[i];if(i)out<<",\n";
            out<<"    {\"sequence\":"<<i<<",\"epoch\":"<<e.epoch<<",\"lane\":"<<e.lane<<",\"cell_before\":"<<e.cell_before
               <<",\"flags\":"<<e.flags<<",\"payload\":"<<e.payload<<",\"byte_count\":"<<((e.flags>>8)&7u)
               <<",\"byte_order\":"<<quoted((e.flags&(1u<<11))?"big":"little")<<",\"lineage\":"<<e.lineage
               <<",\"cell_after\":"<<e.cell_after<<",\"branch_after\":"<<e.branch_after<<",\"status_after\":"<<e.status_after<<'}';
        }
        out<<"\n  ]\n}\n";const auto json=out.str();
        if(o.report.empty())std::cout<<json;else write(o.report,json.data(),json.size());
        return complete?0:2;
    }catch(const std::exception& e){std::cerr<<"wqk_materialize: "<<e.what()<<'\n';return 1;}
}
