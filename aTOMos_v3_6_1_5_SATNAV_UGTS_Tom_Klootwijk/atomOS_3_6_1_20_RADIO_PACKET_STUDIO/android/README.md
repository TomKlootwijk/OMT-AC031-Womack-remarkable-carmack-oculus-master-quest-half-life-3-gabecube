# aTOMos Radio + Packet Studio for Android — 3.6.1.20

Native Java application, Android 10 / API 29 or newer. Build targets API 36. No account, Internet permission, upload service, native binary or third-party runtime library is included.

## Record

1. Install `../output/android/aTOMos-Radio-3.6.1.20-debug.apk` as an update. The package and signing key are unchanged; never uninstall to upgrade, because uninstalling deletes private sessions.
2. Enable Wi-Fi and Android Location. Start a session and allow **precise location**. Android requires this permission for Wi-Fi/cell observations; the app does not collect GPS positions. Phone permission is optional and enables subscription labels. Notification permission makes the ongoing status visible in the notification drawer.
3. Start a session. The foreground service requests Wi-Fi scans every 35 seconds and cell information every 10 seconds. Android/modem throttling and cached results still apply. A renewable partial wake lock keeps sampling scheduled while the screen is off; system/OEM interruptions remain visible as gaps or an unterminated log.
4. Add text markers during experiments. **Stop & save**, select a saved session, then **Export selected JSONL**. Android's document picker lets you choose the destination. Active logs cannot be exported; interrupted logs are explicitly labelled and retained.

The Wi-Fi count is the number of recorded AP observations, including repeated cached results. The cellular count likewise includes callbacks/cache/request results. Neither number is a count of independent measurements or unique devices. Wi-Fi BSSID identifies an observed AP interface. Cell identities identify reported cells, not subscribers. The current logger collects reported power/quality fields, not I/Q, complex channel state, audio or GPS coordinates.

## Study on the phone

Choose a saved session, then **Study selected session**. Review total records, duration, observed AP/cell identities, per-entity source age, repeated consecutive source timestamps and recent signal levels. A report counts as recent when its source timestamp is 0–30 seconds old at receipt, matching the desktop default. Old initial scan-cache entries remain in the log but are excluded from the recent trend. The graph uses receipt times and at most 256 retained display points; original journal values are unchanged. Missing values never become zero.

The reviewer streams the file off the UI thread and keeps up to 512 entity summaries, 64 KiB of details per entity and a 1 MiB maximum line. It explicitly reports malformed/unfinished lines and reached limits. Active-session review is a snapshot of the file length at the moment review begins. Use the desktop tools for exhaustive validation and analysis.

**Inspect this phone's current IP / DNS / routes** reads Android-visible link context. Changes are also logged as `status` records with code `network_context`. It does not discover or probe other LAN devices. Android 13+ raw SSID bytes and Android 11+ exposed Wi-Fi information-element bytes are logged in Base64, alongside decoded annotations. These are reported beacon fields, not full captured frames; raw bytes remain authoritative.

## Packet study

Open **Packet study**, then **Capture phone packets · open PCAPdroid**. In PCAPdroid, choose PCAP file output and explicitly start capture, accept Android's VPN prompt, exercise the apps of interest, stop, and export the capture. Return to Packet Studio and **Import PCAP / PCAPNG** using Android's document picker.

Imports up to 64 MiB are copied to private application storage without changing the original bytes. The native decoder reports protocols, endpoint addresses, bounded packet/DNS summaries, encryption boundaries, unknown formats and truncation. Review or export the decoded JSON and export the original capture separately. PCAPdroid handles capture; the aTOMos APK contains no VPN forwarding service and requires no INTERNET permission. Imported captures describe this phone's captured routed traffic, not every nearby transmitter or subscriber. TLS ciphertext is not decrypted.

**Browse packets** opens a native searchable packet list with All / UDP / DNS / TCP / TLS filters. UDP includes DNS transported inside UDP. Tap a packet to read its source/destination IP and port, exact capture timestamp, lengths, DNS questions/answers and any supported NTP or DHCP candidate fields. A bounded 128-byte escaped ASCII/hex view displays original captured UDP bytes; printable bytes do not establish that application content is plaintext. The browser explicitly shows how many of the capture's packets are represented by the first 200 retained detail records. Export the original file for exhaustive desktop analysis. Reviewing a saved capture refreshes its report with the current decoder, so imported captures survive app upgrades and acquire new readable fields.

For background use, start the radio session explicitly and leave its foreground notification running. Start PCAPdroid capture separately; its foreground/VPN service continues while other apps or this studio are open. Each recorder has its own Stop control. Reviewing or importing a saved file does not stop the radio logger.

For USB OTG **storage**, connect and mount the drive, choose **Import capture · Downloads or USB storage**, open the Android document-picker sidebar and choose the drive/file. The same raw-byte preservation applies. This is file import from Android-visible storage, not direct USB radio-adapter capture. Actual USB mounting depends on the attached drive and Android; no OTG device is bundled.

## Build

From PowerShell:

```powershell
..\tools\build_android.ps1 -IncludeTests
```

Pass `-SdkPath` and `-JdkPath` for nondefault installations. Required: Android SDK platform 36, JDK 17+, network access for missing Gradle/build artifacts. The checked-in wrapper pins Gradle 8.13; Android Gradle Plugin is 8.10.0. The build produces a debug-signed, debuggable prototype APK. Preserve the same debug signing key for subsequent in-place updates, or Android will reject a differently signed replacement.

The app is entirely framework-based. The instrumented tests use Android's optional `android.test.runner`/`android.test.base` libraries, with no Maven test dependencies.

```powershell
adb -s emulator-5554 install -r app/build/outputs/apk/debug/app-debug.apk
adb -s emulator-5554 install -r -t app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk
adb -s emulator-5554 shell am instrument -w org.atomos.radio.test/android.test.InstrumentationTestRunner
```

On Windows, copy APKs to a short temporary path first if `adb` reports a missing file despite its existence; some builds do not support long paths.

## Evidence contract

Every JSONL row uses `atomos.radio.v1`. Session UUID + strictly increasing `seq` orders records; elapsed nanoseconds are decimal strings so JavaScript cannot round them. Values unavailable from the API are JSON null. Logs are flushed after each row and fsynced on orderly closure. A final `session_end` means the service closed the journal; missing termination is never silently repaired.

Wi-Fi `ScanResult.timestamp` is microseconds since boot and is converted to a nanosecond string. API 29 cell timestamps retain their reported nanosecond representation; API 30+ uses `getTimestampMillis()` and preserves that millisecond resolution. The raw unknown timestamp sentinel is checked before conversion. Neither timestamp is a sampled RF waveform time.

LTE RSSNR keeps `rssnr_api_raw` and `rssnr_api_unit`. API 29 supplies tenths of dB (`rssnr_tenth_db`); API 30+ supplies dB (`rssnr_db`). This follows AOSP Android 10 versus Android 11 implementations; no magnitude-based unit guessing occurs. NR `csi_*` fields are scalar power/quality metrics, not complex Wi-Fi CSI.

Private app files are excluded from backup and device transfer. The application asks Android for no network access. The user controls where exported copies are stored. Session files are not automatically deleted.
