"""CPU-only synthetic export regressions; these fixtures are not GPU evidence."""
import csv
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
sys.path.insert(0, str(ROOT / 'tools'))
import sdf_nor_reference as nr
from sdf_atlas import default_config, write_atlas
from universal_reference import parse_program, initial_state, simulate, pack_state
from validate_sdf_nor import cases, expected_result


def save_json(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')


def write_csv(path, header, rows):
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


def synthetic_export(directory, *, injection='none', budget=1, layout='linear',
                     head=0, move=0, start=0):
    """Hand-built controller: next=write=defined=halt-after=NOT q, halt=q.

    Both read symbols have the same transition; a single NOR(q,q) suffices.
    The constructor does not invoke the production replay verifier or compiler.
    """
    origin, cells, fill = -1, 35, 0xa5a5a5a5
    program_text = ('atomos-universal 1\nstates 2\nalphabet 2\n'
        f'start {start} {head}\nhalt 1\nrule 0 0 1 1 {"L" if move < 0 else "S"}\n'
        f'rule 0 1 1 1 {"L" if move < 0 else "S"}\n')
    (directory / 'program.atomos').write_text(program_text, encoding='utf-8')
    program = parse_program(program_text)
    reference = simulate(program, initial_state(program), origin=origin, cells=cells, budget=budget)
    circuit = dict(schema='atomOS-sdf-nor-circuit-v1', states=2, alphabet=2,
        control_bits=1, symbol_bits=1, input_count=3, gates=[[0, 0]],
        outputs=[3, 3, 3 if move < 0 else 2, 2, 3, 0, 3])
    save_json(directory / 'circuit.json', circuit)
    write_atlas(default_config('nor_sites', 3, 64), directory / 'operators.atlas')
    in_extent = origin <= head < origin + cells
    output = 1 - start
    if injection != 'none' and in_extent:
        output = output ^ 1 if injection == 'gate' else 0
    decoded = dict(next=output, write=output, move=-output if move < 0 else 0,
                   defined=output, halt_current=start, halt_after=output)
    if injection != 'none' and in_extent and start == 0 and budget:
        candidate = dict(control=start, head=head, tape={}, transitions=[], status_name='missing_rule')
    else:
        candidate = reference
    evaluation_rows = [dict(evaluation=0, control=start, head=head, read=0, **decoded)] if in_extent else []
    masks = dict(asa=6 if injection == 'texture' else 7, na=7, boundary=6, fringe=7)
    gate_rows = [dict(evaluation=0, gate=0, a=start, b=start, output=output,
                     texel=16 if layout == 'linear' else 4, parity=1, **masks)] if in_extent else []
    write_csv(directory / 'gate_trace.csv', nr.GATE_HEADER, gate_rows)
    write_csv(directory / 'evaluations.csv', nr.EVALUATION_HEADER, evaluation_rows)
    write_csv(directory / 'transitions.csv', nr.TRANSITION_HEADER, candidate['transitions'])
    before_words = pack_state({}, origin=origin, cells=cells, alphabet=2, original_words=[fill, fill])
    candidate_words = pack_state(candidate['tape'], origin=origin, cells=cells, alphabet=2,
                                 original_words=before_words)
    reference_words = pack_state(reference['tape'], origin=origin, cells=cells, alphabet=2,
                                 original_words=before_words)
    fault = injection != 'none' and in_extent
    native = dict(gates=not fault, controller=not fault,
        machine=candidate['control'] == reference['control'] and candidate['head'] == reference['head'] and
                candidate['status_name'] == reference['status_name'],
        transitions=candidate['transitions'] == reference['transitions'],
        tape=candidate_words == reference_words, texture_sweeps=True,
        gates_checked=int(in_extent), gate_mismatches=int(fault), odd_seam_gate_evaluations=int(in_extent))
    native['passed'] = all(native[key] for key in ('gates', 'controller', 'machine', 'transitions', 'tape', 'texture_sweeps'))
    accepted = native['passed'] and candidate['status_name'] in ('running', 'halted')
    committed_words = candidate_words if accepted else before_words
    for name, words in (('before', before_words), ('candidate', candidate_words), ('committed', committed_words)):
        (directory / (name + '.u32le')).write_bytes(struct.pack('<II', *words))
    for name, tape in (('before', {}), ('candidate', candidate['tape']), ('committed', candidate['tape'] if accepted else {})):
        write_csv(directory / (name + '_tape.csv'), ['address', 'symbol'],
                  [dict(address=a, symbol=s) for a, s in sorted(tape.items()) if s])
    checksum = [int(injection == 'texture'), 0, 0, 0]
    payload = 1024 + 8 + 28 + 16 + 36 * max(1, budget) + 48 * max(1, budget) + 40 * budget + 8 + 80
    summary = dict(schema='atomOS-sdf-nor-universal-v1',
        profile='new-compiled-SDF-NOR-controller-v1', topology='klein_m1_angular_twist',
        operator_source='loaded-SDF-predicate-atlas', runtime_rule_table=False,
        gate_operation='source-whole-word-ASA-NOR', injection=injection,
        tape_addressing='nonaliasing-signed-logical-addresses-separate-from-immutable-operator-atlas',
        rows=3, angles=64, words=2, padded_rows=8, padded_words=8,
        atlas_file_bytes=112, atlas_texture_bytes=1024, control_bits=1, symbol_bits=1,
        circuit_gates=1, circuit_wires=4, origin=origin, cells=cells, tail_fill=fill,
        steps_budget=budget, evaluations=len(evaluation_rows), executed_steps=len(candidate['transitions']),
        layout=layout, before=dict(control=start, head=head),
        candidate=dict(control=candidate['control'], head=candidate['head']),
        committed=dict(control=candidate['control'], head=candidate['head']) if accepted else dict(control=start, head=head),
        program_stop=candidate['status_name'], reference_stop=reference['status_name'],
        warm_checksum=checksum, reread_checksum=checksum, sm_before=3, sm_after=3,
        accepted=accepted, verification=native,
        status='passed' if accepted else 'rejected_program' if native['passed'] else 'rejected_verification',
        device_payload_bytes=payload, host_geometry_bytes=64 * 48 + 6 * 88,
        abi=dict(gate=8, gate_trace=36, evaluation=48, transition=40, kernel_result=80, u32=4, texture_texel=16),
        memory_budget_bytes=256 << 20, reserve_bytes=512 << 20,
        device=dict(name='CPU synthetic fixture; not a GPU run', free_bytes_at_start=1 << 30,
            total_bytes=2 << 30, max_texture_1d_linear=1 << 20, runtime=0, driver=0, cc_major=0, cc_minor=0),
        kernel_ms=0, texture_reads=dict(warm=64, gates=len(gate_rows), reread=64, total=128 + len(gate_rows)))
    save_json(directory / 'summary.json', summary)
    (directory / ('COMMITTED' if accepted else 'REJECTED')).write_text('CPU test fixture\n', encoding='utf-8')
    return summary


class SdfNorReferenceTests(unittest.TestCase):
    def test_complete_good_export_both_layouts(self):
        for layout in ('linear', 'morton8'):
            with tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                synthetic_export(directory, layout=layout)
                result = nr.verify_export(directory)
                self.assertTrue(result['computation_accepted'])
                self.assertEqual(result['compiler_truth_rows'], 4)
                self.assertEqual(result['tm_transitions'], 1)

    def test_injected_texture_and_gate_require_full_rollback(self):
        for injection in ('texture', 'gate'):
            with tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                synthetic_export(directory, injection=injection)
                result = nr.verify_export(directory)
                self.assertTrue(result['rejection_verified'])
                self.assertEqual(result['nor_faults_detected'], 1)
                self.assertEqual(result['actual_transitions'], 0)
                self.assertEqual(result['tm_transitions'], 1)
                (directory / 'committed.u32le').write_bytes(struct.pack('<II', 2, 0xa5a5a5a0))
                with self.assertRaisesRegex(ValueError, 'commit/rollback'):
                    nr.verify_export(directory)

    def test_zero_budget_halt_and_checked_boundary(self):
        for settings, expected_stop in ((dict(budget=0), 'running'),
                (dict(start=1, budget=0), 'halted'),
                (dict(head=-1, move=-1), 'tape_range'),
                (dict(head=99, budget=0), 'tape_range')):
            with tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                synthetic_export(directory, **settings)
                result = nr.verify_export(directory)
                self.assertEqual(result['program_stop'], expected_stop)
                self.assertEqual(result['actual_transitions'], 0)

    def test_tampered_tail_address_decode_and_count_rejected(self):
        mutations = (
            ('candidate.u32le', lambda data: data[:-1] + bytes([data[-1] ^ 128])),
            ('gate_trace.csv', lambda data: data.replace(b',16,1,', b',0,0,')),
            ('evaluations.csv', lambda data: data.replace(b'0,0,0,0,1,1,0,1,0,1', b'0,0,0,0,0,1,0,1,0,1')),
            ('gate_trace.csv', lambda data: data + data.splitlines(keepends=True)[1]),
        )
        for name, mutation in mutations:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                synthetic_export(directory)
                path = directory / name
                original = path.read_bytes()
                altered = mutation(original)
                self.assertNotEqual(original, altered)
                path.write_bytes(altered)
                with self.assertRaises(ValueError):
                    nr.verify_export(directory)

    def test_forged_resource_and_truth_metadata_rejected(self):
        for key, replacement in (('device_payload_bytes', 1), ('accepted', 1),
                                 ('runtime_rule_table', True), ('host_geometry_bytes', 0)):
            with tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                summary = synthetic_export(directory)
                summary[key] = replacement
                save_json(directory / 'summary.json', summary)
                with self.assertRaises(ValueError):
                    nr.verify_export(directory)

    def test_circuit_forward_wire_and_unused_input_truth_are_checked(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            synthetic_export(directory)
            circuit = json.loads((directory / 'circuit.json').read_text())
            circuit['gates'][0][0] = 3
            save_json(directory / 'circuit.json', circuit)
            with self.assertRaisesRegex(ValueError, 'topologically'):
                nr.verify_export(directory)
            circuit['gates'][0][0] = 1  # agrees at observed q=read=0, fails at unread input (q0,s1)
            save_json(directory / 'circuit.json', circuit)
            with self.assertRaisesRegex(ValueError, 'controller truth'):
                nr.verify_export(directory)

    def test_gate_sites_cover_negative_and_positive_angular_lifts(self):
        self.assertEqual(nr.gate_site(0, 3, 64, 8, 'linear'), (2, 0, 16, 1))
        self.assertEqual(nr.gate_site(1, 3, 64, 8, 'linear'), (0, 1, 1, 0))
        self.assertEqual(nr.gate_site(2, 3, 64, 8, 'linear'), (1, 0, 8, 1))
        self.assertEqual(nr.gate_site(0, 3, 64, 8, 'morton8'), (2, 0, 4, 1))

    def test_study_matrix_and_independent_exit_predictions(self):
        jobs = cases()
        self.assertEqual(len(jobs), 80)
        self.assertEqual(len({job['name'] for job in jobs}), len(jobs))
        self.assertTrue(any(job['budget'] == 4096 for job in jobs))
        self.assertEqual({job['layout'] for job in jobs}, {'linear', 'morton8'})
        for job in jobs:
            result = expected_result(job)
            if job['injection'] != 'none':
                self.assertEqual(result['exit_code'], 2)
            if 'oscillator' in job['name'] and job['injection'] == 'none':
                self.assertEqual(result['stop'], 'running')
                self.assertEqual(result['transitions'], job['budget'])


if __name__ == '__main__':
    unittest.main()
