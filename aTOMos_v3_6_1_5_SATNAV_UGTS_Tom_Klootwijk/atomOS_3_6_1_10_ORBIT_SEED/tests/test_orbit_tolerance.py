"""Acceptance cannot hide an interior error peak or a missing reference interval."""
import csv
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from assess_orbit_tolerance import assess


class ToleranceTests(unittest.TestCase):
    def report(self, times, errors, end):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            curve = base / "curve.csv"
            with curve.open("w", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(["seconds_after_cutoff", "position_error_m"])
                writer.writerows(zip(times, errors))
            report = {"status": "measured", "objects": [{"object_id": "synthetic", "physical_model_sha256": "fixture",
                "curve_file": curve.name, "curve_sha256": hashlib.sha256(curve.read_bytes()).hexdigest(),
                "maximum_sample_gap_seconds": max(b - a for a, b in zip(times, times[1:]))}]}
            path = base / "accuracy.json"
            path.write_text(json.dumps(report))
            return assess(path, hours=[end / 3600])["objects"][0]["durations"][0]

    def test_interior_exceedance_cannot_be_hidden_by_good_endpoint(self):
        row = self.report([300, 600, 900], [1, 11, 1], 900)
        self.assertEqual(row["status"], "failed")
        self.assertEqual(row["worst_sample_seconds"], 600)

    def test_missing_day_prevents_pass_even_with_low_sample_errors(self):
        row = self.report([300, 600, 900, 87300, 87600, 87900], [1] * 6, 87900)
        self.assertEqual(row["status"], "insufficient_coverage")
        self.assertFalse(row["coverage_complete_at_nominal_cadence"])

    def test_known_failure_stays_failure_despite_coverage_gap(self):
        row = self.report([300, 600, 900, 87300, 87600, 87900], [1, 1, 1, 11, 1, 1], 87900)
        self.assertEqual(row["status"], "failed")
        self.assertFalse(row["coverage_complete_at_nominal_cadence"])


if __name__ == "__main__": unittest.main()
