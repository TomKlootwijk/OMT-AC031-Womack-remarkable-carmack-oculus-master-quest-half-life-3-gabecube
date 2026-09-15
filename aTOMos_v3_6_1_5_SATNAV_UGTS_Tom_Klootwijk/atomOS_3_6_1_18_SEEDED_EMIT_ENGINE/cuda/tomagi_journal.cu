#include "tomagi_journal.cuh"
#include "tomagi_transition.cuh"
#include <algorithm>
#include <cstring>
#include <limits>
#include <stdexcept>
#include <utility>

namespace atomos { namespace tomagi { namespace {
void cu(cudaError_t e){if(e!=cudaSuccess)throw std::runtime_error(cudaGetErrorString(e));}
void need(bool ok,const char* message){if(!ok)throw std::invalid_argument(message);}
std::size_t checked_bytes(std::uint64_t n,std::size_t size){
    need(n<=std::numeric_limits<std::size_t>::max()/size,"journal allocation size overflow");
    return std::size_t(n)*size;
}
template<class T>void copy_from(std::vector<T>& host,const T* device){
    if(!host.empty())cu(cudaMemcpy(host.data(),device,host.size()*sizeof(T),cudaMemcpyDeviceToHost));
}
template<class T>bool same(const std::vector<T>& a,const std::vector<T>& b){
    return a.size()==b.size()&&(a.empty()||std::memcmp(a.data(),b.data(),a.size()*sizeof(T))==0);
}
bool same_profile(const atomos::WordProfile& a,const atomos::WordProfile& b){
    return a.valid_mask==b.valid_mask&&a.a0==b.a0&&a.n0==b.n0&&a.b0==b.b0&&
        a.a1==b.a1&&a.n1==b.n1&&a.b1==b.b1&&a.x_lut==b.x_lut&&a.j_lut==b.j_lut&&a.k_lut==b.k_lut;
}
} // namespace
std::vector<std::uint8_t> decode_emit_payload(std::uint32_t flags,std::uint32_t payload){
    const unsigned count=(flags>>8)&7u;need(count>=1&&count<=4,"EMIT byte count must be1..4");
    std::vector<std::uint8_t> bytes(count);
    for(unsigned k=0;k<count;++k){unsigned byte=(flags&(1u<<11))?count-1-k:k;bytes[k]=std::uint8_t(payload>>(8*byte));}
    return bytes;
}
void require_journal_continuation(const EmitJournalChunk& previous,const EmitJournalChunk& next){
    need(previous.source&&next.source&&previous.source==next.source&&previous.source->owner_id==next.source->owner_id,
         "journal source owner differs");
    need(previous.generation==next.generation&&previous.lanes==next.lanes&&previous.end_epoch==next.start_epoch,
         "journal generation, lane count or contiguous epoch differs");
    need(previous.execution==next.execution&&previous.binding==next.binding&&same_profile(previous.word_profile,next.word_profile),
         "journal execution profile differs");
    need(same(previous.final_states,next.initial_states)&&same(previous.errors,next.initial_errors)&&
         same(previous.final_words,next.initial_words),"journal boundary state differs");
}
namespace detail { namespace {
template<bool Texture>__global__ void journal_batch(DeviceView vm,JournalDeviceView journal,std::uint32_t ticks){
    const std::uint64_t lane=std::uint64_t(blockIdx.x)*blockDim.x+threadIdx.x;if(lane>=vm.state_count)return;
    State64 state=vm.states[lane];std::uint32_t fault=vm.errors[lane];Receipt receipt{};
    const std::uint64_t first=vm.epoch;
    for(std::uint32_t step=0;step<ticks;++step){
        vm.epoch=first+step;transition<Texture>(vm,state,fault,receipt);
        append_emit(journal,std::uint32_t(lane),state,receipt);
    }
    vm.states[lane]=state;vm.errors[lane]=fault;vm.receipts[lane]=receipt;
}
__global__ void journal_receipt(DeviceView vm,JournalDeviceView journal){
    const std::uint64_t lane=std::uint64_t(blockIdx.x)*blockDim.x+threadIdx.x;if(lane>=vm.state_count)return;
    append_emit(journal,std::uint32_t(lane),vm.states[lane],vm.receipts[lane]);
}
} // namespace
struct JournalCapture::Impl {
    EmitJournalChunk result;
    JournalDeviceView device;
    std::vector<std::uint32_t> counts,overflow;
    bool coupled=false,finished=false;
    void release()noexcept{cudaFree(device.events);cudaFree(device.counts);cudaFree(device.overflow);}
    ~Impl(){release();}
};
JournalCapture::JournalCapture(VM& vm,std::uint32_t ticks,std::uint64_t max_events,const WordState* words)
    :impl_(new Impl){
    need(ticks<=256,"journal chunk exceeds256 transitions");
    const auto view=vm.device_view();need(view.state_count>0,"journal requires at least one lane");
    need(ticks<=std::numeric_limits<std::uint64_t>::max()-view.epoch,"journal epoch range overflows");
    const std::uint64_t slots=std::uint64_t(view.state_count)*ticks;
    need(!max_events||max_events>=slots,"journal capacity below proven lanes*steps maximum");
    const auto bytes=checked_bytes(slots,sizeof(EmitEvent));
    checked_bytes(std::uint64_t(view.state_count)+1,sizeof(std::uint64_t));
    auto& p=*impl_;p.coupled=words!=nullptr;
    auto& r=p.result;r.source=vm.journal_source();r.generation=view.generation;
    r.start_epoch=view.epoch;r.end_epoch=view.epoch+ticks;r.lanes=view.state_count;
    r.execution=p.coupled?JournalExecution::WordFeedback:JournalExecution::Pure;
    r.events.resize(std::size_t(slots));r.lane_offsets.resize(std::size_t(r.lanes)+1);
    r.initial_states.resize(r.lanes);r.final_states.resize(r.lanes);
    r.initial_errors.resize(r.lanes);r.errors.resize(r.lanes);r.final_receipts.resize(r.lanes);
    if(p.coupled){r.initial_words.resize(r.lanes);r.final_words.resize(r.lanes);}
    p.counts.resize(r.lanes);p.overflow.resize(r.lanes);p.device.lanes=r.lanes;p.device.steps=ticks;
    // Every potentially large allocation is complete before any VM transition.
    if(slots){cu(cudaMalloc(reinterpret_cast<void**>(&p.device.events),bytes));cu(cudaMemset(p.device.events,0,bytes));}
    cu(cudaMalloc(reinterpret_cast<void**>(&p.device.counts),r.lanes*sizeof(std::uint32_t)));
    cu(cudaMalloc(reinterpret_cast<void**>(&p.device.overflow),r.lanes*sizeof(std::uint32_t)));
    cu(cudaMemset(p.device.counts,0,r.lanes*sizeof(std::uint32_t)));
    cu(cudaMemset(p.device.overflow,0,r.lanes*sizeof(std::uint32_t)));
    vm.synchronize();copy_from(r.initial_states,view.states);copy_from(r.initial_errors,view.errors);
    if(p.coupled)copy_from(r.initial_words,words);
}
JournalCapture::~JournalCapture()=default;
JournalDeviceView JournalCapture::view()const{return impl_->device;}
EmitJournalChunk JournalCapture::finish(VM& vm,const WordState* words,WordBinding binding,atomos::WordProfile profile){
    auto& p=*impl_;auto& r=p.result;need(!p.finished,"journal already drained");
    need((words!=nullptr)==p.coupled,"journal word-state binding changed");
    need(vm.state_generation()==r.generation&&vm.epoch()==r.end_epoch&&vm.journal_source()==r.source,
         "journal owner changed during chunk");
    const auto vmview=vm.device_view();need(vmview.state_count==r.lanes,"journal lane count changed during chunk");
    vm.synchronize();copy_from(r.events,p.device.events);copy_from(p.counts,p.device.counts);copy_from(p.overflow,p.device.overflow);
    copy_from(r.final_states,vmview.states);copy_from(r.errors,vmview.errors);copy_from(r.final_receipts,vmview.receipts);
    if(p.coupled){copy_from(r.final_words,words);r.binding=binding;r.word_profile=profile;}
    std::size_t out=0;
    for(std::uint32_t lane=0;lane<r.lanes;++lane){
        need(!p.overflow[lane]&&p.counts[lane]<=p.device.steps,"journal overflow: output is incomplete");
        r.lane_offsets[lane]=out;std::uint64_t previous=0;
        for(std::uint32_t j=0;j<p.counts[lane];++j){
            const auto e=r.events[std::uint64_t(lane)*p.device.steps+j];
            need(e.lane==lane&&e.epoch>=r.start_epoch&&e.epoch<r.end_epoch&&(!j||e.epoch>previous),
                 "journal event ordering or epoch is invalid");
            previous=e.epoch;r.events[out++]=e;
        }
    }
    r.lane_offsets[r.lanes]=out;r.events.resize(out);
    bool halted=true,faulted=false;
    for(std::uint32_t lane=0;lane<r.lanes;++lane){halted=halted&&((r.final_states[lane].words[15]&1u)!=0);
        faulted=faulted||r.errors[lane]||(p.coupled&&r.final_words[lane].status);}
    r.status=faulted?JournalStatus::Faulted:halted?JournalStatus::Complete:JournalStatus::Prefix;
    p.finished=true;return std::move(r);
}
void launch_journal_batch(DeviceView vm,JournalDeviceView journal,std::uint32_t ticks,bool texture){
    need(ticks>=1&&ticks<=256&&journal.lanes==vm.state_count&&journal.steps==ticks,"invalid journal batch view");
    const unsigned blocks=unsigned((std::uint64_t(vm.state_count)+127)/128);
    if(texture)journal_batch<true><<<blocks,128>>>(vm,journal,ticks);else journal_batch<false><<<blocks,128>>>(vm,journal,ticks);
    cu(cudaGetLastError());
}
void launch_journal_receipt(DeviceView vm,JournalDeviceView journal){
    need(journal.lanes==vm.state_count&&journal.steps>0,"invalid journal receipt view");
    journal_receipt<<<unsigned((std::uint64_t(vm.state_count)+127)/128),128>>>(vm,journal);cu(cudaGetLastError());
}
} // namespace detail
}} // namespace atomos::tomagi
