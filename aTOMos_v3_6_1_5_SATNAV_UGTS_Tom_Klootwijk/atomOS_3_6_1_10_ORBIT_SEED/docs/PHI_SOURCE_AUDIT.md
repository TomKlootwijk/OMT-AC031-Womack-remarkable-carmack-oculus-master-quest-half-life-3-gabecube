# Supplied phi / binary-word source: audit and transfer decisions

The useful transfer is an explicit finite-state, bitfield architecture. R10 uses an exact bit permutation to implement its existing lossless bitplane format. The supplied source does not establish replacement orbital dynamics, a more accurate ground-station angle, or compression of arbitrary physical coordinates into one bit. Its named transforms are accepted only where their equations support the claimed property.

## Source and scope

- Supplied file: `C:/TOMONETMALFORMED/3.6-phi-2pi-fibonacci-36-10---07---1990-gregorian-calander-Tom-Klootwijk.pdf`.
- SHA-256: `0fddbd55ba01bad0c94b435ddf89c4b778e8a94776946f6cc60cfbed860c5116`.
- 21 physical pages. Page references below are the visible `n / 21` export page numbers. The file is an exported Google Search AI conversation, containing suggestions, pseudocode and claims labelled as proofs. These labels are not independent validation. Equations were checked against rendered pages, not solely extracted text.
- This audit supplies mathematical and implementation counterexamples. No future satellite observations were used, and no fitted physical parameters were changed for this transfer. The pre-existing package's UGTS OTAN2 definition is distinct from the new operator called OTAN2 on source pages 16-17.

## Accepted, corrected and rejected mappings

| Source pages | Source construction | Decision and practical application |
|---|---|---|
| 7-12, 19 | Explicit 64-bit fields, Boolean transitions and a word pipeline | **Accept the organization.** Field widths, signedness, masks, overflow and update order must be part of the contract. A finite word can carry states, counters, flags and indices. It does not preserve arbitrary real-valued state in 64 bits. |
| 4, 8 | Phase sweep and a finite phase counter | **Correct.** Use a declared epoch, period and timescale, with an integer cycle count plus a phase remainder. The fractional-part function is a sawtooth, not itself a Fourier transform. Its range is `[0,1)`. Preserve the absolute timestamp for orbital queries. |
| 5, 9 | Normalized Hadamard and the golden-ratio pinion vector | **Partly valid.** The normalized Hadamard is orthogonal; its further component scaling is not. It preserves four-dimensional volume magnitude, not all lengths or areas. The masked integer pseudocode is lossy. Do not transform physical binary64 values with it. |
| 5, 11 | Golden-ratio phyllotaxis and shifts | **Accept a declared sampling rule, not an equality.** `theta_n = 2*pi*n/phi (mod 2*pi)` is a valid rotation sequence. Multiplication by 2 or 1/2 is not multiplication by phi. A finite quantized sequence requires an explicit recurrence and has a finite repeat period. This can index visualization samples; it does not supply missing orbital observations. |
| 3-5, 15 | One-bit inside/outside predicates and a polar LUT | **Correct the name.** These are occupancy predicates. A Boolean result does not supply signed distance, distance derivatives or a metric. The printed sphere predicate lacks a three-dimensional radius, and the printed pyramid inequality defines an unbounded double cone. |
| 6-7, 10 | Recursive branch culling | **Accept only conservative bounds.** A parent bound must contain every descendant after all transforms. Parent-local exclusion from a slit does not prove that descendants cannot return. No forecast samples may be discarded by this unproved rule. |
| 6, 12-14 | Terminal inversion and a Klein-bottle claim | **Accept finite-state feedback; reject the claimed topological proof.** A loop and a sign/parity flip do not construct a Klein bottle. A surface would require explicit coordinate charts or boundary identifications. The displayed two-axis sign flip preserves spatial orientation. |
| 13-14 | Log radius and modular half-turn | **Accept with a chart domain.** Define dimensionless log radius relative to a positive scale. A binary-angle half-turn is an exact integer operation, but the printed packed mask is wrong. These can represent presentation coordinates and indices, with their loss stated. |
| 16-17 | Radius/occupancy-derived OTAN2 as an ATAN2 replacement | **Reject for geometric direction.** Equal radius and occupancy can correspond to different bearings. Mixing those inputs cannot reconstruct the lost angle. Keep the actual relative position and ENU transformation for azimuth/elevation. |
| 17, 20 | Infinite nesting and infinite volume from a fixed word | **Reject as a capacity claim.** A deterministic 64-bit state has at most `2^64` distinct states; a 5-bit depth field has 32 depth labels. Larger external state or an unbounded index must be explicitly accounted for. |

## Minimal checks and counterexamples

### Metric and integer information loss

Let `phi = (1 + sqrt(5))/2`, `H4 = H2 tensor H2`, and `A = diag(phi, phi^-1, 1, -1) H4`, exactly as on page 5. Then

\[
H_4^T H_4=I,\qquad |\det A|=1,\qquad
\|A(1,0,0,0)^T\|_2^2
=\frac{\phi^2+\phi^{-2}+2}{4}=\frac54.
\]

Consequently `A` increases this unit-vector length to `sqrt(5)/2`; orthogonality of `H4` does not transfer to `A`. Exact irrational phi scaling is also not the dyadic shift approximation printed on page 9.

In that page's integer code, both `(x,y,z,f)=(0,0,0,0)` and `(-1024,-1024,0,0)` are allowed by the stated field widths. The latter has Hadamard sums `(-2048,0,-2048,0)`, which become all zero after the given 11/10-bit masks. The phase adjustment contributes zero. Thus two distinct inputs have the same output. Page 11's right shift likewise maps both `f=0` and `f=1` to zero.

### Masks and execution semantics

- Page 8: `(W >> 63) & 0x001FFC0000000000` is identically zero: the first operand is 0 or 1, while the mask has bit 0 clear. An actual conditional XOR requires an expanded all-ones/all-zeros mask, or a branch, with the correct field mask.
- Page 9: XOR-complementing a two's-complement field gives `-x-1`, not `-x`. Its printed X/Z mask also covers different bits than the page-8 layout; the stated X/Z field mask would be `0x7ff001ffc0000000`.
- Page 12: `W += 4` is not a bit-2 toggle: `W=4` becomes `8`, changing another field. `W ^= 4` toggles exactly that bit.
- Page 14: for an 11-bit angle in bits `[51:41]`, adding half a turn modulo 2048 is XOR of field bit 10, hence XOR of word bit 51: `W ^= (1ULL << 51)`. The printed `0x000FFC0000000000` flips ten bits, rather than one.
- Pages 11-16: a left-to-right notation requires an explicit parser or temporaries. It does not change C/C++ precedence. For page 16, `log_r=2, O=0` gives `2` under C evaluation of `log_r ^ O << 10 & 0x7ff`, but `0` under strict left-to-right evaluation. Parenthesize the intended operation.

These are source-code defects, not reasons to weaken the existing kernel's exactness checks.

### Direction, domain and conservative bounds

The planar points `(1,0)` and `(0,1)` have the same radius and can have the same occupancy bit, yet their bearings differ by `pi/2`. Source OTAN2 therefore cannot replace `atan2` for a station line of sight. `atan2` is usable within three-dimensional coordinates; its two arguments do not restrict the world to a plane. Zero horizontal range requires a named azimuth-undefined case.

An 11-bit full-turn angle has bin width `360/2048 = 0.17578125` degrees. Nearest-bin rounding has a half-bin error of `0.087890625` degrees. At an illustrative radius of 42,164,000 m, the maximum single-angle chord error is

\[
2R\sin(\pi/4096)=64{,}678.76\ \mathrm m.
\]

At this radius, at least 24 angular bits are required even for a 10 m *single-angle quantization* bound; that calculation allocates nothing to range, other angles, model error, frame error or station uncertainty. For a station use the actual slant range, not a fixed geocentric radius.

Log coordinates need `rho = log2(r/r_star)` with `r>0` and `r_star>0`; the origin has no finite log radius. Page 4's `log|sin(omega_g t) cos(omega_c t) sin(omega_m t)|` is undefined at its zeros and is unbounded below. Away from zeros its log term is nonpositive, so it does not establish the nonnegative, monotonic translations assumed by page 7.

The culling inference fails even for a local interval `[1,2]` and slit `x=0`: translating the child by `-1` gives `[0,1]`, which intersects the slit. A correct test uses a bound on the entire descendant set, not just the current node. Finally, `diag(-1,1,-1)` has determinant `+1`: two sign flips alone do not prove non-orientability.

## Transfer into time, keys and the orbital seed

For integer ticks `n`, reference tick `n0`, and positive integer period `P`, define

\[
n-n_0=qP+r,\qquad q=\left\lfloor\frac{n-n_0}{P}\right\rfloor,
\qquad 0\le r<P.
\]

Retaining both `q` and `r` reconstructs the tick exactly, including negative elapsed time. Retaining only the phase does not: times one period apart collide. The seed's GPST/UTC/TT/TDB conversions, epoch and full timestamp remain authoritative. The filename's calendar, 3.6, phi, 2pi and Fibonacci references do not derive an orbital initial state, gravitational constant or timescale conversion.

Log-polar values, phase and occupancy may form *derived* display addresses or spatial keys. Their domain, origin, axes, quantization and wrap count must accompany them. Such keys do not replace metre-valued GCRS/ECEF/ENU geometry, carry the entropy of arbitrary coordinates, or establish cryptographic unpredictability. Keep full state and canonical content digests available for reconstruction and identity.

R10's useful packing transfer is exact binary structure. For a 64 by 64 array of bits, transpose exchanges row/column indices:

\[
B'_{c,r}=B_{r,c},\qquad T^2=I.
\]

Six stages exchange the corresponding row-index and column-index bits. Each stage is a permutation; their composition loses no information. R10 implements this bit transpose for the already specified bitplane format, retaining numeric bit patterns, tags, ordering, padding rules and the canonical digest. This algorithm is an engineering construction inspired by the source's word/butterfly organization; the source does not itself specify or prove it. No Hadamard arithmetic or golden-ratio quantization is imposed on physical binary64 coordinates. Correctness and speed must be established by the release's actual round-trip checks and benchmarks; this audit claims no measured speedup.

Acceptance is therefore specific: transfer the explicit binary organization, correct domains and modular arithmetic, and retain demonstrated physical equations and error evidence. The supplied text does not support a universal perfect-position forecast or a claim that representational changes remove model discrepancy.
