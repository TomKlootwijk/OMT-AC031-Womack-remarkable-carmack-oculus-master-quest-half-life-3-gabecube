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
