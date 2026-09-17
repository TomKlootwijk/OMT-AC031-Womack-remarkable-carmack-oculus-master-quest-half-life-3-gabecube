# Radio Packet Studio
## aTOMos 3.6.1.20 - typed observations and packet evidence

Tom Klootwijk | 2026-09-17 | ATOMOS-RADIO-PACKET-R1

This subversion extends the Android acquisition and study layer with session review, Wi-Fi information-element decoding, the phone's own connection context, and local PCAP/PCAPNG inspection. A separate PCAPdroid installation captures traffic initiated by the phone through Android's VPN interface. The original capture bytes remain the evidence; decoded fields are reproducible interpretations.

The exact word and bit-plane core is retained. R20 introduces no new physical law, propagation model or floating-point replacement. It defines how measured scalar radio reports and packet bytes enter the same provenance-preserving system without conflating their meanings.

| Evidence type | Meaning |
| --- | --- |
| Radio record | Android-reported power, quality, identity and source time. |
| Beacon information element | A typed byte field exposed by Android's scan API; unknown bytes remain available. |
| Packet record | Captured link/IP data with container time, length and interface context. |
| Derived report | Versioned decoding, grouping and statistics linked to source bytes. |

## Release lineage

Seven new pages precede the complete 110-page R19 manuscript. Its pages and original pagination are retained, including the prior mathematical foundation. The build binds the parent PDF by SHA-256 and verifies every inherited page's content stream, extracted text and rendered pixels. Editable sources, Android code, desktop tools, synthetic fixtures and validation records accompany this document.

<!-- page -->
# Evidence before interpretation

Let B be an input byte string and H its SHA-256. Parsing produces typed records, diagnostics and an explicit completeness flag. It must not replace the source with the parsed representation.

```
E = (B, H(B), acquisition_context)
D_v(B) = (records, diagnostics, complete, decoder_version=v)
P^-1(P(B)) = B
H(P^-1(P(B))) = H(B)
```

P is the existing ARADBP1 64-by-64 word bit-plane transpose. Its inverse restores the original byte count exactly, including formatting and unknown fields. This is a storage bijection; it neither removes measurement uncertainty nor supplies missing packet bytes. SHA-256 detects accidental change and binds results to an input; it is not proof that a source measurement is true.

## Typed boundaries

The decoder must retain distinctions between unavailable, unsupported, malformed, truncated and encrypted. A valid container can contain an unsupported link type. A valid IP packet can carry encrypted application data. A stopped-at-limit report is partial even when every inspected packet was valid. Null source time is not time zero.

```
record = (container, interface, timestamp, caplen, wirelen, bytes)
0 <= caplen <= available_record_bytes
derived = (source_hash, decoder_id, scope, result, issues)
```

Original file export and JSON report export are separate operations. Imports and decoding run locally. Public fixtures are explicitly synthetic; real phone captures and identifying derivatives stay outside source-control and release archives.

<!-- page -->
# Clocks and radio freshness

R19 supplies receipt elapsed time, receipt wall time and available radio source elapsed time. R20 exposes source age and repeated cache reports in the on-phone review and desktop study. A requested scan or callback does not establish a new physical observation.

```
age_ns = received_elapsed_ns - source_elapsed_ns
fresh_tau = known(source_elapsed_ns) AND 0 <= age_ns <= tau_ns
tau = 30 seconds  (analysis policy, not an Android guarantee)
```

Identity counts for the whole session and recent observations are separate. A Wi-Fi BSSID identifies a reported access-point interface, not a count of people or subscriber devices. A missing NR record does not establish absence of 5G coverage. Values with the same identity and source time are cache candidates; differing payloads at the same source time are conflicts, not silently averaged observations.

## Cross-stream alignment

PCAP timestamps are container times. PCAPNG time resolution and offsets are interface-specific; a section resets the interface table. Retain integer timestamp ticks and their resolution before deriving display seconds. Records without timestamps remain untimed.

```
wall_est(e) = wall_anchor + (e - elapsed_anchor)
residual_i = recorded_wall_i - wall_est(elapsed_i)
```

The affine mapping is local to an uninterrupted clock segment. A wall-clock jump invalidates a single global offset. Correlating radio and packet events requires overlapping recording windows and clock anchors. Packet timestamps from a software VPN proxy are not RF phase, time of flight or antenna arrival times. R20 adds no automatic ranging or causal conclusion from coincident traffic and RSSI changes.

<!-- page -->
# Beacon and connection context

Android scan records can expose raw SSID bytes and information elements. R20 stores each element's ID, extension ID and byte payload alongside the bounded decode. Unknown elements remain raw and labeled. The available set depends on Android and the device driver.

| Field family | Interpretation |
| --- | --- |
| SSID | Raw bytes preserved; display text is a decoded view. |
| Supported rates / DS channel | Advertised rates and channel information when present. |
| RSN | Declared cipher and authentication suites; not proof of active association security. |
| Vendor element | OUI and bounded payload; unknown vendor content remains undecoded. |
| HT / VHT / HE / EHT | Capability-element recognition; no invented channel-state samples. |

Each count and offset must fit within the element's actual byte length. Malformed suite lists are reported, not read past the buffer. Raw bytes survive unsuccessful interpretation.

## This phone's network context

Read-only Android connection context records visible transports, interface addresses, DNS servers and routes when available. It describes links visible to this phone. The app does not infer the IP address of every scanned AP or enumerate all nearby clients from a beacon table. No active network probing is introduced.

This context is a status observation with its own receipt clocks. Changing a Wi-Fi interface, cellular link or VPN can change it independently of the radio-source cache. The app retains its local storage workflow and does not need Internet permission to launch PCAPdroid or import and inspect a file.

<!-- page -->
# Packet decoding contract

The Android decoder reads classic PCAP and PCAPNG with bounded allocation and traversal. It handles supported byte orders, per-interface link types and timestamps, and reports rejected/truncated records. File, packet and displayed-detail limits are included in the report. A bounded preview is not described as an exhaustive decode.

| Layer | Implemented inspection |
| --- | --- |
| Container | PCAP / PCAPNG records, lengths, interface context, timestamp resolution. |
| Link | Ethernet with VLAN, RAW IP and Linux cooked capture variants. |
| Network | IPv4 / IPv6 headers and bounded extension traversal. |
| Transport | TCP / UDP / ICMP fields, endpoints and protocol counts. |
| Application | Bounded DNS names, NTP/DHCP fields, HTTP method/status and TLS record metadata. |

The small on-phone parser does not perform TCP stream reassembly or TLS decryption. DNS compression traversal must terminate, respect message bounds and reject cycles. A TLS record label does not identify a decrypted request, URL or message. Protocol-port hints do not replace verified protocol bytes.

The readable UDP view presents source/destination endpoints, container time, UDP length, available payload length, decoded fields and a bounded text/hex preview. Printable bytes are a display interpretation, not proof of plaintext. Binary or encrypted content stays labeled; omitted preview bytes remain in the original file. The desktop UDP report offers the broader dissector's interpretation alongside raw previews.

```
payload_length = UDP_length - 8
captured = max(0, min(IP_end, UDP_start + UDP_length) - UDP_start - 8)
phone_preview_bytes = min(captured, 128)
NTP_wire_seconds = seconds_field + fraction_field / 2^32
```

Full UDP payload coverage requires captured = payload_length and no unresolved fragment. NTP fields preserve their wire values; the era is unresolved and no UTC clock calibration is inferred (RFC 768, RFC 5905). DHCP fields follow RFC 2131/2132 with bounded option lengths.

## Desktop inspection

The companion study command delegates broader dissections to an installed TShark, records its version, disables name resolution, and writes local packet, conversation and protocol reports. It keeps source hashes and capture completeness visible. TShark can expose more protocol fields and reassembly than the small phone parser; the two outputs are compared on shared synthetic fixtures within their common scope.

Unknown protocols and encrypted payloads remain available in the original capture for later analysis with an appropriate decoder or separately supplied keys. No missing packet data is reconstructed from radio-power logs.

<!-- page -->
# Capture and experiment workflow

Open PCAPdroid from the aTOMos packet screen, choose PCAP file, start capture and accept Android's VPN prompt when shown. Use the phone normally for the experiment, then stop capture. Import the saved file from Downloads/PCAPdroid into aTOMos for local inspection. Capturing and importing are explicit actions.

Radio acquisition and PCAPdroid capture can continue while backgrounded, using Android foreground services with ongoing notifications. They are started and stopped separately. Android's document picker can also import captures from mounted USB storage through its storage provider; this is file import, with no USB network-adapter driver added. The handset checks used Downloads; a physical USB drive was not tested.

PCAPdroid remains a separate application with its own source, license and settings. Its non-root mode proxies phone-initiated connections: incoming IP and transport headers can be synthetic and packet sizes/timing can change. That provenance belongs in any interpretation of the trace. Radio and packet captures answer different questions and can be studied together when their time windows overlap.

## Useful experiments

Compare the same app action on Wi-Fi and cellular; inspect DNS names and visible TLS metadata; measure reported traffic volumes; repeat a stationary radio recording; add motion/orientation markers and compare per-AP signal trends. Use matched time windows and record context changes. These are observations of reported radio values and routed application traffic, not an ambient RF waveform capture.

The first physical R19 session verified the acquisition path: 172 events over about 32.7 seconds, with Wi-Fi and LTE observations. The initial Wi-Fi batch contained old cache entries; the later batch supplied 25 fresh AP identities. This motivated explicit cache-age displays. It does not establish sensitivity, positioning accuracy, complete device discovery or packet coverage.

## Preservation during deployment

R20 keeps the Android package and signing identity so an in-place update retains sessions. Exported originals remain byte-identical. The previous release is retained. Real sessions, packet traces and identifying derived reports are excluded from the distributable package; only synthetic or clearly marked emulator evidence is published.

<!-- page -->
# Validation and references

Validation separates parser correctness, file preservation, UI behavior and physical acquisition. Synthetic packets exercise supported container/link/transport paths and malformed boundaries. Shared fixtures establish agreement with TShark on supported fields. Android instrumentation and emulator UI checks exercise import/review/export. Physical POCO checks establish deployment and real-source compatibility; they do not replace a calibrated RF experiment.

Release-specific counts, hashes, limits and measured results are recorded in VERSION.json and review/. The build includes the full inherited formalization. Neither new application features nor agreement with a packet decoder proves a new physical law or better orbit, positioning or sensing accuracy.

## Primary specifications and implementation references

Android ScanResult and information-element API:
https://developer.android.com/reference/android/net/wifi/ScanResult

Android clock and VPN interfaces:
https://developer.android.com/reference/android/os/SystemClock
https://developer.android.com/reference/android/net/VpnService

PCAPdroid capture, file workflow and non-root packet provenance:
https://emanuele-f.github.io/PCAPdroid/quick_start.html
https://github.com/emanuele-f/PCAPdroid

TShark command-line dissector and output options:
https://www.wireshark.org/docs/man-pages/tshark.html

Capture container and link-type references:
https://www.tcpdump.org/manpages/pcap-savefile.5.html
https://www.tcpdump.org/linktypes.html

References identify the source interfaces; the executable code defines the exact implemented subset. The formal core remains available for future domain adapters with explicit variables, units, source observations and validation criteria.
