"""Executable admission, exact reuse, and editable-wrapper regressions."""
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
import orbit_native
from orbit_native import NativeOrbit, numeric_model
from orbit_seed import default_feedback, digest, transition_ast

WORKER = Path(os.environ.get("ATOMOS_ORBIT_CPU", ROOT / "bin/cpu/orbit_worker.exe"))


def model():
    return json.loads((ROOT / "examples/orbit/models/G05.json").read_text())["model"]


def raw_run(document, commands, version=3):
    with tempfile.TemporaryDirectory(prefix="atomos_contract_") as directory:
        path = Path(directory) / "model.txt"
        path.write_text(numeric_model(document, version), encoding="ascii")
        result = subprocess.run([str(WORKER), "--model", str(path), "--backend", "cpu"],
                                input=commands + "\nQUIT\n", text=True, capture_output=True, timeout=15)
        return result, [json.loads(line) for line in result.stdout.splitlines()]


@unittest.skipUnless(WORKER.exists(), "native CPU worker unavailable")
class NativeContractTests(unittest.TestCase):
    def test_domain_endpoints_cache_and_one_ulp_exclusion(self):
        m = model(); m["domain_s"] = [-1.25, 2.5]
        m["integration"].update(step_s=.1, checkpoint_stride_steps=1, max_checkpoints=2)
        with NativeOrbit(WORKER, m) as worker:
            expected = {}
            for t in [-1.25, -.325, 0., .325, 2.5]:
                worker.reset(); row = worker.query(t)
                self.assertEqual(row["status"], "ok")
                expected[t] = row["state_gcrs"]
            for t in [2.5, -.325, .325, -1.25, 0., 2.5]:
                self.assertEqual(worker.query(t)["state_gcrs"], expected[t])
                self.assertLessEqual(worker.stats()["cache_count"], 2)
            for t in [math.nextafter(-1.25, -math.inf), math.nextafter(2.5, math.inf)]:
                row = worker.command("QUERY " + repr(t))["queries"][0]
                self.assertEqual(row["status"], "outside_model_domain")
                self.assertEqual(row["rk_steps"], 0)
            self.assertEqual(worker.query(2.5)["state_gcrs"], expected[2.5])

    def test_reference_surface_crossing_is_transactional_failure(self):
        m = model(); m["state_gcrs"] = [m["force"]["radius_m"] + 1, 0., 0., -1000., 0., 0.]
        m["force"]["empirical_rtn_m_s2"] = [0., 0., 0.]
        with NativeOrbit(WORKER, m) as worker:
            row = worker.query(.01)
            self.assertEqual(row["status"], "inside_reference_earth")
            self.assertEqual(row["state_gcrs"], m["state_gcrs"])
            self.assertEqual(worker.query(-.01)["status"], "ok")
            self.assertEqual(worker.query(0)["state_gcrs"], m["state_gcrs"])

    def test_raw_transport_rejects_invalid_epoch_frame_state_and_work(self):
        cases = []
        m = model(); m["epoch_jd_tt"] += 1; cases.append(m)
        m = model(); m["state_gcrs"][0] = 1e308; cases.append(m)
        m = model(); m["state_gcrs"][:3] = [m["force"]["radius_m"] / 2, 0., 0.]; cases.append(m)
        m = model(); m["domain_s"][1] += 1; cases.append(m)
        m = model(); m["integration"]["max_steps_per_query"] = 1; cases.append(m)
        for m in cases:
            with self.subTest(model=m):
                result, rows = raw_run(m, "QUERY 0")
                self.assertEqual(result.returncode, 2)
                self.assertFalse(rows)
        m = model(); m["frame"]["q_segments"][0]["t0_s"] = 1.
        result, rows = raw_run(m, "QUERY 0", 2)
        self.assertEqual(result.returncode, 2)
        self.assertIn("contain epoch", result.stderr)

    def test_legacy_transport_and_subnormal_coefficients_remain_supported(self):
        m = model(); m["force"]["gravity_s"][12][12] = 5e-324
        requests = "QUERY 0\nQUERY 300\nQUERY 604800.00001"
        modern, rows3 = raw_run(m, requests)
        legacy, rows2 = raw_run(m, requests, 2)
        self.assertEqual(modern.returncode, 0)
        self.assertEqual(legacy.returncode, 0)
        for a, b in zip(rows3[1:3], rows2[1:3]):
            self.assertEqual(a["queries"][0]["state_gcrs"], b["queries"][0]["state_gcrs"])
        self.assertEqual(rows2[3]["queries"][0]["status"], "outside_model_domain")

    def test_legacy_v1_physics_uses_same_states_as_v3_transport(self):
        document = json.loads((ROOT / "examples/orbit/baseline_models/G05.json").read_text())
        m = document.get("model", document)
        self.assertEqual(m["profile"], "ORBIT-DYNAMICS-R1")
        requests = "QUERY 0\nQUERY -12345.678\nQUERY 12345.678"
        modern, rows3 = raw_run(m, requests)
        legacy, rows1 = raw_run(m, requests, 1)
        self.assertEqual(modern.returncode, 0)
        self.assertEqual(legacy.returncode, 0)
        for a, b in zip(rows3[1:4], rows1[1:4]):
            self.assertEqual(a["queries"][0]["status"], "ok")
            self.assertEqual(a["queries"][0]["state_gcrs"], b["queries"][0]["state_gcrs"])

    def test_malformed_command_does_not_desynchronize_worker(self):
        with NativeOrbit(WORKER, model()) as worker:
            for command in ["QUERY nan", "QUERY 0 extra", "BATCH 0", "BATCH 4097",
                            "TRANSITION 2 0 1 1 1 0 1 1 0 14 204 0"]:
                with self.assertRaises(RuntimeError): worker.command(command)
                self.assertEqual(worker.command("PING"), {"type": "pong"})

    def test_duplicate_batch_preserves_order_bits_and_actual_work(self):
        with NativeOrbit(WORKER, model()) as worker:
            times = [300., -0., 300., .125, 0., .125, -0.]
            baseline = [worker.query(t)["state_gcrs"] for t in times]
            worker.reset()
            reply = worker.command("BATCH 7 " + " ".join(map(repr, times)))
            self.assertEqual(reply["unique_query_count"], 4)
            for t, state, row in zip(times, baseline, reply["queries"]):
                self.assertEqual(struct.pack("d", row["time_s"]), struct.pack("d", t))
                self.assertEqual(row["state_gcrs"], state)
            self.assertEqual([r["reused_in_batch"] for r in reply["queries"]],
                             [False, False, True, False, False, True, True])
            worker.reset(); rows = worker.batch([300.] * 64)
            self.assertEqual(sum(r["rk_steps"] for r in rows), 10)
            self.assertEqual(worker.stats()["cpu_queries"], 1)

    def test_wrapper_snapshot_cannot_drift_after_caller_model_edit(self):
        m = model(); m["domain_s"] = [-100., 100.]
        with NativeOrbit(WORKER, m) as worker:
            original = digest(m); state = worker.query(0)["state_gcrs"]
            m["domain_s"][1] = 1000.; m["state_gcrs"][0] += 100000.
            self.assertEqual(worker.model_sha256, original)
            self.assertEqual(worker.query(0)["state_gcrs"], state)
            with self.assertRaises(ValueError): worker.query(101.)
            with self.assertRaises(TypeError): worker.model["domain_s"][1] = 1000.
            with self.assertRaises(AttributeError): worker.model_sha256 = digest(m)
            editable = worker.copy_model(); editable["domain_s"][1] = 1000.
            self.assertEqual(worker.model["domain_s"][1], 100.)
            with self.assertRaises(ValueError): worker.query(101.)

    def test_feedback_preparation_reacts_to_typed_content_edits(self):
        feedback = default_feedback()
        with NativeOrbit(WORKER, model()) as worker, patch.object(
                orbit_native, "feedback_luts", wraps=orbit_native.feedback_luts) as prepare:
            worker.transition(feedback, 0, 5); worker.transition(feedback, 0, 5)
            self.assertEqual(prepare.call_count, 1)
            feedback["sets"][1]["boundary_mask"] = 4
            self.assertEqual(worker.transition(feedback, 0, 5)["after"], transition_ast(feedback, 0, 5)["after"])
            self.assertEqual(prepare.call_count, 2)
            invalid = deepcopy(feedback); invalid["sets"] = tuple(invalid["sets"])
            with self.assertRaises(ValueError): worker.transition(invalid, 0, 5)
            invalid = deepcopy(feedback); invalid["cadence"]["fine_s"] = True
            with self.assertRaises(ValueError): worker.transition(invalid, 0, 5)


if __name__ == "__main__": unittest.main()
