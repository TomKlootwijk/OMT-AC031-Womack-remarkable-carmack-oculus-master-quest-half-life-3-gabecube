"""Compare native Python RTCM decoding with independently converted RTKLIB RINEX.

The supplied RINEX files must be outputs of the independent published convbin
executable. RINEX coordinates/ranges are rounded, so a 0.51 mm code tolerance
covers three-decimal RINEX serialization; ephemeris fields allow its printed
decimal precision. This verifies decoded physical values, not just CRC framing.
"""
from __future__ import annotations
import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
from live_gnss import read_rinex_nav, iter_rinex_obs
from live_rtcm import RTCMDecoder, ephemeris_from_event, epoch_from_event


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rtcm', type=Path, required=True)
    p.add_argument('--obs', type=Path, required=True)
    p.add_argument('--nav', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    reference_epochs = {ep.time_gpst_s: ep for ep in iter_rinex_obs(args.obs)}
    if not reference_epochs:
        raise ValueError('independent observation file contains no GPS epochs')
    decoder = RTCMDecoder(min(reference_epochs))
    events = decoder.feed(args.rtcm.read_bytes()) + decoder.finish()
    decoded_eph = [ephemeris_from_event(e) for e in events if e['type'] == 'ephemeris']
    reference_nav = read_rinex_nav(args.nav)
    failures = []
    eph_matches = numeric_fields = 0
    for reference in reference_nav.ephemerides:
        candidates = [e for e in decoded_eph if (e.prn, e.iode, e.toe) ==
                      (reference.prn, reference.iode, reference.toe)]
        if not candidates:
            failures.append({'kind': 'missing_ephemeris', 'prn': reference.prn, 'iode': reference.iode})
            continue
        eph_matches += 1
        actual, expected = asdict(candidates[0]), asdict(reference)
        for name in actual.keys() & expected.keys():
            if isinstance(actual[name], (int, float)) and not isinstance(actual[name], bool):
                numeric_fields += 1
                tolerance = max(1e-11, abs(expected[name]) * 5e-12)
                if abs(actual[name] - expected[name]) > tolerance:
                    failures.append({'kind': 'ephemeris_field', 'prn': reference.prn, 'field': name,
                                     'decoded': actual[name], 'oracle': expected[name]})
    range_errors = []
    matched_times = set()
    native_only_times = []
    for event in events:
        if event['type'] != 'epoch':
            continue
        epoch = epoch_from_event(event)
        if epoch.time_gpst_s not in reference_epochs:
            native_only_times.append(epoch.time_gpst_s)
            continue
        matched_times.add(epoch.time_gpst_s)
        actual = {ob.prn: ob.pseudorange_m for ob in epoch.observations}
        expected = {ob.prn: ob.pseudorange_m for ob in reference_epochs[epoch.time_gpst_s].observations}
        if actual.keys() != expected.keys():
            failures.append({'kind': 'satellite_set', 'time_gpst_s': epoch.time_gpst_s,
                             'decoded': sorted(actual), 'oracle': sorted(expected)})
        for prn in actual.keys() & expected.keys():
            delta = abs(actual[prn] - expected[prn])
            range_errors.append(delta)
            if delta > 0.00051:
                failures.append({'kind': 'code_range', 'time_gpst_s': epoch.time_gpst_s,
                                 'prn': prn, 'difference_m': delta})
    if matched_times != reference_epochs.keys():
        failures.append({'kind': 'missing_reference_epochs',
                         'times_gpst_s': sorted(reference_epochs.keys() - matched_times)})
    if native_only_times:
        failures.append({'kind': 'unexpected_native_epochs', 'times_gpst_s': native_only_times})
    if not eph_matches or not range_errors:
        failures.append({'kind': 'empty_comparison'})
    result = {'status': 'passed' if not failures else 'failed',
              'inputs': {key: {'path': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                         for key, path in [('rtcm', args.rtcm), ('rtklib_rinex_obs', args.obs), ('rtklib_rinex_nav', args.nav)]},
              'event_counts': dict(Counter(e['type'] for e in events)),
              'matched_ephemerides': eph_matches, 'ephemeris_numeric_fields_compared': numeric_fields,
              'matched_epochs': len(matched_times), 'code_ranges_compared': len(range_errors),
              'maximum_code_difference_m': max(range_errors, default=None),
              'code_tolerance_m': 0.00051,
              'ephemeris_tolerance': 'max(1e-11 absolute,5e-12 relative), matching printed RINEX decimal precision',
              'failures': failures}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 0 if not failures else 1


if __name__ == '__main__':
    raise SystemExit(main())
