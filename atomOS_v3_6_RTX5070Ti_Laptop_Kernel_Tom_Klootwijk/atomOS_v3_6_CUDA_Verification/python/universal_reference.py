"""Independent sparse-dictionary interpreter and verifier for the atomOS U profile.

The simulator never reads or updates packed words. A separate packer reconstructs
the GPU representation only when checking an exported result. Standard library only.
"""
from __future__ import annotations

from dataclasses import dataclass
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import struct
from typing import Mapping

STOP_NAMES = {0: 'running', 1: 'halted', 2: 'missing_rule', 3: 'tape_range', 4: 'invalid'}
I64_MIN, I64_MAX = -(1 << 63), (1 << 63) - 1
U32 = (1 << 32) - 1


@dataclass(frozen=True)
class Program:
    states: int
    alphabet: int
    start_control: int
    start_head: int
    halts: frozenset[int]
    cells: Mapping[int, int]
    rules: Mapping[tuple[int, int], tuple[int, int, int]]

    @property
    def bits(self):
        return max(1, (self.alphabet - 1).bit_length())


def _decimal(token: str) -> int:
    if re.fullmatch(r'-?[0-9]+', token) is None:
        raise ValueError(f'expected decimal integer: {token!r}')
    return int(token, 10)


def _unsigned(token: str) -> int:
    value = _decimal(token)
    if token.startswith('-') or not 0 <= value <= U32:
        raise ValueError('unsigned 32-bit decimal required')
    return value


def parse_program(text: str) -> Program:
    """Parse public .atomos grammar independently of the native implementation."""
    rows = []
    for line in text.splitlines():
        values = line.split('#', 1)[0].split()
        if values:
            rows.append(values)
    if not rows or rows.pop(0) != ['atomos-universal', '1']:
        raise ValueError('missing atomos-universal 1 header')
    declarations, halts, cells, rules = {}, set(), {}, {}
    for row in rows:
        kind, rest = row[0], row[1:]
        if kind in ('states', 'alphabet', 'start'):
            count = 2 if kind == 'start' else 1
            if kind in declarations or len(rest) != count:
                raise ValueError(f'invalid or repeated {kind}')
            declarations[kind] = (_unsigned(rest[0]), _decimal(rest[1])) if kind == 'start' else (_unsigned(rest[0]),)
        elif kind == 'halt':
            if not rest:
                raise ValueError('empty halt declaration')
            for q in map(_unsigned, rest):
                if q in halts:
                    raise ValueError('duplicate halt state')
                halts.add(q)
        elif kind == 'cell':
            if len(rest) != 2:
                raise ValueError('cell needs address and symbol')
            address, symbol = _decimal(rest[0]), _unsigned(rest[1])
            if address in cells:
                raise ValueError('duplicate cell address')
            cells[address] = symbol
        elif kind == 'rule':
            if len(rest) != 5 or rest[-1] not in ('L', 'S', 'R'):
                raise ValueError('invalid rule')
            q, read, new_q, write = map(_unsigned, rest[:4])
            if (q, read) in rules:
                raise ValueError('duplicate transition rule')
            rules[q, read] = (new_q, write, {'L': -1, 'S': 0, 'R': 1}[rest[-1]])
        else:
            raise ValueError(f'unknown program clause: {kind}')
    if set(declarations) != {'states', 'alphabet', 'start'}:
        raise ValueError('states, alphabet and start declarations required')
    states, = declarations['states']
    alphabet, = declarations['alphabet']
    control, head = declarations['start']
    if not 1 <= states <= U32 or not 1 <= alphabet <= U32:
        raise ValueError('state/alphabet bounds')
    if not 0 <= control < states or not I64_MIN <= head <= I64_MAX:
        raise ValueError('initial control/head bounds')
    if any(not 0 <= q < states for q in halts):
        raise ValueError('halt state bounds')
    if any(not I64_MIN <= address <= I64_MAX or not 0 <= symbol < alphabet
           for address, symbol in cells.items()):
        raise ValueError('cell address/symbol bounds')
    if any(not (0 <= q < states and 0 <= read < alphabet and 0 <= new_q < states
                and 0 <= write < alphabet) for (q, read), (new_q, write, _) in rules.items()):
        raise ValueError('transition bounds')
    return Program(states, alphabet, control, head, frozenset(halts), cells, rules)


def read_program(path: str | Path) -> Program:
    return parse_program(Path(path).read_text(encoding='utf-8-sig'))


def initial_state(program: Program) -> dict:
    return dict(control=program.start_control, head=program.start_head, tape=dict(program.cells))


def growing_extent(state: dict, budget: int) -> tuple[int, int]:
    """Allocation policy: include the reachable interval, clipped at signed endpoints."""
    lower = max(I64_MIN, state['head'] - budget)
    upper = min(I64_MAX, state['head'] + budget)
    nonzero = [address for address, symbol in state['tape'].items() if symbol]
    lower, upper = min([lower, *nonzero]), max([upper, *nonzero])
    return lower, upper - lower + 1


def simulate(program: Program, state: dict, *, origin: int, cells: int, budget: int) -> dict:
    """Return a candidate prefix; a failed transition cannot partially modify it."""
    if type(origin) is not int or type(cells) is not int or type(budget) is not int:
        raise ValueError('integer runtime parameters required')
    if cells <= 0 or budget < 0 or not I64_MIN <= origin <= I64_MAX or origin + cells - 1 > I64_MAX:
        raise ValueError('invalid runtime bounds')
    q, head, tape = state['control'], state['head'], dict(state['tape'])
    transitions = []
    status = 0
    if type(q) is not int or type(head) is not int or not 0 <= q < program.states:
        status = 4
    elif any(type(a) is not int or type(s) is not int or not 0 <= s < program.alphabet
             for a, s in tape.items()):
        status = 4
    elif any(not origin <= a < origin + cells for a in tape):
        status = 3
    elif not origin <= head < origin + cells:
        status = 3
    elif q in program.halts:
        status = 1
    else:
        for _ in range(budget):
            read = tape.get(head, 0)
            rule = program.rules.get((q, read))
            if rule is None:
                status = 2
                break
            new_q, write, move = rule
            new_head = head + move
            if not origin <= new_head < origin + cells:
                status = 3
                break
            transitions.append(dict(step=len(transitions), control_before=q, head_before=head,
                                    read=read, write=write, move=move,
                                    control_after=new_q, head_after=new_head))
            if write:
                tape[head] = write
            else:
                tape.pop(head, None)
            q, head = new_q, new_head
            if q in program.halts:
                status = 1
                break
    return dict(control=q, head=head, tape={a: s for a, s in tape.items() if s}, status=status, status_name=STOP_NAMES[status],
                steps=len(transitions), transitions=transitions, accepted=status in (0, 1))


def pack_state(tape: Mapping[int, int], *, origin: int, cells: int,
               alphabet: int, original_words: list[int] | None = None) -> list[int]:
    """Build the logical bitstream mathematically; preserve original tail bits."""
    bits = max(1, (alphabet - 1).bit_length())
    logical_bits = bits * cells
    word_count = (logical_bits + 31) // 32
    if alphabet < 1 or cells <= 0:
        raise ValueError('packing bounds')
    if original_words is not None and (len(original_words) != word_count or
            any(type(word) is not int or not 0 <= word <= U32 for word in original_words)):
        raise ValueError('original packed word bounds')
    whole = 0
    for address, symbol in tape.items():
        if not origin <= address < origin + cells or not 0 <= symbol < alphabet:
            raise ValueError('packing address/symbol bounds')
        whole += symbol << ((address - origin) * bits)
    if original_words and logical_bits % 32:
        high = original_words[-1] >> (logical_bits % 32)
        whole += high << logical_bits
    return [(whole >> (32 * index)) & U32 for index in range(word_count)]


def read_nonzero_tape(path: str | Path) -> dict[int, int]:
    tape = {}
    with Path(path).open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ['address', 'symbol']:
            raise ValueError('tape CSV header mismatch')
        for row in reader:
            address, symbol = int(row['address']), int(row['symbol'])
            if address in tape or symbol <= 0:
                raise ValueError('duplicate address or nonpositive sparse symbol')
            tape[address] = symbol
    return tape


def read_packed(path: str | Path) -> list[int]:
    raw = Path(path).read_bytes()
    if len(raw) % 4:
        raise ValueError('partial packed word')
    return list(struct.unpack('<' + 'I' * (len(raw) // 4), raw))


def same_state(actual: dict, expected: dict, label: str) -> None:
    if any(not _exact(actual.get(field), expected.get(field)) for field in ('control', 'head', 'tape')):
        raise ValueError(f'{label}: control/head/tape disagreement')


def _csv_rows(path: Path, header=None):
    with path.open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream)
        if header is not None and reader.fieldnames != header:
            raise ValueError(f'{path.name}: unexpected CSV header')
        rows = list(reader)
    if any(None in row or None in row.values() for row in rows):
        raise ValueError(f'{path.name}: malformed CSV row')
    return rows


def _core_state(path):
    result = []
    for lane, row in enumerate(_csv_rows(path, ['lane', 'word', 'q'])):
        index, word, q = (int(row[key]) for key in ('lane', 'word', 'q'))
        if index != lane or not 0 <= word <= U32 or q not in (0, 1):
            raise ValueError(f'{path.name}: noncanonical core state')
        result.append((word, q))
    return result


def _exact(actual, expected):
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, dict):
        return actual.keys() == expected.keys() and all(_exact(actual[key], expected[key]) for key in actual)
    if isinstance(actual, (list, tuple)):
        return len(actual) == len(expected) and all(_exact(a, b) for a, b in zip(actual, expected))
    return actual == expected


def _require_equal(actual, expected, label):
    if not _exact(actual, expected):
        raise ValueError(f'{label}: {actual!r} != {expected!r}')


def verify_export(directory: str | Path, *, expected: dict | None = None) -> dict:
    """Check actual exported candidates and rollback using independent calculations.

    Process execution and binary/log provenance are the runner's responsibility.
    Metadata asserting success is never accepted in place of replaying its data.
    """
    from reference import (fixture, address, bit_core, producer, observe, bank,
                           verify_execution_metadata, MASKS, NAMES, TOL)
    directory = Path(directory)
    summary = json.loads((directory / 'engine.json').read_text(encoding='utf-8'))
    _require_equal(summary.get('schema'), 'atomOS-word-U-engine-v1', 'engine schema')
    _require_equal(summary.get('execution_profile'), 'word-plus-U-v1', 'execution profile')
    verify_execution_metadata(summary, expected_backend='cuda', expected_read='texture-packed')
    program_path = directory / 'program.atomos'
    program = read_program(program_path)
    _require_equal(summary.get('states'), program.states, 'program states')
    _require_equal(summary.get('alphabet'), program.alphabet, 'program alphabet')
    for key in ('rows', 'angles', 'words', 'padded_rows', 'padded_words', 'requested_epochs',
                'attempted_epochs', 'committed_epochs', 'steps_per_epoch', 'seed', 'tail_fill'):
        if type(summary.get(key)) is not int:
            raise ValueError(f'integer metadata required: {key}')
    if expected is not None:
        for key in ('rows', 'angles', 'layout', 'mode', 'profile', 'fringe', 'seed'):
            _require_equal(summary.get(key), expected[key], 'requested ' + key)
        _require_equal(summary['steps_per_epoch'], expected['budget'], 'requested U budget')
        _require_equal(summary['requested_epochs'], expected['epochs'], 'requested epochs')
        _require_equal(summary['tail_fill'], expected['tape_tail_fill'], 'requested tail fill')
        _require_equal(program_path.read_text(encoding='utf-8'), expected['program'], 'supplied program')
    rows, angles = summary['rows'], summary['angles']
    words, padded_rows, padded_words = (angles + 31) // 32, (rows + 7) // 8 * 8, ((angles + 31) // 32 + 7) // 8 * 8
    if not (1 <= rows <= 65536 and 1 <= angles <= 65536 and 1 <= summary['requested_epochs']
            and 0 <= summary['steps_per_epoch'] <= 65536 and 0 <= summary['seed'] <= U32):
        raise ValueError('engine configuration bounds')
    _require_equal((summary['words'], summary['padded_rows'], summary['padded_words']),
                   (words, padded_rows, padded_words), 'shape metadata')
    if summary['layout'] not in ('linear', 'morton8') or summary['mode'] not in ('provided', 'recurrent', 'shift-xor', 'shift-or'):
        raise ValueError('unknown storage/producer profile')
    if summary['profile'] not in ('source', 'directed', 'mixed') or type(summary['fringe']) is not bool:
        raise ValueError('unknown observation/fringe profile')
    resource_keys = ('memory_budget_bytes', 'reserve_bytes', 'maximum_steps_per_launch', 'requested_memory_mib',
                     'requested_reserve_mib', 'initial_free_vram_bytes', 'initial_available_host_bytes',
                     'host_table_budget_bytes', 'k1_payload_bytes', 'maximum_u_payload_bytes')
    for key in resource_keys:
        if type(summary.get(key)) is not int or summary[key] < 0:
            raise ValueError('nonnegative integer resource metadata required: ' + key)
    _require_equal(summary['maximum_steps_per_launch'], 65536, 'compiled per-launch U budget')
    _require_equal(summary['reserve_bytes'], summary['requested_reserve_mib'] << 20, 'requested memory reserve')
    budget_bytes, reserve, initial_free = (summary[k] for k in ('memory_budget_bytes', 'reserve_bytes', 'initial_free_vram_bytes'))
    if not 0 < initial_free <= summary['device']['total_bytes'] or reserve >= initial_free:
        raise ValueError('invalid memory admission snapshot')
    chosen_budget = (summary['requested_memory_mib'] << 20) if summary['requested_memory_mib'] else min(initial_free - reserve, (initial_free // 100) * 85)
    _require_equal(budget_bytes, chosen_budget, 'selected memory budget')
    if not 0 < budget_bytes <= initial_free - reserve:
        raise ValueError('budget does not preserve declared initial free-memory reserve')
    host_available = summary['initial_available_host_bytes']
    _require_equal(summary['host_table_budget_bytes'], min(budget_bytes, (host_available // 100) * 85) if host_available else budget_bytes,
                   'host table allocation budget')
    if program.states * program.alphabet * 16 + program.states * 4 > summary['host_table_budget_bytes']:
        raise ValueError('program table exceeds recorded host allocation budget')
    k1_payload = 16 * padded_rows * padded_words + 256 * rows * words
    _require_equal(summary['k1_payload_bytes'], k1_payload, 'exact K1 payload')
    if expected is not None:
        _require_equal(summary['requested_memory_mib'], expected.get('memory_mib', 0), 'requested memory override')
        _require_equal(summary['requested_reserve_mib'], expected.get('reserve_mib', 512), 'requested reserve override')
    planes = [read_packed(directory / filename) for filename in MASKS]
    if any(len(plane) != padded_rows * padded_words for plane in planes):
        raise ValueError('mask plane length')
    lanes, masks = [], []
    for r in range(padded_rows):
        for w in range(padded_words):
            actual = [plane[address(r, w, padded_words, summary['layout'])] for plane in planes]
            if r >= rows or w >= words:
                if any(actual):
                    raise ValueError('nonzero mask padding')
            else:
                m, lane = fixture(summary, r, w)
                if m != actual:
                    raise ValueError('mask differs from independent fixture')
                masks.append(m)
                lanes.append(lane)
    input_rows = _csv_rows(directory / 'inputs.csv')
    if len(input_rows) != len(lanes):
        raise ValueError('input lane count')
    for index, (row, lane) in enumerate(zip(input_rows, lanes)):
        if set(row) != set(lane):
            raise ValueError('input lane schema')
        for key, value in lane.items():
            actual = float(row[key]) if key in ('dr', 'dp', 'alpha', 'interval') else int(row[key])
            if actual != value:
                raise ValueError(f'input fixture mismatch at lane {index}, {key}')
    epochs = summary.get('epochs')
    if not isinstance(epochs, list) or len(epochs) != summary['attempted_epochs'] or not 1 <= len(epochs) <= summary['requested_epochs']:
        raise ValueError('attempted epoch count')
    streamed = directory / 'epochs.jsonl'
    if streamed.exists():
        records = [json.loads(line) for line in streamed.read_text(encoding='utf-8').splitlines() if line.strip()]
        _require_equal(records, epochs, 'streamed epoch records')
    core_rows = iter(_csv_rows(directory / 'trace.csv'))
    u_rows = iter(_csv_rows(directory / 'u_trace.csv', ['epoch', 'step', 'control_before', 'head_before',
                                                     'read', 'write', 'move', 'control_after', 'head_after']))
    u_state = initial_state(program)
    u_state['tape'] = {a: s for a, s in u_state['tape'].items() if s}
    _require_equal(summary.get('u_initial'), {k: u_state[k] for k in ('control', 'head')}, 'initial machine')
    core_state = [(lane['initial_word'], lane['initial_q']) for lane in lanes]
    verified_steps = committed_steps = committed_epochs = k1_lane_epochs = 0
    time = 0.0
    max_error = 0.0
    counts = [0, 0, 0]
    attempted_statuses = []
    maximum_u_payload = 0
    interval = summary.get('interval')
    if isinstance(interval, bool) or not isinstance(interval, (int, float)) or not math.isfinite(interval) or interval <= 0:
        raise ValueError('positive finite interval required')

    def equal_float(raw, value, label):
        nonlocal max_error
        if value is None:
            if raw != '':
                raise ValueError(f'{label}: undefined observation has a numeric value')
            return
        actual = float(raw)
        if not math.isfinite(actual):
            raise ValueError(f'{label}: nonfinite observation')
        error = abs(actual - value)
        max_error = max(max_error, error)
        if error > TOL:
            raise ValueError(f'{label}: angle disagreement exceeds unchanged tolerance')

    for index, epoch in enumerate(epochs):
        _require_equal(epoch.get('epoch'), index, 'epoch order')
        if expected is not None and not expected.get('growing'):
            _require_equal(epoch.get('origin'), expected['origin'], 'fixed tape origin')
            _require_equal(epoch.get('cells'), expected['cells'], 'fixed tape cell count')
        origin, cell_count = epoch.get('origin'), epoch.get('cells')
        if type(origin) is not int or type(cell_count) is not int:
            raise ValueError('finite tape metadata')
        if expected is not None and expected.get('growing'):
            _require_equal((origin, cell_count), growing_extent(u_state, expected['budget']), 'growing tape extent')
        candidate = simulate(program, u_state, origin=origin, cells=cell_count, budget=summary['steps_per_epoch'])
        accepted = candidate['accepted']
        _require_equal(epoch.get('accepted'), accepted, 'epoch acceptance')
        _require_equal(epoch.get('status'), candidate['status_name'], 'U stop status')
        _require_equal(epoch.get('steps'), candidate['steps'], 'U transition count')
        _require_equal(epoch.get('packed_bits'), program.bits, 'symbol bit width')
        _require_equal(epoch.get('packed_words'), (cell_count * program.bits + 31) // 32, 'packed word count')
        u_payload = epoch['packed_words'] * 4 + program.states * program.alphabet * 16 + program.states * 4 + summary['steps_per_epoch'] * 40 + 24
        _require_equal(epoch.get('u_payload_bytes'), u_payload, 'exact U payload')
        maximum_u_payload = max(maximum_u_payload, u_payload)
        if k1_payload + u_payload > budget_bytes:
            raise ValueError('combined payload exceeds declared device memory budget')
        _require_equal(epoch.get('tail_fill'), summary['tail_fill'], 'tail initialization')
        for key in ('candidate_verification', 'packed_tape_verification', 'k1_verification'):
            _require_equal(epoch.get(key), 'passed', key)
        for key in ('k1_ms', 'u_ms'):
            value = epoch.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError('invalid kernel timing')
        committed_u = {key: candidate[key] for key in ('control', 'head', 'tape')} if accepted else u_state
        stem = directory / f'epoch_{index}'
        expected_before_words = pack_state(u_state['tape'], origin=origin, cells=cell_count,
            alphabet=program.alphabet, original_words=[summary['tail_fill']] * epoch['packed_words'])
        for phase, state in (('before', u_state), ('candidate', candidate), ('committed', committed_u)):
            recorded = dict(epoch.get('u_' + phase, {}), tape=read_nonzero_tape(Path(str(stem) + f'_u_{phase}.csv')))
            same_state(recorded, state, f'epoch {index} U {phase}')
            packed = read_packed(Path(str(stem) + f'_u_{phase}.u32le'))
            reconstructed = pack_state(state['tape'], origin=origin, cells=cell_count,
                alphabet=program.alphabet, original_words=expected_before_words)
            _require_equal(packed, reconstructed, f'epoch {index} packed {phase}, including untouched cells/tail')
        for transition in candidate['transitions']:
            actual = next(u_rows, None)
            if actual is None:
                raise ValueError('missing exported GPU U transition')
            actual = {key: int(value) for key, value in actual.items()}
            _require_equal(actual, dict(epoch=index, **transition), 'GPU U transition')
        next_core = []
        for lane_index, (lane, mask, (word, q)) in enumerate(zip(lanes, masks, core_state)):
            row = next(core_rows, None)
            if row is None:
                raise ValueError('missing K1 candidate trace row')
            produced = producer(word, lane, summary['mode'])
            valid = (1 << min(32, angles - (lane_index % words) * 32)) - 1
            am, nm, bm, fm = mask
            aa, nn, hits, output = bit_core(produced, am, nm, bm, valid, fm if summary['fringe'] else valid)
            q_after = {(0, 0): q, (1, 0): 1, (0, 1): 0, (1, 1): 1 - q}[lane['j'], lane['k']]
            blend = sum(lane[k] for k in ('north', 'axis', 'kinematic')) % 2 if lane['blend_known'] else 0
            angle = observe(lane)
            checks = bank(lane, angle)
            integers = dict(epoch=index, lane=lane_index, input_word=word, q_before=q, produced=produced,
                asa=aa, na=nn, hits=hits, output=output, q_after=q_after, blend=blend,
                blend_known=lane['blend_known'], beta_status=angle['beta_status'], angle_status=angle['status'])
            for key, value in integers.items():
                if int(row[key]) != value:
                    raise ValueError(f'K1 candidate mismatch epoch {index}, lane {lane_index}, {key}')
            for key in ('beta', 'raw', 'principal', 'line'):
                equal_float(row[key], angle[key], key)
            for name, check in zip(NAMES, checks):
                if int(row[name + '_state']) != check['state'] or int(row[name + '_reason']) != check['reason']:
                    raise ValueError('K1 invariant status/reason disagreement')
                equal_float(row[name + '_error'], check['error'], name)
                counts[check['state']] += 1
            next_core.append((output, q_after))
            k1_lane_epochs += 1
        committed_core = next_core if accepted else core_state
        for phase, state in (('before', core_state), ('candidate', next_core), ('committed', committed_core)):
            _require_equal(_core_state(Path(str(stem) + f'_core_{phase}.csv')), state,
                           f'epoch {index} K1 {phase}')
        if epoch.get('time_before') != time:
            raise ValueError('time changed before commitment')
        if accepted:
            committed_epochs += 1
            committed_steps += candidate['steps']
            time += interval
        elif index != len(epochs) - 1:
            raise ValueError('execution continued after rejected master epoch')
        if epoch.get('time_after') != time:
            raise ValueError('time committed or rolled back incorrectly')
        verified_steps += candidate['steps']
        attempted_statuses.append(candidate['status_name'])
        u_state, core_state = committed_u, committed_core
    if next(core_rows, None) is not None or next(u_rows, None) is not None:
        raise ValueError('extra candidate trace rows')
    rejected = not epochs[-1]['accepted']
    _require_equal(summary.get('status'), 'rejected' if rejected else 'passed', 'master status')
    if not rejected and len(epochs) != summary['requested_epochs']:
        raise ValueError('incomplete successful run')
    marker, absent = ('PREFIX_VERIFIED', 'COMMITTED') if rejected else ('COMMITTED', 'PREFIX_VERIFIED')
    if not (directory / marker).is_file() or (directory / absent).exists():
        raise ValueError('incorrect publication marker')
    if rejected:
        _require_equal(json.loads((directory / 'rejection.json').read_text(encoding='utf-8')), epochs[-1], 'rejection record')
    for key, value in dict(committed_epochs=committed_epochs, verified_u_steps=verified_steps,
                           committed_u_steps=committed_steps, verified_k1_lanes=k1_lane_epochs).items():
        _require_equal(summary.get(key), value, key)
    if summary.get('time') != time:
        raise ValueError('final time differs')
    _require_equal(summary['maximum_u_payload_bytes'], maximum_u_payload, 'maximum actual U payload')
    _require_equal(summary.get('u_status'), attempted_statuses[-1], 'final attempted U status')
    final_machine = {key: u_state[key] for key in ('control', 'head')}
    _require_equal(summary.get('u_final'), final_machine, 'final machine metadata')
    _require_equal(json.loads((directory / 'machine_state.json').read_text(encoding='utf-8')), final_machine, 'final machine file')
    _require_equal(read_nonzero_tape(directory / 'final_tape.csv'), u_state['tape'], 'final committed tape')
    _require_equal(_core_state(directory / 'final_state.csv'), core_state, 'final committed K1 state')
    return dict(status='passed', backend_recorded='cuda', attempted_epochs=len(epochs),
                committed_epochs=committed_epochs, rejected_epochs=int(rejected),
                u_transitions=verified_steps, committed_u_transitions=committed_steps,
                k1_lane_epochs=k1_lane_epochs, u_statuses=attempted_statuses,
                max_float_difference_radians=max_error, tolerance_radians=TOL,
                invariant_counts=counts, all_packed_words_and_tails_verified=True,
                rollback_verified=rejected, program_states=program.states, alphabet=program.alphabet)


FORMALIZATION_SHA256 = 'b51651c007c560775ff1950e278789cd7674e131ec71a09ebd9254cebe9c19ce'
SEAL_FILENAME = 'engine_seal.json'


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf-8')


def _seal_body(directory: Path, verification: dict) -> dict:
    if verification.get('status') != 'passed':
        raise ValueError('only an independently verified export can be sealed')
    manifest = {}
    for path in sorted(directory.rglob('*')):
        if path.is_symlink():
            raise ValueError('seal refuses symbolic links')
        if path.is_file() and path != directory / SEAL_FILENAME:
            manifest[path.relative_to(directory).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    engine = json.loads((directory / 'engine.json').read_text(encoding='utf-8'))
    identity = dict(concept_author='Tom Klootwijk', source='atomOS v3.6 Total Integrated Engine M1',
                    source_pdf_sha256=FORMALIZATION_SHA256,
                    program_sha256=manifest['program.atomos'])
    genesis = hashlib.sha256(b'TomKlootwijk:atomOS:U1:genesis\0' + _canonical(identity)).hexdigest()
    predecessor = genesis
    accepted, rejected = [], []
    for record in engine['epochs']:
        evidence = {name: digest for name, digest in manifest.items()
                    if name.startswith('epoch_' + str(record['epoch']) + '_')}
        content = dict(record=record, files=evidence)
        domain = b'TomKlootwijk:atomOS:U1:accepted\0' if record['accepted'] else b'TomKlootwijk:atomOS:U1:rejected-attempt\0'
        digest = hashlib.sha256(domain + bytes.fromhex(predecessor) + _canonical(content)).hexdigest()
        link = dict(epoch=record['epoch'], predecessor=predecessor, digest=digest)
        if record['accepted']:
            accepted.append(link)
            predecessor = digest
        else:
            rejected.append(link)
    return dict(schema='atomOS-U1-post-run-audit-seal-v1', identity=identity, genesis=genesis,
                scope='Python post-run audit seal after independent export verification; not a native precommit ledger',
                authentication='Local integrity only; authenticity requires a separately trusted seal digest',
                files=manifest, accepted_epoch_chain=accepted, rejected_attempt_receipts=rejected,
                accepted_head=predecessor, verification=verification)


def seal_engine(directory: str | Path, *, expected: dict | None = None) -> dict:
    """Replay before creating a new local audit seal; refuse replacement."""
    directory = Path(directory)
    target = directory / SEAL_FILENAME
    if target.exists():
        raise ValueError('an engine seal already exists')
    verification = verify_export(directory, expected=expected)
    body = _seal_body(directory, verification)
    receipt = dict(body, seal_sha256=hashlib.sha256(b'TomKlootwijk:atomOS:U1:seal\0' + _canonical(body)).hexdigest())
    with target.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(receipt, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
    return dict(status='passed', file=SEAL_FILENAME, seal_sha256=receipt['seal_sha256'],
                accepted_epochs=len(body['accepted_epoch_chain']),
                rejected_attempts=len(body['rejected_attempt_receipts']), sealed_files=len(body['files']))


def verify_engine_seal(directory: str | Path, *, expected: dict | None = None) -> dict:
    directory = Path(directory)
    saved = json.loads((directory / SEAL_FILENAME).read_text(encoding='utf-8'))
    verification = verify_export(directory, expected=expected)
    body = _seal_body(directory, verification)
    actual = dict(body, seal_sha256=hashlib.sha256(b'TomKlootwijk:atomOS:U1:seal\0' + _canonical(body)).hexdigest())
    if _canonical(saved) != _canonical(actual):
        raise ValueError('engine audit seal, file manifest, or epoch chain differs')
    return dict(status='passed', file=SEAL_FILENAME, seal_sha256=actual['seal_sha256'],
                accepted_epochs=len(body['accepted_epoch_chain']),
                rejected_attempts=len(body['rejected_attempt_receipts']), sealed_files=len(body['files']))
