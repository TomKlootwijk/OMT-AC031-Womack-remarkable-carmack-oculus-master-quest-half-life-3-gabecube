# Coverage and proof map

This is a logical coverage map for the 3.6.1.11 specification. A row means that
the named definition and argument are supplied, not that an exact arithmetic
engine or proof checker has been implemented. Document rendering is a separate
delivery check. No numerical tests or simulations are part of this release.

| Requirement | Delivered definition / derivation | Principal condition or boundary |
|---|---|---|
| F01 | `docs/exact_core.tex`, bits/value hierarchy, literal imports and dimension typing; attitude/domain input maps | Exactness is relative to declared input values; uncertainty is independent |
| F02 | Core canonical stream, scoped records and one-bit-plane envelope; `formal/OPERATOR_CATALOG.md` | Inverse proof is for the grammar; a future parser must implement it faithfully |
| F03 | Core limb and bit arithmetic, rationals, selected algebraic roots, elementary and calculus denotations; catalog | Arbitrary-size resources; algebraic decisions in principle; no general transcendental oracle |
| F04 | Core DELAY/state recurrence and finite-prefix uniqueness; strategy authoritative-root induction | Synchronous old-state reads; defined domains; chronological input bindings |
| F05 | `docs/exact_madgwick.tex`, `formal/MADGWICK_DERIVATION.md` | Selected original report equation profile; explicit unit/frame, bias/reference order and zero branches |
| F06 | `docs/exact_domains.tex`, coefficient/frame/gravity/force/RK4/IVP derivations; retained `docs/orbit.tex` | Discrete recurrence differs from continuous flow; fitted frame orthogonality is a separate obligation |
| F07 | Domain station/ECEF/ENU geometry and attitude mounting composition | Synchronized time, nonzero range, chart singularities and measured alignment |
| F08 | Core two ordered ASA/NA sets and synchronous JK; domain signed CGK step; retained coupled chapter | Whole-word absorption; no passive-energy inference for arbitrary signed coefficients |
| F09 | Domain original UGTS charts, both codecs, support/topology and integer calendar/winding; retained calendar body | A key inverts an integer address, not discarded continuous coordinates; cycles do not imply orbital periodicity |
| F10 | Domain least-squares/QR, finite correction loops, Kepler/broadcast clock, atmosphere and reception geometry | Rank, ephemeris and branch domains; finite iteration is distinct from a root/converged solution |
| F11 | `docs/exact_strategy.tex`, core proof rules and `formal/STRATEGY_REVISIONS.md` | Accepted local identities preserve denotation, domain, types, chronology and observations |
| F12 | Conditional propositions throughout; error identity, finite-graph and input-counting arguments | Human-readable reasoning, not machine-checked proof; no new empirical performance or physical bound |
| F13 | Editable master/new chapters plus complete inherited R10 text; final PDF and `review/document_review.json` | Inherited measurements retain their original scope; final visual inspection recorded separately |
| F14 | `VERSION.json`, parent binding, logical review and staged Git history | Parent preserved; completed-stage commits/pushes; no new executable profile claimed |

## Main proof chains

1. **Storage:** minimal self-delimiting fields and tagged schema give unique
   structural decoding; bit transpose is an involution; retained length removes
   padding ambiguity. These facts imply losslessness on canonical records.
2. **Arithmetic:** carry and borrow telescope in the positional integer sum;
   convolution preserves products; division maintains prefix and remainder
   invariants. Rational and real-algebraic expressions then have exact meanings.
3. **State:** topological instantaneous evaluation plus delayed state provides a
   causal recurrence. Induction proves exact finite-prefix denotation, conditional
   on defined operators and valid transformations.
4. **Attitude:** positive-root normalization preserves unit norm; homogeneous
   rotation cancels the paired roots at readout; source gradients remain explicit.
   Quaternion sign cover preserves rotations without identifying serialized states.
5. **Dynamics and inference:** finite polynomial/coefficient/operator identities
   define exact discrete models; nonsingular QR and mechanical solves retain their
   mathematical meanings. IVP/root existence and physical adequacy remain separate.
6. **Improvement:** an accepted rewrite preserves domain and observations under
   its premises; a state-representation change requires an initial/step simulation
   relation. Finite composition preserves the declared observable stream.

## Explicit engineering work still required

The formalization does not provide an executable XOP parser, arbitrary-precision
CPU/GPU evaluator, algebraic decision engine, proof checker, certified real-term
output evaluator or measured resource budget. Implementation of these contracts
is subsequent work. A general terminating evaluator for unrestricted implicit
and transcendental decisions is not promised as an achievable missing feature.
An unresolved predicate is an allowed explicit result, not zero or false.

Physical use further depends on actual observations, clock/frame calibration,
model applicability, discontinuity handling and an application tolerance. R10's
historical numerical evidence remains evidence about R10. This release does not
establish a new GNSS, orbital, attitude or pointing tolerance.
