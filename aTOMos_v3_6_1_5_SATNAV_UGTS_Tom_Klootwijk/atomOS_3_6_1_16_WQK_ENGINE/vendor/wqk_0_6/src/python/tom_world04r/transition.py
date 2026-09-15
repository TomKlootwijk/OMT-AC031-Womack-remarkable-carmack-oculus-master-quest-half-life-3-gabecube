"""Atomic event-set transition and noncompounding continuation construction."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from tom_world03.canonical import attach_hash, require_hash
from tom_world03.interval import ClosedInterval
from tom_world03.model import TransitionOp
from tom_world03.rational import Q

from .model import ContinuationRelation, ContinuationWorld, OpenSegment, OPEN_SEGMENT_KIND, qmap_record


class ContinuationConflict(ValueError):
    """Raised when one simultaneous event set has no deterministic merge."""


@dataclass(frozen=True, slots=True)
class EventBundle:
    event_set: Mapping[str, Any]
    transition: Mapping[str, Any]
    seal: Mapping[str, Any]
    successor: OpenSegment
    successor_record: Mapping[str, Any]
    transaction: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class FinalizationBundle:
    seal: Mapping[str, Any]
    transaction: Mapping[str, Any]


def _merge_ops(
    relations: Sequence[ContinuationRelation],
    attribute: str,
) -> tuple[list[dict[str, Any]], dict[str, tuple[str, Q]]]:
    grouped: dict[str, list[tuple[ContinuationRelation, TransitionOp]]] = defaultdict(list)
    for relation in relations:
        for operation in getattr(relation, attribute):
            grouped[operation.field].append((relation, operation))

    merged: dict[str, tuple[str, Q]] = {}
    audit: list[dict[str, Any]] = []
    for field in sorted(grouped):
        items = grouped[field]
        modes = {operation.mode for _, operation in items}
        if len(modes) != 1:
            raise ContinuationConflict(
                f"simultaneous {attribute} conflict on {field}: mixed modes {sorted(modes)}"
            )
        mode = next(iter(modes))
        values = [operation.value for _, operation in items]
        if mode == "set":
            if any(value != values[0] for value in values[1:]):
                raise ContinuationConflict(f"simultaneous {attribute} set conflict on {field}")
            merged_value = values[0]
        elif mode == "add":
            merged_value = sum(values, Q(0))
        elif mode == "xor":
            accumulator = 0
            for value in values:
                accumulator ^= value.as_integer()
            merged_value = Q(accumulator)
        else:  # TransitionOp already validates.
            raise AssertionError(mode)
        merged[field] = (mode, merged_value)
        audit.append({
            "field": field,
            "mode": mode,
            "merged_value": merged_value.to_record(),
            "contributors": [
                {
                    "relation_id": relation.id,
                    "relation_hash": relation.content_hash,
                    "event_id": relation.event_id,
                    "priority": relation.priority,
                    "value": operation.value.to_record(),
                }
                for relation, operation in items
            ],
        })
    return audit, merged


def _apply_ops(
    source: Mapping[str, Q],
    merged: Mapping[str, tuple[str, Q]],
    *,
    namespace: str,
) -> dict[str, Q]:
    result = dict(source)
    for field, (mode, value) in merged.items():
        if field not in result:
            raise ContinuationConflict(f"{namespace} operation names unknown field {field}")
        current = result[field]
        if mode == "set":
            result[field] = value
        elif mode == "add":
            result[field] = current + value
        elif mode == "xor":
            result[field] = Q(current.as_integer() ^ value.as_integer())
        else:
            raise AssertionError(mode)
    return result


def _time_id(time: Q) -> str:
    sign = "m" if time.numerator < 0 else "p"
    return f"t{sign}{abs(time.numerator)}d{time.denominator}"


def _validate_event_set(
    world: ContinuationWorld,
    segment: OpenSegment,
    event_set: Mapping[str, Any],
) -> tuple[Q, list[ContinuationRelation]]:
    require_hash(event_set, label="0.4.1 event set")
    if event_set.get("schema") != "TOM-NEXT-CONTINUATION-EVENT-SET-0.4.1":
        raise ValueError("unsupported event-set schema")
    if event_set.get("status") != "accepted":
        raise ValueError("event transition requires an accepted event set")
    if event_set.get("world_hash") != world.content_hash:
        raise ValueError("event set is bound to a different world")
    if event_set.get("segment_hash") != segment.content_hash or event_set.get("segment_id") != segment.id:
        raise ValueError("event set is bound to a different open segment")
    if list(event_set.get("fired_relations_before", [])) != list(segment.fired_relations):
        raise ValueError("event set fired-relation basis does not match the segment")

    event_time = Q.from_value(event_set.get("event_time"))
    if event_time <= segment.start:
        raise ValueError("event time must be strictly later than the open segment start")
    if event_time > segment.horizon:
        raise ValueError("event time exceeds the open segment horizon")

    relation_ids = [str(value) for value in event_set.get("relation_order", [])]
    relation_hashes = [str(value) for value in event_set.get("relation_hashes", [])]
    event_ids = [str(value) for value in event_set.get("event_order", [])]
    if not relation_ids or len(relation_ids) != len(set(relation_ids)):
        raise ValueError("event set relation_order must be nonempty and unique")
    if int(event_set.get("event_count", -1)) != len(relation_ids):
        raise ValueError("event_count does not match relation_order")
    relation_map = world.relation_map()
    try:
        relations = [relation_map[ident] for ident in relation_ids]
    except KeyError as exc:
        raise ValueError(f"event set references unknown relation {exc.args[0]}") from exc
    if any(relation.id in segment.fired_relations for relation in relations):
        raise ValueError("event set attempts to refire a once-only relation")
    if [relation.content_hash for relation in relations] != relation_hashes:
        raise ValueError("event set relation hash order mismatch")
    if [relation.event_id for relation in relations] != event_ids:
        raise ValueError("event set event ID order mismatch")

    events = event_set.get("events", [])
    if not isinstance(events, list) or len(events) != len(relations):
        raise ValueError("event set crossing certificates do not match event count")
    for relation, crossing in zip(relations, events):
        if not isinstance(crossing, Mapping):
            raise ValueError("event crossing certificate must be an object")
        require_hash(crossing, label="event crossing")
        if crossing.get("relation_id") != relation.id or crossing.get("relation_hash") != relation.content_hash:
            raise ValueError("event crossing relation binding mismatch")
        if Q.from_value(crossing.get("exact_root_time")) != event_time:
            raise ValueError("event crossing root does not equal event-set time")
        source = crossing.get("source_certificate")
        if not isinstance(source, Mapping):
            raise ValueError("event crossing lacks source certificate")
        require_hash(source, label="corrected 0.3 source crossing")
        if source.get("content_hash") != crossing.get("source_certificate_hash"):
            raise ValueError("event crossing source hash mismatch")
        if not source.get("accepted") or source.get("exact_root_time") != event_time.to_record():
            raise ValueError("event crossing source is not an accepted exact root")

    expected_fired = sorted(set(segment.fired_relations).union(relation_ids))
    if list(event_set.get("fired_relations_after", [])) != expected_fired:
        raise ValueError("event set fired_relations_after is inconsistent")
    return event_time, relations


def apply_event_set(
    world: ContinuationWorld,
    segment: OpenSegment,
    event_set: Mapping[str, Any],
) -> EventBundle:
    """Apply one event set exactly once and create its successor continuation.

    The current open segment is sealed at the solver-produced event time.  The
    successor always extends from that event time to the world horizon.  No
    relation supplies a continuation endpoint, so an earlier solver error
    cannot become the next segment's trusted boundary by construction.
    """
    event_time, relations = _validate_event_set(world, segment, event_set)
    pre_state = segment.state_at(event_time)
    state_audit, state_merged = _merge_ops(relations, "transition")
    rate_audit, rate_merged = _merge_ops(relations, "rate_transition")
    post_state = _apply_ops(pre_state, state_merged, namespace="state")
    post_rates = _apply_ops(segment.rates, rate_merged, namespace="rate")

    transition = attach_hash({
        "schema": "TOM-CONTINUATION-TRANSITION-0.4.1",
        "world_hash": world.content_hash,
        "segment_id": segment.id,
        "segment_hash": segment.content_hash,
        "event_set_hash": event_set["content_hash"],
        "event_time": event_time.to_record(),
        "event_order": list(event_set["event_order"]),
        "relation_order": list(event_set["relation_order"]),
        "merge_policy": {
            "set": "all simultaneous values must be exactly equal",
            "add": "exact rational sum applied once to the common pre-value",
            "xor": "integer xor applied once to the common pre-value",
            "mixed_modes": "reject",
            "boundary_source": "certified solver output, never relation metadata",
        },
        "pre_state": qmap_record(pre_state),
        "pre_rates": qmap_record(segment.rates),
        "state_operations": state_audit,
        "rate_operations": rate_audit,
        "post_state": qmap_record(post_state),
        "post_rates": qmap_record(post_rates),
    })

    seal = attach_hash({
        "schema": "TOM-OPEN-SEGMENT-SEAL-0.4.1",
        "world_hash": world.content_hash,
        "open_segment_id": segment.id,
        "open_segment_hash": segment.content_hash,
        "sequence": segment.sequence,
        "realized_domain": ClosedInterval(segment.start, event_time).to_record(),
        "end_time": event_time.to_record(),
        "end_state": qmap_record(pre_state),
        "event_set_hash": event_set["content_hash"],
        "transition_hash": transition["content_hash"],
        "seal_basis": "next certified exact event time",
    })

    fired = sorted(set(segment.fired_relations).union(relation.id for relation in relations))
    successor_record = attach_hash({
        "id": f"segment:open:{segment.sequence + 1:04d}:{_time_id(event_time)}",
        "kind": OPEN_SEGMENT_KIND,
        "sequence": segment.sequence + 1,
        "domain": ClosedInterval(event_time, world.horizon.upper).to_record(),
        "start_state": qmap_record(post_state),
        "rates": qmap_record(post_rates),
        "fired_relations": fired,
        "parent_segment_hash": segment.content_hash,
        "source_event_set_hash": event_set["content_hash"],
        "source_transition_hash": transition["content_hash"],
        "provenance": {
            "profile": world.profile,
            "boundary_source": "event_set.event_time",
            "corrected_v03_interval_sha256": world.corrected_interval_sha256,
        },
    })
    successor = OpenSegment.from_record(successor_record)

    transaction = attach_hash({
        "schema": "TOM-EVENT-CONTINUATION-TRANSACTION-0.4.1",
        "world_hash": world.content_hash,
        "sequence": successor.sequence,
        "parent_segment_id": segment.id,
        "parent_segment_hash": segment.content_hash,
        "event_time": event_time.to_record(),
        "event_set_hash": event_set["content_hash"],
        "transition_hash": transition["content_hash"],
        "seal_hash": seal["content_hash"],
        "successor_segment_id": successor.id,
        "successor_segment_hash": successor.content_hash,
        "atomicity": "event set, transition, seal, successor, commit, then HEAD",
        "noncompounding_rule": "successor start derives once from common pre-state; successor horizon is the world horizon",
    })
    return EventBundle(event_set, transition, seal, successor, successor_record, transaction)


def finalize_segment(world: ContinuationWorld, segment: OpenSegment) -> FinalizationBundle:
    end_time = world.horizon.upper
    if segment.horizon != end_time:
        raise ValueError("final segment does not extend to the world horizon")
    end_state = segment.state_at(end_time)
    seal = attach_hash({
        "schema": "TOM-OPEN-SEGMENT-SEAL-0.4.1",
        "world_hash": world.content_hash,
        "open_segment_id": segment.id,
        "open_segment_hash": segment.content_hash,
        "sequence": segment.sequence,
        "realized_domain": ClosedInterval(segment.start, end_time).to_record(),
        "end_time": end_time.to_record(),
        "end_state": qmap_record(end_state),
        "event_set_hash": None,
        "transition_hash": None,
        "seal_basis": "declared world horizon after no later accepted event",
    })
    transaction = attach_hash({
        "schema": "TOM-CONTINUATION-FINALIZATION-TRANSACTION-0.4.1",
        "world_hash": world.content_hash,
        "sequence": segment.sequence + 1,
        "segment_id": segment.id,
        "segment_hash": segment.content_hash,
        "seal_hash": seal["content_hash"],
        "final_time": end_time.to_record(),
        "final_state": qmap_record(end_state),
    })
    return FinalizationBundle(seal, transaction)
