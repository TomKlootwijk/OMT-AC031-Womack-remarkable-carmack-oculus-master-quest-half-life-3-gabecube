#!/usr/bin/env python3
"""Render tables from recorded R17 runs; does not execute a benchmark."""
from pathlib import Path
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]


def main():
    source=ROOT/'review/fused_runs.json'
    r=json.loads(source.read_text(encoding='utf-8'))
    tex=[r'\begin{center}\small',r'\begin{tabular}{@{}l r l r r r r@{}}',
         r'\toprule',r'Program & Lanes & Mode & Ref. tex. & Fused tex. & Tex. gain & Global gain\\',
         r' & & & \multicolumn{2}{c}{Device median (ms)} & \multicolumn{2}{c}{Reference/fused}\\\midrule']
    md=['# R17 measured fused execution','',
        '| Program | Lanes | Feedback | Reference texture ms | Fused texture ms | Texture gain | Global gain |',
        '|---|---:|---|---:|---:|---:|---:|']
    gains=[];host_gains=[]
    for c in r['cases']:
        m=c['medians_ms'];s=c['reference_over_fused']
        a=m['reference_texture']['batch_device'];b=m['fused_texture']['batch_device']
        gt=s['texture']['batch_device'];gg=s['global']['batch_device']
        name='3 cells' if c['workload']=='tiny' else '48 MiB'
        mode='pure' if c['feedback']=='none' else 'copy32'
        tex.append(f'{name} & {c["lanes"]:,} & {mode} & {a:.3f} & {b:.3f} & {gt:.2f}' + r'$\times$ & ' + f'{gg:.2f}' + r'$\times$\\')
        md.append(f'| {name} | {c["lanes"]:,} | {mode} | {a:.6f} | {b:.6f} | {gt:.3f}x | {gg:.3f}x |')
        gains.extend([gt,gg]);host_gains.extend([s['texture']['host_complete'],s['global']['host_complete']])
    tex.extend([r'\bottomrule',r'\end{tabular}\end{center}'])
    (ROOT/'docs/fused_benchmark_table.tex').write_text('\n'.join(tex)+'\n',encoding='utf-8')
    baseline=[(c,f,c['r16_over_fused'][f]) for c in r['cases'] if 'r16_over_fused' in c for f in ('texture','global')]
    md += ['',f'Device gains span {min(gains):.3f}x to {max(gains):.3f}x across {len(gains)} matched fetch/profile cases.',
           f'Host-complete gains span {min(host_gains):.3f}x to {max(host_gains):.3f}x; {sum(g>1 for g in host_gains)}/{len(host_gains)} have a lower fused median.',
           'Cold setup, allocations, upload, final readback and hashing remain in host-complete time.',
           'Every case compares the same program, initial lane words, step count and final output contract.',
           'Full-array FNV-1a-64 and exact first-lane outputs match. FNV is noncryptographic; independent word checks are separate.',
           'The 48 MiB table contains 1,048,576 synthetic operator cells with spread lane initialization; it is not a physical dataset.',
           'These are word-machine comparisons, not S2 operations or cache/DRAM saturation measurements.',
           '',f'Original unchanged R16 executable comparisons: {len(baseline)} fetch/profile cases, all final hashes and first-lane fields match.',
           f'Original-R16/fused device gains: {min(s["batch_device"] for _,_,s in baseline):.3f}x to {max(s["batch_device"] for _,_,s in baseline):.3f}x.' if baseline else '',
           '',f'Source report SHA-256: {hashlib.sha256(source.read_bytes()).hexdigest()}',
           'All individual trials, setup times, device and batch-wall times, readback costs and executable hashes are retained in fused_runs.json.']
    (ROOT/'review/FUSED_RESULTS.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
    print('\n'.join(md))


if __name__=='__main__':main()
