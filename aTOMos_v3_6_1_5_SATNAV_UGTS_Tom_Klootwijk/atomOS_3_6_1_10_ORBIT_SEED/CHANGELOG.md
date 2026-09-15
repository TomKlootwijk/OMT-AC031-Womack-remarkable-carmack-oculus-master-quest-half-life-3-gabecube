# 3.6.1.10 - exact seed execution optimization

Applied an exact six-stage transpose to lossless bit-plane words, audited the
supplied phi document, retained byte-identical seeds and original physical
parameters, reconciled native model-domain/reference-surface behavior, reused
identical batch queries, and prepared frame/station/Boolean inputs without stale
mutable model identities. Updated formal equations, source decisions, input
contracts, independent evidence and the complete PDF. Seed schema remains
3.6.1.9; prior releases are preserved.

Verified the full 400-year Gregorian calendar cycle, century boundaries and
exact phase/winding continuity with 9,519,315 comparisons and no failures.
The complete Python suite now passes 164 tests. Calendar coverage is separate
from the declared physical orbit prediction domains.

# 3.6.1.8 - live GPS receiver pipeline

Added raw RTCM3/NTRIP/TCP and RINEX2/3 observations, streamed GPS1019 ephemerides,
explicit broadcast orbit/clock/relativity/TGD/Earth-rotation/Klobuchar/Saastamoinen
equations, cold-start outer correction feedback and one persistent CPU/CUDA worker.
Validated real recordings and Internet-time native positions against independent
RTKLIB, raw-field and numerical references. Full source/evidence/PDF retained.
Existing ASA/NA, JK, CGK, OTAN2 and both UGTS codecs keep their original semantics.

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
