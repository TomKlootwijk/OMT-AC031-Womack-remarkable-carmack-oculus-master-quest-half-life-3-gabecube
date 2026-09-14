# 3.6.1.7 - CGK-R1 complete geometry/physical state coupling

Closes geometry-to-word and word-to-mechanics feedback in native CPU/CUDA and
the actual SATNAV/UGTS handoff. Supplies explicit circle-plus, predicate encoders,
signed stiffness/force operator, mass-normalized eigenmatrix and backward Euler
advance. Publishes original measurements alongside the evolving modeled state,
with independent expression/mechanical replay and updated formalization.

# 3.6.1.6 - SRK-R1 literal self-reference

Adds synchronous persistent ASA/NA + JK state feedback, editable Boolean equation
inputs, exact truth-table compilation, CPU/CUDA trajectory execution, complete
traces and an independent expression-tree reference. Fixed points and cycles are
reported distinctly. Retains the original SATNAV/UGTS profiles and both key layouts.
The combined PDF is rebuilt from editable LaTeX with equations and current validation.
Previous 3.6.1.5 package is preserved beside this subversion.

# 3.6.1.5 — SATNAV-R1

Specializes aTOMos 3.6.1 with passive corrected-code positioning, FP64 weighted QR,
batched CPU and CUDA implementations, independent Python verification and the
uploaded UGTS-KC 3.6.2 SCLP key/geometry/event contracts. New GNSS modelling and
source corrections are identified in docs/SOURCE_DECISIONS.md and the formal PDF.

The original UGTS software package and earlier generated aTOMos archive were not
mounted. The referenced source definitions are newly implemented here; historical
assertion counts are not imported as current tests. CUDA source is delivered with
compilation/execution status explicitly not_run in the preparation environment.
