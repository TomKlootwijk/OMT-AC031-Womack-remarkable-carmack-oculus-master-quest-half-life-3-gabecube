"""Build the final measured-residency report from completed execution evidence."""
from pathlib import Path
from html import escape
import json
from collections import Counter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4

ROOT = Path(__file__).resolve().parents[1]
E = ROOT / 'results/residency_followup'
def read(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
S = read(E / 'summary.json')
B = read(S['bulk_study_path'])
X = read(S['edge_study_path'])
G = read(S['gpu_validation_path'])
C = read(S['cpu_validation_path'])
N = read(S['native_path'])
assert all(d['status'] == 'passed' for d in (B, X, G, C))
assert B['raw_log_validation']['status'] == X['raw_log_validation']['status'] == 'passed'
TEX = 'l1tex__t_sectors_pipe_tex_mem_texture_op_ld'
profiles = [s for d in (B, X) for s in d['samples'] if s['task']['kind'] == 'profile']
floor_passes = sum(s['traffic_audit']['observed_cold_floor_reached'] for s in profiles)
floor_failures = len(profiles) - floor_passes
max_profiles = [s for s in profiles if s['application_results'][0]['mask_bytes'] == 4 * 2**20]
max_passes = sum(s['traffic_audit']['observed_cold_floor_reached'] for s in max_profiles)
BA = B['raw_log_validation']; XA = X['raw_log_validation']
device = B['samples'][0]['application_results'][0]['device']
OUT = ROOT / 'output/pdf/atomOS_v3_6_Kernel_Validation_Texture_Cache.pdf'
OUT.parent.mkdir(parents=True, exist_ok=True)
W = A4[0] - 88
NAVY = HexColor('#15283D'); TEAL = HexColor('#007F82'); GRAY = HexColor('#526273'); LIGHT = HexColor('#EDF4F6')
styles = getSampleStyleSheet()
for name, size, lead, color, font in [('BodyR', 9.6, 13.4, NAVY, 'Helvetica'), ('SmallR', 8, 10.8, GRAY, 'Helvetica'), ('TinyR', 7, 9, GRAY, 'Helvetica'), ('TitleR', 30, 34, NAVY, 'Helvetica-Bold'), ('SectionR', 20, 24, NAVY, 'Helvetica-Bold'), ('SubR', 11.5, 15, TEAL, 'Helvetica-Bold'), ('KickerR', 8, 11, TEAL, 'Helvetica-Bold'), ('CodeR', 7.4, 11, NAVY, 'Courier')]:
    styles.add(ParagraphStyle(name=name, fontName=font, fontSize=size, leading=lead, textColor=color, spaceAfter=9, wordWrap='CJK'))
story = []
def p(text, style='BodyR'): return Paragraph(text, styles[style])
def add(text, style='BodyR'): story.append(p(text, style))
def section(n, title):
    if story: story.append(PageBreak())
    add(f'ATOMOS v3.6 K1  /  FINAL DEVICE REVIEW  /  {n:02d}', 'KickerR')
    add(title, 'SectionR')
def table(headers, rows, widths, small=False):
    style = 'SmallR' if small else 'BodyR'
    data = [[p(escape(str(x)), 'SmallR') for x in headers]] + [[p(escape(str(x)), style) for x in row] for row in rows]
    t = Table(data, colWidths=widths, hAlign='LEFT', repeatRows=1)
    t.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), LIGHT), ('VALIGN', (0,0), (-1,-1), 'TOP'), ('LEFTPADDING', (0,0), (-1,-1), 7), ('RIGHTPADDING', (0,0), (-1,-1), 7), ('TOPPADDING', (0,0), (-1,-1), 6), ('BOTTOMPADDING', (0,0), (-1,-1), 6), ('LINEBELOW', (0,0), (-1,0), .7, TEAL), ('LINEBELOW', (0,1), (-1,-1), .3, HexColor('#DDE5EA'))]))
    story.extend([t, Spacer(1, 9)])
def code(text): add(escape(text).replace('\n', '<br/>'), 'CodeR')
def f(n): return f'{n:,}'
def sample_count(d, kind): return sum(s['task']['kind'] == kind for s in d['samples'])

add('13 SEPTEMBER 2026  /  ACTUAL RTX 5070 Ti LAPTOP EXECUTION', 'KickerR')
add('atomOS v3.6<br/>Kernel validation &amp;<br/>texture residency', 'TitleR')
add('Concept author: Tom Klootwijk', 'SubR')
add('Native CUDA 12.8 / sm_120. Local synthetic K1 inputs. This report replaces the earlier partial-residency report and distinguishes the final binary from retained exploratory builds.')
table(['RESULT', 'OBSERVED EVIDENCE'], [
    ['Full 4 MiB dictionary', f'{max_passes}/{len(max_profiles)} maximum-atlas cold profiles reached exactly 131,072 compulsory misses. The dictionary is distributed across 46 SM caches.'],
    ['After-warm retention', f'{floor_passes}/{len(profiles)} final cold profiles reached their dictionary miss floor across default and additional shape/seed cases.'],
    ['Full computation retained', f'{BA["conformance_runs"] + XA["conformance_runs"]} bulk-path conformance runs; {BA["python_verified_export_runs"]} complete exported traces independently checked by Python.'],
    ['Memory and synchronization', 'Final bulk binary: six memchecks, four syncchecks and four racechecks. The rebuilt production binary passed six additional memchecks.'],
    ['Claim boundary', 'Measured retention through the verified cooperative warm/work/reread epoch. No guaranteed cache pinning across launches or arbitrary competing workloads.'],
], [142, W-142])
add('What changed', 'SubR')
add('The optional bulk-copy kernel stages live inputs and results through native asynchronous shared/global transfers while masks stay on the texture path. Correctly rounded constants replace repeated sine/cosine calls for the fixed .4 rotation. The final kernel uses 84 registers per thread and has zero stack/local allocation.')
add('Residency has an execution cost. The report includes all warming, probing, barriers and diagnostic work in ordinary kernel timing. A complete-residency observation is not a claim of the fastest possible K1 implementation.', 'SmallR')

section(2, 'What the cache result means')
add('The measurement starts cold, reads the entire physical dictionary, runs the real K1 epoch, and rereads the entire dictionary. Grid-wide barriers separate the phases. Inputs are immutable throughout. The host independently checks every candidate before committing word and JK state.')
table(['PHASE', 'COVERAGE / CHECK'], [
    ['Warm', 'Every packed uint4 texel, including physical padding. Each aligned 32-byte sector is required at least once.'],
    ['Real work', 'All logical lanes execute the original producer, word disposition, JK, blend, OTAN2 and six diagnostic checks. Padding executes no logical work.'],
    ['Post-work reread', 'Every physical texel again, on its owning cooperative block. Independent expected per-thread XOR digests cover all texels, but can collide.'],
    ['Ownership', 'Exactly one active 512-thread block per SM is required. All 46 observed SM identifiers must be unique and unchanged at both endpoints of every launch.'],
], [120, W-120])
add('At 4 MiB, 4,194,304 / 32 = 131,072 unique texture sectors. A cold launch with exactly that many misses leaves no observed extra dictionary misses for work or the final reread. This inference depends on the recorded cold-cache and coverage conditions; the counters are aggregate, not separate measurements of a 100% hit rate in each phase. [1]')
table(['SIZE / LAYOUT', 'MISS FLOOR', 'MEASURED MISS RANGE', 'REPEATS AT FLOOR'], [[a['size']+' / '+a['layout'], f(a['cold_compulsory_miss_floor']), f(a['metrics'][TEX+'_lookup_miss.sum']['min'])+' - '+f(a['metrics'][TEX+'_lookup_miss.sum']['max']), str(a['cold_floor_reached_samples'])+'/'+str(a['profile_trials'])] for a in B['aggregates']], [118, 83, 153, W-354], True)
add('Nsight Compute: kernel replay, cache-control all, clock-control none, setup launch skipped, one measured launch per sample. Requested sectors, hits, misses, realized shared configuration, global-load traffic and profiler duration are retained with raw locale-aware CSV values. Missing metrics never become zero.', 'SmallR')
add('Cache operators and carveout preferences are hints, not a supported texture-line pinning interface. Passing this experiment does not establish retention across a new launch or guarantee behavior on another GPU. [2]', 'SmallR')

section(3, 'Native transfer schedule and repairs')
add('The full dictionary is divided into aligned physical intervals. A 64-texel tile stages 64 Lane records plus 64 State records in shared memory. Once all readers have private values, the same shared union holds 64 complete Result records. Native bulk-copy completion and proxy fences protect every reuse. [3, 4]')
table(['CHANGE', 'WHY IT MATTERS'], [
    ['Native bulk I/O', 'cp.async.bulk moves Lane/State into shared memory and Results back to global memory. Mask reads remain tex1Dfetch<uint4>. Diagnostic exports also use bulk copies.'],
    ['Fixed rotation folded exactly', 'cos(binary64 .4) = 0x1.d7954e7dba2f8p-1; sin(binary64 .4) = 0x1.8ec3ae92b676bp-2. The original CPU/GPU literal and runtime calls matched both constants bit for bit.'],
    ['Exact rounding evidence', '40-term rational alternating Taylor sums and next-term bounds lie strictly inside the nearest-double rounding bins. The high-precision calculation and GPU value probe are separate evidence categories.'],
    ['Padded backing and canonical export', 'Padded row-major Lane/State/Result buffers keep bulk ranges aligned. Morton physical tiles map explicitly to these records. Zero output padding is verified before canonical logical rows are gathered.'],
    ['Verify before commit', 'Downloaded candidates, checksums, SM records and padding must all pass. Exported traces contain actual GPU results and pre-commit states; incomplete output remains in an uncommitted staging directory.'],
], [145, W-145], True)
add('The controlled padded before/after comparison changed only the fixed rotation constants in the computation: maximum-atlas excess misses fell from 508 to zero in the first sample of each layout. Registers also fell from 107 to 84. This supports the compiled change; it does not isolate coefficient traffic as the sole microarchitectural cause.')
add('Literal atan(delta_phase / delta_rho), separately selected atan2 completion, whole-word absorption, explicit J/K, separate shift-XOR/shift-OR, unavailable statuses, Morton bit order and original comparison thresholds remain intact. The nearby rotated-singularity regression preserves the difference between literal and directed profiles.', 'SmallR')

section(4, 'Machine code and memory footprint')
r = N['resources']
table(['FINAL BULK KERNEL', 'MEASURED / INSPECTED VALUE'], [
    ['Device / architecture', device['name']+' / compute capability 12.0'],
    ['Toolchain', 'CUDA 12.8.61; MSVC 19.44.35221 (toolset 14.44.35207); CMake 4.3.2; native sm_120 plus compute_120 PTX'],
    ['Registers / stack / local', f"{r['registers_per_thread']} per thread / {r['stack_bytes']} bytes / {r['local_bytes']} bytes"],
    ['Shared allocation', '10,752-byte shared union + 8-byte barrier = 10,760 user bytes. cuobjdump reports 11,784 bytes including the 1,024-byte difference.'],
    ['Realized shared configuration', '16,384 bytes in every final counter sample; maximum-L1 preference is recorded separately.'],
    ['Native texture / bulk instructions', '15 static TLD sites, 18 UBLKCP.S.G sites and 13 UBLKCP.G.S sites. Loop/unrolled sites are not dynamic traffic counts.'],
    ['Remaining global bookkeeping', 'Zero ordinary LDG/STG in the inspected kernel body. Two generic load sites and two atomic sites support cooperative barriers; profiler global-load traffic is still nonzero.'],
], [155, W-155], True)
add('At the atlas cap, 262,144 uint4 texels occupy 4 MiB. On this 46-SM GPU each block owns at most 5,760 texels, or 90 KiB. The 4 MiB is distributed across the SMs. It is not 4 MiB resident in each SM, and maximum-L1 is not evidence of an exclusively available texture-cache capacity. [2]')
table(['ALLOCATION', 'ACTUAL FORMULA'], [
    ['Device payload', '272 x stored_texels + 16 x SMs x (2 x 512 + 2) bytes'],
    ['Diagnostics on this GPU', '755,136 bytes for pre/post thread digests and two uint4 SM records per block'],
    ['Admission', 'Payload + 64 MiB margin; 512 MiB ceiling; preserve 1,536 MiB of actual free VRAM; retain the 70%-of-free limit'],
], [155, W-155], True)
add('The final exporter binary and the pre-export folded binary have identical kernel SASS and encoded instruction words. Native code inspection supports instruction-path claims; it does not constitute a proof of the compiled binary. Source FMA contraction is disabled; explicit fused instructions used inside device math libraries may still occur.', 'SmallR')

section(5, 'Correctness and execution coverage')
normal_gpu = [x for x in G['runs'] if not x['path'].startswith('memcheck_')]
max_error = max(x['max_float_difference_radians'] for x in G['runs'])
bulk_error = max(s['python_export_verification']['max_float_difference_radians'] for s in B['samples'] if 'python_export_verification' in s)
table(['EVIDENCE CATEGORY', 'EXECUTED RESULT'], [
    ['C++ contract regression checks', '32 groups / 134,521 assertions; includes fixed-rotation singularity and nearby available cases'],
    ['Independent Python regressions', '37 tests; includes rejected fabricated bulk profiles, incorrect memory accounting and incomplete receipts'],
    ['CPU execution', f"7 CTest cases; {len(C['runs'])} independently verified exported configurations"],
    ['Symbolic specification', '15 Z3 4.16.0 obligations: every negated property UNSAT. These are mathematical specifications, not a C++/CUDA binary proof.'],
    ['Rebuilt production CUDA', f"{len(normal_gpu)} normal configurations; {f(sum(x['lane_epochs'] for x in normal_gpu))} lane-epochs; six additional memchecks"],
    ['Final bulk conformance', f"{BA['conformance_runs']} main + {XA['conformance_runs']} additional aspect/seed cases; every candidate checked before commit"],
    ['Independent bulk trace exports', f"{BA['python_verified_export_runs']} runs / {f(BA['python_verified_lane_epochs'])} lane-epochs recomputed by Python; run seals checked"],
    ['Bulk Compute Sanitizer', '6 memcheck + 4 synccheck + 4 racecheck runs; zero reported errors or race hazards/warnings'],
], [156, W-156], True)
add('The 192-case main bulk matrix covers 1x1, 17x257, 128x1024 and 512x16384 shapes; both layouts; all four producers; fringe on/off; source, directed and mixed diagnostic profiles; three committed epochs. Selected exports cover every producer and profile, with both maximum-atlas layouts exported for an additional one-epoch check.')
add('The additional 20 cases cover 1x65536, 32768x1, 128x65536, 511x16353 and 9x33, both layouts, and seeds 0 / 4,294,967,295 with different producer/profile/fringe choices. Memory, synchronization and race checks include both padded-tail and full maximum fixtures.')
add(f'Largest independent floating discrepancy: production {max_error:.3g} rad; bulk exports {bulk_error:.3g} rad. Acceptance stays 2e-11 rad; the invariant threshold stays 1e-10. Integer fields, statuses, states and reasons compare exactly. CPU address/undefined-behavior sanitizers were not rerun in this Windows review.', 'SmallR')

section(6, 'Retention, traffic and execution cost')
table(['SIZE / LAYOUT', 'MEDIAN', 'TRIAL RANGE', 'SCOPE'], [[a['size']+' / '+a['layout'], f"{a['ordinary_event_median_ms']*1000:.2f} us", f"{a['ordinary_event_min_ms']*1000:.2f} - {a['ordinary_event_max_ms']*1000:.2f} us", 'warm + work + probe'] for a in B['aggregates']], [114, 83, 145, W-342], True)
add('Each timing row contains five separate, shuffled processes, each with three measured epochs after a verified, uncommitted setup launch. The statistic is the median of each process\'s epoch median. Upload, download, host verification and export are outside the CUDA-event interval. Nsight and sanitizer timings are excluded from this table.')
table(['FINAL COLD COUNTERS', 'SECTORS (MEDIAN)', 'MISSES (MEDIAN)', 'HITS (MEDIAN)'], [[a['size']+' / '+a['layout'], f(a['metrics'][TEX+'.sum']['median']), f(a['metrics'][TEX+'_lookup_miss.sum']['median']), f(a['metrics'][TEX+'_lookup_hit.sum']['median'])] for a in B['aggregates']], [142, 122, 122, W-386], True)
add('The minimum nominal traffic for a full unpadded dictionary is three reads: warm, productive work and final probe. Aggregate sectors can exceed that nominal count; all excess requests are retained in the study. A higher hit percentage alone would not demonstrate an improvement, because redundant reads enlarge the denominator.')
add('Earlier controls explain the search, not the final performance claim', 'SubR')
add('Global warming alone did not remove productive TEX misses. With split I/O, no-allocation stores preserved the large dictionary in the store-only control, but input loads did not. Native bulk I/O reduced the full 4 MiB case to 508 excess misses; folding the fixed rotation removed those remaining observed misses in the controlled comparison.')
add('The earlier production sweep found a 33.1% lower best median after launch tuning (81.25 to 54.34 us at the default shape). That measurement belongs to the archived pre-fold binary and excludes warm/probe work. It is retained as historical evidence, not relabelled as a benchmark of the final bulk binary. Complete retention and minimum runtime are separate objectives.', 'SmallR')

section(7, 'Reproduce and use the delivered kernel')
add('The delivered atomos_cache_bulk.exe implements the full measured schedule and supports --out for independent verification. Keep its profile explicit: bulk-warm-work-probe-v1 with bulk-padded-row-major-v1 allocation. The standard atomos_cuda.exe retains its texture, packed-texture and global choices.')
code('cmake -S . -B C:/Users/Tom/.cache/ak1/bulk_export_sm120\n  -T cuda=12.8 -DATOMOS_ENABLE_CUDA=ON\n  -DATOMOS_CACHE_BULK_EXPERIMENT=ON\ncmake --build C:/Users/Tom/.cache/ak1/bulk_export_sm120\n  --config Release --target atomos_cache_bulk')
add('Enter each wrapped command above as one command. The short build directory avoids the reproduced Windows MSBuild path-length issue; the explicit installed toolset avoids stale CUDA 12.9 integration.', 'SmallR')
code('output/bin/atomos_cache_bulk.exe --rows 512 --angles 16384\n  --layout morton8 --mode recurrent --epochs 1 --out my_bulk_run\npython tools/verify_run.py my_bulk_run')
add('The output directory must be new. Canonical run files contain actual downloaded GPU candidates, with no logical padding rows. The Python verifier checks the complete trace, final state, exact execution profile and actual allocation formula. Seals record local file integrity; they are not author authentication.')
code('python tools/validate.py --proofs\npython tools/validate.py --gpu --sanitizer --proofs\n  --build C:/Users/Tom/.cache/ak1/gpu_fold_final\n  --cmake-arg=-Tcuda=12.8')
add('Use tools/study_cache_bulk.py for the 226-command main study and tools/check_cache_bulk_edges.py for the 46-command supplementary study, passing the executable, a new evidence directory, and the native Nsight/Compute Sanitizer paths recorded in their JSON. Both retain raw logs, before/after source and binary hashes, and an independent receipt audit.')
add('Existing repairs remain: allocation admission preserves the reserve in currently free VRAM; inconsistent execution metadata is rejected; Windows sanitizer discovery resolves the native executable. No drivers, watchdog settings, privileges or service connections were changed.', 'SmallR')

section(8, 'Evidence, identity and limits')
add('All paths below are local. K = C:/Users/Tom/.cache/ak1. R is the workspace root printed below. Each study records exact commands, device metadata, raw logs and executable/source hashes. The final source manifest and output delivery manifest are unsigned integrity records.', 'SmallR')
add(escape(str(ROOT)), 'TinyR')
table(['EVIDENCE', 'LOCATION'], [
    ['Final review / current status', 'R/results/residency_followup/summary.json; R/results/validation_status.json'],
    ['CPU validation', 'K/cpu_fold_final/evidence_1789299038566882500/validation.json'],
    ['Production GPU validation', 'K/gpu_fold_final/evidence_1789299027401576500/validation.json'],
    ['Main bulk study', 'K/bulk_final_study_v2/study.json; raw .stdout.log/.stderr.log/.csv.log files and sealed *.run directories alongside it'],
    ['Additional shapes / sanitizers', 'K/bulk_final_edges/study.json; raw per-command logs alongside it'],
    ['Rounding / native code', 'R/results/residency_followup/rotation_rounding.json; rotation_fold_native.json; final_native.json; bulk_final_sass.txt'],
    ['Initial controlled cache comparison', 'R/results/residency_followup/padded_before_fold_profiles.json; fold_initial_profiles.json'],
    ['Retained rejected attempt', 'K/bulk_final_study/study.json: validator-source change during execution; excluded from final counts'],
], [142, W-142], True)
add('Final bulk executable SHA-256', 'SubR'); add(escape(B['executable_sha256']), 'TinyR')
add('Final production executable SHA-256', 'SubR'); add(escape(S['production_executable_sha256']), 'TinyR')
add('Limits of the conclusion', 'SubR')
add(f'The final profile set records {floor_passes} miss-floor successes and {floor_failures} excess-miss outcomes. These are finite, workload-specific hardware observations. They do not establish cache pinning, arbitrary concurrency, all possible inputs, every future compiler, or a formal CUDA-binary proof. K1 remains the synthetic integrated word-epoch profile; unimplemented engine producers remain listed in docs/coverage.csv.', 'SmallR')
add('Primary references', 'SubR')
for label, title, url in [
    ('1', 'Nsight Compute: cache control and 32-byte L1/TEX sector metrics', 'https://docs.nvidia.com/nsight-compute/ProfilingGuide/'),
    ('2', 'PTX ISA 8.7: cache hints, memory model and texture coherence', 'https://docs.nvidia.com/cuda/archive/12.8.2/parallel-thread-execution/index.html'),
    ('3', 'CUDA 12.8: bulk asynchronous transfers and completion ordering', 'https://docs.nvidia.com/cuda/archive/12.8.2/cuda-c-programming-guide/index.html#using-tma-to-transfer-data'),
    ('4', 'PTX ISA 8.7: cp.async.bulk and async-proxy fences', 'https://docs.nvidia.com/cuda/archive/12.8.2/parallel-thread-execution/index.html#data-movement-and-conversion-instructions-cp-async-bulk'),
]: add(f'[{label}] <link href="{url}" color="#007F82">{escape(title)}</link>. Full URLs and claim mapping: docs/cache_sources.json.', 'TinyR')

def footer(canvas, doc):
    canvas.saveState(); canvas.setStrokeColor(TEAL); canvas.setLineWidth(.5)
    canvas.line(44, 35, A4[0]-44, 35); canvas.setFont('Helvetica', 7.2); canvas.setFillColor(GRAY)
    canvas.drawString(44, 23, 'Tom Klootwijk  |  atomOS v3.6 K1  |  real device evidence  |  13 September 2026')
    canvas.drawRightString(A4[0]-44, 23, str(doc.page)); canvas.restoreState()
doc = SimpleDocTemplate(str(OUT), pagesize=A4, rightMargin=44, leftMargin=44, topMargin=40, bottomMargin=46,
                        title='atomOS v3.6 K1 - Kernel validation and measured texture residency', author='Tom Klootwijk', subject='Native RTX 5070 Ti Laptop kernel validation, cache counters and reproducible evidence')
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print(OUT)
