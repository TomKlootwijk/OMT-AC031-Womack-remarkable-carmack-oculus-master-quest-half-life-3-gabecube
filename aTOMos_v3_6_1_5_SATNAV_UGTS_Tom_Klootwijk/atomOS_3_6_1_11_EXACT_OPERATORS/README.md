# aTOMos 3.6.1.11 - exact operator seed formalization

This subversion specifies how literal one-bit words can encode exact operators,
their operands and persistent expression state. Intermediate rounded values do
not become the authoritative next state. It covers the operator format, original
Madgwick IMU/MARG recurrences, orbital and station geometry, original UGTS and
ASA/NA/JK semantics, coupled mechanics, and retained receiver equations.

The work method is logical derivation and critical review, as requested. No new
unit tests, simulations, benchmarks or physical accuracy experiments are run.
This is an editable mathematical specification; a new executable exact engine is
not claimed. The complete R10 equation body and dated measurements remain in the
PDF as explicitly inherited material. R10 sources and binaries remain unchanged.

The exact model distinguishes operator definitions, conditional propositions,
implementation obligations and physical assumptions. A finite expression can
denote an exact irrational result without storing its infinite digit expansion.
That does not imply constant storage, constant execution cost or complete decision
procedures for arbitrary transcendental expressions and differential equations.

Files are developed and committed in stages:

- `docs/`: editable LaTeX chapters and complete PDF master.
- `formal/SCOPE_AND_CLAIMS.md`: requirements and evidence meanings.
- `formal/OPERATOR_CATALOG.md`: exact operator vocabulary and representation.
- `formal/MADGWICK_DERIVATION.md`: attitude recurrence and its assumptions.
- `formal/DOMAIN_LIFT.md`: lifting the existing physical and spatial profiles.
- `formal/STRATEGY_REVISIONS.md`: deductions that change the design strategy.
- `formal/COVERAGE_AND_PROOFS.md`: final scope-to-derivation audit.
- `review/`: logical and document review records, with no experimental pass claims.

Build the document using `python tools/build_pdf.py --engine PATH_TO_TECTONIC`.
Rendering is document preparation, not an experiment on the proposed algorithms.
