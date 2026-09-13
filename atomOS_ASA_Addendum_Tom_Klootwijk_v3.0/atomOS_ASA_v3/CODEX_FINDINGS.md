# Kernel and texture-cache validation - 13 September 2026

The corrected Windows build executes both native CUDA kernels on the NVIDIA GeForce RTX 5070 Ti Laptop GPU (compute capability 12.0). CPU/global/texture comparisons passed with exact flags and logical cell keys at the unchanged 2e-6 float tolerance. Independent Python verification measured zero error for retained 65,536-sample runs in each layout and 36 boundary cases totaling 14,328 samples. All four requested Compute Sanitizer tools passed on the final source.

This is a user-mode application using the installed NVIDIA driver. The repository has no custom CPU ring-0 driver, and the texture cache holds data rather than the program's executable instructions. Windows reports the installed `nvlddmkm` kernel driver running. This observation does not make ASA itself a ring-0 implementation. See `docs/PRIVILEGE_CONTRACT.md`.

## Defects corrected before the report

| Finding | Correction and regression evidence |
|---|---|
| Zero-sample CUDA metadata unconditionally claimed GPU execution, despite skipping both launches. | `cuda/asa_texture.cu` sets `gpu_executed` from nonzero sample count; CPU/GPU CLI integration checks zero and nonzero records in both layouts. |
| Windows found `compute-sanitizer.bat` during discovery but launching the bare tool name raised uncaught WinError 2. | `scripts/validate.py` resolves the native executable in the same toolkit, without a shell. Launch failures now write an unavailable status. Native tool resolution and failure recording have regressions; all eight final sanitizer invocations actually ran. |
| Requested host ASan/UBSan could silently run uninstrumented under MSVC and report pass. | CMake rejects that unsupported combination with a distinct diagnostic; the validator reports exit 2/unavailable. Actual local rejection and regression recorded. |
| Python checks were optional in CMake, and negative CLI tests accepted any nonzero exit, including a possible crash. | Require Python >=3.10, pin the invoking interpreter, require clean exit 1 and no newly created result directory for rejected inputs, and recheck existing sealed output after rejection. Ten validation regressions now run. |
| Native CUDA linking warned LNK4098 about conflicting MSVC runtime libraries. | Object/library directives demonstrated `/MD` vs static CUDA runtime `LIBCMT`; both CUDA targets now use the matching static CRT. Rebuilt without the linker warning. Strict host floating-point options are also explicit. |

The first GPU configure selected stale CUDA 12.9 Visual Studio integration with an empty toolkit path. Selecting the installed 12.8 toolkit explicitly resolved it. An overly long build-directory path also reproduced an MSBuild FileTracker error; the short `b128` directory resolved it. README documents the working command and the validator records repeated `--cmake-arg` selections. No compiler-version override or driver protection change was used.

## Coverage added

- Extracted the unchanged actual texture/global kernels and resource wrappers into `cuda/asa_device.cuh` so the focused harness tests the production kernels.
- Added `tests/test_cuda.cu` and its independent Python runner: 36 cases, 398 samples each, 16 explicit expected-result assertions, both layouts, nonfinite inputs, aperture/hinge/axis edges, positive/negative/maximal warp, `nextafter` boundaries, LUT seams, rectangular dictionaries and very small/large finite charts.
- Expanded integration to 22 CPU and 23 GPU scenarios: sample counts 0, 1, 257, 4097 and 65536 in both layouts, 8x8/16x24/40x64 dictionaries, invalid dimensions/budget/count/layout/options/device, and existing-output rejection.
- Extracted the unchanged free-VRAM predicate and added 10 deterministic boundary assertions for the half-free rule and 512 MiB reserve. Actual allocation and admission ran on the device; low-VRAM rejection was simulated, not tested by exhausting the laptop.
- `include/asa/core.hpp`, independent Python arithmetic, operator semantics, numerical tolerances, explicit Morton bit order and bundled result data are unchanged.

## Executed final evidence

All paths below are under `local_validation/20260913_kernel_review/` unless stated otherwise.

| Evidence | Outcome |
|---|---|
| `accepted_cpu/status.json` | Pass; three CTest targets. |
| `accepted_gpu/status.json` | Pass; native build, five CTest targets, device query, eight sanitizer invocations. |
| `core_details.log` | 31 groups / 73,569 assertions passed. |
| `python_details.log` | 31 Python tests passed, including ten new regressions. |
| `accepted_gpu/*check*.log` | memcheck/initcheck/synccheck: zero errors; racecheck: zero hazards, errors and warnings. Each tool ran production 4097 and all 36 focused cases. |
| `records_evidence.json` | 65,536 samples per retained layout, 14,328 boundary samples, all independent maximum errors 0; default layout result records byte-identical. All 30 bundled `results/` files still match the original manifest. |
| `native_list-elf.log`, `native_dump-ptx.log`, `native_dump-sass.log` | Native sm_120 image plus PTX, both kernel entry points, texture-fetch instructions and native TLD instructions. |
| `profile_evidence.json` | Final texture kernel: 32,743 texture-load requests per layout; aggregate L1/TEX sector hit rate 78.74% linear, 79.90% Morton8; requested texture sectors 168,028 / 167,449. |
| `host_sanitizer_unavailable/status.json` | Correctly unavailable, exit 2; not a host sanitizer pass. |

Device/toolchain: Windows 11 Home build 26200; GPU total memory 12,820,480,000 bytes, observed free memory 11,561,598,976 bytes; NVIDIA driver 591.59 (CUDA driver API 13.1), CUDA runtime 12.8, nvcc 12.8.61, MSVC 19.44.35221, CMake 4.3.2, Python 3.13.11, Compute Sanitizer 2025.1.0.0 and Nsight Compute 2025.1.0.0. Driver API version and installed runtime version are distinct.

Early `gpu_baseline` configure failed. `gpu_pre_fixes` passed initial CTest but its sanitizer launcher raised WinError 2 before a status record was written. `gpu_final` passed an earlier expanded harness; `gpu_verified` caught a wrong expected test cell caused by assuming a binary64 midpoint was exactly 2. The test was corrected to use an exactly represented sample at rho=1 and rebuilt. `accepted_gpu` is the authoritative completed run on the final source; earlier failures remain visible.

## Practical limits

Tests support the declared synthetic numerical operator on this hardware, not physical lens calibration, every possible input or formal proof. Minimum/maximum LUT-size cases use identity coefficients; nonzero interpolation is covered at 512 bins. GPU memory pressure rejection is tested with simulated free-byte values. Destructor cleanup return codes remain unchecked; normal execution synchronization, separate read/write allocations and resource destruction order were reviewed. Racecheck checks shared-memory hazards and does not prove arbitrary global or texture coherence. Source tables are read-only during kernel execution.

The profiler results are one observation per layout for 65,536 samples with 256 blocks of 256 threads. The hit metric covers aggregate L1/TEX sectors during the texture kernel, not exclusively texture accesses. They establish observed cache activity, not speedup, pinned residency, code execution inside cache or a performance guarantee. No repeated warmed performance benchmark or calibrated optics experiment was claimed.

Original package manifest and delivered PDF remain unchanged. Local source fixes intentionally differ from the delivered edition; the new report and patch describe that difference rather than reissuing its manifest.
