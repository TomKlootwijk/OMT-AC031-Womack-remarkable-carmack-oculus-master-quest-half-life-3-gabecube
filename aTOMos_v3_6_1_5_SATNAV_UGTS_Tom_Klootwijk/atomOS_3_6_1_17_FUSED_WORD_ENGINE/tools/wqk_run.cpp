#include "atomos/tomagi_feedback.hpp"
#include <cuda_runtime.h>
#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <locale>
#include <memory>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace vm = atomos::tomagi;
using U32 = std::uint32_t;
using U64 = std::uint64_t;
using Clock = std::chrono::steady_clock;

namespace {
const char* usage =
    "Usage: wqk_run --program FILE.tmg [--lanes N] [--steps N]\n"
    "               [--fetch texture|global] [--feedback copy32|none]\n"
    "               [--dispatch reference|fused] [--chunk N]\n"
    "               [--lane-init identical|spread] [--output FILE.json]\n"
    "Defaults: lanes=1, steps=24, fetch=texture, feedback=none, dispatch=fused, chunk=32.\n"
    "JSON goes to stdout unless --output is supplied.\n"
    "N is a positive decimal uint32. Every lane starts at entry_state().\n"
    "copy32: old q low/high32 -> rho/vrho before each VM instruction; fresh\n"
    "EMIT payload -> copy-drive ASA/NA+JK (valid mask 0xffffffff, q initially0).\n"
    "Fused chunks contain1..256steps with no intermediate observer.\n"
    "Spread initialization varies raw rho, lineage and cell by lane index.\n"
    "One device phase, then final readback; no per-step host readback or trace.\n"
    "Allocations are checked against host size limits and current free VRAM;\n"
    "the VRAM estimate excludes driver overhead, and allocation can still fail.\n"
    "Pure-VM cumulative emission count is null: only its final receipt is kept.\n"
    "Receipt epochs are zero based. hash64 is noncryptographic FNV-1a-64.\n"
    "Exit status: 0 complete, 1 input/runtime/output error, 2 completed with faults.\n";

void require(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}
void cu(cudaError_t result) {
    if (result != cudaSuccess) throw std::runtime_error(cudaGetErrorString(result));
}
double milliseconds(Clock::time_point first, Clock::time_point last) {
    return std::chrono::duration<double, std::milli>(last - first).count();
}
U64 add_size(U64 a, U64 b) {
    require(b <= std::numeric_limits<U64>::max() - a, "byte-count addition overflow");
    return a + b;
}
U64 multiply_size(U64 a, U64 b) {
    require(!b || a <= std::numeric_limits<U64>::max() / b, "byte-count multiplication overflow");
    return a * b;
}
void host_size(U64 bytes) {
    require(bytes <= std::numeric_limits<std::size_t>::max(), "allocation exceeds host size_t range");
}
U32 positive_u32(const std::string& text) {
    require(!text.empty(), "empty positive integer");
    U64 value = 0;
    for (unsigned char digit : text) {
        require(digit >= '0' && digit <= '9', "N must contain decimal digits only");
        value = value * 10 + (digit - '0');
        require(value <= std::numeric_limits<U32>::max(), "N exceeds positive uint32 range");
    }
    require(value != 0, "N must be positive");
    return static_cast<U32>(value);
}
struct Options {
    std::filesystem::path program, output;
    U32 lanes = 1, steps = 24, chunk = 32;
    bool texture = true, feedback = false, fused = true, spread = false;
};
Options arguments(int argc, char** argv) {
    Options options;
    std::set<std::string> seen;
    for (int i = 1; i < argc; ++i) {
        const std::string flag = argv[i];
        require(flag == "--program" || flag == "--output" || flag == "--lanes" ||
                flag == "--steps" || flag == "--fetch" || flag == "--feedback" ||
                flag == "--dispatch" || flag == "--chunk" || flag == "--lane-init",
                "unknown argument: " + flag);
        require(seen.insert(flag).second, "duplicate argument: " + flag);
        require(i + 1 < argc, "missing value for " + flag);
        const std::string value = argv[++i];
        require(!value.empty(), "empty value for " + flag);
        if (flag == "--program") options.program = value;
        else if (flag == "--output") options.output = value;
        else if (flag == "--lanes") options.lanes = positive_u32(value);
        else if (flag == "--steps") options.steps = positive_u32(value);
        else if (flag == "--chunk") {options.chunk=positive_u32(value);require(options.chunk<=256,"chunk must be1..256");}
        else if (flag == "--dispatch") {
            require(value == "fused" || value == "reference", "dispatch must be reference or fused");
            options.fused = value == "fused";
        } else if (flag == "--lane-init") {
            require(value == "identical" || value == "spread", "lane-init must be identical or spread");
            options.spread = value == "spread";
        }
        else if (flag == "--fetch") {
            require(value == "texture" || value == "global", "fetch must be texture or global");
            options.texture = value == "texture";
        } else {
            require(value == "copy32" || value == "none", "feedback must be copy32 or none");
            options.feedback = value == "copy32";
        }
    }
    require(!options.program.empty(), "--program is required");
    if (!options.output.empty()) {
        require(std::filesystem::absolute(options.program).lexically_normal() !=
                std::filesystem::absolute(options.output).lexically_normal(),
                "output must not overwrite the input program");
        if (std::filesystem::exists(options.output))
            require(!std::filesystem::equivalent(options.program, options.output),
                    "output aliases the input program");
    }
    return options;
}
U32 read32(const std::vector<std::uint8_t>& bytes, std::size_t offset) {
    require(offset <= bytes.size() && bytes.size() - offset >= 4, "truncated program header");
    return U32(bytes[offset]) | (U32(bytes[offset + 1]) << 8) |
           (U32(bytes[offset + 2]) << 16) | (U32(bytes[offset + 3]) << 24);
}
std::vector<std::uint8_t> read_program(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary | std::ios::ate);
    require(bool(input), "cannot open program file");
    const auto end = input.tellg();
    require(end >= std::streampos(128), "program is shorter than its 128-byte header");
    const U64 count = static_cast<U64>(static_cast<std::streamoff>(end));
    host_size(count);
    require(count <= static_cast<U64>(std::numeric_limits<std::streamsize>::max()),
            "program exceeds stream read range");
    std::vector<std::uint8_t> bytes(static_cast<std::size_t>(count));
    input.seekg(0);
    input.read(reinterpret_cast<char*>(bytes.data()), static_cast<std::streamsize>(count));
    require(bool(input), "program read did not complete");
    const char magic[8] = {'T','O','M','A','G','I','1',0};
    require(std::memcmp(bytes.data(), magic, 8) == 0, "wrong TOMAGI magic");
    const U32 cells = read32(bytes, 16);
    require(cells && count == 128 + U64(cells) * 48, "program size differs from its cell count");
    return bytes;
}
std::string json_string(const std::string& value) {
    std::ostringstream out;
    out << '"';
    static const char hex[] = "0123456789abcdef";
    for (unsigned char ch : value) {
        if (ch == '"') out << "\\\"";
        else if (ch == '\\') out << "\\\\";
        else if (ch < 0x20) out << "\\u00" << hex[ch >> 4] << hex[ch & 15];
        else out << char(ch);
    }
    out << '"';
    return out.str();
}
std::string hex64(U64 word) {
    std::ostringstream out;
    out << "0x" << std::hex << std::setfill('0') << std::setw(16) << word;
    return out.str();
}
struct Hash64 {
    U64 value = 14695981039346656037ULL;
    void byte(std::uint8_t b) { value = (value ^ b) * 1099511628211ULL; }
    void word32(U32 w) { for (unsigned i = 0; i < 4; ++i) byte(std::uint8_t(w >> (8 * i))); }
    void word64(U64 w) { for (unsigned i = 0; i < 8; ++i) byte(std::uint8_t(w >> (8 * i))); }
    void text(const char* text) { while (*text) byte(std::uint8_t(*text++)); byte(0); }
};
std::array<U64, 8> feedback_words(const vm::WordState& state) {
    return {state.q, state.parity, state.last_epoch, state.last_drive,
            state.hinges, state.initialized, state.status, state.reserved};
}
void receipt_hash(Hash64& hash, const vm::Receipt& receipt) {
    hash.word64(receipt.epoch);
    hash.word32(receipt.executed); hash.word32(receipt.emitted);
    hash.word32(receipt.cell_before); hash.word32(receipt.opcode);
    hash.word32(receipt.flags); hash.word32(receipt.payload);
    hash.word32(receipt.branch_after); hash.word32(receipt.error);
}
struct Events {
    cudaEvent_t start = nullptr, stop = nullptr;
    Events() {
        cu(cudaEventCreate(&start));
        try { cu(cudaEventCreate(&stop)); }
        catch (...) { cudaEventDestroy(start); start = nullptr; throw; }
    }
    ~Events() { if (stop) cudaEventDestroy(stop); if (start) cudaEventDestroy(start); }
    Events(const Events&) = delete;
    Events& operator=(const Events&) = delete;
};
}

int main(int argc, char** argv) {
    const auto host_begin = Clock::now();
    try {
        if (argc == 2 && std::string(argv[1]) == "--help") { std::cout << usage; return 0; }
        const Options options = arguments(argc, argv);
        const auto binary = read_program(options.program);
        int device = 0, driver_version = 0, runtime_version = 0;
        cudaDeviceProp device_properties{};
        cu(cudaGetDevice(&device));
        cu(cudaGetDeviceProperties(&device_properties, device));
        cu(cudaDriverGetVersion(&driver_version));
        cu(cudaRuntimeGetVersion(&runtime_version));
        std::size_t free_vram = 0, total_vram = 0;
        cu(cudaMemGetInfo(&free_vram, &total_vram));

        const U64 lanes = options.lanes, cells = read32(binary, 16);
        const U64 per_lane = sizeof(vm::State64) + sizeof(U32) + sizeof(vm::Receipt)
                           + (options.feedback ? sizeof(vm::WordState) : 0);
        const U64 lane_bytes = multiply_size(lanes, per_lane);
        // Mirrors the VM's nonsemantic default banking and maximum transient
        // bit-plane scratch. It is a resource estimate, not an allocation promise.
        require(device_properties.maxTexture1DLinear > 0, "device has no linear texture capacity");
        const U64 max_texels = std::min<U64>(device_properties.maxTexture1DLinear,
                                          std::numeric_limits<int>::max());
        const U64 max_bank = std::min<U64>(max_texels / 3, (256ULL << 20) / 48);
        require(max_bank > 0, "device cannot hold one Cell48 texture record");
        U64 bank_capacity = 1;
        while (bank_capacity <= max_bank / 2) bank_capacity *= 2;
        const U64 bank_bytes = multiply_size((cells + bank_capacity - 1) / bank_capacity,
                                            sizeof(vm::ProgramBank));
        U64 scratch_words = (std::min<U64>(2ULL << 20, max_texels) / 32) * 32;
        require(scratch_words >= 32, "device cannot hold one packed plane block");
        scratch_words = std::min<U64>(scratch_words, ((U64(binary.size() / 4) + 31) / 32) * 32);
        const U64 estimate = add_size(add_size(binary.size(), lane_bytes),
                                     add_size(bank_bytes, multiply_size(scratch_words, 4)));
        host_size(add_size(binary.size(), lane_bytes));
        require(estimate <= free_vram, "estimated program/lane/scratch bytes exceed currently free VRAM: "
                + std::to_string(estimate) + " > " + std::to_string(free_vram));

        vm::VM machine(binary);
        if (options.lanes != 1 || options.spread) {
            std::vector<vm::State64> initial(options.lanes, machine.entry_state());
            if(options.spread) for(U32 i=0;i<options.lanes;++i){
                initial[i].words[0]+=U32(0x9e3779b9u*i);
                initial[i].words[12]^=i;
                initial[i].words[11]=U32((U64(initial[i].words[11])+i)%machine.cell_count());
            }
            machine.set_states(initial);
        }
        std::unique_ptr<vm::WordFeedback> feedback;
        std::unique_ptr<Events> events;
        if (options.feedback) {
            atomos::WordProfile profile;
            profile.valid_mask = 0xffffffffULL;
            profile.x_lut = 12; profile.j_lut = 12; profile.k_lut = 3;
            feedback = std::make_unique<vm::WordFeedback>(machine, profile, vm::WordBinding::RhoAndVrho);
        } else events = std::make_unique<Events>();
        machine.synchronize();
        const U64 vm_resident_bytes = machine.resident_bytes();
        const U64 word_state_bytes = options.feedback ? multiply_size(lanes, sizeof(vm::WordState)) : 0;
        const auto setup_end = Clock::now();

        double batch_device_ms = 0, batch_wall_ms = 0;
        if (feedback) {
            if(options.fused) feedback->run_steps_fused(options.steps, options.texture, options.chunk);
            else feedback->run_steps(options.steps, options.texture);
            batch_device_ms = feedback->stats().device_ms;
            batch_wall_ms = feedback->stats().wall_ms;
        } else {
            const auto batch_begin = Clock::now();
            cu(cudaEventRecord(events->start));
            if(options.fused){
                U32 remaining=options.steps;
                while(remaining){U32 count=std::min(remaining,options.chunk);machine.enqueue_batch(count,options.texture);remaining-=count;}
            }else for (U32 step = 0; step < options.steps; ++step) machine.enqueue_step(options.texture);
            cu(cudaEventRecord(events->stop));
            cu(cudaEventSynchronize(events->stop));
            float elapsed = 0;
            cu(cudaEventElapsedTime(&elapsed, events->start, events->stop));
            batch_device_ms = elapsed;
            batch_wall_ms = milliseconds(batch_begin, Clock::now());
        }

        const auto readback_begin = Clock::now();
        const auto states = machine.read_states();
        const auto faults = machine.read_errors();
        const auto receipts = machine.read_receipts();
        const auto words = feedback ? feedback->readback() : std::vector<vm::WordState>{};
        const auto readback_end = Clock::now();
        require(states.size() == lanes && faults.size() == lanes && receipts.size() == lanes &&
                (!feedback || words.size() == lanes), "incomplete final readback");

        U64 fault_lanes = 0, word_fault_lanes = 0, final_executed = 0, final_emitted = 0;
        U64 total_accepted_emissions = 0;
        Hash64 hash;
        hash.text("ATOMOS-WQK-RUN-STATE-V1"); hash.word32(options.lanes); hash.word32(options.steps);
        hash.text("State64");
        for (const auto& state : states) for (U32 word : state.words) hash.word32(word);
        hash.text("Fault32");
        for (U32 fault : faults) { hash.word32(fault); fault_lanes += fault != 0; }
        hash.text("Receipt40");
        for (const auto& receipt : receipts) {
            receipt_hash(hash, receipt);
            final_executed += receipt.executed != 0;
            final_emitted += receipt.executed && receipt.emitted && !receipt.error;
        }
        hash.text("WordState64"); hash.word64(words.size());
        for (const auto& word : words) {
            for (U64 field : feedback_words(word)) hash.word64(field);
            word_fault_lanes += word.status != 0;
            total_accepted_emissions = add_size(total_accepted_emissions, word.hinges);
        }
        const double host_complete_ms = milliseconds(host_begin, Clock::now());
        const bool failed_lanes = fault_lanes || word_fault_lanes;
        const auto& first_receipt = receipts.front();
        std::ostringstream out;
        out.imbue(std::locale::classic()); out << std::fixed << std::setprecision(6);
        out << "{\n  \"profile\": \"ATOMOS-WQK-NATIVE-RUN-R2\",\n"
            << "  \"status\": " << json_string(failed_lanes ? "completed_with_faults" : "completed") << ",\n"
            << "  \"device\": {\"index\": " << device << ", \"name\": " << json_string(device_properties.name)
            << ", \"compute_major\": " << device_properties.major << ", \"compute_minor\": " << device_properties.minor
            << ", \"multiprocessors\": " << device_properties.multiProcessorCount
            << ", \"total_global_bytes\": " << U64(device_properties.totalGlobalMem)
            << ", \"free_bytes_before_setup\": " << U64(free_vram)
            << ", \"runtime_total_bytes\": " << U64(total_vram)
            << ", \"max_texture_1d_linear_texels\": " << device_properties.maxTexture1DLinear
            << ", \"driver_version\": " << driver_version << ", \"runtime_version\": " << runtime_version << "},\n"
            << "  \"program_bytes\": " << binary.size() << ", \"source_vm_cells\": " << machine.cell_count() << ",\n"
            << "  \"lanes\": " << options.lanes << ", \"steps\": " << options.steps
            << ", \"fetch\": " << json_string(options.texture ? "texture" : "global")
            << ", \"feedback\": " << json_string(options.feedback ? "copy32" : "none") << ",\n"
            << "  \"dispatch\": " << json_string(options.fused ? "fused" : "reference")
            << ", \"chunk_steps\": " << options.chunk
            << ", \"lane_init\": " << json_string(options.spread ? "spread" : "identical") << ",\n"
            << "  \"lane_init_contract\": \"identical uses entry_state; spread adds 0x9e3779b9*i modulo2^32 to raw rho, XORs lineage with i, and sets cell=(entry+i)%cell_count\",\n"
            << "  \"execution_launches\": " << (options.fused ? (U64(options.steps)+options.chunk-1)/options.chunk : U64(options.steps)*(options.feedback?3:1)) << ",\n"
            << "  \"vm_resident_bytes\": " << vm_resident_bytes << ", \"word_state_bytes\": " << word_state_bytes
            << ", \"setup_allocation_estimate_bytes\": " << estimate << ",\n"
            << "  \"timings_ms\": {\"setup\": " << milliseconds(host_begin, setup_end)
            << ", \"batch_device\": " << batch_device_ms << ", \"batch_wall\": " << batch_wall_ms
            << ", \"readback\": " << milliseconds(readback_begin, readback_end)
            << ", \"host_complete\": " << host_complete_ms << "},\n"
            << "  \"timing_contract\": \"setup includes input, CUDA initialization, upload and lane allocation; device batch uses CUDA events on the ordered default stream; batch wall includes dispatch and completion; readback includes final vector allocation and copies; host complete includes validation and digest but excludes JSON serialization/output; no warmup or per-step host readback\",\n"
            << "  \"memory_contract\": \"resident bytes count owned arrays, excluding CUDA driver/texture/event overhead; setup estimate includes temporary packed-plane storage; allocation may still fail\",\n"
            << "  \"vm_fault_lanes\": " << fault_lanes << ", \"feedback_fault_lanes\": " << word_fault_lanes << ",\n"
            << "  \"last_dispatch_executed_lanes\": " << final_executed
            << ", \"last_dispatch_emitted_lanes\": " << final_emitted << ",\n"
            << "  \"total_accepted_feedback_emissions\": ";
        if (feedback) out << total_accepted_emissions; else out << "null";
        out << ",\n  \"pure_vm_cumulative_emissions\": null,\n"
            << "  \"emission_contract\": \"feedback counts every accepted fresh EMIT; pure VM retains only the final receipt and does not collect cumulative EMIT counts\",\n"
            << "  \"hash64\": " << json_string(hex64(hash.value)) << ",\n"
            << "  \"hash64_algorithm\": \"FNV-1a-64; noncryptographic, collisions possible\",\n"
            << "  \"hash64_serialization\": \"NUL-terminated profile tag, lanes/steps u32 LE, NUL-terminated State64 tag and all raw state words, Fault32 tag and all fault words, Receipt40 tag and all receipt fields in declaration order, WordState64 tag/count u64 and all feedback fields; all integers little endian, no padding, fetch and timings excluded\",\n"
            << "  \"receipt_epoch_base\": 0, \"next_vm_epoch\": " << machine.epoch() << ",\n"
            << "  \"first_lane\": {\"state_words_u32\": [";
        for (unsigned i = 0; i < 16; ++i) { if (i) out << ", "; out << states.front().words[i]; }
        out << "], \"vm_fault\": " << faults.front()
            << ", \"last_receipt\": {\"epoch\": " << first_receipt.epoch
            << ", \"executed\": " << first_receipt.executed << ", \"emitted\": " << first_receipt.emitted
            << ", \"cell_before\": " << first_receipt.cell_before << ", \"opcode\": " << first_receipt.opcode
            << ", \"flags\": " << first_receipt.flags << ", \"payload\": " << first_receipt.payload
            << ", \"branch_after\": " << first_receipt.branch_after << ", \"error\": " << first_receipt.error
            << "}, \"feedback_words_u64_hex\": ";
        if (feedback) {
            out << '['; const auto first = feedback_words(words.front());
            for (unsigned i = 0; i < first.size(); ++i) { if (i) out << ", "; out << json_string(hex64(first[i])); }
            out << ']';
        } else out << "null";
        out << "},\n  \"feedback_word_order\": [\"q\",\"parity\",\"last_epoch\",\"last_drive\",\"hinges\",\"initialized\",\"status\",\"reserved\"]\n}\n";
        require(bool(out), "JSON serialization failed");
        if (options.output.empty()) {
            std::cout << out.str();
            require(bool(std::cout), "JSON stdout write failed");
        } else {
            std::ofstream output(options.output, std::ios::binary | std::ios::trunc);
            require(bool(output), "cannot open JSON output file");
            output << out.str(); output.close();
            require(bool(output), "JSON output write failed");
        }
        return failed_lanes ? 2 : 0;
    } catch (const std::bad_alloc&) {
        std::cerr << "wqk_run: host allocation failed; reduce --lanes or program size\n";
        return 1;
    } catch (const std::exception& error) {
        std::cerr << "wqk_run: " << error.what() << '\n';
        return 1;
    }
}
