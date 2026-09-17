# aTOMos 3.6.1.21 - Packet Paging

R21 removes the first-200-packet browsing barrier. The phone filters and searches
the inspected capture, then shows bounded pages of up to 200 matching records.
Previous and Next reach later records without retaining every packet object.
The desktop UDP report gains matching offset and page-size controls.

## Install and browse

Install `output/android/aTOMos-Radio-3.6.1.21-debug.apk` over the existing
`org.atomos.radio` app with the same signing key. Do not uninstall: uninstalling
removes private sessions. This is a development APK.

Open **Packet study**, select an imported capture and open the packet browser.
Choose All, UDP, DNS, TCP or TLS; enter search text and use **Previous / Next**.
Search matches decoded metadata and bounded UDP previews across the inspected
capture. It starts at the first matching result when the filter changes.
Status shows how much of the capture was inspected. If bytes change, the browser
discards the page and offers **Reload changed capture** to bind a new source.

Packet study reuses R20's PCAPdroid launch and Android document import workflow:
start and stop capture in PCAPdroid, then import its PCAP from Downloads or
mounted USB storage. Background radio logging remains a separate foreground
service with visible recording controls. This release does not add an automatic
VPN capture service inside aTOMos or a live USB radio adapter driver.

## Desktop pages

```powershell
python -m pip install -r requirements-study.txt
python tools/study_packets.py private/capture.pcap private/page_1 --udp-offset 0 --udp-limit 200
python tools/study_packets.py private/capture.pcap private/page_2 --udp-offset 200 --udp-limit 200
python tools/study_packets.py private/capture.pcap private/page_3 --udp-offset 400 --udp-limit 200
```

Use a new or empty output directory for each run. TShark is required; pass
`--tshark "C:/Program Files/Wireshark/tshark.exe"` if it is not on PATH.
`udp_readable.md` and `udp_previews.json` contain the requested page and
`summary.json` records total matches within the inspected prefix and next offset.
The original capture is preserved with a SHA-256 digest. For pages across runs,
compare source hashes or use the saved `source_original` capture so that pages
refer to the same bytes. Desktop runs do not automatically pin earlier hashes.

The offset is zero-based among UDP matches, not among all frames. Page size is
1-200; the default remains offset 0 and size 200. Packet inspection defaults to
100,000 frames and has an explicit configurable cap. Reaching the scan cap does
not establish that the remaining capture has no matches.

Existing radio study and lossless bit-plane archive commands remain available:

```powershell
python tools/study_radio.py study private/session.jsonl private/radio_study
python tools/study_radio.py pack private/session.jsonl private/session.aradbp
python tools/study_radio.py unpack private/session.aradbp private/restored.jsonl
```

## Execution and evidence

Phone inspection remains bounded by 64 MiB, 100,000 packets and inherited
container limits. Pages keep at most 200 matching details. Each request rescans
the source on a background worker; text input is debounced and stale requests
cannot overwrite newer results. This makes later records accessible, but is
not a persistent index or a maximum-size performance benchmark.

The native decoder preserves exact timestamp fields and source bytes. It
supports PCAP/PCAPNG, common link/IP/transport layers, bounded DNS and UDP
previews, NTP/DHCP candidates, HTTP method/status and TLS record metadata.
TCP/IP reassembly and broader protocol dissection use desktop TShark. Radio
acquisition, calibration, ASA/NA/JK feedback and GPU execution are unchanged.

Public examples are synthetic. Keep physical captures and identifying study
outputs under ignored `private/` or `sessions/`; they are excluded from packaging.
The 750-frame paging fixture contains 500 UDP records over three pages and late
DNS at frames 452 and 749. The original ten fixture hashes are unchanged.
`review/` and `VERSION.json` contain actual test counts, source/APK pins and
deployment scope. A previous R20 phone install is not evidence of an R21 install.

## Build and formal document

```powershell
powershell -File tools/build_android.ps1 -IncludeTests
python -m unittest discover -s tests -v
python tools/build_pdf.py
python tools/review_pdf.py
```

Android requires SDK 36 and JDK 17+. Use the original signing key for upgrades.
PDF dependencies are in `requirements-document.txt`; rendering uses Poppler.
The editable `formal/PACKET_PAGING_PROFILE.md` defines ordered selection,
pagination, completeness and source identity. The complete PDF has 120 pages:
three new pages followed by all 117 hash-bound R20 pages. Rebuilding requires
fresh visual inspection before packaging.

Git repair base `7481591` restores the two R19 Git policy files removed in
`3ce60e2`. The original R20 release commit `87743d5` was already on GitHub;
191 missing tracked R19/R20 files in the main checkout were restored exactly.
This version preserves prior releases and uses exact-byte Git attributes.
