#!/usr/bin/env python3
"""Measure cache reuse and L2 policy effects; no cache-line pinning is claimed."""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from python.reference import verify_directory
from scripts.benchmark_cache import profiler_number
from scripts.integration import verify_execution_metadata

PASSES = 'profiler__replayer_passes'
TEX_PREFIX = 'l1tex__t_sectors_pipe_tex_mem_texture_op_ld'
L2_PREFIX = 'lts__t_sectors_srcunit_tex_op_read'
GROUPS = {
    'texture_l1': {'kernel':'asa_texture_kernel','metrics':(
        TEX_PREFIX+'_lookup_hit.sum',TEX_PREFIX+'_lookup_miss.sum')},
    'texture_l2_hit': {'kernel':'asa_texture_kernel','metrics':(L2_PREFIX+'_lookup_hit.sum',)},
    'texture_l2_miss': {'kernel':'asa_texture_kernel','metrics':(L2_PREFIX+'_lookup_miss.sum',)},
    'texture_l2_priority': {'kernel':'asa_texture_kernel','metrics':(L2_PREFIX+'_evict_last.sum',)},
    'global_l2_hit': {'kernel':'asa_global_kernel','metrics':(L2_PREFIX+'_lookup_hit.sum',)},
    'global_l2_miss': {'kernel':'asa_global_kernel','metrics':(L2_PREFIX+'_lookup_miss.sum',)},
    'global_l2_priority': {'kernel':'asa_global_kernel','metrics':(L2_PREFIX+'_evict_last.sum',)},
}


def parse_measurement(stdout: str, group: str) -> dict:
    spec = GROUPS[group]
    names = (*spec['metrics'],PASSES)
    header = '"ID","Process ID"'
    if header not in stdout:
        raise ValueError('profiler emitted no metric CSV')
    rows = list(csv.DictReader(io.StringIO(stdout[stdout.index(header):])))
    if len(rows) != len(names) or {row['Metric Name'] for row in rows} != set(names):
        raise ValueError('expected exactly one row for each requested metric')
    kernels = {row['Kernel Name'] for row in rows}
    if len(kernels) != 1 or spec['kernel'] not in next(iter(kernels)):
        raise ValueError('profiler reported the wrong kernel or multiple kernels')
    values = {row['Metric Name']:profiler_number(row['Metric Value'],False) for row in rows}
    if any(not math.isfinite(value) or value < 0 or value != int(value) for value in values.values()):
        raise ValueError('profiler counts must be finite nonnegative integers')
    if values[PASSES] != 1:
        raise ValueError('cache measurement requires exactly one profiler pass; replay could change cache state')
    if group != 'texture_l1':
        # L2 hit/miss/priority counters require separate captures on this GPU.
        # Combining them into a per-launch ratio would invent an observation.
        name = spec['metrics'][0]
        return {'metrics':values,'counter_name':name,'counter_value':values[name],
                'same_launch_hit_rate_available':False}
    hit,miss = (values[name] for name in spec['metrics'][:2])
    total = hit+miss
    if total <= 0:
        raise ValueError('no texture-load sectors were observed')
    return {'metrics':values,'hit_sectors':hit,'miss_sectors':miss,'lookup_sectors':total,
            'hit_pct':100*hit/total,'same_launch_hit_rate_available':True}


def summarize_observations(group: str, observations: list[dict]) -> dict:
    if group != 'texture_l1':
        counts = [item['counter_value'] for item in observations]
        return {'counter_name':GROUPS[group]['metrics'][0],
                'counter_median':statistics.median(counts),'counter_range':[min(counts),max(counts)],
                'same_launch_hit_rate_available':False}
    rates = [item['hit_pct'] for item in observations]
    return {'hit_pct_median':statistics.median(rates),'hit_pct_range':[min(rates),max(rates)],
            'lookup_sectors_median':statistics.median(item['lookup_sectors'] for item in observations),
            'miss_sectors_median':statistics.median(item['miss_sectors'] for item in observations),
            'same_launch_hit_rate_available':True}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--executable',type=Path,required=True)
    p.add_argument('--ncu',type=Path,required=True)
    p.add_argument('--report-dir',type=Path,required=True)
    p.add_argument('--samples',type=int,default=65536)
    p.add_argument('--layout',choices=('linear','morton'),default='morton')
    p.add_argument('--sample-order',choices=('natural','locality'),default='locality')
    p.add_argument('--block-size',type=int,choices=(128,256,512,1024),default=512)
    p.add_argument('--warmup',type=int,default=5)
    p.add_argument('--runs',type=int,default=3)
    p.add_argument('--groups',nargs='+',choices=tuple(GROUPS),default=list(GROUPS))
    a = p.parse_args(argv)
    if not 1 <= a.samples <= 4194304 or not 1 <= a.warmup <= 100 or not 1 <= a.runs <= 20:
        p.error('samples must be 1..4194304, warmup 1..100 and runs 1..20')
    if len(a.groups) != len(set(a.groups)):
        p.error('metric groups must not repeat')
    report = a.report_dir.resolve()
    report.mkdir(parents=True,exist_ok=False)
    exe,ncu = a.executable.resolve(),a.ncu.resolve()
    record = {'status':'running','samples':a.samples,'layout':a.layout,'sample_order':a.sample_order,
              'block_size':a.block_size,'warmup_runs':a.warmup,'repetitions':a.runs,
              'replay_mode':'kernel','required_profiler_passes':1,'clock_control':'base',
              'interpretation':'Counters describe sampled cache activity, not guaranteed residence or cache-line pinning.',
              'l2_counter_scope':'Read sectors from the shared L1/TEX source unit; not individual image-table lines.',
              'l2_capture_method':'Each L2 counter is measured in a separate single-pass capture. No same-launch L2 hit ratio is derived.',
              'steps':[],'observations':[]}

    def run(label,command):
        command = list(map(str,command))
        step = {'label':label,'command':command}
        record['steps'].append(step)
        try:
            result = subprocess.run(command,cwd=ROOT,text=True,encoding='utf-8',errors='replace',
                                    stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        except OSError as error:
            step.update(returncode=None,error=str(error))
            (report/(label+'.log')).write_text(str(error)+'\n',encoding='utf-8')
            raise
        step['returncode'] = result.returncode
        (report/(label+'.log')).write_text(result.stdout,encoding='utf-8')
        if result.returncode:
            raise RuntimeError(label+' failed; see its log')
        return result.stdout

    code = 0
    try:
        record['binary_sha256'] = hashlib.sha256(exe.read_bytes()).hexdigest()
        record['profiler_version'] = run('profiler_version',[ncu,'--version'])
        expected = None
        for repetition in range(a.runs):
            caches = ('cold','warm') if repetition%2 == 0 else ('warm','cold')
            policies = ('normal','persist-image') if repetition%2 == 0 else ('persist-image','normal')
            for cache in caches:
                for policy in policies:
                    for group in a.groups:
                        spec = GROUPS[group]
                        label = f'{group}_{cache}_{policy}_{repetition}'
                        output = report/label
                        arguments = ['--samples',str(a.samples),'--layout',a.layout,'--sample-order',a.sample_order,
                                     '--block-size',str(a.block_size),'--l2-policy',policy,'--warmup',str(a.warmup),
                                     '--repeat','1','--out',str(output)]
                        command = [ncu,'--metrics',','.join((*spec['metrics'],PASSES)),
                                   '--cache-control','all' if cache == 'cold' else 'none',
                                   '--clock-control','base','--replay-mode','kernel',
                                   '--kernel-name','regex:'+spec['kernel'],
                                   '--launch-skip',a.warmup,'--launch-count','1','--csv','--print-units','base',
                                   exe,*arguments]
                        stdout = run(label,command)
                        measurement = parse_measurement(stdout,group)
                        meta = json.loads((output/'run.json').read_text())
                        verify_execution_metadata(meta,arguments,True)
                        oracle = verify_directory(output)
                        data = ((output/'samples.f64x2').read_bytes(),(output/'results.bin').read_bytes())
                        if expected is None:
                            expected = data
                        elif data != expected:
                            raise AssertionError('cache policy/profiling changed original sample or result bytes')
                        record['observations'].append({'group':group,'cache':cache,'policy':policy,
                                                       'repetition':repetition,'run':meta,'oracle':oracle,**measurement})
                        print(label+': one pass; samples/results exact',flush=True)
        if hashlib.sha256(exe.read_bytes()).hexdigest() != record['binary_sha256']:
            raise RuntimeError('executable changed during the probe')
        record['summary'] = {}
        for group in a.groups:
            for cache in ('cold','warm'):
                for policy in ('normal','persist-image'):
                    observations = [item for item in record['observations']
                                    if (item['group'],item['cache'],item['policy']) == (group,cache,policy)]
                    record['summary'][group+'_'+cache+'_'+policy] = summarize_observations(group,observations)
        record['all_samples_and_results_exact'] = True
        record['status'] = 'pass'
    except Exception as error:
        code = 2 if isinstance(error,OSError) else 1
        record['status'] = 'unavailable' if code == 2 else 'fail'
        record['error'] = str(error)
        print(str(error),file=sys.stderr)
    finally:
        (report/'residency_probe.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
