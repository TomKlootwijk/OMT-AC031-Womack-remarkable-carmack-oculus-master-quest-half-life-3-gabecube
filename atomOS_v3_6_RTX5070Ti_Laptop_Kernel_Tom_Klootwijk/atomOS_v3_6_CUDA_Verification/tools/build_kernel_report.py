"""Build the evidence-backed PDF; run only after review_summary.json is finalized."""
from pathlib import Path
import json
from html import escape
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Flowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4

ROOT=Path(__file__).resolve().parents[1]
E=ROOT/'results/review_20260913'
S=json.loads((E/'review_summary.json').read_text())
B=json.loads(Path(S['benchmark_path']).read_text())
P=json.loads(Path(S['profile_path']).read_text())
G=json.loads(Path(S['gpu_validation_path']).read_text())
SOURCES=json.loads((ROOT/'docs/cache_sources.json').read_text())['sources']
CONT_PATH=ROOT/'results/residency_continuation/summary.json'
CONT=json.loads(CONT_PATH.read_text()) if CONT_PATH.exists() else None
OUT=ROOT/'output/pdf/atomOS_v3_6_Kernel_Validation_Texture_Cache.pdf'
OUT.parent.mkdir(parents=True,exist_ok=True)
NAVY=HexColor('#15283D'); TEAL=HexColor('#007F82'); GRAY=HexColor('#526273'); LIGHT=HexColor('#EDF4F6'); GOLD=HexColor('#B16B16')
styles=getSampleStyleSheet()
styles.add(ParagraphStyle(name='Body',fontName='Helvetica',fontSize=10,leading=14,textColor=NAVY,spaceAfter=9))
styles.add(ParagraphStyle(name='Small2',fontName='Helvetica',fontSize=8,leading=11,textColor=GRAY,spaceAfter=6,wordWrap='CJK'))
styles.add(ParagraphStyle(name='Tiny',fontName='Helvetica',fontSize=7,leading=9,textColor=GRAY,spaceAfter=4,wordWrap='CJK'))
styles.add(ParagraphStyle(name='Code2',fontName='Courier',fontSize=8,leading=12,textColor=NAVY,backColor=LIGHT,borderPadding=8,spaceAfter=12,wordWrap='CJK'))
styles.add(ParagraphStyle(name='Section2',fontName='Helvetica-Bold',fontSize=20,leading=24,textColor=NAVY,spaceAfter=16))
styles.add(ParagraphStyle(name='Sub2',fontName='Helvetica-Bold',fontSize=12,leading=16,textColor=TEAL,spaceBefore=9,spaceAfter=7))
styles.add(ParagraphStyle(name='Kicker',fontName='Helvetica-Bold',fontSize=8,leading=11,textColor=TEAL,spaceAfter=16))
styles.add(ParagraphStyle(name='Title2',fontName='Helvetica-Bold',fontSize=32,leading=36,textColor=NAVY,spaceAfter=18))
story=[]
def para(text,style='Body'):
    return Paragraph(text,styles[style])
def add(text,style='Body'):
    story.append(para(text,style))
def section(number,title):
    if story: story.append(PageBreak())
    add(f'ATOMOS v3.6 K1  /  ENGINEERING REVIEW  /  {number:02d}','Kicker')
    add(title,'Section2')
def table(headers,rows,widths,small=False):
    sty='Small2' if small else 'Body'
    data=[[para(escape(str(x)), 'Small2') for x in headers]]
    data += [[para(escape(str(x)),sty) for x in row] for row in rows]
    t=Table(data,colWidths=widths,hAlign='LEFT',repeatRows=1)
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),LIGHT),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),('LINEBELOW',(0,0),(-1,0),.7,TEAL),('LINEBELOW',(0,1),(-1,-1),.3,HexColor('#DDE5EA'))]))
    story.append(t);story.append(Spacer(1,10))
def code(s): add(escape(s).replace('\n','<br/>'),'Code2')
def item(k): return next(x for x in B['aggregates'] if x['configuration']==k)
baseline=item('128_1024_texture_morton8_256_default')
fast=item('128_1024_texture_morton8_64_max-l1')
packed=item('128_1024_texture-packed_linear_128_default')
improvement=100*(1-fast['median_ms']/baseline['median_ms'])
W=A4[0]-88

add('13 SEPTEMBER 2026  /  REAL DEVICE VALIDATION','Kicker')
add('atomOS v3.6<br/>Kernel validation &amp;<br/>texture-cache study','Title2')
add('Concept author: Tom Klootwijk','Sub2')
add('Target measured: NVIDIA GeForce RTX 5070 Ti Laptop GPU, compute capability 12.0. Native CUDA 12.8 / sm_120 binary; local synthetic inputs only.')
story.append(Spacer(1,12))
table(['RESULT','EVIDENCE'],[
    ['Correctness validated',f"144 GPU configurations + 6 GPU memchecks passed; {S['supplemental_memchecks']} additional launch-setting memchecks passed."],
    ['Measured kernel improvement',f"{baseline['median_ms']*1000:.2f} to {fast['median_ms']*1000:.2f} microseconds per epoch ({improvement:.1f}% lower median)."],
    ['Minimum streaming texture traffic','Packed linear: 2,048 sectors x 32 bytes = the full 65,536-byte dictionary, read once.'],
    ['Full texture-cache residency',('Default linear dictionary retention measured in the partition experiment; larger-case limits and controls start on page 7. No supported pinning guarantee.' if CONT else 'Not established. Packed linear misses match the complete dictionary footprint. Supported CUDA cache preferences do not pin texture lines.')]
],[154,W-154])
add('Measured baseline operating choices','Sub2')
add('For the cache-traffic target, use the packed linear path with 128-thread blocks and the default cache preference: it reads the dictionary in the minimum sector count with one native texture instruction. The fastest observed median used four-plane Morton8 with 64-thread blocks and maximum-L1 preference, but issued more misses. Their timing ranges overlap; neither is a universal winner.')
add('The report keeps source-equation proofs, actual GPU conformance, sanitizer results, disassembly and hardware counters as distinct evidence categories. Original numerical thresholds and word/JK/OTAN2 semantics were preserved.','Small2')

section(2,'Validation and repairs')
table(['CHECK','ACTUAL RESULT'],[
    ['C++ contract checks','31 groups / 134,509 assertions passed'],
    ['Python regressions','31 unit tests passed'],
    ['CPU execution','7 CTest cases; 48 independently verified configurations'],
    ['Symbolic specification','15 obligations UNSAT, Z3 4.16.0'],
    ['GPU execution',f"144 configurations, {S['ordinary_gpu_lane_epochs']:,} independently checked lane-epochs"],
    ['Compute Sanitizer',f"6 matrix + {S['supplemental_memchecks']} supplemental memchecks; zero reported errors"],
    ['Native target','CUDA 12.8.61 / MSVC 19.44.35221 / sm_120'],
],[164,W-164],True)
add('1. Preserve the free-VRAM reserve','Sub2')
add('Before repair, a 65 MiB plan was admitted with only 1 GiB free, even when the reserve was 1,536 MiB: the check subtracted the reserve only from total VRAM. The new regression failed first. Admission now also requires free VRAM minus the planned allocation to retain the reserve; the existing budget and 70%-of-free limits remain.')
add('2. Reject inconsistent execution evidence','Sub2')
add('The independent verifier previously accepted CPU output relabelled as CUDA, fabricated read/device metadata and a failed candidate-verification label. New checks enforce CPU/CUDA metadata consistency and compare requested backend/read path and stable probed device fields. These checks prevent accidental evidence relabelling; they do not authenticate arbitrary metadata.')
add('3. Launch the Windows sanitizer correctly','Sub2')
add('The first full GPU matrix passed all 144 cases, then failed to start Compute Sanitizer with WinError 2. Tool discovery had found a .bat wrapper. The runner now resolves NVIDIA\'s native executable and records its absolute path. The full command was rerun successfully; the failed attempt remains in the evidence archive.')
add('No word/JK/OTAN2 mismatch was found in the executed matrix. CPU AddressSanitizer/UBSan was not rerun on Windows in this review; older preparation results are archived separately.','Small2')

section(3,'What the texture counters establish')
add('The default grid contains 4,096 logical word lanes. Four uint32 masks per lane occupy 64 KiB; the complete device payload is 1,114,112 bytes. The rest is the 80-byte lane input, 8-byte state and 168-byte result per lane.')
add('NVIDIA documents 128 KiB of unified L1/texture/shared capacity per cc12.x SM, with a configuration-dependent texture working-set range. Fit in that maximum is a capacity check, not proof that all lines survive a launch boundary. Maximum-L1 remains a driver preference. [1, 2]')
metric='l1tex__t_sectors_pipe_tex_mem_texture_op_ld'
rows=[]
for x in P['aggregates']:
    c=x['config'];ms=x['metrics']
    def mv(name): return ms[name].get('median')
    sectors=mv(metric+'.sum'); hits=mv(metric+'_lookup_hit.sum'); misses=mv(metric+'_lookup_miss.sum')
    label=('4-plane' if c['read']=='texture' else 'Packed')+' / '+('M' if c['layout']=='morton8' else 'L')+f" / {c['block_size']} / "+('max' if c['cache']=='max-l1' else 'def')
    rows.append([label,x['condition'],f'{sectors:,.0f}',f'{misses:,.0f}',f'{100*hits/sectors:.1f}%'])
table(['PATH / LAYOUT / BLOCK / CACHE','STATE','SECTORS','MISSES','HIT %'],rows,[211,49,68,68,W-396],True)
add('M = Morton8; L = linear. Values are medians of three counter samples per row. Cold uses kernel replay with cache flushing; warm uses application replay without flushing after the constructor warmup. Warm labels the protocol, not observed L1 warmth. All runs skip one launch and profile one launch; clocks remain under normal system control. Raw values and ranges are retained. [3]','Small2')
add('Why a lower hit percentage can be better','Sub2')
add('A linear packed pass requests each 32-byte dictionary sector once. Its 2,048 misses match the compulsory first read of 64 KiB. Morton ordering revisits sectors: the original path scores 75% hits while issuing four times as many sectors. The fastest 64-thread setting also doubles misses to 4,096. Higher hit percentage or lower runtime alone does not establish better residency. L1 misses do not by themselves mean DRAM reads.')

class TimingChart(Flowable):
    def __init__(self): super().__init__();self.width=W;self.height=188
    def draw(self):
        c=self.canv;left=42;bottom=32;width=W-62;height=118
        series=[('4-plane / Morton8','texture','morton8',TEAL),('Packed / linear','texture-packed','linear',NAVY),('Global / linear','global','linear',GOLD)]
        c.setFont('Helvetica',8)
        for us in (40,60,80,100):
            y=bottom+(us-40)/60*height;c.setStrokeColor(HexColor('#DAE3E9'));c.line(left,y,left+width,y);c.setFillColor(GRAY);c.drawRightString(left-7,y-3,str(us))
        for label,read,layout,color in series:
            points=[]
            for j,block in enumerate((64,128,256)):
                val=item(f'128_1024_{read}_{layout}_{block}_default')['median_ms']*1000
                points.append((left+j*width/2,bottom+(val-40)/60*height))
            c.setStrokeColor(color);c.setFillColor(color);c.setLineWidth(1.8)
            for (x,y),(xx,yy) in zip(points,points[1:]):c.line(x,y,xx,yy)
            for x,y in points:c.circle(x,y,3,fill=1,stroke=0)
        for j,block in enumerate((64,128,256)):
            c.setFillColor(GRAY);c.drawCentredString(left+j*width/2,16,str(block)+' threads')
        c.drawString(2,169,'us')
        for j,(label,_,_,color) in enumerate(series):
            x=44+j*153;c.setFillColor(color);c.rect(x,174,8,4,fill=1,stroke=0);c.drawString(x+13,172,label)

section(4,'Measured performance, with its limits')
add('Each of the 36 settings was run five times in a fixed-seed shuffled order. Each trial contains three epochs; its median is one sample. The table reports the median and range of those five samples. One exported run per setting was independently checked in Python before its timings were accepted.')
story.append(TimingChart())
add('Default cache preference; all three series use the same 128 x 1,024 synthetic fixture. Event timing includes the measured kernel interval only.','Small2')
selected=[baseline,fast,packed,item('128_1024_texture-packed_linear_128_max-l1'),item('128_1024_texture-packed_morton8_128_default'),item('128_1024_global_linear_128_default')]
table(['SETTING','MEDIAN (us)','TRIAL RANGE (us)'],[[f"{x['read']} / {x['layout']} / {x['block_size']} / {x['cache']}",f"{x['median_ms']*1000:.2f}",f"{x['min_ms']*1000:.2f} - {x['max_ms']*1000:.2f}"] for x in selected],[295,86,W-381],True)
add(f'The fastest observed median is {improvement:.1f}% below the original 256-thread Morton texture setting. The broad improvement is associated with smaller blocks: the default workload launches 16 blocks at 256 threads, 32 at 128, or 64 at 64, on a 46-SM GPU. Attribution to scheduling is an inference; the sweep does not isolate every execution cost.')
add('Packing alone is not shown to outperform the best scalar texture path. Maximum-L1 does not consistently reduce runtime. Small differences overlap normal laptop variability, and selecting the smallest median out of 36 settings favors noise. These measurements do not establish a universal optimum or an end-to-end speedup including transfers, verification and CSV export.','Small2')

section(5,'Native kernel and implementation boundary')
table(['PATH','NATIVE TLD','REGISTERS / THREAD','LOCAL / SHARED'],[
    ['Four-plane texture','4','78','0 / 0 bytes'],['Packed uint4 texture','1','78','0 / 0 bytes'],['Global loads','0','78','0 / 0 bytes']
],[158,82,136,W-376],True)
add('cuobjdump on the actual executable identifies native sm_120 code. The packed kernel emits one TLD.LZ; the original emits four. All three use native POPC. Resource reporting shows no local allocation or stack and no statically allocated shared memory. This is compiler-output evidence, not a formal proof of the binary. The TEXTURE:0 resource field does not mean no texture instructions; texture objects use runtime handles. [4]')
add('Preserved contract','Sub2')
add('The packed texel channels are exactly x=ASA, y=NA, z=boundary and w=fringe. It replaces the four device mask allocations only for that read path, so total mask bytes and payload accounting stay unchanged. Input resources remain immutable through each launch; texture objects are destroyed before their backing buffers.')
add('Each logical lane still writes its canonical row-major candidate. Morton radial bits remain even and angular-word bits odd; padding never becomes logical output. Whole-word absorption, separate shift-XOR and shift-OR producers, explicit JK bits and literal atan(dp/dr) remain unchanged. All candidates are checked before host state commit.')
add('What was deliberately not claimed','Sub2')
add('No supported API used here locks every dictionary line in L1/texture cache. L2 persistence is a distinct mechanism, not texture pinning. The kernel remains a host-verified word-epoch engine: uploads, readbacks and full diagnostics are still present. Precomputing diagnostics or a persistent device scheduler would change the execution profile and require its own evidence. [2, 5]')
add('Hardware and binary identity','Sub2')
add('46 SMs; 36 MiB reported L2; 12,820,480,000 bytes device memory; driver 591.59 (CUDA driver API 13.1); runtime 12.8. The profiled preferred maximum-L1 sample reports 32,768 bytes configured shared memory despite the preference request. The request itself does not prove the effective partition.','Small2')
add('Validated executable SHA-256:<br/>'+S['executable_sha256'],'Small2')
add('Concept attribution remains in AUTHORSHIP.json: Tom Klootwijk, author-supplied identifier NL200678942 and date 10-07-1990. Implementation and this report are AI-assisted.','Small2')

section(6,'Reproduction and evidence map')
add('Windows commands from the project directory','Sub2')
code('python tools/validate.py --proofs --build C:/Users/Tom/.cache/ak1/cpu\npython tools/validate.py --gpu --sanitizer --proofs\n  --build C:/Users/Tom/.cache/ak1/gpu128\n  --cmake-arg=-Tcuda=12.8')
add('The second command is shown wrapped for readability; join its lines in the shell. A short build path avoids the reproduced MSBuild path-length failure. Explicit CUDA 12.8 selection avoids the stale 12.9 Visual Studio integration found on this machine. No driver, privilege or watchdog setting was changed.','Small2')
code('atomos_cuda.exe --read texture --layout morton8\n  --block-size 64 --cache max-l1\n\natomos_cuda.exe --read texture-packed --layout linear\n  --block-size 128 --cache default')
add('The existing default remains reproducible; the commands explicitly select measured alternatives. Both use host-verified state commits. The complete benchmark and profiling commands are recorded in their JSON logs.','Small2')
paths=[('Current status','results/validation_status.json'),('GPU matrix',S['gpu_validation_path']),('CPU matrix',S['cpu_validation_path']),('Timing sweep',S['benchmark_path']),('Hardware counters',S['profile_path']),('Native instructions / resources','results/review_20260913/sass.txt; resources.txt'),('Repairs / original failures','results/review_20260913/review_summary.json'),('Current source hashes','results/residency_continuation/source_sha256.json' if CONT else 'results/review_20260913/source_sha256.json')]
table(['EVIDENCE','PATH'],paths,[115,W-115],True)
add('Paths beginning with results/ are relative to the project root. The reviewed source differs from the original unsigned SHA256SUMS.txt; that preparation manifest is preserved, with current source hashes recorded separately. Raw evidence is retained; cache fit, source hashes and SMT results are not hardware-residency certificates.','Small2')
add('Primary documentation','Sub2')
refs=[SOURCES[0],SOURCES[1],next(x for x in SOURCES if 'Profiling' in x['title']),next(x for x in SOURCES if 'Binary' in x['title']),next(x for x in SOURCES if 'L2' in x['title'])]
for i,x in enumerate(refs,1):
    add(f'[{i}] <link href="{escape(x["url"],quote=True)}" color="#007F82">{escape(x["title"])}</link>','Tiny')
add('Source URLs, consulted date and claim scope are also retained in docs/cache_sources.json. Full benchmark and profiling records include commands, raw outputs, exact binaries and measured values.','Tiny')


if CONT:
    section(7,'Residency investigation: measured scope')
    add('The continuation tested explicit in-kernel warming, actual K1 work and a final dictionary reread. Correct numerical output and cache residency are evaluated separately. These are optional experimental executables; the validated production paths on pages 1-6 retain their original evidence and binary identity.')
    add('Partitioned execution','Sub2')
    add('One cooperative 512-thread block owns a disjoint, 512-byte-aligned dictionary interval. Runtime occupancy must permit exactly one such block per SM. Every launch records unique SM assignments before and after the work. All 46 SMs participate, including blocks whose assigned interval is empty for small fixtures.')
    add('Each block reads its entire physical interval, computes the unchanged word/JK/OTAN2 epoch for logical cells, then rereads the physical interval. Nontexture input/output requests either L2-only caching (CG) or no L1 allocation (NA). Padding is checked but produces no logical output. All candidates are host-verified before each epoch commit.')
    table(['FIXTURE','DICTIONARY','MAXIMUM SM INTERVAL','LOGICAL LANES'],[
        ['128 x 1,024','64 KiB','1,536 bytes','4,096'],
        ['512 x 16,384','4 MiB','91,648 bytes','262,144']
    ],[117,100,164,W-381],True)
    add('What counts as successful measured retention','Sub2')
    add('Cold profiling flushes caches before each kernel replay. The first pass covers every unique 32-byte dictionary sector on its assigned SM. If total misses equal that compulsory unique-sector floor, the later work and retention pass add no observed misses. This conclusion depends on the verified address coverage, actual texture execution and cold-start protocol; aggregate counters do not identify a miss instruction by program counter.')
    add('Warm and final reads are real overhead. A full aligned epoch issues three dictionary passes: 6,144 nominal sectors at 64 KiB, or 393,216 at 4 MiB. Any excess measured sectors are retained in the evidence. A high hit percentage obtained by these extra reads is not itself a speed improvement.')
    add('Scope limits','Sub2')
    add('Grid barriers establish a common phase boundary across the cooperative launch. Block barriers establish ordering within each SM partition only. Neither variant pins lines across launches or guarantees behavior under arbitrary competing workloads. Endpoint SM samples and collision-prone XOR integrity checks are finite observations, not hardware guarantees.')
    add('Exact run identities, commands, source snapshots and raw counter CSVs: results/residency_continuation/summary.json.','Small2')

    section(8,'Residency results and counterexamples')
    rows=[]
    for study in CONT['partition_studies']:
        for sample in study['aggregates']:
            rows.append([study['label'],sample['size']+' / '+sample['layout'],f"{sample['sectors']:,.0f}",f"{sample['misses']:,.0f}",f"{sample['compulsory_misses']:,.0f}"])
    table(['BARRIER / I-O','FIXTURE / LAYOUT','SECTORS','MISSES','COLD FLOOR'],rows,[71,129,78,78,W-356],True)
    add('CG = L2-only requests; NA = no L1 allocation hint. Each row reports the median of three cold profiles. Default = 128 x 1,024; max = 512 x 16,384. Exact min/max ranges and ordinary event timings are retained. The profiler uses kernel replay, cache-control all, one setup launch skipped and one measured launch; clocks are unmodified.','Small2')
    add(CONT['residency_interpretation'])
    add('Validation of the partition experiment','Sub2')
    add(CONT['validation_description'])
    add('Timing includes all three phases, barriers and diagnostic stores. Uploads, poisoning, readbacks and host checking remain outside the kernel-event interval. No direct performance claim compares these fringe-on controls with the earlier fringe-off sweep.','Small2')
    add('Resource use','Sub2')
    add(CONT['resource_description'])

    section(9,'Controls, practical result and reproduction')
    table(['CONTROL','OBSERVATION'],CONT['control_rows'],[144,W-144],True)
    add('Causal boundary','Sub2')
    add(CONT['causal_interpretation'])
    add('Practical result','Sub2')
    add(CONT['practical_result'])
    add('Reproduce the full-epoch partition study','Sub2')
    code('cmake --build C:/Users/Tom/.cache/ak1/gpu128 --config Release\n  --target atomos_cache_partition\npython tools/study_cache_partition.py\n  --out NEW_EVIDENCE_DIR --barrier grid --explicit-control')
    add('Configure with ATOMOS_ENABLE_CUDA=ON and ATOMOS_CACHE_PARTITION_EXPERIMENT=ON first. Replace grid with block for the per-block control. Wrapped commands must be joined in PowerShell. The retain-only and word-only controls explicitly report that full candidate validation and state commits were not run.','Small2')
    add('Continuation executable SHA-256:<br/>'+CONT['executable_sha256'],'Tiny')
    add('Evidence status: '+CONT['goal_status_description'],'Small2')

def page(c,doc):
    c.saveState();c.setStrokeColor(TEAL);c.setLineWidth(2);c.line(44,34,A4[0]-44,34)
    c.setFont('Helvetica',8);c.setFillColor(GRAY);c.drawString(44,21,'atomOS v3.6 K1 | Tom Klootwijk | 2026-09-13')
    c.drawRightString(A4[0]-44,21,str(doc.page));c.restoreState()
doc=SimpleDocTemplate(str(OUT),pagesize=A4,rightMargin=44,leftMargin=44,topMargin=39,bottomMargin=49,title='atomOS v3.6 - Kernel Validation and Texture Cache',author='Tom Klootwijk; AI-assisted engineering review')
doc.build(story,onFirstPage=page,onLaterPages=page)
print(OUT)
