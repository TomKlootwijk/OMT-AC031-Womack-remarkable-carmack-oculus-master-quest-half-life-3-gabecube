"""Independent AOPLUT1 decoder and Boolean oracle; never imports the compiler.

One-bit logical cells are decoded individually from the canonical Klein chart.
This intentionally does not reuse the writer's bit reader or native source_gate.
"""
from __future__ import annotations

import csv
import hashlib
import json
import struct
from pathlib import Path


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decode_bank(path: Path, manifest: Path | None = None) -> dict:
    bank_path = Path(path)
    if bank_path.stat().st_size > 512 << 20:
        raise ValueError('bank host byte budget')
    raw = bank_path.read_bytes()
    if len(raw) > 512 << 20:
        raise ValueError('bank host byte budget')
    if len(raw) < 56 or raw[:8] != b'AOPLUT1\n':
        raise ValueError('bank magic or truncated header')
    version, rows, angles, count = struct.unpack_from('<4I', raw, 8)
    if version != 1 or not 2 <= rows <= 65536 or not 32 <= angles <= 65536 or angles % 32:
        raise ValueError('bank schema/dimensions')
    padded_rows = ((rows + 7) // 8) * 8
    padded_words = (((angles // 32) + 7) // 8) * 8
    if padded_rows * padded_words > 1 << 20:
        raise ValueError('native profile page word bound')
    page_bytes = rows * angles // 8
    if page_bytes < 128:
        raise ValueError('page too small for header')
    if not 1 <= count <= 65536 or len(raw) != 56 + count * (8 + page_bytes):
        raise ValueError('bank extent')
    result = dict(rows=rows, angles=angles, capsule_count=count,
                  master_seed_hex=raw[24:56].hex(), bank_file_sha256=sha(raw), capsules=[])
    for slot in range(count):
        start = 56 + slot * (8 + page_bytes)
        row0, angle0 = struct.unpack_from('<2I', raw, start)
        if row0 >= rows or angle0 >= angles:
            raise ValueError('origin outside chart')
        payload = raw[start+8:start+8+page_bytes]
        words = struct.unpack('<' + 'I' * (page_bytes//4), payload)
        bits = []
        # Scatter/gather at each physical bit, independently of the writer.
        for b in range(rows * angles):
            row = (row0 + b // angles) % rows
            raw_angle = angle0 + b % angles
            if (raw_angle // angles) % 2:
                row = rows - 1 - row
            angle = raw_angle % angles
            word = words[row * (angles // 32) + angle // 32]
            bits.append((word >> (angle % 32)) & 1)
        def unsigned(offset, width):
            if offset < 0 or offset + width > len(bits):
                raise ValueError('bitfield outside page')
            return sum(bits[offset+i] << i for i in range(width))
        header = [unsigned(i*32, 32) for i in range(32)]
        if header[0:2] != [0x31504b41, 1] or header[10] != 1024 or header[11] or any(header[28:]):
            raise ValueError('program header/schema/reserved fields')
        inputs, outputs, gates, width, length, identity, revision, nxt = header[2:10]
        wires = inputs + 1 + gates
        if inputs > 32 or not 1 <= outputs <= 32 or wires > 1024:
            raise ValueError('native profile resource bound')
        if width != max(1, (wires - 1).bit_length()):
            raise ValueError('noncanonical wire width')
        if length != 1024 + (2*gates + outputs)*width or length > len(bits):
            raise ValueError('program bit extent')
        if identity != slot or revision < 1 or nxt >= count or any(bits[length:]):
            raise ValueError('identity/link/version or dirty unused cells')
        seed = struct.pack('<8I', *header[12:20])
        expected_origin = (int.from_bytes(seed[:16], 'big')*rows >> 128,
                           int.from_bytes(seed[16:], 'big')*angles >> 128)
        if (row0, angle0) != expected_origin:
            raise ValueError('seed and chart origin disagree')
        pairs = []
        offset = 1024
        for gate in range(gates):
            a, b = unsigned(offset, width), unsigned(offset+width, width)
            if max(a, b) >= inputs + 1 + gate:
                raise ValueError('forward/cyclic gate reference')
            pairs.append((a, b))
            offset += 2*width
        refs = [unsigned(offset+i*width, width) for i in range(outputs)]
        if any(ref >= wires for ref in refs):
            raise ValueError('output reference outside circuit')
        result['capsules'].append(dict(
            id=identity, version=revision, next_slot=nxt, input_bits=inputs,
            output_bits=outputs, gate_count=gates, ref_width=width, bit_length=length,
            origin_row=row0, origin_angle=angle0, seed_hex=seed.hex(),
            parent_sha256=struct.pack('<8I', *header[20:28]).hex(),
            content_sha256=sha(b'atomos-program-page-v1\0'+raw[start:start+8]+payload),
            gates=pairs, outputs=refs))
    if manifest is not None:
        claimed = json.loads(Path(manifest).read_text(encoding='utf-8'))
        if claimed.get('schema') != 'atomos-program-lut-bank-v1':
            raise ValueError('manifest schema mismatch')
        for field in ('rows', 'angles', 'capsule_count', 'master_seed_hex', 'bank_file_sha256'):
            if claimed[field] != result[field]:
                raise ValueError('manifest mismatch: '+field)
        if len(claimed['capsules']) != count:
            raise ValueError('manifest capsule count')
        for expected, actual in zip(claimed['capsules'], result['capsules']):
            for field in ('id','version','next_slot','input_bits','output_bits','gate_count',
                          'ref_width','bit_length','origin_row','origin_angle','seed_hex',
                          'parent_sha256','content_sha256'):
                if expected[field] != actual[field]:
                    raise ValueError('manifest capsule mismatch: '+field)
    return result


def evaluate(capsule: dict, value: int) -> int:
    """Independent Boolean NOR, not the implementation's absorption expression."""
    wires = [bool((value >> bit) & 1) for bit in range(capsule['input_bits'])] + [False]
    for left, right in capsule['gates']:
        wires.append(not (wires[left] or wires[right]))
    return sum(int(wires[ref]) << bit for bit, ref in enumerate(capsule['outputs']))


def replay(bank: dict, initial: int, hops: int, first: int = 0) -> list[dict]:
    records = []
    slot, value = first, initial
    for hop in range(hops):
        capsule = bank['capsules'][slot]
        output = evaluate(capsule, value)
        records.append(dict(hop=hop, program_id=slot, version=capsule['version'],
                            input=value, output=output, next_slot=capsule['next_slot']))
        value, slot = output, capsule['next_slot']
    return records


def verify_trace(path: Path, bank: dict, initial: int, hops: int, first: int = 0,
                 mode: str = 'chain') -> dict:
    with Path(path).open(encoding='utf-8', newline='') as stream:
        actual = list(csv.DictReader(stream))
    if mode == 'chain':
        expected = replay(bank, initial, hops, first)
    elif mode == 'domain':
        capsule = bank['capsules'][first]
        if hops != 1 << capsule['input_bits']:
            raise ValueError('incomplete exhaustive native domain')
        expected = [dict(hop=x,program_id=first,version=capsule['version'],input=x,
                         output=evaluate(capsule,x),next_slot=capsule['next_slot'])
                    for x in range(hops)]
    else:
        raise ValueError('unknown execution mode')
    if len(actual) != len(expected):
        raise ValueError('native hop count')
    for row, wanted in zip(actual, expected):
        for field, value in wanted.items():
            if int(row[field]) != value:
                raise ValueError(f'native trace mismatch hop {wanted["hop"]}: {field}')
    return dict(status='passed', hops=len(expected),
                semantic_sha256=sha(json.dumps(expected, sort_keys=True, separators=(',', ':')).encode()))
