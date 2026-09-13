"""CPU-only evidence-wrapper regressions; native subprocesses are mocked."""
from pathlib import Path
import csv
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
import validate_program_bank as study
from program_bank_reference import decode_bank, replay


class StudyRejectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.bank_path = ROOT / 'examples/program_bank/learned_v1/bank.bin'
        self.bank = decode_bank(self.bank_path, self.bank_path.parent / 'manifest.json')
        self.atlas = self.directory / 'operators.atlas'
        self.atlas.write_bytes(b'CPU mock operator payload')
        self.exe = self.directory / 'native.exe'
        self.exe.write_bytes(b'CPU MOCK: never execute this file')
        self.output = self.directory / 'study'
        self.arguments = ['validate_program_bank.py', '--exe', str(self.exe), '--bank', str(self.bank_path),
                          '--atlas', str(self.atlas), '--out', str(self.output)]

    def fake_native(self, command, **kwargs):
        arguments = dict(zip(command[1::2], command[2::2]))
        if arguments['--inject'] != 'none':
            # The reproduced Windows copy_file failure exits 1 without a receipt.
            return SimpleNamespace(returncode=1)
        folder = Path(arguments['--out'])
        folder.mkdir()
        (folder / 'bank.bin').write_bytes(self.bank_path.read_bytes())
        (folder / 'operators.atlas').write_bytes(self.atlas.read_bytes())
        (folder / 'COMMITTED').write_text('CPU MOCK ONLY\n', encoding='utf-8')
        mode = arguments['--mode']
        (folder / 'summary.json').write_text(json.dumps({'accepted': True, 'execution_mode': mode}), encoding='utf-8')
        first, hops = int(arguments['--initial-slot']), int(arguments['--hops'])
        if mode == 'domain':
            values = []
            for x in range(hops):
                row = replay(self.bank, x, 1, first)[0]
                row['hop'] = x
                values.append(row)
        else:
            values = replay(self.bank, int(arguments['--input']), hops, first)
        with (folder / 'trace.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(values[0]))
            writer.writeheader()
            writer.writerows(values)
        return SimpleNamespace(returncode=0)

    def test_application_failure_is_not_evidence_of_fault_rejection(self):
        with patch.object(sys, 'argv', self.arguments), patch.object(sys, 'stdout', io.StringIO()), \
             patch.object(study.subprocess, 'run', side_effect=self.fake_native):
            with self.assertRaises(ValueError):
                study.main()

    def rejected_fixture(self):
        folder = self.directory / 'rejected'
        folder.mkdir()
        receipt = {'schema': 'atomOS-program-bank-runtime-v1', 'status': 'rejected_verification',
                   'accepted': False, 'committed': False, 'injection': 'program',
                   'execution_mode': 'chain', 'initial_slot': 0, 'input_initial': 7,
                   'committed_program_id': 0, 'committed_input': 7}
        (folder / 'summary.json').write_text(json.dumps(receipt), encoding='utf-8')
        (folder / 'REJECTED').write_text('CPU MOCK ONLY\n', encoding='utf-8')
        (folder / 'bank.bin').write_bytes(self.bank_path.read_bytes())
        (folder / 'operators.atlas').write_bytes(self.atlas.read_bytes())
        return folder, receipt

    def check_rejection(self, folder, exit_code=2):
        return study.verify_injected_rejection(folder, exit_code, bank_path=self.bank_path,
                    atlas_path=self.atlas, initial_slot=0, input_value=7, injection='program')

    def test_valid_rejection_requires_retained_initial_state_and_input_bytes(self):
        folder, receipt = self.rejected_fixture()
        self.assertEqual(self.check_rejection(folder), receipt)
        (folder / 'operators.atlas').write_bytes(b'wrong copied atlas')
        with self.assertRaisesRegex(ValueError, 'input binding'):
            self.check_rejection(folder)

    def test_exit_one_cannot_be_relabelled_using_rejection_artifacts(self):
        folder, _ = self.rejected_fixture()
        with self.assertRaisesRegex(ValueError, 'exit code 2'):
            self.check_rejection(folder, 1)

    def test_conflicting_marker_or_changed_committed_state_is_rejected(self):
        folder, receipt = self.rejected_fixture()
        for field, value in (('committed_program_id', 1), ('committed_input', 0),
                             ('accepted', True), ('committed', True), ('status', 'passed'),
                             ('schema', 'unknown'), ('injection', 'output')):
            with self.subTest(field=field):
                mutated = dict(receipt, **{field: value})
                (folder / 'summary.json').write_text(json.dumps(mutated), encoding='utf-8')
                with self.assertRaises(ValueError):
                    self.check_rejection(folder)
        (folder / 'summary.json').write_text(json.dumps(receipt), encoding='utf-8')
        (folder / 'COMMITTED').write_text('stale marker\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'exclusive REJECTED'):
            self.check_rejection(folder)


if __name__ == '__main__':
    unittest.main()
