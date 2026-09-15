# R15 continuous spherical point index

`include/atomos/spatial_index.hpp` implements the host reference for a continuous
direction index and exports its contiguous hierarchy for a device candidate
pass. It is one bounded engine competency: point radius, nearest and k-nearest
queries on a sphere. It does not implement polygon topology, ellipsoidal
geodesics, signed distance to arbitrary solids or satellite propagation.

## Authoritative seeds and metric

A record is `Point {double x, y, z; uint64_t id}` with a unique ID. Its three
binary64 words are preserved bit for bit, including signed zero. Build only
permutes records. The accepted domain is finite points satisfying the official
`S2::IsUnitLength` check, which allows the small norm error of an ordinary
floating-point normalization. Nonunit inputs are rejected, not silently
renormalized. A caller choosing coordinates from a procedural expression must
record that separate evaluation/approximation step.

The geometric meaning of a seed is its *exact mathematical direction*

\[
 \widehat p=p/\sqrt{p\cdot p},\qquad
 d^2(q,p)=\|\widehat q-\widehat p\|^2
         =2-2\frac{q\cdot p}{\sqrt{(q\cdot q)(p\cdot p)}}.
\]

Thus the source words are exact dyadic inputs, but the normalized direction
may have irrational coordinates. No array of raster cells replaces it. Radius
accepts a finite binary64 `r2` in `[0,4]` and returns every record with
`d² <= r2`, including equality. `r2` itself denotes its exact dyadic value.
This metric is neither raw unnormalized Cartesian chord distance nor a
distance in metres. On a sphere of chosen radius `R`, arc length is
`2 R asin(sqrt(d²)/2)`; this does not automatically supply a physical Earth
surface or a MEO satellite range.

Membership uses official `s2pred::CompareDistance`. Ordering uses
`s2pred::CompareDistances`, including its symbolic tie rule for distinct
coordinate triples at exactly equal distances. Identical coordinate triples
are ordered by increasing record ID. Consequently this is a reproducible
refinement of true nearest-distance order, with the S2 symbolic convention
explicitly retained. `Neighbor::chord_distance2` is an approximate report value
from `S1ChordAngle`, not the value used to establish exact order or inclusion.

S2 applies floating-point filters and exact arithmetic when necessary. This
release therefore uses a shared robust predicate dependency; it does not
claim invention of that dependency or exact arithmetic for arbitrary real
input data. The source used for the comparison is official S2 revision
`079611b654ad89afd9c3c3a1796d64bdd6a6b340`:
[distance predicates](https://github.com/google/s2geometry/blob/079611b654ad89afd9c3c3a1796d64bdd6a6b340/src/s2/s2predicates.h),
[predicate implementation](https://github.com/google/s2geometry/blob/079611b654ad89afd9c3c3a1796d64bdd6a6b340/src/s2/s2predicates.cc),
[unit-length contract](https://github.com/google/s2geometry/blob/079611b654ad89afd9c3c3a1796d64bdd6a6b340/src/s2/s2pointutil.cc).

## Signed-plane hierarchy and conservative exclusion

The index recursively partitions the largest coordinate extent at its median.
Each split has a signed-plane hinge `h(p)=p[axis]-split`. Coordinate equality
uses ID to make a definite partition. Both children may contain points on the
hinge plane; the partition does not assert a geometric gap. Leaves retain
contiguous ranges of original records. The default leaf capacity is 16.

Each node stores a conservative descendant axis-aligned bounding box. Let
`epsilon = 2^-52` and `u = epsilon/2`. Under strict round-to-nearest binary64,
the five elementary operations in the squared norm have relative error at
most `gamma_5=5u/(1-5u)`, plus a negligible absolute gradual-underflow term
when an individual coordinate square is subnormal. Accepted seeds satisfy

\[
 |\operatorname{fl}(p\cdot p)-1|\le 5\epsilon,
 \qquad |p\cdot p-1|<8\epsilon.
\]

It follows that `|norm(p)-1| < 5 epsilon` and each coordinate differs from its
mathematically normalized value by less than `5 epsilon`. The implementation
uses the deliberately larger `delta=16 epsilon` and an additional outward
`nextafter` at each bound:

\[
 B_a^- = \operatorname{nextDown}(\min_i p_{i,a}-\delta),\qquad
 B_a^+ = \operatorname{nextUp}(\max_i p_{i,a}+\delta).
\]

The query has an enclosure `Q` constructed by the same rule. The exact
distance between the two boxes is a lower bound for the distance from the
query direction to every descendant:

\[
 b^2(Q,B)=\sum_{a=1}^3
 \max(0,B_a^- - Q_a^+,Q_a^- - B_a^+)^2
 \le d^2(q,p_i).
\]

The computed positive differences, squares and sum can round upward. With
`eta=2^-1074`, the implementation conservatively reduces their floating-point
sum `s` to

\[
 b_{\rm safe}^2=
 \max\{0,\operatorname{fl}(s(1-16\epsilon)-16\eta)\}.
\]

The normal-operation error needs fewer than 16 epsilons; the additive term
covers gradual-underflow rounding. This bound is deliberately conservative.
It is used only to exclude a node when `b_safe² > limit`. Equality always
survives to the point predicates.

For nearest and k-nearest traversal, `limit` is a certified upper bound on the
current worst retained point's true distance. For each coordinate, start with
`abs(fl(q[a]-p[a])) + 4 delta`, square and sum, enlarge by `1+16 epsilon` and
`16 eta`, and cap at 4. The larger coordinate allowance covers both
normalization errors and subtraction rounding. Thus no better or equally
distant candidate is lost through a rounded-down current best distance.
The final retained records are selected by S2 predicates, not by this bound.

The proof assumes IEEE binary64, round-to-nearest and gradual underflow, with
no reassociation or fast-math. The header checks binary64 at compile time,
rejects the common `__FAST_MATH__` mode, and checks the runtime rounding mode.
Build flags and runtime must also keep flush-to-zero/denormals-are-zero off.
These arithmetic requirements apply to S2's filters as well.

## API and upload layout

```cpp
atomos::SpatialIndex index(points, 16);
index.build(replacement_points);
auto ids = index.radius(query, squared_chord_radius); // unsorted ID set
auto nearest = index.nearest(query);                  // optional<Neighbor>
auto k = index.k_nearest(query, count);               // nearest first
const auto& nodes = index.nodes();
const auto& records = index.points();
```

`Node` contains `double lower[3], upper[3]`, four `uint32_t` fields
`left, right, begin, count`, then `double split` and `uint32_t axis`.
`count>0` identifies the leaf range `[begin,begin+count)`;
`count==0` identifies a branch. A nonempty hierarchy starts at node 0.
Children follow their parent in the flattened array. An empty index has no
nodes. Native structure padding is not a portable on-disk encoding: upload
must use the matching ABI or explicitly pack each field. Record coordinates
and IDs remain losslessly recoverable independently of the hierarchy.

`Neighbor` contains `id`, approximate `chord_distance2` and `point_index` into
the reordered records. A radius result has no promised iteration order; sort
IDs for canonical serialization or equality comparison. Empty nearest yields
`nullopt`; `k=0` yields no results and `k>size` yields all records. A failed
rebuild leaves the preceding index intact. Concurrent const queries are
independent; building concurrently with a query requires caller synchronization.

The public helpers `compare_distance`, `closer` and `distance_upper_bound`
support device candidate refinement with the same metric. They assume
already validated inputs. `QueryStats` counts visited nodes, candidate
records and calls to the S2 predicate; it does not expose S2's internal
exact-fallback count.

## Device candidate contract

The hierarchy is suitable for unfiltered integer texture fetches of packed
source words. A device can cache derived bounds and indices; texture filtering
must not interpolate the authoritative coordinate words. A float node bound
requires an outward conversion from the double enclosure, and a float query
requires an enclosure of the same source direction. A conservative device
bound needs its own floating-point error allowance; the host's binary64
constant is not a binary32 proof.

The device result is a candidate set. Inclusive radius candidates must contain
every true hit; nearest candidates must contain every point that could beat
the certified retained upper bound, including exact ties. A fixed-size
shortlist or truncated candidate buffer alone cannot guarantee this. Capacity
overflow must grow/retry or fall back to a complete host query. Final host
refinement applies the shared S2 predicates and canonicalizes ordering where
required. A new seed snapshot invalidates any bounds or device pages derived
from a previous snapshot. Cache/page allocation can grow within available
memory; recursive addressing does not create physical VRAM.

## Cost, scope and validation

Build uses median selection and scanning with expected `O(n log n)` work.
Storage is linear in points and nodes. Median splitting bounds depth below 32
for the enforced `n<2^31` domain. Query costs remain `O(n)` in adverse geometry;
radius output costs at least its result count, and k-nearest additionally
maintains a heap. Extremely tight clusters can make the conservative padding
dominate, causing a wider candidate pass. Exactness takes priority over
claiming pruning where the bound cannot establish exclusion.

The independently scanned oracle in `tests/spatial_index_tests.cpp` uses the
official S2 predicates directly. It checks exact/adjacent-ULP boundaries,
antipodes, duplicate coordinates with distinct IDs, norm aliases, signed zero,
subnormal coordinate components, empty/invalid inputs, rebuild atomicity,
flattened hierarchy coverage and mixed global/tightly clustered random data.
The native Release executable
`C:/aTOMosBuild/r15cuda/Release/spatial_index_tests.exe` was run on 2026-09-15:
exit code 0, `spatial_index_tests: PASS (34633 checks)`, approximately 1.58 s
wall time. This is evidence for the stated finite test suite, not an exhaustive
enumeration of binary64 inputs. A benchmark against S2 must report
the same source seeds, metric, inclusion and tie rules, workload, hardware,
threading, and build flags, with build, transfer, query and exact-refinement
times separately accounted for.

For ground-station applications this index can accelerate angular candidate
selection or known-scene access. The R14 state, frame, gravity, proper/coordinate
time and two-event light-time equations still determine the physical satellite
position and observed direction. Faster exact queries on a chosen finite seed
set do not improve an ephemeris, clock estimate or measurement uncertainty.
