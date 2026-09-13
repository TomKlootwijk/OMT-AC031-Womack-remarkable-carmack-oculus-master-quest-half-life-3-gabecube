"""CPU-only amendment protocol tests; the native process is explicitly mocked."""
from pathlib import Path
import copy
import csv
import hashlib
import io
import json
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'python'))
import amend_program_bank as amendment
import program_bank as compiler
import program_bank_reference as reference


class AmendmentProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / 'source' / 'bank.bin'
        self.run = self.root / 'source_run'
        self.output = self.root / 'amendment'
        self.exe = self.root / 'mock_native.exe'
        self.atlas = self.root / 'mock.atlas'
        self.exe.write_bytes(b'CPU MOCK ONLY; never executed')
        self.atlas.write_bytes(b'CPU MOCK ONLY; no GPU claim')
        circuit = {'input_bits': 1, 'output_bits': 1, 'constant_zero_wire': 1,
                   'gates': [], 'outputs': [0]}
        capsules = [{'name': f'identity_{i}', 'circuit': copy.deepcopy(circuit),
                     'seed_hex': f'{i + 1:064x}'} for i in range(3)]
        compiler.write_bank(self.source, capsules, master_seed_hex='12' * 32)
        self.before = reference.decode_bank(self.source, self.source.parent / 'manifest.json')
        self.run.mkdir()
        (self.run / 'bank.bin').write_bytes(self.source.read_bytes())
        (self.run / 'COMMITTED').write_text('CPU test fixture only\n', encoding='utf-8')
        summary = {'schema': 'atomOS-program-bank-runtime-v1', 'status': 'passed',
                   'accepted': True, 'committed': True, 'execution_mode': 'chain',
                   'input_initial': 1, 'hops': 2, 'hops_executed': 2,
                   'initial_slot': 0, 'kernel_error': 0}
        (self.run / 'summary.json').write_text(json.dumps(summary), encoding='utf-8')
        self.save_trace(self.run / 'trace.csv', reference.replay(self.before, 1, 2))
        self.arguments = ['amend_program_bank.py', '--bank', str(self.source),
                          '--source-run', str(self.run), '--exe', str(self.exe),
                          '--atlas', str(self.atlas), '--out', str(self.output)]

    @staticmethod
    def save_trace(path, records):
        with path.open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)

    def fake_native(self, command, **kwargs):
        """Emit explicitly synthetic process receipts, never run a GPU process."""
        arguments = dict(zip(command[1::2], command[2::2]))
        target = Path(arguments['--out'])
        target.mkdir()
        source = Path(arguments['--bank'])
        bank = reference.decode_bank(source, source.parent / 'manifest.json')
        initial = int(arguments['--input'])
        first = int(arguments['--initial-slot'])
        hops = int(arguments['--hops'])
        (target / 'bank.bin').write_bytes(source.read_bytes())
        (target / 'operators.atlas').write_bytes(self.atlas.read_bytes())
        (target / 'COMMITTED').write_text('CPU MOCK ONLY\n', encoding='utf-8')
        summary = {'schema': 'atomOS-program-bank-runtime-v1', 'status': 'passed',
                   'accepted': True, 'committed': True, 'execution_mode': 'chain',
                   'input_initial': initial, 'hops': hops, 'hops_executed': hops,
                   'initial_slot': first, 'kernel_error': 0}
        summary.update(getattr(self, 'native_summary_override', {}))
        (target / 'summary.json').write_text(json.dumps(summary), encoding='utf-8')
        self.save_trace(target / 'trace.csv', reference.replay(bank, initial, hops, first))
        return SimpleNamespace(returncode=0)

    def run_main(self, writer=None):
        with patch.object(sys, 'argv', self.arguments), patch.object(sys, 'stdout', io.StringIO()), \
             patch.object(amendment.subprocess, 'run', side_effect=self.fake_native):
            if writer is None:
                return amendment.main()
            with patch.object(amendment, 'write_bank', side_effect=writer):
                return amendment.main()

    def test_cpu_mock_accepts_only_routing_revision(self):
        self.assertEqual(self.run_main(), 0)
        receipt = json.loads((self.output / 'amendment.json').read_text(encoding='utf-8'))
        after = reference.decode_bank(self.output / 'routing_proposal' / 'bank.bin',
                                      self.output / 'routing_proposal' / 'manifest.json')
        self.assertEqual(receipt['original_next_slot'], 1)
        self.assertEqual(receipt['new_next_slot'], 2)
        self.assertEqual(after['capsules'][0]['parent_sha256'], self.before['capsules'][0]['content_sha256'])
        self.assertEqual(amendment.same_skills(self.before, after), 6)
        self.assertTrue((self.output / 'rejected_proposal' / 'REJECTED').is_file())
        active = json.loads((self.output / 'active_bank.json').read_text(encoding='utf-8'))
        self.assertEqual(active['sha256'], after['bank_file_sha256'])

    def test_rejects_changed_seed_even_when_skill_is_identical(self):
        def changed_seed(path, capsules, **kwargs):
            capsules = copy.deepcopy(capsules)
            if Path(path).parent.name == 'routing_proposal':
                capsules[0]['seed_hex'] = 'f' * 64
            return compiler.write_bank(path, capsules, **kwargs)
        with self.assertRaises(ValueError):
            self.run_main(changed_seed)

    def test_rejects_native_rejection_despite_stale_commit_marker(self):
        self.native_summary_override = {'status': 'rejected_verification', 'accepted': False, 'committed': False}
        with self.assertRaises(ValueError):
            self.run_main()

    def test_rejects_candidate_bytes_changed_during_native_call(self):
        native = self.fake_native
        def mutate_candidate(command, **kwargs):
            result = native(command, **kwargs)
            arguments = dict(zip(command[1::2], command[2::2]))
            source = Path(arguments['--bank'])
            raw = bytearray(source.read_bytes())
            raw[24] ^= 1  # Change the bank's master seed without changing its IO.
            source.write_bytes(raw)
            (Path(arguments['--out']) / 'bank.bin').write_bytes(raw)
            return result
        self.fake_native = mutate_candidate
        with self.assertRaises(ValueError):
            self.run_main()

    def test_rejects_equivalent_circuit_rewrite_under_routing_only_policy(self):
        after = copy.deepcopy(self.before)
        old, revised = self.before['capsules'][0], after['capsules'][0]
        revised.update(next_slot=2, version=old['version'] + 1,
                       parent_sha256=old['content_sha256'], content_sha256='f' * 64,
                       gates=[(0, 0)], gate_count=1, ref_width=2, bit_length=1030)
        self.assertEqual(amendment.same_skills(self.before, after), 6)
        with self.assertRaisesRegex(ValueError, 'routing-only'):
            amendment.validate_routing_amendment(self.before, after, 0, 2)

    def test_rejects_nonchain_source_receipt(self):
        path = self.run / 'summary.json'
        summary = json.loads(path.read_text(encoding='utf-8'))
        summary['execution_mode'] = 'domain'
        path.write_text(json.dumps(summary), encoding='utf-8')
        with self.assertRaises(ValueError):
            self.run_main()

    def test_receipt_write_failure_preserves_previous_active_bank(self):
        write_text = Path.write_text
        def fail_receipt(path, *args, **kwargs):
            if path == self.output / 'amendment.json':
                raise OSError('simulated evidence publication failure')
            return write_text(path, *args, **kwargs)
        with patch.object(Path, 'write_text', fail_receipt):
            with self.assertRaisesRegex(OSError, 'simulated evidence'):
                self.run_main()
        active = json.loads((self.output / 'active_bank.json').read_text(encoding='utf-8'))
        self.assertEqual(active['sha256'], hashlib.sha256(self.source.read_bytes()).hexdigest())
        self.assertFalse((self.output / 'COMMITTED').exists())

    def test_pointer_replace_failure_leaves_only_uncommitted_prepared_marker(self):
        replace = Path.replace
        calls = 0
        def fail_final_pointer(path, target):
            nonlocal calls
            if path == self.output / 'active_bank.json.partial':
                calls += 1
                if calls == 2:
                    raise OSError('simulated final pointer failure')
            return replace(path, target)
        with patch.object(Path, 'replace', fail_final_pointer):
            with self.assertRaisesRegex(OSError, 'final pointer'):
                self.run_main()
        active = json.loads((self.output / 'active_bank.json').read_text(encoding='utf-8'))
        self.assertEqual(active['sha256'], hashlib.sha256(self.source.read_bytes()).hexdigest())
        marker = (self.output / 'COMMITTED').read_text(encoding='utf-8').strip()
        self.assertTrue((self.output / 'VERIFIED').exists())
        self.assertNotEqual(marker, active['sha256'])  # Marker alone is not a commit.


if __name__ == '__main__':
    unittest.main()
