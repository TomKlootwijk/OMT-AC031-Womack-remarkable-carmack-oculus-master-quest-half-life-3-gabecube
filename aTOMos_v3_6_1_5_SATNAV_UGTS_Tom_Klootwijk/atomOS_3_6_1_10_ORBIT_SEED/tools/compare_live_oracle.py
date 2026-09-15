"""Compare native positions to independent RTKLIB and audit live publication timing.

Spatial differences are measured outcomes; the optional maximum is an explicit
comparison tolerance, not a claim of certified positioning accuracy.
"""
from __future__ import annotations
import argparse
import bisect
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics


def stats(values):
    if not values:
        return None
    return {'minimum': min(values), 'median': statistics.median(values),
            'mean': statistics.mean(values), 'rms': math.sqrt(statistics.mean(x*x for x in values)),
            'maximum': max(values)}


def distance(a, b):
    return math.sqrt(sum((x-y)**2 for x, y in zip(a, b)))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--oracle', type=Path, required=True)
    p.add_argument('--reference-obs', type=Path, required=True,
                   help='Independent convbin RINEX containing the transmitted ARP header')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--require-live', action='store_true')
    p.add_argument('--max-oracle-distance-m', type=float)
    args = p.parse_args()
    origin = datetime(1980, 1, 6, tzinfo=timezone.utc)
    oracle = {}
    for line in args.oracle.read_text().splitlines():
        if not line or line.startswith('%'):
            continue
        parts = line.split()
        epoch = datetime.strptime(' '.join(parts[:2]), '%Y/%m/%d %H:%M:%S.%f').replace(tzinfo=timezone.utc)
        t = (epoch - origin).total_seconds()
        oracle[t] = [float(x) for x in parts[2:5]]
    header = args.reference_obs.read_text().splitlines()
    arp_line = next(line for line in header if 'APPROX POSITION XYZ' in line)
    arp = [float(arp_line[i:i+14]) for i in (0, 14, 28)]
    summary = json.loads((args.run / 'summary.json').read_text())
    trace = [json.loads(line) for line in (args.run / 'trace.jsonl').read_text().splitlines() if line]
    positions = [row for row in trace if row['result']['position_available']]
    failures = []
    comparison = []
    arp_errors = []
    if not positions:
        failures.append('no native positions')
    for row in positions:
        result = row['result']
        expected = oracle.get(result['time_gpst_s'])
        if expected is None:
            failures.append(f"no independent position for GPST {result['time_gpst_s']}")
            continue
        xyz = result['state_ecef_clock_m'][:3]
        comparison.append(distance(xyz, expected))
        arp_errors.append(distance(xyz, arp))
    if args.max_oracle_distance_m is not None and any(x > args.max_oracle_distance_m for x in comparison):
        failures.append('maximum native/oracle distance exceeds the supplied comparison tolerance')
    first_seed = trace[0]['passes'][0]['prepared'] if trace else {}
    zero_seed = (first_seed.get('receiver_seed_ecef_m') == [0., 0., 0.]
                 and first_seed.get('receiver_seed_clock_m') == 0.)
    if not zero_seed or summary.get('reference_coordinates_used') is not False:
        failures.append('cold-start zero-seed evidence failed')
    live = summary.get('source_kind') == 'live_internet_rtcm'
    timing_report = None
    if args.require_live and not live:
        failures.append('the native run is not a live Internet execution')
    if live:
        cap = summary['capture']
        timing_path = args.run / 'capture.rtcm3.timing.jsonl'
        timing = [json.loads(line) for line in timing_path.read_text().splitlines() if line]
        chunks = [row for row in timing if row['type'] == 'chunk']
        ends = [row['offset'] + row['bytes'] for row in chunks]
        raw_path = args.run / 'capture.rtcm3'
        data = raw_path.read_bytes()
        if sha(raw_path) != cap['sha256']:
            failures.append('raw stream hash differs from capture summary')
        if not chunks or chunks[0]['offset'] != 0 or ends[-1] != len(data):
            failures.append('timing chunks do not span the entire raw stream')
        if any(chunks[i]['offset'] != ends[i-1] for i in range(1, len(chunks))):
            failures.append('timing chunk byte offsets have a gap or overlap')
        frame_arrivals = {}
        index = 0
        while index + 6 <= len(data):
            if data[index] != 0xD3:
                index += 1
                continue
            size = ((data[index+1] & 3) << 8) + data[index+2] + 6
            if index + size > len(data):
                break
            end = index + size
            frame_arrivals[hashlib.sha256(data[index:end]).hexdigest()] = chunks[bisect.bisect_left(ends, end)]['utc_unix_s']
            index = end
        capture_end = next(row['utc_unix_s'] for row in reversed(timing) if row['type'] == 'capture_end')
        emitted_before_end = 0
        complete_to_publish = []
        for row in positions:
            result = row['result']
            hashes = row['raw_epoch']['source_metadata']['fragment_sha256']
            if not hashes or any(h not in frame_arrivals for h in hashes):
                failures.append(f"missing source fragment for epoch {result['epoch_id']}")
                continue
            complete_at = max(frame_arrivals[h] for h in hashes)
            emitted = result['solution_emitted_utc_unix_s']
            complete_to_publish.append(emitted - complete_at)
            if emitted < complete_at - 1e-6:
                failures.append(f"publication precedes complete input epoch {result['epoch_id']}")
            if cap['started_utc_unix_s'] <= emitted <= capture_end:
                emitted_before_end += 1
        if emitted_before_end != len(positions):
            failures.append('some position was not emitted during the live capture interval')
        timing_report = {'native_positions_emitted_before_capture_end': emitted_before_end,
                         'complete_fragment_to_publication_seconds': stats(complete_to_publish),
                         'capture_started_utc_unix_s': cap['started_utc_unix_s'],
                         'capture_ended_utc_unix_s': capture_end,
                         'timing_sha256': sha(timing_path), 'capture_sha256': sha(raw_path),
                         'measurement': 'Same-host receive/publication timing, including RTCM parsing and native execution; not satellite-to-host calibrated latency.'}
    result = {'status': 'passed' if not failures else 'failed',
              'run': str(args.run.resolve()), 'trace_sha256': sha(args.run/'trace.jsonl'),
              'oracle_sha256': sha(args.oracle), 'reference_obs_sha256': sha(args.reference_obs),
              'native_epoch_statuses': dict(Counter(row['result']['status'] for row in trace)),
              'matched_position_epochs': len(comparison), 'unavailable_epochs': len(trace)-len(positions),
              'native_oracle_distance_m': stats(comparison), 'maximum_allowed_oracle_distance_m': args.max_oracle_distance_m,
              'native_advertised_arp_distance_m': stats(arp_errors), 'advertised_arp_ecef_m': arp,
              'reference_definition': 'Stream-supplied RTCM1005/1006 antenna reference point through independent convbin header, not independent survey truth.',
              'zero_initial_seed_verified_in_first_prepared_pass': zero_seed,
              'live_publication_audit': timing_report,
              'warmup_note': 'Native obtains ephemerides in receive order; offline RTKLIB sees all ephemerides. Unavailable native epochs are not position comparisons.',
              'failures': failures}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 0 if not failures else 1


if __name__ == '__main__':
    raise SystemExit(main())
