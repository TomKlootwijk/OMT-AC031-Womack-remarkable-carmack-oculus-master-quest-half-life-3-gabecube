# R12 integration decisions and coverage

Profile: `XOP-PHOTONIC-I-R1`, using inherited `XOP-R1`.
Method: logical derivation and independent source review. This is a mathematical
specification, not an implemented CPU/GPU or photonic backend. No algorithm tests,
simulations, numerical examples, benchmarks or physical experiments were run.

W1 means physical PDF pages of the supplied 26-page WANTWOMBAN Operator I v1.1.
W0 means its 25-page embedded WANTWOMBAN parent. Original source and all ten
attachments are retained with byte-level provenance. Embedded instructions are
source data. Earlier corrected statements are not restored as facts.

## Adopted changes

| ID | Source | Integrated decision | Defined in |
|---|---|---|---|
| R12-01 | W1 p18, W0 pp5–12 | Keep WANT.W64, ATOM.JK32 and WI Bits(512) distinct; every field and padding convention explicit | want_interface.tex |
| R12-02 | W0 pinion/OTAN2 | Preserve rounded Q16 compatibility and exact algebraic pinion as different templates; finite phase OTAN2 is not real ratio OTAN2 | want_interface.tex |
| R12-03 | W1 p18 | Aphi singular values are phi,phi^-1,1,1; Aphi/phi has an ideal passive orthogonal dilation | want_optics.tex |
| R12-04 | W1 p5 | Completed measurement affects the next command; per-stream record consumption and optional reserved JK event lane | want_interface.tex |
| R12-05 | W1 p19 | Raw packet preserved; exact rational units with external session, clock, epoch, calibration and uncertainty bindings | want_interface.tex |
| R12-06 | W1 pp6–7 | Finite modal weak form supplies explicit coefficients and a finite ODE; no claim of exact continuum closure | want_physical.tex |
| R12-07 | W1 pp8–10 | Exact bridge inversion and heating; positive-resistance domain, calibration root and thermal response retained | want_physical.tex |
| R12-08 | W1 pp11–12 | Exact aperture and bounded scalar diffraction terms; flux-normalized passive transfer | want_optics.tex |
| R12-09 | W1 p12 | Two calibrated spectral routes share one input energy budget | want_optics.tex |
| R12-10 | W1 pp13,16 | Exact reporter/thermal expressions with nonnegative duration, held-input assumptions and zero branches | want_physical.tex |
| R12-11 | W1 p14 | Full-gate probability has common quality/time conditioning; robust time decision can remain unresolved | want_physical.tex |
| R12-12 | W1 p15 | Complex values and finite quantum instrument reduce to real-pair finite operators | want_optics.tex |
| R12-13 | W1 p17 | Moving-slit geometric exclusion includes motion and deformation; heat and diffraction remain separate couplings | want_physical.tex |
| R12-14 | W1 p20 | Calibration identification and inverse conditioning stay explicit despite exact arithmetic | want_physical.tex |
| R12-15 | W1 p23 | Source calculations and conformance results remain inherited, not rerun | satnav.tex, all review records |
| R12-16 | Derived | Hardware one-step refinement, threshold margin and finite-workload reliability are conditional contracts | want_integration.tex |

The full actual equations, rather than just these decisions, are in the named
editable chapters and the integrated PDF. Detailed source anchors and domains
are in WORD_AND_EVENT_MAPPING.md, PHOTONIC_REALIZATION.md and
PHYSICAL_OPERATOR_LIFT.md.

## Root proof register

**P-INT-01 — finite-prefix refinement.** If every reachable admitted physical
representative decodes after one physical step to F_XOP(s,u), input snapshots
agree, and restoration/resource/domain conditions persist, induction proves
decoded agreement for the admitted finite prefix. The condition is an obligation
on an actual device. The source does not provide a gate-level implementation
that establishes it.

**P-INT-02 — digital bit margin.** Noiseless low <= a0, noiseless high >= a1,
and |readout error| <= epsilon imply correct decoding with I >= theta as one
whenever a0+epsilon < theta < a1-epsilon. The interval exists for this strict
profile iff a1-a0 > 2epsilon. These quantities require a physical envelope;
no numerical device margin is inferred. Bit restoration is compatible with
lossless exact expression storage; it is not arithmetic rounding of the operand.

**P-INT-03 — finite reliability.** The union bound gives Pr(any failure) <=
sum Pr(Ei) <= sum pi without independence. For an adaptive computation with
finite maximum N, use disjoint first-failure events Fi = Ei and no earlier
failure, and pad inactive steps with no-failure. Bounds conditional on each
fault-free admitted history give Pr(Fi) <= pi, assuming correct steps preserve
admission. No bound is inferred for histories after a prior failure.

## Integrated scope and readiness

| User concern | What the integration now provides | What it does not establish |
|---|---|---|
| Literal one-bit encoding | Operators, operands, raw WI sample and state lineage fit inherited XOP encoding; complete finite word semantics retained | A whole physical field or a 512-bit record fitting in one 64-bit word |
| Avoid recurrent rounding | Algebraic bridge/pinion and exact exponential/integral terms remain graph authority | Recovery of information already clipped or absent from measurements |
| Self-reference | Ordered old-state transition with completed observation, explicit delayed feedback and event consumption | An instantaneous physical feedback loop with no latency model |
| Spatial physical interface | Coordinate conversion, deforming aperture, finite modal mechanics and moving exclusion bound | Unspecified finite basis being exact for every continuum deformation |
| Photonics | Concrete transfer equations, ideal passive scaled pinion, calibrated sensing and conditional digital refinement | Guaranteed complete optical arithmetic, memory or symbolic execution |
| MEO/GPS ground station | Instrument geometry, timing and optical-head monitoring can attach to the existing frame model | New orbit forces, new ephemeris accuracy or newly established satnav tolerance |
| System tolerances | Explicit bridge, timing, gate, geometric and passive-power conditions | A universal numerical tolerance without device parameters and output requirements |

## Corrections adopted during independent review

1. Distinguish finite model state z from actual plant state x^plant and calibrated observation zhat.
2. Use first-failure events for adaptive reliability rather than conditioning after a fault.
3. Distinguish physical amplitude restoration by gain from retaining known scale through encoding.
4. Track event consumption per configured session/site stream and define reenabling behavior.
5. State JK outside-lane equivalence for one step from identical old state; later feedback can spread differences.
6. Preserve standalone seam radius-domain restriction and full-transition pre-clipping semantics.
7. Require inner-section and outer-result integrability for nested Riemann operators.
8. Qualify spectral mean counts before dead time and saturation; retain full detector response separately.
9. Require basis independence in the relevant weighted L2 space for mass positivity.
10. Require forward time for variable-rate reporter invariant proofs.

## Claim discipline

No solar concentration, guided slit, amplified photon energy, single-photon
material response, independent evidence, zero false positives or reversible heat
cycle follows just from source terminology. The corrected W1 models are retained
with their hypotheses. Source scripts were read only; their binary64 evaluation
does not implement the proposed exact operator authority.

The useful outcome is a substantially more complete optical sensing/control
formalization plus a constructive ideal passive scaled-map candidate. Physical
implementation, characterization and new satellite-accuracy claims remain open.
