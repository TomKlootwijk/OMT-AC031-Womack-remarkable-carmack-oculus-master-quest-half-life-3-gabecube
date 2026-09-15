#!/usr/bin/env python3
"""Freeze and score a matched R2 aTOMos/Orekit satellite forecast comparison.

Run prepare once, native for each backend, then compare after the external
Orekit adapter has written orekit_<case>.json. No fitting or clock adjustment.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
LEGACY = WORKSPACE / 'atomOS_3_6_1_10_ORBIT_SEED'
sys.path.insert(0, str(LEGACY / 'python'))
import numpy as np
from orbit_dynamics import state_to_ecef, validate_model
from orbit_seed import digest as physical_digest

spec = importlib.util.spec_from_file_location('r10_reference_validation', LEGACY / 'tools/validate_orbit_accuracy.py')
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)

HOURS = [1, 6, 12, 24, 48, 72, 168]
OBJECTS = {'G05': 'MEO', 'C03': 'GEO', 'C06': 'IGSO', 'CHANDRA': 'HEO'}
DEFAULT_PROTOCOL = ROOT / 'review/r18_orbit_protocol.json'
DEFAULT_OUT = ROOT / 'review/orbit_comparison'
LIMITS = [
    'The January and February 2025 sets were measured in R10. Neither is a newly blind confirmation set for R18.',
    'Models remain frozen; no later target position enters fitting, parameter selection, initial state, force forcing or frame construction in this comparison.',
    'Provider orbit products are retrospective and may use later observations internally. Past target timestamps do not establish real-time model availability.',
    'Precise orbit products and Horizons are external references, not exact truth. No state covariance or certified position bound is provided by this experiment.',
    'Samples are correlated and discrete. Reported errors do not certify continuous-time bounds, general future accuracy or operational navigation availability.',
    'A common frozen GCRS-to-ECEF transform is used to score GNSS states. This deliberately matches frame approximations; it does not validate future EOP accuracy.',
    'Horizons geocentric ICRF axes are compared with model GCRS orientation. Omitted relativistic coordinate distinctions are not certified by this comparison.',
    'No clock, orientation, spatial alignment, orbit refit or post-hoc time shift is estimated from future reference rows.',
    'Native batch timing includes worker startup, model initialization, queries and teardown. One timing sample is diagnostic and does not establish a speed ranking against Java.',
    'SPICE ephemeris interpolation is a separate representation experiment; interpolating future reference samples is not a forward forecast.',
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def relative(path):
    return Path(path).resolve().relative_to(WORKSPACE.resolve()).as_posix()


def resolved(value):
    path = (WORKSPACE / value).resolve()
    if not path.is_relative_to(WORKSPACE.resolve()):
        raise ValueError('Input path outside the frozen workspace: ' + value)
    return path


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf8')


def finite(value, shape, name):
    return reference.finite_array(value, shape, name)


def array_digest(value):
    return canonical_hash(np.asarray(value, dtype=float).tolist())


def inputs_for(period, satellite):
    data = LEGACY / 'source/orbit_data'
    if period == 'jan':
        model = LEGACY / 'examples/orbit/precision_models' / (satellite + '.json')
        target = data
        chandra = data / 'HORIZONS_CHANDRA_20250101_20250109_ICRF_TDB.txt'
        bulletin = data / 'bulletina-xxxvii-052.txt'
        secondary = data
    else:
        model = LEGACY / 'examples/orbit/confirmation_models' / (satellite + '.json')
        target = data / 'confirmation_20250202/holdout'
        chandra = target / 'HORIZONS_CHANDRA_20250202_20250209_ICRF_TDB.txt'
        bulletin = data / 'confirmation_20250202/eop/bulletina-xxxviii-005.txt'
        secondary = data / 'confirmation_20250202/holdout_wum'
    primary_paths = [chandra] if satellite == 'CHANDRA' else sorted(target.glob('GBM0MGXRAP_*_ORB.SP3.gz'))
    secondary_paths = [] if satellite == 'CHANDRA' else sorted(secondary.glob('WUM0MGXFIN_*_ORB.SP3.gz'))
    if not primary_paths or (satellite != 'CHANDRA' and not secondary_paths):
        raise ValueError('Missing requested primary or secondary source files')
    return model, primary_paths, secondary_paths, bulletin


def read_rows(satellite, paths):
    return reference.parse_chandra(paths[0]) if satellite == 'CHANDRA' else reference.parse_sp3(paths, satellite)


def load_case(case):
    path = resolved(case['model_file'])
    envelope = json.loads(path.read_text('utf8'))
    model = envelope['model']
    validate_model(model)
    epoch = float(model['epoch_gpst_s'])
    rows, provenance = read_rows(case['object_id'], [resolved(p) for p in case['primary_sources']])
    holdout = [r for r in rows if 0 < r['gpst_s'] - epoch <= float(model['domain_s'][1])]
    times = finite([r['gpst_s'] - epoch for r in holdout], (len(holdout),), 'reference times')
    if len(times) < 2 or np.any(np.diff(times) <= 0):
        raise ValueError('Missing or unordered strictly future target samples')
    positions = finite([r['position'] for r in holdout], (len(times), 3), 'reference positions')
    if case.get('times_sha256') and array_digest(times) != case['times_sha256']:
        raise ValueError('Selected reference times differ from frozen protocol')
    if case.get('reference_positions_sha256') and array_digest(positions) != case['reference_positions_sha256']:
        raise ValueError('Selected reference positions differ from frozen protocol')
    return model, holdout, times, positions, provenance


def prepare(args):
    if args.protocol.exists():
        raise ValueError('Protocol already exists; never silently replace a frozen comparison')
    if args.out.exists() and any(args.out.glob('request_*.json')):
        raise ValueError('Request files already exist; use a fresh output directory')
    inputs = set()
    cases = []
    helpers = [Path(__file__), ROOT / 'formal/ORBIT_COMPARISON_PROTOCOL.md', LEGACY / 'tools/validate_orbit_accuracy.py']
    helpers += [LEGACY / 'python' / n for n in ('orbit_native.py', 'orbit_seed.py', 'orbit_dynamics.py', 'orbit_precision.py', 'self_reference.py')]
    inputs.update(helpers)
    binaries = {backend: LEGACY / 'bin' / backend / 'orbit_worker.exe' for backend in ('cpu', 'cuda')}
    inputs.update(binaries.values())
    for period in ('jan', 'feb'):
        for satellite in OBJECTS:
            model_path, primary, secondary, bulletin = inputs_for(period, satellite)
            envelope = json.loads(model_path.read_text('utf8'))
            model = envelope['model']
            fit = envelope.get('fit', {})
            if not fit or not math.isfinite(float(fit.get('training_end_s', math.inf))) or float(fit['training_end_s']) > 0 or fit.get('future_target_rows_used') != 0:
                raise ValueError('Missing or invalid frozen past-only fit metadata')
            training = [(LEGACY / fit['training_source'], fit['training_source_sha256'])]
            training += [(LEGACY / p['path'], p['sha256']) for p in fit.get('training_sources', [])]
            for path, expected in training:
                if sha(path) != expected:
                    raise ValueError('Training source hash mismatch: ' + str(path))
                inputs.add(path)
            inputs.update([model_path, bulletin, *primary, *secondary])
            case = {'case_id': period + '_' + satellite, 'object_id': satellite, 'orbit_class': OBJECTS[satellite],
                    'period': period, 'model_file': relative(model_path), 'model_sha256': sha(model_path),
                    'physical_model_sha256': physical_digest(model),
                    'primary_sources': [relative(p) for p in primary], 'secondary_sources': [relative(p) for p in secondary],
                    'bulletin': relative(bulletin), 'earth_orientation_publication': reference.bulletin_metadata(bulletin, model['epoch_gpst_s']),
                    'model_integration': model['integration'], 'training_metadata': fit}
            model, rows, times, positions, metadata = load_case(case)
            case.update({'cutoff_gpst_s': model['epoch_gpst_s'], 'sample_count': len(times), 'first_seconds': float(times[0]),
                         'last_seconds': float(times[-1]), 'maximum_sample_gap_seconds': float(np.diff(times).max()),
                         'times_sha256': array_digest(times), 'reference_positions_sha256': array_digest(positions),
                         'reference_frames': sorted({r['frame'] for r in rows}), 'reference_metadata': metadata})
            cases.append(case)
    for p in (LEGACY / 'source/orbit_data/download_manifest.json', LEGACY / 'source/orbit_data/confirmation_20250202/download_manifest.json'):
        inputs.add(p)
    import erfa
    protocol = {'schema': 'ATOMOS-OREKIT-MATCHED-FORECAST-R1', 'frozen_utc': datetime.now(timezone.utc).isoformat(),
                'status_at_freeze': 'Inputs and sample selections frozen before R18 numerical comparison results',
                'horizon_hours': HOURS, 'selection': 'Every available primary target row strictly after model epoch and within its declared future domain; no time interpolation or gap filling',
                'execution': 'Same initial state, frozen forces, forcing coefficients, frame and GPST offsets; native R2 CPU/CUDA versus an external Orekit adapter',
                'timing_match': 'Engine times_s must equal the frozen IEEE-754 decoded request times exactly; nearest reference row substitution is rejected',
                'python_runtime': {'version': platform.python_version(), 'numpy': np.__version__, 'pyerfa': erfa.__version__},
                'native_binaries': {b: relative(p) for b, p in binaries.items()},
                'limits': LIMITS, 'cases': cases,
                'frozen_inputs': [{'file': relative(p), 'bytes': p.stat().st_size, 'sha256': sha(p)} for p in sorted(inputs)]}
    save(args.protocol, protocol)
    protocol_sha = sha(args.protocol)
    for case in cases:
        model, rows, times, positions, metadata = load_case(case)
        request = {'schema': 'ATOMOS-ORBIT-COMPARISON-REQUEST-R1', 'case_id': case['case_id'],
                   'protocol_sha256': protocol_sha, 'model_file': case['model_file'], 'model_sha256': case['model_sha256'],
                   'epoch_gpst_s': model['epoch_gpst_s'], 'times_s': times.tolist(), 'times_sha256': case['times_sha256'],
                   'state_units': 'metres, metres/second', 'frame': 'model GCRS inertial coordinates',
                   'time_convention': 'SI seconds after model epoch_gpst_s; GPST=TT-51.184s'}
        save(args.out / ('request_' + case['case_id'] + '.json'), request)
        print(json.dumps({k: case[k] for k in ('case_id', 'sample_count', 'first_seconds', 'last_seconds', 'maximum_sample_gap_seconds')}), flush=True)
    print(json.dumps({'protocol': str(args.protocol), 'sha256': protocol_sha, 'frozen_input_count': len(inputs)}), flush=True)


def verify_protocol(path):
    protocol = json.loads(path.read_text('utf8'))
    if protocol.get('schema') != 'ATOMOS-OREKIT-MATCHED-FORECAST-R1':
        raise ValueError('Unsupported protocol schema')
    for item in protocol['frozen_inputs']:
        source = resolved(item['file'])
        if source.stat().st_size != item['bytes'] or sha(source) != item['sha256']:
            raise ValueError('Frozen input changed: ' + item['file'])
    return protocol


def native(args, protocol):
    for case in protocol['cases']:
        if args.cases and case['case_id'] not in args.cases:
            continue
        output = args.out / ('native_' + args.backend + '_' + case['case_id'] + '.json')
        if output.exists():
            raise ValueError('Native output already exists: ' + str(output))
        model, rows, times, positions, metadata = load_case(case)
        binary = resolved(protocol['native_binaries'][args.backend])
        states, elapsed = reference.native_states(binary, model, times, args.backend)
        finite(states, (len(times), 6), 'native states')
        save(output, {'schema': 'ATOMOS-ORBIT-STATES-R1', 'case_id': case['case_id'], 'engine': 'aTOMos_R2_' + args.backend,
                      'model_sha256': case['model_sha256'], 'physical_model_sha256': case['physical_model_sha256'],
                      'protocol_sha256': sha(args.protocol), 'native_binary_sha256': sha(binary),
                      'times_s': times.tolist(), 'states_gcrs_m_m_s': states.tolist(),
                      'timing': {'native_batch_wall_seconds': elapsed, 'trials': 1,
                                 'scope': 'Worker construction/model initialization + full batch queries + shutdown; Python reference parsing excluded'},
                      'time_convention': 'SI seconds after model epoch_gpst_s', 'frame_convention': 'Frozen-model GCRS state'})
        print(json.dumps({'case_id': case['case_id'], 'backend': args.backend, 'samples': len(times), 'batch_wall_seconds': elapsed}), flush=True)
    verify_protocol(args.protocol)


def engine_states(path, case, times, protocol_sha):
    data = json.loads(path.read_text('utf8'))
    if data.get('model_sha256') != case['model_sha256']:
        raise ValueError('Engine output model binding mismatch: ' + str(path))
    if data.get('protocol_sha256', protocol_sha) != protocol_sha:
        raise ValueError('Engine output protocol binding mismatch: ' + str(path))
    engine_times = finite(data.get('times_s'), times.shape, 'engine times')
    if not np.array_equal(engine_times, times):
        raise ValueError('Engine epochs differ from exact requested reference epochs: ' + str(path))
    states = finite(data.get('states_gcrs_m_m_s'), (len(times), 6), 'engine states')
    metadata = {k: v for k, v in data.items() if k not in ('times_s', 'states_gcrs_m_m_s')}
    return states, metadata, {'file': relative(path), 'sha256': sha(path), 'max_absolute_time_offset_seconds': float(np.max(np.abs(engine_times - times))),
                             'exact_epoch_matches': len(times)}


def error_summary(times, errors):
    errors = finite(errors, times.shape, 'position errors')
    result = {'whole_available_arc': reference.stats(errors), 'cumulative_horizons': [], 'nearest_horizon_samples': [],
              'first_sample_seconds': float(times[0]), 'last_sample_seconds': float(times[-1]),
              'maximum_sample_gap_seconds': float(np.diff(times).max()), 'threshold_horizons': reference.threshold_horizons(times, errors)}
    for hours in HOURS:
        end = float(hours * 3600)
        selected = times <= end
        result['cumulative_horizons'].append({'hours': hours, 'selection': '0 < time <= requested horizon', **reference.stats(errors[selected])})
        i = int(np.argmin(np.abs(times - end)))
        result['nearest_horizon_samples'].append({'hours': hours, 'requested_seconds': end, 'sample_seconds': float(times[i]),
                                                 'sample_offset_seconds': float(times[i] - end), 'absolute_sample_offset_seconds': float(abs(times[i] - end)),
                                                 'position_error_m': float(errors[i]), 'exact_requested_horizon': bool(times[i] == end)})
    return result


def secondary_disagreement(case, rows, model):
    if not case['secondary_sources']:
        return {'available': False, 'reason': 'No second independent CHANDRA trajectory product selected'}
    other, provenance = read_rows(case['object_id'], [resolved(p) for p in case['secondary_sources']])
    index = {r['gpst_s']: r for r in other}
    pairs = [(r, index[r['gpst_s']]) for r in rows if r['gpst_s'] in index]
    if not pairs:
        return {'available': False, 'reason': 'No exactly shared reference-product timestamps', 'reference': provenance}
    times = np.asarray([a['gpst_s'] - model['epoch_gpst_s'] for a, b in pairs])
    errors = np.asarray([np.linalg.norm(a['position'] - b['position']) for a, b in pairs])
    return {'available': True, 'comparison': 'GBM primary versus WUM secondary positions at identical GPST epochs',
            'qualification': 'Cross-provider discrepancy; neither product is assumed exact or statistically independent of shared measurements/models',
            'primary_samples_missing_secondary': len(rows) - len(pairs), 'reference': provenance, **error_summary(times, errors)}


def compare(args, protocol):
    report_path = args.out / args.summary_name
    if report_path.exists():
        raise ValueError('Summary already exists: ' + str(report_path))
    protocol_sha = sha(args.protocol)
    cases = []
    orekit_dir = args.orekit_dir or args.out
    for case in protocol['cases']:
        if args.cases and case['case_id'] not in args.cases:
            continue
        model, rows, times, truth, provenance = load_case(case)
        engines = {}
        metadata = {}
        for backend in args.backends:
            path = args.out / ('native_' + backend + '_' + case['case_id'] + '.json')
            engines['atomos_' + backend], source_metadata, binding = engine_states(path, case, times, protocol_sha)
            metadata['atomos_' + backend] = {'source': binding, 'execution': source_metadata}
        path = orekit_dir / ('orekit_' + case['case_id'] + '.json')
        engines['orekit'], source_metadata, binding = engine_states(path, case, times, protocol_sha)
        metadata['orekit'] = {'source': binding, 'execution': source_metadata}
        scores = {}
        for name, states in engines.items():
            prediction = states[:, :3] if case['object_id'] == 'CHANDRA' else np.asarray([state_to_ecef(model, float(t), state)[:3] for t, state in zip(times, states)])
            errors = np.linalg.norm(prediction - truth, axis=1)
            scores[name] = error_summary(times, errors)
            if case['object_id'] == 'CHANDRA':
                velocity = np.linalg.norm(states[:, 3:] - np.asarray([r['velocity'] for r in rows]), axis=1)
                scores[name]['velocity_error_m_s'] = {'rms': float(np.sqrt(np.mean(velocity**2))), 'max': float(velocity.max())}
        pairs = {}
        names = list(engines)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                difference = engines[a] - engines[b]
                velocity = np.linalg.norm(difference[:, 3:], axis=1)
                pairs[a + '_versus_' + b] = {'scope': 'Same frozen model numerical state agreement; separate from external-reference forecast error',
                                             **error_summary(times, np.linalg.norm(difference[:, :3], axis=1)),
                                             'velocity_disagreement_m_s': {'rms': float(np.sqrt(np.mean(velocity**2))), 'max': float(velocity.max())}}
        cases.append({'case_id': case['case_id'], 'object_id': case['object_id'], 'orbit_class': case['orbit_class'],
                      'model_sha256': case['model_sha256'], 'physical_model_sha256': case['physical_model_sha256'],
                      'cutoff_gpst_s': model['epoch_gpst_s'], 'sample_count': len(times),
                      'reference_frames': case['reference_frames'], 'reference': provenance, 'engines': metadata,
                      'external_reference_position_error': scores, 'numerical_state_agreement': pairs,
                      'reference_product_disagreement': secondary_disagreement(case, rows, model)})
        print(json.dumps({'case_id': case['case_id'], 'position_max_m': {k: v['whole_available_arc']['max_m'] for k, v in scores.items()}}), flush=True)
    verify_protocol(args.protocol)
    save(report_path, {'schema': 'ATOMOS-OREKIT-MATCHED-FORECAST-RESULTS-R1', 'status': 'measured',
                       'created_utc': datetime.now(timezone.utc).isoformat(), 'protocol_file': relative(args.protocol), 'protocol_sha256': protocol_sha,
                       'complete_eight_case_scope': len(cases) == 8 and {c['case_id'] for c in cases} == {c['case_id'] for c in protocol['cases']},
                       'horizon_hours': HOURS, 'limits': LIMITS, 'cases': cases})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'native', 'compare', 'verify'])
    parser.add_argument('--protocol', type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT)
    parser.add_argument('--python-deps', type=Path, help='Optional directory containing the pinned PyERFA runtime')
    parser.add_argument('--backend', choices=['cpu', 'cuda'], default='cpu')
    parser.add_argument('--backends', nargs='+', choices=['cpu', 'cuda'], default=['cpu', 'cuda'])
    parser.add_argument('--cases', nargs='+', choices=[p + '_' + s for p in ('jan', 'feb') for s in OBJECTS])
    parser.add_argument('--orekit-dir', type=Path, help='Directory containing orekit_<case>.json state files')
    parser.add_argument('--summary-name', default='matched_forecast_summary.json')
    args = parser.parse_args()
    if args.python_deps:
        sys.path.insert(0, str(args.python_deps.resolve()))
    if Path(args.summary_name).name != args.summary_name:
        parser.error('--summary-name must be one filename')
    if args.action == 'prepare':
        if args.cases:
            parser.error('prepare always freezes the complete eight-case scope')
        prepare(args)
    else:
        protocol = verify_protocol(args.protocol)
        if args.action == 'native':
            native(args, protocol)
        elif args.action == 'compare':
            compare(args, protocol)
        else:
            print(json.dumps({'status': 'verified', 'frozen_inputs': len(protocol['frozen_inputs']), 'protocol_sha256': sha(args.protocol)}))


if __name__ == '__main__':
    main()
