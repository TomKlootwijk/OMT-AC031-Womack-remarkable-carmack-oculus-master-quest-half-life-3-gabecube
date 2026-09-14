from pathlib import Path
root=Path(__file__).resolve().parents[1]/'atomOS_3_6_1_7_COUPLED'
def change(name,old,new):
    p=root/name
    text=p.read_text(encoding='utf-8')
    assert old in text,(name,old)
    p.write_text(text.replace(old,new),encoding='utf-8')
change('docs/validation_current.tex','indexes current evidence','indexes the archived baseline evidence')
change('docs/validation_current.tex','Windows CPU and CUDA executables are included under','The baseline delivered Windows CPU and CUDA executables under')
change('docs/self_reference.tex',"Its observation adapter's\nhold event remains that profile's explicit choice. SRK-R1 is the new formal word", "The earlier observation adapter's\nhold event is retained by the explicit legacy option. SRK-R1 is the retained formal word")
change('docs/satnav.tex','This section retains the 3.6.1.5 preparation record. Current 3.6.1.6 execution\nevidence is given in the SRK-R1 validation section.', 'This section retains the 3.6.1.5 preparation record. Archived 3.6.1.6 evidence\nis given in the SRK-R1 validation section; current 3.6.1.7 checks appear in the\ncoupled implementation validation section.')
change('docs/satnav.tex','On the laptop it becomes the required next validation step,\nnot a placeholder success.', 'Later releases supply separate actual laptop execution records.')
change('docs/satnav.tex','The geometry-support adapter then emits 251 computationally verified candidate', 'The earlier observation-only geometry-support adapter emits 251 verified candidate')
change('docs/satnav.tex','the outlier remains unresolved because the chosen residual criteria are exceeded.','the outlier remains unresolved because the chosen residual criteria are exceeded.\nCGK-R1 instead advances 253 observation-driven and three prediction-only states;\nresidual classifications remain diagnostics beside the original solutions.')
change('docs/satnav.tex',r'\section{Ordered event records and source lineage}',r'\section{Ordered coupled records and source lineage}')
p=root/'docs/satnav.tex'
s=p.read_text(encoding='utf-8')
start=s.index('A UGTS event binds the solved candidate')
end=s.index('The chain uses a domain-tagged',start)
s=s[:start]+r'''A CGK-R1 event binds the original solution and residuals, modeled position and
velocity, executed J/K transition, complete native trace row, both compact keys,
full time and prior digest. A condensed structural sketch is:

\begin{lstlisting}
{
  "version": "3.6.1.7", "profile": "CGK-R1",
  "trajectory_id": 0, "epoch_id": 0, "input_index": 0,
  "event": "COUPLED_OBSERVATION_ADVANCED",
  "observation": {"solver_record": {}, "epoch_record": {},
    "residual_records": [], "formal_variance_m2": {}},
  "modeled": {"enu_m": [], "ecef_m": [],
    "velocity_enu_m_s": [], "q": 0, "hoop_phi_rad": 0},
  "jk": {"before": 0, "j": 0, "k": 0, "after": 0},
  "native_state": {"complete executed trace row": "..."},
  "chart": {"up_m": 0, "time_gpst_s": 0, "winding": 0},
  "packing": {"contiguous_hex": "...", "morton_hex": "..."},
  "lineage": {"sources": {}, "native": {}},
  "previous_hash": "...", "record_hash": "..."
}
\end{lstlisting}
This is a structural sketch; the delivered exports contain full numeric arrays,
source records, statuses and hashes. Unavailable observations produce explicit
prediction events; a failed mechanical advance produces a failure event. The
modeled state is never presented as the original receiver measurement.

''' + s[end:]
p.write_text(s,encoding='utf-8')
change('docs/coupled.tex','The default example is','The default handoff profile uses')
change('docs/coupled.tex','and orthonormal eigenvectors, retaining $D$, $K$, eigenvectors and a residual.',r'''and orthonormal eigenvectors, retaining $D$, $K$, eigenvectors and a residual.
Upper-triangle construction is mirrored to maintain exact floating-point symmetry.
The native Jacobi solver scales by the largest matrix entry and uses a pair-relative
$2\times10^{-15}$ off-diagonal criterion with at most 64 rotations, preserving
small independent modes in matrices with widely separated stiffness scales.''')
print('Updated coupled document and baseline labels')
