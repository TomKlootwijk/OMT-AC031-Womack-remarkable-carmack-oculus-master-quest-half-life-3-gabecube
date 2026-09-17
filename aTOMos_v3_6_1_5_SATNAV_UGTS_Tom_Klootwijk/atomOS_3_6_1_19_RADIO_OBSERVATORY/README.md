# aTOMos 3.6.1.19 - Radio Observatory

An Android Wi-Fi/cellular logger and desktop study tools for reported radio
power, quality and identity. Designed for the POCO X7 Pro; physical handset
field availability is established by its exported sessions. This is a new
acquisition layer beside the unchanged R18 kernel.

## Install and record

1. Copy `output/android/aTOMos-Radio-3.6.1.19-debug.apk` to the phone and open it.
   Allow installation from the file application when Android asks. This is an
   internally signed development build, not a Play Store release.
2. Open **aTOMos Radio**, enable Wi-Fi and Android Location, and press
   **Start session**. Grant precise location for radio results. Phone permission
   adds subscription context; notification permission displays the session.
3. Add notes such as `stationary by window` or `moved to hallway` using
   **Add timestamped note**. The foreground service records while the screen
   is off and holds a CPU wake lock while active; stop it when finished.
4. Press **Stop & save**, choose the session, then **Export selected JSONL**.
   Save through the Android document picker and copy the file to the computer.
   Export sessions you want to retain before uninstalling the app.

The app stores sessions locally and has no Internet permission or upload
function. It collects no GPS coordinates. Precise location permission is an
Android requirement for the Wi-Fi/cell observation APIs. A visible service
does not guarantee constant sampling or immunity to vendor power management.
The default requests are about 35 seconds apart for Wi-Fi and 10 seconds
for cellular; actual report times and request failures are retained.

## What is recorded

- Wi-Fi: SSID, BSSID, frequency, channel width, RSSI, advertised capabilities,
  source timestamp, batch and completion status.
- Cellular: reported serving/neighbor cells, RAT and subscription context,
  available identity/channel fields and individual power/quality measurements.
  NR SS/CSI RSRP, RSRQ and SINR are scalar reports, not complex CSI samples.
- Session identity, sequence, monotonic receipt/source clocks, wall time,
  experiment markers, permission/request errors and an orderly end record.

LTE RSSNR uses explicit API-version units: Android 10 tenths of dB;
Android 11 onward whole dB. Unknown metrics remain null. Missing NR records
do not prove no 5G signal is present. AP BSSIDs and cellular cell identities
do not enumerate nearby subscriber devices. This build records radio reports;
it does not capture raw IQ, packet payloads or perform LAN endpoint discovery.

## Study an export

Run these commands from this release directory with Python 3.10 or later:

```powershell
python -m pip install -r requirements-study.txt
python tools/study_radio.py study sessions/my_capture.jsonl output/study/my_capture
```

Choose a new or empty output directory; existing results are protected.
Use `--no-plots` to run without matplotlib. The analysis keeps the original
input, produces normalized CSV, JSON/Markdown summaries and signal-time plots.
Read the quality/issues report first: repeated cached observations, missing
values, sequence defects and wall-clock changes are separate from signal
changes. Per-metric summary means are in the stored dB/dBm domain, not linear
power averages. No automatic distance/position/phase estimate is produced.

The supplied fixture is synthetic and can be studied before any phone capture:

```powershell
python tools/study_radio.py study examples/synthetic_radio.jsonl output/study/synthetic
```

## Literal one-bit-plane archive

```powershell
python tools/study_radio.py pack sessions/my_capture.jsonl sessions/my_capture.aradbp
python tools/study_radio.py unpack sessions/my_capture.aradbp sessions/restored.jsonl
```

ARADBP1 transposes 64 x 64-bit words per 512-byte block, stores the original
length and SHA-256, and restores the exact original bytes. This is reversible
packing, not compression or an improvement in sensor accuracy. Parsing and
validation remain separate from archival. Never overwrite the only copy of a
capture; keep originals outside the source tree's public release artifacts.

## Build and validate

Android uses the checked Gradle wrapper and standard framework APIs. The
Windows build helper is `tools/build_android.ps1`; SDK 36 and JDK 17+ are
required. The source also builds with `android/gradlew.bat assembleDebug` when
`ANDROID_HOME` is set. No physical handset is automatically installed or scanned
by the desktop build.

```powershell
python -m unittest discover -s tests -v
python tools/build_pdf.py
```

The PDF builder needs `requirements-document.txt`, Calibri/Consolas or DejaVu
fonts, and the bundled hash-bound `source/parent_R18.pdf` (or adjacent R18 release). The resulting full 110-page
PDF contains seven new pages and all 103 reviewed R18 pages. Edit
`formal/RADIO_OBSERVATION_PROFILE.md` to change the supplement.

The delivered build passes 27 Python tests and three Android instrumentation
tests. Final emulator recording and document-picker export were verified;
the 50-event export passed desktop/schema validation and archived/restored
byte-for-byte. Android lint reports zero errors and seven nonblocking warnings.

Review evidence distinguishes unit/CLI tests, synthetic fixtures, emulator
lifecycle/export checks and physical-phone measurements. See `VERSION.json`
and `review/` for the final verified scope. The current release does not lower
these radio records into native ASA/NA/JK feedback or run CUDA on Android.
