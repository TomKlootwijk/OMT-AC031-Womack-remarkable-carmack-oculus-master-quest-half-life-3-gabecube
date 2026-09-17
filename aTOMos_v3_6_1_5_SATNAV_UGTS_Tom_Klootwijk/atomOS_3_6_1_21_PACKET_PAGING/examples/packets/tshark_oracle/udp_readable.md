# Readable UDP packet study

Study label: SYNTHETIC documentation-address protocol fixture

Showing 4 of 4 decoded UDP packet records at zero-based UDP offset 0. Page limit 200; at most 200 records and 64 preview bytes per record are displayed.

Offsets count UDP matches in capture order, including DNS over UDP. Match totals cover decoded packets only, within the declared packet limit; they do not count an uninspected tail of the capture.

Times and protocol summaries come from the capture and TShark. The UDP length field includes its 8-byte header. Payloads may have been reassembled by TShark. Original captured bytes remain in the source artifact.

Hex is the exact bounded byte preview. ASCII displays printable bytes and uses `.` for other bytes; printable characters do not establish plaintext. QUIC/DTLS bytes are not presented as decrypted application data.

## UDP frame 1

```text
Capture epoch time: 1700000000.100000000
Source: 192.0.2.10:53000
Destination: 192.0.2.53:53
UDP length field: 38 bytes
Frame bytes captured/original: 72/72
Protocol stack: eth:ethertype:ip:udp:dns
Decoded summary: Standard query 0x1919 A example.test
Classification: TShark decoded: dns. Read the decoded fields alongside the raw-byte preview.
DNS question: example.test
First UDP payload preview: 30 of 30 reported payload bytes; payload occurrences: 1
HEX: 19 19 01 00 00 01 00 00 00 00 00 00 07 65 78 61 6d 70 6c 65 04 74 65 73 74 00 00 01 00 01
ASCII: .............example.test.....
```

## UDP frame 2

```text
Capture epoch time: 1700000001.101000000
Source: 192.0.2.53:53
Destination: 192.0.2.10:53000
UDP length field: 54 bytes
Frame bytes captured/original: 88/88
Protocol stack: eth:ethertype:ip:udp:dns
Decoded summary: Standard query response 0x1919 A example.test A 203.0.113.7
Classification: TShark decoded: dns. Read the decoded fields alongside the raw-byte preview.
DNS question: example.test
DNS A answers: 203.0.113.7
First UDP payload preview: 46 of 46 reported payload bytes; payload occurrences: 1
HEX: 19 19 81 80 00 01 00 01 00 00 00 00 07 65 78 61 6d 70 6c 65 04 74 65 73 74 00 00 01 00 01 c0 0c 00 01 00 01 00 00 00 3c 00 04 cb 00 71 07
ASCII: .............example.test..............<....q.
```

## UDP frame 13

```text
Capture epoch time: 1700000012.112000000
Source: [2001:db8:a::10]:53001
Destination: [2001:db8:b::53]:53
UDP length field: 38 bytes
Frame bytes captured/original: 92/92
Protocol stack: eth:ethertype:ipv6:udp:dns
Decoded summary: Standard query 0x1919 AAAA example.test
Classification: TShark decoded: dns. Read the decoded fields alongside the raw-byte preview.
DNS question: example.test
First UDP payload preview: 30 of 30 reported payload bytes; payload occurrences: 1
HEX: 19 19 01 00 00 01 00 00 00 00 00 00 07 65 78 61 6d 70 6c 65 04 74 65 73 74 00 00 1c 00 01
ASCII: .............example.test.....
```

## UDP frame 15

```text
Capture epoch time: 1700000014.114000000
Source: 192.0.2.10:49000
Destination: 198.51.100.20:49001
UDP length field: 51 bytes
Frame bytes captured/original: 69/69
Protocol stack: eth:ethertype:ip:udp:data
Decoded summary: 49000 → 49001 Len=43
Classification: Unknown or undissected UDP application payload. Binary bytes are not assumed to be plaintext.
First UDP payload preview: 43 of 43 reported payload bytes; payload occurrences: 1
HEX: 53 59 4e 54 48 45 54 49 43 2d 46 52 41 47 4d 45 4e 54 2d 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
ASCII: SYNTHETIC-FRAGMENT-........................
```
