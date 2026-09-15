# aTOMos 3.6.1.12 — WANTWOMBAN photonic interface

This subversion integrates the supplied WANTWOMBAN Operator I v1.1 equations
with the R11 literal one-bit exact operator seed formalization. It adds explicit
word and measurement adapters, optical propagation, strain and bridge readout,
finite modal mechanics, material and thermal memory, and causal event feedback
into the existing ASA/NA and JK framework.

The golden-ratio/Hadamard pinion has a constructive ideal passive realization
after scaling by 1/phi, using additional optical ports. The unscaled direct
amplitude map is not passive in equal power-normalized modes. This limitation
does not prohibit digital photonic computation on encoded coordinate bits.

Status: mathematical integration and conditional derivation; no new exact
CPU/GPU runtime or photonic backend is implemented. No algorithm tests,
numerical examples, simulations, benchmarks or physical experiments were run.
Document compilation, rendering and artifact hashing are delivery checks.
Historical result tables in the supplied source and inherited R10 chapters
retain their original scope. No new satellite-position accuracy is established.

The profile is `XOP-PHOTONIC-I-R1`, using the unchanged R11 `XOP-R1` wire and
operator vocabulary. The complete inherited R11 and R10 equation corpus is
included in the PDF. Pure templates are specified mathematically; no unseen
compiler or executable template library is claimed. R11 and R10 remain unchanged.

Key files:

- `docs/satnav.tex`: complete editable PDF master.
- `docs/want_integration.tex`: aggregate state and conditional hardware contract.
- `docs/want_interface.tex`: complete W64/WI mappings and optional JK event lane.
- `docs/want_optics.tex`: optical equations, finite quantum instrument, passive pinion.
- `docs/want_physical.tex`: mechanics, bridge, reporter, thermal and error bounds.
- `docs/want_completion.tex`: adopted changes and practical scope.
- `formal/INTEGRATION_DECISIONS.md`: source-to-decision and proof coverage.
- `formal/WORD_AND_EVENT_MAPPING.md`, `PHOTONIC_REALIZATION.md`,
  `PHYSICAL_OPERATOR_LIFT.md`: detailed derivations and assumptions.
- `source/`: byte-preserved PDF, embedded attachments and provenance manifests.
- `review/`: logical and rendered-document review records.
- `output/pdf/`: integrated PDF; `output/distribution/`: complete source archive.

Source attribution is preserved as supplied: Tom Klootwijk, NL200678942,
10-07-1990. Instructions and reference scripts inside the supplied PDF were
treated as source data; none of the embedded programs were executed.

The six inherited R11 Markdown files remain at their original `formal/` paths
for the preserved chapters' references and are duplicated in `formal/inherited_r11/`
as an explicit provenance group. Their R11 status and claims are inherited.

Build: `python tools/build_pdf.py --engine PATH_TO_TECTONIC`.
Document inspection: `python tools/review_pdf.py --render` with Poppler,
Pillow, pypdf and pdfplumber. Distribution: `python tools/package_release.py`.
These tools prepare documents and file provenance; they do not execute the
formalized kernel or source experiments.
