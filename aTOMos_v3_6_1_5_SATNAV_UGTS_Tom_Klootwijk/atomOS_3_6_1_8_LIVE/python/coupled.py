"""CGK-R1 editable input, CSV compiler and independent NumPy/word-AST replay.

The native kernels use lookup tables, pivoted elimination and Jacobi rotations.
This reference evaluates original expression trees, uses NumPy's linear solver,
and computes symmetric eigenpairs with numpy.linalg.eigh.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
import json
import math
from pathlib import Path

import numpy as np

from self_reference import WORD, Expression, canonical_digest, compile_lut, file_digest, parse_expression
from ugts import cone_sdf, otan2_source, wrap as source_wrap

VERSION = "3.6.1.7"
PROFILE = "CGK-R1"
UINT64 = (1 << 64) - 1
VARIABLES = {
    "d": ("q", "align", "limit", "fringe", "support", "valid"),
    "x": ("q", "d", "align", "limit", "fringe", "support", "valid"),
    "j": ("q", "y", "d", "align", "limit", "fringe", "support", "valid"),
    "k": ("q", "y", "d", "align", "limit", "fringe", "support", "valid"),
}
DEFAULT_EQUATIONS = {"d": "limit | fringe", "x": "(q | d) & support",
                     "j": "y & (limit | fringe)", "k": "align & ~limit & ~fringe"}
MANIFEST_FIELDS = tuple(("trajectory_id,q0,present,asa_mask,na_mask,boundary_mask,initial_time,"
    "p0_e,p0_n,p0_u,v0_e,v0_n,v0_u,mass_e,mass_n,mass_u,damping_e,damping_n,damping_u,"
    "k00,k01,k02,k10,k11,k12,k20,k21,k22,r0,core,blend_weight,axis,hoop0,hoop_rate").split(","))
CHANNEL_FIELDS = tuple(("trajectory_id,channel,ux,uy,uz,k_off,k_on,force_off,force_on,angle_center,"
    "angle_tolerance,error_limit,fringe_width,support_kind,cx,cy,cz,support_extent,"
    "support_ax,support_ay,support_az,support_angle").split(","))
SAMPLE_FIELDS = tuple(("trajectory_id,epoch_id,time,valid,target_e,target_n,target_u,observed_x,observed_y,"
    "observed_z,clock_bias_m,force_e,force_n,force_u").split(","))
EQUATION_FIELDS = ("trajectory_id",) + tuple(f"{name}{i}" for name in VARIABLES for i in range(4))
EXACT_FIELDS = ("trajectory_id", "epoch_id", "step", "observation_valid", "q_before", "chart_status",
    "otan_status", "blend_status", "alignment", "limit", "fringe", "support", "drive", "x", "asa", "na",
    "hits", "output", "j", "k", "q_after", "status")
SCALAR_FIELDS = ("time_before", "time_after", "dt", "clock_bias_m", "phi_before", "rho", "theta",
                 "otan", "bearing", "blend", "eigen_residual", "phi_after")
VECTOR_FIELDS = {"target": 3, "observed_ecef": 3, "p_before": 3, "v_before": 3, "stiffness": 9,
    "eigenmatrix": 9, "eigenvalues": 3, "eigenvectors": 9, "force": 3, "mechanical_matrix": 9,
    "mechanical_rhs": 3, "p_after": 3, "v_after": 3}
TRACE_FIELDS = set(EXACT_FIELDS) | set(SCALAR_FIELDS) | set(VECTOR_FIELDS)


def wrap(value):
    """Source phase convention, propagating unavailable arithmetic into failure diagnostics."""
    return source_wrap(float(value)) if math.isfinite(value) else float("nan")


def _keys(value, required, optional=(), name="object"):
    if not isinstance(value, dict) or not set(required) <= set(value) or set(value) - set(required) - set(optional):
        raise ValueError(f"{name} requires {sorted(required)}; optional {sorted(optional)}")


def _uint(value, name, maximum=WORD):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f"{name} must be unsigned integer <= {maximum}")
    return value


def _number(value, name):
    if type(value) not in (int, float):
        raise ValueError(f"{name} must be a finite real number")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{name} must be representable as a finite FP64 number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite real number")
    return result


def _vector(value, name):
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{name} must contain three finite numbers")
    return [_number(item, name) for item in value]


def _unit(value, name):
    vector = _vector(value, name)
    if abs(sum(x * x for x in vector) - 1) > 1e-10:
        raise ValueError(f"{name} must be a unit vector")


def _equation_sources(value):
    if not isinstance(value, dict) or set(value) - set(VARIABLES):
        raise ValueError("equations accepts only d, x, j and k")
    return value


@dataclass
class Trajectory:
    id: int
    spec: dict
    equations: dict[str, Expression]

    @property
    def specification_hash(self):
        return canonical_digest({"profile": PROFILE, "spec": self.spec, "equations": {
            name: expr.canonical for name, expr in self.equations.items()}})


def parse_document(document):
    _keys(document, ("version", "profile", "trajectories"), ("equations", "description", "provenance"), "input")
    if document["version"] != VERSION or document["profile"] != PROFILE:
        raise ValueError(f"Input requires version {VERSION} and profile {PROFILE}")
    defaults = {**DEFAULT_EQUATIONS, **_equation_sources(document.get("equations", {}))}
    records = document["trajectories"]
    if not isinstance(records, list) or not records:
        raise ValueError("trajectories must be a nonempty list")
    result, identifiers = [], set()
    for record in records:
        _keys(record, ("id", "initial", "mass", "damping", "stiffness_base", "chart", "hoop", "masks",
                       "channels", "samples"), ("equations", "description"), "trajectory")
        identifier = _uint(record["id"], "trajectory id", UINT64)
        if identifier in identifiers:
            raise ValueError("Duplicate trajectory id")
        identifiers.add(identifier)
        initial = record["initial"]
        _keys(initial, ("time", "p", "v", "q", "phi"), name="initial")
        _number(initial["time"], "initial time"); _number(initial["phi"], "initial phase")
        _vector(initial["p"], "initial position"); _vector(initial["v"], "initial velocity")
        _uint(initial["q"], "initial q")
        mass = _vector(record["mass"], "mass")
        if any(m <= 0 for m in mass):
            raise ValueError("All masses must be positive")
        _vector(record["damping"], "damping")
        stiffness = record["stiffness_base"]
        if not isinstance(stiffness, list) or len(stiffness) != 3:
            raise ValueError("stiffness_base requires a symmetric 3x3 matrix")
        for row in stiffness:
            _vector(row, "stiffness row")
        if any(stiffness[i][j] != stiffness[j][i] for i in range(3) for j in range(3)):
            raise ValueError("stiffness_base must be exactly symmetric")
        chart = record["chart"]
        _keys(chart, ("r0", "core", "blend_weight", "axis"), name="chart")
        for name, value in chart.items():
            _number(value, name)
        if not chart["r0"] > chart["core"] > 0 or not 0 <= chart["blend_weight"] <= 1:
            raise ValueError("chart requires r0 > core > 0 and blend_weight in [0,1]")
        _keys(record["hoop"], ("rate",), name="hoop")
        _number(record["hoop"]["rate"], "hoop rate")
        masks = record["masks"]
        _keys(masks, ("present", "asa", "na", "boundary"), name="masks")
        for name, value in masks.items():
            _uint(value, name)
        if initial["q"] & ~masks["present"]:
            raise ValueError("Initial q must be a subset of present")
        channels, covered = record["channels"], 0
        if not isinstance(channels, list):
            raise ValueError("channels must be a list")
        for channel in channels:
            _keys(channel, ("index", "direction", "stiffness", "force", "angle_center", "angle_tolerance",
                            "error_limit", "fringe_width", "support"), name="channel")
            index = _uint(channel["index"], "channel index", 31)
            if covered & (1 << index):
                raise ValueError("Duplicate channel")
            covered |= 1 << index
            _unit(channel["direction"], "mechanical direction")
            for name in ("stiffness", "force"):
                _keys(channel[name], ("off", "on"), name=name)
                for value in channel[name].values():
                    _number(value, name)
            for name in ("angle_center", "angle_tolerance", "error_limit", "fringe_width"):
                _number(channel[name], name)
            if not 0 <= channel["angle_tolerance"] <= math.pi or channel["error_limit"] < 0 or channel["fringe_width"] < 0:
                raise ValueError("Invalid angular tolerance, error limit or fringe width")
            support = channel["support"]
            if not isinstance(support, dict) or support.get("kind") not in ("sphere", "cone"):
                raise ValueError("support kind must be sphere or cone")
            required = ("kind", "center", "radius") if support["kind"] == "sphere" else ("kind", "center", "axis", "slant", "half_angle")
            _keys(support, required, name="support")
            _vector(support["center"], "support center")
            if support["kind"] == "sphere":
                if _number(support["radius"], "sphere radius") <= 0:
                    raise ValueError("Sphere radius must be positive")
            else:
                _unit(support["axis"], "cone axis")
                if _number(support["slant"], "cone slant") <= 0 or not 0 < _number(support["half_angle"], "cone angle") < math.pi / 2:
                    raise ValueError("Invalid cone slant/angle")
        if covered != masks["present"]:
            raise ValueError("Channels must exactly cover the present mask")
        samples, epochs, previous = record["samples"], set(), initial["time"]
        if not isinstance(samples, list) or not samples:
            raise ValueError("samples must be a nonempty list")
        for sample in samples:
            _keys(sample, ("epoch_id", "time", "valid", "target", "observed_ecef", "clock_bias_m", "force"), name="sample")
            epoch = _uint(sample["epoch_id"], "epoch id", UINT64)
            if epoch in epochs:
                raise ValueError("Duplicate epoch within trajectory")
            epochs.add(epoch)
            time = _number(sample["time"], "sample time")
            if not time > previous or not math.isfinite(time - previous):
                raise ValueError("Sample times must increase strictly with finite intervals")
            previous = time
            if type(sample["valid"]) is not bool:
                raise ValueError("sample valid must be a JSON Boolean")
            for name in ("target", "observed_ecef", "force"):
                _vector(sample[name], name)
            _number(sample["clock_bias_m"], "clock bias")
        sources = {**defaults, **_equation_sources(record.get("equations", {}))}
        expressions = {name: parse_expression(sources[name], variables) for name, variables in VARIABLES.items()}
        result.append(Trajectory(identifier, json.loads(json.dumps(record, allow_nan=False)), expressions))
    return result


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key {key}")
            result[key] = value
        return result
    with Path(path).open(encoding="utf-8-sig") as stream:
        return json.load(stream, object_pairs_hook=unique)


def load_document(path):
    return parse_document(read_json(path))


def compiled_rows(trajectory):
    s = trajectory.spec
    initial, masks, chart = s["initial"], s["masks"], s["chart"]
    manifest = [trajectory.id, initial["q"], masks["present"], masks["asa"], masks["na"], masks["boundary"],
                initial["time"], *initial["p"], *initial["v"], *s["mass"], *s["damping"],
                *(x for row in s["stiffness_base"] for x in row), chart["r0"], chart["core"],
                chart["blend_weight"], chart["axis"], initial["phi"], s["hoop"]["rate"]]
    channels = []
    for c in sorted(s["channels"], key=lambda row: row["index"]):
        g = c["support"]
        sphere = g["kind"] == "sphere"
        channels.append([trajectory.id, c["index"], *c["direction"], c["stiffness"]["off"], c["stiffness"]["on"],
                         c["force"]["off"], c["force"]["on"], c["angle_center"], c["angle_tolerance"],
                         c["error_limit"], c["fringe_width"], 0 if sphere else 1, *g["center"],
                         g["radius"] if sphere else g["slant"], *(g.get("axis", [0., 0., 1.])),
                         0. if sphere else g["half_angle"]])
    samples = [[trajectory.id, row["epoch_id"], row["time"], int(row["valid"]), *row["target"],
                *row["observed_ecef"], row["clock_bias_m"], *row["force"]] for row in s["samples"]]
    equations = [trajectory.id]
    for name in VARIABLES:
        value = compile_lut(trajectory.equations[name])
        equations.extend((value >> (64 * i)) & UINT64 for i in range(4))
    return manifest, channels, samples, equations


def write_compiled(trajectories, folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    groups = [[], [], [], []]
    for trajectory in trajectories:
        manifest, channels, samples, equations = compiled_rows(trajectory)
        groups[0].append(manifest); groups[1].extend(channels); groups[2].extend(samples); groups[3].append(equations)
    for name, fields, rows in zip(("manifest", "channels", "samples", "equations"),
                                 (MANIFEST_FIELDS, CHANNEL_FIELDS, SAMPLE_FIELDS, EQUATION_FIELDS), groups):
        with (folder / f"{name}.csv").open("x", encoding="ascii", newline="") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(fields); writer.writerows(rows)


def circle_plus(a, b, weight):
    return wrap(a + weight * wrap(b - a))


def support_sdf(point, support):
    if support["kind"] == "sphere":
        return math.dist(point, support["center"]) - support["radius"]
    try:
        return cone_sdf(point, support["center"], support["axis"], support["slant"], support["half_angle"])
    except (OverflowError, ValueError):
        return float("nan")


def _flat(matrix):
    return np.asarray(matrix).reshape(-1).tolist()


def _chart(position, cfg):
    radius = math.hypot(position[0], position[1])
    if radius < cfg["core"]:
        return "origin_core", 0., 0.
    with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
        rho = float(np.log(np.divide(radius, cfg["r0"])))
    return "defined", rho, math.atan2(position[1], position[0])


def initial_state(trajectory):
    initial = trajectory.spec["initial"]
    return {"p": np.array(initial["p"], dtype=float), "v": np.array(initial["v"], dtype=float),
            "q": initial["q"], "phi": wrap(initial["phi"]), "time": initial["time"], "previous_chart": None,
            "failed": False}


def transition(trajectory, state, sample, step):
    """One full coupled step. State is mutated only after all old-state RHS reads."""
    cfg = trajectory.spec
    p, v, q, phi = state["p"], state["v"], state["q"], state["phi"]
    dt = sample["time"] - state["time"]
    row = {"trajectory_id": trajectory.id, "epoch_id": sample["epoch_id"], "step": step,
           "time_before": state["time"], "time_after": sample["time"], "dt": dt,
           "observation_valid": int(sample["valid"]), "target": list(sample["target"]),
           "observed_ecef": list(sample["observed_ecef"]), "clock_bias_m": sample["clock_bias_m"],
           "p_before": p.tolist(), "v_before": v.tolist(), "q_before": q, "phi_before": phi,
           "chart_status": "origin_core", "rho": 0., "theta": 0., "otan_status": "origin_core", "otan": 0.,
           "blend_status": "undefined", "bearing": 0., "blend": 0.,
           **{name: 0 for name in ("alignment", "limit", "fringe", "support", "drive", "x", "asa", "na", "hits", "output", "j", "k")},
           "q_after": q, "stiffness": [0.] * 9, "eigenmatrix": [0.] * 9,
           "eigenvalues": [0.] * 3, "eigenvectors": [0.] * 9, "eigen_residual": 0.,
           "force": [0.] * 3, "mechanical_matrix": [0.] * 9, "mechanical_rhs": [0.] * 3,
           "p_after": p.tolist(), "v_after": v.tolist(), "phi_after": phi,
           "status": "previous_failure" if state["failed"] else "advanced"}
    if state["failed"]:
        row["chart_status"] = "not_evaluated"
        row["otan_status"] = "not_evaluated"
        return row
    chart = _chart(p, cfg["chart"])
    row["chart_status"], row["rho"], row["theta"] = chart
    previous = state["previous_chart"]
    if previous is None:
        row["otan_status"] = "first_observation"
    elif chart[0] == "defined":
        if previous[0] != "defined":
            row["otan_status"] = "origin_core"
        else:
            delta_theta, delta_rho = wrap(chart[2] - previous[2]), chart[1] - previous[1]
            if math.isfinite(delta_theta) and math.isfinite(delta_rho):
                otan = otan2_source(delta_theta, delta_rho, cfg["chart"]["axis"])
                row["otan_status"] = otan["status"]
                row["otan"] = otan["value"] if otan["value"] is not None else 0.
            else:
                with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
                    ratio = float(np.divide(delta_theta, delta_rho))
                if not math.isfinite(ratio) or (ratio == 0 and delta_theta != 0):
                    row["otan_status"] = "numerical_range"
                else:
                    row["otan_status"], row["otan"] = "defined", math.atan(ratio) - cfg["chart"]["axis"]
    with np.errstate(over="ignore", invalid="ignore"):
        error = np.asarray(sample["target"], dtype=float) - p
    geometry_finite = all(math.isfinite(x) for x in (math.hypot(p[0], p[1]), row["rho"], row["otan"])) and np.isfinite(error).all()
    bearing_defined = sample["valid"] and math.hypot(error[0], error[1]) >= cfg["chart"]["core"]
    if bearing_defined:
        row["bearing"] = math.atan2(error[1], error[0])
        if row["otan_status"] == "defined":
            row["blend_status"] = "defined"
            row["blend"] = wrap(circle_plus(row["bearing"], row["otan"], cfg["chart"]["blend_weight"]) + phi)
    geometry_finite = geometry_finite and math.isfinite(row["blend"])
    for channel in sorted(cfg["channels"], key=lambda item: item["index"]):
        bit = 1 << channel["index"]
        if row["blend_status"] == "defined" and abs(wrap(row["blend"] - channel["angle_center"])) <= channel["angle_tolerance"]:
            row["alignment"] |= bit
        with np.errstate(over="ignore", invalid="ignore"):
            projection = float(np.dot(channel["direction"], error))
        if sample["valid"] and abs(projection) > channel["error_limit"]:
            row["limit"] |= bit
        distance = support_sdf(p, channel["support"])
        if abs(distance) <= channel["fringe_width"]:
            row["fringe"] |= bit
        if distance <= 0:
            row["support"] |= bit
        geometry_finite = geometry_finite and math.isfinite(distance) and math.isfinite(projection)
    values = {"q": q, "align": row["alignment"], "limit": row["limit"], "fringe": row["fringe"],
              "support": row["support"], "valid": WORD if sample["valid"] else 0}
    equations, masks = trajectory.equations, cfg["masks"]
    row["drive"] = values["d"] = equations["d"].evaluate(values)
    row["x"] = equations["x"].evaluate(values)
    row["asa"] = row["x"] & masks["asa"] & masks["present"]
    row["na"] = row["asa"] & masks["na"]
    row["hits"] = (row["na"] & masks["boundary"]).bit_count()
    row["output"] = values["y"] = 0 if row["hits"] else row["na"]
    row["j"] = equations["j"].evaluate(values)
    row["k"] = equations["k"].evaluate(values)
    row["q_after"] = after = ((row["j"] & ~q) | (~row["k"] & q)) & masks["present"]
    stiffness = np.asarray(cfg["stiffness_base"], dtype=float).copy()
    force = np.asarray(sample["force"], dtype=float).copy()
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        for channel in sorted(cfg["channels"], key=lambda item: item["index"]):
            value = (after >> channel["index"]) & 1
            direction = np.asarray(channel["direction"])
            k = channel["stiffness"]["on" if value else "off"]
            f = channel["force"]["on" if value else "off"]
            stiffness += k * np.outer(direction, direction)
            force += f * direction
        mass = np.asarray(cfg["mass"], dtype=float)
        invsqrt = 1 / np.sqrt(mass)
        eigenmatrix = invsqrt[:, None] * stiffness * invsqrt[None, :]
        valid = int(sample["valid"])
        mechanical = np.diag(mass + dt * np.asarray(cfg["damping"])) + (dt * dt * stiffness if valid else np.zeros((3, 3)))
        rhs = mass * v + dt * (force + (stiffness @ error if valid else np.zeros(3)))
        row.update(stiffness=_flat(stiffness), eigenmatrix=_flat(eigenmatrix), force=force.tolist(),
                   mechanical_matrix=_flat(mechanical), mechanical_rhs=rhs.tolist())
        try:
            if not np.isfinite(eigenmatrix).all():
                raise FloatingPointError("nonfinite physical eigenmatrix")
            eigenvalues, eigenvectors = np.linalg.eigh(eigenmatrix)
            row.update(eigenvalues=eigenvalues.tolist(), eigenvectors=_flat(eigenvectors),
                       eigen_residual=float(np.max(np.abs(eigenmatrix @ eigenvectors - eigenvectors * eigenvalues))))
            if not geometry_finite or not all(np.isfinite(a).all() for a in (stiffness, force, mechanical, rhs, error)):
                raise FloatingPointError("nonfinite physical operator")
            velocity = np.linalg.solve(mechanical, rhs)
            position = p + dt * velocity
            phase_unwrapped = phi + dt * cfg["hoop"]["rate"]
            if not np.isfinite(velocity).all() or not np.isfinite(position).all() or not math.isfinite(phase_unwrapped):
                raise FloatingPointError("nonfinite physical state")
            phase = wrap(phase_unwrapped)
        except (np.linalg.LinAlgError, FloatingPointError):
            row["status"] = "numeric_failure"
            state["failed"] = True
            state["q"] = after
            # Null identifies unavailable numeric diagnostics; state/status remain explicit.
            for key in SCALAR_FIELDS:
                if not math.isfinite(row[key]):
                    row[key] = None
            for key in VECTOR_FIELDS:
                row[key] = [float(x) if math.isfinite(x) else None for x in row[key]]
            return row
    row.update(p_after=position.tolist(), v_after=velocity.tolist(), phi_after=phase)
    state.update(p=position, v=velocity, q=after, phi=phase, time=sample["time"], previous_chart=chart)
    return row


def trace(trajectory):
    state = initial_state(trajectory)
    for step, sample in enumerate(trajectory.spec["samples"]):
        yield transition(trajectory, state, sample, step)


def _finite_array(value, count, label):
    if not isinstance(value, list) or len(value) != count or any(type(x) not in (int, float) or not math.isfinite(x) for x in value):
        raise ValueError(f"Native {label} requires {count} finite numbers")
    return np.asarray(value, dtype=float)


def compare_trace_row(expected, actual, relative=2e-9, absolute=2e-9):
    """Compare every trace field, with basis-invariant checks for eigenvectors."""
    label = f"Trajectory {expected['trajectory_id']} step {expected['step']}"
    if not isinstance(actual, dict) or set(actual) != TRACE_FIELDS:
        raise ValueError(f"{label}: native trace fields differ from CGK-R1")
    comparisons = 0
    for field in EXACT_FIELDS:
        if type(actual[field]) is not type(expected[field]) or actual[field] != expected[field]:
            raise ValueError(f"{label}: {field} expected {expected[field]!r}, found {actual[field]!r}")
        comparisons += 1
    for field in SCALAR_FIELDS:
        value = actual[field]
        if expected[field] is None and expected["status"] == "numeric_failure":
            if value is not None:
                raise ValueError(f"{label}: {field} nonfinite diagnostic must be null")
            comparisons += 1
            continue
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(f"{label}: {field} must be finite")
        if field != "eigen_residual" and not math.isclose(value, expected[field], rel_tol=relative, abs_tol=absolute):
            raise ValueError(f"{label}: {field} expected {expected[field]}, found {value}")
        comparisons += 1
    for field, count in VECTOR_FIELDS.items():
        if any(x is None for x in expected[field]):
            if expected["status"] != "numeric_failure" or not isinstance(actual[field], list) or len(actual[field]) != count:
                raise ValueError(f"{label}: malformed failed diagnostic {field}")
            for reference, observed in zip(expected[field], actual[field]):
                if reference is None:
                    if observed is not None:
                        raise ValueError(f"{label}: {field} nonfinite diagnostic must be null")
                elif type(observed) not in (int, float) or not math.isfinite(observed) or not math.isclose(reference, observed, rel_tol=relative, abs_tol=absolute):
                    raise ValueError(f"{label}: failed diagnostic {field} mismatch")
            comparisons += count
            continue
        values = _finite_array(actual[field], count, field)
        if field != "eigenvectors" and not np.allclose(values, expected[field], rtol=relative, atol=absolute):
            raise ValueError(f"{label}: {field} mismatch; max absolute error {float(np.max(np.abs(values - expected[field])))}")
        comparisons += count
    d = np.asarray(actual["eigenmatrix"], dtype=float).reshape(3, 3)
    vectors = np.asarray(actual["eigenvectors"]).reshape(3, 3)
    values = np.asarray(actual["eigenvalues"])
    if expected["status"] != "previous_failure" and np.any(vectors) and np.isfinite(d).all():
        scale = max(1., float(np.max(np.abs(d))))
        residual = float(np.max(np.abs(d @ vectors - vectors * values)))
        if residual > 2e-9 * scale or not np.allclose(vectors.T @ vectors, np.eye(3), atol=2e-9, rtol=2e-9):
            raise ValueError(f"{label}: invalid native eigensystem residual/orthogonality")
        if not math.isclose(actual["eigen_residual"], residual, rel_tol=2e-6, abs_tol=2e-12 * scale):
            raise ValueError(f"{label}: dishonest eigen_residual field")
        reference_vectors = np.asarray(expected["eigenvectors"]).reshape(3, 3)
        for i in range(3):
            if all(i == j or abs(values[i] - values[j]) > 1e-7 * scale for j in range(3)):
                if not np.allclose(np.outer(vectors[:, i], vectors[:, i]),
                                   np.outer(reference_vectors[:, i], reference_vectors[:, i]), atol=2e-8, rtol=2e-8):
                    raise ValueError(f"{label}: eigenmode projector {i} mismatch")
    elif actual["eigenvectors"] != expected["eigenvectors"] or actual["eigen_residual"] != expected["eigen_residual"]:
        raise ValueError(f"{label}: failed-state eigen sentinel mismatch")
    return comparisons


def replay(trajectories, trace_path=None, actual_path=None):
    output = actual = None
    try:
        if trace_path is not None:
            output = Path(trace_path).open("x", encoding="utf-8")
        if actual_path is not None:
            actual = Path(actual_path).open(encoding="utf-8")
        transitions = comparisons = 0
        outcomes = []
        for trajectory in trajectories:
            counts = {}
            last = None
            for expected in trace(trajectory):
                if output is not None:
                    output.write(json.dumps(expected, separators=(",", ":"), allow_nan=False) + "\n")
                if actual is not None:
                    line = actual.readline()
                    if not line:
                        raise ValueError("Native trace ended early")
                    comparisons += compare_trace_row(expected, json.loads(line))
                transitions += 1
                counts[expected["status"]] = counts.get(expected["status"], 0) + 1
                last = expected
            outcomes.append({"trajectory_id": trajectory.id, "steps": len(trajectory.spec["samples"]),
                             "statuses": counts, "final_q": last["q_after"], "final_p": last["p_after"],
                             "final_v": last["v_after"], "specification_sha256": trajectory.specification_hash,
                             "equations": {name: value.source for name, value in trajectory.equations.items()}})
        if actual is not None and actual.readline():
            raise ValueError("Native trace contains unexpected trailing records")
        return {"version": VERSION, "profile": PROFILE, "status": "passed", "transitions": transitions,
                "field_comparisons": comparisons, "native_trace_verified": actual is not None,
                "trajectories": outcomes}
    finally:
        if output is not None:
            output.close()
        if actual is not None:
            actual.close()
