# Exact implemented functional tolerances

This audit describes release 3.6.1.9 with ORBIT-DYNAMICS-R2 as implemented and
measured on 15 September 2026. R1-only physical diagnostics are explicitly labelled
as retained baseline evidence. The system has several specific acceptance tests, numerical settings and
input limits. It has **no single intrinsic physical satellite-position error
budget**. Passing a 2 mm replay comparison or a 1 cm CPU/CUDA comparison does
not mean that the predicted satellite is within that distance of its true orbit.

The delivered examples pass the implemented functional checks below. Thresholds
were read from the cited code; no threshold was loosened to accommodate a result.
The new R2 numerical audit additionally declares its own 1 m sampled RK4-versus-
DOP853 acceptance test; this is separate from the chosen 10 m physical budget.
Quantities described as “measured only” have no implemented pass/fail threshold.

## Exact operations: zero mismatches permitted

| Operation | Implemented requirement | Observed result and source |
|---|---|---|
| Binary seed packing | Repacking a decoded seed must reproduce every byte. Binary64 values, including signed zero, retain their bit patterns. Map ordering is canonical. | PASS for all four delivered seeds; [seed release validation](../results/orbit_seed_r2_release_validation/summary.json), [format tests](../tests/test_orbit_seed.py). |
| Seed integrity | Exact header, payload lengths, stream termination, SHA-256 and canonical re-encoding; no tolerated changed bit, missing byte or trailing byte. | PASS for the specified corruption/truncation cases in `test_tamper_every_payload_region`; this is a tested set, not exhaustive enumeration of all corrupt files. |
| Two ASA/NA stages and synchronous JK | Exact uint32 results, masks, hit counts and next state. An intersecting boundary absorbs the whole selected word. | PASS: 4,000 native recurrence cases plus explicit second-stage absorption; 64 exact CPU/CUDA transition comparisons per object. [Native tests](../tests/orbit_native_tests.cpp), [native evidence](../results/orbit_native_r2_validation_final/summary.json). |
| CPU timestamp order/cache | Repeated and reordered queries must return exactly equal binary64 state values; eviction must not alter the answer. | PASS for all four models. The separate forced-eviction test used capacity four and recorded 2,337–14,123 evictions per object. |
| Packed-only reconstruction | Isolated reconstruction must exactly equal the normal runtime state at the same requested timestamps. Original release-file reads are denied in the isolated process. | PASS for all four seeds; [isolation and scrub evidence](../results/orbit_seed_r2_release_validation/summary.json). |
| Feedback counterfactual | Edited JK equations must change the actual timestamp sequence; physical state at common timestamps must remain exactly equal. | PASS for all four seeds. No approximate equality is substituted. |
| Original key codecs | Both 64-bit layouts must round-trip the original `(20,18,14,12)` tuple exactly and reproduce the source golden pair. | PASS: 5,000 random tuples, golden values, widths and winding cases in [UGTS tests](../tests/test_ugts.py). |

These requirements concern equality of the specified representation or algorithm.
Lossless packing adds **zero additional coordinate quantization** relative to the
input binary64 seed. That does not remove floating-point rounding already present
in construction or subsequent integration.

The independent bit-plane review checked byte layout across 64-word group
boundaries, signed zero, subnormal/maximum finite floats and signed/unsigned
integer endpoints. It found and resolved an encoder/decoder structural-limit
mismatch. The [post-fix isolated replay](../results/orbit_bitplane_final_replay.json)
rejects the oversized-container fixture for both codecs and confirms unchanged
seed/model identities, packed bytes and exact states for all four seeds at four
timestamps each. The copied shared runtime source totals 89,342 bytes; it is
separate from the per-seed storage size. The original source directory remains
inaccessible during each isolated reconstruction.

## Native numerical acceptance tests

All inequalities in this table are the actual strict `<` assertions. The C++
unit test reports pass/fail rather than a numeric maximum for each assertion.

| Check | Actual threshold | Observed final result | Code/evidence |
|---|---|---|---|
| Circular two-body Kepler position, 10 s RK4, four specified times through 43,200 s | Each Cartesian component error `< 0.002 m` | PASS; a component threshold, not a 3D norm threshold | `dynamics()` in [native tests](../tests/orbit_native_tests.cpp); [CPU CTest log](../results/orbit_native_r2_build/cpu_ctest.log), [CUDA-build CTest log](../results/orbit_native_r2_build/gpu_ctest.log) |
| Same circular test, velocity | Each component error `< 1e-6 m/s` | PASS | Same test and logs |
| Native harmonic acceleration versus a two-sided potential gradient | Each component error `< 2e-9 m/s²`; gradient uses ±2 m displacement | PASS | `dynamics()` in native tests |
| Explicit polar/ERA matrix multiplication | Each matrix entry error `< 1e-15` | PASS | `dynamics()` in native tests |
| Degree-three Chebyshev analytic polynomial | Absolute error `< 3e-14` at five specified points | PASS | `chebyshev()` in native tests |
| Native force versus independent Python vector arithmetic | 3D acceleration difference `< 1e-12 m/s²` | PASS; worst observed `4.449557262054371e-16 m/s²` | [validate_orbit_native.py](../tools/validate_orbit_native.py), [final native summary](../results/orbit_native_r2_validation_final/summary.json) |
| Native frame versus Python frame | Maximum matrix-entry difference `< 2e-14` | PASS; worst observed `1.1102230246251565e-16` | Same validator and summary |
| CPU versus CUDA position, 260 query times per object | 3D position difference `< 0.01 m` | PASS; worst observed `4.3196113484843136e-5 m` | Same validator and summary |
| CPU versus CUDA velocity, same query grid | 3D velocity difference `< 1e-5 m/s` | PASS; worst observed `8.070485538372328e-9 m/s` | Same validator and summary |
| Actual CUDA memory execution | Successful process exit, every requested query successful, expected absorption, and `ERROR SUMMARY: 0 errors` | PASS: 129 propagation queries and one word transition under Compute Sanitizer memcheck | Same validator; [memcheck log](../results/orbit_native_r2_validation_final/memcheck.log) |

The CPU/CUDA comparisons measure two implementations of the same frozen physical
model. They do not compare either implementation with the real satellite.

## Fresh trace verification

[verify_orbit_run.py](../tools/verify_orbit_run.py) reconstructs a trace from the
packed seed, independently evaluates its Boolean expressions and checks the
ordered timestamps. Its rejection tests use `>`; equality at these numeric
thresholds is accepted.

| Trace quantity | Acceptance condition |
|---|---|
| Fresh GCRS position | 3D difference `<= 0.002 m` |
| Fresh GCRS velocity | 3D difference `<= 1e-6 m/s` |
| GCRS state array, ECEF/ENU position arrays, station ECEF, Up and range | Each floating component difference `<= 0.002` in its stored unit; the additional GCRS position/velocity norm checks above also apply |
| ECEF/ENU velocity components and range rate | Each difference `<= 1e-6 m/s` |
| Other deterministic floating fields, including azimuth/elevation, their rates, sin-elevation rate, chart floats and full GPST | Absolute difference `<= 1e-9` **in that field's own unit**: degrees, degrees/second, 1/second, dimensionless chart units, radians or seconds as applicable |
| OTAN2 numeric value | Absolute difference `<= 1e-10 rad` |
| Record index and elapsed timestamp | Exact equality to the independently reproduced schedule |
| Strings, Booleans, integer keys/winding, seed/model identities, chain links, word results and selected cadence | Exact specified values; numeric approximation does not replace the discrete recurrence |

All four final release traces passed: 289 C03, 417 C06, 520 Chandra and 397 G05
records. Their measured maximum fresh position difference was **0.0 m**.
Rehashed false range, angular/rate, visibility, station, OTAN2 and second-stage
records are rejected by [the verifier regression tests](../tests/test_orbit_verifier.py).
These passed in the [139-test final Python run](../results/python_tests_3619_r2_release.log).

The `1e-9` field tolerance is not a uniform distance tolerance: one nanodegree and
one nanosecond are different quantities. It is also tighter than one ULP of the
large absolute GPST value at this epoch; in practice that absolute-time comparison
therefore requires the same representable value.

## Event search and undefined geometry

The implementation is [orbit_query.py](../python/orbit_query.py), specifically
`station_geometry` and `find_events`. The final cross-grid check is in
[validate_orbit_seed.py](../tools/validate_orbit_seed.py).

| Setting or check | Actual value/rule | Meaning and observed result |
|---|---|---|
| Default rise/set root refinement | `brentq` absolute `xtol = 0.01 s` | A numerical root setting, not an error bar on a real pass time. |
| Derivative-extremum refinement | `xtol = 0.1 * event_tolerance_s`, default `0.001 s` | Used to find derivative-bracketed extrema. |
| Grazing candidate | `abs(sin(el)-sin(mask)) <= 1e-9` at the tested extremum or sampled stationary point | A dimensionless candidate threshold; not a fixed angular threshold at all elevations. |
| Root deduplication | Keep a new sorted root only if separation from the previous retained root is `> event_tolerance_s` | Roots no farther apart than the tolerance are merged. |
| Coarse/dense search agreement | Same event types/counts; paired event-time difference `<= 0.05 s` | PASS for 120 s versus 30 s searches over all four objects and both stations. Worst observed difference `0.002507949131540954 s`. |
| Horizontal-origin handling | Azimuth and azimuth/elevation rates are undefined when horizontal ENU distance `<= 1e-6 m` | Returned as `None`; this does not erase full ENU or sin-elevation rate. |
| Elevation-rate denominator | `max(1e-15, cos(elevation))` when horizontal distance is above the preceding cutoff | Numerical denominator rule, not a visibility or accuracy budget. |
| Visibility decision | `elevation_deg >= station.elevation_mask_deg` | Exact implemented comparison; demonstration masks are 10°. |
| Event-search work limit | Initial sampling grid at most 200,000 points | A resource limit. Additional memoized root-refinement evaluations are not included in that initial-grid count. |
| Ordered-schedule work/progress | At most 100,000 records; next timestamp must be strictly greater unless already at the endpoint | An unrepresentably small positive cadence raises an error. |

The synthetic short-pass and repeated-sine tests request `1e-7 s` root tolerance
and compare their known event times to six decimal places; both pass. The real
search does not establish a continuous no-missed-pass proof. Neither its 10 ms
root setting nor its 50 ms refinement comparison proves physical event-time
accuracy under an imperfect predicted orbit.

## R2 physical-model numerical audit

[validate_precision_dynamics.py](../tools/validate_precision_dynamics.py) adds
the following explicit checks for the upgraded model. Its domain-wide numerical
audit reads gravity/EOP inputs and model coefficients, with no later target
positions. All four models pass in the [final R2 audit](../results/orbit_physical_r2_audit_final/physical_audit.json).

| Check | Actual strict threshold | Worst measured result |
|---|---|---|
| Recomputed normalized-to-unnormalized gravity coefficients | Maximum absolute coefficient difference `< 1e-20`; Earth mu and radius exactly equal source values | `0.0`, PASS |
| Complex-step potential gradient versus independent SciPy associated-Legendre spherical gradient | 3D acceleration difference `< 2e-12 m/s²` | `7.049041960805077e-16 m/s²`, PASS |
| Native force versus Python complex-step force | 3D acceleration difference `< 2e-12 m/s²` | `3.973993651728112e-16 m/s²`, PASS |
| Numba force versus Python complex-step force | 3D acceleration difference `< 2e-12 m/s²` | `3.284083995358298e-16 m/s²`, PASS |
| Embedded frame versus fresh ERFA and published EOP interpolation | Maximum matrix-entry difference `< 1e-10` | `4.7792325652551426e-11`, PASS |
| Analytic frame derivative versus independent five-point derivative | Maximum entry difference `< 2e-12 s^-1`; finite-difference h=0.25 s | `9.730646735421622e-15 s^-1`, PASS |
| Native RK4 versus independent default DOP853 | Maximum sampled 3D position difference `< 1 m`, over 11 specified timestamps per model from -8 to +7 days | `0.0365815487103427 m`, PASS |

The native-versus-default-DOP853 maxima by object are 0.0317155 m for G05,
0.0012320 m for C03, 0.0012515 m for C06 and 0.0365815 m for Chandra. The new
1 m numerical threshold is an explicitly selected test of implementing the
same equations; it does not certify a 1 m or 10 m real satellite forecast.

The tighter/default DOP853 discrepancy reaches 0.0440205 m for Chandra. Its
half-step RK4 comparison to default DOP853 is nonmonotonic and reaches 0.0442562 m.
Those two diagnostics have no additional pass threshold. They expose numerical
reference uncertainty near the model's discontinuous cylindrical-shadow changes;
the measurements do not prove fourth-order convergence for every trajectory or
bound all intermediate timestamps.

An [additional Chandra audit](../results/orbit_physical_r2_jump_audit/physical_audit.json)
at 302348.816 s and 302648.816 s finds default/tighter DOP853 differences of
0.109827 m and 0.105576 m, while native/tighter differences are 0.001498 m and
0.001488 m. Those extra points show why the default solver's smaller eleven-point
maximum must not be promoted to a general numerical bound. They do not account
for kilometre-scale disagreement with an external trajectory.

The new `r2_dynamics()` native unit checks also pass with the actual strict
per-component thresholds: degree-12 spherical gradient `< 2e-12 m/s²`, pole
continuity between the axis and a `(0.001,-0.001)` m displacement `< 3e-9 m/s²`,
R1/R2 sparse-basis equivalence `< 3e-15 m/s²`, isolated Schwarzschild acceleration
`< 3e-17 m/s²`, and EOP frame composition `< 2e-15` per matrix entry. Evaluation
outside EOP coverage must fail exactly. These are synthetic unit-test cases in
[orbit_native_tests.cpp](../tests/orbit_native_tests.cpp), with the R2 CTest logs
linked above; they are not observed orbit residual requirements.

## Retained R1 physical-model numerical audit

The retained R1 audit in [validate_orbit_dynamics.py](../tools/validate_orbit_dynamics.py)
has exactly three strict pass thresholds:

| Check | Pass threshold | Worst observed in [final audit](../results/orbit_physical_audit_final/physical_audit.json) |
|---|---|---|
| Analytic gravity versus five-point potential gradient | 3D difference `< 1e-8 m/s²` | `3.3855828605235474e-11 m/s²`, PASS |
| Compressed frame versus direct ERFA at the seed epoch | Maximum entry difference `< 1e-10` | `3.5368999395934964e-12`, PASS |
| Python vector versus Numba scalar force | 3D difference `< 1e-12 m/s²` | `2.6766507790745728e-16 m/s²`, PASS |

Its integration-convergence values are **measured only**. They do not define a
hidden metre threshold for accepting a physical forecast. The potential audit
uses ±100 m and ±200 m points in its five-point gradient. Construction separately
asserts that the explicit polar matrix matches ERFA `pom00` to `<= 1e-15` per entry.

The numerical settings are:

- Native RK4: fixed 30 s steps for G05/C03/C06, 7.5 s for Chandra. Fixed-step RK4
  has no built-in local error estimator or adaptive physical-position budget.
- Independent SciPy DOP853: `rtol=2e-12`, `atol=1e-6`, maximum step 300 s. These
  are integration-controller settings in the state component units; they are not
  a global trajectory error guarantee. The tighter diagnostic uses `rtol=3e-13`,
  `atol=1e-7`, maximum step 150 s.
- Training least-squares: `xtol=1e-9`, `ftol=1e-9`, `gtol=1e-7`, default
  `max_nfev=35`, `x_scale='jac'`, with an explicit scaled finite-difference
  increment `1e-3`. These terminate an optimizer in its scaled variables/objective;
  they are not a required maximum training residual in metres.
- Fitted parameter bounds: SRP coefficient `0..5e-6 m/s²` at one AU, each signed
  constant RTN acceleration `-2e-6..2e-6 m/s²`. State corrections are not bounded
  by that optimizer. Training uses 30 s RK4 for all objects; Chandra's finer
  replay step is applied afterward without changing its fitted state or forces.

The retained R1 held-out validator reports native versus DOP853 maxima of about 0.026743 m
for G05, 0.001032 m for C03, 0.001058 m for C06 and 0.390933 m for Chandra at nine
checkpoints per object. **There is no asserted DOP853-comparison acceptance
threshold in that validator.** These numbers therefore neither fail nor redefine
the separate 1 cm CPU/CUDA agreement test.

## Format, time and input limits

These are supported-input constraints, not accuracy tolerances. The controlling
paths are [orbit_seed.py](../python/orbit_seed.py), `validate_model` in
[orbit_dynamics.py](../python/orbit_dynamics.py), [orbit_native.py](../python/orbit_native.py)
and the raw transport reader in [orbit_worker.cpp](../src/orbit_worker.cpp).

| Input | Exact implemented rule |
|---|---|
| Seed header and payload | 52-byte header; compressed and canonical decoded lengths each at most 8,388,608 bytes; codec2 bit-plane intermediate length bounded by canonical length plus plane header plus 504 padding bytes; exact lengths and termination required. |
| Canonical structure | Nesting depth at most 48, at most 300,000 decoded values, each decoded list/map at most 100,000 entries; signed int64 or uint64 integer range. |
| Word values | `q0`, present and each of the six mask values are integers in `0..4294967295`; `q0` must be a subset of present; exactly two mask triples. |
| Frame/time metadata | Nonnegative GPST epoch; `abs(JD_TT - (2444244.5+(GPST+51.184)/86400)) <= 1e-8 day`, equivalent to 0.000864 s. This checks two stored labels, not satellite clock accuracy. |
| Physical model domain | Finite ordered interval containing zero; all coefficient series cover it; packed query start/end must lie inside it; native wrapper rejects queries outside it. Delivered R2 domain is `[-691200,604800] s`; the demonstration forward query remains `[0,604800] s`. |
| Frame coefficients | One to 4,096 exactly contiguous segments per series; degree 0..32; nine Q rows and three rows per body or R2 EOP block, with equal row lengths within each segment. |
| Frame inputs | Absolute base ERA rate at most 1 rad/s. R1 constant polar angles are bounded by π/2; R2 EOP coefficients must be finite and cover the domain, with no separate polynomial-angle magnitude bound. |
| Physical constants | Positive Earth mu, reference radius and AU; nonnegative Sun/Moon mu and SRP coefficient; finite signed RTN accelerations and Boolean shadow. R2 gravity degree integer0..12, finite square C/S arrays with zero upper triangle, C00=1 and every Sn0=0; positive finite c and Boolean relativity. R1 retains its five finite low-degree coefficient fields. |
| Initial state | Six finite SI components; epoch radius greater than reference Earth radius; nonzero angular momentum when any RTN acceleration is nonzero. |
| Packed numerical limits | Positive step; checkpoint stride and maximum query steps integers in `1..10000000`; checkpoint capacity integer in `1..1000000`; `ceil(max(abs(domain))/step) <= max_steps_per_query`. |
| Delivered numerical limits | Capacity 256. GNSS stride 120 steps/one hour; Chandra stride 480 steps/one hour. All R2 models declare maximum query steps 100,000. |
| Raw native transport | Its stride/work integer ceilings are `1e12`, larger than the packed profile's `1e7`; it does not independently implement every packed schema constraint. The packed entry point validates first. A command line is at most 1,048,576 bytes; batch count is 1..4,096. |
| Station | Latitude −90..90°, longitude −180..180°, height −500..10,000 m; mask −5° inclusive to 90° exclusive. |
| Query and feedback | Tick duration, chart radius, event step and tolerance are finite and positive; `0 < fine_s <= coarse_s <= 86400`; predicate thresholds nonnegative. Defaults are 1 s ticks, chart r0=1e9 m, 120 s event sampling and 0.01 s root tolerance. |

Elapsed query time and full GPST are stored as binary64, not integer display
ticks. Around the example epoch, absolute GPST has ULP
`2.384185791015625e-7 s`; near elapsed 604,800 s the elapsed field has ULP
`1.1641532182693481e-10 s`. These are representation spacings at those magnitudes,
not guaranteed clock precision. The readable timestamp displays milliseconds.

## Original UGTS address resolution is not physical tolerance

The exact source quantizer is `quantize` in [ugts.py](../python/ugts.py). It maps
the diagnostic chart to an address while the result retains the original full
position, velocity, Up and timestamp. Both key layouts encode the same tuple;
Morton interleaving does not increase its resolution.

Let `H=sqrt(E²+N²)`, `rho=log(H/r0)` and `theta=atan2(N,E)`.

| Field | Exact grid/resolution | Ideal nearest-node rounding consequence |
|---|---|---|
| 20-bit log radius | `rho ∈ [-20,0]`; spacing `Δrho=20/(2^20−1)=1.9073504518036383e-5` | `abs(delta_rho) <= 10/(2^20−1)=9.536752259018191e-6`. Reconstructed radius can differ by up to `H*(exp(Δrho/2)−1)`, about 9.536797734 ppm of H. |
| 18-bit theta | Circular spacing `2π/2^18=2.3968449810713143e-5 rad`, exactly `0.001373291015625°` | Wrapped angular rounding at most `π/2^18=1.1984224905356572e-5 rad`, exactly `0.0006866455078125°`. |
| 14-bit tick phase | Integer phase `k mod 16384`, with full winding retained separately; `k=floor(GPST/tick_s)` | The address tick floors time: residual in `[0,tick_s)` in ideal arithmetic. It is not nearest rounding and has no ±half-tick claim. With 1 s ticks the phase wraps every 16,384 s. Full query time is retained. |
| 12-bit separate hoop phase | Circular spacing `2π/4096=0.0015339807878856412 rad`, exactly `0.087890625°` | Wrapped rounding at most `π/4096`, exactly `0.0439453125°`. This is the separately declared hoop parameter, not a second satellite-position angle. |

These nearest-node expressions describe the specified mathematical quantizer;
floating evaluation is not a directed-rounding error proof. At default `r0=1e9 m`,
the defined horizontal chart spans approximately 2.061153622 m to 1e9 m. Outside
it, a key is explicitly undefined rather than wrapped into a false location.

For a horizontal distance of 40,000 km, the log-radius half-cell corresponds to
about **381.47 m** of radial address rounding; theta's half-cell corresponds to
about **479.37 m** of chord displacement if radius is held fixed. These separate
examples are not summed into a physical error budget. The actual orbital state
is never reconstructed from those quantized keys by this profile.

Consequently, **a key cell cannot be claimed as the system's physical tolerance**.
It describes address resolution after geometry was computed. A metre-accurate
orbit can share a much coarser key; an inaccurate orbit can also produce a valid
key. Neither event establishes the physical error of that orbit.

## Empirical forecast budgets remain separate

[validate_orbit_accuracy.py](../tools/validate_orbit_accuracy.py) sweeps 10 m,
100 m, 1,000 m and 10,000 m as descriptive budgets. Its report explicitly sets
`accuracy_thresholds_are_pass_criteria=false`. Exceedance is `error > budget`;
the first exceeding sample and previous sample are recorded, without a continuous
bound between them. No intrinsic physical tolerance is derived from bit width,
optimizer stopping, checksum validity, integrator agreement or event refinement.

The retained R1 seven-day maximum sampled discrepancies against the selected external
trajectories are about 7,402.96 m for G05, 532.58 m for C03, 1,237.24 m for C06 and
19,399.31 m for Chandra. These are measured outcomes, not failed functional tests.
Their full time dependence, reference-product limitations and precise sample
times are in the [accuracy report](../results/orbit_accuracy_cpu_final/accuracy_summary.json)
and [reference contract](ORBIT_REFERENCE_VALIDATION.md). Any claim that a query
is physically “within tolerance” therefore needs an explicitly chosen physical
budget and horizon, assessed against suitable independent evidence.

## Chosen 10 m physical acceptance for R2

The subsequent request to bring the prediction within tolerance is evaluated
against an explicit **10 m engineering budget**. It is not claimed to be an
intrinsic system constant. [assess_orbit_tolerance.py](../tools/assess_orbit_tolerance.py)
accepts a duration only when every tested position error is `<= budget_m` and
reference coverage is complete at the nominal cadence. The coverage check allows
at most `1.01` times the median reference gap, including the initial gap and final
distance to the requested horizon. An observed exceeding sample is a failure;
missing coverage without such a sample is `insufficient_coverage`. This is a
sampled acceptance rule, not an interpolation theorem.

On the **reused January benchmark**, all four R2 models meet 10 m at every tested
sample in the first 24 hours. They do not all meet the same budget for seven days:

| Object | Maximum first-24-hour error | 24 h at tested samples | Maximum seven-day error | Seven days at tested samples |
|---|---:|---|---:|---|
| G05 MEO | 1.057 m | PASS | 12.998 m | FAIL |
| C03 GEO | 5.304 m | PASS | 78.717 m | FAIL |
| C06 IGSO | 1.172 m | PASS | 8.084 m | PASS |
| Chandra HEO | 8.093 m | PASS | 25,635.95 m | FAIL |

These values come from [the frozen R2 CPU comparison](../results/orbit_accuracy_r2_cpu_verified/accuracy_summary.json).
The target future had previously been inspected for the R1 baseline, so this is
a reused comparative result. R2 fitting and model selection used only past target
samples. A separately frozen February 2 confirmation uses the unchanged past-only
selection rule and has its own result and coverage qualification; it must not be
silently merged with this January result or used to retune these frozen models.

Thus the 24-hour January sample test demonstrates a concrete improvement within
the chosen budget. It does not establish a universal 24-hour operating guarantee,
a continuous 10 m bound, or an all-object seven-day claim.

The **fresh February 2 confirmation** also meets 10 m at every tested sample in
the first 24 hours, using models frozen before the future reference comparison:

| Object | First-24-hour samples | Maximum first-24-hour error | Result at tested samples |
|---|---:|---:|---|
| G05 MEO | 288 | 3.071808499 m | PASS |
| C03 GEO | 288 | 4.654148101 m | PASS |
| C06 IGSO | 288 | 2.107834964 m | PASS |
| Chandra HEO | 288 | 0.289813081 m | PASS |

This is 1,152 complete first-day samples. The full confirmation comparison has
**7,489 samples**: 2,016 each for G05, C06 and Chandra, and 1,441 for C03. C03 is
missing 575 later grid samples, with a maximum 172,800 s (48 h) reference gap;
that later gap does not affect its complete first-day result. The larger
confirmation interval must retain that coverage qualification, and an observed
later error above 10 m is still a failure regardless of a gap elsewhere.

The [February CPU evidence](../results/orbit_accuracy_confirmation_cpu_verified/accuracy_summary.json)
records each actual sample time and curve hash. The [model freeze manifest](../examples/orbit/confirmation_models/freeze_manifest.json)
and identical selection-policy hash establish the selected past-only models.
This is a separate retrospective ephemeris confirmation, not proof of a live
receiver, public real-time availability of the fitted historical precise products,
or accuracy between every pair of samples. No failing seven-day result is hidden
by shortening the seed's computational domain.
