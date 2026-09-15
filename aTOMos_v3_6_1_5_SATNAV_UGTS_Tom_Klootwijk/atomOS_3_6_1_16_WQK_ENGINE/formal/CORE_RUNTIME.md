# ATOMOS-HINGE-R1: implemented exact reference subset

R15 introduces a running Python-standard-library reference in
`python/atomos_hinge.py`. The user explicitly authorized correctness checks and
matched benchmarks for this new release. Earlier no-execution release statements
remain historical; the R15 tests exercise this implementation. This subset has
its own versioned record and envelope. It is **not an XOPSEED1 parser or a full
XOP executor**, and it does not claim automatic compilation of every R14 law.

## Public interface

- `Phi(a,b)` represents `a+b*phi` with exact `Fraction` coefficients. Inputs
  are integers, Fractions or Phi objects; a floating-point input is rejected.
- `plane_guard`, `sphere_guard`, `psi_excludes_ball` expose exact primitive
  decisions and a conditional descendant-ball exclusion predicate.
- `make_guard_seed(kind='plane', ...)` returns an editable typed seed. Without
  velocity, samples supply `point`; with velocity, samples supply `time` and
  the graph computes `origin+velocity*(time-epoch)` with epoch zero.
- `Engine(seed)` copies and admits a seed. Its `seed` and `state` properties
  return snapshots; changes require a newly admitted Engine.
- `engine.evaluate(sample)` returns the demanded exact graph value, or raises
  its explicit domain/input/unsupported exception. It does not change state.
- `engine.step(event_id, sample, crossing=None, seam=None, sequence=None)`
  returns `StepResult(status,state,trace,reason)` and commits one whole state
  only for status `VALUE`.
- `engine.pack()` and `Engine.unpack(blob)` preserve seed, operators, operands,
  masks, expressions, consumed identities, exact values and state.
- `engine.upload_words(32|64)` exports the complete envelope as little-endian
  unsigned words, exact byte length and SHA256, with `geometry_projection=None`.
  A native GPU implementation must decode that format or use an explicitly
  separate declared projection; uploading these bytes is not execution of them.
- `phi_turn`, `phi_branch`, `chart_normalize`, `chart_lift` retain exact phase
  and lift data. A polar expression involving PI/sin/cos stays unevaluated here.

## Exact arithmetic and sequential expressions

The field uses `phi^2=phi+1`:

```
(a+b phi)(c+d phi) = (ac+bd) + (ad+bc+bd) phi
(a+b phi)^-1 = ((a+b)-b phi)/(a^2+ab-b^2), when nonzero
phi(a+b phi) = b+(a+b) phi
```

For sign, write `2x=A+B sqrt(5)`, with `A=2a+b`, `B=b`. The signs of A and B
settle equal-sign/zero cases; otherwise exact comparison of `A^2` and `5B^2`
settles the result. No decimal approximation to phi is used. Floor clears the
coefficient denominators and uses an integer square root of `5B^2`, with the
negative-irrational branch retained. Integer bit length is not fixed.

A node `sequence(args=[a,b,c], operations=['add','mul'])` evaluates `(a+b)*c`.
The word expression `['seq', a, ['or',b], ['and',c]]` similarly means
`(a OR b) AND c`. These explicit left folds are the supported sequential
notation. They do not imply O(1) bit complexity. Integer shifts by themselves
cannot represent multiplication by irrational phi.

## Typed geometry and admitted graph

Nodes are ordered and uniquely named; operand references point only to earlier
nodes. Runtime type/dimension/frame checks apply to demanded operations; this
subset does not implement the full XOP static admission proof. Demand evaluation
memoizes within one evaluation. `if` demands only its
selected branch, and its predicate must be the exact dimensionless scalar 0 or
1. Literal/input values carry seven integer SI exponents. Vectors have exactly
three components and a nonempty nominal frame. Frame identity is preserved; it
does not prove physical alignment or calibration.

Implemented operations are typed scalar add/subtract/multiply/divide/negate,
left-fold sequence, lazy if, exact literals/inputs, affine point motion and
plane/sphere guards. Unsupported operators, including general sin/cos and
continuous ODE solution, yield `UNKNOWN` from `step`; their source graph stays
in the seed. No fallback to float is performed.

Spatial primitives require length-valued coordinates in their declared frame.
For a plane, `g=n dot p-offset` has distance units for dimensionless n. It is
a true signed distance only when `n dot n=1`; `require_sdf` enforces that
condition. The normal must be nonzero. For a sphere of positive radius r,
`g=|p-center|^2-r^2` has squared-distance units and is explicitly labelled
`sphere_sign_polynomial`, not an SDF. Its sign agrees exactly with
`|p-center|-r` because their remaining factor `|p-center|+r` is positive.

`psi_excludes_ball` needs the premise that every relevant descendant over its
declared time interval lies within radius R of the supplied node center. It
does not infer that premise from depth or a parent point. The plane condition
is `g>0 and g^2>R^2*(n dot n)`; the sphere condition is
`|node_center-center|^2>(r+R)^2`. These strictly exclude the entire ball.
Equality and failure of a sufficient condition are retained. These geometry
predicates do not erase state updates or optical/thermal effects.

## The complete atomic hinge step

Each seed has one guard export, an explicit word width (1 through 4096), a
present mask, two independently stored `{asa,na,boundary}` sets, a present
drive lane and optionally a distinct present seam lane. Every accepted sample
has a nonempty event identity. An optional explicit sequence must increase;
otherwise a logical sequence is assigned in arrival order.

1. Bind one sample and evaluate the guard exactly. For a declared seam, require
   `raw_new=(-1)^epsilon*source_value`, with epsilon 0 or 1 and an integer
   winding increment. This checks the submitted algebraic gluing equation;
   the source-value same-physical-point premise remains the profile's input
   claim. An arbitrary comparison with the previous moving point is not used.
2. Use the matching new orientation `kappa'=kappa XOR epsilon` and set
   `corrected=(-1)^kappa' raw_new`. This leaves the corrected value invariant
   for an admitted same-point chart change. The inside bit is `[corrected<0]`.
3. At exactly zero, default `boundary='hold'` returns `BOUNDARY` with no commit.
   Explicit `inside` and `outside` ownership instead give the chosen bit. No
   epsilon replaces equality. The last nonzero side is retained through owned
   boundary samples.
4. A newly accepted pulse h is a nonzero side change after a baseline, an
   explicitly supplied crossing, or a nontrivial declared seam transition.
   The first sample has no pulse unless `pulse_on_first` is explicitly enabled.
   Suppressing an explicitly declared seam event is rejected.
5. Place the guard bit in the drive lane. Evaluate X, both whole-word ASA/NA
   stages, and J/K from the same old q. A boundary hit zeros the whole stage
   output; it does not automatically hold JK. The word AST has explicit
   `q,d,e,y` bindings (X cannot read y). Integer `1` is the one-bit literal;
   `ones` denotes all bits of the declared width.
6. Default `e=h<<drive_lane`, `J=e AND y`, `K=e AND NOT_w(y)` latches the
   **post-mask** branch bit on h and holds otherwise. An optional seam lane
   overrides its J/K with the same `h AND epsilon` pulse. The next word is
   `((J AND NOT_w(q)) OR (NOT_w(K) AND q)) AND present`.
7. Commit the word, orientation, cumulative winding, branch parity
   `p'=p XOR h`, last nonzero side/value, sequence and consumed identity in one
   state. The orientation flip is applied once; it is not applied again as a
   second interpretation of the same chart event.

Consumed identities retain complete canonical request bytes, not merely a
hash. A repeated identical request is `DUPLICATE` with no state change; the
same identity with changed data/bindings is `INVALID`. Missing input,
unsupported operations, domain failures, resource exhaustion and malformed
requests return `MISSING_INPUT`, `UNKNOWN`, `UNDEFINED`, `RESOURCE_LIMIT` or
`INVALID` without a partial commit. The API is serial; concurrent callers must
provide their own synchronization. Deduplication history grows with accepted
records and is not claimed to have bounded memory.

## Chart lift and phase

Angles are represented in turns, not sampled trigonometric coordinates.
`chart_normalize` stores `j=floor((rho-lo)/period)` and `rho'=rho-j*period`.
For odd j, `reflective_klein` maps theta to `1/2-theta`; `source_half_turn`
maps it to `theta+1/2`; both negate the additional phase and toggle orientation.
The record separately retains `theta_winding` and `phi_phase_winding` for the
original angles before reduction modulo one turn. `chart_lift` restores rho,
undoes the angular action and restores both original angular windings exactly.
It preserves the distinction between the two profiles. A wrapped quotient
without those winding integers is not the full lift.

`phi_turn(n)` is exactly the fractional part of `n/phi`. `phi_branch` retains
the polar operator expression and its radius/turn rather than pretending that
general sine/cosine results lie in Q(phi). It does not yet construct a complete
phyllotactic tree, moving-scene enclosure or arbitrary SDF compiler.

## Custom bit-plane envelope and limits

The canonical semantic record is deterministic ASCII JSON with sorted unique
keys and no whitespace. All mathematical integers are tagged canonical signed
hex strings, avoiding decimal-digit limits; rationals have reduced numerator
and positive denominator; Phi has two tagged rational coefficients. Plain
JSON numeric literals, duplicate keys, alternate integer spellings and unknown
reserved types are rejected. The schema/version is `ATOMOS-HINGE-R1`.

The envelope is `AHNGBPL1`, one 8-byte little-endian semantic byte length, a
32-byte SHA256 of the semantic bytes, followed by 512-byte transposed blocks.
Each block is padded with zeros and interpreted as 64 uint64 words. Its output
plane c has bit r equal to source word r's bit c. Plane words are little-endian,
block-major then plane-major. Inverse transposition restores every bit. Length,
digest, zero padding, trailing bytes and canonical reencoding are checked.
SHA256 detects accidental corruption here; it supplies no authenticity or
proof of physical validity. The declared decoder limit is 64 MiB of semantic
bytes and 4096 DAG nodes; available host memory remains a practical limit.

`upload_words` preserves this whole envelope without NumPy or floating-point
conversion. Its 32/64-bit words are transport views, not reduced precision
geometric coordinates. A texture-backed GPU projection or accelerator is a
separate implementation with its own admission domain and comparison evidence.

## Correctness evidence and remaining scope

The accompanying unittest suite exercises independent sign/floor inequalities,
field identities and inverse domains, large integers, affine/unit/frame cases,
boundary ownership, double-mask absorption, same-old-state JK, seam consistency,
duplicate/changed identities, both inverse chart lifts, exact replay after
packing, upload byte identity, malformed envelopes and explicit unresolved
operations. These are tests of this reference subset, not formal proof of the
interpreter or evidence of a physical device.

R14 remains the wider mathematical foundation. This implementation provides
executable pieces of its exact-word/hinge design. It does not establish general
query elimination, numerical dominance over S2, arbitrary PDE integration,
full XOP decoding, external calibration, hardware gate correctness or physical
precision beyond the declared represented inputs.
