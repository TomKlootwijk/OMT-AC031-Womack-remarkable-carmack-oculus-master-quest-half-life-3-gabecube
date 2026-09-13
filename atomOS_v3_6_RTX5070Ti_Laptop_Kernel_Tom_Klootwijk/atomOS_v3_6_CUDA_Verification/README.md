# atomOS v3.6 â€” CUDA kernel and verification package K1

**Concept author: Tom Klootwijk Â· NL200678942 Â· 10-07-1990**  
**Target: NVIDIA GeForce RTX 5070 Ti Laptop GPU, 12 GB GDDR7, `sm_120`.**

This package implements the **integrated v3.6 word-epoch profile**, not just the
OTAN2 panel: word production, ASA/NA/fringe selection, whole-word disposition,
persistent Jâ€“K state, encoded blend, literal OTAN2, its explicitly selected directed
completion, and the six invariant/profile checks. Three native CUDA entry points use
texture reads or global reads over the same log-polar word dictionaries.

The original ZIP provided kernel source and build tools. The September 13 laptop
review now includes real CUDA compilation, on-device execution, Compute Sanitizer,
native disassembly and cache counters. See `results/validation_status.json` and
`output/pdf/atomOS_v3_6_Kernel_Validation_Texture_Cache.pdf` for the current evidence.

## What the evidence establishes

`proofs/CLAIMS.md` states each claim and its domain. Fifteen SMT-LIB obligations were
checked with Z3; every negated property was **UNSAT**. These include full 32-bit
population-count correctness, neutral-mask recovery, support containment, final-word
idempotence, the Jâ€“K truth table, blend parity and the Morton-tile inverse.

Those are symbolic properties of the specified equations, **not a formal verification
of the compiler or GPU machine code**. The concrete implementation is checked with
independent per-bit and Python references. GPU results are accepted only after real
CUDA execution and comparison, never by substituting a CPU run. This establishes
specified software-conformance claims, not every application claim in the transcripts.

**Executed during preparation:** 30 C++ groups / 134,503 assertions; 20 Python unit
tests; seven CPU CTest cases and the same seven under AddressSanitizer + UBSan;
15 symbolic obligations; and 48 full independently checked CPU run configurations.
The original preparation status is retained under `results/review_20260913/`.

**Final laptop review executed:** 32 C++ groups / 134,521 assertions; 37 Python tests;
48 CPU configurations; 15 symbolic obligations; 144 GPU configurations and six
Compute Sanitizer matrix runs. CUDA 12.8.61 and MSVC 19.44.35221 compiled native
`sm_120` code for the RTX 5070 Ti Laptop GPU. The preparation status must not be
confused with this new execution evidence.

**Measured residency:** the optional native bulk-copy kernel retains the complete
4 MiB dictionary across the distributed SM-local texture caches through its full
warm/work/reread epoch. All 12 main cold profiles reached their compulsory miss
floor, including all six maximum-atlas profiles. Its 192-case conformance matrix
and 26 independently Python-verified trace exports passed. See
`docs/BULK_RESIDENCY.md`, `results/residency_followup/summary.json` and the final PDF
for additional shape/sanitizer coverage, timing cost and exact claim boundaries.
This is measured within-launch retention, not a cache-pinning guarantee.

## Run on your laptop

Install a CUDA Toolkit **12.8 or newer**, a CUDA-supported host C++ compiler, CMake
3.24+ and Python 3.10+. Use a compatible installed NVIDIA driver. On Windows, open
the supported x64 compiler developer prompt with `nvcc` on PATH. The hardware/source
references are in `docs/hardware_sources.json`.

From the extracted directory:

```sh
python tools/validate.py --gpu --sanitizer
```

This builds the real CUDA target, records the actual device name/capability/VRAM,
runs CPU/Python checks, then verifies **144 GPU configurations** and six additional
Compute Sanitizer memcheck runs. It covers both layouts, three read paths, all four
word producers, fringe on/off, angular tails and tiny dimensions. Each ordinary run
has three epochs and includes both literal and directed OTAN2 lanes.

To repeat the symbolic proofs too, make Z3 available and add `--proofs`:

```sh
python -m pip install -r requirements-proof.txt
python tools/validate.py --gpu --sanitizer --proofs
```

The proof dependency is optional for the engine. No script installs drivers, changes
privileges or alters a display watchdog. Each review uses a unique evidence directory
and keeps command logs. Missing GPU tools return code 3 and an explicit `not_run`
record; a failed comparison returns an error, not a success certificate.

On this Windows machine, use a short build directory and the installed toolset:

```powershell
python tools/validate.py --gpu --sanitizer --proofs --build C:/Users/Tom/.cache/ak1/gpu128 --cmake-arg=-Tcuda=12.8
```

This avoids a reproduced MSBuild path-length failure and stale CUDA 12.9 Visual
Studio integration. The runner resolves NVIDIA's native Compute Sanitizer executable
behind its Windows batch wrapper; `--sanitizer-executable` can select it explicitly.

### Manual build

```sh
cmake -S . -B build_gpu -DATOMOS_ENABLE_CUDA=ON -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES="120-real;120-virtual"
cmake --build build_gpu --config Release --parallel 2
```

Linux:

```sh
./build_gpu/atomos_cuda --probe
./build_gpu/atomos_cuda --out my_gpu_run
python tools/verify_run.py my_gpu_run
```

Windows with a multi-configuration generator:

```powershell
.\build_gpu\Release\atomos_cuda.exe --probe
.\build_gpu\Release\atomos_cuda.exe --out my_gpu_run
python tools/verify_run.py my_gpu_run
```

`my_gpu_run` must not already exist. Single-configuration Windows generators may put
the executable directly under `build_gpu`; the validation script resolves both forms.

## Implemented epoch

For each logical lane, read its immutable aperture dictionary and pre-epoch state:

```text
provided / recurrent / shift-XOR / shift-OR word producer
    -> ASA & valid & optional fringe
    -> NA
    -> POPCNT(selected & boundary)
    -> output = 0 on ANY intersection, otherwise selected

same frozen epoch:
    JK(q,j,k) -> next q
    north_bit XOR axis_bit XOR kinematic_bit -> encoded blend (when defined)
    OTAN2(delta_phase, delta_rho) - supplied_axis -> typed angle record
    R / W / P / S / F / V -> named comparison records

verify every proposed lane -> commit host word and JK banks together
```

One boundary intersection zeros the **whole selected 32-bit word**, not merely the
intersecting bit. An undefined OTAN2 record does not become a false numerical zero,
a new aperture mask, or an automatic J/K input. J/K is an explicit bit bank, one
stored bit per logical lane in K1. A bad required input or mismatch prevents commit.

The source ratio `atan(delta_phase / delta_rho)` is retained, including its zero-
denominator status. `directed_completion_1` is named separately. The GPU uses double
precision for these diagnostics and disables fused multiply-add contraction in the
build. No fast-math flag is enabled.

## Texture and laptop memory contract

The log-polar dictionary uses r_min=0.25, r_max=64, radial cell centers and periodic
angular nodes. `include/atomos/log_polar.hpp` provides the host coordinate compiler.
The GPU consumes exact packed predicates from this dictionary, not native code in
a texture cache. Texture residency remains hardware-managed.

Four immutable uint32 mask buffers are exposed through `cudaTextureObject_t` and
read with `tex1Dfetch<unsigned int>`. Linear and 8Ã—8 word-Morton layouts have the same
logical output order; radial bits occupy even Morton positions. Live state, lane
inputs and result buffers are separate global-memory resources.

The optional `--read texture-packed` path packs those same masks into one immutable
`uint4` texel (ASA, NA, boundary, fringe), with one `tex1Dfetch<uint4>` and the same
payload. `--cache max-l1` requests maximum-L1 preference, and `--block-size 64|128|256`
controls launch scheduling. The original defaults remain available and unchanged.

The measured default-fixture sweep found a 54.34 us median with
`--read texture --layout morton8 --block-size 64 --cache max-l1`, versus 81.25 us for
the original setting. `--read texture-packed --layout linear --block-size 128`
measured 55.14 us and attained the minimum 2,048 texture sectors for a complete
64 KiB streaming read. These timings belong to the archived pre-fold production
binary; that streaming study did not establish complete texture-cache residency.
The final native bulk-copy profile establishes measured retention separately and
includes warming/probing overhead. See the PDF and `docs/cache_sources.json` for
counter scope and limits. Reproduce the historical sweep with
`tools/benchmark_cache.py` and `tools/profile_cache.py`.

The default 128Ã—1024-cell case has 4,096 logical word lanes and **1,114,112 bytes of
device payload**, plus a 64 MiB planning margin. The default ceiling is 512 MiB,
with a 1,536 MiB device reserve and a limit of 70% of currently free VRAM. The driverâ€™s
reported byte counts govern admission; advertised 12 GB is not assumed to be free.

GPU `compute_ms` records kernel time only, excluding upload, download, CPU checking
and file output. CPU `compute_ms` covers CPU proposal creation, including its output
allocation. They are not matched end-to-end performance measurements.

## Scope within the total engine

K1 is a concrete implementation of the master **word-epoch** producer contract,
including both provided and recurrent words and the two literal shift variants.
Identity/genesis and retained-reference SHA-256 seals run on the host.

The masterâ€™s optional RK4/field producer, continuous lens function, capsule-to-cell
compiler, Klein-surface dynamics and programmable tape interpreter are not CUDA
backends in this package. `docs/coverage.csv` identifies those ports explicitly.
There is no implicit sensor feed, person-matching input, external trigger, privileged
loader or device-actuation interface. The supplied data are deterministic synthetic
word fixtures and declared numerical increments.

## CPU reproduction and file map

```sh
python tools/validate.py --proofs
python tools/verify_run.py results/demo_morton
python tools/seal_run.py results/demo_morton --verify
python tools/verify_package.py
python tools/verify_evidence.py
```

| Path | Contents |
|---|---|
| `cuda/kernel.cu` | Texture/global CUDA entry points, resource ownership and event timing |
| `include/atomos/core.hpp` | Shared operator definitions and invariant bank |
| `include/atomos/host.hpp` | Dictionary layout, fixture, independent bit oracle and commit checks |
| `include/atomos/log_polar.hpp` | Explicit host log-polar coordinate map |
| `src/main.cpp` | CLI, multi-epoch launcher, staged file output and final commit |
| `python/reference.py` | Independent fixture reconstruction and every-row conformance check |
| `python/provenance.py` | Symbolic genesis, full identity digest and run seal |
| `proofs/` | SMT-LIB obligations, solver runner and analytic proof notes |
| `tests/` | CPU and independent Python tests |
| `tools/validate.py` | Reproducible CPU/GPU evidence matrix |
| `AGENTS.md`, `CODEX_REVIEW.md` | Codex review contract and ready-to-use task |
| `results/` | Actual executed evidence, example run and explicit pending statuses |

The package manifest checks byte integrity, not author authentication. Changing a
file invalidates its original manifest entry. Toolkits, drivers, Z3 binaries, font
files and the original private PDF corpus are not bundled.


## Explicit cache-residency experiments

Optional standalone targets `atomos_cache_warm` and `atomos_cache_partition`
measure explicit warming and full-epoch retention. Enable them with
`ATOMOS_CACHE_WARM_EXPERIMENT=ON` and `ATOMOS_CACHE_PARTITION_EXPERIMENT=ON`
in a CUDA build. They are separate from the validated production read modes.

The partition experiment assigns immutable physical dictionary intervals to
cooperatively launched blocks, checks observed SM mappings, requests L2-only
traffic for nontexture input/output, and includes warming plus a final dictionary
reread in its event timing. Every full epoch is verified on the host before
commit. The `retain-only` and `word-only` controls deliberately omit part of the
computation: they report candidate verification as `not_run` and commit no state.
Their timings or successful checksums must not be presented as full K1 execution.

`tools/study_cache_partition.py` retains raw conformance receipts, shuffled timing
trials, cold Nsight Compute counters, source/binary hashes and an independent
receipt/geometry audit. A passed study means its execution and evidence checks
passed; it does not automatically mean cache residency passed. The evidence and
limits are in `results/residency_continuation/summary.json` and the updated PDF.
All warm/probe overhead is reported; no interface here guarantees pinned texture
cache lines across launches or arbitrary competing workloads.

The completed follow-up adds `atomos_cache_bulk`, built with
`ATOMOS_CACHE_BULK_EXPERIMENT=ON`. It uses native `cp.async.bulk` input/output
transfers, packed texture masks and a correctly rounded fixed-rotation constant
fold. It supports padded shapes, tails, every K1 producer/profile, and `--out`
canonical GPU traces for `tools/verify_run.py`. Its separate execution/allocation
profile records actual padded device memory and diagnostic buffers. Use
`tools/study_cache_bulk.py` and `tools/check_cache_bulk_edges.py` for the final
study; `docs/BULK_RESIDENCY.md` describes its synchronization and reproduction.
