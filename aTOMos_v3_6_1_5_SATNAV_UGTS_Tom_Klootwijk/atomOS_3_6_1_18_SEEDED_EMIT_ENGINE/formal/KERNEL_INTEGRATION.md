# R14 exact kernel and physical-field integration

Status: mathematical composition and logical derivation. No runtime, reference
program, numerical example, test, simulation or physical experiment was executed.
The integrated manuscript is `docs/kernel_bridge.tex`. The existing XOP core and
full registry are included elsewhere in R14 rather than redefined here.

## State, chronology and required bindings

The finite delayed record is `(q, W, xi, last_consumed, controller_memory;
exact_roots_and_dependencies)`. The JK word, optional WANT word, finite physical
model state and acquired physical observations are distinct typed components.
The actual plant is not an unknown literal hidden inside the model state.

At control time `t_n`, only a completed available immutable observation `R_n`
enters calibration/event templates. Their outputs feed the declared drive, X,
ordered dual ASA/NA stages and same-old-state J/K. The complete adapter body
selects command `u_n` and the remaining candidate digital state. Hold the command
over `[t_n,t_(n+1)]` under the selected physical interface. A continuous model or a
separately selected finite step predicts the next model state/measurement. The
actual following observation is acquired independently and keeps its acquisition,
availability and source-time bindings. A later measurement cannot alter the
earlier command that caused its acquisition interval.
An acquisition integral uses a declared trajectory or reconstruction. Finite
endpoint states alone do not define an instrument's continuous acquisition.
With the event-lane adapter enabled, its J-star/K-star give the final q-next
through the same synchronous JK equation. The command adapter reads that final
word, rather than the separate base candidate.

All logical roots commit together from one input/old-state snapshot. External
physical command timing, resource availability and plant timeout behavior are
separately specified; mathematical graph evaluation is not an actuator.

## Proof and integration decisions

| Decision | Exact content and premise | Source lineage |
|---|---|---|
| K14-01 | Literal ordered two-mask ASA/NA with whole-word absorption and synchronous JK remains the word body, not a material law | R6 `docs/SELF_REFERENCE.md`; R10 `docs/orbit.tex` two-stage section; R11 catalog ASA_NA/JK |
| K14-02 | Model state, actual plant and completed observation are separate; sample-and-hold command chronology has explicit absolute times and availability | R12 `docs/want_integration.tex`; R13 measurement contract |
| K14-03 | Optional event lane uses accepted event AND new record; tracker and digital state commit atomically | R12 `formal/WORD_AND_EVENT_MAPPING.md`, section 7 |
| K14-04 | Missing/invalid input is not event false; a declared atomic tagged failure value can preserve CGK word-first failure semantics | R11 `formal/DOMAIN_LIFT.md`, final paragraph; R12 event contract |
| K14-05 | W64 fields and physical chart are restated explicitly; no legacy W64 transition is selected by its label alone | R12 `formal/WORD_AND_EVENT_MAPPING.md`, sections 1–4 |
| K14-06 | Original integer pinion rounding is retained as a function; algebraic A_phi is a separate profile | R12 word/event mapping and optical pinion derivation |
| K14-07 | Optical transfer terminates in an instrument acquisition, expected counts remain separate from observed codes | R12 `docs/want_optics.tex`; R13 Maxwell and measurement equations |
| K14-08 | One common field/material energy ledger counts each transfer once | R13 energy/Maxwell contracts |
| K14-09 | Passive scaled pinion B=A_phi/phi has a real orthogonal dilation; side ports carry remaining power | R12 `docs/want_optics.tex`, constructive pinion section |
| K14-10 | Physical carrier realization requires a relation on every reached admitted representative, same snapshots and admitted successor state | R12 `docs/want_integration.tex`, refinement proof |
| K14-11 | Orbital simultaneous geometry differs from received-signal position; word-selected cadence does not alter the source orbit force law | R10 `docs/orbit.tex`; R11 `docs/exact_domains.tex` |
| K14-12 | Optional attitude normalization gives unit norm on its nonzero-candidate domain; residual/bias/sample definitions remain required | R11 `docs/exact_madgwick.tex` |

## Short derivations used in the manuscript

1. Event-lane substitution gives J=K=0 on its reserved lane for no pulse, hence
   hold, and J=K=1 for a pulse, hence toggle. Outside that mask both base words
   are unchanged for the same old state; no global noninterference is implied.
2. W64 extraction and signed interpretation determine its finite fields. The
   declared positive-scale chart supplies physical coordinates. Reversing the
   field coding recovers those codes, not arbitrary discarded input coordinates.
3. H4 is orthogonal, so A_phi has singular values phi, 1/phi, 1, 1. The unit
   vector H4^T e1 gives norm amplification phi. Scaling by phi makes a
   contraction. Each real pair O(d) is orthogonal for |d|<=1, and zero classical
   auxiliary input yields the desired selected-mode amplitude with side-port
   power retained. This is an ideal target construction, not a hardware result.
4. If every reached physical representation decodes correctly after a step and
   the successor is again admitted, initial agreement and identical samples
   imply agreement for every defined finite prefix by induction.
5. The intensity margin bounds the largest low and smallest high readout on
   opposite sides of a declared threshold. It supplies a conditional digital
   decoding tolerance, not a measured device envelope.
6. The norm of U/sqrt(U^T U) is one for a defined U with U^T U>0. Quaternion
   kinematics and this identity alone do not prove an estimator's accuracy.

## Scope and unresolved application choices

R14 provides the complete shared core and equations above. A historical
application is selected through its complete immutable profile/dependency body,
not its name. R14 does not claim to restate every earlier orbital force recipe,
WANT transition, WI transport byte field or Madgwick branch. The full XOP wire
grammar is provided in the main manuscript. External device records may enter
as explicit typed sample data plus their complete selected decoder/registry.

Exact finite expression state can remove additional arithmetic rounding relative
to represented inputs. Intentional quantization and finite-step approximation
remain explicit. A supplied transfer, law or inequality does not prove material
parameters, calibration validity, physical realizability or measured accuracy.
No new opcode, opaque physical oracle, default hidden controller or exact
continuous signal literal is introduced by this integration.

Independent review refinements: the schedule now shows the event-adapted final
JK word explicitly before command selection. The spectral count-sum profile
requires mutually incoherent, separately resolved orthogonal, or appropriately
averaged frequency components; a general coherent finite-window detector model
must retain its field cross terms. These are domain refinements, not new
performance claims.
