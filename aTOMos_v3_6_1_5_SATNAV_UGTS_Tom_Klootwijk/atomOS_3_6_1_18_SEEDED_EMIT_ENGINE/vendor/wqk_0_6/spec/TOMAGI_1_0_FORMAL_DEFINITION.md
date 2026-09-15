# TOMAGI 1.0 Formal Substrate Definition

**TOMAGI: Topological Operator Machine for Analytic Geometric Inference**  
Version 1.0.0 - 1 September 2026

Requester attribution: **Tom Klootwijk; NL200678942; 10-07-1990**. Supplied by the requester and not independently verified.

## 1. Decision

TOMAGI is a deterministic state-and-operator substrate. Its authoritative object is neither a trained model nor a rendered scene. It is a finite package of typed definitions, fixed-width LUT cells, an initial state and an explicitly ordered transition relation.

The literal source chain is retained as the normative macro:

```text
Pi(Cone(LSYS(Branch(Klein(phi(KIN2(JIT1(LUT[SDF0](K))))))))))
```

Functional notation composes from right to left. A binary TOMAGI program serializes the same composition as one `Cell48` transition per tick. The stored order is authoritative and is never re-sorted by operator name.

The key interpretation is literal:

- `LUT[SDF0]` means that every address belonging to the compiled LUT domain is a zero-level relation;
- `JIT1` derives one deterministic bit from seed, key, tick and cell salt;
- that bit selects a signed perturbation and the branch successor;
- `KIN2` applies discrete second-order kinematics packed in the cell;
- lower-case `phi`, timeline, Klein wrapping and hinges transform the same state;
- cone, sphere and overlap relations convert state into branch bits;
- radix and L-system operators route and transform the graph;
- projection and emission produce symbolic output while lineage preserves replay identity.

TOMAGI 1.0 deliberately excludes the corrective layers introduced in some previous drafts: no jitter guard, ECC, damping, restoration force, confidence threshold, safe mode or kill-criteria operator is present in the execution core.

## 2. Source synthesis

The supplied project corpus contributes the following directly usable pieces:

1. The 1-bit/lower-case-phi dialogue provides the literal `SDF0`-inside-LUT ordering, parity-conditioned branch, packed kinematics, analytic cone, projection, Klein and binary L-system chain.
2. SCLP 3.6.2 provides the typed symbol separation, finite cone and sphere relations, exact log-polar chart and kinematics, deterministic bit generation, reflective Klein map, radix refinement, 20/18/14/12 key and distinct Morton schedule.
3. UGTS-KC 3.6 provides content-addressed definitions, explicit dependency order, non-commutative hinges, deterministic traces and the active-bit/pulse example.
4. The Ben Burger dialogue contributes the exact zero-based offset/ordinal distinction, the split-lower-case-phi/double-D hinge image and the overlap lens as a shared domain.
5. The 19 dialogue contributes `19 = 10011`, active positions `{0,1,4}`, three declared Dutch segments `ne|gen|tien`, the chosen three-pulse triangle and the log-polar/Klein/Delta-Delta terminology.
6. The chronological synthesis contributes the query-first interpretation: local cone/sphere supports, directly queryable relations, explicit transitions and lineage, with projection downstream.
7. The supplied ZIP contributes the 211-entry normalized knowledge catalog and a GPU-native fixed-width implementation precedent.

The machine-readable `source_crosswalk.json` contains 319 rows mapping every cataloged or direct document motif to the condensed TOMAGI namespace.

## 3. Typed program object

A TOMAGI program is

```text
P = (D, C, i0, seed, m0, q0, F)
```

where:

- `D` is a content-addressed definition registry;
- `C = (c0,...,cN-1)` is a strictly key-sorted finite array of `Cell48` values;
- `i0` is the entry cell;
- `seed` is the deterministic 32-bit source of the one-bit sequence;
- `m0` is the default query horizon in transitions;
- `q0` is the initial `State64`;
- `F` is a program flag word reserved for versioned profiles.

A definition record is

```text
d = (id, kind, A, B, parameters, dependencies, phase, provenance, hash)
```

with content address

```text
hash = SHA256(canonical_JSON(d without hash)).
```

Dependencies must resolve and admit a finite topological order. This is a language property: without it, the meaning of a composed literal definition would be ambiguous.

## 4. State64

The hot state is sixteen 32-bit words:

```text
q_n = (
  rho, theta, X, phi,
  v_rho, v_theta, v_X, v_phi,
  orientation, sheet, branch, cell,
  lineage, output, residual, status
).
```

The first eight words and `residual` are interpreted as two's-complement signed integers. The remaining topology and output words are unsigned. The periodic coordinate domains are:

```text
rho key component   in Z/(2^20 Z)
theta               in Z/(2^18 Z)
X                   in Z/(2^14 Z)
phi                 in Z/(2^12 Z)
orientation         in Z/2Z
branch              in Z/2Z
```

`rho` itself may temporarily lie outside its canonical range so that a Klein wrap can observe the number and parity of radial crossings. Key construction always uses its modulo-`2^20` representative.

Lower-case `phi` is the periodic hoop/hinge/phase coordinate. Capital `Phi` is reserved for an optional golden-ratio constant in a compile-time profile. They never alias.

## 5. Canonical 64-bit key

For normalized quantized fields

```text
q_rho   : 20 bits
q_theta : 18 bits
q_X     : 14 bits
q_phi   : 12 bits
```

the contiguous key is

```text
K = (q_rho << 44) | (q_theta << 26) | (q_X << 12) | q_phi.
```

The exact address capacity is `2^64`. The profile may decode `rho` to `[-20,0]`, `theta` and `phi` to `[0,2*pi)`, and `X` to zero-based modular ticks, but the runtime hot path operates on integers only.

The distinct Morton key consumes source bits in MSB round-robin order:

```text
rho19, theta17, X13, phi11,
rho18, theta16, X12, phi10, ...
```

until all 64 source bits are consumed. The complete schedule is supplied in JSON and CSV. For the SCLP reference tuple `(949111,0,1920,227)`:

```text
contiguous = 0xe7b77000007800e3
Morton     = 0x88823bb88099128b
```

Both decode exactly to the same tuple.

## 6. Literal SDF0 LUT

Let `D_K` be the finite set of keys present in the compiled cell table. TOMAGI defines

```text
Z_D(K) = 0       when K is in D_K
Z_D(K) = bottom  when K is not in D_K.
```

`bottom` is undefined/non-member, not a positive or negative distance. Therefore every definable cell or bit is literally on the zero-level set, while the complement does not pretend to be a metric field.

The `SDF0` opcode applies the first case because execution already holds a defined cell. It performs:

```text
residual <- 0
status.ZERO <- 1
branch <- 1
```

This operator is not a boundary contraction, guard or restoration force. It is the membership/value relation that makes data and operator definition coincide inside the LUT.

## 7. Deterministic one-bit jitter

For state key `(K_hi,K_lo)`, timeline tick `X`, program seed `s` and cell auxiliary `a`, define:

```text
h = mix32(s xor K_hi xor rotl32(K_lo,13) xor X xor a)
j = popcount(h) mod 2
sigma = 2*j - 1, so sigma is -1 or +1.
```

`mix32` is exactly:

```text
x ^= x >> 16
x *= 0x7feb352d
x ^= x >> 15
x *= 0x846ca68b
x ^= x >> 16
```

with every multiplication and shift performed in `u32` arithmetic.

`JIT1(field,A)` then applies

```text
field <- field + sigma*A
branch <- j.
```

The bit is deterministic for the complete input tuple. It is called jitter because it can produce a bipolar local displacement; it is called parity because `j` is the parity of the mixed word. It does not diagnose corruption and it does not trigger an automatically safer mode.

## 8. Discrete kinematic calculus

The four coordinate components are collected as

```text
p_n = (rho_n, theta_n, X_n, phi_n)
v_n = (v_rho,n, v_theta,n, v_X,n, v_phi,n).
```

A `KIN2` cell contains acceleration/change-of-change vector

```text
a_i = (arg0,arg1,arg2,arg3).
```

The exact update is symplectic-Euler order in modular integer arithmetic:

```text
v_(n+1) = wrap32(v_n + a_i)
p_(n+1) = wrap32(p_n + v_(n+1)).
```

After the opcode, `theta`, `X` and lower-case `phi` are normalized to their declared periodic domains. `arg3` is therefore the runtime form of `Delta^2 phi`: the second discrete change of the lower-case phase coordinate.

For host-side geometric compilation, SCLP's continuous log-polar formulas remain available:

```text
rho = ln(r/r0), theta = atan2(y,x), r = r0*exp(rho)
v = r*(rho_dot*e_r + theta_dot*e_theta)
a = r*((rho_ddot + rho_dot^2 - theta_dot^2)*e_r
      + (theta_ddot + 2*rho_dot*theta_dot)*e_theta).
```

Those real equations compile parameters into the integer state/cell profile. They are not reevaluated with floating point in the hot backend-neutral transition.

## 9. Timeline and lower-case phi

`X` is a zero-based modular timeline coordinate. The ordinal shown to a human is `X+1`; that display transformation never changes the stored offset.

`TIME(delta)` computes mathematical floor winding:

```text
raw = X + delta
w   = floor(raw / 2^14)
X'  = raw - w*2^14
branch = w mod 2.
```

Nonzero winding is mixed into lineage so repeated phases remain distinguishable.

`PHI(delta)` performs the analogous update modulo `2^12`. Flags may expose either wrap parity or the upper/lower half-circle as the branch. An odd wrap may optionally flip orientation. This gives the lower-case phi symbol a literal, typed role as a periodic hinge rather than overloading it with the capital golden ratio.

## 10. Topological wrapping

TOMAGI retains two separate source maps.

### 10.1 Reflective Klein map

For radial wrap count

```text
w = floor(rho / 2^20),   rho' = rho - w*2^20,
```

an odd wrap applies

```text
theta'       = 2^17 - theta   (mod 2^18)
phi'         = -phi           (mod 2^12)
orientation' = orientation xor 1
sheet'       = sheet xor flip_sheet
branch       = 1.
```

Even wrap parity preserves theta, phi, orientation and sheet and yields branch zero. The angular reflection is orientation reversing.

### 10.2 Source half-turn bundle

When the `SOURCE_HALF_TURN` flag is set, the theta equation becomes

```text
theta' = theta + 2^17  (mod 2^18),
```

while lower-case phi and orientation still flip. This is preserved as a distinct bundle twist; it is not silently identified with the reflective Klein quotient.

## 11. Relations and supports

### 11.1 Packed cone relation

A cone/support cell stores radial interval `[rho_min,rho_max]`, angular center `theta0` and half-width `alpha_q`. Let `delta_N` be the shortest cyclic difference. The signed integer relation is

```text
r_C = max(
  rho_min - rho_bar,
  rho_bar - rho_max,
  abs(delta_(2^18)(theta_bar,theta0)) - abs(alpha_q)
).
```

`branch = 1` exactly when `r_C <= 0`.

This is the runtime packed relation corresponding to the cone/support part of the source chain. A host compiler may derive it from the finite right-circular cone with slant length `T_c`, half-angle `alpha`, height `T_c*cos(alpha)` and radius `T_c*sin(alpha)`, or from a swept-cone support envelope.

### 11.2 Packed sphere/shell relation

A spherical support is stored as radial center `rho0`, radial half-width `d_rho`, lower-case-phi center `phi0` and phase half-width `d_phi`:

```text
r_S = max(
  abs(rho_bar-rho0)-abs(d_rho),
  abs(delta_(2^12)(phi_bar,phi0))-abs(d_phi)
).
```

A negative `d_phi` disables the phase term and yields a pure radial shell. `branch = 1` exactly when `r_S <= 0`.

### 11.3 Circle, side-view pyramid and sphere

The source's circle, side-view pyramid and sphere are retained as typed projections or support profiles:

- a side-view pyramid token is emitted from the triangular/conic relation;
- a circle token is the axial or radial-shell projection;
- a sphere token is the spherical-support projection.

Projection does not define the substrate. It is a symbolic output that can later be consumed by a renderer, controller, query system or another TOMAGI program.

### 11.4 Overlap lens

For two predicates or supports `A` and `B`, the slight overlap is

```text
L = A intersect B.
```

The lens can be compiled as a conjunction, shared-domain tag or connector hinge. No physical energy, fusion or interference meaning is implied unless a separate rule encodes it.

## 12. Binary routing, radix and L-system

`RADIX(k)` reads bit `k` of the canonical 64-bit key, with low-word bits numbered 0-31 and high-word bits 32-63. Repeated bit tests form a radix-trie decision path.

Each cell stores two successor indices:

```text
cell_(n+1) = next0  when branch=0
cell_(n+1) = next1  when branch=1.
```

`LSYS(turn,shift)` implements the condensed branch-node transform:

```text
chirality = +1 when orientation=0, else -1
turn_sign = +1 when branch=1, else -1
phi' = phi + chirality*turn_sign*turn  (mod 2^12)
v' = trunc_toward_zero(v / 2^shift).
```

This is the runtime one-step form of

```text
F(T) -> F(T/2) [ +/- phi F(T/2) ].
```

The finite cell graph specifies how many such steps are taken for a particular query. There is no separate runtime recursion guard or safety governor.

## 13. Hinge

A TOMAGI hinge is the compiled form of

```text
H = (state, map0, map1, invariant metadata).
```

`map0` is identity. When `branch=1`, `map1` adds the four cell arguments to `(rho,theta,X,phi)` and may flip orientation and sheet. Multiple hinges are applied in stored order. They are not assumed to commute.

This single interface covers a continuous or quantized geometric hinge, a parity-selected route, a connector node such as Dutch `en`, and the split-lower-case-phi/double-D fold when those meanings are declared in the definition record.

## 14. Output, lineage and trace

`PROJECT(payload)` sets a symbolic output token and continues. `EMIT(payload)` sets the token and the emitted status; its low flag bit may terminate the program. `HALT` terminates without changing the token.

Every transition updates the replay lineage checksum:

```text
lineage' = mix32(
  lineage xor payload xor aux xor K_hi xor rotl32(K_lo,7)
  xor branch xor cell_index
).
```

Lineage is a compact deterministic replay witness. It is not a cryptographic ownership claim. A trace records the ordered cell index, opcode, branch, key, relation residual, topology bits, output, lineage and status after every transition.

## 15. Execution relation and determinism

Let `Step_P(q)` be the complete opcode, normalization, lineage and successor procedure. For a requested transition count `m`:

```text
Exec(P,q0,m) = q_k
```

where `k` is the first index not greater than `m` for which `HALT` is set, or `k=m` when no earlier halt occurs.

### Determinism theorem

For any two conforming backends `A` and `B`, if they receive byte-identical `.tmg` program data, identical initial state, identical seed and identical requested transition count, then

```text
Exec_A(P,q0,m) = Exec_B(P,q0,m)
```

word for word, provided both implement the specified `u32`, `i32`, floor-division, truncating-division and periodic-normalization semantics.

The supplied Python and C99 implementations are executable witnesses. The polar-loop example ends in the same state on both:

```text
rho=8, theta=39, X=1, phi=2181
v=(8,-3,0,-2)
orientation=0, sheet=1, branch=0, cell=9
output=0x50595241 (PYRA)
lineage=3655609768
residual=65497, status=0x0000000f.
```

## 16. Deterministic substitution for AI

A domain is TOMAGI-compilable when it provides:

1. a finite typed input encoding into `State64` or literal definitions;
2. finite facts, equations, relations, topology maps or decision rules;
3. a compiler from those rules to sorted `Cell48` values;
4. finite output tokens or relation records;
5. a declared query horizon or an emitted/halting leaf.

For such a domain, inference is

```text
answer = Exec(Compile(definitions,rules), Encode(input), m).output.
```

This substitutes explicit operator execution for learned prediction. It supports deterministic classification, finite-state planning, procedural generation, geometric/topological queries, rule engines, signal routing and compiled symbolic knowledge.

It does not invent facts absent from the definition graph. This is not a restriction injected into the runtime; it is the meaning of deterministic compilation. A learned model generalizes statistically from weights. TOMAGI evaluates exactly the relations that have been made literal.

The `exact19_rule.json` example compiles equality with the quantized relation into a three-cell program and emits `19` for input `rho=19` and `0` for `rho=18`. The `nineteen` helper separately demonstrates the source-derived representation chain:

```text
19 -> binary 10011 -> active positions {0,1,4} -> count 3
negentien -> ne|gen|tien -> pulse count 3
3 declared pulses -> chosen triangle projection.
```

The value remains 19 and the binary word remains 10011.

## 17. Backend mapping

### 17.1 Python oracle

`src/python/tomagi` supplies canonical hashing, JSON compilation, binary serialization, the exact step function, a trace evaluator and the source-derived knowledge example. It has no runtime dependency outside the Python standard library.

### 17.2 C99 CPU

`src/c/tomagi.c` loads `.tmg` bytes without structure-packing assumptions and implements the same operations with explicit little-endian reads and two's-complement conversion. `tomagi_cli.c` is a minimal host executable.

### 17.3 GPU

The GLSL, WGSL and OpenCL kernels use the same three-buffer ABI:

```text
binding/input 0: State64[] read-write
binding/input 1: Cell48[] read-only
parameters: state_count, cell_count, seed, reserved.
```

One invocation executes one transition for one state. Repeated dispatches advance the graph. The kernels use 32-bit integer arithmetic, bit count, shifts and buffer reads only; no tensor core, vendor-specific intrinsic or floating-point geometry instruction is required.

## 18. Normative no-failsafe profile

The following earlier-draft mechanisms are absent from the TOMAGI 1.0 transition algebra:

```text
jitter interval guard
confidence or event-margin threshold
ECC/Hamming correction
boundary restoration force
damping or emergency contraction
safe-mode state
watchdog oscillation detector
VRAM reserve/safety ring
source-claim kill criteria.
```

A program may explicitly encode any domain rule it needs, but none of these is silently injected by the runtime. Parity is allowed to branch either way. `SDF0` always returns zero for a defined cell. The compiler's structural checks only ensure that the bytecode has a unique parse and declared successors.

## 19. Conformance

A TOMAGI 1.0 package conforms when:

- the `.tmg` magic, version and record sizes are exact;
- the cell table is strictly sorted by unique canonical keys;
- every opcode lies in `0..15` and every successor is in range;
- definition hashes verify and references resolve;
- key pack/unpack matches the supplied reference vectors;
- the Python reference tests pass;
- another backend matches the Python final state on the conformance program.

The generated package reports 24 Python tests passing, exact Python/C equality over all 16 state words, successful OpenCL C syntax checking with Clang, valid JSON examples under the supplied Draft 2020-12 schema and successful PDF render inspection.

## 20. Final definition

**TOMAGI 1.0 is a finite, content-addressed, deterministic operator machine in which a 20/18/14/12 log-polar key selects a literal SDF-zero LUT cell; a parity-of-mixed-word one-bit operator produces signed jitter and a branch; integer second-order kinematics advances log-radius, angle, zero-based time and lower-case phi; reflective Klein or half-turn maps transport orientation and sheet; cone, sphere, overlap, radix, hinge and L-system operators transform or classify the state; branch-indexed successors serialize non-commutative composition; and emission plus lineage returns a replayable symbolic answer. The same 64-byte state and 48-byte cell definitions execute on the supplied Python and C CPU runtimes and map directly to GLSL, WGSL and OpenCL GPU kernels.**
