# What is proved, and what is tested

Author attribution: Tom Klootwijk · NL200678942 · 10-07-1990.
Basis: the atomOS v3.6 master word-epoch contract defined in the preceding project
conversation, and the attached source equations mapped in docs/coverage.csv.

## 1. Exact 32-bit word algebra

Let x,A,N,B,V,F be arbitrary unsigned 32-bit words. Define

    a = x & A & V & F
    n = a & N
    h = popcount(n & B)
    y = n if h == 0 else 0.

Neutral F=V recovers all four original fields, because V&V=V. The selected supports
can only contract. The final output cannot introduce a bit absent from x.

For fixed masks, the final-word map is idempotent. Its first output is either zero,
which stays zero, or a selected word with no B intersection; applying the same masks
again changes no bit and still has no B intersection. This concerns the final word,
not an assertion that its historical intermediate trace remains identical.

It is NOT monotone in mask inclusion after absorption: with x=A=N=V=3, B=2, the
unrestricted output is zero but the F=1 output is one. The example is deliberately
retained in the tests.

P01–P08 establish the corresponding bit-vector identities by asking Z3 whether their
negations have any model. P09 proves the full 32-bit SWAR population-count expression
equals the sum of the 32 input bits. P10 establishes count=0 iff the input word is 0.
These are universally quantified claims via the absence of a satisfying assignment
to their free fixed-width variables, not exhaustive enumeration of only a small word.

## 2. JK and encoded blend

For q,j,k in {0,1}, q' = (j & ~q) | (~k & q) is exactly hold/set/reset/toggle.
P11 compares this expression to an independently written truth-table conditional.
P12 proves toggle applied twice recovers q. P13 proves three-bit XOR equals modulo-2
sum. The angular inputs are not automatically encodings of any of those bits.

## 3. Word-Morton layout

Each tile interleaves the three radial bits into even positions and the three
angular-WORD bits into odd positions. P14 proves that extracting those positions
recovers the two original three-bit coordinates. Thus the map is injective on the
64 pairs and, since its codomain has 64 entries, bijective.

The padded atlas uses unique row-major tile numbers and disjoint address intervals
of 64 values. Combining that quotient with the tile inverse is therefore a bijection.
A stored plane satisfying M_layout[address(r,w)]=M_logical[r,w] returns the same
logical operand for either layout. The output index is r*words+w in both kernels.
This proves the layout transformation at the specification level. Runtime padding,
length and comparison tests establish the recorded finite implementation outcomes.

## 4. Integrated epoch and commit

For the default word profile, ASA output depends on the selected producer, state word
and masks; JK depends on q,j,k; the blend depends on three supplied encoded bits.
Changing only the reference-axis angle cannot change those operands. OTAN2 and the
six comparison records have no assignment to them. Thus projection onto the original
word and JK results recovers their unchanged formulas.

The launcher creates candidate results, verifies every lane, and only then swaps
its next-state vector. The formal selector `accept ? proposed : previous` is checked
by P15 for the rejected case. P15 is not a proof of filesystem crash consistency.
The C++ regression deliberately corrupts a candidate and verifies that all previous
state words and q bits remain unchanged after rejection. Run files are held in a
`.partial_*` directory until final publication, with a distinct COMMITTED marker.

Per-lane prefix agreement follows by induction: initial states match the reference;
a checked epoch applies matching word and JK transitions; committed states then match
before the next epoch. This is conditional on correct resource reads and successful
validation. The independent Python checker reconstructs each exported prefix.

## 5. OTAN2 and the six real-arithmetic laws

The literal source is beta_s = atan(dphi/drho), drho != 0, and e_s=beta_s-alpha.
Its optional directed completion is beta_d=atan2(dphi,drho) with a principal wrap.
A zero vector has no assigned change direction in either profile.

R: common positive radial scaling adds ln(c) to both log radii, cancelling in their
difference. P: a common offset to consistently lifted phases cancels in their
difference. W: division of both increments by one positive interval cancels in the
ratio and retains directed quadrant. S: the same reasoning holds for multiplication
by a positive step factor. For a chart line phi=k*rho+b, every nonzero radial segment
has slope k, so the literal orientation is atan(k).

F: co-rotating the increment vector and axis adds the same chi to both orientation
and reference. The directed residual is unchanged modulo 2*pi. The literal ratio
represents only a line direction, so its correct equality is modulo pi, assuming
both literal denominators are nonzero. Raw literal residuals may differ by pi.

V: simultaneous negation leaves the ratio unchanged, while a directed vector angle
changes by pi. Changing ONLY the axis by eta changes the raw residual by -eta; it is
covariance rather than a conserved value under arbitrary evolution.

These are analytic deductions from the formulas, not Z3 transcendental proofs. The
implementation separately checks finite examples, singularities, numeric statuses
and comparison errors. No arbitrary-width floating-point accuracy theorem is claimed.

## 6. Evidence boundary

The SMT obligations are mathematical specifications. They do not symbolically
execute every line of C++, prove CUDA compiler correctness or verify native SM_120
instructions. The CPU and Python tests are independent finite conformance evidence.
On-device execution and Compute Sanitizer are the next required evidence category.
The original preparation reports mark that category not_run because it was not
available then. The September 13 Windows laptop review records actual CUDA and
Compute Sanitizer execution in results/validation_status.json; those finite
implementation checks remain distinct from these specification proofs.

A working software kernel establishes that the declared computations can be executed
and compared. It is not a proof of every causal, external-system or application claim
contained in earlier AI-export transcripts. The supplied kernel has no such interfaces.
