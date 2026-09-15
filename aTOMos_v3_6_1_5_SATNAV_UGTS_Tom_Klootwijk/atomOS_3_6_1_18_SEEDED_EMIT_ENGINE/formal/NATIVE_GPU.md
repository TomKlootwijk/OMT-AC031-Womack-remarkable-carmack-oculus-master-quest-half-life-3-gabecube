# Native CUDA radius filter and accepted-event word kernel

This document specifies the source-level contract of `TextureIndex` in
`src/texture_index.cpp`, `cuda/texture_index.cu`, and the associated headers.
It distinguishes exact integer operations, conservative floating-point
filtering, and final geometric decisions. Test and benchmark reports provide
separate evidence about the built binary and measured workloads.

## Authoritative data and the implemented device subset

The spatial source is the immutable host `SpatialIndex`: original IEEE
binary64 point coordinates and unique IDs, reordered without normalization,
plus its enclosing hierarchy. The selected geometric meaning is the exact
mathematical direction of each nonzero coordinate triple:

\[
 P=p/\|p\|,\qquad Q=q/\|q\|,\qquad
 D(P,Q)=\|P-Q\|^2\in[0,4].
\]

The supplied binary64 squared radius `r2` is the exact comparison threshold
for this interface. Membership is inclusive, `D(P,Q) <= r2`. Original
coordinates remain available for the final `s2pred::CompareDistance`
decision, whose declared semantics use these normalized directions. This is
exactness relative to the supplied finite data and radius, not a claim about
an unknown physical location. The pinned predicate declaration is
[S2 predicates, revision 079611b654ad89afd9c3c3a1796d64bdd6a6b340](https://github.com/google/s2geometry/blob/079611b654ad89afd9c3c3a1796d64bdd6a6b340/src/s2/s2predicates.h).

The host serializes derived 48-byte GPU nodes and original 32-byte point
records as 64-bit words. Node endpoints are outward binary32 projections;
point records retain their binary64 bits and IDs. Each block of 64 words is
transposed into 64 bit planes, padded with declared zero words. The device
inverse transpose is the exact identity

\[
 B_k=\sum_{j=0}^{63}((W_j\gg k)\mathbin{\&}1)2^j,
 \qquad
 W_j=\sum_{k=0}^{63}((B_k\gg j)\mathbin{\&}1)2^k.
\]

`expand_words` reads these packed integer planes through a texture and writes
the decoded words to a separate allocation in VRAM. No numerical rounding is
part of this transpose. The subsequent point-query kernel projects coordinate
values to binary32 for filtering; that numerical projection is a separate
operation and never replaces the host source.

This native payload currently represents a derived spatial hierarchy and its
point records. It is not the Python `AHNGBPL1` complete operator/state envelope.
The separate native hinge kernel executes bounded 64-bit Boolean profiles,
two ordered ASA/NA mask stages, synchronous JK, and explicit accepted-event
parities. Those are real device operations, but they do not execute the whole
arbitrary-precision rational-phi AST, logarithmic/spherical expression graph,
chart cocycle, acquisition policy, or R14 physical dynamics in this file pair.
In particular, decoding a bit-plane buffer is not itself evaluation of all
operators stored in a different seed format. An exact reference evaluation
can prepare admitted native inputs; a complete lowering must additionally
bind source identity, parameters, event epoch and supported expression bodies.
Additional native operator profiles have their own code and contracts; this
document's statements about the radius/LUT file pair do not negate a separate
bounded exact phi implementation. The native record layout described here is
the selected little-endian host/CUDA ABI, not an unspecified portable binary
serialization format.

## Numerical hypotheses

The filter proof below assumes:

1. Finite point and query triples satisfy the pinned `S2::IsUnitLength` test;
   `r2` is finite and lies in `[0,4]`.
2. Host binary64 and device binary32 operations use round-to-nearest, ties to
   even, with gradual underflow, and preserve the written operation sequence.
   The current CUDA target uses `--fmad=false`; fast-math reassociation or
   flush-to-zero is outside this proof. Host S2 refinement has the same strict
   arithmetic requirement.
3. Every host node encloses the exact normalized directions of all its
   descendants. Its float lower endpoint is rounded downward and upper
   endpoint upward. The source hierarchy is immutable during a query.
4. Resource sizes, integer indices, allocation lengths and launch counts fit
   their declared host/device representations and supported texture limits.
   The wrapper completes the producer before any consumer reads its output.

These are explicit preconditions, not deductions from the presence of a
texture object. NVIDIA documents the distinction between separately rounded
operations and fused multiply-add in its
[Floating Point and IEEE 754 guide](https://docs.nvidia.com/cuda/floating-point/index.html).
The wrapper checks `FE_TONEAREST` at `radius_batch` entry, validates points
through the shared S2 test, bounds query/hinge batches by `INT32_MAX`, checks
candidate allocation multiplication, and checks linear texture element counts
against both `maxTexture1DLinear` and the signed texture-index limit. Query
storage growth allocates complete replacement buffers before publishing them;
a failed growth preserves the earlier buffers. Construction releases acquired
device allocations if it fails. These checks do not substitute for the
compiler/underflow assumptions above.

The pinned [S2 unit-length implementation](https://github.com/google/s2geometry/blob/079611b654ad89afd9c3c3a1796d64bdd6a6b340/src/s2/s2pointutil.cc)
accepts a computed squared norm differing from one by at most `5*DBL_EPSILON`.
Write `eps64 = 2^-52`, `u64 = eps64/2`. A conservative standard bound for the
nonnegative three-square sum is `gamma5 = 5*u64/(1-5*u64)`, with a negligible
additive underflow term. Thus an accepted vector has exact squared norm within
`9*eps64` of one, and exact norm within `5*eps64` of one. The looser bound

\[
 |p_i-P_i| < 8\,\mathrm{eps64}
\]

is sufficient here. It follows from
`p_i-P_i=(||p||-1)P_i` and `|P_i| <= 1`. The host's `16*eps64`
coordinate padding, followed by outward `nextafter`, exceeds that error and
the binary64 endpoint-addition error. Outward conversion to float preserves
the resulting enclosure. This connects the normalized-direction premise to
the actual raw-coordinate bounds; it does not assume the stored points are
exactly unit length.

## Conservative binary32 filter error

Let `u = 2^-24` be binary32 unit roundoff. For every rounded elementary result
`z` in this bounded computation, use

\[
 |\operatorname{RN}(z)-z|\le u|z|+2^{-150}.
\]

The additive term covers gradual underflow. All quantities below have
magnitude less than 27, and there is no overflow. The constants are purposely
loose; they establish a filter bound, not an accuracy estimate for the final
answer.

**Projected coordinates.** A near-unit raw coordinate differs from its exact
normalized coordinate by less than `8*eps64`. Its binary32 rounding adds at
most `u`. Consequently, both the device point coordinate `phat_i` and uploaded
query coordinate `qhat_i` differ from their normalized values by less than
`2*u`.

**Leaf distance.** Put `d_i=P_i-Q_i`, so `|d_i| <= 2`. The exact subtraction
of the two projected coordinates differs from `d_i` by less than `4*u`.
The rounded subtraction adds less than `4*u` because its magnitude is less
than 3, giving

\[
 |\widehat d_i-d_i|<8u.
\]

Its unrounded square exceeds `d_i^2` by less than
`8*u*(4+8*u) < 33*u`. Rounding that square adds less than `10*u`, since
`|dhat_i| < 3`. Three rounded squares therefore overestimate the exact
squared chord distance by less than `129*u`. Each of the two additions is
below magnitude 27 and adds less than `28*u`. Thus the computed leaf scalar
`Dhat` satisfies the conservative one-sided bound

\[
 \widehat D-D(P,Q)<185u<256u.
\]

**Node lower distance.** Choose any exact normalized descendant `P` of the
node. For each coordinate, the distance from `qhat_i` to its outward float
interval is at most `|P_i-Q_i|+2*u`. Rounding either endpoint subtraction
adds less than `4*u`; the `max` selections do not round the chosen value.
The computed coordinate gap is therefore at most `|d_i|+6*u`. Its rounded
square exceeds `d_i^2` by less than `35*u`. The same two-sum bound yields

\[
 \widehat L-D(P,Q)<161u<256u
 \quad\text{for every descendant }P.
\]

This is the relevant exclusion statement. The float quantity `Lhat` is not
claimed to be an unpadded exact lower bound by itself.

**Implemented threshold.** The wrapper rounds `r2` upward to a float
`rhat <= 4`. The kernel uses `kFilterPad=2^-14=1024*u` and the rounded sum

\[
 T=\operatorname{RN}(\widehat r+1024u)
   > r2+1019u.
\]

The sum is at most `4+2^-14`, so its rounding loss is less than `5*u`.
For any true member `D(P,Q) <= r2`, both `Dhat` and every ancestor `Lhat`
are strictly below `T`. Therefore the node rejection `Lhat > T` cannot prune
that member, and the leaf acceptance `Dhat <= T` retains it. Equality at the
true radius is retained. This proof applies identically to the texture-fetch
and global-load variants because they reconstruct the same raw point values
and apply the same arithmetic.

The padding is in dimensionless squared-chord units. It is not a promised
distance error in metres or radians. It can admit many extra candidates,
especially for small radii, clustered points, or duplicate directions.

## Exact refinement, capacity and traversal

The median-split hierarchy contains every point once. Preorder escape links
skip a whole subtree only after its certified rejection; otherwise traversal
descends or visits the points in a leaf, until the overflow rule below takes
effect. For capacity `cap`, a query writes at most `cap` candidates. On finding
candidate `cap+1`, it publishes that count and immediately returns. If `C` is
the count a full traversal would produce, the reported count is therefore

\[
 c=\min(C,\mathrm{cap}+1).
\]

`cap+1` is a saturated lower bound on the full candidate count and a definitive
overflow signal. No subsequent candidate can change the required action:
the wrapper ignores the partial candidate buffer and reruns the complete
query through host `SpatialIndex::radius`. It never returns the prefix as the
answer. No geometric result or logical event is inferred from the unvisited
remainder. The filter proof is unchanged: a nonoverflow query exhausts the
certified traversal, while an overflow query obtains its whole answer from
the complete exact host path. The `candidate_count` statistic sums these
possibly saturated counts, so it is not the total candidate population for
overflowing workloads. `candidate_count_is_lower_bound` explicitly reports
whether any query overflowed.

The current readback first transfers all `N` counts (`4*N` bytes). It then
computes checked 64-bit prefix offsets on the host:

\[
 r_i=\begin{cases}c_i,&c_i\le\mathrm{cap},\\0,&c_i>\mathrm{cap},\end{cases}
 \qquad o_0=0,\quad o_{i+1}=o_i+r_i,\quad M=o_N.
\]

Each addition is checked against the maximum representable candidate-buffer
length `SIZE_MAX/sizeof(uint32_t)`. If `M>0`, the wrapper uploads the `N+1`
offsets, then a separate CUDA kernel copies

\[
 \mathrm{compact}[o_i+k]=\mathrm{candidate}[i\,\mathrm{cap}+k],
 \qquad 0\le k<r_i.
\]

One warp owns a query and its lanes copy indices spaced by 32. The monotone
offset intervals are disjoint; every retained candidate is copied once in
its original per-query order. Source intervals have length at most `cap`,
and destination intervals end at or before `M`. Host refinement reads the
same interval using `o_i`, so compaction does not change a candidate identity
or a predicate. A count exactly equal to capacity is retained in full. A
count of `cap+1` has a zero-length compact interval and still selects the
complete host fallback.

Only the `M` retained candidate indices are read back (`4*M` bytes).
`candidate_readback_bytes` records that payload alone, excluding the separate
count readback. `candidate_offset_upload_bytes` records `8*(N+1)` when
compaction runs. If `M=0`, including an all-overflow batch, no offsets are
uploaded, no compaction kernel runs, and no candidate payload is transferred;
both traffic fields and `compaction_ms` are zero. Counts still drive either
complete host fallback or the empty nonoverflow result. Thus an absent
candidate transfer is never interpreted as an empty answer for an overflow
query.

The fixed-stride candidate buffer remains device scratch; compaction adds a
reusable offset allocation and a reusable compact destination. Their growth
allocates replacement storage before publishing it, preserving the old
allocation if a replacement fails. Selective readback reduces transfer volume
but is not a reduction of the authoritative seed or the requested answer.

For a nonoverflow query, every retained candidate is checked against the
original point and original binary64 radius with `s2pred::CompareDistance`.
This removes possible false positives. The filter argument above supplies
absence of false negatives under its hypotheses. The returned IDs are
sorted; records with distinct IDs but identical coordinates are retained.
This path accelerates inclusive radius queries. It does not implement GPU
nearest-neighbor ordering, polygon operations, or a complete replacement for
S2's other interfaces.

Host refinement and complete fallback use one persistent worker pool owned by
the `TextureIndex`. Its maximum participant count is
`P=max(1,min(hardware_concurrency(),20))`, including the calling thread;
there are at most 19 additional owned threads. They are created during object
construction, not once per query batch. Pool startup precedes the local
`upload_ms` timer and therefore belongs in complete construction timing.

For `N` queries, saturated candidate sum `Csum`, and `O` overflow queries, the
active participant count is

\[
 A=\min\!\left(P,N,
       \max\!\left(1,\left\lceil N/64\right\rceil,
                      \left\lceil C_{\rm sum}/2048\right\rceil,O\right)\right).
\]

An empty batch performs no refinement. Dynamic chunks contain one query if
there is overflow or fewer than 64 queries, otherwise eight. An atomic work
index assigns disjoint output slots; every slot's IDs are sorted. Work
scheduling therefore changes the execution order across queries, not each
query's predicate, output identity, or inclusive boundary rule. A worker
exception is propagated after dispatched workers finish, rather than
returning a partial successful result.

Each owned worker initializes its rounding mode to `FE_TONEAREST`; every
dispatch checks that worker's environment again. The caller's mode is checked
and never changed. Direct predicate refinement and the complete fallback
therefore retain the same arithmetic precondition. Calls on the same object
still require external serialization; the internal pool does not make
concurrent `radius_batch` calls on that object supported.

`refinement_threads` records `A`. `exact_refinements` counts S2 predicate
calls, including calls made by complete host fallback; it does not count how
often S2 internally escalates to arbitrary precision. `kernel_ms` measures
the radius kernel, while `compaction_ms` separately measures only the compact
copy kernel. The latter excludes the preceding offset upload and following
candidate readback. `refinement_ms` begins after compact candidate readback
and includes worker selection/dispatch, per-query output allocation,
predicates/fallback and ID sorting. Count reduction and prefix preparation
therefore belong to `query_wall_ms`, not `refinement_ms`, in this optimized
path. `query_wall_ms` includes the whole host-visible query pipeline,
including query upload, count readback, prefix work, any offset upload,
compaction and retained-candidate transfer. The predicate proof and GPU
filter bound are unchanged by either compaction or parallel scheduling.

## Native hinge equations and event identity

Each array index identifies one persistent device state. New indices start
with `q=0`, hinge parity `p=0`, coorientation `kappa=0`, and no accepted event.
The input is `(drive,event,reversing,valid)`. `valid` and `reversing` have a
binary domain, enforced by the host wrapper before launch. This API consumes already accepted hinge events, so a valid
new event has `h=1`; it does not discover crossings from a continuous path,
evaluate an exact geometric guard, or establish a no-pulse baseline.

For the same state index, an accepted event number must increase. Repeating
the latest event with the same payload has no state transition. A smaller
number is stale. The host wrapper rejects changed drive/seam contents reused
under the latest identity and binds an immutable `WordProfile`; changing that
profile requires a new object/profile epoch. This monotone interface is
narrower than the Python reference's complete consumed-identity history.
Array reordering changes which state receives an input, so persistent index
identity belongs to the caller's binding contract.

For each bit, a four-entry LUT has index `q_bit+2*argument_bit`:

\[
 T_L(q,a)=\bigvee_{i,j\in\{0,1\}:L_{i+2j}=1}
                   [q=i]\land[a=j].
\]

With valid mask `M`, `d=drive & M`, the word bodies are

\[
 x=T_{L_x}(q,d)\land M,\qquad
 A_0=x\land a_0\land n_0,
 \qquad y_0=\begin{cases}0,&A_0\land b_0\ne0,\\A_0,&\text{otherwise},\end{cases}
\]

\[
 A_1=y_0\land a_1\land n_1,\qquad
 y=\begin{cases}0,&A_1\land b_1\ne0,\\A_1,&\text{otherwise},\end{cases}
\]

\[
 J=T_{L_J}(q,y)\land M,\quad K=T_{L_K}(q,y)\land M,
 \quad q^+=((J\land\neg q)\lor(\neg K\land q))\land M,
\]

\[
 p^+=p\oplus1,\qquad \kappa^+=\kappa\oplus\mathrm{reversing}.
\]

The mask boundary test zeros the entire stage output on any boundary hit;
it is not a per-bit removal. All right-hand sides read the old `q`. Native
integer Boolean operations are exact within the 64-bit word domain.

The current native defaults are `Lx=0xE`, `LJ=0xC`, `LK=0x3`: hence
`x=q OR d`, `J=y`, `K=NOT y` within `M`. These are not the Python builder's
default `x=d`; choosing `Lx=0xC` selects that native X body. The native
coorientation field is separate from `q`. A reserved reversing-seam JK lane,
full winding record, local-sign gluing verification, arbitrary lazy word AST,
or availability/sample guard must be supplied by an explicit larger adapter;
it is not implicitly implemented by this four-entry LUT kernel.

Statuses distinguish an available accepted/duplicate record, invalid input
availability, and stale/conflicting order. A status change alone is diagnostic
state, not a new hinge pulse. A raw low-level launch bypassing the wrapper
does not inherit the wrapper's payload/profile checks.

## Texture resources and cache lifecycle

The texture resource is linear `uint4`, read with integer `tex1Dfetch` and
`cudaReadModeElementType`. Filtering and normalized addressing are not used
to interpret source words. A 64-bit word is reconstructed from two 32-bit
lanes; binary64 point components are reconstructed from their original high
and low words. The separate point allocation guarantees an aligned base;
the node count times 48 bytes need not itself be a valid texture alignment.
Resource creation is checked against CUDA's constraints. The API contract is
documented in [NVIDIA Texture Object Management](https://docs.nvidia.com/cuda/cuda-runtime-api/group__CUDART__TEXTURE__OBJECT.html).

Packed source and expanded destination are separate allocations. The wrapper
records and synchronizes completion of the expansion kernel before binding
and consuming the derived node/point textures. Radius traversal reads these
immutable textures and writes only query result storage. The mutable hinge
array is separate global memory, with one thread owning each state per call.
Calls on one object require serialized ownership; concurrent host calls are
not a supported state-update protocol.

One pair of CUDA timing events is owned by the object and reused for seed
expansion, radius traversal and optional compaction. Every measured stage
records start/end, synchronizes its end event and reads elapsed time before
the pair is re-recorded for another stage. This provides ordered reuse under
the serialized-call contract; it introduces no overlap or cache-coherence
assumption. Both handles start null and any successfully created handle is
destroyed during object cleanup, including construction failure. An empty or
zero-retained batch does not invent an elapsed compaction measurement.

This avoids reading through a texture from memory modified by that same
launch. NVIDIA specifically describes the lack of coherence with such global
writes in the [CUDA Best Practices texture-memory section](https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/#texture-memory).
Future dynamic refits or expression expansion must establish a new completed
producer/consumer epoch and update every affected enclosure before pruning.
The present immutable spatial object has no in-place dynamic refit API.

The inspected `review/texture_sass.txt` is evidence for the initial validated
native build, whose CUDA source was committed in `9cfe094`, before the
saturated early-overflow exit, parallel host refinement and selective
candidate-readback optimizations. It
records native `sm_120` code with
`--fmad false`. Its `radius_kernel<true>` contains `TLD.LZ` instructions,
including the node-load sequence at offsets `0x0200` through `0x0220`;
`expand_words` also contains `TLD.LZ`. The corresponding
`radius_kernel<false>` uses `LDG.E` instructions for its global data path.
NVIDIA lists `TLD` as a texture-load instruction in its
[Binary Utilities instruction reference](https://docs.nvidia.com/cuda/cuda-binary-utilities/index.html).
This is concrete evidence that the inspected compiled specialization uses
hardware texture-load instructions. It does not prove that a particular
runtime access hits a cache, that a whole working set remains resident, or
that the texture variant is faster. The disassembly belongs to its recorded
build; later source changes require corresponding build evidence.

Execution evidence is separately recorded in
[`review/ncu_texture.csv`](../review/ncu_texture.csv) for that same initial
validated native build and CUDA source `9cfe094`. Nsight Compute captured
the texture specialization `radius_kernel<1>` on compute capability 12.0,
with four blocks of 128 threads, and reported
`l1tex__t_sectors_pipe_tex_mem_texture_op_ld.sum = 169426` sectors. The CSV's
locale uses dots as thousands separators (`169.426`). This establishes
measured texture-load sector activity for that executed kernel, in addition
to the compiled `TLD.LZ` evidence. The recorded profiled duration is
1,255,392 ns, or 1.255392 ms; profiler instrumentation/replay conditions make
it distinct from the unprofiled benchmark timing. The recorded metric is a
sector count, not a hit ratio, a residency measurement, or a proof that any
particular source word remained cached.
These original artifacts are preserved as original evidence; their counts,
offsets and timing are not attributed to the later optimized kernel.

The device controls cache residency, replacement, coalescing and scheduling.
This implementation makes texture accesses; it does not guarantee a cache
hit or that textures outperform global loads. `resident_bytes` accounts for
the base packed/expanded spatial allocations and aligned point copy, not all
later query/hinge scratch allocations. Timings must distinguish upload,
expansion, resident kernels, host-visible transfer/refinement/fallback, and
the matching global-load baseline. VRAM expansion of a finite payload and
delayed hinge feedback are implemented mechanisms; neither asserts an
infinite self-referential tree resident in finite memory.
