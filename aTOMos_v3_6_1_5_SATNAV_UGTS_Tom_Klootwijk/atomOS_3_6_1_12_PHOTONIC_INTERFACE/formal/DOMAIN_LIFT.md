# Exact-domain lift of the numerical profiles

This is a mathematical specification and conditional derivation, not a new executable runtime. R10 remains the dated numerical reference. No tests, benchmarks, simulations or physical-accuracy reruns are performed for this work. The complete equations and proofs are in `docs/exact_domains.tex`; this file records the operator closure and source map.

## Meaning of exact

An imported finite binary64 payload denotes its exact dyadic rational, with its original bit pattern retained separately when byte identity matters. A rational decimal specification, the exact constant pi, and a rounded runtime constant are distinct atoms. Choosing an exact decimal or pi in place of a stored approximation is a semantic change and must be identified. Signed zeros are identical as real numbers but distinct serialization values. The lifts below remove arithmetic rounding; they do not establish bit-equivalence to R10, preserve every old branch decision, repair model error, or give arbitrary future ephemerides.

Use integers and rationals for finite addresses, times, coefficients and rational algebra; real algebraic extensions for roots and nonsingular rational matrix solves; and explicitly denoted real transcendental expressions for sin, cos, exp, log, atan and atan2. Finite expressions, finite recurrences, piecewise expressions and implicit solution operators are different constructors. `FLOW` and `ROOT` require their defining equations, domain and uniqueness/existence conditions. Naming them is not a closed-form algorithm.

Comparisons have mathematical meaning, but a general transcendental comparison is not thereby an executable decision procedure. A semantic guard can be true or false; an evaluator without a proof must retain an unresolved obligation. Rational/algebraic comparisons are decidable in their exact domains. Floor is specified by the unique integer `n <= x < n+1`; ambiguous equality at a boundary cannot be decided by an invented epsilon. Piecewise branches are lazy: an inactive term's singular denominator is not evaluated.

## Closure matrix

| Operator family | Explicit construction | Domain and obligation | Exact preservation or distinction |
|---|---|---|---|
| Coefficient segments | Finite Chebyshev sum / Clenshaw recurrence and formal derivative | Positive interval length; timestamp covered; highest-index containing segment wins a shared endpoint | Polynomial identities hold exactly; no inferred continuity across separately fitted blocks |
| Earth frame | `M=P(xp,yp) Rz(a) Q`, product-rule derivative | Defined coefficient segments and angles | P and R are orthogonal; M is orthogonal only if the stored polynomial Q is separately proved orthogonal |
| Earth gravity | Finite Cartesian Cunningham recurrence and exact gradient | Positive Earth radius; nonzero position; declared external-Earth domain | Dual differentiation is the exact derivative; finite complex-step sampling is a different operator |
| Other orbital forces | Indirect third bodies, cylindrical-shadow SRP, RTN, Schwarzschild | Active denominators nonzero; RTN angular momentum nonzero when used; branch at shadow boundary declared | These are the given force model, not a claim of complete physical forcing or energy conservation |
| Discrete orbit | Four explicit RK4 stages, canonical signed lattice and final fractional step | Every intermediate stage in the force/time domain | Deterministic canonical query independent of cache history; RK4 is not the exact continuous flow or a reversible group |
| Continuous orbit | IVP/integral operator `FLOW(F,t0,y0,t)` | Local continuity/Lipschitz conditions or declared piecewise event concatenation | Unique maximal local solution under stated assumptions; no global existence, closed form or forecast accuracy inferred |
| Station geometry | WGS84 origin, ENU rotation, norm, azimuth/elevation and rates | Valid station chart, positive range; azimuth needs nonzero horizontal component | ENU rotation preserves norm; orbital product is simultaneous geometry, without light-time correction |
| Live light time | Broadcast clock iteration and Earth-rotation range iteration; separate implicit fixed points | Positive speed of light and the relevant contractions for uniqueness | Finite iterations are defined exactly but do not equal their fixed points by definition |
| UGTS chart/keys | Log radius, theta, OTAN2 ratio, nearest-bin quantization, contiguous and scheduled Morton permutations | Positive radius; named origin/zero-ratio cases; source chart interval; exact boundary comparisons | Codecs invert the integer tuple, not discarded continuous geometry; both time remainder and winding reconstruct the tick |
| Support and topology | Sphere/cone signed distance, finite translated sweep bound, separate half-turn/reflection profiles | Unit axis, positive dimensions; explicit seam and wrap conventions | Conditional 1-Lipschitz sweep enclosure; two topology maps remain different operators |
| Gregorian/phase | Calendar integer day formula, quotient/remainder, exact rational fractional time | Valid Gregorian fields and positive period | Year and absolute time continue across phase cycles; calendar periodicity does not imply orbit periodicity |
| SATNAV correction/solve | Active masks, whitened range Jacobian, Givens/Householder QR, back substitution, finite Gauss-Newton iteration | Positive sigma; native range >1 m versus Python reference range >0; independent four-column rank; configured stopping predicates | Exact QR solves the linearized least-squares problem on their common domain; nonlinear convergence is not guaranteed |
| Live GNSS | Kepler equation/finite Newton recurrence, harmonic orbit, clock, reception rotation, Klobuchar, Saastamoinen and correction feedback | Healthy in-age matching ephemeris, `0<=e<1`, atmosphere/geodetic domains, declared finite limits | Kepler root is unique; the finite iteration and whole outer positioning loop have distinct statuses and limits |
| CGK mechanics | State-dependent symmetric stiffness/force, backward-Euler 3x3 linear system, finite 64-pass Jacobi diagnostic and separate ideal symmetric eigenproblem | Positive mass; invertible step matrix; signed damping/stiffness remain allowed; Jacobi stopping policy separately required | Rational data close under the nonsingular step; passive fixed-operator energy decreases only under explicit positivity assumptions; finite spectral diagnostics are not exact roots by definition |

## Reference map

The reference files below are read from the preserved sibling `atomOS_3_6_1_10_ORBIT_SEED/`. R11 includes the old equations as dated reference text; it does not rename those numerical implementations as exact implementations.

- `python/orbit_dynamics.py`: `segment_value`, `frame_matrix`, `state_to_ecef`, R1 acceleration and finite coefficient construction.
- `python/orbit_precision.py`: `precision_frame`, `harmonic_potential`, `precision_acceleration`, `_gravity`, `_chebrows`, `_precision_force`; `include/orbit_core.hpp` supplies the native Cartesian derivative and RK4 path.
- `python/orbit_query.py`: `station_geometry`, `chart_record`, `predicate_word`, ordered schedule and event-search geometry. Its 1 micrometre horizontal diagnostic threshold and elevation-rate denominator floor are explicit numerical policy, not intrinsic geometric singularities.
- `python/geodesy.py`: WGS84 forward/inverse and ENU definitions. The inverse currently uses a finite 20-step latitude recurrence and a pole convention.
- `python/ugts.py`: `wrap`, `quantize`, `phase_winding`, both codecs, prefix bounds, sphere/cone support, sweep interval, perturbation records, topology and source OTAN2.
- `include/satnav_core.hpp`: online Givens QR, active masks, rank/stopping and residual status. `python/reference.py` supplies the distinct Householder algorithm for the same linearized system.
- `python/live_gnss.py`: full GPS calendar/week selection, broadcast Kepler and harmonic orbit, clock, three emission-clock iterations, four reception-range iterations, ephemeris validity, atmospheric models and observation preparation.
- `python/live_pipeline.py` and `python/live_native.py`: carried receiver estimate and finite outer correction loop.
- `include/coupled_kernel.hpp`, `python/coupled.py`, and `docs/COUPLED_CONTRACT.md`: literal geometry-word feedback, signed mechanical coefficients, pivoted linear solve, eigensystem and failure-commit ordering.

Precise retained mathematical anchors: `sec:orbit` (coefficient/frame/force/RK4/station/key subsections); `sec:live-orbit`, `sec:live-clock`, `eq:live-transmit-time`, `eq:live-earth-rotation`, `sec:live-ionosphere`, `sec:live-observation-equation`, `eq:live-outer-feedback`; `sec:coupled`, `eq:circleplus`, `eq:coupled-mechanics`, `eq:physical-eigenmatrix`; and the retained calendar section. The R11 chapter reproduces the defining numerical operators and gives a domain reason for each rather than delegating its meaning to a runtime call.

## Proof obligations governing improvement

1. Specify whether a rewrite preserves exact mathematical value, finite-iteration behavior, branch/status behavior, or serialized bytes. These are different relations.
2. Preserve all active-domain assumptions and endpoint/tie conventions. A valid cancellation may change the domain if a cancelled denominator can be zero.
3. Replace only subexpressions covered by an identity or proved invariant. Reusing a frame/coefficient result is valid for the same immutable model, timestamp and branch selection.
4. Keep continuous flow and finite discrete stepping separately named. A consistency/order theorem does not identify their outputs.
5. Keep exact model evaluation, parameter/source uncertainty, future unmodelled forcing, and empirical forecast error separate.
6. Return a defined failure or an unresolved proof obligation for unsupported operations; do not assign a numerical value to an unproved transcendental comparison or a nonunique implicit root.

Logical completion means the expression graph and its domains are specified. It does not mean all implicit/transcendental operators now have terminating exact evaluators, nor that a fresh numerical implementation has been executed.

The native CGK word-first failure is represented in the exact graph by one atomic tagged next tuple: the newly computed word, old mechanical state/time and chart-history fields, and `failed=true`. A lazy failure branch does not demand the singular matrix inverse. Successful steps update history from the current before-state chart. This preserves the intended transition relation without requiring partial commits of an undefined mathematical operator. Nonreal roots of the general damped quadratic eigenproblem need an explicit complex extension; only the symmetric real stiffness spectrum is within the stated real spectral domain.
