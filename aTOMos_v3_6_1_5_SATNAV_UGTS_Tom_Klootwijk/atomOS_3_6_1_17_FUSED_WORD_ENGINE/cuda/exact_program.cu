#include "atomos/exact_program.hpp"
#include <cuda_runtime.h>
#include <algorithm>
#include <cstdio>
#include <limits>
#include <new>
#include <vector>

namespace atomos { namespace exact {
struct Program {
    std::uint32_t* words = nullptr;
    std::uint32_t* packed_words = nullptr;
    std::size_t count = 0;
    std::uint32_t nodes = 0, inputs = 0, root = 0;
    cudaTextureObject_t texture = 0;
    cudaTextureObject_t packed_texture = 0;
};
namespace {
void message(char* dst, std::size_t size, const char* value) {
    if (dst && size) std::snprintf(dst, size, "%s", value);
}
bool cuda_ok(cudaError_t code, char* error, std::size_t size) {
    if (code == cudaSuccess) return true;
    message(error, size, cudaGetErrorString(code));
    return false;
}
__host__ __device__ std::int32_t signed_word(std::uint32_t word) {
    return word <= 0x7fffffffu ? static_cast<std::int32_t>(word)
                             : -1 - static_cast<std::int32_t>(~word);
}
int exponent(std::uint32_t units, int index) {
    const int nibble = (units >> (4 * index)) & 15;
    return nibble < 8 ? nibble : nibble - 16;
}
bool product_units(std::uint32_t a, std::uint32_t b, std::uint32_t* result) {
    *result = 0;
    for (int i = 0; i < 7; ++i) {
        const int value = exponent(a, i) + exponent(b, i);
        if (value < -8 || value > 7) return false;
        *result |= static_cast<std::uint32_t>(value & 15) << (4 * i);
    }
    return true;
}
int arity(Op op) {
    switch (op) {
    case Op::Literal: case Op::Input: return 0;
    case Op::Add: case Op::Subtract: case Op::Multiply: return 2;
    case Op::PhiMultiply: return 1;
    case Op::PlaneGuard: return 7;
    default: return -1;
    }
}
bool validate(const std::uint32_t* w, std::size_t count, char* error, std::size_t size) {
    auto reject = [&](const char* why) { message(error, size, why); return false; };
    if (!w || count < header_words || w[0] != magic0 || w[1] != magic1 || w[2] != 1)
        return reject("wrong/truncated exact GPU seed profile");
    if (!w[3] || w[3] > max_nodes || w[4] > max_inputs || w[5] >= w[3]
        || count != seed_word_count(w[3])) return reject("invalid exact program size/root");
    std::uint32_t slot_units[max_inputs]{};
    bool slot_seen[max_inputs]{};
    for (std::uint32_t i = 0; i < w[3]; ++i) {
        const auto* n = w + header_words + i * node_words;
        const Op op = static_cast<Op>(n[0]);
        const int argc = arity(op);
        if (argc < 0 || n[4] >> 28 || n[5] || n[13] || n[14] || n[15])
            return reject("unknown opcode/units/reserved words");
        if (op != Op::Input && n[1]) return reject("noncanonical unused input slot");
        if (op != Op::Literal && (n[2] || n[3])) return reject("noncanonical unused literal");
        for (int j = 0; j < 7; ++j) {
            if ((j < argc && n[6+j] >= i) || (j >= argc && n[6+j]))
                return reject("forward/cyclic or noncanonical operand reference");
        }
        auto units = [&](int operand) { return w[header_words + n[6+operand] * node_words + 4]; };
        if (op == Op::Input) {
            if (n[1] >= w[4]) return reject("input index outside declaration");
            if (slot_seen[n[1]] && slot_units[n[1]] != n[4]) return reject("one sample slot has inconsistent units");
            slot_seen[n[1]] = true;
            slot_units[n[1]] = n[4];
        } else if (op == Op::Add || op == Op::Subtract) {
            if (units(0) != units(1) || n[4] != units(0)) return reject("add/sub unit mismatch");
        } else if (op == Op::Multiply) {
            std::uint32_t result;
            if (!product_units(units(0), units(1), &result) || result != n[4]) return reject("multiply unit mismatch");
        } else if (op == Op::PhiMultiply) {
            if (n[4] != units(0)) return reject("phi multiply must preserve units");
        } else if (op == Op::PlaneGuard) {
            if (n[4] != unit_length) return reject("plane guard result must have length units");
            for (int j = 0; j < 3; ++j)
                if (units(j) != unit_length || units(j+3) != unit_scalar)
                    return reject("plane coordinate/normal unit mismatch");
            if (units(6) != unit_length) return reject("plane offset unit mismatch");
        }
    }
    return true;
}

__device__ bool bounded(Coeff x) {
    return x.a >= -coefficient_limit && x.a <= coefficient_limit
        && x.b >= -coefficient_limit && x.b <= coefficient_limit;
}
__device__ bool coefficient_result(long long a, long long b, Coeff* result) {
    if (a < -coefficient_limit || a > coefficient_limit || b < -coefficient_limit || b > coefficient_limit)
        return false;
    *result = {static_cast<std::int32_t>(a), static_cast<std::int32_t>(b)};
    return true;
}
__device__ bool add(Coeff x, Coeff y, Coeff* result) {
    return coefficient_result(static_cast<long long>(x.a) + y.a, static_cast<long long>(x.b) + y.b, result);
}
__device__ bool subtract(Coeff x, Coeff y, Coeff* result) {
    return coefficient_result(static_cast<long long>(x.a) - y.a, static_cast<long long>(x.b) - y.b, result);
}
__device__ bool multiply(Coeff x, Coeff y, Coeff* result) {
    // Every operand is bounded by B=2^30-1. At most 3 B^2 are summed;
    // this is strictly below INT64_MAX. Only the checked result is retained.
    const long long a = static_cast<long long>(x.a)*y.a + static_cast<long long>(x.b)*y.b;
    const long long b = static_cast<long long>(x.a)*y.b + static_cast<long long>(x.b)*y.a
                      + static_cast<long long>(x.b)*y.b;
    return coefficient_result(a, b, result);
}
__device__ int exact_sign(Coeff x) {
    const long long A = 2LL*x.a + x.b, B = x.b;
    const int sa = (A > 0) - (A < 0), sb = (B > 0) - (B < 0);
    if (!sb) return sa;
    if (!sa || sa == sb) return sb;
    const unsigned long long aa = static_cast<unsigned long long>(A < 0 ? -A : A);
    const unsigned long long bb = static_cast<unsigned long long>(B < 0 ? -B : B);
    // |A| <= 3(2^30-1): A^2 may exceed INT64_MAX but fits UINT64_MAX.
    const unsigned long long left = aa*aa, right = 5ULL*bb*bb;
    return left > right ? sa : left < right ? sb : 0;
}
__device__ std::uint32_t fetch(cudaTextureObject_t texture, std::uint32_t index) {
    return tex1Dfetch<unsigned int>(texture, static_cast<int>(index));
}
__global__ void run(cudaTextureObject_t texture, const Coeff* inputs, std::uint32_t input_count,
                    std::uint32_t nodes, std::uint32_t root, std::size_t count, Result* output) {
    const std::size_t sample = static_cast<std::size_t>(blockIdx.x)*blockDim.x + threadIdx.x;
    if (sample >= count) return;
    Coeff values[max_nodes];
    // Evaluate the root's dependency closure in increasing source order. Other
    // nodes remain losslessly present in the uploaded program, but cannot make
    // an unrelated root unresolved merely because they are outside the domain.
    bool required[max_nodes]{};
    required[root] = true;
    for (int i = static_cast<int>(nodes)-1; i >= 0; --i) {
        if (!required[i]) continue;
        const auto base = static_cast<std::uint32_t>(header_words) + i*static_cast<std::uint32_t>(node_words);
        const Op op = static_cast<Op>(fetch(texture, base));
        const int argc = op == Op::PlaneGuard ? 7 : op == Op::PhiMultiply ? 1
            : op == Op::Add || op == Op::Subtract || op == Op::Multiply ? 2 : 0;
        for (int j = 0; j < argc; ++j) required[fetch(texture, base+6+j)] = true;
    }
    Result result{Status::Unresolved, 0, {0,0}, 0xffffffffu, 0};
    for (std::uint32_t i = 0; i < nodes; ++i) {
        if (!required[i]) continue;
        const std::uint32_t base = static_cast<std::uint32_t>(header_words) + i*static_cast<std::uint32_t>(node_words);
        const Op op = static_cast<Op>(fetch(texture, base));
        std::uint32_t args[7];
        for (int j = 0; j < 7; ++j) args[j] = fetch(texture, base+6+j);
        Coeff value{0,0};
        bool ok = true;
        switch (op) {
        case Op::Literal:
            value = {signed_word(fetch(texture, base+2)), signed_word(fetch(texture, base+3))};
            ok = bounded(value); break;
        case Op::Input:
            value = inputs[sample*input_count + fetch(texture, base+1)];
            ok = bounded(value); break;
        case Op::Add: ok = add(values[args[0]], values[args[1]], &value); break;
        case Op::Subtract: ok = subtract(values[args[0]], values[args[1]], &value); break;
        case Op::Multiply: ok = multiply(values[args[0]], values[args[1]], &value); break;
        case Op::PhiMultiply:
            ok = coefficient_result(values[args[0]].b,
                static_cast<long long>(values[args[0]].a)+values[args[0]].b, &value); break;
        case Op::PlaneGuard: {
            bool normal_nonzero = false;
            for (int j = 0; j < 3; ++j) {
                const Coeff normal = values[args[j+3]];
                normal_nonzero |= normal.a != 0 || normal.b != 0;
                Coeff product, next;
                if (!multiply(values[args[j]], normal, &product) || !add(value, product, &next)) {
                    ok = false; break;
                }
                value = next;
            }
            if (ok) ok = normal_nonzero && subtract(value, values[args[6]], &value);
            break;
        }
        default: result.status = Status::Invalid; ok = false; break;
        }
        if (!ok) {
            result.failed_node = i;
            output[sample] = result;
            return;
        }
        values[i] = value;
    }
    result.value = values[root];
    result.sign = exact_sign(result.value);
    result.status = result.sign ? Status::Value : Status::Boundary;
    result.accept_hinge = result.sign ? 1u : 0u;
    output[sample] = result;
}
__global__ void copy_from_texture(cudaTextureObject_t texture, std::uint32_t* output, std::size_t count) {
    const std::size_t i = static_cast<std::size_t>(blockIdx.x)*blockDim.x + threadIdx.x;
    if (i < count) output[i] = tex1Dfetch<unsigned int>(texture, static_cast<int>(i));
}
__global__ void expand_bit_planes(cudaTextureObject_t packed, std::uint32_t* words, std::size_t count) {
    const std::size_t i = static_cast<std::size_t>(blockIdx.x)*blockDim.x + threadIdx.x;
    if (i >= count) return;
    const std::size_t base = (i/32)*32;
    const unsigned lane = static_cast<unsigned>(i%32);
    std::uint32_t value = 0;
    for (unsigned bit = 0; bit < 32; ++bit)
        value |= ((tex1Dfetch<unsigned int>(packed, static_cast<int>(base+bit)) >> lane) & 1u) << bit;
    words[i] = value;
}
bool bind_texture(std::uint32_t* words, std::size_t count, cudaTextureObject_t* texture,
                  char* error, std::size_t error_capacity) {
    cudaResourceDesc resource{};
    resource.resType = cudaResourceTypeLinear;
    resource.res.linear.devPtr = words;
    resource.res.linear.desc = cudaCreateChannelDesc<unsigned int>();
    resource.res.linear.sizeInBytes = count*sizeof(std::uint32_t);
    cudaTextureDesc descriptor{};
    descriptor.readMode = cudaReadModeElementType;
    return cuda_ok(cudaCreateTextureObject(texture, &resource, &descriptor, nullptr), error, error_capacity);
}
} // anonymous namespace

bool encode_seed(const Node* nodes, std::uint32_t count, std::uint32_t inputs,
                 std::uint32_t root, std::uint64_t frame_identity,
                 std::uint32_t* words, std::size_t capacity, char* error, std::size_t error_capacity) {
    if (!nodes || !words || !count || count > max_nodes || capacity != seed_word_count(count)) {
        message(error, error_capacity, "invalid encoder buffers/count"); return false;
    }
    std::fill(words, words+capacity, 0u);
    words[0] = magic0; words[1] = magic1; words[2] = 1; words[3] = count;
    words[4] = inputs; words[5] = root;
    words[6] = static_cast<std::uint32_t>(frame_identity);
    words[7] = static_cast<std::uint32_t>(frame_identity >> 32);
    for (std::uint32_t i = 0; i < count; ++i) {
        auto* w = words+header_words+i*node_words;
        const Node& n = nodes[i];
        w[0] = static_cast<std::uint32_t>(n.op); w[1] = n.input_slot;
        w[2] = static_cast<std::uint32_t>(n.literal.a); w[3] = static_cast<std::uint32_t>(n.literal.b);
        w[4] = n.units;
        for (int j = 0; j < 7; ++j) w[6+j] = n.args[j];
    }
    return validate(words, capacity, error, error_capacity);
}

bool create_program(const std::uint32_t* words, std::size_t count, Program** output,
                    char* error, std::size_t error_capacity) {
    if (!output) { message(error, error_capacity, "missing program output"); return false; }
    *output = nullptr;
    if (!validate(words, count, error, error_capacity)) return false;
    const std::size_t packed_count = ((count+31)/32)*32;
    std::vector<std::uint32_t> packed;
    try { packed.assign(packed_count, 0u); }
    catch (const std::bad_alloc&) { message(error, error_capacity, "host seed allocation failed"); return false; }
    Program* program = new (std::nothrow) Program;
    if (!program) { message(error, error_capacity, "host program allocation failed"); return false; }
    program->count = count; program->nodes = words[3]; program->inputs = words[4]; program->root = words[5];
    for (std::size_t i = 0; i < count; ++i)
        for (unsigned bit = 0; bit < 32; ++bit)
            packed[(i/32)*32+bit] |= ((words[i] >> bit) & 1u) << (i%32);
    if (!cuda_ok(cudaMalloc(reinterpret_cast<void**>(&program->words), count*sizeof(std::uint32_t)), error, error_capacity)) {
        delete program; return false;
    }
    if (!cuda_ok(cudaMalloc(reinterpret_cast<void**>(&program->packed_words), packed_count*sizeof(std::uint32_t)), error, error_capacity)) {
        destroy_program(program); return false;
    }
    if (!cuda_ok(cudaMemcpy(program->packed_words, packed.data(), packed_count*sizeof(std::uint32_t), cudaMemcpyHostToDevice), error, error_capacity)
        || !bind_texture(program->packed_words, packed_count, &program->packed_texture, error, error_capacity)) {
        destroy_program(program); return false;
    }
    expand_bit_planes<<<static_cast<unsigned>((count+127)/128),128>>>(program->packed_texture, program->words, count);
    if (!cuda_ok(cudaGetLastError(), error, error_capacity)
        || !cuda_ok(cudaDeviceSynchronize(), error, error_capacity)
        || !bind_texture(program->words, count, &program->texture, error, error_capacity)) {
        destroy_program(program); return false;
    }
    *output = program;
    return true;
}

void destroy_program(Program* program) {
    if (!program) return;
    if (program->texture) cudaDestroyTextureObject(program->texture);
    if (program->packed_texture) cudaDestroyTextureObject(program->packed_texture);
    if (program->words) cudaFree(program->words);
    if (program->packed_words) cudaFree(program->packed_words);
    delete program;
}

bool evaluate(Program* program, const Coeff* samples, std::size_t sample_count, Result* results,
              char* error, std::size_t error_capacity) {
    if (!program || (!results && sample_count) || (!samples && sample_count && program->inputs)
        || sample_count > 10000000) {
        message(error, error_capacity, "invalid batch buffers or declared batch limit"); return false;
    }
    if (!sample_count) return true;
    Coeff* device_inputs = nullptr;
    Result* device_output = nullptr;
    const std::size_t input_bytes = sample_count*program->inputs*sizeof(Coeff);
    const std::size_t output_bytes = sample_count*sizeof(Result);
    auto cleanup = [&]() { if (device_inputs) cudaFree(device_inputs); if (device_output) cudaFree(device_output); };
    if (input_bytes) {
        if (!cuda_ok(cudaMalloc(reinterpret_cast<void**>(&device_inputs), input_bytes), error, error_capacity)) return false;
        if (!cuda_ok(cudaMemcpy(device_inputs, samples, input_bytes, cudaMemcpyHostToDevice), error, error_capacity)) {
            cleanup(); return false;
        }
    }
    if (!cuda_ok(cudaMalloc(reinterpret_cast<void**>(&device_output), output_bytes), error, error_capacity)) {
        cleanup(); return false;
    }
    run<<<static_cast<unsigned>((sample_count+127)/128),128>>>(program->texture, device_inputs,
        program->inputs, program->nodes, program->root, sample_count, device_output);
    bool ok = cuda_ok(cudaGetLastError(), error, error_capacity);
    if (ok) ok = cuda_ok(cudaMemcpy(results, device_output, output_bytes, cudaMemcpyDeviceToHost), error, error_capacity);
    cleanup();
    return ok;
}

bool read_seed_words(Program* program, std::uint32_t* words, std::size_t capacity,
                     char* error, std::size_t error_capacity) {
    if (!program || !words || capacity != program->count) {
        message(error, error_capacity, "texture roundtrip capacity mismatch"); return false;
    }
    std::uint32_t* output = nullptr;
    if (!cuda_ok(cudaMalloc(reinterpret_cast<void**>(&output), capacity*sizeof(std::uint32_t)), error, error_capacity)) return false;
    copy_from_texture<<<static_cast<unsigned>((capacity+127)/128),128>>>(program->texture, output, capacity);
    bool ok = cuda_ok(cudaGetLastError(), error, error_capacity);
    if (ok) ok = cuda_ok(cudaMemcpy(words, output, capacity*sizeof(std::uint32_t), cudaMemcpyDeviceToHost), error, error_capacity);
    cudaFree(output);
    return ok;
}

bool device_available() {
    int count = 0;
    return cudaGetDeviceCount(&count) == cudaSuccess && count > 0;
}
}} // namespace atomos::exact
