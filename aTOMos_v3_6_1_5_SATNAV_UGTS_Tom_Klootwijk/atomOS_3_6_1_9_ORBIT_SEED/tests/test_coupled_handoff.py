"""SATNAV binding, lossless publication and absence of implicit hold behavior."""
import copy
import csv
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import coupled_handoff as handoff
from ugts import decode_contiguous, decode_morton, digest


class HandoffBinding(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.input = self.base / "input"
        self.run = self.base / "run"
        self.input.mkdir()
        self.run.mkdir()
        self.config = {
            "frame": "ECEF_reception_axes_satellite_at_emission", "time_scale": "GPST",
            "anchor_geodetic_rad_m": [0, 0, 0], "anchor_ecef_m": [6378137, 0, 0],
            "chart_r0_m": 100000, "chart_core_m": 0.1, "hoop_phi_rad": 0.3,
            "epoch_tick_period_s": 1, "tick_origin_gpst_s": 1400000000,
            "code_residual_bound_m": 0.1, "code_residual_budget_m": 20,
            "support_spheres_enu_m": [{"center": [0, 0, 0], "radius": 10000}],
            "support_position_bound_m": 5, "bounds_origin": "test fixture"}
        (self.input / "profile.json").write_text(json.dumps(self.config), encoding="utf-8")
        self.epochs, self.solutions, self.residuals = [], [], []
        for index, eid in enumerate((42, 7, 900)):
            self.epochs.append({"epoch_id": eid, "t_rx_gpst_s": 1400000000 + index,
                                "x0_m": 6378137, "y0_m": 100 + index, "z0_m": 20,
                                "b0_m": 0, "asa_mask": 4294967295, "na_mask": 4294967295,
                                "boundary_mask": 0})
            self.solutions.append({"epoch_id": eid, "t_rx_gpst_s": 1400000000 + index,
                                   "status": "TOO_FEW" if index == 1 else "CONVERGED",
                                   "fit": "WITHIN_RESIDUAL_BUDGET", "x_m": 6378142,
                                   "y_m": 100 + index, "z_m": 20, "clock_bias_m": 70000.123456789,
                                   "var_x_m2": 1.25, "var_y_m2": 2.5, "var_z_m2": 3.75,
                                   "var_clock_m2": 4.125, "active": 15})
            if index != 1:
                self.residuals.append({"epoch_id": eid, "channel": 0, "residual_m": 100 if index == 2 else 0.125})
        self.write_csv(self.input / "epochs.csv", self.epochs)
        self.write_csv(self.run / "solutions.csv", self.solutions)
        self.write_csv(self.run / "residuals.csv", self.residuals)
        self.profile = self.base / "coupled_profile.json"
        self.profile.write_bytes(handoff.DEFAULT_PROFILE.read_bytes())

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def write_csv(path, rows):
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    def bundle(self):
        return handoff.read_sources(self.input, self.run, self.profile)

    def test_input_order_clock_variances_and_failed_epoch_survive(self):
        records = self.bundle()["observations"]
        self.assertEqual([record["epoch_id"] for record in records], [42, 7, 900])
        self.assertEqual([record["valid"] for record in records], [True, False, True])
        self.assertEqual(records[1]["enu_m"], [101.0, 20.0, 5.0])
        self.assertEqual(records[1]["clock_bias_m"], 70000.123456789)
        self.assertEqual(records[1]["formal_variance_m2"], [1.25, 2.5, 3.75, 4.125])
        self.assertEqual(records[1]["solver_record"]["status"], "TOO_FEW")
        self.assertEqual(records[1]["epoch_record"]["epoch_id"], "7")

    def test_residual_alert_does_not_disable_converged_observation(self):
        bundle = self.bundle()
        record = bundle["observations"][2]
        result = handoff.residual_diagnostic(record, bundle["config"])
        self.assertEqual(result["classification"], "EXCEEDS")
        self.assertFalse(result["changes_observation_validity"])
        self.assertTrue(record["valid"])

    def test_reordered_results_and_duplicate_ids_rejected(self):
        self.write_csv(self.run / "solutions.csv", [self.solutions[1], self.solutions[0], self.solutions[2]])
        with self.assertRaisesRegex(ValueError, "input epoch order"):
            self.bundle()
        self.epochs[1]["epoch_id"] = 42
        self.solutions[1]["epoch_id"] = 42
        self.write_csv(self.run / "solutions.csv", self.solutions)
        self.write_csv(self.input / "epochs.csv", self.epochs)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.bundle()

    def test_bad_frame_and_nonpositive_timestep_are_input_errors(self):
        self.config["frame"] = "unknown"
        (self.input / "profile.json").write_text(json.dumps(self.config))
        with self.assertRaisesRegex(ValueError, "frame"):
            self.bundle()
        self.config["frame"] = "ECEF_reception_axes_satellite_at_emission"
        (self.input / "profile.json").write_text(json.dumps(self.config))
        self.solutions[1]["t_rx_gpst_s"] = self.epochs[1]["t_rx_gpst_s"] = 1400000000
        self.write_csv(self.run / "solutions.csv", self.solutions)
        self.write_csv(self.input / "epochs.csv", self.epochs)
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            self.bundle()

    def test_source_mutation_detected(self):
        bundle = self.bundle()
        handoff.assert_sources_unchanged(bundle)
        self.solutions[0]["clock_bias_m"] = 1
        self.write_csv(self.run / "solutions.csv", self.solutions)
        with self.assertRaisesRegex(ValueError, "solutions"):
            handoff.assert_sources_unchanged(bundle)

    def test_keys_encode_modeled_chart_and_retain_winding_up_hoop(self):
        chart, packing = handoff.chart_and_keys([200, 100, 8], 1400000000 + 16385, 1.2,
                                                self.config, {"r0": 100000, "core": 0.1})
        self.assertEqual(chart["linear_tick"], 16385)
        self.assertEqual(chart["winding"], 1)
        self.assertEqual(chart["up_m"], 8)
        self.assertEqual(chart["hoop_phi_rad"], 1.2)
        self.assertEqual(decode_contiguous(int(packing["contiguous_hex"], 16)), tuple(packing["fields"]))
        self.assertEqual(decode_morton(int(packing["morton_hex"], 16)), tuple(packing["fields"]))
        self.assertEqual(packing["state_source"], "modeled_endpoint")

    def test_chart_domain_does_not_fabricate_packing(self):
        for p, time, status, temporal in (([0, 0, 3], 1400000000, "origin_core", "on_declared_lattice"),
                                          ([1e6, 0, 3], 1400000000, "out_of_key_range", "on_declared_lattice"),
                                          ([100, 0, 3], 1400000000.5, "defined", "tick_not_on_declared_lattice")):
            chart, keys = handoff.chart_and_keys(p, time, 0.4, self.config, {"r0": 100000, "core": 0.1})
            self.assertEqual(chart["status"], status)
            self.assertEqual(chart["temporal_status"], temporal)
            self.assertIsNone(keys)
            self.assertEqual(chart["time_gpst_s"], time)

    def test_numeric_failure_endpoint_is_never_published_as_valid_key(self):
        chart, keys = handoff.chart_and_keys([100, 0, 3], 1400000000, 0.4, self.config,
                                            {"r0": 100000, "core": 0.1}, "numeric_failure")
        self.assertEqual(chart["status"], "physical_state_unavailable")
        self.assertIsNone(keys)

    def fixture_trace(self, bundle=None):
        """Synthetic replay rows exercise publication; these are not native evidence."""
        from coupled import parse_document, trace
        bundle = self.bundle() if bundle is None else bundle
        model = handoff.build_model(bundle)
        model["trajectories"][0]["initial"]["v"] = [1.0, 0.25, -0.125]
        model["equations"]["j"] = "1"
        model["equations"]["k"] = "0"
        return bundle, model, list(trace(parse_document(model)[0]))

    def test_model_binds_default_initial_state_and_actual_samples(self):
        bundle = self.bundle()
        model = handoff.build_model(bundle)
        trajectory = model["trajectories"][0]
        self.assertEqual(trajectory["initial"]["time"], 1399999999)
        self.assertEqual(trajectory["initial"]["p"], [100, 20, 5])
        self.assertEqual([sample["epoch_id"] for sample in trajectory["samples"]], [42, 7, 900])
        self.assertEqual([sample["valid"] for sample in trajectory["samples"]], [True, False, True])
        self.assertEqual(trajectory["samples"][1]["clock_bias_m"], self.solutions[1]["clock_bias_m"])
        self.assertEqual(model["provenance"]["input_records"][1]["solver_record"]["status"], "TOO_FEW")

    def test_custom_initial_state_and_no_fix_initialization(self):
        bundle = self.bundle()
        for sample in bundle["observations"]:
            sample["valid"] = False
        with self.assertRaisesRegex(ValueError, "no converged observation"):
            handoff.build_model(bundle)
        bundle["profile"]["initial_position_source"] = "profile"
        bundle["profile"]["trajectory"]["initial"].update(p=[-4, 5, 6], v=[2, 3, 4], q=17)
        model = handoff.build_model(bundle)
        self.assertEqual(model["trajectories"][0]["initial"]["p"], [-4, 5, 6])
        self.assertEqual(model["trajectories"][0]["initial"]["q"], 17)
        self.assertTrue(all(not sample["valid"] for sample in model["trajectories"][0]["samples"]))

    def test_failed_sample_prediction_original_values_and_real_jk_are_published(self):
        bundle, model, trace = self.fixture_trace()
        records, head = handoff.publish_records(bundle, model, trace, {"test_fixture": True}, "model_hash")
        self.assertEqual(len(records), 3)
        self.assertEqual(records[1]["event"], "COUPLED_PREDICTION_ADVANCED")
        self.assertFalse(records[1]["observation"]["valid"])
        self.assertTrue(records[1]["modeled"]["valid"])
        self.assertNotEqual(trace[1]["p_before"], trace[1]["p_after"])
        self.assertNotEqual(trace[1]["v_before"], trace[1]["v_after"])
        self.assertEqual(records[0]["jk"], {"before": 0, "j": 4294967295, "k": 0, "after": 63})
        self.assertEqual(records[1]["observation"]["clock_bias_m"], self.solutions[1]["clock_bias_m"])
        self.assertNotEqual(records[1]["modeled"]["ecef_m"], records[1]["observation"]["ecef_m"])
        self.assertEqual(records[2]["observation"]["residual_diagnostic"]["classification"], "EXCEEDS")
        self.assertEqual(records[2]["event"], "COUPLED_OBSERVATION_ADVANCED")
        self.assertEqual(head, records[-1]["record_hash"])

    def test_hash_chain_covers_failed_samples_and_original_clock(self):
        bundle, model, trace = self.fixture_trace()
        records, head = handoff.publish_records(bundle, model, trace, {"test_fixture": True}, "model_hash")
        previous = "0" * 64
        for row in records:
            self.assertEqual(row["previous_hash"], previous)
            unsigned = {key: value for key, value in row.items() if key != "record_hash"}
            self.assertEqual(digest(unsigned, domain=handoff.DOMAIN), row["record_hash"])
            previous = row["record_hash"]
        modified = copy.deepcopy(records[1])
        modified["observation"]["clock_bias_m"] += 1
        del modified["record_hash"]
        self.assertNotEqual(digest(modified, domain=handoff.DOMAIN), records[1]["record_hash"])

    def test_unbound_native_rows_are_rejected(self):
        bundle, model, trace = self.fixture_trace()
        for field, value in (("epoch_id", 8), ("time_after", 0), ("target", [0, 0, 0]),
                             ("clock_bias_m", 0), ("observation_valid", True)):
            changed = copy.deepcopy(trace)
            changed[1][field] = value
            with self.assertRaisesRegex(ValueError, "does not bind"):
                handoff.publish_records(bundle, model, changed, {}, "model_hash")
        with self.assertRaisesRegex(ValueError, "sample count"):
            handoff.publish_records(bundle, model, trace[:-1], {}, "model_hash")

    def test_reference_only_report_cannot_publish_native_handoff(self):
        out = self.base / "coupled"
        out.mkdir()
        (out / "summary.json").write_text(json.dumps({"native_execution": "not_run", "native_trace_verified": False}))
        with patch.object(handoff.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")):
            with self.assertRaisesRegex(RuntimeError, "native execution and independent"):
                handoff.execute_native(self.profile, out, Path(sys.executable))

    def test_default_adapter_dispatches_to_coupled(self):
        import ugts_handoff
        with patch.object(handoff, "process", return_value={"test": "coupled"}) as call:
            result = ugts_handoff.process(self.input, self.run)
        self.assertEqual(result, {"test": "coupled"})
        call.assert_called_once_with(self.input, self.run)


if __name__ == "__main__":
    unittest.main()
