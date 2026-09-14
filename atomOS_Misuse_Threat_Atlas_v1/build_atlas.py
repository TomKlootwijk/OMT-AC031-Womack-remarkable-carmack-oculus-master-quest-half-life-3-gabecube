"""Build the documented, conditional atomOS misuse atlas (ReportLab; no kernel changes)."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
from html import escape

from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph
from pypdf import PdfReader

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PACKAGE = ROOT / 'atomOS_v3_6_RTX5070Ti_Laptop_Kernel_Tom_Klootwijk' / 'atomOS_v3_6_CUDA_Verification'
OUTPUT = ROOT / 'Tom_Klootwijk_atomOS_Misuse_Threat_Atlas_Rainbow_v1.pdf'
DATE = '14 September 2026'
VERSION = '1.0'
W, H = A4
M = 44
CW = W - 2 * M
INK = colors.HexColor('#172B3A')
MUTED = colors.HexColor('#506473')
LINE = colors.HexColor('#D8E1E8')
PALE = colors.HexColor('#F2F6F9')
WHITE = colors.white
BANDS = [
    (1, 'C', 'Trace', '#8050B2', 'Minor nuisance or readily reversible local disruption; no sensitive data or bodily harm in the stated scenario.'),
    (2, 'D', 'Limited', '#4C4A91', 'Recoverable local loss or unfairness affecting a limited activity, with a practical route to recovery.'),
    (3, 'E', 'Material', '#247AB5', 'Meaningful financial, privacy or operational harm, or substantial waste of resources.'),
    (4, 'F', 'Serious', '#27815D', 'Substantial individual harm, coercion, discrimination or a persistent violation of rights.'),
    (5, 'G', 'Severe', '#E4BD35', 'Serious injury or major consequences for a community, organization or service.'),
    (6, 'A', 'Critical', '#D37628', 'Plausible loss of life, multiple serious injuries or sustained disruption of an essential service.'),
    (7, 'B', 'Extreme', '#B7404A', 'Catastrophic mass harm or irreversible systemic damage, conditional on independently capable external systems.'),
]

def read_json(name):
    return json.loads((HERE / name).read_text(encoding='utf-8-sig'))

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def safe(text):
    return escape(str(text), quote=False)

def init_fonts():
    candidates = [Path('C:/Windows/Fonts'), Path('/usr/share/fonts/truetype/msttcorefonts')]
    fontdir = next((p for p in candidates if (p / 'arial.ttf').exists()), None)
    if fontdir is None:
        raise RuntimeError('Arial regular, bold and italic fonts are required; specify an installed compatible font set.')
    for name, filename in [('Atlas', 'arial.ttf'), ('AtlasBold', 'arialbd.ttf'), ('AtlasItalic', 'ariali.ttf')]:
        pdfmetrics.registerFont(TTFont(name, str(fontdir / filename)))
    pdfmetrics.registerFontFamily('Atlas', normal='Atlas', bold='AtlasBold', italic='AtlasItalic', boldItalic='AtlasBold')

class Atlas:
    def __init__(self):
        init_fonts()
        self.c = canvas.Canvas(str(OUTPUT), pagesize=A4, pageCompression=1)
        self.c.setTitle('atomOS Misuse Threat Atlas - Rainbow and Tone Scale v1.0')
        self.c.setAuthor('Tom Klootwijk (formalization); OpenAI Codex (AI-assisted threat analysis and layout)')
        self.c.setSubject('40 conditional misuse scenarios, evidence boundaries, warning signs and safeguards')
        self.c.setCreator('ReportLab; editable source in atomOS_Misuse_Threat_Atlas_v1')
        self.styles = {}
        for name, size, leading, font, color in [
            ('body', 10.5, 14.1, 'Atlas', INK),
            ('card', 10.0, 13.1, 'Atlas', INK),
            ('small', 9.0, 11.8, 'Atlas', MUTED),
            ('table', 9.6, 12.4, 'Atlas', INK),
            ('h2', 13.0, 16.2, 'AtlasBold', INK),
            ('h3', 11.2, 14.3, 'AtlasBold', INK),
            ('lead', 12.0, 16.5, 'Atlas', MUTED),
            ('title', 25.0, 29.0, 'AtlasBold', INK),
            ('cover', 39.0, 43.0, 'AtlasBold', INK),
        ]:
            self.styles[name] = ParagraphStyle(name, fontName=font, fontSize=size, leading=leading, textColor=color, spaceAfter=0)
        self.n = 0
        self.audit = []
        self.titles = []

    def rect(self, x, y, w, h, fill, stroke=None, radius=0):
        c = self.c
        c.setFillColor(fill)
        c.setStrokeColor(stroke or fill)
        if radius:
            c.roundRect(x, H-y-h, w, h, radius, stroke=bool(stroke), fill=1)
        else:
            c.rect(x, H-y-h, w, h, stroke=bool(stroke), fill=1)

    def p(self, text, x, y, w, style='body', limit=787):
        paragraph = Paragraph(text, self.styles[style])
        _, height = paragraph.wrap(w, H)
        if y + height > limit + 0.1:
            raise ValueError(f'Page {self.n}: text overflow {y+height:.1f}>{limit}: {text[:100]}')
        paragraph.drawOn(self.c, x, H-y-height)
        self.audit.append({'page':self.n, 'top':round(y,2), 'bottom':round(y+height,2), 'style':style})
        return y + height

    def text(self, text, x, y, size=9, font='Atlas', color=MUTED):
        self.c.setFont(font, size)
        self.c.setFillColor(color)
        self.c.drawString(x, H-y-size, text)

    def rule(self, y):
        self.c.setStrokeColor(LINE)
        self.c.setLineWidth(.6)
        self.c.line(M, H-y, W-M, H-y)

    def page(self, title, subtitle='', key=None):
        if self.n:
            self.footer()
            self.c.showPage()
        self.n += 1
        self.titles.append(title)
        key = key or f'p{self.n}'
        self.c.bookmarkPage(key)
        self.c.addOutlineEntry(title, key, level=0, closed=False)
        self.text('atomOS  /  MISUSE THREAT ATLAS', M, 23, 8.3, 'AtlasBold')
        self.text('CONDITIONAL CONSEQUENCES  /  v1.0', W-260, 23, 8.0)
        self.rule(43)
        y = self.p(safe(title), M, 60, CW, 'title')
        if subtitle:
            y = self.p(subtitle, M, y+9, CW, 'body')
        return y+22

    def footer(self):
        self.rule(H-43)
        self.text('Tom Klootwijk formalization  |  AI-assisted analysis  |  14 Sep 2026', M, H-31, 8.0)
        self.text(f'{self.n:02d} / 23', W-M-39, H-31, 8.2, 'AtlasBold')

    def panel(self, title, body, y, fill=PALE, width=None, x=M, style='body'):
        width = width or CW
        ph = Paragraph(body, self.styles[style]).wrap(width-28, H)[1]
        hh = Paragraph(title, self.styles['h2']).wrap(width-28, H)[1]
        height = ph + hh + 36
        self.rect(x, y, width, height, fill, radius=7)
        self.p(title, x+14, y+13, width-28, 'h2', y+height-10)
        self.p(body, x+14, y+21+hh, width-28, style, y+height-8)
        return y+height+15

    def section(self, title, body, y):
        y = self.p(title, M, y, CW, 'h2')+7
        return self.p(body, M, y, CW)+18

    def flag(self, level, x, y, compact=False):
        _, note, name, hx, _ = BANDS[level-1]
        label = f'L{level} / {note}' if compact else f'L{level} / {note} / {name.upper()}'
        self.rect(x, y, 4, 16, colors.HexColor(hx))
        self.text(label, x+9, y+1, 8.6, 'AtlasBold', INK)

    def finish(self):
        self.footer()
        self.c.save()
        if self.n != 23:
            raise AssertionError(f'Expected 23 pages, got {self.n}')

def cover(a):
    a.page('Threat atlas', key='cover')
    # White over the normal title to make room for the cover typography.
    a.rect(M, 53, CW, 72, WHITE)
    a.p('atomOS<br/>Misuse threat atlas', M, 87, CW, 'cover')
    a.p('A first-principles map of computational,<br/>spatial and physical possibility spaces', M, 194, CW, 'lead')
    a.text('40 SCENARIOS  /  7 COLORS  /  7 MUSICAL NOTES', M, 254, 10.3, 'AtlasBold', INK)
    bandw = CW/7
    for i, (level,note,name,hx,_) in enumerate(BANDS):
        x = M+i*bandw
        a.rect(x, 281, bandw-3, 14, colors.HexColor(hx))
        a.text(f'L{level} / {note}', x+4, 307, 10.8, 'AtlasBold', INK)
        a.text(name, x+4, 327, 8.5)
    y = a.panel('The central finding',
        'The formalization describes ways to encode, transform and verify finite computational states. Misuse becomes concrete when an actor controls inputs, program publication, claims made about results, or an added interface to people and physical systems.', 377)
    y = a.panel('Read the colors as conditional harm',
        'The flags describe consequences <b>if the stated prerequisites are supplied</b>. They do not measure likelihood or identify an active threat. No malicious deployment or external physical connection is established by the reviewed evidence.', y)
    a.p('Prepared for Tom Klootwijk<br/><b>Formalization and required log-polar/Klein direction:</b> Tom Klootwijk<br/><b>Threat analysis, invented scale and layout:</b> AI-assisted synthesis<br/>Version 1.0  |  '+DATE, M, y+7, CW, 'small')

def scope(a):
    y = a.page('What exists, and what follows', 'A source-grounded scope statement before assigning a threat color.')
    y = a.section('The implemented computational core',
        'The required format combines seeded, packed one-bit program pages on a log-polar chart with Klein seam handling and a fixed source-word SDF NOR operator atlas. The current bank has seven pages, including three admitted teacher-derived procedures: a full adder, binary-to-Gray conversion and a selector. [K1, K2]', y)
    y = a.panel('Measured texture residency has a bounded scope',
        'The documented program pages plus operator atlas occupy <b>2,816 texture bytes</b>. Four cold profiles recorded the expected 88 compulsory 32-byte sector misses and no additional misses. This supports retention within those measured launches. Permanent cache pinning, arbitrary-workload residency and general performance superiority are unproved. [K2]', y)
    y = a.section('The current knowledge route',
        'A local teacher pipeline uses a loopback Ollama API and cached models to propose finite algorithms. Admission checks the unchanged finite specification and rejects duplicate functions. The admitted bank holds executable procedures; it does not hold the teachers\' weights. General language behavior and a persistent native texture worker between queries remain unfinished. [K2]', y)
    y = a.section('The physical boundary',
        'The reviewed core has no demonstrated live sensor feed, external identity matcher, neural or biochemical interface, physical actuator or weapon controller. The main formalization itself identifies missing interfaces and rejects treating named external systems as established connections. Source language about such systems is not evidence of access to them. [M1 pp. 24, 29, 36, 40]', y)
    a.panel('Correctness does not settle purpose',
        'A computation can faithfully implement a harmful specification. A finite truth-table check does not prove empirical truth, consent, safe deployment or general harmlessness. Likewise, semantic novelty does not by itself establish usefulness. This distinction drives the entire atlas. [K1; R1, R2]', y)

def primitives(a, grounding):
    y = a.page('Where the misuse could attach', 'Primitive-level reading of the main formalization. Page numbers refer to physical PDF pages in M1.')
    widths=[114,188,CW-302]
    condensed = [
        ('Deterministically projects canonical records into chart seeds; full identity stays separate.', 'No consent, authentication, external location measurement or account connection follows.'),
        ('Represents finite cells through log radius, periodic angle and declared quantization.', 'Physical use needs measurements; chart indices and physical units remain distinct.'),
        ('Reflects radial position at angular winding in the required current format.', 'Coordinate identification creates no physical transport, remote access or device coupling.'),
        ('Defines distinct shifts, lineage, JK state, parity and finite word rules.', 'Recurrence is not external replication; parity is not identity or authorization.'),
        ('Applies supplied predicates and ordered ASA/NA rules, including whole-word zeroing.', 'Binary word rules do not establish physical absorption or every scalar geometry.'),
        ('Uses literal atan of the increment ratio and an explicitly supplied axis.', 'Frames, increments and valid statuses remain required; no tracker appears automatically.'),
        ('Quantizes declared candidates while retaining separate identity and lineage records.', 'Shared occupancy cannot identify each record or create sensors and actuators.'),
        ('Commits verified snapshots and links events for conditionally deterministic replay.', 'Replay proves neither authority nor truth; rollback cannot undo physical effects.'),
        ('Preserves logical cells through packed layouts and immutable texture reads.', 'No host privilege, encryption or permanent cache pinning follows from this layout.'),
        ('Simulates finite machine prefixes when definitions, storage and execution budget suffice.', 'No infinite memory, general intelligence, arbitrary termination or binary proof follows.'),
    ]
    headers=['Primitive / source','What the formal object does','Boundary relevant to misuse']
    a.rect(M,y,CW,28,INK)
    x=M
    for label,w in zip(headers,widths):
        a.text(label,x+8,y+7,8.3,'AtlasBold',WHITE)
        x+=w
    y+=28
    for i,item in enumerate(grounding['primitives']):
        texts=[f'<b>{safe(item["name"])}</b><br/>p. {safe(item["pages"])}',safe(condensed[i][0]),safe(condensed[i][1])]
        hs=[Paragraph(t,a.styles['table']).wrap(w-16,H)[1] for t,w in zip(texts,widths)]
        h=max(hs)+13
        a.rect(M,y,CW,h,WHITE if i%2 else PALE)
        x=M
        for t,w in zip(texts,widths):
            a.p(t,x+8,y+8,w-16,'table',y+h-5)
            x+=w
        y+=h
    a.p('<b>Current design requirement:</b> the Klein topology is part of the requested substrate. This atlas does not recast it as an optional feature. Packing and topology change representation and adjacency; any physical application still needs its own justified coupling.',M,y+15,CW,'small')

def legend(a):
    y = a.page('The rainbow and tone legend', 'An original ordinal scale for <b>conditional consequence severity</b>, created for this atlas. It is not an official standard or a probability model.')
    color_names=['Violet','Indigo','Blue','Green','Yellow','Orange','Red']
    for level,note,name,hx,description in BANDS:
        h=65
        a.rect(M,y,6,h-6,colors.HexColor(hx))
        a.p(f'<b>L{level} / {note}</b><br/>{safe(name)}',M+16,y+4,85,'h3',y+h-4)
        a.text(color_names[level-1],M+16,y+37,8.8)
        a.p(safe(description),M+113,y+4,CW-121,'body',y+h-4)
        a.rule(y+h-5)
        y+=h
    y+=9
    y=a.section('How to interpret a flag',
        'A flag rates the scenario as described, assuming its prerequisites. The bands are ordered judgments with overlapping real-world consequences; they are not equal numerical steps. A different scale of deployment can justify a different band. Likelihood is <b>unassessed</b>: there is no actor, exposure or incident dataset here. [R1]',y)
    a.p('<b>Accessibility and meaning:</b> the number, note and name repeat every color. Green means L4 / F / Serious here, not "safe". Notes C-D-E-F-G-A-B are memory aids only, with no acoustic, physiological or resonance prescription. Text labels apply the principle of not relying on color alone. No WCAG or PDF/UA conformance claim is made. [R8]',M,y,CW,'small')

def evidence(a, grounding):
    y=a.page('Evidence and the physical bridge','Use the path flag alongside the harm color. An existing component is not proof that its misuse succeeds.')
    for title,body in [
        ('K  /  Kernel-adjacent', 'A relevant computational component exists in the reviewed package. The stated abuse has not been demonstrated. An actor would still need the specified ability to supply input, replace data or influence publication.'),
        ('A  /  Added application', 'The scenario requires application logic, sensitive data, a communication channel or permission not established by the core. Existing technology elsewhere does not establish this repository\'s access to it.'),
        ('P  /  Physical interface', 'The scenario additionally requires real sensors, effectors or material processes, actual physical coupling and relevant access. This is a dependency label, not a claim that every named physical technology is scientifically speculative. Authorization and validation are safeguards, not prerequisites for causing harm.'),
    ]:
        y=a.panel(title,body,y)
    a.p('THE REQUIRED CAUSAL CHAIN',M,y,CW,'h3')
    y+=24
    labels=['Encoded state','Operational interface','Physical coupling','Real-world effect']
    gap=12; bw=(CW-3*gap)/4
    for i,label in enumerate(labels):
        x=M+i*(bw+gap)
        a.rect(x,y,bw,43,PALE,LINE,5)
        a.p(safe(label),x+8,y+9,bw-16,'small',y+39)
        if i<3: a.text('>',x+bw+3,y+13,10,'AtlasBold',INK)
    y+=58
    y=a.section('U / Grey: an unsupported causal leap',
        'No operational threat level is assigned when the proposed mechanism has no established bridge. Examples include a hash conferring external authority, a Klein seam physically connecting remote locations, or word absorption by itself removing physical energy. Claims of infinite hardware or established neural/weapon access likewise exceed the evidence. Grey means unsupported, not safe. [M1 pp. 8, 10, 18, 31-32, 40]',y)
    a.p('There is no demonstrated atomOS-specific advantage for misuse. Speed or compactness might change the scale of a real application, but that would require comparative measurements and a deployment analysis.',M,y,CW,'small')

def index(a,groups,first):
    items=[(g,s) for g in groups for s in g['scenarios']][first:first+20]
    y=a.page(f'Scenario index / {1 if first==0 else 2}', 'Scan the consequence flag first, then check the required path. K = kernel-adjacent; A = added application; P = physical interface.')
    a.rect(M,y,CW,28,INK)
    for label,x in [('ID / scenario',M+8),('Level / note',M+337),('Path',M+412),('Page',M+466)]:
        a.text(label,x,y+7,8.5,'AtlasBold',WHITE)
    y+=28
    for j,(g,s) in enumerate(items):
        h=26
        a.rect(M,y,CW,h,PALE if j%2==0 else WHITE)
        a.p(f'<b>{s["id"]}</b>  {safe(s["title"])}',M+8,y+6,326,'table',y+24)
        a.flag(s['level'],M+337,y+5,True)
        a.text(s['path'],M+412,y+6,9.0,'AtlasBold',INK)
        page=8+(int(s['id'][1:])-1)//4
        a.text(str(page),M+474,y+6,9,'AtlasBold',INK)
        a.c.linkRect('',f'domain{(int(s["id"][1:])-1)//4+1}',(M,H-y-h,W-M,H-y),relative=0,thickness=0)
        y+=h
    a.panel('A severe color is not a current capability finding',
        'Orange and red entries depend on independently capable external systems. Their inclusion anticipates governance needs if such systems are ever connected. No current connection or malicious activity is inferred from the formalization.',y+18,style='small')

def domains(a,groups):
    for i,g in enumerate(groups):
        y=a.page(g['title'],safe(g['intro']),f'domain{i+1}')
        top=y
        available=777-top
        cardh=(available-30)/4
        for j,s in enumerate(g['scenarios']):
            y=top+j*(cardh+10)
            bottom=y+cardh
            a.rect(M,y,CW,cardh,PALE,radius=6)
            hx=BANDS[s['level']-1][3]
            a.rect(M,y,4,cardh,colors.HexColor(hx))
            title_bottom=a.p(f'{s["id"]}  {safe(s["title"])}',M+13,y+10,CW-176,'h3',y+39)
            a.flag(s['level'],M+CW-153,y+10)
            cy=max(y+33,title_bottom+8)
            for label,key in [('Path and harm','prerequisite_harm'),('Warning sign','warning'),('Safeguard','safeguard')]:
                cy=a.p(f'<b>{label}:</b> {safe(s[key])}',M+13,cy,CW-26,'card',bottom-18)+3
            source='Path '+s['path']+'  |  '+safe(s['source'])
            a.p(source,M+13,bottom-15,CW-26,'small',bottom-2)

def controls(a):
    y=a.page('Controls: present and still needed', 'Controls below address different failure modes. None converts a harmful objective into an acceptable one.')
    sections=[
        ('Present in the reviewed workflow [K1, K2]',
         '<b>Finite admission and replay:</b> accepted teacher procedures must satisfy the original finite oracle; equivalence checks prevent duplicate function pages. Malformed or incorrect replies remain rejected evidence.<br/><br/>'
         '<b>Data and publication discipline:</b> immutable source bindings, native result verification and rejection before replacing active state protect the stated pipeline. They do not establish a general attacker-resistant trust root.<br/><br/>'
         '<b>Explicit scope:</b> unsupported queries return unknown, and documented cache measurements retain their launch-level qualification.'),
        ('Recommended at the program-bank boundary',
         'Separate the authority defining a task and its expected results from the proposer. Authenticate publishers and authorized version changes; a content hash alone is insufficient. Retain provenance, rejected evidence and rollback records. Bound parsing, compute and memory use. Review who can publish, read logs and export bank contents. These are recommendations, not newly implemented features.'),
        ('Recommended before people or devices depend on it',
         'Document the intended use, data rights and withdrawal process. Validate each empirical rule in its operating domain. Use application-specific privacy, fairness and security evaluation. Any physical integration needs independently enforced device limits, a tested stop/recovery route and qualified review of the actual plant. Consent cannot be inferred from a seed or state transition. [R1-R7]'),
    ]
    for title,body in sections: y=a.panel(title,body,y)
    a.p('<b>Evidence categories stay distinct:</b> mathematical proof, source-code tests, native execution, hardware measurements, physical validation and authorization answer different questions. This report adds analysis and document checks; it performs no new kernel or device experiment.',M,y,CW,'small')

def worked(a):
    y=a.page('Three worked assessments', 'Start with controllable interfaces and evidence. Do not prioritize solely by the brightest color.')
    y=a.panel('T03 / L4-F-Serious / K: a substituted bank',
        '<b>Assumption:</b> an actor can replace a proposed bank or its manifest. <b>Potential result:</b> an application accepts an unauthorized finite function. <b>Evidence:</b> banks and publication checks exist; successful malicious substitution has not been shown. <b>Priority:</b> review the real bank write and approval paths now. Independent oracles and verified commit steps reduce some errors; authenticated publisher authority remains a separate question.',y)
    y=a.panel('T30 / L6-A-Critical / P: neural modulation',
        '<b>Assumption:</b> a separately developed neural interface has the physical capacity for fatal or multiple serious injuries and accepts commands. <b>Potential result:</b> unsafe output causes that critical harm. <b>Evidence:</b> no such interface is established here. <b>Priority:</b> keep this as a conditional integration gate. Responsible deployment would need device-specific validation, withdrawable consent and independent limits. [M1 p. 40; R4]',y)
    y=a.panel('U / Grey: a seed grants remote physical access',
        '<b>Claim:</b> knowing a SHA256 seed or chart coordinate directly controls an external person, device or location. <b>Missing bridge:</b> an effective interface, actual access and a supported physical mechanism. <b>Assessment:</b> the mathematics does not establish this claim. Do not turn it into a red-rated operational capability by repeating it. If a real adapter is later supplied, assess that adapter and its permissions as a new scenario. [M1 pp. 8-10, 40]',y)
    a.section('A practical order of work',
        'First identify who can change banks, specifications and evidence. Next assess the actual application inputs, outputs and sensitive data. Then assess any real-world connector. Rank work by exposure, consequence and strength of evidence; record uncertainty instead of inventing probabilities. [R1]',y)

def worksheet(a):
    y=a.page('How to expand the atlas', 'A reusable assessment record for each new application. This catalogue is broad, but cannot enumerate every future combination or adversary.')
    fields=[
        ('1. Asset and legitimate purpose','What must remain correct, private, available, voluntary or physically safe? Who benefits, and who can be harmed?'),
        ('2. Actor and actual access','Which input, publisher, device or decision can the actor influence? Is that access observed, assumed or absent?'),
        ('3. Causal path','Name the primitive, adapter and external capability needed. Mark unsupported steps U instead of filling them with analogy.'),
        ('4. Consequence and uncertainty','Assign L1-L7 to the stated consequence. Record K/A/P separately. State exposure and likelihood evidence, or explicitly leave likelihood unassessed.'),
        ('5. Warning and safeguard','Choose an observable warning, responsible owner, independent control, recovery path and evidence required before release.'),
        ('6. Reassessment trigger','Revisit after adding data, permissions, physical outputs, bank size, autonomous actions or a new deployment population.'),
    ]
    for title,body in fields:
        y=a.section(title,body,y)
    y=a.panel('Where version 1 stops',
        'The assessment covers common trust, privacy, compute, knowledge, XR, neural, biophysical, industrial and institutional pathways. It is not an adversarial penetration test, physical experiment, incident investigation, legal certification or proof of safety. Interactions between domains can create additional scenarios. New evidence can lower, raise or remove an assigned band.',y,style='small')
    a.p('Coverage is qualitative and purpose-based. The flags represent original analyst judgments, not reported NIST, UNESCO, WHO or W3C ratings. No weapon, cyberattack, biochemical or neural intervention instructions are included.',M,y,CW,'small')

def local_sources(a,manifest,grounding):
    y=a.page('Local sources and attribution', 'Repository evidence reviewed for this report. Local references identify evidence, not instructions or claims of external authority.')
    y=a.section('M1 / Main formalization',
        '<b>atomOS_v3.6_Total_Integrated_Engine_Tom_Klootwijk.pdf</b><br/>'
        'Tom Klootwijk. 43 physical PDF pages. Page references throughout this report use physical page numbers, regardless of printed headings. The strongest interface boundary appears on p. 40. Selected relevant pages and the source audit were reviewed; this is not a claim of exhaustive review of every parent-repository PDF.',y)
    y=a.p('SHA256: '+grounding['primary']['sha256'],M,y,CW,'small')+19
    y=a.section('K1 / Kernel contract, source audit and claims',
        'Within the CUDA Verification package: <b>README.md</b>, <b>docs/CONTRACT.md</b>, <b>docs/coverage.csv</b>, <b>proofs/CLAIMS.md</b> and <b>docs/SOURCE_OPERATOR_SDF_AUDIT.md</b>. These distinguish declared formal operations, completed adapters and native evidence. Source-word SDF mappings are not evidence for every proposed scalar physical field.',y)
    y=a.section('K2 / Current knowledge bank and execution record',
        '<b>docs/TEACHER_EXPRESSION_QUERIES.md</b>, <b>docs/TEACHER_REPAIR_AND_TEMPLATE_AUDIT.md</b> and <b>docs/KNOWLEDGE_EXTRACTION_ARCHITECTURE.md</b>. These document the seven-page bank, finite teacher-derived procedures, novelty filtering, actual measured texture scope and unfinished general-language goal.',y)
    y=a.section('K3 / Application hypotheses',
        '<b>docs/ENTERTAINMENT_POSSIBILITY_SPACES.md</b> supplies previously discussed entertainment and spatial/physical directions. It is possibility-space context, not empirical evidence that the interfaces or claimed effects exist.',y)
    y=a.panel('Authorship and reproducibility',
        'Tom Klootwijk retains concept attribution for the formalization and required seeded log-polar/Klein SDF texture direction. This threat taxonomy, rainbow/tone rubric, prose and PDF layout are AI-assisted analysis prepared for this request. External organizations retain attribution for their publications. The companion folder contains editable scenario data, references, source hashes, builder and validation receipt.',y,style='small')
    a.p('Evidence baseline commit: '+manifest['evidence_baseline_commit']+'<br/>Assessment date: '+DATE+'. No kernel implementation or proof status was changed for this document.',M,y,CW,'small')

def external_sources(a,refs,offset):
    y=a.page(f'Primary references / {1 if offset==0 else 2}', 'Primary-source guidance informs the controls and evidence discipline. The scenario ratings and musical scale remain original to this report.')
    for r in refs[offset:offset+4]:
        link=escape(r['url'],quote=True)
        y=a.p(f'<b>{r["id"]} / {safe(r["title"])}</b>',M,y,CW,'h2')+6
        y=a.p(safe(r['date'])+'  |  '+safe(r['status']),M,y,CW,'small')+8
        y=a.p('<b>Used for:</b> '+safe(r['support'])+'<br/><b>Limit:</b> '+safe(r['limit']),M,y,CW,'body')+7
        y=a.p(f'<link href="{link}" color="#1B6393"><u>Open the primary publication</u></link>',M,y,CW,'small')+15
        a.rule(y)
        y+=12
    a.p('Sources checked 14 September 2026. Dates describe the cited editions or adoption, not a claim that this document is a standards audit. For deployment decisions, reassess the actual system and current applicable requirements.',M,y+3,CW,'small')

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    data=read_json('scenarios.json')
    grounding=read_json('grounding.json')
    refs=read_json('references.json')['references']
    groups=data['groups']
    scenarios=[s for g in groups for s in g['scenarios']]
    assert len(groups)==10 and all(len(g['scenarios'])==4 for g in groups)
    assert [s['id'] for s in scenarios]==[f'T{i:02}' for i in range(1,41)]
    assert [r['id'] for r in refs]==[f'R{i}' for i in range(1,9)]
    assert len(grounding['primitives'])==10
    for s in scenarios:
        assert 1 <= s['level'] <= 7
        assert all(p in ('K','A','P') for p in s['path'].split('/'))
        assert len(s['title'])<=48
    source_paths=[ROOT / grounding['primary']['filename']]
    source_paths += [PACKAGE / p for p in [
        'README.md','docs/CONTRACT.md','docs/coverage.csv','proofs/CLAIMS.md',
        'docs/SOURCE_OPERATOR_SDF_AUDIT.md','docs/TEACHER_EXPRESSION_QUERIES.md',
        'docs/TEACHER_REPAIR_AND_TEMPLATE_AUDIT.md','docs/KNOWLEDGE_EXTRACTION_ARCHITECTURE.md',
        'docs/ENTERTAINMENT_POSSIBILITY_SPACES.md']]
    manifest_path=HERE/'source_manifest.json'
    if manifest_path.exists():
        manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        for source in manifest['sources']:
            if digest(ROOT/source['path']) != source['sha256']:
                raise ValueError('Source changed since recorded evidence baseline: '+source['path'])
    else:
        manifest={
            'date':'2026-09-14',
            'evidence_baseline_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'sources':[{'path':p.relative_to(ROOT).as_posix(),'sha256':digest(p),'bytes':p.stat().st_size} for p in source_paths],
            'attribution':{'formalization':'Tom Klootwijk','analysis_and_scale':'AI-assisted synthesis for Tom Klootwijk; original threat rubric, not a mathematical proof'},
            'review_scope':'Selected relevant primary pages and named kernel records; no comprehensive historical-PDF or security audit claimed.'
        }
        manifest_path.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    assert manifest['sources'][0]['sha256']==grounding['primary']['sha256']
    a=Atlas()
    cover(a); scope(a); primitives(a,grounding); legend(a); evidence(a,grounding)
    index(a,groups,0); index(a,groups,20); domains(a,groups)
    controls(a); worked(a); worksheet(a); local_sources(a,manifest,grounding)
    external_sources(a,refs,0); external_sources(a,refs,4)
    a.finish()
    pdf=PdfReader(OUTPUT)
    texts=[p.extract_text() for p in pdf.pages]
    assert len(texts)==23
    for i,g in enumerate(groups):
        for s in g['scenarios']:
            assert s['id'] in texts[7+i]
            assert s['prerequisite_harm'].split()[0] in texts[7+i]
    for i in range(1,8): assert f'L{i} /' in texts[3]
    assert all('\ufffd' not in t and '\u25a0' not in t for t in texts)
    for i in range(1,9): assert f'R{i} /' in ''.join(texts[-2:])
    links=sum(len(p.get('/Annots',[])) for p in pdf.pages)
    assert links>=48
    receipt={
        'output':OUTPUT.name,'sha256':digest(OUTPUT),'bytes':OUTPUT.stat().st_size,
        'pages':len(pdf.pages),'scenario_count':len(scenarios),'bands':len(BANDS),
        'checks':{'ordered_ids':True,'page_mapping':True,'text_overflow_guard':True,'required_labels':True,'source_hashes':True,'links_count':links},
        'visual_review':'pending final Poppler render inspection',
        'kernel_tests':'not_run - documentation-only task; no kernel changes',
        'implementation_change':'none',
        'new_empirical_threat_validation':'none; conditional threat analysis'
    }
    (HERE/'validation_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(receipt,indent=2))

if __name__=='__main__': main()
