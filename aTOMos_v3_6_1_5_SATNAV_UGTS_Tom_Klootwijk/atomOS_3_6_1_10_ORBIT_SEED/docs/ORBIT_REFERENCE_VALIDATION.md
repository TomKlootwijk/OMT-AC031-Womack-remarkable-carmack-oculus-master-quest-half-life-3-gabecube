# Orbital forecast and reference validation

R2 meets the requested **10 m discrepancy budget at every first-day reference sample for all four targets**, both on the reused January benchmark and on a separate frozen February confirmation. It does **not** meet a seven-day budget for all targets. These are sampled discrepancies from external reference products, not certified continuous or universal physical bounds.

## Results

| Target | R1 January first-day max (m) | R2 January first-day max (m) | R2 February first-day max (m) |
|---|---:|---:|---:|
| G05 / MEO | 285.330289 | 1.056645 | 3.071808 |
| C03 / GEO | 20.599831 | 5.304255 | 4.654148 |
| C06 / IGSO | 44.684370 | 1.172334 | 2.107835 |
| Chandra / HEO | 76.506339 | 8.092836 | 0.289813 |

Each R2 first-day result contains 288 samples. Chandra is sampled on its original TDB grid and ends approximately 51.185 s before the exact 24 h request; exact offsets are retained.

| Target | R2 January whole-window RMS/max (m) | February RMS/max (m) | February samples |
|---|---:|---:|---:|
| G05 / MEO | 5.294 / 12.998 | 33.113 / 71.800 | 2016 |
| C03 / GEO | 37.434 / 78.717 | 39382.862 / 100604.174 | 1441 |
| C06 / IGSO | 2.943 / 8.084 | 3.494 / 7.629 | 2016 |
| Chandra / HEO | 5412.235 / 25635.951 | 2055.685 / 5663.182 | 2016 |

**C03 February coverage is incomplete:** GFZ omits February 5 and 6, leaving 575 missing grid points and a 48 h gap. Its first post-gap observed error is 29256.547 m; the whole-window observed maximum is 100604.174 m. This is both an observed tolerance failure and indeterminate coverage through the gap. Wuhan also lacks February 6. Primary GFZ was retained; no gap was filled or source selected from prediction errors. Curves leave missing intervals blank.

C06 stays below 10 m at every seven-day sample on both dates. G05 eventually exceeds 10 m on both. The Chandra whole-window results require the source-discontinuity qualification below. Baseline R1 seven-day maxima in target order were 7402.960 / 532.582 / 1237.242 / 19399.307 m; improved first-day results do not imply that every seven-day maximum improved.

## Reproduce the evaluations

The validator reads frozen model envelopes containing `model`, `fit` and `construction`. The physical `model` alone is sufficient for replay. Validation additionally uses NumPy, SciPy, Matplotlib and pyerfa. ERFA independently converts Chandra TDB and evaluates coordinate transforms. Construction/review dependencies are distinct from replay dependencies. Run from the release directory with these packages available; task-local ERFA is under workspace `tmp/orbit_model_deps`.

```powershell
python tools/validate_orbit_accuracy.py --models examples/orbit/precision_models --data source/orbit_data --binary C:/tmp/atomos3619_r2_cpu/Release/orbit_worker.exe --benchmark-role reused_development --out results/january_new_run
python tools/validate_orbit_accuracy.py --models examples/orbit/confirmation_models --data source/orbit_data/confirmation_20250202/holdout --chandra-reference source/orbit_data/confirmation_20250202/holdout/HORIZONS_CHANDRA_20250202_20250209_ICRF_TDB.txt --bulletin source/orbit_data/confirmation_20250202/eop/bulletina-xxxviii-005.txt --binary C:/tmp/atomos3619_r2_cpu/Release/orbit_worker.exe --benchmark-role independent_confirmation --procedure-manifest examples/orbit/confirmation_models/freeze_manifest.json --out results/february_new_run
```

Output directories must be new. Use `--backend cuda` with the matching CUDA worker. `--objects` selects a subset and labels four-class scope accordingly. `--python-checks` must be positive; default 9. January's executed forecast reports used one early DOP853 check, while the independent physical audit separately checks 11 times across its domain. February's executed report uses 9 future checkpoints. `--sp3-source OBJECT "PATH_GLOB"` explicitly overrides the SP3 source for one object; default remains GFZ rapid files under `--data`. Neither February's primary source nor its model was changed after prediction errors were read.

`--benchmark-role` explicitly separates `reused_development`, `independent_confirmation`, and a retrospective baseline. This records the declared design; it does not itself prove independence. An optional `--procedure-manifest` records and verifies the frozen procedure-file hash. The bulletin's actual publication date is parsed and must precede the cutoff UTC date; a later bulletin fails before native queries. Original January defaults remain compatible.

## Cutoff, frame and chronology

January origin: 2025-01-02 00:00 GPST, or 1419811200 s. February origin: 2025-02-02 00:00 GPST, or 1422489600 s. R2's fixed rule selects among 1-, 3- and 7-day fits using a held-out day entirely before each origin. Selected windows are 3/3/3/1 days in January and 1/7/3/3 days in February. The February freeze manifest predates its error evaluation. January is explicitly reused because earlier results informed the revision; no January re-evaluation is described as blind confirmation.

The validator checks all declared training-source hashes, `training_end_s <= 0`, and zero declared future-target rows, then excludes all reference rows at or before the origin. Actual builder data flow also requires review: metadata alone cannot prove absence of leakage. Finite but large measured error remains a valid result. Missing entire reference sets, malformed headers, unsupported frames/time labels, truncation or predicted-position flags fail. Partial satellite gaps remain explicit in coverage and maximum-gap fields; four requested object classes do not imply complete temporal coverage.

SP3 fixed-column positions are converted from km to m. January GFZ is IGS20; February GFZ holdout is IGb20. Both labels are preserved. [IGSMAIL-8543](https://lists.igs.org/pipermail/igsmail/2024/008539.html), published 9 December 2024, specifies zero datum transformation parameters because origin/scale/orientation remain aligned, while reference-station coordinates are updated. No fitted alignment is applied. Duplicate midnight estimates use the earlier source filename, with differences recorded.

Chandra uses Earth-centred geometric ICRF positions/velocities in km and km/s and calendar TDB. Rounded printed Julian dates are consistency checked; the calendar labels retain the sampling grid. Geocentric SOFA/ERFA TDB-TT is iterated, then GPST = TT - 51.184 s. January/February first future times are 248.816057 s / 248.815204 s, not artificially rounded to 300 s. ICRF/GCRS-like axes are compared without claiming a complete relativistic coordinate uncertainty bound.

Target products were retrieved retrospectively and their earlier estimates may use later observations in provider processing. These experiments do not prove that identical inputs were publicly available live at the 2025 origins. The external EOP predictions do predate each origin: [December 26 Bulletin A](https://datacenter.iers.org/data/6/bulletina-xxxvii-052.txt) and [January 30 Bulletin A](https://datacenter.iers.org/data/6/bulletina-xxxviii-005.txt). Both permit public release/unlimited distribution.

## Separate numerical, frame and reference evidence

The forecast discrepancy compares native positions against external target positions. Same-seed DOP853/RK4 agreement tests arithmetic and integration, not truth. February's nine-checkpoint maxima are 0.026461 / 0.001023 / 0.001026 / 0.147044 m. The target-independent January physical audit checks 11 past/future times and finds maxima 0.031716 / 0.001232 / 0.001252 / 0.036582 m. Native RK4 steps are 30 s for GNSS and 7.5 s for Chandra. The frame check uses direct SOFA IAU 2006/2000A with the same published daily predictions; it measures approximation to that forecast, not actual later EOP error or station uncertainty. Do not subtract these quantities as independent scalar variances. Exact packing and CPU/CUDA arithmetic are separately audited.

**Chandra's external reference has measured kinematic discontinuities.** On January 5 TDB 12:01:09--12:01:10 its displacement minus integrated source velocity is 24317.077 m, versus at most 0.0654 m away from neighboring jump intervals. Native versus tightened DOP853 agrees to about 1.5 mm at the surrounding five-minute endpoints. February 5 at the same TDB clock interval shows 2487.123 m source mismatch, versus at most 2.26 micrometres away from neighboring intervals. The response identifies CFA's merged trajectory but gives no local join/maneuver explanation. These calculations use only reference positions/velocities and cannot establish the physical cause. They show that the large sampled jumps must not be attributed solely to native integration or smooth-model force error. **All original errors and maxima remain counted; no corrected true-orbit accuracy is invented.**

Evidence: `source/orbit_data/diagnostics/chandra_one_second_continuity.json`, `chandra_february_one_second_continuity.json`, original queries and hashes. The initial unsupported second-unit API request is explicitly marked failed; valid one-second data use the documented unitless interval count. Numerical endpoint audit: `results/orbit_physical_r2_jump_audit/physical_audit.json`.

January GFZ/Wuhan 3D RMS discrepancies are 0.0263 m for G05, 2.074 m for C03 and 0.1692 m for C06; C03 maximum 3.575 m. These are provider differences, not certified absolute bounds, and shared observations weaken statistical independence. Chandra supplies no state covariance or certified positional bound. Tiny early agreement must not be relabeled as equivalent physical accuracy.

## Evidence files and terms

Authoritative R2 reports are `results/orbit_accuracy_r2_cpu_verified/accuracy_summary.json`, its CUDA counterpart, and `results/orbit_accuracy_confirmation_cpu_verified/accuracy_summary.json`. R1 remains in `results/orbit_accuracy_cpu_final`. Failed and superseded trials are clearly labeled and are not final evidence. `summary.json` is a byte-identical alias. Per-object CSV files retain all sample errors, timestamps and frames. Reports distinguish the model-envelope `model_file_sha256` from canonical `physical_model_sha256=orbit_seed.digest(model)`; legacy `model_sha256` is the explicitly documented file-hash alias. Any accuracy claim for a custom packed seed requires a matching physical-model digest.

Reports retain interval RMS/max/percentiles, nearest 15 min / 1 h / 6 h / 24 h / 72 h / 7 day samples and exact offsets, plus first sampled 10 m / 100 m / 1 km / 10 km exceedances. A preceding/first-exceeding pair is not a certified first continuous crossing. Errors can cross and return between samples, and C03's reference gap invalidates a crossing inference through that interval. Samples are correlated; no confidence interval or general operational protection level is inferred. The two scientific plot pages in the PDF show January R2 and separate February curves; first-day plots are also included as standalone artifacts.

Original source and derived-file manifests are under `source/orbit_data`, `earlier_training`, `gravity_reference`, and `confirmation_20250202`. Full provenance and licensing are in their README files and `docs/ORBIT_TRAINING_PROVENANCE.md`. Retain GFZ/IGS attribution and the GFZ product-series **CC BY-NC 4.0** qualification at [DOI 10.5880/GFZ.1.1.2016.003](https://doi.org/10.5880/GFZ.1.1.2016.003); the DOI names ultra-rapid products while these bytes are rapid products without a separate per-file grant. CODE's [DOI 10.48350/197028](https://doi.org/10.48350/197028) lists open-access/BORIS terms, not a blanket MIT grant. Wuhan retains provider/IGS attribution. Acknowledge [NASA/JPL Horizons](https://ssd.jpl.nasa.gov/horizons/), Giorgini and the JPL Solar System Dynamics Group and CFA for Chandra.

EGM96 source constants, tide-free convention and normalization are explicit; the [ICGEM format](https://icgem.gfz.de/docs/ICGEM-Format-2023.pdf) specifies fully_normalized as the default. Sun/Moon Horizons references identify DE441, while the construction oracle is DE440s. Original orbit fixtures, external oracle binaries and documentation have separate terms and byte accounting from the complete replay seed.
