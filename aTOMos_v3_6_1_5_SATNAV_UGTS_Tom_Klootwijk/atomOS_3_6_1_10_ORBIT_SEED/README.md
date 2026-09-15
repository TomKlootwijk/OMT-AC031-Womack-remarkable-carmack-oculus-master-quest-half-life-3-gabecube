# aTOMos 3.6.1.10 - optimized orbital seed kernel

This subversion applies the usable binary-word organization from the supplied phi/2pi/Fibonacci document to the existing seed kernel. A six-stage exact bit transpose replaces per-bit loops. The stored seed format, complete numeric bit patterns, two ASA/NA mask sets, synchronous JK, physical force parameters, and both UGTS layouts are preserved. All eight January/February seeds retain their original bytes.

The native worker now carries the declared time domain through transport version 3, checks propagation against the reference Earth surface, and reuses exact duplicate timestamps inside each batch. Legacy numeric transports 1 and 2 remain readable. Query preparation shares frame calculations and caches station and Boolean inputs by content. Each session uses a consistent seed/model snapshot; editing an input creates a new session and trace identity.

Run from this release directory:

```powershell
python -m pip install -r requirements.txt
python tools/orbit_scrub.py --worker bin/cpu/orbit_worker.exe
```

Open `http://127.0.0.1:3619`. The release is 3.6.1.10; compatible seed schema version remains 3.6.1.9. The examples still describe archived 2025 orbits. Exact bit packing does not remove floating-point propagation error, and the previous longer-horizon physical prediction failures remain recorded.

See [the audited source decisions](docs/PHI_SOURCE_AUDIT.md), [native transport](docs/ORBIT_NATIVE.md), [seed/session input](docs/ORBIT_INPUT.md), and [release evidence](validation_results.json). The editable full formalization is `docs/satnav.tex`; build it with `tools/build_pdf.py`. Reproduce the packing comparison with `tools/benchmark_seed_words.py --out NEW_BENCHMARK.json` and the complete frozen-epoch comparison with `tools/validate_optimization_replay.py --worker bin/cpu/orbit_worker.exe --out NEW_REPLAY`.

The following 3.6.1.9 capability and accuracy record is preserved baseline documentation. Fresh optimization measurements and checks are indexed separately above.

# aTOMos 3.6.1.9 — orbital seeds and timestamp queries

This subversion implements a compact physical satellite seed, native CPU/CUDA prediction, ground-station geometry, timeline scrubbing and two explicit ASA/NA sets feeding synchronous JK. The preserved parent is 3.6.1.8; its receiver pipeline and original UGTS contracts remain separate component profiles.

**Each complete example seed is 8,716–9,074 bytes.** The default codec stores numeric values as lossless **one-bit planes packed into uint64 machine words**, preserving every original bit. It contains the six-component initial state, force parameters, compact Sun/Moon and frame coefficients, both demonstration stations, time/query configuration, two mask sets, editable equations and provenance. No future target trajectory table, original observations, DE440 file or Internet lookup is needed for replay. A shared native/Python runtime is still required. Bit-plane packing does not replace binary64 propagation arithmetic; the ordinary canonical codec is slightly smaller for these examples and remains available.

## Run the timeline

From this release directory on Windows:

```powershell
python -m pip install -r requirements.txt
python tools/orbit_scrub.py --worker bin/cpu/orbit_worker.exe
```

Open `http://127.0.0.1:3619`. Choose a satellite and station, scrub the slider or enter an exact fractional second offset, and compute pass events or ordered feedback playback. The examples describe **January 2025 archived orbits**, not current positions. Delft and Singapore are explicit demonstration stations, not surveyed user hardware locations.

CPU queries use a bounded cache of canonical hourly checkpoints. Fractional query results never become checkpoints; scrubbing order does not change the physical state. A cold seek integrates forward or backward from the packed epoch. CUDA batches independently propagate queries from the epoch; they currently do not share the CPU checkpoint cache.

## Measured accuracy and functional tolerances

R2 selects a one-, three- or seven-day earlier training window by its maximum error on an earlier validation day, then fits through the seed cutoff. The selected January windows are three days for G05/C03/C06 and one day for Chandra. January 2–9 target positions are excluded from fitting; this benchmark was inspected during R1 development and is explicitly reused. Both backends evaluated 8,064 later positions. Values below are discrepancies from external orbit products, not certified absolute errors.

| Target | Complete seed | Maximum first 24 hours | Maximum seven days |
|---|---:|---:|---:|
| G05 — GPS MEO | 9,066 B | 1.057 m | 12.998 m |
| C03 — BeiDou GEO | 9,074 B | 5.304 m | 78.717 m |
| C06 — BeiDou IGSO | 9,073 B | 1.172 m | 8.084 m |
| Chandra — high elliptical | 8,716 B | 8.093 m | 25,635.951 m |

Chandra's final first-day sample is about 51.184 seconds before the nominal horizon. Its reference has no supplied absolute accuracy bound, and the seven-day discrepancy includes a large jump near day 3.5. A targeted independent numerical audit around that jump differs from native propagation by about 1.5 mm, so native integration does not explain that discrepancy. The independent January GEO providers differ by about 2.07 m RMS. Full curves, actual sample times, interval statistics and sampled threshold intervals are in [the accuracy report](results/orbit_accuracy_r2_cpu_verified/accuracy_summary.json). Separate February confirmation is documented in [the reference validation](docs/ORBIT_REFERENCE_VALIDATION.md).

The system's internal functional checks establish exact word semantics, lossless decoding, deterministic replay and measured numerical disagreements. They **do not define an intrinsic maximum physical orbit error**. The explicitly adopted 10 m engineering target passes all sampled first-day January positions for all four objects; it fails some longer intervals. Missing reference intervals cannot be labelled passing. See [the exact functional tolerances](docs/ORBIT_FUNCTIONAL_TOLERANCES.md) and [the measured acceptance report](results/orbit_r2_tolerance_verified.json).

The upgraded model includes all EGM96 gravity coefficients through degree/order 12, Sun/Moon third-body acceleration, a fitted radiation-pressure coefficient, cylindrical shadow, three fitted RTN accelerations, varying published EOP and Schwarzschild relativity. Higher harmonics, tides, detailed spacecraft attitude and future manoeuvres remain omitted. Exact equations appear in [ORBIT_PRECISION_DYNAMICS.md](docs/ORBIT_PRECISION_DYNAMICS.md) and [orbit.tex](docs/orbit.tex). R1 models and evidence are retained separately for comparison.

## Literal feedback and complete state

“Double vacuum, double set” means two independently supplied ASA/NA/boundary mask triples, applied in order. Each retains whole-word absorption. X/J/K equations compile to lookup tables and execute natively; an independent AST checks every word field. The resulting state selects the next query timestamp. Orbital force does not read the word as a hidden physical force.

Default inputs are `x=q|d`, `j=y&d`, `k=~d`; with identity mask sets they simplify to `q_next=d`. Geometry/age bits select 30-second or 300-second cadence. Changing JK to `j=1,k=0` changes the actual schedule while preserving physical states at common timestamps.

Both original 64-bit UGTS layouts remain addresses. Full GCRS/ECEF/ENU state, Up, velocity, GPST, tick phase/winding and provenance remain outside them. Angles are simultaneous geometric quantities without refraction or light-time correction. Literal source OTAN2 retains typed undefined cases.

## Commands and verification

Use new output paths:

```powershell
python tools/orbital_seed.py inspect --seed examples/orbit/seeds/C03.orbseed
python tools/orbital_seed.py query --seed examples/orbit/seeds/C03.orbseed --worker bin/cpu/orbit_worker.exe --station singapore_demo --time-s 12345.678 --out NEW_QUERY.json
python tools/orbital_seed.py predict --seed examples/orbit/seeds/G05.orbseed --worker bin/cpu/orbit_worker.exe --end-s 86400 --out NEW_RUN
python tools/verify_orbit_run.py --seed examples/orbit/seeds/G05.orbseed --worker bin/cpu/orbit_worker.exe --run NEW_RUN --out NEW_VERIFY.json
python tools/orbital_seed.py pack --input MY_EDITED_SEED.json --out MY_EDITED.orbseed
```

Use `bin/cuda/orbit_worker.exe` and `--backend cuda` for device execution. The included CUDA binary targets the tested SM120 device. [ORBIT_INPUT.md](docs/ORBIT_INPUT.md) gives the strict seed and query contract.

- [validation_results.json](validation_results.json) binds the final seed/model/binary and evidence hashes.
- [Packed replay and scrubbing](results/orbit_seed_r2_release_validation/summary.json): isolated bit-plane replay with original-release reads denied, active feedback and eight seven-day station/event searches. Refinement remains below the 0.05 s numerical acceptance threshold; this does not establish physical pass-time accuracy or prove every grazing event was found.
- [Native validation](results/orbit_native_r2_validation_final/summary.json): 1,040 CPU/CUDA comparisons, 256 complete word traces, cache eviction replay and actual Compute Sanitizer. Maximum CPU/CUDA position difference is about 43.2 micrometres. [Independent physical equations and numerical integration](results/orbit_physical_r2_audit_final/physical_audit.json) distinguish this from integration error.
- [Retained regression](results/retained_native_3619/summary.json): four CTests per backend, original SATNAV/SRK/CGK/live-worker checks and both texture/global GPU sanitizer paths. [Python log](results/python_tests_3619_r2_release.log): 139 tests passed.
- `bin/cpu` and `bin/cuda` contain five native programs. `examples/orbit/seeds` contains editable JSON and binary seeds; `web` contains the local interface; `docs` contains the complete editable formalization.
- [Reference provenance](source/orbit_data/README.md) records original products, hashes, chronology and separate data terms.

Earlier failed and superseded investigation folders are retained explicitly; only the reports indexed by `validation_results.json` describe the final release. The large audit archive includes reference data, earlier PDFs and detailed traces. Its size is separate from the 8.5–8.9 KiB seed and shared runtime.

To rebuild, use CMake/CTest as in the retained instructions below. R2 model construction additionally uses `requirements-orbit-construction.txt` and the cited DE440s file: `tools/build_precision_orbit_models.py --de440 PATH --out NEW_MODELS`. Build seeds with `tools/build_orbit_seeds.py --models NEW_MODELS --out NEW_DIRECTORY`. Run `tools/validate_orbit_seed.py --worker bin/cpu/orbit_worker.exe --out NEW_VALIDATION`. Build the editable PDF with `tools/build_pdf.py --engine PATH_TO_TECTONIC`.

## Historical parent instructions and evidence — 3.6.1.8

The following retained text concerns the earlier receiver pipeline and its dated measurements. Its position errors describe the remote receiver, not satellite forecast accuracy. New 3.6.1.9 binaries are under `bin/cpu` and `bin/cuda`.

### aTOMos 3.6.1.8 — live GPS receiver and literal state kernel

The kernel now computes real receiver positions as Internet RTCM observations
arrive. LIVE-GPS-L1-R1 adds the missing raw-data decoder, GPS satellite orbit/clock
model, atmospheric corrections and persistent native solver connection. It uses
the existing FP64 Givens-QR position/clock kernel on CPU or CUDA. The ASA/NA whole
word operation, JK recurrence, CGK geometry/mechanics, both UGTS keys and full
Up/time/clock values remain available as their named component profiles.

The demonstrated Internet source is Centipede's LIENSS reference receiver. These
solutions locate that remote station. This does not measure the laptop's location.
Each run starts from ECEF/clock zero; the advertised station position is never an
estimator input. The current profile is GPS L1 C/A single-point code positioning.

## Run live

Python with NumPy supports all supplied validation/retained kernel utilities.
Windows binaries are included in bin/cpu and bin/cuda.

```powershell
python tools/live_satnav.py --binary bin/cpu/satnav_stream.exe --url ntrip://caster.centipede.fr:2101/LIENSS --iono-nav source/live_data/BRDC00WRD_R_20262570000_01D_MN.rnx --seconds 180 --out results/my_live_run
```

Use the CUDA binary and add --backend cuda to execute the GPU path. Centipede
permits one NTRIP connection per public IP; run clients sequentially. The included
ionosphere header is a 14 September 2026 snapshot. For another day supply current
GPSA/B coefficients through --iono-nav, or omit it for the explicitly labelled
baseline approximation. RTCM ephemerides always come from the live stream itself.

The command creates raw bytes, reception timing, decoded message events, all
correction/solve passes, positions and prepared CSV files. Initial TOO_FEW epochs
are expected until enough ephemerides arrive. No partial or failed solve is
published as a new position. Output directories must be new.

## Replay real observations

```powershell
python tools/live_satnav.py --binary bin/cpu/satnav_stream.exe --rtcm source/live_data/centipede_lienss_20260914/capture.rtcm3 --reference-gpst 1473457283 --iono-nav source/live_data/BRDC00WRD_R_20262570000_01D_MN.rnx --out results/my_replay
python tools/live_satnav.py --binary bin/cpu/satnav_stream.exe --rinex-obs source/live_data/07590920.05o --nav source/live_data/07590920.05n --out results/my_rinex
```

## Review equations and evidence

- [Complete live input/runtime contract](docs/LIVE_INPUT.md)
- [GPS physical model and primary references](docs/LIVE_GNSS_MODEL.md)
- [RTCM decoding, transport and continuity](docs/LIVE_RTCM.md)
- [Live positions connected to the literal CGK state](docs/LIVE_HANDOFF.md)
- [Current execution evidence](results/validation_status.json)
- [Real datasets, independent RTKLIB and licenses](source/live_data/README.md)
- [Complete editable formalization](docs/satnav.tex)
- [Formal PDF](output/pdf/aTOMos_v3_6_1_8_Live_GPS_Receiver_Kernel_UGTS_Tom_Klootwijk.pdf)
- [Retained literal/coupled equations](docs/COUPLED_CONTRACT.md)

Real-data checks include a GPS orbit/clock oracle, raw RTCM field comparisons,
native versus independent Householder/NumPy solves, RTKLIB position comparisons
and timestamp proof that live fixes were emitted before capture ended. Different
observation weights produce different code-only positions; this is measured and
documented. The transmitted antenna reference point is a comparison coordinate,
not an independent survey truth. Formal variance and residual budgets are not
empirical accuracy guarantees.

## Rebuild and validate

Use a short build directory on Windows:

```powershell
cmake -S . -B C:/tmp/atomos3618_cpu -G "Visual Studio 17 2022" -A x64
cmake --build C:/tmp/atomos3618_cpu --config Release --parallel 2
ctest --test-dir C:/tmp/atomos3618_cpu -C Release --output-on-failure
cmake -S . -B C:/tmp/atomos3618_gpu128 -G "Visual Studio 17 2022" -A x64 -T cuda=12.8 -DSATNAV_ENABLE_CUDA=ON
python tools/validate_gpu.py --sanitizer --build-dir C:/tmp/atomos3618_gpu128
python -m unittest discover -s tests -p "test_*.py"
python tools/validate_live_native.py --binary bin/cpu/satnav_stream.exe --out results/my_native_check
bin/cpu/satnav.exe --input results/my_replay/prepared --out results/my_batch --backend cpu --verify
python tools/verify_run.py --input results/my_replay/prepared --run results/my_batch
python tools/live_handoff.py --live-run results/my_live_run --out results/my_live_cgk --satnav-binary bin/cpu/satnav.exe --coupled-binary bin/cpu/coupled_kernel.exe
```

The retained CGK component accepts editable equations through tools/run_coupled.ps1;
its schema and trace version remain3.6.1.7 to preserve replay compatibility. SRK
similarly retains its named component schema. Their historical validation is
identified as historical in the PDF and source/baseline_3_6_1_7_validation.json.
Original release directories remain unchanged.

The current implementation has no local RF tracking, RTK/PPP ambiguities,
multi-constellation clock states, Doppler velocity, moving-receiver field validation
or routing UI. A physical mobile satnav needs local observations and those desired
application layers. The Internet demonstration validates the real positioning
backend and its existing state-kernel connection.

Rebuild the PDF with python tools/build_pdf.py --engine PATH_TO_TECTONIC.
python tools/build_package.py --out NEW_RELEASE.zip regenerates and verifies
the delivered byte manifest; python tools/verify_package.py checks it afterward.
Native binaries require installed Visual C++/CUDA runtimes as applicable.
Optional PDF/plot/parser review dependencies are in requirements-review.txt;
they are not required by the live standard-library transport/model itself.
