#pragma once
#include "atomos/tomagi_vm.hpp"
#include "atomos/texture_index.hpp"
#include <memory>
#include <vector>

namespace atomos { namespace tomagi {
enum class WordBinding : std::uint32_t { None=0, RhoAndVrho=1 };
struct WordState {
    std::uint64_t q=0,parity=0,last_epoch=0,last_drive=0;
    std::uint64_t hinges=0,initialized=0,status=0,reserved=0;
};
static_assert(sizeof(WordState)==64,"R16 feedback word ABI");
struct WordFeedbackStats { double device_ms=0,wall_ms=0; std::uint32_t steps=0,lanes=0; };

// Versioned extension of the pure VM. The VM must outlive this borrower and
// must not be moved, reset, or advanced externally while the borrower is used.
// Each ordered phase is inject old q -> canonical VM step -> fresh EMIT commit.
// No per-step host readback. The binding preserves all 64 q bits in two words;
// TOMAGI's coordinate interpretation remains the original fixed-word profile.
class WordFeedback {
public:
    WordFeedback(VM& source,const atomos::WordProfile& profile,
                 WordBinding binding=WordBinding::RhoAndVrho,
                 const std::vector<std::uint64_t>& initial_words={});
    ~WordFeedback();
    WordFeedback(const WordFeedback&)=delete;
    WordFeedback& operator=(const WordFeedback&)=delete;
    void run_steps(std::uint32_t count,bool texture=true);
    // Reconsume the last receipt without advancing the VM: same event is a hold.
    void recommit_last();
    std::vector<WordState> readback() const;
    const WordFeedbackStats& stats() const;
private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};
}} // namespace atomos::tomagi
