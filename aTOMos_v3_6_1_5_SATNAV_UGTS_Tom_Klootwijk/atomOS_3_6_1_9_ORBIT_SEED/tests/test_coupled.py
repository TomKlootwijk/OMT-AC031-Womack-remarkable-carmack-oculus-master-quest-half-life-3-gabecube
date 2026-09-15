"""CGK-R1 mechanics, feedback direction, input and trace-integrity evidence."""
from copy import deepcopy
import csv
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
import coupled


def document(steps=3, dt=1.):
    """A free physical trajectory, with no discretized channels by default."""
    return {"version": coupled.VERSION, "profile": coupled.PROFILE,
            "equations": {"d": "0", "x": "0", "j": "0", "k": "0"},
            "trajectories": [{"id": 0, "initial": {"time": 0., "p": [10., 2., 3.],
              "v": [1., -2., .5], "q": 0, "phi": 0.}, "mass": [2., 3., 4.],
              "damping": [0., 0., 0.], "stiffness_base": [[0., 0., 0.], [0., 0., 0.], [0., 0., 0.]],
              "chart": {"r0": 100., "core": .001, "blend_weight": .5, "axis": 0.},
              "hoop": {"rate": .25}, "masks": {"present": 0, "asa": coupled.WORD,
              "na": coupled.WORD, "boundary": 0}, "channels": [], "samples": [
              {"epoch_id": i, "time": (i + 1) * dt, "valid": False, "target": [0., 0., 0.],
               "observed_ecef": [3920000., 343000., 5000000.], "clock_bias_m": 5.,
               "force": [0., 0., 0.]} for i in range(steps)]}]}


def add_channel(doc, index=0):
    spec = doc["trajectories"][0]
    spec["masks"]["present"] |= 1 << index
    spec["channels"].append({"index": index, "direction": [1., 0., 0.],
        "stiffness": {"off": 0., "on": 0.}, "force": {"off": 0., "on": 0.},
        "angle_center": 0., "angle_tolerance": math.pi, "error_limit": 1., "fringe_width": .1,
        "support": {"kind": "sphere", "center": [0., 0., 0.], "radius": 100.}})
    return spec["channels"][-1]


def rows(doc):
    return list(coupled.trace(coupled.parse_document(doc)[0]))


class CoupledTests(unittest.TestCase):
    def test_free_motion_exact_analytic(self):
        doc = document(6, .25)
        result = rows(doc)
        initial = doc["trajectories"][0]["initial"]
        for row in result:
            t = row["time_after"]
            np.testing.assert_allclose(row["p_after"], np.array(initial["p"]) + t * np.array(initial["v"]), atol=1e-14)
            np.testing.assert_allclose(row["v_after"], initial["v"], atol=1e-14)
            self.assertEqual(row["status"], "advanced")

    def test_constant_force_backward_euler_closed_form(self):
        doc = document(8, .25)
        spec = doc["trajectories"][0]
        force = np.array([2., -6., 1.])
        for sample in spec["samples"]:
            sample["force"] = force.tolist()
        acceleration = force / np.array(spec["mass"])
        for n, row in enumerate(rows(doc), start=1):
            dt = .25
            expected_v = np.array(spec["initial"]["v"]) + n * dt * acceleration
            expected_p = np.array(spec["initial"]["p"]) + n * dt * np.array(spec["initial"]["v"]) + .5 * n * (n + 1) * dt * dt * acceleration
            np.testing.assert_allclose(row["v_after"], expected_v, atol=1e-13)
            np.testing.assert_allclose(row["p_after"], expected_p, atol=1e-13)

    def test_harmonic_diagonal_known_discrete_step(self):
        doc = document(1, .25)
        spec = doc["trajectories"][0]
        spec["mass"] = [1., 1., 1.]
        spec["initial"]["v"] = [0., 0., 0.]
        spec["stiffness_base"] = np.diag([4., 9., 16.]).tolist()
        spec["samples"][0]["valid"] = True
        row = rows(doc)[0]
        p = np.array(spec["initial"]["p"])
        expected_v = -.25 * np.array([4., 9., 16.]) * p / (1 + .25**2 * np.array([4., 9., 16.]))
        np.testing.assert_allclose(row["v_after"], expected_v, atol=1e-14)
        np.testing.assert_allclose(row["p_after"], p + .25 * expected_v, atol=1e-14)
        np.testing.assert_allclose(row["eigenvalues"], [4., 9., 16.], atol=1e-14)

    def test_refinement_converges_toward_continuous_harmonic_motion(self):
        errors = []
        for n in (10, 20, 40):
            doc = document(n, 1 / n)
            spec = doc["trajectories"][0]
            spec["mass"] = [1., 1., 1.]
            spec["initial"]["p"], spec["initial"]["v"] = [1., 0., 0.], [0., 0., 0.]
            spec["stiffness_base"] = np.diag([1., 1., 1.]).tolist()
            for sample in spec["samples"]:
                sample["valid"] = True
            row = rows(doc)[-1]
            errors.append(math.hypot(row["p_after"][0] - math.cos(1), row["v_after"][0] + math.sin(1)))
        self.assertLess(errors[1], .56 * errors[0])
        self.assertLess(errors[2], .56 * errors[1])

    def test_offdiagonal_generalized_eigenmatrix(self):
        doc = document(1, .1)
        spec = doc["trajectories"][0]
        spec["stiffness_base"] = [[4., 1., .3], [1., 3., .2], [.3, .2, 2.]]
        row = rows(doc)[0]
        k, d = np.array(row["stiffness"]).reshape(3, 3), np.array(row["eigenmatrix"]).reshape(3, 3)
        vectors, values = np.array(row["eigenvectors"]).reshape(3, 3), np.array(row["eigenvalues"])
        modes = vectors / np.sqrt(spec["mass"])[:, None]
        np.testing.assert_allclose(k @ modes, np.diag(spec["mass"]) @ modes * values, atol=1e-13)
        np.testing.assert_allclose(vectors.T @ vectors, np.eye(3), atol=1e-13)
        np.testing.assert_allclose(d @ vectors, vectors * values, atol=1e-13)

    def test_signed_coefficients_are_executed(self):
        doc = document(2, .25)
        spec = doc["trajectories"][0]
        spec["damping"] = [-.1, -.2, -.3]
        spec["stiffness_base"] = np.diag([-1., 0., 2.]).tolist()
        result = rows(doc)
        self.assertTrue(all(row["status"] == "advanced" for row in result))
        self.assertLess(result[0]["eigenvalues"][0], 0)

    def test_unavailable_observation_keeps_force_and_state_feedback(self):
        doc = document(2, .5)
        channel = add_channel(doc)
        channel["stiffness"] = {"off": 100., "on": 1000.}
        channel["force"]["on"] = 4.
        doc["equations"] = {"d": "~valid", "x": "d", "j": "y", "k": "0"}
        result = rows(doc)
        self.assertEqual(result[0]["q_after"], 1)
        self.assertEqual(result[0]["alignment"], 0)
        self.assertEqual(result[0]["limit"], 0)
        np.testing.assert_allclose(result[0]["mechanical_matrix"], np.diag([2., 3., 4.]).reshape(-1), atol=0)
        self.assertAlmostEqual(result[0]["v_after"][0], 2.)
        self.assertAlmostEqual(result[1]["v_after"][0], 3.)

    def test_whole_word_absorption_does_not_add_hold(self):
        doc = document(1)
        add_channel(doc, 0); add_channel(doc, 31)
        spec = doc["trajectories"][0]
        spec["masks"]["boundary"] = 1
        doc["equations"] = {"d": "1", "x": "d", "j": "~valid", "k": "0"}
        row = rows(doc)[0]
        self.assertEqual(row["na"], (1 << 31) | 1)
        self.assertEqual(row["hits"], 1)
        self.assertEqual(row["output"], 0)
        self.assertEqual(row["q_after"], (1 << 31) | 1)

    def test_bidirectional_feedback_counterfactuals(self):
        doc = coupled.read_json(ROOT / "examples/coupled/model.json")
        trajectories = coupled.parse_document(doc)
        base, changed_q = list(coupled.trace(trajectories[0])), list(coupled.trace(trajectories[1]))
        self.assertNotEqual(base[0]["p_after"], changed_q[0]["p_after"])
        self.assertTrue(any(a["drive"] != b["drive"] for a, b in zip(base[1:], changed_q[1:])))
        changed_observation = deepcopy(doc)
        changed_observation["trajectories"] = [deepcopy(doc["trajectories"][0])]
        changed_observation["trajectories"][0]["samples"][0]["target"] = [10., 1., 0.]
        changed = rows(changed_observation)
        self.assertNotEqual(base[0]["drive"], changed[0]["drive"])
        self.assertNotEqual(base[0]["q_after"], changed[0]["q_after"])
        self.assertNotEqual(base[1]["p_before"], changed[1]["p_before"])

    def test_editable_equations_change_full_trajectory(self):
        doc = coupled.read_json(ROOT / "examples/coupled/model.json")
        doc["trajectories"] = [doc["trajectories"][0]]
        before = rows(doc)
        doc["equations"]["j"] = "0"
        after = rows(doc)
        self.assertNotEqual(before[0]["q_after"], after[0]["q_after"])
        self.assertNotEqual(before[0]["p_after"], after[0]["p_after"])
        self.assertTrue(any(a["limit"] != b["limit"] for a, b in zip(before, after)))

    def test_ast_reference_does_not_use_compiled_tables(self):
        trajectory = coupled.load_document(ROOT / "examples/coupled/model.json")[0]
        with patch.object(coupled, "compile_lut", side_effect=AssertionError("reference used LUT")):
            self.assertEqual(len(list(coupled.trace(trajectory))), 24)

    def test_singular_step_commits_q_then_freezes_with_explicit_status(self):
        doc = document(3)
        add_channel(doc)
        spec = doc["trajectories"][0]
        spec["damping"] = [-2., -3., -4.]
        doc["equations"]["j"] = "1"
        result = rows(doc)
        self.assertEqual([r["status"] for r in result], ["numeric_failure", "previous_failure", "previous_failure"])
        self.assertEqual([r["q_after"] for r in result], [1, 1, 1])
        self.assertEqual(result[1]["q_before"], 1)
        self.assertEqual(result[2]["time_before"], 0.)
        self.assertEqual(result[2]["dt"], 3.)
        self.assertEqual(result[2]["chart_status"], "not_evaluated")
        self.assertEqual(result[2]["otan_status"], "not_evaluated")
        self.assertEqual(result[2]["p_after"], spec["initial"]["p"])
        for row in result:
            coupled.compare_trace_row(row, json.loads(json.dumps(row, allow_nan=False)))

    def test_nonfinite_arithmetic_is_numeric_failure_with_null_diagnostics(self):
        doc = document(2, 2.)
        doc["trajectories"][0]["samples"][0]["force"] = [1e308, 0., 0.]
        result = rows(doc)
        self.assertEqual(result[0]["status"], "numeric_failure")
        self.assertIsNone(result[0]["mechanical_rhs"][0])
        self.assertEqual(result[1]["status"], "previous_failure")
        coupled.compare_trace_row(result[0], json.loads(json.dumps(result[0], allow_nan=False)))

    def test_extreme_finite_geometry_is_not_reported_advanced(self):
        doc = document(2)
        spec = doc["trajectories"][0]
        spec["initial"]["p"] = [1e308, 1e308, 0.]
        spec["chart"] = {"r0": 1e-200, "core": 1e-250, "blend_weight": 0., "axis": 0.}
        result = rows(doc)
        self.assertEqual(result[0]["status"], "numeric_failure")
        self.assertIsNone(result[0]["rho"])
        self.assertEqual(result[1]["status"], "previous_failure")

    def test_literal_otan_domain_statuses(self):
        doc = document(3)
        spec = doc["trajectories"][0]
        spec["initial"]["p"], spec["initial"]["v"] = [1., 0., 0.], [0., 0., 0.]
        trajectory = coupled.parse_document(doc)[0]
        state = coupled.initial_state(trajectory)
        first = coupled.transition(trajectory, state, spec["samples"][0], 0)
        second = coupled.transition(trajectory, state, spec["samples"][1], 1)
        self.assertEqual(first["otan_status"], "first_observation")
        self.assertEqual(second["otan_status"], "zero_increment")
        state["p"] = np.array([0., 1., 0.])
        third = coupled.transition(trajectory, state, spec["samples"][2], 2)
        self.assertEqual(third["otan_status"], "ratio_undefined")
        spec["initial"]["p"] = [0., 0., 0.]
        core = rows(doc)
        self.assertEqual(core[0]["otan_status"], "first_observation")
        self.assertEqual(core[1]["otan_status"], "origin_core")

    def test_circle_plus_wrap_and_antipodal_tie(self):
        self.assertEqual(coupled.circle_plus(0., math.pi, .5), -math.pi / 2)
        self.assertAlmostEqual(coupled.circle_plus(math.pi - .1, -math.pi + .1, .5), -math.pi)
        self.assertAlmostEqual(coupled.circle_plus(1., 2., 0.), 1.)
        self.assertAlmostEqual(coupled.circle_plus(1., 2., 1.), 2.)
        doc = document(1)
        doc["trajectories"][0]["initial"]["phi"] = 7 * math.pi
        self.assertEqual(rows(doc)[0]["phi_before"], -math.pi)

    def test_sphere_and_cone_boundary_predicates(self):
        doc = document(1)
        c = add_channel(doc)
        spec = doc["trajectories"][0]
        spec["initial"]["p"] = [10., 0., 0.]
        c["support"]["radius"] = 10.
        row = rows(doc)[0]
        self.assertEqual((row["support"], row["fringe"]), (1, 1))
        c["support"] = {"kind": "cone", "center": [0., 0., 0.], "axis": [0., 0., 1.],
                        "slant": 2., "half_angle": math.pi / 4}
        h = 2 * math.cos(math.pi / 4)
        spec["initial"]["p"] = [0., 0., h]
        cone = rows(doc)[0]
        self.assertEqual((cone["support"], cone["fringe"]), (1, 1))
        spec["initial"]["p"] = [0., 0., h + 1.]
        self.assertEqual(rows(doc)[0]["support"], 0)

    def test_truth_tables_cover_high_words_and_order(self):
        doc = document(1)
        doc["equations"] = {"d": "q", "x": "valid", "j": "q & y & d & align & limit & fringe & support & valid", "k": "~q"}
        trajectory = coupled.parse_document(doc)[0]
        compiled = coupled.compiled_rows(trajectory)[3]
        table = dict(zip(coupled.EQUATION_FIELDS, compiled))
        self.assertEqual(table["d0"], ((1 << 32) - 1) << 32)
        self.assertEqual([table[f"j{i}"] for i in range(4)], [0, 0, 0, 1 << 63])
        self.assertEqual([table[f"k{i}"] for i in range(4)], [coupled.UINT64, coupled.UINT64, 0, 0])

    def test_compiled_csv_headers_and_preserved_input_order(self):
        trajectories = coupled.load_document(ROOT / "examples/coupled/model.json")
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / "compiled"
            coupled.write_compiled(trajectories, folder)
            for name, fields in (("manifest", coupled.MANIFEST_FIELDS), ("channels", coupled.CHANNEL_FIELDS),
                                 ("samples", coupled.SAMPLE_FIELDS), ("equations", coupled.EQUATION_FIELDS)):
                with (folder / f"{name}.csv").open(newline="") as stream:
                    values = list(csv.reader(stream))
                self.assertEqual(tuple(values[0]), fields)
                self.assertTrue(all(len(row) == len(fields) for row in values))
            with self.assertRaises(FileExistsError):
                coupled.write_compiled(trajectories, folder)

    def test_input_rejects_undefined_model_domains(self):
        mutations = [lambda s: s["mass"].__setitem__(0, 0),
                     lambda s: s["stiffness_base"][0].__setitem__(1, .1),
                     lambda s: s["samples"][0].__setitem__("time", 0),
                     lambda s: s["samples"][0].__setitem__("valid", 1),
                     lambda s: s["initial"].__setitem__("q", 1),
                     lambda s: s["chart"].__setitem__("blend_weight", 2),
                     lambda s: s["mass"].__setitem__(0, float("inf")),
                     lambda s: s["samples"][1].__setitem__("epoch_id", 0)]
        for mutate in mutations:
            doc = document()
            mutate(doc["trajectories"][0])
            with self.subTest(model=doc), self.assertRaises(ValueError):
                coupled.parse_document(doc)
        doc = document()
        c = add_channel(doc)
        c["direction"] = [2., 0., 0.]
        with self.assertRaises(ValueError):
            coupled.parse_document(doc)

    def test_equation_parser_rejects_undeclared_syntax(self):
        for expression in ("q + 1", "__import__('os')", "q << 1", "target", "2"):
            doc = document()
            doc["equations"]["j"] = expression
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                coupled.parse_document(doc)

    def test_replay_rejects_scalar_word_matrix_and_mode_mutations(self):
        expected = list(coupled.trace(coupled.load_document(ROOT / "examples/coupled/model.json")[0]))[3]
        for field in ("q_after", "drive", "time_after", "rho", "p_after", "stiffness", "mechanical_rhs", "eigenvalues", "eigenvectors"):
            mutated = deepcopy(expected)
            if isinstance(mutated[field], list):
                mutated[field][0] += .5
            else:
                mutated[field] += 1
            with self.subTest(field=field), self.assertRaises(ValueError):
                coupled.compare_trace_row(expected, mutated)

    def test_eigenvector_sign_and_degenerate_basis_are_not_false_mismatches(self):
        expected = list(coupled.trace(coupled.load_document(ROOT / "examples/coupled/model.json")[0]))[0]
        other = deepcopy(expected)
        other["eigenvectors"] = (-np.array(other["eigenvectors"])).tolist()
        coupled.compare_trace_row(expected, other)
        zero = rows(document(1))[0]
        rotated = deepcopy(zero)
        angle = .7
        rotated["eigenvectors"] = [math.cos(angle), -math.sin(angle), 0., math.sin(angle), math.cos(angle), 0., 0., 0., 1.]
        coupled.compare_trace_row(zero, rotated)

    def test_stream_replay_rejects_missing_and_trailing_rows(self):
        trajectories = coupled.parse_document(document(2))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "trace.jsonl"
            coupled.replay(trajectories, trace_path=path)
            self.assertTrue(coupled.replay(trajectories, actual_path=path)["native_trace_verified"])
            text = path.read_text()
            path.write_text(text.splitlines()[0] + "\n")
            with self.assertRaisesRegex(ValueError, "ended early"):
                coupled.replay(trajectories, actual_path=path)
            path.write_text(text + text.splitlines()[-1] + "\n")
            with self.assertRaisesRegex(ValueError, "trailing"):
                coupled.replay(trajectories, actual_path=path)


if __name__ == "__main__":
    unittest.main()
