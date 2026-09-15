# Original WQK seeded compilation and the R17 runtime boundary

Audit date: 2026-09-15. This is a read-only source audit, followed by writing this report. No original files were changed; no original compiler, formal evaluator, native executable, benchmark or GPU workload was run for this audit. Counts from existing source artifacts below are observations of their stored records, not newly reproduced results.

The inspected original root is:

`C:/TOM/TOM_World_Query_Kernel_0_6_0_Tom_Klootwijk/TOM_World_Query_Kernel_0_6_0_Tom_Klootwijk`

All original source paths and line numbers below are relative to that exact root. The original `AGENTS.md` was read as source context: it describes the intended causal chain and explicitly requires definitions to be executable compilation inputs. It does not independently authorize modifications to that external repository.

## Finding

The original implementation has an actual validated seeded-definition pipeline. R17 has a tested native executor for the resulting Cell48 ABI, but its delivered fixture exercises the legacy literal-cell compiler rather than the complete seeded source chain. A second concrete gap matters for the original use case: the fused R17 path preserves final state, final receipt and coupled word state; it does not preserve every intermediate EMIT payload needed to materialize an artifact.

The strongest bounded next integration is therefore **original seeded fixture compilation plus a capacity-checked, lossless ordered GPU EMIT journal**. That would join the original source-to-artifact contract to the fused native engine without pretending that a precomputed formal result was evaluated on the GPU.

## Actual seed-to-Cell48 path

| Stage | Actual source and behavior |
|---|---|
| Canonical root | `src/python/tomagi/compiler.py:617` requires exactly the 244-byte ASCII seed, its fixed SHA-256, and no final CR/LF. `:326` also checks the declared length/hash/grammar fields. |
| Token binding | `compiler.py:345` verifies the exact canonical registry, lexical token membership and registry identity. `:632` returns the seed record consisting of grammar ID, byte count, hash and text. `seed.tokens` is not a parser that expands every named mathematical operation into executable bodies. |
| Definition admission | `compiler.py:829` validates declared fields, kinds, domains/codomains, parameters, provenance, token use, content hashes and effective limits. The definition bodies and their dependencies are real compilation inputs. |
| Order and selection | `compiler.py:994` checks identities, phase/order slots, dependencies, cycles and rank ordering. `:1056` computes the selected root's dependency closure. `:1204` evaluates that closure in the admitted order. Unselected definitions are still admitted structurally but their operations are not evaluated. |
| Literal external input | `compiler.py:1227` handles `source.json`: directly bound canonical seed record, source-root confinement, exact byte count/SHA, strict UTF-8/JSON and optional canonical-content address checks. This supplies the actual formal program and input records. |
| Formal evaluation | `compiler.py:1310` constructs limits and calls Python `run_formal_program(program, inputs, limits=...)`. `src/python/tomagi/formal.py:896` verifies the program and evaluates its expression at `:929`. The result contains program hash, input hash, evaluation-step count and computed value. |
| Result encoding | `compiler.py:1331` canonical-encodes that returned record, with an explicitly selected terminal LF. |
| Cell graph construction | `compiler.py:1408` splits already available bytes into chunks of 1–4 bytes. At `:1493`, each produced cell is explicitly `Opcode.EMIT`; the final cell may include EMIT-HALT. Payload byte order/count, keys, successors and per-cell origins are recorded. |
| ABI lowering | `compiler.py:1138` sorts graph cells by their canonical keys, resolves successor IDs, validates entry/keys and constructs ordinary Cell48 fields plus a definition-to-cell crosswalk. |
| File entry point | `compiler.py:1604` loads the seed and registry, evaluates the seeded source, writes `.tmg`, and writes a compile sidecar containing selected definitions, source receipts and the cell crosswalk. `:1585` separately preserves the legacy literal-cell path. |

The normative source `spec/TOM_SEEDED_COMPILATION_1_0.md:19` lists the complete chain through authenticated EMIT records and byte materialization. Its seed grammar begins at `:35`, definition order at `:117`, and seeded operations at `:151`.

The original seed is a fixed identity and lexical anchor within this profile. The meaningful equations, datasets, dependency graph and artifact bytes live in explicitly supplied definitions and literal source records. This is a stronger and more concrete statement than saying the short seed string alone determines all domain behavior without those bodies.

## What executes where

`formal.py:30` declares a useful finite, JSON-native language: exact rational arithmetic, records/lists, named bindings, lazy conditionals and assertions, hashing, and bounded `map`, `filter`, `sort`, `group` and `fold`. Its strict expression admission is at `:287`; the formal program is an expression tree with finite input collections and host-supplied budgets, not an unrestricted recursion or loop system.

Those operations currently execute in Python during seeded compilation. In the admitted seeded compiler, `emit.graph` is the only operation producing `cell_graph`; `literal` admits bytes, strings, Booleans, i32/u32 or records, not an executable arbitrary graph. Consequently the formal expression tree is not lowered into a native instruction sequence that recomputes the formal result for new runtime input. The tree is evaluated first, and its resulting bytes are lowered into EMIT cells.

This distinction is directly visible in the stored original `examples/learner06/learner06_family_authority.tmg.compile.json`:

- 32 evaluated definitions and 21 resolved literal source records.
- 32,880 cells; every crosswalk opcode is `EMIT`.
- Stored program length 1,578,368 bytes, which equals `128 + 48 * 32880`.

These are observations of that preserved report, not a new compilation or execution. They are consistent with the source code's evaluation-then-emission path. Executing this program natively demonstrates ordered materialization of the formal result. It does not demonstrate native evaluation of the original 910,171-byte family-authority expression tree, native candidate search, or a GPU implementation of its rational/list operations.

R17's current native transition engine can run all sixteen finite TOMAGI operations, and the fused correctness suite compares its actual state/receipt/feedback words against the original C transition and an independent scalar word oracle. That is a substantial separate capability. The currently delivered fixture builder `tools/build_wqk_fixtures.py:43` uses `compile_document(document)` on literal cells; its evidence explicitly states `seeded_formal_profile_claimed: False` at `:76`. It does not yet reproduce the full original seeded fixture boundary described above.

## Why the final receipt cannot recover the original artifact

Original `src/python/tomagi/materialize.py:56` decodes the EMIT count from flags and accepts 1–4 payload bytes in the selected byte order. At `:67`, it authenticates an ordered canonical-initial-state trace by deterministic replay, including every required trace field. At `:100`, it materializes only actually executed EMIT cells, in that validated order. A final sticky EMIT status bit is not an event record.

R17 `include/atomos/tomagi_vm.hpp:64` explicitly defines the fused batch as retaining only the final receipt, with no intermediate observer. `tools/wqk_run.cpp:39` likewise declares final readback without a per-step trace, and `:42` states that pure-VM cumulative emission count is unavailable. The coupled word path commits every fresh emitted drive internally, but its final `q`, parity, last drive and hinge count are not a lossless encoding of the preceding emitted payload sequence. Different sequences can reach those same final fields.

An illustrative program `EMIT(A) -> EMIT(B) -> HALT` retains a non-emitting final receipt after the third transition. No final-only output can reconstruct both `A` and `B` without replaying the program or having separately retained the intervening records. Thus final-state and final-receipt equivalence establish the declared R17 fused observation boundary; they do not establish an authenticated full output stream.

The existing reference `VM::run_steps(..., capture_receipts=true)` can retain a rectangular receipt trace, but this is separate from the fused output contract. A Receipt40 also is not identical to the source materializer's full `TRACE_FIELDS` schema: a new compact native journal must have its own explicit format and validation, or be supplemented with the fields needed by that existing schema. It must not be passed off as the original trace unchanged.

## Bounded next integration design

### 1. Reproduce the original seeded fixture before claiming coverage

Use an unchanged copied source fixture with its canonical seed, exact registry, selected literal definitions and all referenced source JSON files. Invoke the original seeded compiler entry point with its explicit source root. Retain source hashes, full selected-definition order, resolved-source records, program bytes and crosswalk. Compare complete `.tmg` bytes to the preserved source artifact and independently decode/re-encode the ABI.

Start with a small source fixture, then include a real `formal.evaluate` fixture such as the original learner-authority artifact. Compare its direct formal result, canonical encoding, original reference execution's materialized bytes, and native execution's materialized bytes. A compile-only result is not counted as native output verification. Retain the distinction between Python precomputation and native execution in the report.

### 2. Add an explicit journal mode to the fused engine

Keep the existing final-only mode and its measured costs unchanged. Add a separate, versioned output mode whose admitted observable is the complete fresh EMIT stream for each lane and source generation.

A simple bounded construction uses a preallocated worst-case journal for `lanes * chunk_steps` records, with checked 64-bit size arithmetic before launch. Since one canonical transition emits at most once, this is a finite capacity proof for a chunk of at most 256 steps. Each lane writes only its own segment in logical epoch order, retains its actual event count, and records enough immutable information to bind at least source generation/program identity, lane, epoch, pre-cell, flags, payload and post-lineage. The program/source identity can be stored once in the journal header rather than duplicated per record. Actual EMIT-and-HALT is recorded once; later halted or faulted slots append no event. Repeated equal payloads at distinct accepted epochs remain distinct records.

After the chunk, a stable count/prefix compaction may concatenate only actual entries while preserving the specified order. For multiple lanes, declare lane-separated streams or a deterministic order such as `(epoch,lane)`; GPU scheduling order is not an output order. Runtime source mutation or reset invalidates the previous generation, and a journal cannot silently combine unrelated epochs.

Capacity/allocation failure must occur before the corresponding execution chunk or return an explicit incomplete outcome with its exact committed prefix. A truncated stream is never reported as complete. The simplest first version reserves the proven maximum before launching and therefore needs no per-event atomics, append overflow or rollback logic. Chunk boundaries may drain/persist the completed journal or append into a separately checked larger allocation; no per-step host readback is required.

This extra output is measurable work. Report event count, journal bytes, allocation/compaction/transfer costs and device time separately from the existing final-only benchmarks. A journal-enabled speed comparison must compare equal observable outputs.

### 3. Validate contents, ordering and continuation independently

Compare every actual emitted record and every output byte against the unchanged original C/Python execution, not only their hashes. Small cases should also compare complete per-transition states to establish event metadata and lineage binding. Exercise 1/2/3/4-byte payloads in both endian modes; NOPs between EMITs; same payload repeated at distinct epochs; EMIT-HALT; halted/faulted final slots; no-emission programs; multiple lanes; chunk sizes 1/7/32/256; partial final chunks; reset/generation separation; and exact capacity refusal before mutation.

Rebuild the seeded fixture twice and compare complete bytes and definition crosswalks. Deliberately change a source byte without updating its receipt, omit a dependency, alter a definition hash, and submit a truncated/reordered/duplicated journal; each must fail at its correct boundary. Hashes identify the supplied objects; replay and per-byte comparison establish the tested semantic relationship.

The source materializer currently accepts canonical-initial-state trace prefixes and can materialize a prefix. The new tool must explicitly distinguish a valid prefix from a completed artifact, for example by requiring the expected source terminal state and full reference event sequence when asserting complete artifact reproduction.

## Capabilities still absent after that bounded integration

Even a successful native EMIT journal would not execute the formal expression tree on the GPU. Runtime parameterized `formal.py` arithmetic, collections, assertions and candidate evaluation would require a separately specified compiler/runtime subset with exact operand/storage bounds and an independent oracle. It would also not connect all original event/learner/immutable-store interfaces automatically to R17's resident word state.

Those are worthwhile subsequent tasks. The journal and original seeded fixture verification are the shortest concrete step that completes an existing original source-facing capability, preserves the exact core, and avoids substituting a final-state digest for an artifact stream.

## Inspected original file receipts

These SHA-256 values identify the original bytes read or inspected as source/manifest metadata in this audit. The large formal artifact was identified through its source binding and hash; the audit does not claim a complete line-by-line mathematical proof of its expression tree. The compile artifact was parsed for its metadata, definition list, source list and opcode crosswalk; it was not regenerated.

| Original relative path | SHA-256 of file bytes |
|---|---|
| `AGENTS.md` | `147aa3b9fdc5d3489a4e51d69456195ed43f405d8e7233ae1cdeaa1e3abcaa5b` |
| `TOM_seed_genome_2026-09-01.txt` | `d1417a3136772c0cf3eddcd4962ce07d42cbf87616f7b5bae09fc652d9b807b5` |
| `spec/tom_seed_token_registry_1_0.json` | `5caa96342c280e7e8ae9f18ae8ddfbd0e3ce149059effabca001ad5eeb908d21` |
| `spec/TOM_SEEDED_COMPILATION_1_0.md` | `8c88fd93f04ff5ba085bd32e1a5c42274d93ba6feb1687cf0db9927aa02aa28a` |
| `src/python/tomagi/compiler.py` | `2e1f1b5f1e3f348a1e9ae3561062390a000b5f74120a5e238313676b0e32b368` |
| `src/python/tomagi/formal.py` | `ca472619fcb3e2d34c5ccaac8081bb3f60896cfd2f0c60297a4de2ad9872237e` |
| `src/python/tomagi/materialize.py` | `41689d2a01a303327fd60df66a243136e3385f3ba0418a7020e1d53e42bb64c0` |
| `src/python/tomagi/core.py` | `58c64eaa07e583c619b0c51aba61d7630561e94f911b82e49f99dde0f970f3a9` |
| `src/c/tomagi.c` | `c88242ea069a78ca8fc52531f47182c8399fe6962152c58998a6a5731147a22d` |
| `tests/test_seeded_compilation.py` | `93be898675130304abb3e83dac4f9a458ae0478c2948d76f9037fe4591e5728e` |
| `examples/learner06/learner06_family_authority.literal.json` | `442fbaeea1e50d6da15b1479bb60a07971aeec1c25303c4be96a5ef3a7147389` |
| `examples/learner06/learner06_family_authority.formal.json` | `32ef3fa896bc8fb6493c8fc55fb33052910b8e59c11baba8e923084d6918391e` |
| `examples/learner06/learner06_family_authority.tmg.compile.json` | `b6d9c72bbed5ae18ba07dce4645bba8449c2d599f038c9da768afc1192f39d6f` |

The token registry's file SHA above is distinct from its embedded canonical content address `sha256:d330f7cc3ba5bff2f2e0eb05e32847c295b69e328ed0852fd612b716819044bb`. Both identities are used by the source contract for their different byte/content meanings.
