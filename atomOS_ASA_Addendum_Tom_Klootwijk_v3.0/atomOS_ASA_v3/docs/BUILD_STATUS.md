# Build status — delivered edition

The `results/validation_status.json` record is authoritative for the delivered run.

| Check | Status |
|---|---|
| C++17 release build, Linux | Passed |
| C++ tests | 30 groups / 73,559 assertions passed |
| Independent Python tests | 21 passed |
| CLI integration | 10 scenarios passed |
| CTest | 3 targets passed |
| ASan/UBSan CTest | Same 3 targets passed |
| Independent scalar oracle | 65,536 samples per layout; maximum error 0 in both delivered runs |
| CUDA compilation | Not executed: `nvcc` unavailable |
| CUDA execution / Compute Sanitizer | Not executed: NVIDIA device unavailable |
| Windows compilation | Not executed |

`compute_ms` in bundled examples is CPU timing for the numerical evaluation loop. It excludes fixture construction and file output. It is not a GPU estimate. New local evidence belongs in a new report directory, not in the delivered result files.

## Local Windows validation - 13 September 2026

The delivered-edition table above remains historical. Final-source authority is [final_gpu/status.json](../local_validation/20260913_kernel_review/final_gpu/status.json) and [final_cpu/status.json](../local_validation/20260913_kernel_review/final_cpu/status.json), superseding all earlier local passes. The source was built and executed on an RTX 5070 Ti Laptop GPU, CC 12.0, with CUDA 12.8.61 and MSVC 19.44.35221.

| Final local check | Result |
|---|---|
| CPU configure/build and CTest | Passed; 3 targets |
| CUDA configure/build and CTest | Passed; 5 targets, native sm_120 plus PTX |
| C++ contract | 33 groups / 74,982 assertions passed |
| Python tests | 42 passed |
| CLI integration | 58 CPU / 76 GPU scenarios passed |
| Independent oracle | 65,536 samples per retained layout plus 72 focused cases / 28,656 samples; maximum error 0 |
| Stream completion | Normal destruction, exception unwinding and explicit close passed, 65,536 samples each; CPU comparison only for these additional 196,608 sample evaluations |
| Compute Sanitizer | 16 invocations passed: all 4 tools on natural/512, locality/512, locality/512 with persist-image, and the focused executable including stream-completion regressions |
| Host ASan/UBSan with MSVC | Unavailable, exit 2; not a pass |
| Original bundled results | All 30 files still match the original manifest |

The [final retained evidence](../local_validation/20260913_kernel_review/final_records/records_evidence.json), [512-thread cache benchmark](../local_validation/20260913_kernel_review/cache_final_512/benchmark.json) and [residency probe](../local_validation/20260913_kernel_review/residency_final/residency_probe.json) identify the same final CUDA executable. `include/asa/core.hpp` and the independent `python/reference.py` arithmetic are unchanged, as are logical keys, Morton bit order and the 2e-6 float tolerance.

CUDA now defaults to locality ordering and 512 threads per block. In the controlled 65,536-sample Morton8 comparison, texture-only cold hit rate rose from 67.96% to 71.21%, miss sectors fell from 53,652 to 10,470, and warmed texture mean time fell from 0.060709 ms to 0.029649 ms. The benchmark used five warmups, 30 timed launches per path, five unprofiled process runs and three cold profiler captures per condition. Host sorting/restoration costs remain material; kernel improvements do not establish an end-to-end speedup. Process wall time includes both paths, setup, validation, repeated launches and file output.

The final residency probe accepted 84 one-pass captures. Independently measured warm L2 read misses were zero for both paths and both policies. The image-persistence hint was read back successfully: 524,288 bytes requested, 2,359,296 bytes accepted, a 524,288-byte window, and policy hitRatio 1. That ratio is a policy parameter, not a measured hit rate. Texture-path evict-last counters remained zero; the global path showed priority tagging. No texture persistence benefit was demonstrated, so normal L2 policy remains the default. Separate L2 captures are not combined into a same-launch hit percentage.

One-pass capacity profiling measured an 8 KiB shared-memory partition, 1 KiB driver shared memory per block and zero static/dynamic application shared memory. Together with NVIDIA's documented 128 KiB combined capacity for CC 12.x, this suggests a nominal 120 KiB L1/TEX allocation budget per SM. It is not measured occupancy or proof of permanent cache residence.

Earlier failed and unavailable attempts are retained, including the rejected four-pass L2 probe in `residency_initial`. This repository remains a user-mode numerical CUDA application, not a custom ring-0 driver or executable pinned in a texture cache. [CODEX_FINDINGS.md](../CODEX_FINDINGS.md) gives the fixes, measurement details, source links, earlier failures and limits.
