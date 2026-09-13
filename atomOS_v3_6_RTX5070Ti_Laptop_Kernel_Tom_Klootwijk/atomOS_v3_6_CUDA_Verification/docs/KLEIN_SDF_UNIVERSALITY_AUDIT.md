# Independent audit: universality through the Klein/log-polar operator LUT

This is an analysis and proposed construction, not a claim that the construction
below has been implemented or validated. It responds to the corrected requirement
that the operator SDFs, packed word predicates, log-polar texture LUT, and Klein
topology participate in the universal computation itself.

## Findings from the actual attachment

The supplied 43-page M1 PDF has SHA-256
`b51651c007c560775ff1950e278789cd7674e131ec71a09ebd9254cebe9c19ce`.

- Page 9 defines the log-polar chart and a discrete sampling convention.
- Page 10 defines the Klein quotient `(u+1,v)~(u,v)` and
  `(u,v+1)~(-u,v)`. It explicitly says that this quotient is not an SDF
  automatically supplied by the source name. The attachment does not provide
  explicit signed-distance formulas for a complete operator bank. A search of
  all 43 extracted pages finds this one occurrence of “SDF”; geometry elsewhere
  is supplied regions, fields, masks, or declared adapters.
- Pages 16–18 define region predicates and ASA/NA/whole-word absorption. They do
  not define a general circuit compiler or an SDF-to-program transition rule.
- Page 24 proves consistency of the explicitly selected geometry-to-occupancy
  and admission adapter. This is a representation/selection theorem. It does not
  construct arbitrary computational transitions from those predicates.
- Page 27 proves a storage permutation preserves logical operands. Morton
  interleaving itself is neither Klein topology nor programmable computation.
- Pages 31–32 prove simulation for the explicit U interpreter and a supplied
  transition table, assuming sufficient addressable memory for each finite
  prefix. Page 32 explicitly warns that a finite wrapped polar dictionary will
  alias distinct logical tape cells.
- Page 35 restricts the fixed-mask idempotence claim to the ASA projection. The
  complete engine can evolve. That correction does not establish universality
  of the ASA projection by itself.

The user's new instruction makes Klein mandatory for the requested implementation.
The attachment originally treating it as a selectable profile does not remove
that new requirement. New SDF formulas and a computational adapter can be declared
as implementation choices based on Tom Klootwijk's architecture; they must not be
attributed to nonexistent formulas in this attachment.

## Why the implemented U1 does not satisfy the corrected request

`experiments/universal_engine.cu` currently loads
`rules[control * alphabet + symbol]` in the U CUDA kernel. This is an ordinary
global-memory transition table. `universal.hpp` stores tape symbols by the linear
offset `position-origin`. Its address and transition functions do not implement
the Klein seam. The host independently proposes K1 and U results, then shares
their commit decision. The exported profile explicitly says geometry is disabled
and combined-profile texture residency was not measured.

Consequently, U1 demonstrates a working explicit interpreter alongside K1. Its
47-case validation and capacity results are real evidence for that implementation,
but do not prove that SDF operators in a Klein/log-polar texture LUT perform those
universal transitions. Sharing a transaction, renaming the table, or simply placing
the existing rule structs in a texture would not close this gap.

## What the fixed word map cannot establish

For fixed masks, the existing final-word function is contractive in its input
support and idempotent: `F(F(x))=F(x)`. Repeatedly feeding its own result back into
that function settles immediately. Even varying masks without a producer that
adds support cannot create new occupied bits. A fixed finite bank plus a finite
number of JK bits has finitely many states; cycles do not provide unbounded tape
memory. None of these observations proves that larger constructions using the
operators cannot be universal. They rule out claiming universality of the fixed
contractive projection alone.

## A constructive operator-level route: ASA implements NOR

There is an exact connection available inside the retained whole-word operation.
For Boolean inputs `a,b`, form a fresh candidate word

```
x = 1 | (a << 1) | (b << 2)
ASA mask = NA mask = 0b111
boundary mask = 0b110
valid and fringe admit all three designated cells
output signal = bit 0 of the final ASA word
```

If either input marker is present, whole-word absorption clears the constant
output marker too. If both input markers are absent, the output marker survives.
The output signal is therefore exactly `NOT(a OR b)`. This uses whole-word
absorption, not per-bit clearing. It does not violate support containment: the
constant output marker was present in the proposed input.

Constant injection and routing are essential, explicit parts of this construction.
It is not an iteration of `F` on its own previous output. Define a new gate-input
producer that gathers its two signals and supplies the constant marker; do not
silently change the source shift producer's zero guard.

The gate is sufficient for finite Boolean functions by a direct construction:
`NOT(a)=NOR(a,a)`, `OR(a,b)=NOT(NOR(a,b))`, and
`AND(a,b)=NOR(NOT(a),NOT(b))`. A truth table can be expressed as a sum of input
minterms, hence compiled using these gates. This supplies a proof route rather
than an unexplained assertion that geometry is universal.

One robust machine-level construction stores a symbol and optional head/control
marker at each tape cell. The next record at a cell depends on that cell and its
two neighbours: the head cell writes its symbol; its selected neighbour receives
the next head/control marker; untouched cells retain their symbol. For any finite
machine alphabet/control set, this is a finite Boolean local function and can be
compiled into an ASA/NOR network. Evaluate from immutable old records and commit
the new records together. Prove by induction that exactly one head marker and
the decoded tape/control state match the source machine at every step.

This makes the runtime operator evaluation determine the transition. The supplied
machine table can remain a compiler input and independent reference. It must not
remain the runtime shortcut that actually computes the output while the SDF bank
is merely observed alongside it.

## Making the SDF and Klein layers substantive

An explicit metric is required for “distance.” One possible implementation choice
is the flat metric on the normalized quotient chart. Its distance is

```
dK(p,q) = min over integers m,n of
         sqrt((p.u - ((-1)^n*q.u + m))^2 + (p.v - (q.v+n))^2).
```

The deck transformations are isometries, so this descends to the Klein quotient.
This metric is a computational chart choice; it is not a claim that ordinary
Euclidean distances in the displayed log-polar annulus survive radial gluing.

Choose three distinct sampled cell centres in the same logical 32-cell group.
Around them place sufficiently small, disjoint metric disks. An ASA/NA region is
the union of the three disks; a blocking region is the union of the two input
disks. For disks below the injectivity radius with separated supports, their
signed-distance function is `min_i(dK(p,centre_i)-radius)`. Sampling its sign at
the declared log-polar nodes gives the exact three-bit NOR masks above. State the
sign convention and whether the blocking predicate means a forbidden region or
a boundary band. Do not call a Boolean sign bit the full numerical distance.

Compile these actual SDF samples into the packed planes, using radial bits in
even Morton positions and angular-word bits in odd positions. At runtime, use
the masks fetched through the texture path in the ASA/NOR calculation. A test
that changes the blocking SDF and observes the expected logical gate change is
necessary evidence that the geometry is computationally active.

Klein normalization must occur before losing angular winding. An odd angular
seam reflects the radial coordinate; for radial cell centres this maps row `i`
to `R-1-i`. Scalar masks must descend consistently to the quotient. Vector/frame
records require the corresponding radial tangent reflection and explicit chart
parity: a Klein surface has no globally consistent orientation. A plain angular
modulo and a Morton swizzle do not implement these requirements. Preserve whole
32-cell groups under the chosen seam/reflection maps where whole-word
noninterference is claimed.

## The memory and proof boundary that cannot be removed by topology

A finite Klein atlas has finitely many cells. Identifying logical tape positions
modulo that atlas destroys the general simulation theorem. An honest construction
must retain a lift/sheet or page coordinate, or another growing logical address
space, so a seam crossing changes chart representation without aliasing distinct
tape cells. The finite resident operator dictionary can be shared across those
pages; writable computation state need not be the immutable operator texture.
Alternatively, claim only bounded computation within a finite atlas and report
its boundary explicitly. Fixed finite storage cannot establish unbounded-machine
universality.

The resulting proof should separately establish: quotient/seam consistency; exact
SDF predicate sampling at the chosen nodes; predicate packing/layout equivalence;
the ASA/NOR gate truth table; correctness of circuit composition and routing; and
step-by-step machine simulation under the declared memory assumptions. GPU
conformance and sanitizer evidence then test the concrete implementation.
Texture-cache retention must be measured again for the actual operator-driven
kernel and its dictionary. The earlier cache measurement and separate U1 tape
capacity test cannot be inherited by this new execution path.

A weaker, still honest alternative is to encode transition-table output bits as
SDF regions and prove that sampling/packing/decoding reconstructs the table exactly.
That would make a geometric LUT execute the U construction, but its universality
would be that of an explicitly encoded table interpreter. It would not establish
that the unchanged fixed ASA projection, or Klein topology alone, supplied the
general computation. The NOR construction is the stronger match if the requested
claim is that the formalized word operators themselves form the computational
basis.
