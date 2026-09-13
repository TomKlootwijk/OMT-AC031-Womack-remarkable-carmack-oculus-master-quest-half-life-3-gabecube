"""Declared scalar SDF regions on the M1 flat normalized Klein quotient.

The compiler evaluates signed distances, then packs their signs. The verifier
uses independently enumerated site/deck images, not a second compiler call.
"""
from __future__ import annotations
import copy
import hashlib
import json
import math
from pathlib import Path
import struct
import numpy as np

MAGIC = b"AOSDF01\n"
PLANES = ("asa", "na", "boundary", "fringe")
M1_SHA256 = "b51651c007c560775ff1950e278789cd7674e131ec71a09ebd9254cebe9c19ce"
NOR_SITES = {"asa": (0, 1, 2), "na": (0, 1, 2), "boundary": (1, 2), "fringe": (0, 1, 2)}


def default_config(profile="geometry", rows=128, angles=1024):
    result = {"profile": profile, "rows": rows, "angles": angles,
              "r_min": .25, "r_max": 64., "r_star": 1.}
    if profile == "geometry":
        result["planes"] = {
            "asa": [{"kind": "disk", "center": [.23, .02], "radius": .22}],
            "na": [{"kind": "disk", "center": [.23, .02], "radius": .18}],
            "boundary": [{"kind": "annulus", "center": [.23, .02], "inner": .13, "outer": .15}],
            "fringe": [{"kind": "annulus", "center": [.23, .02], "inner": .06, "outer": .20}],
        }
    return result


def canonical(u, v):
    winding = np.floor(v)
    return np.mod(np.where(np.mod(winding, 2) == 0, u, -u), 1.), np.mod(v, 1.)


def quotient_distance(u, v, center):
    """Nearest even/odd deck images under ds²=du²+dv²."""
    u, v = canonical(np.asarray(u, dtype=float), np.asarray(v, dtype=float))
    cu, cv = center
    even_u = np.mod(u - cu + .5, 1.) - .5
    odd_u = np.mod(u + cu + .5, 1.) - .5
    dv = v - cv
    return np.sqrt(np.minimum(even_u * even_u + dv * dv,
                              odd_u * odd_u + (1. - np.abs(dv)) ** 2))


def prepare_config(config):
    c = copy.deepcopy(config)
    for key in ("rows", "angles"):
        if type(c.get(key)) is not int or not 1 <= c[key] <= 65536:
            raise ValueError(f"{key} must be an integer in 1..65536")
    rows, angles = c["rows"], c["angles"]
    stored = ((rows + 7) // 8 * 8) * ((((angles + 31) // 32 + 7) // 8) * 8)
    if stored > 1 << 20:
        raise ValueError("declared capacity profile permits at most 2^20 padded texels (16 MiB four-plane atlas)")
    for key, default in (("r_min", .25), ("r_max", 64.), ("r_star", 1.)):
        c[key] = float(c.get(key, default))
        if not math.isfinite(c[key]) or c[key] <= 0:
            raise ValueError(f"invalid positive log-chart parameter {key}")
    if c["r_max"] <= c["r_min"]:
        raise ValueError("r_max must exceed r_min")
    if c.get("profile") == "nor_sites":
        if angles < 32 or angles % 32:
            raise ValueError("nor_sites requires angles>=32 and a multiple of 32")
        c.pop("planes", None)
        c["radius"] = .2 * min(1. / rows, 1. / angles)
    elif c.get("profile") == "geometry":
        if not isinstance(c.get("planes"), dict) or set(c["planes"]) != set(PLANES):
            raise ValueError("geometry requires exactly asa, na, boundary, fringe primitive lists")
        for name in PLANES:
            if not isinstance(c["planes"][name], list):
                raise ValueError("plane primitives must be a list")
            bounds = []
            for p in c["planes"][name]:
                if p.get("kind") not in ("disk", "annulus"):
                    raise ValueError("primitive kind must be disk or annulus")
                center = p.get("center")
                if not isinstance(center, list) or len(center) != 2 or not all(math.isfinite(x) and 0 <= x < 1 for x in center):
                    raise ValueError("primitive center must be two canonical normalized coordinates in [0,1)")
                outer = float(p["radius"] if p["kind"] == "disk" else p["outer"])
                inner = 0. if p["kind"] == "disk" else float(p["inner"])
                if not (math.isfinite(outer) and math.isfinite(inner) and 0 <= inner < outer < .5):
                    raise ValueError("radii must satisfy 0<=inner<outer<0.5 (injectivity bound)")
                for other, radius in bounds:
                    if float(quotient_distance(*center, other)) <= outer + radius:
                        raise ValueError("same-plane primitive bounding disks must be disjoint")
                bounds.append((center, outer))
    else:
        raise ValueError("profile must be geometry or nor_sites")
    return c


def evaluate_sdf(config, plane, u, v):
    """Scalar-field evaluation; numpy arrays provide bounded vectorized batches."""
    u, v = canonical(np.asarray(u, dtype=float), np.asarray(v, dtype=float))
    if config["profile"] == "nor_sites":
        rows, angles = config["rows"], config["angles"]
        radial = (u * rows - .5 - np.rint(u * rows - .5)) / rows
        angular = np.full_like(v, np.inf)
        for site in NOR_SITES[plane]:
            angular = np.minimum(angular, np.abs(np.mod(v * angles - site + 16., 32.) - 16.) / angles)
        return np.hypot(radial, angular) - config["radius"]
    result = np.full(np.broadcast_shapes(u.shape, v.shape), np.inf)
    for primitive in config["planes"][plane]:
        distance = quotient_distance(u, v, primitive["center"])
        value = (distance - primitive["radius"] if primitive["kind"] == "disk" else
                 np.maximum(primitive["inner"] - distance, distance - primitive["outer"]))
        result = np.minimum(result, value)
    return result


def reference_sdf_point(config, plane, u, v):
    """Independent scalar enumeration on the covering plane, including seams."""
    if config["profile"] == "nor_sites":
        rows, angles = config["rows"], config["angles"]
        ri = math.floor(u * rows - .5)
        gi = math.floor(v * angles / 32.)
        distance = math.inf
        # Reflection permutes the complete radial-center lattice, so the lifted
        # site set is exactly this Cartesian product on the covering plane.
        for row in range(ri - 1, ri + 3):
            for group in range(gi - 1, gi + 3):
                for site in NOR_SITES[plane]:
                    distance = min(distance, math.hypot(u - (row + .5) / rows,
                                                       v - (32 * group + site) / angles))
        return distance - config["radius"]
    value = math.inf
    for p in config["planes"][plane]:
        cu, cv = p["center"]
        distance = math.inf
        n0 = math.floor(v - cv)
        for n in range(n0 - 1, n0 + 3):
            image_u = -cu if n % 2 else cu
            m0 = math.floor(u - image_u)
            for m in range(m0 - 1, m0 + 3):
                distance = min(distance, math.hypot(u - image_u - m, v - cv - n))
        signed = distance - p["radius"] if p["kind"] == "disk" else max(p["inner"] - distance, distance - p["outer"])
        value = min(value, signed)
    return value


def _pack(bits, angles):
    padding = (-angles) % 32
    if padding:
        bits = np.pad(bits, ((0, 0), (0, padding)))
    return np.packbits(bits, axis=1, bitorder="little").copy().view("<u4")


def _seam_audit(config):
    maximum = 0.
    tested = 0
    for plane in PLANES:
        for u, v in ((.13, .02), (.77, .94), (.5, 0.), (0., .4), (.99, .999), (-.23, -1.4)):
            base = float(evaluate_sdf(config, plane, u, v))
            reference = reference_sdf_point(config, plane, u, v)
            for candidate in (reference, float(evaluate_sdf(config, plane, u + 1., v)),
                              float(evaluate_sdf(config, plane, -u, v + 1.)),
                              float(evaluate_sdf(config, plane, -u, v - 1.))):
                if math.isinf(base) and base == candidate:
                    continue
                error = abs(base - candidate)
                if not math.isfinite(error) or error > 2e-12:
                    raise AssertionError("SDF scalar/deck/seam mismatch")
                maximum = max(maximum, error)
                tested += 1
    return {"comparisons": tested, "maximum_abs_error": maximum,
            "relations": ["d(u+1,v)=d(u,v)", "d(-u,v+1)=d(u,v)", "negative angular seam"]}


def compile_atlas(config):
    c = prepare_config(config)
    rows, angles = c["rows"], c["angles"]
    words = (angles + 31) // 32
    batch_rows = max(1, 65536 // angles)
    v = np.arange(angles, dtype=float)[None, :] / angles
    planes, margins, counts = {}, {}, {}
    for name in PLANES:
        plane = np.empty((rows, words), dtype="<u4")
        minimum = math.inf
        occupied = 0
        for start in range(0, rows, batch_rows):
            end = min(rows, start + batch_rows)
            u = (np.arange(start, end, dtype=float)[:, None] + .5) / rows
            distance = evaluate_sdf(c, name, u, v)
            bits = distance <= 0.
            minimum = min(minimum, float(np.min(np.abs(distance))))
            occupied += int(np.count_nonzero(bits))
            plane[start:end] = _pack(bits, angles)
        planes[name] = plane
        margins[name] = minimum if math.isfinite(minimum) else None
        counts[name] = occupied
    payload = MAGIC + struct.pack("<II", rows, angles) + b"".join(planes[p].tobytes() for p in PLANES)
    stored = ((rows + 7) // 8 * 8) * ((words + 7) // 8 * 8)
    manifest = {"schema": "atomos-sdf-atlas-v1", "concept_author": "Tom Klootwijk",
                "construction": "NEW explicit scalar SDF profile; not a recovered original distance/optical law",
                "source": {"master_sha256": M1_SHA256, "physical_pdf_pages": [9, 10, 16, 17, 18, 27, 31, 32],
                           "original_white_king_pages": [33, 34, 35, 63, 67, 76, 85, 86, 87]},
                "topology": "klein_m1_angular_twist", "metric": "flat_normalized_quotient: ds^2=du^2+dv^2",
                "deck_map": "(u,v)->((-1)^n*u+m,v+n), m,n integers",
                "nodes": "radial_centers_angular_nodes", "log_chart": "rho=ln(r/r_star), u=(rho-rho_min)/(rho_max-rho_min), v=phi/(2*pi)",
                "sign": "inside/on boundary iff scalar SDF<=0; stored bit1", "profile": c["profile"],
                "parameters": c, "rows": rows, "angles": angles, "words_per_row": words,
                "plane_order": list(PLANES), "packing": "32 angular nodes per little-endian u32, canonical row-major; tail bits zero",
                "stored_texels": stored, "canonical_plane_payload_bytes": len(payload) - 16,
                "padded_four_plane_bytes": 16 * stored,
                "capacity_profile": {"max_padded_texels": 1 << 20, "max_padded_four_plane_bytes": 16 << 20,
                                     "cache_residency": "not measured by compiler"},
                "minimum_abs_sdf": margins, "set_bits": counts, "seam_tests": _seam_audit(c),
                "atlas_sha256": hashlib.sha256(payload).hexdigest()}
    if c["profile"] == "nor_sites":
        manifest["site_offsets"] = {k: list(v) for k, v in NOR_SITES.items()}
        manifest["independent_expected_word_masks"] = [7, 7, 6, 7]
    return payload, manifest


def _independent_membership(c, plane, start, end):
    rows, angles = c["rows"], c["angles"]
    j = np.arange(angles, dtype=np.int64)[None, :]
    if c["profile"] == "nor_sites":
        # Independently enumerate neighboring lifted site columns. At every
        # sampled radial center the matching (possibly reflected) site row is
        # present, so its radial distance is exactly zero in the real profile.
        nearest = np.full((1, angles), np.inf)
        groups = j // 32
        for neighbor in (-1, 0, 1):
            for site in NOR_SITES[plane]:
                nearest = np.minimum(nearest, np.abs(j - (32 * (groups + neighbor) + site)) / angles)
        bits = nearest <= c["radius"]
        expected = np.isin(j % 32, NOR_SITES[plane])
        if not np.array_equal(bits, expected):
            raise AssertionError("NOR scalar-site reference disagrees with exact discrete membership")
        return np.broadcast_to(bits, (end - start, angles))
    u = (np.arange(start, end, dtype=float)[:, None] + .5) / rows
    v = j.astype(float) / angles
    accepted = np.zeros((end - start, angles), dtype=bool)
    for p in c["planes"][plane]:
        cu, cv = p["center"]
        squared = np.full((end - start, angles), np.inf)
        for n in (-1, 0, 1):
            center_u = ((-cu) % 1.) if n % 2 else cu
            for m in (-1, 0, 1):
                dx, dy = u - (center_u + m), v - (cv + n)
                squared = np.minimum(squared, dx * dx + dy * dy)
        distance = np.sqrt(squared)
        accepted |= (distance <= p["radius"] if p["kind"] == "disk" else
                     (distance >= p["inner"]) & (distance <= p["outer"]))
    return accepted


def verify_atlas(path):
    path = Path(path)
    manifest_path = path.with_suffix(".json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw = path.read_bytes()
    if manifest.get("schema") != "atomos-sdf-atlas-v1" or hashlib.sha256(raw).hexdigest() != manifest.get("atlas_sha256"):
        raise ValueError("SDF manifest/binary hash mismatch")
    if len(raw) < 16 or raw[:8] != MAGIC:
        raise ValueError("invalid SDF binary header")
    rows, angles = struct.unpack_from("<II", raw, 8)
    c = prepare_config(manifest["parameters"])
    if (rows, angles) != (c["rows"], c["angles"]) or (rows, angles) != (manifest["rows"], manifest["angles"]):
        raise ValueError("SDF manifest/binary dimension mismatch")
    if manifest.get("topology") != "klein_m1_angular_twist" or manifest.get("plane_order") != list(PLANES) or manifest.get("profile") != c["profile"]:
        raise ValueError("SDF representation metadata mismatch")
    if (manifest.get("metric") != "flat_normalized_quotient: ds^2=du^2+dv^2" or
            manifest.get("nodes") != "radial_centers_angular_nodes" or
            manifest.get("sign") != "inside/on boundary iff scalar SDF<=0; stored bit1"):
        raise ValueError("SDF metric/node/sign metadata mismatch")
    words = (angles + 31) // 32
    expected_length = 16 + 16 * rows * words
    if len(raw) != expected_length:
        raise ValueError("SDF atlas length mismatch")
    arrays = np.frombuffer(raw, dtype="<u4", offset=16).reshape(4, rows, words)
    planes = {name: arrays[i] for i, name in enumerate(PLANES)}
    batch_rows = max(1, 65536 // angles)
    verified_bits = 0
    for name in PLANES:
        for start in range(0, rows, batch_rows):
            end = min(rows, start + batch_rows)
            expected = _independent_membership(c, name, start, end)
            actual_words = planes[name][start:end]
            # Decode independently by shifts, including every tail/padding bit.
            actual = ((actual_words[:, :, None] >> np.arange(32, dtype=np.uint32)) & 1).reshape(end - start, words * 32)
            if not np.array_equal(actual[:, :angles], expected) or np.any(actual[:, angles:]):
                raise AssertionError(f"SDF scalar/packed mismatch in {name}, rows {start}:{end}")
            verified_bits += (end - start) * angles
    seam_tests = _seam_audit(c)
    return {"manifest": manifest, "manifest_path": str(manifest_path), "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(), "rows": rows, "angles": angles,
            "words_per_row": words, "planes": planes, "verified_bits": verified_bits,
            "independent_all_bits_verified": True, "seam_tests": seam_tests}


def write_atlas(config, path):
    path = Path(path)
    manifest_path = path.with_suffix(".json")
    if path == manifest_path:
        raise ValueError("binary atlas path cannot use .json extension")
    if path.exists() or manifest_path.exists():
        raise FileExistsError("atlas or manifest already exists")
    payload, manifest = compile_atlas(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    manifest_path.write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    checked = verify_atlas(path)
    manifest["independent_all_bits_verified"] = True
    manifest["verified_bits"] = checked["verified_bits"]
    manifest_path.write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return {"atlas": str(path), "manifest": str(manifest_path), "atlas_sha256": manifest["atlas_sha256"],
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "verified_bits": checked["verified_bits"], "padded_four_plane_bytes": manifest["padded_four_plane_bytes"]}
