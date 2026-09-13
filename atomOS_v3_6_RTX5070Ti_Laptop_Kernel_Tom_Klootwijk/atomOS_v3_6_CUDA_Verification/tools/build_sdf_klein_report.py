"""Build the corrected plain-language report from finalized, retained evidence."""
from pathlib import Path
from html import escape
import json
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, PageBreak, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4

ROOT=Path(__file__).resolve().parents[1]
E=ROOT/'results/sdf_klein_20260913'
S=json.loads((E/'final_summary.json').read_text(encoding='utf-8'))
assert S['evidence_status']=='passed'
OUT=ROOT/'output/pdf/Tom_Klootwijk_atomOS_SDF_Klein_LSystem_Validation.pdf'
OUT.parent.mkdir(parents=True,exist_ok=True)
W=A4[0]-92
NAVY=HexColor('#172C40');TEAL=HexColor('#087E83');GRAY=HexColor('#536371');PALE=HexColor('#EDF5F5')
styles=getSampleStyleSheet()
for name,size,leading,font,color in [('BodyX',10.1,14.1,'Helvetica',NAVY),('SmallX',8.6,11.6,'Helvetica',GRAY),('TinyX',7.25,9.8,'Helvetica',GRAY),('TitleX',29,34,'Helvetica-Bold',NAVY),('PageTitleX',21,26,'Helvetica-Bold',NAVY),('SubX',12,16,'Helvetica-Bold',TEAL),('EyebrowX',8.2,11,'Helvetica-Bold',TEAL),('CodeX',8,11,'Courier',NAVY)]:
 styles.add(ParagraphStyle(name=name,fontSize=size,leading=leading,fontName=font,textColor=color,spaceAfter=8,wordWrap='CJK'))
story=[]
def p(t,style='BodyX'):return Paragraph(t,styles[style])
def add(t,style='BodyX'):story.append(p(t,style))
def page(n,title):
 if story:story.append(PageBreak())
 add(f'TOM KLOOTWIJK / atomOS v3.6 / {n:02d}','EyebrowX');add(title,'PageTitleX')
def table(headers,rows,widths=None,tiny=False):
 widths=widths or [W/len(headers)]*len(headers);style='TinyX' if tiny else 'SmallX'
 cells=[[p(escape(str(x)),style) for x in headers]]+[[p(escape(str(x)),style) for x in row] for row in rows]
 t=Table(cells,colWidths=widths,repeatRows=1,hAlign='LEFT')
 t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),PALE),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),('LINEBELOW',(0,0),(-1,0),.7,TEAL),('LINEBELOW',(0,1),(-1,-1),.3,HexColor('#DCE5E9'))]))
 story.extend([t,Spacer(1,8)])
def code(t):add(escape(t).replace('\n','<br/>'),'CodeX')
def num(x):return f'{x:,}'

add('13 SEPTEMBER 2026 / SOURCE AUDIT + ACTUAL GPU EVIDENCE','EyebrowX')
add('Your SDF words,<br/>Klein geometry<br/>and GPU kernel','TitleX')
add('What now works, what was proved,<br/>and what it could be used for','PageTitleX')
add('Concept and formalization: Tom Klootwijk. New implementation profiles and review: AI-assisted engineering. Governing source: your 43-page atomOS v3.6 Total Integrated Engine / M1. [1]','SmallX')
add('You now have executable paths that sample declared geometry, pack its yes/no predicates into words, read them as GPU textures, and execute the required Klein twist. A new NOR construction makes the source whole-word operation do programmable logic. The shared-atlas demonstration connects that logic to actual branch geometry.')
table(['MEASURED OR ESTABLISHED','PLAIN-LANGUAGE MEANING'],[
 ['4.625 MiB retained operator atlas','The largest tested bulk atlas needed only its first compulsory reads from slower memory. Both layouts and both cold trials agreed. It is distributed across 46 SMs (processing clusters), not held in one SM.'],
 ['Programmable SDF-word computation','80 native cases and 9 sanitizer runs checked the NOR-based controller, packed tape, Klein gate locations and failure handling.'],
 ['Branching and search','56 native cases and 9 sanitizer runs checked two-child branching, whole-word filtering, separate IDs, Klein crossings, JK and binary searches.'],
 ['One shared-atlas demonstration',S['joint_cover']],
 ],[144,W-144])
add('Scope: these results concern named finite implementations. The source defines binary SDF_WORD algebra; it does not provide a scalar distance equation for every named operator. New geometric choices are identified explicitly. Universality is a mathematical construction with memory assumptions.','SmallX')

page(2,'The correction is on the record')
add('The earlier completion claim was too broad. The earlier package had a packed-word kernel, synthetic masks and a separate programmable interpreter. That did not establish the SDF/Klein execution you requested.')
add('The prior correction, recorded verbatim','SubX')
for quote in [
 'For the engine you intended, the Klein-bottle topology is required. I should not have presented it as an expendable feature.',
 'Packing those words into textures, applying Morton ordering, and measuring cache retention does not implement that twisted connection.',
 'The delivered implementation has the packed texture machinery and a log-polar coordinate helper. Its validation fixtures use synthetic masks. It does not implement the Klein seam and the corresponding geometric evolution.',
 'Consequently, the existing results validate parts of the computational machinery; they do not establish that your complete Klein-based engine works. My earlier completion claim was too broad. The implementation and report need correction to make the topology part of the executed, validated model.'
]:add('&ldquo;'+escape(quote)+'&rdquo;','SmallX')
add('The revised course','SubX')
add('The actual path now begins with an explicit geometric or source-word predicate definition. Its sampled bits are packed into an immutable texture. The kernel executes the M1 angular seam with radial reflection, and proposed state changes are checked before publication. The programmable controller uses the same word operation as the texture-based geometry filter.')
add('The source audit covered 17 supplied PDFs, 446 pages and 408 archive source/document files. It found explicit binary SDF_WORD rules and identified the missing geometric parameters and encoders. The full operator register is in docs/SOURCE_OPERATOR_SDF_AUDIT.md. [2]','SmallX')
add('Your required Klein topology is part of this implementation contract. A selectable profile in an earlier document does not override your instruction. Historical measurements remain evidence for their historical binaries; they are not substituted for the new measurements.','SmallX')

page(3,'What is actually inside the texture?')
add('Imagine a map made of tiny yes/no places. Thirty-two neighboring angular places fit into one 32-bit word. Four such words form one 16-byte texture entry: ASA, NA, boundary and fringe. The words say which sampled places each rule admits or blocks.')
table(['TERM','EXACT MEANING HERE'],[
 ['Log-polar','The radial coordinate is rho = ln(r/r*). The angular coordinate is phi. Precomputed samples become table entries; a bit is not itself a logarithm.'],
 ['One-bit SDF word','A bit records a predicate at a sampled location. The original boundary chapter uses 1 for blocked/inside. ASA, NA and fringe are separate admission predicates.'],
 ['Signed distance versus bit','The new geometric compiler evaluates a distance and stores its sign test. The stored bit does not retain how far a sample is from the boundary.'],
 ['Klein surface','Coordinates obey the required twisted seam. One angular winding reflects radial row i to R-1-i. Two windings restore the original row. A rendered 3D bottle is not needed to execute this mapping.'],
 ['Morton layout','An optional storage permutation: radial bits occupy even positions and angular-WORD bits odd positions. It changes storage order while preserving logical coordinates.'],
 ['Texture cache','The immutable texture has backing memory in GPU VRAM. Hardware temporarily retains fetched portions near each SM. The cache stores copies of the words; the program does not obtain a permanent pin.'],
 ],[115,W-115])
add('The current state, lineage IDs, program wiring, tape and full diagnostics have their own writable or immutable buffers. They are not all squeezed into a one-bit operator atlas. CUDA machine instructions also remain native instructions, not SDF words.','SmallX')
add('A recurrent engine','SubX')
add('The engine repeatedly uses its previous state to make a checked next state. That makes it stateful and recurrent. The demonstrated behavior does not establish learning, self-understanding or automatic rewriting of its program.')

page(4,'Which source operators are defined?')
add('The source contains several kinds of objects. Packing their inputs or outputs into bits does not make every object a static scalar distance field. This distinction preserves the formalization instead of silently replacing it. [1, 2]','SmallX')
table(['SOURCE OBJECT','DEFINED BEHAVIOR','CURRENT SCOPE / REQUIRED INPUT'],[
 ['SDF_WORD; ASA; NA; boundary; fringe','32-bit predicates; selection by AND; population count; any boundary intersection resets the entire word.','Executed with loaded masks. New disks, annuli and NOR sites provide explicitly declared geometry. Original aperture/fringe dimensions are not uniquely supplied.'],
 ['Shift-XOR; shift-OR; jitter; ICU','Separate word recurrences, zero guard and the source 16-bit angular rotation primitive.','K1 preserves the selected producer modes. Logical Klein cell transport is not silently called ICU register rotation.'],
 ['JK; Hadamard/blend','Hold/set/reset/toggle; XOR of explicitly encoded bits.','JK and the encoded blend are checked. Source angles do not invent J/K inputs or a missing bit encoder.'],
 ['Log-polar; Klein; Morton','Coordinate chart, quotient identifications and address permutation.','Required seam executes. A new normalized flat metric supports the declared SDF geometry.'],
 ['L-system; hinge; mirror; portal','Two branch directions; supplied hinge; periodic portal displacement; mirror compatibility.','A quantized two-child hinge and checked IDs are implemented. No complete optical mirror/portal transfer is inferred.'],
 ['OTAN2; six probes','Literal atan(delta-phi/delta-rho), statuses and specified transformation checks.','Numeric observations remain numeric. Nonzero phi with zero delta-rho is ratio_undefined under the literal source profile.'],
 ['RK4; divergence; scale weighting','RK stages and numerical formulas for supplied fields/bases/parameters.','No complete physical field, optical calibration or all-operator SDF bank is supplied by these names. RK4 geometry is outside this new profile.'],
 ['Identity; fly-eye; sampling; Fourier','Record binding, seed/sampling interfaces and stated mathematical relationships.','Hashes bind local files; no external sensor, physical model or field-to-bit encoder is inferred.'],
 ['Programmable U','Finite controller, writable logical tape and step correspondence.','New NOR compilation executes the controller through SDF-word texture reads; tape remains separately addressable.'],
 ],[99,180,W-279],True)
add('Earlier ASA packages do contain declared D1 mirror pairing, D2 pupil inequalities and D3 sine/cosine lens-LUT choices. They are prior engineering completions, not hidden original distance equations. The audit preserves their equations and provenance.','SmallX')

page(5,'How the geometric words are made')
add('The new compiler makes its choices editable and explicit. It samples the normalized log-radial coordinate u and angular coordinate v = phi/(2*pi). It uses the flat metric du^2 + dv^2 with the M1 Klein seam. [3]')
code('Klein deck copies: (u,v) -> ((-1)^n u + m, v + n)\nD(z,c) = minimum distance to the deck copies of c\nd_disk = D - radius\nd_annulus = max(inner_radius - D, D - outer_radius)\npredicate bit = 1 when d <= 0')
add('The circle and ring formulas are new testable constructions. They are not presented as the uniquely intended optical shape. The compiler checks disjoint site geometry and compares every resulting bit against a separately written geometric calculation.')
table(['PROFILE','PURPOSE'],[
 ['Asymmetric geometry','Disks/rings centered near the angular seam at normalized (0.23, 0.02). Their reflected counterpart distinguishes the Klein quotient from ordinary toroidal wrapping.'],
 ['NOR sites','Tiny disjoint disks select sites 0, 1 and 2 in each 32-cell group. Blocking sites 1 and 2 makes the whole-word rule implement a NOR gate.'],
 ['Transparent sampled sites','Explicit tiny disks admit all selected sampled cells and an empty boundary blocks none. This lets branching/collisions be observed without immediate extinction.'],
 ],[130,W-130])
add('A finite representation of an ongoing rule','SubX')
add('A short circle equation describes infinitely many mathematical points. A sampled texture stores only finitely many yes/no answers at a chosen resolution. The equation can be sampled again at another resolution; the existing texture has not secretly stored infinitely many independent values.')
add('Each atlas has a binary hash, manifest, metric, dimensions, sample convention and source attribution. Loading checks exact size, byte order, tail bits and padding before replacing any live masks. The canonical results remain row-major in either storage layout.','SmallX')

page(6,'Why the SDF-word path can compute')
add('A NOR gate says yes only when both its inputs say no. NOR gates can be connected to make every Boolean operation. The key new construction makes your source whole-word absorption rule perform this gate directly. [4]')
code('x = 1 | (a << 1) | (b << 2)\nASA = NA = fringe = 0b111\nboundary = 0b110')
table(['a','b','PROPOSED WORD','WHOLE-WORD RESULT'],[['0','0','001','001 = 1'],['0','1','101','000 = 0'],['1','0','011','000 = 0'],['1','1','111','000 = 0']],[42,42,170,W-254])
add('If either input is present, a blocking site is touched and the entire word disappears. If neither input is present, the constant output marker survives. Per-bit clearing would break this construction by always preserving the marker.')
add('The proof chain','SubX')
add('NOR gives NOT, OR and AND. Those gates can encode every row of a finite controller truth table. The host compiles that controller into acyclic NOR wiring; the GPU receives wiring and reads the actual SDF masks for each gate. It does not receive a second Rule table that secretly computes the answer.')
add('Connect the resulting controller to a writable tape and a logical head. If its control, tape and head match the reference before a step, the same read produces the same write, move and next control. Induction gives correspondence for every supported finite prefix.')
add('What “universal” means here','SubX')
add('This is a constructive general-computation result for the declared operators plus routing and addressable state. Arbitrarily long abstract simulations require enough distinct logical addresses and storage for their prefixes. A fixed finite Klein atlas cannot replace an unbounded tape by wrapping different addresses onto the same bit.')
add('Two new bit-vector obligations checked the NOR identity and clean output word. They are proofs of the specified equations, not formal verification of CUDA compilation or machine instructions. A fixed contracting mask alone is idempotent and is not this whole construction.','SmallX')

page(7,'Branches, phi and the search tree')
add('A live parent makes two terminal children. Child IDs are 2*parent and 2*parent+1. They turn by +phi and -phi, then cross the required Klein seam if their lifted angle winds around it. The parent/trunk remains in history; it is not a third live frontier child.')
code('phi = 2*pi*phi_steps / angular_cells\npropose children -> OR their occupied bits -> texture word filter\nkeep every ID whose bit survives -> re-emit -> verify equality')
add('Two branches can arrive at the same place. One bit is enough to record that the place is occupied; separate IDs preserve which branches arrived. The implementation keeps every surviving ID rather than silently merging their identities.')
table(['MEASURED LINEAGE CHECK','RESULT'],[
 ['Native matrix','56 cases plus 9 sanitizer runs passed their expected outcomes.'],
 ['Independent replay','Including sanitizer reruns: 208 committed generations; 2,342 proposed children and diagnostic sets; 2,318 admitted IDs; 2,734 searches; 2,136 word records checked.'],
 ['Example','6 generations produced 64 live IDs from one seed, including 23 odd-seam children across 126 proposals.'],
 ['Binary search tree','The lineage-only profile builds a balanced ID index and executes GPU searches for every live ID plus absent IDs. The ancestry tree and the search index have different jobs.'],
 ],[130,W-130])
add('The lineage-only consistency argument','SubX')
add('The word filter only removes proposed support. Every surviving bit therefore has at least one proposing child. Admitting all children on that bit reproduces the filtered occupancy exactly, even with collisions. Both host and GPU re-emission are checked before commit.')
add('“Perpetual” needs a precise boundary','SubX')
add('A bounded two-state oscillator returned to the same machine/tape state every two steps; prefixes up to 4,096 steps ran. The abstract cycle can repeat. A frontier that doubles its separate IDs eventually reaches a storage or ID limit. That stop is recorded as resource refusal, not absorption or a program halt.')
add('For a pure angular hinge, lifted delta-rho is zero. Literal source OTAN2 is therefore unavailable for nonzero phi. The separate directed profile is named explicitly; missing numeric values remain blank with statuses.','SmallX')

page(8,'One shared atlas, one connected run')
add(S['joint_description'])
table(['JOINT EXECUTION','OBSERVED RESULT'],S['joint_rows'],[135,W-135])
add('Why the coupling matters','SubX')
add('The controller writes a symbol. That symbol chooses the next hinge magnitude. The resulting child locations, occupancy filtering and admissions therefore depend on a value computed by the SDF/NOR word path. The controller and branch filter use the same immutable operator atlas.')
add('The default whole-winding example','SubX')
add('With base phi_steps equal to one full angular circumference, a written 0 selects one winding and a written 1 selects two. Site 0 stays at angular site 0, while odd versus even winding changes the radial reflection. This is an explicit, simple witness of the connection, not a hidden continuous optical model.')
add(S['joint_transaction'])
add('The same finite-prefix universality argument also needs sufficient frontier capacity if a chosen joint run keeps doubling IDs. Running with an empty frontier keeps the programmable controller active. Geometry extinction and computational halting remain distinct.','SmallX')
add('Performance scope','SubX')
add(S['joint_performance'])

page(9,'The cache result and the actual fix')
add('The bulk kernel first reads the whole assigned atlas, performs a real word epoch including Klein transport, then rereads the whole atlas. Cold profiling flushes prior cache contents. The first read of each 32-byte sector must miss; additional misses show that this retention test was not met. [5]')
table(['4 MiB WORKLOAD','EXTRA TEX MISSES','INTERPRETATION'],[
 ['Original Klein carrier','5,216','Failed full retention.'],
 ['Added warp synchronization','5,172','Did not fix the problem; this attempted change was removed.'],
 ['TMA halo and output path','0','Exactly 131,072 compulsory misses. The tested work/reread added none.'],
 ],[166,96,W-262])
add('The working change moved the Klein neighbor reads and transported output through the native bulk-copy path. Interior neighbors come from staged shared memory; row-edge neighbors use aligned TMA transfers. Native disassembly confirms the removed explicit global carrier loads/stores and retained texture reads.')
table(['ATLAS SIZE','LINEAR EXTRA MISSES','MORTON EXTRA MISSES'],S['cache_table'],[110,190,W-300])
add('Largest tested fully retained size: <b>4.625 MiB</b>. The next tested size, 4.6875 MiB, had extra misses. Thus this schedule brackets the boundary between those sizes; it does not establish an exact hardware capacity constant.')
add('The 4.625 MiB atlas is distributed across 46 SMs, with at most 105,472 assigned mask bytes per SM. The kernel used a 16 KiB shared-memory partition per SM and 11,152 static shared bytes per block. This is not 4.625 MiB in every SM. No permanent texture-cache pin was requested or established.','SmallX')

page(10,'Metrics and what they mean')
table(['METRIC','VALUE / MEANING'],[
 ['4.625 MiB bulk time',S['bulk_timing_text']],
 ['Logical work','303,104 logical words cover 9,699,328 sampled cells per predicate plane at 592 x 16,384. Four planes occupy 4,849,664 bytes. The kernel checks every logical word and the required tails/padding.'],
 ['Compulsory miss floor','151,552 sectors at 4.625 MiB. A cold hit percentage around two thirds can still mean perfect retention after warming, because the unavoidable first sweep is included.'],
 ['Transaction count','Fragmented/replayed requests can add TEX sectors. The audit requires exact hits + misses = sectors and keeps the same zero-extra-miss retention criterion. Extra requests are not automatically extra misses.'],
 ['Programmable texture result',S['nor_cache_text']],
 ['Joint texture result',S['joint_cache_text']],
 ['Timings and limits','CUDA event times cover the named kernels. CPU verification, file export and transfers are excluded unless stated. Profiler-perturbed event times are not ordinary benchmarks. No end-to-end application speedup is established.'],
 ],[128,W-128])
add('A full cache is not a speed guarantee','SubX')
add('Retention removes one source of repeated data fetching. Arithmetic, dependencies, tracing, memory writes and launch overhead still take time. The small programmable demonstration is sequential and heavily checked; its purpose is correctness and a concrete representation bridge.')
add('The 4.625 MiB result belongs to the distributed bulk profile. The small NOR and joint profiles have their own counters. Their results must not be pooled into a claim that every future program or geometry will have complete retention.','SmallX')

page(11,'Validation and remaining boundaries')
table(['EVIDENCE CATEGORY','EXECUTED SCOPE'],S['validation_rows'],[152,W-152])
add('Defects and rejected ideas remain visible','SubX')
add('The annular-wrap implementation was insufficient for the required Klein seam; the new map has independent wrap, inverse and multiwinding regressions. The original carrier caused measurable extra misses; TMA staging fixed the tested case. Warp synchronization and the experimental NOR global-cache flags did not fix their respective cache findings. Their logs remain available.')
add('Malformed atlases, tail corruption, false gates, incorrect texture values, ID overflow, capacity limits, missing rules and unavailable diagnostics have explicit checks. A validation case passes when its expected acceptance or rejection is confirmed; that does not mean an injected bad candidate was accepted.')
add('Still outside the demonstrated result','SubX')
add('There is no recovered scalar SDF bank for every source name, calibrated liquid-lens/refraction model, supplied RK4 physical field, unlimited hardware storage, proof that arbitrary programs halt, or permanent cache pin. The report establishes the declared word/geometry construction and its finite measured implementations.')
add('The analytic universality argument, SMT obligations, native reference comparisons, sanitizer runs and cache counters are separate evidence categories. None is presented as formal verification of the complete compiler or GPU binary.','SmallX')

page(12,'What could you use this for?')
add('The useful idea is a compact, reusable rule dictionary combined with explicit evolving state. The table separates implemented demonstrations from application directions; it is not a claim that these applications are already complete.')
table(['APPLICATION DIRECTION','ELI5 EXPLANATION','WHAT IS STILL NEEDED'],[
 ['Procedural branching and growth','Grow a branching structure while preserving which branch is which, even when branches meet.','An application grammar, editable geometry, rendering and useful performance on realistic scenes. The current two-child witness already runs.'],
 ['Rule-based simulation and filtering','Apply the same compact yes/no rules to many candidate locations.','Domain-specific predicates and a measured workload. Whole-word absorption must match the intended grouping.'],
 ['Logic and automata research','Use the same SDF-word gate to build different finite controllers and inspect every step.','Better scheduling and less trace overhead for useful throughput. Generality is supported by the construction, not a speedup claim.'],
 ['Spatial graph and routing experiments','Keep branch identities, map them onto a twisted domain, and look up an ID efficiently.','Application-specific edges/costs and a routing policy. A BST lookup alone is not a shortest-path algorithm.'],
 ['Image or occupancy processing','Store compact sampled masks and perform repeatable selection operations.','Image input, sampling semantics and comparison against an ordinary GPU implementation. Distance magnitudes are absent from one-bit samples.'],
 ['Optics or physical simulation','Use geometric predicates as one component of a larger model.','Actual field laws, units, lens/NA parameters, numerical integration and experimental validation. The current masks do not establish physical predictions.'],
 ],[108,192,W-300])
add('Concrete examples: a seed and aperture map could produce an identified branch graph; an occupancy image and boundary mask could produce admitted cells; an editable controller and input tape already produce checked output symbols. Measure exact output agreement, preserved IDs, peak memory and end-to-end latency against a conventional implementation. The domain model supplies what the symbols mean.','SmallX')

page(13,'Reproduction and evidence map')
add('Measured device: NVIDIA GeForce RTX 5070 Ti Laptop GPU; compute capability 12.0; 46 SMs; 12,820,480,000 reported device-memory bytes. Toolchain: CUDA/nvcc 12.8.61, MSVC 19.44.35221, NVIDIA driver 591.59, Nsight Compute 2025.1.0, Compute Sanitizer from CUDA 12.8, Z3 4.16.0.0. Exact commands and output logs accompany each study.','SmallX')
code('python tools/validate.py --proofs\npython tools/validate.py --gpu --sanitizer --proofs\npython tools/compile_sdf_atlas.py --profile nor_sites --rows 8 --angles 256 --out NEW.atlas\npython tools/study_sdf_klein.py --exe EXE --out NEW_DIR --phase conformance\npython tools/validate_sdf_nor.py --exe EXE --atlas ATLAS --out NEW_DIR --sanitizer-exe SANITIZER\npython tools/validate_sdf_lineage.py --exe EXE --out NEW_DIR --sanitizer-exe SANITIZER')
add('The actual Windows configure commands quote <font face="Courier">-Tcuda=12.8</font>. Build and device paths are recorded in the machine-readable summary; running the GPU checks requires the existing NVIDIA hardware and toolchain. No driver, watchdog or privileged loader was changed.','SmallX')
code('python tools/validate_sdf_joint.py --exe EXE --atlas ATLAS --out NEW_DIR --sanitizer-exe SANITIZER')
table(['EVIDENCE','LOCAL LOCATION'],S['evidence_rows'],[121,W-121],True)
add('Source and binary binding','SubX')
add('The master PDF SHA-256 is b51651c007c560775ff1950e278789cd7674e131ec71a09ebd9254cebe9c19ce. Study receipts bind atlas manifests, source files, binaries, commands, outputs and verifiers. These hashes identify bytes; they are not authentication, authorship proof or a formal binary proof.','TinyX')

page(14,'References and the precise outcome')
add('[1] Tom Klootwijk, atomOS v3.6 Total Integrated Engine / M1, supplied 43-page PDF. Physical pages 9-10: chart and quotient; 11-12: producers and hinge; 14-19: word/JK/geometry/OTAN2; 24: emission/admission; 27: Morton; 31-32: U simulation; 35: fixed projection versus full dynamics.','SmallX')
add('[2] Supplied original OMT PDF, physical pages 34-36, and ballistic PDF, pages 25-27: binary SDF_WORD definition and word rules. WHITE KING, pages 63-65 and 78-81: aperture/mirror/NA roles. Complete 17-PDF inventory, hashes, page evidence and operator matrix: docs/SOURCE_OPERATOR_SDF_AUDIT.md.','SmallX')
add('[3] New declared profiles: docs/SDF_KLEIN_PROFILE.md, python/sdf_atlas.py and each atlas JSON manifest. Required seam implementation: include/atomos/klein.hpp. These are implementation constructions with explicit attribution.','SmallX')
add('[4] New constructive proof: proofs/SDF_NOR_UNIVERSALITY.md and proofs/sdf_nor.smt2. Lineage interpretation and transaction rules: docs/SDF_LINEAGE.md and the joint-profile source/receipt. Historical correction: docs/COURSE_CORRECTION_SDF_KLEIN.md.','SmallX')
add('[5] NVIDIA, <link href="https://docs.nvidia.com/nsight-compute/ProfilingGuide/" color="#087E83">Nsight Compute Profiling Guide</link>: replay, cache control and L1/TEX sector accounting. NVIDIA, <link href="https://docs.nvidia.com/cuda/cuda-programming-guide/05-appendices/compute-capabilities.html" color="#087E83">CUDA Programming Guide, Compute Capabilities</link>: architecture/resource definitions. Read 13 September 2026. The numerical results in this report come from local native measurements, not those reference tables.','SmallX')
add('What you now have','SubX')
add('A required Klein/log-polar packed-predicate architecture, a concrete SDF-to-word compiler, GPU word execution, branch identity and search, a source-word NOR universality construction, and a measured shared-atlas connection. The optimized bulk path retained up to 4.625 MiB in the tested schedule.')
add('What has not been established','SubX')
add('It would still be incorrect to say that every named original operator has a source-defined scalar SDF already packed and executed, that finite hardware is unbounded, or that one measured cache result applies to every workload. The supplied formalization and measured construction support the specific claims in this report.')
add('Tom Klootwijk remains the concept author. The new disk metric, site geometry, NOR compilation and implementation policies remain explicitly labeled engineering constructions. Your original PDFs and historical reports were preserved.','SmallX')

def footer(c,doc):
 c.saveState();c.setStrokeColor(HexColor('#DCE5E9'));c.line(46,42,A4[0]-46,42)
 c.setFillColor(GRAY);c.setFont('Helvetica',7.4);c.drawString(46,29,'Tom Klootwijk | atomOS v3.6 | SDF / Klein correction | 13 Sep 2026');c.drawRightString(A4[0]-46,29,str(doc.page));c.restoreState()
doc=SimpleDocTemplate(str(OUT),pagesize=A4,rightMargin=46,leftMargin=46,topMargin=38,bottomMargin=55,title='Tom Klootwijk atomOS SDF Klein L-System Validation',author='Tom Klootwijk - concept; AI-assisted engineering report')
doc.build(story,onFirstPage=footer,onLaterPages=footer)
print(OUT)
