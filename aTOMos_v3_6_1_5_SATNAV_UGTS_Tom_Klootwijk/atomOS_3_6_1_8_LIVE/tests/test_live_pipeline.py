"""Lifecycle/status regressions; solver/model arithmetic is checked separately."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from live_gnss import GPSEpoch
from live_pipeline import LivePipeline


class Worker:
    """Explicit test double for worker outcomes, not positioning evidence."""
    command = ["test_double"]
    process = SimpleNamespace(pid=-1)
    binary_sha256 = "test_double"
    ready = {"type": "test_double"}

    def __init__(self):
        self.calls = []
        self.status = "CONVERGED"
        self.state = [4400000., -90000., 4570000., 12.]
        self.continuous_drift = False

    def solve(self, epoch_id, time_gpst_s, seed, observations):
        self.calls.append(dict(epoch_id=epoch_id, time_gpst_s=time_gpst_s, seed=list(seed)))
        state = [value + 100. for value in seed] if self.continuous_drift else list(self.state)
        return dict(status=self.status, fit="WITHIN_BUDGET", used=4, state=state,
                    rms_m=1.5, backend="test_double", epoch_id=epoch_id)


def prepared(epoch, ephemerides, seed, clock, *args, **kwargs):
    return dict(observations=[], receiver_seed_ecef_m=list(seed), receiver_seed_clock_m=clock,
                model={"receiver_geometry_initialized": any(seed)})


class LivePipelineTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.worker = Worker()
        self.out = Path(self.folder.name) / "run"
        self.patch = patch("live_pipeline.prepare_epoch", prepared)
        self.patch.start()
        self.pipeline = LivePipeline(self.worker, self.out)

    def tearDown(self):
        self.pipeline.close()
        self.patch.stop()
        self.folder.cleanup()

    def epoch(self, t, station=42):
        return GPSEpoch(t, (), {"station_id": station})

    def test_native_failure_never_publishes_seed_as_fix_and_can_recover(self):
        self.worker.status = "TOO_FEW"
        failed = self.pipeline.process(self.epoch(100.))
        self.assertFalse(failed["position_available"])
        self.assertIsNone(failed["state_ecef_clock_m"])
        self.assertEqual(self.pipeline.seed, [0., 0., 0., 0.])
        self.worker.status = "CONVERGED"
        fixed = self.pipeline.process(self.epoch(101.))
        self.assertTrue(fixed["position_available"])
        self.assertEqual(fixed["state_ecef_clock_m"], self.worker.state)
        self.assertEqual(fixed["outer_passes"], 2)
        self.assertEqual(self.pipeline.seed, self.worker.state)

    def test_last_complete_fix_survives_later_failure(self):
        self.pipeline.process(self.epoch(100.))
        saved = list(self.pipeline.seed)
        self.worker.status = "RANK_DEFICIENT"
        self.worker.state = [1., 2., 3., 4.]
        failed = self.pipeline.process(self.epoch(101.))
        self.assertFalse(failed["position_available"])
        self.assertIsNone(failed["state_ecef_clock_m"])
        self.assertEqual(self.pipeline.seed, saved)
        self.assertEqual(self.worker.calls[-1]["seed"], saved)

    def test_duplicate_and_reordered_epochs_do_not_rewind_state(self):
        self.pipeline.process(self.epoch(100.))
        calls = len(self.worker.calls)
        seed = list(self.pipeline.seed)
        for timestamp in (100., 99.):
            result = self.pipeline.process(self.epoch(timestamp))
            self.assertEqual(result["status"], "STALE_EPOCH")
            self.assertFalse(result["position_available"])
        self.assertEqual(len(self.worker.calls), calls)
        self.assertEqual(self.pipeline.seed, seed)
        self.assertEqual(self.pipeline.last_time, 100.)

    def test_station_change_cold_starts_even_at_same_epoch(self):
        self.pipeline.process(self.epoch(100., station=42))
        calls = len(self.worker.calls)
        result = self.pipeline.process(self.epoch(100., station=43))
        self.assertTrue(result["position_available"])
        self.assertEqual(self.worker.calls[calls]["seed"], [0., 0., 0., 0.])
        self.assertEqual(self.pipeline.last_station, 43)
        changes = [json.loads(line) for line in (self.out / "events.jsonl").read_text().splitlines()]
        self.assertTrue(any(event.get("type") == "receiver_change" for event in changes))

    def test_outer_iteration_limit_cannot_claim_native_convergence_is_full_fix(self):
        self.worker.continuous_drift = True
        self.pipeline.max_outer = 2
        result = self.pipeline.process(self.epoch(100.))
        self.assertEqual(result["native_status"], "CONVERGED")
        self.assertEqual(result["status"], "OUTER_LIMIT")
        self.assertFalse(result["position_available"])
        self.assertIsNone(result["state_ecef_clock_m"])
        self.assertEqual(self.pipeline.seed, [0., 0., 0., 0.])
        summary = self.pipeline.close()
        self.assertEqual(summary["positions"], 0)
        trace = json.loads((self.out / "trace.jsonl").read_text())
        self.assertEqual(len(trace["passes"]), 2)

    def test_reference_station_coordinates_are_not_used_as_position_seed(self):
        epoch = GPSEpoch(100., (), {"station_id": 42, "ecef_arp_m": [1., 2., 3.]})
        result = self.pipeline.process(epoch)
        self.assertTrue(result["position_available"])
        self.assertEqual(self.worker.calls[0]["seed"], [0., 0., 0., 0.])
        self.assertFalse(self.pipeline.metadata["reference_coordinates_used"])

    def test_invalid_outer_limit_rejected_before_new_artifact_creation(self):
        for value in (0, -1):
            out = Path(self.folder.name) / f"invalid_{value}"
            with self.assertRaises(ValueError):
                LivePipeline(self.worker, out, max_outer=value)
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
