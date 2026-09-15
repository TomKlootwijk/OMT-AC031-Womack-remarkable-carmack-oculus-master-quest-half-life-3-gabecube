#!/usr/bin/env python3
"""Read frozen Nsight receipts; do not run or extrapolate a benchmark."""
import csv
import hashlib
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / 'review'
METRICS = {
    'dram_pct': 'dram__throughput.avg.pct_of_peak_sustained_elapsed',
    'sm_pct': 'sm__throughput.avg.pct_of_peak_sustained_elapsed',
    'l1tex_hit_pct': 'l1tex__t_sector_hit_rate.pct',
    'l2_hit_pct': 'lts__t_sector_hit_rate.pct',
    'active_warp_pct': 'sm__warps_active.avg.pct_of_peak_sustained_active',
}
MODES = [('stream_texture', 0, '1, 0'), ('stream_global', 64, '0, 0'),
         ('affine_texture', 128, '1, 1'), ('affine_global', 192, '0, 1')]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_receipt(path):
    raw = path.read_text(encoding='utf-8-sig')
    lines = raw.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith('"ID",'))
    rows = list(csv.DictReader(io.StringIO('\n'.join(lines[start:]))))
    # These preserved receipts use the Dutch locale: comma decimal, dot grouping.
    values = {r['Metric Name']: float(r['Metric Value'].replace('.', '').replace(',', '.'))
              for r in rows}
    assert len({r['Kernel Name'] for r in rows}) == 1
    return rows[0]['Kernel Name'], {k: values[v] for k, v in METRICS.items()}


def main():
    measured = []
    for mode, skip, specialization in MODES:
        path = REVIEW / f'ncu_word_optimized_{mode}.csv'
        kernel, values = read_receipt(path)
        assert f'epoch_kernel<{specialization}>' in kernel
        measured.append({'mode': mode, 'matching_launch_skip': skip, 'kernel': kernel,
                         **values, 'receipt': path.name, 'sha256': sha(path)})
    baseline_path = REVIEW / 'ncu_word_baseline_stream_texture.csv'
    baseline_kernel, baseline_values = read_receipt(baseline_path)
    summary = {
        'source_commit': '59a7e7d', 'baseline_source_commit': '4d89922',
        'source_sha256': sha(ROOT / 'cuda/word_cache_benchmark.cu'),
        'profiler': 'Nsight Compute 2025.1.0',
        'device': 'RTX 5070 Ti Laptop GPU, sm_120',
        'working_bytes': 512 * 1024**2, 'profiled_chunk_logical_bytes': 8 * 1024**2,
        'threads_per_block': 128, 'blocks': 2048,
        'replay': 'kernel', 'cache_control': 'none', 'clock_control': 'none',
        'sample': 'first chunk of first measured epoch for each mode; separate process per mode',
        'command': 'ncu --kernel-name-base function --kernel-name regex:epoch_kernel '
                   '--launch-skip SKIP --launch-count 1 --replay-mode kernel '
                   '--cache-control none --clock-control none --metrics METRICS --csv '
                   '--log-file RECEIPT word_cache_benchmark --only-max --max-mib 512 '
                   '--trials 1 --epochs 1 --warm-epochs 0 --out RUN_RECEIPT',
        'metric_names': METRICS,
        'optimized_samples': measured,
        'baseline_stream_texture': {'kernel': baseline_kernel, **baseline_values,
                                    'sha256': sha(baseline_path), 'matching_launch_skip': 316},
        'baseline_command_difference': 'No --only-max; same 512 MiB final set after smaller sets.',
        'sass_sha256': sha(REVIEW / 'word_optimized_sass.txt'),
        'resource_receipt_sha256': sha(REVIEW / 'word_optimized_resources.txt'),
        'limitations': [
            'One selected chunk per mode, not a whole-epoch or full-VRAM hardware-counter average.',
            'Profiler replay perturbs execution; use unprofiled reports for speed comparisons.',
            'Caches are not flushed and clocks are not locked; counters are observations, not guaranteed bounds.',
            'L1/TEX hit ratio aggregates the shared unit and is not a seed-texture-only hit ratio.',
            'Working-set capacity, cache residency and DRAM bandwidth saturation are different quantities.',
        ],
    }
    (REVIEW / 'word_profile_summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    md = ['# Native word-kernel hardware receipts', '',
          'The optimized sm_120 binary has literal `TLD.LZ` instructions in its texture epoch variants. '
          'The corresponding global variants use ordinary loads. The disassembly and resource receipts are preserved.', '',
          'Nsight Compute sampled the first 8 MiB logical chunk from a 512 MiB working set in each mode. '
          'Each sample uses 2,048 blocks of 128 threads, kernel replay, unchanged clocks and unflushed caches. '
          'These are separate profiling runs; their elapsed times are not the benchmark timings.', '',
          '| Mode | DRAM peak % | SM peak % | L1/TEX hits % | L2 hits % | Active warps % |',
          '| --- | ---: | ---: | ---: | ---: | ---: |']
    tex = [r'\section{Native instructions and hardware-counter receipts}',
           r'The preserved optimized \code{sm\_120} disassembly contains \code{TLD.LZ} '
           r'in the texture epoch variants and ordinary loads in the global variants. '
           r'Compiler resources report 28 registers per texture thread and 26 per global thread, '
           r'with a 40-byte stack. Local stack loads/stores remain visible; no zero-stack claim is made.',
           r'Nsight Compute 2025.1.0 sampled the first 8 MiB logical chunk of a 512 MiB working set '
           r'in each mode, with 2,048 blocks of 128 threads. Kernel replay was enabled; caches were '
           r'not flushed and clocks were not locked. Each mode used a separate process.',
           r'\begin{center}\small', r'\begin{tabular}{lrrrrr}', r'\toprule',
           r'Mode & DRAM \% & SM \% & L1/TEX hit \% & L2 hit \% & Warps \%\\\midrule']
    for row in measured:
        label = row['mode'].replace('_', ' ')
        vals = [row[k] for k in METRICS]
        md.append('| ' + label + ' | ' + ' | '.join(f'{v:.2f}' for v in vals) + ' |')
        tex.append(label + ' & ' + ' & '.join(f'{v:.2f}' for v in vals) + r'\\')
    md += ['', 'DRAM/SM columns are percentages of reported peak sustained elapsed throughput. '
           'The active-warp column is a percentage of peak sustained active warps. '
           'L1/TEX is an aggregate unit hit ratio, not an isolated immutable-seed hit ratio.', '',
           'The earlier baseline streaming-texture sample reported 37.06% DRAM throughput. '
           'The optimized sample reports 58.55%. This does not establish saturated bandwidth, '
           'a full-sweep average or deterministic cache residency.', '',
           'All selected epochs and the surrounding profile runs passed their normal digests and sampled oracle checks. '
           'Unprofiled paired timing reports remain the authority for performance comparisons.']
    tex += [r'\bottomrule\end{tabular}\end{center}',
            r'DRAM and SM are percentages of reported peak sustained elapsed throughput. '
            r'Warps denotes peak sustained active warps. The L1/TEX ratio aggregates the shared unit; '
            r'it does not isolate immutable seed traffic. These are selected-chunk observations, '
            r'not full-working-set averages or cache-residency guarantees.',
            r'The earlier streaming-texture baseline sample reported 37.06\% DRAM throughput, '
            r'compared with 58.55\% in the optimized sample. This does not establish bandwidth saturation. '
            r'Profiler replay changes execution; the separate unprofiled sweeps supply performance timings.',
            r'Commands, source hashes, selected launches and raw receipts are retained in '
            r'\path{review/word_profile_summary.json}. Replay behavior follows the '
            r'\href{https://docs.nvidia.com/nsight-compute/ProfilingGuide/index.html#replay}{official Nsight Compute profiling guide}.']
    (REVIEW / 'WORD_PROFILE.md').write_text('\n'.join(md) + '\n', encoding='utf-8')
    (ROOT / 'docs/word_profile.tex').write_text('\n\n'.join(tex) + '\n', encoding='utf-8')
    print(json.dumps({'samples': measured, 'source_commit': summary['source_commit']}, indent=2))


if __name__ == '__main__':
    main()
