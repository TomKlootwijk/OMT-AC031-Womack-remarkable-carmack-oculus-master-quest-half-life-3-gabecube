"""CPU oracle/mutation regressions; optional retained native fixture via env."""
import csv
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from sdf_lineage_reference import canonical, emission, proposals, verify_export, U64


class GeometryTests(unittest.TestCase):
    def test_multiwrap(self):
        for width in (1, 2, 31, 32, 33, 257):
            for winding in range(-5, 6):
                for row in range(3):
                    self.assertEqual(canonical(row, winding * width, 3, width),
                                     (2 - row if winding % 2 else row, 0, winding % 2))

    def test_zero_phi_preserves_ids(self):
        children = proposals([dict(id=1, row=1, angle=2)], 3, 32, 0, 'source')
        self.assertEqual([child['id'] for child in children], [2, 3])
        self.assertEqual([child['diagnostic_status'] for child in children], [1, 1])
        self.assertEqual(sum(word.bit_count() for word in emission(children, 3, 32)), 1)

    def test_empty_no_resurrection(self):
        self.assertEqual(proposals([], 3, 32, 1, 'source'), [])
        self.assertEqual(emission([], 3, 32), [0, 0, 0])

    def test_last_valid_id(self):
        children = proposals([dict(id=U64 // 2, row=0, angle=0)], 3, 32, 1, 'source')
        self.assertEqual([child['id'] for child in children], [U64 - 1, U64])
        with self.assertRaises(OverflowError):
            proposals([dict(id=U64 // 2 + 1, row=0, angle=0)], 3, 32, 1, 'source')


@unittest.skipUnless(os.environ.get('ATOMOS_LINEAGE_FIXTURE'), 'set ATOMOS_LINEAGE_FIXTURE to a retained native smoke export')
class ExportMutationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='atomos_lineage_cpu_audit_')
        self.path = Path(self.temporary.name) / 'export'
        shutil.copytree(Path(os.environ['ATOMOS_LINEAGE_FIXTURE']), self.path)

    def tearDown(self):
        self.temporary.cleanup()

    def change_csv(self, name, mutate):
        path = self.path / name
        with path.open(newline='', encoding='utf-8') as stream:
            reader = csv.DictReader(stream)
            fields, records = reader.fieldnames, list(reader)
        mutate(records)
        with path.open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fields)
            writer.writeheader()
            writer.writerows(records)

    def rejected(self):
        with self.assertRaises((ValueError, AssertionError)):
            verify_export(self.path)

    def test_unmodified_retained_fixture(self):
        self.assertEqual(verify_export(self.path)['status'], 'passed')

    def test_child_id(self):
        self.change_csv('generation_0/branches.csv', lambda records: records[0].update(id=records[1]['id']))
        self.rejected()

    def test_seam_parity(self):
        self.change_csv('generation_0/branches.csv', lambda records: records[0].update(parity=str(1 - int(records[0]['parity']))))
        self.rejected()

    def test_undefined_is_not_zero(self):
        self.change_csv('generation_0/diagnostics.csv', lambda records: records[0].update(beta='0'))
        self.rejected()

    def test_reemission(self):
        self.change_csv('generation_0/words.csv', lambda records: records[0].update(reemitted=str(int(records[0]['reemitted']) ^ 1)))
        self.rejected()

    def test_bst_cycle(self):
        self.change_csv('generation_0/tree.csv', lambda records: records[0].update(left='0'))
        self.rejected()

    def test_omitted_search(self):
        self.change_csv('generation_0/searches.csv', lambda records: records.pop())
        self.rejected()

    def test_final_jk(self):
        self.change_csv('final_words.csv', lambda records: records[0].update(q=str(1 - int(records[0]['q']))))
        self.rejected()

    def test_incomplete_budget(self):
        path = self.path / 'summary.json'
        summary = json.loads(path.read_text(encoding='utf-8'))
        summary['generations_requested'] += 1
        path.write_text(json.dumps(summary), encoding='utf-8')
        self.rejected()

    def test_payload_metadata(self):
        path = self.path / 'summary.json'
        summary = json.loads(path.read_text(encoding='utf-8'))
        summary['device_payload_bytes'] -= 4
        path.write_text(json.dumps(summary), encoding='utf-8')
        self.rejected()


if __name__ == '__main__':
    unittest.main()
