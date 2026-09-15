"""Typed records for the corrective TOM World & Query Kernel 0.4 rebuild.

The rebuilt profile starts from the corrected 0.3 interval implementation and
uses *open continuation segments*.  Segment end times are discovered by the
certified event solver; relations are not allowed to predeclare the next
segment boundary.  This removes the circular/compounding boundary dependency
that made the superseded 0.4.0 line unsuitable as an authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from tom_world03.canonical import require_hash
from tom_world03.expression import validate_expression
from tom_world03.interval import ClosedInterval
from tom_world03.model import Compatibility, IntervalWorld, Relation as Relation03, Support, TransitionOp
from tom_world03.rational import Q

CANONICAL_SEED_SHA256 = "d1417a3136772c0cf3eddcd4962ce07d42cbf87616f7b5bae09fc652d9b807b5"
CORRECTED_V03_ZIP_SHA256 = "a7103ec92596fd54198e4a902f078712cf8eafcdf1e45320bbdc02dd53947278"
CORRECTED_INTERVAL_SHA256 = "ea7b3ff2127e8ee7a696eb45e84ae9efdbca7c10c532617c51888fb13cd39f6d"
REJECTED_PRECORRECTION_INTERVAL_SHA256 = "d6bef5b9704a3e5444d86b76e73f6b90a51fdbbf624a6c4705ed0bc7cdef9d4b"

WORLD_SCHEMA = "TOM-WORLD-PIECEWISE-CONTINUATION-0.4.1"
WORLD_PROFILE = "TOM-WORLD-QUERY-KERNEL-0.4-REBUILT"
OPEN_SEGMENT_KIND = "piecewise-affine-open-segment"
RELATION_KIND = "piecewise-continuation-relation"
FIRE_POLICY = "once"


def _require_content_hash(value: Any, label: str, *, allow_none: bool = False) -> str | None:
    if value is None and allow_none:
        return None
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        raise ValueError(f"{label} must be a sha256: content hash")
    try:
        int(value[7:], 16)
    except ValueError as exc:
        raise ValueError(f"{label} must contain lowercase hexadecimal SHA-256") from exc
    if value[7:] != value[7:].lower():
        raise ValueError(f"{label} must contain lowercase hexadecimal SHA-256")
    return value


def _qmap(value: Any, label: str) -> dict[str, Q]:
    if not isinstance(value, Mapping) or not value:
        raise ValueError(f"{label} must be a nonempty object")
    result: dict[str, Q] = {}
    for key, item in value.items():
        name = str(key)
        if not name:
            raise ValueError(f"{label} contains an empty field name")
        result[name] = Q.from_value(item)
    return result


def qmap_record(value: Mapping[str, Q]) -> dict[str, dict[str, int]]:
    return {name: Q.from_value(value[name]).to_record() for name in sorted(value)}


def _sorted_unique_strings(value: Any, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    items = [str(item) for item in value]
    if any(not item for item in items):
        raise ValueError(f"{label} must not contain an empty value")
    if len(items) != len(set(items)):
        raise ValueError(f"{label} contains duplicates")
    if items != sorted(items):
        raise ValueError(f"{label} must be sorted canonically")
    return tuple(items)


@dataclass(frozen=True, slots=True)
class OpenSegment:
    """An immutable affine continuation valid from ``start`` to the horizon.

    The segment is intentionally *open to future event discovery*: its upper
    bound is the world horizon, not a predeclared event time.  A separate
    content-addressed seal records the realized prefix once the next event is
    certified.
    """

    id: str
    sequence: int
    domain: ClosedInterval
    start_state: Mapping[str, Q]
    rates: Mapping[str, Q]
    fired_relations: tuple[str, ...]
    parent_segment_hash: str | None
    source_event_set_hash: str | None
    source_transition_hash: str | None
    provenance: Mapping[str, Any]
    content_hash: str

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "OpenSegment":
        require_hash(record, label="open segment")
        if record.get("kind") != OPEN_SEGMENT_KIND:
            raise ValueError(f"segment kind must be {OPEN_SEGMENT_KIND}")
        ident = str(record.get("id", ""))
        if not ident:
            raise ValueError("segment id must be nonempty")
        sequence = record.get("sequence")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise ValueError("segment sequence must be a nonnegative integer")
        domain = ClosedInterval.from_value(record.get("domain"))
        if domain.is_point():
            raise ValueError("open segment domain must have positive width")
        start_state = _qmap(record.get("start_state"), "segment start_state")
        rates_raw = record.get("rates")
        if not isinstance(rates_raw, Mapping):
            raise ValueError("segment rates must be an object")
        unknown = sorted(set(map(str, rates_raw)) - set(start_state))
        if unknown:
            raise ValueError("segment rates name fields absent from start_state: " + ", ".join(unknown))
        rates = {name: Q.from_value(rates_raw.get(name, 0)) for name in start_state}
        fired = _sorted_unique_strings(record.get("fired_relations", []), "fired_relations")
        provenance_raw = record.get("provenance", {})
        if not isinstance(provenance_raw, Mapping):
            raise ValueError("segment provenance must be an object")
        parent_hash = _require_content_hash(record.get("parent_segment_hash"), "parent_segment_hash", allow_none=True)
        event_hash = _require_content_hash(record.get("source_event_set_hash"), "source_event_set_hash", allow_none=True)
        transition_hash = _require_content_hash(record.get("source_transition_hash"), "source_transition_hash", allow_none=True)
        if sequence == 0 and any(value is not None for value in (parent_hash, event_hash, transition_hash)):
            raise ValueError("initial open segment must not carry parent/event/transition hashes")
        if sequence > 0 and any(value is None for value in (parent_hash, event_hash, transition_hash)):
            raise ValueError("successor open segment requires parent, event-set, and transition hashes")
        return cls(
            id=ident,
            sequence=sequence,
            domain=domain,
            start_state=start_state,
            rates=rates,
            fired_relations=fired,
            parent_segment_hash=parent_hash,
            source_event_set_hash=event_hash,
            source_transition_hash=transition_hash,
            provenance=dict(provenance_raw),
            content_hash=str(record["content_hash"]),
        )

    @property
    def start(self) -> Q:
        return self.domain.lower

    @property
    def horizon(self) -> Q:
        return self.domain.upper

    def require_time(self, time: Any) -> Q:
        q = Q.from_value(time)
        if not self.domain.contains(q):
            raise ValueError(f"time {q} is outside segment {self.id} domain {self.domain}")
        return q

    def state_at(self, time: Any) -> dict[str, Q]:
        q = self.require_time(time)
        delta = q - self.start
        return {name: self.start_state[name] + self.rates[name] * delta for name in self.start_state}

    def field_rate(self, name: str) -> Q:
        try:
            return self.rates[name]
        except KeyError as exc:
            raise ValueError(f"segment {self.id} has no field {name}") from exc

    def field_affine(self, name: str) -> tuple[Q, Q]:
        try:
            rate = self.rates[name]
            start_value = self.start_state[name]
        except KeyError as exc:
            raise ValueError(f"segment {self.id} has no field {name}") from exc
        # y(t) = start_value + rate*(t-start) = rate*t + intercept.
        return rate, start_value - rate * self.start

    def field_interval(self, name: str, time: ClosedInterval) -> ClosedInterval:
        if not time.subset_of(self.domain):
            raise ValueError("requested interval is outside open segment domain")
        if name not in self.start_state:
            raise ValueError(f"segment {self.id} has no field {name}")
        return ClosedInterval.hull((self.state_at(time.lower)[name], self.state_at(time.upper)[name]))

    def state_interval(self, time: ClosedInterval) -> dict[str, ClosedInterval]:
        return {name: self.field_interval(name, time) for name in self.start_state}

    def to_record(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "id": self.id,
            "kind": OPEN_SEGMENT_KIND,
            "sequence": self.sequence,
            "domain": self.domain.to_record(),
            "start_state": qmap_record(self.start_state),
            "rates": qmap_record(self.rates),
            "fired_relations": list(self.fired_relations),
            "parent_segment_hash": self.parent_segment_hash,
            "source_event_set_hash": self.source_event_set_hash,
            "source_transition_hash": self.source_transition_hash,
        }
        if self.provenance:
            record["provenance"] = dict(self.provenance)
        record["content_hash"] = self.content_hash
        return record


@dataclass(frozen=True, slots=True)
class ContinuationRelation:
    id: str
    priority: int
    expression: Mapping[str, Any]
    support_id: str
    compatibility_id: str
    active_time: ClosedInterval
    event_id: str
    transition: tuple[TransitionOp, ...]
    rate_transition: tuple[TransitionOp, ...]
    fire_policy: str
    content_hash: str

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "ContinuationRelation":
        require_hash(record, label="continuation relation")
        if record.get("kind") != RELATION_KIND:
            raise ValueError(f"relation kind must be {RELATION_KIND}")
        if record.get("relation_interface") != "SDF0@Def":
            raise ValueError("continuation relation must declare relation_interface SDF0@Def")
        if record.get("domain") != OPEN_SEGMENT_KIND:
            raise ValueError(f"continuation relation domain must be {OPEN_SEGMENT_KIND}")
        if record.get("codomain") != "exact-rational-residual":
            raise ValueError("continuation relation codomain must be exact-rational-residual")
        if not isinstance(record.get("zero_locus"), str) or not str(record.get("zero_locus")).strip():
            raise ValueError("continuation relation requires a nonempty zero_locus declaration")
        if "continuation_until" in record:
            raise ValueError("continuation_until is forbidden: segment boundaries are solver results")
        ident = str(record.get("id", ""))
        event_id = str(record.get("event_id", ""))
        if not ident or not event_id:
            raise ValueError("relation id and event_id must be nonempty")
        priority = record.get("priority", 0)
        if isinstance(priority, bool) or not isinstance(priority, int):
            raise ValueError("relation priority must be an integer")
        expression = record.get("expression")
        if not isinstance(expression, Mapping):
            raise ValueError("relation expression must be an object")
        validate_expression(expression)
        transition_raw = record.get("transition", [])
        rate_raw = record.get("rate_transition", [])
        if not isinstance(transition_raw, list) or not isinstance(rate_raw, list):
            raise ValueError("transition and rate_transition must be arrays")
        fire_policy = str(record.get("fire_policy", ""))
        if fire_policy != FIRE_POLICY:
            raise ValueError(f"0.4.1 fire_policy must be {FIRE_POLICY}")
        support_id = str(record.get("support_id", ""))
        compatibility_id = str(record.get("compatibility_id", ""))
        if not support_id or not compatibility_id:
            raise ValueError("continuation relation requires support_id and compatibility_id")
        return cls(
            id=ident,
            priority=priority,
            expression=dict(expression),
            support_id=support_id,
            compatibility_id=compatibility_id,
            active_time=ClosedInterval.from_value(record.get("active_time")),
            event_id=event_id,
            transition=tuple(TransitionOp.from_record(item) for item in transition_raw),
            rate_transition=tuple(TransitionOp.from_record(item) for item in rate_raw),
            fire_policy=fire_policy,
            content_hash=str(record["content_hash"]),
        )

    def relation03(self) -> Relation03:
        return Relation03(
            id=self.id,
            priority=self.priority,
            expression=self.expression,
            support_id=self.support_id,
            compatibility_id=self.compatibility_id,
            active_time=self.active_time,
            event_id=self.event_id,
            transition=self.transition,
            content_hash=self.content_hash,
        )


@dataclass(frozen=True, slots=True)
class ContinuationWorld:
    schema: str
    profile: str
    seed_sha256: str
    corrected_v03_zip_sha256: str
    corrected_interval_sha256: str
    horizon: ClosedInterval
    initial_segment: OpenSegment
    supports: Mapping[str, Support]
    compatibilities: Mapping[str, Compatibility]
    relations: tuple[ContinuationRelation, ...]
    interval_index: Mapping[str, Any]
    solver: Mapping[str, Any]
    persistence: Mapping[str, Any]
    content_hash: str

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "ContinuationWorld":
        require_hash(record, label="0.4.1 continuation world")
        if record.get("schema") != WORLD_SCHEMA:
            raise ValueError(f"world schema must be {WORLD_SCHEMA}")
        if record.get("profile") != WORLD_PROFILE:
            raise ValueError(f"world profile must be {WORLD_PROFILE}")
        if record.get("seed_sha256") != CANONICAL_SEED_SHA256:
            raise ValueError("world is not bound to the canonical TOM seed")
        lineage = record.get("corrected_v03_baseline")
        if not isinstance(lineage, Mapping):
            raise ValueError("world requires corrected_v03_baseline")
        if lineage.get("archive_sha256") != CORRECTED_V03_ZIP_SHA256:
            raise ValueError("world is not based on the corrected 0.3 archive")
        if lineage.get("interval_py_sha256") != CORRECTED_INTERVAL_SHA256:
            raise ValueError("world does not bind the corrected 0.3 interval implementation")
        if lineage.get("rejected_precorrection_interval_sha256") != REJECTED_PRECORRECTION_INTERVAL_SHA256:
            raise ValueError("world does not declare the rejected pre-correction interval hash")

        horizon = ClosedInterval.from_value(record.get("horizon"))
        if horizon.is_point():
            raise ValueError("world horizon must have positive width")
        initial = OpenSegment.from_record(record.get("initial_segment", {}))
        if initial.sequence != 0:
            raise ValueError("initial segment sequence must be zero")
        if initial.domain != horizon:
            raise ValueError("initial open segment must extend across the complete world horizon")
        if initial.fired_relations:
            raise ValueError("initial segment must have no fired relations")

        supports_raw = record.get("supports", [])
        compat_raw = record.get("compatibilities", [])
        relations_raw = record.get("relations", [])
        if not all(isinstance(value, list) for value in (supports_raw, compat_raw, relations_raw)):
            raise ValueError("supports, compatibilities, and relations must be arrays")
        support_objects = [Support.from_record(item) for item in supports_raw]
        compatibility_objects = [Compatibility.from_record(item) for item in compat_raw]
        relation_objects = [ContinuationRelation.from_record(item) for item in relations_raw]
        supports = {item.id: item for item in support_objects}
        compatibilities = {item.id: item for item in compatibility_objects}
        if len(supports) != len(support_objects):
            raise ValueError("duplicate support id")
        if len(compatibilities) != len(compatibility_objects):
            raise ValueError("duplicate compatibility id")
        if len({item.id for item in relation_objects}) != len(relation_objects):
            raise ValueError("duplicate relation id")
        if len({item.event_id for item in relation_objects}) != len(relation_objects):
            raise ValueError("duplicate event id")
        for relation in relation_objects:
            if relation.support_id not in supports:
                raise ValueError(f"relation {relation.id} references unknown support")
            if relation.compatibility_id not in compatibilities:
                raise ValueError(f"relation {relation.id} references unknown compatibility")
            if relation.active_time.intersection(horizon) is None:
                raise ValueError(f"relation {relation.id} active interval misses world horizon")

        interval_index = record.get("interval_index")
        solver = record.get("solver", {})
        persistence = record.get("persistence", {})
        if not isinstance(interval_index, Mapping):
            raise ValueError("world interval_index must be an object")
        if not isinstance(solver, Mapping) or not isinstance(persistence, Mapping):
            raise ValueError("solver and persistence profiles must be objects")
        if solver.get("arithmetic") != "corrected 0.3 exact reduced rationals and closed intervals":
            raise ValueError("solver arithmetic profile must explicitly bind the corrected 0.3 interval semantics")
        if solver.get("event_time_policy") != "isolated exact affine roots only":
            raise ValueError("solver event_time_policy must be isolated exact affine roots only")
        if solver.get("fire_policy") != FIRE_POLICY:
            raise ValueError("solver fire_policy must be once")
        for name, default, upper in (("refine_steps", 24, 128), ("max_refine_steps", 128, 128),
                                     ("max_event_sets", 64, 1024), ("profile_max_event_sets", 1024, 1024)):
            value = solver.get(name, default)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > upper:
                raise ValueError(f"solver {name} must be an integer in 0..{upper}")
        if int(solver.get("refine_steps", 24)) > int(solver.get("max_refine_steps", 128)):
            raise ValueError("solver refine_steps exceeds max_refine_steps")
        if int(solver.get("max_event_sets", 64)) > int(solver.get("profile_max_event_sets", 1024)):
            raise ValueError("solver max_event_sets exceeds profile_max_event_sets")
        if persistence.get("finalization") != "explicit horizon seal after no later event":
            raise ValueError("persistence finalization policy mismatch")
        mutable_paths = persistence.get("mutable_paths")
        if mutable_paths != ["HEAD"]:
            raise ValueError("only HEAD may be mutable in the continuation persistence profile")
        world = cls(
            schema=str(record["schema"]),
            profile=str(record["profile"]),
            seed_sha256=str(record["seed_sha256"]),
            corrected_v03_zip_sha256=str(lineage["archive_sha256"]),
            corrected_interval_sha256=str(lineage["interval_py_sha256"]),
            horizon=horizon,
            initial_segment=initial,
            supports=supports,
            compatibilities=compatibilities,
            relations=tuple(relation_objects),
            interval_index=dict(interval_index),
            solver=dict(solver),
            persistence=dict(persistence),
            content_hash=str(record["content_hash"]),
        )
        from .index import validate_interval_index
        validate_interval_index(world.interval_index, world.relations, seed_sha256=world.seed_sha256)
        return world

    def relation_map(self) -> dict[str, ContinuationRelation]:
        return {relation.id: relation for relation in self.relations}

    def interval_world(
        self,
        segment: OpenSegment,
        relations: Sequence[ContinuationRelation],
    ) -> IntervalWorld:
        # This view intentionally reuses the corrected 0.3 certifier and its
        # exact rational interval semantics.  The world hash remains the 0.4.1
        # world identity so crossing certificates bind to the actual authority.
        return IntervalWorld(
            schema="TOM-WORLD-INTERVAL-EVENTS-0.3",
            seed_sha256=self.seed_sha256,
            trajectory=segment,  # structural TrajectoryLike contract
            supports=self.supports,
            compatibilities=self.compatibilities,
            relations=tuple(item.relation03() for item in relations),
            solver=self.solver,
            content_hash=self.content_hash,
        )
