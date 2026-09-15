"""Editing and exact numerical regressions for prepared query inputs."""
from copy import deepcopy
import json
import math
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from orbit_dynamics import frame_matrix, frame_pair, state_to_ecef
from orbit_query import OrbitSession, station_geometry
from orbit_seed import _encode, default_feedback, default_stations, digest, feedback_luts, transition_ast


def model(name="G05"):
    return json.loads((ROOT / "examples/orbit/models" / (name + ".json")).read_text())["model"]


class PreparedFeedbackTests(unittest.TestCase):
    def test_edits_change_ast_and_lut_and_return_values_cannot_poison_cache(self):
        feedback = default_feedback()
        first = feedback_luts(feedback)
        original = dict(first)
        first["x_lut"] ^= 15
        self.assertEqual(feedback_luts(feedback), original)
        feedback["equations"] = {"x": "d", "j": "y", "k": "~y"}
        self.assertEqual(transition_ast(feedback, 0, 5)["after"], 5)
        self.assertNotEqual(feedback_luts(feedback), original)
        feedback["sets"][1]["boundary_mask"] = 4
        self.assertEqual(transition_ast(feedback, 0, 5)["after"], 0)
        feedback["sets"][1]["boundary_mask"] = 0
        self.assertEqual(transition_ast(feedback, 0, 5)["after"], 5)

    def test_invalid_edits_never_alias_a_previously_valid_preparation(self):
        changes = [lambda f: f.update(sets=tuple(f["sets"])),
                   lambda f: f["sets"][0].update(asa_mask=True),
                   lambda f: f["cadence"].update(fine_s=0.),
                   lambda f: f["predicates"].update(near_mask_deg=float("nan")),
                   lambda f: f.update(q0=32),
                   lambda f: f["equations"].update(x="q + d")]
        for change in changes:
            feedback = default_feedback()
            feedback_luts(feedback)
            transition_ast(feedback, 0, 5)
            change(feedback)
            with self.assertRaises(ValueError): feedback_luts(feedback)
            with self.assertRaises(ValueError): transition_ast(feedback, 0, 5)


class FramePreparationTests(unittest.TestCase):
    def test_pair_matches_separate_frames_at_boundaries_and_after_model_edit(self):
        m = model()
        times = [-691200., -12345.678, -0., 0., 12345.678, 604800.]
        times += [s["t0_s"] for s in m["frame"]["eop_segments"] if m["domain_s"][0] <= s["t0_s"] <= m["domain_s"][1]]
        for edited in (False, True):
            if edited:
                m["frame"]["q_segments"][0]["coefficients"][0][0] += 1e-8
                m["frame"]["eop_segments"][0]["coefficients"][1][0] += 1e-8
            for t in times:
                matrix, rate = frame_pair(m, t)
                self.assertEqual(matrix.tobytes(), frame_matrix(m, t).tobytes())
                self.assertEqual(rate.tobytes(), frame_matrix(m, t, True).tobytes())
                state = np.asarray(m["state_gcrs"])
                old = np.concatenate((matrix @ state[:3], matrix @ state[3:] + rate @ state[:3]))
                self.assertEqual(old.tobytes(), state_to_ecef(m, t, state).tobytes())

    def test_r1_frame_pair_preserves_the_retained_profile(self):
        m = model()
        m["profile"] = "ORBIT-DYNAMICS-R1"
        m["frame"].pop("eop_segments")
        m["frame"].update(xp_rad=-0., yp_rad=1e-6)
        for t in [-691200., -0., 0., 98765.4321, 604800.]:
            a, b = frame_pair(m, t)
            self.assertEqual(a.tobytes(), frame_matrix(m, t).tobytes())
            self.assertEqual(b.tobytes(), frame_matrix(m, t, True).tobytes())

    def test_station_coordinates_are_content_keyed_including_signed_zero(self):
        station = default_stations()[0]
        station.update(lat_deg=0., lon_deg=0., height_m=0.)
        state = np.array([27000000., 1000000., 2000000., 0., 1., 2.])
        with patch("orbit_query.state_to_ecef", return_value=state):
            first = station_geometry({}, 0., state, station)
            station["lat_deg"] = -0.
            second = station_geometry({}, 0., state, station)
            self.assertEqual(math.copysign(1., first["station_ecef_m"][2]), 1.)
            self.assertEqual(math.copysign(1., second["station_ecef_m"][2]), -1.)
            station["height_m"] = 100.
            third = station_geometry({}, 0., state, station)
            self.assertEqual(third["station_ecef_m"][0] - second["station_ecef_m"][0], 100.)
            station["elevation_mask_deg"] = 89.
            fourth = station_geometry({}, 0., state, station)
            self.assertTrue(third["visible"])
            self.assertFalse(fourth["visible"])


class FrozenSessionTests(unittest.TestCase):
    @staticmethod
    def fixture():
        seed = json.loads((ROOT / "examples/orbit/seeds/G05.json").read_text())
        class Worker:
            model_sha256 = digest(seed["model"])
            frozen_state = deepcopy(seed["model"]["state_gcrs"])
            def query(self, time_s): return {"state_gcrs": list(self.frozen_state)}
        return seed, Worker()

    def test_caller_mutations_do_not_change_existing_geometry_or_identity(self):
        seed, worker = self.fixture()
        session = OrbitSession(seed, worker)
        before = session.query(1234.5)
        seed["model"]["frame"]["era0_rad"] += .1
        seed["model"]["domain_s"][1] = 1.
        seed["stations"][0]["height_m"] += 100.
        seed["feedback"]["equations"]["x"] = "~d"
        seed["query"]["phi_rad"] += .2
        self.assertEqual(_encode(before), _encode(session.query(1234.5)))
        with self.assertRaises(ValueError): OrbitSession(seed, worker)
        with self.assertRaises(TypeError): session.seed["model"]["state_gcrs"][0] = 0.
        with self.assertRaises(TypeError): session.station["height_m"] = 5.

    def test_edit_copy_creates_a_new_identity_with_same_frozen_physical_worker(self):
        seed, worker = self.fixture()
        original = OrbitSession(seed, worker)
        edited = original.copy_seed()
        edited["feedback"]["equations"].update(j="1", k="0")
        edited["stations"][0]["height_m"] += 100.
        changed = OrbitSession(edited, worker)
        self.assertNotEqual(original.seed_hash, changed.seed_hash)
        self.assertEqual(original.model_hash, changed.model_hash)
        self.assertNotEqual(original.query(0.)["station_ecef_m"], changed.query(0.)["station_ecef_m"])
        self.assertEqual(original.query(0.)["state_gcrs_m_mps"], changed.query(0.)["state_gcrs_m_mps"])


if __name__ == "__main__": unittest.main()
