# TOMAGI 1.0 `.tmg` binary format

All integers are little-endian 32-bit words. Signed fields use two's-complement `i32`; unsigned fields use `u32`. The format has no pointer-sized values and is identical on 32-bit and 64-bit hosts.

## Header: 128 bytes

| Byte | Size | Field |
|---:|---:|---|
| 0 | 8 | ASCII magic `TOMAGI1\0` |
| 8 | 4 | version word `0x00010000` |
| 12 | 4 | program flags |
| 16 | 4 | cell count |
| 20 | 4 | entry cell index |
| 24 | 4 | deterministic seed |
| 28 | 4 | default tick count |
| 32 | 4 | cell size, exactly 48 |
| 36 | 4 | state size, exactly 64 |
| 40 | 24 | six reserved zero words |
| 64 | 64 | initial `State64` |

The cell table begins at byte 128 and contains exactly `cell_count` consecutive `Cell48` records. File length is therefore:

```text
128 + 48 * cell_count
```

## State64

The 16-word state layout is defined in `state64_layout.json/csv`. Words 0-7 are signed coordinates and first differences; words 8-13 are unsigned topology, cell, lineage and output fields; word 14 is a signed relation residual; word 15 is status.

## Cell48

The 12-word cell layout is defined in `cell48_layout.json/csv`. A cell contains a canonical key, opcode, flags, four signed arguments, branch-0 and branch-1 successors, a payload and an auxiliary word.

## Canonical ordering

Cells are sorted by unsigned `(key_hi,key_lo)` order and keys are unique. Successors are indices after this canonical sort. The JSON compiler accepts successor IDs and resolves them after sorting.

## Deterministic arithmetic

- general additions are modulo `2^32`;
- signed interpretation is two's-complement;
- `theta`, `tick` and lower-case `phi` are normalized modulo `2^18`, `2^14` and `2^12` respectively;
- integer division in the L-system opcode truncates toward zero;
- topological wrap count uses mathematical floor division;
- no floating-point operation occurs in the hot binary evaluator.
