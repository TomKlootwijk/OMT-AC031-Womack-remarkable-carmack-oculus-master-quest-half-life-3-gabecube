# ORBIT-DYNAMICS-R2: executable physical model

R2 retains a six-component Cartesian GCRS state in SI units and the same explicit
ASA/NA and JK query controller. It replaces R1's selected low-degree gravity terms
with the complete static EGM96 field through degree and order 12, uses all relevant
Earth-orientation rows published before the seed epoch, and adds the specified
Schwarzschild correction. The binary seed contains every numerical coefficient
needed for replay. It does not contain future target satellite coordinates.

The implementation is [orbit_precision.py](../python/orbit_precision.py), dispatched
by [orbit_dynamics.py](../python/orbit_dynamics.py). The retained R1 equations and
results are documented separately in [ORBIT_DYNAMICS.md](ORBIT_DYNAMICS.md).

## State, time and frame

The differential equation is `dr/dt = v`, `dv/dt = a`. Query time `t` is full GPST
seconds relative to the seed epoch; TT = GPST + 51.184 s. The January epoch is
1419811200 GPST seconds since 1980-01-06, and the February confirmation epoch is
1422489600. UTC = GPST - 18 s for these 2025 arcs. Horizons target vectors are
geometric, Earth-centred ICRF states labelled TDB, converted to TT with ERFA's
geocentric Fairhead-Bretagnon correction before comparison. They are not apparent
light-time-corrected observations.

Define `M(t) = P(t) Rz(ERA(t)) Q(t)`, with `rE=M r` and
`vE=M v + Mdot r`. `Rz` is passive:

```
Rz(a) = [[cos(a), sin(a), 0], [-sin(a), cos(a), 0], [0,0,1]].
P = [[ cx,       0,       sx    ],
     [ sy*sx,    cy,     -sy*cx ],
     [-cy*sx,    sy,      cy*cx ]],
cx=cos(xp), sx=sin(xp), cy=cos(yp), sy=sin(yp).
```

`P` equals `erfa.pom00(xp,yp,0)`. The TIO locator s-prime is explicitly zero.
`Q` is a degree-18 Chebyshev representation of the slowly varying IAU 2006/2000A
GCRS-to-CIRS matrix `c2i06a`. The domain is `[-691200,604800]` seconds: eight past
days for training and seven future days for queries. The rapid Earth rotation is
evaluated directly and is not approximated by a large matrix polynomial.

Each `eop_segments` block has three Chebyshev rows: ERA correction in radians,
xp in radians and yp in radians. The construction uses linear interpolation of
the published daily xp, yp and UT1-UTC values, including the prior UTC midnight
needed at the left GPST boundary. With `omega=2*pi*1.00273781191135448/86400`,

```
ERA(t) = ERA0 + omega*t + omega*(DUT1(t)-DUT1(0)).
Mdot = Pdot Rz Q + P Rzdot Q + P Rz Qdot.
```

The derivative includes both polar-motion rates and the ERA correction rate.
Piecewise-linear EOP derivatives use the later segment at a shared endpoint.
The January model uses Bulletin A published 26 December 2024; February uses the
bulletin published 30 January 2025. These are pre-epoch forecasts, not observed
post-epoch orientation. Their actual physical prediction uncertainty remains a
source of Earth-fixed position error even when coefficient replay is exact.

## Complete degree/order-12 gravity

Let `p=M r`, `rho²=p·p`, `aE=6378136.3 m`, and
`mu=398600441500000 m³/s²`, matching the supplied EGM96 source. Define solid
harmonics without the Condon-Shortley phase:

```
V00 = aE/rho, W00 = 0
X = aE*px/rho², Y = aE*py/rho², Z = aE*pz/rho², R = aE²/rho²
Vmm = (2m-1)*(X*V[m-1,m-1] - Y*W[m-1,m-1])
Wmm = (2m-1)*(X*W[m-1,m-1] + Y*V[m-1,m-1])
Vnm = ((2n-1)/(n-m))*Z*V[n-1,m]
      - ((n+m-1)/(n-m))*R*V[n-2,m]
Wnm = ((2n-1)/(n-m))*Z*W[n-1,m]
      - ((n+m-1)/(n-m))*R*W[n-2,m]
```

For `n=m+1`, the final term in each recurrence is omitted. The potential and
acceleration are

```
U(p) = (mu/aE) * sum(n=0..12, m=0..n, Cnm*Vnm + Snm*Wnm)
a_gravity = M^T * gradient_p U.
```

The positive gradient of this positive potential gives inward central gravity.
`C00=1`; every unused `Sn0` is zero. All entries above the triangular coefficient
domain are zero. The stored coefficients are unnormalized, converted from the
supplied fully normalized EGM96 values with

```
Nnm = sqrt((2-delta(m,0))*(2n+1)*(n-m)!/(n+m)!)
Cnm = Nnm*Cbar_nm, Snm = Nnm*Sbar_nm.
```

Thus `Cn0=-Jn`. R1 J2/J3/J4/C22/S22 fields are absent in the R2 JSON force object;
they are not added again. Coefficient provenance, original text and the converted
tables are retained in [gravity_reference](../source/orbit_data/gravity_reference).
This is a degree-12 truncation of a static tide-free model, not all of EGM96.

Independent Python evaluates the scalar potential and differentiates it by
complex-step perturbations of `1e-6 m`. The construction accelerator evaluates
Cartesian derivatives directly. Native C++/CUDA uses its own streaming Cartesian
derivative recurrence; a separate spherical-gradient audit checks that these
implementations agree with the same stated harmonic convention.

## Other forces

Sun and Moon acceleration retains the indirect Earth term:
`a_b=mu_b*((rb-r)/|rb-r|³-rb/|rb|³)`. Earth-centred body vectors are constructed
from DE440s, including the Earth-Moon barycentre-to-Earth offset. One degree-16
Sun block and one degree-30 Moon block cover the full domain. Geocentric TT-to-TDB
conversion is included when evaluating the source ephemeris. Future planetary
forcing from the already published dynamical model is allowed; future target
satellite states are never put into these forcing blocks.

The January construction's independent off-node approximation maxima are
1.986 m for Sun position, 0.060 m for Moon position and `9.27e-15` for a Q matrix
entry. These are coefficient approximation discrepancies, not satellite errors.
Each epoch's construction envelope records its own audit values.

The fitted cannonball SRP acceleration is
`A*(AU/|r-rsun|)²*(r-rsun)/|r-rsun|`. If shadow is enabled it is set to zero behind
Earth when the distance to the Sun-Earth axis is less than aE. This remains a
cylindrical shadow with no penumbra. Three fitted constants act along instantaneous
radial, transverse and normal unit vectors, constructed from r and r-cross-v.

The Schwarzschild term is enabled explicitly and uses `c=299792458 m/s`:

```
a_GR = mu/(c²*|r|³) * [(4*mu/|r| - v·v)*r + 4*(r·v)*v].
```

This does not include every relativistic effect. The model also does not include
solid-Earth/ocean tides, atmospheric drag, solar-disc penumbra, detailed spacecraft
attitude/panel geometry, thermal thrust, albedo or unknown future manoeuvres.
Constant empirical accelerations continue past the fitted arc by explicit model
assumption. A longer query domain is not an accuracy guarantee.

## Frozen past-only model selection

[build_precision_orbit_models.py](../tools/build_precision_orbit_models.py) uses
the same ten fitted parameters, bounds and objective for every object: Cartesian
state6 at the arc centre, SRP1 in `[0,5e-6] m/s²`, and constant RTN3 each in
`[-2e-6,2e-6] m/s²`. Every sixth five-minute reference row, the centre and endpoint
enter the least-squares fit; all rows enter the reported residual audit. The
declared weak RTN regularization remains unchanged.

For each of the fixed candidate windows 1, 3 and 7 days, fitting ends one day
before the epoch. Prediction over the final past day supplies an internal
holdout score. The smallest maximum 3D error wins; ties prefer the shorter
window. The selected duration is then fitted again ending at the seed epoch.
All target times strictly after the epoch are excluded. The full state propagated
from the fitted anchor to the epoch becomes the seed state.

The fixed numerical choices are 30 s RK4 during fitting, at most 35 objective
evaluations, and 30 s native replay except Chandra's 7.5 s. The Chandra replay
choice was made from numerical convergence against DOP853, not future target
coordinates. The fixed selection policy and its hash are recorded in each model
directory's `selection_policy.json`.

For the January construction the selected windows are 3 days for G05, C03 and C06,
and 1 day for Chandra. The internal last-day maximum errors are respectively
0.926, 4.389, 1.631 and 0.321 m. Final fitting RMS/max errors are 0.264/0.531,
0.857/2.442, 0.357/0.642 and 0.019/0.052 m. These are past-data diagnostics.
They do not establish a 10 m future prediction horizon.

The January 2–9 comparison is explicitly a reused benchmark: its baseline R1
errors had already been inspected. February 2 is a separate confirmation epoch
constructed under the same frozen rule from January 25–February 1 target data
and the January 30 EOP bulletin. Its future data remains separate from fitting
and selection. No rigid alignment, future-target correction polynomial or
per-query target sample is fitted or packed.

## Runtime and validation

The strict model validator checks the R2 profile, exact required schema, complete
finite state and constants, triangular coefficient convention, Boolean relativity
and shadow, contiguous coefficient coverage and declared query/integration bounds.
The packed native payload uses `ORBIT-SEED-NATIVE-2` and includes GRAVITY,
RELATIVITY and EOP blocks. The permanent binary seed remains the complete root
seed format and includes the separate ASA/NA and JK control contract.

Replay needs no source SP3, Horizons files, gravity file, DE440 kernel, ERFA,
JPL package or network access. Numba is optional when importing the replay model;
the Python fallback preserves validation and frame evaluation. Numba accelerates
construction. Independent SciPy DOP853 uses the complex-step Python force with
relative tolerance `2e-12` and component absolute tolerance `1e-6` in SI units.
These are integrator settings, not a physical orbit-position acceptance budget.

Physical agreement with target ephemerides, numerical agreement between solvers,
and exact packed reconstruction are reported separately. A 10 m physical budget
must be demonstrated over each stated forecast horizon by external reference
comparison; it cannot be derived from key cell width or lossless seed encoding.
