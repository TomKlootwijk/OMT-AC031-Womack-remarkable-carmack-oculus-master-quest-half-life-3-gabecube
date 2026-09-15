#!/usr/bin/env python3
"""Plot the audited matched forecast errors, retaining missing reference arcs."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('matched_orbit_harness', ROOT / 'tools/compare_orbit_references.py')
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)
import numpy as np


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--summary', type=Path, default=ROOT / 'review/orbit_comparison/matched_forecast_summary.json')
    parser.add_argument('--audit', type=Path, default=ROOT / 'review/r18_orekit_numerical_audit.json')
    parser.add_argument('--python-deps', type=Path)
    parser.add_argument('--out', type=Path, default=ROOT / 'docs/figures')
    args = parser.parse_args()
    if args.python_deps:
        sys.path.insert(0, str(args.python_deps.resolve()))
    audit = json.loads(args.audit.read_text('utf8'))
    if audit.get('complete') is not True or len(audit['cases']) != 8:
        raise ValueError('Require completed eight-case numerical audit')
    if audit['adapter_sha256'] != sha(ROOT / 'tools/OrekitFrozenOrbit.java'):
        raise ValueError('Audit adapter hash mismatch')
    summary = json.loads(args.summary.read_text('utf8'))
    if not summary.get('complete_eight_case_scope'):
        raise ValueError('Require complete eight-case matched forecast summary')
    protocol_path = harness.resolved(summary['protocol_file'])
    if sha(protocol_path) != summary['protocol_sha256']:
        raise ValueError('Protocol binding mismatch')
    protocol = harness.verify_protocol(protocol_path)
    audit_cases = {c['case']: c for c in audit['cases']}
    cases = {c['case_id']: c for c in protocol['cases']}
    curves = {}
    bindings = []
    for result in summary['cases']:
        key = result['case_id']
        case = cases[key]
        model, rows, times, reference, provenance = harness.load_case(case)
        lines = {}
        for engine, info in result['engines'].items():
            path = harness.resolved(info['source']['file'])
            if sha(path) != info['source']['sha256']:
                raise ValueError('Scored engine output changed: ' + str(path))
            if engine == 'orekit' and sha(path) != audit_cases[key]['standard_report_sha256']:
                raise ValueError('Orekit state file differs from audited standard run')
            states, metadata, binding = harness.engine_states(path, case, times, summary['protocol_sha256'])
            positions = states[:, :3] if case['object_id'] == 'CHANDRA' else np.asarray([
                harness.state_to_ecef(model, float(t), y)[:3] for t, y in zip(times, states)])
            errors = np.linalg.norm(positions - reference, axis=1)
            recorded = result['external_reference_position_error'][engine]['whole_available_arc']
            if not np.isclose(errors.max(), recorded['max_m'], rtol=1e-13, atol=1e-12):
                raise ValueError('Recomputed plot errors disagree with report')
            lines[engine] = errors
            bindings.append(binding)
        curves[key] = (times, lines)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.titlesize': 11,
                         'axes.labelsize': 10, 'legend.fontsize': 9, 'xtick.labelsize': 9, 'ytick.labelsize': 9,
                         'pdf.fonttype': 42, 'ps.fonttype': 42})
    styles = {'atomos_cpu': ('aTOMos CPU', '#173244', '-', 1.55),
              'atomos_cuda': ('aTOMos CUDA', '#1a777f', ':', 1.35),
              'orekit': ('Orekit, same frozen model', '#b28448', '--', 1.1)}
    args.out.mkdir(parents=True, exist_ok=True)
    products = []
    for period, date in [('jan', '2 January 2025'), ('feb', '2 February 2025')]:
        fig, axes = plt.subplots(2, 2, figsize=(8.2, 6.25))
        fig.subplots_adjust(left=.10, right=.98, bottom=.14, top=.87, wspace=.26, hspace=.44)
        for ax, satellite in zip(axes.flat, harness.OBJECTS):
            times, lines = curves[period + '_' + satellite]
            gap_indices = np.flatnonzero(np.diff(times) > 1.5 * np.median(np.diff(times))) + 1
            plot_times = np.insert(times / 3600, gap_indices, np.nan)
            for engine, (label, color, style, width) in styles.items():
                values = np.maximum(lines[engine], 1e-12)
                ax.semilogy(plot_times, np.insert(values, gap_indices, np.nan), label=label,
                            color=color, linestyle=style, linewidth=width)
            all_values = np.concatenate([v for p in ('jan', 'feb') for v in curves[p + '_' + satellite][1].values()])
            lower = max(1e-4, float(np.min(all_values[all_values > 0])) / 1.7)
            upper = max(20, float(all_values.max()) * 1.7)
            ax.set_ylim(lower, upper)
            ax.axhline(10, color='#85939d', linewidth=.75, linestyle=(0, (3, 3)), zorder=0)
            ax.axvline(24, color='#b9c4ca', linewidth=.7, linestyle=':', zorder=0)
            ax.set(title=satellite + ' / ' + harness.OBJECTS[satellite], xlabel='Hours after frozen epoch', ylabel='Position discrepancy (m)')
            ax.set_xlim(0, 168)
            ax.set_xticks([0, 24, 72, 120, 168])
            ax.grid(which='major', alpha=.19)
            if len(gap_indices):
                for i in gap_indices:
                    ax.axvspan(times[i-1]/3600, times[i]/3600, color='#dbe2e6', alpha=.38, zorder=-1)
                ax.text(.04, .94, 'Reference gap shaded', transform=ax.transAxes, va='top', fontsize=8, color='#586c79')
        handles, labels = axes.flat[0].get_legend_handles_labels()
        fig.legend(handles, labels, loc='lower center', bbox_to_anchor=(.52, .018), ncol=3, frameon=False)
        fig.suptitle('Frozen forecast versus later external positions\nEpoch: ' + date + ' GPST', fontsize=13, y=.97)
        name = 'r18_orbit_forecast_' + period
        for suffix in ('pdf', 'png'):
            path = args.out / (name + '.' + suffix)
            fig.savefig(path, dpi=190)
            products.append({'file': harness.relative(path), 'sha256': sha(path)})
        plt.close(fig)
    manifest = {'profile': 'ATOMOS-ORBIT-FORECAST-PLOTS-R1', 'summary_sha256': sha(args.summary),
                'numerical_audit_sha256': sha(args.audit), 'generator_sha256': sha(__file__),
                'source_bindings': bindings, 'outputs': products,
                'conventions': 'Logarithmic metre errors; common per-object y limits across dates; gap breaks and shading; 10 m descriptive line and 24 h vertical marker; no interpolated reference rows or fitted alignment'}
    path = ROOT / 'review/r18_orbit_forecast_plots.json'
    path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'plots': products, 'manifest': str(path)}))


if __name__ == '__main__':
    main()
