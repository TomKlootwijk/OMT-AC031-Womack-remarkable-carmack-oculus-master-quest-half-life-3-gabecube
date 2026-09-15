# ORBIT-SEED-R1 required result

User objective: seed-based packing grounded in the existing formalization/kernel,
ground-station horizon prediction for GEO and other higher orbits, and measured
accuracy. The source basis is preserved release3.6.1.8; original ASA/NA, JK, OTAN2,
both UGTS key layouts and full-state distinctions remain intact.

Completion requires all of the following, with actual evidence rather than names:

1. An executable, versioned orbital seed format stores the full model and initial
   state, epoch/time/frame, source provenance, numerical settings and station/query
   configuration. A complete packed seed reconstructs predictions without loading
   the original trajectory or future target samples. Report total seed bytes and
   replay output size, including every dependency required by that seed.
2. Faithful use of the literal ASA/NA and synchronous JK state recurrence. Geometry
   predicates drive it and its state changes the subsequent query/refinement
   schedule. Preserve whole-word absorption and editable equation inputs. Orbital
   dynamics remain explicit; CGK spring mechanics are not silently called gravity.
3. A native CPU/CUDA orbit kernel and independent numerical reference cover MEO,
   GEO, inclined geosynchronous and eccentric high-orbit cases. Explicitly distinguish
   realistic reference datasets from analytic/synthetic dynamics tests.
4. Ground-station predictions retain full ECEF/ENU state, Up, linear time, winding,
   original contiguous and Morton keys where defined, azimuth/elevation/range, and
   velocity/range-rate where available. Define geometric versus apparent angles.
5. Both meanings of horizon: refined visibility rise/set/pass events and measured
   prediction horizon versus error budget. Exercise always-visible, never-visible,
   crossings and numerical/grazing limitations. Do not imply sampled visibility
   alone proves all pass events were found.
6. Accuracy evidence distinguishes seed packing/quantization, numerical propagation,
   coordinate/frame assumptions and future-reference orbit disagreement. Fit seeds
   only from declared earlier data; hold later reference data out of fitting and
   model selection. Publish per-orbit/time error curves and threshold horizons,
   including failures/expired accuracy and source-product limitations.
7. Decode/round-trip/tamper tests, independent CPU/CUDA comparison, actual device
   Compute Sanitizer checks and a counterfactual equation edit prove execution and
   state feedback. Retain required native/Python/previous-solver regression checks.
8. Update the editable PDF and readable input/model contracts; render and inspect
   the PDF. Deliver native binaries, reproducible examples, reference provenance,
   evidence and a hash-verified subversion archive. Preserve previous releases.

Default investigation horizons are15minutes,1hour,6hours,24hours,72hours and7days
where independent reference coverage exists. Error-budget sweeps should show10m,
100m and1km (and other useful thresholds) without turning an empirical result into
a guarantee. Report actual achieved horizons, not a promised accuracy target.

Latest authorized scope adds lossless one-bit-plane packing in machine words,
with existing floating-point propagation retained. Codec 2 must reconstruct
every original numeric bit and canonical digest; it must retain codec 1 reading.
The numeric accuracy repair uses an explicitly stated 10 m engineering target.
The delivered R2 evidence meets this at every tested first-day sample in both
the reused January benchmark and a separate February confirmation. Longer
horizons, coverage gaps and reference discontinuities remain explicit results.
Neither packing nor source Boolean equations imply a universal physical bound.

For the 3.6.1.10 optimization audit, retain all eight requirements above and
verify the following additional items: inspect the supplied phi document and
record which equations transfer; prove exact optimized bit transposition;
compare complete example seed bytes; measure complete packing/loading as well
as the inner primitive; prepare edited feedback/stations without stale caches and give each new session a consistent seed identity; reconcile
native/Python model-domain and reference-surface behavior; retain valid numerical
states under duplicate batch reuse; rebind new binaries/modules and evidence;
and distinguish inherited physical accuracy from new execution measurements.

Calendar verification must cover a complete 400-year Gregorian cycle rather
than one January-to-December sequence, with leap/century transitions and the
next cycle boundary. Absolute time and winding must survive phase/key wraps.
This is a calendar/address requirement; it does not extend the physical orbit
domain or validate UTC leap-second tables.
