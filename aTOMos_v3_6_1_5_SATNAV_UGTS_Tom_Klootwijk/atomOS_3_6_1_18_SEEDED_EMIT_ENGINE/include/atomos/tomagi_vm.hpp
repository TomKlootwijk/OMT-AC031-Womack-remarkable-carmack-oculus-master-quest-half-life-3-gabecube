#pragma once
#include <cstdint>
#include <memory>
#include <vector>

namespace atomos { namespace tomagi {
struct JournalSource;
struct EmitJournalChunk;

struct alignas(16) State64 { std::uint32_t words[16]{}; };
struct alignas(16) Cell48 { std::uint32_t words[12]{}; };
static_assert(sizeof(State64)==64 && sizeof(Cell48)==48,"TOMAGI word ABI");
enum class Error : std::uint32_t { None=0, BadCell=1, BadOpcode=2, BadRadix=3 };
struct Receipt {
    std::uint64_t epoch=0;
    std::uint32_t executed=0,emitted=0,cell_before=0,opcode=0;
    std::uint32_t flags=0,payload=0,branch_after=0,error=0;
};
static_assert(sizeof(Receipt)==40,"R16 receipt ABI");

// POD CUDA view; texture is the CUDA texture-object handle represented as u64.
// State/error/receipt arrays have state_count elements. Bank capacity is 2^shift;
// the final bank's count can be smaller. Pointers become stale after set_states;
// generation changes on every successful reset even if pointers are reused.
struct ProgramBank {
    const Cell48* cells=nullptr;
    std::uint64_t texture=0;
    std::uint32_t count=0,reserved=0;
};
struct DeviceView {
    State64* states=nullptr;
    std::uint32_t* errors=nullptr;
    Receipt* receipts=nullptr;
    const ProgramBank* banks=nullptr;
    std::uint32_t state_count=0,cell_count=0,bank_shift=0,bank_mask=0,seed=0;
    std::uint64_t epoch=0,generation=0;
};

// Enqueues one canonical transition per state on the selected CUDA stream.
// No host readback or synchronization. Errors are a separate sticky sidecar;
// State64 is unchanged on a refused transition. This does not update a VM's
// host epoch counter; use VM::enqueue_step for ordinary ownership.
// Use one ordered stream or explicit cross-stream events for the same lanes;
// neither this hook nor enqueue_step chains independent streams automatically.
void launch_step(DeviceView view,bool texture=true,void* cuda_stream=nullptr);

class VM {
public:
    // Optional nonsemantic bank cap for deployment/validation; zero selects
    // the device-bounded default. The actual capacity is a power of two.
    explicit VM(const std::vector<std::uint8_t>& canonical_tmg,
                std::uint32_t max_cells_per_bank=0);
    ~VM();
    VM(VM&&) noexcept;
    VM& operator=(VM&&) noexcept;
    VM(const VM&)=delete;
    VM& operator=(const VM&)=delete;

    // Constructor starts one entry_state(). Explicit states retain every raw
    // word, including cell/phase/branch; reset clears faults, receipts and epoch.
    State64 header_state() const;
    State64 entry_state() const;
    void set_states(const std::vector<State64>& states);
    // Caller serializes access to this owner and its resident lane arrays.
    void enqueue_step(bool texture=true,void* cuda_stream=nullptr);
    // One fused launch per independent lane. Accepts0..256 transitions;
    // zero is an identity. Only the final receipt is observable at completion.
    // No external mutation/observation is allowed within the fused chunk.
    void enqueue_batch(std::uint32_t ticks,bool texture=true,void* cuda_stream=nullptr);
    // Opt-in synchronous ordered EMIT output; ticks0..256. A nonzero
    // max_events smaller than lanes*ticks refuses before execution.
    // Include tomagi_journal.hpp for the returned versioned chunk contract.
    EmitJournalChunk run_journal_chunk(std::uint32_t ticks,bool texture=true,
                                      bool fused=true,std::uint64_t max_events=0);
    std::shared_ptr<const JournalSource> journal_source() const;
    void synchronize() const;
    void run_steps(std::uint32_t ticks,bool texture=true,bool capture_receipts=false);

    std::vector<State64> read_states() const;
    std::vector<std::uint32_t> read_errors() const;
    std::vector<Receipt> read_receipts() const;
    // Rectangular dispatch-major/state-major trace from the latest run_steps
    // with capture=true. Halted/faulted slots have executed=emitted=0.
    std::vector<Receipt> read_trace() const;
    std::vector<std::uint32_t> read_program_words() const;
    DeviceView device_view() const;
    std::uint32_t cell_count() const;
    std::uint32_t program_flags() const;
    std::uint32_t default_ticks() const;
    std::uint64_t epoch() const;
    std::uint64_t state_generation() const;
    std::uint64_t resident_bytes() const;
private:
    friend class WordFeedback;
    // Only the owning coupled executor may account for its successful launch.
    // The supplied starting epoch must still match this serialized owner.
    void advance_fused_epoch(std::uint64_t expected,std::uint32_t ticks);
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

}} // namespace atomos::tomagi
