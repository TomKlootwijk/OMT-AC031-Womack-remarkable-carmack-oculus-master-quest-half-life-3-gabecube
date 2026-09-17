# Android validation — 2026-09-17

All runtime observations in this directory are **Android emulator synthetic radio data**. No physical handset was installed, configured or sampled during this validation.

## Final artifact

`output/android/aTOMos-Radio-3.6.1.19-debug.apk`

SHA-256: `ce7fa8e104250d30dc926be7df3d115968f294890408caf528a570f68cc3916b`

Built with the checked-in Gradle 8.13 wrapper, Android Gradle Plugin 8.10.0, SDK platform 36 and Android Studio JBR. `assembleDebug`, `assembleDebugAndroidTest` and `lintDebug` passed. Lint reported **0 errors, 7 warnings** (tool version and English-only programmatic UI string localization). APK signature verification passed using v2 signing. This is a debug-signed, debuggable prototype.

The final artifact was installed on `emulator-5554`, Android API 36.1. `instrumentation-final.txt` records **3 passing instrumentation tests** covering unavailable-value sentinels and valid 36-bit NR identities; old/new cell timestamp representation and unknown sentinels; concurrent append ordering, UTF-8 round-trip and closed-session rejection.

## Final artifact runtime smoke

- Start from the native activity with precise location, notification and phone-state permissions.
- Record Wi-Fi and NR observations. The device-wide initial cell cache was read once and emitted with `subscription_id: null` and `subscription_scope: device_wide`. Request/listener observations used subscription 1 with `subscription_scope: query_context`.
- Turn the emulator screen off, retain a foreground location service, then resume. Records continued during screen-off time.
- Stop recording and observe a closed session. Select it in the persistent session list.
- Export through Android's Storage Access Framework document picker to Downloads.
- Compare SHA-256 of the private session and exported file: identical.
- Check AndroidRuntime error log: no crash reported. No foreground recording remained after Stop. The emulator launched for this task was then shut down.

Final exported bytes: `emulator-session-final.jsonl`, **22,871 bytes**, **50 rows**: 1 session, 28 status, 3 Wi-Fi, 17 cellular and 1 session_end.

SHA-256 of both private source and SAF export:
`01cab1d5b6de8967171f6899f2e6b80537ada2d841a9794cd02aaf7af4725f38`

`emulator-final-recording.png` was inspected visually against this APK. It shows the live recording and the retained earlier interrupted session selected in the saved-session picker.

## Earlier build checks

`emulator-session.jsonl` and `emulator-recording.png` belong to the earlier build before the final dual-SIM cache attribution and storage-error handling fixes. They are retained as evidence of the initial UI and broader interaction flow, not represented as final-build captures.

That run tested fresh runtime permission prompts, **denying optional phone-state permission while Wi-Fi/cellular recording continued**, an explicit user marker, screen-off recording, Stop and a byte-identical SAF export. The earlier exported file is 19,538 bytes, SHA-256 `eb1575e1261f8eb5a06215726c4e23b80c300c7241992f01a59039baee40ed45`. It was accepted by the Python study tools.

A second earlier session was deliberately interrupted using force-stop. Relaunch displayed **Interrupted session — missing end record** and retained the data. This also appears in the final screenshot. Export cancellation returned to the application without changing the source log.

## Scope

This validates Android build/install, real framework serialization, UI/service lifecycle and export behavior on an emulator. The radio values are simulated. Actual POCO radio availability, HyperOS background behavior, hardware measurement quality, real dual-SIM modem behavior, API 29 runtime behavior and a forced full-storage failure have not been experimentally validated. The dual-SIM cache attribution and storage-failure paths were reviewed and corrected in source. The final APK has no INTERNET, microphone, camera or background-location permission.
