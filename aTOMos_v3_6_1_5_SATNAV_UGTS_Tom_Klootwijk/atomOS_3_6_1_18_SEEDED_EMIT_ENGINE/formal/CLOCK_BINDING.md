# Atomic-time observation and literal clock binding — R14

The normative body is `docs/clock_binding.tex`. The selected observed source is `source/clock_capture/nist_capture.json`; the source data were read after the root agent acquired them under the user's explicit atomic-clock acquisition request. The earlier Cloudflare observation remains in `capture.json`, but is not the selected latch. No extra network experiment, kernel execution, numerical example or test was performed for this chapter.

## Actual captured identity

- NTP UDP/123 endpoint `time.nist.gov`, resolved peer `132.163.96.4:123`; request version4, response version3.
- Reply mode4, stratum1, leap indicator0, reference ID `NIST`; source is a captured unauthenticated UDP observation.
- Reply SHA-256: `26a429327733f35d8b67abfb9bbb33f54fae9fa590c4ba0e5a7947fe6946c3e4`.
- Transmit u64 word: `17173213285462662115`.
- Era0 is explicit context-derived metadata, not a wire field.
- Epoch-shifted exact rational: `7685678632232377315 / 4294967296`.
- Truncated UTC display: `2026-09-15T08:38:22.859456Z`.
- Recorded monotonic round-trip count: `127594000` ns. This is acquisition evidence, not a certified UTC uncertainty bound.
- No host clock was set and no oscillator was calibrated.

## Mathematical binding

The atomic SI reference is exact `Delta_nu_Cs=9192631770 Hz`; its physical realization is uncertain. NIST describes UTC(NIST) as an ensemble of cesium-beam and hydrogen-maser clocks calibrated against a primary frequency standard. The internet service distributes this atomic reference; aTOMos has acquired a clock observation, not installed a local atomic oscillator.

For unsigned32 seconds s and fraction f, `w=2^32*s+f`; the unfolded source coordinate is `q_N=e*2^32+s+f/2^32`, and its 1970 civil-epoch counterpart is `q_U=q_N−2208988800`. All words, era and reduced rational are retained. Fraction resolution is a property of the representation, not the physical clock's accuracy. Leap ambiguity, table validity and provider smear conventions belong to the complete conversion dependency.

The captured IANA leap file has SHA-256 `db5a895f16853b03bfc865e8d68f9fc8710ef1740e3400c701cd46a5bbbc3433`, last transition NTP3692217600 at offset37 and expiry NTP4023129600. At this non-leap source epoch, the finite nominal mapping is:

- `t_GPST=q_U−315964800+(37−19)`, elapsed seconds from 1980-01-06 GPST.
- `Q_TAI=q_U+37`, a 1970-01-01 TAI calendar-coordinate origin.
- `Q_TT=q_U+37+4023/125`, a 1970-01-01 TT calendar-coordinate origin.
- `Q0=220924800+4023/125`; `t_TCG=(Q_TT−Q0)/(1−L_G)` with exact `L_G=6.969290134e−10`. Q0 names the conventional TT=TCG event 1977-01-01 00:00:32.184; t_TCG is elapsed TCG seconds from that event, matching `anchor_state.json`.

The table/domain is retained, not inferred from the packet leap indicator. Future changes or repeated-second branches need their own mapping. These nominal transformations do not erase UTC(NIST) or GNSS realization error.

The nominal converted source event q* is separated from physical transmit time `t_tx=q*+epsilon_s` and reception `t_rx=t_tx+d_in`. Network asymmetry, source error, local readout error and realization error stay in one joint uncertainty set. The four-stamp NTP offset and delay expressions remain rational; their physical interpretation is conditional.

The typed immutable capture tuple includes raw request/reply Bits(384), source identity, protocol metadata, acquisition stamps, coordinate rational and complete mapping identities. A finite profile fixes all tuple widths/order. A fixed capture is a closed imported value; newly acquired observations use sample ports. Neither mechanism performs a future network lookup.

`source/clock_capture/anchor_state.json` materializes the accepted NIST source record and nominal mappings. This chapter specifies its XOP binding without claiming a running XOP clock executor.

For an accepted pulse a, admission Boolean v and old latch l, define `e=IF(l,false,IF(a,v,false))`, `l_next=l OR e`, `H_next=IF(e,C,H)`. Initial l is false and H is a closed typed placeholder without clock meaning. For defined inputs the pulse equals `a AND v AND NOT l`; the lazy form demands no new pulse/record when latched and no record when an unlatched pulse is false. State commits are simultaneous. Once l is true, e is false forever and induction proves the tuple cannot change. A rising-edge pulse is `a=c AND NOT b` with `b_next=IF(l,b,c)`; optional edge memory also requires no new level after latching. Later captures need separate versioned anchors.

Tag5 exposes source-time rational; tag6 applies the complete registered/custom TimeConvention to GPST-SI. A mapping requires a resolved epoch/era, dated leap/ambiguity rule and stated source interval. A rational timestamp alone does not infer UTC, GPST or TCG. Proper time additionally depends on the physical trajectory and clock model in the gravity chapter.

## Cross-domain integration

For each physical domain, a declared increasing map `t_d=chi_d(t)` gives `dx_d/dt=chi_d'(t) F_d(chi_d(t),x_d,u_d)`. The initial state belongs to the mapped latched event; relabelling a stale measurement does not propagate it.

- Electromagnetism: explicit field/source/boundary time; carrier phase also needs its own phase and frequency reference.
- Mechanics/control: initial q,p, attitude, force histories and ASA/NA/JK actuator events.
- Thermal/material state: temperature, internal variables and accumulated energy/history.
- Gravity/orbit: compatible GPST/TT/TCG chart, force data, station and satellite events.
- Sensors: acquisition endpoints/windows, latency and calibration history.
- Digital replay: causal step n with explicit durations for physical time.

Shared event identity does not force shared sample rate or a spatial raster. Continuous exact denotation and a selected finite approximation retain different roles and discrepancy obligations.

## Primary references

- CL1: [RFC5905, sections6 and8](https://www.rfc-editor.org/rfc/rfc5905.html): NTP fields, era and four-stamp exchange.
- CL2: [RFC8877, sections4.2.1 and5](https://www.rfc-editor.org/rfc/rfc8877.html): timestamp leap ambiguity and protocol time conventions.
- CL3: [NIST Internet Time Service](https://www.nist.gov/pml/time-and-frequency-division/time-distribution/internet-time-service-its): UTC(NIST) distribution and its repeated-final-second leap convention.
- CL4: [BIPM SI defining constants](https://www.bipm.org/en/measurement-units/si-defining-constants): exact cesium frequency definition.
- CL5: [NIST UTC(NIST) realization](https://www.nist.gov/pml/time-and-frequency-division/how-utcnist-related-coordinated-universal-time-utc-international): atomic-clock ensemble and primary-standard calibration.
- CL6: [IANA leap-seconds.list](https://data.iana.org/time-zones/data/leap-seconds.list): retained dated leap table, directly opened and reviewed.
- GT3: [IERS Conventions chapter10](https://iers-conventions.obspm.fr/content/chapter10/tn36_c10.pdf): coordinate scale and epoch relations.

Reviewed 15 September2026. The chapter gives the formal immutable binding of the actual recorded packet; it does not claim a running XOP executor or a calibrated cross-domain physical clock.
