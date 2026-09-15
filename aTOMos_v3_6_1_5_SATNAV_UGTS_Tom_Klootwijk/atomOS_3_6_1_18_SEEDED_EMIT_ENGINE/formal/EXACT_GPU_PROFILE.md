# Native exact operator profile: ATOMOS-EXACT-GPU-ZPHI31-R1

This implemented CUDA profile evaluates a bounded subset of the R15 exact operator graph. It keeps literal operators and integer coefficient operands in a losslessly packed seed, expands that seed into persistent VRAM, and computes guard signs with integer arithmetic. It is a separate profile from XOPSEED1 and the Python AHNGBPL1 envelope. It does not implement arbitrary rational coefficients, the complete R14 operator registry, or a general GPU computer algebra system.

## Domain and exact arithmetic

Every scalar is `Coeff{a,b}` representing

\[
x=a+b\phi,\quad\phi=(1+\sqrt5)/2,\quad a,b\in\mathbb Z,
\quad |a|,|b|\le B=2^{30}-1.
\]

This is a bounded executable subset of the ring Z[phi], not the whole field Q(phi). Each retained node value and every plane-guard product/partial sum must satisfy the coefficient bounds. An input, literal or intermediate outside them returns `Unresolved`, with `failed_node` and a zero hinge eligibility gate. No truncation, wraparound, clamping or floating conversion occurs. A later cancellation does not undo an earlier failed bound check. Unsupported operators are rejected structurally. The Python exact `Phi` reference is the fallback for greater integer magnitudes, arbitrary rationals and supported operations outside this native subset; dispatching that fallback is the caller's responsibility.

Addition/subtraction act coefficientwise. Multiplication and multiplication by phi are

\[
(a+b\phi)(c+d\phi)=(ac+bd)+(ad+bc+bd)\phi,
\qquad \phi(a+b\phi)=b+(a+b)\phi.
\]

All retained operands obey the bound before use. The largest multiplication sum is bounded in absolute value by `3 B^2 < INT64_MAX`; add/sub and phi multiplication also fit signed 64-bit intermediates. Results are checked before narrowing to signed 32-bit coefficients.

For the exact sign, write `A=2a+b`, `C=b`, so `2x=A+C sqrt(5)`. Zeros and equal signs are direct. For opposite signs, compare unsigned 64-bit `A^2` with `5 C^2`: the larger term determines the sign. Both squares fit unsigned 64-bit because `|A|<=3B` and `|C|<=B`. Squaring does not introduce a rounding decision. Equality is possible only for the zero element in this integer-coefficient domain. No floating-point arithmetic appears in operator evaluation or sign classification.

## Operators, graph order, and physical typing

The implemented opcodes are `Literal`, `Input`, `Add`, `Subtract`, `Multiply`, `PhiMultiply`, and `PlaneGuard`. There are at most 128 nodes and 128 input slots. All operand references must point to earlier nodes, preventing cycles. The evaluator marks the requested root's dependency closure and executes its nodes in increasing source order; unused nodes remain in the seed but are not evaluated. This is an explicit finite DAG evaluation, with work proportional to graph size per sample. The notation makes no constant-time claim.

The seven SI dimension exponents are packed in seven signed four-bit nibbles, ordered length, mass, time, current, temperature, amount and luminous intensity. Each exponent ranges from -8 to +7. The high nibble is reserved zero. Addition/subtraction require matching dimensions; multiplication adds dimensions with checked exponent bounds; phi is dimensionless. Repeated references to one input slot must agree on units. One shared 64-bit nominal frame identity applies to the whole program. It does not estimate a transform, attest physical calibration or make measurements exact.

`PlaneGuard(px,py,pz,nx,ny,nz,d)` evaluates

\[
g(p)=n_xp_x+n_yp_y+n_zp_z-d
\]

using a fixed left-to-right sequence of checked products and sums. Coordinates and offset have length dimensions; the normal is dimensionless and nonzero. A zero normal returns `Unresolved` as a refused geometric domain; that status also covers coefficient failures. This is an oriented plane defining function. It equals signed Euclidean distance only under the additional unit-normal condition `n dot n=1`, which this profile does not assert or verify. General sphere distance, transcendental functions, orbital propagation and photonic evolution are outside this native operator subset.

For each batch sample, `Result` returns `Value` with exact nonzero sign -1/+1, `Boundary` for exact zero, or `Unresolved` on an arithmetic/domain failure. Structurally invalid programs fail creation. `accept_hinge` is an eligibility bit: it is one only for a resolved nonzero value. Despite the legacy-style field name, it does not detect a crossing, accept an event, deduplicate an identity, update orientation or perform JK feedback. A repeated nonzero level has the same eligibility bit. The caller must combine the sign with matching seam orientation, an explicit boundary policy, fresh accepted event identity and the two-mask/old-state JK adapter before calling the hinge state update. Neither `Boundary` nor `Unresolved` can enable that gate in this profile. For a generic scalar root, interpreting its sign as a geometric guard is also a caller-declared specialization.

## Canonical word schema and one-bit expansion

The public seed is an array of unsigned 32-bit words, with a portable little-endian byte interpretation when serialized. It is never the native in-memory byte layout of `Node`.

| Location | Meaning |
|---|---|
| Header 0,1 | `0x31475041`, `0x31494850` (little-endian `APG1PHI1`) |
| Header 2 | Version 1 |
| Header 3,4,5 | Node count, input count, root node index |
| Header 6,7 | Frame identity low/high words |
| Node word 0 | Opcode 0..6 in the order listed above |
| Node word 1 | Input slot; zero except for `Input` |
| Node words 2,3 | Literal signed-32 coefficient bit patterns; zero except for `Literal` |
| Node word 4 | Packed SI unit exponents |
| Node word 5 | Reserved zero |
| Node words 6..12 | Up to seven operand indices; unused entries zero |
| Node words 13..15 | Reserved zero |

The exact canonical length is `8 + 16 node_count` words. Plane operands are ordered `px,py,pz,nx,ny,nz,offset`. Unknown versions/opcodes, nonzero reserved or unused fields, unit errors, bad lengths, root errors and forward references are rejected before VRAM allocation.

`create_program` takes groups of 32 canonical words, zero-pads only the final incomplete group, and transposes the bits:

\[
P_{b,k}=\sum_{j=0}^{31}\operatorname{bit}_k(W_{32b+j})2^j,
\qquad
W_{32b+j}=\sum_{k=0}^{31}\operatorname{bit}_j(P_{b,k})2^k.
\]

The host uploads `P` to a persistent unsigned-integer linear texture. A native CUDA inverse-transpose kernel uses raw `tex1Dfetch<unsigned int>` to reconstruct every canonical word in a separate VRAM allocation. Creation synchronizes that expansion, then binds the decoded words to the evaluator's integer texture. Both packed and decoded allocations remain alive until `destroy_program`. Operators, signed operands, dimensions, graph references and frame bits therefore take the same reversible one-bit-plane path. This is lossless bit transposition, not guaranteed compression; retaining both forms costs additional memory.

The operator evaluator fetches decoded words with `cudaReadModeElementType`: there is no normalized texture read, interpolation, floating channel conversion or geometric projection in this path. `read_seed_words` launches a device kernel which fetches the decoded evaluator texture and copies its output to the host, allowing exact comparison with the canonical input. It does not return a cached original host copy. Input samples are separate integer coefficient batches, copied without conversion. Their measured or externally rounded origins remain a separate provenance question.

## Native API and integration

The independent public header is `include/atomos/exact_program.hpp`; it exposes POD types and no CUDA or S2 headers. `encode_seed` validates and emits words. `create_program` validates, packs, uploads and expands them. `evaluate` accepts row-major `[sample_count][input_count]` coefficient pairs and returns synchronous host results. The seed persists across calls; per-call sample/output buffers are allocated and released. `read_seed_words` verifies the native texture roundtrip. `destroy_program` releases both persistent seed forms. A zero-input graph accepts a null sample pointer. Batches are limited to ten million samples; practical limits also depend on device memory.

Suggested independent CMake targets are a static `atomos_exact` library from `cuda/exact_program.cu`, public include directory `include`, C++17/CUDA17, CUDA architecture matching the selected device, and `exact_program_tests` from `tests/exact_program_tests.cpp` linked only to `atomos_exact`. The implementation uses no S2 headers. No performance advantage is established by this profile. CUDA texture caching is an execution mechanism, not a proof of speed or physical fidelity.

The correctness tests exercise exact phi identities, opposite-sign Fibonacci near-cancellation cases, unsigned-square range, coefficient failures, partial-sum failures, boundaries, graph dependency isolation, dimensional validation, malformed words, and actual packed-upload/device-expansion/texture-fetch roundtrips. Their observed run result is reported separately by the release checks; this source document does not turn an unexecuted test into evidence.
