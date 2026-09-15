#!/usr/bin/env python3
"""Compile literal Cell48 source and retain independent Python feedback traces."""
from pathlib import Path
import copy
import hashlib
import json
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / 'vendor/wqk_0_6'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def strict_json(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON key: ' + key)
            result[key] = value
        return result
    def reject(value):
        raise ValueError('non-finite JSON: ' + value)
    return json.loads(data, object_pairs_hook=unique, parse_constant=reject)


def main():
    imports = json.loads((ROOT / 'source/WQK_IMPORTS.json').read_text(encoding='utf-8'))
    for item in imports['files']:
        raw = (VENDOR / item['path']).read_bytes()
        if len(raw) != item['bytes'] or digest(raw) != item['sha256']:
            raise ValueError('upstream reference changed: ' + item['path'])
    sys.path.insert(0, str(VENDOR / 'src/python'))
    from tomagi.compiler import compile_document
    from tomagi.core import step, Opcode, i32
    from tomagi.format import dumps, loads
    source = ROOT / 'examples/wqk_feedback.cells.json'
    document = strict_json(source.read_text(encoding='utf-8'))
    program = compile_document(document)
    binary = dumps(program)
    if dumps(loads(binary)) != binary or dumps(compile_document(copy.deepcopy(document))) != binary:
        raise ValueError('literal program compilation is not byte-repeatable')
    (ROOT / 'examples/wqk_feedback.tmg').write_bytes(binary)
    state = copy.deepcopy(program.initial_state)
    state.cell = program.entry
    q = parity = last_epoch = last_drive = hinges = initialized = 0
    rows = []
    expected = bytearray(b'R16FBR1\0' + struct.pack('<II', 24, 1))
    for epoch in range(24):
        was_halted = bool(state.status & 1)
        if not was_halted:
            state.rho, state.vrho = i32(q), i32(q >> 32)
        before = state.cell
        instruction = program.cells[before]
        step(program, state)
        emitted = not was_halted and instruction.opcode == Opcode.EMIT
        if emitted:
            # Declared fixture profile: x=drive, J=y, K=~y, both ASA/NA masks
            # are identity and valid_mask=0xffffffff. Therefore q+=payload.
            q = instruction.payload & 0xffffffff
            parity ^= 1
            last_epoch, last_drive, hinges, initialized = epoch, q, hinges + 1, 1
        word_state = [q, parity, last_epoch, last_drive, hinges, initialized, 0, 0]
        expected.extend(struct.pack('<16I8Q', *state.words(), *word_state))
        rows.append({'step': epoch + 1, 'receipt_epoch': epoch, 'cell_before': before, 'emitted': emitted,
                     'state_words': state.words(), 'word_state': word_state})
    (ROOT / 'examples/wqk_feedback.expected.bin').write_bytes(expected)
    report = {
        'profile': 'ATOMOS-TOMAGI-EMIT-FEEDBACK-R1',
        'source': source.name, 'source_sha256': digest(source.read_bytes()),
        'compilation': 'Original TOMAGI 1.0 literal-cell compiler; actual cell definitions are executable inputs',
        'seeded_formal_profile_claimed': False,
        'upstream_seed_sha256': digest((VENDOR / 'TOM_seed_genome_2026-09-01.txt').read_bytes()),
        'program_bytes': len(binary), 'program_sha256': digest(binary),
        'expected_bytes': len(expected), 'expected_sha256': digest(expected),
        'reference': 'Unmodified upstream Python canonical transition; separately specified copy-drive word equation',
        'native_gpu_execution': 'Recorded separately by tomagi_feedback_tests',
        'binding': {'inject': {'rho': 'q low32', 'vrho': 'q high32'}, 'drive': 'executed EMIT payload',
                    'valid_mask': 0xffffffff, 'x_lut': 12, 'j_lut': 12, 'k_lut': 3},
        'rows': rows,
    }
    (ROOT / 'review/wqk_fixture_reference.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('program_bytes', 'program_sha256', 'expected_sha256')}, indent=2))


if __name__ == '__main__':
    main()
