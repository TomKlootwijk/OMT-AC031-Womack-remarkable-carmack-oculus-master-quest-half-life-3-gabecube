from pathlib import Path
import json
root=Path('atomOS_3_6_1_9_ORBIT_SEED');d=json.loads(Path('tmp/orbital_reference_data/final_validation_metrics.json').read_text(encoding='utf-8'));ids=['G05','C03','C06','CHANDRA'];labels={'G05':'G05 / MEO','C03':'C03 / GEO','C06':'C06 / IGSO','CHANDRA':'Chandra / HEO'}
def rows24():return '\n'.join(labels[s]+' & '+' & '.join(f"{d[k][s]['firstday_max']:.3f}" for k in ['R1','R2','confirmation'])+r'\\' for s in ids)
def horizonrows():return '\n'.join(labels[s]+' & '+' & '.join(f"{x['position_error_m']:.3f}" for x in d['R2'][s]['horizons'])+r'\\' for s in ids)
def wholerows():return '\n'.join(labels[s]+' & '+' & '.join(f"{d[k][s][q]:.3f}" for k,q in [('R2','rms'),('R2','max'),('confirmation','rms'),('confirmation','max')])+r'\\' for s in ids)
def threshold(x):
 if not x['observed_exceedance']:return 'None at samples'
 return '$('+f"{x['previous_sample_seconds']/3600:.3f},{x['first_sample_seconds']/3600:.3f}"+']$' if x.get('previous_sample_seconds') is not None else f"First: {x['first_sample_seconds']/3600:.3f} h"
def thresholdrows():return '\n'.join(('January' if k=='R2' else 'February')+' & '+labels[s]+' & '+' & '.join(threshold(x) for x in d[k][s]['thresholds'][:3])+r'\\' for k in ['R2','confirmation'] for s in ids)
audit=json.loads((root/'results/orbit_physical_r2_audit_final/physical_audit.json').read_text(encoding='utf-8'))
numrows='\n'.join(labels[s]+' & '+f"{max(audit['models'][s]['native_vs_dop853_position_m']):.6f}"+' & '+f"{d['confirmation'][s]['num']['position_error']['max_m']:.6f}"+' & '+f"{max(d[k][s]['frame']['max_m'] for k in ['R2','confirmation']):.6f}"+r'\\' for s in ids)
tex=r'''% Evidence fragment: include in the orbital chapter. Retained booktabs,
% tabularx/Y, graphicx, hyperref and xurl suffice; no new packages.
\subsection{R2 physical-position results and separate confirmation}
\label{sec:orbit-validation}

The R2 models stay below the requested \textbf{10 m three-dimensional
reference-discrepancy budget at every tested sample through 24 hours} for all
four targets, on both the January benchmark and the separate February
confirmation date. This statement concerns sampled positions of these seeds;
it is not a universal or continuous-time orbit guarantee.
The January window was previously inspected during R1 development and is
explicitly a \textbf{reused benchmark}. The February selection procedure was
frozen before its future errors were evaluated; no model was retuned afterward.

The forecast quantity is
\[
 e_i=\|\widehat{\boldsymbol r}(t_i)-\boldsymbol r_{\rm reference}(t_i)\|_2,
 \qquad t_i>t_0.
\]
The January origin is 2 January 2025 00:00 GPST,
$t_0=1419811200$; February uses 2 February 2025 00:00 GPST,
$t_0=1422489600$. All cutoff and earlier target rows are excluded from the
forecast curves. R2 selects among 1-, 3- and 7-day training windows using an
internal validation day entirely before the forecast origin. The selected
January windows are 3/3/3/1 days for G05/C03/C06/Chandra; the unchanged rule
selects 1/7/3/3 days for February. External EGM96 gravity and planetary forcing
are distinct from future target observations.

\begin{table}[htbp]
\centering\small
\caption{Maximum discrepancy over all first-day samples (metres). Each R2
column has 288 samples per target through 24 h; Chandra's final sample is
approximately 51.185 s before the exact endpoint.}
\label{tab:orbit-first-day-comparison}
\begin{tabular*}{\linewidth}{@{\extracolsep{\fill}}lrrr@{}}
\toprule
Target & R1 January & R2 January & R2 February\\
\midrule
'''+rows24()+r'''
\bottomrule
\end{tabular*}
\end{table}

\begin{table}[htbp]
\centering\small
\caption{R2 January discrepancy in metres at the nearest actual sample to each
requested horizon. Individual samples are not worst-case interval errors.}
\label{tab:orbit-horizon-samples}
\begin{tabular*}{\linewidth}{@{\extracolsep{\fill}}lrrrrrr@{}}
\toprule
Target & 15 min & 1 h & 6 h & 24 h & 72 h & 7 d\\
\midrule
'''+horizonrows()+r'''
\bottomrule
\end{tabular*}
\end{table}

\textbf{Time grid.} GNSS is on the exact requested GPST grid. Chandra is supplied
on a 300 s TDB grid, converted using the periodic TDB--TT correction and
$\mathrm{GPST}=\mathrm{TT}-51.184\,\mathrm{s}$. The nearest 15 min sample is
848.816057 s after the January origin and 848.815204 s after the February
origin. The final samples are respectively 604748.815856 s and
604748.815036 s. Exact offsets remain in the CSV/JSON, including all six
requested horizons for both dates.

\begin{table}[htbp]
\centering\small
\caption{R2 whole-window statistics (metres). January has 2,016 samples per
target. February has 2,016 each except C03, which has 1,441 and a 48 h gap.}
\label{tab:orbit-period-errors}
\begin{tabular*}{\linewidth}{@{\extracolsep{\fill}}lrrrr@{}}
\toprule
Target & Jan. RMS & Jan. maximum & Feb. RMS & Feb. maximum\\
\midrule
'''+wholerows()+r'''
\bottomrule
\end{tabular*}
\end{table}

The seven-day 10 m requirement is \textbf{not met for all targets}. C06 stays
below it at every seven-day sample on both dates; G05 exceeds it later on both
dates. C03 and Chandra have additional reference qualifications below.
The original R1 seven-day maxima were 7402.960/532.582/1237.242/19399.307 m
in the same object order. The R2 first-day improvement must not be extended
into a claim that every seven-day maximum improved or passed.
RMS and percentiles describe correlated samples, not independent-sample
confidence intervals. Reports additionally retain interval RMS/maxima and
sample percentiles.

\subsection{Sampled thresholds and incomplete reference coverage}
\label{sec:orbit-thresholds}
\begin{table}[htbp]
\centering\small
\caption{Preceding sample and first sampled exceedance, in hours after the
origin, rounded to 0.001 h. These pairs are not certified continuous crossing
brackets. ``None'' means no exceedance at the available samples.}
\label{tab:orbit-first-exceedance}
\begin{tabularx}{\linewidth}{@{}llYYY@{}}
\toprule
Date & Target & 10 m & 100 m & 1 km\\
\midrule
'''+thresholdrows()+r'''
\bottomrule
\end{tabularx}
\end{table}

For 10 km, January Chandra first exceeds the level at 302648.815956 s,
following the sample at 302348.815956 s; all January GNSS targets remain below
10 km at their samples. February C03 first exceeds 10 km at the first sample
after its gap, 432000 s; the previous sample is at 259200 s. Other February
targets remain below 10 km at the sampled times.

\textbf{C03 February coverage.} GFZ contains no C03 records on February 5 and
6. Adjacent daily endpoints leave a 48-hour reference gap and 575 missing
five-minute samples. Wuhan also lacks C03 on February 6 and cannot certify the
missing interval. GFZ remains the predeclared primary source. The first
post-gap discrepancy is 29256.547 m and the later maximum is 100604.174 m;
these observed exceedances are retained. Full-window coverage is
\textbf{indeterminate}, and no continuous tolerance passage through the gap is
inferred. No maneuver or other cause is assigned from missing records alone.
The figures leave the missing interval blank.

\subsection{Numerical error and reference discontinuities}
\label{sec:orbit-error-separation}
\begin{table}[htbp]
\centering\small
\caption{Separate numerical and frame comparisons, in metres. January's
independent physical audit uses 11 times across the past/future domain;
February compares nine future checkpoints with adaptive DOP853. The frame
column is the larger of the two complete sampled frame-approximation maxima.}
\label{tab:orbit-error-components}
\begin{tabular*}{\linewidth}{@{\extracolsep{\fill}}lrrr@{}}
\toprule
Target & Jan. RK4/DOP853 & Feb. RK4/DOP853 & Frame approximation\\
\midrule
'''+numrows+r'''
\bottomrule
\end{tabular*}
\end{table}

Native RK4 uses 30 s for GNSS and 7.5 s for Chandra. Same-seed integration
agreement tests arithmetic, not orbit truth. The January forecast report's
own DOP853 check covers only its first sample; the wider January evidence above
comes from the separate, target-independent physical audit. Native CPU/CUDA
checks and exact word/packing checks remain separate evidence.
The frame test compares the embedded daily-EOP/Chebyshev frame with direct SOFA
IAU 2006/2000A evaluation of the same published prediction. It excludes actual
future EOP error, station uncertainty and a complete relativistic ICRF/GCRS
coordinate error budget; it is not subtracted as an independent scalar variance.

\textbf{Chandra source discontinuities.} The January error rises from
123.204 m to 23839.033 m between two five-minute samples. A separate one-second
Horizons query shows that at January 5 TDB 12:01:09--12:01:10 the source
position displacement differs from the integral of its own reported velocity
by \textbf{24317.077 m}; outside the neighboring jump intervals the same local
check is at most 0.0654 m. Native RK4 agrees with independently tightened
DOP853 to about 1.5 mm at the two forecast endpoints surrounding that jump.
The source header identifies CFA's merged trajectory, but no local join or
maneuver cause. The large discontinuity therefore cannot be attributed solely
to smooth force error or native integration.

The February reference has a corresponding kinematic discontinuity at
February 5 TDB 12:01:09--12:01:10: \textbf{2487.123 m} displacement-minus-velocity
integral mismatch, versus at most $2.26\,\mu\mathrm{m}$ away from its neighboring
intervals. The forecast's next five-minute error rises from 1.053 m to
2492.098 m. These diagnostics use only the source's positions and velocities;
no model is fitted to them. \textbf{All original discrepancy samples and
whole-window maxima are retained.} The cause of the provider discontinuities
is not established, and no corrected ``true orbit'' accuracy is invented.
Original queries, hashes and calculations are in
\path{source/orbit_data/diagnostics/}.

\textbf{Reference uncertainty.} January GFZ/Wuhan comparisons give 3D RMS
0.0263 m for G05, 2.074 m for C03 and 0.1692 m for C06; C03's maximum provider
disagreement is 3.575 m. These are product differences, not certified absolute
bounds. Providers share some underlying observations. Chandra supplies no
state covariance or absolute position guarantee. A millimetre or sub-metre
match to a selected reference is therefore not a matching physical-accuracy
claim.

\subsection{Chronology, source conventions and reproducible evidence}
\label{sec:orbit-provenance}
The R2 physical model uses the documented degree/order-12 EGM96 field,
cutoff-available daily Earth orientation, and external Sun/Moon forcing.
EGM96's original mu, reference radius, tide-free convention and fully normalized
coefficients are preserved with explicit conversion in
\path{source/orbit_data/gravity_reference/}. The format's normalization default
is documented by ICGEM:
\url{https://icgem.gfz.de/docs/ICGEM-Format-2023.pdf}.

The EOP sources were published before their cutoffs: IERS Bulletin A of
26 December 2024 and 30 January 2025, respectively:
\url{https://datacenter.iers.org/data/6/bulletina-xxxvii-052.txt} and
\url{https://datacenter.iers.org/data/6/bulletina-xxxviii-005.txt}.
Both permit public release and unlimited distribution.
The February GFZ reference changes from IGS20 to IGb20. IGSMAIL-8543, published
9 December 2024, specifies zero datum transformation parameters because origin,
scale and orientation remain aligned; individual reference-station coordinates
are updated. Preserve each source label and apply no fitted alignment:
\url{https://lists.igs.org/pipermail/igsmail/2024/008539.html}.

Precise target products were retrieved retrospectively; their earlier estimates
can incorporate later observations within provider processing. Neither date
proves that identical seeds were available live in 2025. January is a reused
comparison, while February applies the already-frozen selection rule to a
separate date. The confirmation freeze manifest binds the rule and model-file
hashes. Raw source acquisition and coverage inspection preceded any February
prediction-error evaluation. No later error was used to refit a seed.

\begin{itemize}
\item \textbf{GFZ and IGS.} Retain GFZ/IGS provider and network attribution.
The cited GFZ product-series DOI is
\url{https://doi.org/10.5880/GFZ.1.1.2016.003}; its DataCite record declares
\textbf{CC BY-NC 4.0}. The DOI names an ultra-rapid series whereas these GBM
files are rapid products without a separate per-file grant. The fixture bundle
conservatively retains that noncommercial qualification and is not claimed as
unrestricted commercial data. IGS terms:
\url{https://www.igs.org/wp-content/uploads/2020/09/IGS-Data-and-Product-Disclaimer-and-Terms-of-Use-200805.pdf}.
\item \textbf{CODE and Wuhan.} CODE's reference
\url{https://doi.org/10.48350/197028} lists open access/BORIS terms, not a blanket
MIT grant. Wuhan final products retain provider/IGS attribution. Original
archive URLs and per-file hashes remain in the source manifests.
\item \textbf{NASA/JPL and CFA.} Acknowledge Giorgini and the JPL Solar System
Dynamics Group, NASA/JPL Horizons, and CFA for Chandra:
\url{https://ssd.jpl.nasa.gov/horizons/}.
Retrieval date is 15 September 2026. Geometric ICRF/TDB settings and original
responses are retained. Sun/Moon Horizons responses identify DE441; the
construction oracle is DE440s, a distinct planetary ephemeris version.
\end{itemize}

\textbf{Authoritative reports.} Use
\path{results/orbit_accuracy_r2_cpu_verified/accuracy_summary.json}, its CUDA
counterpart, and
\path{results/orbit_accuracy_confirmation_cpu_verified/accuracy_summary.json}.
R1 evidence remains in \path{results/orbit_accuracy_cpu_final/} for comparison.
The pre-fix failed trial and superseded intermediate models are not final
accuracy evidence. CSVs retain every measured error, exact horizon offset,
source and frame. Each report distinguishes \path{model_file_sha256} from
\path{physical_model_sha256}=\path{orbit_seed.digest(model)}; legacy
\path{model_sha256} is explicitly the file-hash alias. Accuracy displayed for a
custom packed seed applies only when the physical-model digest matches.
Reference fixtures, publications and the DE440s construction binary are
separate from the complete replay seed byte count.

\clearpage
\subsection{R2 January benchmark curves}
\label{sec:orbit-first-day-plot}
\begin{center}
\includegraphics[width=\linewidth]{../results/orbit_accuracy_r2_cpu_verified/forecast_error_curves.pdf}
\end{center}
This is the reused January benchmark. Dotted lines are reporting thresholds,
not fitted constraints. The Chandra source discontinuity remains visible and
its errors remain counted. First-day detail is also supplied as
\path{forecast_error_first_day.pdf} in the same result directory.

\clearpage
\subsection{Separate February confirmation curves}
\label{sec:orbit-full-week-plot}
\begin{center}
\includegraphics[width=\linewidth]{../results/orbit_accuracy_confirmation_cpu_verified/forecast_error_curves.pdf}
\end{center}
The selection rule was frozen before this date's errors were evaluated. The
C03 reference gap is blank; connecting its endpoints would imply unavailable
measurements. Chandra's source discontinuity is retained. Lines join only
available adjacent samples and do not certify error between samples or beyond
the declared window.
'''
(root/'docs/orbit_validation.tex').write_text(tex,encoding='ascii')
# Markdown references use the same source reports and computed tables.
md='''# Orbital forecast and reference validation\n\nR2 meets the requested **10 m discrepancy budget at every first-day reference sample for all four targets**, both on the reused January benchmark and on a separate frozen February confirmation. It does **not** meet a seven-day budget for all targets. These are sampled discrepancies from external reference products, not certified continuous or universal physical bounds.\n\n## Results\n\n| Target | R1 January first-day max (m) | R2 January first-day max (m) | R2 February first-day max (m) |\n|---|---:|---:|---:|\n'''
for s in ids:md+='| '+labels[s]+' | '+' | '.join(f"{d[k][s]['firstday_max']:.6f}" for k in ['R1','R2','confirmation'])+' |\n'
md+='\nEach R2 first-day result contains 288 samples. Chandra is sampled on its original TDB grid and ends approximately51.185s before the exact24h request; exact offsets are retained.\n\n| Target | R2 January whole-window RMS/max (m) | February RMS/max (m) | February samples |\n|---|---:|---:|---:|\n'
for s in ids:md+='| '+labels[s]+' | '+f"{d['R2'][s]['rms']:.3f} / {d['R2'][s]['max']:.3f}"+' | '+f"{d['confirmation'][s]['rms']:.3f} / {d['confirmation'][s]['max']:.3f}"+' | '+str(d['confirmation'][s]['count'])+' |\n'
md+='''\n**C03 February coverage is incomplete:** GFZ omits February5 and6, leaving575 missing grid points and a48h gap. Its first post-gap observed error is29256.547m; the whole-window observed maximum is100604.174m. This is both an observed tolerance failure and indeterminate coverage through the gap. Wuhan also lacks February6. PrimaryGFZ was retained; no gap was filled or source selected from prediction errors. Curves leave missing intervals blank.\n\nC06 stays below10m at every seven-day sample on both dates. G05 eventually exceeds10m on both. The Chandra whole-window results require the source-discontinuity qualification below. Baseline R1 seven-day maxima in target order were7402.960/532.582/1237.242/19399.307m; improved first-day results do not imply that every seven-day maximum improved.\n\n## Reproduce the evaluations\n\nThe validator reads frozen model envelopes containing `model`, `fit` and `construction`. The physical `model` alone is sufficient for replay. Validation additionally uses NumPy, SciPy, Matplotlib and pyerfa. ERFA independently converts Chandra TDB and evaluates coordinate transforms. Construction/review dependencies are distinct from replay dependencies. Run from the release directory with these packages available; task-local ERFA is under workspace `tmp/orbit_model_deps`.\n\n```powershell\npython tools/validate_orbit_accuracy.py --models examples/orbit/precision_models --data source/orbit_data --binary C:/tmp/atomos3619_r2_cpu/Release/orbit_worker.exe --benchmark-role reused_development --out results/january_new_run\npython tools/validate_orbit_accuracy.py --models examples/orbit/confirmation_models --data source/orbit_data/confirmation_20250202/holdout --chandra-reference source/orbit_data/confirmation_20250202/holdout/HORIZONS_CHANDRA_20250202_20250209_ICRF_TDB.txt --bulletin source/orbit_data/confirmation_20250202/eop/bulletina-xxxviii-005.txt --binary C:/tmp/atomos3619_r2_cpu/Release/orbit_worker.exe --benchmark-role independent_confirmation --procedure-manifest examples/orbit/confirmation_models/freeze_manifest.json --out results/february_new_run\n```\n\nOutput directories must be new. Use `--backend cuda` with the matching CUDA worker. `--objects` selects a subset and labels four-class scope accordingly. `--python-checks` must be positive; default9. January's executed forecast reports used one early DOP853 check, while the independent physical audit separately checks11 times across its domain. February's executed report uses9 future checkpoints. `--sp3-source OBJECT "PATH_GLOB"` explicitly overrides the SP3 source for one object; default remains GFZ rapid files under `--data`. Neither February's primary source nor its model was changed after prediction errors were read.\n\n`--benchmark-role` explicitly separates `reused_development`, `independent_confirmation`, and a retrospective baseline. This records the declared design; it does not itself prove independence. An optional `--procedure-manifest` records and verifies the frozen procedure-file hash. The bulletin's actual publication date is parsed and must precede the cutoff UTC date; a later bulletin fails before native queries. Original January defaults remain compatible.\n\n## Cutoff, frame and chronology\n\nJanuary origin:2025-01-02 00:00GPST,1419811200s. February origin:2025-02-02 00:00GPST,1422489600s. R2's fixed rule selects among1/3/7day fits using a held-out day entirely before each origin. Selected windows are3/3/3/1days in January and1/7/3/3days in February. The February freeze manifest predates its error evaluation. January is explicitly reused because earlier results informed the revision; no January re-evaluation is described as blind confirmation.\n\nThe validator checks all declared training-source hashes, training_end_s<=0, and zero declared future-target rows, then excludes all reference rows at or before the origin. Actual builder data flow also requires review: metadata alone cannot prove absence of leakage. Finite but large measured error remains a valid result. Missing entire reference sets, malformed headers, unsupported frames/time labels, truncation or predicted-position flags fail. Partial satellite gaps remain explicit in coverage and maximum-gap fields; four requested object classes do not imply complete temporal coverage.\n\nSP3 fixed-column positions are converted fromkm tom. January GFZ isIGS20; February GFZ holdout isIGb20. Both labels are preserved. [IGSMAIL-8543](https://lists.igs.org/pipermail/igsmail/2024/008539.html), published9December2024, specifies zero datum transformation parameters because origin/scale/orientation remain aligned, while reference-station coordinates are updated. No fitted alignment is applied. Duplicate midnight estimates use the earlier source filename, with differences recorded.\n\nChandra uses Earth-centred geometric ICRF positions/velocities inkm/km/s and calendarTDB. Rounded printed Julian dates are consistency checked; the calendar labels retain the sampling grid. Geocentric SOFA/ERFA TDB-TT is iterated, thenGPST=TT-51.184s. January/February first future times are248.816057s/248.815204s, not artificially rounded to300s. ICRF/GCRS-like axes are compared without claiming a complete relativistic coordinate uncertainty bound.\n\nTarget products were retrieved retrospectively and their earlier estimates may use later observations in provider processing. These experiments do not prove that identical inputs were publicly available live at the2025 origins. The external EOP predictions do predate each origin: [December26BulletinA](https://datacenter.iers.org/data/6/bulletina-xxxvii-052.txt) and [January30BulletinA](https://datacenter.iers.org/data/6/bulletina-xxxviii-005.txt). Both permit public release/unlimited distribution.\n\n## Separate numerical, frame and reference evidence\n\nThe forecast discrepancy compares native positions against external target positions. Same-seed DOP853/RK4 agreement tests arithmetic and integration, not truth. February's nine-checkpoint maxima are0.026461/0.001023/0.001026/0.147044m. The target-independent January physical audit checks11 past/future times and finds maxima0.031716/0.001232/0.001252/0.036582m. Native RK4 steps are30s forGNSS and7.5s forChandra. The frame check uses directSOFAIAU2006/2000A with the same published daily predictions; it measures approximation to that forecast, not actual later EOP error or station uncertainty. Do not subtract these quantities as independent scalar variances. Exact packing and CPU/CUDA arithmetic are separately audited.\n\n**Chandra's external reference has measured kinematic discontinuities.** OnJanuary5TDB12:01:09--12:01:10 its displacement minus integrated source velocity is24317.077m, versus at most0.0654m away from neighboring jump intervals. Native versus tightenedDOP853 agrees to about1.5mm at the surrounding five-minute endpoints. February5at the sameTDBclock interval shows2487.123m source mismatch, versus at most2.26micrometres away from neighboring intervals. The response identifies CFA's merged trajectory but gives no local join/maneuver explanation. These calculations use only reference positions/velocities and cannot establish the physical cause. They show that the large sampled jumps must not be attributed solely to native integration or smooth-model force error. **All original errors and maxima remain counted; no corrected true-orbit accuracy is invented.**\n\nEvidence:`source/orbit_data/diagnostics/chandra_one_second_continuity.json`, `chandra_february_one_second_continuity.json`, original queries and hashes. The initial unsupported second-unit API request is explicitly marked failed; valid one-second data use the documented unitless interval count. Numerical endpoint audit:`results/orbit_physical_r2_jump_audit/physical_audit.json`.\n\nJanuaryGFZ/Wuhan3DRMS discrepancies are0.0263mG05,2.074mC03,0.1692mC06; C03maximum3.575m. These are provider differences, not certified absolute bounds, and shared observations weaken statistical independence. Chandra supplies no state covariance or certified positional bound. Tiny early agreement must not be relabeled as equivalent physical accuracy.\n\n## Evidence files and terms\n\nAuthoritative R2 reports are `results/orbit_accuracy_r2_cpu_verified/accuracy_summary.json`, its CUDA counterpart, and `results/orbit_accuracy_confirmation_cpu_verified/accuracy_summary.json`. R1 remains in `results/orbit_accuracy_cpu_final`. Failed and superseded trials are clearly labeled and are not final evidence. `summary.json` is a byte-identical alias. Per-objectCSV files retain all sample errors, timestamps and frames. Reports distinguish the model-envelope `model_file_sha256` from canonical `physical_model_sha256=orbit_seed.digest(model)`; legacy `model_sha256` is the explicitly documented file-hash alias. Any accuracy claim for a custom packed seed requires a matching physical-model digest.\n\nReports retain intervalRMS/max/percentiles, nearest15min/1h/6h/24h/72h/7day samples and exact offsets, plus first sampled10m/100m/1km/10km exceedances. A preceding/first-exceeding pair is not a certified first continuous crossing. Errors can cross and return between samples, and C03's reference gap invalidates a crossing inference through that interval. Samples are correlated; no confidence interval or general operational protection level is inferred. The two scientific plot pages in the PDF show JanuaryR2 and separateFebruary curves; first-day plots are also included as standalone artifacts.\n\nOriginal source and derived-file manifests are under `source/orbit_data`, `earlier_training`, `gravity_reference`, and `confirmation_20250202`. Full provenance and licensing are in their README files and `docs/ORBIT_TRAINING_PROVENANCE.md`. Retain GFZ/IGS attribution and the GFZ product-series **CCBY-NC4.0** qualification at [DOI10.5880/GFZ.1.1.2016.003](https://doi.org/10.5880/GFZ.1.1.2016.003); the DOI names ultra-rapid products while these bytes are rapid products without a separate per-file grant. CODE's [DOI10.48350/197028](https://doi.org/10.48350/197028) lists open-access/BORIS terms, not a blanketMITgrant. Wuhan retains provider/IGS attribution. Acknowledge [NASA/JPLHorizons](https://ssd.jpl.nasa.gov/horizons/), Giorgini/JPLSolarSystemDynamicsGroup and CFAforChandra.\n\nEGM96source constants, tide-free convention and normalization are explicit; the [ICGEMformat](https://icgem.gfz.de/docs/ICGEM-Format-2023.pdf) specifies fully_normalized as the default. Sun/MoonHorizons references identifyDE441, while the construction oracle isDE440s. Original orbit fixtures, external oracle binaries and documentation have separate terms and byte accounting from the complete replay seed.\n'''
# Keep technical prose readable: expand recurring source abbreviations in the draft text.
replacements={'approximately51.185s':'approximately 51.185 s','exact24h':'exact 24 h','February5':'February 5','February6':'February 6','gap48h':'gap 48 h','a48h':'a 48 h','leaving575':'leaving 575','source1':'source 1','primaryGFZ':'primary GFZ','PrimaryGFZ':'Primary GFZ','at300':'at 300','at most0.':'at most 0.','are0.':'are 0.','are3/':'are 3/','and1/':'and 1/','beforeGPST':'before GPST','through24':'through 24','under10m':'under 10 m','below10m':'below 10 m','all10m':'all 10 m','seven-day10m':'seven-day 10 m','forGNSS':'for GNSS','forChandra':'for Chandra','about1.5mm':'about 1.5 mm','day1':'day 1','one early DOP853 check':'one early DOP853 check','default9':'default 9','checks11':'checks 11','are30s':'are 30 s','and7.5s':'and 7.5 s','December26':'December 26','January30':'January 30','9December2024':'9 December 2024','CFAforChandra':'CFA for Chandra','NASA/JPLHorizons':'NASA/JPL Horizons','CCBY-NC4.0':'CC BY-NC 4.0','blanketMITgrant':'blanket MIT grant','EGM96source':'EGM96 source','CODE\'s':'CODE\'s','Sun/MoonHorizons':'Sun/Moon Horizons','identifyDE441':'identify DE441','isDE440s':'is DE440s','fromkm tom':'from km to m','isIGS20':'is IGS20','isIGb20':'is IGb20','calendarTDB':'calendar TDB','thenGPST':'then GPST','Jan2':'Jan 2','directSOFAIAU2006/2000A':'direct SOFA IAU 2006/2000A','JanuaryGFZ/Wuhan3DRMS':'January GFZ/Wuhan 3D RMS','RMS/max/percentiles':'RMS/max/percentiles','intervalRMS':'interval RMS','per-objectCSV':'per-object CSV','Per-objectCSV':'Per-object CSV','first sampled10m':'first sampled 10 m','JanuaryR2':'January R2','separateFebruary':'separate February','the2025':'the 2025','before each origin':'before each origin','sets, malformed':'sets, malformed'}
for a,b in replacements.items():md=md.replace(a,b)
(root/'docs/ORBIT_REFERENCE_VALIDATION.md').write_text(md,encoding='utf-8')
print('Wrote final R2/confirmation TeX and Markdown. TeX plot includes:',tex.count('includegraphics'))
