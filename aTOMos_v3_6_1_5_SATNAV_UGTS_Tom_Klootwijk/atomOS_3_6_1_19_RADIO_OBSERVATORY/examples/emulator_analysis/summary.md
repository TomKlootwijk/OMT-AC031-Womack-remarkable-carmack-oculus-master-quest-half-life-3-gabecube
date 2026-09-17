# aTOMos R19 radio study

Data origin: **input_capture_as_supplied**.

Study label: ANDROID EMULATOR: synthetic radio values

Android-reported scalar radio power and quality with acquisition metadata; no carrier IQ/phase, range, location or inferred handover.

Input: 19538 bytes; SHA256 `eb1575e1261f8eb5a06215726c4e23b80c300c7241992f01a59039baee40ed45`.

45 JSONL lines, 0 invalid rows, 14 radio records. Final line unterminated: False.

| Observation status | Records |
|---|---:|
| unique_timestamped_observation | 14 |

Counts describe records and cache equivalence, not statistically independent samples.

Stale study policy: age > 30 s; 1 records meet that policy. They remain in the export.

## Metric groups

Only unambiguous unique timestamped observations enter these descriptive groups.

Each row is one link, session and elapsed-clock segment; RSSNR source unit profiles remain separate.

| Link / session / clock | Kind / RAT | Source field | Unit | Count | Min | Max | Mean |
|---|---|---|---|---:|---:|---:|---:|
| sub None, nci=100500 / 57f6e967 / 0 | cell / NR | dbm | dBm | 10 | -126 | -44 | -85.7 |
| sub None, nci=100500 / 57f6e967 / 0 | cell / NR | ss_rsrp_dbm | dBm | 10 | -126 | -44 | -85.7 |
| AP 00:13:10:85:fe:01 @ 2447 MHz / 57f6e967 / 0 | wifi / WIFI | rssi_dbm | dBm | 4 | -50 | -50 | -50 |

## Event and distinct-observation rates

Counts divided by the covered receipt interval, separately for each session and clock segment. These rates do not specify RF sample rate or statistical independence.

- {"accepted_sequence_events":45,"clock_segment":0,"covered_seconds":"88.608357673","first_received_elapsed_ns":"650035146515","last_received_elapsed_ns":"738643504188","radio_event_records":14,"radio_records_per_covered_second":"0.1579986399439379664576079271","session_id":"57f6e967-c4c2-4a94-858a-c3464dd1c7a7","unique_observations_per_covered_second":"0.1579986399439379664576079271","unique_timestamped_observations":14}

## Sessions

- {"accepted_sequence_rows":45,"clock_discontinuities":0,"clock_segments":1,"lifecycle_issues":0,"rows":45,"sequence_issues":0,"session_end_lines":[45],"session_id":"57f6e967-c4c2-4a94-858a-c3464dd1c7a7","session_start_lines":[1],"structurally_complete":true}

## Status and markers

- Line 1 / session: `{"android_release":"16","android_sdk":36,"app":"aTOMos Radio","app_version":"3.6.1.19","cell_request_interval_ms":10000,"clock":{"received_elapsed_ns":"monotonic time since boot, includes sleep; decimal string","received_unix_ms":"wall clock; may jump, not atomic-clock synchronized","source_elapsed_ns":"reported last-seen/modem time since boot; not RF sample time"},"complex_csi_available":false,"device_manufacturer":"Google","device_model":"sdk_gphone64_x86_64","metric_units":{"lte_rssnr_api_unit":"dB","nr_power":"dBm","nr_quality":"dB","wifi_rssi_dbm":"dBm"},"permissions":{"coarse_location":true,"fine_location":true,"notifications":true,"phone_state":false},"raw_waveform_available":false,"signal_type":"reported_power_quality","wifi_request_interval_ms":35000}`
- Line 2 / status: `{"code":"session_started","details":{},"message":"Recording locally; stop before exporting"}`
- Line 3 / status: `{"code":"wifi_results","details":{"batch_id":1,"count":1,"origin":"initial_cache","results_updated":null},"message":"Wi-Fi: 1 AP observations"}`
- Line 5 / status: `{"code":"cell_listener_error","details":{"message":"listen","type":"SecurityException"},"message":"Cell callback unavailable; requests remain enabled"}`
- Line 6 / status: `{"code":"cell_results","details":{"count":1,"origin":"initial_cache","subscription_id":-1},"message":"Cellular: 1 observations"}`
- Line 8 / status: `{"code":"heartbeat","details":{"elapsed_since_start_ms":91,"location_enabled":true,"permissions":{"coarse_location":true,"fine_location":true,"notifications":true,"phone_state":false}},"message":"Recording · Wi-Fi 1 · cellular 1"}`
- Line 9 / status: `{"code":"wifi_scan_requested","details":{"accepted":true,"wifi_enabled":true},"message":"Wi-Fi scan requested"}`
- Line 10 / status: `{"code":"cell_results","details":{"count":1,"origin":"request","subscription_id":-1},"message":"Cellular: 1 observations"}`
- Line 12 / status: `{"code":"wifi_results","details":{"batch_id":2,"count":1,"origin":"broadcast","results_updated":true},"message":"Wi-Fi: 1 AP observations"}`
- Line 14 / status: `{"code":"heartbeat","details":{"elapsed_since_start_ms":10104,"location_enabled":true,"permissions":{"coarse_location":true,"fine_location":true,"notifications":true,"phone_state":false}},"message":"Recording · Wi-Fi 2 · cellular 2"}`
- Line 15 / status: `{"code":"cell_results","details":{"count":1,"origin":"request","subscription_id":-1},"message":"Cellular: 1 observations"}`
- Line 17 / status: `{"code":"heartbeat","details":{"elapsed_since_start_ms":20108,"location_enabled":true,"permissions":{"coarse_location":true,"fine_location":true,"notifications":true,"phone_state":false}},"message":"Recording · Wi-Fi 2 · cellular 3"}`
- Line 18 / status: `{"code":"cell_results","details":{"count":1,"origin":"request","subscription_id":-1},"message":"Cellular: 1 observations"}`
- Line 20 / status: `{"code":"heartbeat","details":{"elapsed_since_start_ms":30113,"location_enabled":true,"permissions":{"coarse_location":true,"fine_location":true,"notifications":true,"phone_state":false}},"message":"Recording · Wi-Fi 2 · cellular 4"}`
- Line 21 / status: `{"code":"cell_results","details":{"count":1,"origin":"request","subscription_id":-1},"message":"Cellular: 1 observations"}`
- Line 23 / status: `{"code":"wifi_scan_requested","details":{"accepted":true,"wifi_enabled":true},"message":"Wi-Fi scan requested"}`
- Line 24 / status: `{"code":"wifi_results","details":{"batch_id":3,"count":1,"origin":"broadcast","results_updated":true},"message":"Wi-Fi: 1 AP observations"}`
- Line 26 / status: `{"code":"heartbeat","details":{"elapsed_since_start_ms":40121,"location_enabled":true,"permissions":{"coarse_location":true,"fine_location":true,"notifications":true,"phone_state":false}},"message":"Recording · Wi-Fi 3 · cellular 5"}`
- Line 27 / status: `{"code":"cell_results","details":{"count":1,"origin":"request","subscription_id":-1},"message":"Cellular: 1 observations"}`
- Line 29 / status: `{"code":"heartbeat","details":{"elapsed_since_start_ms":50128,"location_enabled":true,"permissions":{"coarse_location":true,"fine_location":true,"notifications":true,"phone_state":false}},"message":"Recording · Wi-Fi 3 · cellular 6"}`
- Line 30 / status: `{"code":"cell_results","details":{"count":1,"origin":"request","subscription_id":-1},"message":"Cellular: 1 observations"}`
- Line 32 / status: `{"code":"heartbeat","details":{"elapsed_since_start_ms":60132,"location_enabled":true,"permissions":{"coarse_location":true,"fine_location":true,"notifications":true,"phone_state":false}},"message":"Recording · Wi-Fi 3 · cellular 7"}`
- Line 33 / status: `{"code":"cell_results","details":{"count":1,"origin":"request","subscription_id":-1},"message":"Cellular: 1 observations"}`
- Line 35 / status: `{"code":"heartbeat","details":{"elapsed_since_start_ms":70136,"location_enabled":true,"permissions":{"coarse_location":true,"fine_location":true,"notifications":true,"phone_state":false}},"message":"Recording · Wi-Fi 3 · cellular 8"}`
- Line 36 / status: `{"code":"cell_results","details":{"count":1,"origin":"request","subscription_id":-1},"message":"Cellular: 1 observations"}`
- Line 38 / status: `{"code":"wifi_scan_requested","details":{"accepted":true,"wifi_enabled":true},"message":"Wi-Fi scan requested"}`
- Line 39 / status: `{"code":"wifi_results","details":{"batch_id":4,"count":1,"origin":"broadcast","results_updated":true},"message":"Wi-Fi: 1 AP observations"}`
- Line 41 / status: `{"code":"heartbeat","details":{"elapsed_since_start_ms":80140,"location_enabled":true,"permissions":{"coarse_location":true,"fine_location":true,"notifications":true,"phone_state":false}},"message":"Recording · Wi-Fi 4 · cellular 9"}`
- Line 42 / status: `{"code":"cell_results","details":{"count":1,"origin":"request","subscription_id":-1},"message":"Cellular: 1 observations"}`
- Line 44 / marker: `{"text":"EMULATOR_fixture_markert"}`
- Line 45 / session_end: `{"counts_before_end":{"cell":10,"marker":1,"session":1,"status":28,"wifi":4},"reason":"user_stop"}`

## Input and clock issues

None detected.

## Outputs

`source_original.jsonl` and `source_original.aradbp` retain the original bytes. The bit-plane archive is a reversible permutation with length and SHA256, not compression. `normalized.csv` keeps raw JSON beside each scalar metric; unknown metrics keep unknown units.

Plots use elapsed time from each session/clock segment's first received record. Source timestamps identify Wi-Fi last-seen or modem-reported receipt time. Missing/invalid source timestamps use a separately labeled receipt-time marker. No interpolation between records is drawn.
