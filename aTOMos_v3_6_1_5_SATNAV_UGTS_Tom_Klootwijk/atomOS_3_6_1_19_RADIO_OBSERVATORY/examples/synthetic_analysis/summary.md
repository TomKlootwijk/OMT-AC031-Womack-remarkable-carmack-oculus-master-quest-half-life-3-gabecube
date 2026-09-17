# aTOMos R19 radio study

Data origin: **declared_synthetic_fixture**.

Study label: not supplied

Android-reported scalar radio power and quality with acquisition metadata; no carrier IQ/phase, range, location or inferred handover.

Input: 9688 bytes; SHA256 `a856b26dc46fa5a3c93d8de38c087f602df342284d6b162c512281d6338c26cd`.

20 JSONL lines, 0 invalid rows, 12 radio records. Final line unterminated: False.

| Observation status | Records |
|---|---:|
| cached_duplicate | 3 |
| source_timestamp_unavailable_or_invalid | 1 |
| unique_timestamped_observation | 8 |

Counts describe records and cache equivalence, not statistically independent samples.

Stale study policy: age > 30 s; 1 records meet that policy. They remain in the export.

## Metric groups

Only unambiguous unique timestamped observations enter these descriptive groups.

Each row is one link, session and elapsed-clock segment; RSSNR source unit profiles remain separate.

| Link / session / clock | Kind / RAT | Source field | Unit | Count | Min | Max | Mean |
|---|---|---|---|---:|---:|---:|---:|
| sub 1, ci=19000001 / 19ad1000 / 0 | cell / LTE | dbm | dBm | 3 | -107 | -103 | -105 |
| sub 1, ci=19000001 / 19ad1000 / 0 | cell / LTE | rsrp_dbm | dBm | 3 | -107 | -103 | -105 |
| sub 1, ci=19000001 / 19ad1000 / 0 | cell / LTE | rsrq_db | dB | 3 | -12 | -12 | -12 |
| sub 1, ci=19000001 / 19ad1000 / 0 | cell / LTE | rssi_dbm | dBm | 3 | -77 | -77 | -77 |
| sub 1, ci=19000001 / 19ad1000 / 0 | cell / LTE | rssnr_db | dB | 2 | 11 | 11 | 11 |
| sub 1, ci=19000001 / 19ad1000 / 0 | cell / LTE | rssnr_tenth_db | dB | 1 | 11.5 | 11.5 | 11.5 |
| sub 1, nci=68719476735 / 19ad1000 / 0 | cell / NR | dbm | dBm | 2 | -99 | -97 | -98 |
| sub 1, nci=68719476735 / 19ad1000 / 0 | cell / NR | ss_rsrp_dbm | dBm | 2 | -99 | -97 | -98 |
| sub 1, nci=68719476735 / 19ad1000 / 0 | cell / NR | ss_rsrq_db | dB | 2 | -11 | -11 | -11 |
| sub 1, nci=68719476735 / 19ad1000 / 0 | cell / NR | ss_sinr_db | dB | 2 | 14 | 14 | 14 |
| AP 02:19:00:00:00:01 @ 5180 MHz / 19ad1000 / 0 | wifi / WIFI | rssi_dbm | dBm | 3 | -60 | -55 | -57 |

## Event and distinct-observation rates

Counts divided by the covered receipt interval, separately for each session and clock segment. These rates do not specify RF sample rate or statistical independence.

- {"accepted_sequence_events":20,"clock_segment":0,"covered_seconds":"50","first_received_elapsed_ns":"1000000000000","last_received_elapsed_ns":"1050000000000","radio_event_records":12,"radio_records_per_covered_second":"0.24","session_id":"19ad1000-0000-4000-8000-000000000001","unique_observations_per_covered_second":"0.16","unique_timestamped_observations":8}

## Sessions

- {"accepted_sequence_rows":20,"clock_discontinuities":0,"clock_segments":1,"lifecycle_issues":0,"rows":20,"sequence_issues":0,"session_end_lines":[20],"session_id":"19ad1000-0000-4000-8000-000000000001","session_start_lines":[1],"structurally_complete":true}

## Status and markers

- Line 1 / session: `{"app":{"version":"R19 study fixture"},"collection_intervals_ms":{"cell_request":10000,"wifi_request":35000},"device":{"model":"SYNTHETIC_FIXTURE","sdk_int":36},"historical_unit_case":"One labeled API29 LTE observation tests tenths-dB input handling; not one real device run.","label":"SYNTHETIC: no device or over-air measurements","permissions":{"fine_location":true,"nearby_wifi_devices":true,"read_phone_state":true},"signal_type":"reported_power_quality","synthetic":true,"time":{"elapsed_clock":"since_boot_including_sleep"}}`
- Line 2 / status: `{"code":"synthetic_fixture","details":{},"message":"All observations are invented test data."}`
- Line 3 / marker: `{"text":"SYNTHETIC stationary interval label"}`
- Line 9 / status: `{"code":"wifi_scan_request_rejected","details":{"request_accepted":false},"message":"SYNTHETIC throttled scan request"}`
- Line 13 / marker: `{"text":"SYNTHETIC phone orientation changed; marker only"}`
- Line 17 / status: `{"code":"permission_unavailable","details":{"fine_location":false},"message":"SYNTHETIC permission interruption"}`
- Line 19 / marker: `{"text":"No range, phase, position or handover is implied by this fixture."}`
- Line 20 / session_end: `{"counts":{"events_before_end":19},"reason":"synthetic_complete"}`

## Input and clock issues

- {"code":"out_of_order_source_timestamp","line":18,"previous_source_elapsed_ns":"1019000000000","source_elapsed_ns":"1000000000000"}

## Outputs

`source_original.jsonl` and `source_original.aradbp` retain the original bytes. The bit-plane archive is a reversible permutation with length and SHA256, not compression. `normalized.csv` keeps raw JSON beside each scalar metric; unknown metrics keep unknown units.

Plots use elapsed time from each session/clock segment's first received record. Source timestamps identify Wi-Fi last-seen or modem-reported receipt time. Missing/invalid source timestamps use a separately labeled receipt-time marker. No interpolation between records is drawn.
