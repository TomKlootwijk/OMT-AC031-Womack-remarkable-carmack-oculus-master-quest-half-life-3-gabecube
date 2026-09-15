# aTOMos 3.6.1.13 - physics foundation

A focused supplement to R12, adding physical laws and model closures that
directly strengthen the existing exact operator, sensing and feedback interfaces.
The 145-page parent corpus remains unchanged and is referenced rather than
copied. Parent PDF and commit identities are in `source/PARENT_BINDING.json`.

New definitions include:

- A minimal application profile separating balance laws, constitutive response,
  finite reduction, discrete evolution and measurement.
- Newton/Euler and energy-port connections, thermal entropy production and
  consistent thermoelastic heat coupling.
- Maxwell/charge and Poynting balances with explicit dispersive material state,
  tying optical loss and storage to the same physical model.
- Exact SI defining constants versus measured coefficients, acquisition and
  joint uncertainty, and a scoped output tolerance certificate.
- `PHYS-MIDPOINT-LINEAR-R1`: a finite exact linear mechanical step with derived
  work/dissipation balance and unique rational solve under its stated hypotheses.

Profile `XOP-PHYSICS-R1` uses inherited `XOP-R1` operators. It adds no opcode
and does not silently replace existing backward Euler, orbital RK4 or word
profiles. Exact evaluation of a selected update does not make it the exact
continuous trajectory; law preservation is proved for that update explicitly.

Status: mathematical formalization and logical review. No new runtime, compiler,
proof checker, physical apparatus or measured performance is claimed. No
algorithms, source reference programs, numerical examples, tests, simulations,
benchmarks or physical experiments were run. Document compilation/rendering,
file integrity and Git operations are delivery/provenance work.

`docs/satnav.tex` is the editable master; `formal/` contains normative contracts,
source references and proof coverage; `review/` records review scope;
`output/pdf/` contains the focused PDF and `output/distribution/` its source archive.

Build with `python tools/build_pdf.py --engine PATH_TO_TECTONIC`.
Inspect document with `python tools/review_pdf.py --render` (Poppler, Pillow,
pypdf and pdfplumber). Package with `python tools/package_release.py`.
These scripts prepare documents and provenance; none executes the proposed kernel.

Author attribution is preserved as supplied: Tom Klootwijk, NL200678942,
10-07-1990. Established laws retain their scientific source attribution;
the aTOMos integration and conditional derivations are identified separately.
