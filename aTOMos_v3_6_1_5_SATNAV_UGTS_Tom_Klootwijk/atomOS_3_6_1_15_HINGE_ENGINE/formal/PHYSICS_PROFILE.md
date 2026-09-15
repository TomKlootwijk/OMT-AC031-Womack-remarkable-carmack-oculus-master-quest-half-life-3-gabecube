# R14 adoption of the physical-law profile

The following R13 law-profile and linear mechanical step are adopted in R14.
The current integration profile is XOP-UNIFIED-FIELD-R1. Its common nonlinear
field/thermal state is in UNIFIED_COUPLING.md; its additional finite field step
is defined completely in docs/field_step.tex. This file retains the R13
mathematical definitions and their lineage; it makes no new runtime claim.

# XOP-PHYSICS-R1: minimal physical specialization contract

Status: normative mathematical record and template definitions. This is not a
new parser, runtime, opcode set or physical certification. All operators are
in inherited XOP-R1. R12 and its earlier source corpus remain unchanged.

## Required record

Each selected application declares the following fields. A field can contain
an explicit empty set when it is inapplicable, with the reason recorded.
Only dependency closure needed by the application is imported.

| Field | Required meaning |
|---|---|
| profile | Qualified namespace, version, parent profile and exact dependency identities |
| quantities | State/input/output types, SI dimensions, frame and time conventions |
| initial_boundary | Initial values and required mechanical/field/thermal boundary data |
| parameters | Exact nominal representation, source binding and joint physical uncertainty |
| balances | Applicable conservation/production laws with full bodies and domains |
| constitutive | Material/actuator/detector equations closing those balances |
| reductions | Fixed basis, lumped/scalar assumptions, omitted effects and applicable regime |
| evolution | Continuous model and separately selected finite update with step-domain conditions |
| observations | Acquisition interval, measurand equation, calibration and quantizer/noise meaning |
| ports | Signed power, heat and other boundary exchanges with units and shared ledger identity |
| claims | Output quantity, operating/input domain, exact identities, approximation or uncertainty bounds |
| evidence | Definition / adopted physical law / derived identity / constitutive assumption / measured parameter |

Every imported law has a ProfileId, typed arguments, complete expression body,
boundary terms, hypotheses and source or derivation reference. The record is
finite. No arbitrary real literal, infinite state, unspecified material oracle
or implicit general differential-algebraic solver is added to XOP-R1.

Dimension checks and a correct symbolic derivation establish mathematical
properties under hypotheses. They do not establish that a specimen satisfies
the constitutive assumptions or that a calibration parameter is measured exactly.
Unresolved domains retain inherited UNKNOWN/non-value behavior; they are not
silently converted into a false event or zero coefficient.

## Existing interface bindings strengthened by R13

- `t_lambda`, `H_z_lambda`: select Maxwell/material/boundary/reduction profile.
- `P_abs` and `P_heat`: shared nonduplicating ledger with stored excitation and outputs.
- `M,C,K`: fixed basis, boundary conditions and consistent mechanical energy definition.
- `T,zeta,a`: material storage, coupling, dissipation, temperature and rate assumptions.
- ASA/NA and JK: select actuator/control state; do not become physical absorption or force by name.
- WI/calibration: bind acquired code to time, physical measurand, parameter registry and joint uncertainty.
- XOP graph: capture complete inputs, template bodies, assumptions and requested output accuracy.

## New finite template: PHYS-MIDPOINT-LINEAR-R1

Arguments `(q,v,M,C,K,h,fbar)` and outputs `(qplus,vplus,Win,Qd)`.
All coordinates are length-valued in a fixed finite modal basis; all matrices
are uniform under the specified units. Mixed coordinate dimensions need the
existing block/tuple convention.

Domain: `M=M^T` positive definite, `C=C^T` and `K=K^T` positive semidefinite,
`h>=0`, fixed coefficients/reference over the step, all inputs defined.

```
A = M + (h/2) C + (h*h/4) K
b = (M - (h/2) C - (h*h/4) K) v - h K q + h fbar
vplus = SOLVE_LINEAR(A,b)
qplus = q + (h/2) (vplus+v)
vbar = (vplus+v)/2
Win = h DOT(vbar,fbar)
Qd = h DOT(vbar,C vbar)
```

This is declarative expression pseudocode, not a program executed for the
release. Matrix/vector products expand into existing finite contractions.
No new operator ID is allocated. At h=0 the result is the identity with zero
ledger increments. Positive definiteness of A proves unique solvability.
Rational inputs give rational outputs; ordinary exact field semantics apply.

For `E(q,v)=(v^T M v + q^T K q)/2`,

`E(qplus,vplus)-E(q,v) = Win-Qd`.

The proof uses quadratic polarization and cancellation in the midpoint update;
it is given in `docs/physics_core.tex`. The discrete work/heat are not asserted
equal to continuous trajectory integrals. Parameter switches have their own
storage/work increment before the fixed-coefficient step. The profile is an
explicit alternative to inherited backward Euler and never silently replaces it.

## What is intentionally not imported

No replacement theory of gravity, general quantum-computing stack, new
particle model, all-purpose PDE solver, unrelated application library or
automatic material calibration. Existing orbital relativity/frame equations
remain in the parent; this supplement changes no satellite accuracy claim.
New material/field states are introduced only when they close an actual
energy, constitutive or measurement dependency already present in R12.
