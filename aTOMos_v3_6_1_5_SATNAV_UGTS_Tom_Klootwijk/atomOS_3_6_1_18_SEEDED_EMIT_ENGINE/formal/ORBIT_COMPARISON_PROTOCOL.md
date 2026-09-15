# R18 matched orbital comparison

The experiment measures the existing aTOMos ORBIT-DYNAMICS-R2 engine against an
Orekit numerical propagation of the same frozen physical problem, and scores
both against the same later external reference samples. It does not optimize
the orbit models, refit initial conditions, or infer accuracy from word packing.

## Frozen cases and chronology

The January 2 and February 2, 2025 GPST model epochs each supply G05 (MEO), C03
(GEO), C06 (IGSO) and CHANDRA (HEO). The complete R10 `precision_models` and
`confirmation_models` JSON envelopes are hashed before R18 state comparison.
Both periods were already evaluated in R10. February retains its historical
confirmation provenance, but is not called a fresh blind R18 confirmation.

Training-source hashes and metadata must establish zero future target rows and
an end time at or before each seed epoch. The products are retrospective;
chronological target selection does not prove that the resulting seed could
have been constructed live at the historical epoch. No parameter selection
is based on the new comparison errors.

For GNSS the primary reference remains the original GFZ GBM SP3 collection.
Every available target row strictly after the seed epoch and inside its declared
future domain participates. Missing rows remain missing. The WUM product is
compared on the exact timestamp intersection as a reference-disagreement check.
For CHANDRA the original NASA Horizons geometric geocentric ICRF state tables
are used. Horizons does not supply an independent state covariance here.

`review/r18_orbit_protocol.json` records the cutoff, full model hash, canonical
physical-model hash, selected sample count, timestamp digest, position digest,
source hashes, native binary hashes, IERS publication, and scorer source hashes.
The preparation command refuses to overwrite an existing frozen protocol. All
execution and scoring commands verify the entire frozen input set before work;
native execution and final scoring verify it again afterward.

## Equal physical inputs and time

Each engine receives the same six initial GCRS state components, SI parameters,
degree/order 12 EGM96 coefficients, Sun/Moon forcing segments, frame segments,
empirical RTN acceleration, solar pressure/shadow rule and relativity setting.
The external Orekit adapter must describe its implementation of these forces
and its numerical integrator in its state report. Sharing frozen coefficients
defines the same physical experiment; source-level independence of a force
implementation must be established by that adapter's implementation audit.

The reference epochs are the actual query epochs. Let `tau_i` be a source GPST
epoch and `tau_0` the frozen epoch. The requested time is `t_i = tau_i - tau_0`.
GNSS source GPST is parsed directly. Horizons calendar TDB is converted using
the existing SOFA/ERFA geocentric TDB-to-TT iteration and `GPST = TT - 51.184 s`.
Printed Julian dates are checked but do not perturb the calendar grid.

The adapter returns the requested `times_s` and finite `states_gcrs_m_m_s` rows.
Scoring rejects even a changed decoded floating-point epoch. Maximum absolute
engine/request time offsets are reported and must be zero. This validates
request alignment; it does not measure the accuracy of an operational clock.
No future-reference-derived clock shift or position alignment is fitted.

For GNSS, all output positions use the same frozen model frame transform before
comparison with labelled IGS20/IGb20 ECEF SP3 coordinates. The source realization
labels are retained; no fitted frame alignment is applied. This includes the
frozen frame's error in the forecast score, but does not independently test
actual future Earth orientation. CHANDRA geocentric ICRF positions are compared
with GCRS-oriented positions under the existing model convention; omitted
relativistic coordinate distinctions remain an explicit limitation.

## Quantities and interpretation

For engine `a`, reference position `r_i`, engine position `p_i^a` in the same
declared frame and selected sample count `N`, report

```
e_i^a = norm(p_i^a - r_i)
RMS_a = sqrt(sum_i (e_i^a)^2 / N)
MAX_a = max_i e_i^a
d_i^(a,b) = norm(x_i^a.position - x_i^b.position)
```

Report counts, RMS, maximum, median and 95th percentile for the whole available
arc and cumulative 1, 6, 12, 24, 48, 72 and 168 hour intervals. Report the nearest
available sample to each requested horizon with its signed and absolute time
offset; a nearby sample is never labelled the exact horizon. Report first and
last times, largest sample gap, and first sampled exceedances of descriptive
10/100/1,000/10,000 m levels. These levels are not newly invented system pass
criteria. The samples do not prove continuous-time containment between them.

Numerical state disagreement `d_i` is separate from external-reference forecast
error `e_i`. Close agreement indicates that the implementations solve the same
frozen problem similarly; it cannot validate the physical model. Better
agreement with one precise product does not by itself establish generally
better satellite navigation accuracy. Cross-product disagreement is reported
as observed discrepancy, not as a certified uncertainty floor.

Native execution records one complete batch wall duration including worker
startup, model initialization, query processing and teardown. This is execution
provenance and a diagnostic; it is not a matched speed benchmark against Java.
Scoring and source parsing are excluded from that duration. Engine timing fields
are retained verbatim with their stated scope.

SPICE belongs to a separate ephemeris representation/query comparison. An SPK
built from future reference samples is not a frozen-state forecast. A matched
representation experiment must state the shared input ephemeris, interpolation
degree, knot epochs, time scale, frame and held query epochs; it cannot silently
be pooled with the forward-prediction error table above.

## Reproduction and interchange

```
python tools/compare_orbit_references.py prepare --python-deps C:/aTOMosBuild/orbitdeps/python
python tools/compare_orbit_references.py native --backend cpu --python-deps C:/aTOMosBuild/orbitdeps/python
python tools/compare_orbit_references.py native --backend cuda --python-deps C:/aTOMosBuild/orbitdeps/python
python tools/compare_orbit_references.py compare --python-deps C:/aTOMosBuild/orbitdeps/python
```

The scorer reads the retained R10 sibling release without modifying it. It uses
NumPy and PyERFA; frozen runtime versions are recorded. Requests are named
`request_<jan|feb>_<OBJECT>.json`; native results are
`native_<cpu|cuda>_<case>.json`; external reports default to `orekit_<case>.json`.
The Orekit directory is configurable with `--orekit-dir`. External files require
the exact `model_sha256`, `times_s` and `states_gcrs_m_m_s`; an optional
`protocol_sha256` is validated when present. The output preserves all other
adapter metadata. A partial `--cases` run is marked as a partial scope.
