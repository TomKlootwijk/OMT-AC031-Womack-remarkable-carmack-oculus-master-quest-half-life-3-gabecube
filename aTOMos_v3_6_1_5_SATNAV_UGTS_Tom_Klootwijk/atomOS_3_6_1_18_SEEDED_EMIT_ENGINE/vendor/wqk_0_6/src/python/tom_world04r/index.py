"""Immutable exact-rational interval candidate index for the rebuilt 0.4 line."""
from __future__ import annotations

import hashlib
from typing import Any, Iterable, Mapping, Sequence

from tom_world03.canonical import attach_hash, canonical_bytes, require_hash
from tom_world03.interval import ClosedInterval
from tom_world03.rational import Q

from .model import ContinuationRelation

INDEX_SCHEMA = "TOM-RELATION-INTERVAL-INDEX-0.4.1"
INDEX_VERSION = "0.4.1"
PLAN_SCHEMA = "TOM-INTERVAL-CANDIDATE-PLAN-0.4.1"


def _relation_set(relations: Iterable[ContinuationRelation]) -> list[dict[str, Any]]:
    return [
        {
            "id": relation.id,
            "content_hash": relation.content_hash,
            "active_time": relation.active_time.to_record(),
            "support_id": relation.support_id,
            "compatibility_id": relation.compatibility_id,
            "fire_policy": relation.fire_policy,
        }
        for relation in sorted(relations, key=lambda item: item.id)
    ]


def build_interval_index(
    relations: Iterable[ContinuationRelation],
    *,
    seed_sha256: str,
) -> dict[str, Any]:
    relation_list = list(relations)
    entries = [
        {
            "lower": relation.active_time.lower.to_record(),
            "upper": relation.active_time.upper.to_record(),
            "relation_id": relation.id,
            "relation_hash": relation.content_hash,
            "support_id": relation.support_id,
            "compatibility_id": relation.compatibility_id,
            "fire_policy": relation.fire_policy,
        }
        for relation in relation_list
    ]
    entries.sort(key=lambda item: (
        Q.from_value(item["lower"]).as_fraction(),
        Q.from_value(item["upper"]).as_fraction(),
        str(item["relation_id"]),
        str(item["relation_hash"]),
    ))
    postings_support: dict[str, list[str]] = {}
    postings_compatibility: dict[str, list[str]] = {}
    for relation in relation_list:
        postings_support.setdefault(relation.support_id, []).append(relation.id)
        postings_compatibility.setdefault(relation.compatibility_id, []).append(relation.id)
    for mapping in (postings_support, postings_compatibility):
        for key in mapping:
            mapping[key].sort()
    relation_set = _relation_set(relation_list)
    relation_set_hash = "sha256:" + hashlib.sha256(canonical_bytes(relation_set)).hexdigest()
    return attach_hash({
        "schema": INDEX_SCHEMA,
        "version": INDEX_VERSION,
        "seed_sha256": seed_sha256,
        "relation_count": len(relation_list),
        "relation_set_hash": relation_set_hash,
        "algorithm": "start-sorted exact closed-interval overlap with safe support/compatibility postings",
        "ordering": ["active_lower", "active_upper", "relation_id", "relation_hash"],
        "entries": entries,
        "by_support": {key: postings_support[key] for key in sorted(postings_support)},
        "by_compatibility": {key: postings_compatibility[key] for key in sorted(postings_compatibility)},
    })


def validate_interval_index(
    index: Mapping[str, Any],
    relations: Sequence[ContinuationRelation],
    *,
    seed_sha256: str,
) -> None:
    require_hash(index, label="0.4.1 interval index")
    if index.get("schema") != INDEX_SCHEMA or index.get("version") != INDEX_VERSION:
        raise ValueError("unsupported 0.4.1 interval index schema/version")
    if index.get("seed_sha256") != seed_sha256:
        raise ValueError("interval index seed binding mismatch")
    expected = build_interval_index(relations, seed_sha256=seed_sha256)
    if canonical_bytes(index) != canonical_bytes(expected):
        raise ValueError("interval index does not match the relation set")


def _prefix_limit(entries: Sequence[Mapping[str, Any]], upper: Q) -> int:
    lo, hi = 0, len(entries)
    while lo < hi:
        mid = (lo + hi) // 2
        if Q.from_value(entries[mid]["lower"]) <= upper:
            lo = mid + 1
        else:
            hi = mid
    return lo


def query_interval_index(
    index: Mapping[str, Any],
    interval: ClosedInterval,
    *,
    allowed_support_ids: set[str] | None = None,
    allowed_compatibility_ids: set[str] | None = None,
    excluded_relation_ids: set[str] | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """Return a complete candidate set for one exact query bracket.

    Posting filters are used only with caller-supplied *safe* allowed-ID sets.
    The solver constructs those sets conservatively from exact state intervals:
    a support or compatibility ID is removed only when it is impossible over the
    whole bracket.  This preserves no-false-negative semantics.
    """

    require_hash(index, label="0.4.1 interval index")
    entries_raw = index.get("entries")
    if not isinstance(entries_raw, list):
        raise ValueError("interval index entries must be an array")
    entries: list[Mapping[str, Any]] = []
    for item in entries_raw:
        if not isinstance(item, Mapping):
            raise ValueError("interval index entry must be an object")
        entries.append(item)
    excluded = excluded_relation_ids or set()
    limit = _prefix_limit(entries, interval.upper)
    selected: list[str] = []
    rejected_upper = 0
    rejected_support = 0
    rejected_compatibility = 0
    rejected_fired = 0
    for item in entries[:limit]:
        if Q.from_value(item["upper"]) < interval.lower:
            rejected_upper += 1
            continue
        relation_id = str(item["relation_id"])
        if relation_id in excluded:
            rejected_fired += 1
            continue
        support_id = str(item["support_id"])
        if allowed_support_ids is not None and support_id not in allowed_support_ids:
            rejected_support += 1
            continue
        compatibility_id = str(item["compatibility_id"])
        if allowed_compatibility_ids is not None and compatibility_id not in allowed_compatibility_ids:
            rejected_compatibility += 1
            continue
        selected.append(relation_id)
    selected = sorted(set(selected))
    plan = attach_hash({
        "schema": PLAN_SCHEMA,
        "planner": "indexed",
        "index_hash": index["content_hash"],
        "query_interval": interval.to_record(),
        "relation_count": int(index["relation_count"]),
        "lower_endpoint_prefix": limit,
        "rejected_by_upper_endpoint": rejected_upper,
        "allowed_support_ids": None if allowed_support_ids is None else sorted(allowed_support_ids),
        "rejected_by_support": rejected_support,
        "allowed_compatibility_ids": None if allowed_compatibility_ids is None else sorted(allowed_compatibility_ids),
        "rejected_by_compatibility": rejected_compatibility,
        "excluded_fired_relations": sorted(excluded),
        "rejected_as_already_fired": rejected_fired,
        "candidate_count": len(selected),
        "candidate_ids": selected,
        "completeness_rule": "closed overlap plus only proven-impossible support/compatibility filters",
    })
    return selected, plan


def exhaustive_candidates(
    relations: Sequence[ContinuationRelation],
    interval: ClosedInterval,
    *,
    excluded_relation_ids: set[str] | None = None,
) -> tuple[list[str], dict[str, Any]]:
    excluded = excluded_relation_ids or set()
    selected = sorted(relation.id for relation in relations if relation.id not in excluded)
    overlap = sorted(
        relation.id for relation in relations
        if relation.id not in excluded and relation.active_time.intersection(interval) is not None
    )
    plan = attach_hash({
        "schema": PLAN_SCHEMA,
        "planner": "exhaustive",
        "index_hash": None,
        "query_interval": interval.to_record(),
        "relation_count": len(relations),
        "lower_endpoint_prefix": len(relations),
        "rejected_by_upper_endpoint": 0,
        "allowed_support_ids": None,
        "rejected_by_support": 0,
        "allowed_compatibility_ids": None,
        "rejected_by_compatibility": 0,
        "excluded_fired_relations": sorted(excluded),
        "rejected_as_already_fired": len(excluded.intersection({r.id for r in relations})),
        "candidate_count": len(selected),
        "candidate_ids": selected,
        "overlap_count_after_exhaustive_test": len(overlap),
        "overlap_ids_after_exhaustive_test": overlap,
        "completeness_rule": "every unfired relation enters the exhaustive solver loop",
    })
    return selected, plan
