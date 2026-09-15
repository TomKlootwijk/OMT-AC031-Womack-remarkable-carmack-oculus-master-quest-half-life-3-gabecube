# Resident binary64 radius-count predicate

This document derives a conservative decision certificate for a resident GPU
point-count profile. The exact target is the same normalized-direction,
inclusive squared-chord predicate used by the pinned S2 dependency. This
count profile returns a cardinality and status, not a list of point IDs.
Implementation and measurements must identify this narrower output contract.

## Target and arithmetic premises

Let `p,q` be the original finite binary64 coordinate triples, admitted by
`S2::IsUnitLength`, and let the binary64 value `r2` be finite and in `[0,4]`.
Their exact mathematical directions and squared chord distance are

\[
 P=\frac p{\|p\|},\qquad Q=\frac q{\|q\|},\qquad
 D=\sum_{i=1}^3(P_i-Q_i)^2\in[0,4].
\]

The requested membership is `D <= r2`, with the supplied binary64 radius
interpreted as its exact dyadic value. Preserving the original words does not
mean the raw triples already have exact norm one. S2 declares its distance
predicate in terms of exact mathematical normalization in
[s2predicates.h at 079611b654ad89afd9c3c3a1796d64bdd6a6b340](https://github.com/google/s2geometry/blob/079611b654ad89afd9c3c3a1796d64bdd6a6b340/src/s2/s2predicates.h).

Assume IEEE binary64 round-to-nearest, ties to even, gradual underflow,
finite inputs, no fast-math reassociation, and no fused multiply-add for the
displayed subtraction, square and two-addition body. The host admission test
and any S2 fallback also require their strict arithmetic environment. The
runtime must preserve these hypotheses in every worker performing a predicate.
The selected CUDA build uses `--fmad=false`. See NVIDIA's
[Floating Point and IEEE 754 guide](https://docs.nvidia.com/cuda/floating-point/index.html)
for the distinction between fused and separately rounded operations.

Write

\[
 \varepsilon=2^{-52},\qquad u=2^{-53}=\varepsilon/2,
 \qquad\eta=2^{-1074}.
\]

For each elementary exact result `z` below, rounding obeys

\[
 |\operatorname{RN}(z)-z|\le u|z|+\eta/2.
\]

The additive term covers subnormal rounding. The quantities encountered here
are bounded by small constants, so no overflow is possible in this body.

## Admission implies a raw-to-normalized coordinate bound

The pinned [S2 admission implementation](https://github.com/google/s2geometry/blob/079611b654ad89afd9c3c3a1796d64bdd6a6b340/src/s2/s2pointutil.cc)
requires the computed three-square sum to differ from one by at most
`5*eps`. Its nonnegative products and sums have the conservative error bound
`gamma5=5*u/(1-5*u)`, with an additive gradual-underflow allowance of `6*eta`.
Consequently an admitted raw vector satisfies

\[
 |\|p\|^2-1|<9\varepsilon,
 \qquad
 |\|p\|-1|
 =\frac{|\|p\|^2-1|}{\|p\|+1}<5\varepsilon.
\]

Since `p_i=||p|| P_i` and `|P_i| <= 1`, the deliberately looser coordinate
bound

\[
 |p_i-P_i|<8\varepsilon
\]

holds for every coordinate, and likewise for `q`. This step is necessary:
the subsequent device arithmetic uses preserved raw coordinates rather than
rounded coordinate normalization.

## Error of the direct binary64 distance body

The device evaluates

\[
 d_i=\operatorname{RN}(p_i-q_i),\qquad
 s_i=\operatorname{RN}(d_i^2),\qquad
 \widehat D=\operatorname{RN}
       \bigl(\operatorname{RN}(s_1+s_2)+s_3\bigr).
\]

Set `Delta_i=P_i-Q_i`, so `|Delta_i| <= 2`. The exact raw subtraction differs
from `Delta_i` by less than `16*eps`. Its magnitude is below `2+16*eps`, and
rounding the subtraction adds less than `2*eps`, including its underflow
allowance. Thus

\[
 |d_i-\Delta_i|<18\varepsilon.
\]

The error before rounding the square is bounded by

\[
 |d_i^2-\Delta_i^2|
 <18\varepsilon(4+18\varepsilon)<73\varepsilon.
\]

Here `|d_i|<2+18*eps`, so `d_i^2<5`; rounding that product adds less than
`3*eps`. Each rounded coordinate square consequently has absolute error less
than `76*eps`. Each of the two final additions adds less than `8*eps` because
its exact operands sum to less than `15+8*eps`. Therefore

\[
 |\widehat D-D|
 <3(76\varepsilon)+2(8\varepsilon)
 =244\varepsilon<256\varepsilon.
\]

This is an absolute, two-sided error bound in dimensionless squared-chord
units. It is purposely loose and includes raw norm error, subtraction,
products, sums and gradual underflow. It is not a physical position-error
bound, nor an assertion that the final binary64 value is itself exact.

## Rounded thresholds and definite decisions

Choose the exactly representable margin

\[
 m=2^{-40}=4096\varepsilon,\qquad
 t_-=\operatorname{RN}(r2-m),\quad
 t_+=\operatorname{RN}(r2+m).
\]

Because `r2` lies in `[0,4]`, each threshold has rounding error less than
`3*eps`. This includes `r2=0`, subnormal radii, and `r2=4`; the lower threshold
is allowed to be negative and the upper one to exceed four. Do not silently
replace these thresholds by a different clamp rule without checking it.

The safe decisions are:

| Condition | Certified meaning |
|---|---|
| `Dhat <= t_minus` | Inside: `D < r2`, hence inclusive membership |
| `Dhat > t_plus` | Outside: `D > r2` |
| Otherwise | Unresolved by this interval predicate |

For the inside case,

\[
 D<\widehat D+256\varepsilon
 \le t_-+256\varepsilon
 <r2-(4096-3-256)\varepsilon<r2.
\]

For the outside case,

\[
 D>\widehat D-256\varepsilon
 >t_+-256\varepsilon
 >r2+(4096-3-256)\varepsilon>r2.
\]

The wide margin therefore dominates both distance and threshold error.
Points exactly on the true boundary remain unresolved by these inequalities;
that is required for an honest inclusive decision unless another exact
certificate is available.

The reviewed `resident_index.cu` admits two exact special cases. Componentwise
numerical equality of the original triples proves `P=Q` and `D=0`, including
differences only in signed-zero representations, so every allowed radius
contains the point. Also `r2=4` contains every admitted normalized direction.
These shortcuts are separate from the interval derivation. Neither requires evaluating a square
root. A computed `Dhat==0` alone is not an identity certificate: distinct
subnormal coordinate separations may square to zero. Nonidentical
proportional raw triples can also represent the same direction; they remain
unresolved near zero unless separately certified.

## Combining the predicate with the resident hierarchy

The existing conservative binary32 hierarchy filter may first reject nodes,
provided every node encloses its exact normalized descendants and the
filter's documented error margin is retained. Its proof is in
[`NATIVE_GPU.md`](NATIVE_GPU.md). It can exclude only points that cannot be
members, so it does not remove an unresolved point that could change the
answer. Surviving points are then classified from their preserved binary64
coordinates with the certificate above.

For one query, let `I` count definite inside points, and `U` count unresolved
points. Definite outside points contribute neither. The exact answer obeys

\[
 I\le\operatorname{Count}(q,r2)\le I+U.
\]

Only `U=0` makes `I` a completed exact count under this contract. When `U>0`,
the query result remains explicitly unresolved; a selected host-resolution
path reruns the complete query with the shared exact S2 predicate. The
fallback must be accounted for separately from the resident kernel, and it
must not present the partial `I` as the final count. A count-only query has
no candidate-list capacity or prefix-truncation semantics from the separate
ID-returning GPU path.

Original seeds and derived hierarchy nodes remain immutable during a count
epoch. Uploaded queries are immutable for that epoch. A result or working
buffer written by a producer is read only after a completed kernel/stream
dependency; raw texture reads are not made coherent by an assumption about
cache residency. Reusing a cached hierarchy after source changes needs a new
valid enclosure and version binding.

## Reviewed resident API and selected-query phase

The implementation in `resident_index.hpp`, `resident_index.cpp` and
`resident_index.cu` uploads one immutable source and one immutable query-table
epoch per object. `evaluate` may repeat the resident kernel without source,
query or per-launch result transfers. `readback_counts` transfers only
`ResidentCount{definite_inside,unresolved}` summaries, and checks their sum
does not exceed the source record count. `resolve_exact` invokes complete
host radius queries only for summaries with a nonzero unresolved field and
checks each resolved count against `[I,I+U]`. The independent summaries and
fallback statistics therefore keep device certification and host resolution
visible.

The selected-query launch supports paired immutable alternatives. Lane `i`
selects query `2*i + (old_selector[i*stride]&1)` and writes summary slot `i`.
It requires positive stride in 64-bit words, enough paired queries, a valid
selector allocation covering every indexed word, and a completed producer
epoch for that old selector. It never modifies selector/source/query words.
This selection is a possible coupling to delayed GPU feedback; it is not
itself a state-update rule or a count benchmark result.

Taking `device_view()` invalidates the object's ordinary evaluated/cache
state, so selected summaries cannot silently resolve against the ordinary
host query order. The view is non-owning and belongs to the caller-managed
external phase. The caller must end that phase before resuming ordinary
evaluation and must not later write through an old retained view without
starting a fresh invalidated phase. Raw device pointers do not enforce this
ownership automatically. External selected results and any corresponding
resolution/trace remain the caller's explicit responsibility.

## Reviewed count-to-word feedback profile

`resident_feedback.hpp` and `resident_feedback.cu` bind lane `i` to the paired
immutable queries `2*i+(old_q&1)`. The source/query object must outlive the
feedback object. Each `run_epochs` obtains a fresh `device_view()` and issues
two kernels per epoch in the same default stream: the selected count reads
the old word, then the commit consumes the summary and writes state. Calls
sharing the same source/device output must be externally serialized. No
same-launch read/write of a texture-backed state allocation occurs: source
and query words are immutable textures, and feedback state is separate global
memory. Stream ordering completes each producer before its next consumer.
This use matches the official CUDA rules for
[stream ordering](https://docs.nvidia.com/cuda/archive/12.8.1/cuda-c-programming-guide/index.html#streams)
and [texture coherence](https://docs.nvidia.com/cuda/archive/12.8.1/cuda-c-programming-guide/index.html#read-write-coherency).

For an ordered new epoch with `U=0`, the drive is the exact Boolean
`d=[I>0]`. The declared initialization rule emits a pulse on the first
resolved sample; subsequent pulses require a drive change. On a pulse, the
configured old-word/input LUT, two ordered ASA/NA masks and old-word/output
J/K LUTs supply the synchronous JK update. Every table sees the same old
word. Parity toggles and the accepted hinge count increments. Without a pulse,
the word and parity hold but the resolved epoch and drive are remembered.
This finite profile has no geometric seam transition; orientation remains
zero.

An unresolved count changes only status: the word, parity, hinge count, last
resolved drive and last committed epoch hold. This selected feedback path
does not invoke automatic host resolution. It deliberately requires the
complete count certificate even when some weaker existence-only certificate
might be sufficient for another profile. Repeating the last committed epoch
holds before consuming any recomputed query count; an older epoch is rejected.
Exhausted hinge-counter storage rejects the commit. The header/source's
64-byte state layout puts `q` first and provides the checked eight-word
selector stride.

This is actual delayed state feedback through the selected geometric query.
It is separate from the independent exact-integer operator working-set
experiment in [`WORD_CACHE_BENCHMARK.md`](WORD_CACHE_BENCHMARK.md). That
experiment compares immutable record texture/global fetches with the same
global ping-pong state buffers. Its per-epoch internal nonzero-sign pulses,
coefficient bounds, full-record address permutation and validation contracts
are not silently substituted for the resolved drive-change semantics above.

## Evidence and scope

The derivation is source-level mathematics under explicit arithmetic and
binding hypotheses. Correctness tests must exercise the actual compiled
inside/outside/unresolved paths, equality and adjacent radii, aliases,
subnormal separations, both endpoint radii, and texture/global equivalence.
Their observed results belong in the completed release report.

Resident kernel timing must be separated from initial seed/query upload,
summary readback, exact host fallback and full host-visible timing. A resident
COUNT comparison must use the same point words, radius and cardinality
output requirement for its baseline. It is not an ID-list benchmark.
Neither this predicate nor a separate word-feedback/cache working-set sweep
establishes universal superiority over S2, an advantage caused by phi or
Klein topology, or physical navigation accuracy. No unmeasured timing,
working-set saturation result or cache-hit ratio is supplied by this proof.
