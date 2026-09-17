# Android R21 packet paging validation — 2026-09-17

Final APK: `output/android/aTOMos-Radio-3.6.1.21-debug.apk`

SHA-256: `8527bbcf4aba99e493988eaf50152fed8e3503199b949d740f0dd48a1f3b46d4`

Build, test APK build and lint passed. **29 instrumentation tests passed** in 6.777 seconds on the API 36.1 emulator. Lint reports **0 errors and 27 warnings**. This remains a debug-signed prototype, package `org.atomos.radio`, version code 21; the signing key is unchanged. `validation.json` binds the APK, source files and screenshots by SHA-256.

The test suite covers the existing journal, protocol decoding, readable presentation and radio-session review, plus eight packet-paging tests and two asynchronous request-generation tests. New checks cover three pages without overlap, global late DNS and raw-preview search, protocol filters, changed-source rejection and explicit repinning, source change during inspection, invalid arguments and out-of-range offsets, malformed capture prefixes, interruption, the exact 100,000-packet scan bound, stale query completion and destroyed/recreated browser instances. Full output is in `instrumentation-final.txt`.

## Final native UI verification

The public synthetic fixture `examples/packets/synthetic_paging_750.pcap` has 750 frames: 500 UDP and 250 TCP. Its SHA-256 is `7ebe2e1962ea5e5d6e2fe93ba37234bd9ecc1456853c4be131e8d58cc5ab1325`.

- Installed in place using `adb install -r`. Both previous imported synthetic captures remained byte-identical, each with SHA-256 `a5fa3a30136a0404da19c047a2e40bef823719a3def7bad77357c3733ba56754`. All five prior synthetic session files remained present. Nothing was uninstalled.
- Re-reviewed a capture imported in R20 and opened its new raw-file browser successfully.
- Imported the 750-frame fixture through Android's document picker. The copied raw bytes retained the fixture SHA-256.
- Browsed UDP matches 1–200, 201–400 and 401–500. The first visible frame indices were 1, 301 and 601. Next was disabled on the final page; Previous returned to matches 201–400.
- The DNS filter found both late records, global frame indices 452 and 749. Searching `page0749.example.test` found frame 749 even though it is absent from the summary's first 200 details.
- Opened frame 749's readable detail: endpoints, exact capture timestamp, 39 captured UDP payload bytes, DNS question and escaped raw payload were present.
- Rotated between portrait and landscape. The selected page, protocol and search survived recreation. The landscape header places related controls on shared rows, leaving the list and navigation visible.
- Inspected the four final screenshots visually. They contain only synthetic addresses, fixture DNS names and emulator information.
- The Android crash buffer was empty. No radio recording was started for these paging checks. The emulator was shut down after validation.

Screenshots: `emulator-page3.png`, `emulator-page3-landscape.png`, `emulator-global-dns.png`, `emulator-late-dns-detail.png`.

## Scope

Pages retain at most 200 matching packet details and scan the imported raw file again. Filters and case-insensitive search apply to all inspected packets' decoded metadata and bounded previews. A count from a truncated/limited scan describes its inspected prefix; it does not imply that the unseen tail has no matches. The file remains limited to 64 MiB and inspection to 100,000 packets; the existing decode and payload-preview limits remain explicit.

Summary JSON export retains the legacy first-200 detail behavior; the browser's pages no longer depend on that summary. File SHA-256 is checked before and after a page scan and against the pinned source. Search requests are interrupted and generation-checked; a stale callback cannot update a newer page or a destroyed activity.

This directory contains synthetic emulator evidence only. The root task owns physical POCO testing and its separate sanitized report. No physical phone was operated by this agent. No physical USB OTG drive or radio adapter was tested; the supported USB workflow remains capture-file import through Android's document provider.
