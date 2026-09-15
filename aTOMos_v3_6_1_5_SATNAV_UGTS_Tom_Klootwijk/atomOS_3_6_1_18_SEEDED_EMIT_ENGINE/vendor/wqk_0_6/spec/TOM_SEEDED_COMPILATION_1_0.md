# TOM Seeded Compilation and Formal Evaluation Profile 1.0

Status: normative corrective specification  
Profile identifier: `TOM-SEEDED-COMPILATION-1.0`  
TOMAGI binary ABI: `1.0`  
Initial publication: 2026-09-02  
Validation revision: 2026-09-03

## 1. Scope and authority

This specification defines the complete source-to-bytes meaning of the seeded
compilation profile. It is additive to the frozen TOMAGI 1.0 `Cell48` runtime:
it does not add an opcode, widen a cell, change an existing transition, or
reinterpret a legacy program.

The authoritative causal chain is:

```text
canonical seed genome
+ registered literal source records
+ content-addressed definition graph
+ bounded formal program, when selected
-> validated dependency evaluation
-> deterministic Cell48 lowering
-> ordered TOMAGI execution
-> authenticated EMIT trace
-> materialized bytes
```

Compiler reports, traces, and validation reports are evidence about that chain.
They do not replace any member of the chain. A `.tmg` file alone contains the
runtime program, not the complete source registry; provenance claims therefore
MUST name and hash the source document and compile report as well as the binary.

## 2. Canonical seed genome

The only seed accepted by this profile is the 244-byte ASCII file
`TOM_seed_genome_2026-09-01.txt`, with no terminal CR or LF and SHA-256:

```text
d1417a3136772c0cf3eddcd4962ce07d42cbf87616f7b5bae09fc652d9b807b5
```

Its exact text is:

```text
TOM1[TopologicalOpenModular]|TomKlootwijk|1990-07-10|NL200678942|2026-09-01|LUTlogp^{Klein,SDF0@Def}(rho,theta,t->;phi,dt,d2,J,v,a,j1)>P1>L2_BST^b>ASweepCone(T,apex)>Pi[pyrSide,circle,sphere]>support>compatibility>guard>event>transition>lineage
```

The grammar identifier is exactly `TOM-SEED-GRAMMAR-1.0`. For this finite seed,
lexical tokens are maximal substrings matching `[A-Za-z][A-Za-z0-9_]*`.
Punctuation is literal and does not form a token. A definition's `seed_tokens`
MUST be distinct exact tokens in the canonical registry, and every registered
token marked present MUST occur in the lexical tokenization. Substring matches
are forbidden.

The token registry is itself canonical JSON, content-addressed with `content_hash`
removed before hashing, and MUST bind all of:

- registry ID `TOM-SEED-TOKEN-REGISTRY-1.0`;
- grammar ID `TOM-SEED-GRAMMAR-1.0`;
- the canonical seed SHA-256; and
- the exact registered token list.

## 3. Canonical JSON and content addresses

Canonical JSON is UTF-8 JSON produced with keys sorted lexicographically,
no insignificant whitespace, `ensure_ascii=false`, and separators `,` and `:`.
Non-finite numbers (`NaN`, positive infinity, and negative infinity) are
forbidden. A content-addressed record has:

```text
content_hash = "sha256:" + lowercase_hex(
  SHA256(canonical_JSON(record with content_hash removed))
)
```

Booleans are not integers. Where an integer field permits a string, that string
is parsed by Python/C-style base autodetection (`0x` hexadecimal and decimal are
the forms used by this package) and then checked against the stated range.

## 4. Seeded source document

A seeded source is one JSON object with only these fields:

```text
$schema? title?
tomagi_version compilation_profile seed_genome
root_definition budgets definitions
```

`tomagi_version` MUST be `1.0.0`; `compilation_profile` MUST be
`TOM-SEEDED-COMPILATION-1.0`; and `root_definition` MUST be a non-empty ID.
`seed_genome` contains only `path`, `bytes`, `sha256`, `grammar_id`, and
`token_registry`, each exactly bound as specified above. Unknown fields reject.

The eight required positive integer budgets are:

```text
max_definitions
max_cells
max_output_bytes
max_sequence_items
max_repeat
max_expression_depth
max_expression_nodes
max_string_bytes
```

No operation may relax a document budget. A definition may repeat any subset
in its `limits` object only with a positive value less than or equal to the
document value. Limits apply to the definition's parameters, provenance,
strings, sequences, constructed graph, output, and formal evaluation as
appropriate. `max_repeat` is reserved for bounded versioned operations; no
operation in this version performs an implicit repeat.

## 5. Definition records and evaluation order

Every definition contains only:

```text
id kind domain codomain dependencies phase order
operation parameters limits provenance seed_tokens? content_hash
```

All required strings are non-empty. `dependencies` and `seed_tokens` are
duplicate-free arrays. `operation` contains only `op`. `parameters`, `limits`,
and non-empty `provenance` are objects. The definition content hash MUST verify
before its operation is evaluated.

Phases have the following strict rank:

```text
parse < normalize < resolve < construct < transform < support
      < compatibility < guard < event < transition < lineage
```

The pair `(phase rank, order)` MUST be unique. Every dependency MUST exist and
have a strictly smaller pair. Cycles, missing dependencies, duplicate IDs, and
ambiguous phase/order slots reject. Evaluation selects the transitive closure
of `root_definition` and visits it in the unique stable order
`(phase rank, order, id)` subject to dependencies. Unselected definitions are
still shape-, hash-, token-, order-, and budget-validated; their operations are
not evaluated.

The nominal domain declares the exact dependency value signature. Version 1.0
uses `bytes`, `string`, `bool`, `i32`, `u32`, `record`, `sequence`, `state64`,
`cell_graph`, and `program` as compiler value types. A domain-signature mismatch
rejects before operation evaluation.

## 6. Seeded definition operations

Operation names, kinds, codomains, parameter fields, and meanings are closed.
An unknown operation, kind, codomain, domain, or parameter rejects.

### 6.1 `seed.bytes`

- kind: `canonical-seed`
- domain: `none` (no dependencies)
- codomain: `bytes`
- parameters: empty

Produces the exact validated 244 seed bytes.

### 6.2 `seed.tokens`

- kind: `seed-parse`
- domain: `bytes`
- codomain: `record`
- parameters: empty

Its sole dependency MUST equal the canonical seed bytes. It produces the exact
grammar ID, byte count, bare SHA-256, and ASCII text record.

### 6.3 `literal`

- kind: a non-empty string beginning `literal-`
- domain: one declared fixed signature
- codomain: the declared literal result type
- parameters: exactly `result_type`, `value`

Supported result types are `bytes`, `string`, `bool`, `i32`, `u32`, and
`record`. Byte encodings are UTF-8, ASCII, hexadecimal, or validated base64.
The direct or encoded `data` string carrying a byte literal is representation
overhead and is exempt from `max_string_bytes`; its decoded bytes are instead
bounded by `max_output_bytes`. Encoding labels, parameter keys, ordinary string
values, and strings nested in records remain subject to `max_string_bytes`.
Records MUST contain finite JSON. Integer narrowing uses the TOMAGI 32-bit
rules. Size limits apply before the value is exposed to dependants.

### 6.4 `source.json`

- kind: `literal-json-source`
- domain: `seed-record` (one record dependency)
- codomain: `record`
- parameters: exactly `path`, `bytes`, `sha256`, `canonical_newline`,
  `verify_content_hash`

This is a generic, content-addressed literal input—not a domain adapter.
`path` MUST be relative to and resolve within the directory containing the
seeded source document. Absolute paths, traversal outside that directory,
missing files, non-UTF-8, non-object JSON, wrong byte length, and a digest other
than the exact lower-case `sha256:<64 hex>` declaration reject.

When `canonical_newline` is true, source bytes MUST equal canonical JSON plus
one LF. When `verify_content_hash` is true, the parsed object MUST carry and
verify its generic content address. The compile report records the normalized
relative path, byte length, and SHA-256. In-memory compilation without an
explicit source root rejects this operation.

### 6.5 `sequence.construct`

- kind: `record-sequence`
- domain: `record-sequence`
- codomain: `sequence`
- parameters: empty

Requires at least one dependency, all of type `record`, and returns their
values in declared dependency order. It does not sort or deduplicate them.

### 6.6 `formal.evaluate`

- kind: `formal-evaluation`
- domain: `formal-program-sequence`
- codomain: `record`
- parameters: exactly non-empty `input_name`

The first dependency is a content-addressed `TOMAGI-FORMAL-PROGRAM-1.0`
record; the second is a sequence. The program is statically validated in full,
then evaluated with `{input_name: sequence}`. The result is the addressed
`TOMAGI-FORMAL-RESULT-1.0` record defined in section 7.

The active formal limits are derived only from the effective definition limits:

```text
formal max_steps            = max_expression_nodes
formal max_depth            = max_expression_depth
formal max_collection_items = max_sequence_items
formal max_value_nodes      = max_expression_nodes
formal max_canonical_bytes  = max_output_bytes
```

### 6.7 `canonical.encode`

- kind: `canonical-encoding`
- domain: `record`
- codomain: `bytes`
- parameters: exactly boolean `terminal_newline`

Produces canonical JSON bytes for the dependency and appends one LF if and
only if requested. The complete result MUST fit `max_output_bytes`.

### 6.8 `state64.construct`

- kind: `initial-state`
- domain: `seed-record`
- codomain: `state64`
- parameters: exactly `fields`

Unknown `State64` fields reject. Missing fields are zero. Each supplied integer
is narrowed to its 32-bit word before the frozen TOMAGI 1.0 signed or unsigned
interpretation is applied.

### 6.9 `hash.sha256`

- kind: `computed-hash`
- domain: `bytes`
- codomain: `string`
- parameters: optional boolean `prefix`

Hashes the sole byte dependency. The default and `true` form prepend
`sha256:`; `false` returns bare lower-case hex.

### 6.10 `assert.equal`

- kind: `hash-guard`
- domain: `hash-pair`
- codomain: `bool`
- parameters: empty

Requires two string dependencies and rejects unless their values are exactly
equal. A successful assertion produces `true`.

### 6.11 `emit.graph`

- kind: `byte-emission`
- domain: `bytes`
- codomain: `cell_graph`
- parameters: `chunk_bytes?`, `byte_order?`, `id_prefix?`, `key_base?`,
  `key_field?`, `aux_base?`, `halt_last?`

The non-empty input is split in declared order into chunks of one through four
bytes (default four). One `EMIT` Cell48 is constructed per chunk. Cell IDs are
the prefix, colon, and zero-padded ordinal. A selected canonical key coordinate
is incremented by ordinal; the complete coordinate and `aux` ranges MUST fit
their fixed-width fields without modular aliasing. Duplicate keys reject.

Payload packing follows `byte_order`. In the Cell48 flags word, bits 8 through
10 hold the byte count 1..4, bit 11 selects big endian, and bit 0 on the final
cell requests halt when `halt_last` is true. Successors form the declared
forward chain; the final successor is itself. The origin crosswalk records the
definition ID, byte offset, count, and order.

### 6.12 `program.construct`

- kind: `artifact-program`
- domain: `state-graph-guard`
- codomain: `program`
- parameters: `entry?`, `flags?`, `seed?`, `default_ticks?`, `emit_bytes?`

Requires exactly one graph, at most one state, and only true boolean guards.
The default entry is the graph entry; default state is all zero; default ticks
is the graph length. `default_ticks` MUST fit `u32`; out-of-range values and
missing entries reject. User flags are narrowed to `u32`; seeded-profile bit 0
is always set, and emitted-byte bit 1 is set exactly when `emit_bytes` is true.

## 7. Bounded formal language

A formal program contains only `schema`, optional non-empty `id`, `expression`,
and `content_hash`. Its schema is `TOMAGI-FORMAL-PROGRAM-1.0`; its hash follows
section 3. The entire expression tree is statically validated, including
branches that execution will not select. Unknown operations therefore cannot
hide behind a conditional.

Formal values are null, booleans, integers, strings, lists, records, and reduced
exact rationals `{num,den}` with integer numerator, strictly positive integer
denominator, gcd 1, and zero represented only as `{num:0,den:1}`. Floats and
non-JSON host values are forbidden.

The closed expression operations are:

```text
lit rat ref list record let
get has keys values put merge len is_string concat append
add sub mul div neg abs integer_abs floor bit_length
eq ne lt le gt ge not and or if assert hash
pairs unique map filter sort group fold
```

Their normative meanings are:

- `lit` returns a detached finite JSON value; `rat` reduces two evaluated
  integers; `ref` reads a lexical binding.
- `list` and `record` evaluate declared children in order (record keys in sorted
  order). `let` evaluates unique bindings sequentially, so later bindings may
  reference earlier ones, then evaluates its body in that scope.
- `get` addresses an in-range list integer or existing record string key;
  `has` tests that condition. `keys` returns sorted keys and `values` returns
  values in sorted-key order. `put` and right-biased `merge` return new records.
- `len` accepts list, record, or string. `is_string` returns true exactly for a
  string value without coercion. `concat` joins two lists; `append` returns a
  list with one evaluated terminal item.
- `add`, `sub`, `mul`, `div`, `neg`, and `abs` use mathematical rational
  arithmetic and return a reduced rational. Division by zero rejects.
  `integer_abs` accepts only a plain integer and returns its non-negative
  magnitude. `floor` returns the mathematical floor as a plain integer.
  `bit_length` accepts only a non-negative plain integer and returns its binary
  length (`0` maps to `0`).
- Numeric comparisons compare exact rationals. Equality also permits arbitrary
  formal values and otherwise uses type-strict structural JSON equality, so a
  boolean never equals an integer. Boolean operations require booleans and
  short-circuit in declared order. `if` evaluates only the
  selected branch after whole-tree static validation. `assert` rejects a false
  condition and otherwise returns its value. `hash` returns the section 3
  content address of its evaluated value.
- `pairs` returns all unordered index pairs `i<j` in nested increasing-index
  order as records containing `left`, `left_index`, `right`, `right_index`.
  `unique` compares canonical bytes and preserves first occurrence.
- `map` and `filter` visit a finite list in declared order. `sort` is stable and
  orders a decorated key using the total order null, boolean, exact number,
  string, list lexicographically, then record by sorted key/value pairs; its
  optional descending flag reverses that order. `group` uses canonical key
  identity and returns groups in the same total key order while preserving item
  order inside each group. `fold` visits the source from index zero upward and
  exposes the previous accumulator only.

There are no calls, recursion, `while`, implicit retry, host callback, clock,
random source, file operation, or network operation in the formal language.
Every expression evaluation and collection visit consumes deterministic steps.
Depth, steps, collection size, value nodes, and canonical bytes are checked
against host limits that the source cannot enlarge.

`formal.evaluate` returns:

```text
{
  schema: "TOMAGI-FORMAL-RESULT-1.0",
  program_hash: <verified formal program hash>,
  inputs_hash: <hash of the complete named input record>,
  steps: <deterministic positive integer>,
  value: <evaluated formal value>,
  content_hash: <hash of this record without content_hash>
}
```

## 8. Cell48 lowering and binary ordering

Only a root value of type `program` lowers. Cells are sorted by the unsigned
64-bit canonical key `(key_hi << 32) | key_lo`; IDs and keys MUST each be
unique. Successor IDs and the entry ID are resolved after sorting. Lowering
copies the fixed fields into the existing 48-byte little-endian Cell48 layout.
The header remains 128 bytes and `State64` remains 64 bytes. The opcode count
remains sixteen; `EMIT` is opcode 14.

The compile report contains the canonical seed binding, complete definition
order and hashes, evaluated closure order, external source bindings, cell count,
entry, program flags, and the cell-origin crosswalk. It then binds source and
program file names, byte lengths, and SHA-256 addresses. Reports are canonical
JSON plus LF.

## 9. Execution and byte materialization

Execution uses the frozen TOMAGI 1.0 transition equations. For a seeded byte
artifact, the program MUST carry seeded bit 0 and emit-byte bit 1. Each executed
`EMIT` contributes exactly the byte count and order declared in its cell flags.
Records are concatenated by execution sequence, never by table index, key,
payload value, filesystem order, or trace presentation order.

A supplied trace is accepted for materialization only if deterministic replay
from the program's canonical initial state for exactly the supplied row count
produces an equal row at every field. Missing, extra, non-integer, reordered,
duplicated, mutated, out-of-range, or post-halt rows reject. A proper prefix is
valid and materializes only its executed `EMIT` prefix. A trace with no `EMIT`
record rejects.

`max_output_bytes` is a seeded-source compilation limit and is not serialized
in the frozen TOMAGI 1.0 header. It therefore constrains construction of the
emitted cell graph and the canonical initial artifact, but an authenticated
legacy graph may deliberately revisit a non-halting `EMIT` cell and produce
additional repeated bytes. The version-1 materializer MUST preserve that loop
semantics; it MUST NOT infer a ceiling from the sum of unique cell payloads. A
hard replay ceiling requires a versioned binary/profile field or a separately
authenticated caller policy bound to the program hash.

## 10. Rejection conditions

In addition to operation-specific failures, compilation or materialization MUST
reject:

- wrong seed bytes, length, newline state, hash, grammar, or token registry;
- malformed, non-object, non-finite, or unknown-field seeded JSON;
- false definition hashes, absent provenance, duplicate IDs/tokens/dependencies,
  missing dependencies, cycles, phase inversion, or phase/order collision;
- any exceeded document or tightened definition limit;
- a domain, kind, codomain, operation, parameter, state field, key coordinate,
  auxiliary range, cell ID, cell key, successor, entry, or flag contract error;
- malformed or tampered formal programs, values, inputs, or result hashes;
- float arithmetic, non-reduced rationals, division by zero, invalid access,
  failed assertion, unknown reference, or unbounded/unknown formal operation;
- during compilation, empty emitted bytes, more cells or initial emitted bytes
  than budgeted, or a root that does not produce a program; and
- any unauthenticated execution trace described in section 9.

## 11. Determinism and replay theorem

For fixed accepted seed bytes `S`, token registry `R`, seeded source bytes `D`,
and all accepted `source.json` bytes `I`, evaluation order is uniquely determined
by content-addressed records and phase/order ranks. Every operation is a total
deterministic function on accepted inputs or rejects. Formal traversal order,
arithmetic, hashing, sorting, grouping, lowering, runtime transition, payload
decoding, and concatenation are explicit and contain no environmental input.
Therefore any conforming implementation either rejects at the same declared
contract boundary or produces identical:

```text
definition values
-> ordered Cell48 records
-> .tmg bytes
-> complete execution trace
-> ordered EMIT records
-> materialized artifact bytes.
```

Wall-clock durations, temporary paths, interpreter cache files, compiler path
strings, filesystem enumeration order, and ZIP creator metadata are outside the
semantic chain and MUST NOT enter a reproducibility certificate or package
payload. A package claim requires two clean builds from the same authoritative
capsule and byte equality of every declared boundary, including the final ZIP.

## 12. Backward compatibility

Documents without `compilation_profile: TOM-SEEDED-COMPILATION-1.0` use the
legacy handwritten-cell compiler. This corrective profile does not change its
accepted format, cell sorting, header, state, opcode table, or transition
semantics. Existing seeded sources using the original eight operations retain
byte-identical `.tmg` output when they satisfy the now-explicit validation
rules. New generic source and formal operations are compile-time definitions;
they do not create hidden runtime opcodes.
