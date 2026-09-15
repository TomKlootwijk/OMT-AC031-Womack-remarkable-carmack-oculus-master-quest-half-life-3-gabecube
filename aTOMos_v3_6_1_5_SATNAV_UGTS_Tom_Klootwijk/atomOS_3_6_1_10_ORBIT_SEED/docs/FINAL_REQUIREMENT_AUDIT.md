# R10 completion audit

The 3.6.1.10 implementation preserves the complete orbital seed and literal word
equations while accelerating exact packing and query preparation. The checked
evidence and its SHA-256 bindings are indexed in `../validation_results.json`.

| Requirement | Recorded result |
|---|---|
| Complete seed and isolated reconstruction | All eight packed files retain their R9 bytes. Four isolated runtime cases deny reads of the original release and reconstruct timestamp states. Separate execution checks verify feedback and visibility events. Shared modules and native runtime remain required. |
| Literal ASA/NA and synchronous JK | Two ordered mask sets, whole-word absorption, editable equations and independent AST replay remain. A counterfactual JK equation changes the query schedule while common-time physical states agree. |
| Native CPU/CUDA and orbit classes | MEO, GEO, IGSO and high elliptical examples pass the native checks. Ten packaged binaries match the recorded builds; four CTests per backend pass. |
| Full geometry and time | ECEF/ENU, Up, velocity, GPST, absolute tick, winding, both original key layouts and provenance remain. Session snapshots prevent caller edits from changing active identity. |
| Visibility and prediction horizons | Seven-day station event searches and refinement remain verified. Grazing/between-sample event limitations and forecast-error horizons remain explicit. |
| Physical accuracy | Frozen January and February sampled first-day comparisons remain below the adopted 10 m engineering target. Longer errors, February C03 gaps and Chandra reference discontinuities remain visible. No new fitting or universal bound is claimed. |
| Execution and packing evidence | 164 Python tests pass. The native audit includes 1,040 CUDA trajectories, 256 complete word transitions and zero Compute Sanitizer errors. Exact transpose proof, 4,096 basis vectors, 300,000-word boundary checks and all eight seed byte identities pass. |
| Document and distribution | The 74-page PDF includes actual equations and source decisions, with all pages visually reviewed. The runtime ZIP is verified; the full manifest/ZIP is generated after final indexing. All 775 parent manifest entries remain unchanged. |
| Gregorian calendar continuity | All 146,097 dates in 2000-2399 plus the next boundary, century exceptions, all phase carries in the interval and both key layouts are checked: 9,519,315 comparisons, zero failures. The year and winding continue through phase wraps. |

The complete CPU replay reproduces 15,553 parent positions exactly. January's
8,064 CUDA positions match the prior CUDA baseline exactly. February's 7,489
CUDA positions are compared with CPU and differ by at most 0.220015 mm, within
the 10 mm numerical agreement contract. That is not a claim of bit-identical
CPU/GPU arithmetic or physical satellite truth.

The long CUDA run imported the preceding wrapper. Its exact source is retained
and the compatibility report proves byte-identical native payloads and unchanged
query functions, followed by actual final-wrapper CUDA checks on all eight seeds.
The final index describes this composition explicitly. The query-preparation
benchmark deliberately holds the R9 worker fixed to isolate Python overhead.

The supplied phi document informs finite word organization. Invalid shifts,
noninvertible integer transforms and insufficient angular precision are audited
in `PHI_SOURCE_AUDIT.md`; they are not substituted for physical propagation.
Lossless packing preserves binary64 bits and does not eliminate integration or
model error. Calendar verification does not extend any physical forecast domain
or verify UTC leap-second tables.

Reproduce the release binding with `python tools/finalize_seed_optimization.py`
while the preserved R9 sibling and runtime ZIP are available. Then generate the
full archive with `tools/build_package.py` and verify its extracted manifest with
`tools/verify_package.py`. The final archive hash belongs in the external delivery
report, avoiding a self-referential manifest.
