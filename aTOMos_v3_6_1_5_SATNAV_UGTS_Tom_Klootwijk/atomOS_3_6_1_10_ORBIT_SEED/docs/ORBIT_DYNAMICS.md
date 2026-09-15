# ORBIT-DYNAMICS-R1: retained baseline equations

This document describes the preserved R1 baseline. The upgraded R2 equations,
published varying Earth orientation and past-only model selection are specified
in [ORBIT_PRECISION_DYNAMICS.md](ORBIT_PRECISION_DYNAMICS.md). Baseline models and
seeds are retained with hashes in `examples/orbit/baseline_manifest.json`.

The orbital seed reconstructs a Cartesian satellite state at a requested timestamp.
Its initial state, force parameters, frame coefficients and planetary forcing are
explicit data. The ASA/NA and synchronous JK equations control the declared query
and refinement policy; they do not silently change the gravitational force. This
is a new physical specialization alongside the retained literal profiles.

## State and time

The model state is `state_gcrs = [rx,ry,rz,vx,vy,vz]`, in metres and metres/second,
in geocentric axes aligned with GCRS/ICRF. The linear query coordinate is seconds
from `epoch_gpst_s`, itself full GPST seconds since 1980-01-06. The seed also stores
the consistent Julian date in TT. TT = GPST + 51.184 seconds. At the example epoch,
2025-01-02 00:00:00 GPST, UTC is 2025-01-01 23:59:42 and
`epoch_gpst_s = 1419811200`. The TT Julian date is approximately
2460677.5005924073. These are time scales, not interchangeable calendar labels.

Horizons Chandra vectors are geometric, Earth-centred ICRF coordinates in km and
km/s, labelled TDB. Construction/review converts TDB to TT with the geocentric
SOFA Fairhead-Bretagnon correction and then to seconds from the same epoch. The
printed Julian dates have finite precision. No satellite light-time, atmospheric
refraction or signal-clock correction is included in this geometric orbit state.

## Explicit frame model

Let Q(t) be the embedded slowly varying GCRS-to-CIRS matrix, ERA(t) the Earth
rotation angle, and P the polar-motion matrix. The Earth-fixed frame is

`M(t) = P · Rz(ERA(t)) · Q(t)`, `r_E = M r`,
`v_E = M v + dM/dt r`.

The passive rotation has first two rows `[cos(a),sin(a),0]` and
`[-sin(a),cos(a),0]`. With `cx=cos(xp), sx=sin(xp), cy=cos(yp), sy=sin(yp)`,

```
P = [[ cx,       0,       sx    ],
     [ sy*sx,    cy,     -sy*cx ],
     [-cy*sx,    sy,      cy*cx ]].
```

This equals ERFA `pom00(xp,yp,0)`. The small TIO locator s-prime is explicitly
zero. Q is constructed with IAU 2006/2000A `c2i06a` and stored as nine degree-eight
Chebyshev rows over the eight-day model domain. ERA remains a direct linear
rotation; a polynomial does not attempt to approximate eight days of rapid Earth
rotation. Chebyshev derivatives supply dQ/dt, so Earth-fixed velocity includes
the changing celestial frame as well as Earth rotation.

Earth orientation comes from IERS Bulletin A XXXVII 052, published 26 December
2024, before all example training and prediction intervals. Its announced
January 1 and January 2 forecasts are interpolated to the seed epoch. Polar
motion is then held fixed, and UT1 advances with the constant slope of those two
published forecasts. Neither later observed Earth orientation nor later target
satellite positions enter construction. This approximate Earth-orientation
forecast is a distinct source of Earth-fixed prediction error. IGS20 reference
orbits are compared using this model; no unreported exact GCRS/IGS20 identity is
claimed. See [IERS frame conventions](https://iers-conventions.obspm.fr/content/chapter5/icc5.pdf)
and the [published bulletin](https://datacenter.iers.org/data/6/bulletina-xxxvii-052.txt).

## Gravity and non-gravitational acceleration

The differential equation is `dr/dt=v`, `dv/dt=a`. Gravity is evaluated in the
Earth-fixed axes, then rotated back by M transpose. With `p=M r`, radius R,
`s=pz/R`, gravitational parameter mu and reference Earth radius aE, the static
potential is

```
U(p) = mu/R * [1 - sum(n=2..4, Jn*(aE/R)^n*Pn(s))]
       + mu*aE^2/R^5 * [3*C22*(px^2-py^2) + 6*S22*px*py].
```

Acceleration is the positive gradient of this positive potential. The Legendre
polynomials are `P2=(3s²-1)/2`, `P3=(5s³-3s)/2`, and
`P4=(35s⁴-30s²+3)/8`. For each zonal term,

```
k = mu*Jn*aE^n/R^(n+3)
a_n = k*((n+1)*Pn(s)+s*Pn'(s))*p - k*R*Pn'(s)*ez.
```

For `f=3*C22*(px²-py²)+6*S22*px*py`, the tesseral contribution is
`mu*aE²/R^5 * (gradient(f)-5*f*p/R²)`. C22 and S22 are explicitly unnormalized;
the degree-two order-two conversion from fully normalized coefficients is
`C22=sqrt(5/12)*Cbar22`, likewise for S22. The seed stores the numerical constants
actually used, including `mu=3.986004418e14 m³/s²` and `aE=6378136.3 m`. This is
a declared truncated static field, not an implementation of the full EGM2008 or
IERS gravity standard. The spherical-harmonic convention is described in
[IERS Chapter 6](https://iers-conventions.obspm.fr/content/chapter6/icc6.pdf).

For each third body b (Sun and Moon), with Earth-centred vector rb,

`a_b = mu_b * ((rb-r)/|rb-r|³ - rb/|rb|³)`.

The indirect term removes the acceleration of the Earth. Sun and Moon vectors
are generated from the published DE440s planetary ephemeris, including the
Earth-Moon barycentre-to-Earth offset. They are stored as separate three-row
Chebyshev blocks: degree ten for the Sun and sixteen for the Moon. Future
planetary positions from a model published in 2020 are known forcing inputs;
future target satellite positions are not stored in these blocks. The measured
off-node approximation discrepancies across the example domain are 1.74 m for
the Sun and 0.049 m for the Moon. These are forcing interpolation discrepancies,
not satellite-position errors. [NASA/JPL DE440 description](https://ssd.jpl.nasa.gov/doc/de440_de441.html)
and [published kernel](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440s.bsp).

Solar radiation pressure is a fitted cannonball coefficient A, in m/s² at one AU:
`a_SRP = A*(AU/|r-rsun|)^2*(r-rsun)/|r-rsun|`. The cylinder shadow is explicit:
SRP is zero when the satellite is behind the Earth relative to the Sun and its
perpendicular distance to the Sun-Earth axis is below aE. Otherwise it is on.
This model has no penumbra, satellite attitude, panel articulation, albedo, thermal
thrust or telemetry-derived manoeuvre term.

Three additional fitted constant accelerations act in the instantaneous RTN
frame: `Rhat=r/|r|`, `Nhat=(r×v)/|r×v|`, `That=Nhat×Rhat` and
`a_emp=aR*Rhat+aT*That+aN*Nhat`. Their signed values are explicit in every seed.
They represent unresolved average acceleration during the training arc. Their
continuation into future time is a model assumption, not a guarantee that the
spacecraft keeps the same attitude or performs no manoeuvre.

The model does not include higher tesseral harmonics, gravity tides, relativistic
orbital acceleration, drag, finite solar-disc shadowing, attitude dynamics or
future manoeuvres. These omissions and the short training arc can limit useful
prediction time. They are not repaired by increasing packed key width.

## Training and held-out prediction

`tools/build_orbit_models.py` fits the same fixed ten parameters for all four
objects: six components of a state near the training-arc centre, one SRP
coefficient and three constant RTN accelerations. SRP is constrained to
0..5e-6 m/s² at one AU and each empirical component to +/-2e-6 m/s². Every sixth
five-minute row, the endpoints and the centre define the least-squares sample;
all training rows are retained for residual auditing. The weak, declared RTN
regularization is fixed before any future-target comparison.

GFZ G05 (MEO), C03 (GEO), and C06 (IGSO) use only the January 1 GPST SP3 file,
including its final midnight endpoint at the seed epoch. Chandra uses only rows
in `[-86400,0]` seconds after explicit TDB conversion. Its final training row is
about 51.184 seconds before the seed epoch. The returned anchor state is
propagated to the seed epoch and that full six-component result is packed.
Later target rows are opened only by the separate reference validator.

The resulting training RMS/max 3D residuals in metres are G05 4.968/18.666,
C03 0.395/0.697, C06 0.756/1.411 and Chandra 0.019/0.052. These are training fit
statistics. Forecast accuracy comes from the separate held-out results; a small
fit residual does not establish an equally small future error.

## Numerical and format checks

Python uses an independent NumPy vector force implementation with SciPy DOP853
adaptive integration. Native CPU and CUDA use scalar force arithmetic and fixed
RK4 steps with seed-derived checkpoints. Chandra uses 7.5-second replay steps
because its eccentric perigee makes 30-second RK4 insufficient for sub-metre
numerical agreement over a week. That integration choice comes only from the
independent DOP853 numerical comparison; its fitted initial state and force
parameters remain unchanged. Numba RK4 accelerates construction fits;
it is not the independent numerical oracle. Defaults are 30-second RK4 steps,
DOP853 relative tolerance 2e-12 and absolute tolerance 1e-6 in the corresponding
SI state component units.

The potential-gradient audit checks the analytic gravity acceleration against
an independently evaluated five-point numerical gradient of U. Across the four
seed states the maximum discrepancy is 3.39e-11 m/s². Direct ERFA frame evaluation
differs from the compressed Q frame by at most 3.54e-12 in a matrix entry.
G05 training propagation at 30 seconds differs from DOP853 by at most 2.99 mm;
halving the RK4 step yields the expected substantial reduction. Refitting G05
using 15-second steps leaves its training residual essentially unchanged, so the
metre-scale residual is not explained by RK4 truncation. Reproduce with
`tools/validate_orbit_dynamics.py --out NEW_DIRECTORY --refit-g05-15s`.

`validate_model` enforces the exact executable schema, finite complete state,
consistent GPST/TT epoch, positive central constants, explicit Boolean shadow,
integer integration limits and coefficient domain coverage. Chebyshev segments
must be ordered, exactly adjacent and degree 0..32 with matching component row
lengths. At a shared boundary the later segment applies. The query domain must
be reachable from the epoch within the declared cold-query step limit. These
are deterministic input checks, not physical accuracy certificates.

For model construction/review install `numpy scipy numba pyerfa jplephem`; their
recorded versions are NumPy 2.1.2, SciPy 1.16.3, Numba 0.64.0, pyerfa 2.0.1.5 and
jplephem 2.24. Replay of a packed native seed requires none of DE440s, the SP3
files, Horizons source vectors, ERFA or a network connection.
