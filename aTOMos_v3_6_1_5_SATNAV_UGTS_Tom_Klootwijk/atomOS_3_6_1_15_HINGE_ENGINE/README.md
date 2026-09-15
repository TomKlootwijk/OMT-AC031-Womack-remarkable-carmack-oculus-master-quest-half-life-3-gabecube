# aTOMos 3.6.1.15 — native hinge engine

Tom Klootwijk. This release connects retained equations, exact word packing,
native integer texture evaluation, resident count certificates and delayed
GPU state feedback. The editable PDF
master also retains the R14 field, physics and measurement foundation.

The authoritative exact profiles are separate from derived spatial caches:

- `python/atomos_hinge.py`: rational `a+b*phi`, expression graphs, typed guards,
  two ordered ASA/NA masks, atomic JK, complete seam winding and seed/state packing.
- `cuda/exact_program.cu`: checked integer-coefficient phi expressions, complete
  operator words packed into 32-bit planes, GPU expansion and integer texture
  evaluation. The coefficient bound is `2^30-1`; unresolved results cannot
  authorize dependent state commits.
- `src/engine_demo.cpp`: actual packed operator evaluation feeds sampled sign
  events into persistent native ASA/NA and JK state. Boundary and unresolved
  samples hold state; duplicate events do not repeat a transition.
- `include/atomos/spatial_index.hpp`: exact normalized-direction membership
  and ordering over immutable binary64 point seeds, using official S2 predicates.
- `cuda/texture_index.cu`: native texture and global-memory variants of the same
  conservative spherical radius filter. Exact host refinement and complete
  overflow fallback preserve the declared answer.
- `cuda/resident_index.cu`: immutable resident point/query epochs and a proved
  binary64 count predicate. Definite decisions stay on the GPU; unresolved
  queries remain explicit and can receive complete exact host resolution.
- `cuda/resident_feedback.cu`: old device state selects a paired immutable
  query, then a distinct ordered kernel applies the resolved count's ASA/NA
  and JK transition. Ten device epochs, unresolved holds and replay behavior
  are checked. This profile has a fixed chart.
- `cuda/word_cache_benchmark.cu`: a separate exact integer phi/ASA/NA/JK
  recurrence with old-word operands, banked immutable texture records and
  persistent global ping-pong state. Streaming and coprime-permuted epochs
  visit every record. Paired texture/global trials reset identically outside
  timing; the report identifies each completed working-set size.

`formal/CORE_RUNTIME.md`, `formal/EXACT_GPU_PROFILE.md`,
`formal/NATIVE_GPU.md`, `formal/SPATIAL_INDEX.md`,
`formal/RESIDENT_PREDICATE_PROOF.md` and `formal/WORD_CACHE_BENCHMARK.md`
specify the actual domains.
The full inherited XOP catalog is a specification; these are named executable
subsets. Log-spherical calculus is formalized; complete native transcendental
lowering, dynamic geometry refit/cache rebinding and full S2 feature coverage
remain open. Immutable query epochs and the named device feedback loops are
implemented; they do not lower the entire XOP catalog or dynamic lifecycle.

## Build and run

The checked Windows configuration uses Visual Studio 2022 Build Tools, CMake,
CUDA 12.8 and an RTX 5070 Ti Laptop GPU (sm_120). S2 is pinned in
`source/DEPENDENCIES.json`, and its CMake configuration fetches Abseil.
A short build path avoids MSBuild path-length failures.

```powershell
& ./tools/build_native.ps1
python -m unittest discover -s tests -p test_hinge.py -v
& C:/aTOMosBuild/r15cuda/Release/engine_demo.exe
ctest --test-dir C:/aTOMosBuild/r15cuda -C Release --output-on-failure
& C:/aTOMosBuild/r15cuda/Release/compare_s2.exe --out review/new_comparison.json
& C:/aTOMosBuild/r15cuda/Release/compare_resident.exe --out review/new_resident_comparison.json
& C:/aTOMosBuild/r15cuda/Release/word_cache_benchmark.exe --quick --out review/new_word_quick.json
& C:/aTOMosBuild/r15cuda/Release/word_cache_benchmark.exe --max-gib 11 --out review/new_word_full.json
```

The comparison reports 1, 4 and 20 configured CPU threads with persistent
workers, construction, all repeated timings, device kernel times, complete
host-visible times, output equality and overflow counts. The same GPU algorithm
is measured using texture and ordinary loads. `review/s2_full.json` preserves
the first complete measurement before the recorded pipeline optimization.
`review/s2_compacted.json` records the later selective-readback pipeline.
The report and its generated summary identify the measured gains and losing
regimes. A radius-query gain is not a general replacement of S2.

The extended build passed all six native test targets and 22 Python checks.
The optimized integer word sweep passed 17 working-set sizes through 9.744 GiB,
with every epoch digest agreeing with the preserved baseline. The resident count comparison uses
cardinality output, while the hybrid comparison returns sorted identities.
The large word-state sweep measures a separate operator/memory workload;
its generated report supplies actual completed sizes and timings. It records
full-record digests and sampled CPU replay, not exhaustive bitwise validation
of every large state. Integer textures do not guarantee cache hits, and the
logical record/state throughput is not measured hardware DRAM bandwidth.

Measured host-complete texture wins over the best S2 configuration are 22/36
radius-ID workloads and 20/27 resident count workloads. Every complete answer
matches. Ordinary global loads beat texture device timing in all 27 resident
count cases. Read `review/COMPARISON.md`, `review/RESIDENT_RESULTS.md` and
`review/WORD_OPTIMIZATION.md` for all winning and losing regimes, setup costs
and the distinct output contracts. The exact word optimization removes address
division, narrows this bounded phi body to signed32 and reduces digest barriers.
`review/WORD_PROFILE.md` records selected-chunk Nsight counters and literal
texture instructions; neither capacity nor those samples establishes full
DRAM bandwidth saturation.

## Document and evidence

`docs/unified.tex` is the editable master. `tools/build_pdf.py` compiles it with
Tectonic; `tools/review_pdf.py --render` checks text, layout and rendered pages.
`tools/package_release.py` packages only a PDF whose current bytes have completed
visual review. The final reviewed PDF is also copied into the main Git root.

The retained NIST reply is an immutable historical observation, not continuous
clock synchronization. Physical, orbital and photonic specializations still
need their actual model inputs, calibration and observations. No physical
accuracy follows from bit-preserving storage or a spatial-index benchmark.
