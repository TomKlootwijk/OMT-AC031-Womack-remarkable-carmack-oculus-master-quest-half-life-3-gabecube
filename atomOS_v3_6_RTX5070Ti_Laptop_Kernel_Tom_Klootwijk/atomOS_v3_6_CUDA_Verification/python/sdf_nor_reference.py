"""Independent replay of exported SDF-texture/NOR machine executions.

The controller oracle uses Python Boolean NOR, and the machine oracle uses the
existing sparse-dictionary interpreter. Neither executes the native compiler,
CUDA code, native verifier, or packed tape helpers. GPU execution provenance is
the study runner's responsibility; synthetic unit fixtures are never GPU proof.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

from sdf_atlas import PLANES, verify_atlas
from universal_reference import (I64_MIN, I64_MAX, STOP_NAMES, initial_state,
    pack_state, read_nonzero_tape, read_packed, read_program, simulate)

FILES = ('summary.json', 'program.atomos', 'operators.atlas', 'operators.json',
         'circuit.json', 'before.u32le', 'candidate.u32le', 'committed.u32le',
         'before_tape.csv', 'candidate_tape.csv', 'committed_tape.csv',
         'gate_trace.csv', 'evaluations.csv', 'transitions.csv')
GATE_HEADER = 'evaluation gate a b output texel parity asa na boundary fringe'.split()
EVALUATION_HEADER = 'evaluation control head read next write move defined halt_current halt_after'.split()
TRANSITION_HEADER = 'step control_before head_before read write move control_after head_after'.split()
DECODED = 'next write move defined halt_current halt_after'.split()


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def equal(actual, expected, label):
    def same(a, b):
        if type(a) is not type(b):
            return False
        if isinstance(a, dict):
            return a.keys() == b.keys() and all(same(a[key], b[key]) for key in a)
        if isinstance(a, (tuple, list)):
            return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
        return a == b
    if not same(actual, expected):
        raise ValueError(f'{label}: {actual!r} != {expected!r}')


def integer(value, label, low=0, high=(1 << 64) - 1):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{label}: integer outside [{low}, {high}]')
    return value


def csv_rows(path, header):
    with Path(path).open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream)
        equal(reader.fieldnames, header, Path(path).name + ' header')
        for row in reader:
            if None in row or None in row.values():
                raise ValueError('malformed CSV row: ' + str(path))
            try:
                yield {key: int(value) for key, value in row.items()}
            except ValueError as error:
                raise ValueError('noninteger CSV field: ' + str(path)) from error


def validate_circuit(circuit, program):
    equal(circuit.get('schema'), 'atomOS-sdf-nor-circuit-v1', 'circuit schema')
    qb, sb = max(1, (program.states - 1).bit_length()), program.bits
    for key, value in dict(states=program.states, alphabet=program.alphabet,
                           control_bits=qb, symbol_bits=sb, input_count=qb + sb + 1).items():
        equal(circuit.get(key), value, 'circuit ' + key)
    gates, outputs = circuit.get('gates'), circuit.get('outputs')
    if not isinstance(gates, list) or not gates or not isinstance(outputs, list):
        raise ValueError('circuit gates/outputs missing')
    equal(len(outputs), qb + sb + 5, 'output count')
    for index, pair in enumerate(gates):
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError('gate needs two wire indices')
        for wire in pair:
            integer(wire, 'topologically earlier NOR wire', high=qb + sb + index)
    for wire in outputs:
        integer(wire, 'output wire', high=qb + sb + len(gates))
    return circuit


def boolean_wires(circuit, control, symbol):
    qb, sb = circuit['control_bits'], circuit['symbol_bits']
    values = [(control >> bit) & 1 for bit in range(qb)]
    values += [(symbol >> bit) & 1 for bit in range(sb)] + [0]
    for left, right in circuit['gates']:
        values.append(int(not (values[left] or values[right])))
    return values


def decode(circuit, wires):
    bits = [wires[wire] for wire in circuit['outputs']]
    qb, sb = circuit['control_bits'], circuit['symbol_bits']
    left, right, defined, current, after = bits[qb + sb:]
    return dict(next=sum(bits[bit] << bit for bit in range(qb)),
                write=sum(bits[qb + bit] << bit for bit in range(sb)),
                move=2 if left and right else right - left,
                defined=defined, halt_current=current, halt_after=after)


def table_output(program, control, symbol):
    result = dict(next=0, write=0, move=0, defined=0,
                  halt_current=int(control in program.halts), halt_after=0)
    if not result['halt_current'] and (control, symbol) in program.rules:
        q, write, move = program.rules[control, symbol]
        result.update(next=q, write=write, move=move, defined=1,
                      halt_after=int(q in program.halts))
    return result


def verify_compiler(circuit, program):
    """Check the entire finite legal input domain, including missing/halt rows."""
    validate_circuit(circuit, program)
    checked = 0
    for control in range(program.states):
        for symbol in range(program.alphabet):
            equal(decode(circuit, boolean_wires(circuit, control, symbol)),
                  table_output(program, control, symbol), 'finite controller truth')
            checked += 1
    return checked


def gate_site(gate, rows, angles, padded_words, layout):
    """Integer floor-division deck map, then separately constructed word address."""
    words = angles // 32
    row, word = divmod(gate % (rows * words), words)
    lifted_angle = word * 32 + (gate % 3 - 1) * angles
    loops, angle = divmod(lifted_angle, angles)
    parity = loops % 2
    if parity:
        row = rows - 1 - row
    word = angle // 32
    if layout == 'linear':
        texel = row * padded_words + word
    elif layout == 'morton8':
        local = sum(((row >> bit) & 1) << (bit * 2) |
                    ((word >> bit) & 1) << (bit * 2 + 1) for bit in range(3))
        texel = 64 * ((row // 8) * (padded_words // 8) + word // 8) + local
    else:
        raise ValueError('unknown texture layout')
    return row, word, texel, parity


def payload_bytes(*, stored_words, gates, outputs, wires, budget, cells, bits):
    """Pinned CUDA/MSVC ABI; checked against runtime static_assert declarations."""
    evaluations = max(1, budget)
    return dict(operator_texture=stored_words * 16, gates=gates * 8,
                outputs=outputs * 4, wires=wires * 4,
                gate_trace=evaluations * gates * 36, evaluations=evaluations * 48,
                transitions=budget * 40, tape=((cells * bits + 31) // 32) * 4,
                result=80)


def verify_export(directory, *, expected=None):
    """Verify every exported sample, NOR gate, machine step, tape word and commit.

    A specified fault is independently replayed, but it must fail the correct
    semantics and retain the complete original state. Matching a fault model is
    evidence that rejection worked, not a passing computation.
    """
    directory = Path(directory)
    summary = json.loads((directory / 'summary.json').read_text(encoding='utf-8'))
    metadata = dict(schema='atomOS-sdf-nor-universal-v1',
        profile='new-compiled-SDF-NOR-controller-v1', topology='klein_m1_angular_twist',
        operator_source='loaded-SDF-predicate-atlas', runtime_rule_table=False,
        gate_operation='source-whole-word-ASA-NOR',
        tape_addressing='nonaliasing-signed-logical-addresses-separate-from-immutable-operator-atlas')
    for key, value in metadata.items():
        equal(summary.get(key), value, key)
    program = read_program(directory / 'program.atomos')
    circuit = json.loads((directory / 'circuit.json').read_text(encoding='utf-8'))
    truth_rows = verify_compiler(circuit, program)
    atlas = verify_atlas(directory / 'operators.atlas')
    equal(atlas['manifest']['profile'], 'nor_sites', 'atlas construction profile')
    rows, angles, words = atlas['rows'], atlas['angles'], atlas['words_per_row']
    if rows < 2 or angles < 32 or angles % 32:
        raise ValueError('NOR atlas requires at least two rows and complete words')
    pr, pw = (rows + 7) // 8 * 8, (words + 7) // 8 * 8
    gates, inputs = len(circuit['gates']), circuit['input_count']
    for key, value in dict(rows=rows, angles=angles, words=words, padded_rows=pr,
        padded_words=pw, atlas_file_bytes=16 + 16 * rows * words,
        atlas_texture_bytes=16 * pr * pw, control_bits=circuit['control_bits'],
        symbol_bits=program.bits, circuit_gates=gates, circuit_wires=inputs + gates).items():
        equal(summary.get(key), value, key)
    origin = integer(summary.get('origin'), 'origin', I64_MIN, I64_MAX)
    cells = integer(summary.get('cells'), 'cells', 1)
    if origin + cells - 1 > I64_MAX:
        raise ValueError('tape endpoint outside signed address domain')
    budget = integer(summary.get('steps_budget'), 'steps budget', high=(1 << 32) - 1)
    fill = integer(summary.get('tail_fill'), 'tail fill', high=(1 << 32) - 1)
    layout, injection = summary.get('layout'), summary.get('injection')
    if injection not in ('none', 'texture', 'gate'):
        raise ValueError('unknown injection profile')
    if expected:
        for key, summary_key in (('layout', 'layout'), ('budget', 'steps_budget'),
              ('origin', 'origin'), ('cells', 'cells'), ('injection', 'injection')):
            if key in expected:
                equal(summary.get(summary_key), expected[key], 'requested ' + key)
        if 'program' in expected:
            from universal_reference import parse_program
            equal(program, parse_program(expected['program']), 'requested program')
        if 'atlas_sha256' in expected:
            equal(sha256(directory / 'operators.atlas'), expected['atlas_sha256'], 'requested atlas')
    before = initial_state(program)
    if any(not origin <= address < origin + cells for address in before['tape']):
        raise ValueError('published export has an invalid explicit initial cell')
    reference = simulate(program, before, origin=origin, cells=cells, budget=budget)
    reference_evals = [dict(control=t['control_before'], head=t['head_before'], read=t['read'])
                       for t in reference['transitions']]
    if origin <= program.start_head < origin + cells and (budget == 0 or
        (reference['status'] == 1 and not reference['transitions']) or reference['status'] in (2, 3)):
        reference_evals.append(dict(control=reference['control'], head=reference['head'],
                                    read=reference['tape'].get(reference['head'], 0)))
    expected_initial_words = pack_state(before['tape'], origin=origin, cells=cells,
        alphabet=program.alphabet, original_words=[fill] * ((cells * program.bits + 31) // 32))
    equal(read_packed(directory / 'before.u32le'), expected_initial_words, 'every initial packed word')
    equal(read_nonzero_tape(directory / 'before_tape.csv'),
          {a: s for a, s in before['tape'].items() if s}, 'initial sparse tape')
    equal(summary.get('before'), dict(control=program.start_control, head=program.start_head), 'initial machine')
    eval_rows = list(csv_rows(directory / 'evaluations.csv', EVALUATION_HEADER))
    transitions = list(csv_rows(directory / 'transitions.csv', TRANSITION_HEADER))
    equal(summary.get('evaluations'), len(eval_rows), 'evaluation count')
    equal(summary.get('executed_steps'), len(transitions), 'transition count')
    if len(eval_rows) > max(1, budget) or len(transitions) > budget:
        raise ValueError('execution exceeds allocated trace budget')
    # Expected texture placement and uploaded contents are independent of the
    # exported gate records. The scalar verifier above checked every atlas bit.
    sites = [gate_site(gate, rows, angles, pw, layout) for gate in range(gates)]
    masks = [[int(atlas['planes'][plane][row, word]) for plane in PLANES]
             for row, word, _, _ in sites]
    if any(value != [7, 7, 6, 7] for value in masks):
        raise ValueError('SDF profile does not implement the declared NOR primitive')
    uploaded = [value.copy() for value in masks]
    if injection == 'texture':
        target = sites[0][2]
        for site, value in zip(sites, uploaded):
            if site[2] == target:
                value[0] &= ~1
    q, head, tape = before['control'], before['head'], dict(before['tape'])
    actual_steps, actual_evals, stop = [], 0, 0
    native = dict(gates=True, controller=len(eval_rows) == len(reference_evals),
                  machine=True, transitions=True, tape=True, texture_sweeps=True,
                  gates_checked=0, gate_mismatches=0, odd_seam_gate_evaluations=0)
    actual_nor_mismatches = 0
    records = iter(csv_rows(directory / 'gate_trace.csv', GATE_HEADER))
    if not origin <= head < origin + cells:
        stop = 3
    else:
        while True:
            e = actual_evals
            if e >= len(eval_rows):
                raise ValueError('required current controller evaluation missing')
            symbol = tape.get(head, 0)
            wires = [(q >> bit) & 1 for bit in range(circuit['control_bits'])]
            wires += [(symbol >> bit) & 1 for bit in range(program.bits)] + [0]
            correct = boolean_wires(circuit, q, symbol)
            equal(decode(circuit, correct), table_output(program, q, symbol), 'actual input controller truth')
            oracle_e = reference_evals[e] if e < len(reference_evals) else None
            oracle_wires = boolean_wires(circuit, oracle_e['control'], oracle_e['read']) if oracle_e else None
            if oracle_e is None:
                native['gates'] = native['controller'] = False
            for gate, (left, right) in enumerate(circuit['gates']):
                try:
                    record = next(records)
                except StopIteration as error:
                    raise ValueError('gate trace truncated') from error
                a, b = wires[left], wires[right]
                am, nm, boundary, fringe = uploaded[gate]
                selected = (1 | (a << 1) | (b << 2)) & am & nm & fringe
                output = int(bool(selected & 1) and not bool(selected & boundary))
                if injection == 'gate' and e == 0 and gate == 0:
                    output ^= 1
                wires.append(output)
                _, _, texel, parity = sites[gate]
                actual = dict(evaluation=e, gate=gate, a=a, b=b, output=output,
                              texel=texel, parity=parity, asa=am, na=nm,
                              boundary=boundary, fringe=fringe)
                equal(record, actual, 'actual gate replay / Klein address / SDF sample')
                actual_nor_mismatches += int(output != int(not (a or b)))
                if oracle_wires is not None:
                    intended = dict(evaluation=e, gate=gate, a=oracle_wires[left],
                        b=oracle_wires[right], output=oracle_wires[inputs + gate],
                        texel=texel, parity=parity,
                        **dict(zip(PLANES, masks[gate])))
                    same = record == intended
                    native['gates_checked'] += 1
                    native['odd_seam_gate_evaluations'] += parity
                    native['gate_mismatches'] += int(not same)
                    native['gates'] &= same
            decoded = decode(circuit, wires)
            equal(eval_rows[e], dict(evaluation=e, control=q, head=head, read=symbol, **decoded),
                  'every decoded controller output')
            if oracle_e is not None:
                native['controller'] &= (dict(control=q, head=head, read=symbol) == oracle_e and
                    decoded == table_output(program, oracle_e['control'], oracle_e['read']))
            actual_evals += 1
            if decoded['halt_current']:
                stop = 1
                break
            if len(actual_steps) >= budget:
                break
            if not decoded['defined']:
                stop = 2
                break
            if decoded['next'] >= program.states or decoded['write'] >= program.alphabet or abs(decoded['move']) > 1:
                stop = 4
                break
            new_head = head + decoded['move']
            if not origin <= new_head < origin + cells or not I64_MIN <= new_head <= I64_MAX:
                stop = 3
                break
            actual_steps.append(dict(step=len(actual_steps), control_before=q, head_before=head,
                read=symbol, write=decoded['write'], move=decoded['move'],
                control_after=decoded['next'], head_after=new_head))
            if decoded['write']:
                tape[head] = decoded['write']
            else:
                tape.pop(head, None)
            q, head = decoded['next'], new_head
            if decoded['halt_after']:
                stop = 1
                break
            if len(actual_steps) >= budget:
                break
    if next(records, None) is not None:
        raise ValueError('extra gate trace records')
    equal(actual_evals, len(eval_rows), 'actual evaluation extent')
    equal(transitions, actual_steps, 'chronological actual transition trace')
    equal(summary.get('program_stop'), STOP_NAMES[stop], 'actual stop status')
    equal(summary.get('reference_stop'), reference['status_name'], 'independent TM stop status')
    candidate_machine = dict(control=q, head=head)
    equal(summary.get('candidate'), candidate_machine, 'actual candidate machine')
    actual_words = pack_state(tape, origin=origin, cells=cells, alphabet=program.alphabet,
                              original_words=expected_initial_words)
    equal(read_packed(directory / 'candidate.u32le'), actual_words, 'every candidate word including tail')
    equal(read_nonzero_tape(directory / 'candidate_tape.csv'),
          {a: s for a, s in tape.items() if s}, 'candidate sparse tape')
    reference_words = pack_state(reference['tape'], origin=origin, cells=cells,
                                 alphabet=program.alphabet, original_words=expected_initial_words)
    native.update(machine=candidate_machine == dict(control=reference['control'], head=reference['head'])
                  and stop == reference['status'], transitions=transitions == reference['transitions'],
                  tape=actual_words == reference_words)
    # XOR is evaluated over every uploaded logical texel; declared padding is 0.
    checksum = [0, 0, 0, 0]
    for index, plane in enumerate(PLANES):
        import numpy as np
        checksum[index] = int(np.bitwise_xor.reduce(atlas['planes'][plane].reshape(-1), initial=0))
    if injection == 'texture':
        checksum[0] ^= 1
    equal(summary.get('warm_checksum'), checksum, 'whole uploaded texture warm checksum')
    equal(summary.get('reread_checksum'), checksum, 'whole uploaded texture reread checksum')
    integer(summary.get('sm_before'), 'SM before')
    equal(summary.get('sm_after'), summary['sm_before'], 'same SM across kernel')
    native['passed'] = all(native[key] for key in ('gates', 'controller', 'machine', 'transitions', 'tape', 'texture_sweeps'))
    equal(summary.get('verification'), native, 'independently derived native verification flags')
    accepted = native['passed'] and stop in (0, 1)
    equal(summary.get('accepted'), accepted, 'transaction acceptance')
    equal(summary.get('status'), 'passed' if accepted else 'rejected_program' if native['passed'] else 'rejected_verification', 'transaction status')
    committed_machine = candidate_machine if accepted else summary['before']
    committed_words = actual_words if accepted else expected_initial_words
    committed_tape = tape if accepted else before['tape']
    equal(summary.get('committed'), committed_machine, 'commit/rollback control and head')
    equal(read_packed(directory / 'committed.u32le'), committed_words, 'commit/rollback all packed words')
    equal(read_nonzero_tape(directory / 'committed_tape.csv'),
          {a: s for a, s in committed_tape.items() if s}, 'commit/rollback sparse tape')
    marker = 'COMMITTED' if accepted else 'REJECTED'
    if not (directory / marker).is_file() or (directory / ('REJECTED' if accepted else 'COMMITTED')).exists():
        raise ValueError('transaction marker disagreement')
    components = payload_bytes(stored_words=pr * pw, gates=gates,
        outputs=len(circuit['outputs']), wires=inputs + gates, budget=budget, cells=cells, bits=program.bits)
    equal(summary.get('abi'), dict(gate=8, gate_trace=36, evaluation=48,
          transition=40, kernel_result=80, u32=4, texture_texel=16), 'pinned device ABI')
    equal(summary.get('device_payload_bytes'), sum(components.values()), 'exact allocated device payload bytes')
    equal(summary.get('host_geometry_bytes'), pr * pw * 48 + rows * words * 88,
          'exact declared host geometry bytes')
    memory = integer(summary.get('memory_budget_bytes'), 'memory budget', 1)
    reserve = integer(summary.get('reserve_bytes'), 'memory reserve')
    device = summary.get('device', {})
    free = integer(device.get('free_bytes_at_start'), 'device free bytes', 1)
    total = integer(device.get('total_bytes'), 'device total bytes', free)
    if sum(components.values()) > memory or memory + reserve > free:
        raise ValueError('device payload/budget/reserve admission disagreement')
    if 'memory_mib' in (expected or {}):
        equal(memory, min(expected['memory_mib'] << 20, free - reserve), 'requested memory admission')
    if 'reserve_mib' in (expected or {}):
        equal(reserve, expected['reserve_mib'] << 20, 'requested device reserve')
    max_texture = integer(device.get('max_texture_1d_linear'), 'maximum texture texels', 1)
    if pr * pw > max_texture:
        raise ValueError('texture extent exceeds reported device limit')
    for key in ('runtime', 'driver', 'cc_major', 'cc_minor'):
        integer(device.get(key), 'device ' + key)
    if not isinstance(device.get('name'), str) or not device['name']:
        raise ValueError('missing device identity')
    duration = summary.get('kernel_ms')
    if type(duration) not in (int, float) or not math.isfinite(duration) or duration < 0:
        raise ValueError('invalid CUDA event duration')
    reads = dict(warm=pr * pw, gates=actual_evals * gates, reread=pr * pw,
                 total=2 * pr * pw + actual_evals * gates)
    equal(summary.get('texture_reads'), reads, 'texture read counts')
    return dict(status='passed', computation_accepted=accepted, rejection_verified=not accepted,
        injection=injection, compiler_truth_rows=truth_rows, controller_evaluations=actual_evals,
        gate_evaluations=actual_evals * gates, nor_faults_detected=actual_nor_mismatches,
        gates_differing_from_correct_execution=native['gate_mismatches'],
        odd_seam_gate_evaluations=sum(site[3] for site in sites) * actual_evals,
        tm_transitions=len(reference['transitions']), actual_transitions=len(transitions),
        program_stop=STOP_NAMES[stop], reference_stop=reference['status_name'],
        packed_tape_words_verified=len(actual_words) * 3,
        scalar_atlas_bits_verified=atlas['verified_bits'], device_payload_components=components,
        device_payload_bytes=sum(components.values()), texture_reads=reads,
        export_hashes={name: sha256(directory / name) for name in (*FILES, marker)})
