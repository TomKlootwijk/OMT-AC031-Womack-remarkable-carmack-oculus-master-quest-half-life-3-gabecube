"""Canonical JSON and content-addressed definition records."""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any


def _validate_json(value: Any, *, path: str = "$") -> None:
    """Reject Python values that cannot originate from a JSON document."""

    if value is None or isinstance(value, (bool, str, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path}: non-finite numbers are not valid JSON")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _validate_json(child, path=f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path}: JSON object keys must be strings")
            _validate_json(child, path=f"{path}.{key}")
        return
    raise TypeError(f"{path}: value of type {type(value).__name__} is not JSON-native")


def canonical_bytes(value: Any) -> bytes:
    _validate_json(value)
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def content_hash(record: dict[str, Any]) -> str:
    body = {k: v for k, v in record.items() if k != "content_hash"}
    return "sha256:" + hashlib.sha256(canonical_bytes(body)).hexdigest()


def attach_hash(record: dict[str, Any]) -> dict[str, Any]:
    out = dict(record)
    out["content_hash"] = content_hash(out)
    return out


def verify_hash(record: dict[str, Any]) -> bool:
    return record.get("content_hash") == content_hash(record)
