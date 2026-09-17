# aTOMos R21 packet study

Study label: SYNTHETIC final UDP page of mixed 750-packet fixture

Status: **decoded**. Capture: pcap, 56064 bytes.

Original SHA256: `7ebe2e1962ea5e5d6e2fe93ba37234bd9ecc1456853c4be131e8d58cc5ab1325`.

Decoder: `TShark (Wireshark) 4.6.2 (v4.6.2-0-g24d5e2b5a3dc).`.

Decoded 750 packet rows; packet limit 100000; limit reached: False.

All original bytes remain in `source_original.pcap`. `packet_fields.csv` contains decoded metadata; `protocols_conversations.txt` contains TShark's protocol hierarchy and endpoint conversations.

`udp_readable.md` shows decoded UDP summaries, endpoints and capped ASCII/hex payload previews. `udp_previews.json` keeps the same bounded structured view. UDP page offset 400, limit 200, total decoded UDP matches 500, next offset None.

## Protocols

| Protocol | Frames containing layer |
|---|---:|
| data | 498 |
| dns | 2 |
| eth | 750 |
| ethertype | 750 |
| ip | 750 |
| tcp | 250 |
| udp | 500 |

## Capture interpretation

Offline capture only. Protocol counts may overlap because one frame contains multiple protocol layers. Captured IP traffic is not a radio-power observation or arbitrary neighboring subscriber traffic.

Fields decoded from captured bytes by TShark. TLS application-data records and QUIC may carry encrypted payloads; metadata is not plaintext content. No keys or decryption service are supplied. A PCAPNG file can itself contain embedded decryption secrets; any resulting dissection is attributed to the input and TShark, not invented by this tool.

Captured-frame truncations: none detected

Malformed dissections: none detected

DNS name decoder diagnostics: []

TLS application-data record frames: none decoded

That count includes TLS 1.3 opaque outer record type 23; it does not identify the encrypted inner content type.

## Decoded names and HTTP metadata

These are values in packet bytes, not DNS/network lookups performed during analysis.

- dns_query_names: `["page0452.example.test", "page0749.example.test"]`
- tls_sni_names: `[]`
- http_request_methods: `{}`
- http_response_codes: `{}`

## Decoder issues

No command errors. Frame-level expert messages remain in `packet_fields.csv`.

Absolute capture times are source-provided; this report does not establish synchronization with another device or radio log.
