#!/usr/bin/env python3
"""Convert held-out 3D discrepancies to station-relative line-of-sight errors."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
import numpy as np
from geodesy import enu_matrix, geodetic_to_ecef
from orbit_dynamics import frame_matrix
from orbit_seed import default_stations, digest


def stats(values):
    a = np.asarray(values, dtype=float)
    return {"count": len(a), "rms": float(np.sqrt(np.mean(a*a))) if len(a) else None,
            "max_abs": float(np.max(np.abs(a))) if len(a) else None}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--accuracy", type=Path, required=True)
    p.add_argument("--models", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    report = json.loads(args.accuracy.read_text())
    summary = {"scope": "Station-relative consequences of the measured orbit discrepancy; no antenna beam or operational acceptance limit is assumed",
               "angles": "Simultaneous geometric, no atmospheric refraction or retarded light time",
               "source_accuracy_sha256": hashlib.sha256(args.accuracy.read_bytes()).hexdigest(), "objects": []}
    for obj in report["objects"]:
        model = json.loads((args.models / obj["model_file"]).read_text())["model"]
        if digest(model) != obj["physical_model_sha256"]: raise ValueError("Physical model differs from the accuracy evidence")
        path = args.accuracy.parent / obj["curve_file"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != obj["curve_sha256"]: raise ValueError("Curve hash differs")
        with path.open(newline="") as stream: rows = list(csv.DictReader(stream))
        stations = []
        for station in default_stations():
            lat, lon = math.radians(station["lat_deg"]), math.radians(station["lon_deg"])
            origin = np.asarray(geodetic_to_ecef(lat, lon, station["height_m"]))
            local = np.asarray(enu_matrix(lat, lon))
            results = []
            for row in rows:
                t = float(row["seconds_after_cutoff"])
                ref = np.array([float(row["reference_" + axis + "_m"]) for axis in ("x", "y", "z")])
                pred = np.array([float(row["predicted_" + axis + "_m"]) for axis in ("x", "y", "z")])
                if row["reference_frame"] not in ("IGS20_ECEF", "IGb20_ECEF"):
                    if row["reference_frame"] not in ("ICRF_geocentric", "ICRF_GCRS", "ICRF", "GCRS", "ICRF_GCRS_like"):
                        raise ValueError("Unknown frame: " + row["reference_frame"])
                    matrix = frame_matrix(model, t); ref, pred = matrix @ ref, matrix @ pred
                a, b = local @ (ref - origin), local @ (pred - origin)
                ra, rb = np.linalg.norm(a), np.linalg.norm(b)
                ua, ub = a / ra, b / rb
                separation = math.degrees(math.atan2(np.linalg.norm(np.cross(ua, ub)), float(ua @ ub)))
                el_a, el_b = math.degrees(math.atan2(a[2], math.hypot(a[0], a[1]))), math.degrees(math.atan2(b[2], math.hypot(b[0], b[1])))
                az_a, az_b = math.degrees(math.atan2(a[0], a[1])), math.degrees(math.atan2(b[0], b[1]))
                az_error = (az_b - az_a + 180.) % 360. - 180.
                results.append({"seconds_after_cutoff": t, "line_of_sight_error_deg": separation,
                    "azimuth_error_deg": az_error, "elevation_error_deg": el_b - el_a,
                    "range_error_m": float(rb - ra), "reference_range_m": float(ra),
                    "reference_elevation_deg": el_a, "reference_visible": el_a >= station["elevation_mask_deg"]})
            file = args.out / (obj["object_id"] + "_" + station["id"] + ".csv")
            with file.open("x", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(results[0])); writer.writeheader(); writer.writerows(results)
            visible = [r for r in results if r["reference_visible"]]
            first_day = [r for r in results if r["seconds_after_cutoff"] <= 86400 and r["reference_visible"]]
            stations.append({"station": station, "all_samples": len(results), "visible_reference_samples": len(visible),
                "all_line_of_sight_error_deg": stats([r["line_of_sight_error_deg"] for r in results]),
                "visible_line_of_sight_error_deg": stats([r["line_of_sight_error_deg"] for r in visible]),
                "visible_elevation_error_deg": stats([r["elevation_error_deg"] for r in visible]),
                "visible_range_error_m": stats([r["range_error_m"] for r in visible]), "curve": file.name})
            stations[-1]["first_day_visible_line_of_sight_error_deg"] = stats([r["line_of_sight_error_deg"] for r in first_day])
            stations[-1]["first_day_visible_range_error_m"] = stats([r["range_error_m"] for r in first_day])
        summary["objects"].append({"object_id": obj["object_id"], "physical_model_sha256": digest(model), "stations": stations})
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"objects": len(summary["objects"]), "status": "measured"}))


if __name__ == "__main__": main()
