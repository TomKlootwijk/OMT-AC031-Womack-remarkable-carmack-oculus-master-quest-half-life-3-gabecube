# aTOMos R21 packet study

Study label: SYNTHETIC documentation-address protocol fixture

Status: **decoded**. Capture: pcap, 1497 bytes.

Original SHA256: `a5fa3a30136a0404da19c047a2e40bef823719a3def7bad77357c3733ba56754`.

Decoder: `TShark (Wireshark) 4.6.2 (v4.6.2-0-g24d5e2b5a3dc).`.

Decoded 17 packet rows; packet limit 100000; limit reached: False.

All original bytes remain in `source_original.pcap`. `packet_fields.csv` contains decoded metadata; `protocols_conversations.txt` contains TShark's protocol hierarchy and endpoint conversations.

`udp_readable.md` shows decoded UDP summaries, endpoints and capped ASCII/hex payload previews. `udp_previews.json` keeps the same bounded structured view. UDP page offset 0, limit 200, total decoded UDP matches 4, next offset None.

## Protocols

| Protocol | Frames containing layer |
|---|---:|
| data | 3 |
| data-text-lines | 1 |
| dns | 3 |
| eth | 17 |
| ethertype | 17 |
| http | 2 |
| ip | 15 |
| ipv6 | 1 |
| tcp | 10 |
| tls | 2 |
| udp | 4 |

## Capture interpretation

Offline capture only. Protocol counts may overlap because one frame contains multiple protocol layers. Captured IP traffic is not a radio-power observation or arbitrary neighboring subscriber traffic.

Fields decoded from captured bytes by TShark. TLS application-data records and QUIC may carry encrypted payloads; metadata is not plaintext content. No keys or decryption service are supplied. A PCAPNG file can itself contain embedded decryption secrets; any resulting dissection is attributed to the input and TShark, not invented by this tool.

Captured-frame truncations: 17

Malformed dissections: none detected

DNS name decoder diagnostics: []

TLS application-data record frames: 12

That count includes TLS 1.3 opaque outer record type 23; it does not identify the encrypted inner content type.

## Decoded names and HTTP metadata

These are values in packet bytes, not DNS/network lookups performed during analysis.

- dns_query_names: `["example.test"]`
- tls_sni_names: `["example.test"]`
- http_request_methods: `{"GET": 1}`
- http_response_codes: `{"200": 1}`

## Decoder issues

No command errors. Frame-level expert messages remain in `packet_fields.csv`.

Absolute capture times are source-provided; this report does not establish synchronization with another device or radio log.
