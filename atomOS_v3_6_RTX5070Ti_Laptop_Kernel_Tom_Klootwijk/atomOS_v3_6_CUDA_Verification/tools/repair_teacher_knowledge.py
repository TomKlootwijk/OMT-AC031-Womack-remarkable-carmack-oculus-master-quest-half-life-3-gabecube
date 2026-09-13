"""Bounded local teacher repair using one actual counterexample per round.

Only explicit run()/CLI invocation performs inference. Original integer oracles
remain unchanged; model text is parsed as data and never executed. Correct
repairs still require semantic novelty and separate native publication.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
import re
import sys
import time

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
import acquire_teacher_knowledge as acquisition_api
import compile_teacher_knowledge as compiler
import knowledge_admission as admission
from program_bank_reference import decode_bank, evaluate
import teacher_expression_frontend as frontend
import teacher_knowledge as original

SCHEMA = 'atomos-bounded-teacher-repair-v1'
ENDPOINTS = ('http://127.0.0.1:11434', 'http://localhost:11434')
sha = acquisition_api.sha
save = compiler.save
require_unchanged = acquisition_api.require_unchanged


def retain_bytes(path, raw, bindings):
    """Bind the bytes held in memory, rather than rereading a mutable output."""
    path = Path(path).resolve()
    path.write_bytes(raw)
    bindings[str(path)] = compiler.sha(raw)


def retain_json(path, value, bindings):
    retain_bytes(path, (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode('utf-8'), bindings)


def semantic_review(raw, identity):
    """The independent packed-program evaluator is checked against arithmetic."""
    try:
        parsed = frontend.parse_response(raw, identity)
    except (ValueError, TypeError, SyntaxError) as error:
        return dict(status='invalid_expression', reason=str(error), verified_cases=0)
    circuit = parsed['circuit']
    errors = []
    for value in range(1 << circuit['input_bits']):
        expected, actual = original.scalar_oracle(identity, value), evaluate(circuit, value)
        if actual != expected:
            errors.append(dict(input=value, expected=expected, actual=actual))
    return dict(status='incorrect' if errors else 'oracle_correct',
                verified_cases=1 << circuit['input_bits'], mismatch_count=len(errors),
                counterexample=errors[0] if errors else None,
                semantic_sha256=admission.semantic_signature(circuit))


def checked_options(request):
    options = request.get('options')
    if (not isinstance(options, dict) or set(options) != {'temperature', 'seed', 'num_ctx', 'num_predict'} or
            type(options['temperature']) not in (int, float) or options['temperature'] != 0 or
            type(options['seed']) is not int or options['seed'] != 7 or
            type(options['num_ctx']) is not int or options['num_ctx'] != 4096 or
            type(options['num_predict']) is not int or not 128 <= options['num_predict'] <= 8192 or
            ('think' in request and request['think'] is not False)):
        raise ValueError('repair requires unchanged bounded deterministic acquisition options')
    return copy.deepcopy(options)


def make_request(task, correction):
    request = dict(model=task['model']['ollama_model'], stream=False,
                   format=frontend.response_format(task['profile_id']), keep_alive='2m',
                   messages=[dict(role='user', content=correction['prompt'])], options=task['options'])
    if task['disable_thinking']:
        request['think'] = False
    return request


def prepare(*, curriculum, acquisition, base_bank, max_rounds):
    if type(max_rounds) is not int or not 1 <= max_rounds <= frontend.MAX_REPAIR_ROUNDS:
        raise ValueError('max_rounds must be 1 or 2')
    curriculum, acquisition, base_bank = [Path(p).resolve() for p in (curriculum, acquisition, base_bank)]
    checked = compiler.verify_acquisition(curriculum, acquisition, frontend='boolean-expression')
    frozen = frontend.load_curriculum(curriculum)
    bindings = dict(checked['bindings'])
    paths = [base_bank, base_bank.parent / 'manifest.json', Path(__file__),
             ROOT / 'tools/compile_teacher_knowledge.py', ROOT / 'python/program_bank_reference.py']
    bindings.update({str(p.resolve()): sha(p) for p in paths})
    if frozen['curriculum_sha256'] != checked['curriculum_sha256']:
        raise ValueError('curriculum changed between verification and repair preparation')
    bank = decode_bank(base_bank, base_bank.parent / 'manifest.json')
    present = set()
    for identity, profile in frozen['profiles'].items():
        for capsule in bank['capsules']:
            if ((capsule['input_bits'], capsule['output_bits']) == (profile['input_bits'], profile['output_bits']) and
                    all(evaluate(capsule, x) == original.scalar_oracle(identity, x) for x in range(1 << profile['input_bits']))):
                present.add(identity)
                break
    models = {m['id']: m for m in checked['acquisition']['teachers']}
    tasks, decisions = [], []
    for verified in checked['verified_responses']:
        identity, teacher_id = verified['profile_id'], verified['teacher_id']
        raw = checked['snapshots'][verified['relative_paths']['response']]
        request = compiler.decode_json(checked['snapshots'][verified['relative_paths']['request']])
        review = semantic_review(raw, identity)
        decision = dict(teacher_id=teacher_id, profile_id=identity, original_review=review,
                        original_response_sha256=compiler.sha(raw))
        if identity in present:
            decision.update(status='skipped', reason='exact_function_already_present_in_base')
        elif review['status'] != 'incorrect':
            decision.update(status='skipped', reason='original_response_' + review['status'])
        else:
            model = models[teacher_id]
            if (model.get('model_revision_status') != 'pinned_huggingface_commit' or
                    not isinstance(model.get('model_revision'), str) or
                    re.fullmatch('[0-9a-f]{40}', model['model_revision']) is None):
                raise ValueError('repair requires a pinned public model revision')
            tasks.append(dict(teacher_id=teacher_id, profile_id=identity, model=copy.deepcopy(model),
                              options=checked_options(request), disable_thinking='think' in request,
                              previous_raw=raw, initial_counterexample=review['counterexample']))
            decision.update(status='selected', reason='actual_oracle_mismatch_and_absent_function')
        decisions.append(decision)
    require_unchanged(bindings)
    return dict(checked=checked, bindings=bindings, tasks=tasks, decisions=decisions,
                endpoint=checked['acquisition']['endpoint'], curriculum=curriculum, base_bank=base_bank)


def verify_round(folder, *, task, round_index, previous_path, runtime, show_sha256):
    """Verify raw receipts and the exact repair request before any admission."""
    folder, previous_path = Path(folder).resolve(), Path(previous_path).resolve()
    raw = {name: compiler.read_bytes(folder / filename) for name, filename in
           [('prompt', 'prompt.txt'), ('request', 'request.json'), ('api', 'api_response.json'),
            ('response', 'response.txt'), ('run', 'run.json'), ('correction', 'correction.json')]}
    frozen_hashes = {str(folder / filename): compiler.sha(raw[name]) for name, filename in
                     [('prompt', 'prompt.txt'), ('request', 'request.json'), ('api', 'api_response.json'),
                      ('response', 'response.txt'), ('run', 'run.json'), ('correction', 'correction.json')]}
    previous = compiler.read_bytes(previous_path, frontend.MAX_RESPONSE_BYTES)
    frozen_hashes[str(previous_path)] = compiler.sha(previous)
    run, api, request, correction = [compiler.decode_json(raw[key]) for key in ('run', 'api', 'request', 'correction')]
    prior_review = semantic_review(previous, task['profile_id'])
    if prior_review['status'] != 'incorrect':
        raise ValueError('repair predecessor is not an actual incorrect expression')
    expected_correction = frontend.repair_prompt(task['profile_id'], previous, prior_review['counterexample'], round_index)
    repair = dict(round=round_index, previous_response_path=str(previous_path),
                  previous_response_sha256=compiler.sha(previous), counterexample=prior_review['counterexample'])
    if correction != expected_correction or raw['prompt'] != expected_correction['prompt'].encode('utf-8'):
        raise ValueError('repair prompt or counterexample differs from the frozen exact frontend')
    if request != make_request(task, expected_correction):
        raise ValueError('repair request model/schema/options/prompt changed')
    if (not isinstance(api, dict) or not isinstance(run, dict) or
            api.get('model') != task['model']['ollama_model'] or api.get('done') is not True or
            api.get('message', {}).get('role') != 'assistant' or
            not isinstance(api.get('message', {}).get('content'), str) or
            api['message']['content'].encode('utf-8') != raw['response']):
        raise ValueError('repair raw API model/completion/content mismatch')
    model = task['model']
    expected = {key: model[key] for key in (*compiler.MODEL_FIELDS, 'model_artifact_bytes', 'ollama_model')}
    expected.update(schema='atomos-teacher-inference-run-v1', frontend='boolean-expression',
                    profile_id=task['profile_id'], repair=repair, runtime=runtime,
                    status='completed' if api.get('done_reason') == 'stop' else 'incomplete_generation',
                    prompt_sha256=compiler.sha(raw['prompt']), response_sha256=compiler.sha(raw['response']),
                    request_sha256=compiler.sha(raw['request']), api_response_sha256=compiler.sha(raw['api']),
                    ollama_show_sha256=show_sha256, options=task['options'], teacher_generated_code_executed=False,
                    generation={key: api.get(key) for key in compiler.GENERATION_FIELDS})
    if any(type(run.get(key)) is not type(value) or run[key] != value for key, value in expected.items()):
        raise ValueError('repair run identity or raw artifact binding mismatch')
    elapsed = run.get('elapsed_seconds')
    if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0:
        raise ValueError('invalid repair elapsed time')
    provenance = {key: run[key] for key in (*compiler.MODEL_FIELDS, 'prompt_sha256', 'response_sha256')}
    provenance['run_sha256'] = compiler.sha(raw['run'])
    record = dict(profile_id=task['profile_id'], response_path=str(folder / 'response.txt'),
                  run_path=str(folder / 'run.json'), provenance=provenance, repair=repair)
    review = semantic_review(raw['response'], task['profile_id']) if run['status'] == 'completed' else dict(status='incomplete_generation')
    require_unchanged(frozen_hashes)
    return dict(record=record, review=review, bindings=frozen_hashes, status=run['status'])


class LocalAPI:
    def __init__(self, endpoint):
        if endpoint not in ENDPOINTS:
            raise ValueError('repair endpoint must be local Ollama')
        self.endpoint = endpoint
        self.session = requests.Session()
        self.session.trust_env = False

    def call(self, method, path, payload=None):
        if path not in ('/api/version', '/api/ps', '/api/show', '/api/chat', '/api/generate'):
            raise ValueError('unsupported local repair API path')
        raw = None if payload is None else json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        response = self.session.request(method, self.endpoint + path, data=raw,
                                       headers={'Content-Type': 'application/json'}, timeout=(10, 600), allow_redirects=False)
        if 300 <= response.status_code < 400:
            raise ValueError('local repair API redirect refused')
        response.raise_for_status()
        if len(response.content) > 1 << 20:
            raise ValueError('repair API response byte bound')
        return compiler.decode_json(response.content), response.content, raw


def loaded(ps, names):
    if not isinstance(ps, dict) or not isinstance(ps.get('models'), list):
        raise ValueError('local loaded-model inventory missing')
    return any(model.get('name') in names or model.get('model') in names for model in ps['models'])


def run(*, curriculum, acquisition, base_bank, out, max_rounds=2):
    out = Path(out).resolve()
    if out.exists():
        raise ValueError('refusing to overwrite repair evidence')
    prepared = prepare(curriculum=curriculum, acquisition=acquisition, base_bank=base_bank, max_rounds=max_rounds)
    bindings, tasks = prepared['bindings'], prepared['tasks']
    out.mkdir(parents=True, exist_ok=False)
    report = dict(schema=SCHEMA, status='running', curriculum=str(prepared['curriculum']),
                  source_acquisition=str(Path(acquisition).resolve()), base_bank=str(prepared['base_bank']),
                  max_rounds=max_rounds, selection=prepared['decisions'], rounds=[], teachers=[], later_skips=[],
                  endpoint=prepared['endpoint'], dependency_sha256=bindings, model_artifact_sha256={},
                  actual_repair_queries=0, teacher_generated_code_executed=False, teacher_weights_in_program_bank=False,
                  gpu_execution='not_run', new_active_bank_published=False, accepted_programs=0,
                  feedback_policy='one actual failing input; unchanged six-profile integer oracle; at most two rounds per model/profile',
                  model_authentication='not_claimed; pinned local artifact bytes and retained request/API consistency verified')
    def retain():
        save(out / 'repair.json', report)
    retain()
    api, correct, verified_rounds = None, [], []
    try:
        if not tasks:
            report.update(status='no_repair_needed', repeat_check='not_run_no_repair_candidates', final_bank=str(prepared['base_bank']))
            retain()
            return report
        api = LocalAPI(prepared['endpoint'])
        runtime, raw, _ = api.call('GET', '/api/version')
        retain_bytes(out / 'runtime.json', raw, bindings)
        initially_loaded, raw, _ = api.call('GET', '/api/ps')
        retain_bytes(out / 'initially_loaded.json', raw, bindings)
        names = {task['model']['ollama_model'] for task in tasks}
        if loaded(initially_loaded, names):
            raise ValueError('selected teacher already loaded; refusing another session ownership')
        report.update(runtime=runtime, initially_loaded=initially_loaded)
        learned = set()
        for teacher_id in dict.fromkeys(task['teacher_id'] for task in tasks):
            selected = [task for task in tasks if task['teacher_id'] == teacher_id]
            teacher = selected[0]['model']
            report['later_skips'].extend(dict(teacher_id=teacher_id, profile_id=task['profile_id'],
                                               reason='exact_function_verified_in_earlier_repair')
                                          for task in selected if task['profile_id'] in learned)
            selected = [task for task in selected if task['profile_id'] not in learned]
            if not selected:
                continue
            require_unchanged(bindings)
            if loaded(api.call('GET', '/api/ps')[0], {teacher['ollama_model']}):
                raise ValueError('teacher became owned by another session before repair')
            model_dir = out / teacher_id
            model_dir.mkdir()
            show, show_raw, _ = api.call('POST', '/api/show', {'model': teacher['ollama_model']})
            retain_bytes(model_dir / 'ollama_show.json', show_raw, bindings)
            artifact = acquisition_api.verify_teacher_artifact(show, teacher)
            report['model_artifact_sha256'][artifact['path']] = artifact['sha256']
            model_report = {key: teacher[key] for key in compiler.CONFIG_FIELDS}
            model_report.update(artifact_verification=artifact, show_sha256=compiler.sha(show_raw), unloaded=False)
            report['teachers'].append(model_report)
            owned = False
            try:
                for task in selected:
                    folder = model_dir / task['profile_id']
                    folder.mkdir()
                    previous_path = folder / 'initial_response.txt'
                    retain_bytes(previous_path, task['previous_raw'], bindings)
                    for round_index in range(1, max_rounds + 1):
                        require_unchanged(bindings)
                        previous = compiler.read_bytes(previous_path, frontend.MAX_RESPONSE_BYTES)
                        prior_review = semantic_review(previous, task['profile_id'])
                        correction = frontend.repair_prompt(task['profile_id'], previous, prior_review['counterexample'], round_index)
                        destination = folder / ('round' + str(round_index))
                        destination.mkdir()
                        retain_bytes(destination / 'prompt.txt', correction['prompt'].encode('utf-8'), bindings)
                        retain_json(destination / 'correction.json', correction, bindings)
                        request = make_request(task, correction)
                        request_raw = json.dumps(request, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
                        retain_bytes(destination / 'request.json', request_raw, bindings)
                        attempt = dict(teacher_id=teacher_id, profile_id=task['profile_id'], round=round_index,
                                       folder=str(destination), status='attempted')
                        report['rounds'].append(attempt)
                        report['actual_repair_queries'] += 1
                        retain()
                        print(json.dumps(attempt), flush=True)
                        require_unchanged(bindings)
                        started, owned = time.perf_counter(), True
                        response, raw, sent = api.call('POST', '/api/chat', request)
                        retain_bytes(destination / 'api_response.json', raw, bindings)
                        if sent != request_raw:
                            raise ValueError('repair retained request differs from actual sent bytes')
                        require_unchanged(bindings)
                        content = response.get('message', {}).get('content')
                        if not isinstance(content, str):
                            raise ValueError('repair API lacks textual content')
                        retain_bytes(destination / 'response.txt', content.encode('utf-8'), bindings)
                        repair = dict(round=round_index, previous_response_path=str(previous_path),
                                      previous_response_sha256=compiler.sha(previous), counterexample=prior_review['counterexample'])
                        inference = {key: teacher[key] for key in (*compiler.MODEL_FIELDS, 'model_artifact_bytes', 'ollama_model')}
                        inference.update(schema='atomos-teacher-inference-run-v1', frontend='boolean-expression',
                                         status='completed' if response.get('done_reason') == 'stop' else 'incomplete_generation',
                                         profile_id=task['profile_id'], repair=repair,
                                         prompt_sha256=correction['prompt_sha256'], response_sha256=sha(destination / 'response.txt'),
                                         request_sha256=sha(destination / 'request.json'), api_response_sha256=compiler.sha(raw),
                                         ollama_show_sha256=model_report['show_sha256'], runtime=runtime,
                                         elapsed_seconds=time.perf_counter() - started, options=request['options'],
                                         generation={key: response.get(key) for key in compiler.GENERATION_FIELDS},
                                         teacher_generated_code_executed=False)
                        retain_json(destination / 'run.json', inference, bindings)
                        verified = verify_round(destination, task=task, round_index=round_index, previous_path=previous_path,
                                                runtime=runtime, show_sha256=model_report['show_sha256'])
                        # Preserve hashes of bytes retained directly from the API.
                        # A verifier reread must never replace those original pins.
                        require_unchanged(bindings)
                        verified_rounds.append((destination, task, round_index, previous_path, runtime, model_report['show_sha256']))
                        attempt.update(status=verified['review']['status'], review=verified['review'], run_path=str(destination / 'run.json'))
                        retain()
                        if verified['review']['status'] == 'oracle_correct':
                            correct.append(verified['record'])
                            learned.add(task['profile_id'])
                            break
                        if verified['review']['status'] != 'incorrect':
                            break
                        previous_path = destination / 'response.txt'
            finally:
                if owned:
                    unload, raw, _ = api.call('POST', '/api/generate', {'model': teacher['ollama_model'], 'keep_alive': 0})
                    retain_bytes(model_dir / 'unload_response.json', raw, bindings)
                    after, raw, _ = api.call('GET', '/api/ps')
                    retain_bytes(model_dir / 'loaded_after_unload.json', raw, bindings)
                    model_report.update(unload_response=unload, loaded_after_unload=after,
                                        unloaded=not loaded(after, {teacher['ollama_model']}))
                    retain()
                    if not model_report['unloaded']:
                        raise ValueError('repair teacher still loaded after requested unload')
            require_unchanged({artifact['path']: artifact['sha256']})
        require_unchanged(bindings)
        require_unchanged(report['model_artifact_sha256'])
        for destination, task, index, previous, runtime, show_hash in verified_rounds:
            verify_round(destination, task=task, round_index=index, previous_path=previous, runtime=runtime, show_sha256=show_hash)
        retain_json(out / 'verified_correct_responses.json', correct, bindings)
        if correct:
            request, adapter = frontend.build_request(prepared['curriculum'], correct)
            if adapter['compiled_candidates'] != len(correct) or adapter['rejected_responses']:
                raise ValueError('verified repair could not pass the unchanged frontend')
            retain_json(out / 'adapter.json', adapter, bindings)
            retain_json(out / 'candidates.json', request, bindings)
            proposed = admission.admit_candidates(prepared['base_bank'], request, out / 'proposed', candidate_limit=original.MAX_RESPONSES)
            report.update(admission=proposed, accepted_programs=proposed['accepted_capsules'])
            repeated_base = out / 'proposed/bank.bin' if proposed['accepted_capsules'] else prepared['base_bank']
            repeated = admission.admit_candidates(repeated_base, request, out / 'repeated', candidate_limit=original.MAX_RESPONSES)
            if repeated['status'] != 'no_growth' or repeated['accepted_capsules'] != 0 or (out / 'repeated/bank.bin').exists():
                raise ValueError('replayed repair batch allocated new semantic storage')
            report.update(repeated_admission=repeated, repeat_check='verified_no_growth', final_bank=str(repeated_base))
        else:
            report.update(repeat_check='not_run_no_correct_repair_candidates', final_bank=str(prepared['base_bank']))
        require_unchanged(bindings)
        require_unchanged(report['model_artifact_sha256'])
        report['artifact_sha256'] = {p.relative_to(out).as_posix(): sha(p) for p in out.rglob('*') if p.is_file() and p != out / 'repair.json'}
        report.update(status='prepared' if report['accepted_programs'] else 'no_novel_programs')
        retain()
        return report
    except Exception as error:
        if report['rounds'] and report['rounds'][-1]['status'] == 'attempted':
            report['rounds'][-1].update(status='failed', reason=str(error))
        report.update(status='failed', reason=str(error))
        retain()
        raise
    finally:
        if api is not None:
            api.session.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('curriculum', 'acquisition', 'base-bank', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--max-rounds', type=int, choices=(1, 2), default=2)
    args = parser.parse_args(argv)
    report = run(curriculum=args.curriculum, acquisition=args.acquisition, base_bank=args.base_bank,
                 out=args.out, max_rounds=args.max_rounds)
    print(json.dumps({key: report[key] for key in ('status', 'actual_repair_queries', 'accepted_programs')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
