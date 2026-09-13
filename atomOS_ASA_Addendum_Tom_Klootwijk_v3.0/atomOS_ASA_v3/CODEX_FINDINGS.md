# Kernel, cache and execution findings — 13 September 2026

## Fresh residency delivery follow-up

The latest report is [the kernel residency PDF](output/pdf/atomOS_ASA_kernel_residency_validation.pdf), with [final status and hashes](local_validation/20260913_residency_delivery/delivery_status.json). Evidence in the sections below under `20260913_kernel_review` remains historical; the follow-up lives under `local_validation/20260913_residency_delivery`.

The bounded source review found no new production core/CUDA correctness defect. Existing numeric definitions, scheduling defaults, launch geometry and device binary remain unchanged. Fresh CPU/CUDA builds and CTest, all 16 requested Compute Sanitizer invocations and the 72 retained focused independent-oracle cases passed. The post-repair CTest run includes 47 Python tests. Host ASan/UBSan remains explicitly unavailable with MSVC.

**Repair:** `scripts/benchmark_cache.py` previously accepted a profile without proving a single profiler pass, expected kernel or consistent capture identity. New mocked regressions reproduced those false acceptances (eight tests, 12 failures before the fix; eight tests pass afterward). The parser now requires exactly one pass, one nonempty ID/process/kernel/context/stream identity and the actual `asa_texture_kernel`. It checks matching executable digests before and after every process invocation. Logs and the preliminary test-import error are recorded in `benchmark_regressions/`. Existing metric/summary fields remain compatible.

The repaired fresh benchmark used five timing runs and three cold single-pass profiles per condition. Morton8 natural/locality texture misses were 53,662 / 10,470 (80.49% fewer); warmed texture means were 0.060306 / 0.029486 ms (51.11% lower). Both layouts/orders retained exact samples/results and passed the independent oracle. These are comparisons between already implemented options, not a new speedup over the prior optimized binary. Locality host sorting/restoration medians were 2.3476 / 2.1170 ms; those costs exceed the savings from a single kernel launch.

All 84 fresh residency observations passed the one-pass check. Warm normal L1/TEX hit rate was 71.2286%, with 10,463 miss sectors. Warm L2 miss counters were zero for both paths/policies, each measured independently. Texture evict-last remained zero; only the global path showed persistence tagging. Normal L2 policy remains the default. No full L1/TEX residence or permanent pinning is claimed.

**New diagnostic:** `scripts/trace_texture_footprint.cpp` records host-side table-sector requests around unchanged `evaluate`, validating traced results against CPU output. Across 65,536 samples, unique requested table footprints are 217,280 bytes linear and 205,472 bytes Morton. Natural/locality maximum block footprints are 23,008 / 8,000 bytes linear and 19,648 / 9,216 bytes Morton. Locality packs table-free rejected samples into the tail (44 of 128 blocks request tables), so the zero median across all blocks is not presented as a representative active-block footprint. Full allocations total 532 KiB. This model excludes hardware mapping, concurrent blocks and non-table traffic; it is not cache occupancy or a miss prediction.

Fresh `native/` logs confirm the same sm_120 executable SHA-256 `81413c8efe273b3383f9ba4028766bbbaef467b52f30c5dd3c730425f211e32a`. Both kernels use 36 registers and report zero local/stack/static shared bytes. Texture SASS contains eight static TLD, two LDG and eight STG instructions, with no LDL/STL. A separate fresh capacity capture reports one pass, an 8 KiB shared partition and zero application shared memory. The nominal 120 KiB L1/TEX budget remains an inference, not occupied bytes. Actual source/toolchain and command records are retained. The collection helper's initial import error and tracer's initial command-path error were corrected and recorded; all completed GPU/oracle evidence is retained. Original bundled result hashes and the original addendum PDF are preserved.

## Earlier kernel review

The final Windows build executes the native CUDA texture and global-load kernels on the RTX 5070 Ti Laptop GPU, CC 12.0. CPU comparisons, the independent Python oracle, CLI integration and the requested Compute Sanitizer runs passed. Spatial sample ordering improves the measured texture-cache behavior and warmed kernel time for the tested workload. The selected CUDA defaults are locality ordering, 512 threads per block and normal L2 policy.

The optional image-persistence policy was accepted by the CUDA API and read back, but it produced no demonstrated texture-path persistence benefit. Ordinary warm execution already showed zero L2 read misses in the measured captures. This is a user-mode CUDA application using the installed NVIDIA driver; it is not a custom CPU ring-0 driver or a program pinned inside the texture cache. The [privilege contract](docs/PRIVILEGE_CONTRACT.md) remains unchanged.

## Authoritative final evidence

All evidence paths below are relative to `local_validation/20260913_kernel_review/`. **`final_gpu` and `final_cpu` supersede earlier successful runs as final-source acceptance records.** Earlier successes, failures and unavailable steps remain in their original directories.

| Final record | Executed outcome |
|---|---|
| [final_gpu/status.json](local_validation/20260913_kernel_review/final_gpu/status.json) | Native configure/build, five CTest targets, device query and 16 sanitizer invocations passed. |
| [final_cpu/status.json](local_validation/20260913_kernel_review/final_cpu/status.json) | CPU configure/build and three CTest targets passed. |
| [final_records/core_details.log](local_validation/20260913_kernel_review/final_records/core_details.log) | 33 groups / 74,982 assertions passed. |
| [final_records/python_details.log](local_validation/20260913_kernel_review/final_records/python_details.log) | 42 Python tests passed. |
| CLI integration in final CTest | 58 CPU and 76 GPU scenarios passed, including clean rejections and exact sample/result comparisons. |
| [final_records/records_evidence.json](local_validation/20260913_kernel_review/final_records/records_evidence.json) | Independent oracle: 65,536 samples in each layout and 72 focused cases / 28,656 samples; maximum error 0 throughout. Default-layout result records are byte-identical. All 30 bundled `results/` files still match the original manifest. |
| [final_records/retained_boundaries.log](local_validation/20260913_kernel_review/final_records/retained_boundaries.log) | Also passed three stream-completion workloads of 65,536 samples each: normal destruction, exception unwinding and explicit close. These additional 196,608 sample evaluations have CPU comparison, not separate Python-oracle records. |
| [cache_final_512/benchmark.json](local_validation/20260913_kernel_review/cache_final_512/benchmark.json) | Controlled natural/locality comparison, both layouts, warmed timings and cold texture-specific counters, with exact outputs and independent oracle verification. |
| [residency_final/residency_probe.json](local_validation/20260913_kernel_review/residency_final/residency_probe.json) | 84 accepted one-pass captures across cold/warm state, normal/persist-image policy and seven counter groups. Every retained result passed the oracle and exact sample/result comparison. |

Memcheck, initcheck and synccheck each reported zero errors; racecheck reported zero hazards, errors and warnings. Each tool ran natural/512, locality/512 with repeated launches, locality/512 with `persist-image`, and the focused executable. Production sanitizer batches contain 4,097 samples. The focused executable includes the 72 configuration/order cases plus all three stream-completion workloads.

The final retained executable, cache benchmark and residency probe share SHA-256 `81413c8efe273b3383f9ba4028766bbbaef467b52f30c5dd3c730425f211e32a`. Native sm_120 code, PTX and TLD instructions are retained in the `final_records/native_*` logs. This digest identifies the measured binary; it is not access authority.

Device/toolchain: CUDA 12.8.61, MSVC 19.44.35221, CMake 4.3.2, Python 3.13.11, Compute Sanitizer and Nsight Compute 2025.1.0.0. The final device query reports 12,820,480,000 total bytes and 11,561,598,976 free bytes at that observation, runtime API 12080 and driver API 13010. Free memory is an observed state, not nominal capacity.

## Repairs and implementation changes

| Finding or change | Resolution and regression coverage |
|---|---|
| Empty CUDA batches claimed device execution despite skipping launches. | Metadata now records no kernel execution, block size 0, zero measured iterations and no policy activation. CLI regressions cover empty/default/explicit configurations. |
| Windows tool discovery found a Compute Sanitizer batch wrapper that failed to launch as a bare executable. | `scripts/validate.py` resolves the same toolkit's native executable. Launch failures now leave an unavailable status and log. |
| MSVC host ASan/UBSan could silently run without the requested instrumentation. | CMake rejects that unsupported configuration; the validator returns exit 2/unavailable. The actual rejection is retained in `host_sanitizer_unavailable/`. |
| Python verification could be omitted; negative scenarios could count a crash as a successful rejection. | Require and pin Python >=3.10, require clean exit 1, reject output creation on invalid inputs, and verify existing sealed outputs remain unchanged. |
| CUDA object and static runtime used conflicting MSVC CRT libraries. | Object/library directives identified `/MD` versus `LIBCMT`. CUDA targets now use the matching static CRT; final builds have no LNK4098 warning. CUDA host floating-point settings are explicit. |
| Random sample order caused scattered table accesses. | Added a deterministic host-side locality schedule and checked restoration to original order. Both layouts, both orders, nonfinite/extreme coordinates and malformed restore permutations are covered. Extra scheduling storage is on the host; device payload allocations are unchanged. |
| Launch geometry and single-launch timing limited controlled comparisons. | Added bounded block-size, warmup and repetition options; metadata records actual launch counts and mean/minimum CUDA event times. Integration compares exact outputs across supported block sizes and repetition settings. |
| Owned stream destruction alone did not guarantee pending work had completed before surrounding resources could leave scope. | Stream cleanup now synchronizes before destruction. Explicit close checks errors and is idempotent; destruction is a nonthrowing fallback. Three actual-device scope-completion regressions query the completion event without waiting afterward and compare all outputs with CPU. |
| Persistence configuration could be mistaken for measured residence. | Added opt-in image-only L2 policy, device-capability checks, accepted-limit queries, stream-window readback, and completion/reset/restoration ordering. Its activity is measured separately from whether configuration succeeded. |
| Aggregate cache percentages, locale parsing and replay could mislead the report. | Benchmark parsing validates finite counts, percentages, metric sets and exact outputs, with separate percentage/count parsing. Residency probing requires one pass, separates incompatible L2 counters into independent captures, and never derives a same-launch L2 hit percentage from them. |

The actual kernels and resource wrappers are shared through `cuda/asa_device.cuh`; production and focused tests use those same kernels. The free-memory admission predicate retains the half-free rule and 512 MiB reserve, with deterministic boundary regressions. `include/asa/core.hpp` and `python/reference.py` have no changes. Operator order, numerical profile, Morton bit assignment, logical cell keys, read-only texture ownership and the 2e-6 comparison tolerance are preserved.

## Measured cache and timing behavior

The final controlled benchmark uses 65,536 identical samples, 512 threads per block, five warmups and 30 timed launches per path. It takes five unprofiled process runs per condition, alternating natural/locality order, before three cold profiler captures per condition. Values below are medians across those runs; kernel entries are medians of each process's mean CUDA event time.

| Layout / order | Texture-load hit rate | Cold texture miss sectors | Warm texture kernel, ms | Warm global kernel, ms |
|---|---:|---:|---:|---:|
| Linear / natural | 62.89% | 62,360 | 0.060474 | 0.060366 |
| Linear / locality | 85.27% | 10,035 | 0.029629 | 0.029949 |
| Morton8 / natural | 67.96% | 53,652 | 0.060709 | 0.061215 |
| Morton8 / locality | 71.21% | 10,470 | 0.029649 | 0.029375 |

For Morton8, locality cut observed texture miss sectors by about 80.5% and the warmed texture-kernel mean by about half. Total texture sectors also fell from 167,449 to 36,366; requests fell from 32,743 to 11,168. More coalescing can reduce the absolute number of hits while improving access efficiency, so a hit percentage alone is not the decision criterion. Linear/locality achieved a higher hit percentage than Morton/locality, with similar kernel time and more requested sectors; no universal layout winner is claimed.

Host work remains material. Morton/locality median sorting was 2.3351 ms and restoration was 2.0705 ms; restoration includes both downloaded CUDA paths. Those costs exceed the time saved by a single texture launch. Whole-process medians were 1,504.59 ms for Morton/natural and 1,570.27 ms for Morton/locality. These process measurements include context/setup, fixture generation, CPU comparisons, transfers, 70 kernel launches including warmups, synchronization and file output. They do not demonstrate a whole-application speedup or represent single-batch kernel latency. A reusable engine integration would need its own end-to-end measurements and scheduling-cost amortization.

## L2 reuse and persistence observations

The device reports 36 MiB of L2, a 22.5 MiB maximum persistence reservation and a 128 MiB maximum access-policy window. For the optional image policy, the application requested 524,288 bytes; CUDA reported an accepted reservation of **2,359,296 bytes**, while the read-back image window remained **524,288 bytes**. Readback showed `hitProp=Persisting`, `missProp=Normal` and `hitRatio=1`. The ratio is a policy parameter, not a measured 100% hit rate. The matte and lens allocations are outside that image window. [CUDA L2 access-management semantics](https://docs.nvidia.com/cuda/archive/12.8.0/cuda-c-programming-guide/index.html#device-memory-l2-access-management)

All 84 final residency captures reported one profiler pass. Cold captures flush caches; warm captures disable profiler flushing after five application warmups. Texture L1 hit/miss counters fit one capture; each L2 counter is captured independently because combined L2 metrics required multiple passes. No L2 percentage is computed by combining separate launches. This avoids replay changing the cache state being assessed. [NVIDIA cache/replay guidance](https://docs.nvidia.com/nsight-compute/ProfilingGuide/#cache-control)

- For both kernels and both policies, independently captured warm L2 read misses were 0 in all three repetitions, compared with 39,189 cold misses. Separate warm hit captures were positive, approximately 43,234 sectors for the texture kernel and 43,238 for the global kernel with normal policy. This supports ordinary warm data reuse for the measured trace.
- The texture kernel's L2 evict-last counter remained 0 with either policy, cold or warm. Its texture-load hit rate remained approximately 71.2%; enabling image persistence did not improve it.
- The global kernel did show the policy's priority effect: evict-last median 8,230 cold and 8,225 warm under persist-image, versus 0 under normal policy. This demonstrates a tagging effect on that path, not a texture-residency or speed guarantee.

L2 counters refer to reads from the shared L1/TEX source unit; they do not identify the residence of particular table lines. The observed policy effect differs between the texture and global paths. **No texture persistence benefit was demonstrated, so normal L2 policy remains the default.** Data is retained in device allocations across the repeated launches, not across separate process exits, and no permanent cache-line pinning is established.

## Cache capacity: measurement versus inference

[l1_capacity.log](local_validation/20260913_kernel_review/l1_capacity.log) is a one-pass capture of the final texture kernel at block size 512. It reports an 8 KiB shared-memory partition, 1 KiB driver shared memory per block and zero static/dynamic application shared memory. NVIDIA documents 128 KiB of combined data cache/shared memory for CC 12.x. Subtracting the measured 8 KiB partition gives a **nominal 120 KiB remaining L1/TEX allocation budget per SM**. This is an inference about partition capacity, not measured cache occupancy, a count of resident table bytes or a pinning guarantee. The 1 KiB per-block driver allocation is not an additional amount to subtract again from that inferred cache budget. [NVIDIA CC 12.x capacity table](https://docs.nvidia.com/cuda/archive/13.1.1/cuda-programming-guide/05-appendices/compute-capabilities.html)

## Earlier attempts and remaining limits

The first GPU configuration selected stale CUDA 12.9 Visual Studio integration with an empty toolkit path. Explicit selection of installed CUDA 12.8 fixed it. An overly long build path reproduced an MSBuild FileTracker error; the short `b128` directory fixed that. No host-compiler override, driver-protection change or global toolkit repair was needed.

`gpu_baseline` failed configuration. `gpu_pre_fixes` reached initial CTest but its sanitizer launcher failed before writing a final status. `gpu_verified` caught an incorrect expected test cell caused by assuming a binary64 midpoint was exactly 2; the regression was corrected to use an exactly represented sample. Older `accepted_*`, `optimized_*` and `residency_gpu` runs describe earlier revisions and are superseded by `final_gpu`/`final_cpu`. `residency_initial` was correctly rejected when a combined L2 group required four profiler passes; a hit/miss pair needed three. Those failed captures were preserved and excluded from final residency claims. MSVC host ASan/UBSan remains unavailable, not passed.

Validation covers the declared synthetic numerical operator on the measured laptop, not physical lens calibration, every possible input or a formal proof. Extreme LUT-size cases use identity coefficients; nonzero interpolation is covered at the default LUT size. Low-VRAM rejection boundaries use simulated free-byte values rather than deliberately exhausting the laptop. Racecheck's clean shared-memory result is not a proof of arbitrary global/texture coherence. The implemented tables are read-only during execution and output allocations are separate. Explicit stream/L2 close checks CUDA errors; buffer, texture and event destructors and unwinding fallbacks do not propagate destruction errors.

The original package manifest, delivered PDF and all 30 bundled result files are unchanged. The local source and new reports document this corrected and extended implementation without reissuing the original edition's manifest.
