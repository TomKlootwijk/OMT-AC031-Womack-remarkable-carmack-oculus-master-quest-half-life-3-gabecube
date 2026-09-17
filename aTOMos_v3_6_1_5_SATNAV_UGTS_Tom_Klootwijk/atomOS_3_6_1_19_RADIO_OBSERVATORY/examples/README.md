# R19 synthetic radio study

`synthetic_radio.jsonl` contains **invented test records**, not phone or over-air measurements. `make_synthetic.py` recreates its exact bytes. It includes Wi-Fi, LTE, NR, cached repeats, an old cached Wi-Fi timestamp, missing NR timestamps/metrics, status events and human marker labels.

One LTE event deliberately carries the Android 29 `rssnr_tenth_db` field; other LTE events use the Android 30+ `rssnr_db` field. This tests both explicit unit profiles in one synthetic stream. It does not describe one physical phone changing its Android version.

From the release directory:

```powershell
python tools/study_radio.py study examples/synthetic_radio.jsonl path/to/new-study-directory
python -m unittest discover -s tests -v
python tools/study_radio.py pack examples/synthetic_radio.jsonl path/to/new-capture.aradbp
python tools/study_radio.py unpack path/to/new-capture.aradbp path/to/new-decoded.jsonl
```

Study output must be a new or empty directory. Pack/unpack output files must not already exist. Captures with invalid/truncated records are preserved and their issues are reported; an invalid record is never repaired into a fabricated observation.

`synthetic_analysis/` is the generated worked example. It has 20 JSONL records and 12 radio records: 8 unambiguous unique timestamped observations, 3 cached duplicates, and 1 record with no source timestamp. One old cached source time is explicitly flagged as out of order and older than the default 30-second study threshold. Its complete original bytes and bit-plane archive are included beside the normalized CSV, JSON/Markdown report and 11 plots.

`emulator_analysis/` studies the Android app's actual exported log from the API 36.1 emulator. Its radio values are **emulator-generated**, not physical over-air measurements. There are 45 valid event records, 14 timestamped radio observations (10 NR, 4 Wi-Fi), and 3 plots. The supplied label `ANDROID EMULATOR: synthetic radio values` appears on those plots; it annotates the study without editing the capture. `--label` is available for other clearly named experiments. The original emulator JSONL SHA256 is `eb1575e1261f8eb5a06215726c4e23b80c300c7241992f01a59039baee40ed45`.

`normalized.csv` uses one row per signal field. Original JSON remains beside every metric, so unknown fields and large identifiers are recoverable. The original JSONL and `.aradbp` files preserve the complete source including status events, line endings and invalid rows. Null remains unavailable; unknown signal fields keep an unknown unit. Source timestamps are reported Wi-Fi last-seen or approximate modem-reception timestamps, not waveform sample instants.

Descriptive statistics group each link, session, clock segment, RAT and source metric separately. Both historical LTE RSSNR profiles normalize to dB but remain separate source-field groups. Means are arithmetic means of the reported numeric dB/dBm values, not a mean computed in linear power. Repeated source observations are not counted as new observations; none of the resulting counts assumes statistical independence. Conflicting payloads at one identity/timestamp are retained and excluded from those statistics.

Elapsed timestamps are comparable only within their declared session/clock segment. Plots use source time when valid and distinct receipt-only markers otherwise. Samples are not interpolated. AP/cell changes are reported identities; no handover, range, position, velocity, phase, or raw complex CSI is inferred.

The ARADBP1 archive is an eight-byte magic, unsigned little-endian 64-bit original byte length, 32-byte SHA256, then zero-padded 512-byte blocks transposed as 64 little-endian 64-bit words. The same transpose decodes each block. Decoding checks exact length, zero padding and SHA256. This is a reversible bit permutation, not compression or improved measurement accuracy.
