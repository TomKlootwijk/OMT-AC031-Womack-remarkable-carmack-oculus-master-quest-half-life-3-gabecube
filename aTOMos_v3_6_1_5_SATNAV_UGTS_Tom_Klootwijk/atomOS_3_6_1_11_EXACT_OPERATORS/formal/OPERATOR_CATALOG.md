# XOP-R1 exact operator seed contract

Status: mathematical definition and conditional proof obligations for release 3.6.1.11. This document does not describe an implemented encoder, arbitrary-precision engine or proof checker. No tests, simulations, numerical experiments or benchmarks were run for this formalization. The accompanying derivations are in `docs/exact_core.tex`. R10's implemented ORBIT-SEED-R1 format and binary64 evaluation remain unchanged.

“Exact” distinguishes three properties: exact reconstruction of raw input bits; exact arithmetic on represented integers, rationals and algebraic values; and exact symbolic denotation of a finite expression whose numerical value may require an infinite process. None implies exact physical measurements, an exact continuous orbit from finite RK4 steps, or finite storage for arbitrary real numbers.

## 1. Semantic sorts and outcomes

The scalar sorts are `Int`, `Rat`, `Alg`, and `RealTerm`, with explicit value-preserving coercions in that order. `Bool` is separate. `Bits(w)` is an ordered finite bit vector with explicit positive width; its complement and shifts have finite-word semantics. An integer operation never truncates to `Bits(w)` implicitly.

`Tuple(T...)`, `Vec(n,T)`, `Mat(r,c,T)`, `Fn(T... -> U)`, and `Stream(T)` are structural types. `Dim(T,d)` adds the seven rational SI exponents to a numeric scalar type. Dimension addition/subtraction, compatible frame declarations, and angle conventions are part of the admitted interface. Transcendental arguments are dimensionless; vector addition requires matching dimensions and frames. A coordinate frame label refers to a declared transformation interface, not a guessed transform.

`RealTerm` is a syntax-level carrier with partial real denotation. A term may remain unevaluated. Predicates may also remain undecided. The evaluator outcome is a tagged result, separate from the mathematical scalar types:

- `VALUE`: an exact literal with evidence of its construction.
- `TERM`: well-typed retained syntax, with its current assumptions and obligations.
- `UNDEFINED`: a violated domain condition has been established.
- `UNKNOWN`: a required comparison, domain or existence statement has not been decided.
- `MISSING_INPUT`: a required declared dependency or sample is unavailable.
- `RESOURCE_LIMIT`: a declared time, memory or proof-search limit was reached.

`UNKNOWN` and exhausted resources are not false, zero, NaN, divergence proofs or disproofs. A retained term is not a certificate that all its domain conditions hold. Only proved domains permit an assertion of a real value.

`COMPARE(a,b)` is a decision-service request, not an additional arithmetic oracle. It returns `LT`, `EQ`, `GT` with a justification, or `UNKNOWN`. The graph's `EQ`, `LT` and `LE` nodes denote mathematical predicates and need not have a terminating general decision procedure on `RealTerm` inputs.

## 2. Canonical exact literals

- **Int:** sign `s` in `{0,1}` and a finite little-endian limb sequence `a`, base `beta=2^64`. Its value is `(-1)^s sum(a[i]*beta^i)`. Zero is sign zero and no limbs; a nonzero highest limb is required. Limb counts are unbounded natural numbers at the format level.
- **Rat:** canonical `Int p`, positive canonical `Int q`, with `gcd(abs(p),q)=1`. Zero is `0/1`.
- **Alg:** primitive irreducible polynomial with integer coefficients, positive leading coefficient, degree at least one, and a zero-based index into its distinct real roots in increasing order. The coefficient sequence runs from constant to highest degree. A rational root may be represented by its degree-one minimal polynomial. An isolating interval and proof of polynomial properties are witnesses, not extra alternatives for the canonical value spelling.
- **Bool:** one octet, zero or one.
- **Bits(w):** exactly `ceil(w/8)` octets; bit zero is the low bit of the first octet. Unused high bits in the last octet are zero. Width is carried by the type.

There is no `RealTerm` raw literal containing an unspecified real number. Nonalgebraic constants and functions are operator nodes. An exact decimal input becomes a reduced rational; finite IEEE binary64 conversion explicitly becomes a dyadic rational. NaN and infinity have no conversion to a real scalar. Raw IEEE bits, including signed zero and payloads, can still be retained as `Bits(64)`.

Exact algebraic canonicalization requires exact polynomial factorization, minimal-polynomial selection, root isolation and branch identification. A finite resultant calculation produces candidate roots, not automatically the correct selected root. The implementation must retain and establish the selected-root obligations. Root equality uses polynomial/common-root reasoning; it cannot rely solely on repeated interval refinement when roots coincide.

## 3. Canonical byte primitives

The grammar uses the following primitives; concatenation has no implicit alignment:

- `U(n)`: minimal unsigned base-128 variable-length integer, low seven bits per digit, least significant digit first, high bit one on every nonterminal octet and zero on the final octet. Zero is one zero octet. Multi-octet encodings with a zero final payload are rejected. There is no 64-bit count limit.
- `O(b)`: one octet in `[0,255]`.
- `B(bytes)`: `U(length)` followed by those octets.
- `Seq_T(items)`: `U(count)` followed by each item encoded according to schema `T`.
- `Z(z)`: `O(sign) U(limb_count)` and that many fixed eight-octet little-endian limbs, with the canonical integer restrictions above.
- `Q(q)`: `Z(numerator) Z(denominator)` with the rational restrictions above.
- `Name`: a byte string of printable ASCII octets `0x21..0x7e`, used case-sensitively; empty names are rejected. Display text/provenance uses opaque `B` bytes and has no binding semantics.

An implementation may set finite count, depth, width and memory limits, announced before decoding. A valid larger mathematical record is unsupported under those limits; it is not silently reinterpreted or partially accepted. Field lengths must be checked before allocation and arithmetic on counts must not wrap.

Type encodings begin with `U(tag)`:

| Tag | Type | Remaining fields |
|---:|---|---|
| 0 | Bool | none |
| 1 | Int | none |
| 2 | Rat | none |
| 3 | Alg | none |
| 4 | RealTerm | none |
| 5 | Bits | `U(w)`, `w>0` |
| 6 | Tuple | `Seq_Type(component_types)` |
| 7 | Vec | `U(n) Type(T)`, `n>0` |
| 8 | Mat | `U(rows) U(cols) Type(T)`, both positive |
| 9 | Fn | `Seq_Type(parameter_types) Type(result)` |
| 10 | Dim | `Type(scalar)`, exactly seven `Q` exponents |
| 11 | Stream | `Type(element)` |

`Dim` accepts only an unwrapped numeric scalar type; redundant nested dimension wrappers are rejected. Structural shape and dimension constraints are checked before applying arithmetic. A function type's domain obligations are declared in its body/interface, not erased by its type name.

## 4. Scope, reference and document records

An ordered scope is `Seq_Node(nodes) Seq_Ref(exports)`. Each node is

`U(opcode) Type(result) Seq_Ref(operands) B(opcode_payload)`.

The payload must itself decode exactly under the selected opcode schema; trailing bytes or unknown fields are rejected. The result type is checked against the operator rule rather than trusted. Empty payload means a zero length byte string.

A reference is `U(tag)` followed by these fields:

| Tag | Meaning | Fields and obligation |
|---:|---|---|
| 0 | local node | `U(index)`; a node operand may refer only to an earlier node in its current scope |
| 1 | bound variable | `U(de_bruijn_index)`; index zero is the nearest lexical binder |
| 2 | old state | `U(slot)`; permitted only in the main dynamic scope |
| 3 | current sample | `U(slot)`; permitted only in the main dynamic scope |
| 4 | dependency export | `U(dependency) U(export)`; export type and complete dependency bytes must resolve |

A scope export or state root may reference any already declared node in its complete scope. This does not authorize a forward dependency inside a node. Nested scopes use lexical binders; they cannot accidentally reach an outer local node by reusing its numeric index. Captures must be passed as explicit bound parameters. Templates are pure: state and sample values are passed as arguments. A nested scope's binders have the order in its payload; the last parameter has de Bruijn index zero. Substitution is capture-avoiding and shifts indices under binders.

The complete semantic stream, in order, is:

```
ASCII("XOPSEED1") U(1) U(0)
Seq_Dependency(dependencies)
Seq_Template(templates)
Seq_State(states)
Seq_Sample(samples)
Scope(main)
Seq_Export(exports)
Strategy(strategy)
B(provenance)
```

The eight-octet magic is new and does not collide with or reinterpret R10's format. The two naturals are the major and minor profile numbers. No trailing octets are allowed.

- `Dependency = Name(label) O(kind) B(canonical_seed_bytes)`, where kind zero means a seed value export and kind one means a template-library seed. The content is a complete `XOPSEED1` record. The import graph is finite and acyclic. Labels are unique. An imported value export must be closed and stateless, with no state/sample dependencies in its demanded graph. A fixed snapshot can be exported as closed literal/expression data; a live imported stream must instead enter through an explicit sample input. Importing a seed does not silently execute its state machine or choose a clock tick.
- `Template = Name(label) Seq_Type(parameters) Type(result) Scope(body)`. There is exactly one body export of `result` type. Bodies call only earlier templates or explicitly imported templates, and contain no main-state/sample references. Template calls are therefore acyclic. The encoded ordered body, not just the label, fixes the template.
- `State = Name(label) Type(T) Ref(init) Ref(next)`. These roots refer to the main scope. Initial roots are closed with respect to state and samples and must have proved values of `T`. The next roots have type `T` under the old-state/input environment. The state table is the sole causal `DELAY` mechanism. Reading state tag two means `DELAY(init,next)` at the current step; no instantaneous feedback edge is allowed.
- `Sample = Name(label) Type(T) Name(time_convention) O(mode) B(binding) B(provenance)`. Mode zero binding is `Seq_Row(rows)`, with `Row = Z(logical_step) Q(absolute_time) Literal(T)`; step indices are nonnegative and strictly increasing. Mode one binding is `Name(external_port)`: each step must supply a typed literal and an absolute timestamp under the named convention. No implicit interpolation, nearest-row selection, leap-second conversion or future extrapolation is defined. Missing rows/ports yield `MISSING_INPUT`.
- `Export = Name(label) U(main_export_index) O(observation)`. Observation is zero or one. Stateful equivalence must preserve all observation-one exports, sample identities and declared output timestamps. Export labels are unique. Even unobserved exports remain part of the ordinary value interface unless an explicit interface change is adopted.
- `Literal(T) = Type(T) B(payload)`, with the payload selected by section 2; inline sample literals are limited to these literal types and their finite tuples/vectors/matrices. Structural literal payloads are ordered `Seq_Literal` values with shape/type agreement. Function, stream and ungrounded real-term literals are rejected.
- `Strategy = U(version) Name(proof_system) Seq_Rule(rules) B(priority_policy) B(cost_model) B(resource_policy) Seq_Proposal(history)`; these fields are detailed in section 9. In the baseline definition, empty rules/policy/history means identity-only execution strategy. Uninterpreted policy bytes grant no execution authority.

The encoding is canonical for an ordered syntactic record, not for all semantically equivalent expressions. Node order, structural sharing and chosen explicit coercions can distinguish equivalent graphs. Dependency hashes may index content but cannot establish collision-free mathematical identity: when identity is required, compare the complete canonical bytes. An open manifest containing only dependency digests is not the self-contained encoding defined here.

## 5. One-bit plane envelope

Let `C` be the complete canonical seed and `L=len(C)`. Zero-pad `C` to a multiple of 512 octets. In each block, parse 64 little-endian uint64 patterns `w[r]` and form

`p[c] = sum((((w[r] >> c) & 1) << r) for r=0..63)`.

The packed envelope is `ASCII("XOPPLAN1") U(L)` followed by the plane words, each eight-octet little-endian, block-major then plane-major. Exactly `512*ceil(L/512)` payload octets are required. Apply the same transpose to invert it, reject nonzero decoded padding, take exactly `L` octets, then parse `XOPSEED1`. A canonical seed has positive length. Compression is not part of this canonical envelope; an external compressor must declare its own transport and reconstruct the envelope exactly.

The bit at `(r,c)` becomes `(c,r)`, so two transposes are the identity. Explicit length removes tail ambiguity. The transform is a bit permutation and does not itself shrink arbitrary data or encode an unbounded limb sequence in one word. An implementation may stream blocks; it must retain all counts, limbs, types and payload bits.

## 6. Numeric and Boolean operator registry

The table fixes numeric opcodes. `S` means a common scalar sort reached by explicit coercions. Unless stated otherwise payload is empty. A typed node denotes its expression; an exact evaluation procedure may return the unresolved outcomes in section 1.

| ID | Name | Operands and result | Domain / payload |
|---:|---|---|---|
| 0 | LITERAL | none -> literal type | Payload is that type's canonical literal payload |
| 1 | COERCE | one scalar -> higher scalar | Only stated injective scalar embeddings; payload empty |
| 2 | TUPLE | ordered values -> Tuple | Result component types match |
| 3 | PROJECT | Tuple -> component | Payload `U(index)`, within bounds |
| 4 | VECTOR | n scalars -> Vec(n,S) | Positive size, common scalar/dimension |
| 5 | MATRIX | r*c scalars -> Mat(r,c,S) | Row-major order; result fixes shape |
| 6 | LAMBDA | explicit capture operands -> Fn | Payload `Seq_Type(parameters) Scope(body)`; body has one export; capture binders precede parameter binders |
| 7 | APPLY | function, arguments -> declared result | Exact arity and types; body/domain substitution |
| 8 | TEMPLATE | arguments -> template result | Payload `O(location) U(index)`, location zero local; location one additionally carries `U(imported_template_index)` and index denotes dependency |
| 16 | ADD | S,S -> S | Matching dimensions |
| 17 | SUB | S,S -> S | Matching dimensions |
| 18 | NEG | S -> S | Numeric scalar |
| 19 | MUL | S,S -> S | Dimensions add |
| 20 | DIV | S,S -> S | Denominator nonzero; Int result forbidden, explicit Rat promotion |
| 21 | IDIV | Int,Int -> Int | Divisor nonzero; Euclidean quotient |
| 22 | MOD | Int,Int -> Int | Divisor nonzero; `0<=r<abs(divisor)` |
| 23 | POW_INT | S,Int -> S | Nonnegative exponent, or nonzero base with rational/higher result; `x^0=1` by finite-product convention |
| 24 | ABS | S -> S | Ordered real scalar |
| 25 | SIGN | S -> Int | -1,0,1 according to exact sign; decision may be unresolved |
| 26 | MIN | S,S -> S | Matching dimensions; selection needs order evidence |
| 27 | MAX | S,S -> S | Matching dimensions; selection needs order evidence |
| 28 | FLOOR | dimensionless scalar -> Int | Unique integer n with `n<=x<n+1`; decision may be unresolved |
| 29 | CEIL | dimensionless scalar -> Int | `-floor(-x)` |
| 30 | ROOT | Int n,scalar x -> Alg/RealTerm | n>=1; even n requires x>=0 and nonnegative root; odd n real root; dimensions divided by n |
| 31 | SQRT | scalar -> Alg/RealTerm | x>=0, nonnegative root; explicit scalar promotion; dimensions halved |
| 32 | EQ | equal compatible types -> Bool | Exact value equality; RealTerm decision need not terminate |
| 33 | LT | S,S -> Bool | Ordered scalar, matching dimensions |
| 34 | LE | S,S -> Bool | Ordered scalar, matching dimensions |
| 35 | AND_BOOL | Bool,Bool -> Bool | Logical conjunction, not a word operation |
| 36 | OR_BOOL | Bool,Bool -> Bool | Logical disjunction |
| 37 | NOT_BOOL | Bool -> Bool | Logical negation |
| 38 | IF | Bool,T,T -> T | Lazy branch selection; only selected branch domain required |
| 40 | FULL_ADDER | Bool a,b,carry -> Tuple(Bool,Bool) | Result sum bit, carry bit; exact equations below |
| 41 | FULL_SUBTRACTOR | Bool a,b,borrow -> Tuple(Bool,Bool) | Result difference bit, borrow bit; exact equations below |
| 48 | BIT_AND | Bits(w),Bits(w) -> Bits(w) | Equal explicit widths |
| 49 | BIT_OR | Bits(w),Bits(w) -> Bits(w) | Equal explicit widths |
| 50 | BIT_XOR | Bits(w),Bits(w) -> Bits(w) | Equal explicit widths |
| 51 | BIT_NOT | Bits(w) -> Bits(w) | Complement inside width only |
| 52 | BIT_SHIFT | Bits(w),Int count -> Bits(w) | Payload `O(direction)`: zero left, one logical right; count>=0; shifted-out bits deliberately discarded |
| 53 | POPCOUNT | Bits(w) -> Int | Sum of the w Boolean bits |
| 54 | BITS_TO_UINT | Bits(w) -> Int | `sum(b[i]*2^i)` |
| 55 | UINT_TO_BITS | Int -> Bits(w) | Requires `0<=x<2^w`; no implicit modular truncation |
| 56 | INT_SHIFT | Int,Int count -> Int | count>=0; payload direction zero multiplies by `2^count`, one returns floor division by it |

Rational operations reduce by gcd and normalize signs after exact integer arithmetic. Algebraic operations must preserve root identity. On `Bits(w)`, a literal zero and an all-ones word are explicit different payloads; the retained equation-language token `1` maps to the all-ones word only under that separately declared language adapter.

The literal arithmetic equations are:

```
sum = a XOR b XOR carry
carry_next = (a AND b) OR (carry AND (a XOR b))
a + b + carry = sum + 2*carry_next

difference = a XOR b XOR borrow
borrow_next = ((NOT a) AND b) OR (borrow AND NOT(a XOR b))
a - b - borrow = difference - 2*borrow_next
```

These complements act on one Boolean bit. Chain the output carry/borrow into the next more significant position, starting at zero. Multiplication forms `a[i] AND b[j]` at binary position `i+j` and adds the finite shifted rows with the same full adder, keeping every carry. Magnitude comparison scans padded bits from most significant to least: start `(equal,greater)=(true,false)`, then simultaneously set `greater'=greater OR (equal AND a AND NOT b)` and `equal'=equal AND NOT(a XOR b)`. Euclidean long division uses this exact comparison and the subtractor. Arbitrary-length exact arithmetic is therefore a finite composition of literal one-bit operations for every finite input, without a fixed format-level precision ceiling. This derivation is not an implementation or an executed bit test.

## 7. Elementary, tensor and calculus registry

| ID | Name | Signature / denotation | Domain / payload |
|---:|---|---|---|
| 64 | SIN | RealTerm -> RealTerm | Entire sine series; dimensionless input |
| 65 | COS | RealTerm -> RealTerm | Entire cosine series; dimensionless input |
| 66 | TAN | x -> sin(x)/cos(x) | cos(x) != 0 |
| 67 | EXP | RealTerm -> RealTerm | Entire exponential series |
| 68 | LOG | x -> integral(1 to x,du/u) | x>0 |
| 69 | ATAN | x -> integral(0 to x,du/(1+u^2)) | All real x |
| 70 | ATAN2 | y,x -> angle | `(x,y)!=(0,0)`; range `(-pi,pi]`, exact cases in chapter |
| 71 | ASIN | x -> angle | -1<=x<=1; inverse sine on `[-pi/2,pi/2]` |
| 72 | ACOS | x -> angle | -1<=x<=1; inverse cosine on `[0,pi]` |
| 73 | PI | none -> RealTerm | `4*atan(1)` |
| 74 | POW_REAL | x,y -> exp(y*log(x)) | x>0, dimensionless x,y; distinct from integer powers/root branches |
| 80 | DOT | Vec(n,S),Vec(n,S) -> S | Finite sum of pairwise products |
| 81 | CROSS | Vec(3,S),Vec(3,S) -> Vec(3,S) | Right-handed determinant convention in declared frame |
| 82 | NORM | Vec(n,S) -> Alg/RealTerm | Nonnegative square root of dot product; dimensions retained |
| 83 | TRANSPOSE | Mat(r,c,S) -> Mat(c,r,S) | Swap indices |
| 84 | MATMUL | Mat(r,k,S),Mat(k,c,S) -> Mat(r,c,S) | Finite contraction over k |
| 85 | DET | square matrix -> S | Finite signed permutation sum |
| 86 | INVERSE | Mat(n,n,S) -> Mat(n,n,S) | det != 0; scalar sort closed under division |
| 87 | SOLVE_LINEAR | A,b -> x with Ax=b | Square A, det != 0, compatible vector; division-capable scalar sort |
| 96 | FIN_SUM | Int a,Int b,captures -> S | Inclusive integer bounds; payload Type(S),Scope(body); index binder last; empty interval gives additive identity |
| 97 | FIN_PRODUCT | Int a,Int b,captures -> S | Same binding; empty interval gives multiplicative identity; dimensionless terms in this base rule |
| 98 | DIFF | point,captures -> RealTerm | Payload Type(variable),Scope(body); derivative exists at point; variable binder last |
| 99 | INTEGRAL | a,b,captures -> RealTerm | Same payload/binder; oriented finite Riemann integral, integrability required |
| 100 | LIMIT | point,captures -> RealTerm | Payload Type(variable),O(side),Scope(body); side zero two-sided, one from below, two from above; unique finite limit required |
| 101 | ODE | t0,s0,t,captures -> state | Payload Q(interval_left),Q(interval_right),Scope(F); closed finite interval, t and t0 included; bind time then state last; unique differentiable solution across interval required |
| 102 | SOLVE_ROOT | captures -> RealTerm | Payload Q(left),Q(right),Scope(f); binder x last; exactly one real root in open rational interval, existence/uniqueness required |
| 112 | ASA_NA | x,V,A,N,B -> Tuple(a,n,h,y) | Five Bits(w); h is Int; whole-word absorption below |
| 113 | JK | q,J,K,V -> Bits(w) | Four Bits(w), same old q; complement restricted to w |

For calculus nodes, captures become typed binders in operand order followed by the indicated integration/differentiation variables; there is exactly one body export. Body result and variable dimensions determine derivative/integral dimensions. `ODE` supports a scalar or finite vector state and checks every component of `F` against state/time dimensions. A variable's units do not change because it is a binder. A finite interval declaration supplies no automatic existence certificate. Unbounded sums, improper integrals, complex roots and distributional derivatives require separate profiles; no current opcode silently extends its domain to them.

For a dimensioned integer power or root, its degree must establish the annotated result dimensions at admission. A variable degree cannot yield inconsistent fixed output dimensions; dimensionless inputs avoid that issue. Ordinary numeric operands are strict in their demanded subexpressions; `IF` is lazy and a lambda body is demanded only through application. Declaring a node does not execute an unused branch. Topological order supplies dependencies and is not a command to evaluate all declared nodes eagerly.

An ODE root or general real root declaration is not an algorithm guaranteed to find that root or solution. Local regularity hypotheses do not automatically establish continuation throughout the declared interval. Algebraic `ROOT` and the general `SOLVE_ROOT` therefore have different decision obligations.

The finite word primitives are defined by:

```
a = x AND A AND V
n = a AND N
h = popcount(n AND B)
y = 0 if h > 0 else n
ASA_NA(x,V,A,N,B) = (a,n,h,y)
JK(q,J,K,V) = ((J AND NOT_w(q)) OR (NOT_w(K) AND q)) AND V
```

Two-stage composition applies `ASA_NA` to x with set A, then applies it to the first stage's y with set B. Both four-component traces are exported when required. J and K evaluate from the same old q and final y; the state table supplies the delay. Absorption changes the whole stage output and does not substitute a hold rule.

## 8. Derived named templates and causal interpretation

The following names require explicit template bodies and typed parameters. Their label alone never supplies an implementation or equation:

- `WRAP(x,P) = x-P*floor(x/P)`, P>0, paired with `WINDING=floor(x/P)` when an absolute phase is needed. Absolute time remains a separate value.
- `PHI = (1+sqrt(5))/2`, selecting the positive square root; `FIBONACCI` has integer initial states F0=0,F1=1 and delayed next pair `(b,a+b)`. Neither identity is an orbital force law or a universal compression result.
- `NORMALIZE(v)=v/norm(v)`, with norm nonzero; `GRADIENT` and `JACOBIAN` assemble coordinate `DIFF` terms under explicit coordinate binders.
- `POLYNOMIAL` and `HORNER` use the same finite coefficient list; `CHEBYSHEV` uses T0=1,T1=x,T(n+1)=2*x*Tn-T(n-1). Their finite expansion retains domain, coefficient values and requested degree.
- `LEGENDRE`, gravity recurrences, polar/rotation matrices, third-body terms, solar-pressure shadow predicates and station transforms are named finite expressions from their declared source model. Singular denominators and branch predicates must be retained.
- `RK4` is exactly the finite four-stage expression in the chapter. `ODE` is the separate continuous solution declaration. Equating them requires an additional theorem and is not a default rewrite.
- `OTAN2`, the two UGTS key layouts, circle-plus, cone/hoop geometry, ASA/NA and JK keep their separate literal equations and source identity. `OTAN2` is not an alias for `ATAN2`. Spatial key widths never replace the full coordinate/time operands of geometry.
- `SEED`, `TEMPLATE`, `STATE` and `SAMPLE` are the explicitly tagged reference mechanisms in section 4, not magic numeric constants. A complete operator seed includes all closed dependencies and initial values required for replay; external sample ports keep the declared system open.

Deleting the state/DELAY edges must leave a finite acyclic instantaneous graph. Initial expressions cannot read their own or another state's old value. Next expressions read one old-state/input snapshot; all commits are simultaneous. A domain or input failure prevents a value transition and remains an explicit outcome. No partial state commit is defined. Samples required by multiple nodes in one step bind identically. For physical timestamps, the epoch, time scale and absolute instant are observables when declared; modulo equality does not establish equality of instants.

## 9. Proof objects and strategy versions

A rewrite obligation is `Gamma |- e ~= e' : T`: both expressions have identical domains under Gamma and identical denotations on those domains. The proof discipline includes these rule families:

| Rule | Required premise |
|---|---|
| ASSUMPTION | Exact declared proposition occurs in the typed environment |
| REFL / SYM / TRANS | Typed equality and compatible domain judgements |
| CONGRUENCE | Proven equality of corresponding operands, same operator/bindings, preserved definedness |
| SUBSTITUTION / BETA | Capture-avoiding typed substitution; function/body domain preserved |
| EXPAND | Exact catalog or template definition, including branch and domain conditions |
| INTEGER_RING / RATIONAL_FIELD | Exact laws, including every nonzero denominator obligation |
| ORDER / ROOT_BRANCH | Required sign, range and unique-root facts |
| ANALYTIC_LEMMA | Explicit derivative/integral/limit hypotheses and proof in the accepted calculus |
| STATE_SIMULATION | Initial relation, step-domain equivalence and equal declared observations for every admitted input |

`x/x -> 1` requires x!=0; `sqrt(x*x) -> abs(x)` does not permit dropping abs without x>=0; real `log(x*y) -> log(x)+log(y)` requires x>0 and y>0. Float reassociation is not licensed by an exact-field proof. Deciding an assumption is separate from writing it. A proof mentioning a theorem identifier must resolve to an accepted theorem with all substitution and side conditions discharged.

A `Rule` record is `Name(label) B(typed_statement) B(proof_object)`. A `Proposal` is `U(parent_version) U(new_version) B(old_canonical_graph) B(new_canonical_graph) B(statement) B(proof_object) B(cost_argument)`. All `B` contents are resolved by the named proof-system/policy profile; they are not executable arbitrary source. XOP-R1 defines the interface and proof obligations, not a completed proof language. The only unconditional baseline rule is identity under the explicitly stated semantic grammar. A nonidentity rule cannot be admitted by an absent or merely named checker. This is an implementation obligation, not a hidden exact oracle.

Strategy versions are immutable. The previously accepted checker evaluates a proposed change; the proposal cannot change that checker and use its own new rule to certify itself. A checker/profile update creates an explicit new trust boundary and requires a separate acceptance argument. Hashes bind exact code/data bytes only; they do not prove soundness or termination.

Permitted reasoning-based improvements include structural sharing of identical pure subgraphs with identical lexical bindings, exact constant folding, and typed domain-preserving rewrites. Memoization keys must include complete operator/dependency identity, bound arguments, sample snapshot and state step. A finite cache affects resource behavior but cannot alter a mathematical value. Resource outcomes and trace observables must be included if they are part of the promised interface.

A decreasing natural-valued measure proves that a rewrite phase terminates. A bounded proposal budget terminates search even when no improvement is found. Neither proves global optimality. A smaller graph or an improved declared cost expression is a logical property under that cost model; it is not a measured reduction in runtime, limb growth, memory consumption or physical forecast error.

## 10. Outstanding implementation obligations

The following remain unimplemented under this release's no-testing formalization scope: a canonical XOP parser/encoder; allocation-safe variable-limb arithmetic; algebraic canonicalization and root witnesses; a typed graph executor with exact dependency and sample binding; a delayed state scheduler; certified approximations for elementary functions; exact-domain decision procedures where available; and a sound proof-object checker. General transcendental decisions and global strategy optimality remain open-ended, not promised capabilities.

The chapter's structural decoding, transpose, integer arithmetic, causal uniqueness and conditional rewrite-preservation arguments are mathematical derivations. They are not executable verification results or machine-checked proofs. Inherited R10 measurements remain evidence about R10 and its preserved inputs; they do not validate this newly declared exact-operator profile.
