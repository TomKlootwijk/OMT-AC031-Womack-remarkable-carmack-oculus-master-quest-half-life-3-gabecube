"""Run pinned local Hugging Face teachers against a previously frozen curriculum.

Only loopback Ollama is supported. Teacher bytes stay in the existing external
model cache; retained prompts, responses and inference receipts form acquisition
evidence. No teacher-generated code is executed or automatically repaired.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import time

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from teacher_knowledge import load_curriculum


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def now():
    return datetime.now(timezone.utc).isoformat()


def require_unchanged(bindings):
    for path, expected in bindings.items():
        if not Path(path).is_file() or sha(path) != expected:
            raise ValueError('frozen acquisition dependency changed: ' + path)


def verify_teacher_artifact(show, teacher):
    matches = re.findall(r'^FROM (.+)$', show.get('modelfile', ''), re.MULTILINE)
    digest = teacher['model_artifact_sha256']
    if len(matches) != 1 or not re.fullmatch('[0-9a-f]{64}', digest):
        raise ValueError('one local pinned GGUF artifact is required')
    path = Path(matches[0].strip().strip('"')).resolve()
    if path.name != 'sha256-' + digest or not path.is_file():
        raise ValueError('Ollama model artifact differs from pinned Hugging Face bytes')
    if path.stat().st_size != teacher['model_artifact_bytes'] or sha(path) != digest:
        raise ValueError('actual GGUF bytes fail the pinned hash/size')
    if show.get('details', {}).get('format') != 'gguf':
        raise ValueError('this acquisition profile requires GGUF')
    return {'path': str(path), 'sha256': digest, 'bytes': path.stat().st_size,
            'verified_at_utc': now(),
            'scope': 'installed bytes match the named file at observed pinned HF revision; original acquisition revision unknown'}


def acquire(*, curriculum, teachers, out, max_tokens=2048):
    curriculum, teachers, out = map(lambda p: Path(p).resolve(), (curriculum, teachers, out))
    if out.exists():
        raise ValueError('refusing to overwrite acquisition evidence')
    if type(max_tokens) is not int or not 128 <= max_tokens <= 8192:
        raise ValueError('bounded generated token count must be 128..8192')
    frozen = load_curriculum(curriculum)
    manifest = frozen['manifest']
    config = json.loads(teachers.read_text(encoding='utf-8'))
    endpoint = config.get('endpoint')
    if endpoint not in ('http://127.0.0.1:11434', 'http://localhost:11434'):
        raise ValueError('this tool only sends the frozen curriculum to local Ollama')
    models = config.get('teachers')
    if config.get('schema') != 'atomos-local-teachers-v1' or not isinstance(models, list) or not 1 <= len(models) <= 4:
        raise ValueError('expected one to four pinned local teachers')
    if len({m['id'] for m in models}) != len(models) or any(not re.fullmatch('[a-z0-9_]{1,80}', m['id']) for m in models):
        raise ValueError('teacher identities must be unique safe directory names')
    bound = {str(p): sha(p) for p in curriculum.rglob('*') if p.is_file()}
    bound.update({str(p): sha(p) for p in [teachers, Path(__file__), ROOT / 'python/teacher_knowledge.py',
                                         ROOT / 'python/program_bank.py', ROOT / 'python/knowledge_admission.py']})
    session = requests.Session()
    session.trust_env = False
    def api(method, path, payload=None):
        raw = None if payload is None else json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        response = session.request(method, endpoint + path, data=raw,
                                   headers={'Content-Type': 'application/json'}, timeout=(10, 600), allow_redirects=False)
        if 300 <= response.status_code < 400:
            raise ValueError('local teacher API redirect refused')
        response.raise_for_status()
        if len(response.content) > 1 << 20:
            raise ValueError('local API response exceeded evidence byte bound')
        return response.json(), response.content, raw
    version = api('GET', '/api/version')[0]
    initially_loaded = api('GET', '/api/ps')[0]
    selected_names = {m['ollama_model'] for m in models}
    if any(m.get('name') in selected_names or m.get('model') in selected_names for m in initially_loaded.get('models', [])):
        raise ValueError('selected teacher already loaded; do not take ownership of another active session')
    out.mkdir(parents=True, exist_ok=False)
    report = {'schema': 'atomos-local-teacher-acquisition-v1', 'status': 'running',
              'started_at_utc': now(), 'runtime': version, 'endpoint': endpoint,
              'curriculum': str(curriculum), 'dependency_sha256': bound, 'initially_loaded': initially_loaded,
              'teacher_weights_in_program_bank': False, 'model_artifact_sha256': {},
              'teachers': [], 'responses': [], 'failures': []}
    def retain():
        save(out / 'acquisition.json', report)
    retain()
    try:
        for teacher in models:
            model_dir = out / teacher['id']
            model_dir.mkdir()
            show = api('POST', '/api/show', {'model': teacher['ollama_model']})[0]
            save(model_dir / 'ollama_show.json', show)
            artifact = verify_teacher_artifact(show, teacher)
            report['model_artifact_sha256'][artifact['path']] = artifact['sha256']
            model_report = {**teacher, 'artifact_verification': artifact, 'show_sha256': sha(model_dir / 'ollama_show.json'),
                            'loaded_observations': [], 'unloaded': False}
            report['teachers'].append(model_report)
            retain()
            owned_model = False
            try:
                for profile in manifest['profiles']:
                    profile_id = profile['profile_id']
                    folder = model_dir / profile_id
                    folder.mkdir()
                    require_unchanged(bound)
                    prompt = frozen['profiles'][profile_id]['prompt']
                    request = {'model': teacher['ollama_model'], 'stream': False, 'format': 'json',
                               'messages': [{'role': 'user', 'content': prompt}], 'keep_alive': '2m',
                               'options': {'temperature': 0, 'seed': 7, 'num_ctx': 4096, 'num_predict': max_tokens}}
                    if 'thinking' in show.get('capabilities', []):
                        request['think'] = False
                    request_raw = json.dumps(request, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
                    (folder / 'request.json').write_bytes(request_raw)
                    print(json.dumps({'teacher': teacher['id'], 'profile': profile_id, 'status': 'querying'}), flush=True)
                    started = time.perf_counter()
                    owned_model = True
                    response, raw, sent = api('POST', '/api/chat', request)
                    if sent != request_raw:
                        raise ValueError('retained request differs from sent bytes')
                    elapsed = time.perf_counter() - started
                    (folder / 'api_response.json').write_bytes(raw)
                    require_unchanged(bound)
                    content = response.get('message', {}).get('content')
                    if not isinstance(content, str) or response.get('done') is not True:
                        raise ValueError('teacher response lacks completed textual content')
                    if response.get('model') != teacher['ollama_model']:
                        raise ValueError('response model differs from requested teacher')
                    (folder / 'response.txt').write_bytes(content.encode('utf-8'))
                    run = {key: teacher[key] for key in ('model_repo', 'model_revision', 'model_revision_status', 'model_artifact_sha256')}
                    run.update(schema='atomos-teacher-inference-run-v1', profile_id=profile_id,
                               status='completed' if response.get('done_reason') == 'stop' else 'incomplete_generation',
                               prompt_sha256=sha(curriculum / profile['prompt_file']), response_sha256=sha(folder / 'response.txt'),
                               request_sha256=sha(folder / 'request.json'), api_response_sha256=sha(folder / 'api_response.json'),
                               ollama_show_sha256=model_report['show_sha256'], ollama_model=teacher['ollama_model'],
                               model_artifact_bytes=artifact['bytes'], runtime=version, elapsed_seconds=elapsed,
                               completed_at_utc=now(), generation={k: response.get(k) for k in
                               ('done_reason', 'total_duration', 'load_duration', 'prompt_eval_count', 'prompt_eval_duration',
                                'eval_count', 'eval_duration')}, options=request['options'], teacher_generated_code_executed=False)
                    save(folder / 'run.json', run)
                    if run['status'] == 'completed':
                        provenance = {key: run[key] for key in ('model_repo', 'model_revision', 'model_revision_status',
                                                              'model_artifact_sha256', 'prompt_sha256', 'response_sha256')}
                        provenance['run_sha256'] = sha(folder / 'run.json')
                        report['responses'].append({'profile_id': profile_id, 'response_path': str(folder / 'response.txt'),
                                                    'run_path': str(folder / 'run.json'), 'provenance': provenance})
                    else:
                        report['failures'].append({'teacher': teacher['id'], 'profile_id': profile_id,
                                                   'reason': run['status'], 'run_path': str(folder / 'run.json')})
                    model_report['loaded_observations'].append(api('GET', '/api/ps')[0])
                    retain()
                    print(json.dumps({'teacher': teacher['id'], 'profile': profile_id, 'status': run['status'],
                                      'tokens': response.get('eval_count'), 'seconds': round(elapsed, 3)}), flush=True)
            finally:
                if owned_model:
                    unloaded = api('POST', '/api/generate', {'model': teacher['ollama_model'], 'keep_alive': 0})[0]
                    loaded_after = api('GET', '/api/ps')[0]
                    model_report['unload_response'] = unloaded
                    model_report['loaded_after_unload'] = loaded_after
                    model_report['unloaded'] = not any(m.get('name') == teacher['ollama_model'] or m.get('model') == teacher['ollama_model']
                                                        for m in loaded_after.get('models', []))
                    retain()
                    if not model_report['unloaded']:
                        raise ValueError('teacher still loaded after requested unload')
            require_unchanged({artifact['path']: artifact['sha256']})
        require_unchanged(bound)
        require_unchanged(report['model_artifact_sha256'])
        report.update(status='completed' if not report['failures'] else 'completed_with_generation_failures', finished_at_utc=now())
        retain()
        return report
    except Exception as error:
        report.update(status='failed', reason=str(error), finished_at_utc=now())
        retain()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('curriculum', 'teachers', 'out'):
        parser.add_argument('--' + key, type=Path, required=True)
    parser.add_argument('--max-tokens', type=int, default=2048)
    args = parser.parse_args()
    report = acquire(curriculum=args.curriculum, teachers=args.teachers, out=args.out, max_tokens=args.max_tokens)
    print(json.dumps({'status': report['status'], 'responses': len(report['responses']), 'failures': len(report['failures'])}))


if __name__ == '__main__':
    raise SystemExit(main())
