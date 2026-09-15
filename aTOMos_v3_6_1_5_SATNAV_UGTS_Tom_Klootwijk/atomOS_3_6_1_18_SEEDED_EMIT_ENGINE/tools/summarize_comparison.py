"""Generate measured comparison text and LaTeX from the complete raw report."""
from pathlib import Path
import argparse
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding='utf-8'))
    rows = report['workloads']
    if report['correctness_failures'] or not all(r['all_results_equal'] for r in rows):
        raise ValueError('Cannot publish a successful comparison with mismatching answers')
    def wall(r): return r['gpu_texture_host_visible']['median_ms']
    cpu_ratios = [r['best_s2_median_ms'] / r['best_host_median_ms'] for r in rows]
    tex_ratios = [r['best_s2_median_ms'] / wall(r) for r in rows]
    texture_wins = sum(x > 1 for x in tex_ratios)
    global_wins = sum(r['gpu_global_host_visible']['median_ms'] < wall(r) for r in rows)
    summary = {
        'report': args.report.name,
        'sha256': hashlib.sha256(args.report.read_bytes()).hexdigest(),
        'workloads': len(rows), 'correctness_failures': 0,
        'cpu_bvh_faster_than_best_s2': sum(x > 1 for x in cpu_ratios),
        'cpu_bvh_over_s2_speedup_range': [min(cpu_ratios), max(cpu_ratios)],
        'texture_pipeline_faster_than_best_s2': texture_wins,
        'texture_pipeline_over_s2_speedup_range': [min(tex_ratios), max(tex_ratios)],
        'global_pipeline_faster_than_texture': global_wins,
        'scope': 'Observed median host-visible inclusive spherical point radius queries on the recorded laptop, with all requested CPU configurations retained. Not universal superiority or whole-engine completion.'
    }
    (ROOT / 'review/comparison_summary.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8')
    md = ['# Recorded S2 comparison', '',
          f"All {len(rows)} workload answers matched across methods and repetitions.",
          f"The CPU BVH was faster than the best measured S2 CPU configuration in {summary['cpu_bvh_faster_than_best_s2']}/{len(rows)} cases ({min(cpu_ratios):.2f}–{max(cpu_ratios):.2f}× observed ratio).",
          f"The complete texture pipeline was faster in {texture_wins}/{len(rows)} cases. Ordinary GPU reads were faster than texture reads in {global_wins}/{len(rows)} cases.", '',
          'GPU pipeline timing includes CPU refinement/fallback and host-visible output. CPU baselines use persistent workers; GPU refinement resources are recorded separately. Five timed trials follow a warmup for each method. The table reports medians in milliseconds; all trials remain in the source JSON.', '',
          '| Distribution | Points | Queries (requested) | Best S2 | Best BVH | Texture pipeline | S2 / texture |',
          '|---|---:|---:|---:|---:|---:|---:|']
    tex = [r'\begin{panel}',
           f"All {len(rows)} measured workload answers matched. The CPU BVH was faster than",
           f"the best tested S2 CPU configuration in {summary['cpu_bvh_faster_than_best_s2']}/{len(rows)} cases, with observed",
           f"ratios from {min(cpu_ratios):.2f} to {max(cpu_ratios):.2f}. The complete texture pipeline was",
           f"faster than that S2 configuration in {texture_wins}/{len(rows)} cases. Ordinary GPU reads",
           f"were faster than texture reads in {global_wins}/{len(rows)} cases. These are measured median",
           r'results for the declared radius workload and hardware, not a universal ranking.',
           r'\end{panel}',
           r'Five timed trials follow a warmup for each method. The table reports complete',
           r'host-visible milliseconds. S2 and BVH columns use the best of the recorded',
           r'1/4/20-thread configurations; every configuration remains in the JSON report.',
           r'An asterisk marks a capped query count, whose requested count is retained in',
           r'the machine-readable report. A ratio above one favors the texture pipeline.',
           r'{\small',
           r'\begin{longtable}{@{}lrrrrrr@{}}',
           r'\toprule Data & Points & Queries & S2 & BVH & Texture & Ratio\\\midrule',
           r'\endfirsthead',
           r'\toprule Data & Points & Queries & S2 & BVH & Texture & Ratio\\\midrule',
           r'\endhead',
           r'\bottomrule\endfoot']
    for r, ratio in zip(rows, tex_ratios):
        family = r['family'].replace('_', ' ')
        q = str(r['queries']) + ('*' if r.get('queries_capped') else '')
        md.append(f"| {family} | {r['points']} | {r['queries']} ({r['requested_queries']}) | {r['best_s2_median_ms']:.4f} | {r['best_host_median_ms']:.4f} | {wall(r):.4f} | {ratio:.2f} |")
        tex.append(f"{family} & {r['points']} & {q} & {r['best_s2_median_ms']:.4f} & {r['best_host_median_ms']:.4f} & {wall(r):.4f} & {ratio:.2f}" + r'\\')
    tex += [r'\end{longtable}}',
            r'The first complete report is retained as \code{review/s2\_full.json}.',
            r'The current report includes the subsequent bounded-overflow and parallel',
            r'exact-refinement optimization; no answer semantics were changed.']
    md += ['', 'The first complete pre-optimization run remains in `review/s2_full.json`. The current report includes the recorded overflow/refinement optimization. Constructor costs, CPU refinement threads, device-only samples, transfers and overflow counts must accompany any use of the numbers.', '',
           'Dynamic updates, full nearest/region throughput, complete log-spherical LUT lowering and the full S2 library remain unmeasured. Broader engine superiority is open.']
    (ROOT / 'review/COMPARISON.md').write_text('\n'.join(md)+'\n', encoding='utf-8')
    (ROOT / 'docs/benchmark_table.tex').write_text('\n'.join(tex)+'\n', encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
