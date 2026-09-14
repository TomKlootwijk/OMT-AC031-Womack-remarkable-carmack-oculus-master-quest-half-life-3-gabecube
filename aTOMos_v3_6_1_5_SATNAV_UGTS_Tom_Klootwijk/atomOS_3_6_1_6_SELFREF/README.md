# aTOMos 3.6.1.6 - literal self-referential kernel

This subversion completes the existing ASA/NA + JK primitives with persistent
state feedback. Supply the actual Boolean equations in
[examples/self_reference/equations.json](examples/self_reference/equations.json).
The compiler creates exact truth tables, the CPU/CUDA kernel emits every state
transition, and an independent expression-tree reference replays every field.

The complete recurrence and input grammar are in
[docs/SELF_REFERENCE.md](docs/SELF_REFERENCE.md). The rebuilt formalization is
[the 3.6.1.6 PDF](output/pdf/aTOMos_v3_6_1_6_Literal_Self_Referential_Kernel_UGTS_Tom_Klootwijk.pdf),
with editable sources in `docs/satnav.tex` and `docs/self_reference.tex`.

On this Windows machine, the delivered binaries can run immediately:

```powershell
./tools/run_self_reference.ps1 -Backend cpu
./tools/run_self_reference.ps1 -Backend cuda
```

Use `-InputFile PATH` for your own equations. Each run creates a new results
directory and independently verifies the complete native trace. The binaries
use the installed Visual C++ runtime; CUDA also uses the installed CUDA runtime
and NVIDIA driver.

```sh
cmake -S . -B build_cpu
cmake --build build_cpu --config Release --parallel 2
ctest --test-dir build_cpu -C Release --output-on-failure
python tools/self_reference.py --input examples/self_reference/equations.json --out results/selfref_local --binary build_cpu/Release/self_reference.exe --backend cpu
```

Single-configuration systems use `build_cpu/self_reference`. To run CUDA, build
with `-DSATNAV_ENABLE_CUDA=ON` and select `--backend cuda`. JSON equations are
editable without recompiling native code. Fixed points, cycles and no repeat
within the requested steps are distinct results.

For this long Windows workspace path, native rebuilds used short build folders:
`cmake -S . -B C:/tmp/atomos3616_cpu -G "Visual Studio 17 2022" -A x64`.
The CUDA configure additionally used `-T cuda=12.8 -DSATNAV_ENABLE_CUDA=ON` and
`-B C:/tmp/atomos3616_gpu128`. The installed default CUDA 12.9 toolset selection
was unusable here; explicit 12.8 built and passed on the actual device.

Current execution evidence is in `results/validation_status.json`. The preserved
3.6.1.5 preparation logs are under `results_3_6_1_5/`. The original release folder
remains beside this one. SATNAV numerical behavior, literal OTAN2 and both UGTS
key codecs are retained. The feedback bindings are explicit definitions of SRK-R1.

Rebuild the PDF with `python tools/build_pdf.py` (Tectonic or latexmk), then check
the delivered source/artifact bytes with `python tools/verify_package.py`.

## Retained SATNAV-R1 profile and prior preparation record

The following describes the inherited 3.6.1.5 preparation. Its historical
execution statements are superseded by this subversion's current results above.
**Concept author:** Tom Klootwijk · NL200678942 · 10-07-1990  
**Base:** aTOMos 3.6.1 / M2 contracts  
**Geometric source:** UGTS-KC 3.6.2 SCLP  
**Specialization:** SATNAV-R1, passive corrected-code receiver positioning

This package contains actual CUDA source, a C++17 CPU implementation, an independent
Python Householder reference, the UGTS adapter, deterministic examples, tests and the
editable PDF source. The GPU computes batches of independent receiver-position and
clock-bias solutions from **already decoded and corrected GNSS observations**. It
is not an RF frontend, a navigation-message decoder or a replacement for a GNSS
antenna/receiver. It does not transmit, steer an antenna, or control a vehicle.

## What runs where

`include/satnav_core.hpp` contains the shared numerical implementation: ASA/NA
whole-word selection, FP64 range residuals, iterative weighted Givens QR, convergence
and formal covariance. `cuda/backend.cu` launches one GPU thread per independent
epoch and supports **texture** and **global** input reads. Structure-of-arrays storage
makes the same observation field contiguous across epoch threads. FP64 texture
values use exact `int2` bit transport, never floating texture interpolation.

`tools/ugts_handoff.py` adds the UGTS sequence: support -> compatibility -> guard ->
verified event -> observation transition -> lineage. It preserves the 20/18/14/12
contiguous and MSB-round-robin Morton codecs, full time/winding, local log coordinates,
Up separately, literal OTAN2 diagnostics and the original unquantized receiver state.
The two-sphere support and error bounds in the demo are declared model choices, not
an independently established positioning protection level.

## Build and run the CPU reference

Use CMake 3.24+, a C++17 compiler and Python 3.10+.

```sh
cmake -S . -B build_cpu -DCMAKE_BUILD_TYPE=Release
cmake --build build_cpu --config Release --parallel 2
ctest --test-dir build_cpu -C Release --output-on-failure
./build_cpu/satnav --input examples/demo --out run_cpu --backend cpu --verify
python tools/verify_run.py --input examples/demo --run run_cpu
python tools/ugts_handoff.py --input examples/demo --run run_cpu
python -m unittest discover -s tests -p "test_*.py" -v
```

On a Windows multi-configuration build, the executable is usually
`build_cpu/Release/satnav.exe`. Commands must run from the package root. Each run
uses a **new output directory**; existing evidence is not silently replaced.

## Build and validate on the requested RTX laptop

The build targets `sm_120` plus `compute_120` PTX. Use CUDA Toolkit 12.8 or later,
a CUDA-supported host compiler, and a compatible installed NVIDIA driver. On Windows,
run from an x64 compiler developer terminal so CMake can locate the host compiler.

```sh
cmake -S . -B build_gpu -DSATNAV_ENABLE_CUDA=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build_gpu --config Release --parallel 2
./build_gpu/satnav --probe
./build_gpu/satnav --input examples/demo --out run_gpu --backend cuda --read texture --verify
python tools/verify_run.py --input examples/demo --run run_gpu
```

The automated laptop review is:

```sh
python tools/validate_gpu.py --sanitizer
```

It builds CUDA, records the actual device, runs both texture/global paths, compares
with the shared CPU path **and** the independent Python solution, and invokes Compute
Sanitizer when requested. Missing nvcc or a requested missing sanitizer returns an
explicit unavailable result (exit 3), not a passing GPU result.

**Preparation status:** CPU compiled and executed; 105,559 C++ checks, 18 Python tests,
11 CLI cases, CPU sanitizer checks and 4,828 independent comparisons passed. No nvcc
or NVIDIA GPU was available in the preparation environment. CUDA compilation,
on-device execution, Windows compilation and GPU timing are therefore **not_run**.
The ZIP contains CUDA source, not a prevalidated cubin or Windows executable.

## Input model: read this before using receiver data

`docs/INPUT.md` defines the two CSV files and correction signs. Observations must
already have satellite coordinates at emission expressed in reception-time ECEF
axes, matching code epochs, corrected satellite clocks and other selected delays.
The kernel adds exactly `add_correction_m` once:

    corrected_code = code_m + add_correction_m
    predicted_code = distance(receiver, satellite_rx_axes) + receiver_clock_bias_m

The current estimator has **one** receiver-clock unknown. Use one compatible clock
system, or perform and document an upstream inter-system-bias alignment. Do not mix
uncorrected raw constellations and call their shared bias solved. No RINEX/SP3/nav
message parser, ambiguity resolution, carrier-phase RTK/PPP, Doppler velocity solver
or full GNSS integrity-monitoring standard is implemented.

The new geometry matrix `H` is an explicit satnav-specific binding of the earlier
open matrix role. It is not secretly the original source's unprovided physical
beamforming/eigenmatrix. OTAN2 measures a local log-chart motion slope, not latitude,
longitude, azimuth or the receiver's geographic heading.

## Results and reproducibility

The supplied example has 256 artificial epochs with known truth. It deliberately
includes too few satellites, whole-word absorption, rank-deficient geometry, a gross
outlier, exactly four observations and all 32 channel positions. 253 epochs converge;
3 retain explicit no-solution statuses. Of the converged results, 251 meet the chosen
residual budget, one triggers a residual alert and one has no redundancy. The noisy
fixture's position RMSE is about 1.602 m; that is a synthetic test outcome, not a
real-world accuracy claim. The formal covariance is tied to the supplied sigma model.

Generate a larger independent batch for an actual laptop timing comparison:

```sh
python tools/generate_demo.py --out examples/large_local --epochs 16384
```

The GPU chunks within `--budget-mib` (default 512), actual free VRAM and
`--reserve-mib` (default 1536), with a 64 MiB planning margin. It does not allocate
12 GB merely to fill the device. Kernel-only timing excludes CSV parsing, upload,
download, allocation and post-processing; small batches may favor the CPU.

## Source fidelity

The UGTS source has 19 physical PDF pages, with 16 numbered main/appendix pages.
Its earlier referenced software ZIP was not supplied. This package implements the
source-defined contracts anew and does not inherit its reported 153 passing tests.
The base aTOMos 3.6.1 material was available as this project's specification/code
history, not as a mounted prior release archive. `source/manifest.json` records that.

`docs/SOURCE_DECISIONS.md` identifies the one printed jitter-interval equality that
must remain distinct, the planar chart versus 3D receiver state, source versus
reflective topology, and physical observation versus synthetic fixture boundaries.
The original 64-bit golden key pair is reproduced in the new codec tests.

## Rebuild the formalization and verify delivery bytes

```sh
sh tools/build_pdf.sh
python tools/verify_package.py
```

The PDF build needs LaTeX and the packages in its preamble. The unsigned manifest
checks delivered bytes, not authorship or authenticity. Source font files, private
raw prior transcripts, proprietary drivers and third-party binaries are not bundled.

