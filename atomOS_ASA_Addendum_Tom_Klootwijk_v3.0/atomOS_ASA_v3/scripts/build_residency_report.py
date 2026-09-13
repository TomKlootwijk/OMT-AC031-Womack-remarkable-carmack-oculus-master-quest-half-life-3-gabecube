#!/usr/bin/env python3
"""Build the measured September 2026 kernel report from retained evidence."""
from pathlib import Path
import hashlib
import json
import statistics
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Flowable

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'local_validation/20260913_residency_delivery'
OUT = ROOT / 'output/pdf/atomOS_ASA_kernel_residency_validation.pdf'
NAVY = colors.HexColor('#142C43')
TEAL = colors.HexColor('#007F80')
INK = colors.HexColor('#233747')
MUTED = colors.HexColor('#526575')
PALE = colors.HexColor('#EDF5F6')
LINE = colors.HexColor('#D8E2E9')
AMBER = colors.HexColor('#925414')

for name, path in [('Body','C:/Windows/Fonts/arial.ttf'),('Bold','C:/Windows/Fonts/arialbd.ttf')]:
    pdfmetrics.registerFont(TTFont(name, path))
pdfmetrics.registerFontFamily('Body', normal='Body', bold='Bold', italic='Body', boldItalic='Bold')
styles = {
    'body': ParagraphStyle('body',fontName='Body',fontSize=10,leading=14.5,textColor=INK,spaceAfter=9),
    'small': ParagraphStyle('small',fontName='Body',fontSize=8,leading=11,textColor=MUTED,spaceAfter=7),
    'title': ParagraphStyle('title',fontName='Bold',fontSize=29,leading=33,textColor=NAVY,spaceAfter=15),
    'heading': ParagraphStyle('heading',fontName='Bold',fontSize=21,leading=25,textColor=NAVY,spaceAfter=15),
    'sub': ParagraphStyle('sub',fontName='Bold',fontSize=12,leading=16,textColor=TEAL,spaceBefore=9,spaceAfter=8),
    'cell': ParagraphStyle('cell',fontName='Body',fontSize=8.5,leading=11.8,textColor=INK),
    'white': ParagraphStyle('white',fontName='Bold',fontSize=8.5,leading=11.8,textColor=colors.white),
    'code': ParagraphStyle('code',fontName='Body',fontSize=8,leading=11.5,textColor=INK,spaceAfter=8),
}

def p(text, style='body'):
    return Paragraph(text, styles[style])

def table(rows, widths):
    parsed = [[p(escape(str(c)), 'white' if i == 0 else 'cell') for c in row] for i,row in enumerate(rows)]
    t = Table(parsed,colWidths=widths,repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),NAVY),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),
        ('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,PALE]),
        ('LINEBELOW',(0,0),(-1,0),.6,NAVY),('LINEBELOW',(0,-1),(-1,-1),.6,LINE),
    ]))
    return t

def note(title, text):
    t=Table([[p(title,'sub')],[p(text)]],colWidths=[174*mm])
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),PALE),('BOX',(0,0),(-1,-1),.6,LINE),
        ('LEFTPADDING',(0,0),(-1,-1),12),('RIGHTPADDING',(0,0),(-1,-1),12),
        ('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),4)]))
    return t

class MissBars(Flowable):
    def __init__(self, data):
        Flowable.__init__(self); self.data=data; self.width=174*mm; self.height=150
    def draw(self):
        c=self.canv; maximum=max(x[1] for x in self.data); left=115; extent=300
        c.setFont('Body',8);c.setFillColor(MUTED);c.drawString(left,138,'Cold texture-load miss sectors (32 bytes each)')
        for i,(name,value,locality) in enumerate(self.data):
            y=106-i*28;c.setFont('Body',9);c.setFillColor(INK);c.drawString(0,y+4,name)
            c.setFillColor(TEAL if locality else colors.HexColor('#9AAEBD'))
            c.roundRect(left,y,extent*value/maximum,15,2,fill=1,stroke=0)
            c.setFillColor(INK);c.setFont('Bold',9);c.drawString(left+extent*value/maximum+6,y+4,f'{value:,.0f}')

def read(name): return json.loads((EVIDENCE/name).read_text(encoding='utf-8'))
def num(v,d=0): return f'{v:,.{d}f}'
def page(title,subtitle): return [p(title,'heading'),p(subtitle,'small')]
def footer(canvas,doc):
    w,h=doc.pagesize;canvas.saveState();canvas.setStrokeColor(LINE);canvas.setLineWidth(.5)
    canvas.line(18*mm,17*mm,w-18*mm,17*mm);canvas.setFont('Body',8);canvas.setFillColor(MUTED)
    canvas.drawString(18*mm,12*mm,'atomOS ASA v3 | Tom Klootwijk | 13 September 2026')
    canvas.drawRightString(w-18*mm,12*mm,f'{doc.page}');canvas.restoreState()

def main():
    bench=read('benchmark/benchmark.json');res=read('residency/residency_probe.json')
    acceptance=read('delivery_status.json');native=read('native/native_evidence.json')
    footprint=read('footprint/footprint.json')
    assert bench['status']==res['status']==acceptance['status']=='pass'
    assert bench['binary_sha256']==res['binary_sha256']==native['binary_sha256']
    assert len(res['observations'])==84
    summaries={name:cond['summary'] for name,cond in bench['conditions'].items()}
    n,l=summaries['morton_natural'],summaries['morton_locality']
    miss_reduction=100*(1-l['texture_miss_sectors_median']/n['texture_miss_sectors_median'])
    time_reduction=100*(1-l['texture_compute_ms_median']/n['texture_compute_ms_median'])
    rs=res['summary'];warm=rs['texture_l1_warm_normal']
    policy=next(x['run'] for x in res['observations'] if x['policy']=='persist-image')
    story=[p('MEASURED ON THE RTX 5070 Ti LAPTOP GPU','sub'),p('Kernel and texture-cache<br/>validation','title'),
        p('atomOS ASA v3 | Numerical image operator<br/>Concept author: Tom Klootwijk | Validation: 13 September 2026'),
        Spacer(1,7*mm),note('Validated execution. Full L1/TEX residence was not reached.',
        f'The native CUDA kernel passed correctness and sanitizer checks. Locality scheduling reduced cold texture misses by {miss_reduction:.1f}% against natural ordering in the fresh Morton8 comparison. Warm L1/TEX hit rate was {warm["hit_pct_median"]:.2f}%, with remaining misses. Warm L2 read-miss captures were zero for both kernels and both policies.'),
        Spacer(1,8*mm),table([
            ['Question','Evidence-backed answer'],
            ['Does the kernel execute on this GPU?','Yes. Native sm_120 binary, actual CUDA execution, texture-load SASS instructions.'],
            ['Are numerical outputs preserved?','Yes for the executed fixtures. Exact flags and logical keys; maximum independent-oracle error 0. Tolerance remains 2e-6.'],
            ['Is every table permanently in texture cache?','No such result was demonstrated. Warm L1/TEX misses remain, and an L2 persistence hint is not a pinning guarantee.'],
            ['What was repaired in this run?','The benchmark now rejects replay-dependent, misidentified or mixed-launch captures and binary changes during measurement.'],
            ['Selected configuration','Locality ordering, 512 threads per block, normal L2 policy. Existing numerical kernel retained after review.'],
        ],[48*mm,126*mm]),Spacer(1,6*mm),
        p('This report adds fresh evidence and a measurement repair to the existing optimized implementation. It does not claim a new kernel speedup over that already optimized build. Earlier package results and the original addendum PDF remain unchanged.','small'),
        p('Environment: CUDA 12.8.61, MSVC 19.44.35221, Nsight Compute 2025.1.0.0. Device CC 12.0; runtime API 12080, driver API 13010. Observed total/free VRAM: 12,820,480,000 / 11,561,598,976 bytes. Free memory describes that query, not guaranteed availability.','small'),PageBreak()]

    story+=page('Correctness before performance','Fresh acceptance records: baseline_cpu, baseline_gpu, final_checks and retained_cases.')
    story+=[table([
        ['Executed check','Result / scope'],
        ['CPU configure, build and CTest','Passed: 3 targets.'],
        ['CUDA configure, build and CTest','Passed: 5 targets; native sm_120 and PTX.'],
        ['Final Python regression suite',f'{acceptance["python_tests"]} tests passed, including the benchmark capture regressions.'],
        ['C++ numerical contract','33 groups / 74,982 assertions passed.'],
        ['CLI integration','58 CPU and 76 GPU scenarios passed.'],
        ['Focused independent oracle','72 retained cases / 28,656 samples; maximum error 0. Both layouts and both orders.'],
        ['Compute Sanitizer','16 invocations passed: memcheck, initcheck, racecheck and synccheck across natural, locality, persist-image and focused boundary workloads.'],
        ['Stream completion','Normal destruction, exception unwinding and explicit close checked with 65,536 samples each; CPU comparison.'],
        ['Host ASan / UBSan','Unavailable with the configured MSVC compiler; requested configuration rejected. No host sanitizer pass claimed.'],
    ],[57*mm,117*mm]),Spacer(1,4*mm),p('The preserved numerical contract','sub'),
        p('Paired coordinates are formed before numerical-aperture gating. Radial intervals remain lower-inclusive and upper-exclusive; the angular edge is inclusive. Morton8 keeps radial bits even and angular bits odd. Result cell keys are logical row-major keys. The independent Python arithmetic and C++ core are unchanged.'),
        p('Coverage includes 0, 1, 257, 4,097 and 65,536 samples; rectangular dictionaries; seams and nextafter boundaries; nonfinite and extreme coordinates; invalid dimensions, device selection and nonempty output directories. Zero samples launch no kernel. Low-memory admission boundaries are tested with simulated free-byte values, retaining the half-free rule and 512 MiB reserve.'),
        p('Scope limits: synthetic numerical fixtures, not physical lens calibration or formal proof. Extreme LUT-size fixtures use identity coefficients. Read-only tables and separate outputs prevent same-invocation texture/write aliasing in the implemented path. Destructor fallbacks do not propagate CUDA cleanup errors.','small'),PageBreak()]

    story+=page('What locality changes','65,536 identical samples | 512 threads/block | both explicit storage layouts')
    rows=[['Layout / order','L1/TEX hit','Cold misses','Texture ms','Global ms']]
    labels=[('linear_natural','Linear / natural'),('linear_locality','Linear / locality'),('morton_natural','Morton / natural'),('morton_locality','Morton / locality')]
    for key,label in labels:
        s=summaries[key];rows.append([label,f'{s["texture_hit_pct_median"]:.2f}%',num(s['texture_miss_sectors_median']),num(s['texture_compute_ms_median'],6),num(s['global_compute_ms_median'],6)])
    story+=[table(rows,[51*mm,29*mm,31*mm,32*mm,31*mm]),Spacer(1,4*mm),MissBars([(label,summaries[key]['texture_miss_sectors_median'],'locality' in key) for key,label in labels]),
        p(f'Morton8 locality reduced cold miss sectors by {miss_reduction:.1f}% and warmed texture-kernel mean time by {time_reduction:.1f}% relative to natural ordering. These are fresh A/B measurements of the existing scheduling options, not a before/after change to the current kernel.'),
        p(f'Total Morton texture sectors fell from {num(n["texture_requested_sectors_median"])} to {num(l["texture_requested_sectors_median"])}. A higher hit percentage alone does not mean less traffic: locality also coalesces requests. Both layouts preserve byte-identical samples and output records.'),
        p('Measurement method','sub'),p('Each condition has five unprofiled process runs, five warmups and 30 timed launches per path. A/B order alternates within each layout. Timings above are medians of process mean CUDA-event times. Three separate cold captures per condition use base clock control, cache flushing and exactly one profiler pass. Every saved run is independently oracle-checked.'),
        p(f'Host overhead remains material: Morton/locality median sorting {l["reorder_ms_median"]:.3f} ms and restoration {l["restore_ms_median"]:.3f} ms. Restoration covers both GPU outputs. Process medians are {n["process_wall_ms_median"]:.1f} ms natural and {l["process_wall_ms_median"]:.1f} ms locality; these include both paths, setup, CPU comparison, transfers, repeated launches and files. They are not single-batch latency or evidence of an application-wide speedup.','small'),PageBreak()]

    story+=page('Residency: what the counters prove','84 accepted one-pass captures | 3 repetitions | cold/warm x normal/persist-image')
    rows=[['Path / policy','Cold L2 read misses','Warm L2 read misses']]
    for path in ['texture','global']:
        for pol in ['normal','persist-image']:
            cold=rs[path+'_l2_miss_cold_'+pol]; w=rs[path+'_l2_miss_warm_'+pol]
            rows.append([path+' / '+pol,num(cold['counter_median'])+' ['+', '.join(num(v) for v in cold['counter_range'])+']',num(w['counter_median'])+' ['+', '.join(num(v) for v in w['counter_range'])+']'])
    story+=[table(rows,[65*mm,56*mm,53*mm]),p('Values are medians [minimum, maximum] of read-miss counters. L2 hit counters were captured separately and are not combined into a same-launch percentage.','small'),
        p(f'Warm texture L1/TEX remained at {warm["hit_pct_median"]:.2f}% hits, with {num(warm["miss_sectors_median"])} miss sectors. Therefore zero measured warm L2 read misses does not mean zero texture-cache misses: L2 can satisfy a miss from the smaller per-SM cache.'),
        p('The persistence policy','sub'),
        p(f'The image-only window requested {num(policy["l2_requested_bytes"])} bytes; CUDA accepted a {num(policy["l2_accepted_bytes"])}-byte reservation and read back a {num(policy["l2_window_bytes"])}-byte window. The policy ratio was {policy["l2_hit_ratio"]:g}, with persisting hits and normal misses. This ratio controls policy selection; it is not an observed hit rate. The 16 KiB matte and 4 KiB lens are outside the image window. [1]'),
        p('Texture-path evict-last counters remained zero with either policy. The global path showed nonzero evict-last tagging with persist-image. This demonstrates a path-specific priority effect; it does not establish a texture performance benefit. Normal policy remains the default.'),
        note('Measurement discipline', 'Cold captures flush caches before the measured launch. Warm captures disable flushing after five application warmups. Hardware cache state cannot be restored like device memory during replay, so the retained evidence requires one pass. L2 counters describe the shared L1/TEX read source, not the residency of individual image lines. [2]'),
        Spacer(1,4*mm),p('No supported control used here pins all table lines permanently in L1/TEX. Full allocations being live in VRAM, an accepted L2 hint, and zero misses in a finite capture are three different observations. None supplies a permanent residency guarantee.','small'),PageBreak()]

    story+=page('Native instructions and capacity','Inspecting the shipped device code and the requested data footprint')
    story+=[table([
        ['Native property','Observed value'],
        ['Architecture','sm_120 native cubin; PTX version 8.7 also embedded.'],
        ['Texture instructions','TLD.LZ for table reads; LDG.E.64 for coordinate inputs; STG.E for results.'],
        ['Both kernels','36 registers/thread; 0 stack bytes; 0 local bytes; 0 static application shared bytes.'],
        ['Profiler shared-memory partition','8,192 bytes; 1,024 driver bytes/block; 0 dynamic and static application shared bytes.'],
        ['L2 capacity','37,748,736 bytes (36 MiB), queried from the actual device.'],
        ['Default table allocations','Image 512 KiB + matte 16 KiB + lens 4 KiB = 532 KiB.'],
    ],[61*mm,113*mm]),Spacer(1,3*mm),
        p('NVIDIA documents 128 KiB of unified data cache/shared memory per CC 12.x SM. Subtracting the measured 8 KiB shared partition suggests a nominal 120 KiB L1/TEX allocation budget per SM. This is a capacity inference, not measured occupancy. The full 532 KiB table allocation cannot fit in that single-SM budget. Active block footprints are smaller. [3]'),
        p('Requested footprint model','sub')]
    for line in acceptance['footprint_report_lines']:
        story.append(p(escape(line),'small'))
    story+=[p('The host trace records the unique 32-byte sectors requested by the existing numerical evaluator, separately for image, matte and lens allocations. It compares traced outputs with the ordinary CPU evaluation. It excludes input/output traffic, concurrent blocks, hardware set mapping, fetch granularity beyond the model, scheduling and replacement. A small per-block footprint is useful locality evidence; it does not predict a miss count or prove cache residence.'),
        p('The SASS dump is retained alongside resource usage and binary identity. It confirms that texture instructions survived compilation. Zero local/stack resource allocation and the absence of local-load/store instructions in this dump support no observed local-memory spilling for these kernels. These are native compiled instructions, not an emulated cache result. [4]','small'),PageBreak()]

    story+=page('Repairs, evidence and reproduction','Fresh report root: local_validation/20260913_residency_delivery/')
    story+=[p('Repair made during this validation','sub'),
        p('The older benchmark could accept captures without pass-count evidence, the wrong kernel or metrics from mixed launches. It now requires a single texture-kernel capture, exactly one profiler pass, consistent launch identity and matching executable digests before and after every process invocation. Minimal mocked regressions reproduced the invalid acceptances before the fix; retained before/after logs document what ran.'),
        p('No new production kernel correctness defect was found in this review. The existing fixes remain in place: zero-batch metadata, fail-fast admission, exact sample-order restoration, explicit launch bounds, synchronized stream cleanup, L2 policy readback and cleanup, and Windows compiler/tool selection. C++ core arithmetic, independent Python arithmetic and numerical profiles remain unchanged.'),
        table([
            ['Evidence','Content'],
            ['baseline_cpu/ and baseline_gpu/','Configure/build, CTest, actual device, 16 sanitizer logs.'],
            ['final_checks/ and retained_cases/','Post-repair checks, retained focused inputs/results and independent oracle records.'],
            ['benchmark/ and residency/','Fresh timings, single-pass counter CSV logs, exact commands, run metadata and oracle output.'],
            ['native/ and footprint/','Native ELF/PTX/SASS, resource usage, compile command and host request model.'],
            ['delivery_status.json','Final source/binary hashes, executed outcomes and original-result preservation.'],
        ],[64*mm,110*mm]),Spacer(1,3*mm),
        p('Measured CUDA executable SHA-256','sub'),p(native['binary_sha256'],'code'),
        p('Build with scripts/validate.py --gpu --sanitizer --build-dir b128 and an unused --report-dir. On this Windows host select -Tcuda=C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8 via --cmake-arg. Use scripts/benchmark_cache.py with --block-size 512 and scripts/probe_cache_residency.py with --runs 3. Pass the native Nsight Compute executable through --ncu. Exact argument arrays are retained in the JSON records.','small'),
        p('Technical sources, checked 13 September 2026','sub'),
        p('[1] <link href="https://docs.nvidia.com/cuda/archive/12.8.0/cuda-c-programming-guide/index.html#device-memory-l2-access-management" color="#007F80">NVIDIA CUDA 12.8 Programming Guide: L2 access management</link>. Policy windows, hitRatio and reset semantics.','small'),
        p('[2] <link href="https://docs.nvidia.com/nsight-compute/ProfilingGuide/index.html#cache-control" color="#007F80">NVIDIA Nsight Compute Profiling Guide: cache control</link>. Cache flushing and replay-state limits.','small'),
        p('[3] <link href="https://docs.nvidia.com/cuda/archive/13.1.1/cuda-programming-guide/05-appendices/compute-capabilities.html" color="#007F80">NVIDIA compute-capability tables, CUDA 13.1.1</link>. Table 32, CC 12.x unified capacity.','small'),
        p('[4] <link href="https://docs.nvidia.com/cuda/cuda-binary-utilities/index.html" color="#007F80">NVIDIA CUDA Binary Utilities</link>. cuobjdump resource/SASS interpretation and texture instructions.','small')]
    OUT.parent.mkdir(parents=True,exist_ok=True)
    SimpleDocTemplate(str(OUT),pagesize=(210*mm,297*mm),rightMargin=18*mm,leftMargin=18*mm,
        topMargin=18*mm,bottomMargin=24*mm,title='atomOS ASA Kernel and Texture-Cache Validation',
        author='Tom Klootwijk (concept author); Codex (validation report)').build(story,onFirstPage=footer,onLaterPages=footer)
    print(OUT)

if __name__=='__main__': main()
