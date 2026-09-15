# Resident spherical radius count profile

This specialization keeps an immutable spherical point index and an immutable
query table in CUDA device memory. Repeated evaluations produce **count
certificates**, with a separately requested exact host completion for queries
that contain unresolved points. This is a different output contract from the
earlier ID-return benchmarks.

## Exact target and finite source words

Source records are the unchanged `Point` words from `SpatialIndex::points()`.
Queries preserve their binary64 coordinates and squared chord radius. Both
point and query directions satisfy the shared `S2::IsUnitLength` contract;
the radius is a finite binary64 value in `[0,4]`. The exact target is

\[
 P=p/\|p\|,\quad Q=q/\|q\|,\qquad
 C(q,r^2)=\#\{p:\|P-Q\|^2\le r^2\}.
\]

Each source word and radius denotes its exact dyadic value. The mathematical
normalization need not be rational. Distinct record IDs count separately even
when their coordinate triples coincide. This profile uploads original words
directly; it does not include a bit-plane decoding operation in its timed
resident evaluation. The earlier `TextureIndex` profile provides that separate
lossless bit-plane expansion path.

Node, point and query textures use integer `uint4` element fetches at integer
indices, with point filtering and unnormalized texture coordinates. Two
128-bit fetches reconstruct each point/query record's binary64 words. Texture
and global-memory variants perform the same predicates and traversal; their
loads differ. A texture fetch supplies exact stored words, not an interpolated
position or a spatial raster cell substituted for the original geometry.

## Certified binary64 decisions

Let `eps=2^-52`, `u=eps/2`, and `m=2^-40=4096 eps`. The existing conservative
float node filter remains a candidate exclusion step: outward node bounds
and the `2^-14` allowance preserve all possible true members. Every point in
every unpruned leaf is then classified. There is no candidate-capacity limit,
truncated prefix, or early return when an unresolved point is found.

For a source/query pair the kernel computes

\[
 \widehat d_a=\operatorname{RN}(p_a-q_a),\qquad
 \widehat D=\operatorname{RN}\!\left(
   \operatorname{RN}(\widehat d_x^2+\widehat d_y^2)+\widehat d_z^2\right),
\]

with separately rounded products under the declared strict compilation mode.
The notation abbreviates the individual multiplication roundings. A loose
bound, deliberately wider than the needed local error estimates, is

\[
 |\widehat D-\|P-Q\|^2|<256\,\mathrm{eps}.
\]

One derivation is:

1. S2's unit-norm acceptance and the five-operation norm bound
   `gamma_5=5u/(1-5u)` give true squared norm within `9 eps` of one, allowing
   negligible absolute gradual-underflow contributions. Hence
   `|p_a-P_a|<8 eps` and likewise for the query.
2. Normalization error changes a coordinate difference by less than `16 eps`.
   Rounded subtraction adds less than `2 eps`, giving
   `|dhat_a-(P_a-Q_a)|<18 eps`.
3. Since `|P_a-Q_a|<=2`, squaring changes the result by less than `73 eps`.
   Multiplication rounding contributes less than `3 eps`, for less than
   `76 eps` per component. Three terms and two conservative `8 eps` addition
   allowances total less than `244 eps`, hence the stated `256 eps` envelope.

Each rounded threshold `RN(r²±m)` differs from its mathematical threshold by
less than `3 eps`. Therefore these decisions are certified:

\[
 \begin{array}{lll}
 \widehat D\le\operatorname{RN}(r^2-m)&\Rightarrow&\text{definitely inside},\\
 \widehat D>\operatorname{RN}(r^2+m)&\Rightarrow&\text{definitely outside},\\
 \text{otherwise}&&\text{unresolved}.
 \end{array}
\]

The margin is a computational certificate for this finite input domain. It
is not a physical position tolerance and does not remove model or observation
uncertainty. The proof requires IEEE binary64 operations in round-to-nearest,
finite near-unit inputs, and the declared operation model. Build the CUDA
target with `--fmad=false`, no fast-math, and strict host floating-point flags.

Two exact domain shortcuts are used. Numerically identical coordinate triples
have distance zero; the kernel checks their words, allowing opposite signs of
zero and no other word differences. A merely computed zero squared distance
does **not** prove identity: distinct subnormal separations can round to zero.
Proportional but nonidentical triples can represent the same normalized
direction, so they remain unresolved near zero unless the interval decides.
At radius squared exactly four, every accepted direction is inside by the
unit-sphere domain itself, and the kernel returns the full point count.

## Count certificate and host completion

Each query returns `ResidentCount {definite_inside, unresolved}` as two
unsigned 64-bit words. If these are `I,U`, complete traversal establishes

\[
 I\le C(q,r^2)\le I+U,\qquad
 N-I-U\text{ points are certified outside}.
\]

An unresolved count is never silently treated as outside. `resolve_exact()`
uses the certificate directly when `U=0`. Only when `U>0` does it run the
complete `SpatialIndex::radius_count` query with official S2 predicates. It
also checks that the exact answer lies within `[I,I+U]`. The fallback is
separately reported, with query and predicate-call counts. A predicate-call
count is not the count of S2's internal arbitrary-precision fallbacks.

`SpatialIndex::radius_count` uses the same inclusive traversal and robust
predicate as `radius`, without allocating an ID result vector. A CPU/S2 count
comparison must disclose whether the chosen public S2 API materializes a
temporary candidate vector. Count timings must not be presented as timings
for returning all matching IDs, polygons, arbitrary solids or ephemerides.

## Immutable epochs and explicit device feedback

```cpp
atomos::ResidentIndex gpu(host_index);
gpu.upload_queries(requests);        // once per object/epoch
gpu.evaluate(true, repetitions);     // texture path; no count readback
auto interval = gpu.readback_counts();
auto exact = gpu.resolve_exact();    // only unresolved queries use the host
```

Source and query storage remain immutable for the object's lifetime. A second
query upload is rejected; a new table requires a new epoch object. Repeated
`evaluate` launches overwrite only the output counts. Empty query tables
launch no kernel. The API records actual launches, not empty logical repeats.
Ordinary readback before evaluation, or after entering an external device
phase, is rejected to avoid interpreting stale/uninitialized output words.

`device_view()` supplies a non-owning `ResidentDeviceView`. Sources and query
pointers are const; count outputs are writable. The selected wrapper evaluates

\[
 \text{query index}_i=2i+(s_{i\,\mathrm{stride}}\mathbin{\&}1)
\]

and writes `counts[i]`. It does not change selector words. The selector buffer
must contain at least `(lanes-1)*stride+1` words for nonempty work, with its
producer epoch completed or correctly ordered before launch. There must be
two immutable query alternatives per lane. `HingeState`'s `q` is its first
word, so an array of those 64-byte states uses stride eight.

This wrapper lets a separate device feedback phase implement
`state -> selected query -> count certificate -> ASA/NA+JK state update`.
That phase must hold state whenever `U!=0`; the definite-inside prefix alone
cannot drive an accepted decision. Event deduplication, count-derived drive,
parity and phase traces are the feedback specialization's explicit contract,
not hidden effects of this count kernel.

The caller must serialize use of one object and keep all borrowed resources
alive. A device-view borrow ends before ordinary evaluation/readback/resolution
resumes; a later external phase must acquire a fresh view. Raw device pointers
cannot mechanically revoke an old borrow. Correct epoch use is a caller
precondition, not a claim that retaining a pointer enforces ownership.

## Timing, resources and validation scope

`evaluate` records CUDA events around repeated resident launches and waits for
completion; it reports total device-event time, per-launch time and host wall
time. Event intervals can include stream scheduling/launch gaps; they are not
a claim of isolated instruction execution time. There is no query upload,
count readback or exact host completion in those repeated launches. Readback
and complete host fallback are separate calls with separate statistics.

Reported device bytes comprise original points, flattened nodes, immutable
queries and count outputs. Allocations are finite and fail explicitly when
device texture/address capacity or memory is insufficient. This profile does
not create additional physical VRAM or guarantee cache residency; bandwidth,
cache behavior and capacity saturation require separate measured workloads.

`resident_index_tests.cpp` compares certificates and completed counts with
exact CPU radius results across endpoints, adjacent representable radii,
normalization aliases, subnormal separations, random directions, empty epochs,
texture/global paths and paired selector strides. Execution results must be
reported separately from this source-level proof and test plan.

Primary references: the pinned
[S2 predicates](https://github.com/google/s2geometry/blob/079611b654ad89afd9c3c3a1796d64bdd6a6b340/src/s2/s2predicates.h),
[S2 unit-length acceptance](https://github.com/google/s2geometry/blob/079611b654ad89afd9c3c3a1796d64bdd6a6b340/src/s2/s2pointutil.cc),
and NVIDIA's [floating-point guide](https://docs.nvidia.com/cuda/floating-point/index.html).
