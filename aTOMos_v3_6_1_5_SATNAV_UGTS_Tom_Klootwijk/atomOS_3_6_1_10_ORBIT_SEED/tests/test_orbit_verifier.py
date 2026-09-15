"""Regression: recomputing hashes cannot make false derived geometry verify."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "tools"))
from orbit_native import NativeOrbit
from orbit_query import OrbitSession, record_digest
from orbit_seed import inspect_bytes, load, validate
from verify_orbit_run import verify


@unittest.skipUnless(os.name == "nt" and (ROOT / "bin/cpu/orbit_worker.exe").exists(), "Delivered Windows native worker required")
class TraceRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = ROOT / "examples/orbit/seeds/C03.orbseed"
        cls.worker = ROOT / "bin/cpu/orbit_worker.exe"
        cls.seed = load(cls.path)
        with NativeOrbit(cls.worker, cls.seed["model"]) as w:
            session = OrbitSession(cls.seed, w)
            cls.rows = list(session.schedule(0., 300.))
            cls.summary = {"seed": inspect_bytes(cls.path.read_bytes()), "station": dict(session.station),
                           "queries": len(cls.rows), "start_s": 0., "end_s": 300.}

    def attempt(self, rows):
        rows, summary = deepcopy(rows), deepcopy(self.summary)
        previous = "0" * 64
        for row in rows:
            row["previous_sha256"] = previous
            row["record_sha256"] = record_digest(row)
            previous = row["record_sha256"]
        summary["final_record_sha256"] = previous
        with tempfile.TemporaryDirectory(prefix="orbit_trace_regression_") as directory:
            path = Path(directory)
            (path / "summary.json").write_text(json.dumps(summary))
            (path / "trace.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
            return verify(self.seed, path, self.worker)

    def test_unchanged_trace_verifies(self):
        self.assertEqual(self.attempt(self.rows)["status"], "passed")

    def test_rehashed_derived_scalar_forgery_rejected(self):
        for key in ("range_m", "range_rate_m_s", "up_m", "azimuth_deg", "elevation_deg",
                    "azimuth_rate_deg_s", "elevation_rate_deg_s", "sin_elevation_rate_s"):
            with self.subTest(key=key):
                rows = deepcopy(self.rows); rows[0][key] += 1.
                with self.assertRaises(ValueError): self.attempt(rows)

    def test_rehashed_visibility_station_and_otan_rejected(self):
        changes = [lambda r: r[0].update(visible=not r[0]["visible"]),
                   lambda r: r[0]["station_ecef_m"].__setitem__(0, r[0]["station_ecef_m"][0] + 1.),
                   lambda r: r[1]["otan2_source"].update(value=123.),
                   lambda r: r[0]["feedback"]["stage_b"].update(output=123)]
        for change in changes:
            rows = deepcopy(self.rows); change(rows)
            with self.assertRaises(ValueError): self.attempt(rows)

    def test_domain_and_unrepresentable_cadence(self):
        seed = deepcopy(self.seed); seed["query"]["end_s"] = seed["model"]["domain_s"][1] + 1
        with self.assertRaises(ValueError): validate(seed)
        seed = deepcopy(self.seed)
        seed["feedback"]["cadence"].update(fine_s=1.e-320, coarse_s=1.e-320)
        with NativeOrbit(self.worker, seed["model"]) as worker:
            with self.assertRaisesRegex(ValueError, "cannot advance"):
                list(OrbitSession(seed, worker).schedule(1., 2.))


if __name__ == "__main__": unittest.main()
