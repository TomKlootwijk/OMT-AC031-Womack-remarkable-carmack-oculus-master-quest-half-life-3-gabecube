#include "atomos/tomagi_feedback.hpp"
#include "tomagi.h" // Unmodified, separately compiled canonical C transition.
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
U64 checks = 0, compared_state_words = 0, compared_receipt_words = 0,
    compared_feedback_words = 0;
constexpr U32 Seed = 0x93ab71cdu;

void require(bool yes, const std::string& why) {
    ++checks;
    if (!yes) throw std::runtime_error(why);
}
template<class F> void rejects(F&& f, const std::string& why) {
    bool refused = false;
    try { f(); } catch (const std::exception&) { refused = true; }
    require(refused, why);
}
void cuda_check(cudaError_t error) {
    if (error != cudaSuccess) throw std::runtime_error(cudaGetErrorString(error));
}
int signed_word(U32 x) { return x <= 0x7fffffffu ? int(x) : -1 - int(~x); }
TomagiState to_c(const vm::State64& w) {
    return {signed_word(w.words[0]), signed_word(w.words[1]), signed_word(w.words[2]), signed_word(w.words[3]),
            signed_word(w.words[4]), signed_word(w.words[5]), signed_word(w.words[6]), signed_word(w.words[7]),
            w.words[8], w.words[9], w.words[10], w.words[11], w.words[12], w.words[13],
            signed_word(w.words[14]), w.words[15]};
}
vm::State64 from_c(const TomagiState& s) {
    return {{U32(s.rho), U32(s.theta), U32(s.tick), U32(s.phi), U32(s.vrho), U32(s.vtheta), U32(s.vtick), U32(s.vphi),
             s.orientation, s.sheet, s.branch, s.cell, s.lineage, s.output, U32(s.residual), s.status}};
}
TomagiCell to_c(const vm::Cell48& c) {
    return {c.words[0], c.words[1], c.words[2], c.words[3], signed_word(c.words[4]), signed_word(c.words[5]),
            signed_word(c.words[6]), signed_word(c.words[7]), c.words[8], c.words[9], c.words[10], c.words[11]};
}
void put(std::vector<std::uint8_t>& b, std::size_t at, U32 value) {
    for (unsigned k = 0; k < 4; ++k) b.at(at + k) = std::uint8_t(value >> (8 * k));
}
std::vector<std::uint8_t> encode(const std::vector<vm::Cell48>& cells) {
    std::vector<std::uint8_t> b(128 + 48 * cells.size());
    const char magic[8] = {'T','O','M','A','G','I','1',0};
    std::memcpy(b.data(), magic, 8);
    put(b, 8, 0x10000); put(b, 12, 3); put(b, 16, U32(cells.size()));
    put(b, 24, Seed); put(b, 28, 263); put(b, 32, 48); put(b, 36, 64);
    for (std::size_t i = 0; i < cells.size(); ++i)
        for (unsigned k = 0; k < 12; ++k) put(b, 128 + 48 * i + 4 * k, cells[i].words[k]);
    return b;
}
U32 random_word(U32& state) {
    state ^= state << 13; state ^= state >> 17; state ^= state << 5; return state;
}
vm::Cell48 cell(U32 key, U32 op, U32 next = 0) {
    vm::Cell48 c{};
    c.words[1] = key; c.words[2] = op; c.words[8] = c.words[9] = next;
    c.words[10] = 0x80000001u ^ (key * 0x10203041u);
    c.words[11] = 0xfedcba98u ^ (key * 0x01010101u);
    return c;
}
std::vector<vm::Cell48> mixed_program() {
    std::vector<vm::Cell48> cells;
    for (U32 i = 0; i < 21; ++i) {
        auto c = cell(i, i < 16 ? i : 0, (i + 1) % 15);
        c.words[9] = (i + 5) % 15;
        c.words[4] = 0x80000001u + i; c.words[5] = 0x7fffffffu - i;
        c.words[6] = 0xfffff000u + i; c.words[7] = i * 20003u;
        cells.push_back(c);
    }
    cells[1].words[3] = 0; // SET rho.
    cells[2].words[3] = 4; // JIT1 vrho, full signed argument.
    cells[4].words[3] = TOMAGI_FLAG_PHI_FLIP_ORIENTATION | TOMAGI_FLAG_PHI_BRANCH_HALF;
    cells[9].words[3] = TOMAGI_FLAG_KLEIN_SOURCE_HALF_TURN | TOMAGI_FLAG_KLEIN_FLIP_SHEET;
    cells[10].words[4] = 63;
    cells[11].words[3] = TOMAGI_FLAG_HINGE_FLIP_ORIENTATION | TOMAGI_FLAG_HINGE_FLIP_SHEET;
    cells[12].words[5] = 31; // Canonical clamping to 30.
    cells[14].words[3] = 0x00000c00u; // Non-HALT literal emit metadata.
    cells[16].words[2] = cells[17].words[2] = TOMAGI_OP_RADIX;
    cells[16].words[4] = 64; cells[17].words[4] = 0xffffffffu;
    cells[18].words[2] = TOMAGI_OP_EMIT; cells[18].words[3] = TOMAGI_FLAG_EMIT_HALT;
    cells[19].words[2] = TOMAGI_OP_SET; cells[19].words[3] = TOMAGI_FLAG_REKEY | 3;
    cells[19].words[4] = 20;
    cells[20].words[3] = TOMAGI_FLAG_REKEY;
    return cells;
}
std::vector<vm::State64> varied_states(U32 count, U32 cells) {
    std::vector<vm::State64> result(count);
    U32 seed = 0x19900710u;
    for (U32 i = 0; i < count; ++i) {
        for (auto& word : result[i].words) word = random_word(seed);
        result[i].words[10] = i % 4; // Includes raw 2/3, not pre-normalized Booleans.
        result[i].words[11] = i % cells;
        result[i].words[15] &= ~U32(TOMAGI_STATUS_HALT);
    }
    if (count > cells + 2) {
        result[count - 1].words[11] = cells + 41; // Bad active PC.
        result[count - 2].words[11] = cells + 41;
        result[count - 2].words[15] |= TOMAGI_STATUS_HALT; // HALT takes precedence.
    }
    return result;
}

// This reference intentionally evaluates each bit's Boolean truth table and
// JK transition independently. Whole-word absorption is applied between them.
U64 scalar_table(U32 lut, U64 q, U64 argument, U64 mask) {
    U64 result = 0;
    for (unsigned bit = 0; bit < 64; ++bit) {
        const unsigned index = unsigned((q >> bit) & 1) + 2 * unsigned((argument >> bit) & 1);
        if ((lut >> index) & 1) result |= U64(1) << bit;
    }
    return result & mask;
}
U64 scalar_jk(U64 q, U64 drive, const atomos::WordProfile& p) {
    U64 y = scalar_table(p.x_lut, q, drive, p.valid_mask) & p.a0 & p.n0;
    if (y & p.b0) y = 0;
    y &= p.a1 & p.n1;
    if (y & p.b1) y = 0;
    const U64 j = scalar_table(p.j_lut, q, y, p.valid_mask);
    const U64 k = scalar_table(p.k_lut, q, y, p.valid_mask);
    U64 result = 0;
    for (unsigned bit = 0; bit < 64; ++bit) {
        const bool old = ((q >> bit) & 1) != 0;
        const bool next = ((((j >> bit) & 1) != 0) && !old) || ((((k >> bit) & 1) == 0) && old);
        if (next) result |= U64(1) << bit;
    }
    return result & p.valid_mask;
}

struct Oracle {
    std::vector<TomagiCell> cells;
    std::vector<vm::State64> state;
    std::vector<U32> errors;
    std::vector<vm::Receipt> receipts;
    std::vector<vm::WordState> words;
    U64 epoch = 0, rekey_hits = 0, rekey_misses = 0, cross_bank_rekeys = 0;
    U32 executed_opcodes = 0;

    Oracle(const std::vector<vm::Cell48>& source, const std::vector<vm::State64>& initial,
           const std::vector<U64>& q = {}) : state(initial), errors(initial.size()),
           receipts(initial.size()), words(initial.size()) {
        for (auto c : source) cells.push_back(to_c(c));
        for (std::size_t i = 0; i < q.size(); ++i) words.at(i).q = q[i];
    }
    void advance(U32 count, const atomos::WordProfile* profile = nullptr,
                 vm::WordBinding binding = vm::WordBinding::None) {
        TomagiProgram program{};
        program.cells = cells.data(); program.cell_count = U32(cells.size()); program.seed = Seed;
        for (U32 tick = 0; tick < count; ++tick, ++epoch) {
            for (std::size_t lane = 0; lane < state.size(); ++lane) {
                auto& raw = state[lane]; auto& word = words[lane];
                if (profile && binding == vm::WordBinding::RhoAndVrho && !errors[lane]
                    && !(raw.words[15] & TOMAGI_STATUS_HALT) && !word.status) {
                    raw.words[0] = U32(word.q); raw.words[4] = U32(word.q >> 32);
                }
                vm::Receipt receipt{};
                receipt.epoch = epoch; receipt.cell_before = raw.words[11]; receipt.branch_after = raw.words[10];
                if (errors[lane]) receipt.error = errors[lane];
                else if (!(raw.words[15] & TOMAGI_STATUS_HALT)) {
                    if (raw.words[11] >= cells.size()) receipt.error = errors[lane] = U32(vm::Error::BadCell);
                    else {
                        const auto& c = cells[raw.words[11]];
                        receipt.opcode = c.opcode; receipt.flags = c.flags; receipt.payload = c.payload;
                        auto next = to_c(raw);
                        if (!tomagi_step(&program, &next)) {
                            receipt.error = errors[lane] = c.opcode > TOMAGI_OP_HALT
                                ? U32(vm::Error::BadOpcode) : U32(vm::Error::BadRadix);
                        } else {
                            raw = from_c(next); receipt.executed = 1;
                            receipt.emitted = c.opcode == TOMAGI_OP_EMIT;
                            receipt.branch_after = next.branch;
                            executed_opcodes |= U32(1) << c.opcode;
                            if ((c.flags & TOMAGI_FLAG_REKEY) && !(next.status & TOMAGI_STATUS_HALT)) {
                                if (next.status & TOMAGI_STATUS_REKEY_MISS) ++rekey_misses;
                                else { ++rekey_hits; if (receipt.cell_before / 2 != next.cell / 2) ++cross_bank_rekeys; }
                            }
                        }
                    }
                }
                receipts[lane] = receipt;
                if (!profile) continue;
                if (errors[lane] || receipt.error) { word.status = 1; continue; }
                if (!receipt.executed || !receipt.emitted) continue;
                if (word.initialized && receipt.epoch <= word.last_epoch) {
                    if (receipt.epoch < word.last_epoch) word.status = 2;
                    continue;
                }
                if (word.status) continue;
                if (word.hinges == ~U64(0)) { word.status = 3; continue; }
                word.q = scalar_jk(word.q, receipt.payload, *profile);
                word.parity ^= 1; ++word.hinges; word.initialized = 1;
                word.last_epoch = receipt.epoch; word.last_drive = receipt.payload;
            }
        }
    }
};

template<class T, class Word, std::size_t N> std::array<Word, N> raw_words(const T& value) {
    static_assert(sizeof(T) == sizeof(Word) * N, "complete object representation required");
    std::array<Word, N> out{}; std::memcpy(out.data(), &value, sizeof(value)); return out;
}
void same_vm(vm::VM& actual, const Oracle& expected, const std::string& label) {
    const auto states = actual.read_states(); const auto errors = actual.read_errors(); const auto receipts = actual.read_receipts();
    require(states.size() == expected.state.size() && errors.size() == states.size() && receipts.size() == states.size(), label + " lane counts");
    require(actual.epoch() == expected.epoch, label + " managed epoch");
    for (std::size_t lane = 0; lane < states.size(); ++lane) {
        for (unsigned k = 0; k < 16; ++k) {
            ++compared_state_words;
            require(states[lane].words[k] == expected.state[lane].words[k], label + " State64 lane " + std::to_string(lane) + " word " + std::to_string(k));
        }
        require(errors[lane] == expected.errors[lane], label + " exact error sidecar lane " + std::to_string(lane));
        const auto a = raw_words<vm::Receipt, U32, 10>(receipts[lane]);
        const auto e = raw_words<vm::Receipt, U32, 10>(expected.receipts[lane]);
        for (unsigned k = 0; k < 10; ++k) {
            ++compared_receipt_words;
            require(a[k] == e[k], label + " Receipt40 lane " + std::to_string(lane) + " word " + std::to_string(k));
        }
    }
}
void same_word(vm::WordFeedback& actual, const Oracle& expected, const std::string& label) {
    const auto words = actual.readback(); require(words.size() == expected.words.size(), label + " word lane count");
    for (std::size_t lane = 0; lane < words.size(); ++lane) {
        const auto a = raw_words<vm::WordState, U64, 8>(words[lane]);
        const auto e = raw_words<vm::WordState, U64, 8>(expected.words[lane]);
        for (unsigned k = 0; k < 8; ++k) {
            ++compared_feedback_words;
            require(a[k] == e[k], label + " WordState64 lane " + std::to_string(lane) + " word " + std::to_string(k));
        }
    }
}
void enqueue_chunks(vm::VM& machine, U32 count, U32 chunk, bool texture, void* stream = nullptr) {
    for (U32 done = 0; done < count;) {
        const U32 next = std::min(chunk, count - done);
        machine.enqueue_batch(next, texture, stream); done += next;
    }
}

void pure_case(const std::string& name, const std::vector<vm::Cell48>& cells,
               const std::vector<vm::State64>& initial, bool check_coverage = false, bool check_rekey = false) {
    const auto binary = encode(cells);
    Oracle expected(cells, initial); expected.advance(263);
    if (check_coverage) require(expected.executed_opcodes == 0xffffu, "all 16 canonical opcodes actually executed");
    if (check_rekey) require(expected.rekey_hits && expected.rekey_misses && expected.cross_bank_rekeys, "actual REKEY hit/miss and cross-bank coverage");
    for (bool texture : {false, true}) {
        vm::VM reference(binary, 2); reference.set_states(initial); reference.run_steps(263, texture);
        same_vm(reference, expected, name + " retained reference");
        for (U32 chunk : {1u, 7u, 32u, 256u}) {
            vm::VM machine(binary, 2); machine.set_states(initial);
            require(machine.device_view().bank_shift == 1, name + " forced bank cap");
            enqueue_chunks(machine, 263, chunk, texture); same_vm(machine, expected, name + " chunk " + std::to_string(chunk));
            machine.enqueue_batch(0, !texture); same_vm(machine, expected, name + " zero count after live work");
        }
    }
}

void pure_and_rekey() {
    const auto cells = mixed_program();
    pure_case("mixed all-opcode lanes", cells, varied_states(257, U32(cells.size())), true);
    std::vector<vm::Cell48> keyed;
    for (U32 i = 0; i < 9; ++i) {
        auto c = cell(i, 0, (i + 1) % 9); c.words[9] = (i + 2) % 9;
        c.words[3] = i & 1 ? TOMAGI_FLAG_REKEY : 0; keyed.push_back(c);
    }
    keyed[0].words[2] = TOMAGI_OP_SET; keyed[0].words[3] = TOMAGI_FLAG_REKEY | 3; keyed[0].words[4] = 4;
    std::vector<vm::State64> initial(33);
    for (U32 i = 0; i < initial.size(); ++i) {
        initial[i].words[3] = i % 11; initial[i].words[10] = i % 4; initial[i].words[11] = i % 9;
    }
    pure_case("REKEY split banks", keyed, initial, false, true);
}

void lsys_signed_shift_cases() {
    std::vector<U32> shifts;
    for (U32 shift = 0; shift <= 30; ++shift) shifts.push_back(shift);
    for (U32 raw : {0xffffffffu, 0x80000000u, 31u, 0x7fffffffu, 0xfffffffdu}) shifts.push_back(raw);
    std::vector<U32> rates{0u, 1u, 0xffffffffu, 0x80000000u, 0x7fffffffu,
                           0xfffffffdu, 0xfffffff9u, 17u};
    U32 random = 0x51f70dd5u;
    for (unsigned i = 0; i < 8; ++i) rates.push_back(random_word(random));
    std::vector<vm::Cell48> cells;
    std::vector<vm::State64> initial;
    for (U32 index = 0; index < shifts.size(); ++index) {
        auto c = cell(index, TOMAGI_OP_LSYS, index);
        c.words[4] = 0x80000000u + index; c.words[5] = shifts[index];
        cells.push_back(c);
        for (U32 rate = 0; rate < rates.size(); ++rate) {
            vm::State64 state{};
            state.words[0] = 0xfedcba98u ^ rate;
            state.words[1] = 0x80000000u + index;
            state.words[2] = 0x7fffffffu - rate;
            state.words[3] = 0xffffffffu - index;
            // Rotate the corpus so every rate field receives every edge/random
            // value at every shift. Raw coordinate and branch aliases remain.
            for (U32 k = 0; k < 4; ++k) state.words[4 + k] = rates[(rate + k) % rates.size()];
            state.words[8] = rate & 1; state.words[9] = 0x80000000u | index;
            state.words[10] = rate % 4; state.words[11] = index;
            state.words[12] = random_word(random); state.words[13] = 0x98765432u;
            state.words[14] = 0x80000000u; state.words[15] = TOMAGI_STATUS_EMIT;
            initial.push_back(state);
        }
    }
    require(initial.size() == 576, "LSYS corpus has 36 shift encodings times 16 rate tuples");
    Oracle first(cells, initial); first.advance(1);
    // Hand-derived edge anchors additionally check the C oracle fixture itself.
    const auto first_rate = [&](U32 shift_index, U32 rate_index) {
        return first.state.at(std::size_t(shift_index) * rates.size() + rate_index).words[4];
    };
    require(first_rate(0, 3) == 0x80000000u, "LSYS shift0 preserves INT_MIN");
    require(first_rate(1, 3) == 0xc0000000u, "LSYS INT_MIN/2 is -1073741824");
    require(first_rate(1, 5) == 0xffffffffu, "LSYS -3/2 truncates toward zero");
    require(first_rate(30, 3) == 0xfffffffeu && first_rate(30, 4) == 1u,
            "LSYS shift30 handles signed extremes");
    require(first_rate(31, 3) == 0x80000000u && first_rate(32, 5) == 0xfffffffdu,
            "LSYS negative shift encodings clamp to zero");
    require(first_rate(33, 3) == 0xfffffffeu && first_rate(34, 4) == 1u,
            "LSYS oversized shift encodings clamp to thirty");
    Oracle final(cells, initial); final.advance(264);
    const auto binary = encode(cells);
    atomos::WordProfile profile;
    for (bool texture : {false, true}) {
        vm::VM retained(binary, 2); retained.set_states(initial); retained.run_steps(1, texture);
        same_vm(retained, first, "LSYS retained single tick/C");
        retained.run_steps(263, texture); same_vm(retained, final, "LSYS retained full continuation/C");
        for (U32 chunk : {1u, 7u, 32u, 256u}) {
            const auto label = "LSYS signed shift chunk " + std::to_string(chunk);
            vm::VM pure(binary, 2); pure.set_states(initial); pure.enqueue_batch(1, texture);
            same_vm(pure, first, label + " first pure fused tick/C");
            enqueue_chunks(pure, 263, chunk, texture); same_vm(pure, final, label + " pure continuation/C");
            vm::VM coupled(binary, 2); coupled.set_states(initial);
            vm::WordFeedback feedback(coupled, profile, vm::WordBinding::None);
            feedback.run_steps_fused(1, texture, chunk);
            same_vm(coupled, first, label + " first coupled fused tick/C");
            same_word(feedback, first, label + " sticky initial EMIT is not an event");
            feedback.run_steps_fused(263, texture, chunk);
            same_vm(coupled, final, label + " coupled continuation/C");
            same_word(feedback, final, label + " LSYS emits no fresh feedback event");
        }
    }
}

void coupled_cases() {
    const auto cells = mixed_program(); const auto binary = encode(cells);
    const auto initial = varied_states(129, U32(cells.size()));
    for (U32 variant = 0; variant < 4; ++variant) {
        atomos::WordProfile p;
        p.x_lut = 6; p.j_lut = variant == 3 ? 9 : 12; p.k_lut = variant == 3 ? 5 : 3;
        if (variant == 1) { p.valid_mask = 0xfedcba987654321fULL; p.a0 = 0xf0f0fffff00fffffULL; p.n1 = 0x8fffffffffffffffULL; }
        if (variant == 2) p.b0 = 1;
        if (variant == 3) p.b1 = 0x80000000u;
        U32 random = 0x10203040u + variant;
        std::vector<U64> q(initial.size());
        for (auto& word : q) { const U64 hi = random_word(random); word = ((hi << 32) | random_word(random)) & p.valid_mask; }
        for (auto binding : {vm::WordBinding::None, vm::WordBinding::RhoAndVrho}) {
            Oracle expected(cells, initial, q); expected.advance(263, &p, binding);
            for (bool texture : {false, true}) {
                const auto label = "coupled profile " + std::to_string(variant) + " binding " + std::to_string(U32(binding));
                vm::VM reference(binary, 2); reference.set_states(initial);
                vm::WordFeedback retained(reference, p, binding, q); retained.run_steps(263, texture);
                same_vm(reference, expected, label + " reference/C"); same_word(retained, expected, label + " reference/scalar");
                for (U32 chunk : {1u, 7u, 32u, 256u}) {
                    vm::VM machine(binary, 2); machine.set_states(initial);
                    vm::WordFeedback fused(machine, p, binding, q);
                    fused.run_steps_fused(263, texture, chunk);
                    same_vm(machine, expected, label + " fused/C"); same_word(fused, expected, label + " fused/scalar");
                    require(fused.stats().steps == 263 && fused.stats().lanes == initial.size(), label + " fused stats scope");
                    fused.recommit_last(); same_word(fused, expected, label + " repeated receipt hold");
                    fused.run_steps_fused(0, !texture, chunk);
                    same_vm(machine, expected, label + " zero VM hold"); same_word(fused, expected, label + " zero word hold");
                    require(fused.stats().steps == 0 && fused.stats().device_ms == 0 && fused.stats().wall_ms == 0, label + " zero timing");
                }
            }
        }
    }
}

void terminal_and_sticky() {
    auto emit = cell(0, TOMAGI_OP_EMIT, 1); emit.words[10] = 0x80000001u;
    auto nop = cell(1, TOMAGI_OP_NOP, 1);
    auto final_emit = cell(2, TOMAGI_OP_EMIT, 2); final_emit.words[3] = TOMAGI_FLAG_EMIT_HALT; final_emit.words[10] = 7;
    auto fault = cell(3, TOMAGI_OP_RADIX, 3); fault.words[4] = 64;
    const std::vector<vm::Cell48> cells{emit, nop, final_emit, fault};
    std::vector<vm::State64> initial(5);
    initial[1].words[11] = 2; initial[2].words[11] = 3;
    initial[3].words[11] = 99; initial[4].words[11] = 99; initial[4].words[15] = TOMAGI_STATUS_HALT;
    atomos::WordProfile p; p.x_lut = 12;
    for (bool texture : {false, true}) {
        vm::VM machine(encode(cells), 1); machine.set_states(initial);
        vm::WordFeedback feedback(machine, p, vm::WordBinding::None);
        Oracle expected(cells, initial);
        feedback.run_steps_fused(1, texture, 1); expected.advance(1, &p);
        same_vm(machine, expected, "first emit/halt/fault receipts"); same_word(feedback, expected, "first word commit");
        feedback.run_steps_fused(262, texture, 256); expected.advance(262, &p);
        same_vm(machine, expected, "final halted/faulted receipt slots"); same_word(feedback, expected, "sticky emit hold");
        const auto words = feedback.readback(); const auto receipts = machine.read_receipts();
        require(words[0].hinges == 1 && words[0].q == 0x80000001u, "NOP after EMIT does not repeat pulse");
        require(words[1].hinges == 1 && words[1].q == 7, "final EMIT-and-HALT commits once");
        require(words[2].status == 1 && words[3].status == 1 && words[4].status == 0, "faulted versus already-halted invalid PCs");
        for (const auto& receipt : receipts) require(receipt.epoch == 262 && !receipt.emitted, "final requested epoch has no duplicate emits");
        feedback.recommit_last(); same_word(feedback, expected, "terminal recommit holds");
    }
    // Fresh repeated emissions must not be deduplicated merely by equal payload.
    auto repeated = cell(0, TOMAGI_OP_EMIT); repeated.words[10] = 0x12345678u;
    vm::VM machine(encode({repeated})); vm::WordFeedback words(machine, p, vm::WordBinding::None);
    words.run_steps_fused(263, true, 7);
    require(words.readback()[0].hinges == 263 && words.readback()[0].last_epoch == 262,
            "263 identical payloads with distinct epochs are 263 fresh events");
}

void ownership_and_composition() {
    const auto cells = mixed_program(); const auto binary = encode(cells);
    const auto initial = varied_states(35, U32(cells.size()));
    vm::VM pure(binary, 2); pure.set_states(initial); Oracle expected(cells, initial);
    pure.enqueue_batch(0); same_vm(pure, expected, "initial pure zero identity");
    rejects([&] { pure.enqueue_batch(257); }, "pure chunk 257 rejected");
    same_vm(pure, expected, "oversized pure request has no mutation");
    cudaStream_t stream = nullptr; cuda_check(cudaStreamCreateWithFlags(&stream, cudaStreamNonBlocking));
    try {
        pure.enqueue_batch(7, true, stream); pure.enqueue_batch(32, false, stream);
        cuda_check(cudaStreamSynchronize(stream)); expected.advance(39);
        same_vm(pure, expected, "ordered nondefault stream and mixed fetch batches");
    } catch (...) { cudaStreamDestroy(stream); throw; }
    cuda_check(cudaStreamDestroy(stream));
    pure.run_steps(1, false); expected.advance(1);
    pure.enqueue_batch(256, true); expected.advance(256);
    same_vm(pure, expected, "reference/pure batch composition");
    const U64 generation = pure.state_generation(); pure.set_states(initial);
    require(pure.epoch() == 0 && pure.state_generation() == generation + 1, "reset establishes new epoch generation");
    Oracle reset_expected(cells, initial); same_vm(pure, reset_expected, "reset clears every error and receipt word");
    pure.set_states({}); pure.enqueue_batch(0); require(pure.epoch() == 0, "empty zero epoch hold");
    pure.enqueue_batch(7); require(pure.epoch() == 7 && pure.read_states().empty() && pure.read_receipts().empty(), "empty lanes retain logical epoch progression");

    atomos::WordProfile profile; profile.x_lut = 6;
    vm::VM machine(binary, 2); machine.set_states(initial);
    vm::WordFeedback feedback(machine, profile); Oracle coupled(cells, initial);
    for (U32 count : {0u, 1u, 7u, 32u, 256u, 3u}) {
        if (count == 1 || count == 32) feedback.run_steps(count, false);
        else feedback.run_steps_fused(count, true, 7);
        coupled.advance(count, &profile, vm::WordBinding::RhoAndVrho);
        same_vm(machine, coupled, "reference/fused sequential composition");
        same_word(feedback, coupled, "reference/fused scalar composition");
    }
    for (U32 bad : {0u, 257u}) for (U32 count : {0u, 1u}) {
        rejects([&] { feedback.run_steps_fused(count, true, bad); }, "invalid fused chunk rejected even for zero count");
        same_vm(machine, coupled, "invalid fused chunk leaves VM unchanged");
        same_word(feedback, coupled, "invalid fused chunk leaves words unchanged");
    }
    machine.set_states(initial);
    rejects([&] { feedback.run_steps_fused(0); }, "reset invalidates borrower even for zero work");
    vm::WordFeedback fresh(machine, profile); Oracle fresh_expected(cells, initial);
    fresh.run_steps_fused(7); fresh_expected.advance(7, &profile, vm::WordBinding::RhoAndVrho);
    same_vm(machine, fresh_expected, "new borrower after reset"); same_word(fresh, fresh_expected, "new borrower exact words");
    machine.enqueue_batch(1);
    rejects([&] { fresh.run_steps_fused(1); }, "external advance invalidates fused owner");
    rejects([&] { fresh.recommit_last(); }, "external advance invalidates recommit");

    // A newly attached borrower starts at the owner's current epoch, not zero.
    vm::VM continued(binary, 2); continued.set_states(initial);
    Oracle continued_expected(cells, initial);
    continued.enqueue_batch(13, false); continued_expected.advance(13);
    std::vector<U64> resumed_q(initial.size());
    for (std::size_t i = 0; i < resumed_q.size(); ++i) {
        resumed_q[i] = 0x1234567800000000ULL + U64(i);
        continued_expected.words[i].q = resumed_q[i];
    }
    vm::WordFeedback attached(continued, profile, vm::WordBinding::RhoAndVrho, resumed_q);
    attached.run_steps_fused(17, true, 7);
    continued_expected.advance(17, &profile, vm::WordBinding::RhoAndVrho);
    same_vm(continued, continued_expected, "borrower attached at nonzero source epoch");
    same_word(attached, continued_expected, "nonzero-epoch initial word binding");
    attached.run_steps(5, false);
    continued_expected.advance(5, &profile, vm::WordBinding::RhoAndVrho);
    same_vm(continued, continued_expected, "nonzero source epoch reference continuation");
    same_word(attached, continued_expected, "nonzero source epoch exact word continuation");
}
} // namespace

int main() {
    try {
        pure_and_rekey(); lsys_signed_shift_cases(); coupled_cases(); terminal_and_sticky(); ownership_and_composition();
        std::cout << "tomagi_fused_tests: " << checks << " checks passed; State64 words " << compared_state_words
                  << ", Receipt40 words " << compared_receipt_words << ", WordState64 words " << compared_feedback_words
                  << "; canonical C plus independent scalar per-bit ASA/NA/JK; both fetch paths; chunks 1/7/32/256; all LSYS shifts and signed extremes\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "tomagi_fused_tests: " << error.what() << '\n'; return 1;
    }
}
