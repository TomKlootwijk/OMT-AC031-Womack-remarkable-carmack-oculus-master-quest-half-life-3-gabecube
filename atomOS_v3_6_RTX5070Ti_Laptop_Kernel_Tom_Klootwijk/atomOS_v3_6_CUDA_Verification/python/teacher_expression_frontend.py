"""Versioned, bounded Boolean-expression text frontend for retained teachers.

Python's parser supplies syntax trees only. No Python expression is executed.
All operands are one bit; ~ and not both mean one-bit complement. The original
integer specifications and frozen oracle bytes remain unchanged.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

import knowledge_admission as admission
import program_bank as codec
import teacher_knowledge as original


ROOT = Path(__file__).resolve().parents[1]
VERSION = "atomos-safe-bit-expression-frontend-v2"
CURRICULUM_SCHEMA = "atomos-frozen-expression-curriculum-v2"
RESPONSE_SCHEMA = "atomos-teacher-procedure-v2"
MAX_RESPONSE_BYTES = original.MAX_RESPONSE_BYTES
MAX_EXPR_BYTES = 2048
MAX_AST_NODES = 512
MAX_AST_DEPTH = 32
MAX_RESPONSES = original.MAX_RESPONSES
MAX_REPAIR_ROUNDS = 2
DEFAULT_ORACLE_CURRICULUM = ROOT / "examples/teacher_knowledge/curriculum"


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _json(raw):
    return json.loads(raw, object_pairs_hook=original._unique_object,
                      parse_constant=original._reject_json_constant)


def _profile(identity):
    for profile in original.profiles():
        if profile["profile_id"] == identity:
            return profile
    raise ValueError("unknown original profile")


def prompt(profile_id: str) -> str:
    p = _profile(profile_id)
    shape = {"schema": RESPONSE_SCHEMA, "profile_id": profile_id,
             "procedures": [{"name": profile_id, "input_bits": p["input_bits"], "output_bits": p["output_bits"],
                             "outputs": ["BOOLEAN_EXPRESSION_STRING"] * p["output_bits"]}]}
    return (
        "Express this known digital algorithm using your existing algorithm knowledge. "
        "Return only the requested JSON object, without reasoning, prose, Markdown or a truth table.\n\n"
        + p["specification"] + "\n"
        + "Input bits (the only variable identifiers): " + ", ".join(p["input_labels"]) + ".\n"
        + "Output expression order: " + ", ".join(f"{i}={label}" for i, label in enumerate(p["output_labels"])) + ".\n"
        + "Each outputs entry is a STRING containing a Boolean expression. Allowed syntax: input identifiers, "
        "integer constants 0 and 1, parentheses, binary & (AND), | (OR), ^ (XOR), and unary ~ (NOT). "
        "The words not, and, or are also accepted with pure one-bit semantics. "
        "Every operand and result is exactly one bit; ~x and not x both mean 1-x. "
        "Use parentheses to make grouping explicit; Python expression precedence applies. "
        "Do not use arithmetic, comparisons, shifts, indexing, function calls, assignments, "
        "conditional expressions, named intermediate variables or references to other outputs. "
        "Do not use JSON true/false as constants. "
        f"Each string is limited to {MAX_EXPR_BYTES} UTF-8 bytes; the complete procedure is limited "
        f"to {MAX_AST_NODES} expression nodes and depth {MAX_AST_DEPTH}.\n"
        + "Required JSON shape (replace every placeholder with a complete expression string):\n"
        + json.dumps(shape, separators=(",", ":")) + "\n"
    )


def response_format(profile_id: str) -> dict:
    """JSON grammar for a constrained local API; it contains no solution."""
    p = _profile(profile_id)
    procedure = {"type": "object", "additionalProperties": False,
                 "required": ["name", "input_bits", "output_bits", "outputs"],
                 "properties": {"name": {"type": "string", "const": profile_id},
                                "input_bits": {"type": "integer", "const": p["input_bits"]},
                                "output_bits": {"type": "integer", "const": p["output_bits"]},
                                "outputs": {"type": "array", "minItems": p["output_bits"], "maxItems": p["output_bits"],
                                            "items": {"type": "string", "minLength": 1, "maxLength": MAX_EXPR_BYTES}}}}
    return {"type": "object", "additionalProperties": False,
            "required": ["schema", "profile_id", "procedures"],
            "properties": {"schema": {"type": "string", "const": RESPONSE_SCHEMA},
                           "profile_id": {"type": "string", "const": profile_id},
                           "procedures": {"type": "array", "minItems": 1, "maxItems": 1, "items": procedure}}}


def _balanced(op, expressions):
    work = expressions
    while len(work) > 1:
        work = [[op, work[i], work[i + 1]] if i + 1 < len(work) else work[i]
                for i in range(0, len(work), 2)]
    return work[0]


def _parse_expression(text, input_labels, budget):
    if not isinstance(text, str) or not 1 <= len(text.encode("utf-8")) <= MAX_EXPR_BYTES:
        raise ValueError("Boolean expression string byte bound")
    if re.fullmatch(r"[A-Za-z0-9_ \t\r\n&|^~()]+", text) is None:
        raise ValueError("unsupported character in Boolean expression")
    try:
        tree = ast.parse(text.strip(), mode="eval")
    except (SyntaxError, RecursionError) as error:
        raise ValueError("invalid bounded Boolean expression syntax") from error
    labels = {name: index for index, name in enumerate(input_labels)}
    binary = {ast.BitAnd: "and", ast.BitOr: "or", ast.BitXor: "xor"}
    boolean = {ast.And: "and", ast.Or: "or"}
    def convert(node, depth):
        budget["nodes"] += 1
        budget["depth"] = max(budget["depth"], depth)
        if budget["nodes"] > MAX_AST_NODES or depth > MAX_AST_DEPTH:
            raise ValueError("Boolean expression node/depth bound")
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id not in labels:
                raise ValueError("unknown input identifier: " + node.id)
            return ["input", labels[node.id]]
        if isinstance(node, ast.Constant):
            if type(node.value) is not int or node.value not in (0, 1):
                raise ValueError("Boolean constants must be integer 0 or 1")
            return ["constant", node.value]
        if isinstance(node, ast.UnaryOp) and type(node.op) in (ast.Invert, ast.Not):
            return ["not", convert(node.operand, depth + 1)]
        if isinstance(node, ast.BinOp) and type(node.op) in binary:
            return [binary[type(node.op)], convert(node.left, depth + 1), convert(node.right, depth + 1)]
        if isinstance(node, ast.BoolOp) and type(node.op) in boolean:
            if not 2 <= len(node.values) <= MAX_AST_NODES:
                raise ValueError("Boolean operator operand count bound")
            values = [convert(value, depth + 1) for value in node.values]
            # Pure bit operations are associative and side-effect free. Balance
            # multi-operand syntax before lowering to the binary NOR grammar.
            return _balanced(boolean[type(node.op)], values)
        raise ValueError("unsupported Boolean expression syntax node: " + type(node).__name__)
    return convert(tree.body, 1)


def parse_response(raw: str | bytes, profile_id: str) -> dict:
    raw = raw.encode("utf-8") if isinstance(raw, str) else raw
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_RESPONSE_BYTES:
        raise ValueError("teacher response byte bound")
    text = raw.decode("utf-8").strip()
    wrapping = "plain_json"
    fence = re.fullmatch(r"```(?:json)?\r?\n(.*?)\r?\n```", text, flags=re.DOTALL)
    if fence:
        text, wrapping = fence.group(1), "single_json_fence"
    original._bounded_json_depth(text)
    value = json.loads(text, object_pairs_hook=original._unique_object, parse_constant=original._reject_json_constant)
    if (not isinstance(value, dict) or set(value) != {"schema", "profile_id", "procedures"} or
            value.get("schema") != RESPONSE_SCHEMA or value.get("profile_id") != profile_id):
        raise ValueError("V2 response schema/profile mismatch")
    p = _profile(profile_id)
    if not isinstance(value["procedures"], list) or len(value["procedures"]) != 1:
        raise ValueError("exactly one V2 procedure is required")
    procedure = value["procedures"][0]
    if (not isinstance(procedure, dict) or set(procedure) != {"name", "input_bits", "output_bits", "outputs"} or
            procedure.get("name") != profile_id):
        raise ValueError("invalid V2 procedure fields")
    for field in ("input_bits", "output_bits"):
        original._integer(procedure.get(field), field, p[field], p[field])
    outputs = procedure["outputs"]
    if not isinstance(outputs, list) or len(outputs) != p["output_bits"]:
        raise ValueError("V2 output list differs from original interface")
    budget = {"nodes": 0, "depth": 0}
    canonical = [_parse_expression(expression, p["input_labels"], budget) for expression in outputs]
    circuit = codec.compile_nor(canonical, p["input_bits"])
    if p["input_bits"] + 1 + len(circuit["gates"]) > admission.MAX_WIRES:
        raise ValueError("V2 compiled program exceeds native wire bound")
    return {"procedure": procedure, "canonical_ast": canonical, "circuit": circuit,
            "expression_nodes": budget["nodes"], "expression_depth": budget["depth"],
            "wrapping": wrapping, "response_sha256": _sha(raw),
            "semantics": "pure one-bit Boolean operations; ~ and not both map to one-bit complement; no Python evaluation"}


def freeze_curriculum(out, oracle_curriculum=None, profile_ids=None):
    out = Path(out)
    source = Path(oracle_curriculum) if oracle_curriculum is not None else DEFAULT_ORACLE_CURRICULUM
    if out.exists():
        raise ValueError("refusing to overwrite V2 frozen curriculum")
    inherited = original.load_curriculum(source)
    identities = list(profile_ids) if profile_ids is not None else list(inherited["profiles"])
    if (not 1 <= len(identities) <= len(inherited["profiles"]) or len(set(identities)) != len(identities) or
            any(identity not in inherited["profiles"] for identity in identities)):
        raise ValueError("V2 profile selection must be unique inherited profiles")
    source_raw = original._read(source / "curriculum.json", original.MAX_RUN_BYTES)
    if _sha(source_raw) != inherited["curriculum_sha256"]:
        raise ValueError("original curriculum changed during V2 freeze")
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".expression_curriculum_", dir=out.parent) as temporary:
        staged = Path(temporary) / "prepared"
        staged.mkdir()
        (staged / "source_curriculum.json").write_bytes(source_raw)
        records = []
        for identity in identities:
            p = _profile(identity)
            old = inherited["profiles"][identity]
            oracle_bytes = original._read(source / old["oracle_file"], original.MAX_RUN_BYTES)
            if _sha(oracle_bytes) != old["oracle_sha256"]:
                raise ValueError("original oracle changed during V2 freeze")
            prompt_bytes = prompt(identity).encode("utf-8")
            prompt_name, oracle_name = identity + ".prompt.txt", identity + ".oracle.json"
            (staged / prompt_name).write_bytes(prompt_bytes)
            (staged / oracle_name).write_bytes(oracle_bytes)
            records.append(dict(p, prompt_file=prompt_name, oracle_file=oracle_name,
                                prompt_sha256=_sha(prompt_bytes), oracle_sha256=_sha(oracle_bytes),
                                source_oracle_sha256=old["oracle_sha256"]))
        manifest = {"schema": CURRICULUM_SCHEMA, "adapter_version": VERSION,
                    "frontend_source_sha256": _sha(Path(__file__).read_bytes()),
                    "original_frontend_sha256": _sha(Path(original.__file__).read_bytes()),
                    "source_curriculum": str(source), "source_curriculum_sha256": _sha(source_raw),
                    "oracle_policy": "original V1 oracle bytes retained unchanged; only response representation and prompt changed",
                    "teacher_execution": "not_run_by_curriculum_freeze", "profiles": records}
        (staged / "curriculum.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        if out.exists():
            raise ValueError("V2 output appeared while freezing")
        os.rename(staged, out)
    return manifest


def load_curriculum(folder):
    folder = Path(folder)
    raw = original._read(folder / "curriculum.json", original.MAX_RUN_BYTES)
    manifest = _json(raw)
    if (not isinstance(manifest, dict) or manifest.get("schema") != CURRICULUM_SCHEMA or
            manifest.get("adapter_version") != VERSION):
        raise ValueError("unsupported V2 frozen curriculum")
    if (manifest.get("frontend_source_sha256") != _sha(Path(__file__).read_bytes()) or
            manifest.get("original_frontend_sha256") != _sha(Path(original.__file__).read_bytes())):
        raise ValueError("frozen V2 frontend source changed")
    source_raw = original._read(folder / "source_curriculum.json", original.MAX_RUN_BYTES)
    if _sha(source_raw) != manifest.get("source_curriculum_sha256"):
        raise ValueError("inherited curriculum hash mismatch")
    source_manifest = _json(source_raw)
    if source_manifest.get("schema") != original.CURRICULUM_SCHEMA:
        raise ValueError("V2 oracles must originate from the original frozen schema")
    old = {p["profile_id"]: p for p in source_manifest["profiles"]}
    records = manifest.get("profiles")
    if not isinstance(records, list) or not 1 <= len(records) <= len(original.profiles()):
        raise ValueError("V2 profile list bound")
    profiles = {}
    for record in records:
        p = _profile(record.get("profile_id"))
        identity = p["profile_id"]
        if identity in profiles or identity not in old or any(record.get(key) != value for key, value in p.items()):
            raise ValueError("V2 profile changed the original typed interface")
        if record.get("prompt_file") != identity + ".prompt.txt" or record.get("oracle_file") != identity + ".oracle.json":
            raise ValueError("noncanonical V2 artifact path")
        prompt_bytes = original._read(folder / record["prompt_file"], MAX_RESPONSE_BYTES)
        oracle_bytes = original._read(folder / record["oracle_file"], original.MAX_RUN_BYTES)
        oracle_hash = _sha(oracle_bytes)
        if (_sha(prompt_bytes) != record.get("prompt_sha256") or prompt_bytes.decode("utf-8") != prompt(identity) or
                oracle_hash != record.get("oracle_sha256") or oracle_hash != record.get("source_oracle_sha256") or
                oracle_hash != old[identity].get("oracle_sha256")):
            raise ValueError("V2 prompt/oracle hash or inherited-byte mismatch")
        oracle = _json(oracle_bytes)
        expected = [{"input": x, "output": original.scalar_oracle(identity, x)} for x in range(1 << p["input_bits"])]
        if (oracle.get("cases") != expected or oracle.get("id") != identity or
                oracle.get("kind") != "fixed-domain-oracle" or oracle.get("independent_of_candidate") is not True or
                any(oracle.get(field) != p[field] for field in ("input_bits", "output_bits"))):
            raise ValueError("V2 oracle differs from original integer specification")
        profiles[identity] = dict(record, prompt=prompt_bytes.decode("utf-8"), oracle=oracle)
    return {"manifest": manifest, "curriculum_sha256": _sha(raw), "profiles": profiles}


def repair_prompt(profile_id, previous_response, counterexample, round_index):
    """One verified counterexample, with at most two explicitly numbered rounds."""
    original._integer(round_index, "repair round", 1, MAX_REPAIR_ROUNDS)
    p = _profile(profile_id)
    if not isinstance(counterexample, dict) or set(counterexample) != {"input", "expected", "actual"}:
        raise ValueError("repair requires exactly one concrete counterexample")
    x = original._integer(counterexample["input"], "counterexample input", 0, (1 << p["input_bits"]) - 1)
    expected = original._integer(counterexample["expected"], "expected output", 0, (1 << p["output_bits"]) - 1)
    actual = original._integer(counterexample["actual"], "actual output", 0, (1 << p["output_bits"]) - 1)
    parsed = parse_response(previous_response, profile_id)
    if (expected != original.scalar_oracle(profile_id, x) or
            actual != codec.evaluate_circuit(parsed["circuit"], x) or actual == expected):
        raise ValueError("repair counterexample is not a real mismatch against the original oracle")
    previous = previous_response.decode("utf-8") if isinstance(previous_response, bytes) else previous_response
    feedback = {"input_assignment": {name: (x >> bit) & 1 for bit, name in enumerate(p["input_labels"])},
                "expected_output_bits": [(expected >> bit) & 1 for bit in range(p["output_bits"])],
                "actual_output_bits": [(actual >> bit) & 1 for bit in range(p["output_bits"])]}
    text = (prompt(profile_id) + f"\nBounded revision round {round_index} of {MAX_REPAIR_ROUNDS}. "
            "The following is your retained previous candidate, quoted as data, followed by ONE verified failing input. "
            "Derive a corrected Boolean procedure that satisfies the original specification for every input. "
            "Return the same JSON schema. No solution expression or full truth table is supplied.\n"
            + json.dumps({"previous_candidate": previous, "single_counterexample": feedback}, ensure_ascii=False) + "\n")
    return {"prompt": text, "prompt_sha256": _sha(text.encode("utf-8")), "profile_id": profile_id,
            "repair_round": round_index, "previous_response_sha256": parsed["response_sha256"],
            "counterexample": copy.deepcopy(counterexample), "counterexample_count": 1,
            "scope": "single verified counterexample feedback; maximum two numbered repair rounds; caller retains round lineage"}


def build_request(curriculum_dir, responses):
    if not isinstance(responses, list) or not 1 <= len(responses) <= MAX_RESPONSES:
        raise ValueError("V2 retained response count bound")
    frozen = load_curriculum(curriculum_dir)
    request = {"schema": admission.SCHEMA, "oracles": [], "candidates": []}
    decisions, rounds = [], set()
    for index, record in enumerate(responses):
        decision = {"response_index": index, "status": "rejected"}
        decisions.append(decision)
        try:
            if not isinstance(record, dict) or record.get("profile_id") not in frozen["profiles"]:
                raise ValueError("response references an unfrozen V2 profile")
            identity = record["profile_id"]
            decision["profile_id"] = identity
            profile = frozen["profiles"][identity]
            repair = record.get("repair")
            expected_profile = profile
            if repair is not None:
                if not isinstance(repair, dict) or set(repair) != {"round", "previous_response_path", "previous_response_sha256", "counterexample"}:
                    raise ValueError("invalid retained repair context")
                previous = original._read(repair["previous_response_path"], MAX_RESPONSE_BYTES)
                if _sha(previous) != repair["previous_response_sha256"]:
                    raise ValueError("repair predecessor response hash mismatch")
                correction = repair_prompt(identity, previous, repair["counterexample"], repair["round"])
                expected_profile = dict(profile, prompt_sha256=correction["prompt_sha256"])
            provenance, raw = original._provenance(record, expected_profile)
            if repair is not None:
                run = _json(original._read(record["run_path"], original.MAX_RUN_BYTES))
                if run.get("repair") != repair:
                    raise ValueError("repair context is not bound by the retained inference run")
                round_key = (identity, provenance["model_artifact_sha256"], repair["round"])
                if round_key in rounds:
                    raise ValueError("duplicate model/profile repair round in bounded batch")
                rounds.add(round_key)
            parsed = parse_response(raw, identity)
            oracle = copy.deepcopy(profile["oracle"])
            oracle_id = identity + ":expression-response:" + str(index)
            oracle["id"] = oracle_id
            oracle["source"]["frozen_oracle_sha256"] = profile["oracle_sha256"]
            oracle["source"]["teacher_proposal"] = provenance
            if repair is not None:
                oracle["source"]["repair"] = copy.deepcopy(repair)
            seed = codec.digest("atomos-teacher-expression-seed-v2", {
                "frontend": VERSION, "profile_id": identity, "oracle_sha256": profile["oracle_sha256"],
                "prompt_sha256": provenance["prompt_sha256"], "response_sha256": provenance["response_sha256"],
                "run_sha256": provenance["run_sha256"], "model_artifact_sha256": provenance["model_artifact_sha256"],
                "model_repo": provenance["model_repo"], "model_revision": provenance["model_revision"]})
            request["oracles"].append(oracle)
            request["candidates"].append({"name": identity, "oracle_id": oracle_id, "kind": "boolean-circuit",
                                           "capsule": {"seed_hex": seed, "version": 1, "next_slot": 0,
                                                       "circuit": parsed["circuit"], "expressions": parsed["canonical_ast"],
                                                       "generator": VERSION}})
            decision.update(status="compiled_candidate", expression_nodes=parsed["expression_nodes"],
                            expression_depth=parsed["expression_depth"], gate_count=len(parsed["circuit"]["gates"]),
                            wrapping=parsed["wrapping"], response_sha256=parsed["response_sha256"],
                            oracle_id=oracle_id, seed_hex=seed, teacher_provenance=provenance,
                            repair_round=repair["round"] if repair is not None else 0)
        except (OSError, KeyError, TypeError, ValueError, RecursionError) as error:
            decision.update(reason="invalid_expression_response_or_provenance", detail=str(error))
    return request, {"schema": "atomos-teacher-expression-adapter-receipt-v2", "adapter_version": VERSION,
                     "frontend_source_sha256": _sha(Path(__file__).read_bytes()),
                     "original_frontend_sha256": _sha(Path(original.__file__).read_bytes()),
                     "curriculum_sha256": frozen["curriculum_sha256"],
                     "status": "candidates_prepared" if request["candidates"] else "no_valid_candidates",
                     "responses_received": len(responses), "compiled_candidates": len(request["candidates"]),
                     "rejected_responses": len(responses) - len(request["candidates"]), "decisions": decisions,
                     "semantic_verification": "pending unchanged full-domain oracle and semantic-novelty admission",
                     "scope": "representation-only frontend change; no supplied algorithms, teacher repairs, Python evaluation or GPU claim",
                     "limits": {"response_bytes": MAX_RESPONSE_BYTES, "expression_bytes": MAX_EXPR_BYTES,
                                "expression_nodes": MAX_AST_NODES, "expression_depth": MAX_AST_DEPTH,
                                "responses": MAX_RESPONSES, "repair_rounds": MAX_REPAIR_ROUNDS}}
