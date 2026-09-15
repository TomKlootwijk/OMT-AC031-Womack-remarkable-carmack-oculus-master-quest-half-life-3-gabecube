# R13 measurement and constants contract

This is a logical extension of R12's word/event registry and physical operator lift. It adds no packet format, runtime or physical measurement result. No tests, simulations, numerical examples or experiments were run. The editable derivation is `docs/physics_measurement.tex`.

## Kept additions

| Addition | Reason it belongs in the foundation |
|---|---|
| Exact SI `c`, `h`, `e`, `k_B`, with existing seven SI exponents | Optical, electrical and thermal templates can use canonical rational coefficients directly. |
| Shared measured `alpha_fs` dependency for `mu0` and `epsilon0` | Retains `mu0*epsilon0=1/c^2` instead of manufacturing independent errors. |
| Explicit acquisition/transduction/quantization equation | Distinguishes an exact code from the physical quantity inferred through it. |
| Joint uncertainty and data-compatible sets | Shared offsets, clocks, gains and frames remain coupled across records. |
| Calibration rank and matrix-inverse domain proof | Establishes when the stated linear inverse exists without claiming calibration accuracy. |
| First-order covariance versus rigorous bounded enclosure | Prevents exact evaluation from relabelling an approximation as a physical guarantee. |
| Scoped output/tolerance certificate | Converts application tolerances into explicit, reusable mathematical obligations. |

No unrelated constant catalog, replacement WI table, domain checklist, generic device guarantee or new uncertainty opcode is added.

## 1. Constants and dimensions

The inherited dimension order is length, mass, time, electric current, thermodynamic temperature, amount of substance, luminous intensity. Use existing `Dim(Rat, d)` literals, reducing the following SI numerical coefficients canonically:

| Name | Exact coefficient before reduction | Dimension vector |
|---|---|---|
| `SI.c` | 299792458 | (1,0,-1,0,0,0,0) |
| `SI.h` | 662607015 / 10^42 | (2,1,-1,0,0,0,0) |
| `SI.e` | 1602176634 / 10^28 | (0,0,1,1,0,0,0) |
| `SI.k_B` | 1380649 / 10^29 | (2,1,-2,0,-1,0,0) |

Exact SI numerical definitions do not remove uncertainty of unit realizations. `e` denotes the positive elementary charge and must be distinct from the event bit. No value for measured `G` or `alpha_fs` is frozen here. When needed, bind the selected dated estimate and uncertainty in the specialization.

For positive `alpha_fs`, define `mu0 = 2*alpha_fs*h/(e^2*c)` and `epsilon0 = e^2/(2*alpha_fs*h*c)` through the same dependency. Their product is exactly `1/c^2` under that relation. Their dimensions are `(1,1,-2,-2,0,0,0)` and `(-3,-1,4,2,0,0,0)`. The old exact assignment of `mu0` is not imported into the current SI profile.

## 2. Measurement equation and dependency closure

For an averaging instrument:

`M = integral_[t-,t+] w(t) m(x(t), theta, t) dt`, with nonnegative `w` and integral `w = 1`.

`y = Q_Delta(M + d_M + eta)`.

`d_M` is discrepancy of the declared measurement model; `eta` is analogue noise; the quantizer includes its actual step, offset, tie rule, range and saturation. A count/integral instrument supplies its accumulation law instead of the averaging normalization. An instantaneous observation is a distinct profile.

Integrals require finite bounds and stated integrability; the trajectory and weighting require finite function templates or explicit external input bindings. No arbitrary unknown continuous signal is assumed to be a fully known finite literal.

An unsaturated nearest uniform quantizer permits `q=Q(v)-v`, `|q|<=Delta/2`. It does not imply a uniform independent noise process. Preserve raw codes and exact rational code-unit conversions. Finite bound endpoints and calibration coefficients may have exact encodings without making the physical measurand exact.

The existing R12 immutable registry/session dependency gains only the measurement template, acquisition weighting/accumulation convention, quantizer semantics and joint uncertainty/evidence definition. It retains the actual source records and distinct acquisition, availability and conversion-validity times. No source packet field is invented.

For affine clocks, `t_endpoint = a*tau_endpoint + b + delta_t_endpoint`, `a>0`. Share `a,b` throughout their declared calibration interval; elapsed-time subtraction cancels the common `b`. For a rigid frame realization, `x_B = R_BA*x_A + o_BA`, with `R^T R=I`, `det R=1`. Frame names alone do not establish physical mounting or alignment. Synchronizing coordinates from different acquisition times needs the selected dynamical/time-transfer model.

## 3. Joint set and calibration domains

Use finite profile parameters `p`, joint admissible set `U`, and observation map `F`. Then `U_y={p in U:F(p)=y}` and the output image is `Z_y={g(p):p in U_y}`. Repeated records constrain the same calibration parameters. Proved-empty `U_y` means inconsistency of the stated assumptions and observations; it must never yield a vacuous tolerance pass. An unresolved set remains unresolved. These sets are mathematical/evidence metadata, not newly registered scalar literal types.

For known `A` in the linear calibration `y_cal=A theta+epsilon`, unique noiseless parameters exist exactly when `rank(A)` equals its column count. If also `Sigma` is positive definite, `A^T Sigma^-1 A` is positive definite because its quadratic form is `(Az)^T Sigma^-1(Az)>0` for nonzero `z`. This establishes the GLS inverse formula's domain. Uncertain reference settings require uncertain `A` in the joint model. Nonlinear full-column-rank Jacobian supports a local regular inverse after choosing independent output components; neither global uniqueness nor nonlinear nonidentifiability follows merely from the local rank check.

`Sigma_z ~= J Sigma_p J^T` is first-order propagation for a nonlinear `g`, with cross terms intact. For affine `g`, it is the exact covariance transformation under the supplied covariance. A standard uncertainty is not a bounded worst-case error. In general, `g(E[p])` is not `E[g(p)]`.

## 4. Conditional output proof

Assume nonempty `U_y` contained in nonempty compact convex `K`, nominal `p_hat in K`, and `g_i` continuously differentiable on an open neighborhood of `K`. Suppose every `p in K` satisfies `|p_j-p_hat_j|<=r_j`, `|partial_j g_i(p)|<=L_ij` with finite nonnegative bounds. Integrating the derivative along the segment inside `K` proves:

`|g_i(p)-g_i(p_hat)| <= sum_j L_ij*r_j`.

The derivative bound must hold through the entire segment, so the certified domain cannot cross an undefined division or a nonsmooth branch. Conservative boxes may enclose correlated sets, although retaining correlations can tighten the result. Discrete/piecewise maps need image or branch enclosure.

If the physical target is `z_phys_i=g_i(p)+d_out_i`, `|d_out_i|<=b_i`, and delivered output satisfies `|z_del_i-g_i(p_hat)|<=rho_i`, the triangle inequality proves:

`|z_phys_i-z_del_i| <= B_i = sum_j L_ij*r_j + b_i + rho_i`.

Do not count a modeled effect both in `p` and `b_i`. A finite output rendering needs its own rounding/evaluation certificate. R12 binary64 execution does not acquire `rho_i=0`; an unevaluated exact term has exact nominal denotation, not necessarily a available numerical answer.

- `B_i<=tau_i` is sufficient for the declared absolute-error tolerance.
- `[z_del_i-B_i,z_del_i+B_i]` inside the allowed operating band is sufficient for containment.
- A wholly disjoint enclosing interval establishes exclusion.
- Overlap is unresolved, and failure of a conservative sufficient condition is not proof of physical failure.

All claims bind the same dependency versions, physical assumptions, acquisition interval, output quantity and tolerance. A physical discrepancy bound must be evidence or an explicit hypothesis; symbolic naming does not estimate it. The existing `UNKNOWN`, `MISSING_INPUT` and `RESOURCE_LIMIT` statuses remain available. No universal interval solver or proof checker is implemented here.

## 5. Primary source register

Accessed 15 September 2026. These sources support physical unit and metrology conventions. The aTOMos binding choices and the mean-value/triangle-inequality certificate are the explicit derivations above; this document is not a rebranded standard.

- **ME1** [BIPM SI defining constants](https://www.bipm.org/en/measurement-units/si-defining-constants): exact current SI numerical definitions.
- **ME2** [NIST CODATA constants table](https://physics.nist.gov/cuu/Constants/Table/allascii.txt): distinguishes fixed quantities from measured constants with uncertainty.
- **ME3** [BIPM SI Brochure, 9th edition, updated 2026](https://doi.org/10.59161/AUEZ1291), section 2.3.2: present status of vacuum permeability/permittivity and exact product relation.
- **ME4** [JCGM GUM-6:2020](https://doi.org/10.59161/JCGMGUM-6-2020), sections 6–7: defined measurand, measurement model, conditions and omitted effects.
- **ME5** [JCGM 100:2008](https://doi.org/10.59161/JCGM100-2008E), sections 5.1–5.2: correlated uncertainty propagation and its first-order basis.
- **ME6** [JCGM 100:2008, Amendment 1:2026](https://doi.org/10.59161/PPDI3267): significant nonlinearity may require changes to the estimate as well as its uncertainty.
- **ME7** [NIST policy on metrological traceability](https://www.nist.gov/calibrations/traceability): calibration-chain support for a result and its uncertainty, with fitness for the intended use a separate requirement.

Source contents were read. No prescribed numerical procedure, Monte Carlo method, calibration sequence or physical test was executed.

Independent-review clarifications: calibration uniqueness refers to consistent
noiseless data. Applying the output certificate to a physical result requires
its actual parameter vector to belong to the admitted data-compatible set;
nonemptiness alone is not evidence of that inclusion.
