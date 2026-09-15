# R16 native TOMAGI execution contract

`include/atomos/tomagi_vm.hpp` and `cuda/tomagi_vm.cu` implement the finite TOMAGI 1.0 machine from the supplied WQK 0.6 source. The source authorities are the preserved `vendor/wqk_0_6/src/c/tomagi.h`, `src/c/tomagi.c`, and Python `tomagi/core.py` and `format.py`; the release provenance manifest identifies their source contents. `formal/WQK_INTEGRATION.md` supplies the surrounding mathematical and application interpretation. This document specifies the native memory and execution boundary. It is a finite integer and modular phase profile, distinct from the inherited exact rational/golden-ratio expression engine.

## Canonical input and raw state

The constructor accepts canonical `.tmg` bytes: little endian, eight-byte magic `TOMAGI1\0`, version `0x00010000`, 128-byte header, 48-byte cells, and 64-byte initial state. Header offsets 12, 16, 20, 24 and 28 hold flags, cell count, entry index, seed and default ticks. Offsets 32 and 36 declare cell/state sizes; offsets 40 through 63 are six zero reserved words; offsets 64 through 127 contain State64. Exact length is `128 + 48 * cell_count`. The cell table is nonempty, its entry and both successors are in range, opcodes are 0 through 15, and unsigned `(key_hi,key_lo)` pairs are strictly increasing and unique. Unknown flag bits remain preserved. An invalid RADIX argument is a per-transition fault, not a blanket rejection of an otherwise unexecuted cell.

State64 words are:

| Words | Meaning |
|---|---|
| 0–3 | Signed rho, theta, tick, phase |
| 4–7 | Signed corresponding velocities |
| 8–13 | Unsigned orientation, sheet, branch, cell, lineage, output |
| 14–15 | Signed residual, unsigned status |

Cell48 words are `(key_hi,key_lo,opcode,flags,arg0,arg1,arg2,arg3,next0,next1,payload,aux)`, with signed argument interpretation. The C++ records store **raw uint32 words**; signed interpretation is explicit. `header_state()` returns all sixteen initial words unchanged. `entry_state()` changes only the cell word to the declared entry. The constructor starts one such entry lane, matching the source fresh-run convention. `set_states()` is explicit checkpoint initialization: every provided raw word is retained, including a nonnormalized branch, signed phase, or arbitrary cell index. It clears sidecar faults and receipts, clears captured traces, resets the next dispatch epoch to zero, and increments the state generation. It never normalizes the first state to conceal an instruction difference.

## Transition semantics

Let `u32` reduce an integer modulo `2^32` and `s32` give its signed two's-complement interpretation. Coordinate periods are `(2^20,2^18,2^14,2^12)`. Before the body, the machine captures the old cell index and normalized key

`K = mod(rho,2^20)*2^44 + mod(theta,2^18)*2^26 + mod(tick,2^14)*2^12 + mod(phase,2^12)`.

Normalization here is a key view and does not mutate the raw input. Masking raw words gives the same normalized residues because every period divides `2^32`. Cell selection uses the raw PC word, not this key. The source unsigned hash is retained exactly:

```
x ^= x >> 16; x *= 0x7feb352d;
x ^= x >> 15; x *= 0x846ca68b;
x ^= x >> 16;
```

Multiplication and addition in this hash wrap modulo `2^32`. Rotate and population parity operate on unsigned words. Bodies follow the source order, including aliasing when SET or JIT1 selects a special state word.

| Opcode | Body before the mandatory postlude |
|---:|---|
| 0 NOP | No body write. |
| 1 SET | Copy arg0 bits to state word `flags & 15`. |
| 2 JIT1 | `h=mix(seed XOR old_key_hi XOR rotl(old_key_lo,13) XOR raw_tick XOR aux)`; assign branch to popcount parity; then add `+arg0` for parity one or `-arg0` for zero to the selected state word, modulo `2^32`. A selected branch word observes the earlier branch assignment. |
| 3 KIN2 | For each coordinate, add its argument to velocity, then add the updated velocity to position; both are word additions. |
| 4 PHI | Compute signed phase plus arg0 in signed64; floor-divide by `2^12`; retain reduced phase. Odd wrap count and flag bit4 toggle orientation. Nonzero wrap sets PHI_WRAP, zero clears it. Branch is reduced phase bit11 when flag bit5 is set, otherwise wrap parity. |
| 5 TIME | Compute signed tick plus arg0 in signed64 and floor-divide by `2^14`; retain reduced tick and wrap-parity branch. Nonzero wrap first replaces lineage by `mix(lineage XOR u32(wraps) XOR aux)`. |
| 6 SDF0 | Set residual zero, ZERO status and branch one. |
| 7 CONE | For normalized rho/theta, take `max(arg0-rho, rho-arg1, abs(cyclic_delta(theta,arg2))-abs(arg3))` in signed64. Wrap residual to one word, then classify its signed interpretation `<=0` into branch and CONE status. |
| 8 SPHERE | For normalized rho/phase, start `abs(rho-arg0)-abs(arg1)`; if arg3 is nonnegative, take the maximum with `abs(cyclic_delta(phase,arg2))-abs(arg3)`. Wrap first, then classify signed residual `<=0` into branch and SPHERE status. |
| 9 KLEIN | Floor-divide signed rho by `2^20`, retain reduced rho and wrap parity. For odd wraps, flag bit0 selects theta half-turn versus half-turn reflection; negate phase modulo its period, toggle orientation and optionally sheet bit0 (flag bit1), and set WRAP. Even wraps clear WRAP. Branch receives parity. |
| 10 RADIX | Branch receives the declared bit of the old key. Signed arg0 outside `[0,63]` faults without a state commit. |
| 11 HINGE | Only when `raw_branch & 1`, add all four coordinate arguments modulo `2^32`; flags bits0/1 toggle orientation/sheet respectively. |
| 12 LSYS | Clamp signed arg1 to `[0,30]`. Turn phase by arg0 times orientation sign (odd is negative) times branch sign (odd is positive), using signed64 and phase reduction. Divide each signed velocity by `2^shift`, truncating toward zero. |
| 13 PROJECT | Copy payload to output. |
| 14 EMIT | Copy payload to output, set EMIT, optionally set HALT with flag bit0. |
| 15 HALT | Set HALT. |

The signed cyclic delta is the normalized difference, with values at or above half-period shifted down by one period. Wide intermediates preserve `abs(INT_MIN)`, signed extreme coordinate differences, and addition before phase/tick reduction. This profile uses no floating-point arithmetic. The wide intermediate range fits signed64 for these fixed fields. Word wrapping is deliberate source behavior, not arithmetic drift.

Every successful body then normalizes theta/tick/phase, masks orientation and branch to one bit, and updates lineage using the **old** key and executed cell:

`lineage = mix(lineage_body XOR payload XOR aux XOR old_key_hi XOR rotl(old_key_lo,7) XOR final_branch XOR old_cell)`.

Rho and sheet are not globally normalized. If the resulting state lacks HALT, final branch selects next0/next1. With REKEY (flag bit31), a lower-bound search of the sorted table compares the new key: a hit takes that cell and clears REKEY_MISS; a miss sets REKEY_MISS and takes the selected successor. A resulting HALT state takes no successor but still receives normalization and lineage. An already halted lane executes nothing. Source OpenCL's whole-word HINGE truth test differs for raw branch2; this implementation deliberately follows the canonical C/Python low-bit rule.

PHI denotes a finite phase update, not algebraic multiplication by the golden ratio. CONE/SPHERE are source coordinate interval predicates with wrapped residuals, not general Euclidean signed-distance functions. SDF0 literally writes zero. KLEIN stores reduced coordinates and parity, not the signed full winding. HINGE applies a branch-level motion body; it does not by itself discover a continuous physical crossing or deduplicate an external event.

## Faults and actual execution receipts

Each lane has a separate sticky uint32 error: 0 none, 1 invalid cell, 2 invalid opcode, 3 invalid RADIX. Invalid opcodes are normally excluded at program admission; the error also makes the low-level device transition total. A refused transition leaves all sixteen state words unchanged. Later dispatches retain that fault until reset. Existing faults take precedence over the halted no-op. An initially halted state with no existing fault does not inspect its PC, even when it is out of range. Host input/resource/CUDA errors throw and are separate from these per-lane errors.

Every dispatch rewrites a 40-byte receipt per lane: uint64 epoch followed by uint32 `(executed,emitted,cell_before,opcode,flags,payload,branch_after,error)`. Executed means the canonical body and postlude committed. Emitted is true exactly for such an executed opcode14, including EMIT-HALT. Prior sticky status EMIT and stale output do not count. Halted/faulted slots have executed=emitted=0. Receipt opcode/flags/payload are meaningful as an attempted instruction only if a cell was fetched; otherwise their initialized values are zero. The error and execution fields must gate use. The last successful branch, or unchanged raw branch on refusal/no-op, is recorded explicitly.

`run_steps(ticks, texture, capture)` performs the requested number of dispatches; halted and faulted lanes remain unchanged. This preserves final-state stopping semantics while giving a rectangular optional trace of `ticks * state_count` receipts in dispatch-major, lane-major order. `read_receipts()` gives only the latest dispatch. `read_trace()` gives the latest captured run; a noncapturing run clears it. Trace allocation and byte arithmetic are checked before dispatch. Receipt identity is `(state_generation,epoch,lane)` within a VM owner; coupling consumes a successful emission at most once. The pure VM does not interpret this identity as a physical event.

## Bit planes, texture banks, and synchronization

For each at-most-32-word group, plane b contains bit b of each source word j at bit position j:

`plane[b] = sum_j (((word[j] >> b) & 1) << j)`.

The CUDA inverse is `word[j] = sum_b (((plane[b] >> j) & 1) << b)`. This permutation preserves every opcode, sign, operand and state-header bit. Padding only fills missing terminal lanes with zero; no padded word becomes part of the admitted program. It is lossless bit-plane transport, not compression or a change of numeric domain, and makes no XOPSEED1 parser-compatibility claim.

The constructor transposes host words in bounded scratch chunks, uploads the planes to a raw integer texture, and executes the actual CUDA inverse into separate header/cell allocations. It synchronizes before reusing scratch or binding decoded evaluator textures. Packed scratch is released after construction. The header and cell records remain immutable and resident. `read_program_words()` executes device texture reads of all decoded header and cell words and copies their result back; it does not return a saved host input. Readback therefore checks the upload/expansion/texture path directly.

Each Cell48 bank has a power-of-two capacity, limited by the actual device's `maxTexture1DLinear`, signed texture-index range, and a 256 MiB per-bank byte cap. An optional lower constructor cap supports deployment and boundary testing. The last bank can be shorter. A cell consumes three raw `uint4` texels with integer indexing and `cudaReadModeElementType`; no filtering, coordinate normalization, or floating conversion is applied. A separate template variant reads the identical allocation through global uint4 loads. Bank division/modulo uses the declared shift/mask. REKEY searches the same global sorted cell order across banks.

State64, errors, and receipts are separate mutable global arrays. Each launch assigns one thread to each lane; its complete old snapshot is local until a single canonical state commit. Program texture reads never alias mutable state. `resident_bytes()` reports owned decoded header/cell, bank descriptor, state, error, receipt and optional trace bytes; CUDA driver bookkeeping, host vectors and temporary construction scratch are excluded. This API does not claim cache residency, cache hits, bandwidth improvement, or free-memory saturation. Device allocation failures are explicit; a caller performing a capacity benchmark must impose its own desktop-memory reserve.

`enqueue_step` enqueues without readback or synchronization and advances the owner's host epoch after a successful launch. The same lanes must use one ordered CUDA stream, or the caller must supply explicit cross-stream event dependencies. Distinct streams are not automatically chained. Concurrent access to one owner is unsupported. `run_steps` uses an ordered default stream; readback and explicit synchronize complete device work. Reset synchronizes old work, allocates and initializes new arrays, synchronizes their readiness, then publishes them atomically at the host metadata boundary. Destruction completes pending consumers before destroying resources.

`device_view()` lends POD pointers, bank metadata, seed, epoch and generation for native coupling. `set_states` invalidates borrowed lane pointers even if CUDA reuses addresses; its checked monotonically increasing generation makes that detectable. The initial constructor reset gives generation1. Callers retain the VM and serialize all use. The low-level `launch_step(view,...)` deliberately does not update owner epoch, and direct pointer writes bypass owner accounting; these hooks are explicit responsibility boundaries, not protected high-level calls. Root's coupling uses the owner-managed enqueue path, captures generation plus expected epoch, and orders injection, canonical transition, and receipt commit without per-step host state readback.

## Validation boundary

`tests/tomagi_vm_tests.cpp` compares both texture and global CUDA variants against the separately compiled, unmodified C oracle. Every successful/refused transition compares all sixteen words and explicit receipt/error behavior. Fixtures cover all sixteen opcodes, raw branch2, signed extrema, negative division and wraps, aliased target fields, invalid RADIX/PC, wrapped residual classification, multi-bank addressing, REKEY hit/miss, actual versus sticky EMIT, final EMIT-HALT, generation resets, malformed input, and exact texture word readback. The trace retains no false emissions for post-halt slots.

These are meaningful prepared checks, not an exhaustive proof over all programs or a performance claim. Actual build/test outcomes and independent Python-fixture results belong to the release evidence and must be reported only after execution. The source equivalence argument concerns this admitted finite word machine; it supplies no independent physical calibration, continuous-event completeness, learner search, or superiority to a spherical spatial index.
