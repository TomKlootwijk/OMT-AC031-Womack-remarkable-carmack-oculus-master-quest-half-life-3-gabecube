"""Bounded, oracle-checked semantic admission into existing AOPLUT1 textures.

Novelty is exact finite input/output behavior, not new seeds or program spelling.
The caller supplies the oracle separately; matching it is not proof of its truth.
This module prepares immutable artifacts and never updates a running/active bank.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile

import program_bank as codec
import program_bank_reference as reference


SCHEMA = "atomos-knowledge-candidates-v1"
RECEIPT_SCHEMA = "atomos-knowledge-admission-v1"
MAX_CANDIDATES = 256
MAX_BANK_CAPSULES = 4096
MAX_BANK_BYTES = 64 << 20
MAX_PAGE_BYTES = 64 << 10
MAX_JSON_BYTES = 16 << 20
MAX_WIRES = 1024
MAX_BOOLEAN_WORK = 64 << 20


def _integer(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer in [{minimum}, {maximum}]")
    return value


def _json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha(payload):
    return hashlib.sha256(payload).hexdigest()


def read_request(path: Path) -> dict:
    path = Path(path)
    if path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError("candidate JSON byte bound")
    raw = path.read_bytes()
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError("candidate JSON byte bound")
    return json.loads(raw.decode("utf-8"))


def _checked_circuit(circuit):
    if not isinstance(circuit, dict):
        raise ValueError("candidate circuit must be an object")
    inputs = _integer(circuit.get("input_bits"), "input_bits", 1, 12)
    _integer(circuit.get("output_bits"), "output_bits", 1, 8)
    _integer(circuit.get("constant_zero_wire"), "constant_zero_wire", inputs, inputs)
    gates = circuit.get("gates")
    if not isinstance(gates, list) or inputs + 1 + len(gates) > MAX_WIRES:
        raise ValueError("native 1024-wire bound")
    return codec.validate_circuit(circuit)


class _Budget:
    def __init__(self):
        self.boolean_work = 0
        self.domain_evaluations = 0

    def outputs(self, circuit):
        circuit = _checked_circuit(circuit)
        count = 1 << circuit["input_bits"]
        work = count * (circuit["input_bits"] + len(circuit["gates"]) + circuit["output_bits"])
        if self.boolean_work + work > MAX_BOOLEAN_WORK:
            raise ValueError("bounded Boolean verification work exhausted")
        self.boolean_work += work
        self.domain_evaluations += count
        ref = {"input_bits": circuit["input_bits"], "gates": circuit["gates"],
               "outputs": circuit["outputs"]}
        return bytes(reference.evaluate(ref, value) for value in range(count))


def _semantic_key(circuit, outputs):
    # The complete bytes are the archive key. SHA-256 is only a receipt identity;
    # a hypothetical digest collision cannot cause semantic equality here.
    return (b"atomos-finite-boolean-interface-v1\0" +
            struct.pack("<BB", circuit["input_bits"], circuit["output_bits"]) + outputs)


def semantic_signature(circuit: dict) -> str:
    """Digest of widths and full behavior, independent of chart and metadata."""
    return _sha(_semantic_key(circuit, _Budget().outputs(circuit)))


def _oracle(record):
    if not isinstance(record, dict) or record.get("kind") != "fixed-domain-oracle":
        raise ValueError("oracle must declare fixed-domain-oracle")
    if record.get("independent_of_candidate") is not True:
        raise ValueError("oracle independence declaration is missing")
    source = record.get("source")
    if (not isinstance(source, dict) or
            not all(isinstance(source.get(key), str) and 0 < len(source[key]) <= 4096
                    for key in ("kind", "reference"))):
        raise ValueError("oracle needs bounded source kind and reference")
    inputs = _integer(record.get("input_bits"), "oracle input_bits", 1, 12)
    outputs = _integer(record.get("output_bits"), "oracle output_bits", 1, 8)
    count = 1 << inputs
    cases = record.get("cases")
    if not isinstance(cases, list) or len(cases) != count:
        raise ValueError("oracle must cover the entire finite domain exactly once")
    values = [None] * count
    for row in cases:
        if not isinstance(row, dict) or set(row) != {"input", "output"}:
            raise ValueError("oracle cases contain only input and output")
        x = _integer(row["input"], "oracle input", 0, count - 1)
        y = _integer(row["output"], "oracle output", 0, (1 << outputs) - 1)
        if values[x] is not None:
            raise ValueError("oracle repeats an input")
        values[x] = y
    return {"input_bits": inputs, "output_bits": outputs,
            "values": bytes(values), "source": copy.deepcopy(source),
            "record_sha256": _sha(_json_bytes(record))}


def _base_preflight(path):
    if path.stat().st_size > MAX_BANK_BYTES:
        raise ValueError("base bank byte bound")
    raw = path.read_bytes()
    if len(raw) < 56 or len(raw) > MAX_BANK_BYTES or raw[:8] != codec.BANK_MAGIC:
        raise ValueError("base bank magic/byte bound")
    version, rows, angles, count = struct.unpack_from("<4I", raw, 8)
    if version != 1 or not 1 <= count <= MAX_BANK_CAPSULES:
        raise ValueError("base bank schema/capsule bound")
    page_bytes = rows * angles // 8
    if not 128 <= page_bytes <= MAX_PAGE_BYTES:
        raise ValueError("base page byte bound")
    if len(raw) != 56 + count * (8 + page_bytes):
        raise ValueError("base bank byte extent")
    manifest_path = path.parent / "manifest.json"
    if not manifest_path.is_file() or manifest_path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError("base bank needs a bounded manifest")
    manifest_bytes = manifest_path.read_bytes()
    if len(manifest_bytes) > MAX_JSON_BYTES:
        raise ValueError("base manifest byte bound")
    return raw, manifest_bytes


def admit_candidates(base_bank: Path, request: dict, out: Path, *, candidate_limit: int = 64) -> dict:
    """Append verified novel functions; retain the base bytes and active pointer.

    Per-candidate rejection is normal and appears in admission.json. Malformed
    top-level input, an invalid base, or failed final verification raises instead
    and publishes no output directory. A no-novelty run writes only its bounded
    request/receipt, with no redundant bank copy or new active revision.
    """
    base_bank, out = Path(base_bank), Path(out)
    _integer(candidate_limit, "candidate_limit", 1, MAX_CANDIDATES)
    if out.exists():
        raise ValueError("refusing to overwrite an existing output directory")
    raw_request = _json_bytes(request)
    if len(raw_request) > MAX_JSON_BYTES:
        raise ValueError("candidate JSON byte bound")
    request = json.loads(raw_request)
    if not isinstance(request, dict) or request.get("schema") != SCHEMA:
        raise ValueError("unsupported knowledge candidate schema")
    candidates, oracle_records = request.get("candidates"), request.get("oracles")
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= candidate_limit:
        raise ValueError("candidate count bound")
    if not isinstance(oracle_records, list) or not 1 <= len(oracle_records) <= MAX_CANDIDATES:
        raise ValueError("oracle count bound")
    oracles, oracle_errors = {}, {}
    for record in oracle_records:
        identity = record.get("id") if isinstance(record, dict) else None
        if not isinstance(identity, str) or not 1 <= len(identity) <= 256:
            raise ValueError("oracle id must be a bounded string")
        if identity in oracles or identity in oracle_errors:
            raise ValueError("duplicate oracle id")
        try:
            oracles[identity] = _oracle(record)
        except (TypeError, ValueError) as error:
            oracle_errors[identity] = str(error)

    base_bytes, base_manifest_bytes = _base_preflight(base_bank)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".knowledge_admission_", dir=out.parent) as temporary:
        staging = Path(temporary)
        # Decode retained bytes, so concurrent changes to the source cannot alter
        # the meaning of this verification. The source is checked again at exit.
        snapshot = staging / "base"
        snapshot.mkdir()
        (snapshot / "bank.bin").write_bytes(base_bytes)
        (snapshot / "manifest.json").write_bytes(base_manifest_bytes)
        bank = codec.load_bank(snapshot / "bank.bin")
        independent_base = reference.decode_bank(snapshot / "bank.bin", snapshot / "manifest.json")
        base_manifest = json.loads(base_manifest_bytes)
        budget = _Budget()
        archive, base_keys = {}, []
        for slot, capsule in enumerate(bank["capsules"]):
            values = budget.outputs(capsule["circuit"])
            decoded = independent_base["capsules"][slot]
            ref_circuit = {"input_bits": decoded["input_bits"], "output_bits": decoded["output_bits"],
                           "constant_zero_wire": decoded["input_bits"],
                           "gates": [list(pair) for pair in decoded["gates"]], "outputs": decoded["outputs"]}
            if values != budget.outputs(ref_circuit):
                raise ValueError("independent base decoder semantics disagree")
            key = _semantic_key(capsule["circuit"], values)
            archive.setdefault(key, slot)
            base_keys.append(key)

        capsules = copy.deepcopy(bank["capsules"])
        admitted, decisions = [], []
        for index, candidate in enumerate(candidates):
            decision = {"candidate_index": index, "status": "rejected"}
            decisions.append(decision)
            try:
                if not isinstance(candidate, dict) or candidate.get("kind", "boolean-circuit") != "boolean-circuit":
                    raise ValueError("only bounded boolean-circuit candidates are supported")
                name = candidate.get("name")
                if not isinstance(name, str) or not 1 <= len(name) <= 256:
                    raise ValueError("candidate needs a bounded name")
                decision["name"] = name
                oracle_id = candidate.get("oracle_id")
                if not isinstance(oracle_id, str) or oracle_id not in oracles:
                    decision["reason"] = "missing_or_invalid_oracle"
                    decision["detail"] = oracle_errors.get(oracle_id, "no independently declared full-domain oracle") if isinstance(oracle_id, str) else "invalid oracle id"
                    continue
                oracle = oracles[oracle_id]
                capsule = copy.deepcopy(candidate.get("capsule"))
                if not isinstance(capsule, dict):
                    raise ValueError("candidate capsule must be an object")
                circuit = _checked_circuit(capsule.get("circuit"))
                if any(circuit[k] != oracle[k] for k in ("input_bits", "output_bits")):
                    raise ValueError("oracle and candidate interfaces differ")
                values = budget.outputs(circuit)
                if values != oracle["values"]:
                    first = next(x for x in range(len(values)) if values[x] != oracle["values"][x])
                    decision.update(reason="oracle_mismatch", counterexample={
                        "input": first, "expected": oracle["values"][first], "actual": values[first]})
                    continue
                key = _semantic_key(circuit, values)
                decision.update(semantic_sha256=_sha(key), oracle_id=oracle_id, verified_cases=len(values))
                if key in archive:
                    decision.update(reason="duplicate_semantics", existing_slot=archive[key])
                    continue
                if len(capsules) >= MAX_BANK_CAPSULES:
                    decision["reason"] = "bank_capsule_bound"
                    continue
                slot = len(capsules)
                capsule["name"] = name
                capsule.setdefault("next_slot", slot)  # Bounded self-reference is permitted.
                capsule.setdefault("parent_sha256", capsules[-1]["content_sha256"])
                words, descriptor = codec.encode_capsule(capsule, rows=bank["rows"], angles=bank["angles"],
                                                          program_id=slot, capsule_count=slot + 1)
                if 56 + (slot + 1) * (8 + len(words) * 4) > MAX_BANK_BYTES:
                    decision["reason"] = "bank_byte_bound"
                    continue
                capsule["content_sha256"] = descriptor["content_sha256"]
                capsules.append(capsule)
                archive[key] = slot
                admitted.append({"slot": slot, "key": key, "oracle": oracle, "oracle_id": oracle_id,
                                 "candidate_index": index})
                decision.update(status="accepted", reason="verified_novel_function", slot=slot,
                                content_sha256=descriptor["content_sha256"])
            except (KeyError, TypeError, ValueError) as error:
                decision.update(reason="invalid_or_unsupported_candidate", detail=str(error))

        prepared = staging / "prepared"
        prepared.mkdir()
        (prepared / "candidates.json").write_bytes(raw_request + b"\n")
        proposed_sha = None
        if admitted:
            manifest = codec.write_bank(prepared / "bank.bin", capsules,
                                        master_seed_hex=bank["master_seed_hex"],
                                        rows=bank["rows"], angles=bank["angles"])
            proposed_bytes = (prepared / "bank.bin").read_bytes()
            if proposed_bytes[56:len(base_bytes)] != base_bytes[56:]:
                raise ValueError("existing program pages changed during admission")
            # Retain prior metadata as well as their exact program bytes.
            for field, value in base_manifest.items():
                manifest.setdefault(field, value)
            for old, record in zip(base_manifest["capsules"], manifest["capsules"]):
                if any(field in old and old[field] != value for field, value in record.items()):
                    raise ValueError("existing capsule metadata changed during admission")
                record.clear()
                record.update(copy.deepcopy(old))
            for entry in admitted:
                manifest["capsules"][entry["slot"]]["knowledge_admission"] = {
                    "semantic_sha256": _sha(entry["key"]), "oracle_id": entry["oracle_id"],
                    "oracle_record_sha256": entry["oracle"]["record_sha256"],
                    "source": entry["oracle"]["source"],
                    "scope": "exact finite oracle conformance; oracle truth and origin are not authenticated"}
            (prepared / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            codec.load_bank(prepared / "bank.bin")
            independent = reference.decode_bank(prepared / "bank.bin", prepared / "manifest.json")
            expected_keys = base_keys + [entry["key"] for entry in admitted]
            for slot, decoded in enumerate(independent["capsules"]):
                circuit = {"input_bits": decoded["input_bits"], "output_bits": decoded["output_bits"],
                           "constant_zero_wire": decoded["input_bits"],
                           "gates": [list(pair) for pair in decoded["gates"]], "outputs": decoded["outputs"]}
                if _semantic_key(circuit, budget.outputs(circuit)) != expected_keys[slot]:
                    raise ValueError("packed proposal failed independent full-domain verification")
            proposed_sha = _sha(proposed_bytes)

        receipt = {
            "schema": RECEIPT_SCHEMA,
            "status": "prepared" if admitted else "no_growth",
            "base_bank_sha256": _sha(base_bytes), "base_manifest_sha256": _sha(base_manifest_bytes),
            "request_sha256": _sha(raw_request), "proposed_bank_sha256": proposed_sha,
            "base_capsules": bank["capsule_count"], "accepted_capsules": len(admitted),
            "rejected_candidates": len(candidates) - len(admitted), "result_capsules": len(capsules),
            "base_unique_functions": len(set(base_keys)), "result_unique_functions": len(archive),
            "base_program_pages_unchanged": True,
            "new_active_bank_published": False, "gpu_execution": "not_run",
            "novelty_scope": "exact ordered bit-index interface widths and full-domain outputs; labels, seed, name, ancestry, routing and layout excluded; not universal typed semantic equivalence",
            "knowledge_scope": "conformance to separately supplied oracle cases; source independence is declared, not authenticated",
            "stateful_novelty": "not_supported; combinational function admission does not classify recurrent system equivalence",
            "stop_rule": "each input candidate considered once; equivalent functions allocate no program page; fixed work and capacity bounds",
            "limits": {"candidate_limit": candidate_limit, "maximum_candidates": MAX_CANDIDATES,
                       "input_bits": 12, "output_bits": 8, "wires": MAX_WIRES,
                       "bank_capsules": MAX_BANK_CAPSULES, "bank_bytes": MAX_BANK_BYTES,
                       "page_bytes": MAX_PAGE_BYTES, "json_bytes": MAX_JSON_BYTES,
                       "boolean_work": MAX_BOOLEAN_WORK},
            "work": {"boolean_work": budget.boolean_work, "domain_evaluations": budget.domain_evaluations},
            "decisions": decisions,
        }
        (prepared / "admission.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        if base_bank.read_bytes() != base_bytes or (base_bank.parent / "manifest.json").read_bytes() != base_manifest_bytes:
            raise ValueError("base bank or manifest changed during admission")
        if out.exists():
            raise ValueError("output directory appeared during verification; refusing overwrite")
        # The project runs on Windows, where directory rename does not replace an
        # existing destination. No active-bank pointer is read or changed here.
        os.rename(prepared, out)
        return receipt


def demo_request(base_bank: Path) -> dict:
    """Five supplied proposals; oracle meanings are independent scalar formulas.

    This is explicitly a synthetic learned_v1 fixture, not an LLM extraction run.
    """
    _base_preflight(Path(base_bank))
    bank = codec.load_bank(Path(base_bank))
    old = copy.deepcopy(bank["capsules"][0])
    if old["circuit"]["input_bits"] != 6 or old["circuit"]["output_bits"] != 1:
        raise ValueError("demo requires learned_v1's six-input enabled-fault first skill")
    old_expected = [int(bool(x & 1) and bool(x & 6)) for x in range(64)]
    if list(_Budget().outputs(old["circuit"])) != old_expected:
        raise ValueError("demo base does not match independently specified enabled fault")
    xor_expected = [int(bool(x & 1) != bool(x & 2)) for x in range(64)]
    def oracle(identity, values, meaning):
        return {"id": identity, "kind": "fixed-domain-oracle", "independent_of_candidate": True,
                "input_bits": 6, "output_bits": 1,
                "source": {"kind": "synthetic-independent-specification", "reference": meaning},
                "cases": [{"input": x, "output": y} for x, y in enumerate(values)]}
    seed_clone = copy.deepcopy(old)
    seed_clone.update(seed_hex=codec.seed_digest("novelty demo reseed"), version=old["version"] + 1)
    circuit_clone = copy.deepcopy(old)
    original_output = circuit_clone["circuit"]["outputs"][0]
    wire = 7 + len(circuit_clone["circuit"]["gates"])
    circuit_clone["circuit"]["gates"].extend([[original_output, original_output], [wire, wire]])
    circuit_clone["circuit"]["outputs"] = [wire + 1]
    circuit_clone["seed_hex"] = codec.seed_digest("novelty demo alternate NOR spelling")
    xor = {"seed_hex": codec.seed_digest("novelty demo xor skill"), "next_slot": 0,
           "circuit": codec.compile_nor([["xor", ["input", 0], ["input", 1]]], 6)}
    invalid = copy.deepcopy(xor)
    invalid["circuit"]["outputs"] = [6]  # Constant zero contradicts the independent XOR oracle.
    repeat = copy.deepcopy(xor)
    repeat["seed_hex"] = codec.seed_digest("novelty demo another xor seed")
    return {"schema": SCHEMA,
            "oracles": [oracle("enabled_fault", old_expected,
                               "Synthetic fault-alarm policy: input bit0=enabled, bit1=fault_a, bit2=fault_b; bits3..5 ignored. Output bit0=enabled AND (fault_a OR fault_b). Domain: all 64 six-bit inputs."),
                        oracle("two_signal_xor", xor_expected,
                               "Synthetic sensor-disagreement predicate: input bit0=sensor_a, bit1=sensor_b; bits2..5 ignored. Output bit0=signals_disagree=(sensor_a != sensor_b). Domain: all 64 six-bit inputs; appended capsule routes to existing slot0.")],
            "candidates": [
                {"name": "reseeded_old_skill", "oracle_id": "enabled_fault", "capsule": seed_clone},
                {"name": "equivalent_double_negation", "oracle_id": "enabled_fault", "capsule": circuit_clone},
                {"name": "incorrect_xor", "oracle_id": "two_signal_xor", "capsule": invalid},
                {"name": "two_signal_xor", "oracle_id": "two_signal_xor", "capsule": xor},
                {"name": "repeated_xor", "oracle_id": "two_signal_xor", "capsule": repeat}]}
