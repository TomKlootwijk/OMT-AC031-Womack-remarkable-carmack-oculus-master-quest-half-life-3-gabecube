# R16: source-pinned word execution and exact affine events

This profile integrates two useful, distinct mechanisms from Tom Klootwijk's TOM World Query Kernel 0.6 source: the finite TOMAGI 1.0 word-machine semantics, ported to the native CUDA engine, and an exact rational affine event model connected to the existing aTOMos plane-guard/ASA/JK core. It does not identify that finite machine with the full aTOMos exact-expression language or with a physical law.

The source package is `TOM_World_Query_Kernel_0_6_0_Tom_Klootwijk`, supplied by the user at the external path recorded in the release provenance manifest. The reference authorities are `src/c/tomagi.h`, `src/c/tomagi.c`, the Python TOMAGI implementation, `spec/TOMAGI_1_0_FORMAL_DEFINITION.md`, and the world-query event specification and implementation. File-content hashes in the release manifest pin the reviewed source. Source notices retain their attribution; no independent license grant or third-party authorship determination is inferred from them.

## 1. Three meanings of execution

1. **Native word execution:** the GPU loads the actual Cell48 operator words and executes one of the sixteen TOMAGI transitions against a resident State64. Its arithmetic and branches are the source finite-word arithmetic.
2. **Exact affine event discovery:** the host evaluates rational trajectory/plane equations, finds the complete earliest admissible simultaneous event set, and commits the corresponding aTOMos hinge transitions atomically. This is an exact CPU rational profile, not GPU analytic event discovery.
3. **Source formal precomputation:** the source compiler's `formal.evaluate` calls its Python formal evaluator and can lower the serialized answer into EMIT cells. Executing those cells proves materialization of those bytes; it does not move the preceding Python computation onto the GPU. This source route is not evidence of native GPU learner search or native symbolic event discovery.

The R15 golden-ratio algebra, retained winding representation, exact expression graph, physical models, and resident spatial predicates remain distinct profiles with their existing domains. The R16 additions connect through explicit typed state and event bindings.

## 2. Canonical finite-word machine

Let `u32(z)` mean the residue of the integer `z` modulo `2^32`, and let `s32(w)` interpret that residue as a two's-complement signed integer. Define

\[
\operatorname{mod}_m z=z-m\lfloor z/m\rfloor,\qquad
\operatorname{wrap}_{32}z=\operatorname{s32}(\operatorname{u32}(z)).
\]

Positive powers of two are exact moduli, not floating-point scale factors. Addition of raw unsigned state words implements modulo-`2^32` addition, including signed fields. Wide signed intermediates are used before explicit wrapping where the source requires them. A complete successful instruction includes its common postlude.

### 2.1 Source ABI and admission

The canonical stream is little endian: a 128-byte header followed by `N` 48-byte cells, exactly `128+48N` bytes. The magic is the eight bytes `TOMAGI1\0`; version is `0x00010000`; the header declares cell size 48 and state size 64; its six reserved words are zero. `N>0`, entry index is below `N`, cell opcodes are in `[0,15]`, both successors are below `N`, and cell keys are strictly increasing and unique under unsigned lexicographic `(key_hi,key_lo)` ordering.

`State64` is sixteen raw `uint32` words. Fields 0–7 are signed `(rho,theta,tick,phi,vrho,vtheta,vtick,vphi)`; 8–13 are unsigned `(orientation,sheet,branch,cell,lineage,output)`; 14 is signed `residual`; 15 is unsigned `status`. Cell48 is twelve words: `(key_hi,key_lo,opcode,flags,arg0,arg1,arg2,arg3,next0,next1,payload,aux)`, with signed interpretations for the four arguments.

The native constructor provides `header_state()` with all header state words intact and `entry_state()` with only `cell` replaced by the entry index. Its initial lane uses `entry_state()`. Explicit `set_states()` preserves every supplied word and clears sidecar faults, receipts, and dispatch epoch. It does not normalize phase or branch before the first instruction.

Periods are

\[
M_\rho=2^{20},\quad M_\theta=2^{18},\quad M_t=2^{14},\quad M_\phi=2^{12}.
\]

The pre-instruction packed key is

\[
K=(\operatorname{mod}_{M_\rho}\rho)2^{44}
 +(\operatorname{mod}_{M_\theta}\theta)2^{26}
 +(\operatorname{mod}_{M_t}t)2^{12}
 +\operatorname{mod}_{M_\phi}\phi.
\]

This is an exact finite bit-field address. It is neither a metric nor a claim that equal packed keys identify the same physical point in every application.

### 2.2 Instruction bodies and order

All assignments below retain the written source order; source aliasing is meaningful. In particular SET or JIT1 may select any state field, including branch, cell, lineage, or status. No optimizer may commute those writes across their dependent reads or across the common postlude.

| Opcode | Name | Exact body before common postlude |
|---:|---|---|
| 0 | NOP | No body mutation. |
| 1 | SET | Write `arg0` bits to field `flags & 15`. |
| 2 | JIT1 | Compute the source `mix32` parity from seed, pre-key, pre-tick, and aux; write branch; then add the signed perturbation to the selected field with word wrapping. A selected branch field can alter that earlier branch write. |
| 3 | KIN2 | For each of four coordinates, update its velocity by the corresponding argument, then update position by the updated velocity; both wrap as words. |
| 4 | PHI | Add `arg0` to the signed phase in a wide intermediate; Euclidean division by `2^12` supplies reduced phase and signed wrap count. Flags choose wrap-parity or half-phase branch and optional orientation flip. |
| 5 | TIME | Wide signed tick addition and Euclidean reduction by `2^14`; branch is wrap parity; nonzero wraps mix lineage before the common lineage update. |
| 6 | SDF0 | Set residual to zero, set ZERO status, set branch to one. |
| 7 | CONE | Evaluate the source radial/angular interval maximum, wrap the residual to signed 32 bits, then use the wrapped residual `<=0` for branch and CONE status. |
| 8 | SPHERE | Evaluate the source radial and optional cyclic-phase interval maximum, wrap the residual first, then use `<=0` for branch and SPHERE status. |
| 9 | KLEIN | Reduce signed rho by `2^20`; odd wrap parity applies the selected theta map, phase negation, orientation flip and optional sheet flip. Record only parity in branch. |
| 10 | RADIX | Select a bit of the pre-instruction 64-bit key. Signed shift outside `[0,63]` is a refused transition. |
| 11 | HINGE | Test `branch & 1`; on one, add the four coordinate arguments with wrapping and apply selected orientation/sheet flips. |
| 12 | LSYS | Apply the signed orientation/branch phase turn; divide rates by `2^clamp(arg1,0,30)` with signed truncation toward zero. |
| 13 | PROJECT | Copy payload into output; no fresh emission. |
| 14 | EMIT | Copy payload into output, set EMIT status, optionally HALT. |
| 15 | HALT | Set HALT status. |

For CONE and SPHERE, preservation of the wrapped source residual is a compatibility requirement. It does not certify the unwrapped geometry if an application chooses arguments whose residual overflows. Such a geometry interpretation requires a separately proven no-overflow domain.

The source PHI opcode is a **phase update**, not multiplication by the golden ratio. Its reduced phase is unrelated to the R15 pair `(a,b)` representing `a+b*golden_ratio`. SDF0 is a defined-zero operator, not a Euclidean signed-distance calculation. CONE/SPHERE are finite interval predicates in the source coordinates, not general physical solids or true signed-distance functions. The KLEIN opcode retains reduced coordinates and parity; it discards the full signed wrap count. Its 32-bit lineage hash cannot replace the R15 explicit winding integers or establish invertibility.

### 2.3 Common postlude and refusal

After a successful instruction, normalize `theta`, `tick`, and `phi` by their periods, and mask orientation and branch to one bit. Do not globally normalize rho or sheet. Update lineage using the source unsigned `mix32` function and the old instruction's key and cell index:

\[
L^+=\operatorname{mix32}\bigl(L_{\rm body}\mathbin\oplus payload
 \mathbin\oplus aux\mathbin\oplus K_{hi}^-
 \mathbin\oplus\operatorname{rotl}_{32}(K_{lo}^-,7)
 \mathbin\oplus b^+\mathbin\oplus i^-\bigr).
\]

Unless the resulting state is halted, use the normalized branch's successor. With REKEY enabled, first pack the new coordinate key and perform an exact lower-bound lookup in the sorted cell table; a matching key takes precedence and clears REKEY_MISS, while a miss sets that status and uses the branch successor. HALT and EMIT-HALT still run normalization and lineage, but do not take a successor. An already halted state executes nothing and creates no fresh emission.

The native profile has a separate sticky fault word for bad cell, opcode, or RADIX shift. A refused transition leaves State64 unchanged and records a non-executed error receipt. This explicit result is not a new mathematical operator or a fabricated successful transition. Admission/resource failures are reported separately from the canonical word semantics.

### 2.4 Known source-backend disagreement

The reviewed OpenCL HINGE tests the whole branch word for nonzero, whereas the canonical C/Python transition tests its low bit. A raw initial branch value of `2` therefore selects different bodies before common normalization. R16 follows the C/Python low-bit rule and preserves that regression case. The reviewed OpenCL file is source evidence, not an independent execution oracle for this discrepancy. Agreement on ordinary already-normalized branches does not resolve it.

## 3. Lossless storage, CUDA memory, and emission feedback

For a block of at most 32 canonical words `w_j`, encode plane words and decode by

\[
P_b=\sum_{j=0}^{31}((w_j\gg b)\mathbin\&1)2^j,\qquad
w_j=\sum_{b=0}^{31}((P_b\gg j)\mathbin\&1)2^b.
\]

Missing terminal lanes are zero padding and are not extra program words. Every source bit is preserved, including signs, opcodes, flags, and operands. The native constructor uploads these integer planes and reconstructs canonical header/cell words on the GPU. Decoded cells remain immutable and are read through banked `tex1Dfetch<uint4>` element reads (three 16-byte texels per Cell48), with a matching global-memory variant. Texture addressing is integral; there is no filtering, normalized-value conversion, or geometric raster approximation in this transport.

The decoded program is a derived VRAM representation of the immutable canonical input; State64, fault, and receipt arrays are mutable separate resources. Their sizes and texture indices must fit the device and the API's signed texture-index domain. A texture object enables the hardware texture path; it provides no guarantee of cache hits, permanent residency in a particular cache, or speedup. Whole-state host readback is unnecessary for a correctly ordered native coupling dispatch. Mutable lanes require one ordered CUDA stream or explicit cross-stream dependencies; sequential host calls alone do not order different streams.

A receipt names the dispatch epoch, whether an instruction actually executed, whether that instruction was EMIT, the executed cell/opcode/flags/payload, final branch, and error. Fresh emission eligibility is

\[
e_{k,i}=[\mathrm{executed}_{k,i}=1]\land
 [\mathrm{opcode}_{k,i}=14]\land[\mathrm{error}_{k,i}=0].
\]

The integration consumes an eligible identity `(epoch,lane)` at most once. A prior EMIT status bit or retained output payload is insufficient: PROJECT, NOP after EMIT, a halted lane, a duplicate receipt, or a failed transition must not generate a new hinge event. EMIT-HALT remains one valid fresh emission. Equal payloads at later fresh EMIT epochs are separate events.

The concrete `ATOMOS-TOMAGI-EMIT-FEEDBACK-R1` binding optionally copies all 64 old hinge bits before a canonical VM step: low 32 bits to raw `rho`, high 32 bits to raw `vrho`, skipping halted/faulted lanes. After the step, the fresh EMIT payload is zero-extended to form the drive word. The declared R15 WordProfile Boolean `x_lut` reads old `q` and drive; two whole-word mask stages produce `y`; the `j_lut` and `k_lut` bodies read the same old `q` and `y`; then JK commits the masked word and toggles event parity once. The next enabled pre-step binding reads this committed word. Fixed chart orientation stays zero; VM orientation remains a distinct state field. This coupling is an explicit application profile, and changes the trajectory relative to the uncoupled pure VM. Merely storing an EMIT flag does not implement it.

For width `W`, complement mask `M=2^W-1`, and present mask `P`, each of the two retained ASA/NA stages has three independently stored masks `(A_i,N_i,B_i)`:

\[
a_i(x)=x\mathbin\&A_i\mathbin\&P,\qquad
n_i(x)=a_i(x)\mathbin\&N_i,\qquad
T_i(x)=\begin{cases}n_i(x),&n_i(x)\mathbin\&B_i=0,\\0,&\text{otherwise.}\end{cases}
\]
\[
y=T_1(T_0(x)),\qquad
q^+=\bigl[(J\mathbin\&(M\mathbin\oplus q))
 \mathbin\vert((M\mathbin\oplus K)\mathbin\&q)\bigr]\mathbin\&P.
\]

Here NA names the retained masking stage, not logical complementation. In the generic hinge profile, a latch lane uses `J=e&y`, `K=e&~y`, and a declared reversing seam may use `J=K=e` on a distinct lane. The concrete EMIT binding uses its declared whole-word LUT bodies and makes no seam claim. Read/write dispatch order and old-state snapshots are part of the feedback contract. The coupler's borrowed-VM lifetime, state-generation, and expected-epoch checks detect managed resets/advances; direct DeviceView mutation or low-level `launch_step` must not bypass that ownership. Executed evidence is recorded separately from this contract.

## 4. Exact affine event specialization

Let an immutable epoch contain rational start time `t0`, horizon `H>t0`, rational state and rates, a finite set of once-only relation IDs, and fixed nominal coordinate bindings. Between events,

\[
x(t)=x_0+v(t-t_0),\qquad t\in[t_0,H].
\]

This is a conditional current-epoch prediction; an earlier accepted event replaces its remaining continuation. A relation binds the trajectory to an existing literal rational plane guard `g(x)=n·x-d` in the R15 editable expression graph. The binding supplies the coordinate names and dimensions; it does not introduce a second independent plane equation. Derive exactly

\[
g(x(t))=a(t-t_0)+c,\quad a=n\cdot v,\quad c=n\cdot x_0-d.
\]

No unit-normal premise is needed for the zero set or crossing signs. Without it, `g` is a defining function, not Euclidean signed distance. The profile accepts exactly parsed rationals and supported affine plane graphs; nonlinear/spherical roots require another profile rather than silent sampling or approximation.

For each unconsumed relation with a nonzero slope, the only root is `tau=t0-c/a`. Candidate admission requires `t0<tau<=H`, the relation's declared active interval, and exact support/equality gates at `tau`. Roots at the epoch start are excluded, including zeros introduced by a simultaneous reset at that start; there is no implicit instantaneous cascade. A constant nonzero guard has no root. An identically zero guard remains unresolved unless exact time/support/equality exclusion proves it irrelevant over the whole forward window. Point sampling cannot supply that exclusion proof.

Search all eligible relations and choose the least accepted rational root. Include every accepted relation at exactly that same rational time; no floating tolerance separates ties. Support/equality checks at the candidate are insufficient to skip another relation with an earlier accepted root. A result is complete only with respect to the declared finite relation set and supported affine algebra.

At a nonzero-slope root, the exact local one-sided signs are

\[
\operatorname{sgn}g(\tau-\epsilon)=-\operatorname{sgn}a,\qquad
\operatorname{sgn}g(\tau+\epsilon)=\operatorname{sgn}a\quad(\epsilon>0),
\]

for the affine extension, with no numerical epsilon evaluation. At `tau=H`, the latter is an algebraic continuation sign, not an assertion that a subsequent physical epoch has been observed or evolved. The terminal event commits at `H` and does not construct an invalid zero-length next interval.

The hinge adapter recomputes the root and slope from the actual plane graph and bound path, then applies the selected two-mask/JK event exactly once. Simultaneous state/rate edits read a common pre-event snapshot: equal `set` values coalesce, `add` values sum onto that snapshot, and `xor` values combine only on nonnegative dimensionless integer state (never rates). Mixed modes or unequal sets for one field reject. Relations sharing a hinge coalesce to one pulse only when origin, velocity, root, and plane-seed binding all agree; differing paths conflict. Priority and relation identity order the certificate, not the physical time or partially mutated state. Candidate application occurs on cloned state and hinges and commits all or none.

### 4.1 Semantic event certification

A checksum of a candidate event only binds its bytes. Before commit, the adapter recomputes the complete expected earliest event set from the current immutable epoch and requires exact canonical equality with the submitted request. This checks root, membership, gates, simultaneous completeness, source bindings, and updates; rehashing an altered event cannot make it valid. Exact rational parsing rejects floating values, booleans used as integers, zero denominators, and lossy coercion. Canonicalization reduces rational signs and common factors under the selected serialization schema.

Repeated application of the same accepted event identity must not repeat the hinge transition. A conflicting request under an already used identity rejects. Once-only relation removal and strictly increasing event times bound the number of relation firings by the finite initial relation count; this does not prove termination for arbitrary rearming, changing relation graphs, or zero-time cascades.

### 4.2 Corrections to the reviewed source event path

The reviewed source admits a root at the horizon and then attempts a zero-length OpenSegment; R16 treats that case as terminal. The reviewed rational-dictionary path applies integer conversion that can truncate a floating numerator/denominator when the schema has not been run; R16 uses strict rational admission. The reviewed event-application path can verify a recalculated certificate hash without semantically replaying a changed root or acceptance claim; R16 recomputes the entire expected earliest event set. These are narrowly identified implementation corrections, not evidence against exact rational event calculus itself.

## 5. Evaluated source material left outside this import

The finite learner has useful ideas: finite declared candidate families, exact rational training checks, retention of all surviving candidates, explicit ambiguity, and separate validation/holdout gates. Its delivered families are small authored sets, not open-ended physical model discovery. Its independent Python oracle is a falsifier with less structural validation than the formal program, so an oracle pass alone does not establish every admission rule. The source compiler's precomputed EMIT route does not establish native GPU candidate evaluation.

R16 documents this audit and does not add those CPU candidate families. If a future native calibration profile imports the idea, unresolved or overflowed candidates must remain unknown, not be discarded as mismatches. Unique selection requires exactly one verified fitting candidate and no unresolved eligible candidate. Noise models, observability, units, identifiability, and held-out physical evidence remain explicit application work. This release adds no statistical accuracy or cross-domain guarantee by naming a finite learner.

## 6. Scope of the result

R16 can combine a source-compatible finite operator stream, lossless bit-plane transport, native receipt-based word feedback, and a separate exact affine crossing adapter. Its proofs concern those arithmetic, ordering, and domain contracts. They do not turn phase cells into golden-ratio algebra, table zeros into physical distances, modular state into unbounded winding, or serialized host answers into GPU computation. Physical use still requires the retained R14/R15 dimensional models, constitutive closure, measurement calibration, and error contracts. Execution counts, cross-backend comparisons, timings, and device details belong to the release's recorded evidence, not to this normative document.
