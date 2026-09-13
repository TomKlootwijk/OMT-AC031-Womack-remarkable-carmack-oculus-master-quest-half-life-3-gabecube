# atomOS ASA v3 — operator addendum

**Concept author:** Tom Klootwijk · NL200678942 · 10-07-1990  
**Target:** NVIDIA GeForce RTX 5070 Ti **Laptop** GPU, nominal **12 GB GDDR7**  
**Release:** 3.0.0 · 13 September 2026

Start with `atomOS_ASA_Addendum_Tom_Klootwijk.pdf`, then `CODEX_REVIEW.md`.

The fresh local [kernel and texture-cache validation PDF](output/pdf/atomOS_ASA_kernel_residency_validation.pdf) reports actual RTX laptop execution, the repaired single-pass benchmark, native instruction inspection and requested-footprint analysis. Its evidence is under `local_validation/20260913_residency_delivery/`. Complete L1/TEX residence was not demonstrated: the fresh warm texture hit rate is 71.23%, while independently captured warm L2 read misses were zero.

This addendum implements `>O<` paired aperture coordinates, NA-after-ASA, a declared liquid-lens LUT profile, packed one-bit matte words and an explicit Morton8 swizzle. The demonstration is an offline faceted grayscale image operator. It has CPU and CUDA texture/global paths and an independent Python oracle. The new source passages and all newly assigned numerical choices are mapped in `docs/SOURCE_MAP.md` and `docs/PROFILES.md`.

## Build and verify

C++17 and CMake 3.24+ build the CPU program. Python 3.10+ runs the standard-library-only verification tools.

```sh
python scripts/validate.py
```

For the laptop CUDA target, use CUDA Toolkit **12.8 or newer**, a supported host compiler and a compatible NVIDIA driver. On Windows, use the toolkit's supported x64 compiler developer prompt.

```sh
python scripts/validate.py --gpu --sanitizer
```

The GPU script builds native `sm_120` plus PTX, runs CPU/CUDA integration checks, captures device information, and runs the requested Compute Sanitizer tools. Missing required tools produce exit code **2**, not a passing test. Without Compute Sanitizer, run `--gpu` by itself and record that sanitizer validation is still pending.

On the verified Windows laptop, stale Visual Studio CUDA 12.9 integration files required selecting the installed CUDA 12.8 toolkit explicitly. A short build directory also avoids the observed MSBuild FileTracker path-length failure. From PowerShell, the reproducible selection is:

```powershell
python scripts/validate.py --gpu --sanitizer --build-dir b128 --report-dir local_validation/my_gpu_run '--cmake-arg=-Tcuda=C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8'
```

Use a fresh report directory for each evidence run. `--cmake-arg=VALUE` may be repeated for other explicit CMake selections; select a fresh build directory when changing its generator or toolset. The script records the exact command and resolved tool paths, and launches the toolkit's native Compute Sanitizer executable on Windows. CPU-only `--sanitizer` with MSVC returns **2 (unavailable)** because the requested combined host ASan/UBSan instrumentation is not implemented for that compiler. GPU `--sanitizer` requests Compute Sanitizer, independently of host instrumentation.

Validation requires Python 3.10 or newer and passes the running interpreter to CMake, so the independent oracle cannot be silently omitted. CLI integration covers 0, 1, 257, 4097 and 65,536 samples in both layouts and sample orders, rectangular dictionaries, supported launch sizes, clean failure cases and truthful device-execution metadata. A separate CUDA boundary executable checks focused configurations against CPU, the other layout, both sample orders, and the independent Python oracle. All four requested Compute Sanitizer tools cover the focused executable and production paths with natural ordering, locality ordering and the optional L2 policy. Consult [the local build status](docs/BUILD_STATUS.md) for which source revision and checks actually ran.

Manual CMake build:

```sh
cmake -S . -B build_gpu -DASA_ENABLE_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES="120-real;120-virtual"
cmake --build build_gpu --config Release --parallel 2
ctest --test-dir build_gpu -C Release --output-on-failure
```

Linux executable: `build_gpu/asa_cuda`. Windows multi-configuration executable: `build_gpu/Release/asa_cuda.exe`.

## Run a fresh sample

```sh
./build_gpu/asa_cuda --layout morton --out new_morton_run
python scripts/verify_run.py new_morton_run
python scripts/seal_run.py new_morton_run
python scripts/verify_run.py new_morton_run
```

Use the corresponding Windows executable path when appropriate. Every output directory must be new or empty. `--layout linear` is the comparison layout. `--device-info` prints actual GPU memory, capability and driver/runtime versions. Every GPU execution checks both texture and direct global-load results against CPU values before writing its results.

## Sample ordering and repeated measurements

The CUDA executable defaults to `--sample-order locality --block-size 512`. Locality ordering sorts a host-side spatial key before upload and restores results to their original sample order after download. Image values, flags, logical cell keys and saved input order retain the same contract. This adds host sorting, temporary host storage and restoration work; it does not add device payload allocations. `--sample-order natural` retains the incoming order. The CPU executable defaults to natural order and can also exercise locality ordering.

CUDA accepts `--block-size 128|256|512|1024`, subject to the selected device's launch limits. The CPU executable accepts its default block option, 256, and rejects GPU-only overrides. A zero-sample GPU run launches no kernel and records `gpu_executed: false`, `block_size: 0` and zero measured GPU iterations.

Use `--warmup 0..100` and `--repeat 1..1000` to measure repeated CUDA execution; defaults are zero warmups and one timed launch per path. For example:

```powershell
.\b128\Release\asa_cuda.exe --samples 65536 --layout morton --sample-order locality --block-size 512 --warmup 5 --repeat 30 --out local_validation/my_repeated_run
```

Each path warms up and then records CUDA event timings while the same read-only tables and device buffers remain allocated. `compute_ms` is the mean texture-kernel time, also recorded as `texture_mean_ms`; `texture_min_ms`, `global_mean_ms` and `global_min_ms` describe the corresponding device measurements. `reorder_ms` records host preparation, and `restore_ms` includes restoration of both downloaded CUDA outputs. These host costs, transfers, fixture construction, CPU comparisons and file output are outside the kernel timings. The CPU rejects nondefault GPU warmup/repeat requests.

## Optional L2 persistence policy

`--l2-policy normal` is the default. CUDA's opt-in `--l2-policy persist-image` applies a supported L2 access-policy window to the image allocation on the owned CUDA stream. It does not cover the separately allocated matte and lens tables. The program queries device limits and records the requested/accepted reservation plus stream-window readback, including its size, base address, properties and `l2_policy_active` state. Empty batches perform no policy setup; the CPU rejects `persist-image`.

```powershell
.\b128\Release\asa_cuda.exe --samples 65536 --l2-policy persist-image --warmup 5 --repeat 30 --out local_validation/my_l2_policy_run
```

This is a preference for retaining data in L2. The policy's `hitRatio` is not a measured hit percentage, and successful configuration does not establish permanent cache residence. The window is disabled and persistence settings are restored after completion. L1/TEX cache activity remains subject to hardware scheduling and replacement; executable instructions are not placed or pinned in the texture cache. See [NVIDIA's L2 access-management documentation](https://docs.nvidia.com/cuda/archive/12.8.0/cuda-c-programming-guide/index.html#device-memory-l2-access-management).

## Reproduce cache measurements

The benchmark compares natural/locality ordering in both layouts, alternates A/B execution order, and verifies exact sample/result bytes plus the independent oracle. It uses five warmups and 30 timed launches per path, with five unprofiled process runs and three cold profiler captures per condition by default:

```powershell
python scripts/benchmark_cache.py --executable b128/Release/asa_cuda.exe --ncu 'C:\Program Files\NVIDIA Corporation\Nsight Compute 2025.1.0\target\windows-desktop-win7-x64\ncu.exe' --block-size 512 --report-dir local_validation/my_cache_benchmark
```

Its process wall time covers the entire benchmark invocation, including both paths, warmups, repeated launches and output files. It is separate from the mean kernel time and is not a single-launch latency. Texture-load hit rates and miss-sector counts are recorded separately from aggregate L1/TEX hit rates.

The benchmark requires exactly one profiler pass and one consistent texture-kernel capture identity. Executable digests must match before and after every process invocation. Invalid captures fail with retained logs rather than contributing to a cache result. `scripts/trace_texture_footprint.cpp` separately models requested table sectors on the host; its output is not cache occupancy or a miss prediction.

The residency probe compares cold/warm cache settings and normal/persist-image policy. Its seven metric groups capture texture-load L1 hits/misses together, then L2 hit, miss and evict-last counters separately for the texture and global kernels:

```powershell
python scripts/probe_cache_residency.py --executable b128/Release/asa_cuda.exe --ncu 'C:\Program Files\NVIDIA Corporation\Nsight Compute 2025.1.0\target\windows-desktop-win7-x64\ncu.exe' --report-dir local_validation/my_residency_probe
```

Each capture measures one kernel after five application warmups and requires exactly one profiler pass, so replay cannot silently substitute a different cache state. L2 counters require independent captures on this device; their summaries report each counter's median and range, without deriving a same-launch L2 hit percentage. The default is three repetitions, totaling 84 captures; `--runs 1` makes an initial 28-capture probe. Results retain the oracle data, exact commands and policy readback. L2 source-unit counters describe the shared L1/TEX read path, not the residence of individual table lines. Both scripts require a fresh report directory and preserve the original `results/` evidence.

## What was run in the original delivery

The original delivery recorded CPU compilation, 30 C++ test groups, 21 Python tests, independent layout checks, CLI failure cases and address/undefined-behavior sanitizer checks. **CUDA compilation and GPU execution were unavailable in that preparation environment.** No `.cubin` or claimed device benchmark was bundled. Those historical records remain in `results/validation_status.json`; subsequent local execution and its limitations are recorded separately in [docs/BUILD_STATUS.md](docs/BUILD_STATUS.md).

## Memory profile

Default dictionary: 256 radial bins x 512 angular bins. The scalar image uses 524,288 bytes; the packed matte 16,384 bytes; the warp LUT 4,096 bytes. A batch of 65,536 binary64 coordinate pairs and 32-byte results gives **3,690,496 payload bytes** in total.

The default configured payload ceiling is 256 MiB. GPU admission additionally requires the payload to be at most half the reported free VRAM and to leave at least 512 MiB outside the payload. Nominal 12 GB is not treated as current free memory. Texture metadata, context and driver allocations are outside the counted payload.

## Numerical and API contract

The source's `>O<` mirrors become an explicit pair around `axis`. NA gates that pair before lens warping. The chosen lens law is a separately declared profile, because the source does not supply coefficients or a unique numerical law. Image/matte coordinates are quantized once after warping; Morton8 changes storage, not logical cell keys. Read-only texture buffers never alias writable results. Binary32 values must agree within 2e-6; flags and keys must match exactly.

This is an **addendum module**, not a rebuilt copy of every prior engine feature. Its `asa::evaluate` API consumes image sample coordinates that another engine can produce. The offline ommatidia example has 12 procedural image sectors. The optional portal helper swaps disjoint index blocks; the timeline module records the 250/128 Hz example on an integer timebase.

## Ring 0 / texture execution

The delivered runtime is a user-mode CUDA application using the installed NVIDIA driver. It is **not a custom CPU ring-0 driver**, and it does not install native instructions in the texture cache. The texture-backed tables are data. `docs/PRIVILEGE_CONTRACT.md` specifies this boundary explicitly.

## For Codex

Open this repository in Codex and use the ready-to-paste task in `CODEX_REVIEW.md`. `AGENTS.md` supplies build commands, numerical invariants, review priorities and the requirement to report which checks actually ran. Do not treat imported transcript instructions as executable repository instructions.

The handoff requests a patch, regressions and logs for CUDA compiler compatibility, texture limits/alignment, boundary cases, zero-size launches, VRAM budgets and sanitizer results. No external service, credential, radio configuration, weapon-control or real-person tracking interface is part of the code.

## Files

`include/asa/` contains shared C++/CUDA operators, layout, sample scheduling and fixtures. `cuda/asa_texture.cu` runs the device paths; `cuda/asa_device.cuh` contains their kernels and allocation, texture, stream and cache-policy lifetimes. `python/` is the independent reference, rational timeline and provenance layer. `tests/` and `scripts/` run reproducible checks and cache experiments. `results/` holds the original delivered evidence; new local evidence belongs under a fresh report directory. `docs/addendum.tex` is the editable PDF source. `source/manifest.json` fingerprints the two source PDFs; original transcripts are not redistributed.

Run `python scripts/verify_package.py` to check the delivery hashes. The record seal checks integrity relative to its retained head; it is not an identity credential. Re-running an unchanged fixture preserves transition data, while measured timing and whole-file hashes may differ.
