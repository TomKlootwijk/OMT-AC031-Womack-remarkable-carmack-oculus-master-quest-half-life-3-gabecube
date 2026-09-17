# Synthetic packet fixtures

All addresses, names and payloads here are synthetic. `make_fixtures.py` constructs bytes locally without sockets or network calls. `fixture_manifest.json` records every container hash and the intended packet descriptions. `example.test`, documentation IP ranges and locally administered MAC addresses are used.

The main classic PCAP and PCAPNG contain the same 17 Ethernet frames: DNS query and compressed response; TCP/HTTP GET and 200 response; a TLS ClientHello with SNI and an opaque application-data record; IPv6 DNS; IPv4 fragments; an experimental EtherType; and a captured frame shorter than its wire length. The TLS fixture tests parsing and does not represent an authenticated TLS connection.

Additional files exercise RAW IP, big-endian nanosecond PCAP, Linux cooked v1/v2, mixed-endian PCAPNG sections, per-interface decimal/binary timestamp resolution and timestamp offsets. Separate malformed examples contain a DNS compression-pointer loop, an unknown PCAPNG interface, a truncated container and non-capture text.

`synthetic_udp_truncated.pcap` keeps a complete UDP header but captures only four payload bytes. It checks that the report distinguishes the declared UDP length, original frame length and bytes actually available for preview.

From the release directory:

```powershell
python tools/study_packets.py examples/packets/synthetic_ethernet.pcap path/to/new-study --label "SYNTHETIC protocol fixture"
python tools/study_packets.py examples/packets/synthetic_paging_750.pcap path/to/third-udp-page --udp-offset 400 --udp-limit 200 --label "SYNTHETIC paging fixture"
python -m unittest discover -s tests -v
```

TShark defaults to `C:/Program Files/Wireshark/tshark.exe`; use `--tshark PATH` for another official installation. The output directory must be new or empty. The tool copies original bytes, writes their hash, selected packet metadata, a protocol hierarchy, TCP/UDP/IP conversation summaries and decoder errors. It runs offline with name resolution disabled and no live capture interface. Packet or time limits remain explicit.

`udp_readable.md` and `udp_previews.json` add readable packet times, IP:ports, UDP length fields, decoded protocol summaries and a maximum 64-byte ASCII/hex preview per record. `--udp-offset` is zero-based among all decoded UDP matches, including DNS over UDP; `--udp-limit` sets a page size from 1 to 200. Defaults preserve the first 200-record view. Metadata records `total_matches`, `has_next` and `next_offset`; use a new output directory for each page. Counts cover the inspected packet prefix (default maximum 100,000 packets), with limit/error status retained. Hex preserves the preview bytes exactly; ASCII uses a dot for nonprintable bytes. QUIC/DTLS and unknown binary payloads receive explicit labels. The complete packet capture remains the source; a bounded preview is not a decrypted payload or a replacement for original bytes.

`synthetic_paging_750.pcap` contains 750 frames: every third frame is TCP, and the remaining 500 are UDP. Only frames 452 and 749 contain DNS questions (`page0452.example.test` and `page0749.example.test`). Pages of 200 UDP matches begin at offsets 0, 200 and 400, returning 200, 200 and 100 records. The final page reaches frame 749. `paging_oracle/` records that last-page TShark result; exact expected indices and fixture hashes are in the manifest.

`tshark_oracle/` is the successful independent TShark 4.6.2 decoding of the main synthetic fixture. TLS outer record type 23 is counted using both classic `tls.record.content_type` and TLS 1.3 `tls.record.opaque_type`. An opaque TLS 1.3 outer record does not identify the encrypted inner content type. DNS decoder placeholders remain diagnostics instead of invented host names. Unknown protocols, packet truncation and container errors remain visible.

Real phone captures and their identifying results belong under `private/`, which is excluded from Git and public release archives.
