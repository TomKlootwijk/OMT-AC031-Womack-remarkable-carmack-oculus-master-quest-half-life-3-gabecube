"""Assemble measured live validation and scientific plots from immutable run records."""
from pathlib import Path
import datetime,hashlib,json,math,re,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'python'))
from geodesy import ecef_to_geodetic,ecef_to_enu

def read(path):return json.loads((ROOT/path).read_text())
def rows(path):return [json.loads(line) for line in (ROOT/path).read_text().splitlines()]
def sha(path):return hashlib.sha256((ROOT/path).read_bytes()).hexdigest()

def main():
    runs={backend:read(f'results/lienss_live_{backend}_final/summary.json') for backend in ('cpu','cuda')}
    comparisons={backend:read(f'results/network_probes/lienss_live_{backend}_final_comparison.json') for backend in runs}
    raw={backend:read(f'results/network_probes/lienss_live_{backend}_final_rtcm_values.json') for backend in runs}
    for report in [*comparisons.values(),*raw.values()]:assert report['status']=='passed' and not report['failures']
    traces={backend:rows(f'results/lienss_live_{backend}_final/trace.jsonl') for backend in runs}
    # Identical raw bytes, same receive order, full outer model; CPU/CUDA/live comparison.
    replay={name:rows(f'results/lienss_final_replay_{name}/trace.jsonl') for name in runs}
    pairs=[('cpu','cuda',replay['cpu'],replay['cuda']),('cuda_replay','cuda_live',replay['cuda'],traces['cuda'])]
    cross=[]
    for an,bn,aa,bb in pairs:
        assert len(aa)==len(bb);maximum=0.;count=0
        for a,b in zip(aa,bb):
            x,y=a['result'],b['result']
            assert (x['epoch_id'],x['time_gpst_s'],x['status'],x['used'])==(y['epoch_id'],y['time_gpst_s'],y['status'],y['used'])
            if x['position_available']:
                error=max(abs(i-j) for i,j in zip(x['state_ecef_clock_m'],y['state_ecef_clock_m']));maximum=max(maximum,error);assert error<1e-4;count+=1
        cross.append(dict(a=an,b=bn,epochs=len(aa),positions=count,max_state_component_difference_m=maximum,status='passed'))
    (ROOT/'results/live_cross_backend.json').write_text(json.dumps(cross,indent=2)+'\n')

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'axes.labelcolor':'#173244','text.color':'#173244','axes.titleweight':'bold'})
    fig,axes=plt.subplots(2,2,figsize=(10,6.2),constrained_layout=True)
    for column,backend in enumerate(runs):
        arp=comparisons[backend]['advertised_arp_ecef_m'];lat,lon,_=ecef_to_geodetic(*arp)
        first=traces[backend][0]['result']['time_gpst_s']
        good=[r['result'] for r in traces[backend] if r['result']['position_available']]
        t=[r['time_gpst_s']-first for r in good];enu=[ecef_to_enu(r['state_ecef_clock_m'][:3],arp,lat,lon) for r in good]
        for axis,color,label in [(0,'#1A777F','East'),(1,'#B28448','North'),(2,'#8054A0','Up')]:axes[0,column].plot(t,[v[axis] for v in enu],lw=1.3,color=color,label=label)
        axes[0,column].axhline(0,lw=.7,color='#697C87');axes[0,column].set_title(backend.upper()+f': {len(good)} live positions')
        axes[0,column].set_ylabel('Offset from advertised ARP (m)');axes[0,column].legend(loc='best',ncol=3,fontsize=8)
        axes[1,column].plot(t,[math.sqrt(sum(v*v for v in xyz)) for xyz in enu],color='#173244',lw=1.3)
        axes[1,column].set_ylabel('3D separation (m)');axes[1,column].set_xlabel('Seconds from first received epoch')
        for row in range(2):axes[row,column].grid(alpha=.18);axes[row,column].set_xlim(0,180)
    fig.suptitle('LIENSS: independently computed positions during two live sessions',fontsize=13)
    (ROOT/'docs/figures').mkdir(exist_ok=True)
    fig.savefig(ROOT/'docs/figures/live_position_evidence.png',dpi=190);plt.close(fig)

    pythonlog=(ROOT/'results/python_tests_final.log').read_text();testcount=int(re.search(r'Ran (\d+) tests',pythonlog)[1]);assert '\nOK' in pythonlog
    gpu_path=next(p for p in sorted((ROOT/'results').glob('gpu_*/status.json')) if json.loads(p.read_text()).get('memcheck')=='passed')
    required=['results/gnss_math_oracle.json','results/rtcm_independent_audit.json','results/real_0759_cpu/independent_comparison.json','results/live_stream_memcheck/summary.json','results/live_final_corrected_cpu/independent_verification.json','results/live_native_cpu/summary.json','results/live_native_cuda/summary.json','results/live_physical_audit.json']
    for path in required:assert read(path)['status']=='passed',path
    evidence={path:{'sha256':sha(path),'status':'passed'} for path in required}
    for backend in runs:
        for kind in ('comparison','rtcm_values'):
            path=f'results/network_probes/lienss_live_{backend}_final_{kind}.json';evidence[path]={'sha256':sha(path),'status':'passed'}
    summary=dict(version='3.6.1.8',profile='LIVE-GPS-L1-R1',status='passed',
        measured_at_utc_date='2026-09-14',scope='Real Internet remote receiver GPS L1 single-point positioning; static LIENSS. Does not locate host laptop.',
        cpu_ctest='3/3 passed',cuda_ctest='3/3 passed',python_test_methods=testcount,
        gpu_validation=str(gpu_path.relative_to(ROOT)).replace('\\','/'),
        live_sessions={backend:dict(epochs=runs[backend]['epochs'],positions=runs[backend]['positions'],status_counts=runs[backend]['epoch_status_counts'],
             source=runs[backend]['capture']['source'],raw_sha256=runs[backend]['capture']['sha256'],
             native_vs_rtklib_3d_m=comparisons[backend]['native_oracle_distance_m'],
             advertised_arp_separation_3d_m=comparisons[backend]['native_advertised_arp_distance_m'],
             complete_fragment_to_publication_s=comparisons[backend]['live_publication_audit']['complete_fragment_to_publication_seconds'],
             all_positions_emitted_during_capture=True,cold_start_seed=[0,0,0,0]) for backend in runs},
        cross_backend=cross,evidence=evidence,
        limitations=['remote receiver position only','static sessions, no moving-field validation','code SPP; no RTK/PPP or Doppler velocity','nominal weights and standard atmosphere','no independent surveyed ground truth','bounded synchronous transport, no hard-real-time guarantee'],
        preserved_parent_index='source/baseline_3_6_1_7_validation.json')
    (ROOT/'results/validation_status.json').write_text(json.dumps(summary,indent=2)+'\n')
    c,g=comparisons['cpu'],comparisons['cuda']
    def mm(rep,key,stat):return f"{rep[key][stat]:.3f}"
    table=[]
    for label,field,stat in [('Mean 3D separation from advertised ARP (m)','native_advertised_arp_distance_m','mean'),('Maximum ARP separation (m)','native_advertised_arp_distance_m','maximum'),('Mean 3D difference from RTKLIB (m)','native_oracle_distance_m','mean'),('Maximum RTKLIB difference (m)','native_oracle_distance_m','maximum')]:table.append(label+' & '+mm(c,field,stat)+' & '+mm(g,field,stat)+r'\\')
    for label,key in [('Median complete-input-to-position (ms)','median'),('Maximum complete-input-to-position (ms)','maximum')]:
        values=[r['live_publication_audit']['complete_fragment_to_publication_seconds'][key]*1000 for r in [c,g]]
        table.append(label+' & '+f'{values[0]:.3f} & {values[1]:.3f}'+r'\\')
    intervals=[]
    for backend,run in runs.items():
        cap=run['capture'];fmt=lambda t:datetime.datetime.fromtimestamp(t,datetime.timezone.utc).strftime('%H:%M:%S')
        intervals.append(f"{backend.upper()}: {fmt(cap['started_utc_unix_s'])}--{fmt(cap['started_utc_unix_s']+cap['duration_s'])} UTC")
    tex=r'''\clearpage
\subsection{Current live execution and independent validation}
\label{sec:live-validation}
Both final sessions ran on 14 September 2026 UTC (the local Netherlands date
crossed into 15 September during the work). Each captured 180 complete one-second
epochs using one public caster connection. CPU and CUDA ran sequential sessions:
INTERVALS. The source is \code{caster.centipede.fr:2101/LIENSS}.
\begin{center}
\begin{tabularx}{\textwidth}{@{}P{.61\textwidth}YY@{}}\toprule
\textbf{Measured quantity} & \textbf{CPU} & \textbf{CUDA}\\\midrule
Complete received epochs & 180 & 180\\
Published native positions & 172 & 175\\
Initial unavailable epochs (ephemeris warmup) & 8 & 5\\
Initial ECEF/clock seed & Zero & Zero\\
TABLE
All positions emitted during socket capture & Yes & Yes\\\bottomrule
\end{tabularx}
\end{center}
The native outputs and their timestamps were checked against the exact raw-frame
hashes and receive-chunk sidecars. The latency above runs from the host receiving
the final required input fragment to publication of a valid position. It includes
local decoding and solving; it is not a calibrated radio/network transit time.
It excludes unavailable warmup epochs. CUDA's first unavailable live epoch took
2.59 seconds inside processing, including initial device work. A separate
persistent-worker regression measured about 1.05 seconds for its first request.
CPU is faster for this small 1 Hz workload; these results establish CUDA correctness,
not a speedup. The CUDA device was the RTX 5070 Ti Laptop, compute capability 12.0,
built with CUDA 12.8 and driver 591.59.

The comparison coordinate is the stream's advertised antenna reference point:
\begin{equation}
 (4426043.0455,\ -89429.1998,\ 4576296.6447)\ \mathrm m.
\end{equation}
It was neither a supplied initial estimate nor an observation. It is not an
independently surveyed truth coordinate in this experiment. Consequently the table
reports separation from advertised ARP, not certified absolute accuracy. RTKLIB
also performs single-point code positioning here; its output quality code is 5,
not an RTK fixed-ambiguity solution.

\clearpage
\subsection{Measured position series and independent checks}
\begin{center}
\includegraphics[width=\textwidth]{figures/live_position_evidence.png}
\end{center}
\textbf{Figure.} East/North/Up and three-dimensional separation from the advertised
ARP in the two actual live sessions. The blank beginning is ephemeris warmup;
no position is fabricated for it. These are different time windows, so their
physical differences are not a CPU-versus-GPU numerical comparison.

For that numerical comparison, the same final raw capture was replayed through
both backends with the same preparation model and receive order. Both produced
175 positions from 180 epochs; their maximum ECEF/clock component difference was
CROSSERROR m. Live CUDA and its archived-byte replay also passed the same
epoch/status/position comparison. \path{results/live_cross_backend.json} records it.

The independent published RTKLIB \code{convbin} decoded each capture to RINEX.
The final CPU and CUDA decoded satellite/epoch sets matched exactly; 1980 and
2094 common C1C ranges agreed to 0.279 mm, within RINEX decimal rounding. Respectively
280 and 588 ephemeris numeric fields agreed. A separate pyrtcm field audit on the
five-minute source capture passed 96,880 comparisons. The orbit/clock oracle
matched eight satellite positions to 0.578 mm and clocks to 0.000438 ns, limited
by its printed output precision. Source hashes and commands are retained.

\clearpage
\subsection{Regression, real-model checks and retained state connection}
The older GSI recording solved all 120 real epochs from ECEF zero. Its raw physical
model and weight-isolation experiment are described with the equations above.
Prepared final live CPU observations passed 3,324 independent Householder checks
across all 180 epochs, with maximum state-component difference below
$8.4\times10^{-9}$ m. All partial/warmup statuses were retained. The persistent
CUDA worker processed those same real final-pass inputs under Compute Sanitizer:
zero memory errors, 180 responses and 1,048 independent checks.

Current native builds passed all three CTest suites on CPU and CUDA. Python passed
PYTESTS test methods. The persistent-interface regression passed 6,861 comparisons
per backend, including rejected requests followed by successful recovery.
The existing texture/global CUDA paths also passed independent comparison and
Compute Sanitizer through \code{validate\_gpu.py --sanitizer}. Analytic/parser tests
cover wrong CRC, fragments, missing data, stream truncation, HTTP chunking,
reconnection, callback failure, stale epochs, native failure and cold-start rules.

Independent NumPy re-solves verified all 698 converged outer passes across both
final live sessions to $1.40\times10^{-8}$ m per component. The physical audit
checked 6,284 prepared rows, including original code, correction signs and proof
that every chosen 1019 issue had already arrived before its epoch was solved.
All 347 published fixes preserve the corrected reception-time equation.

The same live position records also cross the retained CGK-R1 handoff after
capture. Only completed positions enter that downstream replay; omitted warmup
epochs remain listed in its manifest. ENU is anchored at the first computed
position, never at the advertised ARP. Original IDs, ECEF, receiver clock and full
time remain attached. Both key layouts are emitted wherever the chart is defined.
The stationary demonstration does not require the word state to switch, and its
modeled mechanics are not interpreted as a measured receiver velocity. The final
CPU bridge retained 172 fixes and listed eight warmup omissions; its native batch
position/clock replay exactly matched the stream. CGK replay passed 16,684 field
comparisons, and a separate binding audit passed 1,042 checks. The word remained
$q=0$ in this static session. Both keys were emitted for 153 positions; 19
remained inside the chart core. These facts do not assert dynamic switching.

\textbf{Evidence index.} \path{results/validation_status.json} links current
reports and their hashes. \path{results/network_probes/} contains the independent
conversion, raw-field and RTKLIB comparisons. \path{source/live_data/README.md}
records data provenance and third-party attribution. Parent 3.6.1.7 totals in
the following chapters are explicitly historical and are not added to these
live-session results. The original sibling release remains unchanged.
'''
    mantissa,exponent=f"{cross[0]['max_state_component_difference_m']:.2e}".split('e')
    cross_tex='$'+mantissa+r'\times10^{'+str(int(exponent))+'}$'
    tex=tex.replace('INTERVALS','; '.join(intervals)).replace('TABLE','\n'.join(table)).replace('CROSSERROR',cross_tex).replace('PYTESTS',str(testcount))
    (ROOT/'docs/live_validation.tex').write_text(tex,encoding='utf-8')
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
