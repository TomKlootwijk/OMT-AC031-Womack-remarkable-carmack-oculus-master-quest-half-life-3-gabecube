# Synthetic packet fixtures

All addresses, names and payloads here are synthetic. `make_fixtures.py` constructs bytes locally without sockets or network calls. `fixture_manifest.json` records every container hash and the intended packet descriptions. `example.test`, documentation IP ranges and locally administered MAC addresses are used.

The main classic PCAP and PCAPNG contain the same 17 Ethernet frames: DNS query and compressed response; TCP/HTTP GET and 200 response; a TLS ClientHello with SNI and an opaque application-data record; IPv6 DNS; IPv4 fragments; an experimental EtherType; and a captured frame shorter than its wire length. The TLS fixture tests parsing and does not represent an authenticated TLS connection.

Additional files exercise RAW IP, big-endian nanosecond PCAP, Linux cooked v1/v2, mixed-endian PCAPNG sections, per-interface decimal/binary timestamp resolution and timestamp offsets. Separate malformed examples contain a DNS compression-pointer loop, an unknown PCAPNG interface, a truncated container and non-capture text.

From the release directory:

```powershell
python tools/study_packets.py examples/packets/synthetic_ethernet.pcap path/to/new-study --label "SYNTHETIC protocol fixture"
python -m unittest discover -s tests -v
```

TShark defaults to `C:/Program Files/Wireshark/tshark.exe`; use `--tshark PATH` for another official installation. The output directory must be new or empty. The tool copies original bytes, writes their hash, selected packet metadata, a protocol hierarchy, TCP/UDP/IP conversation summaries and decoder errors. It runs offline with name resolution disabled and no live capture interface. Packet or time limits remain explicit.

`tshark_oracle/` is the successful independent TShark 4.6.2 decoding of the main synthetic fixture. TLS outer record type 23 is counted using both classic `tls.record.content_type` and TLS 1.3 `tls.record.opaque_type`. An opaque TLS 1.3 outer record does not identify the encrypted inner content type. DNS decoder placeholders remain diagnostics instead of invented host names. Unknown protocols, packet truncation and container errors remain visible.

Real phone captures and their identifying results belong under `private/`, which is excluded from Git and public release archives.
