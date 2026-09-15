#pragma once
#include <cstddef>
#include <cstdint>

// Independent POD API: no CUDA, S2 or C++ container headers are required.
namespace atomos { namespace exact {

constexpr std::int32_t coefficient_limit = (std::int32_t(1) << 30) - 1;
constexpr std::uint32_t max_nodes = 128;
constexpr std::uint32_t max_inputs = 128;
constexpr std::size_t header_words = 8;
constexpr std::size_t node_words = 16;
constexpr std::uint32_t magic0 = 0x31475041u; // little-endian bytes APG1
constexpr std::uint32_t magic1 = 0x31494850u; // little-endian bytes PHI1
constexpr std::uint32_t unit_scalar = 0;
constexpr std::uint32_t unit_length = 1;
// Seven signed 4-bit SI exponents (L,M,T,I,temperature,amount,intensity),
// low nibble first. Upper nibble is reserved and must be zero.

struct Coeff { std::int32_t a, b; }; // a+b*phi, integer coefficients only
enum class Op : std::uint32_t {
    Literal = 0, Input = 1, Add = 2, Subtract = 3, Multiply = 4,
    PhiMultiply = 5, PlaneGuard = 6
};
struct Node {
    Op op;
    std::uint32_t args[7]; // PlaneGuard: px,py,pz,nx,ny,nz,offset
    Coeff literal;
    std::uint32_t input_slot;
    std::uint32_t units;
};
enum class Status : std::uint32_t {
    Value = 0, Boundary = 1, Unresolved = 2, Invalid = 3
};
struct Result {
    Status status;
    std::int32_t sign; // -1,0,+1; meaningful only for Value/Boundary
    Coeff value;
    std::uint32_t failed_node; // UINT32_MAX on success
    std::uint32_t accept_hinge; // nonzero guard eligibility, NOT an accepted event
};
struct Program; // opaque persistent VRAM seed and integer texture

constexpr std::size_t seed_word_count(std::uint32_t count) {
    return header_words + node_words * count;
}

// All functions return false and fill an optional error buffer on failure.
// The emitted word schema is ATOMOS-EXACT-GPU-ZPHI31-R1, not XOPSEED1 or AHNGBPL1.
bool encode_seed(const Node* nodes, std::uint32_t count, std::uint32_t inputs,
                 std::uint32_t root, std::uint64_t frame_identity,
                 std::uint32_t* words, std::size_t capacity,
                 char* error = nullptr, std::size_t error_capacity = 0);
bool create_program(const std::uint32_t* words, std::size_t count, Program** output,
                    char* error = nullptr, std::size_t error_capacity = 0);
void destroy_program(Program* program);
bool evaluate(Program* program, const Coeff* samples, std::size_t sample_count,
              Result* results, char* error = nullptr, std::size_t error_capacity = 0);
// Samples are row-major [sample_count][declared input count]. Zero-input programs
// may pass nullptr. This function synchronizes before returning host results.
bool read_seed_words(Program* program, std::uint32_t* words, std::size_t capacity,
                     char* error = nullptr, std::size_t error_capacity = 0);
bool device_available();

}} // namespace atomos::exact
