"""SRK-R1 expression input, truth-table compiler and independent word-AST replay.

JSON: {"version":"3.6.1.6", "profile":"SRK-R1", "equations":{"x":...,"j":...,"k":...},
       "trajectories":[{"id":0,"q0":0,"drive":15,"present":15,"asa_mask":15,
                        "na_mask":15,"boundary_mask":0,"steps":4,"equations":{...}}]}.
Root equations are optional defaults; trajectory equations override individual defaults.
Every resulting trajectory requires x, j and k. Expressions use q,d for x; q,y,d for
j/k; &, |, ^, ~, parentheses and integer literals 0/1 (word zero/all 32 bits set).
Masks and drive remain constant within each trajectory; every RHS reads old q.
No Python eval, calls, attribute access or arbitrary code execution is used.
"""
from __future__ import annotations

import ast
import csv
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

VERSION = "3.6.1.6"
PROFILE = "SRK-R1"
WORD = (1 << 32) - 1
INPUT_FIELDS = ("trajectory_id", "q0", "drive", "present", "asa_mask", "na_mask",
                "boundary_mask", "x_lut", "j_lut", "k_lut", "steps")
TRACE_FIELDS = ("trajectory_id", "step", "before", "drive", "x", "asa", "na", "hits",
                "output", "j", "k", "after")
PARAMETERS = ("q0", "drive", "present", "asa_mask", "na_mask", "boundary_mask")
VARIABLES = {"x": ("q", "d"), "j": ("q", "y", "d"), "k": ("q", "y", "d")}


def canonical_digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@dataclass(frozen=True)
class Expression:
    source: str
    variables: tuple[str, ...]
    tree: ast.AST

    @property
    def canonical(self):
        return ast.dump(self.tree, annotate_fields=True, include_attributes=False)

    def evaluate(self, values):
        """Evaluate the word expression directly, without using compiled truth tables."""
        def visit(node):
            if isinstance(node, ast.Name):
                return values[node.id] & WORD
            if isinstance(node, ast.Constant):
                return WORD if node.value == 1 else 0
            if isinstance(node, ast.UnaryOp):
                return (~visit(node.operand)) & WORD
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.BitAnd):
                return left & right
            if isinstance(node.op, ast.BitOr):
                return left | right
            return left ^ right
        return visit(self.tree)


def parse_expression(source, variables):
    if not isinstance(source, str) or not source.strip():
        raise ValueError("Equation must be a nonempty expression string")
    try:
        tree = ast.parse(source.strip(), mode="eval").body
    except (SyntaxError, RecursionError) as exc:
        raise ValueError(f"Invalid equation syntax: {source!r}") from exc
    permitted = (ast.Name, ast.Load, ast.Constant, ast.BinOp, ast.UnaryOp,
                 ast.BitAnd, ast.BitOr, ast.BitXor, ast.Invert)
    for node in ast.walk(tree):
        if not isinstance(node, permitted):
            raise ValueError(f"Equation uses unsupported syntax {type(node).__name__}")
        if isinstance(node, ast.Name) and node.id not in variables:
            raise ValueError(f"Equation variable {node.id!r} is not one of {tuple(variables)}")
        if isinstance(node, ast.Constant) and (type(node.value) is not int or node.value not in (0, 1)):
            raise ValueError("Equation constants must be integer 0 or 1 (word zero/ones)")
        if isinstance(node, ast.UnaryOp) and not isinstance(node.op, ast.Invert):
            raise ValueError("Only bitwise ~ is a unary equation operator")
        if isinstance(node, ast.BinOp) and not isinstance(node.op, (ast.BitAnd, ast.BitOr, ast.BitXor)):
            raise ValueError("Only &, | and ^ are binary equation operators")
    return Expression(source.strip(), tuple(variables), tree)


def compile_lut(expression):
    """Compile scalar Boolean evaluations; native execution uses only the resulting LUT."""
    def scalar(node, values):
        if isinstance(node, ast.Name):
            return values[node.id]
        if isinstance(node, ast.Constant):
            return bool(node.value)
        if isinstance(node, ast.UnaryOp):
            return not scalar(node.operand, values)
        left, right = scalar(node.left, values), scalar(node.right, values)
        if isinstance(node.op, ast.BitAnd):
            return left and right
        if isinstance(node.op, ast.BitOr):
            return left or right
        return left != right
    count = len(expression.variables)
    table = 0
    for index in range(1 << count):
        values = {name: bool((index >> (count - 1 - position)) & 1)
                  for position, name in enumerate(expression.variables)}
        if scalar(expression.tree, values):
            table |= 1 << index
    return table


def _unsigned(value, name, maximum=WORD):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f"{name} must be an integer in [0,{maximum}]")
    return value


def _equations(value, location):
    if not isinstance(value, dict) or set(value) - set(VARIABLES):
        raise ValueError(f"{location} must map only x, j and k to expression strings")
    return value


@dataclass
class Trajectory:
    id: int
    parameters: dict
    steps: int
    equations: dict[str, Expression]

    @property
    def equation_hash(self):
        return canonical_digest({"profile": PROFILE, "equations": {
            name: expression.canonical for name, expression in self.equations.items()}})

    @property
    def specification_hash(self):
        return canonical_digest({"id": self.id, **self.parameters, "steps": self.steps,
                                 "equation_sha256": self.equation_hash})

    def compiled(self):
        return {"trajectory_id": self.id, **self.parameters,
                **{name + "_lut": compile_lut(self.equations[name]) for name in VARIABLES},
                "steps": self.steps}


def parse_document(document):
    if not isinstance(document, dict):
        raise ValueError("Equation input must be a JSON object")
    if document.get("version") != VERSION or document.get("profile") != PROFILE:
        raise ValueError(f"Equation input requires version={VERSION!r}, profile={PROFILE!r}")
    if set(document) - {"version", "profile", "equations", "trajectories", "description"}:
        raise ValueError("Unknown root equation-input field")
    defaults = _equations(document.get("equations", {}), "Root equations")
    records = document.get("trajectories")
    if not isinstance(records, list) or not records:
        raise ValueError("trajectories must be a nonempty list")
    trajectories, seen = [], set()
    required = {"id", "steps", *PARAMETERS}
    for record in records:
        if not isinstance(record, dict) or not required <= set(record):
            raise ValueError("Trajectory requires id, steps, q0, drive, present and all three masks")
        if set(record) - required - {"equations", "description"}:
            raise ValueError("Unknown trajectory field")
        identifier = _unsigned(record["id"], "id", (1 << 64) - 1)
        if identifier in seen:
            raise ValueError(f"Duplicate trajectory id: {identifier}")
        seen.add(identifier)
        parameters = {key: _unsigned(record[key], key) for key in PARAMETERS}
        if parameters["q0"] & ~parameters["present"]:
            raise ValueError("q0 must be a subset of present")
        steps = _unsigned(record["steps"], "steps", (1 << 64) - 1)
        if steps == 0:
            raise ValueError("steps must be nonzero")
        sources = {**defaults, **_equations(record.get("equations", {}), "Trajectory equations")}
        if set(sources) != set(VARIABLES):
            raise ValueError("Every trajectory requires x, j and k equations after applying defaults")
        equations = {key: parse_expression(sources[key], variables) for key, variables in VARIABLES.items()}
        trajectories.append(Trajectory(identifier, parameters, steps, equations))
    return trajectories


def load_document(path):
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result
    with Path(path).open(encoding="utf-8-sig") as stream:
        return parse_document(json.load(stream, object_pairs_hook=unique_object))


def transition(trajectory, q, step):
    """The independent full-word equation interpreter; no lookup tables are consulted."""
    p, equations = trajectory.parameters, trajectory.equations
    d = p["drive"]
    x = equations["x"].evaluate({"q": q, "d": d})
    a = x & p["asa_mask"] & p["present"]
    n = a & p["na_mask"]
    hits = (n & p["boundary_mask"]).bit_count()
    y = 0 if hits else n
    values = {"q": q, "y": y, "d": d}
    j = equations["j"].evaluate(values)
    k = equations["k"].evaluate(values)
    after = ((j & ~q) | (~k & q)) & p["present"]
    return {"trajectory_id": trajectory.id, "step": step, "before": q, "drive": d,
            "x": x, "asa": a, "na": n, "hits": hits, "output": y,
            "j": j, "k": k, "after": after}


def write_compiled(trajectories, path):
    with Path(path).open("x", encoding="ascii", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=INPUT_FIELDS, lineterminator="\n")
        writer.writeheader()
        for trajectory in trajectories:
            writer.writerow(trajectory.compiled())


def replay(trajectories, trace_path=None, actual_path=None):
    """Stream expected transitions, optionally write them and verify a native trace."""
    output = actual = None
    try:
        writer = reader = None
        if trace_path is not None:
            output = Path(trace_path).open("x", encoding="ascii", newline="")
            writer = csv.DictWriter(output, fieldnames=TRACE_FIELDS, lineterminator="\n")
            writer.writeheader()
        if actual_path is not None:
            actual = Path(actual_path).open(encoding="ascii", newline="")
            reader = csv.DictReader(actual)
            if tuple(reader.fieldnames or ()) != TRACE_FIELDS:
                raise ValueError("Native trace header differs from SRK-R1 schema")
        outcomes, transitions, comparisons = [], 0, 0
        for trajectory in trajectories:
            q = trajectory.parameters["q0"]
            seen = {q: 0}
            cycle = None
            for step in range(trajectory.steps):
                expected = transition(trajectory, q, step)
                if writer is not None:
                    writer.writerow(expected)
                if reader is not None:
                    observed = next(reader, None)
                    if observed is None:
                        raise ValueError(f"Native trace ended before trajectory {trajectory.id}, step {step}")
                    if None in observed or any(value is None for value in observed.values()):
                        raise ValueError("Malformed native trace row")
                    for field in TRACE_FIELDS:
                        text = observed[field]
                        if not text or not text.isascii() or not text.isdecimal():
                            raise ValueError(f"Native trace {field} must be an unsigned decimal integer")
                        value = int(text)
                        if value != expected[field]:
                            raise ValueError(f"Trajectory {trajectory.id} step {step}: {field} expected "
                                             f"{expected[field]}, found {value}")
                        comparisons += 1
                q = expected["after"]
                transitions += 1
                if cycle is None:
                    if q in seen:
                        period = step + 1 - seen[q]
                        cycle = {"kind": "fixed_point" if period == 1 else "cycle",
                                 "entry_step": seen[q], "period": period,
                                 "first_repeat_step": step + 1, "repeated_state": q}
                    else:
                        seen[q] = step + 1
            outcomes.append({"trajectory_id": trajectory.id, "steps": trajectory.steps,
                             "initial_state": trajectory.parameters["q0"], "final_state": q,
                             "orbit": cycle or {"kind": "no_repeat_observed"},
                             "finite_state_count": 1 << trajectory.parameters["present"].bit_count(),
                             "equation_sha256": trajectory.equation_hash,
                             "specification_sha256": trajectory.specification_hash,
                             "equations": {key: expression.source for key, expression in trajectory.equations.items()},
                             "lookup_tables": {key: compile_lut(value) for key, value in trajectory.equations.items()}})
        if reader is not None and next(reader, None) is not None:
            raise ValueError("Native trace contains unexpected trailing transitions")
        return {"version": VERSION, "profile": PROFILE, "status": "passed",
                "transitions": transitions, "field_comparisons": comparisons,
                "native_trace_verified": reader is not None, "trajectories": outcomes}
    finally:
        if output is not None:
            output.close()
        if actual is not None:
            actual.close()
