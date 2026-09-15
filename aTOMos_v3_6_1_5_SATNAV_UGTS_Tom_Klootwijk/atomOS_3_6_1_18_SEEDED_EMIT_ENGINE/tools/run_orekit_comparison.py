"""Compile the pinned Orekit adapter, run frozen requests, audit and refine it.

The reference harness prepares the requests before this tool runs. Refinement
changes only integrator controls; no physical parameters are fitted or changed.
"""
from pathlib import Path
import argparse, hashlib, json, os, subprocess, sys, time
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT.parent / 'atomOS_3_6_1_10_ORBIT_SEED'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=ROOT / 'review/orbit_comparison')
    parser.add_argument('--dependencies', type=Path, default=Path('C:/aTOMosBuild/orbitdeps/java'))
    parser.add_argument('--classes', type=Path, default=Path('C:/aTOMosBuild/orbitdeps/classes'))
    args = parser.parse_args()
    sys.path.insert(0, str(OLD / 'python'))
    from orbit_precision import precision_acceleration
    requests = sorted(args.directory.glob('request_*.json'))
    if len(requests) != 8:
        raise ValueError('Exactly eight frozen comparison requests required')
    dependencies = json.loads((ROOT / 'review/r18_orbit_java_dependencies.json').read_text())
    for item in dependencies['files']:
        p = args.dependencies / Path(item['path']).name
        if sha(p) != item['sha256']:
            raise ValueError('Pinned dependency differs: ' + str(p))
    args.classes.mkdir(parents=True, exist_ok=True)
    source = ROOT / 'tools/OrekitFrozenOrbit.java'
    subprocess.run(['javac', '-cp', str(args.dependencies / '*'), '-d', str(args.classes), str(source)], check=True)
    classpath = os.pathsep.join((str(args.classes), str(args.dependencies / '*')))
    report = {
        'profile': 'ATOMOS-OREKIT-NUMERICAL-AUDIT-R1',
        'adapter_sha256': sha(source), 'runner_sha256': sha(__file__),
        'dependency_manifest_sha256': sha(ROOT / 'review/r18_orbit_java_dependencies.json'),
        'java_runtime': subprocess.run(['java', '-version'], capture_output=True, text=True, check=True).stderr.strip(),
        'controls_frozen_before_run': {'standard': {'position_abs_tol_m': 1e-6, 'max_step_s': 60},
                                       'tight': {'position_abs_tol_m': 1e-7, 'max_step_s': 15}},
        'scope': 'Numerical convergence and independent force audit only. Shared physical model; no fit or future observations supplied to either propagation.',
        'cases': [],
    }
    for request_path in requests:
        key = request_path.stem.removeprefix('request_')
        request = json.loads(request_path.read_text())
        period, satellite = key.split('_', 1)
        model_path = OLD / 'examples/orbit' / ('precision_models' if period == 'jan' else 'confirmation_models') / (satellite + '.json')
        if sha(model_path) != request['model_sha256']:
            raise ValueError('Frozen input file differs')
        model = json.loads(model_path.read_text())['model']
        results = {}
        for label, controls in report['controls_frozen_before_run'].items():
            target = args.directory / (('orekit_' if label == 'standard' else 'orekit_tight_') + key + '.json')
            before = time.perf_counter()
            subprocess.run(['java', '-Xmx2g', '-cp', classpath, 'OrekitFrozenOrbit', str(model_path), str(request_path),
                            str(target), str(controls['position_abs_tol_m']), str(controls['max_step_s'])], check=True)
            elapsed = time.perf_counter() - before
            result = json.loads(target.read_text())
            if result['times_s'] != request['times_s'] or result['model_sha256'] != request['model_sha256']:
                raise ValueError('Adapter returned different input binding')
            results[label] = (result, target, elapsed)
        nominal, refined = results['standard'][0], results['tight'][0]
        y = np.asarray(nominal['states_gcrs_m_m_s']); yt = np.asarray(refined['states_gcrs_m_m_s'])
        position = np.linalg.norm(y[:, :3] - yt[:, :3], axis=1)
        velocity = np.linalg.norm(y[:, 3:] - yt[:, 3:], axis=1)
        # Audit points span each sampled trajectory, including first and last.
        indices = np.unique(np.linspace(0, len(y) - 1, 65).astype(int))
        accelerations = np.asarray(nominal['accelerations_gcrs_m_s2'])
        discrepancy = [float(np.linalg.norm(precision_acceleration(model, nominal['times_s'][i], y[i]) - accelerations[i])) for i in indices]
        if not np.isfinite(y).all() or not np.isfinite(yt).all() or max(discrepancy) > 1e-10:
            raise ValueError('Independent force agreement or finite-state admission failed')
        row = {
            'case': key, 'samples': len(y), 'model_sha256': sha(model_path), 'request_sha256': sha(request_path),
            'standard_report_sha256': sha(results['standard'][1]), 'tight_report_sha256': sha(results['tight'][1]),
            'position_refinement_rms_m': float(np.sqrt(np.mean(position ** 2))),
            'position_refinement_max_m': float(position.max()),
            'position_refinement_final_m': float(position[-1]),
            'velocity_refinement_max_m_s': float(velocity.max()),
            'independent_force_audit_samples': len(indices), 'force_difference_max_m_s2': max(discrepancy),
            'force_difference_all_m_s2': discrepancy,
            'wall_s_including_jvm_and_report': {label: values[2] for label, values in results.items()},
        }
        report['cases'].append(row)
        (ROOT / 'review/r18_orekit_numerical_audit.json').write_text(json.dumps(report, indent=2) + '\n')
        print(key, 'refinement max m', row['position_refinement_max_m'], 'force difference', max(discrepancy), flush=True)
    report['complete'] = True
    (ROOT / 'review/r18_orekit_numerical_audit.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
