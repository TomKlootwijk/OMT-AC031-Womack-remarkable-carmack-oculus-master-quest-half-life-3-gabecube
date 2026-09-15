# aTOMos 3.6.1.17 — fused word engine

R17 optimizes the native TOMAGI machine and ASA/NA/JK feedback by executing
several complete transitions per GPU launch. Every final state, error, receipt
and feedback word retains the R16 semantics. The source-compatible reference
path remains available.

## Execution

- VM::enqueue_batch executes 0..256 requested epochs per lane in one launch.
- WordFeedback::run_steps_fused composes injection, canonical VM execution and
  fresh-EMIT commit. It accepts a uint32 total and chunk size 1..256, default 32.
- Lane state is published at chunk boundaries. Use the reference APIs when an
  observer needs each intermediate state or receipt.
- HALT and fault slots still advance receipt epochs correctly. Equal fresh
  payloads remain distinct events; stale or duplicate events cannot commit twice.
- LSYS division by 2^shift retains signed truncation toward zero, implemented
  through unsigned magnitude shifts and sign restoration.
- Integer textures read the same immutable Cell48 banks. One-bit-plane
  transport preserves the complete original words; no geometry interpolation
  is introduced.

formal/FUSED_WORD_EXECUTION.md and docs/fused_execution.tex give the induction
proof, chunk-composition law, exact division identity and ownership contract.
The full R16 operator/event profiles and R15/R14 mathematical foundation are
preserved. The external WQK source and older releases are unchanged.

## Build and run

Run from this release directory. The measured target uses CUDA 12.8,
Visual Studio 2022 Build Tools and an RTX 5070 Ti Laptop GPU, sm_120.

~~~powershell
cmake -S . -B C:/aTOMosBuild/r17vm -G 'Visual Studio 17 2022' -A x64 -T cuda=12.8 -DATOMOS_SPATIAL=OFF
cmake --build C:/aTOMosBuild/r17vm --config Release --parallel 8
ctest --test-dir C:/aTOMosBuild/r17vm -C Release --output-on-failure

& C:/aTOMosBuild/r17vm/Release/wqk_run.exe --program examples/wqk_feedback.tmg --lanes 262144 --steps 96 --feedback copy32 --fetch texture --dispatch fused --chunk 32 --output review/my_fused_run.json
~~~

The runner defaults to fused execution in chunks of 32. Select --dispatch
reference for the retained launch-per-instruction implementation and --fetch
global for ordinary loads. --feedback none executes the pure VM. An optional
--lane-init spread explicitly varies raw rho, lineage and cell by lane index;
the JSON report describes this initialization. It is not the default source
header initialization.

The full inherited spatial build uses tools/build_native.ps1 and
C:/aTOMosBuild/r17cuda, including the pinned official S2 dependency.

## Reproduce measurements

~~~powershell
python tools/build_wqk_fixtures.py
python tools/build_mixed_workload.py
python tools/measure_fused.py --executable C:/aTOMosBuild/r17vm/Release/wqk_run.exe --baseline-executable C:/aTOMosBuild/r16cuda/Release/wqk_run.exe --repeats 3
python tools/summarize_fused.py
python -m unittest discover -s tests -p 'test_*.py' -v
~~~

The optional baseline executable runs the unchanged R16 binary on identical
tiny-fixture inputs. All cases also compare R17 reference/fused and
texture/global paths. The large fixture contains 1,048,576 synthetic Cell48
instructions (48 MiB), with varied opcode bodies and spread lane states.
Its canonical binary is reproduced from the checked-in recipe/generator
and excluded from Git and the ZIP; its exact hash is recorded.

review/FUSED_RESULTS.md and fused_runs.json contain final timings and every
trial. Initial measurements are retained under names ending in _initial.
Device batch, host dispatch, cold setup, readback and complete host-visible
costs are separate. Full-array FNV-1a-64 comparisons are noncryptographic;
independent C/scalar tests compare individual words.

Final validation passes all nine native suites and 49 Python tests. The fused
suite passes 1,513,078 checks, including every LSYS shift and signed extremes.
Across 16 matched comparisons, device execution improves by 3.347–20.277x;
cold host-complete ratios range from 0.965x to 1.098x. These are different
measurement boundaries, and three host-complete cases have a higher median.

The fresh return to the original source is recorded in
review/R17_ORIGINAL_RETURN.md and review/R17_SEEDED_RUNTIME_AUDIT.md. Its
artifact materializer requires the complete ordered EMIT stream. Fused final
receipts alone do not supply that stream; this remains a concrete next step.

## Formalization and remaining work

The full editable PDF master is docs/unified.tex. Source preparation only
verifies the authored inputs. Build, rendering, visual review and packaging
bind the exact PDF bytes to those sources and preserve all three parent PDFs.

The optimization concerns finite word execution. It does not broaden the
meaning of the source PHI phase counter, SDF0 zero operator, exact rational
event solver or physical application laws. The inherited S2, clock and VRAM
records retain their original scope. Broader expression lowering, non-affine
events and dynamic geometry/cache rebinding remain continuing engine work.
