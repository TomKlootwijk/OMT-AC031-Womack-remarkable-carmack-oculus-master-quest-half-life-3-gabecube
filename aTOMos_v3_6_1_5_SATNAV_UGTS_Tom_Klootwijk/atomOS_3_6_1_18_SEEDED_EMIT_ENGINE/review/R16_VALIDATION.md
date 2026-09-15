# R16 validation

All eight native suites and all 49 Python tests pass. R16 reuses the preserved
R15 spatial engine and adds native TOMAGI and exact affine-event profiles.

## Native execution

- Full build: CMake, Visual Studio 2022 Build Tools, CUDA 12.8, Release/sm_120.
- Device: NVIDIA GeForce RTX 5070 Ti Laptop GPU, compute capability 12.0.
- `r16_native_checks.txt`: all 8 CTest suites pass; 37,837 spatial checks,
  135 exact GPU phi assertions, 4,365 resident-count checks, retained texture
  and feedback suites, 28,794 native TOMAGI assertions and 1,718 word-feedback
  checks. The native VM is compared with the unmodified imported C oracle.
- `r16_python_checks.txt`: 49 tests (22 inherited hinge, 27 new event).
- `exact_events_validation.json`: 36 independent public-API evidence checks,
  including exact roots, complete event sets, terminal roots and semantic replay.
- `wqk_fixture_reference.json`: actual original literal-cell compilation and
  unmodified Python transition reference; program 272 bytes, 24 steps. This uses
  the literal-cell profile, not the separate seeded formal-DAG materializer.
- `r16_run_reference.json`: native command-line result matches every first-lane
  word of the independent 24-step Python fixture.

The first feedback check failed because the fixture numbered receipts 1..24
instead of the native 0..23 convention. The generator now distinguishes display
steps from receipt epochs. The VM semantics were preserved. The final reports
and expected binary use the corrected convention.

## Timing scope

`wqk_paired_runs.json` retains 36 fresh-process trials: three repeats per fetch
path across six profile/lane cases, each 96 instructions. All pairs and repetitions
have equal full-array FNV-1a-64 digests and exact first-lane fields. This digest
is noncryptographic; the smaller independent suites compare individual words.
Feedback cases also match the expected 48 accepted EMITs per lane.

At 262,144 lanes, median device batch times are 5.926 ms texture / 5.764 ms global for
the pure VM, and 15.481 ms / 15.333 ms with copy32 feedback. The latter executes
25,165,824 VM instructions and accepts 12,582,912 emissions. Cold host-complete
medians are separately recorded and include setup, readback and digest.

Global loads have the lower device median in 4/6 cases. The three-cell program
is tiny and all lanes start identically. These are word-machine measurements,
not S2 comparisons or evidence of cache/DRAM saturation. No general throughput
claim is extrapolated to diverse or large operator programs.

## Reproduction

Run from this release directory:

```powershell
python tools/build_wqk_fixtures.py
./tools/build_native.ps1
ctest --test-dir C:/aTOMosBuild/r16cuda -C Release --output-on-failure -V
python -m unittest discover -s tests -p 'test_*.py' -v
python tools/check_exact_events.py
& C:/aTOMosBuild/r16cuda/Release/wqk_run.exe --program examples/wqk_feedback.tmg --lanes 1 --steps 24 --fetch texture --feedback copy32 --output review/r16_run_reference.json
python tools/measure_wqk.py --executable C:/aTOMosBuild/r16cuda/Release/wqk_run.exe
```

The standalone configuration uses `-DATOMOS_SPATIAL=OFF`; its build/check logs
are retained separately. No source files are modified by document preparation.
All 125 preserved source records, both parent PDFs and 42 WQK imports are byte-checked
before packaging.

## Historical evidence

R16 carries R15 reports without changing their measured inputs or claims.
`COMPARISON.md`, `RESIDENT_RESULTS.md`, `WORD_OPTIMIZATION.md`, `WORD_PROFILE.md`
and their JSON reports describe R15 workloads. `R15_DOCUMENT_REVIEW.json` is
the prior PDF's review. They do not establish performance of the new VM.
R16 `document_review.json` is generated only from the new final PDF.
