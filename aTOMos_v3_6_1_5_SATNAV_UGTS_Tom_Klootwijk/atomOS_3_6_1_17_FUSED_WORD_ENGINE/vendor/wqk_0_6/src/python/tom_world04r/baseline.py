"""Independent Fraction baseline for the 0.4 corrective rebuild.

This module intentionally imports no ``tom_world03`` or ``tom_world04r`` code.
It independently parses rational records, linearizes expressions, selects exact
roots, merges simultaneous operations, and constructs the semantic chain.
"""
from __future__ import annotations

from collections import defaultdict
from fractions import Fraction
import hashlib
import json
from typing import Any, Mapping


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _attach(record: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(record)
    out.pop("content_hash", None)
    out["content_hash"] = "sha256:" + hashlib.sha256(_canonical(out)).hexdigest()
    return out


def _f(value: Any) -> Fraction:
    if isinstance(value, Fraction):
        return value
    if isinstance(value, bool):
        return Fraction(int(value), 1)
    if isinstance(value, int):
        return Fraction(value, 1)
    if isinstance(value, str):
        return Fraction(value)
    if isinstance(value, Mapping):
        return Fraction(int(value["num"]), int(value["den"]))
    raise TypeError(f"cannot parse Fraction from {type(value).__name__}")


def _q(value: Fraction) -> dict[str, int]:
    return {"num": value.numerator, "den": value.denominator}


def _qmap(values: Mapping[str, Fraction]) -> dict[str, dict[str, int]]:
    return {name: _q(values[name]) for name in sorted(values)}


def _interval(value: Mapping[str, Any]) -> tuple[Fraction, Fraction]:
    lo, hi = _f(value["lower"]), _f(value["upper"])
    if hi < lo:
        raise ValueError("baseline interval upper below lower")
    return lo, hi


def _linear(
    expr: Mapping[str, Any],
    start: Fraction,
    state: Mapping[str, Fraction],
    rates: Mapping[str, Fraction],
) -> tuple[Fraction, Fraction] | None:
    op = expr.get("op")
    if op == "const":
        return Fraction(0), _f(expr["value"])
    if op == "time":
        return Fraction(1), Fraction(0)
    if op == "field":
        name = str(expr["name"])
        rate = rates[name]
        return rate, state[name] - rate * start
    if op == "neg":
        inner = _linear(expr["value"], start, state, rates)
        return None if inner is None else (-inner[0], -inner[1])
    args = expr.get("args")
    if not isinstance(args, list) or len(args) != 2:
        raise ValueError("baseline binary expression requires two args")
    left = _linear(args[0], start, state, rates)
    right = _linear(args[1], start, state, rates)
    if left is None or right is None:
        return None
    if op == "add":
        return left[0] + right[0], left[1] + right[1]
    if op == "sub":
        return left[0] - right[0], left[1] - right[1]
    if op == "mul":
        if left[0] == 0:
            return right[0] * left[1], right[1] * left[1]
        if right[0] == 0:
            return left[0] * right[1], left[1] * right[1]
        return None
    raise ValueError(f"unsupported baseline expression op {op}")


def _state_at(
    start: Fraction,
    state: Mapping[str, Fraction],
    rates: Mapping[str, Fraction],
    time: Fraction,
) -> dict[str, Fraction]:
    return {name: state[name] + rates[name] * (time - start) for name in state}


def _support_ok(record: Mapping[str, Any], state: Mapping[str, Fraction]) -> bool:
    for name, bound in record.get("bounds", {}).items():
        lo, hi = _interval(bound)
        if name not in state or not (lo <= state[name] <= hi):
            return False
    return True


def _compatibility_ok(record: Mapping[str, Any], state: Mapping[str, Fraction]) -> bool:
    return all(name in state and state[name] == _f(expected) for name, expected in record.get("equals", {}).items())


def _merge(
    relations: list[Mapping[str, Any]],
    attribute: str,
    source: Mapping[str, Fraction],
) -> dict[str, Fraction]:
    grouped: dict[str, list[tuple[str, Fraction]]] = defaultdict(list)
    for relation in relations:
        operations = relation.get(attribute, [])
        if not isinstance(operations, list):
            raise ValueError(f"baseline {attribute} must be an array")
        for operation in operations:
            grouped[str(operation["field"])].append((str(operation["mode"]), _f(operation["value"])))
    result = dict(source)
    for field in sorted(grouped):
        if field not in result:
            raise ValueError(f"baseline operation names unknown field {field}")
        modes = {mode for mode, _ in grouped[field]}
        if len(modes) != 1:
            raise ValueError(f"baseline mixed modes on {field}")
        mode = next(iter(modes))
        values = [value for _, value in grouped[field]]
        if mode == "set":
            if any(value != values[0] for value in values[1:]):
                raise ValueError(f"baseline unequal set values on {field}")
            result[field] = values[0]
        elif mode == "add":
            result[field] = result[field] + sum(values, Fraction(0))
        elif mode == "xor":
            if result[field].denominator != 1 or any(value.denominator != 1 for value in values):
                raise ValueError("baseline xor requires integers")
            merged = 0
            for value in values:
                merged ^= value.numerator
            result[field] = Fraction(result[field].numerator ^ merged, 1)
        else:
            raise ValueError(f"unsupported baseline transition mode {mode}")
    return result


def trusted_piecewise_baseline(world: Mapping[str, Any]) -> dict[str, Any]:
    """Exhaustively execute the literal world with independent arithmetic."""
    horizon_start, horizon_end = _interval(world["horizon"])
    initial = world["initial_segment"]
    start = _f(initial["domain"]["lower"])
    state = {name: _f(value) for name, value in initial["start_state"].items()}
    rates = {name: _f(initial["rates"].get(name, {"num": 0, "den": 1})) for name in state}
    fired: set[str] = set(initial.get("fired_relations", []))
    supports = {record["id"]: record for record in world["supports"]}
    compatibilities = {record["id"]: record for record in world["compatibilities"]}
    relations = list(world["relations"])
    max_events = int(world.get("solver", {}).get("max_event_sets", 64))

    realized: list[dict[str, Any]] = []
    event_sets: list[dict[str, Any]] = []
    sequence = 0
    while True:
        candidates: list[tuple[Fraction, int, str, str, str, Mapping[str, Any]]] = []
        for relation in relations:
            ident = str(relation["id"])
            if ident in fired:
                continue
            if relation.get("fire_policy") != "once":
                raise ValueError("baseline supports only once fire policy")
            coeff = _linear(relation["expression"], start, state, rates)
            if coeff is None:
                raise ValueError(f"baseline relation {ident} is non-affine")
            slope, intercept = coeff
            if slope == 0:
                if intercept == 0:
                    raise ValueError(f"baseline relation {ident} is identically zero")
                continue
            root = -intercept / slope
            active_lo, active_hi = _interval(relation["active_time"])
            if not (start < root <= horizon_end and active_lo <= root <= active_hi):
                continue
            root_state = _state_at(start, state, rates, root)
            if not _support_ok(supports[relation["support_id"]], root_state):
                continue
            if not _compatibility_ok(compatibilities[relation["compatibility_id"]], root_state):
                continue
            candidates.append((
                root,
                int(relation.get("priority", 0)),
                ident,
                str(relation["event_id"]),
                str(relation["content_hash"]),
                relation,
            ))
        candidates.sort(key=lambda item: item[:5])
        if not candidates:
            end_state = _state_at(start, state, rates, horizon_end)
            realized.append({
                "sequence": sequence,
                "domain": {"lower": _q(start), "upper": _q(horizon_end)},
                "start_state": _qmap(state),
                "rates": _qmap(rates),
                "end_state": _qmap(end_state),
            })
            final_state = end_state
            break
        if len(event_sets) >= max_events:
            raise ValueError("baseline event-set budget exhausted")
        root = candidates[0][0]
        simultaneous = [item for item in candidates if item[0] == root]
        selected_relations = [item[5] for item in simultaneous]
        pre_state = _state_at(start, state, rates, root)
        post_state = _merge(selected_relations, "transition", pre_state)
        post_rates = _merge(selected_relations, "rate_transition", rates)
        realized.append({
            "sequence": sequence,
            "domain": {"lower": _q(start), "upper": _q(root)},
            "start_state": _qmap(state),
            "rates": _qmap(rates),
            "end_state": _qmap(pre_state),
        })
        relation_order = [str(item[2]) for item in simultaneous]
        fired.update(relation_order)
        event_sets.append({
            "event_time": _q(root),
            "event_order": [str(item[3]) for item in simultaneous],
            "relation_order": relation_order,
            "pre_state": _qmap(pre_state),
            "post_state": _qmap(post_state),
            "pre_rates": _qmap(rates),
            "post_rates": _qmap(post_rates),
            "fired_relations_after": sorted(fired),
        })
        sequence += 1
        start, state, rates = root, post_state, post_rates

    baseline_pin = world["corrected_v03_baseline"]
    semantic = {
        "schema": "TOM-CONTINUATION-SEMANTIC-CHAIN-0.4.1",
        "world_hash": world["content_hash"],
        "corrected_v03_zip_sha256": baseline_pin["archive_sha256"],
        "corrected_interval_sha256": baseline_pin["interval_py_sha256"],
        "realized_segments": realized,
        "event_sets": event_sets,
        "final_time": _q(horizon_end),
        "final_state": _qmap(final_state),
        "fired_relations": sorted(fired),
        "boundary_policy": "event times are solver outputs; final boundary is the declared world horizon",
    }
    semantic_hash = "sha256:" + hashlib.sha256(_canonical(semantic)).hexdigest()
    return _attach({
        "schema": "TOM-INDEPENDENT-PIECEWISE-BASELINE-0.4.1",
        "implementation": "standalone fractions.Fraction exhaustive event continuation",
        "world_hash": world["content_hash"],
        "event_set_count": len(event_sets),
        "realized_segment_count": len(realized),
        "semantic_chain": semantic,
        "semantic_chain_sha256": semantic_hash,
    })
