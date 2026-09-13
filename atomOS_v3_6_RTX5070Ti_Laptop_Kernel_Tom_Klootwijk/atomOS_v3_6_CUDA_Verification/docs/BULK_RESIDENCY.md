# Native bulk-copy texture residency profile

Concept author: Tom Klootwijk. This is the same K1 word epoch and diagnostic
contract, with a different device data-transfer schedule. The standalone
`atomos_cache_bulk` executable exposes the complete measured schedule. It is an
optional target; ordinary texture/global launch defaults remain available.

## What runs

One cooperative 512-thread block per SM owns a disjoint, 64-texel-aligned interval
of the immutable packed mask dictionary. The executable requires occupancy to
allow exactly one such block per SM and checks unique, unchanged physical SM IDs
at the two endpoints of every launch. It does not assume that SM IDs are dense or
that block numbering determines their order.

1. Export initial SM records, read every assigned physical texel through
   `tex1Dfetch<uint4>` to warm TEX, and export the pre-work checksums through bulk
   copies.
2. Synchronize the whole cooperative grid.
3. Stage Lane/State through native one-dimensional `cp.async.bulk` transfers into
   shared memory, compute the full K1 result, and bulk-copy Results to global
   memory. Productive masks still come from TEX. The shared input/output union is
   protected by completion barriers, block barriers and async-proxy fences.
4. Synchronize the whole grid and reread the entire physical dictionary through
   TEX. Export diagnostic checksums and SM records through native bulk copies.
5. Download and verify all logical candidates and zero padding. Commit the host
   word and JK state only after verification.

The optimized schedule groups four physical tiles for simultaneous computation
by 256 threads, then exports the four results in waves. The same shared union is
reused. `compute_tiles` and `compute_threads` distinguish this grouping from the
unchanged 64-texel physical tile. The build-time `ATOMOS_BULK_COMPUTE_TILES` macro
permits controlled comparisons.

The fixed `.4` rotation uses correctly rounded binary64 sine/cosine constants.
Exact rational rounding enclosures and a CPU/GPU bit comparison are recorded in
`results/residency_followup/`. This removes the reviewed binary's otherwise
unnecessary global coefficient-table loads. It does not replace literal OTAN2
with atan2 or change any numerical threshold.

## Working set and accounting

The largest permitted atlas is 262,144 packed uint4 texels, or 4 MiB. On the
46-SM review device, each block owns at most 5,760 texels (90 KiB). The dictionary
is distributed across the SM caches; it is not replicated in every SM cache.
Nsight Compute reports the actual shared-memory configuration separately from
the requested maximum-L1 preference.

Device Lane/State/Result arrays use padded row-major backing so every native
bulk transfer has valid, aligned source and destination ranges. Physical Morton
tiles map to these canonical records explicitly. Padding never executes K1 and
never appears as a logical output row. Its output bytes must remain zero.

Actual payload is `272 * stored_texels + 16 * SMs * (2 * 512 + 2)` bytes.
The second term is 755,136 bytes on this device. The existing 64 MiB planning
margin, 512 MiB ceiling, actual-free-VRAM reserve and admission limits still apply.
Input resources remain immutable during texture reads, and the texture object is
destroyed before its backing allocation.

## Measured meaning of residency

A cold Nsight Compute launch includes warm, real work and final probe. The
compulsory miss count is `16 * stored_texels / 32` sectors. Reaching exactly that
count means no additional dictionary misses were observed during work and the
final reread, under the recorded cold-cache and coverage conditions. The complete
sector, hit and miss counts are retained; added reads are never hidden behind a
hit percentage. Per-thread XOR digests cover every texel but can collide; they
do not measure cache residency.

This measurement is conditional on the recorded workload, launch and device.
It is not a mathematical GPU-binary proof or a supported cache-pinning guarantee
across launches or arbitrary competing workloads. All warm/probe, bulk-copy,
barrier and diagnostic overhead is included in the ordinary CUDA-event timing;
host transfer, checking and file export time is excluded. Profiler-perturbed
durations are kept separate from ordinary timing trials.

## Reproduce

Use the installed CUDA/MSVC toolchain and a short Windows build directory:

```powershell
cmake -S . -B C:/Users/Tom/.cache/ak1/bulk_export_sm120 -T cuda=12.8 -DATOMOS_ENABLE_CUDA=ON -DATOMOS_CACHE_BULK_EXPERIMENT=ON
cmake --build C:/Users/Tom/.cache/ak1/bulk_export_sm120 --config Release --target atomos_cache_bulk
C:/Users/Tom/.cache/ak1/bulk_export_sm120/Release/atomos_cache_bulk.exe --rows 17 --angles 257 --layout morton8 --mode shift-or --epochs 3 --out my_bulk_run
python tools/verify_run.py my_bulk_run
```

The output directory must be new. Exported traces contain actual downloaded GPU
values in the existing canonical run format. Summary metadata explicitly names
`bulk-warm-work-probe-v1` and `bulk-padded-row-major-v1`; the Python verifier checks
the different allocation formula and the embedded execution receipt strictly.

`tools/study_cache_bulk.py` runs the conformance, ordinary timing and cold-counter
study, with selected complete trace exports for the independent Python reference.
`tools/check_cache_bulk_edges.py` covers additional aspect ratios, seeds and
Compute Sanitizer tools. Their summaries keep exact executable/source hashes,
commands, raw logs and observed residency outcomes. Consult the final PDF and
`results/residency_followup/summary.json` for the executed counts and limitations.

## Source atlas and Klein carrier: first TMA result, 2026-09-13

The capacity and allocation statements above describe the original direct
profile. The extended runner can load a strictly checked `AOSDF01` source atlas
with `--atlas`, and selects `direct`, `klein-plus`, or `klein-minus` occupancy
transport with `--carrier`. The default atlas cap remains 262,144 stored texels;
`--atlas-cap-texels` explicitly permits studies up to 1,048,576. These storage
limits are not measured cache-capacity claims. This section records only the
first successful 4 MiB source-atlas/carrier profile; larger studies are separate.

The carrier reads an immutable pre-epoch occupancy snapshot, crosses the angular
seam by reflecting the radial row, and runs before the selected word producer.
Each destination retains its own JK state. Downloaded transported words,
including every padded word, are compared with an independent per-cell scatter
before the proposed K1 results are verified and committed. Declared synthetic
OTAN2 increments remain explicitly identified as synthetic inputs.

The first carrier implementation used scalar `.cg` neighbor loads and exported
each transported word with a scalar `.cg` store. A cold hardware-counter run
revealed extra texture misses despite the cache policy. Adding an explicit warp
barrier before the productive TEX read did not restore retention. The replacement
uses neighbor states already in the shared input tile, fetches each required
external row neighbor as an aligned 16-byte State pair through native bulk TMA,
and exports transported words through bulk TMA. A linear tile exports 256 bytes;
a Morton tile exports eight canonical rows of 32 bytes each.

The input tile remains 5,632 bytes and the input/output union remains 10,752 bytes.
Separate shared storage adds 128 bytes for neighbor pairs and 256 bytes for the
carrier export. The observed binary uses 11,152 static shared bytes, 102 registers
per thread, no local-memory spill storage, and a realized 16 KiB shared-memory
configuration. Disassembly of the bulk function removes its two explicit
`LDG.E.STRONG.GPU` sites and one `STG.E.STRONG.GPU` site. Other kernel infrastructure
still contributes LSU traffic; this is not a claim of zero LSU traffic globally.

The measured case was a 512-row by 16,384-angle source atlas, linear layout,
`klein-plus`, recurrent producer, fringe enabled, mixed diagnostic profile, and
one measured epoch after the verified setup launch. The device was the NVIDIA
GeForce RTX 5070 Ti Laptop GPU, compute capability 12.0, with 46 SMs. CUDA 12.8,
MSVC 14.44.35207 and Nsight Compute 2025.1.0 were used. Profiling selected one cold
kernel using kernel replay, `--cache-control all`, and unchanged GPU clocks.

| Recorded schedule | TEX sectors | TEX miss sectors | LSU global-load miss sectors |
| --- | ---: | ---: | ---: |
| Original binary, direct carrier control | 393,702 | 131,072 | 4,536 |
| Original binary, Klein-plus with scalar `.cg` carrier I/O | 393,738 | 136,288 | 78,789 |
| TMA carrier replacement, Klein-plus | 393,738 | 131,072 | 4,824 |

The 4 MiB dictionary has 131,072 compulsory 32-byte sectors. The TMA run reached
that exact miss floor, eliminating the original carrier run's 5,216 additional
misses for this recorded launch. Total TEX sectors exceed the ideal coalescing
minimum of 393,216 in both the direct control and the corrected carrier run;
extra request splitting alone therefore does not imply dictionary eviction.
The residency criterion remains exact equality to the compulsory miss floor,
with complete dictionary coverage and the recorded phase ordering. No miss
tolerance was relaxed.

For this shape the new metadata reports 4,096 halo transfers, 65,536 halo bytes,
4,096 carrier export transfers, and 1,048,576 carrier export bytes per epoch.
Its device payload is `272 * stored_texels + diagnostics + 4 * stored_texels`,
or 73,106,880 bytes here; the last term is the separately verified carrier output.
Halo storage is shared memory, so it adds no global allocation. Metadata records
zero scalar carrier `.cg` loads and stores and identifies the TMA policy. A host
coverage check verifies the staged or halo source of every logical destination.
An independent CPU scatter audit covered 264 shape/layout/direction cases and
12,160 logical words, including one-cell angles, non-power-of-two row counts,
partial angular words and row strides that do not divide a tile. Actual CUDA
candidate/transport checking remains required for each device run.

Nsight Compute reported 1.327328 ms for this TMA kernel. This is a profiler
duration, not an ordinary timing benchmark; CUDA-event output captured inside
the replayed process must also not be treated as ordinary timing. These results
show observed retention for this workload and launch, not a driver-supported
cache pin or a guarantee across launches, competing workloads, other layouts,
larger atlases, or the separate SDF/NOR interpreter kernel.

Evidence: the preserved original source is
[`baseline_cache_bulk.cu`](../results/sdf_klein_20260913/baseline_cache_bulk.cu).
The build and small Morton/tail smoke receipts are
[`bulk_tma_carrier_build.log`](../results/sdf_klein_20260913/bulk_tma_carrier_build.log)
and [`tma_smoke.log`](../results/sdf_klein_20260913/tma_smoke.log).
The first profile's exact command and raw counters are
`C:/Users/Tom/.cache/ak1/sdf_capacity/tma_plus.command.json` and
`C:/Users/Tom/.cache/ak1/sdf_capacity/tma_plus.csv.log`; the direct and original
carrier controls are the same directory's `direct_control.csv.log` and
`cold_512_16384_linear_0.csv.log`. The fixed executable is
`C:/Users/Tom/.cache/ak1/sdf_gpu/Release/atomos_cache_bulk.exe`; the preserved
baseline is `C:/Users/Tom/.cache/ak1/sdf_bulk_before.exe`.
