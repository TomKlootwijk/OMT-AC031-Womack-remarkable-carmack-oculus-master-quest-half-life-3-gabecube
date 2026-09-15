"""Exact affine plane events and atomic world/hinge continuation for R16.

Adapted mathematical architecture from TOM WQK 0.4.1; this implementation is
an explicitly bounded aTOMos profile, not an imported TOMAGI instruction set.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from fractions import Fraction
import hashlib
from typing import Any, Mapping

from atomos_hinge import (Engine, LENGTH, canonical_bytes, pack_document,
                         unpack_document, UnsupportedOperation)

PROFILE = "ATOMOS-EXACT-AFFINE-EVENTS-R1"
SESSION = "ATOMOS-EXACT-AFFINE-SESSION-R1"


class EventDomainError(ValueError):
    pass


class UnresolvedEvent(EventDomainError):
    pass


class EventConflict(EventDomainError):
    pass


def rational(value: Any) -> Fraction:
    """No floating/coercing path: rational record limbs must be actual ints."""
    if type(value) is int:
        return Fraction(value)
    if isinstance(value, Fraction):
        return value
    if isinstance(value, dict) and set(value) == {"num", "den"}:
        n, d = value["num"], value["den"]
        if type(n) is not int or type(d) is not int or d <= 0:
            raise ValueError("rational limbs must be integers with positive denominator")
        return Fraction(n, d)
    raise TypeError("exact event inputs require int, Fraction or integer num/den records")


def _keys(value, expected, name):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError(name + " fields differ from the declared profile")


def _interval(value):
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError("interval requires exactly two rational endpoints")
    lo, hi = map(rational, value)
    if lo > hi:
        raise ValueError("inverted exact interval")
    return [lo, hi]


def _name(value):
    if not isinstance(value, str) or not value:
        raise ValueError("nonempty nominal identity required")
    return value


def _hash(record):
    return "sha256:" + hashlib.sha256(canonical_bytes(record)).hexdigest()


def seal(record):
    """Attach a deterministic byte receipt; this is not a semantic proof."""
    body = copy.deepcopy(record)
    body.pop("content_hash", None)
    return {**body, "content_hash": _hash(body)}


def _verify_hash(record):
    if not isinstance(record, dict) or record.get("content_hash") != seal(record)["content_hash"]:
        raise ValueError("certificate content hash mismatch")


@dataclass(frozen=True)
class EventResult:
    status: str
    epoch: dict
    transition: dict | None = None
    reason: str = ""


class EventEngine:
    """Serial immutable-epoch event engine, with semantic replay on admission."""

    def __init__(self, profile: dict):
        p = copy.deepcopy(profile)
        _keys(p, {"profile", "frame", "time_convention", "horizon", "fields", "hinges", "relations", "max_event_sets"}, "event profile")
        if p["profile"] != PROFILE:
            raise ValueError("unsupported event profile")
        _name(p["frame"])
        _name(p["time_convention"])
        p["horizon"] = _interval(p["horizon"])
        if p["horizon"][0] == p["horizon"][1]:
            raise ValueError("initial event horizon must have positive width")
        if type(p["max_event_sets"]) is not int or not 0 <= p["max_event_sets"] <= 4096:
            raise ValueError("event-set budget outside 0..4096")
        if not isinstance(p["fields"], dict) or not 1 <= len(p["fields"]) <= 4096:
            raise ValueError("field count outside 1..4096")
        for name, field in p["fields"].items():
            _name(name)
            _keys(field, {"dimension", "initial", "rate"}, "field")
            dim = field["dimension"]
            if not isinstance(dim, (list, tuple)) or len(dim) != 7 or any(type(x) is not int for x in dim):
                raise ValueError("field dimension must contain seven integer SI exponents")
            field["dimension"] = list(dim)
            field["initial"], field["rate"] = rational(field["initial"]), rational(field["rate"])
        if not isinstance(p["hinges"], dict) or not 1 <= len(p["hinges"]) <= 4096:
            raise ValueError("hinge count outside 1..4096")
        hinges, bindings = {}, {}
        for name, seed in p["hinges"].items():
            _name(name)
            hinge = Engine(seed)
            binding = hinge.affine_plane_binding()
            if binding["frame"] != p["frame"]:
                raise ValueError("hinge plane and event world frame differ")
            hinges[name], bindings[name] = hinge, binding
        if not isinstance(p["relations"], list) or len(p["relations"]) > 4096:
            raise ValueError("relation count outside 0..4096")
        ids = set()
        for r in p["relations"]:
            _keys(r, {"id", "hinge", "point_fields", "active", "priority", "equals", "support", "state_updates", "rate_updates"}, "relation")
            ident = _name(r["id"])
            if ident in ids:
                raise ValueError("duplicate relation identity")
            ids.add(ident)
            if r["hinge"] not in hinges:
                raise ValueError("relation names unknown hinge")
            names = r["point_fields"]
            if not isinstance(names, (list, tuple)) or len(names) != 3:
                raise ValueError("plane relation requires three coordinate field bindings")
            for name in names:
                if name not in p["fields"] or tuple(p["fields"][name]["dimension"]) != LENGTH:
                    raise ValueError("plane coordinate must bind a declared length field")
            r["point_fields"] = list(names)
            r["active"] = _interval(r["active"])
            if type(r["priority"]) is not int:
                raise ValueError("event priority must be an integer")
            for kind in ("equals", "support"):
                if not isinstance(r[kind], dict):
                    raise ValueError("gate must be a field mapping")
                for name, value in r[kind].items():
                    if name not in p["fields"]:
                        raise ValueError("gate names unknown field")
                    r[kind][name] = rational(value) if kind == "equals" else _interval(value)
            for kind in ("state_updates", "rate_updates"):
                if not isinstance(r[kind], list):
                    raise ValueError("updates must be a list")
                for update in r[kind]:
                    _keys(update, {"field", "op", "value"}, "update")
                    if update["field"] not in p["fields"] or update["op"] not in ("set", "add", "xor"):
                        raise ValueError("unsupported update field or operation")
                    update["value"] = rational(update["value"])
                    if update["op"] == "xor":
                        dimension = p["fields"][update["field"]]["dimension"]
                        if any(dimension) or kind != "state_updates" or update["value"].denominator != 1 or update["value"] < 0:
                            raise ValueError("xor is limited to nonnegative dimensionless integer state")
        p["relations"].sort(key=lambda r: r["id"])
        self._profile, self._profile_hash = p, _hash(p)
        self._hinges, self._bindings = hinges, bindings
        self._relations = {r["id"]: r for r in p["relations"]}
        self._history, self._transitions, self._accepted = [], [], {}
        self._event_sets, self._finalized = 0, False
        self._epoch = self._make_epoch(p["horizon"][0],
            {k: f["initial"] for k, f in p["fields"].items()},
            {k: f["rate"] for k, f in p["fields"].items()}, [], 0, None, None, hinges)

    @property
    def profile(self):
        return copy.deepcopy(self._profile)

    @property
    def epoch(self):
        return copy.deepcopy(self._epoch)

    @property
    def history(self):
        return copy.deepcopy(self._history)

    @property
    def transitions(self):
        return copy.deepcopy(self._transitions)

    @property
    def finalized(self):
        return self._finalized

    def hinge(self, name):
        """A complete independent clone; no caller gets mutable owned state."""
        h = self._hinges[name]
        return Engine(h.seed, h.state)

    def _make_epoch(self, start, state, rates, fired, sequence, parent, event, hinges):
        return seal({"profile": PROFILE, "profile_hash": self._profile_hash,
                     "kind": "terminal_state" if start == self._profile["horizon"][1] else "open_affine_epoch",
                     "sequence": sequence, "start": start, "horizon": self._profile["horizon"][1],
                     "state": state, "rates": rates, "fired_relations": sorted(fired),
                     "parent_epoch": parent, "source_certificate": event,
                     "hinge_states": {k: h.state for k, h in sorted(hinges.items())}})

    def state_at(self, time):
        t = rational(time)
        if not self._epoch["start"] <= t <= self._epoch["horizon"]:
            raise EventDomainError("time is outside the current epoch")
        return {k: x + self._epoch["rates"][k] * (t - self._epoch["start"])
                for k, x in self._epoch["state"].items()}

    def _gates_impossible(self, relation, lower, upper):
        a, b = self.state_at(lower), self.state_at(upper)
        for name, allowed in relation["support"].items():
            lo, hi = sorted((a[name], b[name]))
            if hi < allowed[0] or allowed[1] < lo:
                return True
        for name, value in relation["equals"].items():
            lo, hi = sorted((a[name], b[name]))
            if not lo <= value <= hi:
                return True
        return False

    def _candidate(self, r):
        e, binding = self._epoch, self._bindings[r["hinge"]]
        lower, upper = max(e["start"], r["active"][0]), min(e["horizon"], r["active"][1])
        if lower > upper or upper <= e["start"] or self._gates_impossible(r, lower, upper):
            return None
        origin = tuple(e["state"][k] for k in r["point_fields"])
        velocity = tuple(e["rates"][k] for k in r["point_fields"])
        slope = sum((n * v for n, v in zip(binding["normal"], velocity)), Fraction(0))
        value = sum((n * x for n, x in zip(binding["normal"], origin)), Fraction(0)) - binding["offset"]
        if slope == 0:
            if value == 0:
                raise UnresolvedEvent("identically zero active plane has no isolated event: " + r["id"])
            return None
        root = e["start"] - value / slope
        if not e["start"] < root <= e["horizon"] or not lower <= root <= upper:
            return None
        state = self.state_at(root)
        if any(state[k] != v for k, v in r["equals"].items()):
            return None
        if any(not bounds[0] <= state[k] <= bounds[1] for k, bounds in r["support"].items()):
            return None
        return {"relation": r["id"], "hinge": r["hinge"], "priority": r["priority"],
                "point_fields": list(r["point_fields"]), "root": root, "slope": slope,
                "value_at_epoch_start": value, "plane_seed_hash": binding["seed_hash"],
                "origin": list(origin), "velocity": list(velocity),
                "point_at_root": [state[k] for k in r["point_fields"]],
                "pre_side_raw": -((slope > 0) - (slope < 0)),
                "post_side_raw": (slope > 0) - (slope < 0)}

    def next_event_set(self):
        if self._finalized:
            raise EventDomainError("world is already finalized")
        candidates = []
        for relation in self._profile["relations"]:
            if relation["id"] not in self._epoch["fired_relations"]:
                candidate = self._candidate(relation)
                if candidate is not None:
                    candidates.append(candidate)
        candidates.sort(key=lambda c: (c["root"], c["priority"], c["relation"]))
        root = candidates[0]["root"] if candidates else None
        selected = [c for c in candidates if c["root"] == root]
        return seal({"profile": "ATOMOS-AFFINE-EVENT-CERTIFICATE-R1",
                     "profile_hash": self._profile_hash, "epoch_hash": self._epoch["content_hash"],
                     "epoch_sequence": self._epoch["sequence"], "after_exclusive": self._epoch["start"],
                     "before_inclusive": self._epoch["horizon"], "status": "EVENT" if selected else "NONE",
                     "event_time": root, "events": selected, "all_candidates": candidates,
                     "ordering": ["exact_root", "priority", "relation_identity"]})

    def _apply_updates(self, source, relations, kind):
        grouped = {}
        for relation in relations:
            for update in relation[kind]:
                grouped.setdefault(update["field"], []).append(update)
        result = dict(source)
        for field, updates in grouped.items():
            modes = {u["op"] for u in updates}
            if len(modes) != 1:
                raise EventConflict("simultaneous mixed update modes: " + field)
            mode, values = next(iter(modes)), [u["value"] for u in updates]
            if mode == "set":
                if any(x != values[0] for x in values):
                    raise EventConflict("unequal simultaneous sets: " + field)
                result[field] = values[0]
            elif mode == "add":
                result[field] = source[field] + sum(values, Fraction(0))
            else:
                if source[field].denominator != 1 or source[field] < 0:
                    raise EventConflict("xor prestate is not a nonnegative integer: " + field)
                word = source[field].numerator
                for value in values:
                    word ^= value.numerator
                result[field] = Fraction(word)
        return result

    def apply_event_set(self, certificate) -> EventResult:
        """Recompute semantics before any state effect; duplicate bytes hold."""
        try:
            _verify_hash(certificate)
            receipt, encoded = certificate["content_hash"], canonical_bytes(certificate)
            if receipt in self._accepted:
                if encoded != self._accepted[receipt]:
                    raise ValueError("receipt reused with changed bytes")
                return EventResult("DUPLICATE", self.epoch)
            expected = self.next_event_set()
            if encoded != canonical_bytes(expected):
                raise ValueError("certificate is not the complete earliest event set of the current epoch")
            is_event = certificate["status"] == "EVENT"
            if is_event and self._event_sets >= self._profile["max_event_sets"]:
                return EventResult("RESOURCE_LIMIT", self.epoch, reason="event-set budget exhausted")
            root = certificate["event_time"] if is_event else self._epoch["horizon"]
            before = self.state_at(root)
            relations = [self._relations[c["relation"]] for c in certificate["events"]]
            after = self._apply_updates(before, relations, "state_updates")
            rates = self._apply_updates(self._epoch["rates"], relations, "rate_updates")
            hinges = {k: Engine(h.seed, h.state) for k, h in self._hinges.items()}
            groups = {}
            for crossing in certificate["events"]:
                groups.setdefault(crossing["hinge"], []).append(crossing)
            traces = {}
            for name, crossings in sorted(groups.items()):
                first = crossings[0]
                path_keys = ("origin", "velocity", "root", "plane_seed_hash")
                if any(any(c[k] != first[k] for k in path_keys) for c in crossings[1:]):
                    raise EventConflict("one simultaneous hinge has different trajectory bindings: " + name)
                result = hinges[name].step_certified_crossing(receipt + ":" + name,
                    origin=first["origin"], velocity=first["velocity"], epoch=self._epoch["start"],
                    time=root, frame=self._profile["frame"], source_epoch=self._epoch["content_hash"],
                    sequence=self._epoch["sequence"])
                if result.status != "VALUE":
                    raise EventDomainError("certified hinge refused event: " + result.status + ": " + result.reason)
                traces[name] = {"contributors": [c["relation"] for c in crossings], **result.trace}
            fired = sorted(set(self._epoch["fired_relations"]) | {r["id"] for r in relations})
            terminal = root == self._epoch["horizon"]
            successor = self._make_epoch(root, after, rates, fired, self._epoch["sequence"] + 1,
                                         self._epoch["content_hash"], receipt, hinges)
            transition = seal({"profile": "ATOMOS-AFFINE-TRANSITION-R1", "certificate_hash": receipt,
                "from_epoch": self._epoch["content_hash"], "to_epoch": successor["content_hash"],
                "time": root, "realized_interval": [self._epoch["start"], root],
                "relations": [r["id"] for r in relations], "pre_state": before, "post_state": after,
                "pre_rates": self._epoch["rates"], "post_rates": rates,
                "hinge_traces": traces, "terminal": terminal, "event": is_event})
            # No externally visible mutation occurred before this publication.
            history = self._history + [copy.deepcopy(certificate)]
            transitions = self._transitions + [transition]
            accepted = {**self._accepted, receipt: encoded}
            event_sets = self._event_sets + int(is_event)
            self._hinges, self._epoch, self._finalized = hinges, successor, terminal
            self._event_sets, self._history, self._transitions, self._accepted = event_sets, history, transitions, accepted
            return EventResult("APPLIED" if is_event else "FINALIZED", self.epoch, copy.deepcopy(transition))
        except UnresolvedEvent as error:
            return EventResult("UNKNOWN", self.epoch, reason=str(error))
        except EventDomainError as error:
            return EventResult("UNDEFINED", self.epoch, reason=str(error))
        except (TypeError, ValueError, KeyError, IndexError) as error:
            return EventResult("INVALID", self.epoch, reason=str(error))

    def advance(self):
        try:
            certificate = self.next_event_set()
        except UnresolvedEvent as error:
            return EventResult("UNKNOWN", self.epoch, reason=str(error))
        return self.apply_event_set(certificate)

    def run(self):
        results = []
        while not self.finalized:
            result = self.advance()
            results.append(result)
            if result.status not in ("APPLIED", "FINALIZED"):
                break
        return results

    def pack(self):
        return pack_document({"profile": SESSION, "definition": self.profile,
                              "certificates": self.history, "transitions": self.transitions,
                              "epoch": self.epoch, "finalized": self.finalized})

    @classmethod
    def unpack(cls, payload):
        document = unpack_document(payload)
        _keys(document, {"profile", "definition", "certificates", "transitions", "epoch", "finalized"}, "event session")
        if document["profile"] != SESSION or not isinstance(document["certificates"], list):
            raise ValueError("unsupported event session")
        engine = cls(document["definition"])
        for certificate in document["certificates"]:
            result = engine.apply_event_set(certificate)
            if result.status not in ("APPLIED", "FINALIZED"):
                raise ValueError("session semantic replay failed: " + result.status + ": " + result.reason)
        if (canonical_bytes(engine.epoch) != canonical_bytes(document["epoch"])
                or canonical_bytes(engine.transitions) != canonical_bytes(document["transitions"])
                or engine.finalized is not document["finalized"]):
            raise ValueError("session derived state differs from semantic replay")
        return engine
