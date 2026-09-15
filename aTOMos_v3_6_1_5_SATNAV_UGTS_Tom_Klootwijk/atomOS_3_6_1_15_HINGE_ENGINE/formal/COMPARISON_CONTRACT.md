# S2 comparison contract

The goal is a usable engine whose exact hinge/phi/seam core and native GPU
realization improve on S2. A selected point-query win is evidence for that
operation, not proof of universal replacement of S2's polygonal toolkit.
This contract is written before collecting R15 benchmark results.

## Shared semantics

Use the same immutable point coordinates, IDs, query directions and distances.
Compare normalized directions on the unit sphere. Radius membership is inclusive;
ties and duplicate points are retained. Exact geometric comparisons use the
official S2 robust predicates as the shared baseline and final decision oracle.
Derived GPU arithmetic must conservatively retain ambiguous candidates. A
rounded accelerator output cannot silently overwrite authoritative seed state.

Nearest, k-nearest and radius queries must agree under the declared tie rule.
Boundary, pole, seam, near-antipodal and duplicate cases are correctness cases.
The simple brute-force oracle is independent of each spatial index.

## Workload families

Cover uniform spherical points, clustered data, narrow curves and degenerate
or repeated points. Measure multiple dataset sizes and single-query as well as
batched workloads. Include coherent and shuffled queries. Record construction,
updates/refits, seed packing, upload, VRAM expansion, resident query time and
host-visible end-to-end query time separately. Include persistent repeated use
and cold startup. Do not hide losing regimes or select only the fastest trial.

## Baselines and execution

Pin official google/s2geometry source and dependency versions. Use optimized
builds, identical input generation and the same timed output requirements.
Report S2 single-thread and available multi-thread throughput where independent
queries permit it. Describe CPU versus GPU resource differences. Record warmup,
every repeated timing, synchronization, memory use, driver/compiler and hardware.
Compare texture fetches with a matching global-memory path to distinguish the
texture mechanism's contribution from generic batching or GPU parallelism.

## Whole-core evidence

The exact reference core must execute guards, two ordered ASA/NA sets, JK,
hinge-event deduplication, parity/seam transitions and lossless seed packing.
GPU results must connect back to this state contract. Merely benchmarking an
unrelated point index does not complete the engine goal. The log/spherical LUT,
phi expression authority, VRAM cache lifecycle and source/output epochs must be
specified and exercised. Claims of exactness concern the stated mathematical
inputs, not unknown physical truth or arbitrary transcendental evaluation.

## Completion status

Measured on 15 September 2026. The predeclared contract above is retained.
The compacted hybrid radius-ID path matches all 36 workloads and beats the
best measured 1/4/20-worker S2 median in 22. The resident count path matches
all 27 workloads and beats that S2 baseline in 20 host-complete cases.
It also beats the best measured CPU method (including the allocation-free
aTOMos BVH) in 13 cases. Setup is separately reported and excluded from
these persistent-use timings. All losing regimes remain in the reports.

The packed exact operator profile, reference hinge/seam transitions and
native delayed count-to-ASA/NA+JK loop are implemented and checked. A separate
banked integer word-feedback sweep exercises every record through large
VRAM working sets; it does not measure the S2 geometry operation. Texture
and ordinary loads are reported separately, without attributing generic GPU
parallelism to texture-cache superiority.

Full native transcendental lowering, dynamic refit/rebinding and the complete
log-spherical LUT lifecycle remain outside this release's measured scope.
CPU nearest/k-nearest correctness is checked; broad region/polygon S2 parity
and performance are not established. See review/COMPARISON.md and
review/RESIDENT_RESULTS.md for complete conditions and source-bound results.
