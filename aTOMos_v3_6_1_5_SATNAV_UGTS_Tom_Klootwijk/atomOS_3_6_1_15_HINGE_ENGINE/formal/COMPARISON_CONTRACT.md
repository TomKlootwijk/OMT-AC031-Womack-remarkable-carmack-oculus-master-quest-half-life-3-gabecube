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

Open. No S2 benchmark result has yet been collected for R15. No aggregate
superiority or complete S2 feature replacement is claimed. Results will name
the operation, correctness contract, data, device and measured costs.
