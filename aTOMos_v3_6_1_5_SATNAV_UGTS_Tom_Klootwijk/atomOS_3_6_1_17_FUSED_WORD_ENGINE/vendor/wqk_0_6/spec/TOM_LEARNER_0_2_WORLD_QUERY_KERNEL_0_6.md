# TOM Learner 0.2 / World & Query Kernel 0.6

## Finite typed hypothesis-family authority

**Release:** 0.6.0  
**Learner profile:** `TOM-LEARNER-0.2-FAMILY-AUTHORITY`  
**Promotion profile:** `TOM-LEARNER-0.2-PROMOTION-AUTHORITY`  
**Continuation plan:** `TOMAGI-IMMUTABLE-PUBLICATION-PLAN-1.1`  
**Underlying machine:** TOMAGI ABI 1.0  
**Validation revision:** 2026-09-03

## 1. Purpose and authority boundary

This specification advances TOM Learner 0.1 from one exact affine family to a finite typed family registry. It does not weaken the corrective authority rule established by WQK 0.5.1 and 0.5.2:

```text
formal authority
!= independent oracle
!= mechanical host service
```

The formal authority owns candidate membership, candidate semantics, train-only selection, validation and holdout gates, ambiguity, counterexamples, contradiction records, supersession, regression-impact evidence, acceptance/rejection, and the complete parent-bound publication plan.

The independent oracle may falsify that authority but cannot publish. The host may parse, verify, evaluate a bounded formal program, compile to `Cell48`, execute TOMAGI, authenticate traces, materialize bytes, persist addressed records, and compare-and-swap `HEAD`. It may not silently choose a family, break a tie, waive a counterexample, or decide what becomes authoritative.

## 2. Corrective prerequisite

WQK 0.6 incorporates the CODEX WQK 0.5.2 kernel-repair handoff as a required source boundary. Before family expansion, a conforming release must demonstrate:

1. defined C arithmetic intermediates followed by explicit 32-bit wrapping;
2. rejection of nonzero values in all six reserved TOMAGI header words;
3. a same-host thread/process publication lock spanning expected-HEAD read, immutable verification, and atomic replacement;
4. recursive formal-result limits enforced before a parent consumes the value;
5. reproducible package construction from pinned authority sources, with volatile transcripts and previous inventory products excluded; and
6. documented CLI argument order equal to the public parser.

This release preserves those behaviors and adds regression tests. The lock coordinates ordinary processes on one host. Distributed writers and mixed Windows/WSL access to one shared store remain unsupported.

## 3. Canonical root and ABI

The canonical seed remains the exact 244-byte ASCII file `TOM_seed_genome_2026-09-01.txt`, without a terminal newline:

```text
sha256:d1417a3136772c0cf3eddcd4962ce07d42cbf87616f7b5bae09fc652d9b807b5
```

TOMAGI ABI 1.0 remains fixed:

| Record | Size |
|---|---:|
| Program header | 128 bytes |
| `State64` | 64 bytes |
| `Cell48` | 48 bytes |
| Opcode count | 16 |

No learner family consumes a new hot opcode. Family semantics are content-addressed formal definitions evaluated before generic `EMIT` lowering.

## 4. Family registry

The authoritative registry is `examples/learner06/family_registry.json` and validates under `spec/tom_learner_family_registry_0_6.schema.json`.

A registry record contains:

```text
schema
id
seed_sha256
partition_policy_hash
family_order[]
families[]
content_hash
```

Each family contains:

```text
id
semantic_version
kind
domain
codomain
search_budget
candidate_order
candidates[]
content_hash
```

Every candidate is itself content-addressed. In the canonical profile every
family declares `candidate_order = literal-registry-order`; the addressed array
is therefore the executable order. The finite registry is the search space; an
implementation may not synthesize a candidate from validation or holdout
targets.

The canonical registry contains four families and 121 candidates:

| Family | Candidate count | Bound |
|---|---:|---|
| Exact polynomial | 34 | degree at most 2 |
| Piecewise affine | 21 | at most two affine segments |
| Transition table | 27 | complete table over `A`, `B`, `C` |
| Expression tree | 39 | declared operations, complexity at most 5 |

The canonical profile requires `max_candidates` to equal the literal candidate
count. A budget-only rehash or any budget/count mismatch rejects rather than
widening, truncating, or sampling the search space. A coordinated valid registry
change receives a different authority address and is not a replay of this
canonical release.

## 5. Exact values and observations

Numeric values use reduced exact rationals:

```json
{"num": n, "den": d}
```

where `n` and `d` are integers, `d > 0`, `gcd(|n|,d)=1`, and zero is represented as `0/1`. Symbolic transition-table values are finite strings.

An observation contains:

```text
schema = TOM-LEARNER-0.2-OBSERVATION-1.0
id
input
target
source
content_hash
```

A data set contains an ordered observation array, an eligible-family list, and explicit ordered train/validation/holdout ID lists. The partition-assignment record contains IDs and policy identity but no target values.

All observation IDs must be unique. Partition lists must be internally unique,
mutually disjoint, and cover every observation exactly once. Resolution maps
over the declared partition ID list, preserving that order; each referenced ID
must resolve to exactly one observation.

## 6. Candidate semantics

### 6.1 Bounded exact polynomial

For coefficients `(c0,c1,c2)`:

```text
P(x) = c0 + c1*x + c2*x^2
```

All operations are exact rational operations. Complexity is the highest nonzero degree plus one under the canonical profile.

### 6.2 Bounded piecewise affine

For exact breakpoint `b`:

```text
F(x) = aL*x + cL   when x <= b
       aR*x + cR   when x >  b
```

The boundary convention is part of the family law. A different convention requires a new family version.

### 6.3 Finite transition table

A candidate contains one output for every declared input symbol. Prediction succeeds only when exactly one entry matches the input.

### 6.4 Bounded expression tree

The canonical operation registry is:

```text
x, const, neg, abs, square, add, sub, mul
```

The source registry limits depth and complexity. The evaluator validates the
closed tree grammar before prediction and rejects undeclared operations or
excessive depth; there is no fallback operator. Exact, reduced,
positive-denominator rationals remain the only numeric representation.

## 7. Train-only derivation and selection

For data set `D` and registry `G`:

1. resolve only the literal candidates in families listed by `D.eligible_families`;
2. resolve training observations only from `D.partitions.train`;
3. evaluate every eligible candidate in declared order;
4. retain a candidate only when it exactly matches every training observation;
5. record every surviving candidate hash; and
6. select a candidate only when the survivor count is exactly one.

The derivation evidence records:

```text
training observation IDs
eligible family IDs
family-registry hash
fit-input hash
survivor hashes
```

The fit-input hash excludes validation and holdout target bytes. A same-ID mutation of a validation or holdout target must preserve the split, fit-input hash, survivor list, and selected training candidate while it may change final acceptance.

## 8. Ambiguity

When more than one distinct candidate survives training, the result is not resolved by candidate order, lower complexity, family priority, or host iteration order. It is rejected with an addressed ambiguity record:

```text
dataset_id
candidate_hashes[]
resolution = reject-without-hidden-tie-break
content_hash
```

A later profile may introduce an explicit ambiguity policy, but that policy must itself be formal authority and versioned.

## 9. Validation, holdout, contradiction, and counterexamples

A uniquely selected candidate is checked against validation observations and then untouched holdout observations. Every mismatch produces an addressed counterexample naming the partition and observation hash.

Contradictions are explicit evidence. Two observations with equal typed input and unequal typed target produce an addressed contradiction record. Contradictions do not disappear because one family lacks a fitting candidate.

The canonical decision-reason order is:

```text
multiple survivors        -> ambiguous-train-survivors
zero survivors            -> no-exact-train-candidate
contradiction              -> contradiction
validation mismatch        -> validation-counterexample
holdout mismatch           -> holdout-counterexample
regression-impact failure  -> regression-impact
otherwise                  -> accepted
```

This ordering is literal profile behavior and may not be silently rearranged.

## 10. Termination certificate

Each data-set result contains a termination certificate with:

```text
dataset_id
candidate_count
evaluated_count
completed
content_hash
```

A conforming result requires `completed = true` and exact equality of evaluated and declared candidate counts. No stochastic early stopping, beam truncation, or approximate search is part of this profile.

## 11. Supersession and regression impact

A data set may name one previously authoritative definition hash in `supersedes`. The hash must resolve in the pinned prior-authority record. A successful proposal receives an addressed supersession record.

The regression-impact certificate evaluates the selected replacement against the pinned regression cases of the definition it supersedes. Other prior definitions are checked against their own pinned models and cases. The certificate records each case and an `all_pass` result.

This is a finite regression boundary, not a proof of universal behavioral preservation. A broader integration suite requires a new versioned record.

No proposal is accepted when:

- the named prior definition is absent;
- any pinned replacement case fails; or
- the regression certificate is incomplete.

## 12. Learned definition

An accepted candidate becomes a proposed typed definition carrying:

```text
schema = TOM-LEARNER-0.2-HYPOTHESIS-DEFINITION-1.0
id
kind = family ID
domain
codomain
model
relation_interface = SDF0@Def
zero_locus
supersedes
provenance
content_hash
```

The learned definition is still non-authoritative until the separate promotion formal program produces and publishes its transaction.

## 13. Promotion continuation

WQK 0.6 does not create a new unrelated world. Its promotion plan is a `1.1` continuation whose `initial_head` is the terminal head of repaired WQK 0.5.2.

The plan includes:

```text
store descriptor
initial_head
base_records[]
publications[]
terminal_head
content_hash
```

The canonical publication sequence continues at 20 and ends at 35. Each of the sixteen data sets creates exactly one publication, accepted or rejected.

Every publication contains:

```text
expected_head
replacement_head
sequence
required_hashes[]
writes[]
content_hash
```

Required evidence includes the prior authority, partition policy, repair proof,
promotion context, registry, data set, learner result, data-set result row,
decision, derivation evidence, termination certificate, regression certificate,
and accepted definition or rejection lineage. The publication itself is
content-addressed.

## 14. Store mechanics and same-host CAS

The generic immutable store:

1. acquires a same-host inter-thread and inter-process lock;
2. reads the current `HEAD` while holding the lock;
3. rejects unless it equals the publication's expected head;
4. writes immutable canonical records;
5. scans addressed records and verifies every required hash;
6. verifies that the replacement commit exists in the head namespace;
7. atomically replaces `HEAD`; and
8. releases the lock.

Two contenders using the same expected head cannot both report success on one supported host. An abnormal publisher exit must release the operating-system lock.

The lock is not a distributed consensus protocol. Multi-host concurrent writers and mixed Windows/WSL writers to one shared store remain outside the supported profile.

## 15. Formal programs and TOMAGI execution

Two static formal programs are authoritative:

```text
learner06_family_authority.formal.json
learner06_promotion_authority.formal.json
```

Each is loaded as a content-addressed source by a seeded definition graph, evaluated under bounded formal limits, canonically encoded, lowered to an `EMIT` cell graph, compiled to `.tmg`, and executed by Python and C.

The formal program is a separate `formal.evaluate` dependency and MUST NOT be
included in its own named input sequence. The learner input sequence is exactly:

```text
family registry
partition policy
sixteen data sets in dataset-bundle order
prior 0.5.2 authority
repair handoff proof
```

Before evaluating any row, the learner program validates exact record shapes,
all mutable registry and data-set nested hashes, the top-level addresses and
fixed identities of pinned prerequisite records, the canonical seed, the closed
family/candidate profiles, canonical rationals, global IDs and hashes, partition
coverage/order, assignment identity, and eligible-family resolution.

The promotion input sequence is exactly:

```text
learner result
prior 0.5.2 authority
family registry
partition policy
repair handoff proof
promotion context
data-set bundle
```

Promotion validates those contracts and binds the exact learner program hash,
named input-set hash, learner-result hash/value, repaired parent, registry,
bundle, context, data-set order, result-row order, and corresponding data-set
hashes. A self-consistent rehash does not authorize a changed input.

The materializer authenticates every supplied trace row against deterministic replay before consuming any payload. Equal Python/C full traces and equal ordered EMIT sequences are required.

The current canonical boundaries are recorded in:

```text
validation/learner06/learner_authority_proof.json
validation/learner06/promotion_authority_proof.json
```

Those records, rather than this narrative, are the result authority.

## 16. Formal-value budget repair

Every recursively evaluated formal result is checked immediately against:

```text
max collection items
max value nodes
max canonical bytes
```

The check occurs before a parent expression consumes or discards the child. Fold accumulators are checked after every iteration. A large intermediate cannot evade limits merely because the root later returns a small value.

## 17. Runtime, loader, and GPU parity repairs

The C runtime performs potentially overflowing signed arithmetic in defined wider intermediates and then lowers explicitly with `wrap32`. It does not rely on C signed-overflow behavior. Extreme `i32` tests compare complete Python/C traces.

Both Python and C loaders require all six reserved 32-bit header words at bytes 40 through 63 to be zero. A nonzero value in any word is a format error.

Direct in-memory `Program` construction applies the same opcode range,
successor range, entry, and tick validation as persisted `.tmg` loading. Seeded
`State64`, legacy `Cell48`, and header fields are narrowed according to their
declared signed/unsigned widths; `default_ticks` is an unsigned 32-bit value and
is rejected before serialization when out of range.

Formal `eq` and `ne` use type-strict canonical structural equality for JSON
values while retaining exact rational equality for numeric operands. In
particular, a boolean is not equal to an integer.

The WGSL, GLSL, and OpenCL kernels implement the CPU equations without relying
on overflow-prone signed intermediates for `PHI`, `TIME`, `CONE`, `SPHERE`,
`JIT1`, `KLEIN`, or `LSYS`, and defensively reject `RADIX` shift domains outside
0 through 63. Source-level contract validation and integer-vector parity are
required; this release does not claim physical GPU dispatch evidence.

## 18. Deterministic rejection conditions

A conforming implementation rejects or records an authoritative rejection for at least:

- wrong seed identity;
- malformed or nonreduced rational;
- registry, family, candidate, observation, data-set, program, or proof hash mismatch;
- undeclared family or expression operation;
- candidate-count/budget mismatch;
- missing, duplicate, overlapping, or unresolved partition membership;
- zero training survivors;
- multiple distinct training survivors;
- validation or holdout counterexample;
- contradictory observations;
- missing superseded authority;
- regression-impact failure;
- incomplete termination certificate;
- stale continuation parent, context, learner result, input set, registry, or data-set order;
- missing base commit or required evidence;
- noncontiguous publication sequence;
- forged execution trace;
- nonzero reserved header word;
- nonfinite canonical JSON; and
- intermediate formal value-node or byte-budget overflow.

## 19. Independent oracle

`src/python/tom_learner06/oracle.py` is a separately implemented falsification oracle using `fractions.Fraction` and ordinary finite enumeration. It does not import `tomagi.formal` and does not reuse the formal expression tree.

Agreement is required for:

```text
accepted/rejected result
reason
candidate count
survivor hashes
selected candidate hash
fit-input hash
validation and holdout failures
contradiction count
regression result
supersession target
```

Oracle agreement does not grant publication authority.

## 20. Determinism and replay theorem

For fixed canonical seed `g`, repaired kernel `K`, registry `G`, partition
policy `Q`, ordered data sets `D`, prior authority `A`, repair proof `H`, formal
programs `P`, promotion context `C`, data-set bundle `U`, learner result `L`, and
finite limits `B`:

```text
formal_result(g,K,G,Q,D,A,H,P,B)
compiled_TMG(...)
Python_trace(...)
C_trace(...)
materialized_bytes(...)
promotion_plan(g,K,G,Q,D,A,H,P,C,U,L,B)
store_terminal_head(...)
```

are uniquely determined under this profile.

The proof follows from exact seed bytes, canonical JSON, verified content hashes, literal candidate order, finite enumeration, exact rational arithmetic, explicit ambiguity rejection, fixed promotion order, fixed-width TOMAGI execution, trace authentication, immutable writes, and parent-bound CAS publication.

A release claim additionally requires two generated-output-free builds to reproduce all declared boundaries and the promotion-store tree, followed by deterministic ZIP construction and archive replay.

## 21. Canonical fixture acceptance

The canonical fixture contains sixteen data sets:

- nine accepted exact models across all four families;
- three explicit ambiguity rejections;
- one validation counterexample;
- one contradictory table with no exact candidate;
- one supersession regression-impact rejection; and
- one target outside the finite polynomial search space.

Expected aggregate result:

```text
families:          4
candidates:      121
data sets:        16
accepted:          9
rejected:          7
ambiguities:       3
false promotions:  0
```

The benchmark is evidence for this finite registry only. It is not evidence of noisy-data robustness, open-domain induction, broad transfer, perception, planning, autonomous action, general intelligence, or AGI.

## 22. CLI contract

```bash
PYTHONPATH=src/python python3 -m tom_learner06 oracle \
  examples/learner06/family_registry.json \
  examples/learner06/prior_authority.json \
  examples/learner06/datasets/*.json

PYTHONPATH=src/python python3 -m tom_learner06 validate-plan \
  validation/learner06/promotion_authority.materialized.json

PYTHONPATH=src/python python3 -m tom_learner06 apply-plan \
  validation/learner06/promotion_authority.materialized.json \
  TOM_seed_genome_2026-09-01.txt \
  /tmp/tom-learner06-store

PYTHONPATH=src/python python3 -m tom_learner06 audit-store \
  validation/learner06/promotion_authority.materialized.json \
  /tmp/tom-learner06-store
```

The `audit-store` order is `SOURCE STORE`, matching the parser.

## 23. Remaining boundary and next milestone

WQK 0.6 remains exact and finite. Candidate lists are authored registry data; it does not discover arbitrary syntax, learn from noisy measurements, calibrate uncertainty, or perform open-domain concept formation.

The version-1 `.tmg` header does not serialize the source compiler's
`max_output_bytes` budget. Consequently, an authenticated legacy graph that
intentionally loops over non-halting `EMIT` cells can materialize repeated bytes
beyond that source-only ceiling. Inferring a ceiling from unique cell payloads
would break valid loop semantics. A hard runtime ceiling therefore requires a
versioned header/profile field or an authenticated caller policy; all artifacts
in this release use a final halting `EMIT` cell.

The next permitted milestone is **TOM Learner 0.3 / WQK 0.7 — noisy evidence**. It may introduce typed observation intervals, explicit noise assumptions, calibration records, and confidence certificates. Confidence must remain explicit evidence and must not silently alter TOMAGI opcode semantics or bypass the 0.5.2/0.6 promotion authority.
