# R18 complete native seeded EMIT journals

Profile: `ATOMOS-EMIT-JOURNAL-R1`. Source authority is the unchanged, pinned WQK 0.6 canonical transition, seeded compiler and byte materializer. Implementation: `include/atomos/tomagi_journal.hpp`, `cuda/tomagi_journal.{cuh,cu}`, journal entry points in the VM/feedback implementation and `tools/wqk_materialize.cpp`.

R17 preserves final state and the last requested dispatch receipt. R18 adds an optional complete stream of fresh VM emissions inside fused chunks. The final-only paths remain separate. This compact observation schema is distinct from the vendor's full `TRACE_FIELDS` instruction trace.

## 1. Transition and event

Let `P` be the immutable canonical program and `z_i(k)` the complete VM state, error, receipt and optional ASA/NA/JK feedback state of lane `i` at next dispatch epoch `k`. Retain

\[
z_i(k+1)=C_k(z_i(k);P),\qquad
C_k=\operatorname{commit}_k\circ\operatorname{VM}_k\circ\operatorname{inject}_k.
\]

Injection and word commit are identities for pure execution. `C_k` retains every existing hold, refusal, lineage, successor and fresh-receipt meaning. After it, append an event if and only if that epoch's actual VM receipt has both `executed != 0` and `emitted != 0`. A sticky EMIT state flag alone supplies no event. EMIT-HALT supplies one, even when later requested epochs hold the halted state. Equal payloads at distinct epochs remain distinct events.

The 40-byte native event contains one uint64 epoch and eight uint32 fields:

| Field | Exact source |
| --- | --- |
| `epoch` | Actual dispatch receipt epoch |
| `lane` | Owning lane index |
| `cell_before` | Actual receipt's pre-instruction cell |
| `flags`, `payload` | Actual receipt's flags and emitted payload |
| `lineage` | Post-transition State64 word 12 |
| `cell_after` | Post-transition State64 word 11 |
| `branch_after` | Actual receipt's post-transition branch |
| `status_after` | Post-transition State64 word 15 |

A fresh VM emission and successful word-feedback commit are different observables. Final feedback status records a refused commit. The journal records a fresh VM emission even if its flags have no valid byte count; the decoder separately admits counts 1 through 4.

## 2. Ordering, capacity and terminal status

For chunk `[k,k+n)` define the lane's sequence

\[
J_i[k,k+n)=\mathop{\Vert}_{j=0}^{n-1}
\begin{cases}[E_i(k+j)]&\text{fresh VM emission},\\[]&\text{otherwise}.\end{cases}
\]

Here `||` denotes ordered concatenation. At most one emission per canonical transition implies `|J_i| <= n`. For `L` lanes the proven bound is `L*n`. The GPU assigns lane `i` the disjoint interval `[i*n,(i+1)*n)` and writes events in increasing epoch order. GPU scheduling and global atomic append order do not define output order. Host compaction publishes lane-major storage with `lane_offsets` identifying each lane's strictly increasing epoch subsequence.

`VM::run_journal_chunk` and `WordFeedback::run_journal_chunk` admit `0 <= n <= 256`, `L >= 1`, a non-overflowing uint64 epoch interval and representable allocation sizes. `max_events=0` selects the automatic proven bound; a nonzero value below `L*n` refuses before transition or injection. A larger value does not enlarge allocation beyond `L*n`. Zero work observes an unchanged boundary without dispatch, new receipt, event or epoch advance.

Worst-case event storage is `40*L*n` bytes on both GPU and host, plus counters, overflow indicators and initial/final boundary arrays of size `O(L)`. Coupled execution also captures initial/final feedback words. The immutable canonical source is retained separately. GPU and host event/boundary allocations complete before corresponding mutable execution. Runtime failure is not a successful completed journal, and no rollback is promised after that failure.

At the synchronous drain, check capacity/overflow, lane, epoch bounds and per-lane ordering, then capture every final State64, VM error and final receipt, with applicable feedback words. Status is `Faulted` if any final VM error or feedback status is nonzero; otherwise `Complete` if all final lanes have the HALT bit; otherwise `Prefix`. A complete library journal may contain no emissions. The artifact CLI separately requires at least one EMIT.

All requested epochs still run after an early HALT or fault, preserving the canonical final held receipt. Dispatch epoch, executed instruction count, VM emission count and accepted word-feedback count remain distinct.

## 3. Composition, source and ownership

For contiguous unchanged execution,

\[
J_i[k,k+a+b)=J_i[k,k+a)\Vert J_i[k+a,k+a+b).
\]

The retained R17 state-composition induction extends directly: equal pre-states give the same next complete transition, fresh-emission predicate and event fields, hence the same appended prefix and post-state. Disjoint output intervals prevent inter-lane interference. Any admitted chunk partition preserves each lane's sequence. For multiple lanes concatenate corresponding lane subsequences; simply appending whole lane-major chunks would produce a different global lane order.

Every chunk holds a shared immutable `JournalSource`: a process-unique owner ID and the complete canonical `.tmg` bytes read back from actual GPU-expanded program words. The source survives VM destruction. Moving a VM preserves the source/owner; resetting state changes generation. An owner ID is not a content hash or a cryptographic credential.

`require_journal_continuation(previous,next)` requires:

1. The same source object and owner ID, generation and lane count.
2. `previous.end_epoch == next.start_epoch`.
3. The same execution mode, feedback binding and complete word profile.
4. Exact previous-final/next-initial equality for State64 arrays, VM errors and applicable feedback arrays.

Exclusive VM/lane ownership is required during the synchronous call; no concurrent same-lane work may run on another stream. The feedback wrapper also enforces its existing borrower epoch/generation contract. External advance/reset invalidates that borrower even before a zero-work call. Ordinary non-journal execution creates a gap that cannot be silently stitched into a contiguous journal.

The continuation function checks these in-memory boundaries. It does not authenticate caller-edited event rows, establish source authorship, or reconstruct live source identity from serialized owner IDs. Persisted output verification uses pinned source bytes and deterministic external replay. Mathematical completeness and file provenance are separate claims.

## 4. Byte materialization and CLI

For flags `F` and payload `W`, count `c=(F>>8)&7` must satisfy `1 <= c <= 4`. With endian bit `b=(F>>11)&1`, byte ordinal `j`, `0 <= j < c`, is

\[
d_j=\begin{cases}j&b=0,\\c-1-j&b=1,\end{cases}\qquad
B_j=(W\gg8d_j)\mathbin{\&}255.
\]

Big endian reverses the selected low `c` bytes; it does not select the high `c` bytes. The artifact concatenates these decoded records in one lane's fresh-EMIT order.

`wqk_materialize` requires a canonical one-lane initial state and source bits 0 (seeded profile) and 1 (emitted bytes). Steps default to the source header horizon; explicit `--steps` is uint32, `--chunk` is 1 through 256. Reference/fused and texture/global modes preserve the same source and output semantics.

Before mutable execution, the CLI reserves the entire requested event vector and up to four artifact bytes per epoch, and verifies exact equality between the GPU-expanded source and the complete input. It joins chunks through the continuation checks, decodes every event, and writes the artifact only after fault-free terminal completion with at least one EMIT. Exit 0 means complete; exit 2 with prefix/fault report means no artifact write; admission/runtime/decoding/output failures return 1. Source, artifact and report paths must not alias. A prefix call does not delete a pre-existing output file.

The JSON adds sequence, byte count and byte order to all nine native event fields, for twelve compared fields, together with complete final State64 and run parameters. The external verifier requires literal true `artifact_written` and `expanded_source_bytes_equal_input`, lane zero, complete status, zero error, exact bounds, all event fields, all sixteen final state words and complete byte equality with fresh original replay. The booleans are report assertions, not independently authenticated credentials; exact deterministic replay and pinned files provide the substantive output check.

Host timings cover setup; journal allocation, execution, transfers, compaction and decoding; artifact write; and total through artifact persistence. JSON encoding/report output is excluded. These are not device-only timings or a matched performance comparison against another materializer.

## 5. Original source evidence and limits

The unchanged original seeded compiler reproduced both selected programs and complete sidecars twice, identically to stored originals. world03 emits 866 records and 3,461 bytes. learner06 family authority emits 32,880 records and 131,517 bytes; its original formal evaluator performed 352,593 host steps before encoding the result as EMIT cells. Native output verification compares respectively 10,392 and 394,560 event fields, every final State64 word and every artifact byte to fresh original Python replay. Exact source/program/report/output SHA-256 identifiers are in `review/r18_world03_verified.json` and `review/r18_family_authority_verified.json`.

The native journal suite independently uses the unchanged C transition and scalar per-bit ASA/NA/JK. It compares 1,030,950 event fields and 439,904 materialized bytes as part of 10,075,735 checks across both fetch paths, reference/fused modes and chunks 1/7/32/256. Both bounded-phase and signed-wide builds pass. All 59 Python tests pass, including ten seeded verifier/admission tests which separately reject altered source, event, state, completion and output evidence.

This establishes complete native execution and materialization of these host-compiled Cell48 graphs. It does not move `formal.evaluate`, dependency selection, formal expression search, arbitrary JSON evaluation or the host compiler onto the GPU. A journal adds output memory and transfer work; final-only R17 or phase timings cannot substitute for a complete-artifact benchmark. Exact finite words and lossless one-bit-plane packing retain their defined widths and do not establish exact continuous physical prediction.
