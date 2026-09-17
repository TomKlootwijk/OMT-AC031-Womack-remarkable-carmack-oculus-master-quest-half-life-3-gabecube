"""R21 reported radio observations: exact archives, inventories and study data.

This module processes Android-reported scalar power/quality records. It does
not process carrier waveform samples or infer range, location or phase.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
import re
import struct
from typing import Any
import uuid

SCHEMA = "atomos.radio.v1"
ARCHIVE_MAGIC = b"ARADBP1\0"
KINDS = {"session", "wifi", "cell", "status", "marker", "session_end"}
COLLECTION_METADATA = {"origin", "batch_id", "results_updated"}
NS = 1_000_000_000
METRICS = {
    "dbm": ("reported_power", "dBm", Decimal(1)),
    "rssi_dbm": ("rssi", "dBm", Decimal(1)),
    "rsrp_dbm": ("rsrp", "dBm", Decimal(1)),
    "rsrq_db": ("rsrq", "dB", Decimal(1)),
    "rssnr_db": ("rssnr", "dB", Decimal(1)),
    "rssnr_tenth_db": ("rssnr", "dB", Decimal("0.1")),
    "ss_rsrp_dbm": ("ss_rsrp", "dBm", Decimal(1)),
    "ss_rsrq_db": ("ss_rsrq", "dB", Decimal(1)),
    "ss_sinr_db": ("ss_sinr", "dB", Decimal(1)),
    "csi_rsrp_dbm": ("csi_rsrp", "dBm", Decimal(1)),
    "csi_rsrq_db": ("csi_rsrq", "dB", Decimal(1)),
    "csi_sinr_db": ("csi_sinr", "dB", Decimal(1)),
}


def exact_json(value: Any) -> str:
    """Deterministic JSON preserving parsed integer and finite decimal values."""
    if value is None or type(value) in (str, bool, int):
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("non-finite JSON number")
        return str(value)
    if isinstance(value, list):
        return "[" + ",".join(exact_json(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(exact_json(k) + ":" + exact_json(value[k])
                              for k in sorted(value)) + "}"
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: " + key)
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("non-finite JSON constant: " + value)


def parse_json(line: str):
    return json.loads(line, parse_float=Decimal, object_pairs_hook=_object,
                      parse_constant=_reject_constant)


def _transpose(block: bytes) -> bytes:
    words = struct.unpack("<64Q", block)
    planes = [sum(((word >> bit) & 1) << lane
                  for lane, word in enumerate(words)) for bit in range(64)]
    return struct.pack("<64Q", *planes)


def pack_bytes(original: bytes) -> bytes:
    """Lossless 64x64 bit transposition; no compression or numeric conversion."""
    if type(original) is not bytes:
        raise TypeError("archive input must be bytes")
    padded = original + bytes((-len(original)) % 512)
    payload = b"".join(_transpose(padded[i:i + 512])
                       for i in range(0, len(padded), 512))
    return (ARCHIVE_MAGIC + struct.pack("<Q", len(original))
            + hashlib.sha256(original).digest() + payload)


def unpack_bytes(archive: bytes) -> bytes:
    if type(archive) is not bytes or len(archive) < 48 or archive[:8] != ARCHIVE_MAGIC:
        raise ValueError("invalid or truncated ARADBP1 header")
    length = struct.unpack("<Q", archive[8:16])[0]
    expected = 48 + 512 * ((length + 511) // 512)
    if len(archive) != expected:
        raise ValueError("truncated or trailing bit-plane archive data")
    decoded = b"".join(_transpose(archive[i:i + 512])
                       for i in range(48, len(archive), 512))
    if any(decoded[length:]):
        raise ValueError("nonzero decoded archive padding")
    original = decoded[:length]
    if hashlib.sha256(original).digest() != archive[16:48]:
        raise ValueError("archive SHA256 mismatch")
    return original


def _elapsed(value, name: str, nullable=False):
    if nullable and value is None:
        return None
    if type(value) is not str or not re.fullmatch(r"0|[1-9][0-9]*", value):
        raise ValueError(name + " must be a nonnegative canonical decimal string")
    return int(value)


def _validate(record):
    if type(record) is not dict:
        raise ValueError("record must be an object")
    required = {"schema", "session_id", "seq", "kind", "received_elapsed_ns",
                "received_unix_ms", "source_elapsed_ns", "payload"}
    missing = required - record.keys()
    if missing:
        raise ValueError("missing fields: " + ", ".join(sorted(missing)))
    if record["schema"] != SCHEMA:
        raise ValueError("unsupported schema")
    if type(record["session_id"]) is not str:
        raise ValueError("session_id must be UUID string")
    try:
        uuid.UUID(record["session_id"])
    except (ValueError, AttributeError) as error:
        raise ValueError("invalid session_id UUID") from error
    if type(record["seq"]) is not int or record["seq"] < 0:
        raise ValueError("seq must be nonnegative integer")
    if type(record["kind"]) is not str or record["kind"] not in KINDS:
        raise ValueError("unknown event kind")
    if type(record["received_unix_ms"]) is not int:
        raise ValueError("received_unix_ms must be integer")
    if type(record["payload"]) is not dict:
        raise ValueError("payload must be object")
    received = _elapsed(record["received_elapsed_ns"], "received_elapsed_ns")
    source = _elapsed(record["source_elapsed_ns"], "source_elapsed_ns", True)
    return received, source


def _identity(record):
    p = record["payload"]
    if record["kind"] == "wifi":
        bssid = p.get("bssid")
        if not isinstance(bssid, str) or not bssid:
            return None
        return {"kind": "wifi", "bssid": bssid,
                "frequency_mhz": p.get("frequency_mhz")}
    if record["kind"] == "cell":
        identity = p.get("identity")
        rat = p.get("rat")
        if (not isinstance(identity, dict) or not identity
                or not any(v is not None for v in identity.values())
                or not isinstance(rat, str) or not rat):
            return None
        return {"kind": "cell", "rat": rat,
                "subscription_id": p.get("subscription_id"), "identity": identity}
    return None


def _metric_rows(observation, issues):
    p = observation["record"]["payload"]
    kind = observation["kind"]
    signal = {"rssi_dbm": p.get("rssi_dbm")} if kind == "wifi" else p.get("signal", {})
    if not isinstance(signal, dict):
        issues.append({"line": observation["line"], "code": "invalid_signal_object"})
        return []
    result = []
    # Deliberately retain unknown scalar fields with no invented unit.
    for name, raw in signal.items():
        mapping = METRICS.get(name)
        metric, unit, scale = mapping if mapping else (name, None, None)
        number = type(raw) is int or isinstance(raw, Decimal)
        valid_number = number and (not isinstance(raw, Decimal) or raw.is_finite())
        value = Decimal(raw) * scale if valid_number and scale is not None else None
        if raw is not None and mapping and not valid_number:
            issues.append({"line": observation["line"], "code": "invalid_metric_value",
                           "field": name, "value": raw})
        result.append({"source_field": name, "metric": metric, "unit": unit,
                       "raw_value": raw, "value": value,
                       "value_status": "available" if value is not None else
                       "unavailable" if raw is None else
                       "unknown_unit" if mapping is None else "invalid_value"})
    return result


def analyze_bytes(original: bytes, *, stale_after_seconds=Decimal(30),
                  wall_jump_seconds=Decimal(2)):
    """Retain every byte; flag input defects and separate all metric families.

    Source timestamps identify reported observations, not RF waveform instants.
    The two thresholds are study policies, not instrument specifications.
    """
    stale_ns = Decimal(stale_after_seconds) * NS
    wall_jump_ns = Decimal(wall_jump_seconds) * NS
    if (not stale_ns.is_finite() or not wall_jump_ns.is_finite()
            or stale_ns < 0 or wall_jump_ns < 0):
        raise ValueError("study thresholds must be finite and nonnegative")
    issues, observations, events = [], [], []
    sessions = {}
    invalid = []
    clusters = defaultdict(list)
    last_source = {}
    lines = original.splitlines(keepends=True)
    final_unterminated = bool(original) and not original.endswith((b"\n", b"\r"))
    for line_number, raw in enumerate(lines, 1):
        try:
            line = raw.decode("utf-8")
            if not line.strip():
                raise ValueError("blank JSONL row")
            record = parse_json(line)
            received, source = _validate(record)
        except (UnicodeDecodeError, ValueError, TypeError, RecursionError) as error:
            invalid.append({"line": line_number, "error": str(error),
                            "raw_line_sha256": hashlib.sha256(raw).hexdigest(),
                            "possible_truncated_final_row": line_number == len(lines)
                            and final_unterminated})
            continue
        sid, seq, kind = record["session_id"], record["seq"], record["kind"]
        state = sessions.setdefault(sid, {"last_seq": None, "last_received": None,
            "last_unix": None, "segment": 0, "session_rows": [], "end_rows": [],
            "rows": 0, "accepted_rows": 0, "sequence_issues": 0,
            "clock_discontinuities": 0, "lifecycle_issues": 0, "origin_elapsed_ns": received,
            "segment_windows": {}})
        state["rows"] += 1
        chronology_valid = True
        if state["last_seq"] is None:
            if seq != 0:
                issues.append({"line": line_number, "code": "sequence_does_not_start_at_zero",
                               "seq": seq, "session_id": sid})
                state["sequence_issues"] += 1
        elif seq <= state["last_seq"]:
            chronology_valid = False
            issues.append({"line": line_number, "code": "duplicate_or_out_of_order_seq",
                           "seq": seq, "previous_seq": state["last_seq"], "session_id": sid})
            state["sequence_issues"] += 1
        elif seq != state["last_seq"] + 1:
            issues.append({"line": line_number, "code": "sequence_gap",
                           "seq": seq, "previous_seq": state["last_seq"], "session_id": sid})
            state["sequence_issues"] += 1
        if chronology_valid:
            if state["last_received"] is not None:
                elapsed_delta = received - state["last_received"]
                wall_delta = (record["received_unix_ms"] - state["last_unix"]) * 1_000_000
                if elapsed_delta < 0:
                    state["segment"] += 1
                    state["clock_discontinuities"] += 1
                    issues.append({"line": line_number, "code": "elapsed_clock_reset",
                                   "session_id": sid, "possible_reboot_or_mixed_clock": True})
                elif abs(wall_delta - elapsed_delta) > wall_jump_ns:
                    state["clock_discontinuities"] += 1
                    issues.append({"line": line_number, "code": "wall_clock_discontinuity",
                                   "session_id": sid,
                                   "wall_minus_elapsed_delta_ns": str(wall_delta - elapsed_delta)})
            state["last_seq"], state["last_received"] = seq, received
            state["last_unix"] = record["received_unix_ms"]
            state["accepted_rows"] += 1
            window = state["segment_windows"].setdefault(state["segment"],
                {"first": received, "last": received, "events": 0, "radio_events": 0})
            window["last"] = received
            window["events"] += 1
            window["radio_events"] += kind in {"wifi", "cell"}
        if kind == "session":
            state["session_rows"].append(line_number)
            if seq != 0 or len(state["session_rows"]) != 1:
                issues.append({"line": line_number, "code": "misplaced_session_start"})
                state["lifecycle_issues"] += 1
        if kind == "session_end":
            if state["end_rows"]:
                issues.append({"line": line_number, "code": "repeated_session_end"})
                state["lifecycle_issues"] += 1
            state["end_rows"].append(line_number)
        elif state["end_rows"]:
            issues.append({"line": line_number, "code": "record_after_session_end"})
            state["lifecycle_issues"] += 1
            chronology_valid = False
        if kind not in {"wifi", "cell"}:
            events.append({"line": line_number, "chronology_valid": chronology_valid,
                           "record": record})
            continue
        identity = _identity(record)
        source_valid = source is not None and source <= received
        if source is not None and not source_valid:
            issues.append({"line": line_number, "code": "source_time_after_receipt",
                           "source_elapsed_ns": str(source), "received_elapsed_ns": str(received)})
        age = received - source if source_valid else None
        rat = "WIFI" if kind == "wifi" else record["payload"].get("rat")
        if rat is not None and (type(rat) is not str or not rat):
            issues.append({"line": line_number, "code": "invalid_rat_label", "value": rat})
            rat = None
        observation = {"line": line_number, "session_id": sid, "seq": seq, "kind": kind,
            "rat": rat,
            "record": record, "raw_json": raw.decode("utf-8").rstrip("\r\n"),
            "segment": state["segment"], "chronology_valid": chronology_valid,
            "received_elapsed_ns": received, "measurement_elapsed_ns": source if source_valid else None,
            "source_time_status": "valid_reported_timestamp" if source_valid else
                "unavailable" if source is None else "invalid_after_receipt",
            "age_ns": age, "stale_by_policy": age is not None and age > stale_ns,
            "identity": identity, "duplicate_status": "unclassified"}
        observation["metrics"] = _metric_rows(observation, issues)
        observations.append(observation)
        if not chronology_valid:
            observation["duplicate_status"] = "excluded_sequence_error"
            continue
        if not source_valid:
            observation["duplicate_status"] = "source_timestamp_unavailable_or_invalid"
            continue
        if identity is None:
            observation["duplicate_status"] = "identity_unavailable"
            continue
        identity_key = (sid, state["segment"], exact_json(identity))
        if identity_key in last_source and source < last_source[identity_key]:
            issues.append({"line": line_number, "code": "out_of_order_source_timestamp",
                           "previous_source_elapsed_ns": str(last_source[identity_key]),
                           "source_elapsed_ns": str(source)})
        last_source[identity_key] = max(source, last_source.get(identity_key, source))
        observation_payload = {k: v for k, v in record["payload"].items()
                               if k not in COLLECTION_METADATA}
        observation["comparison_payload"] = exact_json(observation_payload)
        clusters[(*identity_key, source)].append(observation)
    for cluster in clusters.values():
        payloads = {o["comparison_payload"] for o in cluster}
        if len(payloads) > 1:
            for observation in cluster:
                observation["duplicate_status"] = "inconsistent_same_timestamp"
            issues.append({"line": cluster[0]["line"], "code": "inconsistent_same_timestamp",
                           "lines": [o["line"] for o in cluster]})
        else:
            cluster[0]["duplicate_status"] = "unique_timestamped_observation"
            for observation in cluster[1:]:
                observation["duplicate_status"] = "cached_duplicate"
    session_summaries = []
    for sid, state in sessions.items():
        if not state["session_rows"]:
            issues.append({"code": "missing_session_start", "session_id": sid})
        if not state["end_rows"]:
            issues.append({"code": "missing_session_end", "session_id": sid})
        complete = (len(state["session_rows"]) == len(state["end_rows"]) == 1
                    and state["sequence_issues"] == 0 and state["clock_discontinuities"] == 0
                    and state["lifecycle_issues"] == 0 and not invalid)
        session_summaries.append({"session_id": sid, "structurally_complete": complete,
            "rows": state["rows"], "accepted_sequence_rows": state["accepted_rows"],
            "session_start_lines": state["session_rows"], "session_end_lines": state["end_rows"],
            "sequence_issues": state["sequence_issues"],
            "lifecycle_issues": state["lifecycle_issues"],
            "clock_discontinuities": state["clock_discontinuities"], "clock_segments": state["segment"] + 1})
    groups = defaultdict(list)
    for observation in observations:
        if observation["duplicate_status"] != "unique_timestamped_observation":
            continue
        for metric in observation["metrics"]:
            if metric["value"] is not None:
                # Different source field/unit profiles remain separate even after scaling.
                groups[(observation["kind"], observation["rat"], metric["source_field"],
                        metric["metric"], metric["unit"], observation["session_id"],
                        observation["segment"], exact_json(observation["identity"]))].append(metric["value"])
    statistics = [{"kind": key[0], "rat": key[1], "source_field": key[2],
                   "metric": key[3], "unit": key[4], "unique_timestamped_count": len(values),
                   "session_id": key[5], "clock_segment": key[6], "identity": parse_json(key[7]),
                   "min": str(min(values)), "max": str(max(values)),
                   "mean": str(sum(values) / len(values))}
                  for key, values in sorted(groups.items(), key=lambda pair: str(pair[0]))]
    rates = []
    for sid, state in sessions.items():
        for segment, window in state["segment_windows"].items():
            duration = Decimal(window["last"] - window["first"]) / NS
            distinct = sum(o["session_id"] == sid and o["segment"] == segment
                and o["duplicate_status"] == "unique_timestamped_observation" for o in observations)
            rates.append({"session_id": sid, "clock_segment": segment,
                "first_received_elapsed_ns": str(window["first"]),
                "last_received_elapsed_ns": str(window["last"]), "covered_seconds": str(duration),
                "accepted_sequence_events": window["events"], "radio_event_records": window["radio_events"],
                "unique_timestamped_observations": distinct,
                "radio_records_per_covered_second": str(Decimal(window["radio_events"]) / duration) if duration else None,
                "unique_observations_per_covered_second": str(Decimal(distinct) / duration) if duration else None})
    session_events = [e for e in events if e["record"]["kind"] == "session"]
    declared_synthetic = bool(session_events) and all(e["record"]["payload"].get("synthetic") is True
                                                     for e in session_events)
    any_synthetic = any(e["record"]["payload"].get("synthetic") is True for e in session_events)
    summary = {"schema": "atomos.radio.study.v1", "input_sha256": hashlib.sha256(original).hexdigest(),
        "data_origin": "declared_synthetic_fixture" if declared_synthetic else
                       "mixed_synthetic_and_unlabeled_sessions" if any_synthetic else "input_capture_as_supplied",
        "input_bytes": len(original), "line_count": len(lines), "invalid_rows": invalid,
        "final_line_unterminated": final_unterminated,
        "radio_records": len(observations), "sessions": session_summaries,
        "observation_status_counts": dict(Counter(o["duplicate_status"] for o in observations)),
        "stale_by_policy_records": sum(o["stale_by_policy"] for o in observations),
        "study_policy": {"stale_after_seconds": str(stale_after_seconds),
            "wall_jump_seconds": str(wall_jump_seconds),
            "dedup_excluded_collection_fields": sorted(COLLECTION_METADATA),
            "dedup_identity": "session + elapsed-clock segment + radio identity + source timestamp + exact remaining payload",
            "statistics": "only unique timestamped observations; no statistical independence assumed",
            "plot_time": "source reported timestamp if valid, otherwise labeled receipt time",
            "unknown_fields": "retained in original bytes and raw_json; unknown metrics have no assigned unit"},
        "metric_statistics": statistics, "covered_interval_rates": rates,
        "events": events, "issues": issues,
        "interpretation": "Android-reported scalar radio power and quality with acquisition metadata; no carrier IQ/phase, range, location or inferred handover."}
    return {"summary": summary, "observations": observations, "events": events}


CSV_FIELDS = ["line", "session_id", "seq", "kind", "rat", "clock_segment",
    "received_elapsed_ns", "received_unix_ms", "source_elapsed_ns", "measurement_elapsed_ns",
    "source_time_status", "age_ns", "stale_by_policy", "chronology_valid", "duplicate_status",
    "identity_json", "source_field", "metric", "unit", "raw_value_json", "value",
    "value_status", "raw_json"]


def normalized_csv(analysis) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for o in analysis["observations"]:
        base = {k: o[k] for k in ("line", "session_id", "seq", "kind", "rat",
            "received_elapsed_ns", "measurement_elapsed_ns", "source_time_status", "age_ns",
            "stale_by_policy", "chronology_valid", "duplicate_status", "raw_json")}
        base.update(clock_segment=o["segment"], received_unix_ms=o["record"]["received_unix_ms"],
                    source_elapsed_ns=o["record"]["source_elapsed_ns"],
                    identity_json=exact_json(o["identity"]))
        for m in o["metrics"] or [{"source_field": None, "metric": None, "unit": None,
                                  "raw_value": None, "value": None, "value_status": "no_metrics"}]:
            writer.writerow({**base, **{k: m[k] for k in ("source_field", "metric", "unit", "value", "value_status")},
                             "raw_value_json": exact_json(m["raw_value"])})
    return stream.getvalue()


def wifi_band_channel(frequency):
    if type(frequency) is not int:
        return None, None
    if frequency == 2484:
        return "2.4 GHz", 14
    if 2412 <= frequency <= 2472 and (frequency - 2407) % 5 == 0:
        return "2.4 GHz", (frequency - 2407) // 5
    if 5000 <= frequency < 5925 and frequency % 5 == 0:
        return "5 GHz", (frequency - 5000) // 5
    if frequency == 5935:
        return "6 GHz", 2
    if 5955 <= frequency <= 7115 and (frequency - 5950) % 5 == 0:
        return "6 GHz", (frequency - 5950) // 5
    return "other", None


def radio_inventory(analysis):
    channels, cells, batches = {}, {}, {}
    for o in analysis["observations"]:
        if not o["chronology_valid"]:
            continue
        p = o["record"]["payload"]
        identity = exact_json(o["identity"])
        fresh = o["measurement_elapsed_ns"] is not None and not o["stale_by_policy"]
        unique = o["duplicate_status"] == "unique_timestamped_observation"
        scope = (o["session_id"], o["segment"])
        if o["kind"] == "wifi":
            frequency = p.get("frequency_mhz")
            key = (*scope, exact_json(frequency))
            band, channel = wifi_band_channel(frequency)
            entry = channels.setdefault(key, {"session_id": scope[0], "clock_segment": scope[1],
                "frequency_mhz": frequency, "band": band, "primary_channel": channel,
                "records": 0, "unique_timestamped_observations": 0, "stale_records": 0,
                "unknown_freshness_records": 0, "identities": set(), "fresh_identities": set(),
                "fresh_unique_rssi_dbm": []})
            entry["records"] += 1
            entry["unique_timestamped_observations"] += unique
            entry["stale_records"] += o["stale_by_policy"]
            entry["unknown_freshness_records"] += o["measurement_elapsed_ns"] is None
            if o["identity"] is not None:
                entry["identities"].add(identity)
                if fresh:
                    entry["fresh_identities"].add(identity)
            if fresh and unique and type(p.get("rssi_dbm")) is int:
                entry["fresh_unique_rssi_dbm"].append(p["rssi_dbm"])
            if p.get("batch_id") is not None:
                batch_key = (*scope, exact_json(p["batch_id"]))
                batch = batches.setdefault(batch_key, {"session_id": scope[0], "clock_segment": scope[1],
                    "batch_id": p["batch_id"], "first_received_elapsed_ns": str(o["received_elapsed_ns"]),
                    "last_received_elapsed_ns": str(o["received_elapsed_ns"]), "records": 0,
                    "fresh_by_policy_records": 0, "stale_records": 0})
                batch["first_received_elapsed_ns"] = str(min(int(batch["first_received_elapsed_ns"]), o["received_elapsed_ns"]))
                batch["last_received_elapsed_ns"] = str(max(int(batch["last_received_elapsed_ns"]), o["received_elapsed_ns"]))
                batch["records"] += 1
                batch["fresh_by_policy_records"] += fresh
                batch["stale_records"] += o["stale_by_policy"]
        else:
            key = (*scope, identity)
            entry = cells.setdefault(key, {"session_id": scope[0], "clock_segment": scope[1],
                "identity": o["identity"], "rat": o["rat"], "records": 0,
                "registered_records": 0, "neighbor_records": 0,
                "unique_timestamped_observations": 0, "stale_records": 0})
            entry["records"] += 1
            entry["registered_records"] += p.get("registered") is True
            entry["neighbor_records"] += p.get("registered") is False
            entry["unique_timestamped_observations"] += unique
            entry["stale_records"] += o["stale_by_policy"]
    channel_rows = []
    for key, entry in sorted(channels.items(), key=lambda item: str(item[0])):
        powers = entry.pop("fresh_unique_rssi_dbm")
        entry["distinct_ap_identities"] = len(entry.pop("identities"))
        entry["fresh_by_policy_ap_identities"] = len(entry.pop("fresh_identities"))
        entry["fresh_rssi_dbm_min"] = min(powers) if powers else None
        entry["fresh_rssi_dbm_max"] = max(powers) if powers else None
        channel_rows.append(entry)
    return {"wifi_channels": channel_rows, "wifi_batches": list(batches.values()),
        "reported_cells": list(cells.values()),
        "meaning": "Counts of reported AP identities on their reported primary frequencies, not channel utilization or physical router counts. Freshness uses the named study threshold. Registered/neighbor values are reported fields; cell changes alone do not establish handovers."}


def summary_markdown(summary) -> str:
    counts = summary["observation_status_counts"]
    text = ["# aTOMos R21 radio study", "", f"Data origin: **{summary['data_origin']}**.", "",
        "Study label: " + (summary.get("study_label") or "not supplied"), "", summary["interpretation"], "",
        f"Input: {summary['input_bytes']} bytes; SHA256 `{summary['input_sha256']}`.", "",
        f"{summary['line_count']} JSONL lines, {len(summary['invalid_rows'])} invalid rows, "
        f"{summary['radio_records']} radio records. Final line unterminated: {summary['final_line_unterminated']}.", "",
        "| Observation status | Records |", "|---|---:|"]
    text.extend(f"| {key} | {value} |" for key, value in sorted(counts.items()))
    text += ["", "Counts describe records and cache equivalence, not statistically independent samples.", "",
        f"Stale study policy: age > {summary['study_policy']['stale_after_seconds']} s; "
        f"{summary['stale_by_policy_records']} records meet that policy. They remain in the export.", "",
        "## Metric groups", "", "Only unambiguous unique timestamped observations enter these descriptive groups.", "",
        "Each row is one link, session and elapsed-clock segment; RSSNR source unit profiles remain separate.", "",
        "| Link / session / clock | Kind / RAT | Source field | Unit | Count | Min | Max | Mean |",
        "|---|---|---|---|---:|---:|---:|---:|"]
    for g in summary["metric_statistics"]:
        text.append(f"| {identity_label(g['identity'])} / {g['session_id'][:8]} / {g['clock_segment']} | "
                    f"{g['kind']} / {g['rat']} | {g['source_field']} | {g['unit']} | "
                    f"{g['unique_timestamped_count']} | {g['min']} | {g['max']} | {g['mean']} |")
    text += ["", "## Event and distinct-observation rates", "",
        "Counts divided by the covered receipt interval, separately for each session and clock segment. "
        "These rates do not specify RF sample rate or statistical independence.", ""]
    text.extend("- " + exact_json(r) for r in summary["covered_interval_rates"])
    if summary.get("radio_inventory"):
        inventory = summary["radio_inventory"]
        text += ["", "## Observed Wi-Fi primary channels", "", inventory["meaning"], "",
            "| MHz | Band / channel | AP identities | Fresh AP identities | Stale records | Fresh RSSI span dBm |",
            "|---:|---|---:|---:|---:|---|"]
        for channel in inventory["wifi_channels"]:
            text.append(f"| {channel['frequency_mhz']} | {channel['band']} / {channel['primary_channel']} | "
                f"{channel['distinct_ap_identities']} | {channel['fresh_by_policy_ap_identities']} | "
                f"{channel['stale_records']} | {channel['fresh_rssi_dbm_min']} to {channel['fresh_rssi_dbm_max']} |")
    text += ["", "## Sessions", ""]
    text.extend("- " + exact_json(s) for s in summary["sessions"])
    text += ["", "## Status and markers", ""]
    text.extend(f"- Line {e['line']} / {e['record']['kind']}: `{exact_json(e['record']['payload'])}`"
                for e in summary["events"])
    text += ["", "## Input and clock issues", ""]
    text.extend("- " + exact_json(i) for i in summary["invalid_rows"] + summary["issues"])
    if not summary["invalid_rows"] and not summary["issues"]:
        text.append("None detected.")
    text += ["", "## Outputs", "", "`source_original.jsonl` and `source_original.aradbp` retain the original bytes. "
        "The bit-plane archive is a reversible permutation with length and SHA256, not compression. "
        "`normalized.csv` keeps raw JSON beside each scalar metric; unknown metrics keep unknown units.", "",
        "Plots use elapsed time from each session/clock segment's first received record. Source timestamps identify "
        "Wi-Fi last-seen or modem-reported receipt time. Missing/invalid source timestamps use a separately "
        "labeled receipt-time marker. No interpolation between records is drawn.", ""]
    return "\n".join(text)


def identity_label(identity):
    if identity is None:
        return "unknown radio identity"
    if identity.get("kind") == "wifi":
        return f"AP {identity.get('bssid')} @ {identity.get('frequency_mhz')} MHz"
    cell = identity.get("identity", {})
    identifier = next((f"{k}={cell[k]}" for k in ("nci", "ci", "cid", "basestation_id")
                       if cell.get(k) is not None), exact_json(cell))
    return f"sub {identity.get('subscription_id')}, {identifier}"


def plot_signals(analysis, directory: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    groups = defaultdict(list)
    for o in analysis["observations"]:
        if not o["chronology_valid"] or o["duplicate_status"] in {"cached_duplicate", "inconsistent_same_timestamp"}:
            continue
        for m in o["metrics"]:
            if m["value"] is not None:
                groups[(o["kind"], o["rat"], m["source_field"], m["unit"])].append((o, m))
    artifacts = []
    index = 0
    for key, records in sorted(groups.items(), key=lambda pair: str(pair[0])):
        series = defaultdict(list)
        origins = {(r["session_id"], r["clock_segment"]): int(r["first_received_elapsed_ns"])
                   for r in analysis["summary"]["covered_interval_rates"]}
        for o, m in records:
            source = o["measurement_elapsed_ns"]
            timestamp = source if source is not None else o["received_elapsed_ns"]
            origin = origins[(o["session_id"], o["segment"])]
            identity = exact_json(o["identity"])
            basis = "reported source time" if source is not None else "receipt time only"
            label = (o["session_id"], o["segment"], identity, basis)
            series[label].append(((timestamp - origin) / NS, float(m["value"])))
        ordered_series = sorted(series.items())
        for offset in range(0, len(ordered_series), 8):
            index += 1
            page = ordered_series[offset:offset + 8]
            fig, ax = plt.subplots(figsize=(10, 6.4), constrained_layout=True)
            for series_index, (series_label, points) in enumerate(page, 1):
                basis = series_label[-1]
                ax.scatter([p[0] for p in points], [p[1] for p in points], s=30,
                           marker="o" if basis == "reported source time" else "x",
                           label=f"{identity_label(parse_json(series_label[2]))}; {series_label[0][:8]} / clock {series_label[1]}; {basis}")
            origin = analysis["summary"]["data_origin"]
            title_prefix = ("SYNTHETIC — " if origin == "declared_synthetic_fixture" else
                            "MIXED SYNTHETIC / UNLABELED — " if origin == "mixed_synthetic_and_unlabeled_sessions" else "")
            if analysis["summary"].get("study_label"):
                title_prefix += analysis["summary"]["study_label"] + "\n"
            radio_title = "Wi-Fi" if key[0] == "wifi" else f"Cell / {key[1]}"
            part = f" · links {offset + 1}–{offset + len(page)} of {len(ordered_series)}"
            ax.set(title=f"{title_prefix}{radio_title} — {key[2]}{part}",
                   xlabel="Elapsed seconds from session/clock segment start (negative: earlier cached report)", ylabel=key[3])
            ax.grid(alpha=.25)
            ax.legend(fontsize=7, loc="upper left", bbox_to_anchor=(0, -.18), borderaxespad=0)
            filename = f"signal_{index:02d}.png"
            fig.savefig(directory / filename, dpi=150)
            plt.close(fig)
            artifacts.append({"file": filename, "kind": key[0], "rat": key[1],
                              "source_field": key[2], "unit": key[3],
                              "series": [{"label": i + 1, "session_id": label[0],
                                          "clock_segment": label[1], "identity_json": label[2],
                                          "time_basis": label[3]}
                                         for i, (label, _) in enumerate(page)]})
    return artifacts


def plot_inventory(analysis, directory: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    artifacts = []
    summary = analysis["summary"]
    prefix = "SYNTHETIC — " if summary["data_origin"] == "declared_synthetic_fixture" else ""
    prefix += (summary.get("study_label") + "\n") if summary.get("study_label") else ""
    origins = {(r["session_id"], r["clock_segment"]): int(r["first_received_elapsed_ns"])
               for r in summary["covered_interval_rates"]}
    age_groups = defaultdict(list)
    unknown = 0
    for o in analysis["observations"]:
        if not o["chronology_valid"]:
            continue
        if o["age_ns"] is None:
            unknown += 1
            continue
        origin = origins[(o["session_id"], o["segment"])]
        age_groups[(o["kind"], o["session_id"], o["segment"])].append(
            ((o["received_elapsed_ns"] - origin) / NS, o["age_ns"] / NS))
    if age_groups:
        fig, ax = plt.subplots(figsize=(10, 5.5), constrained_layout=True)
        for (kind, sid, segment), points in sorted(age_groups.items()):
            ax.scatter([v[0] for v in points], [v[1] for v in points], s=20,
                       label=f"{kind}, {sid[:8]} / clock {segment}")
        threshold = float(summary["study_policy"]["stale_after_seconds"])
        ax.axhline(threshold, linestyle="--", color="black", linewidth=1,
                   label=f"Stale policy: age > {threshold:g} s")
        ax.set_yscale("symlog", linthresh=1)
        ax.set_ylim(bottom=0)
        ax.set(title=prefix + "Age of reported source observations at receipt",
               xlabel="Receipt elapsed seconds from session/clock segment start",
               ylabel="Reported observation age, seconds (symmetric log scale above 1 s)")
        ax.text(.01, .99, f"All records, including cached repeats. Unknown/invalid source time: {unknown} records.",
                transform=ax.transAxes, va="top", fontsize=8)
        ax.legend(fontsize=8, loc="lower right")
        ax.grid(alpha=.25)
        fig.savefig(directory / "observation_freshness.png", dpi=150)
        plt.close(fig)
        artifacts.append({"file": "observation_freshness.png", "family": "reported_observation_age",
                          "unknown_or_invalid_source_records": unknown})
    channels = summary.get("radio_inventory", {}).get("wifi_channels", [])
    if channels:
        by_scope = defaultdict(list)
        for channel in channels:
            by_scope[(channel["session_id"], channel["clock_segment"])].append(channel)
        for index, ((sid, segment), rows) in enumerate(sorted(by_scope.items()), 1):
            rows.sort(key=lambda r: (type(r["frequency_mhz"]) is not int, str(r["frequency_mhz"])))
            fig, ax = plt.subplots(figsize=(10, 5.5), constrained_layout=True)
            x = list(range(len(rows)))
            ax.bar([v - .2 for v in x], [r["distinct_ap_identities"] for r in rows], width=.4,
                   color="#8995a3", label="All reported AP identities, including older cache")
            ax.bar([v + .2 for v in x], [r["fresh_by_policy_ap_identities"] for r in rows], width=.4,
                   color="#1675bb", label="AP identities fresh under the study policy")
            ax.set_xticks(x, [f"{r['frequency_mhz']}\nch {r['primary_channel']}" for r in rows])
            ax.set(title=prefix + "Reported Wi-Fi AP identities by primary frequency",
                   xlabel=f"Reported frequency (MHz) / primary channel · session {sid[:8]} / clock {segment}",
                   ylabel="Distinct reported AP identities")
            ax.text(.01, .99, "Observation counts, not airtime utilization or physical router counts.",
                    transform=ax.transAxes, va="top", fontsize=8)
            ax.legend(fontsize=8, loc="upper right")
            ax.grid(axis="y", alpha=.25)
            filename = f"observed_wifi_channels_{index:02d}.png"
            fig.savefig(directory / filename, dpi=150)
            plt.close(fig)
            artifacts.append({"file": filename, "family": "observed_wifi_primary_channels",
                              "session_id": sid, "clock_segment": segment})
    return artifacts


def study_file(source: Path, output: Path, *, plots=True, label=None, **policies):
    source, output = Path(source), Path(output)
    targets = [output / name for name in ("source_original.jsonl", "source_original.aradbp",
               "normalized.csv", "summary.json", "summary.md")]
    if any(source.resolve() == path.resolve() for path in targets):
        raise ValueError("study output must not overwrite input")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("study output must be a new or empty directory")
    original = source.read_bytes()
    analysis = analyze_bytes(original, **policies)
    analysis["summary"]["study_label"] = label
    analysis["summary"]["radio_inventory"] = radio_inventory(analysis)
    output.mkdir(parents=True, exist_ok=True)
    (output / "source_original.jsonl").write_bytes(original)
    archive = pack_bytes(original)
    if unpack_bytes(archive) != original:
        raise AssertionError("archive round-trip failed")
    (output / "source_original.aradbp").write_bytes(archive)
    (output / "normalized.csv").write_text(normalized_csv(analysis), encoding="utf-8", newline="")
    summary = analysis["summary"]
    summary["archive"] = {"profile": "ARADBP1", "bytes": len(archive),
                          "sha256": hashlib.sha256(archive).hexdigest(), "roundtrip_verified": True}
    summary["plots"] = plot_signals(analysis, output) + plot_inventory(analysis, output) if plots else []
    (output / "summary.json").write_text(exact_json(summary) + "\n", encoding="utf-8")
    (output / "summary.md").write_text(summary_markdown(summary), encoding="utf-8")
    return summary
