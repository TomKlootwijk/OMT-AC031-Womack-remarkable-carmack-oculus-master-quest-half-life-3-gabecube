from pathlib import Path
p=Path(__file__).resolve().parents[1]/'atomOS_3_6_1_7_COUPLED/docs/satnav.tex'
s=p.read_text(encoding='utf-8')
s=s.replace('the prior aTOMos release archive','the original aTOMos 3.6.1 archive')
s=s.replace(r'\section{Paired supports and the canonical UGTS event}',r'''\section{Paired supports and the canonical UGTS event}
This section records the retained observation-only adapter, selected with
\code{--legacy-hold}. The default coupled handoff is specified in
Section~\ref{sec:coupled}; it retains residual diagnostics without using this
earlier admission rule to override its equations.
''')
s=s.replace(r'\subsection{Metre-domain guard in the event adapter}',r'\subsection{Metre-domain guard in the legacy event adapter}')
s=s.replace('The Python reference and adapters use the standard library. No PyTorch or external model service\nis required for this kernel.', 'The retained SATNAV reference uses the Python standard library. The coupled\nreference additionally requires NumPy, installed from \code{requirements.txt}.')
s=s.replace(r'\textbf{aTOMos v3.6.1.7 --- Literal self-referential kernel}',r'\textbf{aTOMos v3.6.1.7 --- Coupled geometry and physical state}')
p.write_text(s,encoding='utf-8')
print('Final source/baseline labels updated')
