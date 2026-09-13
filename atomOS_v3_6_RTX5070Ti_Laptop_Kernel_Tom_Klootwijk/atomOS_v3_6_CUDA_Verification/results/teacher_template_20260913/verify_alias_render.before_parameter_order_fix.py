"""Verify the already-created alias by actual render-only API responses.

Creation succeeded, but Ollama exposed its selected Jinja template instead of
the requested Go text. This follow-up checks the actual prompt for each case.
"""
import copy
import json
from pathlib import Path
import sys
import requests
from jinja2 import StrictUndefined
from jinja2.sandbox import SandboxedEnvironment

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from acquire_teacher_knowledge import sha, require_unchanged, verify_teacher_artifact
from compile_teacher_knowledge import save, decode_json

def main():
    study = ROOT / 'results/teacher_template_20260913'
    out = study / 'verified_alias'
    out.mkdir(parents=True, exist_ok=False)
    config = decode_json((ROOT / 'examples/teacher_knowledge/teachers.json').read_bytes())
    teacher = copy.deepcopy(config['teachers'][0])
    alias = 'atomos-qwen3-4b-instruct2507-faithful-v1:latest'
    old = ROOT / 'results/teacher_expression_20260913/compilation/retained_acquisition/qwen3_4b_instruct'
    inputs = [Path(__file__), study / 'configure_alias.py', study / 'sources/qwen_tokenizer_config.json']
    inputs += [p for p in (study / 'alias_setup').iterdir() if p.is_file()]
    inputs += list(old.glob('*/request.json'))
    bindings = {str(p):sha(p) for p in inputs}
    source = decode_json((study / 'sources/qwen_tokenizer_config.json').read_bytes())
    hf = SandboxedEnvironment(undefined=StrictUndefined).from_string(source['chat_template'])
    s = requests.Session(); s.trust_env = False
    def api(route, payload=None):
        raw = None if payload is None else json.dumps(payload,separators=(',',':')).encode('utf-8')
        response = s.request('GET' if payload is None else 'POST', 'http://127.0.0.1:11434'+route,
                             data=raw, headers={'Content-Type':'application/json'}, timeout=(10,300), allow_redirects=False)
        response.raise_for_status()
        if response.status_code != 200 or len(response.content)>1<<20:
            raise ValueError('unsupported local render API response')
        return decode_json(response.content),response.content,raw
    owned = False
    checks = []
    try:
        ps,raw,_=api('/api/ps'); (out/'loaded_before.json').write_bytes(raw)
        if any(m.get('name')==alias for m in ps['models']):
            raise ValueError('alias already owned by another session')
        show,raw,_=api('/api/show',dict(model=alias)); (out/'alias_show.json').write_bytes(raw)
        artifact=verify_teacher_artifact(show,teacher)
        original=decode_json((study/'alias_setup/original_show.json').read_bytes())
        for key in ('parameters','model_info','system'):
            if show.get(key)!=original.get(key): raise ValueError('inherited metadata changed: '+key)
        for request_path in sorted(old.glob('*/request.json')):
            request=decode_json(request_path.read_bytes()); request.update(model=alias,_debug_render_only=True)
            require_unchanged(bindings); owned=True
            value,raw,sent=api('/api/chat',request)
            stem=request_path.parent.name
            (out/(stem+'.request.json')).write_bytes(sent); (out/(stem+'.response.json')).write_bytes(raw)
            expected=hf.render(messages=request['messages'],tools=None,add_generation_prompt=True)
            actual=value['_debug_info']['rendered_template']
            if actual!=expected: raise ValueError('actual alias render differs from pinned HF: '+stem)
            checks.append(dict(profile_id=stem,exact_hf_render_match=True,rendered_sha256=__import__('hashlib').sha256(actual.encode('utf-8')).hexdigest()))
        after,raw,_=api('/api/show',dict(model=teacher['ollama_model'])); (out/'original_show_after.json').write_bytes(raw)
        if after!=original: raise ValueError('original imported alias was modified')
        require_unchanged(bindings)
    finally:
        if owned:
            _,raw,_=api('/api/generate',dict(model=alias,keep_alive=0)); (out/'unload.json').write_bytes(raw)
            ps,raw,_=api('/api/ps'); (out/'loaded_after.json').write_bytes(raw)
            if any(m.get('name')==alias for m in ps['models']): raise ValueError('alias did not unload')
        s.close()
    teacher.update(id='qwen3_4b_instruct_faithful',ollama_model=alias,
                   template_experiment='actual render-only API matches exact pinned HF template for all six frozen one-user-message prompts')
    save(out/'teachers.json',dict(schema=config['schema'],endpoint=config['endpoint'],teachers=[teacher]))
    report=dict(schema='atomos-verified-model-template-render-v1',status='verified_for_six_frozen_prompts',
                dependency_sha256=bindings,checks=checks,model_artifact=artifact,
                initial_setup_verification='failed exact template-text comparison; creation succeeded; runtime exposes a Jinja template',
                verified_claim='actual rendered prompts match the pinned original HF byte-for-byte; parameters/model_info/system and original alias unchanged',
                teacher_generation='not_run; render-only requests load/tokenize and selected alias is unloaded',
                artifact_sha256={p.name:sha(p) for p in out.iterdir() if p.is_file()})
    save(out/'verification.json',report)
    print(json.dumps({'status':report['status'],'matching_actual_renders':len(checks)}))

if __name__=='__main__': main()
