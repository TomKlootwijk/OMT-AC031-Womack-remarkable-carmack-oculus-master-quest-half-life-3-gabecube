"""Synthetic CPU/API regressions only; no teacher, network, or GPU is run here."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

try:
    import jsonschema
except ImportError:
    jsonschema = None

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
sys.path.insert(0, str(ROOT / 'tools'))
from teacher_knowledge import prepare_curriculum
import acquire_teacher_knowledge as acquisition


class SyntheticResponse:
    def __init__(self, value, status=200):
        self.content = json.dumps(value).encode('utf-8')
        self.status_code = status
        self.is_redirect = 300 <= status < 400
        self.headers = {'Location': 'https://invalid.example/redirect'} if self.is_redirect else {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise acquisition.requests.HTTPError('synthetic CPU failure')

    def json(self):
        return json.loads(self.content)


class SyntheticSession:
    """An in-memory API fixture, explicitly unrelated to an inference runtime."""
    def __init__(self, show, model):
        self.show, self.model = show, model
        self.trust_env = True
        self.loaded = False
        self.calls = []
        self.response_model = model
        self.done = True
        self.done_reason = 'length'
        self.redirect = False
        self.after_chat = None

    def request(self, method, url, data=None, **kwargs):
        payload = None if data is None else json.loads(data)
        self.calls.append((method, url, payload, kwargs))
        if self.redirect:
            return SyntheticResponse({'synthetic_fixture': True}, 307)
        if url.endswith('/api/version'):
            return SyntheticResponse({'version': 'synthetic-cpu-fixture-no-model-execution'})
        if url.endswith('/api/ps'):
            return SyntheticResponse({'models': [{'name': self.model}] if self.loaded else []})
        if url.endswith('/api/show'):
            return SyntheticResponse(self.show)
        if url.endswith('/api/chat'):
            self.loaded = True
            if self.after_chat:
                self.after_chat()
            return SyntheticResponse({'model': self.response_model, 'done': self.done,
                                      'done_reason': self.done_reason,
                                      'message': {'content': '{"synthetic_fixture":true}'},
                                      'eval_count': 1})
        if url.endswith('/api/generate'):
            self.loaded = False
            return SyntheticResponse({'model': self.model, 'done': True, 'done_reason': 'unload'})
        raise AssertionError('unexpected synthetic endpoint: ' + url)

    def close(self):
        pass


class TeacherAcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='atomos_synthetic_teacher_test_')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.curriculum = self.root / 'curriculum'
        prepare_curriculum(self.curriculum, ['full_adder_1bit_v1'])
        raw = b'SYNTHETIC CPU FIXTURE; this is not a model and is never executed.'
        digest = hashlib.sha256(raw).hexdigest()
        self.blob = self.root / ('sha256-' + digest)
        self.blob.write_bytes(raw)
        self.teacher = dict(id='synthetic_teacher', ollama_model='synthetic-cpu-fixture:latest',
                            model_repo='synthetic/cpu-test-only', model_revision='1' * 40,
                            model_revision_status='pinned_huggingface_commit',
                            model_artifact_sha256=digest, model_artifact_bytes=len(raw))
        self.config = dict(schema='atomos-local-teachers-v1', endpoint='http://127.0.0.1:11434',
                           teachers=[self.teacher])
        self.teachers = self.root / 'teachers.json'
        acquisition.save(self.teachers, self.config)
        self.show = {'modelfile': 'FROM "' + str(self.blob) + '"\n', 'details': {'format': 'gguf'}}
        self.session = SyntheticSession(self.show, self.teacher['ollama_model'])

    def acquire(self, **kwargs):
        with patch.object(acquisition.requests, 'Session', return_value=self.session):
            return acquisition.acquire(curriculum=self.curriculum, teachers=self.teachers,
                                       out=self.root / 'acquisition', **kwargs)

    def calls(self, endpoint):
        return [row for row in self.session.calls if row[1].endswith(endpoint)]

    def test_artifact_requires_actual_full_bytes_not_just_digest_filename(self):
        self.blob.write_bytes(b'x' * self.teacher['model_artifact_bytes'])
        with self.assertRaisesRegex(ValueError, 'actual GGUF bytes'):
            acquisition.verify_teacher_artifact(self.show, self.teacher)

    def test_artifact_refuses_a_different_local_filename(self):
        other = self.root / 'arbitrary.gguf'
        other.write_bytes(self.blob.read_bytes())
        changed = copy.deepcopy(self.show)
        changed['modelfile'] = 'FROM ' + str(other)
        with self.assertRaisesRegex(ValueError, 'artifact differs'):
            acquisition.verify_teacher_artifact(changed, self.teacher)

    def test_artifact_refuses_missing_or_multiple_from_records(self):
        for value in ('', self.show['modelfile'] * 2):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'one local pinned'):
                acquisition.verify_teacher_artifact({'modelfile': value}, self.teacher)

    def test_artifact_size_mismatch_fails_before_inference(self):
        self.teacher['model_artifact_bytes'] += 1
        acquisition.save(self.teachers, self.config)
        with self.assertRaisesRegex(ValueError, 'hash/size'):
            self.acquire()
        self.assertFalse(self.calls('/api/chat'))
        self.assertFalse(self.calls('/api/generate'))

    def test_non_loopback_endpoint_is_refused_before_any_api_request(self):
        for endpoint in ('https://example.com', 'http://127.0.0.1:11434@evil.example', 'http://192.168.1.2:11434'):
            with self.subTest(endpoint=endpoint):
                self.config['endpoint'] = endpoint
                acquisition.save(self.teachers, self.config)
                with self.assertRaisesRegex(ValueError, 'local Ollama'):
                    self.acquire()
                self.assertFalse(self.session.calls)

    def test_redirect_is_rejected_without_following_outside_loopback(self):
        self.session.redirect = True
        with self.assertRaises((ValueError, acquisition.requests.HTTPError)):
            self.acquire()
        self.assertFalse(self.calls('/api/chat'))
        self.assertTrue(self.session.calls)
        self.assertTrue(all(row[3].get('allow_redirects') is False for row in self.session.calls))

    def test_generated_token_bound_rejects_boolean_and_out_of_range_values(self):
        for value in (True, 127, 8193, 1.5):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, '128..8192'):
                self.acquire(max_tokens=value)
        self.assertFalse(self.session.calls)

    def test_already_loaded_selected_teacher_is_not_queried_or_unloaded(self):
        self.session.loaded = True
        with self.assertRaisesRegex(ValueError, 'already loaded'):
            self.acquire()
        self.assertFalse(self.calls('/api/chat'))
        self.assertFalse(self.calls('/api/generate'))
        self.assertFalse((self.root / 'acquisition').exists())

    def test_wrong_response_model_is_not_admitted_and_owned_model_unloads(self):
        self.session.response_model = 'another-synthetic-fixture'
        with self.assertRaisesRegex(ValueError, 'response model differs'):
            self.acquire()
        report = json.loads((self.root / 'acquisition/acquisition.json').read_text())
        self.assertEqual(report['responses'], [])
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(len(self.calls('/api/generate')), 1)
        self.assertTrue(report['teachers'][0]['unloaded'])

    def test_unfinished_response_is_not_admitted_and_owned_model_unloads(self):
        self.session.done = False
        with self.assertRaisesRegex(ValueError, 'completed textual'):
            self.acquire()
        report = json.loads((self.root / 'acquisition/acquisition.json').read_text())
        self.assertFalse(report['responses'])
        self.assertEqual(len(self.calls('/api/generate')), 1)

    def test_length_limited_response_is_retained_but_not_eligible(self):
        report = self.acquire(max_tokens=128)
        self.assertEqual(report['status'], 'completed_with_generation_failures')
        self.assertEqual(report['responses'], [])
        self.assertEqual(len(report['failures']), 1)
        self.assertTrue((self.root / 'acquisition/synthetic_teacher/full_adder_1bit_v1/api_response.json').is_file())
        request = self.calls('/api/chat')[0][2]
        self.assertEqual(request['options']['num_predict'], 128)
        self.assertEqual(request['options']['num_ctx'], 4096)
        self.assertFalse(request['stream'])
        self.assertFalse(self.session.trust_env)

    def test_frozen_prompt_mutation_is_detected_before_any_query(self):
        prompt = self.curriculum / 'full_adder_1bit_v1.prompt.txt'
        prompt.write_text('Changed input must not be sent', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'frozen prompt/oracle'):
            self.acquire()
        self.assertFalse(self.session.calls)

    def test_curriculum_mutation_during_query_cannot_admit_completed_response(self):
        prompt = self.curriculum / 'full_adder_1bit_v1.prompt.txt'
        self.session.done_reason = 'stop'
        self.session.after_chat = lambda: prompt.write_text('mutated during synthetic request', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.acquire()
        report = json.loads((self.root / 'acquisition/acquisition.json').read_text())
        self.assertEqual(report['responses'], [])
        self.assertTrue(report['teachers'][0]['unloaded'])

    def test_model_blob_mutation_during_query_is_detected(self):
        self.session.done_reason = 'stop'
        self.session.after_chat = lambda: self.blob.write_bytes(b'z' * self.teacher['model_artifact_bytes'])
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.acquire()
        report = json.loads((self.root / 'acquisition/acquisition.json').read_text())
        self.assertEqual(report['status'], 'failed')
        self.assertTrue(report['teachers'][0]['unloaded'])

    def test_prompt_change_between_validated_load_and_binding_is_refused(self):
        actual_load = acquisition.load_curriculum
        def changed_after_load(folder):
            frozen = actual_load(folder)
            (folder / 'full_adder_1bit_v1.prompt.txt').write_text('changed after checked read', encoding='utf-8')
            return frozen
        with patch.object(acquisition, 'load_curriculum', side_effect=changed_after_load):
            with self.assertRaises(ValueError):
                self.acquire()
        self.assertFalse(self.session.calls)

    def test_teacher_config_change_during_query_cannot_admit_response(self):
        self.session.done_reason = 'stop'
        self.session.after_chat = lambda: self.teachers.write_text('changed during request', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.acquire()
        report = json.loads((self.root / 'acquisition/acquisition.json').read_text())
        self.assertEqual(report['responses'], [])
        self.assertTrue(report['teachers'][0]['unloaded'])


@unittest.skipIf(jsonschema is None, 'optional jsonschema CPU validator unavailable')
class TeacherResponseSchemaTests(unittest.TestCase):
    def setUp(self):
        profile = dict(profile_id='full_adder_1bit_v1', input_bits=3, output_bits=2)
        self.schema = acquisition.response_format(profile)
        jsonschema.Draft202012Validator.check_schema(self.schema)
        self.validator = jsonschema.Draft202012Validator(self.schema)
        self.value = dict(schema='atomos-teacher-procedure-v1', profile_id=profile['profile_id'],
                          procedures=[dict(name=profile['profile_id'], input_bits=3, output_bits=2,
                          outputs=[['xor', ['input', 0], ['and', ['input', 1], ['not', ['input', 2]]]],
                                   ['or', ['constant', 0], ['constant', 1]]])])

    def test_recursive_array_ast_is_valid_syntax_without_claiming_correct_algorithm(self):
        self.validator.validate(self.value)
        self.value['procedures'][0]['outputs'] = [['constant', 0], ['constant', 0]]
        # Deliberately wrong full-adder semantics still meet syntax. Independent
        # oracle verification, never schema constraints, decides correctness.
        self.validator.validate(self.value)

    def test_stringified_expression_arrays_are_rejected(self):
        self.value['procedures'][0]['outputs'][0] = json.dumps(self.value['procedures'][0]['outputs'][0])
        with self.assertRaises(jsonschema.ValidationError):
            self.validator.validate(self.value)

    def test_input_index_outside_declared_interface_is_rejected(self):
        self.value['procedures'][0]['outputs'][0] = ['input', 3]
        with self.assertRaises(jsonschema.ValidationError):
            self.validator.validate(self.value)

    def test_wrong_schema_and_profile_are_rejected(self):
        for field in ('schema', 'profile_id'):
            value = copy.deepcopy(self.value)
            value[field] = 'another_schema_or_profile'
            with self.subTest(field=field), self.assertRaises(jsonschema.ValidationError):
                self.validator.validate(value)

    def test_wrong_operator_arity_and_output_count_are_rejected(self):
        for expression in (['not', ['input', 0], ['input', 1]], ['xor', ['input', 0]], ['execute', 'code']):
            value = copy.deepcopy(self.value)
            value['procedures'][0]['outputs'][0] = expression
            with self.subTest(expression=expression), self.assertRaises(jsonschema.ValidationError):
                self.validator.validate(value)
        self.value['procedures'][0]['outputs'].pop()
        with self.assertRaises(jsonschema.ValidationError):
            self.validator.validate(self.value)


if __name__ == '__main__':
    unittest.main()
