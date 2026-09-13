// Standalone numerical evidence for invariant_bank's fixed binary64 .4 rotation.
// This probe does not alter kernel inputs, perform epochs, or measure residency.
#include <cuda_runtime.h>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>

namespace {
constexpr double rotation = .4;
constexpr double rounded_cos = 0x1.d7954e7dba2f8p-1;
constexpr double rounded_sin = 0x1.8ec3ae92b676bp-2;

void check(cudaError_t status, const char* operation) {
    if (status != cudaSuccess)
        throw std::runtime_error(std::string(operation) + ": " + cudaGetErrorString(status));
}

std::uint64_t bits(double value) {
    std::uint64_t result;
    std::memcpy(&result, &value, sizeof(result));
    return result;
}

std::string quote(const std::string& value) {
    std::ostringstream result;
    result << '"';
    for (unsigned char c : value) {
        if (c == '"' || c == '\\') result << '\\' << char(c);
        else if (c < 32) result << "\\u" << std::hex << std::setw(4) << std::setfill('0') << unsigned(c);
        else result << char(c);
    }
    result << '"';
    return result.str();
}

void emit_value(double value, double expected) {
    std::ostringstream hex, bit_string;
    hex << std::hexfloat << value;
    bit_string << "0x" << std::hex << std::setfill('0') << std::setw(16) << bits(value);
    std::cout << "{\"decimal\":" << std::setprecision(17) << value
              << ",\"hex\":" << quote(hex.str())
              << ",\"bits\":" << quote(bit_string.str())
              << ",\"matches_correctly_rounded\":" << (bits(value) == bits(expected) ? "true" : "false") << '}';
}

void emit_pair(const char* name, const double* values) {
    std::cout << quote(name) << ":{\"cos\":";
    emit_value(values[0], rounded_cos);
    std::cout << ",\"sin\":";
    emit_value(values[1], rounded_sin);
    std::cout << '}';
}

// The uploaded argument prevents the runtime path from becoming a literal.
// Literal calls intentionally match the original core.hpp source expressions.
__global__ void rotation_values(const double* input, double* output) {
    output[0] = ::cos(.4);
    output[1] = ::sin(.4);
    output[2] = ::cos(input[0]);
    output[3] = ::sin(input[0]);
    output[4] = rounded_cos;
    output[5] = rounded_sin;
}
}

int main() {
    double* input = nullptr;
    double* output = nullptr;
    try {
        volatile double host_argument = rotation;
        const double cpu_literal[] = {::cos(.4), ::sin(.4)};
        const double cpu_runtime[] = {::cos(host_argument), ::sin(host_argument)};
        double gpu[6]{};
        cudaDeviceProp device{};
        int device_index = 0, runtime = 0, driver = 0;
        check(cudaGetDevice(&device_index), "cudaGetDevice");
        check(cudaGetDeviceProperties(&device, device_index), "cudaGetDeviceProperties");
        check(cudaRuntimeGetVersion(&runtime), "cudaRuntimeGetVersion");
        check(cudaDriverGetVersion(&driver), "cudaDriverGetVersion");
        check(cudaMalloc(reinterpret_cast<void**>(&input), sizeof(double)), "cudaMalloc input");
        check(cudaMalloc(reinterpret_cast<void**>(&output), sizeof(gpu)), "cudaMalloc output");
        check(cudaMemcpy(input, &rotation, sizeof(double), cudaMemcpyHostToDevice), "copy rotation input");
        rotation_values<<<1, 1>>>(input, output);
        check(cudaGetLastError(), "rotation_values launch");
        check(cudaDeviceSynchronize(), "rotation_values synchronize");
        check(cudaMemcpy(gpu, output, sizeof(gpu), cudaMemcpyDeviceToHost), "copy rotation output");
        check(cudaFree(output), "cudaFree output"); output = nullptr;
        check(cudaFree(input), "cudaFree input"); input = nullptr;

        bool all_match = true;
        const double* pairs[] = {cpu_literal, cpu_runtime, gpu, gpu + 2, gpu + 4};
        for (const double* pair : pairs)
            all_match = all_match && bits(pair[0]) == bits(rounded_cos) && bits(pair[1]) == bits(rounded_sin);
        std::cout << "{\"schema\":\"atomos.rotation_probe.v1\",\"capture_status\":\"passed\","
                     "\"comparison_status\":" << quote(all_match ? "matched" : "mismatch")
                  << ",\"scope\":\"literal and runtime sin/cos of the exact binary64 .4 argument; no epoch or cache claim\","
                     "\"device\":" << quote(device.name) << ",\"compute_capability\":"
                  << quote(std::to_string(device.major) + "." + std::to_string(device.minor))
                  << ",\"cuda_runtime\":" << runtime << ",\"cuda_driver\":" << driver
                  << ",\"input\":";
        emit_value(rotation, rotation);
        std::cout << ','; emit_pair("cpu_literal", cpu_literal);
        std::cout << ','; emit_pair("cpu_runtime_volatile", cpu_runtime);
        std::cout << ','; emit_pair("gpu_literal", gpu);
        std::cout << ','; emit_pair("gpu_runtime_uploaded", gpu + 2);
        std::cout << ','; emit_pair("gpu_hex_constant", gpu + 4);
        std::cout << "}\n";
        return all_match ? 0 : 2;
    } catch (const std::exception& error) {
        if (output) cudaFree(output);
        if (input) cudaFree(input);
        std::cerr << "{\"capture_status\":\"failed\",\"error\":" << quote(error.what()) << "}\n";
        return 1;
    }
}
