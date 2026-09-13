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

## 7. Programmable U1 extension

The M1 machine-simulation theorem on page 32 assumes logical addresses and enough
storage for each finite prefix. Encoding preserves tape symbols, head and program
control initially; every defined transition preserves that correspondence by
reading the same symbol, applying the same rule and changing only that symbol
block. Induction gives agreement over each defined prefix. This is the theorem's
mathematical scope, not an infinite-hardware or compiled-binary proof.

`universal_packing.smt2` checks two additional bit-vector obligations: reading a
newly written 1..32-bit symbol returns that symbol, and all outside bits remain
unchanged in its 64-bit backing window. Run `python proofs/check_universal_proofs.py`.
Both negated properties were UNSAT. These obligations are separate from the
original 15 and do not prove the C++ parser, compiler or every GPU execution.

U1 now has executable CUDA implementations. `atomos_engine` stages U and K1
proposals and verifies every transition, every packed word and every K1 candidate
before their shared commit. A required failure preserves the accepted prefix.
`atomos_universal_stress` checks many independent tapes and their full allocation.
Exact counts, capacity stops, source hashes, commands and toolchain evidence are
in `results/optimization_20260913/summary.json`. The combined profile's cache
residency is unmeasured; it does not inherit the separate bulk-word observation.

## 8. Declared SDF/Klein/NOR and connected lineage profiles

The source audit in `docs/SOURCE_OPERATOR_SDF_AUDIT.md` distinguishes the original
binary SDF_WORD algebra from absent scalar distance formulas. The new normalized
Klein metric, disks/annuli and NOR sites are explicit constructions. They do not
recover a uniquely specified original optical geometry.

`SDF_NOR_UNIVERSALITY.md` constructs NOR from the preserved whole-word sink and
then compiles arbitrary finite controller tables to acyclic NOR wiring. The GPU
evaluates that wiring through the actual SDF predicate texture. Two additional
SMT obligations in `sdf_nor.smt2` were UNSAT. Together with the original fifteen
and the two tape-field obligations, nineteen symbolic obligations have executed.
They do not prove the scalar SDF implementation, compiler or generated binary.

The finite-prefix tape simulation requires nonaliasing addressable memory. The
joint profile adds the explicit coupling
`phi_steps = base_phi_steps * (1 + decoded.write)` and two terminal children per
live parent. Its general finite-prefix embedding also needs enough frontier and
ID capacity; finite device limits are not unbounded hardware. Empty geometry does
not halt the programmable controller. All admitted IDs, including collisions,
are retained, and sorted-array midpoint searches implement an implicit BST.

The complete joint candidate includes tape, frontier, occupancy, JK and time.
Resource/program stops add no partial failing step; a fully verified prior prefix
can be retained. Verification failure restores every initially committed
component. `docs/SDF_JOINT.md` gives precise stop/commit rules.

Actual evidence is in `results/sdf_klein_20260913/final_summary.json`: source,
binary, CPU/Python comparisons, fault cases, sanitizers, native instructions and
hardware counters remain separate categories. The joint 1 KiB cache observation
and distributed bulk 4.625 MiB observation belong to different execution profiles.
