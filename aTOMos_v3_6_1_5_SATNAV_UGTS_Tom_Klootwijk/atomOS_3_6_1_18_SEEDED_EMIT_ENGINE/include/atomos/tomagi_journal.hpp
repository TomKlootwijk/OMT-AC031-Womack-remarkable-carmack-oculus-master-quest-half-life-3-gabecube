#pragma once
#include "atomos/tomagi_feedback.hpp"
#include <memory>
#include <vector>

namespace atomos { namespace tomagi {
// ATOMOS-EMIT-JOURNAL-R1. This is a new compact observation schema, not the
// vendor TRACE_FIELDS schema. A source survives its VM through shared ownership.
struct JournalSource {
    std::uint64_t owner_id=0; // unique in this process; not a cryptographic hash
    std::vector<std::uint8_t> canonical_tmg; // exact complete immutable source
};
struct EmitEvent {
    std::uint64_t epoch=0;
    std::uint32_t lane=0,cell_before=0,flags=0,payload=0;
    std::uint32_t lineage=0,cell_after=0,branch_after=0,status_after=0;
};
static_assert(sizeof(EmitEvent)==40,"R18 ordered EMIT record");
enum class JournalStatus : std::uint32_t { Prefix=0, Complete=1, Faulted=2 };
enum class JournalExecution : std::uint32_t { Pure=0, WordFeedback=1 };
struct EmitJournalChunk {
    std::shared_ptr<const JournalSource> source;
    std::uint64_t generation=0,start_epoch=0,end_epoch=0;
    std::uint32_t lanes=0;
    JournalStatus status=JournalStatus::Prefix;
    JournalExecution execution=JournalExecution::Pure;
    WordBinding binding=WordBinding::None;
    atomos::WordProfile word_profile{};
    // Events are lane-major; [lane_offsets[l],lane_offsets[l+1]) has strictly
    // increasing epochs. GPU scheduling order is never an output order.
    std::vector<std::uint64_t> lane_offsets;
    std::vector<EmitEvent> events;
    std::vector<State64> initial_states,final_states;
    std::vector<std::uint32_t> initial_errors,errors;
    std::vector<Receipt> final_receipts;
    std::vector<WordState> initial_words,final_words; // empty for pure execution
};
// Rejects unrelated source/reset/epoch/lane/profile or changed boundary state.
// Checks completed chunk boundaries; does not cryptographically authenticate
// caller-edited records. External deterministic replay supplies that evidence.
void require_journal_continuation(const EmitJournalChunk& previous,const EmitJournalChunk& next);
// Source-compatible flag/count/endian decoding. Reject count outside1..4.
std::vector<std::uint8_t> decode_emit_payload(std::uint32_t flags,std::uint32_t payload);
}} // namespace atomos::tomagi
