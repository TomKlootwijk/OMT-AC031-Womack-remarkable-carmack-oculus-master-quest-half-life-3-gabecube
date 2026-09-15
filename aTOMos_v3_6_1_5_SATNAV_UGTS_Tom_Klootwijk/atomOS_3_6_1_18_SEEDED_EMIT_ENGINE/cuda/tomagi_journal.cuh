#pragma once
#include "atomos/tomagi_journal.hpp"
#include <cuda_runtime.h>

namespace atomos { namespace tomagi { namespace detail {
struct JournalDeviceView {
    EmitEvent* events=nullptr;
    std::uint32_t* counts=nullptr;
    std::uint32_t* overflow=nullptr;
    std::uint32_t lanes=0,steps=0;
};
__device__ inline void append_emit(JournalDeviceView j,std::uint32_t lane,
                                   const State64& state,const Receipt& r){
    if(!r.executed||!r.emitted)return;
    const std::uint32_t count=j.counts[lane];
    if(count>=j.steps){j.overflow[lane]=1;return;} // asserted impossible for admitted canonical chunks
    EmitEvent e{};e.epoch=r.epoch;e.lane=lane;e.cell_before=r.cell_before;
    e.flags=r.flags;e.payload=r.payload;e.lineage=state.words[12];
    e.cell_after=state.words[11];e.branch_after=r.branch_after;e.status_after=state.words[15];
    j.events[std::uint64_t(lane)*j.steps+count]=e;j.counts[lane]=count+1;
}
// Allocates GPU and host worst-case storage before any corresponding mutation.
// Both methods synchronize at the explicit observation boundary. Exclusive VM
// ownership is required; no same-lane work may run concurrently on any stream.
class JournalCapture {
public:
    JournalCapture(VM& vm,std::uint32_t ticks,std::uint64_t max_events,
                   const WordState* words=nullptr);
    ~JournalCapture();
    JournalCapture(const JournalCapture&)=delete;
    JournalCapture& operator=(const JournalCapture&)=delete;
    JournalDeviceView view()const;
    EmitJournalChunk finish(VM& vm,const WordState* words=nullptr,
                           WordBinding binding=WordBinding::None,
                           atomos::WordProfile profile={});
private:
    struct Impl;std::unique_ptr<Impl> impl_;
};
void launch_journal_batch(DeviceView vm,JournalDeviceView journal,std::uint32_t ticks,bool texture);
void launch_journal_receipt(DeviceView vm,JournalDeviceView journal);
}}} // namespace atomos::tomagi::detail
