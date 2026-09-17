# Android R20 validation — 2026-09-17

This directory contains **synthetic packet fixtures and Android emulator radio data only**. Physical POCO captures and derived identifying data are not part of these artifacts.

## Current UDP browser artifact

The completed R20 artifact includes the later user-requested human-readable UDP browser and clearer background/USB-storage workflow. Its APK SHA-256 is `b683df8e4a42ffed00302f46ca0caa4d6a85fa4502ab3f936196c3258fa90c26`; **19 instrumentation tests passed**. The APK is 290,404 bytes; final lint has **0 errors and 22 warnings**. See `UDP_VALIDATION.md` and `instrumentation-udp-final.txt` for the final artifact's evidence. The initial R20 checks below describe the preceding validated build, whose acquisition behavior is unchanged by the UDP UI extension.

## Initial R20 artifact

`output/android/aTOMos-Radio-3.6.1.20-debug.apk`, 267,604 bytes.

SHA-256: `193913324330442eedf2fec5c180ed74ba59f5353a521fa7f225b221a0b1eeff`

Gradle wrapper 8.13 / Android Gradle Plugin 8.10.0 / Android SDK 36. Build targets `assembleDebug`, `assembleDebugAndroidTest` and `lintDebug` passed. Lint: **0 errors, 16 warnings**, concerning English-only UI strings/tooling/style. APK remains a debug-signed, debuggable prototype with package `org.atomos.radio`, version code 20.

Installed over R19 using `adb install -r` on the API 36.1 emulator. All three existing R19 synthetic sessions remained present; the application was never uninstalled.

## Instrumentation

`instrumentation-final.txt`: **14 tests passed** against the initial R20 APK identified above.

- 3 journal/representation tests: unavailable-value sentinels, valid 36-bit NCI, timestamp units/unknowns, concurrent record ordering, UTF-8 and closed-session behavior.
- 9 decoder tests: Wi-Fi SSID/rates/RSN, malformed and unknown IEs; PCAP endian and micro/nanosecond variants; VLAN and unsupported links; PCAPNG sections/interfaces/time resolutions/offsets; fractional nanosecond rational preservation; DNS pointer loops; truncated files; HTTP/TLS/fragment boundaries; bounded packet detail retention.
- 2 native session review tests: old cached Wi-Fi observations separated from recent reports, repeated source-time indicators, partial lines, missing timestamps and null signal values.

TLS record headers are not treated as proof that the payload is unencrypted. Payloads remain opaque; no decryption or reassembly is claimed.

## Initial R20 UI and acquisition smoke

1. Imported `examples/packets/synthetic_ethernet.pcap` through Android's document picker. The original source and private imported bytes have identical SHA-256 `a5fa3a30136a0404da19c047a2e40bef823719a3def7bad77357c3733ba56754` (1,497 bytes).
2. Native packet review displayed 17 visited packets, including DNS 3 / HTTP 2 / TLS 2 and explicitly 1 unsupported, 1 malformed and 1 truncated packet. The fixture deliberately contains these cases. The UI says **Container scan finished**, not that every payload was decoded.
3. Exported the final decoded report through the Storage Access Framework. Private report and exported bytes match SHA-256 `323f839c05d8e9487638e9472e26c002b4a059c4407e48c7ff9e6fe6503dbd1a` (20,137 bytes). Saved as `emulator-packet-report.json`.
4. Started and stopped a new radio session on the final APK. `emulator-radio-session.jsonl` is the UTF-8 extraction of that emulator journal: 27 records (1 session, 15 status, 2 Wi-Fi, 8 cellular, 1 session_end).
5. Confirmed raw SSID bytes, seven exposed Wi-Fi IEs with raw Base64 and decoded/unsupported annotations, and this emulator's own link/IP/DNS/route context. No active probing occurs.
6. Opened the native session review. It reported 9 recent radio rows and 1 older cached row using the explicit **30-second source-age threshold**, preserved the full log, and excluded the old cache value from the recent trend.
7. Inspected `emulator-packets.png` and `emulator-study.png` visually. Text, statistics, buttons and signal trend were readable. No AndroidRuntime crash was reported. Recording was stopped and only the emulator launched for this validation was shut down.

The signal and network-context values here come from the emulator, not measured real radio conditions. Root-thread physical-phone verification is documented separately. The included `emulator-packet-report.json`, `emulator-packets.png`, `emulator-study.png` and radio journal belong to the initial R20 artifact identified above. Current UDP-browser screenshots are identified in `UDP_VALIDATION.md`.
