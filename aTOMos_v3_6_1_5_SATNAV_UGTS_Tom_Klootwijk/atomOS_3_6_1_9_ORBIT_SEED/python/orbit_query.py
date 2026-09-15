"""Ground-station geometry, timestamp queries and explicit state-feedback schedule."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import math

import numpy as np
from scipy.optimize import brentq

from geodesy import enu_matrix, geodetic_to_ecef
from orbit_dynamics import state_to_ecef
from orbit_seed import digest, transition_ast
from ugts import contiguous, morton, otan2_source, phase_winding, quantize, wrap

GPS_EPOCH = datetime(1980, 1, 6, tzinfo=timezone.utc)


def timestamp_gpst(gpst_s):
    return (GPS_EPOCH + timedelta(seconds=float(gpst_s))).isoformat(timespec="milliseconds").replace("+00:00", " GPST")


def station_geometry(model, time_s, state, station):
    ecef = np.asarray(state_to_ecef(model, time_s, state))
    lat, lon = math.radians(station["lat_deg"]), math.radians(station["lon_deg"])
    origin = np.asarray(geodetic_to_ecef(lat, lon, station["height_m"]))
    matrix = np.asarray(enu_matrix(lat, lon))
    enu, velocity = matrix @ (ecef[:3] - origin), matrix @ ecef[3:]
    east, north, up = enu.tolist()
    horizontal, distance = math.hypot(east, north), float(np.linalg.norm(enu))
    if distance <= 0: raise ValueError("Satellite coincides with station")
    range_rate = float(enu @ velocity / distance)
    elevation = math.atan2(up, horizontal)
    # Derivative of sin(elevation) is finite even at zenith.
    sin_rate = float(velocity[2] / distance - up * range_rate / distance**2)
    elevation_rate = sin_rate / max(1.e-15, math.cos(elevation)) if horizontal > 1.e-6 else None
    azimuth = math.atan2(east, north) % (2 * math.pi) if horizontal > 1.e-6 else None
    azimuth_rate = float((north * velocity[0] - east * velocity[1]) / horizontal**2) if horizontal > 1.e-6 else None
    return {"ecef_m": ecef[:3].tolist(), "ecef_velocity_m_s": ecef[3:].tolist(),
            "station_ecef_m": origin.tolist(), "enu_m": enu.tolist(), "enu_velocity_m_s": velocity.tolist(),
            "up_m": up, "range_m": distance, "range_rate_m_s": range_rate,
            "azimuth_deg": math.degrees(azimuth) if azimuth is not None else None,
            "elevation_deg": math.degrees(elevation),
            "azimuth_rate_deg_s": math.degrees(azimuth_rate) if azimuth_rate is not None else None,
            "elevation_rate_deg_s": math.degrees(elevation_rate) if elevation_rate is not None else None,
            "sin_elevation_rate_s": sin_rate,
            "visible": math.degrees(elevation) >= station["elevation_mask_deg"],
            "angle_definition": "Simultaneous geometric topocentric; no refraction or light-time correction"}


def chart_record(seed, time_s, geometry):
    query = seed["query"]
    gpst = seed["model"]["epoch_gpst_s"] + time_s
    tick = math.floor(gpst / query["tick_s"])
    winding, phase = phase_winding(tick, 0, 1 << 14)
    e, n, _ = geometry["enu_m"]
    horizontal = math.hypot(e, n)
    result = {"absolute_tick": tick, "winding": winding, "tick_phase_fraction": phase,
              "tick_phase_index": tick % (1 << 14),
              "rho": None, "theta_rad": None, "phi_rad": query["phi_rad"],
              "contiguous_key_hex": None, "morton_key_hex": None,
              "key_role": "Spatial/time address; full state and Up remain outside the key"}
    if horizontal <= 0:
        result["status"] = "horizontal_origin_undefined"
        return result
    rho, theta = math.log(horizontal / query["chart_r0_m"]), math.atan2(n, e)
    result.update(rho=rho, theta_rad=theta)
    if not -20 <= rho <= 0:
        result["status"] = "outside_source_chart"
        return result
    indices = quantize(rho, theta, tick, query["phi_rad"])
    result.update(status="defined", indices=list(indices),
                  contiguous_key_hex=f"{contiguous(indices):016x}", morton_key_hex=f"{morton(indices):016x}")
    return result


def predicate_word(feedback, geometry, age_s, station):
    p = feedback["predicates"]
    drive = int(geometry["visible"])
    if abs(geometry["elevation_deg"] - station["elevation_mask_deg"]) <= p["near_mask_deg"]: drive |= 2
    if abs(age_s) >= p["age_warning_s"]: drive |= 4
    if geometry["elevation_rate_deg_s"] is not None and geometry["elevation_rate_deg_s"] > p["rising_rate_deg_s"]: drive |= 8
    if geometry["range_rate_m_s"] < 0: drive |= 16
    return drive & feedback["present"]


def _state(reply):
    status = reply.get("status", 0)
    if status not in (0, "ok", "OK", "success"):
        raise RuntimeError("Native orbital query failed: " + str(reply))
    state = reply.get("state_gcrs", reply.get("state"))
    if not isinstance(state, list) or len(state) != 6 or not all(math.isfinite(v) for v in state):
        raise RuntimeError("Invalid native orbital state")
    return state


def record_digest(record):
    # Runtime timings/cache occupancy are observations, not mathematical replay state.
    return digest({k: v for k, v in record.items() if k not in ("native", "record_sha256")})


class OrbitSession:
    def __init__(self, seed, worker, station_id=None):
        self.seed, self.worker = seed, worker
        stations = seed["stations"]
        self.station = next((s for s in stations if s["id"] == (station_id or stations[0]["id"])), None)
        if self.station is None: raise ValueError("Unknown station ID")
        self.seed_hash, self.model_hash = digest(seed), digest(seed["model"])

    def query(self, time_s):
        time_s = float(time_s)
        native = self.worker.query(time_s)
        state = _state(native)
        geometry = station_geometry(self.seed["model"], time_s, state, self.station)
        gpst = self.seed["model"]["epoch_gpst_s"] + time_s
        return {"seed_sha256": self.seed_hash, "model_sha256": self.model_hash,
                "object_id": self.seed["object"]["id"], "station_id": self.station["id"],
                "time_s": time_s, "time_gpst_s": gpst, "timestamp_gpst": timestamp_gpst(gpst),
                "state_gcrs_m_mps": state, **geometry, "chart": chart_record(self.seed, time_s, geometry),
                "model_age_s": time_s, "accuracy_status": "Model domain is not an accuracy guarantee; consult measured validation",
                "native": native}

    def schedule(self, start=None, end=None, max_records=100000):
        """Replay q from its declared initial state; native transitions determine time."""
        seed, feedback = self.seed, self.seed["feedback"]
        start = seed["query"]["start_s"] if start is None else float(start)
        end = seed["query"]["end_s"] if end is None else float(end)
        if not math.isfinite(start) or not math.isfinite(end) or end < start:
            raise ValueError("Finite ordered schedule interval required")
        q, t, previous, previous_chart, count = feedback["q0"], start, "0" * 64, None, 0
        while True:
            if count >= max_records: raise ValueError("Schedule record limit reached")
            record = self.query(t)
            drive = predicate_word(feedback, record, t, self.station)
            native_transition = self.worker.transition(feedback, q, drive)
            expected = transition_ast(feedback, q, drive)
            # Native adapter returns all fields. Independent AST is evidence, not the engine.
            actual = native_transition.get("trace", native_transition)
            for key in ("before", "drive", "x", "j", "k", "after"):
                if actual.get(key) != expected[key]: raise RuntimeError("Native/AST disagreement: " + key)
            for name, stage in zip(("stage_a", "stage_b"), expected["stages"]):
                for key in ("asa", "na", "hits", "output"):
                    if actual.get(name, {}).get(key) != stage[key]: raise RuntimeError("Native/AST disagreement: " + name + "." + key)
            q = actual["after"]
            cadence = feedback["cadence"]
            next_dt = cadence["fine_s"] if q & cadence["fine_bits"] else cadence["coarse_s"]
            chart = record["chart"]
            otan = {"status": "no_previous_chart", "value": None}
            if previous_chart and chart["status"] == previous_chart["status"] == "defined":
                otan = otan2_source(wrap(chart["theta_rad"] - previous_chart["theta_rad"]),
                                    chart["rho"] - previous_chart["rho"])
            record.update(index=count, feedback=actual, feedback_independent_ast=expected,
                          chosen_next_dt_s=next_dt, otan2_source=otan, previous_sha256=previous)
            record["record_sha256"] = record_digest(record)
            previous, previous_chart = record["record_sha256"], chart
            yield record
            count += 1
            if t == end: break
            next_time = min(end, t + next_dt)
            if next_time <= t: raise ValueError("Selected cadence cannot advance floating-point query time")
            t = next_time


def find_events(evaluate, start, end, step_s=120., tolerance_s=.01, max_samples=200000):
    """Refine sign changes and slope-bracketed extrema, retaining coverage limits.

    evaluate(t) returns (sin(el)-sin(mask), derivative of sin(el)). Finding roots
    of the derivative catches short passes with below-mask sampled endpoints when
    their maximum is bracketed. It is not an interval-arithmetic no-missed-root proof.
    """
    if not all(math.isfinite(float(v)) for v in (start, end, step_s, tolerance_s)) or end < start or min(step_s, tolerance_s) <= 0:
        raise ValueError("Invalid event-search interval/settings")
    size = math.ceil((end - start) / step_s) + 1
    if size > max_samples: raise ValueError("Event-search sample limit exceeded")
    memo = {}
    def at(t):
        t = float(t)
        if t not in memo:
            pair = tuple(float(v) for v in evaluate(t))
            if len(pair) != 2 or not all(math.isfinite(v) for v in pair): raise ValueError("Nonfinite event geometry")
            memo[t] = pair
        return memo[t]
    times = [start + (end - start) * j / (size - 1) for j in range(size)] if size > 1 else [start]
    extrema, roots, grazing = [], [], []
    for a, b in zip(times, times[1:]):
        fa, da = at(a); fb, db = at(b)
        if da * db < 0:
            peak = brentq(lambda t: at(t)[1], a, b, xtol=tolerance_s * .1)
            extrema.append(peak)
            if abs(at(peak)[0]) <= 1.e-9: grazing.append(peak)
        elif da == 0 and abs(fa) <= 1.e-9:
            grazing.append(a)
    knots = sorted(set(times + extrema))
    for a, b in zip(knots, knots[1:]):
        fa, _ = at(a); fb, _ = at(b)
        if fa == 0: roots.append(a)
        if fa * fb < 0:
            roots.append(brentq(lambda t: at(t)[0], a, b, xtol=tolerance_s))
    if at(end)[0] == 0: roots.append(end)
    unique = []
    for t in sorted(roots):
        if not unique or abs(t - unique[-1]) > tolerance_s: unique.append(t)
    events = [{"time_s": t, "kind": "rise" if at(t)[1] > 0 else "set" if at(t)[1] < 0 else "grazing",
               "residual_sin_elevation": at(t)[0]} for t in unique]
    vals = [at(t)[0] for t in knots]
    classification = "crossings_found" if events else "visible_over_searched_interval" if min(vals) > 0 else "hidden_over_searched_interval" if max(vals) < 0 else "grazing_or_boundary"
    return {"events": events, "grazing_candidates_s": sorted(set(grazing)),
            "extrema_s": sorted(set(extrema)), "classification": classification,
            "start_visible": at(start)[0] >= 0, "end_visible": at(end)[0] >= 0,
            "start_s": start, "end_s": end, "evaluations": len(memo), "max_sampling_step_s": step_s,
            "root_time_tolerance_s": tolerance_s,
            "coverage": "Sampled values plus derivative-bracketed extrema; no certified exclusion of multiple roots between samples",
            "uncertainty": "Time tolerance is numerical refinement, not predicted physical pass-time accuracy"}


def station_events(session, start=None, end=None, step_s=None):
    query = session.seed["query"]
    mask_sin = math.sin(math.radians(session.station["elevation_mask_deg"]))
    def evaluate(t):
        row = session.query(t)
        return math.sin(math.radians(row["elevation_deg"])) - mask_sin, row["sin_elevation_rate_s"]
    return find_events(evaluate, query["start_s"] if start is None else start,
                       query["end_s"] if end is None else end,
                       query["event_step_s"] if step_s is None else step_s,
                       query["event_tolerance_s"])
