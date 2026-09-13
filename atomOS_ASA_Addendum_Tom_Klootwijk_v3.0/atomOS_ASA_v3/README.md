# atomOS ASA v3 — operator addendum

**Concept author:** Tom Klootwijk · NL200678942 · 10-07-1990  
**Target:** NVIDIA GeForce RTX 5070 Ti **Laptop** GPU, nominal **12 GB GDDR7**  
**Release:** 3.0.0 · 13 September 2026

Start with `atomOS_ASA_Addendum_Tom_Klootwijk.pdf`, then `CODEX_REVIEW.md`.

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

## What has been run in this delivery

See `docs/BUILD_STATUS.md` and `results/validation_status.json`. Recorded tests include CPU compilation, 30 C++ test groups, 21 Python tests, independent layout checks, CLI failure cases and address/undefined-behavior sanitizer checks. **CUDA compilation and GPU execution were not available in the preparation environment.** No `.cubin` or claimed device benchmark is bundled.

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

`include/asa/` contains shared C++/CUDA operators, layout and fixtures. `cuda/asa_texture.cu` contains device kernels and texture lifetimes. `python/` is the independent reference, rational timeline and provenance layer. `tests/` and `scripts/` run reproducible checks. `results/` holds executed evidence. `docs/addendum.tex` is the editable PDF source. `source/manifest.json` fingerprints the two source PDFs; original transcripts are not redistributed.

Run `python scripts/verify_package.py` to check the delivery hashes. The record seal checks integrity relative to its retained head; it is not an identity credential. Re-running an unchanged fixture preserves transition data, while measured timing and whole-file hashes may differ.
