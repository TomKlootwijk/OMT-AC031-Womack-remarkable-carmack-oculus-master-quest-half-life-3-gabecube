"""Independent AOPLUT1 fixtures: hand-built bits, inverse physical-cell mapping.

No compiler packer is used to create the malformed or mapping fixtures. These
tests establish CPU format/oracle behavior, never GPU execution or cache claims.
"""
from pathlib import Path
import csv
import hashlib
import json
import struct
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
import program_bank_reference as reference


def origin_seed(rows, angles, row, angle):
    """Choose the first BE128 fraction in each requested quantization bin."""
    scale = 1 << 128
    return (((row * scale + rows - 1) // rows).to_bytes(16, 'big') +
            ((angle * scale + angles - 1) // angles).to_bytes(16, 'big'))


def manual_page(*, rows=3, angles=512, row=2, angle=511, inputs=2,
                gates=((0, 1),), outputs=(3,), identity=0, revision=1,
                nxt=0, seed=None, parent=bytes(range(32)), changes=None,
                dirty_bit=None):
    """Build logical fields and visit physical cells to invert the Klein map."""
    seed = origin_seed(rows, angles, row, angle) if seed is None else seed
    width = max(1, (inputs + len(gates)).bit_length())
    length = 1024 + (2 * len(gates) + len(outputs)) * width
    header = [0x31504b41, 1, inputs, len(outputs), len(gates), width,
              length, identity, revision, nxt, 1024, 0]
    header += list(struct.unpack('<8I', seed))
    header += list(struct.unpack('<8I', parent)) + [0] * 4
    for index, value in (changes or {}).items():
        header[index] = value
    logical = bytearray(rows * angles)
    for index, word in enumerate(header):
        for bit in range(32):
            logical[index * 32 + bit] = (word >> bit) & 1
    position = 1024
    for wire in [v for gate in gates for v in gate] + list(outputs):
        for bit in range(width):
            logical[position + bit] = (wire >> bit) & 1
        position += width
    if dirty_bit is not None:
        logical[dirty_bit] = 1
    physical = bytearray(rows * angles // 8)
    visited = set()
    for physical_row in range(rows):
        for physical_angle in range(angles):
            # Invert the quotient: columns preceding the origin crossed its seam.
            unreflected_row = (rows - 1 - physical_row
                               if physical_angle < angle else physical_row)
            logical_row = (unreflected_row - row) % rows
            logical_angle = (physical_angle - angle) % angles
            logical_index = logical_row * angles + logical_angle
            visited.add(logical_index)
            physical_index = physical_row * angles + physical_angle
            physical[physical_index // 8] |= logical[logical_index] << (physical_index % 8)
    assert len(visited) == rows * angles
    return struct.pack('<2I', row, angle) + physical


def manual_bank(pages, *, rows=3, angles=512, master=bytes(reversed(range(32)))):
    return (b'AOPLUT1\n' + struct.pack('<4I', 1, rows, angles, len(pages)) +
            master + b''.join(pages))


class ProgramBankReferenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'bank.aoplut'

    def decode(self, raw, manifest=None):
        self.path.write_bytes(raw)
        return reference.decode_bank(self.path, manifest)

    def test_manual_inverse_mapping_seams_and_seed_extremes(self):
        fixtures = [(3, 512, 0, 0, bytes(32)),
                    (3, 512, 2, 511, b'\xff' * 32),
                    (9, 128, 4, 33, None),
                    (5, 256, 1, 255, None)]
        for rows, angles, row, angle, seed in fixtures:
            with self.subTest(rows=rows, angles=angles, row=row, angle=angle):
                page = manual_page(rows=rows, angles=angles, row=row, angle=angle, seed=seed)
                capsule = self.decode(manual_bank([page], rows=rows, angles=angles))['capsules'][0]
                self.assertEqual(capsule['gates'], [(0, 1)])
                self.assertEqual(capsule['outputs'], [3])
                self.assertEqual([reference.evaluate(capsule, x) for x in range(4)], [1, 0, 0, 0])
                self.assertEqual(capsule['origin_row'], row)
                self.assertEqual(capsule['origin_angle'], angle)
                self.assertEqual(capsule['parent_sha256'], bytes(range(32)).hex())
                self.assertEqual(capsule['content_sha256'],
                                 hashlib.sha256(b'atomos-program-page-v1\0' + page).hexdigest())

    def test_bit_fields_cross_word_boundary(self):
        gates = ((0, 1), (4, 2), (5, 5), (6, 3))
        capsule = self.decode(manual_bank([manual_page(inputs=3, gates=gates, outputs=(4, 6, 7))]))['capsules'][0]
        self.assertEqual(capsule['bit_length'], 1057)
        self.assertEqual(capsule['gates'], list(gates))
        self.assertEqual(capsule['outputs'], [4, 6, 7])
        for x in range(8):
            first = not (bool(x & 1) or bool(x & 2))
            sixth = first or bool(x & 4)
            self.assertEqual(reference.evaluate(capsule, x), int(first) + 2 * int(sixth) + 4 * int(not sixth))

    def test_zero_input_constant_and_high_input_bit(self):
        constant = manual_page(inputs=0, gates=((0, 0),), outputs=(1,))
        capsule = self.decode(manual_bank([constant]))['capsules'][0]
        self.assertEqual(reference.evaluate(capsule, 0), 1)
        high_bit = manual_page(inputs=32, gates=(), outputs=(31,))
        capsule = self.decode(manual_bank([high_bit]))['capsules'][0]
        self.assertEqual(reference.evaluate(capsule, 0x80000000), 1)
        self.assertEqual(reference.evaluate(capsule, 0x7fffffff), 0)

    def test_same_origin_preserves_distinct_programs_and_routing(self):
        pages = [manual_page(inputs=1, gates=((0, 0),), outputs=(2,), identity=0, nxt=1),
                 manual_page(inputs=1, gates=(), outputs=(0,), identity=1, nxt=0)]
        bank = self.decode(manual_bank(pages))
        self.assertEqual(len(bank['capsules']), 2)
        self.assertEqual(bank['capsules'][0]['seed_hex'], bank['capsules'][1]['seed_hex'])
        self.assertNotEqual(bank['capsules'][0]['content_sha256'], bank['capsules'][1]['content_sha256'])
        replay = reference.replay(bank, 1, 4)
        self.assertEqual([x['program_id'] for x in replay], [0, 1, 0, 1])
        self.assertEqual([x['output'] for x in replay], [0, 0, 1, 1])

    def test_rejects_dirty_logical_tail_after_reflected_seam(self):
        for dirty_bit in (1030, 1279, 1535):
            with self.subTest(dirty_bit=dirty_bit):
                with self.assertRaisesRegex(ValueError, 'dirty unused'):
                    self.decode(manual_bank([manual_page(dirty_bit=dirty_bit)]))

    def test_rejects_header_reserved_extent_and_identity_mutations(self):
        for field, value in ((0, 0), (1, 2), (5, 3), (6, 1024), (7, 1),
                             (8, 0), (9, 1), (10, 0), (11, 1), (28, 1), (31, 1)):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    self.decode(manual_bank([manual_page(changes={field: value})]))

    def test_rejects_seed_origin_disagreement_and_outside_chart(self):
        with self.assertRaisesRegex(ValueError, 'seed and chart origin'):
            self.decode(manual_bank([manual_page(seed=bytes(32))]))
        page = manual_page()
        for row, angle in ((3, 511), (2, 512)):
            with self.subTest(row=row, angle=angle):
                with self.assertRaisesRegex(ValueError, 'origin outside'):
                    self.decode(manual_bank([struct.pack('<2I', row, angle) + page[8:]]))

    def test_rejects_forward_gate_and_invalid_output(self):
        with self.assertRaisesRegex(ValueError, 'forward/cyclic'):
            self.decode(manual_bank([manual_page(gates=((3, 0),))]))
        with self.assertRaisesRegex(ValueError, 'output reference'):
            self.decode(manual_bank([manual_page(gates=((0, 1), (3, 2)), outputs=(5,))]))

    def test_rejects_wire_count_above_native_limit(self):
        page = manual_page(rows=8, angles=4096, row=7, angle=4095,
                           gates=((0, 1),) * 1022, outputs=(3,))
        with self.assertRaisesRegex(ValueError, 'resource bound'):
            self.decode(manual_bank([page], rows=8, angles=4096))

    def test_rejects_container_magic_extent_and_dimensions(self):
        raw = manual_bank([manual_page()])
        variants = [raw[:55], raw[:-1], raw + b'\0', b'NOTALUT\n' + raw[8:]]
        for offset, value in ((8, 2), (12, 1), (16, 511), (20, 0), (20, 65537)):
            mutation = bytearray(raw)
            struct.pack_into('<I', mutation, offset, value)
            variants.append(bytes(mutation))
        for mutation in variants:
            with self.subTest(length=len(mutation)):
                with self.assertRaises(ValueError):
                    self.decode(mutation)

    def test_rejects_native_padded_extent_before_payload_decode(self):
        # Logical words fit, but the native Morton padding needs 1,440,000 words.
        raw = manual_bank([], rows=60000, angles=544)
        raw = raw[:20] + struct.pack('<I', 1) + raw[24:]
        with self.assertRaisesRegex(ValueError, 'page.*bound'):
            self.decode(raw)

    def test_rejects_bank_byte_budget_before_reading(self):
        fake_path = Mock()
        fake_path.stat.return_value.st_size = (512 << 20) + 1
        fake_path.read_bytes.side_effect = AssertionError('oversized bank must not be read')
        with patch.object(reference, 'Path', return_value=fake_path):
            with self.assertRaisesRegex(ValueError, 'byte budget'):
                reference.decode_bank('oversized-bank.bin')

    def test_manual_page_cross_decodes_with_compiler_reader(self):
        import program_bank as compiler
        raw = manual_bank([manual_page()])
        expected = self.decode(raw)
        actual = compiler.load_bank(self.path)
        self.assertEqual(actual['capsules'][0]['circuit']['gates'], [[0, 1]])
        self.assertEqual(actual['capsules'][0]['circuit']['outputs'], [3])
        for field in ('origin_row', 'origin_angle', 'seed_hex', 'content_sha256', 'bit_length'):
            self.assertEqual(actual['capsules'][0][field], expected['capsules'][0][field])

    def test_compiler_bytes_equal_manually_scattered_fixture(self):
        import program_bank as compiler
        circuit = {'input_bits': 2, 'output_bits': 1, 'constant_zero_wire': 2,
                   'gates': [[0, 1]], 'outputs': [3]}
        seed = origin_seed(3, 512, 2, 511)
        manifest = compiler.write_bank(self.path, [{'circuit': circuit, 'seed_hex': seed.hex(),
                                                   'parent_sha256': bytes(range(32)).hex()}],
                                       master_seed_hex=bytes(reversed(range(32))).hex(), rows=3, angles=512)
        self.assertEqual(self.path.read_bytes(), manual_bank([manual_page()]))
        self.assertEqual(reference.decode_bank(self.path, self.path.parent / 'manifest.json')['bank_file_sha256'],
                         manifest['bank_file_sha256'])

    def test_rejects_manifest_schema_and_metadata_mutations(self):
        raw = manual_bank([manual_page()])
        decoded = self.decode(raw)
        manifest = dict(decoded, schema='atomos-program-lut-bank-v1')
        manifest_path = self.path.parent / 'independent_manifest.json'
        for key, value in (('schema', 'unrecognized-schema'), ('rows', 4), ('master_seed_hex', '0' * 64)):
            with self.subTest(key=key):
                mutation = dict(manifest, **{key: value})
                manifest_path.write_text(json.dumps(mutation), encoding='utf-8')
                with self.assertRaises(ValueError):
                    reference.decode_bank(self.path, manifest_path)
        mutation = json.loads(json.dumps(manifest))
        mutation['capsules'][0]['parent_sha256'] = '0' * 64
        manifest_path.write_text(json.dumps(mutation), encoding='utf-8')
        with self.assertRaises(ValueError):
            reference.decode_bank(self.path, manifest_path)

    def test_trace_rejects_changed_version_and_extra_hop(self):
        bank = self.decode(manual_bank([manual_page()]))
        rows = reference.replay(bank, 0, 2)
        trace = self.path.parent / 'trace.csv'
        def save(records):
            with trace.open('w', newline='', encoding='utf-8') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(records)
        save(rows)
        self.assertEqual(reference.verify_trace(trace, bank, 0, 2)['status'], 'passed')
        altered = [dict(row) for row in rows]
        altered[1]['version'] += 1
        save(altered)
        with self.assertRaisesRegex(ValueError, 'version'):
            reference.verify_trace(trace, bank, 0, 2)
        save(rows + [rows[-1]])
        with self.assertRaisesRegex(ValueError, 'hop count'):
            reference.verify_trace(trace, bank, 0, 2)


if __name__ == '__main__':
    unittest.main()
