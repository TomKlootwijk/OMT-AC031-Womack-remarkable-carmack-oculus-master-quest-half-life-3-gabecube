# aTOMos 3.6.1.16 — World Query Kernel engine

Tom Klootwijk. R16 integrates executable parts of the supplied TOM World Query
Kernel 0.6 package into the preserved R15 engine and formalization.

## What changed

- **Native TOMAGI VM:** all 16 Cell48 opcodes execute over persistent State64
  lanes on CUDA. Canonical program bytes are transposed into literal one-bit
  planes, reconstructed on the GPU and fetched through banked integer textures
  or an equivalent global-load path.
- **Actual word feedback:** each freshly executed EMIT supplies its payload to
  two ordered ASA/NA stages and JK. The resulting 64-bit word is injected into
  the next VM step's rho/vrho words. Sticky EMIT status cannot create extra
  events. Dispatch receipt epochs start at zero.
- **Exact affine events:** the Python adapter derives rational plane roots,
  certifies the complete earliest simultaneous set, and atomically changes
  world state, rates and the inherited exact hinge state. Packed replay
  recomputes event semantics.
- **Executable source fixture:** the original literal-cell compiler creates
  a real three-cell feedback program. The source Python VM independently
  generates the expected coupled trace.
- **Preserved foundation:** all R15 spatial, word, physics and clock contracts
  remain available. New source files are pinned under vendor/wqk_0_6; the
  external source package and earlier releases are preserved.

The imported PHI opcode is a 12-bit phase counter; SDF0 assigns zero. They
retain their source meanings. The inherited exact a+b*phi algebra and metric
guard contracts remain distinct. KLEIN carries reduced coordinates and parity;
full winding remains the separate inherited hinge representation.

See formal/TOMAGI_NATIVE.md, formal/WQK_INTEGRATION.md and
formal/EXACT_AFFINE_EVENTS.md for equations, source corrections and scope.
No finite learner or source publication stack is added to the runtime.

## Build and use

Validated Windows toolchain: Visual Studio 2022 Build Tools, CUDA 12.8,
CMake and RTX 5070 Ti Laptop GPU (sm_120). Use a short build directory.
Run these commands from this release directory:

~~~powershell
python tools/build_wqk_fixtures.py
./tools/build_native.ps1
ctest --test-dir C:/aTOMosBuild/r16cuda -C Release --output-on-failure
python -m unittest discover -s tests -p 'test_*.py' -v
python tools/check_exact_events.py
& C:/aTOMosBuild/r16cuda/Release/wqk_run.exe --program examples/wqk_feedback.tmg --lanes 4096 --steps 96 --fetch texture --feedback copy32 --output review/my_run.json
~~~

Use --fetch global for matched ordinary loads and --feedback none for the
pure imported VM. The copy32 profile uses a valid mask of 0xffffffff,
x=drive, J=y and K=~y; the C++ WordFeedback API supports declared general
64-bit masks and four-entry Boolean tables.

A standalone VM build can omit inherited S2/spatial targets:

~~~powershell
cmake -S . -B C:/aTOMosBuild/r16vm -G 'Visual Studio 17 2022' -A x64 -T cuda=12.8 -DATOMOS_SPATIAL=OFF
cmake --build C:/aTOMosBuild/r16vm --config Release --parallel 8
~~~

Full spatial builds retain the official S2 revision in source/DEPENDENCIES.json.
The build script checks that revision before compiling. The supplied CPU
event profile admits rational literal planes and affine epochs, with each
relation firing at most once. It does not yet perform GPU root discovery
or update a dynamic BVH.

## Validation and evidence

R16 checks compare all raw VM words with the unmodified source C oracle,
and both CUDA fetch paths with the separately generated Python feedback trace.
The event suite covers exact roots, same-sign endpoint turnarounds,
simultaneous updates, terminal roots, forged certificates and semantic replay.
review/R16_VALIDATION.md records final commands and results.

All inherited S2 and large-VRAM timing reports are explicitly historical R15
measurements. The new TOMAGI interpreter runs a different workload; its timing
is recorded separately. Texture fetches do not imply permanent cache residency,
and capacity occupancy does not establish DRAM bandwidth saturation.

## Editable formalization

docs/unified.tex retains the full previous formalization and adds the R16
opcode, feedback and exact-event equations. tools/prepare_document.py verifies
authored sources without rewriting them. tools/build_pdf.py builds the PDF;
tools/review_pdf.py checks and renders it. Packaging verifies source bindings,
vendor bytes and completed visual review for the exact PDF bytes.

The retained NIST packet is an earlier observation. Physical specializations
still need their actual parameters, frame, measurement model and validation;
lossless words preserve inputs and do not determine physical accuracy.
