# aTOMos 3.6.1.21
## Packet paging and source identity

Tom Klootwijk | 17 September 2026 | ATOMOS-PACKET-PAGING-R1

R21 extends the Radio Packet Studio with bounded pages over an ordered capture. The phone now reaches records beyond the former first-200-detail window. Protocol and text filters select from the inspected stream before pagination. The desktop UDP report gains explicit offset and page-size controls. The exact mathematical core and radio observation model remain unchanged.

## Ordered selection

Let B be the original capture bytes and H(B) their SHA-256 digest. Parsing visits packet records p_i in container order. The record index i is one-based; the result offset o is zero-based. Unsupported or malformed records retain the decoder's existing status and issue semantics.

```
S_F(B) = [p_i in visited order : F(p_i) = true]
M = length(S_F(B))
P(B,F,o,n) = S_F(B)[o : min(o+n,M)]
0 <= o,  1 <= n <= 200
next_exists = o + length(P) < M
```

Here F combines a supported protocol label with a case-insensitive text match over exposed packet metadata and bounded UDP previews. The phone applies F before discarding non-page rows. Text search does not inspect encrypted plaintext or every raw payload byte. The desktop page predicate is UDP; its offset is counted among UDP matches.

## Coverage and completeness

M counts matches in the inspected prefix. It is a whole-file count only when the container scan completes and the source stays unchanged. A parse stop or resource limit must remain visible with its status. Completing a scan does not imply every protocol has been decoded. An empty page past M is valid and must not fabricate rows.

For a fixed B and F, consecutive pages at offsets 0, n, 2n and so on partition S_F(B): every selected record appears once and the original ordering is preserved. This is an exact property of indexing over a defined sequence, independent of sensor accuracy or floating-point propagation.

<!-- page -->
# Execution contract
## Bind a page to its capture

A page is meaningful only together with the source digest, filter, query and offset. The phone checks its expected digest against the current file and checks the file again after inspection. A changed source invalidates the result. The browser requires an explicit reload of the changed source before presenting new pages.

```
Q = (H(B), protocol, text_query, offset, page_size)
valid(Q) => source digest before = source digest after
accept(result_g) <=> g = latest_requested_generation
```

The digest check detects changed bytes with cryptographic collision resistance; it is not a digital signature or a substitute for origin authentication. A successful page retains the decoder's integer timestamp fields and exact rational timestamp representation. Paging never rounds or synthesizes packet bytes.

## Bounded execution

| Item | R21 contract |
| --- | --- |
| Phone scan | At most 64 MiB input, 100,000 visited packets and the inherited container limits. |
| Page retention | At most 200 selected packet details. Aggregate counters and issues retain their existing caps. |
| Search | Applies to every visited record; details outside the selected page are discarded. |
| Repeated requests | A background worker scans the capture for each page; memory stays bounded, work scales with the inspected input. |
| Lifecycle | Debounced text input, request generations and interruption checks prevent stale results replacing the current query. |
| Desktop | --udp-offset and --udp-limit select readable UDP rows from TShark's inspected frame prefix; each run records the source digest. |

This release uses rescanning rather than a persistent index. It makes late records accessible without retaining every packet object in the phone UI. It does not establish a speed advantage over Wireshark or a throughput bound for maximum-size captures.

<!-- page -->
# Verification and use
## Reproducible paging evidence

The shared synthetic capture contains 750 frames: 500 UDP and 250 TCP. DNS records at frames 452 and 749 occur after the old detail window. Three UDP pages contain 200, 200 and 100 records. Tests check ordering, page boundaries, source identity, late matches and empty results. Additional phone checks cover source changes, cancellation and supported container variants; the release's review files report the checks actually executed.

The original ten packet fixtures remain available for timestamp, container, malformed input and protocol regression checks. Their bytes are unchanged. Public examples use synthetic addresses and payloads. Physical sessions and their identifying derivatives remain outside the release package.

## Phone and desktop workflow

On the phone, open Packet study, select an imported capture, and open the packet browser. Choose a protocol or enter search text, then use Previous and Next. The match count describes the current inspected capture; the status identifies incomplete inspection. Changing filters starts again at the first result.

```
python tools/study_packets.py private/capture.pcap
  private/page_3 --udp-offset 400 --udp-limit 200
```

Run that command on one line, with a new or empty output directory. The resulting udp_readable.md and udp_previews.json contain the selected page; packet fields and the original capture remain available for deeper desktop study.

## Continuity of the formalization

The following 117 pages retain R20 and its prior mathematical foundation. Their page text, content streams and rendered pixels are checked against the hash-bound parent. R21 changes access to recorded observations, not the physical measurement equations, ASA/NA/JK operators, bit-plane archive or calibration claims.

The application continues to capture radio measurements through Android and launch PCAPdroid separately for this phone's routed traffic. Downloads and mounted USB storage use the Android document picker. Protocol reassembly and broader dissection remain available in the desktop TShark workflow. This profile introduces no additional radio hardware interface or decryption model.

The editable source, APK, test transcripts, source pins and PDF review accompany this version. R21 validation and any device deployment status are recorded in VERSION.json and review/; inherited R20 device evidence is not counted as a new deployment.
