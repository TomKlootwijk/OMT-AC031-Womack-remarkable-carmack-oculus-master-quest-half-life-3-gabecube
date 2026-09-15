# SPICE representation of a frozen aTOMos orbit forecast

The R18 comparison executes CSPICE N0067 through SpiceyPy 8.2.0. It constructs
type 9 SPK files from the existing ORBIT-DYNAMICS-R2 native forecasts and measures
the additional error introduced when those forecast samples are interpolated.
SPICE does not perform forward physical propagation in this experiment. No
external observation file is read, no fitted parameter changes, and no future
reference state is inserted into an SPK. Consequently, this experiment cannot
establish that either system predicts an actual satellite more accurately.

## Inputs and experimental contract

The unchanged R10 CPU orbit worker evaluates the January 2 and February 2, 2025
frozen models for GPS G05 (MEO), BeiDou C03 (GEO), BeiDou C06 (IGSO) and Chandra
(HEO). Both periods have been inspected in previous releases; neither is a new
blind confirmation. The initial experiment was specified in
`review/r18_spice_protocol.json` before computing its state outputs:

- Seven days, including both endpoints; native reference states every 150 s.
- SPK input intervals 300, 900 and 1800 s, independently crossed with Lagrange
  polynomial degrees 7, 9 and 15: 72 cases across eight frozen models.
- Every midpoint between adjacent nodes is compared with the native state at
  that exact model offset. Every input node is checked for preservation. Queries
  one second outside either endpoint must be rejected.
- Input models, native binary, adapters, Python harness, CSPICE DLL, wrapper and
  NAIF leap-second kernel are pinned by SHA-256. Native state arrays and every
  resulting SPK are retained and hashed.

These are sampled errors. No continuous-time maximum or tolerance certificate
is inferred from midpoint agreement.

## Time, axes, units and derivatives

Let \(g_0\) be the model's GPS seconds since January 6, 1980, and let \(t\) be
the model query offset in seconds. Relative to J2000 noon, the TT coordinate is

\[
T=(2444244.5-2451545.0)86400+g_0+51.184+t.
\]

The harness uses CSPICE `UNITIM(T,"TDT","TDB")` to obtain the SPK epoch \(E\)
in TDB seconds past J2000. This uses the pinned `naif0012.tls`, not an assumed
identity between GPS, UTC, TT and TDB. The LSK's short periodic model satisfies

\[
T=E-K\sin\epsilon,\qquad
\epsilon=M+e_B\sin M,\qquad M=M_0+M_1E.
\]

Thus

\[
\frac{dT}{dE}=1-K\cos\epsilon\,M_1(1+e_B\cos M).
\]

Native velocities are derivatives with respect to model GPST/TT seconds. Before
writing the SPK they are multiplied by \(dT/dE\); query velocities are divided
by the same factor at the query epoch. Position and velocity are converted from
metres to kilometres on writing and back on reading. Type 9 interpolates all six
stored components independently; it does not impose a derivative relation
between its position and velocity interpolation polynomials.

The segment center is Earth (399), with geometric `NONE` aberration correction.
The model's Earth-centered GCRS numerical axes are transported under an explicit
identity-orientation convention to the SPICE J2000 label. This comparison does
not implement or validate the full relativistic relationship between GCRS and
barycentric ICRF coordinates. It cannot certify physical frame accuracy.

The original experiment's TT-to-TDB-to-TT round trips were exactly equal at the
tested floating-point inputs. The SPICE short periodic correction differed from
geocentric SOFA/ERFA `dtdb` by up to 15.320 microseconds in January and 22.406
microseconds in February. The model's stored Julian TT epoch, when converted back
to seconds, differed by -8.8215 microseconds from the GPS-derived TT epoch.
These differences are reported, not silently mixed into one convention. Both
the node and query times use the same CSPICE conversion. An absolute ET double
around these epochs has approximately 0.119 microsecond spacing, so exact seed
transport does not make this floating-point ephemeris interface exact.

## Initial measured results

The predeclared 300 s / degree 9 profile uses 2,017 nodes and a 116,736-byte SPK
for each seven-day object. Its midpoint position reconstruction errors were:

| Frozen model | January RMS / maximum | February RMS / maximum |
|---|---:|---:|
| G05 MEO | 0.226 / 0.575 mm | 0.235 / 1.082 mm |
| C03 GEO | 0.180 / 0.457 mm | 0.186 / 0.862 mm |
| C06 IGSO | 0.180 / 0.455 mm | 0.186 / 0.861 mm |
| Chandra HEO | 0.248 / 3.211 m | 0.134 / 1.667 m |

Coarse sampling was inadequate for Chandra. The 900 s / degree 9 profile reached
8,715.928 m (January) and 5,998.573 m (February). The 1800 s / degree 15 profile
reached 45,580,643.558 m in February. These failures remain in the complete
report. Increasing polynomial degree does not guarantee improvement on a fixed
sparse sample grid. They are failures of the chosen ephemeris representation,
not evidence that SPICE is a less accurate physical propagator.

Across the 72 original cases, all 72,648 stored-node preservation checks passed;
the greatest observed node position transport error was 94.317 nanometres.
All 144 out-of-coverage queries were refused. A separate fresh process verified
99 pinned files, reopened all 72 SPKs and reproduced every reported maximum
position error from all 72,576 midpoint queries exactly. These checks establish
the measurement and transport behavior, not an external satellite-position bound.

## Denser Chandra follow-up and practical storage profile

After inspecting those failures, a separately written follow-up protocol fixed
Chandra node spacings of 30, 60 and 120 s, each with degrees 9 and 15, for both
existing periods. This was an adaptive investigation, not a blind confirmation
of the initial experiment. A 15 s native reference grid supplied 40,321 states
per period. All previously computed 150 s reference states were preserved
exactly. The six degree-9 results were:

| Interval | Seven-day SPK size | January max | February max |
|---|---:|---:|---:|
| 30 s | 1,134,592 bytes | 0.497 mm | 0.484 mm |
| 60 s | 569,344 bytes | 0.497 mm | 0.704 mm |
| 120 s | 286,720 bytes | 1.012 mm | 0.752 mm |

Degree 15 sometimes worsened boundary interpolation, reaching 14.626 mm for the
February 30 s case. All 12 cases are retained. This follow-up checked another
141,132 stored nodes and 141,120 midpoints, plus coverage refusal on both ends.
A fresh process verified 24 pins, reopened all 12 SPKs and reproduced every
reported maximum exactly. The complete reference grids took 42.479 and 42.940 s;
this includes dense oracle evaluation, not just SPK input generation.

For these models, a practical starting profile is **degree 9, 300 s nodes for
GNSS and 60 s nodes for Chandra**. The sampled maximum reconstruction error of
this combined choice is 1.083 mm or less, before adding the native forecast's
physical error. It uses 114 KiB per GNSS object and 556 KiB per Chandra seven-day
SPK. A 120 s Chandra profile reduces that object to 280 KiB and also stayed below
1.013 mm at the sampled midpoints. The 60 s choice provides denser sampling;
neither configuration is certified for other trajectories, manoeuvres, longer
intervals or continuous-time errors. Revalidate when the model or trajectory
changes. A sampling interval cannot be selected solely from a satellite's
altitude class.

## Query cost and storage

For the 300 s / degree 9 profile, five repeated batches of 2,016 deterministically
shuffled midpoint queries were measured after complete warmup. The full native
Python-to-worker API took median 0.457--0.463 s for GNSS objects and 1.793 s for
Chandra. The SpiceyPy iterable query API took median 0.00875--0.00935 s. Thus this
SPICE API path was 49.4--51.9 times faster for the GNSS cases and 197.0--204.9
times faster for Chandra. It reused a precomputed 116,736-byte SPK; the native
path executed remaining RK4 steps from cached checkpoints and crossed an IPC/JSON
boundary. This is an observed end-to-end storage/compute tradeoff, not equal
arithmetic work, a GPU throughput comparison, or a general product ranking.

The complete native reference grid required about 0.96--0.99 s for each GNSS
model and 3.74--3.80 s for Chandra in this run. That grid also supplied midpoint
oracles; it is not an optimized SPK-generation-only measurement. Conversion and
SPK-writing times are recorded separately. Host load was uncontrolled, and no
energy, peak memory or production service latency claim is made.

## Interpreting the comparison

For a common physical time and frame, let \(x_N\) be the native forecast,
\(x_S\) its SPK reconstruction and \(x_*\) an external physical reference.
Then the triangle inequality gives

\[
\|x_S-x_*\|\leq\|x_S-x_N\|+\|x_N-x_*\|.
\]

The SPICE experiment measures only the first term at declared samples. The
second term requires the separate held-out observation comparison. High-quality
SPK reconstruction can preserve a good forecast or faithfully preserve a poor
one. This establishes a practical route to distributing aTOMos forecasts through
existing SPICE geometry interfaces; it does not replace orbit determination,
uncertainty estimation, manoeuvre handling or physical-model validation.

## Reproduction and primary references

Run `python tools/compare_spice_ephemeris.py` from R18 with the declared isolated
dependencies. The original results are `review/r18_spice_comparison.json`, with
`review/r18_spice_validation.json` recording fresh-process re-query verification.
The follow-up is executable as `python review/r18_spice_refine_chandra.py`, with
its separate protocol, results and validation under
`review/r18_spice_chandra_refinement*.json`.

- NASA NAIF, [SPK type 9 writer and its state/epoch contract](https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/C/cspice/spkw09_c.html).
- NASA NAIF, [uniform time conversion](https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/C/cspice/unitim_c.html).
- NASA NAIF, [pinned LSK periodic time model](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/lsk/naif0012.tls).

The numerical tables and API measurements above are local experimental results;
the linked references define the external interface, not those outcomes.
