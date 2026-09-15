# Exact bounded phase and seam lowering

Profile: ATOMOS-EXACT-PHASE32-R1. This changes the implementation of canonical
finite TOMAGI PHI, TIME, KLEIN and LSYS phase operations. It preserves every
raw State64 word, fault and receipt, and their ordered feedback composition.
It neither introduces golden-ratio arithmetic into PHI nor adds winding state
to KLEIN. The separately inherited exact-expression and lifted-chart profiles
retain their own definitions.

The source mechanism and locations are pinned in the R17 original-return
audit. R18 retains the previous wide expressions behind
`ATOMOS_WIDE_PHASE_REFERENCE`; this is an explicit build comparison option,
not a different semantic profile. The unmodified C interpreter remains an
independent oracle. The previous helper is preserved byte for byte in
`review/tomagi_transition_r17.cuh`.

## 1. Complete Euclidean PHI/TIME quotient without a wide sum

Let `A,B` be unsigned 32-bit words and `a=s32(A), b=s32(B)`. For PHI take
`p=12`; for TIME take `p=14`; write `M=2^p`. The canonical result satisfies

\[
a+b=Mq+r,\qquad 0\le r<M.
\]

For each input set

\[
q_a=(A\gg p)-(A\gg31)2^{32-p},\quad r_a=A\mathbin{\&}(M-1),
\]

and similarly for `B`. The two quotient terms are converted from their
bounded nonnegative values to signed32 before subtraction. Since
`s32(A)=A-(A>>31)2^32`, these definitions give `a=M q_a+r_a` exactly.
Define

\[
t=r_a+r_b,\quad q=q_a+q_b+(t\gg p),\quad r=t\mathbin{\&}(M-1).
\]

Substitution proves the canonical Euclidean quotient and remainder. Both
input quotients lie in `[-2^(31-p),2^(31-p)-1]`. The remainder sum is at most
`2M-2`; its carry is 0 or 1. Thus PHI's complete quotient lies in
`[-1048576,1048575]`, and TIME's in `[-262144,262143]`. All intermediate
quotient arithmetic fits signed32; no signed-overflow assumption is used.

The implementation keeps the **complete signed q**. PHI's wrap status tests
`q!=0`, its selected parity branch/orientation uses `q mod 2`, and TIME's
lineage mixes the raw 32-bit representation of `q`. Retaining only remainder
or parity would break observable behavior. The other instruction fields and
the mandatory pre-key, lineage and successor postlude are unchanged.

## 2. Finite KLEIN seam update

For raw rho word `R`, the canonical period is `2^20`. Therefore

\[
\rho'=R\mathbin{\&}(2^{20}-1),\qquad
\epsilon=(R\gg20)\mathbin{\&}1.
\]

Signed interpretation subtracts `2^32` when the sign bit is set, changing the
quotient by `2^12`, an even integer. It does not change the remainder or seam
parity. If `epsilon=1`, define `theta0=Theta & (2^18-1)`. The source half-turn
and reflection are respectively

\[
\theta'=(\theta_0+2^{17})\bmod2^{18},\qquad
\theta'=(2^{17}-\theta_0)\bmod2^{18}.
\]

Phase becomes `(-Phi) mod 2^12`. Compute subtraction with unsigned word
arithmetic and retain the appropriate low bits. Each period divides `2^32`,
so unsigned wrapping commutes with its final modular reduction. Preserve
orientation, optional sheet, wrap flag, branch and canonical normalization.
The even-seam path still performs the canonical normalization and postlude.

This equality covers raw negative/non-normalized input words. It preserves
the source's finite seam parity; it cannot reconstruct an unbounded winding
history that the source State64 never stored.

## 3. LSYS phase and rate have different division contracts

Let `o=orientation&1`, `b=branch&1`, and let `A` be the raw signed turn
argument. Chirality times branch-turn sign is positive exactly when
`o xor b=1`. Thus set

\[
D=\begin{cases}A&o\oplus b=1,\\-A\pmod{2^{32}}&o\oplus b=0,\end{cases}
\qquad\Phi'=(\Phi+D)\mathbin{\&}(2^{12}-1).
\]

The period divides `2^32`, proving equality with the original wide signed
phase expression, including `INT_MIN` turn and raw phase words. This update
does not alter the rates' truncation-toward-zero contract. Rates continue
using R17's proved unsigned magnitude/right-shift/sign-restoration identity
for the clamped shift in `[0,30]`. PHI/TIME continue using floor division.

## 4. Composition, validation and performance scope

Replacing an expression with an equal result for every admitted input does
not change its enclosing canonical transition. The retained postlude and
ordered injection/VM/commit then give the R17 fused composition theorem.
Journaling records those actual transitions; it must not reorder them.

The boundary suite tests signed endpoints, both sides of each period,
negative exact multiples, carries, raw orientation/branch words, all phase
and seam flag choices, both fetch paths, reference/fused dispatch and word
injection against the unchanged C machine. Compiled-resource inspection and
matched measurements with the wide build establish implementation costs
separately. Source-level operation counts alone do not prove speed, texture
cache behavior, occupancy or memory saturation.
