"""Answer bounded typed commands by executing a verified knowledge texture page."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from knowledge_queries import (decode_answer, load_registry, plan_query, public_registry,
                               require_unchanged, sha)
from validate_knowledge_bank import STUDY_SOURCES, verify_native


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def execute_query(*, bank, query, exe=None, atlas=None, out=None):
    registry = load_registry(bank)
    plan = plan_query(registry, query)
    if plan['status'] == 'unknown':
        return plan
    if exe is None or atlas is None or out is None:
        raise ValueError('a supported query requires --exe, --atlas and a fresh --out directory')
    exe, atlas, out = [Path(p).resolve() for p in (exe, atlas, out)]
    if out.exists():
        raise ValueError('refusing to overwrite native query evidence')
    bindings = dict(registry['bindings'])
    sources = sorted(set(STUDY_SOURCES + ['tools/query_knowledge.py', 'tools/validate_knowledge_bank.py',
                                         'tools/profile_cache.py', 'tools/validate.py']))
    bindings.update({str(path): sha(path) for path in [exe, atlas] + [ROOT / name for name in sources]})
    require_unchanged(bindings)
    out.mkdir(parents=True, exist_ok=False)
    report = dict(plan, status='running', answer=None, dependency_sha256=bindings,
                  output_source='native texture program execution; CPU oracle checks the result',
                  scope='bounded typed command grammar; no language-model inference or general natural-language understanding')
    save(out / 'query.json', report)
    capability = plan['capability']
    command = [str(exe), '--bank', registry['bank_path'], '--atlas', str(atlas), '--out', str(out / 'native'),
               '--layout', 'morton8', '--mode', 'chain', '--initial-slot', str(capability['program_id']),
               '--input', str(plan['packed_input']), '--hops', '1', '--inject', 'none']
    try:
        started = time.perf_counter()
        report['gpu_execution'] = 'attempted'
        with (out / 'native.log').open('w', encoding='utf-8') as log:
            result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        report['native_command'] = command
        report['exit_code'] = result.returncode
        report['wall_seconds'] = time.perf_counter() - started
        save(out / 'query.json', report)
        if result.returncode:
            raise RuntimeError('native knowledge query failed')
        require_unchanged(bindings)
        evidence = {str(path): sha(path) for path in (out / 'native').rglob('*') if path.is_file()}
        evidence[str(out / 'native.log')] = sha(out / 'native.log')
        verified = verify_native(out / 'native', registry['bank'], bank_hash=bindings[registry['bank_path']],
                                 atlas_hash=bindings[str(atlas)], layout='morton8', mode='chain',
                                 first=capability['program_id'], value=plan['packed_input'], hops=1)
        output = verified['receipt']['committed_input']
        decoded = decode_answer(plan, output)
        require_unchanged(bindings)
        require_unchanged(evidence)
        report.update(decoded, status='answered', gpu_execution='run_and_independently_verified',
                      packed_output=output, native_verification=verified,
                      trace_path=str(out / 'native/trace.csv'), evidence_sha256=evidence)
        save(out / 'query.json', report)
        return report
    except Exception as error:
        report.update(status='failed', reason=str(error), answer=None)
        save(out / 'query.json', report)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bank', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--list', action='store_true')
    mode.add_argument('--query')
    parser.add_argument('--exe', type=Path)
    parser.add_argument('--atlas', type=Path)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args(argv)
    if args.list:
        result = public_registry(load_registry(args.bank))
    else:
        result = execute_query(bank=args.bank, query=args.query, exe=args.exe, atlas=args.atlas, out=args.out)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
