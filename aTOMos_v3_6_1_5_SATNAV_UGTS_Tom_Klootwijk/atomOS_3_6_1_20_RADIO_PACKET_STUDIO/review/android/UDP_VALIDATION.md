# Final R20 UDP browser validation — 2026-09-17

APK: `output/android/aTOMos-Radio-3.6.1.20-debug.apk`

SHA-256: `b683df8e4a42ffed00302f46ca0caa4d6a85fa4502ab3f936196c3258fa90c26`

Build, Android test APK build and lint passed. The package and signing key remain unchanged; installation used `adb install -r`, preserving the existing emulator sessions and imported capture files. `instrumentation-udp-final.txt` records **19 passing tests**: 12 decoder, 3 journal, 2 session review and 2 human-readable presentation tests. The new cases cover bounded UDP byte previews and escaping, truncation, exact NTP fields, DHCP option boundaries, DNS inclusion in UDP filters, IPv6 address/port formatting, exact human-readable capture timestamps and raw-byte hex presentation.

Native UI checks on the API 36.1 emulator:

- Started a radio foreground session, then opened Packet Studio. The background status showed the running radio logger and its increasing counters.
- Reviewed an already imported synthetic PCAP. The report was regenerated with the current decoder, making the new UDP fields available without reimporting or modifying the original capture.
- Opened **Browse packets**. The default UDP filter showed four matching packets out of seventeen retained/scanned fixture packets, including three DNS packets carried over UDP. The first-200-detail limit is explicit in the browser.
- Opened a DNS query. Its readable view showed IPv4 endpoints and ports, exact UTC capture time, declared/captured lengths, checksum field with verification status, the DNS question and A-record type, and escaped original payload bytes.
- Opened **Payload hex** and inspected the exact 30 captured DNS payload bytes. No decryption is claimed.
- Confirmed the imported PCAP SHA remained `a5fa3a30136a0404da19c047a2e40bef823719a3def7bad77357c3733ba56754`.
- Confirmed the radio service remained foreground while reviewing packets. Returning to the recorder showed counts advancing from 1 Wi-Fi / 4 cellular to 4 Wi-Fi / 32 cellular observations. Stopped the recording and shut down only the emulator used for validation.
- No AndroidRuntime crash was reported. `emulator-udp-browser.png` and `emulator-udp-detail.png` were inspected visually; both contain only public synthetic addresses and fixture data.

USB OTG support is **capture-file import through Android's Storage Access Framework**, using a mounted drive exposed by a document provider. The same import path was tested with Downloads; no physical OTG storage device was attached for this agent's tests. Direct USB radio-adapter capture is not implemented or claimed. PCAPdroid remains the separate user-started phone-traffic capture application; this app's radio logger remains a separate explicit foreground session.

Physical POCO verification is performed and documented by the root task, separately from these synthetic emulator artifacts.
