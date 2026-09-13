"""Synthetic acquire-to-compile frontend binding regressions; no model/API/GPU.

All returned procedures below are hand-authored test fixtures, never recorded
as actual teacher-generated knowledge. The HTTP session is entirely in memory.
"""
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
for directory in ('python', 'tools', 'tests'):
    sys.path.insert(0, str(ROOT / directory))
import acquire_teacher_knowledge as acquisition
import compile_teacher_knowledge as compiler
import teacher_expression_frontend as expression
import teacher_knowledge as original
import test_teacher_acquisition as fixtures


def hand_authored_response(profile, frontend):
    if frontend == 'boolean-expression':
        schema = expression.RESPONSE_SCHEMA
        outputs = ['(a ^ b) ^ carry_in', '(a & b) | (carry_in & (a ^ b))']
    else:
        schema = original.RESPONSE_SCHEMA
        a, b, carry = ['input', 0], ['input', 1], ['input', 2]
        outputs = [['xor', ['xor', a, b], carry],
                   ['or', ['and', a, b], ['and', carry, ['xor', a, b]]]]
    return json.dumps({'schema': schema, 'profile_id': profile,
                       'procedures': [{'name': profile, 'input_bits': 3,
                                       'output_bits': 2, 'outputs': outputs}]})


class CompletedSyntheticSession(fixtures.SyntheticSession):
    def __init__(self, show, model, content):
        super().__init__(show, model)
        self.content = content

    def request(self, method, url, data=None, **kwargs):
        response = super().request(method, url, data=data, **kwargs)
        if url.endswith('/api/chat'):
            return fixtures.SyntheticResponse({
                'model': self.model, 'done': True, 'done_reason': 'stop',
                'message': {'role': 'assistant', 'content': self.content},
                'total_duration': 100, 'load_duration': 1, 'prompt_eval_count': 25,
                'prompt_eval_duration': 10, 'eval_count': 20, 'eval_duration': 89})
        return response


class TeacherFrontendSelectionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.TeacherAcquisitionTests(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.identity = 'full_adder_1bit_v1'
        self.original_curriculum = self.fixture.curriculum
        self.curriculum = self.root / 'curriculum_v2'
        self.manifest = expression.freeze_curriculum(
            self.curriculum, oracle_curriculum=self.original_curriculum)
        self.acquisition = self.root / 'acquisition_v2'
        self.base = ROOT / 'examples/program_bank/learned_v1/bank.bin'
        self.out = self.root / 'compiled'
        self.report, self.session = self.acquire('boolean-expression', self.curriculum, self.acquisition)
        self.folder = self.acquisition / self.fixture.teacher['id'] / self.identity

    def acquire(self, frontend, curriculum, out, *, use_default=False):
        session = CompletedSyntheticSession(
            self.fixture.show, self.fixture.teacher['ollama_model'],
            hand_authored_response(self.identity, frontend))
        selected = {} if use_default else {'frontend': frontend}
        with patch.object(acquisition.requests, 'Session', return_value=session), redirect_stdout(io.StringIO()):
            report = acquisition.acquire(curriculum=curriculum, teachers=self.fixture.teachers,
                                         out=out, **selected)
        return report, session

    def compile(self, *, frontend='boolean-expression', curriculum=None, source=None, out=None):
        return compiler.compile_acquisition(curriculum=curriculum or self.curriculum,
                                            acquisition=source or self.acquisition,
                                            base_bank=self.base, out=out or self.out,
                                            frontend=frontend)

    def save_report(self):
        compiler.save(self.acquisition / 'acquisition.json', self.report)

    def change_run(self, change):
        path = self.folder / 'run.json'
        run = compiler.decode_json(path.read_bytes())
        change(run)
        compiler.save(path, run)
        self.report['responses'][0]['provenance']['run_sha256'] = compiler.sha(path.read_bytes())
        self.save_report()

    def preflight_rejected(self, frontend='boolean-expression'):
        with patch.object(expression, 'build_request', side_effect=AssertionError('adapter began before binding checks')) as v2, \
             patch.object(original, 'build_teacher_request', side_effect=AssertionError('wrong adapter selected')) as v1:
            with self.assertRaises(ValueError):
                self.compile(frontend=frontend)
            v2.assert_not_called()
            v1.assert_not_called()
        self.assertFalse(self.out.exists())

    def test_v2_acquisition_binds_actual_selected_prompt_schema_and_module(self):
        self.assertEqual(self.report['status'], 'completed')
        self.assertEqual(self.report['frontend'], 'boolean-expression')
        self.assertIn(str((ROOT / 'python/teacher_expression_frontend.py').resolve()),
                      self.report['dependency_sha256'])
        chats = [call for call in self.session.calls if call[1].endswith('/api/chat')]
        self.assertEqual(len(chats), 1)
        sent = chats[0][2]
        self.assertEqual(sent['format'], expression.response_format(self.identity))
        self.assertEqual(sent['messages'], [{'role': 'user', 'content': expression.prompt(self.identity)}])
        run = compiler.decode_json((self.folder / 'run.json').read_bytes())
        self.assertEqual(run['frontend'], 'boolean-expression')
        self.assertFalse(run['teacher_generated_code_executed'])
        self.assertTrue(self.report['teachers'][0]['unloaded'])

    def test_valid_v2_synthetic_acquisition_compiles_and_admits_exact_full_adder(self):
        result = self.compile()
        self.assertEqual(result['frontend'], 'boolean-expression')
        self.assertEqual(result['status'], 'prepared')
        self.assertEqual(result['accepted_programs'], 1)
        self.assertEqual(result['repeat_check'], 'verified_no_growth')
        self.assertEqual(result['model_or_api_calls'], 0)
        self.assertEqual(result['gpu_execution'], 'not_run')
        self.assertFalse(result['new_active_bank_published'])
        adapter = compiler.decode_json((self.out / 'adapter.json').read_bytes())
        self.assertEqual(adapter['schema'], 'atomos-teacher-expression-adapter-receipt-v2')
        candidates = compiler.decode_json((self.out / 'candidates.json').read_bytes())
        self.assertEqual(candidates['oracles'][0]['cases'], [
            {'input': x, 'output': (x & 1) + ((x >> 1) & 1) + ((x >> 2) & 1)}
            for x in range(8)])

    def test_original_oracle_bytes_are_reused_exactly_and_retained_by_compiler(self):
        source_manifest = original.load_curriculum(self.original_curriculum)['manifest']
        source_record = source_manifest['profiles'][0]
        original_bytes = (self.original_curriculum / source_record['oracle_file']).read_bytes()
        record = self.manifest['profiles'][0]
        self.assertEqual((self.curriculum / record['oracle_file']).read_bytes(), original_bytes)
        self.assertEqual(record['oracle_sha256'], source_record['oracle_sha256'])
        self.assertEqual(record['source_oracle_sha256'], source_record['oracle_sha256'])
        self.assertEqual((self.curriculum / 'source_curriculum.json').read_bytes(),
                         (self.original_curriculum / 'curriculum.json').read_bytes())
        self.compile()
        retained = compiler.decode_json((self.out / 'retained_dependencies.json').read_bytes())
        oracle = next(item for item in retained if Path(item['original_path']) == self.curriculum / record['oracle_file'])
        self.assertEqual((self.out / oracle['retained_file']).read_bytes(), original_bytes)

    def test_selected_v1_cannot_compile_v2_acquisition(self):
        self.preflight_rejected('boolean-tree')

    def test_report_frontend_mismatch_rejects_before_adapter(self):
        self.report['frontend'] = 'boolean-tree'
        self.save_report()
        self.preflight_rejected()

    def test_missing_v2_report_frontend_does_not_downgrade_silently(self):
        del self.report['frontend']
        self.save_report()
        self.preflight_rejected()

    def test_rehashed_run_frontend_mismatch_rejects_before_adapter(self):
        self.change_run(lambda run: run.update(frontend='boolean-tree'))
        self.preflight_rejected()

    def test_rehashed_missing_v2_run_frontend_rejects_before_adapter(self):
        self.change_run(lambda run: run.pop('frontend'))
        self.preflight_rejected()

    def test_missing_v2_module_dependency_rejects_before_adapter(self):
        self.report['dependency_sha256'].pop(str((ROOT / 'python/teacher_expression_frontend.py').resolve()))
        self.save_report()
        self.preflight_rejected()

    def test_rehashed_incompatible_v2_request_schema_rejects_before_adapter(self):
        request_path = self.folder / 'request.json'
        request = compiler.decode_json(request_path.read_bytes())
        request['format'] = {'type': 'null'}
        compiler.save(request_path, request)
        self.change_run(lambda run: run.update(request_sha256=compiler.sha(request_path.read_bytes())))
        self.preflight_rejected()

    def test_rehashed_v2_request_cannot_replace_exact_schema_with_generic_json(self):
        request_path = self.folder / 'request.json'
        request = compiler.decode_json(request_path.read_bytes())
        request['format'] = 'json'
        compiler.save(request_path, request)
        self.change_run(lambda run: run.update(request_sha256=compiler.sha(request_path.read_bytes())))
        self.preflight_rejected()

    def test_rehashed_curriculum_cannot_substitute_original_oracle_serialization(self):
        manifest_path = self.curriculum / 'curriculum.json'
        manifest = compiler.decode_json(manifest_path.read_bytes())
        record = manifest['profiles'][0]
        oracle_path = self.curriculum / record['oracle_file']
        changed = oracle_path.read_bytes() + b' '
        oracle_path.write_bytes(changed)
        record['oracle_sha256'] = compiler.sha(changed)
        record['source_oracle_sha256'] = compiler.sha(changed)
        compiler.save(manifest_path, manifest)
        for path in (manifest_path, oracle_path):
            self.report['dependency_sha256'][str(path.resolve())] = compiler.sha(path.read_bytes())
        self.save_report()
        self.preflight_rejected()

    def test_original_v1_defaults_still_acquire_and_compile(self):
        source = self.root / 'acquisition_v1'
        report, session = self.acquire('boolean-tree', self.original_curriculum, source, use_default=True)
        self.assertEqual(report['frontend'], 'boolean-tree')
        chats = [call for call in session.calls if call[1].endswith('/api/chat')]
        profile = original.load_curriculum(self.original_curriculum)['manifest']['profiles'][0]
        self.assertEqual(chats[0][2]['format'], acquisition.response_format(profile))
        result = compiler.compile_acquisition(curriculum=self.original_curriculum, acquisition=source,
                                              base_bank=self.base, out=self.root / 'v1_compiled')
        self.assertEqual(result['frontend'], 'boolean-tree')
        self.assertEqual(result['accepted_programs'], 1)

    def test_legacy_v1_missing_frontend_fields_and_generic_json_still_compile(self):
        source = self.root / 'acquisition_legacy_v1'
        report, _ = self.acquire('boolean-tree', self.original_curriculum, source)
        report.pop('frontend')
        folder = source / self.fixture.teacher['id'] / self.identity
        request = compiler.decode_json((folder / 'request.json').read_bytes())
        request['format'] = 'json'
        compiler.save(folder / 'request.json', request)
        run = compiler.decode_json((folder / 'run.json').read_bytes())
        run.pop('frontend')
        run['request_sha256'] = compiler.sha((folder / 'request.json').read_bytes())
        compiler.save(folder / 'run.json', run)
        report['responses'][0]['provenance']['run_sha256'] = compiler.sha((folder / 'run.json').read_bytes())
        compiler.save(source / 'acquisition.json', report)
        result = compiler.compile_acquisition(curriculum=self.original_curriculum, acquisition=source,
                                              base_bank=self.base, out=self.root / 'legacy_v1_compiled')
        self.assertEqual(result['frontend'], 'boolean-tree')
        self.assertEqual(result['accepted_programs'], 1)


if __name__ == '__main__':
    unittest.main()
