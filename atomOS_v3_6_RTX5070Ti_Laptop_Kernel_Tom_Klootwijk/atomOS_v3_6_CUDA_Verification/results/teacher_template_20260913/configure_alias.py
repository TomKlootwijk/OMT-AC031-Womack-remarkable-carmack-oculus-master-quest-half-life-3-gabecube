"""Create an isolated local Qwen alias after checking the pinned HF prompt format.

This experiment covers one text-only user message and generation prefix only.
It does not modify the existing imported model or implement tools/multimodal chat.
"""
import copy
import json
from pathlib import Path
import sys

from jinja2 import StrictUndefined
from jinja2.sandbox import SandboxedEnvironment
import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'python'))
from acquire_teacher_knowledge import sha, require_unchanged, verify_teacher_artifact
from compile_teacher_knowledge import decode_json, save
from teacher_expression_frontend import load_curriculum

ALIAS = 'atomos-qwen3-4b-instruct2507-faithful-v1:latest'
TEMPLATE = '{{range .Messages}}<|im_start|>{{.Role}}\n{{.Content}}<|im_end|>\n{{end}}<|im_start|>assistant\n'

def main():
    source = ROOT / 'results/teacher_template_20260913/sources/qwen_tokenizer_config.json'
    curriculum = ROOT / 'examples/teacher_knowledge/expression_curriculum_v2'
    teachers = ROOT / 'examples/teacher_knowledge/teachers.json'
    out = ROOT / 'results/teacher_template_20260913/alias_setup'
    if out.exists():
        raise ValueError('refusing to overwrite alias setup evidence')
    config = decode_json(teachers.read_bytes())
    teacher = next(t for t in config['teachers'] if t['id'] == 'qwen3_4b_instruct')
    if (teacher['original_model_repo'] != 'Qwen/Qwen3-4B-Instruct-2507' or
            teacher['original_model_revision'] != 'cdbee75f17c01a7cc42f958dc650907174af0554'):
        raise ValueError('this template experiment requires the named original model revision')
    paths = [source, teachers, Path(__file__), ROOT / 'tools/acquire_teacher_knowledge.py',
             ROOT / 'tools/compile_teacher_knowledge.py', ROOT / 'python/teacher_expression_frontend.py',
             ROOT / 'python/teacher_knowledge.py']
    paths += [p for p in curriculum.rglob('*') if p.is_file()]
    bindings = {str(p.resolve()): sha(p) for p in paths}
    tokenizer = decode_json(source.read_bytes())
    original_template = tokenizer['chat_template']
    if not isinstance(original_template, str) or '<think>' in original_template:
        raise ValueError('unexpected pinned non-thinking original template')
    frozen = load_curriculum(curriculum)
    environment = SandboxedEnvironment(undefined=StrictUndefined)
    rendered_template = environment.from_string(original_template)
    render_checks = []
    for identity, profile in frozen['profiles'].items():
        prompt = profile['prompt']
        rendered = rendered_template.render(messages=[dict(role='user', content=prompt)],
                                            tools=None, add_generation_prompt=True)
        expected = '<|im_start|>user\n' + prompt + '<|im_end|>\n<|im_start|>assistant\n'
        if rendered != expected:
            raise ValueError('faithful one-user-message format differs from original HF rendering: ' + identity)
        render_checks.append(dict(profile_id=identity, matched=True, rendered_prompt=rendered))
    require_unchanged(bindings)
    session = requests.Session()
    session.trust_env = False
    endpoint = config['endpoint']
    if endpoint != 'http://127.0.0.1:11434':
        raise ValueError('expected the existing loopback Ollama endpoint')
    def api(method, route, payload=None):
        raw = None if payload is None else json.dumps(payload, separators=(',', ':')).encode('utf-8')
        response = session.request(method, endpoint + route, data=raw, headers={'Content-Type':'application/json'},
                                   timeout=(10,600), allow_redirects=False)
        if 300 <= response.status_code < 400:
            raise ValueError('local alias API redirect refused')
        response.raise_for_status()
        if len(response.content) > 1 << 20:
            raise ValueError('alias API evidence byte bound')
        return decode_json(response.content), response.content
    try:
        tags, tags_raw = api('GET', '/api/tags')
        if any(m.get('name') == ALIAS or m.get('model') == ALIAS for m in tags['models']):
            raise ValueError('alias already exists; refuse to overwrite a local model')
        before, before_raw = api('POST', '/api/show', dict(model=teacher['ollama_model']))
        before_artifact = verify_teacher_artifact(before, teacher)
        if before.get('system'):
            raise ValueError('unexpected inherited system prompt')
        out.mkdir(parents=True, exist_ok=False)
        (out / 'tags_before.json').write_bytes(tags_raw)
        (out / 'original_show.json').write_bytes(before_raw)
        save(out / 'hf_render_checks.json', render_checks)
        payload = dict(model=ALIAS, **{'from':teacher['ollama_model']}, template=TEMPLATE, stream=False)
        save(out / 'create_request.json', payload)
        report = dict(schema='atomos-local-template-alias-v1', status='prepared', alias=ALIAS,
                      original_alias=teacher['ollama_model'], dependency_sha256=bindings,
                      original_hf_revision=teacher['original_model_revision'], hf_source_sha256=bindings[str(source.resolve())],
                      scope='one text-only user message; six frozen prompts match the pinned HF template byte-for-byte',
                      teacher_inference='not_run_by_setup', original_model_modified=False,
                      model_weights_copied=False, original_artifact=before_artifact)
        save(out / 'setup.json', report)
        require_unchanged(bindings)
        created, raw = api('POST', '/api/create', payload)
        (out / 'create_response.json').write_bytes(raw)
        if created.get('status') != 'success':
            raise ValueError('local alias creation did not report success')
        after, raw = api('POST', '/api/show', dict(model=ALIAS))
        (out / 'alias_show.json').write_bytes(raw)
        after_artifact = verify_teacher_artifact(after, teacher)
        if after.get('template') != TEMPLATE:
            raise ValueError('alias did not retain the requested template exactly')
        for field in ('parameters', 'model_info', 'system'):
            if before.get(field) != after.get(field):
                raise ValueError('alias changed inherited metadata beyond template: ' + field)
        unchanged, raw = api('POST', '/api/show', dict(model=teacher['ollama_model']))
        (out / 'original_show_after.json').write_bytes(raw)
        if unchanged != before:
            raise ValueError('original imported model metadata changed')
        require_unchanged(bindings)
        alias_teacher = copy.deepcopy(teacher)
        alias_teacher.update(id='qwen3_4b_instruct_faithful', ollama_model=ALIAS,
                             template_experiment='one-user-message format verified against pinned original HF template')
        save(out / 'teachers.json', dict(schema=config['schema'], endpoint=endpoint, teachers=[alias_teacher]))
        report.update(status='created_and_verified', inherited_metadata_equal=True,
                      original_model_unchanged=True, alias_artifact=after_artifact)
        report['artifact_sha256'] = {p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name != 'setup.json'}
        save(out / 'setup.json', report)
        print(json.dumps({'status':report['status'], 'alias':ALIAS, 'verified_original_prompt_renders':len(render_checks)}))
    finally:
        session.close()

if __name__ == '__main__':
    main()
