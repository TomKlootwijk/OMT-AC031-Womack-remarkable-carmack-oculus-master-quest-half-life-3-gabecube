from pathlib import Path
from decimal import Decimal
import csv
import hashlib
import io
import json
import random
import struct
import sys
import tempfile
import unittest
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from atomos_radio import (analyze_bytes, pack_bytes, unpack_bytes, normalized_csv,
                          exact_json, parse_json, study_file, radio_inventory, wifi_band_channel)

SID = "19ad1000-0000-4000-8000-000000000001"


def record(seq, kind="wifi", received=100_000_000_000, source=99_000_000_000, **changes):
    payload = ({"ssid": "Test", "bssid": "02:00:00:00:00:19", "frequency_mhz": 5180,
                "channel_width": 2, "rssi_dbm": -60, "capabilities": "[TEST]"}
               if kind == "wifi" else {})
    value = {"schema": "atomos.radio.v1", "session_id": SID, "seq": seq, "kind": kind,
             "received_elapsed_ns": str(received), "received_unix_ms": 1_000_000 + received // 1_000_000,
             "source_elapsed_ns": None if source is None else str(source), "payload": payload}
    value.update(changes)
    return value


def stream(*records, final_newline=True):
    result = "\n".join(exact_json(r) for r in records)
    return (result + ("\n" if final_newline else "")).encode("utf-8")


class ArchiveTests(unittest.TestCase):
    def test_partial_word_and_block_roundtrip(self):
        rng = random.Random(19)
        for length in (0, 1, 2, 7, 8, 9, 63, 64, 65, 511, 512, 513, 1023, 1024, 1025):
            raw = rng.randbytes(length)
            packed = pack_bytes(raw)
            self.assertEqual(len(packed), 48 + 512 * ((length + 511) // 512))
            self.assertEqual(packed[16:48], hashlib.sha256(raw).digest())
            self.assertEqual(unpack_bytes(packed), raw)

    def test_corruption_and_truncation_rejected(self):
        packed = pack_bytes(bytes(range(256)) * 2)
        for value in (packed[:-1], packed + b"x", b"wrong", packed[:16] + bytes(32) + packed[48:]):
            with self.assertRaises(ValueError):
                unpack_bytes(value)
        altered = bytearray(packed)
        altered[48] ^= 1
        with self.assertRaisesRegex(ValueError, "SHA256"):
            unpack_bytes(bytes(altered))

    def test_nonzero_padding_rejected_even_with_matching_trimmed_hash(self):
        packed = bytearray(pack_bytes(b"ab"))
        packed[8:16] = struct.pack("<Q", 1)
        packed[16:48] = hashlib.sha256(b"a").digest()
        with self.assertRaisesRegex(ValueError, "padding"):
            unpack_bytes(bytes(packed))


class StudyTests(unittest.TestCase):
    def statuses(self, result):
        return [o["duplicate_status"] for o in result["observations"]]

    def codes(self, result):
        return {issue["code"] for issue in result["summary"]["issues"]}

    def test_cache_metadata_changes_do_not_create_new_observation(self):
        a, b = record(1), record(2, received=110_000_000_000)
        a["payload"].update(origin="callback", batch_id="a", results_updated=True)
        b["payload"].update(origin="cache", batch_id="b", results_updated=False)
        result = analyze_bytes(stream(record(0, "session"), a, b, record(3, "session_end", received=111_000_000_000)))
        self.assertEqual(self.statuses(result), ["unique_timestamped_observation", "cached_duplicate"])
        self.assertEqual(result["summary"]["metric_statistics"][0]["unique_timestamped_count"], 1)

    def test_conflicting_same_timestamp_marks_entire_cluster(self):
        a, b, c = record(1), record(2), record(3)
        b["payload"]["rssi_dbm"] = -61
        result = analyze_bytes(stream(record(0, "session"), a, b, c))
        self.assertEqual(set(self.statuses(result)), {"inconsistent_same_timestamp"})
        self.assertEqual(result["summary"]["metric_statistics"], [])
        self.assertIn("inconsistent_same_timestamp", self.codes(result))

    def test_unknown_payload_fields_participate_in_exact_cache_comparison(self):
        a, b = record(1), record(2)
        a["payload"]["vendor"] = 2**90
        b["payload"]["vendor"] = 2**90 + 1
        result = analyze_bytes(stream(record(0, "session"), a, b))
        self.assertIn("inconsistent_same_timestamp", self.codes(result))

    def test_duplicate_out_of_order_and_gap_sequences_are_explicit(self):
        result = analyze_bytes(stream(record(0, "session"), record(1), record(1), record(0), record(4)))
        self.assertEqual(self.statuses(result)[1:3], ["excluded_sequence_error"] * 2)
        self.assertIn("duplicate_or_out_of_order_seq", self.codes(result))
        self.assertIn("sequence_gap", self.codes(result))
        self.assertFalse(result["summary"]["sessions"][0]["structurally_complete"])

    def test_missing_source_does_not_claim_freshness_or_dedup(self):
        result = analyze_bytes(stream(record(0, "session"), record(1, source=None), record(2, source=None)))
        for observation in result["observations"]:
            self.assertIsNone(observation["measurement_elapsed_ns"])
            self.assertIsNone(observation["age_ns"])
            self.assertEqual(observation["duplicate_status"], "source_timestamp_unavailable_or_invalid")
        self.assertEqual(result["summary"]["metric_statistics"], [])

    def test_stale_source_is_retained_and_flagged_by_named_policy(self):
        result = analyze_bytes(stream(record(0, "session"), record(1, source=60_000_000_000)))
        observation = result["observations"][0]
        self.assertEqual(observation["measurement_elapsed_ns"], 60_000_000_000)
        self.assertTrue(observation["stale_by_policy"])
        self.assertEqual(observation["age_ns"], 40_000_000_000)

    def test_future_source_timestamp_not_used_as_measurement_time(self):
        result = analyze_bytes(stream(record(0, "session"), record(1, source=101_000_000_000)))
        self.assertIn("source_time_after_receipt", self.codes(result))
        self.assertIsNone(result["observations"][0]["measurement_elapsed_ns"])

    def test_invalid_rat_payload_reported_without_invented_classification(self):
        a = record(1, "cell", payload={"rat": ["NR"], "identity": {"nci": 123},
                                       "signal": {"ss_rsrp_dbm": -95}})
        result = analyze_bytes(stream(record(0, "session"), a))
        self.assertIn("invalid_rat_label", self.codes(result))
        self.assertIsNone(result["observations"][0]["rat"])
        self.assertEqual(result["observations"][0]["record"]["payload"]["rat"], ["NR"])

    def test_reboot_and_wall_clock_step_explicit(self):
        a, b = record(1, received=101_000_000_000), record(2, received=102_000_000_000)
        b["received_unix_ms"] += 5000
        c = record(3, received=1_000_000_000, source=900_000_000)
        result = analyze_bytes(stream(record(0, "session"), a, b, c))
        self.assertIn("wall_clock_discontinuity", self.codes(result))
        self.assertIn("elapsed_clock_reset", self.codes(result))
        self.assertEqual(result["observations"][-1]["segment"], 1)

    def test_equal_ns_identity_not_deduped_between_sessions(self):
        a = record(1)
        second_sid = "19ad1000-0000-4000-8000-000000000002"
        b = record(1, session_id=second_sid)
        result = analyze_bytes(stream(record(0, "session"), a,
            record(0, "session", session_id=second_sid), b))
        self.assertEqual(self.statuses(result), ["unique_timestamped_observation"] * 2)

    def test_rssnr_units_are_explicit_not_guessed_from_value(self):
        a = record(1, "cell", payload={"rat": "LTE", "subscription_id": 1,
            "identity": {"ci": 123}, "signal": {"rssnr_tenth_db": 11, "rssnr_db": 11,
            "rsrp_dbm": -105, "timing_advance_raw": 7, "unknown_metric": 12,
            "csi_rsrp_dbm": None}})
        result = analyze_bytes(stream(record(0, "session"), a))
        metrics = {m["source_field"]: m for m in result["observations"][0]["metrics"]}
        self.assertEqual(metrics["rssnr_tenth_db"]["value"], Decimal("1.1"))
        self.assertEqual(metrics["rssnr_db"]["value"], Decimal(11))
        self.assertIsNone(metrics["timing_advance_raw"]["unit"])
        self.assertEqual(metrics["unknown_metric"]["value_status"], "unknown_unit")
        self.assertEqual(metrics["csi_rsrp_dbm"]["value_status"], "unavailable")

    def test_large_identifiers_decimal_unknowns_and_raw_bytes_preserved(self):
        a = record(1)
        a["payload"].update(large=2**100 + 1, decimal=Decimal("0.123456789012345678901234567890123456789"))
        raw = stream(record(0, "session"), a).replace(b"\n", b"\r\n")
        result = analyze_bytes(raw)
        parsed = result["observations"][0]["record"]["payload"]
        self.assertEqual(parsed["large"], a["payload"]["large"])
        self.assertEqual(parsed["decimal"], a["payload"]["decimal"])
        exported = list(csv.DictReader(io.StringIO(normalized_csv(result))))[0]
        self.assertEqual(parse_json(exported["raw_json"])["payload"], a["payload"])
        self.assertEqual(unpack_bytes(pack_bytes(raw)), raw)

    def test_invalid_rows_and_truncated_tail_are_not_fabricated(self):
        raw = stream(record(0, "session"), record(1)) + b'{"schema":'
        result = analyze_bytes(raw)
        self.assertEqual(len(result["summary"]["invalid_rows"]), 1)
        self.assertTrue(result["summary"]["invalid_rows"][0]["possible_truncated_final_row"])
        self.assertEqual(len(result["observations"]), 1)

    def test_duplicate_json_key_nonfinite_and_invalid_utf8_rejected(self):
        raw = b'{"schema":"a","schema":"b"}\n{"value":NaN}\n\xff\n'
        result = analyze_bytes(raw)
        self.assertEqual(len(result["summary"]["invalid_rows"]), 3)

    def test_strict_schema_elapsed_and_boolean_integer_validation(self):
        variants = []
        for changes in ({"seq": True}, {"received_elapsed_ns": 100},
                        {"received_elapsed_ns": "01"}, {"source_elapsed_ns": "-1"},
                        {"received_unix_ms": True}, {"session_id": "not-a-uuid"},
                        {"schema": "different"}, {"kind": "invented"}):
            value = record(1)
            value.update(changes)
            variants.append(value)
        self.assertEqual(len(analyze_bytes(stream(*variants))["summary"]["invalid_rows"]), len(variants))

    def test_valid_final_record_without_newline_is_not_declared_truncated(self):
        result = analyze_bytes(stream(record(0, "session"), record(1, "session_end"), final_newline=False))
        self.assertTrue(result["summary"]["final_line_unterminated"])
        self.assertTrue(result["summary"]["sessions"][0]["structurally_complete"])

    def test_record_after_session_end_excluded(self):
        result = analyze_bytes(stream(record(0, "session"), record(1, "session_end"), record(2)))
        self.assertIn("record_after_session_end", self.codes(result))
        self.assertFalse(result["summary"]["sessions"][0]["structurally_complete"])
        self.assertFalse(result["observations"][0]["chronology_valid"])

    def test_analysis_artifacts_preserve_source_and_plot(self):
        raw = stream(record(0, "session"), record(1), record(2, "session_end"))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "test.jsonl"
            source.write_bytes(raw)
            summary = study_file(source, root / "analysis", label="SYNTHETIC test")
            self.assertEqual((root / "analysis/source_original.jsonl").read_bytes(), raw)
            self.assertEqual(unpack_bytes((root / "analysis/source_original.aradbp").read_bytes()), raw)
            self.assertEqual(len(summary["plots"]), 3)
            self.assertEqual(summary["study_label"], "SYNTHETIC test")
            self.assertTrue((root / "analysis" / summary["plots"][0]["file"]).is_file())
            self.assertTrue((root / "analysis/normalized.csv").is_file())
            self.assertEqual(json.loads((root / "analysis/summary.json").read_text())["input_sha256"], hashlib.sha256(raw).hexdigest())

    def test_source_output_alias_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / "source_original.jsonl"
            source.write_bytes(stream(record(0, "session")))
            with self.assertRaisesRegex(ValueError, "overwrite"):
                study_file(source, directory)

    def test_nonempty_study_output_is_not_reused(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / "input.jsonl"
            source.write_bytes(stream(record(0, "session")))
            output = directory / "output"
            output.mkdir()
            (output / "old_signal.png").write_bytes(b"keep")
            with self.assertRaisesRegex(ValueError, "empty directory"):
                study_file(source, output)
            self.assertEqual((output / "old_signal.png").read_bytes(), b"keep")

    def test_metric_statistics_do_not_mix_links_sessions_or_clock_segments(self):
        a, b, c = record(1), record(2), record(3, received=1_000_000_000, source=900_000_000)
        b["payload"]["bssid"] = "02:00:00:00:00:20"
        b["payload"]["rssi_dbm"] = -90
        second_sid = "19ad1000-0000-4000-8000-000000000002"
        result = analyze_bytes(stream(record(0, "session"), a, b, c,
            record(0, "session", session_id=second_sid), record(1, session_id=second_sid)))
        groups = result["summary"]["metric_statistics"]
        self.assertEqual(len(groups), 4)
        self.assertTrue(all(g["unique_timestamped_count"] == 1 for g in groups))

    def test_pack_cli_refuses_existing_output_and_preserves_it(self):
        cli = Path(__file__).resolve().parents[1] / "tools/study_radio.py"
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source, target = directory / "input", directory / "output"
            source.write_bytes(b"source")
            target.write_bytes(b"keep")
            result = subprocess.run([sys.executable, str(cli), "pack", str(source), str(target)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("already exists", result.stderr)
            self.assertEqual(target.read_bytes(), b"keep")

    def test_synthetic_fixture_has_cache_unknowns_and_all_radio_types(self):
        path = Path(__file__).resolve().parents[1] / "examples/synthetic_radio.jsonl"
        result = analyze_bytes(path.read_bytes())
        self.assertTrue(result["events"][0]["record"]["payload"]["synthetic"])
        self.assertEqual({o["rat"] for o in result["observations"]}, {"WIFI", "LTE", "NR"})
        self.assertEqual(result["summary"]["invalid_rows"], [])
        self.assertGreater(result["summary"]["observation_status_counts"]["cached_duplicate"], 0)

    def test_mixed_session_provenance_is_explicit(self):
        synthetic = record(0, "session", payload={"synthetic": True})
        other = record(0, "session", session_id="19ad1000-0000-4000-8000-000000000002")
        result = analyze_bytes(stream(synthetic, other))
        self.assertEqual(result["summary"]["data_origin"], "mixed_synthetic_and_unlabeled_sessions")

    def test_channel_inventory_distinguishes_stale_cache_and_fresh_identities(self):
        a = record(1, source=60_000_000_000)
        b = record(2, source=99_000_000_000)
        c = record(3, source=99_000_000_000)
        c["payload"]["bssid"] = "02:00:00:00:00:20"
        c["payload"]["frequency_mhz"] = 2412
        inv = radio_inventory(analyze_bytes(stream(record(0, "session"), a, b, c)))
        channels = {r["frequency_mhz"]: r for r in inv["wifi_channels"]}
        self.assertEqual(channels[5180]["distinct_ap_identities"], 1)
        self.assertEqual(channels[5180]["fresh_by_policy_ap_identities"], 1)
        self.assertEqual(channels[5180]["stale_records"], 1)
        self.assertEqual(channels[2412]["primary_channel"], 1)
        self.assertEqual(wifi_band_channel(5180), ("5 GHz", 36))
        self.assertEqual(wifi_band_channel(2484), ("2.4 GHz", 14))
        self.assertEqual(wifi_band_channel(None), (None, None))

    def test_many_radio_links_are_paginated_instead_of_overflowing_legend(self):
        records = [record(0, "session", payload={"synthetic": True})]
        for i in range(9):
            value = record(i + 1)
            value["payload"]["bssid"] = f"02:19:00:00:00:{i:02x}"
            records.append(value)
        records.append(record(10, "session_end"))
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "input.jsonl"
            source.write_bytes(stream(*records))
            result = study_file(source, Path(d) / "output")
            signals = [plot for plot in result["plots"] if "series" in plot]
            self.assertEqual(len(signals), 2)
            self.assertTrue(all(len(plot["series"]) <= 8 for plot in signals))


if __name__ == "__main__":
    unittest.main()
