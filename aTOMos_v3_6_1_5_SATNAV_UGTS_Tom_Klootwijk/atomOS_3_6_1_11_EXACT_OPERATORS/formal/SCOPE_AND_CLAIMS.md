# Scope derived from the user objective

Objective: "Formalize everything and self improve the strategy without testing it
using logical reasoning", with the PDF subversion updated along the way.

"Everything" covers the kernel, encoding, operator arithmetic and physical/spatial
uses discussed in this thread and present in the R10 equation corpus. It does not
assert a formalization of unrelated mathematics. All named existing component
profiles remain in scope; Madgwick adds the attitude component.

| ID | Required formalization | Evidence required for completion |
|---|---|---|
| F01 | Exact source literals, value types, units, frames and uncertainty separation | Explicit denotation and import rules; no claim to recover already discarded input information |
| F02 | Literal one-bit word packing of operators, operands, references and state | Wire grammar and inverse construction with a mathematical losslessness proof |
| F03 | Exact arithmetic and complete operator vocabulary used by the named profiles | Integer carry/product/division laws, rational/algebraic semantics, transcendental/function declarations and domain conditions |
| F04 | Persistent self-reference and causal input streams | State-root recurrence, delay scoping, immutable inputs, checkpoint and query semantics |
| F05 | Original Madgwick IMU and MARG, bias/reference variants | Actual quaternion/objective/gradient/update equations; source variant and zero cases explicit |
| F06 | Orbital R2 forces, frames, interpolation and time evolution | Operator closure and exact discrete/continuous distinctions connected to the retained full equations |
| F07 | Station/body pointing and observation geometry | Frame and timing maps, mounting transform, measured and geometric quantities distinguished |
| F08 | Literal ASA/NA, synchronous JK, CGK mechanical recurrence | Existing whole-word and signed mechanical semantics retained; no substitution by per-bit clearing or hidden force |
| F09 | Both UGTS key layouts, source OTAN2 and full calendar/time | Quantization named explicitly as address projection; full continuous state and winding retained |
| F10 | SATNAV and live GNSS measurement/clock/QR equations | Exact operator lift, numerical iteration versus physical inference distinction and rank/branch conditions |
| F11 | Logical strategy improvement | Actual deductions, rejected proposals and adopted revisions with hypotheses and consequences; no benchmark-based selection |
| F12 | Proof discipline and uncertainty limits | Theorems with conditions, unresolved decision cases, resource growth, source uncertainty and discretization identified |
| F13 | Updated editable PDF subversion | R11 front matter, complete new chapters and labelled inherited corpus; inspected rendered document |
| F14 | Reviewable delivery and preservation | Logical coverage audit, version/status/provenance, completed-stage commits and pushes; parent untouched |

## Meaning of evidence

- **Definition:** a selected mathematical or serialization contract.
- **Conditional proposition:** a conclusion derived here under stated hypotheses.
- **Logical review:** human-readable inspection of deductions; not a proof-assistant certificate.
- **Implementation obligation:** a condition a future implementation must meet.
- **Inherited measurement:** an earlier result, retaining its original scope and date.
- **Physical assumption:** a statement about sensors, environment or model applicability
  that this formalization does not establish experimentally.

The current objective requests formalization and reasoned strategy improvement.
It does not authorize labelling an unimplemented runtime as working or a physical
forecast as newly validated. No numerical tests will be substituted for proofs;
document builds, file inspection and Git operations only deliver the formal work.
