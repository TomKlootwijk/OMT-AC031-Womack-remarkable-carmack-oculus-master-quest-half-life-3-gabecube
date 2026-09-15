#!/usr/bin/env python3
"""Measure exact fused chunks against the retained dispatch-per-step baseline."""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import statistics
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--executable',required=True,type=Path)
    p.add_argument('--baseline-executable',type=Path)
    p.add_argument('--repeats',type=int,default=3)
    p.add_argument('--smoke',action='store_true')
    args=p.parse_args()
    if not 1<=args.repeats<=15:p.error('repeats must be1..15')
    exe=args.executable.resolve()
    workloads=[('tiny',ROOT/'examples/wqk_feedback.tmg','identical',96,n,f)
               for n in ((4096,) if args.smoke else (1,4096,262144)) for f in ('none','copy32')]
    workloads += [('mixed48m',ROOT/'review/workloads/mixed_1048576.tmg','spread',128,
                   4096 if args.smoke else 65536,f) for f in ('none','copy32')]
    variants=[(d,t) for d in ('reference','fused') for t in ('texture','global')]
    cases=[]
    for name,program,lane_init,steps,lanes,feedback in workloads:
        assert program.is_file(),'Run tools/build_mixed_workload.py first'
        case_variants=variants+([('r16','texture'),('r16','global')] if name=='tiny' and args.baseline_executable else [])
        trials={d+'_'+t:[] for d,t in case_variants}
        for repeat in range(args.repeats):
            order=case_variants[repeat%len(case_variants):]+case_variants[:repeat%len(case_variants)]
            if repeat%2:order=order[::-1]
            for dispatch,fetch in order:
                selected=args.baseline_executable.resolve() if dispatch=='r16' else exe
                command=[str(selected),'--program',str(program),'--lanes',str(lanes),'--steps',str(steps),
                         '--fetch',fetch,'--feedback',feedback]
                if dispatch!='r16':command+=['--dispatch',dispatch,'--chunk','32','--lane-init',lane_init]
                run=subprocess.run(command,capture_output=True,text=True,check=True)
                result=json.loads(run.stdout)
                if result['status']!='completed' or result['vm_fault_lanes'] or result['feedback_fault_lanes']:
                    raise ValueError('runtime fault')
                if name=='tiny' and feedback=='copy32' and result['total_accepted_feedback_emissions']!=lanes*(steps//2):
                    raise ValueError('unexpected fresh EMIT total')
                trials[dispatch+'_'+fetch].append(result)
        hashes={r['hash64'] for runs in trials.values() for r in runs}
        first={json.dumps(r['first_lane'],sort_keys=True) for runs in trials.values() for r in runs}
        if len(hashes)!=1 or len(first)!=1:raise ValueError('reference/fused/texture/global disagreement')
        medians={k:{t:statistics.median(r['timings_ms'][t] for r in runs) for t in runs[0]['timings_ms']}
                 for k,runs in trials.items()}
        speedups={f:{t:medians['reference_'+f][t]/medians['fused_'+f][t]
                     for t in ('batch_device','batch_wall','host_complete')} for f in ('texture','global')}
        case={'workload':name,'program_sha256':hashlib.sha256(program.read_bytes()).hexdigest(),
              'lanes':lanes,'steps':steps,'feedback':feedback,'lane_init':lane_init,
              'matching_full_array_hash64_and_exact_first_lane':True,
              'medians_ms':medians,'reference_over_fused':speedups,'trials':trials}
        if 'r16_texture' in medians:
            case['r16_over_fused']={f:{t:medians['r16_'+f][t]/medians['fused_'+f][t]
                                      for t in ('batch_device','batch_wall','host_complete')}
                                   for f in ('texture','global')}
        cases.append(case)
        print(json.dumps({k:case[k] for k in ('workload','lanes','feedback','reference_over_fused')}),flush=True)
    report={'profile':'ATOMOS-FUSED-WORD-MEASUREMENT-R1',
            'captured_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'executable_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),
            'repeats':args.repeats,'chunk_steps':32,'separate_process_each_trial':True,
            'r16_baseline_executable_sha256':hashlib.sha256(args.baseline_executable.read_bytes()).hexdigest() if args.baseline_executable else None,
            'order':'rotated variant order; odd repetitions reversed; original R16 executable also included for tiny identical-lane cases when supplied',
            'warmup':'none; cold initialization is included in host_complete',
            'scope':'Exact finite word execution; no S2 operation, cache-hit or memory-saturation claim',
            'comparison':'same source program, lane initialization, steps and output contract in every variant for each case; R17 reference retains instruction-by-instruction launches',
            'equality':'full-array FNV-1a-64 (noncryptographic) plus exact first lane; independent per-word C/scalar tests recorded separately',
            'cases':cases}
    target=ROOT/'review'/('fused_smoke.json' if args.smoke else 'fused_runs.json')
    target.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
