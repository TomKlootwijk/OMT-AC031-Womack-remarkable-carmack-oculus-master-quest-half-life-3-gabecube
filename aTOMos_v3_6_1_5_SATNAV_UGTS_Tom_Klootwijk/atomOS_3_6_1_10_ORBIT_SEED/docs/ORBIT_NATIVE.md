# ORBIT-WORKER-1 native contract

Release3.6.1.10 provides `orbit_worker --model FILE --backend cpu|cuda [--device N]`.
The complete physical seed is decoded and converted to the numeric transport by
`python/orbit_native.py`; original observations and future target samples do not
enter the worker. All runtime timestamps are seconds relative to the explicit
seed epoch. Positions and velocities are GCRS metres and metres/second.

The default transport is now `ORBIT-SEED-NATIVE-3`. It begins:

```
ORBIT-SEED-NATIVE-3
DYNAMICS 1|2
DOMAIN lower_seconds upper_seconds
... the corresponding V1 or V2 numerical body described below ...
```

The dynamics token selects the existing R1 or R2 equations; `1|2` denotes a choice,
not a literal token. The closed domain must have positive width, contain zero,
fit within every required coefficient interval, and fit the cold-query step budget.
The worker enforces it directly, including `EVALUATE` and zero-time queries.
Each integration work/stride limit is an integer in 1..10,000,000; checkpoint
capacity remains in 1..1,000,000. Epoch GPST/TT consistency and an initial state
outside the reference Earth are checked before the ready record is emitted.

V1 and V2 remain readable. Since those transports have no separate domain field,
their effective domain is the intersection of the required forcing/frame intervals;
that intersection must contain the epoch. Newly rejected invalid raw inputs are
not compatibility guarantees. `numeric_model(model, transport_version=1|2)` exists
for explicit legacy transport tests; the default is V3.

`NativeOrbit` snapshots the validated input before serialization. `model` is a
recursive read-only view, `model_sha256` binds the frozen model, and `copy_model()`
returns editable input for a new worker. Editing the caller's original dictionary
cannot change the active worker, timestamp domain or snapshot digest.

`ORBIT-SEED-NATIVE-1` begins the ASCII whitespace-separated numeric file. It contains,
in order: GPST epoch, JD TT epoch, RK4 step, checkpoint stride in steps, maximum
checkpoint count, maximum steps per query; six initial state values; Earth mu,
radius, J2,J3,J4,C22,S22, Sun mu, Moon mu, AU, SRP acceleration at AU, cylindrical
shadow flag, three constant RTN accelerations; ERA origin/rate and polar xp/yp.
Each of `Q`, `SUN`, `MOON` then names a series: segment count followed by each
segment's t0,t1,degree and component-major Chebyshev coefficients. Q has nine
components, each body three. `END` terminates the model; trailing tokens fail.
Degree is at most32 and each series has at most4096 contiguous segments. All
floating inputs are finite; integer fields require unsigned decimal tokens.

`ORBIT-SEED-NATIVE-2` carries `ORBIT-DYNAMICS-R2`. Its prefix is identical, with
the five legacy gravity values and constant xp/yp placeholders set to zero.
After Q/SUN/MOON it adds the following, before `END`:

```
GRAVITY degree
C00 S00
C10 S10 C11 S11
... triangular Cnm Snm pairs for n=0..degree, m=0..n ...
RELATIVITY flag c_m_s
EOP segment_count
... segments with three component rows: ERA correction, xp, yp ...
END
```

Indices are implicit and are not tokens in the coefficient stream. Gravity
degree is at most 12; coefficients are unnormalized in the geodetic convention
without the Condon--Shortley phase. C00 must be one and each Sn0 must be zero.
The separate Chebyshev degree limit remains 32. EOP uses the same segment syntax
as the body series and must cover the requested force evaluations. The declared
ERA is `era0 + era_rate*t + EOP[0]`; polar angles are EOP[1] and EOP[2].
R1 input and equations remain supported.

Q maps GCRS to CIRS. The full terrestrial matrix is
P Rz(ERA) Q, with passive Rz and P=Rx(-yp) Ry(-xp), matching ERFA pom00 at s'=0.
Gravity is evaluated in terrestrial coordinates then transformed back using the
matrix transpose. R1 uses central gravity, J2–J4 and unnormalized C22/S22. R2 uses
the complete declared Earth harmonic coefficients through degree/order 12.
Its Cartesian Cunningham recurrence carries three analytic derivatives per value,
streams one order at a time, and retains the diagonal and two preceding degrees.
It is nonsingular at the poles and uses no runtime finite differences. Both
profiles include Sun/Moon third-body acceleration, optional cylindrical-shadow
SRP and constant RTN acceleration. R2 additionally declares the Schwarzschild
Earth term and time-dependent EOP. Celestial forcing consists of embedded
Chebyshev coefficients. See the physical-model formalization for provenance.

The worker first emits one JSON ready record. Each input line produces one JSON
response; an invalid command emits a typed error and subsequent requests remain
available. Commands are:

- `QUERY time`: one arbitrary timestamp; response has a one-element `queries` list.
- `BATCH count time...`: one to4096 timestamps, retaining input order and duplicates.
- `TRANSITION q drive present A1 N1 B1 A2 N2 B2 x_lut j_lut k_lut`.
- `EVALUATE time state0...state5`: CPU force/frame diagnostic, explicitly labelled
  `cpu_diagnostic` even when the worker's propagation backend is CUDA.
- `STATS`, `RESET`, `PING`, `QUIT`.

Each propagation record reports time, status, state and actual RK4-step count.
Within one BATCH, exactly equal binary64 timestamp bit patterns are computed once,
then copied to their original output positions. `unique_query_count` reports the
number computed; repeated rows set `reused_in_batch=true` and `rk_steps=0` because
they perform no extra integration. Positive and negative zero are distinct input
patterns, and negative zero is serialized as `-0.0` so JSON readers preserve it.
Only `ok` denotes a completed requested state. Failure records may contain a last
partial state; their position must not be published as a successful prediction.
Forcing outside the embedded interval, nonfinite/singular arithmetic and the
declared work limit have distinct statuses. `outside_model_domain` rejects a
timestamp before integration; `inside_reference_earth` rejects a state at or below
the declared reference radius. Every RK4 stage and the final candidate state are
checked; a rejected step does not commit its candidate to the state or cache.
No trajectory is extrapolated through
missing external forcing coefficients. Requested forecast intervals can be extended
by constructing a seed with the desired forcing domain.

CPU propagation uses a canonical lattice at integer multiples of the declared step
from the seed epoch, independently in both time directions. Sparse checkpoints are
created only on this lattice at the declared stride. A fractional query takes one
extra RK4 step from its canonical predecessor and never becomes a checkpoint.
Query order therefore does not change the reconstructed state. Checkpoints are
created lazily, evicted by bounded least-recent use, and regenerated from available
canonical predecessors or the permanently retained initial seed. Cache capacity
includes the seed; no precomputed trajectory is stored in the seed payload.

The integer lattice predecessor is corrected if binary64 division rounds it beyond
the requested time. RK4 receives an explicit integer-index endpoint for a full
step and the exact requested endpoint for a fractional step. Stage times remain in
that closed step interval. This avoids false domain failures such as
`2.4000000000000004 + 0.1 > 2.5`. Frozen 30 s and 7.5 s model grids keep the same
stage times; arbitrary decimal steps now use these explicit endpoint semantics.

CUDA uses one thread per requested timestamp, with independent integration from
the epoch. CUDA output metadata explicitly names `independent_from_epoch`; it does
not claim use of the CPU cache. Kernel time excludes copies, allocations and host
protocol work; wall time includes the native query operation. CPU `kernel_ms=0`
means no CUDA event timing, while `wall_ms` measures its query work.

The R10 CUDA 12.8.61 build on the RTX 5070 Ti Laptop GPU reports 210
registers and 216 local bytes per thread, zero static shared bytes, and a
3,064-byte model parameter. These are measured compiler/device properties,
also emitted in the device metadata; they are not portable performance promises.

The two word stages are ordered and literal:

```
x = LUT2(q,drive)
A = ASA_NA(x,A1,N1,B1,present)
B = ASA_NA(A.output,A2,N2,B2,present)
j = LUT3(q,B.output,drive)
k = LUT3(q,B.output,drive)
qnext = ((j & ~q) | (~k & q)) & present
```

Both J/K tables read the same old q; each boundary hit absorbs that stage's whole
word. The trace publishes both stages, including ASA, NA, hit count and output.
The worker transition is stateless with respect to q: the calling scheduler owns
and supplies the persistent q, so random-access orbit queries cannot silently alter
the event-state recurrence. CPU/CUDA share the exact primitive implementation.

The wrapper caches the validated static transition inputs using the complete
typed canonical feedback bytes, including all nested masks, equations, predicates
and cadence fields. Any content/type edit invalidates that preparation immediately.
State and drive remain arguments to every transition; this cache does not skip
the recurrence or reuse previous outputs.

`tests/orbit_native_tests.cpp` checks the circular Kepler solution, gravity against
an independent potential gradient, polar/ERA multiplication, Chebyshev polynomials
and 4000 two-stage word cases. R2 checks add an independent spherical-harmonic
gradient oracle, polar continuity, sparse R1 basis equivalence, relativity and
varying EOP. `tools/validate_orbit_native.py` checks exact query-order
replay with forced cache eviction, Python force/frame agreement, actual GPU batches
spanning multiple blocks, CPU/CUDA word equality and optional Compute Sanitizer.
These checks establish numerical execution; physical forecast accuracy is measured
separately against held-out reference products.

R10 evidence is in `results/orbit_native_36110_validation/summary.json`: all four
models passed 1,040 CUDA trajectory comparisons, 256 complete word traces and
108 cache-replay queries. Maximum sampled CPU/GPU position disagreement remains
43.196 micrometres, and velocity disagreement is 8.071e-9 m/s. Compute Sanitizer
reported zero errors for 129 trajectory queries and a word transition. Nine new
executable/wrapper regression tests cover V1/V2/V3 transport, closed endpoints and
one-ULP exclusions, Earth-surface failure, raw-input admission, malformed-command
recovery, exact duplicate reuse, signed zero, typed feedback edits and frozen model
snapshots. Their logs and targeted CPU/CUDA admission records are under
`results/orbit_native_36110_build`.
Both native builds passed all four CTests. The fresh retained receiver regression
at `results/gpu_20260915_070915_949456` passed actual texture/global CUDA execution,
both independent `verify_run.py` comparisons, and both Compute Sanitizer runs with
zero errors. All ten packaged executable hashes equal the tested build artifacts;
`results/orbit_native_36110_build/binaries.json` records them.

In the recorded 64-copy/300-second timestamp case, both backends perform 10 RK4
steps instead of 640. The CPU operation took 0.0468 ms in that sample; CUDA took
11.42 ms because uploads and launch overhead dominate this small batch. This is
an integration-work reduction, not a universal runtime speedup. Reused timestamps
remain ordinary requested output rows; no future target samples are packed.

The retained R9 R2 validation in `results/orbit_native_r2_validation_final` passed
1,040 actual GPU trajectory queries, 256 complete word traces and 108 cache
replay queries. Maximum sampled CPU/GPU position disagreement was 43.2 micrometres;
the maximum velocity disagreement was 8.08e-9 m/s. Compute Sanitizer reported
zero errors for 129 trajectory queries and a word transition. Separately,
`results/orbit_native_r2_build/r1_compatibility.json` records 36 sampled R1 queries
whose CPU states are bit-for-bit identical to the retained baseline executable.
These are measured finite-precision comparisons, not a mathematical roundoff
bound. `tools/validate_precision_dynamics.py` separately compares fixed-step
integration, half-step integration and two DOP853 tolerances without reading
future target positions.

The domain-wide R2 numerical audit passed its declared sampled 1 m integration
threshold. Across its eleven timestamps per object, native/default DOP853
position differences peaked at 31.72 mm (G05), 1.233 mm (C03), 1.252 mm (C06)
and 36.59 mm (CHANDRA). The independent solver itself has finite numerical error:
the tighter/default CHANDRA solutions differ by up to 44.03 mm in that grid,
and the half-step results are not monotonic against the default reference.
An additional two-timestamp investigation near 3.5 days found up to 109.83 mm
between those DOP853 settings, while native/tighter DOP853 differed by at most
1.50 mm. Full states for that comparison are retained in
`results/orbit_physical_r2_jump_audit/physical_audit.json`. These measurements
separate solver uncertainty from CPU/GPU rounding differences and from physical
forecast residuals; none is a universal numerical error bound.
