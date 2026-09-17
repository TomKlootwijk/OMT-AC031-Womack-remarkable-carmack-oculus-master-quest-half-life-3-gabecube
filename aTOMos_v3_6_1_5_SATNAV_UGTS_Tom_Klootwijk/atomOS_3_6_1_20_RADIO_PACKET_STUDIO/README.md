# aTOMos 3.6.1.20 - Radio Packet Studio

R20 adds on-phone session review, signal trends, Wi-Fi beacon-field decoding,
the phone's own IP/DNS/route context, and local packet-file inspection. It uses
PCAPdroid as a separate capture app and TShark for deeper desktop analysis.
R19 and the exact mathematical kernel remain preserved.

## Upgrade

Install `output/android/aTOMos-Radio-3.6.1.20-debug.apk` over the existing
`org.atomos.radio` app. Keep the same signing key when rebuilding. **Do not
uninstall to upgrade:** Android removes private sessions when an app is
uninstalled. This is a development APK, not a Play Store release.

## Review the session you already captured

Open aTOMos Radio, select the saved session and open its study screen. The
review shows access-point and cell identities, signal ranges and trends,
source age, repeated source timestamps and the latest recorded fields.
An AP count for the entire file can include stale Android scan-cache results.
The review separately counts identities with reports no more than 30 seconds
old at receipt. This is an explicit analysis threshold, not a measurement
guarantee. The desktop study has additional sequence/clock/conflict checks.

Record a new session to collect raw SSID bytes and exposed information elements
along with decoded SSID/rates/channel/RSN/vendor and capability labels. The new
read-only network-context records describe this phone's visible links, interface
addresses, DNS servers and routes. Historical R19 files cannot gain fields
that were never recorded. Add timestamped notes for motion or app actions.

## Capture and decode this phone's packets

1. Open **Packet study**, then **Capture phone packets Â· open PCAPdroid**.
2. In PCAPdroid select **PCAP file** output; press Start and accept Android's
   VPN prompt when shown. Use the phone or the chosen app for the experiment.
3. Stop PCAPdroid. Its file is saved in **Downloads/PCAPdroid**.
4. Return to aTOMos, press **Import capture · Downloads or USB storage** and choose the file.
5. Review protocol counts, endpoints, packet/DNS details and decoding issues.
   Export either the original capture bytes or the decoded JSON report.

The readable UDP browser shows packet endpoints, ports, timestamps, lengths,
decoded protocol fields and bounded text/hex payload previews. Binary bytes
and encrypted content are not presented as decoded messages. Display limits
are explicit; original bytes remain available for the desktop dissector.

For background observation, start the radio session and PCAPdroid separately,
then use other apps or turn off the screen. Their ongoing Android notifications
indicate recording and let you return to the controls. Stop both when the
experiment ends. Radio acquisition continues through its foreground service;
PCAPdroid owns the independent VPN capture service.

For OTG file import, attach a USB drive using a compatible adapter, open
**Import capture · Downloads or USB storage**, select the mounted drive in Android's file picker,
and choose the capture. This uses the same local byte-preserving import path.
The release was tested with Downloads; physical USB storage was not attached
during validation. No USB Wi-Fi/Ethernet capture driver is added.

The phone inspector supports PCAP and PCAPNG, Ethernet/VLAN, raw IPv4/IPv6,
Linux cooked links, TCP/UDP/ICMP, bounded DNS, HTTP method/status and TLS record
metadata. It preserves unsupported or encrypted content in the original file.
Its preview has explicit limits: 64 MiB files, 100,000 visited packets,
200 packet details and 512 displayed endpoints. It does not reassemble TCP or
IP fragments, verify every checksum or decrypt TLS. Use the desktop tool for
broader protocol dissection and Wireshark for interactive packet inspection.

The aTOMos app itself has no Internet permission and does not upload captures.
PCAPdroid handles the phone's routed traffic separately. Its non-root VPN proxy
can change packet sizes/timing and incoming IP/transport headers; these traces
are not direct antenna or over-the-air timing measurements. See the
[official PCAPdroid guide](https://emanuele-f.github.io/PCAPdroid/quick_start.html).

## Desktop study

Run from this release directory with Python 3.10+:

```powershell
python -m pip install -r requirements-study.txt
python tools/study_radio.py study private/my_session.jsonl private/radio_study
python tools/study_packets.py private/my_capture.pcap private/packet_study
```

Choose a new or empty output directory. Packet study needs an installed
[TShark](https://www.wireshark.org/docs/man-pages/tshark.html); pass
`--tshark "C:/Program Files/Wireshark/tshark.exe"` when it is not found.
The command reads existing files, disables name resolution and records the
decoder version. Outputs include original bytes and hashes, packet fields,
protocol hierarchy, conversations, JSON and Markdown summaries. The additional
`udp_readable.md` lists readable UDP details with capped 64-byte payload previews
for up to 200 UDP records; all original bytes remain available. TLS/QUIC
metadata does not mean encrypted application payloads have been decoded.

Radio outputs include normalized records, per-link statistics, source-age and
channel summaries, quality diagnostics and readable per-link plots. Radio and
packet traces need overlapping windows and clock context before correlation.
The original radio session and the later packet experiment are separate runs.

## Literal lossless bit-plane archive

```powershell
python tools/study_radio.py pack private/my_session.jsonl private/session.aradbp
python tools/study_radio.py unpack private/session.aradbp private/restored.jsonl
```

ARADBP1 restores the exact source bytes using a 64-by-64 word transpose,
original length and SHA-256. This is reversible storage, not compression or
additional sensor precision. All private captures and identifying study
outputs belong under `private/` or `sessions/`, which are excluded from Git
and release packaging. Public packet and radio examples are synthetic.

## Build and validation

```powershell
powershell -File tools/build_android.ps1
python -m unittest discover -s tests -v
python tools/build_pdf.py
python tools/review_pdf.py
```

Android requires SDK 36 and JDK 17+. The PDF uses the editable source
`formal/RADIO_PACKET_PROFILE.md`, the hash-bound `source/parent_R19.pdf`,
`requirements-document.txt`, Calibri/Consolas or DejaVu fonts and Poppler.
The complete document has 117 pages: seven new pages and all 110 R19 pages.
Every inherited page is checked for identical rendered pixels. New pages are
visually reviewed before packaging; rebuilding requires a fresh visual review.

The release passes 47 host tests and 19 Android instrumentation tests.
`VERSION.json` and `review/` record the actual test and deployment results.
The fixtures exercise mixed byte order, timestamp resolution, common packet
layers and malformed input; agreement is limited to the fields both decoders
support. Physical POCO evidence establishes compatibility and data availability,
not calibrated RF sensitivity, ranging accuracy or discovery of every nearby
device. The app does not yet connect these observations to ASA/NA/JK feedback
or implement a Mali GPU backend.
