# TOM World & Query Kernel 0.4.1 — Corrective Rebuild

## Open-segment exact event continuation based only on corrected 0.3

**Normative profile:** `TOM-WORLD-QUERY-KERNEL-0.4-REBUILT`  
**World schema:** `TOM-WORLD-PIECEWISE-CONTINUATION-0.4.1`  
**Implementation namespace:** `tom_world04r`  
**Underlying interval certifier:** corrected TOM WQK 0.3  
**Underlying execution ABI:** TOMAGI 1.0  
**Release date:** 2026-09-01

## 1. Status

This document supersedes the previous 0.4.0 continuation profile. The earlier package is not an authority for this release and no earlier 0.4 source file is an upstream input.

The only 0.4 inheritance root is the corrected 0.3 archive:

```text
SHA-256 a7103ec92596fd54198e4a902f078712cf8eafcdf1e45320bbdc02dd53947278
bytes   22,217,713
entries 10,291
```

The corrected inherited interval source is pinned as:

```text
src/python/tom_world03/interval.py
SHA-256 ea7b3ff2127e8ee7a696eb45e84ae9efdbca7c10c532617c51888fb13cd39f6d
```

The pre-correction hash `d6bef5b9704a3e5444d86b76e73f6b90a51fdbbf624a6c4705ed0bc7cdef9d4b` is explicitly rejected.

The terms **MUST**, **MUST NOT**, **REQUIRED**, **SHOULD**, and **MAY** are normative.

## 2. Purpose

Version 0.3 certifies exact rational zero crossings on a single affine trajectory. Version 0.4.1 adds a deterministic world-transition loop in which accepted simultaneous event sets change state and rates, produce the next affine continuation, and are persisted with lineage.

The corrective design has one central rule:

> A future segment boundary MUST be a result of the certified next-event query. It MUST NOT be supplied as relation metadata or copied from a pre-authored expected trajectory.

## 3. Trust correction and noncompounding architecture

### 3.1 Rejected circular pattern

The superseded line allowed a relation to carry `continuation_until` and required an accepted event to equal the current segment's predeclared end. That conflates a query result with a source assumption. Once used as a successor start, an incorrect boundary can compound through all later state evaluations.

A conforming 0.4.1 relation therefore MUST NOT contain `continuation_until`.

### 3.2 Open continuation segment

An open segment is an immutable exact affine trajectory valid on:

```text
I_s = [t_s, H]
```

where `t_s` is the segment start and `H` is the declared world horizon. It contains:

```text
id
sequence
domain = [start, horizon]
start_state
rates
fired_relations
parent_segment_hash
source_event_set_hash
source_transition_hash
provenance
content_hash
```

For field `x`:

```text
x(t) = x_s + v_x (t - t_s)
```

The initial segment has sequence zero, no parent/event/transition hashes, no fired relations, and a domain equal to the complete world horizon. Every successor has all three causal hashes, starts at the certified event time, and again extends to `H`.

### 3.3 Realized segment seal

The open segment is not mutated when an event occurs. A separate immutable seal records its realized prefix:

```text
[t_s, t*]
```

The seal binds the open segment hash, exact end time, end state, accepted event-set hash, and transition hash. The final seal binds the horizon and has no event or transition.

## 4. Canonical seed and fixed TOMAGI substrate

The authoritative TOM seed remains exactly 244 ASCII bytes, no terminal newline, with SHA-256:

```text
d1417a3136772c0cf3eddcd4962ce07d42cbf87616f7b5bae09fc652d9b807b5
```

TOMAGI 1.0 remains unchanged:

| Object | Size |
|---|---:|
| program header | 128 bytes |
| `State64` | 64 bytes |
| `Cell48` | 48 bytes |
| hot opcodes | 16 |

The 0.4.1 world/query layer does not add an opcode or modify the binary transition algebra.

## 5. Corrected exact rational and interval semantics

All certified times, states, rates, residuals, and bounds use reduced rationals:

```text
q = (num, den), den > 0, gcd(|num|, den) = 1
```

Closed intervals are `[lower, upper]` with `lower <= upper`. Arithmetic is exact. Sign classification compares full normalized rational values against `Q(0)`. The implementation MUST use the pinned corrected 0.3 interval file.

Binary floating point MUST NOT enter the certified continuation path.

## 6. World record

A world validates against `spec/tom_world_piecewise_continuation_0_4_1.schema.json` and contains:

```text
schema
profile
seed_sha256
corrected_v03_baseline
horizon
initial_segment
supports
compatibilities
relations
interval_index
solver
persistence
provenance
content_hash
```

The top-level content hash and every nested support, compatibility, relation, segment, and index hash MUST verify through canonical JSON.

The provenance record MUST say:

```json
{
  "base_archive_sha256": "a7103e...7278",
  "prior_v0_4_used_as_source": false,
  "implementation_namespace": "tom_world04r"
}
```

## 7. Continuation relation

Each relation is a content-addressed `piecewise-continuation-relation` with:

```text
relation_interface = SDF0@Def
domain = piecewise-affine-open-segment
codomain = exact-rational-residual
zero_locus
priority
expression
support_id
compatibility_id
active_time
event_id
fire_policy = once
transition
rate_transition
provenance
content_hash
```

The expression language is the corrected 0.3 finite continuous relation language: exact constants, time, affine trajectory fields, negation, addition, subtraction, and multiplication. Continuation requires that the selected expression linearize affinely on the current segment. A nonaffine expression or an identically zero relation is unresolved and MUST reject rather than invent an ordering.

A once-only relation is inserted into `fired_relations` after acceptance and MUST be excluded from later candidate sets.

## 8. Support and compatibility

Support and compatibility precede event acceptance.

For interval indexing, a support or compatibility posting may be removed only when exact state-interval evidence proves it impossible throughout the query bracket. Ambiguous gates remain candidates and are tested at the certified root. This provides a no-false-negative filter.

At an exact root `t*`:

```text
support(state(t*)) = true
compatibility(state(t*)) = true
```

are REQUIRED for acceptance.

## 9. Immutable interval candidate index

The content-addressed index contains one entry per relation, sorted by:

```text
(active_lower, active_upper, relation_id, relation_hash)
```

It also contains postings by support and compatibility ID. The complete index MUST rebuild byte-identically from the relation set.

For query bracket `[a,b]`, interval selection keeps entries satisfying:

```text
active_lower <= b
active_upper >= a
```

then applies only sound support/compatibility impossibility filters and the exact fired-relation exclusion.

An exhaustive planner remains normative as an independent semantic comparison path. Indexed and exhaustive planners MUST return the same accepted semantic chain.

## 10. Next-event query

For current open segment `s`, search bounds `(after, before]`, and unfired relation set `R_s`, the query seeks:

```text
t* = min { t : after < t <= before,
                 relation residual is exactly zero,
                 t lies in active_time,
                 support and compatibility accept }
```

The implementation partitions the interval at exact integer boundaries, produces a complete candidate set per bracket, and invokes the corrected 0.3 crossing certifier.

For every accepted crossing, the certificate MUST bind:

```text
world hash
segment ID/hash/sequence
relation ID/hash
event ID
priority
fire policy
exact root time
corrected 0.3 source certificate and hash
state and rate transition declarations
```

The query stops at the first bracket containing accepted exact roots, selects the minimum exact root, and groups all crossings having that same reduced rational root.

## 11. Simultaneity and deterministic order

Simultaneity requires exact equality of reduced rational root times on the same open segment. Approximate bracket overlap is not sufficient.

The total order is:

```text
(root_time, priority, relation_id, event_id, relation_hash)
```

The event-set record contains the complete crossing certificates, fired-relation basis before and after, candidate plans, and content hash.

## 12. Atomic transition

All simultaneous operations read one common pre-event state/rate pair.

For each field:

- all `set` values MUST be exactly equal;
- all `add` values are summed exactly once and applied to the common pre-value;
- all `xor` values and the pre-value MUST be integers and are XOR-reduced once;
- mixed modes on one field MUST reject.

No hidden last-writer-wins rule exists.

After merging:

```text
post_state = apply(common_pre_state, merged state operations)
post_rates = apply(common_pre_rates, merged rate operations)
```

The current segment is sealed at `t*`. A successor open segment starts at `t*`, carries `post_state` and `post_rates`, extends to the unchanged world horizon, and records the event/transition/parent hashes.

## 13. Continuation loop

The engine repeats:

```text
current = initial open segment
while event set exists strictly after current.start:
    require event-set budget
    transition atomically
    seal current at solver-produced event time
    persist event set, transition, seal, successor, transaction, commit
    current = successor
seal current at world horizon after no later event
```

If the budget is exhausted before the horizon, the run MUST reject. If a candidate relation is nonaffine, identically zero, or accepted without an exact root, the run MUST reject as unresolved.

## 14. Append-only journal

The journal contains:

```text
seed.bin
store.json
objects/
transactions/
commits/
HEAD
```

Only `HEAD` is mutable. Publication order is:

```text
event-set/final seal
transition
segment seal
successor segment
transaction
commit
HEAD
```

The chain begins with one genesis commit, continues with event commits, and ends with exactly one finalization commit.

A strict audit MUST re-read and hash-verify every reachable world, segment, event set, corrected 0.3 crossing, transition, seal, transaction, and commit. It MUST verify sequence, parent, world, current-segment, state/rate, exact-time, and fired-relation linkages. Missing objects, changed bytes, cycles, invalid ancestry, duplicate finalization, or orphans under strict policy invalidate the store.

Reconstruction MUST reproduce the same semantic-chain hash as direct execution.

## 15. Independent trusted baseline

The package includes a separate exhaustive implementation based only on Python's standard-library `fractions.Fraction`. It does not import `tom_world03` or the 0.4.1 kernel.

It independently:

1. linearizes expressions;
2. finds exact roots;
3. applies active-time, support, and compatibility tests;
4. sorts and groups event sets;
5. merges transitions;
6. produces successor trajectories; and
7. constructs the canonical semantic chain.

The baseline and kernel MUST return the same semantic-chain SHA-256 for the canonical fixture.

## 16. TOMAGI anchor program

A separate literal TOMAGI program represents integer-time anchors with:

```text
rho = 2*x
tick = time
```

Its 15-cell program contains `KIN2`, `SET`, and `HALT` cells. It reproduces anchors:

```text
time 0..10
rho  0,2,4,8,12,16,10,4,5,6,6
```

The same `.tmg` MUST yield equal full Python and C traces. This anchor does not change or approximate the exact rational event certificates; it confirms compatibility with the frozen execution substrate at integer points.

## 17. Canonical corrective fixture

The world horizon is `[0,10]`. Initially:

```text
x(0)=0, x'=1
clock(0)=0, clock'=1
mode=1, counter=0, output=0
```

Eight core relations form four simultaneous event sets:

| Time | Common pre-state condition | Post rate for x | Counter increment | Mode/output |
|---:|---|---:|---:|---|
| 2 | `time=2` and `x=2` | 2 | 1+2 | 2 / 20 |
| 5 | `time=5` and `x=8` | -3 | 2+3 | 3 / 50 |
| 7 | `time=7` and `x=2` | 1/2 | 4+5 | 4 / 70 |
| 9 | `time=9` and `x=3` | 0 | 8+9 | 5 / 90 |

The realized segments are discovered as:

```text
[0,2]  x'=1
[2,5]  x'=2
[5,7]  x'=-3
[7,9]  x'=1/2
[9,10] x'=0
```

Final state:

```text
clock=10, counter=34, mode=5, output=90, x=3
```

There are 1,200 decoy relations for candidate-index validation. The authoritative semantic-chain hash is:

```text
sha256:9fd4f3e1ae8550ae3ca99e27e7bf61b22a4935fe764fd443723abfdb3804f226
```

Recorded aggregate candidate work is 796 for the indexed route and 12,046 for exhaustive enumeration. These are deterministic implementation counters, not a universal timing claim.

## 18. Deterministic rejection conditions

A conforming implementation MUST reject at least:

- wrong canonical seed or corrected-base identity;
- use of the rejected interval implementation hash;
- bad content hash at any authority boundary;
- `continuation_until` in a relation;
- initial segment not spanning the complete horizon;
- successor segment without all causal hashes;
- relation lacking `SDF0@Def`, exact residual codomain, support, compatibility, or once-only policy;
- malformed or inverted rational interval;
- invalid or non-reproducible interval index;
- nonaffine or identically zero continuation relation;
- accepted crossing lacking an exact root;
- event time at or before the successor start;
- once-only relation refire;
- unequal simultaneous sets, mixed modes, or fractional XOR;
- event-set budget exhaustion;
- stale journal parent, missing object, mutated immutable bytes, commit cycle, event after finalization, or strict orphan; and
- TOMAGI ABI or Python/C trace mismatch.

## 19. Determinism and noncompounding theorem

For fixed canonical seed, corrected 0.3 implementation, world, open segment, index, query bounds, budgets, and planner, all conforming implementations produce the same accepted exact event set, transition, successor, journal transaction, and semantic chain.

The result follows because:

1. all authority records are canonical and content-addressed;
2. rational and interval arithmetic is exact and pinned to the corrected implementation;
3. candidate filtering may remove only exact impossibilities;
4. exact affine roots are unique algebraic values;
5. simultaneity and ordering use total exact keys;
6. transition merge has explicit conflict rules;
7. the successor start is exactly the accepted event time; and
8. the successor upper bound remains the fixed horizon.

A source boundary error cannot be copied into the successor because no relation can author that boundary. An implementation error can still occur, but it must disagree with the exhaustive route, independent baseline, content-addressed journal reconstruction, or clean replay rather than silently becoming a source premise for the next segment.

## 20. Evidence boundary

This release demonstrates an exact finite piecewise-affine rational profile. It does not claim arbitrary nonlinear integration, transcendental interval arithmetic, approximate simultaneity, autonomous learning, cognitive memory, general planning, grounded perception, autonomous action, physical GPU dispatch, or AGI.

The next research milestone may begin learner work only after preserving the corrected-base pin, open-boundary rule, exact event certificates, explicit promotion transactions, and independent holdout evaluation.
