"""Compile retained teacher algorithms into checked finite program candidates.

No teacher is invoked here and no response is supplied or repaired. Integer
specifications are frozen before queries; returned expression trees are data,
never executable source. Source hashes bind records, not the truth of a model.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

import knowledge_admission as admission
import program_bank as codec


VERSION = "atomos-teacher-expression-adapter-v1"
CURRICULUM_SCHEMA = "atomos-frozen-knowledge-curriculum-v1"
RESPONSE_SCHEMA = "atomos-teacher-procedure-v1"
MAX_RESPONSE_BYTES = 64 << 10
MAX_RUN_BYTES = 1 << 20
MAX_AST_NODES = 512
MAX_AST_DEPTH = 24
MAX_JSON_DEPTH = 32
MAX_RESPONSES = 32


_PROFILES = [
    {"profile_id": "full_adder_1bit_v1", "input_bits": 3, "output_bits": 2,
     "input_labels": ["a", "b", "carry_in"], "output_labels": ["sum", "carry_out"],
     "specification": "Add the three unsigned one-bit inputs a, b and carry_in. Return the two-bit exact sum, least-significant bit first."},
    {"profile_id": "unsigned_compare_2bit_v1", "input_bits": 4, "output_bits": 3,
     "input_labels": ["a0", "a1", "b0", "b1"], "output_labels": ["a_less_b", "a_equal_b", "a_greater_b"],
     "specification": "Compare unsigned A=a0+2*a1 with B=b0+2*b1. Return three Boolean results in this order: A<B, A==B, A>B."},
    {"profile_id": "unsigned_add_2bit_v1", "input_bits": 4, "output_bits": 3,
     "input_labels": ["a0", "a1", "b0", "b1"], "output_labels": ["sum0", "sum1", "sum2"],
     "specification": "Add unsigned A=a0+2*a1 and B=b0+2*b1. Return their exact three-bit sum without overflow, least-significant bit first."},
    {"profile_id": "binary_to_gray_4bit_v1", "input_bits": 4, "output_bits": 4,
     "input_labels": ["binary0", "binary1", "binary2", "binary3"],
     "output_labels": ["gray0", "gray1", "gray2", "gray3"],
     "specification": "Convert a four-bit unsigned binary integer to its standard binary-reflected Gray-code representation. Input and output bits are ordered least-significant first."},
    {"profile_id": "absolute_difference_2bit_v1", "input_bits": 4, "output_bits": 2,
     "input_labels": ["a0", "a1", "b0", "b1"], "output_labels": ["difference0", "difference1"],
     "specification": "For unsigned A=a0+2*a1 and B=b0+2*b1, return the exact absolute difference |A-B| as two bits, least-significant bit first."},
    {"profile_id": "mux_2bit_v1", "input_bits": 5, "output_bits": 2,
     "input_labels": ["a0", "a1", "b0", "b1", "select_b"], "output_labels": ["selected0", "selected1"],
     "specification": "Select between unsigned two-bit words A=a0+2*a1 and B=b0+2*b1. Return A when select_b=0 and B when select_b=1, least-significant bit first."},
]


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _integer(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer in [{minimum}, {maximum}]")
    return value


def _digest(value, name):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(name + " must be a lower-case full SHA256")
    return value


def _read(path, limit):
    path = Path(path)
    if path.stat().st_size > limit:
        raise ValueError("retained artifact byte bound")
    raw = path.read_bytes()
    if len(raw) > limit:
        raise ValueError("retained artifact byte bound")
    return raw


def profiles() -> list[dict]:
    """Public typed curriculum, with no teacher-generated material."""
    return copy.deepcopy(_PROFILES)


def _profile(identity):
    for record in _PROFILES:
        if record["profile_id"] == identity:
            return copy.deepcopy(record)
    raise ValueError("unsupported curriculum profile")


def scalar_oracle(profile_id: str, value: int) -> int:
    """Independent arithmetic specifications, not expression-tree evaluation."""
    profile = _profile(profile_id)
    _integer(value, "oracle input", 0, (1 << profile["input_bits"]) - 1)
    a, b = value & 3, (value >> 2) & 3
    if profile_id == "full_adder_1bit_v1":
        return (value & 1) + ((value >> 1) & 1) + ((value >> 2) & 1)
    if profile_id == "unsigned_compare_2bit_v1":
        return int(a < b) | (int(a == b) << 1) | (int(a > b) << 2)
    if profile_id == "unsigned_add_2bit_v1":
        return a + b
    if profile_id == "binary_to_gray_4bit_v1":
        return value ^ (value >> 1)
    if profile_id == "absolute_difference_2bit_v1":
        return abs(a - b)
    if profile_id == "mux_2bit_v1":
        return b if value & 16 else a
    raise ValueError("unsupported scalar oracle")


def teacher_prompt(profile_id: str) -> str:
    """Request an algorithm from prior knowledge; include no oracle case labels."""
    p = _profile(profile_id)
    shape = {"schema": RESPONSE_SCHEMA, "profile_id": profile_id,
             "procedures": [{"name": profile_id, "input_bits": p["input_bits"],
                             "output_bits": p["output_bits"], "outputs": "REPLACE_WITH_OUTPUT_EXPRESSION_LIST"}]}
    return (
        "Express the following known digital algorithm as Boolean expression trees. "
        "Use your existing algorithm knowledge. Return only one JSON object; no prose, "
        "reasoning, Markdown, executable code or truth table.\n\n"
        + p["specification"] + "\n"
        + "Input wire indices: " + ", ".join(f"{i}={name}" for i, name in enumerate(p["input_labels"])) + ".\n"
        + "Output list order: " + ", ".join(f"{i}={name}" for i, name in enumerate(p["output_labels"])) + ".\n"
        + "Each output is one nested JSON array. The complete grammar is: "
        '["input", integer_wire_index], ["constant", 0_or_1], ["not", expression], '
        '["and", expression, expression], ["or", expression, expression], '
        '["xor", expression, expression]. All and/or/xor nodes have exactly two operands. '
        "Use literal integer 0 or 1 for constants, not JSON true/false. "
        "No named references, local definitions or other operators are supported. "
        f"Return exactly {p['output_bits']} expressions, at most {MAX_AST_NODES} total nodes "
        f"and depth at most {MAX_AST_DEPTH}.\n"
        + "Required object structure (replace the outputs placeholder with the expression list):\n"
        + json.dumps(shape, separators=(",", ":")) + "\n"
    )


def prepare_curriculum(out_dir: Path, profile_ids: list[str] | None = None) -> dict:
    """Freeze specifications, prompt bytes and independent cases before queries."""
    out_dir = Path(out_dir)
    if out_dir.exists():
        raise ValueError("refusing to overwrite a frozen curriculum")
    identities = list(profile_ids) if profile_ids is not None else [p["profile_id"] for p in _PROFILES]
    if not 1 <= len(identities) <= len(_PROFILES) or len(set(identities)) != len(identities):
        raise ValueError("curriculum profile count or duplicate identity")
    selected = [_profile(identity) for identity in identities]
    adapter_sha = _sha(Path(__file__).read_bytes())
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".teacher_curriculum_", dir=out_dir.parent) as temporary:
        prepared = Path(temporary) / "prepared"
        prepared.mkdir()
        records = []
        for p in selected:
            identity = p["profile_id"]
            prompt = teacher_prompt(identity).encode("utf-8")
            oracle = {"id": identity, "kind": "fixed-domain-oracle", "independent_of_candidate": True,
                      "input_bits": p["input_bits"], "output_bits": p["output_bits"],
                      "source": {"kind": "independent-integer-specification",
                                 "reference": identity + ": " + p["specification"],
                                 "input_labels": p["input_labels"], "output_labels": p["output_labels"],
                                 "specification_adapter_sha256": adapter_sha,
                                 "scope": "complete bounded integer specification; no teacher labels used"},
                      "cases": [{"input": x, "output": scalar_oracle(identity, x)}
                                for x in range(1 << p["input_bits"])]}
            oracle_bytes = json.dumps(oracle, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
            prompt_file, oracle_file = identity + ".prompt.txt", identity + ".oracle.json"
            (prepared / prompt_file).write_bytes(prompt)
            (prepared / oracle_file).write_bytes(oracle_bytes)
            records.append(dict(p, prompt_file=prompt_file, oracle_file=oracle_file,
                                prompt_sha256=_sha(prompt), oracle_sha256=_sha(oracle_bytes)))
        manifest = {"schema": CURRICULUM_SCHEMA, "adapter_version": VERSION,
                    "specification_adapter_sha256": adapter_sha,
                    "query_order": "freeze this curriculum before acquiring any teacher responses",
                    "teacher_execution": "not_run_by_curriculum_preparation", "profiles": records}
        (prepared / "curriculum.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        if out_dir.exists():
            raise ValueError("curriculum output appeared while preparing; refusing overwrite")
        os.rename(prepared, out_dir)
    return manifest


def load_curriculum(folder: Path) -> dict:
    folder = Path(folder)
    raw = _read(folder / "curriculum.json", MAX_RUN_BYTES)
    manifest = json.loads(raw)
    if (not isinstance(manifest, dict) or manifest.get("schema") != CURRICULUM_SCHEMA or
            manifest.get("adapter_version") != VERSION):
        raise ValueError("unsupported frozen curriculum schema")
    records = manifest.get("profiles")
    if not isinstance(records, list) or not 1 <= len(records) <= len(_PROFILES):
        raise ValueError("frozen profile list bound")
    by_id = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("invalid frozen profile")
        p = _profile(record.get("profile_id"))
        identity = p["profile_id"]
        if identity in by_id or any(record.get(key) != value for key, value in p.items()):
            raise ValueError("frozen profile differs from declared typed interface")
        if record.get("prompt_file") != identity + ".prompt.txt" or record.get("oracle_file") != identity + ".oracle.json":
            raise ValueError("noncanonical frozen artifact filename")
        prompt = _read(folder / record["prompt_file"], MAX_RESPONSE_BYTES)
        oracle_bytes = _read(folder / record["oracle_file"], MAX_RUN_BYTES)
        if _sha(prompt) != record.get("prompt_sha256") or _sha(oracle_bytes) != record.get("oracle_sha256"):
            raise ValueError("frozen prompt/oracle hash mismatch")
        if prompt.decode("utf-8") != teacher_prompt(identity):
            raise ValueError("frozen prompt does not match declared algorithm request")
        oracle = json.loads(oracle_bytes)
        expected_cases = [{"input": x, "output": scalar_oracle(identity, x)} for x in range(1 << p["input_bits"])]
        if (oracle.get("id") != identity or oracle.get("kind") != "fixed-domain-oracle" or
                oracle.get("independent_of_candidate") is not True or
                any(oracle.get(key) != p[key] for key in ("input_bits", "output_bits")) or
                oracle.get("cases") != expected_cases or
                oracle.get("source", {}).get("specification_adapter_sha256") != manifest.get("specification_adapter_sha256")):
            raise ValueError("frozen oracle differs from independent integer specification")
        by_id[identity] = dict(record, prompt=prompt.decode("utf-8"), oracle=oracle)
    return {"manifest": manifest, "curriculum_sha256": _sha(raw), "profiles": by_id}


def _reject_json_constant(value):
    raise ValueError("nonfinite JSON numbers are unsupported: " + value)


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON object key")
        value[key] = item
    return value


def _bounded_json_depth(text):
    depth, in_string, escaped = 0, False, False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
        elif character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > MAX_JSON_DEPTH:
                raise ValueError("teacher JSON nesting bound")
        elif character in "]}":
            depth -= 1
    # Syntax and balanced delimiters are checked by the JSON decoder below.


def parse_teacher_response(response: str | bytes, profile_id: str) -> dict:
    """Strict data parsing; accept only JSON or one enclosing JSON code fence."""
    raw = response.encode("utf-8") if isinstance(response, str) else response
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_RESPONSE_BYTES:
        raise ValueError("teacher response byte bound")
    text = raw.decode("utf-8").strip()
    wrapping = "plain_json"
    fence = re.fullmatch(r"```(?:json)?\r?\n(.*?)\r?\n```", text, flags=re.DOTALL)
    if fence:
        text, wrapping = fence.group(1), "single_json_fence"
    _bounded_json_depth(text)
    value = json.loads(text, object_pairs_hook=_unique_object, parse_constant=_reject_json_constant)
    if (not isinstance(value, dict) or set(value) != {"schema", "profile_id", "procedures"} or
            value.get("schema") != RESPONSE_SCHEMA or value.get("profile_id") != profile_id):
        raise ValueError("teacher response schema/profile mismatch")
    p = _profile(profile_id)
    procedures = value["procedures"]
    if not isinstance(procedures, list) or len(procedures) != 1:
        raise ValueError("one named procedure is required for each profile response")
    procedure = procedures[0]
    if (not isinstance(procedure, dict) or set(procedure) != {"name", "input_bits", "output_bits", "outputs"} or
            procedure.get("name") != profile_id):
        raise ValueError("invalid named procedure schema")
    for field in ("input_bits", "output_bits"):
        _integer(procedure.get(field), field, p[field], p[field])
    outputs = procedure["outputs"]
    if not isinstance(outputs, list) or len(outputs) != p["output_bits"]:
        raise ValueError("procedure output count differs from typed interface")
    pending = [(expression, 1) for expression in outputs]
    count = 0
    while pending:
        node, depth = pending.pop()
        count += 1
        if count > MAX_AST_NODES or depth > MAX_AST_DEPTH:
            raise ValueError("teacher expression node/depth bound")
        if not isinstance(node, list) or not node or not isinstance(node[0], str):
            raise ValueError("expression must be an opcode array")
        op = node[0]
        if op in ("input", "constant"):
            if len(node) != 2:
                raise ValueError("terminal expression arity")
            _integer(node[1], op, 0, p["input_bits"] - 1 if op == "input" else 1)
        elif op == "not":
            if len(node) != 2:
                raise ValueError("not expression arity")
            pending.append((node[1], depth + 1))
        elif op in ("and", "or", "xor"):
            if len(node) != 3:
                raise ValueError("binary expression arity")
            pending.extend(((node[1], depth + 1), (node[2], depth + 1)))
        else:
            raise ValueError("unsupported expression opcode")
    circuit = codec.compile_nor(outputs, p["input_bits"])
    if circuit["input_bits"] + 1 + len(circuit["gates"]) > admission.MAX_WIRES:
        raise ValueError("compiled teacher procedure exceeds native wire bound")
    return {"procedure": procedure, "circuit": circuit, "ast_nodes": count,
            "wrapping": wrapping, "response_sha256": _sha(raw)}


def _provenance(record, profile):
    if not isinstance(record, dict) or not isinstance(record.get("provenance"), dict):
        raise ValueError("response requires retained teacher provenance")
    if len(_canonical(record["provenance"])) > MAX_RUN_BYTES:
        raise ValueError("teacher provenance byte bound")
    p = copy.deepcopy(record["provenance"])
    repo = p.get("model_repo")
    if not isinstance(repo, str) or not 1 <= len(repo) <= 512:
        raise ValueError("teacher model_repo is missing or excessive")
    for field in ("model_artifact_sha256", "prompt_sha256", "response_sha256", "run_sha256"):
        _digest(p.get(field), field)
    revision, status = p.get("model_revision"), p.get("model_revision_status")
    if status == "unknown_cached_origin":
        if revision not in (None, "unknown"):
            raise ValueError("unknown cached origin must not invent a model revision")
    elif status == "pinned_huggingface_commit":
        if not isinstance(revision, str) or re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", revision) is None:
            raise ValueError("pinned model revision must be a full commit digest")
    else:
        raise ValueError("model revision status is unsupported")
    if p["prompt_sha256"] != profile["prompt_sha256"]:
        raise ValueError("teacher prompt was not the frozen profile prompt")
    response_path, run_path = Path(record["response_path"]), Path(record["run_path"])
    response = _read(response_path, MAX_RESPONSE_BYTES)
    run_bytes = _read(run_path, MAX_RUN_BYTES)
    if _sha(response) != p["response_sha256"] or _sha(run_bytes) != p["run_sha256"]:
        raise ValueError("retained teacher response/run hash mismatch")
    run = json.loads(run_bytes, object_pairs_hook=_unique_object, parse_constant=_reject_json_constant)
    if not isinstance(run, dict):
        raise ValueError("teacher run record must be an object")
    for field in ("model_repo", "model_revision", "model_revision_status", "model_artifact_sha256", "prompt_sha256", "response_sha256"):
        if field not in run or run[field] != p.get(field):
            raise ValueError("teacher run/provenance binding differs: " + field)
    p["response_path"], p["run_path"] = str(response_path), str(run_path)
    return p, response


def build_teacher_request(curriculum_dir: Path, responses: list[dict]) -> tuple[dict, dict]:
    """Adapt only retained actual response bytes; return all parsing failures.

    ``responses`` records contain profile_id, response_path, run_path and a
    provenance object with model_repo, model_revision, model_revision_status,
    model_artifact_sha256, prompt_sha256, response_sha256 and run_sha256. This
    function compiles proposed algorithms; semantic admission remains separate.
    """
    if not isinstance(responses, list) or not 1 <= len(responses) <= MAX_RESPONSES:
        raise ValueError("teacher response count bound")
    curriculum = load_curriculum(curriculum_dir)
    request = {"schema": admission.SCHEMA, "oracles": [], "candidates": []}
    decisions = []
    for index, record in enumerate(responses):
        decision = {"response_index": index, "status": "rejected"}
        decisions.append(decision)
        try:
            if not isinstance(record, dict) or record.get("profile_id") not in curriculum["profiles"]:
                raise ValueError("response references an unfrozen profile")
            identity = record["profile_id"]
            decision["profile_id"] = identity
            profile = curriculum["profiles"][identity]
            provenance, response = _provenance(record, profile)
            parsed = parse_teacher_response(response, identity)
            oracle = copy.deepcopy(profile["oracle"])
            oracle_id = identity + ":response:" + str(index)
            oracle["id"] = oracle_id
            oracle["source"]["frozen_oracle_sha256"] = profile["oracle_sha256"]
            oracle["source"]["teacher_proposal"] = provenance
            seed = codec.digest("atomos-teacher-procedure-seed-v1", {
                "profile_id": identity, "adapter_version": VERSION,
                "oracle_sha256": profile["oracle_sha256"], "prompt_sha256": profile["prompt_sha256"],
                "response_sha256": provenance["response_sha256"], "run_sha256": provenance["run_sha256"],
                "model_repo": provenance["model_repo"], "model_revision": provenance["model_revision"],
                "model_artifact_sha256": provenance["model_artifact_sha256"]})
            request["oracles"].append(oracle)
            request["candidates"].append({"name": identity, "oracle_id": oracle_id,
                                           "kind": "boolean-circuit",
                                           "capsule": {"seed_hex": seed, "next_slot": 0, "version": 1,
                                                       "circuit": parsed["circuit"],
                                                       "expressions": parsed["procedure"]["outputs"],
                                                       "generator": VERSION}})
            decision.update(status="compiled_candidate", ast_nodes=parsed["ast_nodes"],
                            gate_count=len(parsed["circuit"]["gates"]), wrapping=parsed["wrapping"],
                            seed_hex=seed, response_sha256=parsed["response_sha256"],
                            oracle_id=oracle_id, teacher_provenance=provenance)
        except (OSError, KeyError, TypeError, ValueError, RecursionError) as error:
            decision.update(reason="invalid_response_or_provenance", detail=str(error))
    receipt = {"schema": "atomos-teacher-adapter-receipt-v1", "adapter_version": VERSION,
               "adapter_source_sha256": _sha(Path(__file__).read_bytes()),
               "curriculum_sha256": curriculum["curriculum_sha256"],
               "status": "candidates_prepared" if request["candidates"] else "no_valid_candidates",
               "responses_received": len(responses), "compiled_candidates": len(request["candidates"]),
               "rejected_responses": len(responses) - len(request["candidates"]), "decisions": decisions,
               "semantic_verification": "pending knowledge_admission full-domain oracle and novelty checks",
               "teacher_execution": "external retained run records; this adapter invokes no model",
               "scope": "extracted algorithm expressions compiled to NOR; not predictive student training or full-model knowledge transfer",
               "limits": {"responses": MAX_RESPONSES, "response_bytes": MAX_RESPONSE_BYTES,
                          "run_bytes": MAX_RUN_BYTES, "ast_nodes": MAX_AST_NODES,
                          "ast_depth": MAX_AST_DEPTH, "json_depth": MAX_JSON_DEPTH}}
    return request, receipt


def admit_teacher_knowledge(base_bank: Path, curriculum_dir: Path, responses: list[dict], out: Path) -> dict:
    """Convenience wrapper; CPU admission produces a proposal, not GPU proof."""
    request, adapter = build_teacher_request(curriculum_dir, responses)
    if not request["candidates"]:
        return {"adapter": adapter, "admission": None}
    receipt = admission.admit_candidates(base_bank, request, Path(out), candidate_limit=MAX_RESPONSES)
    return {"adapter": adapter, "admission": receipt}
