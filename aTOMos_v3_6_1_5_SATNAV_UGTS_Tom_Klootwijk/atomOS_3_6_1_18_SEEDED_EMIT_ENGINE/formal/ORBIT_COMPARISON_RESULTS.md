# R18 matched orbital comparison: measured results

The existing aTOMos R2 solver closely agrees with Orekit solving the same frozen
physical problem. It does not demonstrate better satellite-position accuracy
than Orekit. Both implementations show nearly the same later external-reference
discrepancies, including substantial growth on some seven-day arcs.

## Inputs and admission

The eight cases retain the original January 2 and February 2, 2025 GPST seeds for
G05/MEO, C03/GEO, C06/IGSO and CHANDRA/HEO. No model, initial state, forcing,
frame, clock offset, training selection or reference row was fitted to the new
comparison. Both dates were previously inspected in R10, so neither is a fresh
blind R18 confirmation set. Retrospective provider products do not prove live
historical availability of the seed.

The protocol freezes 71 inputs, including model envelopes, canonical physical
model digests, reference products, native binaries and scorer source. Its SHA256
is `a7d30ae0e9c1bc85f7aa1c98caeef8e77d10714a34d7452405ca18c1fcd72d6d`.
Every frozen input was verified before and after native execution and scoring.
The final Orekit audit has `complete: true` and eight current case records;
its adapter hash matches the final source and all sixteen standard/tight state
file hashes were checked before scoring. Discarded pre-admission adapter output
does not participate in these results.

Orekit 13.1.8 / Hipparchus 4.0.3 supplies numerical propagation, the independent
Holmes–Featherstone gravity recurrence and relativity. Java adapters independently
implement the remaining frozen Sun/Moon, shadowed solar-pressure and RTN forces.
All engines use the same degree/order 12 EGM96 coefficients and raw frozen
frame/forcing series. Central gravity is included once. The final adapter uses
absolute Cartesian position/velocity propagation and a short-time motion check.
It does not exercise Orekit orbit determination, its full physical-model menu,
variational equations or an operational navigation pipeline.

The [Orekit numerical-propagator API](https://www.orekit.org/static/apidocs/org/orekit/propagation/numerical/NumericalPropagator.html)
documents integration and force-model configuration. The
[Holmes–Featherstone API](https://www.orekit.org/static/apidocs/org/orekit/forces/gravity/HolmesFeatherstoneAttractionModel.html)
describes its normalized-coefficient gravity recurrence. Exact executed binary
and source archive versions are pinned in `review/r18_orbit_java_dependencies.json`,
separately from these explanatory live documentation pages.

## External-reference position errors

All values below are metres. CPU denotes the existing native aTOMos R2 CPU
solver. Arc values cover all available strictly future samples up to seven days.
No position alignment or reference interpolation is applied. There are 2,016
samples in seven cases and 1,441 in February C03: 15,553 total. First-day values
use 288 samples per case. February C03 retains a 172,800-second reference gap.
CHANDRA's final sample precedes the exact seven-day GPST endpoint by about
51.184 seconds; precise offsets remain in the report.

| Epoch | Object | CPU 24 h max | Orekit 24 h max | CPU arc max | Orekit arc max | CPU arc RMS | Orekit arc RMS |
|---|---|---:|---:|---:|---:|---:|---:|
| Jan | G05 | 1.057 | 1.056 | 12.998 | 12.975 | 5.294 | 5.281 |
| Jan | C03 | 5.304 | 5.304 | 78.717 | 78.716 | 37.434 | 37.434 |
| Jan | C06 | 1.172 | 1.172 | 8.084 | 8.083 | 2.943 | 2.943 |
| Jan | CHANDRA | 8.093 | 8.093 | 25635.951 | 25635.961 | 5412.235 | 5412.237 |
| Feb | G05 | 3.072 | 3.069 | 71.800 | 71.773 | 33.113 | 33.099 |
| Feb | C03 | 4.654 | 4.654 | 100604.174 | 100604.175 | 39382.862 | 39382.863 |
| Feb | C06 | 2.108 | 2.108 | 7.629 | 7.630 | 3.494 | 3.494 |
| Feb | CHANDRA | 0.290 | 0.290 | 5663.182 | 5663.184 | 2055.685 | 2055.685 |

All eight first-day sampled maxima are below 10 m. This is a descriptive result
for these cases, not a certified system tolerance or continuous-time guarantee.
Longer horizons have very different limits: January CHANDRA reaches 25.636 km,
February CHANDRA 5.663 km and February C03 100.604 km. Orekit almost reproduces
these discrepancies, so substituting its integrator does not remove them.
The experiment does not uniquely identify force-model errors, unmodelled events
or reference limitations as the cause of any jump or large error.

The full standard and tight JSON summaries retain cumulative 1, 6, 12, 24, 48,
72 and 168 hour statistics, median/p95, exact nearest-horizon offsets, sampled
threshold exceedances and native CUDA physical-reference scores. Every engine
returns the exact decoded requested time: maximum engine/request offset is zero
seconds for all 15,553 rows. This establishes calculation alignment, not live
clock accuracy or the absolute accuracy of the reference time scale.

## Numerical state agreement and refinement

The next table reports maximum same-epoch inertial position differences over
each complete sampled arc, in **millimetres**. Orekit denotes the standard run.
Refinement compares standard and tighter Orekit integration of the same model.

| Epoch | Object | CPU–CUDA | CPU–Orekit | CUDA–Orekit | Orekit refinement |
|---|---|---:|---:|---:|---:|
| Jan | G05 | 0.043202 | 26.652946 | 26.696136 | 0.026221 |
| Jan | C03 | 0.040229 | 1.035783 | 0.995845 | 0.011058 |
| Jan | C06 | 0.014359 | 1.081491 | 1.095529 | 0.021503 |
| Jan | CHANDRA | 0.019398 | 9.973403 | 9.992799 | 0.064834 |
| Feb | G05 | 0.027756 | 26.759896 | 26.786545 | 0.018755 |
| Feb | C03 | 0.024485 | 1.027233 | 1.050839 | 0.006472 |
| Feb | C06 | 0.005661 | 1.009391 | 1.013778 | 0.027620 |
| Feb | CHANDRA | 0.220015 | 6.077876 | 6.297885 | 0.022174 |

The largest CPU–Orekit discrepancy is 0.02675989615163471 m; CPU–CUDA is
0.0002200149622629772 m. The largest Orekit refinement displacement is
0.00006483363349510388 m, for January CHANDRA. The GNSS refinement maximum is
0.00002762000226325821 m, for February C06.

Standard DP853 controls are 1e-6 m position absolute tolerance, 1e-9 m/s velocity
absolute tolerance and a 60 s maximum step. Tight controls are 1e-7 m,
1e-10 m/s and 15 s. Both use relative tolerance 2e-14. These settings are
numerical controls, not physical accuracy guarantees. All tight runs are also
scored against the same external positions in a separate full report.

The independent force audit evaluates 65 points per trajectory, 520 total,
against the retained Python R2 equations. Maximum acceleration discrepancy is
1.1157603309187458e-15 m/s². Agreement is checked at sampled states and does
not prove every possible force evaluation identical. The numerical discrepancies
measured here are small compared with the measured physical-reference errors.

Lossless one-bit word packing preserves the encoded seeds and operators.
Physical orbital propagation still uses finite-precision floating-point
arithmetic. Exact discrete-state execution and finite numerical agreement are
distinct guarantees; neither removes uncertainty in initial states, forces,
Earth orientation, observations or future operational events.

## Independent reference-product comparison

The following comparison uses GBM/WUM positions only at identical GPST epochs,
without fitting alignment. The final boundary row is absent in WUM, leaving
2,015 shared samples in five cases and 1,440 for February C03.

| Epoch | Object | GBM/WUM RMS (m) | GBM/WUM maximum (m) |
|---|---|---:|---:|
| Jan | G05 | 0.024361 | 0.077045 |
| Jan | C03 | 2.204400 | 3.575096 |
| Jan | C06 | 0.168937 | 0.585127 |
| Feb | G05 | 0.024472 | 0.055579 |
| Feb | C03 | 0.938938 | 1.962472 |
| Feb | C06 | 0.153155 | 0.344293 |

These observed cross-product differences are not a certified uncertainty floor.
Products can share observations and models. CHANDRA has no independent second
trajectory product here. Common frozen EOP and frame approximations remain in
the scores. The existing GCRS/ICRF orientation convention does not certify all
relativistic coordinate distinctions. Correlated discrete samples do not yield
a general confidence level or continuous-time bound.

## Runtime and scope

One native batch includes process startup, model initialization, queries and
teardown. GNSS CPU batches take 0.43–0.57 s and CHANDRA about 2.23 s; CUDA takes
21.2–24.0 s and 84.6–87.5 s respectively. These diagnostic single trials show
no GPU benefit for this workload/lifecycle. Orekit internal timings have a
different boundary, so no cross-library speed ratio is inferred. Other aTOMos
word or spatial benchmarks cannot establish orbital performance.

[NASA NAIF describes SPICE as an observation-geometry system](https://naif.jpl.nasa.gov/naif/index.html).
The separate SPK experiment measures interpolation of a supplied frozen
forecast, not independent prediction of a satellite from the initial state.
Neither experiment establishes general superiority over space agencies or
their complete navigation systems. The current result supplies reproducible
external numerical comparison and concrete accuracy-versus-horizon evidence
for these eight retained seeds.

## Reproduction and artifacts

- `review/r18_orbit_protocol.json`: frozen inputs and sample selection.
- `review/r18_orekit_numerical_audit.json`: final adapter/dependency/state hashes,
  force checks and refinement results.
- `review/orbit_comparison/matched_forecast_summary.json`: complete standard scores.
- `review/orbit_comparison/matched_forecast_tight_summary.json`: complete tight scores.
- `review/orbit_comparison/request_*.json`: exact requested epochs and model bindings.
- `review/orbit_comparison/native_<cpu|cuda>_*.json`: all native states and timing scope.
- `review/orbit_comparison/orekit_*.json`: audited standard/tight states.
- `tools/compare_orbit_references.py`: frozen scorer; no refit operations.
- `tools/plot_orbit_comparison.py`: plot generator that verifies the completed
  audit, source hashes and recomputed errors before rendering.
- `docs/figures/r18_orbit_forecast_{jan,feb}.{pdf,png}`: two standalone four-panel
  scientific figures, with shared per-object scales and visible reference gaps.
- `review/r18_orbit_forecast_plots.json`: plot source/output hashes.

The frozen protocol and scorer were not changed when writing this results
document. The reviewed figures show the near-overlapping engine curves and
retain the large later-reference discrepancies rather than hiding them.
