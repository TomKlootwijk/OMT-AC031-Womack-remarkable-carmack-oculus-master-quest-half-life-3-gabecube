#!/usr/bin/env python3
"""Compare the same R18 word program with wide and bounded phase expressions."""
from pathlib import Path
import argparse,datetime,hashlib,json,statistics,subprocess
ROOT=Path(__file__).resolve().parents[1]
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--narrow',required=True,type=Path);p.add_argument('--wide',required=True,type=Path)
    p.add_argument('--repeats',type=int,default=5);p.add_argument('--smoke',action='store_true');a=p.parse_args()
    if a.repeats<1:raise ValueError('Positive repeat count required')
    executables={'narrow':a.narrow.resolve(),'wide':a.wide.resolve()}
    lanes=4096 if a.smoke else 65536
    recipes=[('phase_sum',ROOT/'examples/phase18/phase_sum.tmg',256),('seam_turn',ROOT/'examples/phase18/seam_turn.tmg',256),('mixed48m',ROOT/'review/workloads/mixed_1048576.tmg',128)]
    cases=[]
    for name,program,steps in recipes:
        for feedback in ('none','copy32'):
            for dispatch in ('reference','fused'):
                variants=[(build,fetch) for build in ('wide','narrow') for fetch in ('texture','global')]
                trials={b+'_'+f:[] for b,f in variants}
                for repeat in range(a.repeats):
                    order=variants[repeat%4:]+variants[:repeat%4]
                    if repeat%2:order=order[::-1]
                    for build,fetch in order:
                        cmd=[str(executables[build]),'--program',str(program),'--lanes',str(lanes),'--steps',str(steps),'--fetch',fetch,'--feedback',feedback,'--dispatch',dispatch,'--chunk','32','--lane-init','spread']
                        r=json.loads(subprocess.run(cmd,capture_output=True,text=True,check=True).stdout)
                        if r['status']!='completed' or r['vm_fault_lanes'] or r['feedback_fault_lanes']:raise ValueError('Faulted phase workload')
                        expected='R17 signed-wide reference' if build=='wide' else 'exact bounded 32-bit phase and seam'
                        if r['phase_lowering']!=expected:raise ValueError('Wrong executable phase build')
                        trials[build+'_'+fetch].append(r)
                if len({r['hash64'] for runs in trials.values() for r in runs})!=1:raise ValueError('Complete final digest mismatch')
                if len({json.dumps(r['first_lane'],sort_keys=True) for runs in trials.values() for r in runs})!=1:raise ValueError('First-lane fields differ')
                med={k:{t:statistics.median(r['timings_ms'][t] for r in runs) for t in runs[0]['timings_ms']} for k,runs in trials.items()}
                ratios={f:{t:med['wide_'+f][t]/med['narrow_'+f][t] for t in ('batch_device','batch_wall','host_complete')} for f in ('texture','global')}
                case=dict(program=name,program_sha256=digest(program),lanes=lanes,steps=steps,feedback=feedback,dispatch=dispatch,lane_init='spread',medians_ms=med,wide_over_narrow=ratios,matching_full_array_hash64_and_exact_first_lane=True,trials=trials)
                cases.append(case);print(json.dumps({k:case[k] for k in ('program','feedback','dispatch','wide_over_narrow')}),flush=True)
    report=dict(profile='ATOMOS-PHASE-COMPARISON-R1',captured_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),executables={k:dict(path=str(v),sha256=digest(v)) for k,v in executables.items()},repeats=a.repeats,chunk=32,order='Rotated and alternately reversed; fresh process per trial; no warmup; GPU jobs serialized',scope='Final-only equal-output comparison. Different from ordered journal output costs. FNV-1a-64 is noncryptographic; independent field checks are separate.',cases=cases)
    target=ROOT/'review'/('r18_phase_smoke.json' if a.smoke else 'r18_phase_runs.json')
    target.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()
