# Build status — delivered edition

The `results/validation_status.json` record is authoritative for the delivered run.

| Check | Status |
|---|---|
| C++17 release build, Linux | Passed |
| C++ tests | 30 groups / 73,559 assertions passed |
| Independent Python tests | 21 passed |
| CLI integration | 10 scenarios passed |
| CTest | 3 targets passed |
| ASan/UBSan CTest | Same 3 targets passed |
| Independent scalar oracle | 65,536 samples per layout; maximum error 0 in both delivered runs |
| CUDA compilation | Not executed: `nvcc` unavailable |
| CUDA execution / Compute Sanitizer | Not executed: NVIDIA device unavailable |
| Windows compilation | Not executed |

`compute_ms` in bundled examples is CPU timing for the numerical evaluation loop. It excludes fixture construction and file output. It is not a GPU estimate. New local evidence belongs in a new report directory, not in the delivered result files.
