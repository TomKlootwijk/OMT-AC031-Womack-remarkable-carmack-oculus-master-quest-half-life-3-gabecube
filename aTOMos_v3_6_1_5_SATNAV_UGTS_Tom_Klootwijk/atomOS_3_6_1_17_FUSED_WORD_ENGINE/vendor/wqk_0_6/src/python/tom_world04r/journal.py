"""Append-only continuation journal for the corrective 0.4 rebuild.

The journal is deliberately stricter than the superseded 0.4 line.  Every
reachable immutable object is re-read from disk and content-hash verified; each
transaction is checked against its commit, parent segment, solver-produced
event set, transition, segment seal, and successor.  Only ``HEAD`` is mutable.
"""
from __future__ import annotations

import errno
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from tom_world03.canonical import attach_hash, canonical_bytes, require_hash
from tom_world03.interval import ClosedInterval
from tom_world03.rational import Q

from .model import (
    CANONICAL_SEED_SHA256,
    CORRECTED_INTERVAL_SHA256,
    CORRECTED_V03_ZIP_SHA256,
    ContinuationWorld,
    OpenSegment,
    qmap_record,
)
from .transition import EventBundle, FinalizationBundle

STORE_SCHEMA = "TOM-CONTINUATION-STORE-0.4.1"
COMMIT_SCHEMA = "TOM-CONTINUATION-COMMIT-0.4.1"
GENESIS_SCHEMA = "TOM-CONTINUATION-GENESIS-TRANSACTION-0.4.1"
EVENT_TX_SCHEMA = "TOM-EVENT-CONTINUATION-TRANSACTION-0.4.1"
FINAL_TX_SCHEMA = "TOM-CONTINUATION-FINALIZATION-TRANSACTION-0.4.1"


def _digest(content_hash: str) -> str:
    if not isinstance(content_hash, str) or not content_hash.startswith("sha256:") or len(content_hash) != 71:
        raise ValueError(f"invalid content hash {content_hash!r}")
    suffix = content_hash[7:]
    try:
        int(suffix, 16)
    except ValueError as exc:
        raise ValueError(f"invalid content hash {content_hash!r}") from exc
    if suffix != suffix.lower():
        raise ValueError(f"invalid content hash {content_hash!r}")
    return suffix


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _record_bytes(record: Mapping[str, Any]) -> bytes:
    return canonical_bytes(record) + b"\n"


def _qmap_from_record(value: Any, label: str) -> dict[str, Q]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return {str(name): Q.from_value(item) for name, item in value.items()}


class ContinuationStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        if not self.path.is_dir():
            raise FileNotFoundError(self.path)
        for name in ("objects", "transactions", "commits"):
            if not (self.path / name).is_dir():
                raise ValueError(f"continuation store lacks {name} directory")
        if not (self.path / "HEAD").is_file() or not (self.path / "store.json").is_file():
            raise ValueError("continuation store is incomplete")

    @classmethod
    def initialize(
        cls,
        path: str | Path,
        seed_bytes: bytes,
        world_record: Mapping[str, Any],
        world: ContinuationWorld,
    ) -> "ContinuationStore":
        target = Path(path)
        if target.exists() and any(target.iterdir()):
            raise FileExistsError(f"continuation store destination is not empty: {target}")
        if len(seed_bytes) != 244 or seed_bytes.endswith((b"\n", b"\r")) or _sha256(seed_bytes) != CANONICAL_SEED_SHA256:
            raise ValueError("continuation store requires the exact 244-byte canonical seed")
        require_hash(world_record, label="journal world")
        if world_record.get("content_hash") != world.content_hash:
            raise ValueError("journal world object and typed world disagree")

        target.mkdir(parents=True, exist_ok=True)
        for name in ("objects", "transactions", "commits"):
            (target / name).mkdir()
        (target / "seed.bin").write_bytes(seed_bytes)
        descriptor = attach_hash({
            "schema": STORE_SCHEMA,
            "version": "0.4.1",
            "seed_sha256": CANONICAL_SEED_SHA256,
            "corrected_v03_zip_sha256": world.corrected_v03_zip_sha256,
            "corrected_interval_sha256": world.corrected_interval_sha256,
            "world_hash": world.content_hash,
            "mutable_paths": ["HEAD"],
            "immutable_directories": ["objects", "transactions", "commits"],
            "atomic_commit_order": [
                "event-set-or-final-seal",
                "transition",
                "segment-seal",
                "successor-segment",
                "transaction",
                "commit",
                "HEAD",
            ],
        })
        (target / "store.json").write_bytes(_record_bytes(descriptor))
        store = cls.__new__(cls)
        store.path = target
        store._put("objects", world_record)
        store._put("objects", world.initial_segment.to_record())
        genesis = attach_hash({
            "schema": GENESIS_SCHEMA,
            "world_hash": world.content_hash,
            "sequence": 0,
            "initial_segment_id": world.initial_segment.id,
            "initial_segment_hash": world.initial_segment.content_hash,
            "corrected_v03_zip_sha256": world.corrected_v03_zip_sha256,
            "corrected_interval_sha256": world.corrected_interval_sha256,
        })
        store._put("transactions", genesis)
        commit = attach_hash({
            "schema": COMMIT_SCHEMA,
            "commit_kind": "genesis",
            "world_hash": world.content_hash,
            "sequence": 0,
            "parent_commit_hash": None,
            "transaction_hash": genesis["content_hash"],
            "current_segment_hash": world.initial_segment.content_hash,
            "finalized": False,
        })
        store._put("commits", commit)
        store._publish_head(commit["content_hash"])
        return cls(target)

    @property
    def head(self) -> str:
        value = (self.path / "HEAD").read_text(encoding="ascii").strip()
        _digest(value)
        return value

    def descriptor(self) -> dict[str, Any]:
        record = json.loads((self.path / "store.json").read_text(encoding="utf-8"))
        if not isinstance(record, dict):
            raise ValueError("continuation store descriptor is not an object")
        require_hash(record, label="continuation store descriptor")
        if record.get("schema") != STORE_SCHEMA or record.get("version") != "0.4.1":
            raise ValueError("unsupported continuation store descriptor")
        if record.get("seed_sha256") != CANONICAL_SEED_SHA256:
            raise ValueError("continuation store descriptor seed mismatch")
        if record.get("corrected_v03_zip_sha256") != CORRECTED_V03_ZIP_SHA256:
            raise ValueError("continuation store descriptor corrected-0.3 archive mismatch")
        if record.get("corrected_interval_sha256") != CORRECTED_INTERVAL_SHA256:
            raise ValueError("continuation store descriptor corrected interval mismatch")
        if record.get("mutable_paths") != ["HEAD"]:
            raise ValueError("continuation store permits unexpected mutable paths")
        return record

    def _path(self, namespace: str, content_hash: str) -> Path:
        if namespace not in {"objects", "transactions", "commits"}:
            raise ValueError(f"unknown continuation namespace {namespace}")
        return self.path / namespace / f"{_digest(content_hash)}.json"

    def _put(self, namespace: str, record: Mapping[str, Any]) -> Path:
        require_hash(record, label=f"{namespace} record")
        path = self._path(namespace, str(record["content_hash"]))
        data = _record_bytes(record)
        if path.exists():
            if path.read_bytes() != data:
                raise ValueError(f"immutable object collision at {path}")
            return path
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)
        return path

    def _get(self, namespace: str, content_hash: str) -> dict[str, Any]:
        path = self._path(namespace, content_hash)
        if not path.is_file():
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), str(path))
        record = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(record, dict):
            raise ValueError(f"record at {path} is not an object")
        require_hash(record, label=f"{namespace} record")
        if record.get("content_hash") != content_hash:
            raise ValueError(f"filename/content hash mismatch at {path}")
        return record

    def _publish_head(self, content_hash: str) -> None:
        _digest(content_hash)
        tmp = self.path / "HEAD.tmp"
        tmp.write_text(content_hash + "\n", encoding="ascii")
        os.replace(tmp, self.path / "HEAD")

    def get_commit(self, content_hash: str | None = None) -> dict[str, Any]:
        return self._get("commits", self.head if content_hash is None else content_hash)

    def commit_event(self, bundle: EventBundle) -> str:
        head = self.get_commit()
        if head.get("finalized"):
            raise ValueError("cannot append an event to a finalized continuation")
        if head.get("current_segment_hash") != bundle.transaction.get("parent_segment_hash"):
            raise ValueError("event transaction parent is not the current HEAD segment")
        if int(head.get("sequence", -1)) + 1 != int(bundle.transaction.get("sequence", -2)):
            raise ValueError("event transaction sequence does not follow HEAD")

        self._put("objects", bundle.event_set)
        self._put("objects", bundle.transition)
        self._put("objects", bundle.seal)
        self._put("objects", bundle.successor_record)
        self._put("transactions", bundle.transaction)
        commit = attach_hash({
            "schema": COMMIT_SCHEMA,
            "commit_kind": "event",
            "world_hash": bundle.transaction["world_hash"],
            "sequence": int(head["sequence"]) + 1,
            "parent_commit_hash": head["content_hash"],
            "transaction_hash": bundle.transaction["content_hash"],
            "current_segment_hash": bundle.successor.content_hash,
            "finalized": False,
        })
        self._put("commits", commit)
        self._publish_head(commit["content_hash"])
        return commit["content_hash"]

    def commit_finalization(self, bundle: FinalizationBundle) -> str:
        head = self.get_commit()
        if head.get("finalized"):
            raise ValueError("continuation store is already finalized")
        if head.get("current_segment_hash") != bundle.transaction.get("segment_hash"):
            raise ValueError("finalization segment is not the current HEAD segment")
        if int(head.get("sequence", -1)) + 1 != int(bundle.transaction.get("sequence", -2)):
            raise ValueError("finalization transaction sequence does not follow HEAD")
        self._put("objects", bundle.seal)
        self._put("transactions", bundle.transaction)
        commit = attach_hash({
            "schema": COMMIT_SCHEMA,
            "commit_kind": "finalization",
            "world_hash": bundle.transaction["world_hash"],
            "sequence": int(head["sequence"]) + 1,
            "parent_commit_hash": head["content_hash"],
            "transaction_hash": bundle.transaction["content_hash"],
            "current_segment_hash": bundle.transaction["segment_hash"],
            "finalized": True,
        })
        self._put("commits", commit)
        self._publish_head(commit["content_hash"])
        return commit["content_hash"]

    def _chain(self) -> list[dict[str, Any]]:
        seen: set[str] = set()
        chain: list[dict[str, Any]] = []
        cursor: str | None = self.head
        while cursor is not None:
            if cursor in seen:
                raise ValueError("commit cycle detected")
            seen.add(cursor)
            commit = self._get("commits", cursor)
            if commit.get("schema") != COMMIT_SCHEMA:
                raise ValueError("unsupported commit schema")
            chain.append(commit)
            parent = commit.get("parent_commit_hash")
            cursor = None if parent is None else str(parent)
        chain.reverse()
        return chain

    def audit(self, *, require_no_orphans: bool = True) -> dict[str, Any]:
        errors: list[str] = []
        warnings: list[str] = []
        reachable_objects: set[str] = set()
        reachable_transactions: set[str] = set()
        reachable_commits: set[str] = set()
        chain: list[dict[str, Any]] = []
        event_count = 0
        try:
            descriptor = self.descriptor()
            seed = (self.path / "seed.bin").read_bytes()
            if len(seed) != 244 or seed.endswith((b"\n", b"\r")) or _sha256(seed) != descriptor["seed_sha256"]:
                errors.append("seed bytes do not match descriptor")

            world_hash = str(descriptor["world_hash"])
            reachable_objects.add(world_hash)
            world_record = self._get("objects", world_hash)
            world = ContinuationWorld.from_record(world_record)
            if world.content_hash != world_hash:
                errors.append("world object identity mismatch")

            chain = self._chain()
            current_segment: OpenSegment | None = None
            previous_commit_hash: str | None = None
            finalized_seen = False
            for expected_sequence, commit in enumerate(chain):
                commit_hash = str(commit["content_hash"])
                reachable_commits.add(commit_hash)
                if int(commit.get("sequence", -1)) != expected_sequence:
                    errors.append(f"commit sequence mismatch at {commit_hash}")
                if commit.get("parent_commit_hash") != previous_commit_hash:
                    errors.append(f"commit parent mismatch at {commit_hash}")
                previous_commit_hash = commit_hash
                if commit.get("world_hash") != world_hash:
                    errors.append(f"commit world mismatch at {commit_hash}")

                tx_hash = str(commit.get("transaction_hash", ""))
                reachable_transactions.add(tx_hash)
                tx = self._get("transactions", tx_hash)
                if tx.get("world_hash") != world_hash:
                    errors.append(f"transaction world mismatch at {tx_hash}")
                if int(tx.get("sequence", -1)) != expected_sequence:
                    errors.append(f"transaction sequence mismatch at {tx_hash}")

                kind = commit.get("commit_kind")
                if kind == "genesis":
                    if expected_sequence != 0 or tx.get("schema") != GENESIS_SCHEMA:
                        errors.append("invalid genesis transaction")
                    if commit.get("finalized"):
                        errors.append("genesis commit cannot be finalized")
                    if tx.get("corrected_v03_zip_sha256") != world.corrected_v03_zip_sha256:
                        errors.append("genesis corrected 0.3 archive mismatch")
                    if tx.get("corrected_interval_sha256") != world.corrected_interval_sha256:
                        errors.append("genesis corrected interval mismatch")
                    segment_hash = str(tx.get("initial_segment_hash"))
                    reachable_objects.add(segment_hash)
                    segment_record = self._get("objects", segment_hash)
                    current_segment = OpenSegment.from_record(segment_record)
                    if current_segment.id != tx.get("initial_segment_id"):
                        errors.append("genesis initial segment id mismatch")
                    if current_segment.content_hash != world.initial_segment.content_hash:
                        errors.append("genesis segment is not the world's initial segment")
                    if commit.get("current_segment_hash") != segment_hash:
                        errors.append("genesis current segment mismatch")

                elif kind == "event":
                    event_count += 1
                    if finalized_seen:
                        errors.append("event commit appears after finalization")
                    if tx.get("schema") != EVENT_TX_SCHEMA:
                        errors.append(f"invalid event transaction schema at {tx_hash}")
                    if commit.get("finalized"):
                        errors.append(f"event commit unexpectedly finalized at {commit_hash}")
                    if current_segment is None:
                        errors.append("event commit has no current segment")
                        continue
                    if tx.get("parent_segment_hash") != current_segment.content_hash or tx.get("parent_segment_id") != current_segment.id:
                        errors.append(f"event parent segment mismatch at {tx_hash}")

                    event_hash = str(tx.get("event_set_hash"))
                    transition_hash = str(tx.get("transition_hash"))
                    seal_hash = str(tx.get("seal_hash"))
                    successor_hash = str(tx.get("successor_segment_hash"))
                    for ref in (event_hash, transition_hash, seal_hash, successor_hash):
                        reachable_objects.add(ref)
                    event_set = self._get("objects", event_hash)
                    transition = self._get("objects", transition_hash)
                    seal = self._get("objects", seal_hash)
                    successor_record = self._get("objects", successor_hash)
                    successor = OpenSegment.from_record(successor_record)

                    event_time = Q.from_value(tx.get("event_time"))
                    if event_set.get("schema") != "TOM-NEXT-CONTINUATION-EVENT-SET-0.4.1" or event_set.get("status") != "accepted":
                        errors.append(f"invalid accepted event set at {event_hash}")
                    if event_set.get("world_hash") != world_hash or event_set.get("segment_hash") != current_segment.content_hash:
                        errors.append(f"event set authority mismatch at {event_hash}")
                    if Q.from_value(event_set.get("event_time")) != event_time:
                        errors.append(f"event set time mismatch at {event_hash}")
                    if transition.get("schema") != "TOM-CONTINUATION-TRANSITION-0.4.1":
                        errors.append(f"invalid transition schema at {transition_hash}")
                    if transition.get("event_set_hash") != event_hash or transition.get("segment_hash") != current_segment.content_hash:
                        errors.append(f"transition linkage mismatch at {transition_hash}")
                    if Q.from_value(transition.get("event_time")) != event_time:
                        errors.append(f"transition time mismatch at {transition_hash}")
                    if seal.get("schema") != "TOM-OPEN-SEGMENT-SEAL-0.4.1":
                        errors.append(f"invalid segment seal schema at {seal_hash}")
                    if seal.get("open_segment_hash") != current_segment.content_hash or seal.get("event_set_hash") != event_hash or seal.get("transition_hash") != transition_hash:
                        errors.append(f"segment seal linkage mismatch at {seal_hash}")
                    if Q.from_value(seal.get("end_time")) != event_time:
                        errors.append(f"segment seal time mismatch at {seal_hash}")
                    expected_domain = ClosedInterval(current_segment.start, event_time).to_record()
                    if seal.get("realized_domain") != expected_domain:
                        errors.append(f"segment seal domain mismatch at {seal_hash}")

                    if successor.id != tx.get("successor_segment_id") or successor.content_hash != successor_hash:
                        errors.append(f"successor identity mismatch at {successor_hash}")
                    if successor.sequence != expected_sequence:
                        errors.append(f"successor sequence mismatch at {successor_hash}")
                    if successor.parent_segment_hash != current_segment.content_hash:
                        errors.append(f"successor parent mismatch at {successor_hash}")
                    if successor.source_event_set_hash != event_hash or successor.source_transition_hash != transition_hash:
                        errors.append(f"successor causal source mismatch at {successor_hash}")
                    if successor.start != event_time or successor.horizon != world.horizon.upper:
                        errors.append(f"successor open-domain mismatch at {successor_hash}")
                    if successor_record.get("start_state") != transition.get("post_state") or successor_record.get("rates") != transition.get("post_rates"):
                        errors.append(f"successor state/rates mismatch at {successor_hash}")
                    expected_fired = event_set.get("fired_relations_after")
                    if list(successor.fired_relations) != list(expected_fired or []):
                        errors.append(f"successor fired-relation set mismatch at {successor_hash}")
                    if commit.get("current_segment_hash") != successor_hash:
                        errors.append(f"event current segment mismatch at {commit_hash}")
                    current_segment = successor

                elif kind == "finalization":
                    if finalized_seen:
                        errors.append("multiple finalization commits")
                    finalized_seen = True
                    if tx.get("schema") != FINAL_TX_SCHEMA:
                        errors.append(f"invalid finalization transaction at {tx_hash}")
                    if current_segment is None:
                        errors.append("finalization has no current segment")
                        continue
                    if tx.get("segment_hash") != current_segment.content_hash or tx.get("segment_id") != current_segment.id:
                        errors.append(f"finalization segment mismatch at {tx_hash}")
                    seal_hash = str(tx.get("seal_hash"))
                    reachable_objects.add(seal_hash)
                    seal = self._get("objects", seal_hash)
                    if seal.get("schema") != "TOM-OPEN-SEGMENT-SEAL-0.4.1":
                        errors.append(f"invalid final seal schema at {seal_hash}")
                    if seal.get("open_segment_hash") != current_segment.content_hash or seal.get("event_set_hash") is not None or seal.get("transition_hash") is not None:
                        errors.append(f"final seal linkage mismatch at {seal_hash}")
                    if Q.from_value(seal.get("end_time")) != world.horizon.upper:
                        errors.append(f"final seal horizon mismatch at {seal_hash}")
                    expected_final = qmap_record(current_segment.state_at(world.horizon.upper))
                    if seal.get("end_state") != expected_final or tx.get("final_state") != expected_final:
                        errors.append(f"final state mismatch at {tx_hash}")
                    if Q.from_value(tx.get("final_time")) != world.horizon.upper:
                        errors.append(f"final time mismatch at {tx_hash}")
                    if not commit.get("finalized"):
                        errors.append("finalization commit is not marked finalized")
                    if commit.get("current_segment_hash") != current_segment.content_hash:
                        errors.append("finalization commit current segment mismatch")
                else:
                    errors.append(f"unknown commit kind {kind}")

            if not chain or chain[0].get("commit_kind") != "genesis":
                errors.append("commit chain lacks genesis")
            if not chain or chain[-1].get("commit_kind") != "finalization" or not chain[-1].get("finalized"):
                errors.append("HEAD is not the unique finalized commit")

            def listed(namespace: str) -> set[str]:
                return {"sha256:" + path.stem for path in (self.path / namespace).glob("*.json")}

            for namespace, reachable in (
                ("objects", reachable_objects),
                ("transactions", reachable_transactions),
                ("commits", reachable_commits),
            ):
                orphans = sorted(listed(namespace) - reachable)
                if orphans:
                    message = f"orphan {namespace}: {orphans}"
                    if require_no_orphans:
                        errors.append(message)
                    else:
                        warnings.append(message)
        except FileNotFoundError as exc:
            # Store audits are content-addressed evidence.  Never include the
            # ambient absolute temporary-directory path in the audit bytes.
            # The immutable filename/hash is sufficient to identify the missing
            # authority record and is stable across clean replays.
            missing = Path(exc.filename).name if exc.filename else "unknown"
            errors.append(f"missing immutable record: {missing}")
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")

        return attach_hash({
            "schema": "TOM-CONTINUATION-STORE-AUDIT-0.4.1",
            "store": self.path.name,
            "head": None if not (self.path / "HEAD").exists() else (self.path / "HEAD").read_text().strip(),
            "valid": not errors,
            "require_no_orphans": require_no_orphans,
            "commit_count": len(chain),
            "event_commit_count": event_count,
            "transaction_count": len(reachable_transactions),
            "object_count": len(reachable_objects),
            "errors": errors,
            "warnings": warnings,
        })

    def reconstruct(self) -> dict[str, Any]:
        audit = self.audit(require_no_orphans=True)
        if not audit["valid"]:
            raise ValueError("cannot reconstruct invalid continuation store: " + "; ".join(audit["errors"]))
        descriptor = self.descriptor()
        world_record = self._get("objects", str(descriptor["world_hash"]))
        world = ContinuationWorld.from_record(world_record)
        chain = self._chain()
        genesis = self._get("transactions", str(chain[0]["transaction_hash"]))
        current_segment = OpenSegment.from_record(
            self._get("objects", str(genesis["initial_segment_hash"]))
        )

        segments: list[dict[str, Any]] = []
        event_sets: list[dict[str, Any]] = []
        event_semantics: list[dict[str, Any]] = []
        transitions: list[dict[str, Any]] = []
        seals: list[dict[str, Any]] = []
        transactions: list[dict[str, Any]] = [genesis]
        segment_records: list[dict[str, Any]] = [current_segment.to_record()]
        final_state: Mapping[str, Any] | None = None
        final_time: Mapping[str, Any] | None = None

        for commit in chain[1:]:
            tx = self._get("transactions", str(commit["transaction_hash"]))
            transactions.append(tx)
            if commit["commit_kind"] == "event":
                event = self._get("objects", str(tx["event_set_hash"]))
                transition = self._get("objects", str(tx["transition_hash"]))
                seal = self._get("objects", str(tx["seal_hash"]))
                segments.append({
                    "sequence": current_segment.sequence,
                    "domain": seal["realized_domain"],
                    "start_state": qmap_record(current_segment.start_state),
                    "rates": qmap_record(current_segment.rates),
                    "end_state": seal["end_state"],
                })
                event_sets.append(event)
                transitions.append(transition)
                seals.append(seal)
                successor_record = self._get("objects", str(tx["successor_segment_hash"]))
                successor = OpenSegment.from_record(successor_record)
                event_semantics.append({
                    "event_time": event["event_time"],
                    "event_order": list(event["event_order"]),
                    "relation_order": list(event["relation_order"]),
                    "pre_state": transition["pre_state"],
                    "post_state": transition["post_state"],
                    "pre_rates": transition["pre_rates"],
                    "post_rates": transition["post_rates"],
                    "fired_relations_after": list(successor.fired_relations),
                })
                current_segment = successor
                segment_records.append(successor_record)
            elif commit["commit_kind"] == "finalization":
                seal = self._get("objects", str(tx["seal_hash"]))
                seals.append(seal)
                segments.append({
                    "sequence": current_segment.sequence,
                    "domain": seal["realized_domain"],
                    "start_state": qmap_record(current_segment.start_state),
                    "rates": qmap_record(current_segment.rates),
                    "end_state": seal["end_state"],
                })
                final_state = tx["final_state"]
                final_time = tx["final_time"]

        semantic_chain = {
            "schema": "TOM-CONTINUATION-SEMANTIC-CHAIN-0.4.1",
            "world_hash": world.content_hash,
            "corrected_v03_zip_sha256": world.corrected_v03_zip_sha256,
            "corrected_interval_sha256": world.corrected_interval_sha256,
            "realized_segments": segments,
            "event_sets": event_semantics,
            "final_time": final_time,
            "final_state": final_state,
            "fired_relations": list(current_segment.fired_relations),
            "boundary_policy": "event times are solver outputs; final boundary is the declared world horizon",
        }
        semantic_hash = "sha256:" + hashlib.sha256(canonical_bytes(semantic_chain)).hexdigest()
        return attach_hash({
            "schema": "TOM-CONTINUATION-RECONSTRUCTION-0.4.1",
            "store_head": self.head,
            "world_hash": world.content_hash,
            "commit_hashes": [commit["content_hash"] for commit in chain],
            "transaction_hashes": [tx["content_hash"] for tx in transactions],
            "segment_hashes": [segment["content_hash"] for segment in segment_records],
            "seal_hashes": [seal["content_hash"] for seal in seals],
            "event_set_hashes": [event["content_hash"] for event in event_sets],
            "transition_hashes": [transition["content_hash"] for transition in transitions],
            "commit_count": len(chain),
            "event_set_count": len(event_sets),
            "segment_count": len(segment_records),
            "semantic_chain": semantic_chain,
            "semantic_chain_sha256": semantic_hash,
            "final_state": final_state,
            "final_time": final_time,
        })
