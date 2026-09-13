# Evidence inventory

`validation_status.json` is the release summary. `proofs.json` contains the fifteen
actual Z3 results, each bound to its SMT-LIB file hash. `cpp_tests.txt`, `ctest.txt`,
`sanitizer_ctest.txt` and `python_tests.txt` are actual local outputs.

`cpu_matrix_evidence/` contains all 48 independently checked CPU run payloads, their
full command logs, unsigned run-integrity seals, and
the original validation report. The commands inside that report retain the actual
preparation paths; the corresponding run subdirectories are bundled here. These are
CPU results, not substituted GPU data.

`demo_morton/` and `demo_tail/` are two additional complete worked runs with independent
verification summaries and retained-reference SHA-256 seals. `cli_tests.json` records
12 command-line success/refusal cases. `corruption_tests.json` records four changes
rejected by the independent verifier. `cuda_availability.txt` records the unavailable
compiler preflight, rather than a fabricated compilation or GPU result.

Run `python tools/verify_evidence.py` from the package root to recompute every bundled
matrix result and verify its seal without needing CUDA or a host C++ compiler. Run
`python proofs/check_proofs.py` to repeat the symbolic claims with an available Z3
binary/library. Neither check is described as GPU execution.
