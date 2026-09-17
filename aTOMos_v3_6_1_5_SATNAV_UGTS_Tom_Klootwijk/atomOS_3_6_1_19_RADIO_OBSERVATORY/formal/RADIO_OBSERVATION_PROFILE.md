# aTOMos 3.6.1.19
## Radio observatory

Wi-Fi and cellular observation, local logging, study and lossless archival.

Formalization by Tom Klootwijk. Release profile ATOMOS-RADIO-OBSERVATION-R1,
extending the 3.6.1.18 seeded EMIT engine. The R18 mathematical manuscript is
retained after this supplement, with its original pagination and evidence scope.

This release connects a concrete acquisition boundary to the existing formal
core: Android reports become ordered, typed observations. The phone records
what its radio interfaces expose; the desktop tools examine those records.
The new collector runs on Android's CPU and operating-system APIs. It does
not execute the NVIDIA CUDA kernel on the POCO's Mali GPU.

## Implemented path

Phone radio APIs -> append-only session JSONL -> export -> desktop analysis
-> lossless bit-plane archive -> byte-identical restoration.

Wi-Fi records identify observed access-point interfaces and carry RSSI,
frequency and advertised capabilities. Cellular records carry reported cell
identity, registration status and technology-specific power/quality values.
Session events, marker notes, errors and acquisition timestamps accompany them.

## What can be studied

Compare signal histories while stationary, moving or changing the phone's
orientation. Observe access-point visibility, reported cell changes, received
power/quality variation, missing fields and acquisition gaps. Repeat an
experiment with explicit marker notes and compare like metrics on like links.
This profile does not infer a calibrated distance, reflected path, carrier
phase, or another subscriber's identity from a scalar signal-strength value.

## Evidence boundary

The collector is an installable development APK. Automated host checks and
emulator checks are recorded separately in review/. The supplied study fixture
is explicitly synthetic. Physical POCO acquisition and device-specific field
availability remain to be measured on the user's handset. No example plot is
presented as a real radio capture.

<!-- page -->
# 1. Physical observation and units

The inherited measurement model is specialized to a reported radio indication.
Let x(t) be the physical state, m the selected transduction and measurement
procedure, w an acquisition weighting, d model discrepancy and eta noise.

```text
y_k = Q_k[ integral(w_k(t) m(x(t), theta, t) dt) + d_k + eta_k ]
integral(w_k(t) dt) = 1
```

Android may not expose the averaging window, quantizer or full calibration.
Those quantities remain unspecified; a callback time does not define them.
Storing the returned integer exactly preserves the indication, not an unknown
analogue waveform preceding it. This is the measurement distinction already
formalized in R18, now attached to a practical acquisition source.

| Quantity | Stored unit and interpretation |
| --- | --- |
| Wi-Fi RSSI | dBm, reported received power indication |
| LTE RSRP / RSSI | dBm, distinct reference-signal / aggregate indications |
| LTE RSRQ | dB, reference-signal received quality |
| LTE RSSNR, Android 10 | raw integer tenths of dB; explicit field rssnr_tenth_db |
| LTE RSSNR, Android 11+ | raw integer dB; explicit field rssnr_db |
| NR SS-/CSI-RSRP | dBm, reference-signal received power |
| NR SS-/CSI-RSRQ and SINR | dB, reported quality / interference-plus-noise ratio |
| Wi-Fi frequency | integer MHz, directly supplied by the scan result |
| Cellular ARFCN | channel number; not a frequency in Hz without a RAT mapping |

Unavailable values are JSON null. The Android UNAVAILABLE sentinel is not
plotted as a measurement and is not converted to zero. NR fields containing
the name CSI are scalar reference-signal reports, not complex channel samples.

```text
P_mW = 10^(p_dBm / 10)
mean_power_dBm = 10 log10( sum(10^(p_i/10)) / N )
```

An arithmetic mean of dBm values is a log-domain summary, not mean linear
power. The study tools label their statistics in the recorded metric's domain.
The exponential expression above defines an optional physical conversion;
it is not a new exact transcendental implementation in the native kernel.

<!-- page -->
# 2. Ordered records and identity

Each UTF-8 JSON line is one event. The schema is atomos.radio.v1. Unknown
payload fields survive in the original file and the lossless archive.

| Common field | Meaning |
| --- | --- |
| session_id | UUID for one collection session |
| seq | monotonically increasing integer, beginning with zero |
| kind | session, wifi, cell, status, marker or session_end |
| received_elapsed_ns | decimal string; elapsed-real-time nanoseconds |
| received_unix_ms | local wall-clock milliseconds at recording |
| source_elapsed_ns | decimal string or null; source report timestamp |
| payload | kind-specific data, provenance and status |

Nanosecond integers are serialized as decimal strings to avoid silent loss
through JSON consumers that use binary64 numbers. Phone measurements retain
their returned integer units. JSON encoding and bit-plane transport do not
round these integers.

A Wi-Fi observation key uses the BSSID and frequency within its session.
A cellular key includes subscription, radio technology and reported cell
identity. The complete identity is retained even if some fields are unknown.
An SSID alone is not a unique access point; a PCI alone is not a unique cell.

The physical-device grouping problem is deliberately separate. A router may
have several BSSIDs. MAC addresses can be randomized. An IP address is not
inferred from an ambient Wi-Fi beacon. A cellular cell identifier names a
cell, not a nearby handset. Changes in reported registered cells can be
studied without declaring every change a proven network handover.

## Repeated and conflicting reports

All received events remain in the source file. Analysis recognizes a repeat
only within a session when the source timestamp, observation identity and
observation payload agree. Collection metadata (batch_id, origin and
results_updated) is excluded from that equality but retained in the record.
Different values under the same identity and source time are reported as a
conflict. Missing source times do not establish identical acquisition events.
Unknown fields remain part of comparison, avoiding unsupported equivalence.

<!-- page -->
# 3. Two clocks and actual acquisition time

Let r_k denote received_elapsed_ns, s_k source_elapsed_ns when known, and
u_k received_unix_ms. Elapsed real time includes deep sleep and is local to
one device boot. Wall time is a separate display and alignment coordinate.

```text
age_k_seconds = (r_k - s_k) / 1000000000
delta_t_seconds = (s_j - s_i) / 1000000000
clock_step_ns = 1000000*(u_j-u_i) - (r_j-r_i)
```

These are exact integer/rational relations on the recorded values. A large
clock-step residual calls for inspection of the wall-clock history; it is
not automatically an oscillator-drift measurement. Wall and elapsed clocks
are read sequentially, so their pair also includes readout skew.

Wi-Fi source time is the last-seen timestamp from ScanResult in microseconds
since boot, multiplied exactly by 1000. CellInfo timestamps are approximate
times at which cell information was received from the modem. Where Android
returns milliseconds, multiplication by 1000000 changes units without adding
resolution. They are not radio-carrier phase timestamps.

## Cache, gaps and asynchronous reports

Wi-Fi scan requests and cellular update requests may be throttled. A request
does not guarantee fresh measurements. Log the request/completion status,
retain per-result source timestamps, and distinguish callback receipt from
source time. Foreground execution does not promise a constant sampling rate.
Sleep, scheduling and vendor power management can widen observation gaps.

The default requests are spaced about 35 seconds for Wi-Fi and 10 seconds
for cell reports while the service is scheduled. Broadcasts/callbacks may
arrive at other times. Plot measured elapsed times, not a fictitious uniform
sample index. A normal FFT of callback sequence number is not a justified
physical spectrum of the surrounding RF signal.

A backward receive clock is a session-integrity problem, such as a reboot
or malformed merge. Source timestamps may legitimately arrive out of order;
record arrival order and sort only a derived view. Do not silently join clocks
from different boots or claim atomic-clock synchronization from a timestamp.

<!-- page -->
# 4. Lossless one-bit planes and core binding

Let a session's original bytes be b_0,...,b_(N-1). Zero-pad the last block
to 512 bytes and read each block as 64 unsigned little-endian 64-bit words
w_0,...,w_63. Define 64 one-bit planes packed into 64-bit words:

```text
P_j = sum( ((w_i >> j) & 1) << i, i=0,...,63 )
w_i = sum( ((P_j >> i) & 1) << j, j=0,...,63 )
```

The ARADBP1 archive header is 8 magic bytes, 8 bytes of original length as
little-endian uint64, and 32 bytes of SHA-256. Each block follows as 64
little-endian plane words. Applying the transpose again is its inverse.
The decoder rejects inconsistent lengths, nonzero padding and wrong hashes.
Decoding must return
the original byte sequence, including whitespace, line endings, unknown
fields and any incomplete trailing bytes.

This is lossless one-bit-plane packing of the acquired record. It does not
claim compression, reconstruct an analogue signal, or reduce measurement
uncertainty. Parsing is a separate operation: a byte-preserving archive can
contain a malformed log, which the analysis tool must still report as such.

## Existing aTOMos core

R18 Cell48/State64, ordered EMIT journals, ASA/NA/JK feedback and exact bounded
phase/word execution remain unchanged. R19 supplies a typed external-input
boundary and repeatable acquisition records. It does not silently reinterpret
radio strength as an ASA/NA mask or a native phase word.

A later feedback specialization must explicitly bind an observation
predicate, a time-selection policy, a mask width and an update rule. For
example, a threshold predicate may use an observed RSSI and declared threshold:

```text
e_k = 1  if valid(y_k) and y_k >= threshold
e_k = 0  if valid(y_k) and y_k <  threshold
e_k = unknown  if y_k is unavailable
```

Mapping unknown to an inactive bit would discard information unless a policy
explicitly requests it. This example is a formal input contract, not an
implemented GPU feedback adapter. The executable path delivered here is
capture, export, analysis and reversible archival.

<!-- page -->
# 5. Collection and study protocol

Install the development APK on the POCO. Open the app, grant the requested
radio/location permissions and enable Android Location so scan results are
available. Start a session from the visible app. A notification identifies
the active logging service. Stop before exporting a complete session.

Data remains in app-private storage until the user exports it through the
Android document picker. The application has no network-upload function.
Interrupted sessions are retained as incomplete evidence. The public release
contains synthetic fixtures and emulator evidence, never the user's private
radio survey. Uninstalling the app can remove its private sessions, so export
the records to be retained first.

## A first controlled experiment

Record at a fixed position for several minutes. Add a marker describing the
position and phone orientation. Move to a second position and add another
marker. Return to the first position and repeat. Keep the setup described
well enough to distinguish repeatable changes from ordinary fluctuations.

Export JSONL, then run the study command documented in README.md. The output
contains a normalized CSV, a machine-readable summary, a readable report and
plots with actual timestamps. Inspect cache counts, missing values, status
events and clock issues before interpreting apparent signal changes.

Compare the same BSSID/frequency or the same cellular identity and metric.
RSRP, RSSI, RSRQ and SINR have different definitions. A 5G status icon does not
guarantee a reported NR CellInfo entry; LTE and NR may coexist, and fields
depend on the modem/operator interface. An absent NR entry is not evidence
that no 5G transmission exists nearby.

## Verification and completion

The release records APK build/signature checks, runtime smoke evidence,
study-tool tests and archive round trips in review/. Synthetic and emulator
inputs are labelled by origin. These establish implementation behavior for
those inputs. The next physical acceptance step is one exported POCO session
with Wi-Fi results, available cellular fields, a marker and an orderly stop.
Its actual cadences and available metrics become device-specific evidence.

<!-- page -->
# 6. Sources and retained foundation

Primary Android sources determine the meanings of the recorded API fields.
Links were checked on 2026-09-17. The field contract, analysis and packing
rules in this supplement are the implementation's own specialization.

1. Android Wi-Fi scanning overview. Visible AP scans, permission requirements,
   cached results and request throttling.
   https://developer.android.com/develop/connectivity/wifi/wifi-scan

2. Android ScanResult reference. BSSID, RSSI, frequency and last-seen time.
   https://developer.android.com/reference/android/net/wifi/ScanResult

3. Android TelephonyManager reference. Reported serving/neighbor cells and
   rate-limited requests for updated cell information.
   https://developer.android.com/reference/android/telephony/TelephonyManager

4. Android CellInfo reference. Timestamp clock and approximate modem receipt.
   https://developer.android.com/reference/android/telephony/CellInfo

5. Android CellSignalStrengthNr and CellSignalStrengthLte references.
   https://developer.android.com/reference/android/telephony/CellSignalStrengthNr
   https://developer.android.com/reference/android/telephony/CellSignalStrengthLte

6. AOSP CellSignalStrengthLte.java, android-10.0.0_r1 and android-11.0.0_r1.
   Source code confirms the RSSNR transition from tenths to whole dB.
   Exact source URLs and hashes are recorded in source/api_sources.json.

7. Android SystemClock reference. Elapsed time includes deep sleep; wall time
   and network-time observations have distinct semantics.
   https://developer.android.com/reference/android/os/SystemClock

## Retained R18 manuscript

The following 103 pages reproduce the reviewed R18 manuscript. They retain
its cover, page numbers, equations, citations and bounded implementation
claims. The parent PDF's SHA-256 is:

```text
a62e3d7a57ec4c01c18308d9eb4b3c2f1617
2baf0e88276fbf6e64e591390cf0
```

The PDF builder requires that exact parent hash before including it. Existing
orbit/S2/CUDA results are inherited evidence for their original workloads;
they do not validate the phone's radio measurements or imply a new numerical
performance result. Source bindings and release artifact hashes accompany
the installable logger and study tools.
