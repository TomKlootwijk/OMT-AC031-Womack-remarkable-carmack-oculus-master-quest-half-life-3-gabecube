from __future__ import annotations

"""Independent exact oracle for the finite Learner 0.2 registry.

This module deliberately does not invoke :mod:`tomagi.formal` or reuse the
formal expression tree.  It is a separately implemented falsification oracle
using :class:`fractions.Fraction` and ordinary finite enumeration.
"""

from dataclasses import dataclass
from fractions import Fraction
import copy
from typing import Any, Iterable, Mapping

from tomagi.canonical import attach_hash, content_hash, verify_hash


class OracleError(ValueError):
    pass


def frac(value: Any) -> Fraction:
    if isinstance(value, bool):
        raise OracleError("boolean is not an exact rational")
    if isinstance(value, int):
        return Fraction(value, 1)
    if isinstance(value, Mapping) and set(value) == {"num", "den"}:
        n, d = value["num"], value["den"]
        if isinstance(n, bool) or isinstance(d, bool) or not isinstance(n, int) or not isinstance(d, int):
            raise OracleError("rational words must be integers")
        if d <= 0:
            raise OracleError("rational denominator must be positive")
        f = Fraction(n, d)
        if f.numerator != n or f.denominator != d:
            raise OracleError("rational must be reduced")
        return f
    raise OracleError(f"not an exact rational: {value!r}")


def q(value: Fraction | int) -> dict[str, int]:
    f = value if isinstance(value, Fraction) else Fraction(value, 1)
    return {"num": f.numerator, "den": f.denominator}


def _eval_tree(node: Mapping[str, Any], x: Fraction, depth: int = 0) -> Fraction:
    if depth > 2:
        raise OracleError("expression tree exceeds depth 2")
    op = node.get("op")
    if op == "x":
        return x
    if op == "const":
        return frac(node["value"])
    if op in {"neg", "abs", "square"}:
        value = _eval_tree(node["arg"], x, depth + 1)
        if op == "neg":
            return -value
        if op == "abs":
            return abs(value)
        return value * value
    if op in {"add", "sub", "mul"}:
        left = _eval_tree(node["left"], x, depth + 1)
        right = _eval_tree(node["right"], x, depth + 1)
        if op == "add":
            return left + right
        if op == "sub":
            return left - right
        return left * right
    raise OracleError(f"unknown expression-tree op {op!r}")


def predict(candidate: Mapping[str, Any], observation: Mapping[str, Any]) -> tuple[bool, Any]:
    family = candidate.get("family_id")
    x_value = observation.get("input")
    if family == "family:polynomial:0.2":
        x = frac(x_value)
        coeffs = candidate["coefficients"]
        return True, q(frac(coeffs[0]) + frac(coeffs[1]) * x + frac(coeffs[2]) * x * x)
    if family == "family:piecewise-affine:0.2":
        x = frac(x_value)
        side = candidate["left"] if x <= frac(candidate["breakpoint"]) else candidate["right"]
        return True, q(frac(side["slope"]) * x + frac(side["intercept"]))
    if family == "family:transition-table:0.2":
        matches = [entry for entry in candidate["entries"] if entry["input"] == x_value]
        if len(matches) != 1:
            return False, None
        return True, copy.deepcopy(matches[0]["output"])
    if family == "family:expression-tree:0.2":
        return True, q(_eval_tree(candidate["tree"], frac(x_value)))
    raise OracleError(f"unknown candidate family {family!r}")


def _matches(candidate: Mapping[str, Any], observation: Mapping[str, Any]) -> bool:
    defined, value = predict(candidate, observation)
    if not defined:
        return False
    target = observation["target"]
    numeric = isinstance(target, int) or isinstance(target, Mapping)
    if numeric:
        try:
            return frac(value) == frac(target)
        except OracleError:
            return False
    return value == target


def _partition(dataset: Mapping[str, Any], name: str) -> list[Mapping[str, Any]]:
    ids = dataset["partitions"][name]
    by_id = {observation["id"]: observation for observation in dataset["observations"]}
    return [by_id[item] for item in ids]


def _contradictions(observations: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = list(observations)
    out: list[dict[str, Any]] = []
    for left_index, left in enumerate(rows):
        for right in rows[left_index + 1:]:
            if left["input"] == right["input"] and left["target"] != right["target"]:
                out.append(attach_hash({
                    "schema": "TOM-LEARNER-0.2-CONTRADICTION-1.0",
                    "left_observation": left["content_hash"],
                    "right_observation": right["content_hash"],
                    "input": copy.deepcopy(left["input"]),
                    "left_target": copy.deepcopy(left["target"]),
                    "right_target": copy.deepcopy(right["target"]),
                }))
    return out


def _family_candidates(registry: Mapping[str, Any], dataset: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    eligible = set(dataset["eligible_families"])
    out: list[Mapping[str, Any]] = []
    for family in registry["families"]:
        if family["id"] in eligible:
            if len(family["candidates"]) > family["search_budget"]["max_candidates"]:
                raise OracleError("family candidate registry exceeds declared search budget")
            out.extend(family["candidates"])
    return out


def _fit_hash(dataset: Mapping[str, Any], registry: Mapping[str, Any]) -> str:
    train = _partition(dataset, "train")
    return content_hash({
        "schema": "TOM-LEARNER-0.2-TRAIN-FIT-INPUT-1.0",
        "dataset_id": dataset["id"],
        "family_registry_hash": registry["content_hash"],
        "eligible_families": dataset["eligible_families"],
        "train_observations": [item["content_hash"] for item in train],
    })


def _regression_impact(selected: Mapping[str, Any] | None, dataset: Mapping[str, Any],
                       prior: Mapping[str, Any]) -> dict[str, Any]:
    supersedes = dataset.get("supersedes")
    found = supersedes is None
    results: list[dict[str, Any]] = []
    for definition in prior["definitions"]:
        replacement = definition["model"]
        replaced = supersedes == definition["content_hash"]
        if replaced:
            found = True
            if selected is not None:
                replacement = selected
        case_results = []
        for case in definition["regression_cases"]:
            observation = {"input": case["input"], "target": case["expected"]}
            passed = _matches(replacement, observation)
            case_results.append({"case_id": case["id"], "passed": passed})
        results.append({
            "definition_hash": definition["content_hash"],
            "replaced": replaced,
            "passed": all(item["passed"] for item in case_results),
            "cases": case_results,
        })
    all_pass = found and all(item["passed"] for item in results)
    return attach_hash({
        "schema": "TOM-LEARNER-0.2-REGRESSION-IMPACT-1.0",
        "dataset_id": dataset["id"],
        "supersedes": supersedes,
        "superseded_definition_found": found,
        "tested_definitions": len(results),
        "all_pass": all_pass,
        "results": results,
    })


def evaluate_dataset(dataset: Mapping[str, Any], registry: Mapping[str, Any],
                     prior: Mapping[str, Any]) -> dict[str, Any]:
    if not verify_hash(dict(dataset)) or not verify_hash(dict(registry)) or not verify_hash(dict(prior)):
        raise OracleError("oracle input content hash mismatch")
    train = _partition(dataset, "train")
    validation = _partition(dataset, "validation")
    holdout = _partition(dataset, "holdout")
    candidates = _family_candidates(registry, dataset)
    survivors = [candidate for candidate in candidates if all(_matches(candidate, row) for row in train)]
    contradictions = _contradictions(dataset["observations"])
    selected = survivors[0] if len(survivors) == 1 else None
    validation_failures = [] if selected is None else [row for row in validation if not _matches(selected, row)]
    holdout_failures = [] if selected is None else [row for row in holdout if not _matches(selected, row)]
    regression = _regression_impact(selected, dataset, prior)
    accepted = (
        len(survivors) == 1
        and not contradictions
        and not validation_failures
        and not holdout_failures
        and regression["all_pass"]
    )
    if len(survivors) > 1:
        reason = "ambiguous-train-survivors"
    elif len(survivors) == 0:
        reason = "no-exact-train-candidate"
    elif contradictions:
        reason = "contradiction"
    elif validation_failures:
        reason = "validation-counterexample"
    elif holdout_failures:
        reason = "holdout-counterexample"
    elif not regression["all_pass"]:
        reason = "regression-impact"
    else:
        reason = "accepted"
    return {
        "dataset_id": dataset["id"],
        "accepted": accepted,
        "reason": reason,
        "candidate_count": len(candidates),
        "survivor_hashes": [item["content_hash"] for item in survivors],
        "selected_candidate_hash": None if selected is None else selected["content_hash"],
        "fit_input_hash": _fit_hash(dataset, registry),
        "validation_failures": [item["id"] for item in validation_failures],
        "holdout_failures": [item["id"] for item in holdout_failures],
        "contradiction_count": len(contradictions),
        "regression_all_pass": regression["all_pass"],
        "supersedes": dataset.get("supersedes"),
    }


def evaluate_all(datasets: list[Mapping[str, Any]], registry: Mapping[str, Any],
                 prior: Mapping[str, Any]) -> dict[str, Any]:
    rows = [evaluate_dataset(dataset, registry, prior) for dataset in datasets]
    return {
        "dataset_count": len(rows),
        "accepted_count": sum(row["accepted"] for row in rows),
        "rejected_count": sum(not row["accepted"] for row in rows),
        "ambiguous_count": sum(row["reason"] == "ambiguous-train-survivors" for row in rows),
        "rows": rows,
    }
