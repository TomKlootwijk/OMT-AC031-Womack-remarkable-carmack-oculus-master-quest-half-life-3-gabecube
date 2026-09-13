import sys
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
from universal_reference import parse_program, initial_state, simulate, pack_state, growing_extent
from universal_reference import seal_engine, verify_engine_seal


class UniversalReferenceTests(unittest.TestCase):
    def program(self, extra='', alphabet=2, head=0):
        return parse_program(f'atomos-universal 1\nstates 3\nalphabet {alphabet}\nstart 0 {head}\nhalt 2\n{extra}')

    def run_program(self, program, budget=10, origin=-8, cells=17):
        return simulate(program, initial_state(program), origin=origin, cells=cells, budget=budget)

    def test_unary_increment(self):
        p = self.program('cell 0 1\ncell 1 1\ncell 2 1\nrule 0 1 0 1 R\nrule 0 0 2 1 S')
        r = self.run_program(p)
        self.assertEqual((r['status'], r['steps'], r['head'], r['control']), (1, 4, 3, 2))
        self.assertEqual(r['tape'], {0: 1, 1: 1, 2: 1, 3: 1})

    def test_budget_is_running(self):
        p = self.program('rule 0 0 0 1 R')
        r = self.run_program(p, budget=2)
        self.assertEqual((r['status'], r['steps'], r['head']), (0, 2, 2))
        self.assertEqual(r['tape'], {0: 1, 1: 1})

    def test_zero_budget_is_identity(self):
        p = self.program()
        r = self.run_program(p, budget=0)
        self.assertEqual((r['status'], r['steps'], r['head'], r['tape']), (0, 0, 0, {}))

    def test_initial_halt_with_zero_budget(self):
        p = parse_program('atomos-universal 1\nstates 1\nalphabet 2\nstart 0 0\nhalt 0')
        r = self.run_program(p, budget=0)
        self.assertEqual((r['status'], r['steps']), (1, 0))

    def test_final_budget_step_can_halt(self):
        p = self.program('rule 0 0 2 1 S')
        self.assertEqual(self.run_program(p, budget=1)['status'], 1)

    def test_missing_rule_retains_completed_candidate_prefix(self):
        p = self.program('rule 0 0 1 1 R')
        before = initial_state(p)
        r = simulate(p, before, origin=-8, cells=17, budget=4)
        self.assertEqual((r['status'], r['steps'], r['control'], r['head']), (2, 1, 1, 1))
        self.assertEqual(r['tape'], {0: 1})
        self.assertFalse(r['accepted'])
        self.assertEqual(before, dict(control=0, head=0, tape={}))

    def test_range_failure_does_not_write_or_enter_halt(self):
        p = self.program('rule 0 0 2 1 L', head=-8)
        r = self.run_program(p)
        self.assertEqual((r['status'], r['steps'], r['control'], r['head'], r['tape']), (3, 0, 0, -8, {}))

    def test_left_movement_and_erasure(self):
        p = self.program('cell -2 1\ncell -1 1\ncell 0 1\nrule 0 1 0 0 L\nrule 0 0 2 0 S')
        r = self.run_program(p)
        self.assertEqual((r['status'], r['steps'], r['head'], r['tape']), (1, 4, -3, {}))

    def test_packed_cross_word_symbol_and_nonzero_tail(self):
        # Three-bit symbol at bit 30 crosses words. The logical tape ends at bit 39.
        old = [0, 0xFFFF_FF80]
        words = pack_state({-1: 4, 0: 3}, origin=-11, cells=13, alphabet=5, original_words=old)
        self.assertEqual(words, [0, 0xFFFF_FF87])
        self.assertEqual(old, [0, 0xFFFF_FF80])

    def test_six_bit_symbols_preserve_neighbours(self):
        tape = {-5: 32, -4: 31, -3: 1, -2: 16, -1: 2, 0: 30}
        words = pack_state(tape, origin=-5, cells=7, alphabet=33)
        integer = sum(v << (6 * (a + 5)) for a, v in tape.items())
        self.assertEqual(words, [integer & 0xFFFF_FFFF, integer >> 32])

    def test_duplicate_and_invalid_program_rejected(self):
        bad = ['states 3', 'cell 0 1\ncell 0 0', 'rule 0 0 1 1 R\nrule 0 0 2 0 L',
               'rule 0 2 1 0 S', 'rule 0 0 3 0 S', 'rule 0 0 1 0 X', 'halt 2',
               'cell 9223372036854775808 0', 'cell 0 -1', 'unsupported 1', 'cell 0x1 1']
        for extra in bad:
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                self.program(extra)

    def test_signed_endpoint_overflow_is_range_error(self):
        edge = (1 << 63) - 1
        p = self.program('rule 0 0 2 1 R', head=edge)
        r = self.run_program(p, origin=edge, cells=1)
        self.assertEqual((r['status'], r['steps'], r['head'], r['tape']), (3, 0, edge, {}))

    def test_one_symbol_alphabet_uses_one_storage_bit(self):
        p = parse_program('atomos-universal 1\nstates 1\nalphabet 1\nstart 0 0\nrule 0 0 0 0 R')
        self.assertEqual(p.bits, 1)
        self.assertEqual(self.run_program(p, budget=3)['head'], 3)
        self.assertEqual(pack_state({}, origin=-1, cells=3, alphabet=1, original_words=[0xFFFFFFFF]), [0xFFFFFFF8])

    def test_explicit_zero_cell_still_requires_valid_address(self):
        p = self.program('cell 99 0')
        self.assertEqual(self.run_program(p)['status'], 3)

    def test_unsigned_negative_zero_is_not_a_valid_program_token(self):
        with self.assertRaises(ValueError):
            self.program('cell 0 -0')

    def test_growing_extent_clamps_both_signed_endpoints(self):
        maximum, minimum = (1 << 63) - 1, -(1 << 63)
        self.assertEqual(growing_extent({'head': maximum, 'tape': {}}, 8), (maximum - 8, 9))
        self.assertEqual(growing_extent({'head': minimum, 'tape': {}}, 8), (minimum, 9))
        self.assertEqual(growing_extent({'head': maximum, 'tape': {maximum - 12: 1}}, 8), (maximum - 12, 13))


class UniversalSealTests(unittest.TestCase):
    """Seal mechanics only; a mocked replay receipt is explicitly not GPU evidence."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        (self.directory / 'program.atomos').write_text('synthetic seal fixture\n', encoding='utf-8')
        (self.directory / 'engine.json').write_text(json.dumps({'epochs': [
            {'epoch': 0, 'accepted': True}, {'epoch': 1, 'accepted': False}]}), encoding='utf-8')
        (self.directory / 'epoch_0_u_committed.csv').write_text('accepted\n', encoding='utf-8')
        (self.directory / 'epoch_1_u_candidate.csv').write_text('candidate\n', encoding='utf-8')
        (self.directory / 'PREFIX_VERIFIED').write_text('synthetic fixture\n', encoding='utf-8')
        self.mock = patch('universal_reference.verify_export', return_value={'status': 'passed', 'scope': 'mocked seal-only unit test'})
        self.mock.start()
        self.addCleanup(self.mock.stop)

    def test_rejection_receipt_does_not_advance_accepted_head(self):
        sealed = seal_engine(self.directory)
        self.assertEqual(verify_engine_seal(self.directory), sealed)
        body = json.loads((self.directory / 'engine_seal.json').read_text(encoding='utf-8'))
        self.assertEqual(body['accepted_head'], body['accepted_epoch_chain'][0]['digest'])
        self.assertEqual(body['rejected_attempt_receipts'][0]['predecessor'], body['accepted_head'])
        self.assertNotEqual(body['rejected_attempt_receipts'][0]['digest'], body['accepted_head'])

    def test_seal_detects_modified_candidate_payload(self):
        seal_engine(self.directory)
        (self.directory / 'epoch_1_u_candidate.csv').write_text('changed\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            verify_engine_seal(self.directory)

    def test_seal_detects_added_file(self):
        seal_engine(self.directory)
        (self.directory / 'additional.txt').write_text('unsealed addition\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            verify_engine_seal(self.directory)

    def test_seal_refuses_replacement(self):
        seal_engine(self.directory)
        with self.assertRaises(ValueError):
            seal_engine(self.directory)


if __name__ == '__main__':
    unittest.main()
