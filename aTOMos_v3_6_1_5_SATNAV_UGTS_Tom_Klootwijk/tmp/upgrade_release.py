from pathlib import Path
import json

root=Path(__file__).resolve().parents[1]/'atomOS_3_6_1_6_SELFREF'
p=root/'docs/satnav.tex'
s=p.read_text(encoding='utf-8')
s=s.replace('3.6.1.5','3.6.1.6')
s=s.replace('UGTS Satnav Kernel','Literal Self-Referential Kernel and UGTS Satnav')
s=s.replace('UGTS SATNAV KERNEL / SATNAV-R1','LITERAL SELF-REFERENCE / SRK-R1')
s=s.replace('AC031 / AC130 ATOMOS \\hfill SATNAV-R1','AC031 / AC130 ATOMOS \\hfill SRK-R1 + SATNAV-R1')
s=s.replace('\\fontsize{31}{37}\\selectfont UGTS satnav kernel','\\fontsize{28}{34}\\selectfont Literal self-referential kernel')
s=s.replace('Passive GNSS positioning\\par\nwith a source-linked geometric substrate','ASA/NA + J--K state feedback\\par\nwith editable equation inputs')
s=s.replace('Corrected-code observations \\;\\textperiodcentered\\; FP64 QR\\par\nUGTS event sequence \\;\\textperiodcentered\\; Exact 64-bit keys','Explicit recurrence \\;\\textperiodcentered\\; Exact Boolean algebra\\par\nCPU / CUDA execution \\;\\textperiodcentered\\; Independent replay')
s=s.replace('\\textbf{One specialized engine}\\par\nObservation support and whole-word ASA selection; iterative receiver position and\nclock-bias estimation; local ENU/log-polar diagnostics; exact source key codecs;\nUGTS support, compatibility, guard, event, transition and lineage.', '\\textbf{An executable state-feedback subversion}\\par\nLiteral ASA/NA and J--K equations now form a persistent recurrence. Editable\nexpressions compile to exact truth tables; every intermediate state is replayed\nindependently. The SATNAV and UGTS numerical profiles remain included.')
s=s.replace('This release specializes the user\'s \\textbf{aTOMos 3.6.1} engine for a concrete satnav\nworkload: \\textbf{batched passive GNSS code-positioning from prepared observations}.\nIt imports the supplied UGTS SCLP geometry, key and event contracts without claiming\nthat SCLP already contained a pseudorange receiver model.', 'This subversion completes the literal ASA/NA and J--K primitives with explicit\nstate feedback, supplied Boolean equations and independent replay. The new\n\\textbf{SRK-R1} profile is formally specified in Section~\\ref{sec:selfref}.\nIt also retains the 3.6.1.5 SATNAV-R1 corrected-code and UGTS implementations.')
s=s.replace('Specialization version & \\textbf{3.6.1.6}, as requested; profile \\textbf{SATNAV-R1}.','Subversion & \\textbf{3.6.1.6}; profiles \\textbf{SRK-R1} and \\textbf{SATNAV-R1}.')
s=s.replace('Kernel delivered & Native CUDA source with texture and global-read paths; C++17 CPU path.', 'Kernel delivered & Literal word-feedback recurrence plus retained FP64 satnav; CPU and CUDA source.')
s=s.replace('Executed here & CPU build/tests, independent Python comparisons, CPU sanitizer checks and local adapter examples.', 'Execution record & Current subversion results appear in the SRK-R1 validation section; previous release evidence is retained separately.')
s=s.replace('On-device status & CUDA compile and GPU execution \\code{not\\_run}: no nvcc or NVIDIA GPU was available in preparation.', 'On-device status & Recorded from the actual local device in this subversion; see the current validation record.')
s=s.replace('The archive contains a buildable source target, not a prevalidated cubin or Windows\nexecutable. Its laptop review script compiles the actual CUDA target, probes the device,\ncompares both input paths against CPU/Python, and records the resulting evidence.\nA successful CPU run is not reported as a GPU run.', 'Buildable source and reproducible commands are included. The native recurrence\nrecords every state transition. The satnav laptop review script compares both\ninput paths with CPU/Python and records Compute Sanitizer evidence.')
s=s.replace("The supplied PDF's equations and catalog were read directly. \\src{pp.\\,1--16}", "The earlier release records direct reading of U; this subversion inherits its\ntranscribed equations and provenance. The original U and OTAN2 PDFs are not mounted\nhere. \\src{pp.\\,1--16}")
s=s.replace('\\tableofcontents\n\\clearpage','\\tableofcontents\n\\clearpage\n\\input{self_reference.tex}',1)
start=s.index('\\subsection{No new J/K feedback hidden in the adapter}')
end=s.index('\\clearpage',start)
s=s[:start]+r'''\subsection{Literal J/K and the explicit feedback profile}
The retained equation is
\begin{equation}
q^+=(J\land\neg q)\lor(\neg K\land q).
\end{equation}
SRK-R1 binds J and K to supplied expressions that read the old state and literal
ASA output, then carries $q^+$ into the next step. The full recurrence, expression
input and execution semantics are given in Section~\ref{sec:selfref}.

The SATNAV-R1 observation adapter retains its explicit hold event $J=K=0$ as a
compatibility profile. This choice does not restrict the separate SRK-R1 equation
inputs. The original encoded circle-plus blend and predicate encoders are still
not supplied in the mounted source, so the new feedback bindings are identified
as new definitions rather than reconstructed earlier encoders.
'''+s[end:]
s=s.replace('\\section{The deterministic worked satnav batch}', '\\section{The retained deterministic satnav batch}')
s=s.replace('\\section{Verification completed and pending}', '\\section{Prior release verification record}\nThis section retains the 3.6.1.5 preparation record. Current 3.6.1.6 execution\nevidence is given in the SRK-R1 validation section. The following unexecuted\nCUDA statements refer to the prior preparation environment only.\n')
s=s.replace('Source-grounded specialization, executable CPU and CUDA source, independent reference,\nfinite tests and a defined UGTS observation handoff. Prepared with AI assistance.', 'Literal self-reference with editable equations, CPU/CUDA source, independent replay,\nand the retained SATNAV/UGTS formalization. Prepared with AI assistance.')
s=s.replace('\\textbf{Profile:} SATNAV-R1.', '\\textbf{Profiles:} SRK-R1 and SATNAV-R1.')
p.write_text(s,encoding='utf-8')
for name in ['src/main.cpp','include/satnav_core.hpp','VERSION.json','profiles/SATNAV_R1.json','CITATION.cff','docs/CONTRACT.md']:
    p=root/name
    p.write_text(p.read_text(encoding='utf-8').replace('3.6.1.5','3.6.1.6'),encoding='utf-8')
p=root/'VERSION.json'; d=json.loads(p.read_text());d.update(parent_version='3.6.1.5',profile='SRK-R1',included_profiles=['SRK-R1','SATNAV-R1']);p.write_text(json.dumps(d,indent=2)+'\n')
p=root/'AUTHORSHIP.json';d=json.loads(p.read_text());d['preparation']='AI-assisted explicit ASA/NA + JK feedback formalization and native/reference implementation';p.write_text(json.dumps(d,indent=2)+'\n')
p=root/'source/manifest.json';d=json.loads(p.read_text());d['subversion']={'version':'3.6.1.6','parent':'3.6.1.5','source_basis':'Mounted parent package code and editable LaTeX; user authorized ASA/NA + JK with explicit state feedback','new_definitions':['SRK-R1 feedback composition','Boolean expression grammar and exact truth-table compilation','state projection to present mask','independent trajectory execution'],'original_pdfs_mounted_in_this_run':False};p.write_text(json.dumps(d,indent=2)+'\n')
p=root/'CHANGELOG.md';p.write_text('# 3.6.1.6 - SRK-R1 literal self-reference\n\nAdds synchronous persistent ASA/NA + JK state feedback, editable Boolean equation\ninputs, exact truth-table compilation, CPU/CUDA trajectory execution, complete\ntraces and an independent expression-tree reference. Fixed points and cycles are\nreported distinctly. Retains the original SATNAV/UGTS profiles and both key layouts.\nThe combined PDF is rebuilt from editable LaTeX with equations and current validation.\nPrevious 3.6.1.5 package is preserved beside this subversion.\n\n'+p.read_text(encoding='utf-8'),encoding='utf-8')
