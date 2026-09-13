"""Verify prepared novel knowledge, run native domains/chains, then hand off a bank.

The active_bank.json pointer is the publication authority. This is a host epoch
handoff; immutable pages switch within each native chain. No cache pinning or
filesystem crash-durability claim is made. Oracle independence remains declared.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from knowledge_admission import admit_candidates, MAX_BANK_BYTES, MAX_JSON_BYTES
from program_bank_reference import decode_bank, evaluate, replay, verify_trace
from validate_program_bank import verify_injected_rejection

STUDY_SOURCES = ['experiments/program_bank.cu', 'include/atomos/program_bank.hpp',
                 'include/atomos/sdf_nor.hpp', 'python/program_bank.py',
                 'python/program_bank_reference.py', 'tools/validate_program_bank.py',
                 'include/atomos/publication.hpp', 'include/atomos/klein.hpp',
                 'include/atomos/host.hpp', 'include/atomos/core.hpp',
                 'include/atomos/universal.hpp', 'include/atomos/packed_atlas.hpp', 'cuda/kernel.cu']


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def bounded_bytes(path, limit):
    path = Path(path)
    if path.stat().st_size > limit:
        raise ValueError('artifact byte bound: ' + str(path))
    raw = path.read_bytes()
    if len(raw) > limit:
        raise ValueError('artifact byte bound: ' + str(path))
    return raw


def read_json(path):
    return json.loads(bounded_bytes(path, MAX_JSON_BYTES).decode('utf-8'))


def require_unchanged(bindings):
    for name, expected in bindings.items():
        if not Path(name).is_file() or file_hash(name) != expected:
            raise ValueError('verification dependency changed: ' + name)


def preflight_admission(base_bank, admission):
    """Reproduce admission from retained bytes before native work or publication."""
    base_bank, admission = Path(base_bank).resolve(), Path(admission).resolve()
    files = {'base/bank.bin': base_bank,
             'base/manifest.json': base_bank.parent / 'manifest.json',
             'proposal/bank.bin': admission / 'bank.bin',
             'proposal/manifest.json': admission / 'manifest.json',
             'proposal/admission.json': admission / 'admission.json',
             'proposal/candidates.json': admission / 'candidates.json'}
    retained = {name: bounded_bytes(path, MAX_BANK_BYTES if name.endswith('.bin') else MAX_JSON_BYTES)
                for name, path in files.items()}
    bindings = {str(files[name]): hashlib.sha256(raw).hexdigest() for name, raw in retained.items()}
    receipt = json.loads(retained['proposal/admission.json'])
    request = json.loads(retained['proposal/candidates.json'])
    if (receipt.get('schema') != 'atomos-knowledge-admission-v1' or
            receipt.get('status') != 'prepared' or
            receipt.get('new_active_bank_published') is not False or
            receipt.get('gpu_execution') != 'not_run'):
        raise ValueError('admission is not an unpublished prepared proposal')
    for field, key in [('base_bank_sha256', 'base/bank.bin'),
                       ('base_manifest_sha256', 'base/manifest.json'),
                       ('proposed_bank_sha256', 'proposal/bank.bin')]:
        if receipt.get(field) != hashlib.sha256(retained[key]).hexdigest():
            raise ValueError('admission artifact hash mismatch: ' + field)
    if receipt.get('request_sha256') != hashlib.sha256(canonical(request)).hexdigest():
        raise ValueError('admission oracle/request hash mismatch')
    limits = receipt.get('limits')
    if not isinstance(limits, dict) or type(limits.get('candidate_limit')) is not int:
        raise ValueError('admission candidate limit missing')
    with tempfile.TemporaryDirectory(prefix='atomos_knowledge_verify_') as temporary:
        stage = Path(temporary)
        for name, raw in retained.items():
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        reproduced = admit_candidates(stage / 'base/bank.bin', request, stage / 'reproduced',
                                      candidate_limit=limits['candidate_limit'])
        if reproduced != receipt:
            raise ValueError('admission receipt does not reproduce from supplied evidence')
        if (stage / 'reproduced/bank.bin').read_bytes() != retained['proposal/bank.bin']:
            raise ValueError('proposed bank does not reproduce from candidates')
        if read_json(stage / 'reproduced/manifest.json') != json.loads(retained['proposal/manifest.json']):
            raise ValueError('proposed manifest does not reproduce from admitted provenance')
        before = decode_bank(stage / 'base/bank.bin', stage / 'base/manifest.json')
        after = decode_bank(stage / 'proposal/bank.bin', stage / 'proposal/manifest.json')
    old_raw, new_raw = retained['base/bank.bin'], retained['proposal/bank.bin']
    if (old_raw[:20] != new_raw[:20] or old_raw[24:56] != new_raw[24:56] or
            old_raw[56:] != new_raw[56:len(old_raw)]):
        raise ValueError('admission changed base header or existing program bytes')
    preserved = 0
    for old, new in zip(before['capsules'], after['capsules']):
        if (old['input_bits'], old['output_bits']) != (new['input_bits'], new['output_bits']):
            raise ValueError('admission changed a base interface')
        for value in range(1 << old['input_bits']):
            if evaluate(old, value) != evaluate(new, value):
                raise ValueError('admission changed a base function')
            preserved += 1
    oracles = {oracle['id']: oracle for oracle in request['oracles']}
    accepted = [decision for decision in receipt['decisions'] if decision['status'] == 'accepted']
    if not accepted:
        raise ValueError('no admitted novelty to publish')
    checked = 0
    for decision in accepted:
        capsule, oracle = after['capsules'][decision['slot']], oracles[decision['oracle_id']]
        if (capsule['input_bits'], capsule['output_bits']) != (oracle['input_bits'], oracle['output_bits']):
            raise ValueError('admitted oracle interface mismatch')
        for case in oracle['cases']:
            if evaluate(capsule, case['input']) != case['output']:
                raise ValueError('independent packed oracle replay failed')
            checked += 1
    require_unchanged(bindings)
    return dict(before=before, after=after, admission=receipt, bindings=bindings,
                accepted_slots=[decision['slot'] for decision in accepted],
                preserved_base_cases=preserved, independently_checked_oracle_cases=checked)


def verify_native(folder, bank, *, bank_hash, atlas_hash, layout, mode, first, value, hops):
    folder = Path(folder)
    receipt = read_json(folder / 'summary.json')
    expected = dict(schema='atomOS-program-bank-runtime-v1', status='passed', accepted=True,
                    committed=True, execution_mode=mode, layout=layout, injection='none',
                    initial_slot=first, input_initial=value, hops=hops, hops_executed=hops,
                    kernel_error=0, topology='klein_m1_angular_twist')
    for key, wanted in expected.items():
        if type(receipt.get(key)) is not type(wanted) or receipt[key] != wanted:
            raise ValueError('native receipt mismatch: ' + key)
    if not (folder / 'COMMITTED').is_file() or (folder / 'REJECTED').exists():
        raise ValueError('native run lacks exclusive committed evidence')
    if file_hash(folder / 'bank.bin') != bank_hash or file_hash(folder / 'operators.atlas') != atlas_hash:
        raise ValueError('native copied inputs differ from bound proposal')
    verification = verify_trace(folder / 'trace.csv', bank, value, hops, first, mode)
    if mode == 'chain':
        last = replay(bank, value, hops, first)[-1]
    else:
        last = dict(next_slot=bank['capsules'][first]['next_slot'],
                    output=evaluate(bank['capsules'][first], hops - 1))
    for field, wanted in [('final_program_id', last['next_slot']), ('committed_program_id', last['next_slot']),
                          ('final_input', last['output']), ('committed_input', last['output'])]:
        if type(receipt.get(field)) is not int or receipt[field] != wanted:
            raise ValueError('native committed state mismatch: ' + field)
    if (type(receipt.get('sm_before')) is not int or type(receipt.get('sm_after')) is not int or
            receipt['sm_before'] < 0 or receipt['sm_before'] != receipt['sm_after']):
        raise ValueError('native same-SM receipt mismatch')
    return dict(receipt=receipt, verification=verification)


def verify_domain_study(folder, bank, *, bank_hash, atlas_hash, exe_hash, sanitizer):
    folder = Path(folder)
    study = read_json(folder / 'study.json')
    if (study.get('schema') != 'atomos-program-bank-study-v1' or study.get('status') != 'passed' or
            study.get('domain_only') is not True or study.get('smoke_only') is not False or
            study.get('executable_sha256') != exe_hash or study.get('bank_file_sha256') != bank_hash or
            study.get('atlas_sha256') != atlas_hash):
        raise ValueError('domain study lacks complete bound native evidence')
    expected = {}
    for layout in ('linear', 'morton8'):
        for slot in range(bank['capsule_count']):
            expected[f'domain_{layout}_{slot}'] = (layout, slot, 'ordinary')
        if sanitizer:
            expected[f'memcheck_domain_{layout}'] = (layout, bank['capsule_count'] - 1, 'memcheck')
    runs = study.get('runs', [])
    if (not isinstance(runs, list) or len(runs) != len(expected) or
            len({run.get('label') for run in runs}) != len(expected) or
            {run.get('label') for run in runs} != set(expected) or study.get('native_runs') != len(expected)):
        raise ValueError('domain study is missing or duplicating required native runs')
    source_hashes = study.get('source_hashes')
    if not isinstance(source_hashes, dict) or set(source_hashes) != set(STUDY_SOURCES):
        raise ValueError('domain study source bindings are incomplete')
    require_unchanged({str(ROOT / name): digest for name, digest in source_hashes.items()})
    evaluations = 0
    for run in runs:
        layout, slot, kind = expected[run['label']]
        if type(run.get('exit_code')) is not int or run['exit_code'] != 0 or run.get('kind') != kind:
            raise ValueError('domain study contains a failed or incorrect run')
        if kind == 'memcheck':
            command = run.get('command', [])
            log = bounded_bytes(folder / (run['label'] + '.log'), MAX_JSON_BYTES).decode('utf-8')
            summaries = re.findall(r'ERROR SUMMARY:\s*(\d+) errors?', log)
            if (len(command) < 6 or Path(command[0]).name.lower() not in ('compute-sanitizer', 'compute-sanitizer.exe') or
                    command[1:5] != ['--tool', 'memcheck', '--error-exitcode', '2'] or
                    'COMPUTE-SANITIZER' not in log or not summaries or any(int(n) for n in summaries)):
                raise ValueError('requested memcheck lacks tool invocation and clean completion evidence')
        hops = 1 << bank['capsules'][slot]['input_bits']
        verified = verify_native(folder / run['label'], bank, bank_hash=bank_hash, atlas_hash=atlas_hash,
                                 layout=layout, mode='domain', first=slot, value=0, hops=hops)
        if run.get('receipt') != verified['receipt']:
            raise ValueError('domain summary changed after study verification')
        evaluations += hops
    return dict(native_runs=len(runs), program_evaluations=evaluations,
                sanitizer_runs=2 if sanitizer else 0, study_sha256=file_hash(folder / 'study.json'))


def save_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def publish_pointer(path, value, *, bindings, expected_previous):
    """Fail closed on changed dependencies or state before the atomic handoff."""
    path = Path(path)
    require_unchanged(bindings)
    if path.read_bytes() != expected_previous:
        raise ValueError('active bank changed during proposal verification')
    temporary = path.with_suffix('.json.partial')
    with temporary.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(value, indent=2) + '\n')
    require_unchanged(bindings)
    if path.read_bytes() != expected_previous:
        raise ValueError('active bank changed before final handoff')
    os.replace(temporary, path)


def checked_switch(visited, first, base_count, require_switch=False):
    if first not in visited:
        raise ValueError('chain did not execute the admitted initial slot')
    switched = any(slot < base_count for slot in visited)
    if require_switch and not switched:
        raise ValueError('requested chain did not switch to a retained program texture')
    return switched


def validate_and_publish(*, exe, base_bank, admission, atlas, out, sanitizer=False, require_switch=False):
    exe, base_bank, admission, atlas, out = [Path(p).resolve() for p in (exe, base_bank, admission, atlas, out)]
    if out.exists():
        raise ValueError('refusing to overwrite verification output')
    checked = preflight_admission(base_bank, admission)
    proposal = admission / 'bank.bin'
    bindings = checked['bindings']
    sources = ['tools/validate_knowledge_bank.py', 'tools/validate_program_bank.py',
               'python/knowledge_admission.py', 'python/program_bank.py', 'python/program_bank_reference.py',
               'experiments/program_bank.cu', 'include/atomos/program_bank.hpp', 'include/atomos/sdf_nor.hpp',
               'include/atomos/publication.hpp', 'include/atomos/klein.hpp', 'include/atomos/host.hpp',
               'include/atomos/core.hpp', 'include/atomos/universal.hpp', 'include/atomos/packed_atlas.hpp',
               'cuda/kernel.cu', 'tools/validate.py', 'tools/profile_cache.py']
    bindings.update({str(path): file_hash(path) for path in [exe, atlas] + [ROOT / name for name in sources]})
    exe_hash, atlas_hash, bank_hash = bindings[str(exe)], bindings[str(atlas)], bindings[str(proposal)]
    out.mkdir(parents=True, exist_ok=False)
    active = out / 'active_bank.json'
    save_json(active, dict(bank=str(base_bank), sha256=bindings[str(base_bank)], publication_sequence=0))
    active_before = active.read_bytes()
    report = dict(schema='atomos-knowledge-publication-v1', status='running',
                  scope='oracle-checked finite knowledge admission and host epoch handoff',
                  dependency_sha256=bindings, accepted_slots=checked['accepted_slots'],
                  preserved_base_cases=checked['preserved_base_cases'],
                  independently_checked_oracle_cases=checked['independently_checked_oracle_cases'],
                  runs=[], new_active_bank_published=False, cache_pinning=False,
                  cache_residency_measurement='not_run in this publication check',
                  oracle_origin_and_truth='not_authenticated; exact conformance to supplied cases',
                  publication_protocol='Prepared evidence and hash marker precede atomic active_bank.json replacement; pointer is authority',
                  marker_valid_only_when_active_hash_matches=True, filesystem_crash_durability='not_claimed')
    def save():
        save_json(out / 'publication.json', report)
    def run(label, command):
        require_unchanged(bindings)
        with (out / (label + '.log')).open('w', encoding='utf-8') as log:
            result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        record = dict(label=label, command=list(map(str, command)), exit_code=result.returncode)
        report['runs'].append(record)
        save()
        require_unchanged(bindings)
        return record
    save()
    try:
        command = [sys.executable, str(ROOT / 'tools/validate_program_bank.py'), '--exe', str(exe),
                   '--bank', str(proposal), '--atlas', str(atlas), '--out', str(out / 'domains'), '--domain-only']
        if sanitizer:
            command.append('--sanitizer')
        domain_run = run('domains', command)
        if domain_run['exit_code']:
            raise RuntimeError('native domain study failed or requested tool unavailable')
        report['domain_verification'] = verify_domain_study(
            out / 'domains', checked['after'], bank_hash=bank_hash, atlas_hash=atlas_hash,
            exe_hash=exe_hash, sanitizer=sanitizer)
        first, hops = checked['accepted_slots'][0], 24
        value = min(7, (1 << checked['after']['capsules'][first]['input_bits']) - 1)
        chain_checks = []
        for layout in ('linear', 'morton8'):
            label = 'chain_' + layout
            command = [str(exe), '--bank', str(proposal), '--atlas', str(atlas), '--out', str(out / label),
                       '--layout', layout, '--mode', 'chain', '--initial-slot', str(first),
                       '--input', str(value), '--hops', str(hops), '--inject', 'none']
            record = run(label, command)
            if record['exit_code']:
                raise RuntimeError('native knowledge chain failed: ' + layout)
            verified = verify_native(out / label, checked['after'], bank_hash=bank_hash, atlas_hash=atlas_hash,
                                     layout=layout, mode='chain', first=first, value=value, hops=hops)
            with (out / label / 'trace.csv').open(encoding='utf-8', newline='') as stream:
                visited = sorted({int(row['program_id']) for row in csv.DictReader(stream)})
            switched = checked_switch(visited, first, checked['before']['capsule_count'], require_switch)
            verified.update(layout=layout, visited_program_slots=visited,
                            switched_between_new_and_retained_textures=switched)
            chain_checks.append(verified)
        report['chains'] = chain_checks
        label = 'reject_new_output'
        command = [str(exe), '--bank', str(proposal), '--atlas', str(atlas), '--out', str(out / label),
                   '--layout', 'morton8', '--mode', 'chain', '--initial-slot', str(first),
                   '--input', str(value), '--hops', str(hops), '--inject', 'output']
        rejected = run(label, command)
        report['rejection'] = verify_injected_rejection(
            out / label, rejected['exit_code'], bank_path=proposal, atlas_path=atlas,
            initial_slot=first, input_value=value, injection='output')
        if active.read_bytes() != active_before:
            raise ValueError('rejected proposal changed active bank pointer')
        report['rejected_preserved_active_bank'] = True
        require_unchanged(bindings)
        # Bind raw execution evidence before its final replay. These files are
        # immutable; the separately written report/pointer are not self-hashed.
        bindings.update({str(path): file_hash(path) for path in out.rglob('*') if path.is_file()
                         and path not in (active, out / 'publication.json')})
        # Recheck accepted evidence immediately before publication as well.
        report['domain_verification'] = verify_domain_study(
            out / 'domains', checked['after'], bank_hash=bank_hash, atlas_hash=atlas_hash,
            exe_hash=exe_hash, sanitizer=sanitizer)
        for layout in ('linear', 'morton8'):
            verify_native(out / ('chain_' + layout), checked['after'], bank_hash=bank_hash, atlas_hash=atlas_hash,
                          layout=layout, mode='chain', first=first, value=value, hops=hops)
        verify_injected_rejection(out / label, rejected['exit_code'], bank_path=proposal, atlas_path=atlas,
                                  initial_slot=first, input_value=value, injection='output')
        require_unchanged(bindings)
        report.update(status='verified_pending_handoff', proposed_bank_sha256=bank_hash,
                      native_runs=report['domain_verification']['native_runs'] + 3,
                      accepted_program_evaluations=report['domain_verification']['program_evaluations'] + 2 * hops)
        save()
        (out / 'VERIFIED').write_text(bank_hash + '\n', encoding='utf-8')
        (out / 'COMMITTED').write_text(bank_hash + '\n', encoding='utf-8')
        handoff_bindings = dict(bindings)
        handoff_bindings.update({str(out / name): file_hash(out / name)
                                for name in ('publication.json', 'VERIFIED', 'COMMITTED')})
        publish_pointer(active, dict(bank=str(proposal), sha256=bank_hash, publication_sequence=1),
                        bindings=handoff_bindings, expected_previous=active_before)
        report.update(status='passed', new_active_bank_published=True, active_bank_sha256=bank_hash)
        save()
        return report
    except Exception as error:
        report.update(status='failed', reason=str(error),
                      active_pointer_retained=active.read_bytes() == active_before)
        save()
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('exe', 'base-bank', 'admission', 'atlas', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--sanitizer', action='store_true')
    parser.add_argument('--require-switch', action='store_true',
                        help='Require this demonstration chain to visit retained and admitted pages; self-links are otherwise valid')
    args = parser.parse_args(argv)
    report = validate_and_publish(exe=args.exe, base_bank=args.base_bank, admission=args.admission,
                                  atlas=args.atlas, out=args.out, sanitizer=args.sanitizer,
                                  require_switch=args.require_switch)
    print(json.dumps(dict(status=report['status'], native_runs=report['native_runs'],
                          accepted_program_evaluations=report['accepted_program_evaluations'],
                          publication=str(args.out / 'publication.json'))))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
