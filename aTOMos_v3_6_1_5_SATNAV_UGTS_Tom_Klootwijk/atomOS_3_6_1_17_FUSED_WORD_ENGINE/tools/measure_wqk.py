#!/usr/bin/env python3
"""Paired native word-machine runs; this is not an S2 or saturation benchmark."""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import statistics
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', required=True, type=Path)
    parser.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args()
    if not 3 <= args.repeats <= 15:
        parser.error('repeats must be 3..15')
    executable = args.executable.resolve()
    program = ROOT / 'examples/wqk_feedback.tmg'
    cases = []
    for feedback in ('none', 'copy32'):
        for lanes in (1, 4096, 262144):
            trials = {'texture': [], 'global': []}
            for repeat in range(args.repeats):
                order = ('texture', 'global') if repeat % 2 == 0 else ('global', 'texture')
                for fetch in order:
                    command = [str(executable), '--program', str(program), '--lanes', str(lanes),
                               '--steps', '96', '--fetch', fetch, '--feedback', feedback]
                    run = subprocess.run(command, check=True, capture_output=True, text=True)
                    result = json.loads(run.stdout)
                    if (result['status'] != 'completed' or result['vm_fault_lanes']
                            or result['feedback_fault_lanes']):
                        raise ValueError('runtime fault: ' + repr(command))
                    if feedback == 'copy32' and result['total_accepted_feedback_emissions'] != lanes * 48:
                        raise ValueError('unexpected executed-EMIT total')
                    trials[fetch].append(result)
            hashes = {r['hash64'] for values in trials.values() for r in values}
            first_lanes = {json.dumps(r['first_lane'], sort_keys=True)
                           for values in trials.values() for r in values}
            if len(hashes) != 1 or len(first_lanes) != 1:
                raise ValueError('matched paths or repeated runs disagree')
            medians = {fetch: {key: statistics.median(r['timings_ms'][key] for r in values)
                               for key in values[0]['timings_ms']}
                       for fetch, values in trials.items()}
            case = {'feedback': feedback, 'lanes': lanes, 'steps': 96,
                    'matching_hash64_and_first_lane': True, 'medians_ms': medians, 'trials': trials}
            cases.append(case)
            print(json.dumps({'feedback': feedback, 'lanes': lanes, 'medians_ms': medians}), flush=True)
    fixture = json.loads((ROOT / 'review/wqk_fixture_reference.json').read_text(encoding='utf-8'))
    native = json.loads((ROOT / 'review/r16_run_reference.json').read_text(encoding='utf-8'))
    expected = fixture['rows'][-1]
    if native['first_lane']['state_words_u32'] != expected['state_words']:
        raise ValueError('runner first lane differs from independent 24-step Python trace')
    if [int(x, 16) for x in native['first_lane']['feedback_words_u64_hex']] != expected['word_state']:
        raise ValueError('runner feedback differs from independent Python trace')
    report = {'profile': 'ATOMOS-WQK-PAIRED-RUNS-R1',
              'captured_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'program_sha256': hashlib.sha256(program.read_bytes()).hexdigest(),
              'executable_sha256': hashlib.sha256(executable.read_bytes()).hexdigest(),
              'repeats': args.repeats, 'separate_process_each_trial': True,
              'gpu_jobs_serialized': True, 'warmup': 'none; each process includes cold setup in host_complete',
              'workload': 'same three-cell RADIX/EMIT literal program; every lane starts identically',
              'scope': 'six finite word-machine cases; no S2 output, cache-hit, DRAM-bandwidth or saturation claim',
              'equality': 'full-array noncryptographic FNV-1a-64 digests plus exact first-lane fields; independent exhaustive small native checks are separate',
              'independent_24_step_runner_reference_match': True,
              'cases': cases}
    (ROOT / 'review/wqk_paired_runs.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
