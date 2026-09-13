"""Example-driven finite Boolean skill distillation and packed program banks.

Concept: Tom Klootwijk, atomOS. This is a new finite engineering profile.
Search uses training labels only. All-input behavior signatures are unlabelled
novelty probes, not teacher answers. A seed schedules search; it is not lossless
compression of the teacher dataset or arbitrary knowledge.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
from typing import Any

SCHEMA = "atomos-teacher-examples-v1"
GENERATOR = "atomos-novelty-boolean-synthesis-v1"
BANK_MAGIC = b"AOPLUT1\n"
PAGE_MAGIC = 0x31504B41


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(domain: str, value: Any) -> str:
    payload = canonical(value)
    return hashlib.sha256(domain.encode("ascii") + b"\0" +
                          len(payload).to_bytes(8, "big") + payload).hexdigest()


def seed_digest(seed: str) -> str:
    if not isinstance(seed, str) or not seed:
        raise ValueError("seed must be a nonempty string")
    return digest("atomOS:program-bank:seed:v1", {"seed": seed})


def _integer(value: Any, name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer in {minimum}..{maximum}")
    return value


def validate_examples(data: dict) -> dict:
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise ValueError("unsupported teacher example schema")
    bits = _integer(data.get("input_bits"), "input_bits", 1, 12)
    outputs = _integer(data.get("output_bits"), "output_bits", 1, 8)
    skills = data.get("skills")
    if not isinstance(skills, list) or not skills:
        raise ValueError("at least one teacher skill is required")
    names: set[str] = set()
    for skill in skills:
        if not isinstance(skill, dict) or not isinstance(skill.get("name"), str) or not skill["name"]:
            raise ValueError("each teacher skill requires a nonempty name")
        if skill["name"] in names:
            raise ValueError("duplicate skill name")
        names.add(skill["name"])
        seen: dict[str, dict[int, int]] = {}
        for split in ("train", "holdout", "full_domain"):
            rows = skill.get(split, [])
            if not isinstance(rows, list) or (split == "train" and not rows):
                raise ValueError(f"{skill['name']}: nonempty training examples required")
            seen[split] = {}
            for row in rows:
                if not isinstance(row, dict) or set(row) != {"input", "output"}:
                    raise ValueError("example rows must contain exactly input and output")
                x = _integer(row["input"], "example input", 0, (1 << bits) - 1)
                y = _integer(row["output"], "example output", 0, (1 << outputs) - 1)
                if x in seen[split]:
                    raise ValueError(f"duplicate input in {split}")
                seen[split][x] = y
        if set(seen["train"]) & set(seen["holdout"]):
            raise ValueError("training and holdout input sets must be disjoint")
        if seen["full_domain"]:
            if len(seen["full_domain"]) != 1 << bits:
                raise ValueError("full_domain must label every input exactly once")
            for split in ("train", "holdout"):
                if any(seen["full_domain"][x] != y for x, y in seen[split].items()):
                    raise ValueError("full-domain labels disagree with training/holdout evidence")
    return data


def builtin_examples(seed: str, train_count: int = 40) -> dict:
    """Synthetic independent teachers; their functions never enter synthesis."""
    _integer(train_count, "train_count", 1, 63)
    def alarm(x: int) -> int:
        return ((x & 1) != 0) and ((x & 6) != 0)
    def permit(x: int) -> int:
        return ((x & 1) != 0) and ((x & 2) == 0)
    def parity(x: int) -> int:
        return (int(bool(x & 1)) + int(bool(x & 2)) + int(bool(x & 4))) % 2
    teachers = (("enabled_fault_alarm", alarm), ("permission_without_block", permit),
                ("three_signal_parity", parity))
    root = seed_digest(seed)
    skills = []
    for name, teacher in teachers:
        ordered = sorted(range(64), key=lambda x: digest("atomOS:teacher:split:v1", [root, name, x]))
        rows = [{"input": x, "output": int(teacher(x))} for x in range(64)]
        skills.append({"name": name, "train": [rows[x] for x in ordered[:train_count]],
                       "holdout": [rows[x] for x in ordered[train_count:]], "full_domain": rows})
    return validate_examples({"schema": SCHEMA, "input_bits": 6, "output_bits": 1,
                              "teacher_kind": "independent_synthetic_finite_policy_functions",
                              "skills": skills})


@dataclass(frozen=True)
class Expression:
    op: str
    signature: int
    operators: int
    args: tuple = ()

    def record(self) -> list:
        return [self.op, *[v.record() if isinstance(v, Expression) else v for v in self.args]]


def expression_value(record: list, x: int) -> int:
    """Recursive scalar evaluator, independent of bit-parallel search signatures."""
    op = record[0]
    if op == "input":
        return (x >> record[1]) & 1
    if op == "constant":
        return record[1]
    if op == "not":
        return 1 - expression_value(record[1], x)
    a, b = expression_value(record[1], x), expression_value(record[2], x)
    if op == "and":
        return int(a == 1 and b == 1)
    if op == "or":
        return int(a == 1 or b == 1)
    if op == "xor":
        return int(a != b)
    raise ValueError("unknown expression opcode")


def compile_nor(records: list[list], input_bits: int) -> dict:
    """Inputs followed by a constant-zero wire; only acyclic NOR gates follow."""
    _integer(input_bits, "input_bits", 1, 12)
    gates: list[list[int]] = []
    shared: dict[tuple[int, int], int] = {}
    expressions: dict[bytes, int] = {}
    zero = input_bits
    def nor(a: int, b: int) -> int:
        key = tuple(sorted((a, b)))
        if key not in shared:
            shared[key] = input_bits + 1 + len(gates)
            gates.append(list(key))
        return shared[key]
    def invert(a: int) -> int:
        if a > input_bits:
            left, right = gates[a - input_bits - 1]
            if left == right:
                return left
        return nor(a, a)
    def lower(e: list) -> int:
        key = canonical(e)
        if key in expressions:
            return expressions[key]
        op = e[0]
        if op == "input":
            result = _integer(e[1], "expression input", 0, input_bits - 1)
        elif op == "constant":
            result = zero if _integer(e[1], "constant", 0, 1) == 0 else invert(zero)
        elif op == "not":
            a = lower(e[1]); result = invert(a)
        else:
            a, b = lower(e[1]), lower(e[2])
            if op == "and":
                result = nor(invert(a), invert(b))
            elif op == "or":
                c = nor(a, b); result = invert(c)
            elif op == "xor":
                c = nor(a, b); d = nor(nor(a, c), nor(b, c)); result = invert(d)
            else:
                raise ValueError("unknown expression opcode")
        expressions[key] = result
        return result
    outputs = [lower(e) for e in records]
    needed: set[int] = set()
    pending = list(outputs)
    while pending:
        wire = pending.pop()
        if wire > input_bits and wire not in needed:
            needed.add(wire)
            pending.extend(gates[wire - input_bits - 1])
    remap = {wire: wire for wire in range(input_bits + 1)}
    compact = []
    for i, (a, b) in enumerate(gates):
        old_wire = input_bits + 1 + i
        if old_wire in needed:
            remap[old_wire] = input_bits + 1 + len(compact)
            compact.append([remap[a], remap[b]])
    gates = compact
    outputs = [remap[wire] for wire in outputs]
    circuit = {"input_bits": input_bits, "output_bits": len(outputs),
               "constant_zero_wire": input_bits, "gates": gates, "outputs": outputs}
    validate_circuit(circuit)
    return circuit


def validate_circuit(circuit: dict) -> dict:
    inputs = _integer(circuit.get("input_bits"), "input_bits", 1, 12)
    outputs = _integer(circuit.get("output_bits"), "output_bits", 1, 8)
    if circuit.get("constant_zero_wire") != inputs:
        raise ValueError("missing canonical zero wire")
    gates = circuit.get("gates")
    if not isinstance(gates, list) or len(gates) > 65535:
        raise ValueError("invalid or excessive gate list")
    for i, gate in enumerate(gates):
        if not isinstance(gate, list) or len(gate) != 2:
            raise ValueError("NOR gate must contain two references")
        for wire in gate:
            _integer(wire, "gate wire", 0, inputs + i)
    refs = circuit.get("outputs")
    if not isinstance(refs, list) or len(refs) != outputs:
        raise ValueError("output reference count differs")
    for wire in refs:
        _integer(wire, "output wire", 0, inputs + len(gates))
    return circuit


def evaluate_circuit(circuit: dict, x: int) -> int:
    validate_circuit(circuit)
    _integer(x, "input", 0, (1 << circuit["input_bits"]) - 1)
    values = [(x >> i) & 1 for i in range(circuit["input_bits"])] + [0]
    for a, b in circuit["gates"]:
        values.append(int(values[a] == 0 and values[b] == 0))
    return sum(values[wire] << bit for bit, wire in enumerate(circuit["outputs"]))


def synthesize(training: list[dict], input_bits: int, output_bits: int, seed256: str,
               *, max_operators: int = 3, candidate_budget: int = 12000,
               archive_capacity: int = 64) -> tuple[list[list] | None, dict]:
    """Novelty-first bounded expression search with no access to audit labels.

    Each complexity round ranks previously unseen behavior by minimum Hamming
    distance from a frozen archive, then a seeded tie key. Only that order may
    consume the candidate budget. Training labels gate acceptance, never novelty.
    The archive samples the ranked stream at a fixed declared capacity.
    """
    _integer(input_bits, "input_bits", 1, 12)
    _integer(output_bits, "output_bits", 1, 8)
    _integer(max_operators, "max_operators", 0, 5)
    _integer(candidate_budget, "candidate_budget", 1, 1000000)
    _integer(archive_capacity, "archive_capacity", 1, 256)
    if len(seed256) != 64 or any(c not in "0123456789abcdef" for c in seed256):
        raise ValueError("search seed must be a lower-case full SHA-256 digest")
    if not training:
        raise ValueError("training examples are empty")
    seen_inputs = set()
    for row in training:
        x = _integer(row.get("input"), "training input", 0, (1 << input_bits) - 1)
        _integer(row.get("output"), "training output", 0, (1 << output_bits) - 1)
        if x in seen_inputs:
            raise ValueError("duplicate training input")
        seen_inputs.add(x)
    domain = 1 << input_bits
    full_mask = (1 << domain) - 1
    training_mask = sum(1 << row["input"] for row in training)
    wanted = [sum(((row["output"] >> bit) & 1) << row["input"] for row in training)
              for bit in range(output_bits)]
    literals = [Expression("input", sum(((x >> bit) & 1) << x for x in range(domain)), 0, (bit,))
                for bit in range(input_bits)]
    literals += [Expression("constant", 0, 0, (0,)), Expression("constant", full_mask, 0, (1,))]
    by_cost: dict[int, list[Expression]] = {}
    seen: dict[int, Expression] = {}
    archive: list[int] = []
    accepted: list[tuple | None] = [None] * output_bits
    rounds = []
    evaluated = duplicates = 0
    selection_trace = []
    budget_exhausted = False
    proposal_budget = min(100000, max(256, candidate_budget * 16))
    proposal_budget_exhausted = False
    for cost in range(max_operators + 1):
        proposals: dict[int, Expression] = {}
        lowered_costs: dict[bytes, tuple] = {}
        generated = 0
        def representation_cost(expr: Expression):
            encoded = canonical(expr.record())
            if encoded not in lowered_costs:
                lowered_costs[encoded] = (len(compile_nor([expr.record()], input_bits)["gates"]), encoded)
            return lowered_costs[encoded]
        def offer(expr: Expression):
            nonlocal generated, duplicates
            generated += 1
            if expr.signature in seen:
                duplicates += 1
            elif expr.signature in proposals:
                duplicates += 1
                if representation_cost(expr) < representation_cost(proposals[expr.signature]):
                    proposals[expr.signature] = expr
            else:
                proposals[expr.signature] = expr
        def candidates():
            if cost == 0:
                yield from literals
                return
            for expr in by_cost.get(cost - 1, []):
                yield Expression("not", full_mask ^ expr.signature, cost, (expr,))
            for left_cost in range(cost):
                right_cost = cost - 1 - left_cost
                if left_cost > right_cost:
                    continue
                for ai, a in enumerate(by_cost.get(left_cost, [])):
                    for bi, b in enumerate(by_cost.get(right_cost, [])):
                        if left_cost == right_cost and ai > bi:
                            continue
                        for op, signature in (("and", a.signature & b.signature),
                                              ("or", a.signature | b.signature),
                                              ("xor", a.signature ^ b.signature)):
                            yield Expression(op, signature, cost, (a, b))
        round_truncated = False
        for expr in candidates():
            if generated >= proposal_budget:
                proposal_budget_exhausted = round_truncated = True
                break
            offer(expr)
        archive_before = tuple(archive)
        def priority(expr: Expression):
            novelty = min(((expr.signature ^ old).bit_count() for old in archive_before), default=domain)
            tie = digest("atomOS:synthesis:tie:v1", [seed256, cost, expr.record()])
            return -novelty, tie
        ordered = sorted(proposals.values(), key=priority)
        kept = []
        for expr in ordered:
            if evaluated >= candidate_budget:
                budget_exhausted = True
                break
            novelty = -priority(expr)[0]
            evaluated += 1
            seen[expr.signature] = expr
            kept.append(expr)
            if len(archive) < archive_capacity:
                archive.append(expr.signature)
            else:
                # Fixed seeded reservoir admission does not inspect labels.
                key = int(digest("atomOS:synthesis:archive:v1", [seed256, evaluated]), 16)
                position = key % evaluated
                if position < archive_capacity:
                    archive[position] = expr.signature
            for bit in range(output_bits):
                if (expr.signature & training_mask) == wanted[bit]:
                    record = expr.record()
                    gates = len(compile_nor([record], input_bits)["gates"])
                    score = (gates, expr.operators, canonical(record))
                    if accepted[bit] is None or score < accepted[bit][0]:
                        accepted[bit] = (score, record)
                        selection_trace.append({"output_bit": bit, "candidate_number": evaluated,
                                                "nor_gates": gates, "operators": expr.operators,
                                                "novelty_distance": novelty, "probe_count": domain})
        by_cost[cost] = kept
        rounds.append({"operators": cost, "generated": generated, "unique_proposals": len(proposals),
                       "evaluated": len(kept), "archive_size_before": len(archive_before),
                       "proposal_generation_truncated": round_truncated,
                       "ranking": "descending_min_hamming_then_seeded_tie"})
        if budget_exhausted:
            break
    records = None if any(item is None for item in accepted) else [item[1] for item in accepted]
    receipt = {"generator": GENERATOR, "seed256": seed256, "grammar": ["input", "constant", "not", "and", "or", "xor"],
               "max_operators": max_operators, "candidate_budget": candidate_budget,
               "archive_capacity": archive_capacity, "probe_domain": "all_inputs_unlabelled",
               "proposal_budget_per_round": proposal_budget,
               "proposal_budget_exhausted": proposal_budget_exhausted,
               "probe_count": domain, "training_rows": len(training),
               "training_digest256": digest("atomOS:synthesis:training:v1", training),
               "evaluated_candidates": evaluated, "duplicate_behaviors_skipped": duplicates,
               "budget_exhausted": budget_exhausted, "rounds": rounds,
               "selection_trace": selection_trace, "status": "frozen" if records is not None else "no_training_fit",
               "frozen_expression_digest256": digest("atomOS:synthesis:frozen:v1", records) if records is not None else None}
    return records, receipt


def distill(data: dict, seed: str, *, max_operators: int = 3,
            candidate_budget: int = 12000, parent_digest256: str | None = None) -> tuple[list[dict], dict]:
    validate_examples(data)
    root_seed = seed_digest(seed)
    if parent_digest256 is not None and (len(parent_digest256) != 64 or
            any(c not in "0123456789abcdef" for c in parent_digest256)):
        raise ValueError("parent digest must be a lower-case full SHA-256 digest")
    packages, records = [], []
    for skill in data["skills"]:
        training = sorted(skill["train"], key=lambda row: row["input"])
        skill_seed = digest("atomOS:synthesis:skill-seed:v1", [root_seed, skill["name"], training])
        expressions, search = synthesize(training, data["input_bits"], data["output_bits"], skill_seed,
                                         max_operators=max_operators, candidate_budget=candidate_budget)
        result = {"name": skill["name"], "search": search, "audit_status": "not_run"}
        if expressions is not None:
            circuit = compile_nor(expressions, data["input_bits"])
            audits = {}
            for split in ("train", "holdout", "full_domain"):
                rows = skill.get(split, [])
                failures = []
                for row in rows:
                    actual = evaluate_circuit(circuit, row["input"])
                    scalar = sum(expression_value(e, row["input"]) << bit for bit, e in enumerate(expressions))
                    if actual != scalar:
                        raise ValueError("NOR lowering differs from independent scalar expression evaluator")
                    if actual != row["output"]:
                        failures.append({**row, "actual": actual})
                audits[split] = {"status": "not_run" if not rows else "failed" if failures else "passed",
                                 "rows": len(rows), "failures": failures,
                                 "labels_digest256": digest("atomOS:teacher:audit:v1", rows) if rows else None}
            result.update(expressions=expressions, circuit=circuit, audits=audits,
                          audit_status="failed" if any(v["status"] == "failed" for v in audits.values()) else "passed")
            if result["audit_status"] == "passed":
                package = {"name": skill["name"], "root_seed256": root_seed,
                           "skill_seed256": skill_seed, "parent_digest256": parent_digest256,
                           "generator": GENERATOR, "training": training, "expressions": expressions,
                           "circuit": circuit, "frozen_expression_digest256": search["frozen_expression_digest256"]}
                package["content_digest256"] = digest("atomOS:program-bank:skill:v1", package)
                packages.append(package)
        records.append(result)
    receipt = {"schema": "atomos-program-distillation-receipt-v1", "generator": GENERATOR,
               "root_seed256": root_seed, "seed_text": seed, "parent_digest256": parent_digest256,
               "teacher_dataset_digest256": digest("atomOS:teacher:dataset:v1", data),
               "input_bits": data["input_bits"], "output_bits": data["output_bits"],
               "status": "passed" if len(packages) == len(data["skills"]) else "incomplete",
               "accepted_skills": len(packages), "requested_skills": len(data["skills"]),
               "claim_scope": "finite structured Boolean skill distillation; not language-model replacement",
               "holdout_policy": "candidate frozen before audit labels; no reselection on audit failure",
               "skills": records}
    receipt["receipt_digest256"] = digest("atomOS:program-bank:learning-receipt:v1", receipt)
    return packages, receipt


def _hex_digest(value: Any, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"{name} must be a lower-case full SHA-256 digest")
    return value


def seed_origin(seed_hex: str, rows: int, angles: int) -> tuple[int, int]:
    raw = bytes.fromhex(_hex_digest(seed_hex, "seed_hex"))
    return ((int.from_bytes(raw[:16], "big") * rows) >> 128,
            (int.from_bytes(raw[16:], "big") * angles) >> 128)


def klein_cell(bit: int, origin_row: int, origin_angle: int,
               rows: int, angles: int) -> tuple[int, int]:
    row = (origin_row + bit // angles) % rows
    winding, angle = divmod(origin_angle + bit % angles, angles)
    return (rows - 1 - row if winding & 1 else row), angle


def page_digest(origin_row: int, origin_angle: int, words: list[int]) -> str:
    payload = struct.pack("<II", origin_row, origin_angle) + struct.pack(f"<{len(words)}I", *words)
    return hashlib.sha256(b"atomos-program-page-v1\0" + payload).hexdigest()


def _shape(rows: int, angles: int):
    _integer(rows, "rows", 2, 65536)
    _integer(angles, "angles", 32, 65536)
    padded_rows = ((rows + 7) // 8) * 8
    padded_words = (((angles // 32) + 7) // 8) * 8
    if angles % 32 or rows * angles < 1024 or padded_rows * padded_words > 1 << 20:
        raise ValueError("program page shape requires whole angular words, header capacity and bounded extent")


def encode_capsule(capsule: dict, *, rows: int, angles: int, program_id: int,
                   capsule_count: int, default_parent: str = "0" * 64) -> tuple[list[int], dict]:
    _shape(rows, angles)
    circuit = validate_circuit(capsule["circuit"])
    seed_hex = _hex_digest(capsule.get("seed_hex", capsule.get("skill_seed256")), "capsule seed")
    parent = capsule.get("parent_sha256", capsule.get("parent_digest256")) or default_parent
    parent = _hex_digest(parent, "parent_sha256")
    _integer(program_id, "program_id", 0, capsule_count - 1)
    version = _integer(capsule.get("version", 1), "version", 1, 0xffffffff)
    next_slot = _integer(capsule.get("next_slot", (program_id + 1) % capsule_count),
                         "next_slot", 0, capsule_count - 1)
    gates = circuit["gates"]
    if circuit["input_bits"] + 1 + len(gates) > 1024:
        raise ValueError("program page exceeds native 1024-wire limit")
    width = max(1, (circuit["input_bits"] + len(gates)).bit_length())
    bit_length = 1024 + (2 * len(gates) + circuit["output_bits"]) * width
    if bit_length > rows * angles:
        raise ValueError("compiled program exceeds declared page bit capacity")
    header = [PAGE_MAGIC, 1, circuit["input_bits"], circuit["output_bits"], len(gates), width,
              bit_length, program_id, version, next_slot, 1024, 0]
    header += list(struct.unpack("<8I", bytes.fromhex(seed_hex)))
    header += list(struct.unpack("<8I", bytes.fromhex(parent))) + [0] * 4
    logical = list(header) + [0] * (rows * (angles // 32) - 32)
    offset = 1024
    for reference in [v for gate in gates for v in gate] + circuit["outputs"]:
        for bit in range(width):
            logical[(offset + bit) // 32] |= ((reference >> bit) & 1) << ((offset + bit) % 32)
        offset += width
    origin_row, origin_angle = seed_origin(seed_hex, rows, angles)
    words = [0] * len(logical)
    for bit in range(rows * angles):
        row, angle = klein_cell(bit, origin_row, origin_angle, rows, angles)
        if (logical[bit // 32] >> (bit % 32)) & 1:
            words[row * (angles // 32) + angle // 32] |= 1 << (angle % 32)
    descriptor = {"id": program_id, "name": capsule.get("name", f"skill_{program_id}"),
                  "version": version, "next_slot": next_slot, "origin_row": origin_row,
                  "origin_angle": origin_angle, "seed_hex": seed_hex, "parent_sha256": parent,
                  "content_sha256": page_digest(origin_row, origin_angle, words),
                  "input_bits": circuit["input_bits"], "output_bits": circuit["output_bits"],
                  "gate_count": len(gates), "ref_width": width, "bit_length": bit_length}
    for key in ("root_seed256", "generator", "training", "expressions", "frozen_expression_digest256"):
        if key in capsule:
            descriptor[key] = capsule[key]
    return words, descriptor


def decode_capsule(words: list[int], *, rows: int, angles: int, origin_row: int,
                   origin_angle: int, capsule_count: int) -> dict:
    _shape(rows, angles)
    _integer(origin_row, "origin_row", 0, rows - 1)
    _integer(origin_angle, "origin_angle", 0, angles - 1)
    if len(words) != rows * (angles // 32):
        raise ValueError("program page word count differs from shape")
    for word in words:
        _integer(word, "packed word", 0, 0xffffffff)
    logical = [0] * len(words)
    for bit in range(rows * angles):
        row, angle = klein_cell(bit, origin_row, origin_angle, rows, angles)
        value = (words[row * (angles // 32) + angle // 32] >> (angle % 32)) & 1
        logical[bit // 32] |= value << (bit % 32)
    header = logical[:32]
    if header[0] != PAGE_MAGIC or header[1] != 1 or header[10] != 1024:
        raise ValueError("invalid program page header")
    if header[11] or any(header[28:32]):
        raise ValueError("nonzero reserved header fields")
    inputs = _integer(header[2], "input_bits", 1, 12)
    outputs = _integer(header[3], "output_bits", 1, 8)
    count = _integer(header[4], "gate_count", 0, 65535)
    if inputs + 1 + count > 1024:
        raise ValueError("program page exceeds native 1024-wire limit")
    width = max(1, (inputs + count).bit_length())
    length = 1024 + (2 * count + outputs) * width
    if header[5] != width or header[6] != length or length > rows * angles:
        raise ValueError("noncanonical reference width or program length")
    program_id = _integer(header[7], "program_id", 0, capsule_count - 1)
    version = _integer(header[8], "version", 1, 0xffffffff)
    next_slot = _integer(header[9], "next_slot", 0, capsule_count - 1)
    seed_hex = struct.pack("<8I", *header[12:20]).hex()
    parent = struct.pack("<8I", *header[20:28]).hex()
    if seed_origin(seed_hex, rows, angles) != (origin_row, origin_angle):
        raise ValueError("seed digest does not reconstruct declared origins")
    for bit in range(length, rows * angles):
        if (logical[bit // 32] >> (bit % 32)) & 1:
            raise ValueError("nonzero unused program tail")
    offset = 1024
    refs = []
    for _ in range(2 * count + outputs):
        reference = sum(((logical[(offset + bit) // 32] >> ((offset + bit) % 32)) & 1) << bit
                        for bit in range(width))
        refs.append(reference)
        offset += width
    circuit = {"input_bits": inputs, "output_bits": outputs, "constant_zero_wire": inputs,
               "gates": [refs[2 * i:2 * i + 2] for i in range(count)], "outputs": refs[2 * count:]}
    validate_circuit(circuit)
    return {"id": program_id, "version": version, "next_slot": next_slot,
            "origin_row": origin_row, "origin_angle": origin_angle, "seed_hex": seed_hex,
            "parent_sha256": parent, "content_sha256": page_digest(origin_row, origin_angle, words),
            "input_bits": inputs, "output_bits": outputs, "gate_count": count,
            "ref_width": width, "bit_length": length, "circuit": circuit}


def write_bank(path: Path, capsules: list[dict], *, master_seed_hex: str,
               rows: int = 8, angles: int = 256) -> dict:
    """Write the shared native ABI plus manifest.json; returns that manifest."""
    path = Path(path)
    if path.exists() or (path.parent / "manifest.json").exists():
        raise ValueError("refusing to overwrite an existing bank or manifest")
    _shape(rows, angles)
    _hex_digest(master_seed_hex, "master_seed_hex")
    _integer(len(capsules), "capsule_count", 1, 65536)
    payload = bytearray(BANK_MAGIC + struct.pack("<IIII", 1, rows, angles, len(capsules)) + bytes.fromhex(master_seed_hex))
    descriptors = []
    parent = "0" * 64
    for index, capsule in enumerate(capsules):
        words, descriptor = encode_capsule(capsule, rows=rows, angles=angles, program_id=index,
                                            capsule_count=len(capsules), default_parent=parent)
        decoded = decode_capsule(words, rows=rows, angles=angles,
                                  origin_row=descriptor["origin_row"], origin_angle=descriptor["origin_angle"],
                                  capsule_count=len(capsules))
        if decoded["circuit"] != capsule["circuit"] or any(
                descriptor.get(key) != value for key, value in decoded.items() if key != "circuit"):
            raise ValueError("packed candidate does not verify before publication")
        payload.extend(struct.pack("<II", descriptor["origin_row"], descriptor["origin_angle"]))
        payload.extend(struct.pack(f"<{len(words)}I", *words))
        descriptors.append(descriptor)
        parent = descriptor["content_sha256"]
    manifest = {"schema": "atomos-program-lut-bank-v1", "bank_file_sha256": hashlib.sha256(payload).hexdigest(),
                "rows": rows, "angles": angles, "capsule_count": len(capsules),
                "master_seed_hex": master_seed_hex, "capsules": descriptors,
                "logical_representation": "one-bit cells packed in canonical little-endian uint32 words",
                "coordinate_profile": "log-radius rows, angular nodes, SHA256 origin, reflected Klein angular seam",
                "seed_role": "versioned generation/order and origin; retained payload required for arbitrary content"}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    (path.parent / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    load_bank(path)
    return manifest


def load_bank(path: Path, manifest_path: Path | None = None) -> dict:
    path = Path(path)
    raw = path.read_bytes()
    if len(raw) < 56 or raw[:8] != BANK_MAGIC:
        raise ValueError("invalid bank magic or truncated bank header")
    version, rows, angles, count = struct.unpack_from("<IIII", raw, 8)
    if version != 1:
        raise ValueError("unsupported bank ABI version")
    _shape(rows, angles)
    _integer(count, "capsule_count", 1, 65536)
    size = rows * (angles // 32)
    if len(raw) != 56 + count * (8 + size * 4):
        raise ValueError("bank byte count does not match declared shape/count")
    manifest_file = Path(manifest_path) if manifest_path is not None else path.parent / "manifest.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8")) if manifest_file.exists() else None
    if manifest is not None:
        if manifest.get("schema") != "atomos-program-lut-bank-v1" or manifest.get("bank_file_sha256") != hashlib.sha256(raw).hexdigest():
            raise ValueError("bank manifest schema or file digest mismatch")
        for key, actual in (("rows", rows), ("angles", angles), ("capsule_count", count), ("master_seed_hex", raw[24:56].hex())):
            if manifest.get(key) != actual:
                raise ValueError(f"manifest {key} differs from bank")
        if len(manifest.get("capsules", [])) != count:
            raise ValueError("manifest capsule count differs")
    capsules = []
    offset = 56
    for index in range(count):
        origin_row, origin_angle = struct.unpack_from("<II", raw, offset)
        words = list(struct.unpack_from(f"<{size}I", raw, offset + 8))
        capsule = decode_capsule(words, rows=rows, angles=angles, origin_row=origin_row,
                                  origin_angle=origin_angle, capsule_count=count)
        if capsule["id"] != index:
            raise ValueError("capsule program id does not match bank slot")
        if manifest is not None:
            record = manifest["capsules"][index]
            for key, actual in capsule.items():
                if key != "circuit" and record.get(key) != actual:
                    raise ValueError(f"manifest capsule {index} {key} differs from decoded page")
            capsule.update({key: value for key, value in record.items() if key not in capsule})
        capsule["words"] = words
        capsules.append(capsule)
        offset += 8 + size * 4
    return {"schema": "atomos-program-lut-bank-v1", "rows": rows, "angles": angles,
            "capsule_count": count, "master_seed_hex": raw[24:56].hex(), "capsules": capsules,
            "bank_file_sha256": hashlib.sha256(raw).hexdigest(), "manifest_verified": manifest is not None}
