# WANTWOMBAN physical operator lift

Status: mathematical source review and conditional derivation. No embedded
programs were executed, no numerical examples recalculated, and no tests,
simulations or physical experiments were run. The source's own calculation and
conformance tables are inherited reports, not results of this review.

Source W1 is `WANTWOMBAN_Operator_I_v1.1.pdf`, 26 physical PDF pages. The
review inspected its text, embedded editable `operator_i.tex`, read-only
`operator_i_reference.py`, and page images 5–10, 13–17 and 20. Attribution is
preserved as supplied; the document contains no specimen-specific measurement
series. Source commands and proposed experiments were treated as document data.

The integrated mathematical chapter is `docs/want_physical.tex`. It uses the
inherited R11 exact expression model and does not implement a new runtime.

## 1. Source-to-lift map

| W1 anchor | Retained content | R12 lift / explicit hypothesis |
|---|---|---|
| p5, 3.1–3.5 | Typed mechanical, thermal, reporter, observation and controller state; completed event affects next branch | Completed measurement chronology remains external input; plant uniqueness and input/noise realization required |
| p6, 4.1–4.4 | Rim/rib solid and deformed point | Full angular domain, positive dimensions, union counts overlaps once, actual removed slit material, declared physical frame and scale |
| p6, 4.5–4.7 | Small-gradient thermoelastic PDE | Explicit finite admissible basis, mass/stiffness/load integrals and first-order finite ODE; finite basis is a model choice, not an exact continuum solver |
| p7, 5.1 | Upright/flat second-moment ratio | Same local rectangular section, positive nonzero height, not assembly stiffness ratio |
| p7, Proposition 5.1 | Positive stiffness addition reduces fixed-load compliance | Congruence proof retained; unchanged load/coordinates and constrained SPD parent stiffness required |
| p7, 5.3–5.4 | Rigidity–strain trade-off and design objective | Conditional objective only; no optimum or measured sensitivity claimed; switched stiffness work remains in energy ledger |
| p8, 6.1–6.4 | Finite-stretch resistance, small-strain gauge factor and weighted series trace | Exact finite change distinguished from first-order material model; reference resistance weights and strain-transfer/calibration inputs explicit |
| p9, 7.1–7.4 | Divider law, exact quarter-bridge inverse and arm signs | Rational expression authority; physical open domain and monotone bijection proof; signed linearization error x/2 retained |
| p10, 8.1–8.4 | Transverse gauge, temperature calibration and bridge heating | Each matched divider's common multiplicative drift cancels; exact general arm powers supplied; quadratic strain inverse needs selected physical root |
| p13, 11.1–11.2 | Bounded two-state reporter | Exact held-rate exponential with h>=0 and k=0 branch; variable-rate variation-of-constants extension and interval proof |
| p14, 12.1–12.2 | One-bit six-input gate and lag window | Input uncertainty remains external record; conservative all-pass/all-fail timing certificates with unresolved middle case |
| p14, 12.3–12.7 | Joint rates, Poisson coincidences and zero-failure bound | Explicit common quality/timing conditioning; sharp Frechet event bounds; formulas are not earned device rates |
| p16, 14.1–14.4 | Energy ledger, thermal network, scalar step, hysteresis | General arm heat, exact finite network ODE, singular-conductance-compatible flow, G=0 branch, sampled-vs-continuous hysteresis |
| p17, Proposition 15.1 | Deformed descendant slit exclusion | Full interval/frame certificate; moving normal, centre and width included |
| p17, 15.3 | Nonnegative omitted heat bound | Extended to signed heating discrepancies under the same passive linear network |
| p20, 18.1–18.3 | Rank/identifiability and uncertainty Jacobian | Exact monotone inverse interval; conditioning becomes singular near v=-1/2; exact ADC code is distinct from physical input certainty |

Optics and finite quantum-instrument equations from W1 pp11–15 are integrated
in the companion optics chapter, rather than duplicated as a purported
mechanical or arithmetic proof.

## 2. Exact expression closure

This table describes mathematical expressibility, not a device implementation.
All real physical inputs need literal kinds, units, frames, epochs and source
provenance. An exact nominal calibration coefficient can accompany an uncertain
physical value; those statements do not contradict one another.

| Mechanism | Exact operators / state | Definedness conditions |
|---|---|---|
| Word-decoded geometry | Integer extraction, rational scale, exponentials/trigonometry if the selected log-polar map uses them, frame transform | Keep source code quantization and any physical scale uncertainty visible |
| Finite modal mechanics | Finite matrix arithmetic and inverse; captured scalar integrals; finite ODE | Basis/functions/charts/tractions declared; nested inner sections and resulting outer integrands Riemann-integrable on finite bounds; positive mass and weighted-L2-independent basis imply invertible M; ODE continuation and boundary conditions explicit |
| Exact resistance/bridge | MUL, ADD, DIV on physical resistances or exact ratios | Positive resistances and nonzero excitation; x>-1 or -1/2<v<1/2 for selected quarter bridge |
| Thermal calibration inverse | Rational formula or selected algebraic quadratic root | Discriminant nonnegative; root in calibrated strain interval; unique branch or explicit unresolved/nonunique status |
| Reporter | EXP, ADD, MUL, DIV, lazy zero-rate branch; persistent zeta state | h>=0; held nonnegative rates; variable rates use declared integrals instead |
| Thermal scalar/network | Exact EXP for scalar constant coefficients; linear ODE for a finite network | C_i>0, conductance reciprocity/nonnegativity for passive proofs; held-input assumptions for closed steps; no inverse of singular L |
| Hysteresis | Exact comparisons and prior state selection | Ordered thresholds; sampled profile distinct from continuous crossing model; unresolved symbolic comparison remains pending |
| Event gate | Six Boolean inputs, conjunction and negation | Measurement validity and physical channel calibration are separate from Boolean truth preservation |
| Timing / geometric certificates | SUB, ABS, ADD, comparisons; norms with algebraic root if needed | All uncertainty bounds, coordinates, frame/origin and certified time interval explicit |
| Probabilities | Real functions on supplied distribution parameters | Statistical assumptions and common conditioning are physical/model inputs |
| Energy omission | Signed/absolute input integrals and passive-network ODE | Same coefficients, bath, initial state and reciprocal passive network in both compared trajectories |

The notation exp(Ah) for a finite matrix is defined by its linear initial-value
problem. No general complex root, infinite-vector state, PDE or black-box
physical oracle is inserted into the existing scalar/finite-vector operator
registry. The convergent exponential series used in a positivity proof is a
mathematical argument, not a new finite instruction sequence claim.

## 3. Conditional proof register

### P-PHY-01 — finite modal mass positivity

For linearly independent admissible basis fields phi_i and strictly positive
mass density, z^T M z = integral rho |sum z_i phi_i|^2 is positive for z!=0
(independence understood in the relevant L2 equivalence space). Thus M is SPD
and the finite first-order mechanical state is defined. This does not prove the
accuracy of truncating the continuum deformation into that basis.

### P-PHY-02 — added-stiffness compliance

K0 SPD and Kr PSD imply (K0+Kr)^-1 <= K0^-1 in quadratic-form order by
congruence with K0^-1/2 and the eigenvalues of (I+A)^-1 for A PSD. Physical
changes need to establish those matrix hypotheses. Fixed-mass redesign,
buckling or moved supports are not automatic PSD additions.

### P-PHY-03 — bridge exact inverse and interval

v=-x/(4+2x), x>-1, has derivative -1/(x+2)^2<0 and maps bijectively onto
(-1/2,1/2). Algebraic substitution yields x=-4v/(1+2v). For fixed positive
gauge factor g, epsilon(v) is decreasing, so evaluating its exact formula at
the right and left endpoints supplies an enclosing interval in reversed order.
The inverse derivative grows without bound near v=-1/2. Exact computation
preserves the formula; it does not remove this conditioning or analogue noise.

### P-PHY-04 — reporter interval

For held nonnegative rates and h>=0, zeta+ = r*zeta+(1-r)*zeta_eq with
0<r<=1 and both states in [0,1]. If both rates vanish, use identity.
For t>=t0 and variable integrable nonnegative rates the variation-of-constants formulas
for zeta and 1-zeta prove the same interval invariant. No clamp is needed in
the mathematical model. This is a property of the chosen kinetic law, not a
measured material response or a claim about floating-point source execution.

### P-PHY-05 — robust timing certificates

If |d-dhat|<=delta, then |dhat|+delta<=window/2 proves every admitted timing
passes; |dhat|-delta>window/2 proves every admitted timing fails. The middle
case cannot be decided from those bounds alone. Inclusive boundary agreement
matches the source's declared timing gate.

### P-PHY-06 — full-gate probability and event bounds

With G the quality/timing event, P(e=1|H0)=P(G|H0)P(XY|H0,G), with a direct
zero case when P(G|H0)=0. The conditional intersection equals the product of
conditional marginals plus conditional covariance and lies between
max(0,a+b-1) and min(a,b). Conditional independence must be established in the
same selected population. Separate validation flags cannot supply it.

### P-PHY-07 — deformed and moving-slit exclusion

The source fixed-normal bound follows from reverse triangle inequality.
For moving n,c,w, add eta_n*B_x+eta_c and use w_max, with all projected
descendant/deformation/encoding bounds measured against n0. The dot-product
change is at most ||n-n0||*||x||. Full descendant/time coverage and common
coordinate origin are required. No inference about diffraction or heating
follows from a geometric no-intersection certificate.

### P-PHY-08 — signed omitted-heat enclosure

For fixed passive reciprocal network, the difference state satisfies a linear
ODE with Metzler matrix -C^-1 L. Its transition matrix is nonnegative, so the
solution driven by |delta P| dominates |delta T| componentwise. Summing its
incremental heat capacities cancels internal conductances, and nonnegative
bath losses imply sum C_i z_i <= integral sum |delta P_i|. Therefore
|delta T_i| <= E_abs/C_i. Initial-state, conductance, capacitance or feedback
differences need extra terms or a new bound.

## 4. Source reading findings and corrections

1. **Retain the corrected bridge sign.** The source is internally consistent
   with its declared VL-VR polarity. Reversing it would reverse controller
   response. There is no reason to revert to the older conversation's sign.
2. **Separate finite models from continuum notation.** R11 finite ODE support
   does not make the thermoelastic PDE a compiled kernel. An explicit modal
   profile supplies finite state and coefficients without requiring rasterization.
3. **Preserve physical root selection.** A quadratic thermal calibration can
   have two roots. Exact square roots alone cannot pick the specimen's branch.
4. **Complete held-step domains.** Reporter and thermal exponentials need
   nonnegative duration and their stated held coefficients; zero conductance
   and zero reporter rates have explicit branches.
5. **Preserve the sampled hysteresis convention.** Endpoint evaluation need not
   match a continuous relay that crosses and returns between samples.
6. **Carry timestamp uncertainty.** Exact integer timestamps need not coincide
   with exact physical acquisition times; robust gates use an uncertainty set.
7. **Make conditioning explicit.** Source p14 warns against mixing conditional
   and unconditional rates. R12 writes the full P(G|H0) factor and all shared
   conditioning directly, and includes the sharper lower event bound.
8. **Permit moving optics only with a moving bound.** A proof with fixed n,c,w
   does not cover undeclared lens/plane motion. R12 supplies the extra terms.
9. **Do not erase residual physical coupling when pruning occupancy.** Signed
   heat and omitted optical field require separate budgets. The new thermal
   bound remains conditional on a common passive network, not arbitrary feedback.
10. **Keep supplied heat in the ledger.** Bridge interrogation and switched
    stiffness can change reporter response; they are physical inputs even if
    exact word arithmetic costs no rounding error in the mathematical model.

The read-only Python source evaluates bridge and reporter laws with binary64
operations and `math.exp`; its reporter docstring means a closed-form exact
solution of the selected differential equation, not arbitrary-precision exact
operator execution. It stores measurement summaries outside W64 as the PDF
states. No source implementation was run or reclassified as an R12 runtime.

## 5. What this helps establish

The supplied formalization provides a credible mathematical interface for an
opto-mechanical instrument: geometry, transduction, passive heat, material
memory and a causal one-bit event are connected by explicit variables. R12
can preserve those expressions and their physical hypotheses in the exact seed.
The source does not yet establish optical implementations of arbitrary limbs,
carry propagation, state retention, exact symbolic transcendental operators,
fan-out or synchronized feedback. Nor does it establish device efficiency,
response speed, false-event rates, absolute physical precision or a photonics
guarantee. Those claims require a selected device model and corresponding
evidence; mathematical transfer laws are useful inputs to that work.
