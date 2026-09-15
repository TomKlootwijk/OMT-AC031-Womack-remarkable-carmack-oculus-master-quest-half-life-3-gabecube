# aTOMos 3.6.1.18 — seeded EMIT engine

R18 adds complete ordered native EMIT journals to the exact TOMAGI word
machine and ASA/NA/JK feedback engine. Two original seeded artifacts now
materialize from native GPU execution with complete byte equality against
fresh original Python replay. Canonical Cell48, State64, faults, receipts
and word-feedback semantics remain intact.

## Execution and exactness

- `VM::run_journal_chunk` and `WordFeedback::run_journal_chunk` capture every
  fresh VM emission over 0..256 requested epochs. Reference/fused dispatch
  supports texture or global reads.
- Disjoint per-lane storage preserves epoch order, repeated fresh payloads
  and EMIT-HALT. Final receipts remain exact after additional held epochs.
- Capacity is proven by `lanes * ticks`. GPU/host buffers and boundary arrays
  are allocated before corresponding mutable execution.
- Source ownership, generation, contiguous epochs, complete word profile
  and exact boundary state govern continuation. Runtime failures are not
  reported as successful completed journals.
- `wqk_materialize` decodes a canonical one-lane seeded program and writes
  bytes only after fault-free HALT with at least one EMIT. Prefix/fault
  reports do not write the artifact.
- PHI/TIME and seam/turn updates have exact bounded 32-bit forms. The retained
  signed-wide expressions permit matched comparisons. Complete quotients,
  parity and lineage are preserved.
- One-bit-plane transport retains complete words. Integer texture reads
  introduce no geometry interpolation.

`formal/SEEDED_EMIT_JOURNAL.md` gives the stream, capacity, ownership,
composition and byte-order contract. `formal/EXACT_PHASE32.md` proves the
bounded arithmetic. The complete earlier engine and mathematical foundation
are retained. External WQK sources and older releases remain unchanged.

## Build and materialize

Run from this release directory. The checked target uses CUDA 12.8,
Visual Studio 2022 Build Tools and an RTX 5070 Ti Laptop GPU, sm_120.

~~~powershell
cmake -S . -B C:/aTOMosBuild/r18vm -G 'Visual Studio 17 2022' -A x64 -T cuda=12.8 -DATOMOS_SPATIAL=OFF
cmake --build C:/aTOMosBuild/r18vm --config Release --parallel 8
ctest --test-dir C:/aTOMosBuild/r18vm -C Release --output-on-failure

& C:/aTOMosBuild/r18vm/Release/wqk_materialize.exe --program examples/seeded18/world03/world03_release_artifact.tmg --output review/my_world03.bin --report review/my_world03.json --steps 869 --chunk 32 --fetch texture --dispatch fused
python tools/verify_seeded_runtime.py --fixture world03 --report review/my_world03.json --artifact review/my_world03.bin --ticks 869 --output review/my_world03_verified.json
~~~

The source header supplies the horizon when `--steps` is omitted. CLI
timings describe host setup; journal allocation, execution, transfers,
compaction and decoding; artifact write; and total through persistence.
JSON encoding/report output is excluded. No device-only materialization
speedup is claimed.

`wqk_run` retains final-only reference/fused execution, default fused chunks
of 32. `--lane-init spread` explicitly varies raw lane state, distinct from
canonical header initialization used by the one-lane materializer. The full
spatial build uses `tools/build_native.ps1` and pinned official S2.

## Reproduce source and phase evidence

~~~powershell
python tools/build_seeded_fixtures.py
python tools/build_phase_workloads.py
python tools/build_mixed_workload.py

cmake -S . -B C:/aTOMosBuild/r18wide -G 'Visual Studio 17 2022' -A x64 -T cuda=12.8 -DATOMOS_SPATIAL=OFF -DATOMOS_WIDE_PHASE_REFERENCE=ON
cmake --build C:/aTOMosBuild/r18wide --config Release --parallel 8
ctest --test-dir C:/aTOMosBuild/r18wide -C Release --output-on-failure
python tools/measure_phase.py --narrow C:/aTOMosBuild/r18vm/Release/wqk_run.exe --wide C:/aTOMosBuild/r18wide/Release/wqk_run.exe --repeats 5
python -m unittest discover -s tests -p 'test_*.py' -v
~~~

Both bounded-phase and signed-wide builds pass all four standalone native
suites. Fused execution passes 8,073,110 checks; journals pass 10,075,735,
including 1,030,950 event fields and 439,904 bytes. Canonical C execution and
independent scalar per-bit feedback supply the oracles. All 59 Python tests
pass, including ten seeded verifier/admission tests. The complete spatial
build also passes all ten native suites. Eight full-build CLI combinations
(two fixtures, both fetch paths and dispatch modes) reproduce every byte;
seven prefix/no-EMIT/path-alias publication checks pass. Results are in
`review/r18_materialize_cli_checks.json`.

The two native original fixtures produce 866 events / 3,461 bytes and
32,880 events / 131,517 bytes. All twelve event fields, every final State64
word and every artifact byte match fresh original replay. The verifier also
requires literal true artifact-written and source-equality fields. Exact
program/source/output hashes are in `review/r18_world03_verified.json` and
`review/r18_family_authority_verified.json`.

The phase experiment runs 240 fresh-process trials over three programs,
two feedback modes, two dispatch modes, both fetch paths and both builds.
Wide/bounded median device ratios span 0.880x to 1.099x; cold host-complete
ratios span 0.973x to 1.044x. These mixed results establish no universal
speedup. Full-array noncryptographic FNV-1a-64 and exact first-lane fields
agree in every case; individual-word correctness is separate evidence.
Every trial is in `review/r18_phase_runs.json`. These final-only timings
are distinct from complete ordered-artifact costs.

`review/R18_NATIVE_CODE.md` and `r18_native_code.json` bind static resources
and SASS for both measured builds and materializers. All inspected kernels
have zero stack/local allocation and no local loads/stores. Bounded forms
reduce static sites while retaining actual texture instructions, with small
register-count changes in either direction. Static counts establish no
runtime speedup or cache-hit rate. Reproduce with `python tools/audit_r18_native.py`.

The 48 MiB mixed program is reproduced from its checked-in generator/recipe
and excluded from Git and the ZIP; its exact hash is recorded. Program size
alone establishes no VRAM saturation or cache-hit rate.

## Formalization and continuing work

The editable master is `docs/unified.tex`, with new journal/phase chapters
followed by the full retained earlier formalization. Source preparation
verifies authored inputs; rendering, review and packaging bind reviewed
PDF bytes to their sources.

The original compiler evaluates its formal tree on the host before encoding
its result as EMIT cells. R18 executes and materializes those cells natively.
Native formal-AST evaluation, broader expression lowering, non-affine events
and dynamic geometry/cache rebinding remain separate work. The finite PHI
counter, SDF0 zero operator and rational event profile retain their meanings.

Orbital comparisons use their own matched model/frame/time/reference
contract. Exact finite words and complete artifact reproduction alone do
not establish better satellite-position accuracy. Inherited S2, clock,
VRAM and physics results retain their original scope.
