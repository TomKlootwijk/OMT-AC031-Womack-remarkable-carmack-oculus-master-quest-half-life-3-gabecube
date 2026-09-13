# Tom Klootwijk atomOS: the compiled SDF/NOR universality construction

This is a new explicit execution profile based on the M1 formalization's ASA
whole-word operation, packed predicate dictionary, Klein quotient, and finite
machine-simulation construction. It is not attributed to an SDF compiler or
circuit-wiring equation absent from the supplied 43-page PDF. The analytic
construction, its implementation tests, and its measured cache behavior are
different evidence categories.

## 1. The source word operation gives a NOR primitive

For Boolean a and b, propose the word x = 1 | (a << 1) | (b << 2).
Use ASA=NA=fringe=7, boundary=6 and a valid mask admitting these three cells.
The source aperture leaves x; NA leaves x; the boundary intersection contains
exactly a+b marked input cells. If either input is true, whole-word absorption
returns zero. Otherwise only the constant output marker remains, yielding one.
Thus the entire final word is NOR(a,b), not merely a word with an incidental
matching output bit.

This preserves M1 page 17's whole-word semantics. With per-bit clearing the
constant marker would always survive and the construction would fail. The
candidate producer supplies its constant marker before the contracting selector;
the selector never invents support. This is not repeated application of one
fixed contraction to its previous result. The existing shift producer's zero
guard remains a different producer profile.

The accompanying `sdf_nor.smt2` obligations check the identity and clean final
word at the bit-vector level. Such obligations do not verify generated machine
instructions or the SDF compiler.

## 2. Geometry and storage preserve the primitive

The declared `nor_sites` geometry uses disjoint metric disks around sampled
log-polar cell centres 0, 1 and 2 within each logical 32-cell group. ASA, NA and
fringe admit those sites; the blocking region admits sites 1 and 2. The metric
and disk parameters are explicit compiler inputs. They are defined on the flat
normalized Klein quotient, not inferred from a three-dimensional rendering of a
bottle. A numerical signed distance and its sampled Boolean sign are distinct
representations.

The compiler evaluates the signed-distance predicates, packs their samples into
canonical words, and records its configuration. Independent geometric/sample
checks must establish that each word is exactly (7,7,6,7). The native loader
checks byte count, all logical masks, all padding, and the selected layout.
Changing linear/Morton storage preserves the words by the bijection already
described in M1 page 27.

For lifted integer gate coordinates the mandatory Klein map performs signed
floor angular winding and reflects radial cell-centre row i to R-1-i when the
winding is odd. Gate placement deliberately uses winding representatives -1,
0 and +1. It therefore executes the twist, rather than discarding winding with
a plain angular modulo. Whole logical words map to whole logical words under
this reflection. The run exports each gate's actual texture index and parity;
the checker independently reconstructs them.

Every native gate performs `tex1Dfetch<uint4>` of these operator masks, then
calls the preserved source word operation. An ordinary global-memory Rule table
is not passed to this kernel. Altering an operative texture predicate changes
the gate truth function; the injected-operator test must detect the discrepancy
and reject the epoch.

## 3. NOR circuits represent every finite controller

NOR gives NOT(a)=NOR(a,a), OR(a,b)=NOT(NOR(a,b)), and
AND(a,b)=NOR(NOT(a),NOT(b)). For each possible finite control state q and read
symbol a, the compiler constructs bit-equality predicates. Exactly one pair of
these predicates is true for any valid encoded input. For a defined transition,
their conjunction activates its minterm. OR-reducing the active minterms for
each output bit reproduces next control, written symbol, left/right movement,
rule-defined status and halt status. Halt-state rows suppress rule execution.
Absent minterms produce zero, so a missing rule is explicit rather than guessed.

Each composed operation expands into NOR gates only. The graph uses indices
strictly below the new gate's output index, so evaluation is acyclic. Inputs are
control bits, symbol bits and one explicit zero bit. A NOR(0,0) signal supplies
one, and equality predicates use that computed signal. Induction over gate
order proves all signals remain Boolean and every gate equals its intended
Boolean subexpression. The minterm argument then proves equality of the decoded
controller and the supplied finite transition function for every valid input.

The source Program table is used by the host compiler and independent CPU
oracle. It is not a second runtime path that secretly calculates device results.
Program-specific wiring is ordinary immutable metadata; the primitive operator
dictionary is the SDF-derived texture. The theorem concerns this explicit
combination of representation, routing, state and operators. Klein topology or
a fixed SDF surface alone is not asserted to be universal.

## 4. Machine simulation and memory assumptions

Use the finite controller with a writable symbol tape, control register and
signed logical head position. Initially the decoded tape, control and head
agree with the source machine. Suppose they agree before a defined step. The
same symbol is read; section 3 gives the same next-control/write/move outputs;
the packed write modifies only the addressed symbol block; and the identical
head update is applied. Other symbol blocks are unchanged. Induction gives
agreement for every supported finite prefix, including the same entry into a
halt state. The existing packed-field preservation proof is an additional
representation obligation, not a substitute for the controller proof.

In the abstract construction, logical addresses and enough storage must exist
for each prefix. This is the precise computational universality sense of M1
pages 31–32. The executable uses finite signed addresses and finite allocated
memory. It does not identify tape positions modulo the finite operator atlas.
The Klein operator dictionary is shared computational structure; distinct tape
positions retain distinct backing storage. A finite closed atlas without a
nonaliasing address extension would eventually conflate positions and would
not establish the unrestricted simulation theorem.

On the concrete device, an unavailable next cell or signed-address overflow is
detected before any part of that transition is written. A missing rule also
writes nothing. Reaching the chosen step budget means running, unless the last
completed transition entered a halt state. A bounded oscillator can continue
for arbitrarily many successive abstract ticks without establishing that all
programs halt or that an arbitrary finite device has unbounded capacity.

## 5. What must be verified before publication

The native profile stages a complete candidate epoch. It compares the exact
chronological evaluation count, each evaluation's control/head/read symbol,
each decoded controller output, every gate input/output/mask/address/parity,
every completed transition, final machine status, and every packed tape word
including untouched tail bits. Gate checks use an independent Boolean evaluator;
transition checks use the independent sparse-map machine oracle. The independent
Python export checker is a further implementation check.

Only running or halted candidates that satisfy all these checks are committed.
A required program error or a verification mismatch leaves the committed
machine and tape equal to the original epoch input. Candidate traces remain
available as rejected proposals. This is local checked publication, not a
filesystem crash-consistency theorem or an external authentication claim.

The operator atlas remains immutable during the launch and its texture object
is destroyed before its backing allocation. Warm/readback checksums and matching
SM identifiers test the declared sweep and placement observations. Cache
residency still requires actual hardware counters for this precise warm/work/
reread kernel; it does not follow from these algebraic proofs or from a prior
kernel's measurements. Likewise, the finite instruction/sanitizer/correctness
tests are evidence about their tested binaries and cases, not a universal proof
of the compiler, GPU or every possible application.
