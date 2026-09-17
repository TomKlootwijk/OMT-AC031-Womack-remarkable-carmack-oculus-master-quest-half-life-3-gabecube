# aTOMos Radio for Android

Native Java application, Android 10 / API 29 or newer. Build targets API 36. No account, network permission, upload service, native binary or third-party runtime library is included.

## Record

1. Install `../output/android/aTOMos-Radio-3.6.1.19-debug.apk`.
2. Enable Wi-Fi and Android Location. Start a session and allow **precise location**. Android requires this permission for Wi-Fi/cell observations; the app does not collect GPS positions. Phone permission is optional and enables subscription labels. Notification permission makes the ongoing status visible in the notification drawer.
3. Start a session. The foreground service requests Wi-Fi scans every 35 seconds and cell information every 10 seconds. Android/modem throttling and cached results still apply. A renewable partial wake lock keeps sampling scheduled while the screen is off; system/OEM interruptions remain visible as gaps or an unterminated log.
4. Add text markers during experiments. **Stop & save**, select a saved session, then **Export selected JSONL**. Android's document picker lets you choose the destination. Active logs cannot be exported; interrupted logs are explicitly labelled and retained.

The Wi-Fi count is the number of recorded AP observations, including repeated cached results. The cellular count likewise includes callbacks/cache/request results. Neither number is a count of independent measurements or unique devices. Wi-Fi BSSID identifies an observed AP interface. Cell identities identify reported cells, not subscribers. The current logger collects reported power/quality fields, not I/Q, complex channel state, audio or GPS coordinates.

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
