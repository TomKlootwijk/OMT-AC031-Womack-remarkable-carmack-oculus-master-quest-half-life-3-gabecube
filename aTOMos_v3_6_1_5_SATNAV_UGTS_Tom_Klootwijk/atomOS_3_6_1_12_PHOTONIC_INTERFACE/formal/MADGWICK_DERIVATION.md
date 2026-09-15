# Exact Madgwick operator derivation

Status: mathematical specification and conditional proofs, not an implementation,
machine-checked proof, simulation or new accuracy result. R10 is unchanged.

## Source and selected profile

Primary source: Sebastian O. H. Madgwick, *An efficient orientation filter for
inertial and inertial/magnetic sensor arrays* (2010),
https://x-io.co.uk/downloads/madgwick_internal_report.pdf.
Equation references below identify the source mathematics; expansions and proofs
use the explicit frame convention defined here. The selected profile is
`MDG2010-EQ-SIMPLIFIED-R1`: equations (25)--(34), (42)--(51), with declared
normalization, sample order and domain branches. Its MARG reference uses the
current sample and previous attitude, as in equation (45). Optional gyro drift
compensation follows (47)--(49). IMU mode does not estimate all-axis bias.

The finite-mixture derivation (35)--(38) is recorded separately below. It is not
algebraically identical to the simplified profile at arbitrary finite gain.
The modern x-io Fusion algorithm is a different revised algorithm and is not
silently included: https://github.com/xioTechnologies/Fusion.

The report's appendix C implementation updates magnetic reference after the
new attitude and reuses it at the next sample; this differs from equation (45)'s
time order. It also initializes `twom_x`, `twom_y`, `twom_z` before magnetometer
normalization and later uses those aliases in the flux update. Consequently a
literal lift of that C code requires its own specification, including its
unnormalized aliases, floating arithmetic and zero-division behavior. Neither
equation-profile equivalence nor bit identity with that code is asserted here.

## 1. Types, frame and state

Let B be the calibrated right-handed sensor/body frame and E the right-handed
filter reference frame. E's positive z direction is the accelerometer reference
direction after the declared sensor-sign conversion, and its x direction is the
chosen horizontal magnetic/heading reference. Do not identify E with geodetic
ENU without an explicit alignment.

`q_att = q = (w,x,y,z)` is a scalar-first Hamilton quaternion mapping B vectors
to E vectors by `[0,v_E] = q*[0,v_B]*conj(q)`. It obeys `q.q=1`.
`q_word` denotes the separate uint32 JK word; no field is shared with `q_att`.
For `a=(a0,a)` and `b=(b0,b)`, Hamilton multiplication is
`a*b=(a0*b0-a.b, a0*b+b0*a+a cross b)` and conjugation is `(a0,-a)`.

Inputs at event n are the exact ordered record
`I_n=(id_n,t_n,omega_n,a_n,m_n,validity_n,calibration_id)`.
The calibrated gyro is in rad/s, acceleration in m/s^2 before direction
normalization, and magnetometer values in a consistent declared magnetic unit.
`h_n=t_n-t_(n-1)>0` is seconds on one declared monotonic time scale. Source sensor
time must have a declared mapping to GPST before combining with orbital output.
Acceleration is a measured specific-force vector; its sign must be calibrated
to the declared reference rather than inferred from the word "gravity".

Initial q is either declared unit or obtained from a nonzero supplied Q by exact
normalization. With optional MARG drift, the persistent bias is `b_omega in R^3`
in rad/s. Constants include beta>=0 (1/s), zeta>=0 (1/s^2), calibration transforms,
initialization policy, magnetic-reference policy, frame/mounting transforms,
event-order and missing-data rules. Fixed calibration and estimated bias must
not be subtracted twice. The selected current-reference profile has no independent
persistent magnetic b; a lagged-reference variant requires its two components
and initialization in the state.

Raw ADC integers with exact scale ratios remain rational. Finite IEEE literals
have their exact dyadic-rational meanings, with original bit payload separately
retained when required. An exact decimal ratio is a different literal type.
Degree/radian conversion introduces symbolic pi when applied exactly; pi is a
transcendental constant, not a rational approximation. A purely algebraic profile
therefore accepts already declared rational/algebraic radian inputs or treats the
conversion as a separate transcendental extension. No physical sensor accuracy
is inferred from the exact value assigned to its recorded sample.

## 2. Rotation and objective functions

For unit q, the body-to-E rotation is

```text
R(q) = [[1-2(y*y+z*z), 2(x*y-w*z),   2(x*z+w*y)],
        [2(x*y+w*z),   1-2(x*x+z*z), 2(y*z-w*x)],
        [2(x*z-w*y),   2(y*z+w*x),   1-2(x*x+y*y)]] .
```

Normalize each admitted nonzero observation using
`N(v)=v/sqrt(v.v)`, with the positive square root. Write the resulting
accelerometer and magnetic directions as `a_hat` and `m_hat`.
For the reference `g_E=(0,0,1)`, source equations (25)--(26) become

```text
f_g = [2(x*z-w*y)-a_hat_x,
       2(w*x+y*z)-a_hat_y,
       1-2(x*x+y*y)-a_hat_z]
J_g = [[-2*y,  2*z, -2*w, 2*x],
       [ 2*x,  2*w,  2*z, 2*y],
       [   0, -4*x, -4*y,   0]] .
```

For magnetic reference `b_E=(b_x,0,b_z)`, equations (29)--(30) become

```text
f_b = [b_x*(1-2(y*y+z*z))+2*b_z*(x*z-w*y)-m_hat_x,
       2*b_x*(x*y-w*z)+2*b_z*(w*x+y*z)-m_hat_y,
       2*b_x*(w*y+x*z)+b_z*(1-2(x*x+y*y))-m_hat_z]
J_b = [[-2*b_z*y,           2*b_z*z,       -4*b_x*y-2*b_z*w, -4*b_x*z+2*b_z*x],
       [-2*b_x*z+2*b_z*x,   2*b_x*y+2*b_z*w, 2*b_x*x+2*b_z*z, -2*b_x*w+2*b_z*y],
       [ 2*b_x*y,          2*b_x*z-4*b_z*x, 2*b_x*w-4*b_z*y,  2*b_x*x]] .
```

These are ambient derivatives of the displayed source polynomial extension,
evaluated at a unit q. Treat b as fixed while computing J_b. Derive each entry
by differentiating its row with respect to `(w,x,y,z)`; for example
`d(f_b1)/dy=-4*b_x*y-2*b_z*w` and `d(f_g3)/dw=0`.
Replacing the off-sphere polynomial by a homogeneous quaternion expression can
alter its ambient gradient even when both objectives agree on the unit sphere.

For IMU, `f=f_g`, `J=J_g`; for MARG, vertically stack the two residuals and
Jacobians. For the half squared residual `F=0.5*f.f`, the gradient is
`s=J^T*f` (chain rule), with `s_g=J_g^T*f_g` and
`s_MARG=s_g+J_b^T*f_b`. This fixes the relative weights to the source's unweighted
sum. Additional sensor-dependent weighting would define a different profile.

The source current magnetic reference is computed *before* the residual:
`h_E=R(q_(n-1))*m_hat_n`,
`b_x=sqrt(h_Ex^2+h_Ey^2)`, `b_z=h_Ez`.
Although b is computed from the current state, the source residual-gradient step
holds the resulting b fixed. Differentiating through this reference update would
introduce extra chain-rule terms and change the recurrence.

**Proposition M1 (reference norm).** For unit q and unit m_hat, the constructed
reference satisfies `b_x>=0` and `b_x^2+b_z^2=1`.
Proof: quaternion rotation preserves vector norm; squaring the definition of b_x
and adding b_z^2 yields `h_E.h_E=1`. This proves a representation identity, not
that the measured magnetic direction is physically undisturbed.

## 3. Exact discrete recurrence and gyro drift

Define `e=0` when `s.s=0`, and `e=s/sqrt(s.s)` otherwise. Zero means no
gradient correction; it is a declared extension of the source's otherwise
undefined normalized-gradient expression, not evidence of correct attitude.

For enabled MARG drift with both admitted reference vectors and `b_x>0`, let
`d_omega=2*vec(conj(q_(n-1))*e)` and
`b_omega_n=b_omega_(n-1)+zeta*h_n*d_omega`.
Use `omega_c=omega_n-b_omega_n` in this sample, explicitly fixing the updated-bias
order. Otherwise hold bias and use its previously held value. With zeta=0 the
state is constant. The vector projection discards the scalar component; a
normalized ambient gradient need not be tangent to the quaternion sphere.
Component expansion, for `e=(e_w,e_x,e_y,e_z)`, is

```text
d_omega = 2*[w*e_x-x*e_w-y*e_z+z*e_y,
             w*e_y+x*e_z-y*e_w-z*e_x,
             w*e_z-x*e_y+y*e_x-z*e_w] .
```

The selected recurrence is
`d_q=0.5*q_(n-1)*[0,omega_c]-beta*e`,
`u=q_(n-1)+h_n*d_q`, `q_n=N(u)` for `u.u>0`.
The source gain parameterization may be retained symbolically as
`beta=sqrt(3)/2*omega_error`, `zeta=sqrt(3)/2*gyro_drift_rate`.
The error/drift parameters remain declared inputs, not inferred guarantees.

**Proposition M2 (unit norm).** Every successful update has `q_n.q_n=1`.
Proof: `u.u=S>0`, hence `N(u).N(u)=S/(sqrt(S)^2)=1`.
Initialization and induction establish the invariant across any finite accepted
input prefix. The proof assumes the positive-root and nonzero-domain obligations.

**Finite-mixture source family.** Set `d_w=0.5*q*[0,omega_c]`,
`mu=alpha*||d_w||*h` with alpha>1, and
`gamma=beta/(mu/h+beta)` where its denominator is positive. Before final
normalization the mixed state is
`u_mix=q+(1-gamma)*h*d_w-gamma*mu*e`.
Because `gamma*mu=(1-gamma)*beta*h`, this is
`q+(1-gamma)*h*(d_w-beta*e)`. It is generally not the selected update with h.
If both denominator terms vanish, this specification chooses gamma=0.
At zero corrected rate and beta>0, mu=0 and gamma=1: finite mixing holds q even
when e is nonzero. The source's large-alpha simplification is consequently not
an identity valid at every stationary input. The exact-operator representation
preserves whichever family is explicitly selected; it does not erase that
modeling/discretization choice.

## 4. Domain branches and input order

These are specification choices resolving otherwise partial equations:

| Condition | Defined action |
|---|---|
| Initial quaternion zero | No initialized state; request an explicit nonzero initialization. |
| Nonfinite/untyped input, invalid timestamp mapping, or missing gyro | No transition; record an input-domain failure. |
| Duplicate or decreasing event time | No transition; ordering/duplicate resolution belongs to a separately declared input policy. |
| Zero or explicitly missing acceleration | Set e=0; gyro-only update without demanding a residual, magnetic correction or drift adaptation. |
| Nonzero acceleration, zero/missing magnetometer | IMU objective; hold all-axis drift estimate. |
| Both vectors admitted, b_x=0 | MARG residual may be evaluated, but mark heading-degenerate and hold all-axis drift adaptation. |
| Gradient exactly zero | Set e=0; no gradient-driven bias increment. |
| beta=0 | No attitude-gradient correction; independently enabled zeta is still a different operation. |
| Candidate quaternion u exactly zero | No transition; hold last complete state and report undefined normalization. |
| Missing/invalid observation quality | Use the explicit supplied flag; no silently invented small-norm epsilon or outlier rejection. |

All state changes are committed together only after a valid u is established.
The source does not supply the whole table; these branches are visible additions.
Exact algebraic zero/sign predicates decide their mathematical conditions.
A transcendental extension must retain unresolved comparisons rather than
silently replacing them by floating thresholds.

## 5. Operator-graph lift and normalization rewrites

An immutable graph uses typed literals, add/subtract/multiply/divide, positive
sqrt, tuple/projection, dot/cross/Hamilton product, and explicit piecewise nodes.
State roots and sample identities bind the operator template, gains, calibrations,
clock mapping and branch policy. All denominators carry nonzero obligations;
sqrt operands carry nonnegative obligations. Algebraic inputs stay algebraic by
closure under these operations. Exact sign/equality is mathematically decidable
for real algebraic numbers, but this is not a bounded-cost implementation claim.

**Proposition M3 (valid scale cancellation).** For c>0 and v!=0,
`N(c*v)=N(v)`. Proof: `sqrt(c^2*(v.v))=c*sqrt(v.v)`.
For c<0, the normalized quaternion changes sign; its rotation may be the same
while its representative/serialized identity differs. For c=0 normalization is
undefined. Rewrites must retain these premises.

**Proposition M4 (rotation without the quaternion sqrt).** For v!=0 and
`S=v.v`, rotation by `N(v)` is
`vec(v*[0,p]*conj(v))/S`. Proof: each of the two quaternion factors contributes
`1/sqrt(S)`, so the product denominator is S. This removes the normalization
sqrt for that consumer, not for every later gradient or bias operation.

**Proposition M5 (pure-gyro projective update).** If the corrected gyro is fixed
for the step and no attitude-gradient correction is applied, then
`N(N(v)+h/2*N(v)*[0,omega_c]) = N(v+h/2*v*[0,omega_c])`
whenever the candidates are nonzero. Factor `1/sqrt(v.v)` and apply M3.
For real h and corrected rate, Hamilton norm multiplicativity gives
`||v+h/2*v*[0,omega_c]||^2=(v.v)*(1+h^2*||omega_c||^2/4)>0` when v!=0.
Thus the candidate is automatically nonzero in this subcase; the same inference
does not apply to a candidate with an attitude-gradient correction.
Thus a homogeneous state can postpone normalization in the pure-gyro subcase.

With correction, the corresponding numerator is
`v+h/2*v*[0,omega_c]-h*beta*sqrt(v.v)*e(N(v))`.
Deleting the sqrt or substituting the source unit-sphere polynomial directly at
unnormalized v changes the recurrence in general. Likewise
`grad_v(F(N(v)))=(I-q*q^T)*s/||v||`; this projected gradient is not the source's
ambient s or its normalized direction e. Projective optimization must use proved local rewrites,
not substitute a different descent direction.

**Proposition M6 (quaternion sign cover).** R(q)=R(-q), because each rotation term
is quadratic. With the same input/reference, `f(-q)=f(q)`, `J(-q)=-J(q)` and
`e(-q)=-e(q)`; gyro drift increments are unchanged and candidate u changes sign.
Thus the recurrence is sign-equivariant wherever defined. This is equivalence
of represented rotations, not equality of quaternion tuples, raw bits or hashes.
No automatic sign canonicalization is assumed. Euler-angle display or shortest-
arc comparison requires its own explicit convention and potentially transcendental
operations; no such display is fed back into the algebraic recurrence.

## 6. Sampling, causality and irreducible state history

Each accepted sample is processed in increasing mapped time. By induction the
state after n events depends only on the seed and events 1..n; no future sensor
sample is a numerical dependency. A restart needs q, optional bias, current event
time/index and, if selected, lagged magnetic state plus all retained calibration
or scheduler state. Fixed-dimensional root tuples do not imply bounded byte size:
exact expression roots can retain an arbitrarily growing dependency history.

For an alphabet of K possible sample records, there are K^n possible length-n
streams. An injective fixed-capacity B-bit record cannot represent all of them
once K^n>2^B. This is a statement about complete stream reconstruction; it does
not assert that every distinct stream produces a distinct final attitude.
Sharing repeated graph nodes avoids tree duplication but does not repeal this
counting bound or bound algebraic degree/evaluation cost. Rounded checkpoints
lose exact state lineage. An exact checkpoint must retain a sufficient exact
representation and all dependencies not absorbed by proved equalities.

JK/ASA may select when to *observe/export* an already computed attitude without
changing it. Dropping IMU samples, changing h, changing beta/zeta, or reordering
measurements changes the mathematical recurrence and needs a new profile/event
record. Noncommuting angular increments already show why replacing two steps by
one summed-rate step is not generally an identity. Observation scheduling must
not silently become sensor-integration scheduling.

## 7. Ground-station composition and error categories

Let L be the station ENU frame and A the antenna/camera frame. Let `C_(L<-E)`
be the declared filter-to-ENU alignment and `C_(A<-B)` the calibrated mounting.
Both are declared proper orthogonal rotations (`C^T*C=I`, `det(C)=1`), so
transpose equals inverse. An arbitrary scale/shear calibration matrix requires
a separate coordinate model and is not silently treated as such a rotation.
For a simultaneous station-relative line-of-sight vector `ell_L(t)`, the body
instrument vector is
`ell_A(t)=C_(A<-B)*R(q(t))^T*C_(L<-E)^T*ell_L(t)`.
The orbital kernel supplies ell_L from its satellite/station geometry; the
attitude operator changes its coordinates, not the satellite orbit. A moving
station additionally needs its position and velocity at the same t. An IMU
attitude quaternion supplies neither. Between-sample interpolation, latency
compensation, Earth-frame alignment, magnetic declination and mounting changes
are separate declared operators, not implicit extrapolation.

The orbit's discrete RK4 approximation, approximated forcing/frame coefficients,
source physical uncertainty, sensor calibration/noise and the attitude sampling
model remain even if graph evaluation is exact. For unit q and a fixed candidate
derivative G, the derivative of normalization gives
`N(q+h*G)=q+h*(I-q*q^T)*G+O(h^2)`. Thus the first-order unit-sphere field of this
normalized step is the projected candidate derivative. The gyro term is tangent,
but the ambient correction generally is not; the unprojected candidate derivative
is not automatically the corresponding continuous unit-sphere field.
If the ideal continuous
derivative F is smooth on a branch, Taylor expansion gives
`q(t+h)=q(t)+h*F(q(t),t)+O(h^2)`; an exact Euler-like discrete update still has
that discretization distinction. Normalization is a smooth map away from zero;
near zero candidates, zero gradients or mode switches, this local smoothness
argument cannot be applied without additional hypotheses. The reference here
is the selected discrete recurrence, not a proof of a particular continuous
filter's convergence or physical accuracy.

For measured direction alone, rotations about that direction are unobservable.
Two consistent nonparallel directions determine a rotation, with q and -q as
its two quaternion representatives; when b_x=0 the reference directions are
collinear. Linear acceleration violates the accelerometer-only reference model,
and disturbed magnetism does not become true heading through exact arithmetic.
GNSS/INS position fusion needs additional position/velocity/bias estimation and
GNSS observations; this attitude recurrence proves no millimetre position or
arcsecond pointing result.

## Logical strategy conclusion

Preserve the chosen equation graph and sample provenance, simplify only under
proved domain/sign identities, and defer numerical materialization to a declared
output precision. Distinguish exact literal semantics from physical knowledge.
No runtime has been added, no performance improvement has been measured, and no
new physical result follows from these conditional derivations alone.
