# Review aTOMos SATNAV-R1

Read README.md and docs/{INPUT,CONTRACT,SOURCE_DECISIONS}.md before changing code.
Retain the literal source OTAN2 profile and U's two distinct key layouts. Do not
quantize ECEF pseudorange geometry into the SCLP key or erase the Up/time/clock fields.
Never replace the whole-word absorption operation by per-bit clearing without a new
explicit profile. Do not label a residual budget, covariance or supplied support bound
as certified GNSS integrity. No RF generation, spoofing, jamming, live steering or
weapon/action loop is part of this repository.

Run CPU CMake/CTest, Python tests and the independent verify_run.py on a new output
directory. Before claiming CUDA success run tools/validate_gpu.py --sanitizer on the
actual compatible GPU. Record compiler, runtime, device and logs. Missing tools mean
not_run, not pass. Fix concrete defects with regression tests and do not change tests
to hide mismatches. The upstream UGTS PDF's earlier 153 tests were not supplied as code.
