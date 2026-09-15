"""R16 exact event checks, including independent closed-form continuation."""
import copy
from fractions import Fraction as F
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from atomos_hinge import (DIMLESS, LENGTH, Engine, UnsupportedOperation,
                         make_guard_seed, pack_document, unpack_document)
from atomos_events import (PROFILE, EventEngine, EventDomainError, UnresolvedEvent,
                          rational, seal)


def field(initial=0, rate=0, dimension=DIMLESS):
    return {"initial": initial, "rate": rate, "dimension": list(dimension)}


def op(name, value, mode="set"):
    return {"field": name, "op": mode, "value": value}


def relation(identity, hinge="zero", *, point_fields=("x", "y", "z"),
             active=(0, 1), equals=None, support=None, state=(), rates=(), priority=0):
    return {"id": identity, "hinge": hinge, "point_fields": list(point_fields),
            "active": list(active), "priority": priority, "equals": equals or {},
            "support": support or {}, "state_updates": list(state), "rate_updates": list(rates)}


def simple_profile(x=-1, velocity=2, *, offset=0):
    return {"profile": PROFILE, "frame": "world", "time_convention": "local elapsed SI seconds",
            "horizon": [0, 1], "max_event_sets": 16,
            "fields": {"x": field(x, velocity, LENGTH), "y": field(0, 0, LENGTH),
                       "z": field(0, 0, LENGTH), "mode": field(), "counter": field()},
            "hinges": {"zero": make_guard_seed(normal=(1, 0, 0), offset=offset, width=8)},
            "relations": [relation("cross")]}


def turnaround_profile():
    p = simple_profile(-1, 4)
    p["hinges"]["zero"]["q0"] = 1
    p["hinges"]["turn"] = make_guard_seed(normal=(1, 0, 0), offset=1, width=8)
    p["relations"] = [
        relation("enter", equals={"mode": 0}, state=[op("mode", 1), op("counter", 1, "add")]),
        relation("turn", "turn", equals={"mode": 1}, state=[op("mode", 2), op("counter", 10, "add")],
                 rates=[op("x", -4)]),
        relation("exit", equals={"mode": 2}, state=[op("mode", 3), op("counter", 1, "add")]),
    ]
    return p


class RationalAdmissionTests(unittest.TestCase):
    def test_strict_integer_limbs_and_reduction(self):
        self.assertEqual(rational({"num": 6, "den": 8}), F(3, 4))
        for value in (0.5, True, "1/2", {"num": 1.9, "den": 1}, {"num": 1, "den": 2.1},
                      {"num": True, "den": 2}, {"num": 1, "den": False}, {"num": 1, "den": 0},
                      {"num": 1, "den": -2}, {"num": 1, "den": 2, "ignored": 1}):
            with self.subTest(value=value), self.assertRaises((TypeError, ValueError)):
                rational(value)

    def test_profile_rejects_float_before_state_creation(self):
        p = simple_profile()
        p["fields"]["x"]["rate"] = {"num": 1.9, "den": 1}
        with self.assertRaises(ValueError):
            EventEngine(p)

    def test_declared_frames_dimensions_and_unknown_fields(self):
        p = simple_profile()
        p["frame"] = "different"
        with self.assertRaises(ValueError):
            EventEngine(p)
        p = simple_profile()
        p["fields"]["x"]["dimension"] = list(DIMLESS)
        with self.assertRaises(ValueError):
            EventEngine(p)
        p = simple_profile()
        p["relations"][0]["future_boundary"] = F(1, 2)
        with self.assertRaises(ValueError):
            EventEngine(p)

    def test_quadratic_sphere_graph_is_explicitly_unsupported(self):
        p = simple_profile()
        p["hinges"]["zero"] = make_guard_seed("sphere")
        with self.assertRaises(UnsupportedOperation):
            EventEngine(p)


class CertifiedHingeTests(unittest.TestCase):
    def call(self, engine, **changes):
        args = dict(origin=(-1, 0, 0), velocity=(2, 0, 0), epoch=F(0), time=F(1, 2),
                    frame="world", source_epoch="sha256:" + "a" * 64, sequence=0)
        args.update(changes)
        return engine.step_certified_crossing("root", **args)

    def test_root_keeps_boundary_hold_semantics_separate(self):
        h = Engine(make_guard_seed(width=8))
        self.assertEqual(h.step("ordinary", {"point": [0, 0, 0]}, crossing=True).status, "BOUNDARY")
        out = self.call(h)
        self.assertEqual(out.status, "VALUE")
        self.assertEqual(out.trace["time"], F(1, 2))
        self.assertEqual((out.trace["pre_side"], out.trace["post_side"]), (-1, 1))
        self.assertEqual(out.trace["guard"], 0 * out.trace["guard"])
        self.assertEqual(h.state["branch_parity"], 1)
        self.assertEqual(h.state["orientation"], 0)

    def test_existing_packing_and_duplicate_identity(self):
        h = Engine(make_guard_seed(width=8))
        self.assertEqual(self.call(h).status, "VALUE")
        packed = h.pack()
        resumed = Engine.unpack(packed)
        self.assertEqual(resumed.pack(), packed)
        self.assertEqual(self.call(resumed).status, "DUPLICATE")
        self.assertEqual(resumed.pack(), packed)
        self.assertEqual(self.call(resumed, velocity=(4, 0, 0), origin=(-2, 0, 0)).status, "INVALID")
        self.assertEqual(resumed.pack(), packed)

    def test_actual_root_graph_is_checked_without_epsilon(self):
        h = Engine(make_guard_seed(width=8))
        old = h.pack()
        self.assertEqual(self.call(h, time=F(1, 2) + F(1, 10**80)).status, "UNDEFINED")
        self.assertEqual(self.call(h, velocity=(0, 0, 0)).status, "UNDEFINED")
        self.assertEqual(self.call(h, frame="other").status, "UNDEFINED")
        self.assertEqual(self.call(h, time=0.5).status, "INVALID")
        self.assertEqual(h.pack(), old)

    def test_same_masks_and_jk_with_common_old_word(self):
        seed = make_guard_seed(width=8)
        seed["q0"] = 3
        seed["equations"]["x"] = ["xor", "q", "d"]
        seed["masks"] = [{"asa": 6, "na": 255, "boundary": 4},
                         {"asa": 3, "na": 255, "boundary": 8}]
        h = Engine(seed)
        out = self.call(h, origin=(1, 0, 0), velocity=(-2, 0, 0))
        # Independent finite word calculation for this literal profile:
        # old=3, inside-drive=1, x=3 xor 1=2, both stages retain2,
        # J=1&2=0, K=1&(~2&255)=1, next=(0&252)|((254)&3)=2.
        self.assertEqual(out.status, "VALUE")
        self.assertEqual((out.trace["x"], out.trace["output"], out.trace["j"], out.trace["k"], out.trace["after"]), (2, 2, 0, 1, 2))

    def test_orientation_is_applied_once_and_never_flipped(self):
        h = Engine(make_guard_seed(width=8, seam_lane=1))
        state = h.state
        state["orientation"] = 1
        h = Engine(h.seed, state)
        out = self.call(h)
        self.assertEqual(out.status, "VALUE")
        self.assertEqual((out.trace["pre_side"], out.trace["post_side"]), (1, -1))
        self.assertEqual(h.state["orientation"], 1)
        self.assertEqual(h.state["winding"], 0)
        self.assertEqual(out.trace["j"] & 2, 0)
        self.assertEqual(out.trace["k"] & 2, 0)


class ExactContinuationTests(unittest.TestCase):
    def test_turnaround_against_independent_closed_form(self):
        e = EventEngine(turnaround_profile())
        records = e.run()
        self.assertEqual([r.status for r in records], ["APPLIED", "APPLIED", "APPLIED", "FINALIZED"])
        # Closed-form oracle comes from two line pieces, independent of event
        # enumeration, certificates and the implementation's candidate method.
        def oracle_x(t):
            return -1 + 4*t if t <= F(1, 2) else 3 - 4*t
        expected_times = [F(1, 4), F(1, 2), F(3, 4), F(1)]
        expected_modes, expected_counters = [1, 2, 3, 3], [1, 11, 12, 12]
        for i, record in enumerate(records):
            self.assertEqual(record.transition["time"], expected_times[i])
            self.assertEqual(record.transition["pre_state"]["x"], oracle_x(expected_times[i]))
            self.assertEqual(record.epoch["state"]["mode"], expected_modes[i])
            self.assertEqual(record.epoch["state"]["counter"], expected_counters[i])
        self.assertEqual(oracle_x(F(0)), oracle_x(F(1)))
        plane_events = [r.transition["hinge_traces"]["zero"] for r in records if "zero" in r.transition["hinge_traces"]]
        self.assertEqual([x["time"] for x in plane_events], [F(1, 4), F(3, 4)])
        self.assertEqual([x["post_side"] for x in plane_events], [1, -1])
        self.assertEqual([x["after"] for x in plane_events], [0, 1])
        self.assertEqual(e.hinge("zero").state["branch_parity"], 0)
        self.assertEqual(e.epoch["kind"], "terminal_state")

    def test_constructed_rational_roots_independent_of_search_grid(self):
        rng = random.Random(0x16A701)
        for _ in range(100):
            expected = F(rng.randrange(1, 1000), 1001)
            rate = F(rng.choice([-1, 1]) * rng.randrange(1, 1000), rng.randrange(1, 1000))
            offset = F(rng.randrange(-1000, 1000), rng.randrange(1, 1000))
            p = simple_profile(offset-rate*expected, rate, offset=offset)
            engine = EventEngine(p)
            event = engine.next_event_set()
            with self.subTest(root=expected, rate=rate):
                self.assertEqual(event["event_time"], expected)
                self.assertEqual(engine.apply_event_set(event).status, "APPLIED")

    def test_horizon_root_commits_terminal_poststate(self):
        p = simple_profile(-1, 1)
        p["relations"][0]["state_updates"] = [op("counter", 7, "add")]
        e = EventEngine(p)
        out = e.advance()
        self.assertEqual(out.status, "APPLIED")
        self.assertTrue(e.finalized)
        self.assertTrue(out.transition["terminal"])
        self.assertEqual((e.epoch["kind"], e.epoch["state"]["counter"]), ("terminal_state", 7))
        self.assertEqual(e.run(), [])
        with self.assertRaises(EventDomainError):
            e.next_event_set()

    def test_fractional_and_point_active_windows(self):
        for interval, expected in [([F(1, 4), F(3, 4)], "APPLIED"), ([F(1, 2), F(1, 2)], "APPLIED"),
                                   ([F(3, 5), F(4, 5)], "FINALIZED")]:
            p = simple_profile()
            p["relations"][0]["active"] = interval
            with self.subTest(interval=interval):
                self.assertEqual(EventEngine(p).advance().status, expected)

    def test_support_and_equality_at_actual_root(self):
        p = simple_profile()
        p["fields"]["mode"] = field(0, 2)
        p["relations"][0]["equals"] = {"mode": 1}
        p["relations"][0]["support"] = {"x": [0, 0]}
        self.assertEqual(EventEngine(p).advance().status, "APPLIED")
        p["relations"][0]["equals"] = {"mode": F(3, 2)}
        self.assertEqual(EventEngine(p).advance().status, "FINALIZED")

    def test_start_root_and_reset_created_root_are_excluded(self):
        self.assertEqual(EventEngine(simple_profile(0, 1)).advance().status, "FINALIZED")
        p = simple_profile(-1, 4)
        p["fields"]["y"] = field(1, 1, LENGTH)
        p["hinges"]["yplane"] = make_guard_seed(normal=(0, 1, 0), width=8)
        p["relations"][0]["state_updates"] = [op("y", 0)]
        p["relations"].append(relation("reset_zero", "yplane"))
        e = EventEngine(p)
        self.assertEqual([x.status for x in e.run()], ["APPLIED", "FINALIZED"])
        self.assertEqual(e.epoch["fired_relations"], ["cross"])

    def test_identically_zero_is_unresolved_unless_gate_excludes_it(self):
        p = simple_profile(0, 0)
        e = EventEngine(p)
        old = e.pack()
        self.assertEqual(e.advance().status, "UNKNOWN")
        self.assertEqual(e.pack(), old)
        p["relations"][0]["equals"] = {"mode": 1}
        self.assertEqual(EventEngine(p).advance().status, "FINALIZED")
        self.assertEqual(EventEngine(simple_profile(1, 0)).advance().status, "FINALIZED")

    def test_budget_holds_without_partial_commit(self):
        p = simple_profile()
        p["max_event_sets"] = 0
        e = EventEngine(p)
        old = e.pack()
        self.assertEqual(e.advance().status, "RESOURCE_LIMIT")
        self.assertEqual(e.pack(), old)


class SimultaneityTests(unittest.TestCase):
    def profile(self):
        p = simple_profile()
        p["fields"]["counter"]["initial"] = 7
        p["fields"]["bits"] = field(4)
        p["relations"] = [relation("b", state=[op("counter", 2, "add"), op("bits", 1, "xor")], priority=1),
                          relation("a", state=[op("counter", 3, "add"), op("bits", 2, "xor")], priority=0)]
        return p

    def test_complete_group_add_xor_and_single_shared_hinge_pulse(self):
        e = EventEngine(self.profile())
        cert = e.next_event_set()
        self.assertEqual([x["relation"] for x in cert["events"]], ["a", "b"])
        out = e.apply_event_set(cert)
        self.assertEqual(out.status, "APPLIED")
        self.assertEqual(e.epoch["state"]["counter"], 12)
        self.assertEqual(e.epoch["state"]["bits"], 7)
        self.assertEqual(e.hinge("zero").state["step"], 1)
        self.assertEqual(out.transition["hinge_traces"]["zero"]["contributors"], ["a", "b"])

    def test_equal_sets_coalesce_and_conflicts_are_atomic(self):
        for updates, expected in [((op("mode", 2), op("mode", 2)), "APPLIED"),
                                  ((op("mode", 1), op("mode", 2)), "UNDEFINED"),
                                  ((op("mode", 1), op("mode", 2, "add")), "UNDEFINED")]:
            p = self.profile()
            for r, update in zip(p["relations"], updates):
                r["state_updates"].append(update)
            e = EventEngine(p)
            old = e.pack()
            with self.subTest(updates=updates):
                self.assertEqual(e.advance().status, expected)
                if expected != "APPLIED":
                    self.assertEqual(e.pack(), old)

    def test_different_paths_to_one_hinge_conflict(self):
        p = self.profile()
        p["fields"]["other_x"] = field(-2, 4, LENGTH)
        p["relations"][1]["point_fields"][0] = "other_x"
        e = EventEngine(p)
        old = e.pack()
        self.assertEqual(e.advance().status, "UNDEFINED")
        self.assertEqual(e.pack(), old)


class CertificateReplayTests(unittest.TestCase):
    def assert_rejected_unchanged(self, engine, certificate):
        old = engine.pack()
        self.assertEqual(engine.apply_event_set(certificate).status, "INVALID")
        self.assertEqual(engine.pack(), old)

    def test_rehashed_false_root_and_wrong_guard_binding(self):
        e = EventEngine(simple_profile())
        cert = e.next_event_set()
        cert["event_time"] = F(3, 4)
        cert["events"][0]["root"] = F(3, 4)
        cert["all_candidates"][0]["root"] = F(3, 4)
        self.assert_rejected_unchanged(e, seal(cert))
        cert = e.next_event_set()
        cert["events"][0]["plane_seed_hash"] = "sha256:" + "0"*64
        self.assert_rejected_unchanged(e, seal(cert))

    def test_omitted_earlier_event(self):
        p = simple_profile(-1, 4)
        p["hinges"]["later"] = make_guard_seed(offset=1, width=8)
        p["relations"].append(relation("later", "later"))
        e = EventEngine(p)
        cert = e.next_event_set()
        later = cert["all_candidates"][1]
        cert["events"] = [later]
        cert["all_candidates"] = [later]
        cert["event_time"] = later["root"]
        self.assert_rejected_unchanged(e, seal(cert))

    def test_incomplete_simultaneous_group_and_false_none(self):
        p = simple_profile()
        p["relations"].append(relation("same_time"))
        e = EventEngine(p)
        cert = e.next_event_set()
        cert["events"] = cert["events"][:1]
        cert["all_candidates"] = cert["all_candidates"][:1]
        self.assert_rejected_unchanged(e, seal(cert))
        cert = e.next_event_set()
        cert.update(status="NONE", event_time=None, events=[], all_candidates=[])
        self.assert_rejected_unchanged(e, seal(cert))

    def test_duplicate_hold_and_stale_epoch_rejection(self):
        e = EventEngine(turnaround_profile())
        first = e.next_event_set()
        self.assertEqual(e.apply_event_set(first).status, "APPLIED")
        old = e.pack()
        self.assertEqual(e.apply_event_set(first).status, "DUPLICATE")
        self.assertEqual(e.pack(), old)
        stale = copy.deepcopy(first)
        stale["epoch_sequence"] += 1
        self.assert_rejected_unchanged(e, seal(stale))

    def test_exact_replay_resumes_and_preserves_every_byte(self):
        e = EventEngine(turnaround_profile())
        e.advance()
        resumed = EventEngine.unpack(e.pack())
        self.assertEqual(resumed.pack(), e.pack())
        e.run()
        resumed.run()
        self.assertEqual(resumed.pack(), e.pack())
        terminal = EventEngine.unpack(e.pack())
        self.assertTrue(terminal.finalized)
        self.assertEqual(terminal.pack(), e.pack())
        self.assertEqual(terminal.apply_event_set(e.history[-1]).status, "DUPLICATE")

    def test_rehashed_session_state_does_not_replace_replay(self):
        e = EventEngine(turnaround_profile())
        e.run()
        document = unpack_document(e.pack())
        document["epoch"]["state"]["x"] = F(99)
        document["epoch"] = seal(document["epoch"])
        with self.assertRaisesRegex(ValueError, "differs from semantic replay"):
            EventEngine.unpack(pack_document(document))

    def test_returned_profiles_epochs_hinges_are_independent(self):
        p = simple_profile()
        e = EventEngine(p)
        original = e.pack()
        p["fields"]["x"]["initial"] = 99
        e.profile["fields"]["x"]["initial"] = 88
        e.epoch["state"]["x"] = 77
        clone = e.hinge("zero")
        clone.step("free", {"point": [-1, 0, 0]}, crossing=True)
        self.assertEqual(e.pack(), original)


if __name__ == "__main__":
    unittest.main()
