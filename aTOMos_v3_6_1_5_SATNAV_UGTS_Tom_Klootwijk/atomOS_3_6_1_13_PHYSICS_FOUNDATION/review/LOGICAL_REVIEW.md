# R13 logical review - 15 September 2026

The user requested actual physics that strengthens the aTOMos formalization
without unnecessary baggage. The result is a focused supplement to R12,
with established laws attributed to inspected primary/official sources and
new finite-model consequences derived explicitly. The parent is unchanged.

No algorithms, reference programs, numerical examples, tests, simulations,
benchmarks or physical experiments were run. PDF compilation/rendering,
source inspection, file hashes and Git operations are document delivery work.

## Review coverage

- Root reviewed the domain chapters, composed the minimal law-profile contract,
  and derived the exact finite midpoint solve, unique solvability and energy identity.
- The energy/mechanics reviewer independently checked electromagnetic
  polarization storage, harmonic signs, Poynting/source terms, passivity and
  radiation-pressure scope, as well as the midpoint derivation.
- The electromagnetic reviewer independently checked the midpoint and
  measurement chapters, including exact constants and the uncertainty theorem.
- The measurement reviewer independently checked the core and energy chapter,
  including units, port cancellation, free-energy derivatives and entropy signs.

This is internal independent derivation review, not external peer review,
proof-assistant certification or physical characterization. The detailed
conditional proof coverage is in `formal/DECISIONS_AND_PROOFS.md`.

## Corrections incorporated

1. Continuous and discrete balance residuals have separate symbols and meanings.
2. Applying the output certificate to a physical result explicitly requires
   its actual parameter vector to lie in the admitted data-compatible set.
3. Calibration uniqueness is stated for consistent noiseless data.
4. A finite Maxwell reduction must incorporate or eliminate algebraic
   constraints before being represented as an ordinary finite ODE.
5. Power-port conversion carries required units/frames, avoiding force/velocity
   identification based only on a shared variable name.
6. Dispersive material and thermoelastic coefficient changes retain their
   work/storage consequences; fixed-coefficient proofs do not cover arbitrary switching.
7. Discrete mechanical work and dissipation remain distinct from integrals
   along the exact continuous physical trajectory.

## Material findings

The exact midpoint step provides a complete finite expression under its stated
fixed passive-matrix assumptions. Its energy identity follows algebraically,
and the rational case needs only the inherited finite exact linear solve.
It is an explicit alternative profile, with no replacement of existing
backward Euler or orbital RK4 semantics.

The optical and thermoelastic additions close actual dependencies: stored
polarization and loss share a model; expansion stress and reversible thermal
coupling derive from one free energy; dissipative transfers are counted once.
The uncertainty certificate has finite smooth-domain hypotheses and separate
input, model and output bounds. It supplies no invented tolerance or device result.

The source references support the stated laws and conventions. Chosen material
parameters, model adequacy, executable implementation and physical performance
remain separate evidence requirements. No new satnav accuracy is asserted.
