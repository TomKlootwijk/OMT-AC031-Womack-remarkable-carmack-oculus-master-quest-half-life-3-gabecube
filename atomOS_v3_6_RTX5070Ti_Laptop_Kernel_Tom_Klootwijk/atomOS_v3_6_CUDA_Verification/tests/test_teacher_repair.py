"""Synthetic CPU repair fixtures. No real model, network or GPU is exercised."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
sys.path.insert(0, str(ROOT / 'tools'))
import repair_teacher_knowledge as repair
import teacher_expression_frontend as frontend
import teacher_knowledge as original


def response(outputs):
    return json.dumps(dict(schema=frontend.RESPONSE_SCHEMA, profile_id='full_adder_1bit_v1',
                           procedures=[dict(name='full_adder_1bit_v1', input_bits=3, output_bits=2, outputs=outputs)]))


WRONG = response(['0', '0'])
CORRECT = response(['a ^ b ^ carry_in', '(a & b) | (carry_in & (a ^ b))'])


class TeacherRepairTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='synthetic_teacher_repair_cpu_')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.identity = 'full_adder_1bit_v1'
        old, self.curriculum = self.root / 'original', self.root / 'curriculum'
        original.prepare_curriculum(old, [self.identity])
        frontend.freeze_curriculum(self.curriculum, old)
        self.profile = frontend.load_curriculum(self.curriculum)['profiles'][self.identity]
        self.acquisition, self.out = self.root / 'acquisition', self.root / 'repair'
        self.folder = self.acquisition / 'synthetic_fixture' / self.identity
        self.folder.mkdir(parents=True)
        artifact_raw = b'synthetic fixture bytes; not a language model or GGUF'
        artifact_hash = repair.compiler.sha(artifact_raw)
        self.artifact = self.root / ('sha256-' + artifact_hash)
        self.artifact.write_bytes(artifact_raw)
        self.model = dict(id='synthetic_fixture', ollama_model='synthetic-fixture:no-model-executed',
                          model_repo='synthetic-fixture/no-model-executed', model_revision='a' * 40,
                          model_revision_status='pinned_huggingface_commit', model_artifact_sha256=artifact_hash,
                          model_artifact_bytes=len(artifact_raw))
        self.config = self.root / 'teachers.json'
        repair.save(self.config, dict(schema='atomos-local-teachers-v1', endpoint='http://127.0.0.1:11434',
                                      teachers=[self.model], scope='synthetic CPU fixture, no teacher execution'))
        self.show = dict(modelfile='FROM ' + str(self.artifact), details=dict(format='gguf'),
                         scope='synthetic fixture metadata, no real GGUF')
        repair.save(self.folder.parent / 'ollama_show.json', self.show)
        self.show_hash = repair.sha(self.folder.parent / 'ollama_show.json')
        self.runtime = dict(version='synthetic-fixture-no-runtime')
        self.request = dict(model=self.model['ollama_model'], stream=False, format=frontend.response_format(self.identity),
                            messages=[dict(role='user', content=self.profile['prompt'])], keep_alive='2m',
                            options=dict(temperature=0, seed=7, num_ctx=4096, num_predict=2048))
        repair.save(self.folder / 'request.json', self.request)
        self.api_response = self.envelope(WRONG)
        repair.save(self.folder / 'api_response.json', self.api_response)
        (self.folder / 'response.txt').write_bytes(WRONG.encode())
        inference = {key: self.model[key] for key in repair.compiler.MODEL_FIELDS}
        inference.update(schema='atomos-teacher-inference-run-v1', frontend='boolean-expression',
                         profile_id=self.identity, status='completed', prompt_sha256=self.profile['prompt_sha256'],
                         response_sha256=repair.sha(self.folder / 'response.txt'), request_sha256=repair.sha(self.folder / 'request.json'),
                         api_response_sha256=repair.sha(self.folder / 'api_response.json'), ollama_show_sha256=self.show_hash,
                         ollama_model=self.model['ollama_model'], model_artifact_bytes=len(artifact_raw), runtime=self.runtime,
                         elapsed_seconds=0.001, options=self.request['options'], teacher_generated_code_executed=False,
                         generation={key: self.api_response.get(key) for key in repair.compiler.GENERATION_FIELDS},
                         scope='synthetic CPU fixture, no teacher execution')
        repair.save(self.folder / 'run.json', inference)
        provenance = {key: inference[key] for key in (*repair.compiler.MODEL_FIELDS, 'prompt_sha256', 'response_sha256')}
        provenance['run_sha256'] = repair.sha(self.folder / 'run.json')
        paths = [p for p in self.curriculum.rglob('*') if p.is_file()]
        paths += [self.config, ROOT / 'python/teacher_expression_frontend.py']
        paths += [ROOT / name for name in repair.compiler.ACQUISITION_SOURCES]
        self.report = dict(schema='atomos-local-teacher-acquisition-v1', status='completed', frontend='boolean-expression',
                           runtime=self.runtime, endpoint='http://127.0.0.1:11434', curriculum=str(self.curriculum),
                           dependency_sha256={str(p.resolve()): repair.sha(p) for p in paths},
                           teacher_weights_in_program_bank=False, model_artifact_sha256={str(self.artifact): artifact_hash},
                           teachers=[dict(self.model, show_sha256=self.show_hash,
                                          artifact_verification=dict(path=str(self.artifact), sha256=artifact_hash, bytes=len(artifact_raw)),
                                          unloaded=True, loaded_after_unload=dict(models=[]))], failures=[],
                           responses=[dict(profile_id=self.identity, response_path=str(self.folder / 'response.txt'),
                                           run_path=str(self.folder / 'run.json'), provenance=provenance)],
                           scope='synthetic retained receipt fixture; no actual acquisition')
        repair.save(self.acquisition / 'acquisition.json', self.report)
        self.base = ROOT / 'examples/program_bank/learned_v1/bank.bin'

    def envelope(self, content, **changes):
        value = dict(model=self.model['ollama_model'], done=True, done_reason='stop',
                     message=dict(role='assistant', content=content), total_duration=100,
                     load_duration=1, prompt_eval_count=100, prompt_eval_duration=10, eval_count=100, eval_duration=89)
        value.update(changes)
        return value

    def prepare(self, **kwargs):
        return repair.prepare(curriculum=self.curriculum, acquisition=self.acquisition,
                              base_bank=kwargs.get('base_bank', self.base), max_rounds=kwargs.get('max_rounds', 2))

    def fake_api(self, envelopes, chat_callback=None, initially_loaded=False):
        calls, pending = [], list(envelopes)
        fixture = self
        class FakeAPI:
            def __init__(self, endpoint):
                self.session = Mock()
            def call(self, method, path, payload=None):
                calls.append((method, path, copy.deepcopy(payload)))
                sent = None if payload is None else json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode()
                if path == '/api/chat':
                    if chat_callback:
                        chat_callback()
                    value = pending.pop(0)
                elif path == '/api/show':
                    value = fixture.show
                elif path == '/api/version':
                    value = fixture.runtime
                elif path == '/api/ps':
                    value = dict(models=[dict(name=fixture.model['ollama_model'])] if initially_loaded else [])
                else:
                    value = dict(done=True, model=fixture.model['ollama_model'])
                return value, json.dumps(value).encode(), sent
        return FakeAPI, calls

    def invoke(self, fake, **kwargs):
        with patch.object(repair, 'LocalAPI', fake):
            return repair.run(curriculum=self.curriculum, acquisition=self.acquisition, base_bank=self.base,
                              out=self.out, max_rounds=kwargs.get('max_rounds', 2))

    def test_preflight_selects_only_actual_failure_and_one_counterexample(self):
        prepared = self.prepare()
        self.assertEqual(len(prepared['tasks']), 1)
        self.assertEqual(prepared['tasks'][0]['initial_counterexample'], dict(input=1, expected=1, actual=0))
        self.assertEqual(prepared['decisions'][0]['original_review']['mismatch_count'], 7)

    def test_round_limits_fail_before_network_or_output(self):
        for value in (0, 3, True, 1.5):
            with patch.object(repair, 'LocalAPI') as api:
                with self.assertRaisesRegex(ValueError, 'max_rounds'):
                    repair.run(curriculum=self.curriculum, acquisition=self.acquisition, base_bank=self.base,
                               out=self.out, max_rounds=value)
                api.assert_not_called()
        self.assertFalse(self.out.exists())

    def test_changed_acquisition_is_rejected_before_repair(self):
        (self.folder / 'response.txt').write_text(CORRECT)
        with patch.object(repair, 'LocalAPI') as api:
            with self.assertRaises(ValueError):
                self.invoke(api)
            api.assert_not_called()
        self.assertFalse(self.out.exists())

    def test_synthetic_correct_repair_admits_once_and_repeat_allocates_nothing(self):
        fake, calls = self.fake_api([self.envelope(CORRECT)])
        result = self.invoke(fake)
        self.assertEqual((result['actual_repair_queries'], result['accepted_programs']), (1, 1))
        self.assertEqual(result['repeat_check'], 'verified_no_growth')
        self.assertEqual(result['repeated_admission']['accepted_capsules'], 0)
        self.assertEqual(result['gpu_execution'], 'not_run')
        self.assertFalse(result['new_active_bank_published'])
        self.assertTrue(result['teachers'][0]['unloaded'])
        self.assertEqual(sum(path == '/api/generate' for _, path, _ in calls), 1)
        self.assertFalse((self.out / 'repeated/bank.bin').exists())
        # Record origin remains explicitly synthetic even through real CPU admission.
        self.assertIn('synthetic-fixture', result['teachers'][0]['model_repo'])
        selected = self.prepare(base_bank=self.out / 'proposed/bank.bin')
        self.assertEqual(selected['tasks'], [])
        self.assertEqual(selected['decisions'][0]['reason'], 'exact_function_already_present_in_base')

    def test_two_failed_repairs_stop_at_limit_without_program_growth(self):
        fake, calls = self.fake_api([self.envelope(WRONG), self.envelope(WRONG)])
        result = self.invoke(fake)
        self.assertEqual((result['actual_repair_queries'], result['accepted_programs']), (2, 0))
        self.assertEqual([r['status'] for r in result['rounds']], ['incorrect', 'incorrect'])
        self.assertEqual(sum(path == '/api/chat' for _, path, _ in calls), 2)
        second = self.out / 'synthetic_fixture' / self.identity / 'round2/run.json'
        record = repair.compiler.decode_json(second.read_bytes())
        self.assertTrue(record['repair']['previous_response_path'].endswith('round1\\response.txt') or
                        record['repair']['previous_response_path'].endswith('round1/response.txt'))
        self.assertFalse((self.out / 'proposed').exists())

    def test_incomplete_generation_is_retained_never_admitted_or_retried(self):
        fake, calls = self.fake_api([self.envelope(CORRECT, done_reason='length')])
        result = self.invoke(fake)
        self.assertEqual(result['rounds'][0]['status'], 'incomplete_generation')
        self.assertEqual((result['actual_repair_queries'], result['accepted_programs']), (1, 0))
        self.assertEqual(sum(path == '/api/chat' for _, path, _ in calls), 1)

    def test_wrong_model_fails_and_unloads_owned_model(self):
        fake, calls = self.fake_api([self.envelope(CORRECT, model='wrong:model')])
        with self.assertRaisesRegex(ValueError, 'model/completion/content'):
            self.invoke(fake)
        result = repair.compiler.decode_json((self.out / 'repair.json').read_bytes())
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(result['teachers'][0]['unloaded'])
        self.assertEqual(sum(path == '/api/generate' for _, path, _ in calls), 1)
        self.assertFalse((self.out / 'proposed').exists())

    def test_dependency_change_during_chat_fails_and_unloads(self):
        fake, calls = self.fake_api([self.envelope(CORRECT)], chat_callback=lambda: self.config.write_text('{}'))
        with self.assertRaisesRegex(ValueError, 'dependency changed'):
            self.invoke(fake)
        self.assertEqual(sum(path == '/api/generate' for _, path, _ in calls), 1)
        self.assertFalse((self.out / 'proposed').exists())

    def test_changed_gguf_bytes_fail_before_chat(self):
        self.artifact.write_bytes(b'wrong pinned bytes')
        fake, calls = self.fake_api([])
        with self.assertRaisesRegex(ValueError, 'actual GGUF bytes'):
            self.invoke(fake)
        self.assertFalse(any(path in ('/api/chat', '/api/generate') for _, path, _ in calls))

    def test_retained_request_whitespace_mutation_during_chat_is_detected(self):
        def mutate():
            path = self.out / 'synthetic_fixture' / self.identity / 'round1/request.json'
            path.write_bytes(path.read_bytes() + b' ')
        fake, calls = self.fake_api([self.envelope(CORRECT)], chat_callback=mutate)
        with self.assertRaisesRegex(ValueError, 'dependency changed'):
            self.invoke(fake)
        self.assertEqual(sum(path == '/api/generate' for _, path, _ in calls), 1)
        self.assertFalse((self.out / 'proposed').exists())

    def test_retained_show_mutation_during_chat_is_detected(self):
        def mutate():
            path = self.out / 'synthetic_fixture/ollama_show.json'
            path.write_bytes(path.read_bytes() + b' ')
        fake, calls = self.fake_api([self.envelope(CORRECT)], chat_callback=mutate)
        with self.assertRaisesRegex(ValueError, 'dependency changed'):
            self.invoke(fake)
        self.assertEqual(sum(path == '/api/generate' for _, path, _ in calls), 1)
        self.assertFalse((self.out / 'proposed').exists())

    def test_coherent_rewritten_api_content_and_run_cannot_replace_original_bindings(self):
        original_verify = repair.verify_round
        def rewrite_before_verify(folder, **kwargs):
            folder = Path(folder)
            api = repair.compiler.decode_json((folder / 'api_response.json').read_bytes())
            api['message']['content'] = CORRECT
            repair.save(folder / 'api_response.json', api)
            (folder / 'response.txt').write_bytes(CORRECT.encode())
            run = repair.compiler.decode_json((folder / 'run.json').read_bytes())
            run.update(api_response_sha256=repair.sha(folder / 'api_response.json'),
                       response_sha256=repair.sha(folder / 'response.txt'))
            repair.save(folder / 'run.json', run)
            return original_verify(folder, **kwargs)
        fake, calls = self.fake_api([self.envelope(WRONG)])
        with patch.object(repair, 'verify_round', side_effect=rewrite_before_verify):
            with self.assertRaisesRegex(ValueError, 'dependency changed'):
                self.invoke(fake)
        self.assertEqual(sum(path == '/api/generate' for _, path, _ in calls), 1)
        self.assertFalse((self.out / 'proposed').exists())

    def test_existing_session_is_never_taken_over_or_unloaded(self):
        fake, calls = self.fake_api([], initially_loaded=True)
        with self.assertRaisesRegex(ValueError, 'already loaded'):
            self.invoke(fake)
        self.assertFalse(any(path in ('/api/chat', '/api/generate') for _, path, _ in calls))

    def test_api_refuses_nonloopback_and_redirect(self):
        with patch.object(repair.requests, 'Session') as session:
            with self.assertRaisesRegex(ValueError, 'local Ollama'):
                repair.LocalAPI('https://example.com')
            session.assert_not_called()
            session.return_value.request.return_value.status_code = 302
            api = repair.LocalAPI('http://127.0.0.1:11434')
            with self.assertRaisesRegex(ValueError, 'redirect'):
                api.call('GET', '/api/version')
            self.assertFalse(session.return_value.request.call_args.kwargs['allow_redirects'])
            self.assertFalse(session.return_value.trust_env)

    def test_options_reject_unbounded_or_changed_generation(self):
        for field, value in [('num_predict', 8193), ('num_predict', True), ('num_ctx', 8192), ('temperature', 1), ('seed', 8)]:
            request = copy.deepcopy(self.request)
            request['options'][field] = value
            with self.assertRaisesRegex(ValueError, 'bounded deterministic'):
                repair.checked_options(request)

    def test_raw_repair_request_mutation_fails_even_after_rehashed_run(self):
        fake, _ = self.fake_api([self.envelope(CORRECT)])
        self.invoke(fake)
        folder = self.out / 'synthetic_fixture' / self.identity / 'round1'
        request = repair.compiler.decode_json((folder / 'request.json').read_bytes())
        request['format'] = 'json'
        repair.save(folder / 'request.json', request)
        run = repair.compiler.decode_json((folder / 'run.json').read_bytes())
        run['request_sha256'] = repair.sha(folder / 'request.json')
        repair.save(folder / 'run.json', run)
        task = self.prepare()['tasks'][0]
        with self.assertRaisesRegex(ValueError, 'model/schema/options/prompt'):
            repair.verify_round(folder, task=task, round_index=1, previous_path=folder.parent / 'initial_response.txt',
                                runtime=self.runtime, show_sha256=run['ollama_show_sha256'])

    def test_false_counterexample_is_rejected_before_request_construction(self):
        with self.assertRaisesRegex(ValueError, 'not a real mismatch'):
            frontend.repair_prompt(self.identity, WRONG, dict(input=1, expected=0, actual=1), 1)


if __name__ == '__main__':
    unittest.main()
