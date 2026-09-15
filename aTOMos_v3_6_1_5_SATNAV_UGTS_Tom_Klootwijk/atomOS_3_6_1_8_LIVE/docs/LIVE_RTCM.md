# LIVE-R1 Internet receiver input

`python/live_rtcm.py` is an incremental RTCM3 framing, GPS code-observation and
broadcast-navigation decoder. `capture()` supplies bounded TCP or NTRIP/HTTP input.
These are measurements from the remote receiver named by the stream, not measurements
of the computer's position. No local receiver hardware is required to run this path.

## Input and supported messages

The implementation reads arbitrary byte chunks. RTCM3 framing is the 0xD3 preamble,
six reserved zero bits, a ten-bit payload length, the payload, and three CRC24Q bytes.
The CRC polynomial is `0x1864CFB`, initialized to zero, with no reflected input or
final XOR. The check vector `123456789` gives `0xCDE703`. CRC failure slides the search
by one byte. Non-frame bytes produce a noise event. A plausible incomplete header
waits for its declared frame length, at most 1029 bytes; EOF or reconnect records and
discards the partial frame. CRC validity checks transmission framing, not authenticity.

| RTCM type | Decoded use |
|---|---|
| 1019 | GPS broadcast ephemeris, clock polynomial, group delay, health, issue identifiers and accuracy index |
| 1005/1006 | Reference station antenna reference point (ARP) in ECEF, realization indicators; 1006 antenna height retained separately |
| 1004 | GPS L1/L2 extended code observations, ambiguity milliseconds, C/N0, and raw carrier/lock fields |
| 1074/1075 | GPS MSM4/MSM5 code observations and C/N0; MSM5 rate fields retained |
| 1076/1077 | GPS MSM6/MSM7 high-resolution code observations and C/N0; MSM7 rate fields retained |
| Other MSM1–7 for GPS/GLONASS/Galileo/SBAS/QZSS/BeiDou | Header and exact payload-length validation for sequence assembly; unsupported observations remain unsupported |
| Other types | Explicit unsupported message event with complete original frame |

Carrier phase and rate fields are retained as raw diagnostics, not used to claim
carrier-phase positioning, Doppler velocity or ambiguity resolution. Unknown GPS
signals and non-GPS PRNs inside the legacy message do not enter the GPS position
solution. Non-GPS ephemerides do not enter a GPS orbit cache.

## Actual code equations

Let `c = 299792458 m/s` and `R_ms = c × 10^-3 m`. For GPS MSM, let `N` be the
eight-bit integer range in milliseconds, `M` the ten-bit rough fractional field,
and `p` the signed fine pseudorange integer. The code is

```
P_MSM4/5 = R_ms [N + M 2^-10 + p 2^-24]
P_MSM6/7 = R_ms [N + M 2^-10 + p 2^-29].
```

`N=255`, `p=-16384` for MSM4/5 and `p=-524288` for MSM6/7 are unavailable values;
the event stores `pseudorange_m=null` and a specific status. They do not become zero
or artificial ranges. C/N0 is the six-bit value in dB-Hz for MSM4/5 and one-sixteenth
of the ten-bit value for MSM6/7; zero is represented as unavailable C/N0.

For legacy 1004, with the 24-bit L1 code integer `r`, eight-bit ambiguity `a` and
signed 14-bit L2-minus-L1 difference `d`,

```
P_L1 = 0.02 r + a R_ms
P_L2 = P_L1 + 0.02 d.
```

`d=-8192` makes L2 code unavailable. A missing carrier-phase difference does not
erase a separately present code observation. Both legacy C/N0 fields have a scale
of 0.25 dB-Hz. The GPS L1 C/A code is labelled `C1C`; all code identifiers remain
explicit. `epoch_from_event()` selects one requested code per GPS satellite,
default `C1C`, choosing the finest supplied code quantization among duplicate
representations. Full original fragments retain every code and observation status.
Nonpositive reconstructed code is reported as `nonpositive_pseudorange` and does
not become an observation. The real capture exposed seven legacy missing-signal
records with zero code and no corresponding MSM C1C signal; a regression test and
independent admission check cover this case.

## Time and clock conventions

`RTCMDecoder(reference_gpst_s)` requires full GPS seconds since 1980-01-06.
Archived data require a reference date associated with the capture. No capture is
silently assigned today's date during replay. A GPS MSM or legacy epoch provides
time of week `T`, in milliseconds. Its full time is

```
t = T/1000 + 604800 floor[(reference - T/1000)/604800 + 1/2].
```

This is the nearest GPS week to the supplied reference, so that reference must
identify the correct half-week. RTCM1019 has a 10-bit GPS week. The decoder chooses
the nearest 1024-week realization to the reference and scales toe/toc in 16-second
units. The clock-reference epoch is assigned to the week nearest toe. Orbital angles
and their rates are converted from semicircles to radians, multiplying the decoded
semicircle value by pi. Clock coefficients remain seconds, seconds/second and
seconds/second squared; `TGD` remains seconds. Broadcast fit flag one means an
unspecified interval greater than four hours; it is recorded explicitly and not
invented as a precise duration. URA index15 remains unavailable and is not turned
into a nominal accuracy by the dataclass adapter.

For live capture, the configured conversion is

```
GPST seconds = Unix UTC seconds - 315964800 + gps_utc_offset_s.
```

The default explicit offset is 18 seconds, checked against the [USNO GPS/UTC
offset table](https://maia.usno.navy.mil/information/eo-values). The value and every
socket-read timestamp are stored. This is a configurable value, not a maintained
leap-second service. For mixed-constellation sequence matching, Galileo, SBAS and
QZSS epoch TOW is aligned with GPS; BeiDou TOW gets +14 seconds. GLONASS day/time is
converted from UTC+3 using the configured GPS–UTC offset before week resolution.

The RTCM epoch is tagged by the remote receiver. It is not the network reception
timestamp. Pseudorange and receiver epoch must use the same receiver-clock
convention. Satellite transmit time and the receiver clock estimate are handled
by the distinct observation-preparation and native-positioning components in
`LIVE_GNSS_MODEL.md`. Network arrival time is used for week resolution and latency
evidence, never substituted for the observation epoch.

## Fragment assembly and continuation

`feed(data, reception_gpst_s)` returns dictionaries with type, message type, full
raw frame hex, SHA256, stream offset and reception time. Supported observation
messages also produce `observation_fragment` events. The multiple-message bit one
means more messages follow. A terminal bit zero closes an assembly only for its
station ID and full epoch. Mixed-constellation messages can close the GPS assembly;
their unsupported measurements are not turned into GPS rows.
The completed epoch's reception timestamp is the terminal fragment's socket-read
timestamp. Its first-fragment timestamp is retained separately, so assembly time is
not silently removed from observation-to-reception latency.

A station/time change before a terminal, malformed message, CRC error, reconnect,
or EOF produces `incomplete_epoch` and discards that assembly. Conflicting repeated
satellite/signal data also produce an incomplete event. Completed times must increase
within a station; duplicates and older epochs produce `stale_epoch`. A reconnect
clears decoder completion history; the application must decide whether returning
epochs are stale relative to its persistent state. RTCM MMI has no explicit
beginning-of-sequence marker: a capture can start mid-sequence. Events expose
`sequence_start=not_identifiable_from_rtcm_mmi`; receipt of a terminal does not prove
that no earlier fragment was lost. The position solver still requires sufficient
usable, distinct satellites.

Call `finish(reason)` at capture end and `reset(reason)` at a transport reconnect.
The `epoch_from_event()` and `ephemeris_from_event()` helpers instantiate the shared
`GPSEpoch`, `GPSObservation` and `GPSEphemeris` classes in `live_gnss.py`.

## TCP and NTRIP transport

`capture()` accepts `tcp://host:port`, `ntrip://host:port/mount`, `ntrips://...`,
`http://...` or `https://...`. It sends a read-only GET for HTTP/NTRIP; it does not
send GGA, receiver configuration, or external actions. TLS uses normal certificate
validation. Optional Basic credentials are excluded from stored URL metadata and
errors. Existing output files are not overwritten.

Duration, received-byte count, socket timeout and reconnection count are bounded.
HTTP/1.1 chunked transfer is decoded incrementally, including split chunk delimiters,
extensions and trailers; malformed/truncated chunks are explicit errors. HTTP
Content-Length is enforced. NTRIP v1's `ICY 200 OK` can be followed directly by RTCM
or by additional headers. Those headers are removed. Public Centipede was observed
to send `Content-Length: 0` on a continuing ICY stream, so v1 uses socket-until-EOF
semantics and records its protocol rather than applying that misleading length.

Outputs are the exact de-framed transport body, `<raw>.timing.jsonl` with read
boundaries and reconnect offsets, and `<raw>.json` with source, hash, byte count,
time settings, connection events and stop reason. HTTP framing bytes are not part
of the RTCM body. A byte limit can leave an incomplete final RTCM frame, which the
decoder reports. Reception callbacks run synchronously and their failure aborts the
capture instead of being mistaken for a network problem. Synchronous execution
applies TCP backpressure; this is not an asynchronous queue or a guarantee of
bounded application processing time. At higher rates, an application must provision
and measure its own processing budget. DNS resolution also follows the operating
system's resolver behavior.

## Executed decoder evidence

The no-authentication Centipede `LIENSS` stream was recorded on 2026-09-14. The
664759-byte archived RTCM capture contains 3162 valid frames, including 301 legacy
1004, 413 GPS1077 and 115 GPS1019 messages. This decoder produced 300 complete GPS
epochs with 13–14 C1C satellites and one explicitly incomplete final epoch. It
reported no CRC or malformed-message errors. These epoch counts agree with the
independent RTKLIB capture conversion. The stationary ARP carried by 1006 was
`[4426043.0455, -89429.1998, 4576296.6447] m`; this is separately reported station
metadata, not a solved position or an automatically trusted accuracy benchmark.

`results/rtcm_independent_audit.json` records 96880 comparisons of decoded real
frames against independently installed `pyrtcm 1.2.0`. Station coordinates and
broadcast orbital/clock fields agreed exactly. The largest reconstructed code-range
difference was `3.725290298461914e-9 m`, from floating addition order. This validates
field decoding, not GNSS positioning accuracy. The test suite additionally exercises
constructed MSM4/5/6/7, unavailable values, frame splits, CRC recovery, truncation,
mixed-constellation completion, week/day rollover, ICY variants, HTTP chunking,
connection loss, deadlines and callback failures.

```powershell
python -m unittest discover -s tests -p test_live_rtcm.py -v
# Optional independent validation dependency, not required by the live receiver:
python -m pip install pyrtcm==1.2.0
python tests/test_live_rtcm.py --audit source/live_data/centipede_lienss_20260914/capture.rtcm3 --reference-gpst-s 1473457300 --out results/my_rtcm_audit.json
```

The implementation was written independently from these primary implementation
references: [RTKLIB RTCM3 decoder](https://github.com/tomojitakasu/RTKLIB/blob/master/src/rtcm3.c),
[pyrtcm field definitions](https://github.com/semuconsulting/pyrtcm/blob/main/src/pyrtcm/rtcmtypes_get.py)
and [pyrtcm MSM definitions](https://github.com/semuconsulting/pyrtcm/blob/main/src/pyrtcm/rtcmtypes_get_msm.py).
They provide transparent field cross-checks; this work does not claim access to or
reproduce a purchased RTCM standard.
