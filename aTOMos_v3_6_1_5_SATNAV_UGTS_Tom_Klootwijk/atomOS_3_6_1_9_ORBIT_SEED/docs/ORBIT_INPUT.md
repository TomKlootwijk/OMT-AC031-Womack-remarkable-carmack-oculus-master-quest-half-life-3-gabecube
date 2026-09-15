# ORBIT-SEED-R1 input and timestamp contract

A seed contains the complete physical model and query configuration. See the exact validators in `python/orbit_seed.py` and `python/orbit_dynamics.py`; unknown/missing root or model fields are errors. JSON equations are data, never Python code.

The JSON root requires `profile="ORBIT-SEED-R1"`, `version="3.6.1.9"`, `object`, `model`, `stations`, `query`, `feedback`, `provenance`. Optional roots are `description`, `accuracy`, `encoding`. Current models use `profile="ORBIT-DYNAMICS-R2"`; R1 decoding remains supported. Both retain six-component GCRS-like state, consistent GPST/TT epoch, domain, frame, forcing, force and integration dictionaries. R2 embeds full degree/order-12 gravity, varying published EOP and Schwarzschild terms; see `ORBIT_PRECISION_DYNAMICS.md`. All numerical replay dependencies are embedded; original source URLs/hashes are provenance.

`model.integration` owns the actual integration step, checkpoint stride/capacity and cold-query work limit. `query` owns start/end, tick duration, chart radius, separate hoop and event-search settings. Query start/end must lie inside the model domain. Direct scrubbing accepts other times in that physical domain, including the declared earlier training interval. Model coverage is not an accuracy horizon.

Each station has a unique ID, WGS84 latitude/longitude in degrees, ellipsoidal height in metres, elevation mask and description. Edit coordinates in a JSON companion and repack. Full origin and local rotation participate in each query.

`feedback` stores `q0`, `present`, exactly two ordered `sets`, `equations`, `predicates` and `cadence`. Each set has unsigned 32-bit `asa_mask`, `na_mask`, `boundary_mask`. X accepts `q,d`; J/K accept `q,y,d`. Only `&`, `|`, `^`, `~`, parentheses and integer 0/1 are accepted; 1 means all word bits. Both whole-word stages execute before synchronous JK. A selected positive cadence must advance representable time.

| Drive bit | Predicate |
|---:|---|
| 0 | Geometric elevation at or above the station mask |
| 1 | Absolute elevation-minus-mask within `near_mask_deg` |
| 2 | Absolute elapsed seed age at least `age_warning_s` |
| 3 | Elevation rate above `rising_rate_deg_s` |
| 4 | Negative range rate, approaching the station |

These project through `present`. `cadence.fine_bits` selects which next-q bits request `fine_s`; otherwise `coarse_s` applies. Defaults use identity sets with empty absorption boundaries. Both sets still execute; active second-set absorption and both-stage whole-word tests are included.

`predict` starts from packed q0 at its requested start time. Direct `query` is a physical-state lookup. The UI labels its word snapshot as one transition from q0; ordered playback exposes carried-state scheduling. Scrubbing interaction history never changes orbital force or state.

The binary uses a 52-byte little-endian `<8sHHII32s` header: magic `ATOMORB1`, version 1, codec, compressed length, canonical raw length and SHA256. Codec 2 (`bitplanes64-zlib`) is the default; codec 1 (`canonical-zlib`) remains readable and selectable. The digest input is `b"atomOS:ORBIT-SEED-R1:canonical-binary\0"` plus the canonical tagged payload, independent of codec. Values retain binary64 exactly, including signed zero; integer widths are explicit. Maps sort unique UTF-8 keys. Decompression must be bounded and end exactly. Trailing data, noncanonical maps, bad digests, nonfinite state, absent model dependencies and unsupported schema fail before replay.

Codec 2 implements the requested **lossless 1-bit planes in machine words**. Its decompressed stream begins with `<8sII>`: `BITPLN64`, structural-template length, numeric-word count. The template is the canonical tagged encoding with each eight-byte numeric value removed, retaining its `i`, `u` or `d` tag. In canonical traversal order each removed value becomes its unchanged 64-bit pattern. For plane `b=0..63` and group `g`, uint64 word `P[b,g]` has lane `l` equal to bit `b` of numeric word `64*g+l`. Plane-major words are little endian, and unused tail lanes must be zero. The decoder restores every numeric bit, its original type and canonical digest. Structural strings, tags and Boolean tokens remain in the template. No value is reduced to a single bit.

Packing itself has zero numeric error. It does not replace native binary64 arithmetic or remove propagation roundoff. Current examples are 8,716–9,074 bytes, including the full R2 environment and provenance; their ordinary canonical codec is slightly smaller. `seed_sizes.json` reports both measurements. Exact byte-pattern, boundary-lane, padding, legacy-codec and packed-only replay checks cover this representation.

Original UGTS keys are added after geometry. The log chart is valid only for rho in [-20,0]. `absolute_tick`, integer `winding`, `tick_phase_index` and `tick_phase_fraction` remain separately available; `phi_rad` is independent. OTAN2 uses wrapped theta difference divided by rho difference, with named undefined cases.

`verify_orbit_run.py` checks a fresh native reconstruction, independent AST schedule, both stages, full geometry, time, keys, OTAN2 and deterministic chain. Timings/cache occupancy are excluded from the mathematical digest. Physical accuracy is separately measured against later reference data; the accuracy service requires a matching canonical physical-model hash.

Other objects/dates need an appropriate earlier-data model and forcing interval. Merely extending `domain_s` is insufficient: coefficient coverage must exist, and a new forecast needs its own validation. Input limits, numerical acceptance checks and empirical discrepancy budgets are listed separately in `ORBIT_FUNCTIONAL_TOLERANCES.md`.
