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

The delivered-edition table above is historical and unchanged. The corrected local source was subsequently built and executed on an RTX 5070 Ti Laptop GPU, CC 12.0, with CUDA 12.8.61 and MSVC 19.44.35221. Authoritative new status: `local_validation/20260913_kernel_review/accepted_gpu/status.json` and `accepted_cpu/status.json` in the same report root.

Local CPU validation passed three CTest targets; CUDA validation passed five. Detailed results: 31 C++ groups / 73,569 assertions, 31 Python tests, 22 CPU and 23 GPU integration scenarios, and 36 focused GPU cases / 14,328 samples. Independent Python verification had maximum error 0 for retained 65,536-sample runs in each layout and every focused case. Memcheck, initcheck, racecheck and synccheck each passed production 4097 samples and all focused cases. MSVC host ASan/UBSan was explicitly unavailable (exit 2), not passed.

Nsight Compute observed texture-load requests and aggregate L1/TEX cache hits in the final texture kernel. This is evidence for a CUDA texture-data path, not a custom ring-0 implementation, executable cache residency or a performance guarantee. `CODEX_FINDINGS.md` records fixes, exact scope, earlier failures, limitations and retained evidence. All 30 bundled `results/` files still match the original manifest.
