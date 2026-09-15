# R17 fused finite-word execution

This profile changes the dispatch and observation boundary of the R16 native TOMAGI word machine and its explicit ASA/NA+JK feedback binding. It retains the immutable Cell48 program, State64 field interpretations, every canonical opcode/postlude operation, zero-based dispatch receipts, and the original unfused execution modes. It adds no floating-point approximation, new physical law, or new source-language operator.

The source authority remains the imported C/Python TOMAGI transition pinned under `vendor/wqk_0_6/` and the R16 integration/feedback contract. R17's fused implementation must be equivalent to the ordered reference launches under the hypotheses below. Tests and timings are recorded separately; this mathematical contract does not invent execution evidence or promise that a compiler keeps every local value in registers.

## 1. Complete per-lane state and ordered composition

For lane `i`, let

\[
z_i=(s_i,f_i,r_i,w_i,k),
\]

where `s_i` is the complete sixteen-word State64, `f_i` its sticky VM fault word, `r_i` the most recent complete receipt, `w_i` the optional complete eight-word feedback state, and `k` the next dispatch epoch. The program, its seed, bank metadata, word profile, and injection binding are immutable inputs, denoted collectively by `P`. Distinct state lanes do not alias.

The coupled transition is the written composition

\[
C_k=\operatorname{commit}_k\circ\operatorname{VM}_k
                 \circ\operatorname{inject}_k.
\]

The extended transition `C` includes `k -> k+1`. The subscript is not an extra algebraic operation: it makes the receipt identity and next-epoch convention explicit. For pure VM execution, replace injection and word commit with identity operations and retain the canonical VM transition and receipt publication.

1. **Inject:** when enabled and the lane is eligible, copy the old feedback word's low 32 bits to raw `rho` and its high 32 bits to raw `vrho`. Already halted, VM-faulted, or feedback-faulted lanes follow the existing injection hold rule. Other State64 fields remain as in the reference profile.
2. **VM:** execute one canonical instruction, or its existing halted/faulted no-execution result, with dispatch receipt epoch `k`. The key is computed from the injected pre-instruction state. The body and mandatory postlude retain all source dependencies, wrapping, floor/truncation rules, and old-key/old-cell lineage inputs. A refused instruction leaves the State64 presented to the VM unchanged; it does not undo an earlier authorized injection.
3. **Commit:** consume that actual receipt under the existing fresh-EMIT and duplicate rules. A successful EMIT payload is zero-extended to drive the two declared whole-word ASA/NA stages and the declared JK bodies, all reading one old feedback word. Accepted emission updates the word, event parity, count, and last accepted epoch once. A repeated payload at another fresh epoch remains a new event. VM faults, feedback faults, count overflow, duplicate receipts, PROJECT, sticky EMIT status, and non-EMIT instructions retain their existing distinct behavior.

The three stages cannot be commuted. In particular, the VM must read the old committed feedback word for that epoch, and the commit must read the receipt of the instruction just executed. Inlining a stage does not authorize replacing it with a different Boolean equation or moving the shared postlude.

## 2. Fused loop and equivalence proof

For a requested positive chunk length `n`, a fused thread loads its lane's complete resident state, evaluates the same ordered transition `n` times locally, and publishes the final state. Denote this operation by `F_n`; the ordered reference operation is

\[
C^{[n]}_k=C_{k+n-1}\circ\cdots\circ C_{k+1}\circ C_k.
\]

The contract is

\[
F_n(z_i;P)=C^{[n]}_k(z_i;P)
\]

for every admitted initial lane state and immutable input `P`, with equality of **all** State64 words, VM fault, complete final receipt, feedback words, and next epoch. If zero-length calls are admitted by an API, their meaning is identity: no dispatch, no new receipt, and no epoch change.

### Hypotheses

- The same canonical integer transition and feedback equations are used in both paths, including raw initial state, alias-sensitive instruction writes, source key ordering, signed/wrapping operations, and postlude.
- Program, bank descriptors, seed, word profile, and injection binding do not change during a chunk.
- One thread has exclusive ownership of each mutable lane; lanes do not alias and the transition has no inter-lane mutable dependency.
- No observer, external state editor, receipt consumer, callback, or intermediate sample requires visibility inside the chunk. Any such application boundary must end the chunk.
- Host dispatches sharing lane arrays are ordered on one CUDA stream or by explicit cross-stream dependencies. Host call order alone is insufficient for different streams.
- Epoch range, chunk count, lane count, array lengths, and resource sizes are admitted before dispatch. In particular `k+n` must fit the managed epoch counter. Allocation or launch failure is not treated as a successful mathematical transition.

**Proof.** At entry, both paths read the same complete lane state. Suppose the local fused state after `j` iterations equals the reference state after `j` ordered epochs. Their next injection therefore sees the same old word and eligibility. The canonical VM sees the same injected state and immutable program and computes the same instruction, fault result, postlude, and receipt at `k+j`. Commit sees the same old feedback state and fresh receipt, so computes the same word/fault/metadata result. The states agree after `j+1` iterations. Induction gives equality after `n` iterations. Final publication makes that common state observable. Because each lane reads only its own mutable state and common immutable program, the argument applies independently to every lane; no cross-lane synchronization is needed for this profile.

This proof does not cover a future opcode that reads another lane's mutable state, concurrent program mutation, an external per-epoch sensor input, or a required intermediate observer. Those would change the hypotheses and require explicit synchronization/observation boundaries.

## 3. Halt, faults, and the final receipt

Dispatch epoch is distinct from the number of successful instructions or accepted hinge events. A chunk beginning at epoch `k` and requesting `n>0` epochs leaves the managed next epoch at `k+n` and its final dispatch receipt at `k+n-1`, even when the lane halted or faulted earlier. It must not report the earlier halt's receipt as though it were the last requested epoch.

- If EMIT-HALT executes in the final requested iteration, its final receipt says executed/emitted and that emission is committed once.
- If EMIT-HALT executes earlier, later iterations produce the reference halted no-execution receipts. The final receipt says no fresh execution/emission, while the previously accumulated feedback count and state retain the emission.
- If HALT executes in the final iteration, its receipt still identifies a successful HALT instruction after normalization and lineage; there is no successor update.
- If a bad cell/opcode/RADIX transition is first refused in the final iteration, the final receipt preserves that refusal's actual available instruction metadata. If the sticky fault predates the final iteration, the final receipt is the reference faulted no-execution receipt, including its cleared/default fields and current dispatch epoch.
- Raw initially halted or faulted state is not normalized just to simplify a fused fast path. Held state words and the reference receipt initialization must remain exact.
- Existing word-state faults suppress or alter later stages only as the ordered reference specifies. A fused path cannot invent recovery, erase faults, or count held epochs as emissions.

An early-exit optimization is valid only if it constructs exactly the same final held state and receipt for the remaining requested epochs. Merely breaking the loop on HALT or fault generally leaves the wrong receipt epoch/metadata. The simple full local loop already establishes the reference behavior without this additional shortcut proof.

The final receipt authenticates only its represented dispatch. Cumulative accepted EMIT count comes from the feedback state when that profile is active. A final receipt alone does not count all prior pure-VM emissions. Recommitting a consumed final EMIT receipt remains a hold under the same last-epoch rule.

## 4. Chunk composition and observation boundaries

For admitted `a,b`, the local equivalence gives

\[
F_{a+b}(z;k)=F_b(F_a(z;k);k+a).
\]

Chunking a requested run into `n_1,...,n_m` with exact sum `N` therefore preserves the final result and total dispatch epoch. An ordered completed chunk publishes an allowed observation boundary. The reference per-step path publishes one after every canonical instruction/feedback phase; a fused chunk need not expose those intermediate states.

This is final-state and explicitly selected boundary equivalence, not a claim that all intermediate memory traces are identical. An application requiring an observation, mutable input, host decision, or other GPU consumer after each logical epoch must use chunk length one or a properly ordered finer-grained boundary. Final-state digests compare final serialized state; they do not prove intermediate equality by themselves. Per-step or chunk-partition comparisons and the transition proof supply different evidence.

An implementation may bound chunk length to keep dispatch duration practical. That bound is an execution/resource choice, not a new arithmetic cutoff or a permission to skip internal hinge events. Every logical epoch still executes the specified recurrence, and every eligible internal EMIT still reaches commit.

The R17 native API selects the following bounds. `VM::enqueue_batch(ticks, texture, stream)` accepts `ticks` in `[0,256]`; zero holds without changing epoch/receipt, and a value above 256 rejects before mutation. `WordFeedback::run_steps_fused(count, texture, chunk_steps)` uses `chunk_steps` in `[1,256]`, default 32, and partitions an arbitrary `uint32` total count into admitted chunks. It validates the chunk argument even when count is zero. Zero count holds state, receipt, and epoch, while resetting the timing record. The complete epoch range is checked before work is enqueued; the managed epoch advances only after a successful enqueue. Asynchronous device/runtime failure is reported as failure, not accepted final-state equivalence.

## 5. Exact LSYS rate division by shifts

The shared native transition lowers only LSYS's four signed rate divisions here. The source operation is division by `2^s`, truncated toward zero, with `s = clamp(arg1,0,30)`. This is distinct from PHI/TIME's mathematical floor division and from LSYS's phase update.

Let `w` be an arbitrary raw 32-bit rate word, `x = signed32(w)`, and `b = w >> 31`. All arithmetic below on raw words is unsigned modulo `2^32`. Define

\[
m=\begin{cases}w&b=0,\\(-w)\bmod2^{32}&b=1,\end{cases}
\qquad d=m\mathbin{\gg}s,
\qquad w'=\begin{cases}d&b=0,\\(-d)\bmod2^{32}&b=1.\end{cases}
\]

As an unsigned integer, `m` equals `|x|` in `[0,2^31]`, including `x = -2^31`. Logical right shift gives `d = floor(|x|/2^s)`. Restoring the sign therefore gives exactly

\[
w'=\operatorname{raw32}\!\left(\operatorname{trunc}(x/2^s)\right).
\]

The construction never performs overflowing signed negation, a negative signed shift, or floating arithmetic. Shift zero preserves every raw word, including `0x80000000`; shift 30 is also admitted. A direct arithmetic right shift of a negative signed value would generally round toward minus infinity and is not this operation.

`cuda/tomagi_transition.cuh::trunc_shift_word` implements this identity for both reference and fused execution. Replacing the rate subexpression by an equal function preserves the transition and the induction above. Source-level equivalence does not by itself establish a particular compiled instruction sequence or speedup; the initial helper and machine-code reports are preserved separately for matched comparison. Other proposed phase/seam lowerings are documented in `review/R17_ORIGINAL_RETURN.md` and are not asserted to be implemented by this change.

## 6. Texture and local-state contract

The texture variant continues to fetch immutable integer Cell48 records through the native raw element texture path, including any key search required by the canonical instruction. Its global-memory counterpart reads the same immutable records. No filtering, floating interpolation, geometric rasterization, or renormalization is introduced.

The mutable lane state is held as local program variables through a chunk and published at its end. This reduces required global state publication boundaries; it is not a guarantee that every variable occupies a physical register. Register allocation, local-memory spills, cache behavior, occupancy, and instruction scheduling depend on the compiled kernel and device and must be measured. Program textures do not guarantee cache hits or speedup.

For `N>0` requested coupled epochs, the reference uses `2N` kernel launches without injection or `3N` with injection; fixed positive chunk size `c` gives `ceil(N/c)` fused launches. Pure VM changes from `N` launches to `ceil(N/c)` when the caller applies that chunk partition. These counts exclude setup, trace collection, other observation work, and final readback. They count launches rather than integer operations or accepted emissions, and by themselves do not establish a speed ratio.

Fused and reference modes remain separately selectable so identical seeds, initial lane words, profiles, epoch counts, and fetch choices can be compared. Timings must distinguish setup, upload, batch device interval, host dispatch/completion, final readback, and host digest/output costs. A speed ratio is meaningful only for declared matched work and output boundaries; it must not silently compare per-step trace collection with an unobserved fused batch.

## 7. Scope

R17 fuses the already bounded finite-word VM and explicit word-feedback profile. It does not make a source phase opcode into golden-ratio algebra, remove finite overflow contracts, lower all XOP expressions, move the exact rational affine event solver to the GPU, add cross-lane world synchronization, or validate a physical accuracy claim. The retained R16 source provenance, exact affine event specialization, and inherited physics contracts remain in force for their own domains.
