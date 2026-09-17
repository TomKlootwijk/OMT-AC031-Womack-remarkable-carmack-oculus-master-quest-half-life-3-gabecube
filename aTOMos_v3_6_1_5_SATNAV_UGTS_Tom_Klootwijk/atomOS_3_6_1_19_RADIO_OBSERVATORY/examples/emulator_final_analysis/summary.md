# aTOMos R19 radio study

Data origin: **input_capture_as_supplied**.

Study label: ANDROID EMULATOR: final APK synthetic radio values

Android-reported scalar radio power and quality with acquisition metadata; no carrier IQ/phase, range, location or inferred handover.

Input: 22871 bytes; SHA256 `01cab1d5b6de8967171f6899f2e6b80537ada2d841a9794cd02aaf7af4725f38`.

50 JSONL lines, 0 invalid rows, 20 radio records. Final line unterminated: False.

| Observation status | Records |
|---|---:|
| cached_duplicate | 5 |
| unique_timestamped_observation | 15 |

Counts describe records and cache equivalence, not statistically independent samples.

Stale study policy: age > 30 s; 0 records meet that policy. They remain in the export.

## Metric groups

Only unambiguous unique timestamped observations enter these descriptive groups.

Each row is one link, session and elapsed-clock segment; RSSNR source unit profiles remain separate.

| Link / session / clock | Kind / RAT | Source field | Unit | Count | Min | Max | Mean |
|---|---|---|---|---:|---:|---:|---:|
| sub 1, nci=100500 / 988d445c / 0 | cell / NR | dbm | dBm | 11 | -121 | -97 | -108.0909090909090909090909091 |
| sub None, nci=100500 / 988d445c / 0 | cell / NR | dbm | dBm | 1 | -97 | -97 | -97 |
| sub 1, nci=100500 / 988d445c / 0 | cell / NR | ss_rsrp_dbm | dBm | 11 | -121 | -97 | -108.0909090909090909090909091 |
| sub None, nci=100500 / 988d445c / 0 | cell / NR | ss_rsrp_dbm | dBm | 1 | -97 | -97 | -97 |
| AP 00:13:10:85:fe:01 @ 2447 MHz / 988d445c / 0 | wifi / WIFI | rssi_dbm | dBm | 3 | -50 | -50 | -50 |

## Event and distinct-observation rates

Counts divided by the covered receipt interval, separately for each session and clock segment. These rates do not specify RF sample rate or statistical independence.

- {"accepted_sequence_events":50,"clock_segment":0,"covered_seconds":"44.290282122","first_received_elapsed_ns":"985862587496","last_received_elapsed_ns":"1030152869618","radio_event_records":20,"radio_records_per_covered_second":"0.4515663265568936354945533304","session_id":"988d445c-690e-4b3e-a54a-fca38f1769d2","unique_observations_per_covered_second":"0.3386747449176702266209149978","unique_timestamped_observations":15}

## Sessions

- {"accepted_sequence_rows":50,"clock_discontinuities":0,"clock_segments":1,"lifecycle_issues":0,"rows":50,"sequence_issues":0,"session_end_lines":[50],"session_id":"988d445c-690e-4b3e-a54a-fca38f1769d2","session_start_lines":[1],"structurally_complete":true}

## Status and markers

- Line 1 / session: `{"android_release":"16","android_sdk":36,"app":"aTOMos Radio","app_version":"3.6.1.19","cell_request_interval_ms":10000,"clock":{"received_elapsed_ns":"monotonic time since boot, includes sleep; decimal string","received_unix_ms":"wall clock; may jump, not atomic-clock synchronized","source_elapsed_ns":"reported last-seen/modem time since boot; not RF sample time"},"complex_csi_available":false,"device_manufacturer":"Google","device_model":"sdk_gphone64_x86_64","metric_units":{"lte_rssnr_api_unit":"dB","nr_power":"dBm","nr_quality":"dB","wifi_rssi_dbm":"dBm"},"permissions":{"coarse_location":true,"fine_location":true,"notifications":true,"phone_state":true},"raw_waveform_available":false,"signal_type":"reported_power_quality","wifi_request_interval_ms":35000}`
- Line 2 / status: `{"code":"session_started","details":{},"message":"Recording locally; stop before exporting"}`
- Line 3 / status: `{"code":"wifi_results","details":{"batch_id":1,"count":1,"origin":"initial_cache","results_updated":null},"message":"Wi-Fi: 1 AP observations"}`
- Line 5 / status: `{"code":"cell_results","details":{"count":1,"origin":"initial_cache","subscription_id":-1},"message":"Cellular: 1 observations"}`
- Line 7 / status: `{"code":"cell_results","details":{"count":1,"origin":"callback","subscription_id":1},"message":"Cellular: 1 observations"}`
- Line 9 / status: `{"code":"heartbeat","details":{"elapsed_since_start_ms":53,"location_enabled":true,"permissions":{"coarse_location":true,"fine_location":true,"notifications":true,"phone_state":true}},"message":"Recording · Wi-Fi 1 · cellular 2"}`
- Line 10 / status: `{"code":"wifi_scan_requested","details":{"accepted":true,"wifi_enabled":true},"message":"Wi-Fi scan requested"}`
- Line 11 / status: `{"code":"cell_results","details":{"count":1,"origin":"callback","subscription_id":1},"message":"Cellular: 1 observations"}`
- Line 13 / status: `{"code":"cell_results","details":{"count":1,"origin":"request","subscription_id":1},"message":"Cellular: 1 observations"}`
- Line 15 / status: `{"code":"cell_results","details":{"count":1,"origin":"callback","subscription_id":1},"message":"Cellular: 1 observations"}`
- Line 17 / status: `{"code":"wifi_results","details":{"batch_id":2,"count":1,"origin":"broadcast","results_updated":true},"message":"Wi-Fi: 1 AP observations"}`
- Line 19 / status: `{"code":"heartbeat","details":{"elapsed_since_start_ms":10060,"location_enabled":true,"permissions":{"coarse_location":true,"fine_location":true,"notifications":true,"phone_state":true}},"message":"Recording · Wi-Fi 2 · cellular 5"}`
- Line 20 / status: `{"code":"cell_results","details":{"count":1,"origin":"callback","subscription_id":1},"message":"Cellular: 1 observations"}`
- Line 22 / status: `{"code":"cell_results","details":{"count":1,"origin":"request","subscription_id":1},"message":"Cellular: 1 observations"}`
- Line 24 / status: `{"code":"cell_results","details":{"count":1,"origin":"callback","subscription_id":1},"message":"Cellular: 1 observations"}`
- Line 26 / status: `{"code":"heartbeat","details":{"elapsed_since_start_ms":20066,"location_enabled":true,"permissions":{"coarse_location":true,"fine_location":true,"notifications":true,"phone_state":true}},"message":"Recording · Wi-Fi 2 · cellular 8"}`
- Line 27 / status: `{"code":"cell_results","details":{"count":1,"origin":"callback","subscription_id":1},"message":"Cellular: 1 observations"}`
- Line 29 / status: `{"code":"cell_results","details":{"count":1,"origin":"request","subscription_id":1},"message":"Cellular: 1 observations"}`
- Line 31 / status: `{"code":"cell_results","details":{"count":1,"origin":"callback","subscription_id":1},"message":"Cellular: 1 observations"}`
- Line 33 / status: `{"code":"heartbeat","details":{"elapsed_since_start_ms":30070,"location_enabled":true,"permissions":{"coarse_location":true,"fine_location":true,"notifications":true,"phone_state":true}},"message":"Recording · Wi-Fi 2 · cellular 11"}`
- Line 34 / status: `{"code":"cell_results","details":{"count":1,"origin":"callback","subscription_id":1},"message":"Cellular: 1 observations"}`
- Line 36 / status: `{"code":"cell_results","details":{"count":1,"origin":"request","subscription_id":1},"message":"Cellular: 1 observations"}`
- Line 38 / status: `{"code":"cell_results","details":{"count":1,"origin":"callback","subscription_id":1},"message":"Cellular: 1 observations"}`
- Line 40 / status: `{"code":"wifi_scan_requested","details":{"accepted":true,"wifi_enabled":true},"message":"Wi-Fi scan requested"}`
- Line 41 / status: `{"code":"wifi_results","details":{"batch_id":3,"count":1,"origin":"broadcast","results_updated":true},"message":"Wi-Fi: 1 AP observations"}`
- Line 43 / status: `{"code":"heartbeat","details":{"elapsed_since_start_ms":40075,"location_enabled":true,"permissions":{"coarse_location":true,"fine_location":true,"notifications":true,"phone_state":true}},"message":"Recording · Wi-Fi 3 · cellular 14"}`
- Line 44 / status: `{"code":"cell_results","details":{"count":1,"origin":"callback","subscription_id":1},"message":"Cellular: 1 observations"}`
- Line 46 / status: `{"code":"cell_results","details":{"count":1,"origin":"request","subscription_id":1},"message":"Cellular: 1 observations"}`
- Line 48 / status: `{"code":"cell_results","details":{"count":1,"origin":"callback","subscription_id":1},"message":"Cellular: 1 observations"}`
- Line 50 / session_end: `{"counts_before_end":{"cell":17,"session":1,"status":28,"wifi":3},"reason":"user_stop"}`

## Input and clock issues

None detected.

## Outputs

`source_original.jsonl` and `source_original.aradbp` retain the original bytes. The bit-plane archive is a reversible permutation with length and SHA256, not compression. `normalized.csv` keeps raw JSON beside each scalar metric; unknown metrics keep unknown units.

Plots use elapsed time from each session/clock segment's first received record. Source timestamps identify Wi-Fi last-seen or modem-reported receipt time. Missing/invalid source timestamps use a separately labeled receipt-time marker. No interpolation between records is drawn.
