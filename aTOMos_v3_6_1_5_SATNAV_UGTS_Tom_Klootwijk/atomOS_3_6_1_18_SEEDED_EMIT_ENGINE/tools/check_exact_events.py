"""Standalone public-API evidence for the R16 exact affine event profile.

This script constructs its own inputs and closed-form oracle. It imports no
test fixtures and requires neither a native build nor a GPU. Run from any cwd.
"""
from __future__ import annotations

import copy
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from atomos_events import EventEngine, EventDomainError, PROFILE, seal
from atomos_hinge import (DIMLESS, LENGTH, Phi, make_guard_seed,
                          pack_document, unpack_document)


def exact_json(value):
    """Readable lossless evidence representation; never cast to binary float."""
    if isinstance(value, F):
        return {"num": value.numerator, "den": value.denominator}
    if isinstance(value, Phi):
        return {"a": exact_json(value.a), "b": exact_json(value.b),
                "meaning": "a+b*phi, phi=(1+sqrt(5))/2"}
    if isinstance(value, dict):
        return {k: exact_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [exact_json(v) for v in value]
    if value is None or type(value) in (int, str, bool):
        return value
    raise TypeError("evidence contains a non-exact value")


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def field(initial=0, rate=0, dimension=DIMLESS):
    return {"dimension": list(dimension), "initial": initial, "rate": rate}


def update(name, value, operation="set"):
    return {"field": name, "op": operation, "value": value}


def relation(name, hinge="zero", *, equals=None, states=(), rates=()):
    return {"id": name, "hinge": hinge, "point_fields": ["x", "y", "z"],
            "active": [0, 1], "priority": 0, "equals": equals or {},
            "support": {}, "state_updates": list(states), "rate_updates": list(rates)}


def base_profile(rate=4):
    return {"profile": PROFILE, "frame": "world",
            "time_convention": "local elapsed SI seconds", "horizon": [0, 1],
            "max_event_sets": 16,
            "fields": {"x": field(-1, rate, LENGTH), "y": field(0, 0, LENGTH),
                       "z": field(0, 0, LENGTH), "mode": field(), "counter": field()},
            "hinges": {"zero": make_guard_seed(normal=(1, 0, 0), offset=0, width=8)},
            "relations": []}


def turnaround_input():
    p = base_profile()
    p["hinges"]["zero"]["q0"] = 1
    p["hinges"]["turn"] = make_guard_seed(normal=(1, 0, 0), offset=1, width=8)
    p["relations"] = [
        relation("enter", equals={"mode": 0}, states=[update("mode", 1), update("counter", 1, "add")]),
        relation("turn", "turn", equals={"mode": 1}, states=[update("mode", 2), update("counter", 10, "add")],
                 rates=[update("x", -4)]),
        relation("exit", equals={"mode": 2}, states=[update("mode", 3), update("counter", 1, "add")]),
    ]
    return p


def closed_form_x(time):
    """Independent piecewise closed form, not derived from runtime candidates."""
    return -1 + 4 * time if time <= F(1, 2) else 3 - 4 * time


def main():
    checks = []

    def check(name, actual, expected):
        passed = actual == expected
        checks.append({"name": name, "passed": passed, "actual": actual, "expected": expected})
        if not passed:
            raise RuntimeError("exact event evidence check failed: " + name)

    report = {"profile": "ATOMOS-EXACT-EVENTS-VALIDATION-R1", "all_passed": False,
              "method": "standalone public API; independently constructed inputs and Fraction closed-form oracle",
              "source_sha256": {str(p.relative_to(ROOT)).replace("\\", "/"): digest(p.read_bytes())
                                for p in (Path(__file__).resolve(), ROOT / "python/atomos_events.py",
                                          ROOT / "python/atomos_hinge.py")},
              "scope": ["finite rational affine epochs and recognized literal plane guards",
                        "no sampled root approximation, GPU root discovery, dynamic GPU BVH refit, or physical-accuracy measurement",
                        "once-only relation identities; a terminal point has no successor open interval",
                        "fraction records preserve exact values; digests are receipts and semantic checks execute separately"],
              "checks": checks}
    try:
        profile = turnaround_input()
        engine = EventEngine(profile)
        initial_word = engine.hinge("zero").state["q"]
        results = engine.run()
        event_transitions = [r.transition for r in results if r.status == "APPLIED"]
        check("turnaround statuses", [r.status for r in results], ["APPLIED"] * 3 + ["FINALIZED"])
        check("all three exact event times", [t["time"] for t in event_transitions], [F(1, 4), F(1, 2), F(3, 4)])
        check("complete selected relation sequence", [t["relations"] for t in event_transitions], [["enter"], ["turn"], ["exit"]])
        oracle = []
        for transition in engine.transitions:
            time = transition["time"]
            expected_x = closed_form_x(time)
            check("closed-form position at " + str(time), transition["pre_state"]["x"], expected_x)
            check("continuous position at " + str(time), transition["post_state"]["x"], expected_x)
            oracle.append({"time": time, "expected_x": expected_x, "actual_x": transition["pre_state"]["x"]})
        check("equal initial and final endpoint position", [profile["fields"]["x"]["initial"], engine.epoch["state"]["x"]], [F(-1), F(-1)])
        zero_traces = [t["hinge_traces"]["zero"] for t in event_transitions if "zero" in t["hinge_traces"]]
        check("two zero-plane crossings retained", [t["time"] for t in zero_traces], [F(1, 4), F(3, 4)])
        check("one-sided signs without epsilon", [[t["pre_side"], t["post_side"]] for t in zero_traces], [[-1, 1], [1, -1]])
        check("actual JK word transitions", [initial_word] + [t["after"] for t in zero_traces], [1, 0, 1])
        check("final world state", engine.epoch["state"], {"x": F(-1), "y": F(0), "z": F(0), "mode": F(3), "counter": F(12)})
        check("event-free terminal kind", engine.epoch["kind"], "terminal_state")
        check("event-free terminal time", engine.epoch["start"], F(1))
        check("finalized engine has no additional run", engine.run(), [])
        blob = engine.pack()
        replay = EventEngine.unpack(blob)
        check("semantic packed roundtrip byte equality", replay.pack() == blob, True)
        first = engine.history[0]
        duplicate = engine.apply_event_set(first)
        check("accepted duplicate status", duplicate.status, "DUPLICATE")
        check("accepted duplicate state hold", digest(engine.pack()), digest(blob))
        report["turnaround"] = {"input": profile, "oracle": {"equations": ["x(t)=-1+4*t for 0<=t<=1/2", "x(t)=3-4*t for 1/2<=t<=1"], "samples": oracle},
                                "certificates": engine.history, "transitions": engine.transitions,
                                "final_epoch": engine.epoch, "packed_bytes": len(blob), "packed_sha256": digest(blob)}

        horizon_profile = base_profile(rate=1)
        horizon_profile["relations"] = [relation("at_horizon", states=[update("counter", 3)])]
        horizon = EventEngine(horizon_profile)
        terminal_result = horizon.advance()
        check("horizon event applies", terminal_result.status, "APPLIED")
        check("horizon exact root", terminal_result.transition["time"], F(1))
        check("horizon is terminal point", [horizon.finalized, horizon.epoch["kind"]], [True, "terminal_state"])
        check("horizon post-state update", horizon.epoch["state"]["counter"], F(3))
        try:
            horizon.next_event_set()
            rejected_after_horizon = False
        except EventDomainError:
            rejected_after_horizon = True
        check("no next open interval after horizon event", rejected_after_horizon, True)
        report["horizon_event"] = {"input": horizon_profile, "certificate": horizon.history[0],
                                   "transition": terminal_result.transition, "final_epoch": horizon.epoch}

        rejection_records = []

        def reject(name, p, edit):
            subject = EventEngine(p)
            original = subject.next_event_set()
            forged = copy.deepcopy(original)
            edit(forged)
            forged = seal(forged)  # Recompute a valid receipt deliberately.
            before = subject.pack()
            result = subject.apply_event_set(forged)
            check(name + " rejected semantically", result.status, "INVALID")
            check(name + " leaves state unchanged", digest(subject.pack()), digest(before))
            rejection_records.append({"name": name, "input": p, "original": original,
                                      "submitted_with_valid_new_receipt": forged,
                                      "status": result.status, "reason": result.reason,
                                      "unchanged_packed_sha256": digest(before)})

        def false_root(c):
            c["event_time"] = F(1, 3)
            for event in c["events"] + c["all_candidates"]:
                event["root"] = F(1, 3)

        reject("rehashed false root", turnaround_input(), false_root)
        linear = base_profile()
        linear["hinges"]["later"] = make_guard_seed(normal=(1, 0, 0), offset=1, width=8)
        linear["relations"] = [relation("earlier"), relation("later", "later")]

        def omit_earlier(c):
            c["all_candidates"] = [x for x in c["all_candidates"] if x["relation"] != "earlier"]
            c["events"] = copy.deepcopy(c["all_candidates"])
            c["event_time"] = F(1, 2)

        reject("omitted earlier root", linear, omit_earlier)
        simultaneous = base_profile()
        simultaneous["relations"] = [relation("left"), relation("right")]

        def omit_tied(c):
            c["events"] = c["events"][:1]
            c["all_candidates"] = c["all_candidates"][:1]

        reject("incomplete simultaneous set", simultaneous, omit_tied)

        def false_none(c):
            c.update(status="NONE", event_time=None, events=[], all_candidates=[])

        reject("false event-free horizon", turnaround_input(), false_none)
        document = unpack_document(blob)
        document["certificates"] = document["certificates"][1:]
        missing_blob = pack_document(document)
        try:
            EventEngine.unpack(missing_blob)
            missing_status, missing_reason = "ACCEPTED", ""
        except ValueError as error:
            missing_status, missing_reason = "REJECTED", str(error)
        check("packed session with missing first certificate", missing_status, "REJECTED")
        report["adversarial_rejections"] = rejection_records
        report["missing_session_certificate"] = {"removed_receipt": first["content_hash"],
            "submitted_packed_bytes": len(missing_blob), "submitted_packed_sha256": digest(missing_blob),
            "status": missing_status, "reason": missing_reason}
        report["all_passed"] = True
    except Exception as error:
        report["failure"] = {"type": type(error).__name__, "reason": str(error)}
    report["check_count"] = len(checks)
    output = ROOT / "review/exact_events_validation.json"
    output.write_text(json.dumps(exact_json(report), indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"all_passed": report["all_passed"], "checks": len(checks),
                      "report": str(output), "report_sha256": digest(output.read_bytes())}))
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
