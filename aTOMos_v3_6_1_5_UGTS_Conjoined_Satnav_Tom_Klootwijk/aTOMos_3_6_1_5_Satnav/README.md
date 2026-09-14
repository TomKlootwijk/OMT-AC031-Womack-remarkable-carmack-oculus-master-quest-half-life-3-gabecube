# aTOMos v3.6.1.5 × UGTS — Conjoined Satnav Kernel

**Tom Klootwijk · NL200678942 · 10-07-1990**

A receive-only positioning and geometric-query specialization joining the aTOMos
3.6.1 operator contract to the supplied UGTS-KC 3.6.2 SCLP mathematics. The satellite
navigation observation model is the new, explicitly named **SN1** specialization.
It is not an equation already supplied by UGTS or aTOMos.

## Delivered computation

The C++17 and CUDA paths perform the same sequence:

1. Apply the retained ASA → NA → POPCNT → whole-word rule to a 32-slot observation mask.
2. Estimate receiver ECEF x/y/z and receiver clock bias in **metres** from corrected code observations.
3. Use weighted nonlinear least squares with streaming Givens QR in FP64.
4. Compute postfit RMS, normalized residual sum and formal diagonal uncertainty.
5. Convert the solution to a fixed local ENU frame; retain Up separately.
6. Evaluate UGTS cone/sphere point relations, the local log-polar chart and both 64-bit codecs.
7. Compute the source OTAN2 ratio and the separately named directed residual from consecutive local chart samples.
8. Return the explicit per-epoch JK/blend values and all numerical/status fields in one CSV record.

The GPU source includes global-load and integer-texture-load variants, followed by a
second GPU enrichment kernel. FP64 texture values are read as `int2` and rebuilt bit
for bit; no float32 ECEF reduction occurs. Batches are chunked using actual free VRAM.
The selected code is a positioning postprocessor, not a radio receiver, route planner,
flight controller or external actuation interface.

## Input contract — prepared observations

The input uses two simple CSV files, described in `docs/INPUT.md` and demonstrated in
`examples/clean`. Each observation supplies a satellite position at emission time
**already expressed in reception-time ECEF**, a corrected code pseudorange, and a
positive measurement sigma. Satellite clock, atmospheric/instrument terms and
Earth-rotation frame handling are upstream preparation, not silently set to zero for
real observations. The synthetic fixtures generate data consistent with this model.

Use one receiver, one common GNSS time scale and one receiver-clock-bias family per
batch, with 0..32 contiguous slots per epoch. Different constellations with unresolved
inter-system offsets require an expanded estimator and are not silently treated as
one clock. Full GPST millisecond ticks remain separate from the 14-bit modular key.
No ephemeris decoder, RINEX reader, SDR sample processing or carrier-ambiguity engine
is included. Existing processors can export the prepared CSV interface directly.

## CPU build and run

CMake 3.24+, a C++17 compiler; no third-party C++ libraries are needed.

```sh
cmake -S . -B build_cpu -DCMAKE_BUILD_TYPE=Release
cmake --build build_cpu --config Release --parallel 2
ctest --test-dir build_cpu -C Release --output-on-failure
./build_cpu/atomos_satnav --epochs examples/clean/epochs.csv --observations examples/clean/observations.csv --out clean_run.csv
```

Windows multi-configuration builds put the executable at
`build_cpu/Release/atomos_satnav.exe`. An output file must not already exist.

## RTX 5070 Ti Laptop CUDA build

Use CUDA Toolkit **12.8 or newer**, an installed compatible NVIDIA driver, CMake,
and a host compiler supported by that toolkit. The default CUDA targets are native
`sm_120` and virtual `compute_120`.

```sh
cmake -S . -B build_gpu -DAO_ENABLE_CUDA=ON -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES="120-real;120-virtual"
cmake --build build_gpu --config Release --parallel 2
./build_gpu/atomos_satnav --probe
./build_gpu/atomos_satnav --epochs examples/clean/epochs.csv --observations examples/clean/observations.csv --out gpu_global.csv --backend cuda --read global
./build_gpu/atomos_satnav --epochs examples/clean/epochs.csv --observations examples/clean/observations.csv --out gpu_texture.csv --backend cuda --read texture
```

On Windows use `build_gpu/Release/atomos_satnav.exe` from the supported compiler
prompt. `--chunk` (default 8192) and `--budget-mib` (default 1024) are explicit
allocation parameters. The uploader also uses no more than 60% of currently free
memory, then checks actual allocations. A 12 GB device does not require filling all
VRAM to solve a small batch. The probe reports the actual GPU, free/total bytes,
compute capability, driver/runtime versions and texture limit.

CUDA source is included; **CUDA compilation and GPU execution were not run in the
preparation environment**, which had no nvcc or accessible NVIDIA GPU. The package
contains no precompiled GPU binary. CPU compilation, tests and independent oracle
checks were executed. `results/validation_status.json` records the actual categories.

## Independent verification and device matrix

Python 3.10+ and NumPy are required for the independent positioning oracle. The pure
UGTS helper tests use only the Python standard library.

```sh
python -m unittest discover -s tests -p test_python.py -v
python python/verify_result.py examples/clean clean_run.csv
python tools/validate.py
python tools/validate.py --gpu
python tools/validate.py --gpu --memcheck
```

The GPU review runs **global/texture × chunks 1/7/8192 × two fixtures**, verifies each
against the independent NumPy `lstsq` equations, and compares GPU enrichment against
the CPU including chunk boundaries. `--memcheck` additionally invokes NVIDIA Compute
Sanitizer. Missing requested tools produce an explicit unavailable result, not a pass.

Executed preparation results: **26 C++ groups / 217,707 assertions**, **15 Python
unit tests**, and **320 independent positioning-epoch comparisons / 4,462 checks**.
Three deliberately invalid/unsolvable epochs return distinct expected states; 317
have solutions. CPU CTest also passed with AddressSanitizer and UBSan.

## Interpretation and profiles

The default local anchor is 52° N, 5° E, ellipsoid height 20 m. Supply another anchor
with `--anchor-lat`, `--anchor-lon` and `--anchor-height`. `--axis-deg` supplies the
OTAN2 reference orientation. Other local region/chart example parameters are ordinary
editable values in `make_geo()` in `include/atomos/math.hpp`; their role and units are
listed in `docs/CONTRACT.md`.

The SCLP chart uses theta for spatial azimuth and phi for the independent hinge.
Neither field is silently merged with the receiver clock or the third spatial
coordinate. ECEF/ENU height is not encoded into the four-field key. The 64-bit key
addresses a quantized tuple; it is not an exact full navigation state or a lossless
float-vector compression scheme.

The full position, observation sigma, numerical status and absolute timestamp remain
available alongside the packed keys. There is no runtime hash-chain or provenance
service. Source equations and the new SN1 additions are distinguished in the PDF,
with concise technical references rather than a separate historical ledger.

## Package entry points

`include/atomos/nav.hpp`: shared WLS, ASA and conjoined enrichment.
`include/atomos/math.hpp`: geometry, coordinates, codecs and typed arithmetic.
`cuda/backend.cu`: two observation-read paths and fused GPU enrichment.
`python/sclp.py`: independent finite UGTS helpers, including grammar/constraint tests.
`python/make_fixture.py`: deterministic geometric observation generator.
`docs/conjoined.tex`: editable formalization.

To rebuild the PDF: `sh tools/build_pdf.sh` (LaTeX packages in the preamble are required).
