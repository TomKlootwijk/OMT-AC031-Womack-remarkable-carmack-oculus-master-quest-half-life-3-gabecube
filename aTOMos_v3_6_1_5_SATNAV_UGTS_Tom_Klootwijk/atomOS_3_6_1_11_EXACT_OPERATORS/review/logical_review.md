# Logical review record - R11

Method: source-equation reading, symbolic derivation, counterexample arguments,
domain analysis and independent agent-assisted cross-review. No unit tests,
numerical examples, simulations, benchmarks or physical experiments were run.
This is human-readable reasoning, not a proof-assistant certificate or a human
expert sign-off. PDF compilation and visual inspection are document preparation.

## Reviewed work

- The root strategy's exact-state induction, homogeneous quaternion readout,
  error decomposition, graph-count and history-counting arguments.
- The core bit/limb arithmetic, literal grammar, scoped operators, domain-aware
  rewrite rules and synchronous state semantics.
- The original Madgwick objectives/Jacobians, magnetic reference and bias order,
  normalization, finite-mixture distinction, sign cover and mounting composition.
- The retained orbital/frame/force/geometry, UGTS/calendar, receiver/live-GPS and
  coupled-mechanical operators, finite iteration choices and implicit alternatives.
- The independently read source variants and the coverage requirements F01-F14.

## Concrete findings and adopted corrections

| Finding | Correction in the delivered specification |
|---|---|
| Madgwick equation and appendix reference timing differ | Pin the report-equation profile and record the appendix lag and normalization aliases separately |
| Normalized-coordinate differentiation changes the gradient | Retain the ambient source Jacobian; state the projector introduced by a normalized-coordinate pullback |
| Finite mixing differs from the simplified beta update | Derive the `(1-gamma)` factor and the zero-corrected-rate case; name both families |
| Gyro-only correction was implicit | Explicitly set e=0 and avoid demanding an unadmitted residual |
| Frame transpose was used as inverse | Require proper orthogonal alignment/mounting; distinguish arbitrary fitted orbital matrices |
| Imported dynamic exports lacked a snapshot binding | Restrict value imports to closed stateless expressions; use explicit input ports for live data |
| Vector/matrix component extraction was underspecified | Extend projection grammar and type rules to those components |
| Dimensional literals and powers/roots lacked complete typing | Encode scalar wrappers and static degree obligations; state tensor dimension transformations |
| Mixed position/velocity units did not fit homogeneous ODE vectors | Admit heterogeneous tuple states with componentwise derivative dimensions |
| Algebraic literal byte order was assumed | Specify coefficient sequence, root index and complete payload grammar |
| Frame/time identity was not represented in canonical types/bindings | Add versioned frame annotations and explicit registered/custom time definitions |
| Sample timestamps were stored but lacked graph references | Add shared-snapshot raw and explicitly mapped GPST timestamp references, with epoch/unit rules for t and h |
| New framed vectors were not listed among ODE state leaves | Admit framed-vector components with matching derivative frame identity and state/time dimensions |
| Everywhere differentiable ODE conflicted with piecewise forcing | Use a unique continuous integral-equation solution, with integrability/continuation obligations |
| Source-map filename was inaccurate | Identify the preserved `include/orbit_core.hpp` correctly |
| Python/native SATNAV input policies differ | Preserve positive-range versus one-metre range policies explicitly |
| CGK word-first failure looked incompatible with atomic state commitment | Define the entire next tuple on failure, with new word, old mechanics/history and failure flag; do not demand the inverse |
| Finite Jacobi diagnostics were too close to an ideal spectrum claim | Define the finite thresholded recurrence separately; distinguish ideal algebraic spectrum and complex damping roots |
| PDF relied on an external opcode/wire table | Include the normative registry inside the PDF as well as editable Markdown |

The independent attitude review found no remaining sign or frame-direction
defect in the displayed residuals, Jacobians, bias components or conditional
quaternion identities after these clarifications. The domain review checked
the coefficient, force, frame-derivative, finite-step, station and mechanical
identities under their explicit conditions. These observations report the
scope of reasoning performed; they do not guarantee that all possible errors
have been excluded.

The final read-only scope audit found no additional missing mathematical
definition among F01-F12 after the timestamp and framed-ODE corrections. It
confirmed that the CGK failure branch is a defined lazy state tuple, compatible
with synchronous DELAY. F13/F14 are satisfied by the separately recorded final
document inspection and release delivery, rather than a mathematical theorem.

## Conditions that remain visible

Every proposition retains its premises. Exact integer operations need sufficient
storage; exact algebraic decisions need a conforming algorithm; real-term and
implicit-solution predicates may remain unresolved. No claim is made that all
future proof searches terminate or that a fixed seed holds arbitrary sensor
histories. Undefined operators, missing inputs and modeled failure flags are
different outcomes.

The new parser, exact CPU/GPU evaluator, proof checker and certified output
backend remain implementation work. The proof-record field format is an
interface to a separately named proof system, not an implemented calculus.
Physical tolerances still require physical/model evidence and an application
criterion. The preserved R10 evidence has not been reclassified as R11 evidence.

Document structure and visual inspection are recorded separately in
`document_review.json`, which binds the reviewed PDF by SHA-256.
