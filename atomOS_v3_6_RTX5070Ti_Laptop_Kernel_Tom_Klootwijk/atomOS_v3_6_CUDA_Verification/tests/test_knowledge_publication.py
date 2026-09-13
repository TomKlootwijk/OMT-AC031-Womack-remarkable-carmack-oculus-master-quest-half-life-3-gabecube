"""CPU regressions for fail-closed publication; these do not simulate GPU passes."""
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
from knowledge_admission import admit_candidates, demo_request
import validate_knowledge_bank as publication


class KnowledgePublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='atomos_publication_test_')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.base = self.root / 'base/bank.bin'
        self.base.parent.mkdir()
        for name in ('bank.bin', 'manifest.json'):
            shutil.copy2(ROOT / 'examples/program_bank/learned_v1' / name, self.base.parent / name)
        self.admission = self.root / 'admission'
        self.request = demo_request(self.base)
        admit_candidates(self.base, self.request, self.admission)

    def rewrite(self, filename, change):
        path = self.admission / filename
        value = publication.read_json(path)
        change(value)
        publication.save_json(path, value)

    def assert_invalid_before_native(self):
        out = self.root / 'must_not_publish'
        with patch.object(publication.subprocess, 'run', side_effect=AssertionError('native work must not begin')) as native:
            with self.assertRaises((ValueError, OSError, KeyError)):
                publication.validate_and_publish(exe=self.root / 'missing.exe', base_bank=self.base,
                                                 admission=self.admission, atlas=self.root / 'missing.atlas', out=out)
            native.assert_not_called()
        self.assertFalse(out.exists())

    def test_valid_preflight_independently_checks_original_and_novel_functions(self):
        checked = publication.preflight_admission(self.base, self.admission)
        self.assertEqual(checked['accepted_slots'], [3])
        self.assertEqual(checked['preserved_base_cases'], 192)
        self.assertEqual(checked['independently_checked_oracle_cases'], 64)
        self.assertEqual(len(checked['bindings']), 6)

    def test_missing_admission_receipt_fails_before_native_or_publication(self):
        (self.admission / 'admission.json').unlink()
        self.assert_invalid_before_native()

    def test_fabricated_accepted_decision_fails_before_native(self):
        self.rewrite('admission.json', lambda value: value['decisions'][0].update(status='accepted', slot=4))
        self.assert_invalid_before_native()

    def test_manifest_provenance_rewrite_cannot_bypass_bank_hash(self):
        self.rewrite('manifest.json', lambda value: value['capsules'][-1]['knowledge_admission']['source'].update(reference='different evidence'))
        self.assert_invalid_before_native()

    def test_oracle_change_with_rehashed_request_still_requires_readmission(self):
        self.rewrite('candidates.json', lambda value: value['oracles'][1]['cases'][0].update(output=1))
        request = publication.read_json(self.admission / 'candidates.json')
        digest = publication.hashlib.sha256(publication.canonical(request)).hexdigest()
        self.rewrite('admission.json', lambda value: value.update(request_sha256=digest))
        self.assert_invalid_before_native()

    def test_changed_proposal_bytes_fail_before_native(self):
        path = self.admission / 'bank.bin'
        raw = bytearray(path.read_bytes())
        raw[-1] ^= 1
        path.write_bytes(raw)
        self.rewrite('admission.json', lambda value: value.update(proposed_bank_sha256=publication.file_hash(path)))
        self.assert_invalid_before_native()

    def test_changed_base_manifest_is_detected(self):
        path = self.base.parent / 'manifest.json'
        value = publication.read_json(path)
        value['capsules'][0]['name'] = 'renamed after admission'
        publication.save_json(path, value)
        self.assert_invalid_before_native()

    def test_invalid_limits_fail_without_native(self):
        self.rewrite('admission.json', lambda value: value['limits'].update(candidate_limit=True))
        self.assert_invalid_before_native()

    def test_process_failure_retains_base_pointer_and_no_commit_marker(self):
        # Simulate only a failed subprocess, never a passing GPU execution.
        exe, atlas = self.root / 'unused.exe', self.root / 'unused.atlas'
        exe.write_bytes(b'never executed')
        atlas.write_bytes(b'never executed')
        out = self.root / 'failure_evidence'
        with patch.object(publication.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1)):
            with self.assertRaisesRegex(RuntimeError, 'domain study failed'):
                publication.validate_and_publish(exe=exe, base_bank=self.base, admission=self.admission,
                                                 atlas=atlas, out=out)
        pointer = publication.read_json(out / 'active_bank.json')
        self.assertEqual(pointer['sha256'], publication.file_hash(self.base))
        self.assertEqual(pointer['publication_sequence'], 0)
        self.assertFalse((out / 'COMMITTED').exists())
        self.assertTrue(publication.read_json(out / 'publication.json')['active_pointer_retained'])

    def test_missing_native_receipt_cannot_establish_success(self):
        with self.assertRaises(OSError):
            publication.verify_native(self.root / 'no_native_run', {}, bank_hash='unused', atlas_hash='unused',
                                      layout='linear', mode='domain', first=0, value=0, hops=64)

    def test_incomplete_native_success_receipt_is_rejected(self):
        folder = self.root / 'fabricated'
        folder.mkdir()
        publication.save_json(folder / 'summary.json', dict(schema='atomOS-program-bank-runtime-v1',
                              status='passed', accepted=True, committed=True, execution_mode='domain',
                              layout='linear', injection='none', initial_slot=0, input_initial=0,
                              hops=64, hops_executed=63, kernel_error=0, topology='klein_m1_angular_twist'))
        with self.assertRaisesRegex(ValueError, 'hops_executed'):
            publication.verify_native(folder, {}, bank_hash='unused', atlas_hash='unused',
                                      layout='linear', mode='domain', first=0, value=0, hops=64)

    def test_domain_study_missing_runs_is_not_a_gpu_pass(self):
        folder = self.root / 'missing_runs'
        folder.mkdir()
        publication.save_json(folder / 'study.json', dict(schema='atomos-program-bank-study-v1', status='passed',
                              domain_only=True, smoke_only=False, executable_sha256='exe', bank_file_sha256='bank',
                              atlas_sha256='atlas', native_runs=0, runs=[]))
        with self.assertRaisesRegex(ValueError, 'missing or duplicating'):
            publication.verify_domain_study(folder, {'capsule_count': 4}, bank_hash='bank', atlas_hash='atlas',
                                            exe_hash='exe', sanitizer=True)

    def test_dependency_mutation_prevents_atomic_handoff(self):
        pointer, dependency = self.root / 'active.json', self.root / 'dependency'
        publication.save_json(pointer, {'sha256': 'base'})
        original = pointer.read_bytes()
        dependency.write_bytes(b'before')
        bindings = {str(dependency): publication.file_hash(dependency)}
        dependency.write_bytes(b'after')
        with self.assertRaisesRegex(ValueError, 'dependency changed'):
            publication.publish_pointer(pointer, {'sha256': 'proposal'}, bindings=bindings, expected_previous=original)
        self.assertEqual(pointer.read_bytes(), original)

    def test_changed_active_pointer_is_not_overwritten(self):
        pointer = self.root / 'active.json'
        publication.save_json(pointer, {'sha256': 'base'})
        original = pointer.read_bytes()
        publication.save_json(pointer, {'sha256': 'other verified revision'})
        changed = pointer.read_bytes()
        with self.assertRaisesRegex(ValueError, 'active bank changed'):
            publication.publish_pointer(pointer, {'sha256': 'proposal'}, bindings={}, expected_previous=original)
        self.assertEqual(pointer.read_bytes(), changed)

    def test_self_reference_is_valid_without_optional_switch_requirement(self):
        self.assertFalse(publication.checked_switch([3], first=3, base_count=3))
        self.assertTrue(publication.checked_switch([0, 1, 2, 3], first=3, base_count=3, require_switch=True))
        with self.assertRaisesRegex(ValueError, 'requested chain'):
            publication.checked_switch([3], first=3, base_count=3, require_switch=True)

    def test_changed_verified_trace_prevents_handoff(self):
        pointer, trace = self.root / 'active.json', self.root / 'trace.csv'
        publication.save_json(pointer, {'sha256': 'base'})
        original = pointer.read_bytes()
        trace.write_bytes(b'hop,input,output\n0,7,0\n')
        bindings = {str(trace): publication.file_hash(trace)}
        trace.write_bytes(b'hop,input,output\n0,7,1\n')
        with self.assertRaisesRegex(ValueError, 'dependency changed'):
            publication.publish_pointer(pointer, {'sha256': 'proposal'}, bindings=bindings, expected_previous=original)
        self.assertEqual(pointer.read_bytes(), original)

    def test_contradictory_final_state_in_real_saved_receipt_is_rejected(self):
        # Retained actual native evidence supplies the control. Only receipt
        # mutations are synthetic; no mocked GPU success is created here.
        folder = ROOT / 'results/program_bank_20260913/verified_study/domain_linear_0'
        receipt = publication.read_json(folder / 'summary.json')
        bank = publication.decode_bank(self.base, self.base.parent / 'manifest.json')
        for field in ('final_program_id', 'committed_program_id', 'final_input', 'committed_input'):
            with self.subTest(field=field):
                changed = dict(receipt, **{field: 999999})
                with patch.object(publication, 'read_json', return_value=changed):
                    with self.assertRaisesRegex(ValueError, 'committed state mismatch'):
                        publication.verify_native(folder, bank, bank_hash=publication.file_hash(self.base),
                                                  atlas_hash=publication.file_hash(folder / 'operators.atlas'),
                                                  layout='linear', mode='domain', first=0, value=0, hops=64)


if __name__ == '__main__':
    unittest.main()
