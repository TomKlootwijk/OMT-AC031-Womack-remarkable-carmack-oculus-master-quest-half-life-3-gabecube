"""Certified next-event solving for open piecewise-affine continuations.

The solver reuses the corrected 0.3 crossing certifier but changes the 0.4
continuation architecture: it searches forward over an open segment whose upper
bound is the world horizon.  The next event time is therefore a solver output,
not an input hidden in a relation's ``continuation_until`` field.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from tom_world03.canonical import attach_hash
from tom_world03.expression import affine_coefficients
from tom_world03.interval import ClosedInterval
from tom_world03.rational import Q
from tom_world03.solver import CrossingResult, certify_crossing

from .index import exhaustive_candidates, query_interval_index
from .model import ContinuationRelation, ContinuationWorld, OpenSegment


class UnresolvedContinuation(ValueError):
    """Raised when earliest-event ordering cannot be certified exactly."""


@dataclass(frozen=True, slots=True)
class ContinuationCrossing:
    relation: ContinuationRelation
    segment: OpenSegment
    exact_root: Q
    source: CrossingResult
    certificate: Mapping[str, Any]


def event_order_key(result: ContinuationCrossing) -> tuple[Any, ...]:
    relation = result.relation
    return (
        result.exact_root.as_fraction(),
        relation.priority,
        relation.id,
        relation.event_id,
        relation.content_hash,
    )


def _unit_brackets(start: Q, end: Q) -> list[ClosedInterval]:
    """Partition ``[start,end]`` at integer boundaries without zero-width gaps."""
    if end < start:
        raise ValueError("search end is before start")
    if end == start:
        return [ClosedInterval.point(start)]
    result: list[ClosedInterval] = []
    cursor = start
    while cursor < end:
        next_integer = Q(cursor.floor() + 1)
        if next_integer <= cursor:
            next_integer = cursor + 1
        upper = min(end, next_integer)
        result.append(ClosedInterval(cursor, upper))
        cursor = upper
    return result


def _safe_gate_ids(
    world: ContinuationWorld,
    segment: OpenSegment,
    bracket: ClosedInterval,
) -> tuple[set[str], set[str], dict[str, Any]]:
    """Return IDs not proven impossible over the whole bracket.

    Removing a posting is sound only when exact interval evidence proves that
    no point in the bracket can satisfy that gate.  Ambiguous intervals remain
    candidates and are evaluated at the certified root by the corrected 0.3
    solver.
    """
    state_iv = segment.state_interval(bracket)
    supports: set[str] = set()
    support_reasons: dict[str, str] = {}
    for ident, support in world.supports.items():
        impossible = False
        for field, allowed in support.bounds.items():
            actual = state_iv.get(field)
            if actual is None or actual.intersection(allowed) is None:
                impossible = True
                break
        if not impossible:
            supports.add(ident)
        else:
            support_reasons[ident] = "proven-disjoint-state-interval"

    compatibilities: set[str] = set()
    compatibility_reasons: dict[str, str] = {}
    for ident, compatibility in world.compatibilities.items():
        impossible = False
        for field, expected in compatibility.equals.items():
            actual = state_iv.get(field)
            if actual is None or not actual.contains(expected):
                impossible = True
                break
        if not impossible:
            compatibilities.add(ident)
        else:
            compatibility_reasons[ident] = "expected-value-excluded-by-state-interval"

    audit = {
        "state_interval": {name: value.to_record() for name, value in sorted(state_iv.items())},
        "allowed_support_ids": sorted(supports),
        "excluded_supports": support_reasons,
        "allowed_compatibility_ids": sorted(compatibilities),
        "excluded_compatibilities": compatibility_reasons,
        "soundness_rule": "only exact interval impossibility may remove a posting",
    }
    return supports, compatibilities, audit


def _candidate_relations(
    world: ContinuationWorld,
    segment: OpenSegment,
    bracket: ClosedInterval,
    planner: str,
) -> tuple[list[ContinuationRelation], dict[str, Any], dict[str, Any]]:
    fired = set(segment.fired_relations)
    supports, compatibilities, gate_audit = _safe_gate_ids(world, segment, bracket)
    if planner == "indexed":
        ids, plan = query_interval_index(
            world.interval_index,
            bracket,
            allowed_support_ids=supports,
            allowed_compatibility_ids=compatibilities,
            excluded_relation_ids=fired,
        )
    elif planner == "exhaustive":
        ids, plan = exhaustive_candidates(world.relations, bracket, excluded_relation_ids=fired)
    else:
        raise ValueError("planner must be indexed or exhaustive")
    relation_map = world.relation_map()
    try:
        relations = [relation_map[ident] for ident in ids]
    except KeyError as exc:  # index validation should make this unreachable.
        raise ValueError(f"candidate index references unknown relation {exc.args[0]}") from exc
    return relations, plan, gate_audit


def _certify_relation_on_bracket(
    world: ContinuationWorld,
    segment: OpenSegment,
    relation: ContinuationRelation,
    bracket: ClosedInterval,
    *,
    refine_steps: int | None,
) -> ContinuationCrossing | None:
    active = relation.active_time.intersection(bracket)
    if active is None:
        return None

    proxy = world.interval_world(segment, (relation,))
    coefficients = affine_coefficients(relation.expression, segment)
    if coefficients is None:
        raise UnresolvedContinuation(
            f"relation {relation.id} is not affine in time on segment {segment.id}"
        )
    slope, intercept = coefficients
    if slope == Q(0):
        if intercept == Q(0):
            raise UnresolvedContinuation(
                f"relation {relation.id} is identically zero on segment {segment.id}; isolated event time is undefined"
            )
        return None

    source = certify_crossing(proxy, relation.relation03(), active, refine_steps=refine_steps)
    if not source.accepted:
        return None
    if source.exact_root is None:
        raise UnresolvedContinuation(
            f"relation {relation.id} has an accepted but nonexact bracket; exact continuation ordering is unavailable"
        )
    root = source.exact_root
    certificate = attach_hash({
        "schema": "TOM-CONTINUATION-CROSSING-0.4.1",
        "world_hash": world.content_hash,
        "segment_id": segment.id,
        "segment_hash": segment.content_hash,
        "segment_sequence": segment.sequence,
        "relation_id": relation.id,
        "relation_hash": relation.content_hash,
        "event_id": relation.event_id,
        "priority": relation.priority,
        "fire_policy": relation.fire_policy,
        "exact_root_time": root.to_record(),
        "source_certificate_hash": source.certificate["content_hash"],
        "source_certificate": dict(source.certificate),
        "state_transition": [operation.to_record() for operation in relation.transition],
        "rate_transition": [operation.to_record() for operation in relation.rate_transition],
    })
    return ContinuationCrossing(relation, segment, root, source, certificate)


def bracket_events(
    world: ContinuationWorld,
    segment: OpenSegment,
    bracket: ClosedInterval,
    *,
    after: Q,
    planner: str = "indexed",
    refine_steps: int | None = None,
) -> tuple[list[ContinuationCrossing], dict[str, Any]]:
    if not bracket.subset_of(segment.domain):
        raise ValueError("event bracket lies outside open segment")
    candidates, candidate_plan, gate_audit = _candidate_relations(world, segment, bracket, planner)
    accepted: list[ContinuationCrossing] = []
    rejected_or_absent = 0
    for relation in candidates:
        result = _certify_relation_on_bracket(
            world, segment, relation, bracket, refine_steps=refine_steps,
        )
        if result is None:
            rejected_or_absent += 1
            continue
        if result.exact_root <= after:
            # Strict post-state continuation: a relation fired at the previous
            # boundary cannot fire again merely because it remains zero there.
            rejected_or_absent += 1
            continue
        accepted.append(result)
    accepted.sort(key=event_order_key)
    plan = attach_hash({
        "schema": "TOM-CONTINUATION-BRACKET-PLAN-0.4.1",
        "world_hash": world.content_hash,
        "segment_id": segment.id,
        "segment_hash": segment.content_hash,
        "planner": planner,
        "after_exclusive": after.to_record(),
        "bracket": bracket.to_record(),
        "gate_audit": gate_audit,
        "candidate_plan_hash": candidate_plan["content_hash"],
        "candidate_plan": candidate_plan,
        "candidate_relations": len(candidates),
        "rejected_or_absent": rejected_or_absent,
        "accepted_crossings": len(accepted),
        "accepted_relation_ids": [item.relation.id for item in accepted],
    })
    return accepted, plan


def next_event_set(
    world: ContinuationWorld,
    segment: OpenSegment,
    after: Any | None = None,
    before: Any | None = None,
    *,
    planner: str = "indexed",
    refine_steps: int | None = None,
) -> dict[str, Any]:
    """Find the earliest exact event strictly after ``after``.

    Search proceeds bracket by bracket and stops at the first bracket containing
    an accepted exact root.  This makes candidate work explicit and ensures the
    interval index is used for next-event search rather than merely filtering a
    predeclared segment boundary.
    """
    after_q = segment.start if after is None else Q.from_value(after)
    before_q = segment.horizon if before is None else Q.from_value(before)
    if after_q < segment.start or after_q > segment.horizon:
        raise ValueError("after lies outside open segment")
    if before_q < after_q or before_q > segment.horizon:
        raise ValueError("before lies outside the requested forward interval")

    plans: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    selected: list[ContinuationCrossing] = []
    for bracket in _unit_brackets(after_q, before_q):
        events, plan = bracket_events(
            world,
            segment,
            bracket,
            after=after_q,
            planner=planner,
            refine_steps=refine_steps,
        )
        plans.append(plan)
        unique: list[ContinuationCrossing] = []
        for item in events:
            key = (item.relation.id, item.exact_root.to_text())
            if key not in seen:
                seen.add(key)
                unique.append(item)
        if unique:
            earliest = min(item.exact_root for item in unique)
            selected = [item for item in unique if item.exact_root == earliest]
            selected.sort(key=event_order_key)
            break

    total_candidates = sum(int(plan["candidate_relations"]) for plan in plans)
    if not selected:
        return attach_hash({
            "schema": "TOM-NEXT-CONTINUATION-EVENT-SET-0.4.1",
            "world_hash": world.content_hash,
            "segment_id": segment.id,
            "segment_hash": segment.content_hash,
            "segment_sequence": segment.sequence,
            "after_exclusive": after_q.to_record(),
            "before_inclusive": before_q.to_record(),
            "planner": planner,
            "status": "none",
            "fired_relations_before": list(segment.fired_relations),
            "scanned_brackets": len(plans),
            "total_candidate_relations": total_candidates,
            "plan_hashes": [plan["content_hash"] for plan in plans],
            "plans": plans,
            "events": [],
        })

    event_time = selected[0].exact_root
    relation_ids = [item.relation.id for item in selected]
    fired_after = sorted(set(segment.fired_relations).union(relation_ids))
    return attach_hash({
        "schema": "TOM-NEXT-CONTINUATION-EVENT-SET-0.4.1",
        "world_hash": world.content_hash,
        "segment_id": segment.id,
        "segment_hash": segment.content_hash,
        "segment_sequence": segment.sequence,
        "after_exclusive": after_q.to_record(),
        "before_inclusive": before_q.to_record(),
        "planner": planner,
        "status": "accepted",
        "event_time": event_time.to_record(),
        "simultaneity_basis": "exact equal reduced rational root on the same open segment",
        "event_count": len(selected),
        "event_order": [item.relation.event_id for item in selected],
        "relation_order": relation_ids,
        "relation_hashes": [item.relation.content_hash for item in selected],
        "ordering_rule": ["root_time", "priority", "relation_id", "event_id", "relation_hash"],
        "fired_relations_before": list(segment.fired_relations),
        "fired_relations_after": fired_after,
        "scanned_brackets": len(plans),
        "total_candidate_relations": total_candidates,
        "plan_hashes": [plan["content_hash"] for plan in plans],
        "plans": plans,
        "events": [dict(item.certificate) for item in selected],
    })
