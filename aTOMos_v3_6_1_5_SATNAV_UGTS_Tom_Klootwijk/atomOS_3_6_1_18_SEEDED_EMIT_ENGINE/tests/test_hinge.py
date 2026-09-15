"""Correctness checks authorized for the new R15 reference implementation."""
import copy
from fractions import Fraction
import hashlib
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from atomos_hinge import (Engine, Phi, PHI, DomainError, PROFILE, MAGIC, LENGTH,
                         DIMLESS, canonical_bytes, chart_normalize, chart_lift,
                         eval_word, make_guard_seed, pack_document, unpack_document,
                         phi_turn, phi_branch, plane_guard, sphere_guard, psi_excludes_ball, _transpose)


class PhiTests(unittest.TestCase):
    def test_algebraic_identity_inverse_and_negative(self):
        self.assertEqual(PHI * PHI, PHI + 1)
        self.assertEqual(PHI.inverse(), PHI - 1)
        for a, b in ((0, 1), (-7, 3), (Fraction(2, 13), Fraction(-19, 11)),
                     ((1 << 4096) + 71, -(1 << 2048))):
            x = Phi(a, b)
            self.assertEqual(x * x.inverse(), Phi(1))
            self.assertEqual(-(-x), x)
            self.assertEqual((x / x).sign(), 1)
        with self.assertRaises(DomainError):
            Phi().inverse()

    def test_exact_sign_and_floor_including_huge_integers(self):
        self.assertGreater(PHI, Fraction(1618, 1000))
        self.assertLess(PHI, Fraction(1619, 1000))
        self.assertEqual(Phi(-1, 1).sign(), 1)
        self.assertEqual(Phi(-2, 1).sign(), -1)
        self.assertEqual(Phi(1, -1).sign(), -1)
        self.assertEqual(Phi(2, -1).sign(), 1)
        self.assertEqual(Phi().sign(), 0)
        huge = 1 << 20000
        self.assertEqual(Phi(huge, 1).floor(), huge + 1)
        self.assertEqual(Phi(-huge, -1).floor(), -huge - 2)
        for a in range(-5, 6):
            for b in range(-5, 6):
                x = Phi(Fraction(a, 3), Fraction(b, 7))
                n = x.floor()
                self.assertTrue(Phi(n) <= x < Phi(n + 1))

    def test_no_implicit_float(self):
        for value in (1.0, float("inf"), float("nan")):
            with self.assertRaises(TypeError):
                Phi(value)
        self.assertEqual(Phi(2, 3) * PHI, Phi(3, 5))

    def test_exact_phase_and_expression_retention(self):
        for index in (-1000, -2, -1, 0, 1, 2, 1000):
            turn = phi_turn(index)
            self.assertTrue(Phi(0) <= turn < Phi(1))
            original = index / PHI
            self.assertEqual(original - turn, Phi(original.floor()))
        self.assertEqual(phi_branch(37)["numeric_cartesian_status"], "UNKNOWN")


class GeometryAndGraphTests(unittest.TestCase):
    def test_lazy_branch_does_not_demand_unsupported_operator(self):
        seed = make_guard_seed()
        seed["nodes"] = [
            {"id": "yes", "op": "literal", "value": 1, "type": {"kind": "scalar", "dim": list(DIMLESS)}},
            {"id": "known", "op": "literal", "value": 2, "type": {"kind": "scalar", "dim": list(DIMLESS)}},
            {"id": "unsupported", "op": "sin", "args": ["known"]},
            {"id": "guard", "op": "if", "args": ["yes", "known", "unsupported"]},
        ]
        self.assertEqual(Engine(seed).evaluate().data, Phi(2))
        seed["nodes"][0]["value"] = 0
        self.assertEqual(Engine(seed).step("unknown").status, "UNKNOWN")

    def test_psi_bound_includes_descendants_and_retains_equality(self):
        self.assertFalse(psi_excludes_ball("plane", (1, 0, 0), 2))
        self.assertFalse(psi_excludes_ball("plane", (2, 0, 0), 2))
        self.assertTrue(psi_excludes_ball("plane", (3, 0, 0), 2))
        self.assertTrue(psi_excludes_ball("plane", (3, 0, 0), 2, normal=(2, 0, 0)))
        self.assertFalse(psi_excludes_ball("sphere", (2, 0, 0), 1, radius=1))
        self.assertTrue(psi_excludes_ball("sphere", (PHI + 1, 0, 0), 1, radius=PHI - 1))
        with self.assertRaises(DomainError):
            psi_excludes_ball("sphere", (3, 0, 0), -1)

    def test_plane_and_sphere_algebraic_boundary(self):
        self.assertEqual(plane_guard((PHI, 2, 0), (1, 0, 0), PHI), Phi())
        self.assertEqual(sphere_guard((PHI, 0, 0), radius=PHI), Phi())
        self.assertLess(sphere_guard((PHI - 1, 0, 0), radius=PHI), 0)
        self.assertGreater(sphere_guard((PHI + 1, 0, 0), radius=PHI), 0)
        for args in (((0, 0, 0), (0, 0, 0), 0),):
            with self.assertRaises(DomainError):
                plane_guard(*args)

    def test_affine_motion_and_units(self):
        engine = Engine(make_guard_seed(point=(2, 0, 0), velocity=(-1, 0, 0)))
        self.assertEqual(engine.evaluate({"time": Fraction(3, 2)}).data, Phi(Fraction(1, 2)))
        self.assertEqual(engine.step("outside", {"time": 1}).status, "VALUE")
        self.assertEqual(engine.step("on", {"time": 2}).status, "BOUNDARY")
        result = engine.step("inside", {"time": 3})
        self.assertEqual(result.state["q"], 1)
        self.assertTrue(result.trace["accepted_event"])
        broken = make_guard_seed(velocity=(-1, 0, 0))
        broken["nodes"][1]["type"]["frame"] = "another-frame"
        other = Engine(broken)
        before = copy.deepcopy(other.state)
        self.assertEqual(other.step("bad", {"time": 1}).status, "UNDEFINED")
        self.assertEqual(other.state, before)

    def test_defining_function_not_automatically_sdf(self):
        plane = Engine(make_guard_seed(normal=(2, 0, 0)))
        value = plane.evaluate({"point": (3, 0, 0)})
        self.assertEqual(value.data, Phi(6))
        self.assertFalse(value.is_sdf)
        sphere = Engine(make_guard_seed("sphere"))
        value = sphere.evaluate({"point": (2, 0, 0)})
        self.assertEqual(value.data, Phi(3))
        self.assertFalse(value.is_sdf)
        self.assertEqual(value.dimension, (2, 0, 0, 0, 0, 0, 0))
        required = make_guard_seed(normal=(2, 0, 0))
        required["nodes"][-1]["require_sdf"] = True
        self.assertEqual(Engine(required).step("x", {"point": (1, 0, 0)}).status, "UNDEFINED")

    def test_zero_order_left_fold_and_no_transcendental_float(self):
        seed = make_guard_seed()
        seed["nodes"] = [{"id": name, "op": "literal", "value": value,
                          "type": {"kind": "scalar", "dim": list(DIMLESS)}}
                         for name, value in (("a", 2), ("b", 3), ("c", 4))]
        seed["nodes"].append({"id": "guard", "op": "sequence", "args": ["a", "b", "c"],
                              "operations": ["add", "mul"]})
        engine = Engine(seed)
        self.assertEqual(engine.evaluate().data, Phi(20))
        unsupported = engine.seed
        unsupported["nodes"][-1]["op"] = "sin"
        unknown = Engine(unsupported)
        before = unknown.pack()
        self.assertEqual(unknown.step("unsupported").status, "UNKNOWN")
        self.assertEqual(unknown.pack(), before)
        self.assertEqual(eval_word(["seq", 1, ["or", 2], ["and", 2]], {}, 8), 2)

    def test_missing_and_nonfinite_are_atomic(self):
        engine = Engine(make_guard_seed())
        before = engine.pack()
        self.assertEqual(engine.step("missing").status, "MISSING_INPUT")
        self.assertEqual(engine.step("float", {"point": (0.0, 0, 0)}).status, "INVALID")
        self.assertEqual(engine.pack(), before)

    def test_forward_graph_and_future_word_reads_rejected(self):
        seed = make_guard_seed()
        seed["nodes"][0] = {"id": "point", "op": "add", "args": ["guard", "guard"]}
        with self.assertRaises(ValueError):
            Engine(seed)
        seed = make_guard_seed()
        seed["equations"]["x"] = "y"
        with self.assertRaises(DomainError):
            Engine(seed)


class HingeTests(unittest.TestCase):
    def test_full_geometry_masks_latch_and_duplicate(self):
        engine = Engine(make_guard_seed())
        baseline = engine.step("a", {"point": (3, 0, 0)})
        self.assertFalse(baseline.trace["accepted_event"])
        inside = engine.step("b", {"point": (-3, 0, 0)})
        self.assertTrue(inside.trace["accepted_event"])
        self.assertEqual(inside.trace["after"], 1)
        self.assertEqual(len(inside.trace["stages"]), 2)
        packed = engine.pack()
        self.assertEqual(engine.step("b", {"point": (-3, 0, 0)}).status, "DUPLICATE")
        self.assertEqual(engine.pack(), packed)
        self.assertEqual(engine.step("b", {"point": (-4, 0, 0)}).status, "INVALID")
        self.assertEqual(engine.pack(), packed)
        result = engine.step("c", {"point": (-4, 0, 0)})
        self.assertFalse(result.trace["accepted_event"])
        self.assertEqual(result.state["q"], 1)
        self.assertEqual(engine.step("d", {"point": (4, 0, 0)}).state["q"], 0)

    def test_whole_word_absorption_and_same_old_jk(self):
        seed = make_guard_seed(width=8, pulse_on_first=True)
        seed["q0"] = 5
        seed["equations"] = {"x": ["or", "d", 8], "j": "y", "k": "q"}
        seed["masks"][1]["boundary"] = 8
        result = Engine(seed).step("hit", {"point": (-1, 0, 0)})
        self.assertEqual(result.trace["stages"][0]["output"], 9)
        self.assertEqual(result.trace["stages"][1]["hits"], 1)
        self.assertEqual(result.trace["output"], 0)
        self.assertEqual(result.trace["k"], 5)
        self.assertEqual(result.state["q"], 0)

    def test_boundary_ownership_and_order(self):
        engine = Engine(make_guard_seed())
        before = engine.pack()
        self.assertEqual(engine.step("zero", {"point": (0, 0, 0)}).status, "BOUNDARY")
        self.assertEqual(engine.pack(), before)
        inside = Engine(make_guard_seed(boundary="inside", pulse_on_first=True))
        self.assertEqual(inside.step("zero", {"point": (0, 0, 0)}, sequence=10).state["q"], 1)
        self.assertEqual(inside.step("past", {"point": (1, 0, 0)}, sequence=9).status, "INVALID")

    def test_seam_corrected_sign_and_single_orientation_flip(self):
        engine = Engine(make_guard_seed(seam_lane=1))
        engine.step("baseline", {"point": (2, 0, 0)})
        seam = {"parity": 1, "winding_delta": 1, "source_value": Phi(2)}
        result = engine.step("seam", {"point": (-2, 0, 0)}, seam=seam)
        self.assertEqual(result.trace["corrected_guard"], Phi(2))
        self.assertEqual(result.state["orientation"], 1)
        self.assertEqual(result.state["winding"], 1)
        self.assertEqual(result.state["branch_parity"], 1)
        self.assertEqual(result.state["q"], 2)
        self.assertEqual(engine.step("seam", {"point": (-2, 0, 0)}, seam=seam).status, "DUPLICATE")
        self.assertEqual(engine.state["orientation"], 1)
        before = engine.pack()
        bad = engine.step("bad-glue", {"point": (-3, 0, 0)}, seam=seam)
        self.assertEqual(bad.status, "UNDEFINED")
        self.assertEqual(engine.pack(), before)

    def test_chart_lift_both_profiles_negative_and_large_winding(self):
        for profile in ("reflective_klein", "source_half_turn"):
            for winding in (-(1 << 128), -3, -2, -1, 0, 1, 2, 3, 1 << 128):
                rho = Phi(winding) + Fraction(1, 3)
                record = chart_normalize(rho, Fraction(1, 7), Fraction(2, 9),
                                         orientation=1, profile=profile)
                lifted = chart_lift(record)
                self.assertEqual(record["winding"], winding)
                self.assertEqual(lifted, {"rho": rho, "theta_turn": Phi(Fraction(1, 7)),
                                          "phi_phase_turn": Phi(Fraction(2, 9)), "orientation": 1})
        theta, phase = Phi(-(1 << 256), 1), Phi(1 << 128, -1)
        record = chart_normalize(Phi(-3, 1), theta, phase)
        lifted = chart_lift(record)
        self.assertEqual(lifted["theta_turn"], theta)
        self.assertEqual(lifted["phi_phase_turn"], phase)
        record["period"] = Phi(0)
        with self.assertRaises(DomainError):
            chart_lift(record)


class PackingTests(unittest.TestCase):
    def test_seed_and_state_access_are_snapshots(self):
        seed = make_guard_seed()
        engine = Engine(seed)
        before = engine.pack()
        seed["equations"]["x"] = "y"
        engine.seed["equations"]["x"] = "y"
        engine.state["orientation"] = 99
        self.assertEqual(engine.pack(), before)

    def test_operator_operand_state_roundtrip_and_resume(self):
        seed = make_guard_seed(normal=(PHI, 0, 0))
        seed["provenance"]["huge"] = (1 << 20000) + 1
        engine = Engine(seed)
        engine.step("a", {"point": (3, 0, 0)})
        engine.step("b", {"point": (-3, 0, 0)})
        packed = engine.pack()
        restored = Engine.unpack(packed)
        self.assertEqual(restored.pack(), packed)
        self.assertEqual(restored.seed, engine.seed)
        self.assertEqual(restored.state, engine.state)
        self.assertEqual(restored.step("b", {"point": (-3, 0, 0)}).status, "DUPLICATE")
        self.assertEqual(restored.step("c", {"point": (5, 0, 0)}), engine.step("c", {"point": (5, 0, 0)}))

    def test_upload_words_exact_bytes_without_projection(self):
        engine = Engine(make_guard_seed())
        for bits in (32, 64):
            exported = engine.upload_words(bits)
            blob = b"".join(w.to_bytes(bits // 8, "little") for w in exported["words"])
            blob = blob[:exported["byte_length"]]
            self.assertEqual(blob, engine.pack())
            self.assertIsNone(exported["geometry_projection"])
            self.assertEqual(hashlib.sha256(blob).hexdigest(), exported["sha256"])

    def test_malformed_length_digest_and_padding(self):
        packed = Engine(make_guard_seed()).pack()
        for invalid in (packed[:-1], packed + b"x", b"XOPPLAN1" + packed[8:],
                        packed[:8] + struct.pack("<Q", (1 << 64) - 1) + packed[16:],
                        packed[:16] + bytes(32) + packed[48:]):
            with self.assertRaises(ValueError):
                Engine.unpack(invalid)
        raw = canonical_bytes({"x": 1})
        padded = raw + bytes(511 - len(raw)) + b"\x01"
        invalid = MAGIC + struct.pack("<Q", len(raw)) + hashlib.sha256(raw).digest() + _transpose(padded)
        with self.assertRaisesRegex(ValueError, "padding"):
            unpack_document(invalid)

    def test_canonical_schema_rejection(self):
        for raw in (b'{"x":{"$int":"00"}}', b'{"x":1}',
                    b'{"x":{"$rat":["2","4"]}}', b'{"x":null,"x":null}'):
            padded = raw + bytes((-len(raw)) % 512)
            blob = MAGIC + struct.pack("<Q", len(raw)) + hashlib.sha256(raw).digest() + _transpose(padded)
            with self.assertRaises(ValueError):
                unpack_document(blob)
        for data in ({"x": 0.1}, {"$unknown": 1}):
            with self.assertRaises((TypeError, ValueError)):
                pack_document(data)


if __name__ == "__main__":
    unittest.main()
