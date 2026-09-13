"""CPU typed-query checks. Synthetic fixture records are not teacher/GPU runs."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
sys.path.insert(0, str(ROOT / 'tools'))
import knowledge_admission as admission
import knowledge_queries as queries
import program_bank as codec
import query_knowledge as cli
import teacher_knowledge as teacher


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class KnowledgeQueryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shared = tempfile.TemporaryDirectory(prefix='synthetic_query_fixture_')
        cls.fixture_root = Path(cls.shared.name)
        curriculum = cls.fixture_root / 'curriculum'
        frozen = teacher.prepare_curriculum(curriculum)
        a, b, carry = ['input', 0], ['input', 1], ['input', 2]
        ab = ['xor', a, b]
        expressions = {
            'full_adder_1bit_v1': [['xor', ab, carry], ['or', ['and', a, b], ['and', carry, ab]]],
            'binary_to_gray_4bit_v1': [['xor', ['input', i], ['input', i + 1]] for i in range(3)] + [['input', 3]],
        }
        records = []
        for profile in frozen['profiles']:
            identity = profile['profile_id']
            if identity not in expressions:
                continue
            folder = cls.fixture_root / identity
            folder.mkdir()
            response = json.dumps(dict(schema=teacher.RESPONSE_SCHEMA, profile_id=identity,
                                       procedures=[dict(name=identity, input_bits=profile['input_bits'],
                                                        output_bits=profile['output_bits'], outputs=expressions[identity])])).encode()
            response_path, run_path = folder / 'response.json', folder / 'run.json'
            response_path.write_bytes(response)
            provenance = dict(model_repo='synthetic-test-fixture/no-model-executed', model_revision='a' * 40,
                              model_revision_status='pinned_huggingface_commit',
                              model_artifact_sha256=digest(b'hand-authored test data, not model weights'),
                              prompt_sha256=profile['prompt_sha256'], response_sha256=digest(response))
            run = json.dumps(dict(provenance, scope='synthetic CPU test fixture; no teacher execution')).encode()
            run_path.write_bytes(run)
            provenance['run_sha256'] = digest(run)
            records.append(dict(profile_id=identity, response_path=str(response_path), run_path=str(run_path),
                                provenance=provenance))
        request, receipt = teacher.build_teacher_request(curriculum, records)
        assert receipt['compiled_candidates'] == 2
        cls.fixture = cls.fixture_root / 'bank'
        result = admission.admit_candidates(ROOT / 'examples/program_bank/learned_v1/bank.bin', request, cls.fixture)
        assert result['accepted_capsules'] == 2

    @classmethod
    def tearDownClass(cls):
        cls.shared.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='typed_query_cpu_test_')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.bank = self.folder / 'bank/bank.bin'
        self.bank.parent.mkdir()
        for name in ('bank.bin', 'manifest.json'):
            shutil.copy2(self.fixture / name, self.bank.parent / name)

    def mutate_manifest(self, change):
        path = self.bank.parent / 'manifest.json'
        value = json.loads(path.read_text())
        change(value)
        path.write_text(json.dumps(value), encoding='utf-8')

    def rejected_full_adder(self, change):
        self.mutate_manifest(lambda m: change(m['capsules'][3]['knowledge_admission']))
        registry = queries.load_registry(self.bank)
        self.assertEqual([c['profile_id'] for c in registry['capabilities']], ['binary_to_gray_4bit_v1'])
        self.assertEqual(len(registry['rejected_capabilities']), 1)
        return registry['rejected_capabilities'][0]['reason']

    def test_registry_lists_only_specified_profiles_after_all_24_cpu_cases(self):
        registry = queries.load_registry(self.bank)
        self.assertEqual([c['profile_id'] for c in registry['capabilities']],
                         ['full_adder_1bit_v1', 'binary_to_gray_4bit_v1'])
        self.assertEqual(sum(c['verified_domain_cases'] for c in registry['capabilities']), 24)
        self.assertEqual(registry['rejected_capabilities'], [])
        self.assertNotIn('bank', queries.public_registry(registry))
        self.assertIn('no GPU execution', registry['scope'])

    def test_names_neither_create_nor_remove_capabilities(self):
        def change(manifest):
            manifest['capsules'][0]['name'] = 'unsigned_compare_2bit_v1'
            manifest['capsules'][3]['name'] = 'a completely different display name'
        self.mutate_manifest(change)
        registry = queries.load_registry(self.bank)
        self.assertEqual(len(registry['capabilities']), 2)
        self.assertEqual(queries.plan_query(registry, 'add one-bit 1 0 carry 1')['capability']['program_id'], 3)
        self.assertEqual(queries.plan_query(registry, 'compare 2 3')['status'], 'unknown')

    def test_swapped_input_labels_reject_profile(self):
        reason = self.rejected_full_adder(lambda a: a['source'].update(input_labels=['carry_in', 'b', 'a']))
        self.assertIn('labels', reason)

    def test_wrong_output_labels_reject_profile(self):
        self.rejected_full_adder(lambda a: a['source'].update(output_labels=['carry_out', 'sum']))

    def test_changed_specification_rejects_profile(self):
        self.rejected_full_adder(lambda a: a['source'].update(reference='full_adder_1bit_v1: a made-up specification'))

    def test_wrong_source_kind_rejects_profile(self):
        self.rejected_full_adder(lambda a: a['source'].update(kind='unverified-model-answer'))

    def test_unpinned_teacher_revision_is_not_a_pinned_capability(self):
        self.rejected_full_adder(lambda a: a['source']['teacher_proposal'].update(model_revision='main'))

    def test_missing_teacher_artifact_digest_rejects_profile(self):
        self.rejected_full_adder(lambda a: a['source']['teacher_proposal'].pop('model_artifact_sha256'))

    def test_changed_oracle_digest_rejects_profile(self):
        self.assertIn('oracle digest', self.rejected_full_adder(lambda a: a.update(oracle_record_sha256='0' * 64)))

    def test_changed_semantic_digest_rejects_profile(self):
        self.assertIn('semantic digest', self.rejected_full_adder(lambda a: a.update(semantic_sha256='0' * 64)))

    def test_oracle_identifier_requires_known_frontend_and_numeric_suffix(self):
        self.assertIn('oracle identity', self.rejected_full_adder(lambda a: a.update(oracle_id='full_adder_1bit_v1:response:arbitrary')))

    def test_expression_frontend_oracle_prefix_is_allowed_when_rebound(self):
        def change(manifest):
            metadata = manifest['capsules'][3]['knowledge_admission']
            metadata['oracle_id'] = 'full_adder_1bit_v1:expression-response:0'
            oracle = dict(id=metadata['oracle_id'], kind='fixed-domain-oracle', independent_of_candidate=True,
                          input_bits=3, output_bits=2, source=metadata['source'],
                          cases=[dict(input=x, output=teacher.scalar_oracle('full_adder_1bit_v1', x)) for x in range(8)])
            metadata['oracle_record_sha256'] = digest(queries.canonical(oracle))
        self.mutate_manifest(change)
        self.assertEqual(len(queries.load_registry(self.bank)['capabilities']), 2)

    def test_corrupt_packed_bank_is_rejected(self):
        raw = bytearray(self.bank.read_bytes())
        raw[-1] ^= 1
        self.bank.write_bytes(raw)
        with self.assertRaises(ValueError):
            queries.load_registry(self.bank)

    def test_validly_repacked_wrong_algorithm_is_rejected_by_full_oracle(self):
        loaded = codec.load_bank(self.bank)
        capsules = copy.deepcopy(loaded['capsules'])
        capsules[3]['circuit']['outputs'] = [3, 3]
        wrong = self.folder / 'wrong/bank.bin'
        manifest = codec.write_bank(wrong, capsules, master_seed_hex=loaded['master_seed_hex'])
        for old, new in zip(loaded['capsules'], manifest['capsules']):
            if 'knowledge_admission' in old:
                new['knowledge_admission'] = old['knowledge_admission']
        (wrong.parent / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        registry = queries.load_registry(wrong)
        self.assertIn('full-domain mismatch at 1', registry['rejected_capabilities'][0]['reason'])
        self.assertEqual(len(registry['capabilities']), 1)

    def test_all_six_grammar_forms_pack_documented_bit_order(self):
        cases = [('add one-bit 1 0 carry 1', 'full_adder_1bit_v1', 5, 2),
                 ('gray 11', 'binary_to_gray_4bit_v1', 11, 14),
                 ('compare 2 3', 'unsigned_compare_2bit_v1', 14, 1),
                 ('add 2 3', 'unsigned_add_2bit_v1', 14, 5),
                 ('difference 1 3', 'absolute_difference_2bit_v1', 13, 2),
                 ('select 2 1 if 1', 'mux_2bit_v1', 22, 1)]
        for text, identity, packed, expected in cases:
            with self.subTest(text=text):
                parsed = queries.parse_query(text)
                self.assertEqual((parsed['profile_id'], parsed['packed_input']), (identity, packed))
                self.assertEqual(teacher.scalar_oracle(identity, packed), expected)
                parsed['expected_output'] = expected
                self.assertIsInstance(queries.decode_answer(parsed, expected)['answer'], str)

    def test_exact_grammar_allows_case_and_whitespace_normalization(self):
        parsed = queries.parse_query('  ADD\tONE-BIT 1 0 CARRY 1\n')
        self.assertEqual((parsed['status'], parsed['packed_input']), ('parsed', 5))

    def test_out_of_domain_has_no_answer(self):
        for text in ('gray 16', 'gray -1', 'add 4 1', 'add one-bit 2 0 carry 1', 'select 2 1 if 2'):
            with self.subTest(text=text):
                result = queries.parse_query(text)
                self.assertEqual((result['status'], result['reason']), ('unknown', 'out_of_domain'))
                self.assertIsNone(result['answer'])
                self.assertEqual(result['gpu_execution'], 'not_run')

    def test_unsupported_prose_float_code_and_oversized_queries_are_unknown(self):
        for text in ('please gray 11', 'gray 1.1', 'gray 11; launch()', 'gray 11 then add 2 3', '', 'x' * 257, None):
            with self.subTest(text=text):
                self.assertEqual(queries.parse_query(text)['status'], 'unknown')

    def test_unknown_or_unavailable_query_never_launches_native_or_creates_output(self):
        for index, text in enumerate(('gray 16', 'please answer me', 'compare 2 3')):
            out = self.folder / ('must_not_launch' + str(index))
            with patch.object(cli.subprocess, 'run') as native:
                result = cli.execute_query(bank=self.bank, query=text, exe='absent.exe', atlas='absent.atlas', out=out)
            native.assert_not_called()
            self.assertEqual((result['status'], result['gpu_execution']), ('unknown', 'not_run'))
            self.assertIsNone(result['answer'])
            self.assertFalse(out.exists())

    def test_supported_query_requires_native_artifacts(self):
        with patch.object(cli.subprocess, 'run') as native:
            with self.assertRaisesRegex(ValueError, 'requires --exe'):
                cli.execute_query(bank=self.bank, query='gray 11')
            native.assert_not_called()

    def test_failed_native_process_retains_failure_and_never_uses_cpu_as_answer(self):
        exe, atlas, out = self.folder / 'unused.exe', self.folder / 'unused.atlas', self.folder / 'failed'
        exe.write_bytes(b'not an executable; synthetic failure test')
        atlas.write_bytes(b'not an atlas; synthetic failure test')
        with patch.object(cli.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1)):
            with self.assertRaisesRegex(RuntimeError, 'native knowledge query failed'):
                cli.execute_query(bank=self.bank, query='gray 11', exe=exe, atlas=atlas, out=out)
        report = json.loads((out / 'query.json').read_text())
        self.assertEqual(report['status'], 'failed')
        self.assertIsNone(report['answer'])
        self.assertNotEqual(report['gpu_execution'], 'run_and_independently_verified')

    def test_zero_exit_without_native_evidence_is_not_an_answer(self):
        exe, atlas, out = self.folder / 'unused.exe', self.folder / 'unused.atlas', self.folder / 'missing_evidence'
        exe.write_bytes(b'synthetic no-evidence test')
        atlas.write_bytes(b'synthetic no-evidence test')
        with patch.object(cli.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)):
            with self.assertRaises(OSError):
                cli.execute_query(bank=self.bank, query='gray 11', exe=exe, atlas=atlas, out=out)
        report = json.loads((out / 'query.json').read_text())
        self.assertEqual(report['status'], 'failed')
        self.assertIsNone(report['answer'])

    def test_dependency_mutation_after_attempt_cannot_return_answer(self):
        exe, atlas, out = self.folder / 'unused.exe', self.folder / 'unused.atlas', self.folder / 'mutated'
        exe.write_bytes(b'synthetic mutation test')
        atlas.write_bytes(b'synthetic mutation test')
        def mutate(*args, **kwargs):
            atlas.write_bytes(b'changed during attempted native invocation')
            return subprocess.CompletedProcess([], 0)
        with patch.object(cli.subprocess, 'run', side_effect=mutate):
            with self.assertRaisesRegex(ValueError, 'dependency changed'):
                cli.execute_query(bank=self.bank, query='gray 11', exe=exe, atlas=atlas, out=out)
        self.assertIsNone(json.loads((out / 'query.json').read_text())['answer'])

    def test_output_decoder_rejects_mismatch_and_boolean_integer_alias(self):
        plan = queries.plan_query(queries.load_registry(self.bank), 'gray 11')
        for value in (13, True, '14', None):
            with self.assertRaisesRegex(ValueError, 'native output disagrees'):
                queries.decode_answer(plan, value)


if __name__ == '__main__':
    unittest.main()
