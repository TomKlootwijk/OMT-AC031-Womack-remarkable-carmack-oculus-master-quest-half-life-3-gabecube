"""Compile literal TOMAGI JSON into the portable .tmg binary.

The module preserves the original TOMAGI 1.0 handwritten-cell format and adds
the finite, domain-neutral seeded-definition operations required to derive
artifacts from literal JSON sources.  The binary ABI remains unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import base64
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from .canonical import canonical_bytes, verify_hash
from .core import (
    Cell,
    FLAG_EMIT_BIG_ENDIAN,
    FLAG_EMIT_COUNT_SHIFT,
    FLAG_EMIT_HALT,
    OPCODE_BY_NAME,
    Opcode,
    Program,
    PROGRAM_FLAG_EMIT_BYTES,
    PROGRAM_FLAG_SEEDED_PROFILE,
    PHI_STATES,
    RHO_STATES,
    State,
    THETA_STATES,
    TIME_STATES,
    i32,
    key_as_u64,
    pack_key_contiguous,
    u32,
)
from .format import dump, dumps, load
from .formal import Limits as FormalLimits, run_program as run_formal_program

CANONICAL_SEED_LENGTH = 244
CANONICAL_SEED_SHA256 = "d1417a3136772c0cf3eddcd4962ce07d42cbf87616f7b5bae09fc652d9b807b5"
SEEDED_PROFILE_ID = "TOM-SEEDED-COMPILATION-1.0"
SEED_GRAMMAR_ID = "TOM-SEED-GRAMMAR-1.0"
TOKEN_REGISTRY_ID = "TOM-SEED-TOKEN-REGISTRY-1.0"
CANONICAL_TOKEN_REGISTRY_CONTENT_HASH = (
    "sha256:d330f7cc3ba5bff2f2e0eb05e32847c295b69e328ed0852fd612b716819044bb"
)
PHASE_ORDER = (
    "parse", "normalize", "resolve", "construct", "transform", "support",
    "compatibility", "guard", "event", "transition", "lineage",
)

BUDGET_NAMES = (
    "max_definitions",
    "max_cells",
    "max_output_bytes",
    "max_sequence_items",
    "max_repeat",
    "max_expression_depth",
    "max_expression_nodes",
    "max_string_bytes",
)
SUPPORTED_SEEDED_OPERATIONS = {
    "seed.bytes",
    "seed.tokens",
    "literal",
    "state64.construct",
    "hash.sha256",
    "assert.equal",
    "emit.graph",
    "program.construct",
    "source.json",
    "sequence.construct",
    "formal.evaluate",
    "canonical.encode",
}
SEEDED_DOCUMENT_FIELDS = {
    "$schema", "tomagi_version", "compilation_profile", "title",
    "seed_genome", "root_definition", "budgets", "definitions",
}
SEEDED_DEFINITION_FIELDS = {
    "id", "kind", "domain", "codomain", "dependencies", "phase", "order",
    "operation", "parameters", "limits", "provenance", "seed_tokens",
    "content_hash",
}
DOMAIN_SIGNATURES: Mapping[str, tuple[str, ...]] = {
    "none": (),
    "bytes": ("bytes",),
    "seed-record": ("record",),
    "hash-pair": ("string", "string"),
    "state-graph-guard": ("state64", "cell_graph", "bool"),
    "record-sequence": (),  # Variable arity; checked by _validate_operation_contract.
    "formal-program-sequence": ("record", "sequence"),
    "record": ("record",),
}
OPERATION_KINDS = {
    "seed.bytes": "canonical-seed",
    "seed.tokens": "seed-parse",
    "state64.construct": "initial-state",
    "hash.sha256": "computed-hash",
    "assert.equal": "hash-guard",
    "emit.graph": "byte-emission",
    "program.construct": "artifact-program",
    "source.json": "literal-json-source",
    "sequence.construct": "record-sequence",
    "formal.evaluate": "formal-evaluation",
    "canonical.encode": "canonical-encoding",
}
OPERATION_CODOMAINS = {
    "seed.bytes": "bytes",
    "seed.tokens": "record",
    "state64.construct": "state64",
    "hash.sha256": "string",
    "assert.equal": "bool",
    "emit.graph": "cell_graph",
    "program.construct": "program",
    "source.json": "record",
    "sequence.construct": "sequence",
    "formal.evaluate": "record",
    "canonical.encode": "bytes",
}
OPERATION_DOMAINS = {
    "seed.bytes": "none",
    "seed.tokens": "bytes",
    "state64.construct": "seed-record",
    "hash.sha256": "bytes",
    "assert.equal": "hash-pair",
    "emit.graph": "bytes",
    "program.construct": "state-graph-guard",
    "source.json": "seed-record",
    "sequence.construct": "record-sequence",
    "formal.evaluate": "formal-program-sequence",
    "canonical.encode": "record",
}
OPERATION_PARAMETER_FIELDS: Mapping[str, tuple[frozenset[str], frozenset[str]]] = {
    "seed.bytes": (frozenset(), frozenset()),
    "seed.tokens": (frozenset(), frozenset()),
    "literal": (
        frozenset({"result_type", "value"}),
        frozenset({"result_type", "value"}),
    ),
    "state64.construct": (frozenset({"fields"}), frozenset({"fields"})),
    "hash.sha256": (frozenset(), frozenset({"prefix"})),
    "assert.equal": (frozenset(), frozenset()),
    "emit.graph": (
        frozenset(),
        frozenset({
            "chunk_bytes", "byte_order", "id_prefix", "key_base", "key_field",
            "aux_base", "halt_last",
        }),
    ),
    "program.construct": (
        frozenset(),
        frozenset({"entry", "flags", "seed", "default_ticks", "emit_bytes"}),
    ),
    "source.json": (
        frozenset({
            "path", "bytes", "sha256", "canonical_newline", "verify_content_hash",
        }),
        frozenset({
            "path", "bytes", "sha256", "canonical_newline", "verify_content_hash",
        }),
    ),
    "sequence.construct": (frozenset(), frozenset()),
    "formal.evaluate": (frozenset({"input_name"}), frozenset({"input_name"})),
    "canonical.encode": (
        frozenset({"terminal_newline"}), frozenset({"terminal_newline"}),
    ),
}
SEED_TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_]*")


def _int(value: Any) -> int:
    if isinstance(value, bool):
        raise TypeError("boolean is not a TOMAGI integer")
    if isinstance(value, str):
        return int(value, 0)
    if isinstance(value, int):
        return value
    raise TypeError(f"TOMAGI integer must be an integer or integer string, found {type(value).__name__}")


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _strict_json_loads(text: str, *, label: str) -> Any:
    def reject_constant(value: str) -> None:
        raise ValueError(f"{label} contains non-finite JSON number {value}")

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"{label} contains duplicate object key {key!r}")
            result[key] = value
        return result

    return json.loads(
        text,
        parse_constant=reject_constant,
        object_pairs_hook=reject_duplicate_keys,
    )


def _expect_mapping_keys(
    value: Mapping[str, Any],
    *,
    required: set[str],
    allowed: set[str],
    label: str,
) -> None:
    missing = sorted(required - set(value))
    if missing:
        raise ValueError(f"{label} is missing required fields: {', '.join(missing)}")
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"{label} has unknown fields: {', '.join(unknown)}")


def _positive_int(value: Any, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _u32_value(value: Any, *, label: str) -> int:
    parsed = _int(value)
    if not 0 <= parsed <= 0xFFFFFFFF:
        raise ValueError(f"{label} must be in the u32 range")
    return parsed


def _bounded_string(value: Any, *, label: str, max_bytes: int) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    if len(value.encode("utf-8")) > max_bytes:
        raise ValueError(f"{label} exceeds max_string_bytes")
    return value


def _tree_metrics(value: Any) -> tuple[int, int, int]:
    """Return node count, maximum depth, and largest collection length."""
    if isinstance(value, Mapping):
        children = list(value.values())
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        children = list(value)
    else:
        return 1, 1, 0
    if not children:
        return 1, 1, 0
    metrics = [_tree_metrics(child) for child in children]
    return (
        1 + sum(item[0] for item in metrics),
        1 + max(item[1] for item in metrics),
        max(len(children), *(item[2] for item in metrics)),
    )


def _validate_tree_budget(value: Any, budgets: Mapping[str, int], *, label: str) -> None:
    nodes, depth, sequence = _tree_metrics(value)
    if nodes > budgets["max_expression_nodes"]:
        raise ValueError(f"{label} exceeds max_expression_nodes")
    if depth > budgets["max_expression_depth"]:
        raise ValueError(f"{label} exceeds max_expression_depth")
    if sequence > budgets["max_sequence_items"]:
        raise ValueError(f"{label} exceeds max_sequence_items")


def _validate_string_tree(value: Any, *, max_bytes: int, label: str) -> None:
    if isinstance(value, str):
        if len(value.encode("utf-8")) > max_bytes:
            raise ValueError(f"{label} contains a string exceeding max_string_bytes")
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{label} contains a non-string mapping key")
            if len(key.encode("utf-8")) > max_bytes:
                raise ValueError(f"{label} contains a key exceeding max_string_bytes")
            _validate_string_tree(child, max_bytes=max_bytes, label=label)
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        for child in value:
            _validate_string_tree(child, max_bytes=max_bytes, label=label)


def _validate_budgets(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        raise ValueError("budgets must be an object")
    _expect_mapping_keys(
        value,
        required=set(BUDGET_NAMES),
        allowed=set(BUDGET_NAMES),
        label="budgets",
    )
    budgets = {
        name: _positive_int(value[name], label=f"budgets.{name}")
        for name in BUDGET_NAMES
    }
    return budgets


def _effective_limits(
    definition: Mapping[str, Any],
    budgets: Mapping[str, int],
) -> dict[str, int]:
    raw = definition["limits"]
    if not isinstance(raw, Mapping):
        raise ValueError(f"definition {definition['id']} limits must be an object")
    unknown = sorted(set(raw) - set(BUDGET_NAMES))
    if unknown:
        raise ValueError(
            f"definition {definition['id']} has unknown limits: {', '.join(unknown)}"
        )
    result = dict(budgets)
    for name, value in raw.items():
        limit = _positive_int(value, label=f"definition {definition['id']} limits.{name}")
        if limit > budgets[name]:
            raise ValueError(f"definition {definition['id']} limit {name} exceeds document budget")
        result[name] = limit
    return result


def _validate_seed_genome_record(document: Mapping[str, Any]) -> Mapping[str, Any]:
    seed_info = document.get("seed_genome")
    if not isinstance(seed_info, Mapping):
        raise ValueError("seeded source requires seed_genome")
    fields = {"path", "bytes", "sha256", "grammar_id", "token_registry"}
    _expect_mapping_keys(seed_info, required=fields, allowed=fields, label="seed_genome")
    if not isinstance(seed_info["path"], str) or not seed_info["path"]:
        raise ValueError("seed_genome.path must be a non-empty string")
    if not isinstance(seed_info["token_registry"], str) or not seed_info["token_registry"]:
        raise ValueError("seed_genome.token_registry must be a non-empty string")
    if isinstance(seed_info["bytes"], bool) or seed_info["bytes"] != CANONICAL_SEED_LENGTH:
        raise ValueError("seed_genome declared byte length mismatch")
    if seed_info["sha256"] != CANONICAL_SEED_SHA256:
        raise ValueError("seed_genome declared hash mismatch")
    if seed_info["grammar_id"] != SEED_GRAMMAR_ID:
        raise ValueError(f"seed_genome.grammar_id must be {SEED_GRAMMAR_ID}")
    return seed_info


def _validate_token_registry(
    registry: Mapping[str, Any] | None,
    *,
    seed_text: str,
) -> frozenset[str]:
    if not isinstance(registry, Mapping):
        raise ValueError("seeded compilation requires the canonical token registry")
    fields = {"content_hash", "grammar_id", "purpose", "registry_id", "seed_sha256", "tokens"}
    _expect_mapping_keys(registry, required=fields, allowed=fields, label="token registry")
    try:
        canonical_bytes(registry)
    except (TypeError, ValueError) as exc:
        raise ValueError("token registry is not canonical finite JSON") from exc
    if not verify_hash(dict(registry)):
        raise ValueError("token registry content hash mismatch")
    if registry["content_hash"] != CANONICAL_TOKEN_REGISTRY_CONTENT_HASH:
        raise ValueError("token registry is not the canonical TOM seed token registry")
    if registry["registry_id"] != TOKEN_REGISTRY_ID:
        raise ValueError(f"token registry ID must be {TOKEN_REGISTRY_ID}")
    if registry["grammar_id"] != SEED_GRAMMAR_ID:
        raise ValueError(f"token registry grammar_id must be {SEED_GRAMMAR_ID}")
    if registry["seed_sha256"] != CANONICAL_SEED_SHA256:
        raise ValueError("token registry seed hash mismatch")
    if not isinstance(registry["purpose"], str) or not registry["purpose"]:
        raise ValueError("token registry purpose must be a non-empty string")
    raw_tokens = registry["tokens"]
    if not isinstance(raw_tokens, list) or not raw_tokens:
        raise ValueError("token registry tokens must be a non-empty array")
    lexical_tokens = set(SEED_TOKEN_PATTERN.findall(seed_text))
    registered: list[str] = []
    for index, record in enumerate(raw_tokens):
        if not isinstance(record, Mapping):
            raise ValueError(f"token registry entry {index} must be an object")
        entry_fields = {"token", "present_in_seed"}
        _expect_mapping_keys(
            record, required=entry_fields, allowed=entry_fields,
            label=f"token registry entry {index}",
        )
        token = record["token"]
        if not isinstance(token, str) or not token:
            raise ValueError(f"token registry entry {index} has an invalid token")
        if record["present_in_seed"] is not True:
            raise ValueError(f"token registry token {token!r} is not declared present")
        if token not in lexical_tokens:
            raise ValueError(f"token registry token {token!r} is not an exact seed token")
        if token in registered:
            raise ValueError(f"duplicate token registry token {token!r}")
        registered.append(token)
    return frozenset(registered)


def _key_from_json(value: Any) -> tuple[int, int]:
    if isinstance(value, str):
        word = int(value, 0)
        return (word >> 32) & 0xFFFFFFFF, word & 0xFFFFFFFF
    if isinstance(value, int):
        return (value >> 32) & 0xFFFFFFFF, value & 0xFFFFFFFF
    if isinstance(value, dict):
        return pack_key_contiguous(
            _int(value.get("rho", 0)), _int(value.get("theta", 0)),
            _int(value.get("tick", 0)), _int(value.get("phi", 0)),
        )
    raise TypeError("cell key must be an integer, hex string, or rho/theta/tick/phi object")


def _state_from_json(value: Mapping[str, Any]) -> State:
    unknown = sorted(set(value) - set(State.__dataclass_fields__))
    if unknown:
        raise ValueError("unknown State64 fields: " + ", ".join(unknown))
    signed = {
        "rho", "theta", "tick", "phi", "vrho", "vtheta", "vtick", "vphi",
        "residual",
    }
    fields = {
        name: i32(_int(value.get(name, 0))) if name in signed
        else u32(_int(value.get(name, 0)))
        for name in State.__dataclass_fields__
    }
    return State(**fields)


def definition_order(definitions: list[dict[str, Any]]) -> list[str]:
    """Return a stable topological order for literal definition records."""
    by_id: dict[str, dict[str, Any]] = {}
    input_rank: dict[str, int] = {}
    for rank, definition in enumerate(definitions):
        ident = str(definition["id"])
        if ident in by_id:
            raise ValueError(f"duplicate definition id {ident}")
        by_id[ident] = definition
        input_rank[ident] = rank
        if "content_hash" in definition and not verify_hash(definition):
            raise ValueError(f"definition hash mismatch: {ident}")

    indegree = {ident: 0 for ident in by_id}
    children: dict[str, list[str]] = {ident: [] for ident in by_id}
    for ident, definition in by_id.items():
        seen: set[str] = set()
        for dep_value in definition.get("dependencies", []):
            dep = str(dep_value)
            if dep not in by_id:
                raise ValueError(f"unknown dependency {dep} from {ident}")
            if dep in seen:
                raise ValueError(f"duplicate dependency {dep} from {ident}")
            seen.add(dep)
            indegree[ident] += 1
            children[dep].append(ident)

    ready = sorted((input_rank[i], i) for i, degree in indegree.items() if degree == 0)
    order: list[str] = []
    while ready:
        _, ident = ready.pop(0)
        order.append(ident)
        for child in sorted(children[ident], key=input_rank.__getitem__):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append((input_rank[child], child))
                ready.sort()
    if len(order) != len(by_id):
        cyclic = sorted(ident for ident, degree in indegree.items() if degree > 0)
        raise ValueError("definition dependency cycle: " + ", ".join(cyclic))
    return order


def _compile_legacy_document(document: Mapping[str, Any]) -> Program:
    if document.get("tomagi_version") != "1.0.0":
        raise ValueError("tomagi_version must be 1.0.0")

    definitions = document.get("definitions", [])
    if not isinstance(definitions, list):
        raise ValueError("definitions must be an array")
    definition_order(definitions)
    ids = {str(d["id"]) for d in definitions}

    raw_cells = document.get("cells", [])
    if not raw_cells:
        raise ValueError("program requires cells")
    prepared: list[dict[str, Any]] = []
    for index, c in enumerate(raw_cells):
        ident = str(c.get("id", f"cell:{index}"))
        if c.get("definition_ref") and c["definition_ref"] not in ids:
            raise ValueError(f"cell {ident} references unknown definition {c['definition_ref']}")
        hi, lo = _key_from_json(c["key"])
        op_value = c["op"]
        if isinstance(op_value, str):
            try:
                opcode = int(OPCODE_BY_NAME[op_value.upper()])
            except KeyError as exc:
                raise ValueError(f"unknown opcode {op_value}") from exc
        else:
            opcode = int(Opcode(_int(op_value)))
        args = list(c.get("args", [0, 0, 0, 0]))
        if len(args) != 4:
            raise ValueError(f"cell {ident} requires four args")
        nxt = list(c.get("next", [ident, ident]))
        if len(nxt) != 2:
            raise ValueError(f"cell {ident} requires two successor IDs")
        prepared.append({
            "id": ident, "key_hi": hi, "key_lo": lo, "opcode": opcode,
            "flags": u32(_int(c.get("flags", 0))),
            "args": [i32(_int(x)) for x in args],
            "next_ids": [str(nxt[0]), str(nxt[1])],
            "payload": u32(_int(c.get("payload", 0))),
            "aux": u32(_int(c.get("aux", 0))),
        })

    prepared.sort(key=lambda c: key_as_u64(c["key_hi"], c["key_lo"]))
    index_by_id = {c["id"]: i for i, c in enumerate(prepared)}
    if len(index_by_id) != len(prepared):
        raise ValueError("cell IDs must be unique")
    for c in prepared:
        for target in c["next_ids"]:
            if target not in index_by_id:
                raise ValueError(f"cell {c['id']} references unknown successor {target}")

    cells = [
        Cell(
            c["key_hi"], c["key_lo"], c["opcode"], c["flags"],
            c["args"][0], c["args"][1], c["args"][2], c["args"][3],
            index_by_id[c["next_ids"][0]], index_by_id[c["next_ids"][1]],
            c["payload"], c["aux"],
        )
        for c in prepared
    ]
    entry_id = str(document.get("entry", prepared[0]["id"]))
    if entry_id not in index_by_id:
        raise ValueError(f"entry cell {entry_id} does not exist")
    state = _state_from_json(document.get("initial_state", {}))
    state.cell = index_by_id[entry_id]
    return Program(
        cells=cells,
        entry=index_by_id[entry_id],
        seed=u32(_int(document.get("seed", 0))),
        default_ticks=_u32_value(
            document.get("default_ticks", len(cells)), label="default_ticks"
        ),
        initial_state=state,
        flags=u32(_int(document.get("flags", 0))),
    )


@dataclass(frozen=True, slots=True)
class _Typed:
    type_name: str
    value: Any


@dataclass(frozen=True, slots=True)
class _CellSpec:
    ident: str
    key_hi: int
    key_lo: int
    opcode: int
    flags: int
    args: tuple[int, int, int, int]
    next_ids: tuple[str, str]
    payload: int
    aux: int
    source_definition: str
    origin: Mapping[str, Any]

    @property
    def key(self) -> int:
        return key_as_u64(self.key_hi, self.key_lo)


@dataclass(frozen=True, slots=True)
class _Graph:
    cells: tuple[_CellSpec, ...]
    entry_id: str


@dataclass(frozen=True, slots=True)
class _ProgramSpec:
    graph: _Graph
    state: State
    entry_id: str
    seed: int
    default_ticks: int
    flags: int


@dataclass(frozen=True, slots=True)
class SeededCompilationResult:
    program: Program
    definition_order: tuple[str, ...]
    crosswalk: tuple[Mapping[str, Any], ...]
    report: Mapping[str, Any]


def _decode_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    if not isinstance(value, Mapping):
        raise TypeError("bytes literal must be a string or encoding object")
    encoding = str(value.get("encoding", "utf8")).lower()
    data = value.get("data", "")
    if not isinstance(data, str):
        raise TypeError("encoded bytes data must be a string")
    if encoding in {"utf8", "utf-8"}:
        return data.encode("utf-8")
    if encoding == "ascii":
        return data.encode("ascii")
    if encoding == "hex":
        return bytes.fromhex(data)
    if encoding == "base64":
        return base64.b64decode(data, validate=True)
    raise ValueError(f"unsupported bytes encoding {encoding}")


def _validate_seed(seed: bytes) -> str:
    if seed.endswith((b"\n", b"\r")):
        raise ValueError("canonical seed must not have a terminal line ending")
    try:
        text = seed.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError("canonical seed must be ASCII") from exc
    digest = hashlib.sha256(seed).hexdigest()
    if len(seed) != CANONICAL_SEED_LENGTH:
        raise ValueError("canonical seed length mismatch")
    if digest != CANONICAL_SEED_SHA256:
        raise ValueError("canonical seed hash mismatch")
    return text


def _parsed_seed_record(seed_bytes: bytes, seed_text: str) -> dict[str, Any]:
    return {
        "grammar_id": SEED_GRAMMAR_ID,
        "bytes": len(seed_bytes),
        "sha256": hashlib.sha256(seed_bytes).hexdigest(),
        "text": seed_text,
    }


def _resolve_literal_source(
    source_root: str | Path | None,
    relative_path: str,
) -> tuple[Path, str]:
    if source_root is None:
        raise ValueError("source.json requires an explicit source_root")
    root = Path(source_root).resolve()
    if not root.is_dir():
        raise ValueError("source_root must name an existing directory")
    requested = Path(relative_path)
    if requested.is_absolute():
        raise ValueError("source.json path must be relative to source_root")
    try:
        resolved = (root / requested).resolve(strict=True)
        normalized = resolved.relative_to(root).as_posix()
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise ValueError("source.json path is missing or escapes source_root") from exc
    if not resolved.is_file():
        raise ValueError("source.json path must name a regular file")
    return resolved, normalized


def _validate_seeded_document_shape(document: Mapping[str, Any]) -> dict[str, int]:
    _expect_mapping_keys(
        document,
        required={
            "tomagi_version", "compilation_profile", "seed_genome",
            "root_definition", "budgets", "definitions",
        },
        allowed=SEEDED_DOCUMENT_FIELDS,
        label="seeded source",
    )
    try:
        canonical_bytes(document)
    except (TypeError, ValueError) as exc:
        raise ValueError("seeded source is not canonical finite JSON") from exc
    if document["tomagi_version"] != "1.0.0":
        raise ValueError("tomagi_version must be 1.0.0")
    if document["compilation_profile"] != SEEDED_PROFILE_ID:
        raise ValueError(f"compilation_profile must be {SEEDED_PROFILE_ID}")
    schema_uri = document.get("$schema")
    if schema_uri is not None and (not isinstance(schema_uri, str) or not schema_uri):
        raise ValueError("$schema must be a non-empty string when present")
    title = document.get("title")
    if title is not None and (not isinstance(title, str) or not title):
        raise ValueError("title must be a non-empty string when present")
    root = document["root_definition"]
    if not isinstance(root, str) or not root:
        raise ValueError("root_definition must be a non-empty string")
    seed_info = _validate_seed_genome_record(document)
    budgets = _validate_budgets(document["budgets"])
    _bounded_string(
        seed_info["path"], label="seed_genome.path",
        max_bytes=budgets["max_string_bytes"],
    )
    _bounded_string(
        seed_info["token_registry"], label="seed_genome.token_registry",
        max_bytes=budgets["max_string_bytes"],
    )
    _bounded_string(
        root, label="root_definition", max_bytes=budgets["max_string_bytes"]
    )
    if title is not None:
        _bounded_string(title, label="title", max_bytes=budgets["max_string_bytes"])
    definitions = document["definitions"]
    if not isinstance(definitions, list) or not definitions:
        raise ValueError("seeded program requires definitions")
    if len(definitions) > budgets["max_definitions"]:
        raise ValueError("definition count exceeds budgets.max_definitions")
    return budgets


def _validate_operation_parameter_shape(
    definition: Mapping[str, Any],
    limits: Mapping[str, int],
) -> None:
    """Validate parameter syntax even when a definition is outside the root closure."""
    ident = definition["id"]
    op = definition["operation"]["op"]
    params = definition["parameters"]
    if op == "literal":
        result_type = params["result_type"]
        value = params["value"]
        if result_type == "bytes":
            if isinstance(value, Mapping):
                _expect_mapping_keys(
                    value,
                    required={"encoding", "data"},
                    allowed={"encoding", "data"},
                    label=f"definition {ident} bytes literal",
                )
                encoding = value["encoding"]
                data = value["data"]
                if not isinstance(encoding, str) or encoding.lower() not in {
                    "utf8", "utf-8", "ascii", "hex", "base64",
                }:
                    raise ValueError(f"definition {ident} has an unsupported bytes encoding")
                if not isinstance(data, str):
                    raise TypeError(f"definition {ident} encoded bytes data must be a string")
            elif not isinstance(value, str):
                raise TypeError(f"definition {ident} bytes literal has an invalid value")
        elif result_type == "string" and not isinstance(value, str):
            raise TypeError(f"definition {ident} string literal must be a string")
        elif result_type == "bool" and not isinstance(value, bool):
            raise TypeError(f"definition {ident} bool literal must be true or false")
        elif result_type in {"i32", "u32"}:
            _int(value)
        elif result_type == "record" and not isinstance(value, Mapping):
            raise TypeError(f"definition {ident} record literal must be an object")
    elif op == "source.json":
        _bounded_string(
            params["path"], label=f"definition {ident} source.json path",
            max_bytes=limits["max_string_bytes"],
        )
        declared_bytes = params["bytes"]
        if (
            isinstance(declared_bytes, bool)
            or not isinstance(declared_bytes, int)
            or declared_bytes < 0
        ):
            raise TypeError(f"definition {ident} source.json bytes must be a non-negative integer")
        if not isinstance(params["sha256"], str) or not re.fullmatch(
            r"sha256:[0-9a-f]{64}", params["sha256"]
        ):
            raise ValueError(f"definition {ident} source.json sha256 is invalid")
        for name in ("canonical_newline", "verify_content_hash"):
            if not isinstance(params[name], bool):
                raise TypeError(f"definition {ident} source.json {name} must be boolean")
    elif op == "formal.evaluate":
        _bounded_string(
            params["input_name"], label=f"definition {ident} formal input_name",
            max_bytes=limits["max_string_bytes"],
        )
    elif op == "canonical.encode":
        if not isinstance(params["terminal_newline"], bool):
            raise TypeError(f"definition {ident} terminal_newline must be boolean")
    elif op == "state64.construct":
        if not isinstance(params["fields"], Mapping):
            raise TypeError(f"definition {ident} State64 fields must be an object")
        _state_from_json(params["fields"])
    elif op == "hash.sha256":
        if "prefix" in params and not isinstance(params["prefix"], bool):
            raise TypeError(f"definition {ident} hash prefix must be boolean")
    elif op == "emit.graph":
        chunk_size = _int(params.get("chunk_bytes", 4))
        if not 1 <= chunk_size <= 4:
            raise ValueError(f"definition {ident} chunk_bytes must be in 1..4")
        if params.get("byte_order", "little") not in {"little", "big"}:
            raise ValueError(f"definition {ident} byte_order must be little or big")
        _bounded_string(
            params.get("id_prefix", "cell:emit"),
            label=f"definition {ident} id_prefix",
            max_bytes=limits["max_string_bytes"],
        )
        base = params.get("key_base", {})
        if not isinstance(base, Mapping):
            raise TypeError(f"definition {ident} key_base must be an object")
        unknown_coords = sorted(set(base) - {"rho", "theta", "tick", "phi"})
        if unknown_coords:
            raise ValueError(
                f"definition {ident} key_base has unknown coordinates: "
                + ", ".join(unknown_coords)
            )
        for value in base.values():
            _int(value)
        if params.get("key_field", "rho") not in {"rho", "theta", "tick", "phi"}:
            raise ValueError(f"definition {ident} key_field is invalid")
        aux_base = _int(params.get("aux_base", 0))
        if not 0 <= aux_base <= 0xFFFFFFFF:
            raise ValueError(f"definition {ident} aux_base exceeds u32")
        if not isinstance(params.get("halt_last", True), bool):
            raise TypeError(f"definition {ident} halt_last must be boolean")
    elif op == "program.construct":
        if "entry" in params:
            _bounded_string(
                params["entry"], label=f"definition {ident} entry",
                max_bytes=limits["max_string_bytes"],
            )
        u32(_int(params.get("flags", 0)))
        u32(_int(params.get("seed", 0)))
        _u32_value(
            params.get("default_ticks", 0),
            label=f"definition {ident} default_ticks",
        )
        if not isinstance(params.get("emit_bytes", False), bool):
            raise TypeError(f"definition {ident} emit_bytes must be boolean")


def _validate_definition_shape(
    definition: Mapping[str, Any],
    *,
    budgets: Mapping[str, int],
    registered_tokens: frozenset[str],
) -> None:
    required = {
        "id", "kind", "domain", "codomain", "dependencies", "phase", "order",
        "operation", "parameters", "limits", "provenance", "content_hash",
    }
    _expect_mapping_keys(
        definition,
        required=required,
        allowed=SEEDED_DEFINITION_FIELDS,
        label="seeded definition",
    )
    ident = _bounded_string(
        definition["id"], label="definition.id", max_bytes=budgets["max_string_bytes"]
    )
    limits = _effective_limits(definition, budgets)
    _bounded_string(
        ident, label="definition.id", max_bytes=limits["max_string_bytes"]
    )
    kind = _bounded_string(
        definition["kind"], label=f"definition {ident} kind",
        max_bytes=limits["max_string_bytes"],
    )
    domain = _bounded_string(
        definition["domain"], label=f"definition {ident} domain",
        max_bytes=limits["max_string_bytes"],
    )
    codomain = _bounded_string(
        definition["codomain"], label=f"definition {ident} codomain",
        max_bytes=limits["max_string_bytes"],
    )
    if domain not in DOMAIN_SIGNATURES:
        raise ValueError(f"definition {ident} has unsupported domain {domain}")
    dependencies = definition["dependencies"]
    if not isinstance(dependencies, list):
        raise ValueError(f"definition {ident} dependencies must be an array")
    if len(dependencies) > limits["max_sequence_items"]:
        raise ValueError(f"definition {ident} dependencies exceed max_sequence_items")
    if any(not isinstance(dep, str) or not dep for dep in dependencies):
        raise ValueError(f"definition {ident} has an invalid dependency ID")
    for dep in dependencies:
        _bounded_string(
            dep, label=f"definition {ident} dependency ID",
            max_bytes=limits["max_string_bytes"],
        )
    if len(dependencies) != len(set(dependencies)):
        raise ValueError(f"definition {ident} has duplicate dependencies")
    phase = definition["phase"]
    if phase not in PHASE_ORDER:
        raise ValueError(f"definition {ident} has unknown phase {phase}")
    order = definition["order"]
    if isinstance(order, bool) or not isinstance(order, int) or order < 0:
        raise ValueError(f"definition {ident} has invalid order")
    operation = definition["operation"]
    if not isinstance(operation, Mapping):
        raise ValueError(f"definition {ident} operation must be an object")
    _expect_mapping_keys(
        operation, required={"op"}, allowed={"op"}, label=f"definition {ident} operation"
    )
    op = operation["op"]
    if not isinstance(op, str):
        raise ValueError(f"definition {ident} operation op must be a string")
    if op not in SUPPORTED_SEEDED_OPERATIONS:
        raise ValueError(f"unknown seeded definition operation {op}")
    expected_kind = OPERATION_KINDS.get(op)
    if op == "literal":
        if not kind.startswith("literal-") or len(kind) == len("literal-"):
            raise ValueError(f"definition {ident} kind is incompatible with literal")
    elif kind != expected_kind:
        raise ValueError(f"definition {ident} kind {kind!r} is incompatible with {op}")
    expected_codomain = OPERATION_CODOMAINS.get(op)
    if expected_codomain is not None and codomain != expected_codomain:
        raise ValueError(
            f"definition {ident} codomain {codomain!r} is incompatible with {op}"
        )
    expected_domain = OPERATION_DOMAINS.get(op)
    if expected_domain is not None and domain != expected_domain:
        raise ValueError(
            f"definition {ident} domain {domain!r} is incompatible with {op}"
        )
    parameters = definition["parameters"]
    if not isinstance(parameters, Mapping):
        raise ValueError(f"definition {ident} parameters must be an object")
    required_parameters, allowed_parameters = OPERATION_PARAMETER_FIELDS[op]
    _expect_mapping_keys(
        parameters,
        required=set(required_parameters),
        allowed=set(allowed_parameters),
        label=f"definition {ident} parameters",
    )
    if op == "literal":
        result_type = parameters["result_type"]
        if not isinstance(result_type, str) or result_type not in {
            "bytes", "string", "bool", "i32", "u32", "record",
        }:
            raise ValueError(f"literal result type {result_type!r} is unsupported")
        if codomain != result_type:
            raise ValueError(
                f"definition {ident} codomain {codomain!r} is incompatible with literal "
                f"result type {result_type!r}"
            )
    _validate_tree_budget(parameters, limits, label=f"definition {ident} parameters")
    string_parameters: Mapping[str, Any] = parameters
    if op == "literal" and parameters["result_type"] == "bytes":
        raw_value = parameters["value"]
        if isinstance(raw_value, Mapping):
            # The encoded carrier is representation overhead for a semantic byte
            # result.  Its decoded value is bounded by max_output_bytes below;
            # every key, the encoding label, and any unexpected field still pass
            # through the ordinary string limit and shape validation.
            bounded_value = dict(raw_value)
            if "data" in bounded_value:
                bounded_value["data"] = None
            string_parameters = {
                "result_type": parameters["result_type"],
                "value": bounded_value,
            }
        else:
            # A direct string is likewise the carrier for semantic bytes.
            string_parameters = {
                "result_type": parameters["result_type"],
                "value": None,
            }
    _validate_string_tree(
        string_parameters,
        max_bytes=limits["max_string_bytes"],
        label=f"definition {ident} parameters",
    )
    _validate_operation_parameter_shape(definition, limits)
    provenance = definition["provenance"]
    if not isinstance(provenance, Mapping) or not provenance:
        raise ValueError(f"definition {ident} provenance must be a non-empty object")
    _validate_tree_budget(provenance, limits, label=f"definition {ident} provenance")
    _validate_string_tree(
        provenance, max_bytes=limits["max_string_bytes"],
        label=f"definition {ident} provenance",
    )
    seed_tokens = definition.get("seed_tokens", [])
    if not isinstance(seed_tokens, list):
        raise ValueError(f"definition {ident} seed_tokens must be an array")
    if len(seed_tokens) > limits["max_sequence_items"]:
        raise ValueError(f"definition {ident} seed_tokens exceed max_sequence_items")
    if any(not isinstance(token, str) or not token for token in seed_tokens):
        raise ValueError(f"definition {ident} has an invalid seed token")
    for token in seed_tokens:
        _bounded_string(
            token, label=f"definition {ident} seed token",
            max_bytes=limits["max_string_bytes"],
        )
    if len(seed_tokens) != len(set(seed_tokens)):
        raise ValueError(f"definition {ident} repeats a seed token")
    for token in seed_tokens:
        if token not in registered_tokens:
            raise ValueError(f"definition {ident} references unregistered seed token {token!r}")
    content_address = definition["content_hash"]
    if not isinstance(content_address, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", content_address):
        raise ValueError(f"definition {ident} has an invalid content_hash")
    if not verify_hash(dict(definition)):
        raise ValueError(f"definition hash mismatch: {ident}")


def _seeded_order(
    definitions: Sequence[Mapping[str, Any]],
    *,
    budgets: Mapping[str, int],
    registered_tokens: frozenset[str],
) -> tuple[list[str], dict[str, Mapping[str, Any]]]:
    by_id: dict[str, Mapping[str, Any]] = {}
    slots: dict[tuple[int, int], str] = {}
    ranks: dict[str, tuple[int, int, str]] = {}
    for definition in definitions:
        if not isinstance(definition, Mapping):
            raise ValueError("definitions must contain objects")
        _validate_definition_shape(
            definition, budgets=budgets, registered_tokens=registered_tokens
        )
        ident = definition["id"]
        if len(definitions) > _effective_limits(definition, budgets)["max_definitions"]:
            raise ValueError(f"definition {ident} max_definitions limit is exceeded")
        if not ident or ident in by_id:
            raise ValueError(f"duplicate or empty definition id {ident!r}")
        phase = definition["phase"]
        order = definition["order"]
        slot = (PHASE_ORDER.index(phase), order)
        if slot in slots:
            raise ValueError(f"ambiguous phase/order slot for {ident} and {slots[slot]}")
        slots[slot] = ident
        ranks[ident] = (slot[0], slot[1], ident)
        by_id[ident] = definition

    indegree = {ident: 0 for ident in by_id}
    children = {ident: [] for ident in by_id}
    for ident, definition in by_id.items():
        seen: set[str] = set()
        for dep_value in definition.get("dependencies", []):
            dep = str(dep_value)
            if dep not in by_id:
                raise ValueError(f"unknown dependency {dep} from {ident}")
            if dep in seen:
                raise ValueError(f"duplicate dependency {dep} from {ident}")
            seen.add(dep)
            indegree[ident] += 1
            children[dep].append(ident)
    ready = sorted((ranks[i], i) for i, degree in indegree.items() if degree == 0)
    ordered: list[str] = []
    while ready:
        _, ident = ready.pop(0)
        ordered.append(ident)
        for child in sorted(children[ident], key=ranks.__getitem__):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append((ranks[child], child))
                ready.sort()
    if len(ordered) != len(by_id):
        raise ValueError("definition dependency cycle")
    for ident, definition in by_id.items():
        for dep_value in definition.get("dependencies", []):
            dep = str(dep_value)
            if ranks[dep] >= ranks[ident]:
                raise ValueError(f"definition order violation: {ident} depends on {dep}")
    return ordered, by_id


def _closure(root: str, by_id: Mapping[str, Mapping[str, Any]]) -> set[str]:
    if root not in by_id:
        raise ValueError(f"root definition {root} does not exist")
    selected: set[str] = set()
    stack = [root]
    while stack:
        ident = stack.pop()
        if ident in selected:
            continue
        selected.add(ident)
        stack.extend(str(dep) for dep in by_id[ident].get("dependencies", []))
    return selected


def _validate_operation_contract(
    definition: Mapping[str, Any],
    dep_values: Sequence[_Typed],
) -> None:
    ident = definition["id"]
    domain = definition["domain"]
    actual = tuple(value.type_name for value in dep_values)
    if domain == "record-sequence":
        if not actual or any(type_name != "record" for type_name in actual):
            raise TypeError(
                f"definition {ident} domain 'record-sequence' requires one or more "
                f"record dependencies, found {actual}"
            )
        return
    expected = DOMAIN_SIGNATURES[domain]
    if actual != expected:
        raise TypeError(
            f"definition {ident} domain {domain!r} requires dependencies {expected}, found {actual}"
        )


def _validate_parameter_keys(
    definition: Mapping[str, Any],
    *,
    required: set[str] = frozenset(),
    allowed: set[str] = frozenset(),
) -> Mapping[str, Any]:
    params = definition["parameters"]
    _expect_mapping_keys(
        params,
        required=set(required),
        allowed=set(allowed),
        label=f"definition {definition['id']} parameters",
    )
    return params


def _validate_result_limits(
    result: _Typed,
    limits: Mapping[str, int],
    *,
    ident: str,
) -> None:
    """Apply effective limits before a selected value is exposed to dependants."""
    if result.type_name == "bytes":
        if len(result.value) > limits["max_output_bytes"]:
            raise ValueError(f"definition {ident} exceeds max_output_bytes")
        return
    if result.type_name == "cell_graph":
        if len(result.value.cells) > limits["max_cells"]:
            raise ValueError(f"definition {ident} exceeds max_cells")
        return
    if result.type_name not in {"string", "bool", "i32", "u32", "record", "sequence"}:
        return
    _validate_tree_budget(result.value, limits, label=f"definition {ident} result")
    _validate_string_tree(
        result.value,
        max_bytes=limits["max_string_bytes"],
        label=f"definition {ident} result",
    )
    try:
        encoded = canonical_bytes(result.value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"definition {ident} result is not finite JSON") from exc
    if len(encoded) > limits["max_output_bytes"]:
        raise ValueError(f"definition {ident} exceeds max_output_bytes")


def _lower(spec: _ProgramSpec) -> tuple[Program, tuple[Mapping[str, Any], ...]]:
    cells = sorted(spec.graph.cells, key=lambda c: c.key)
    if not cells:
        raise ValueError("seeded program graph is empty")
    ids = [cell.ident for cell in cells]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate cell ID")
    keys = [cell.key for cell in cells]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate canonical cell key")
    by_id = {cell.ident: i for i, cell in enumerate(cells)}
    if spec.entry_id not in by_id:
        raise ValueError(f"entry cell {spec.entry_id} does not exist")
    lowered: list[Cell] = []
    crosswalk: list[Mapping[str, Any]] = []
    for index, cell in enumerate(cells):
        for target in cell.next_ids:
            if target not in by_id:
                raise ValueError(f"cell {cell.ident} references unknown successor {target}")
        lowered.append(Cell(
            cell.key_hi, cell.key_lo, cell.opcode, cell.flags,
            *cell.args,
            by_id[cell.next_ids[0]], by_id[cell.next_ids[1]],
            cell.payload, cell.aux,
        ))
        crosswalk.append({
            "cell_index": index,
            "cell_id": cell.ident,
            "key": f"0x{cell.key:016x}",
            "opcode": Opcode(cell.opcode).name,
            "definition_id": cell.source_definition,
            "next0": by_id[cell.next_ids[0]],
            "next1": by_id[cell.next_ids[1]],
            "flags": cell.flags,
            "payload": cell.payload,
            "aux": cell.aux,
            "origin": dict(cell.origin),
        })
    state = replace(spec.state)
    state.cell = by_id[spec.entry_id]
    return Program(
        cells=lowered,
        entry=by_id[spec.entry_id],
        seed=spec.seed,
        default_ticks=spec.default_ticks,
        initial_state=state,
        flags=spec.flags,
    ), tuple(crosswalk)


def _compile_seeded_document(
    document: Mapping[str, Any],
    *,
    seed_bytes: bytes,
    token_registry: Mapping[str, Any] | None,
    source_root: str | Path | None = None,
) -> SeededCompilationResult:
    budgets = _validate_seeded_document_shape(document)
    seed_text = _validate_seed(seed_bytes)
    registered_tokens = _validate_token_registry(token_registry, seed_text=seed_text)
    definitions = document["definitions"]
    order, by_id = _seeded_order(
        definitions, budgets=budgets, registered_tokens=registered_tokens
    )
    root = document["root_definition"]
    selected = _closure(root, by_id)
    selected_order = [ident for ident in order if ident in selected]
    values: dict[str, _Typed] = {}
    resolved_sources: list[dict[str, Any]] = []
    seed_record = _parsed_seed_record(seed_bytes, seed_text)

    for ident in selected_order:
        definition = by_id[ident]
        op = definition["operation"]["op"]
        params = definition["parameters"]
        deps = definition["dependencies"]
        dep_values = [values[dep] for dep in deps]
        limits = _effective_limits(definition, budgets)
        if len(definitions) > limits["max_definitions"]:
            raise ValueError(f"definition {ident} max_definitions limit is exceeded")
        _validate_operation_contract(definition, dep_values)

        if op == "seed.bytes":
            _validate_parameter_keys(definition)
            result = _Typed("bytes", seed_bytes)
        elif op == "seed.tokens":
            _validate_parameter_keys(definition)
            if len(dep_values) != 1 or dep_values[0].type_name != "bytes" or dep_values[0].value != seed_bytes:
                raise ValueError("seed.tokens requires canonical seed.bytes")
            result = _Typed("record", dict(seed_record))
        elif op == "source.json":
            params = _validate_parameter_keys(
                definition,
                required={
                    "path", "bytes", "sha256", "canonical_newline",
                    "verify_content_hash",
                },
                allowed={
                    "path", "bytes", "sha256", "canonical_newline",
                    "verify_content_hash",
                },
            )
            if by_id[deps[0]]["operation"]["op"] != "seed.tokens" or dep_values[0].value != seed_record:
                raise ValueError("source.json must depend directly on canonical seed.tokens")
            relative_path = _bounded_string(
                params["path"], label="source.json path",
                max_bytes=limits["max_string_bytes"],
            )
            declared_bytes = params["bytes"]
            if (
                isinstance(declared_bytes, bool)
                or not isinstance(declared_bytes, int)
                or declared_bytes < 0
            ):
                raise TypeError("source.json bytes must be a non-negative integer")
            declared_sha256 = params["sha256"]
            if not isinstance(declared_sha256, str) or not re.fullmatch(
                r"sha256:[0-9a-f]{64}", declared_sha256
            ):
                raise ValueError("source.json sha256 must be a lowercase sha256 content address")
            canonical_newline = params["canonical_newline"]
            verify_content_address = params["verify_content_hash"]
            if not isinstance(canonical_newline, bool):
                raise TypeError("source.json canonical_newline must be boolean")
            if not isinstance(verify_content_address, bool):
                raise TypeError("source.json verify_content_hash must be boolean")
            resolved_path, normalized_path = _resolve_literal_source(
                source_root, relative_path
            )
            raw = resolved_path.read_bytes()
            if len(raw) != declared_bytes:
                raise ValueError("source.json declared byte length mismatch")
            actual_sha256 = _sha256_bytes(raw)
            if actual_sha256 != declared_sha256:
                raise ValueError("source.json declared SHA-256 mismatch")
            if len(raw) > limits["max_output_bytes"]:
                raise ValueError(f"definition {ident} exceeds max_output_bytes")
            try:
                source_text = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError("source.json input must be strict UTF-8") from exc
            value = _strict_json_loads(
                source_text, label=f"source.json input {normalized_path}"
            )
            if not isinstance(value, Mapping):
                raise TypeError("source.json input must be a JSON object")
            value = dict(value)
            try:
                encoded = canonical_bytes(value)
            except (TypeError, ValueError) as exc:
                raise ValueError("source.json input must be finite JSON") from exc
            _validate_tree_budget(value, limits, label=f"source.json input {normalized_path}")
            _validate_string_tree(
                value, max_bytes=limits["max_string_bytes"],
                label=f"source.json input {normalized_path}",
            )
            if canonical_newline and raw != encoded + b"\n":
                raise ValueError("source.json input is not canonical JSON plus LF")
            if verify_content_address and not verify_hash(value):
                raise ValueError("source.json input content hash mismatch")
            resolved_sources.append({
                "definition_id": ident,
                "path": normalized_path,
                "bytes": len(raw),
                "sha256": actual_sha256,
            })
            result = _Typed("record", value)
        elif op == "sequence.construct":
            _validate_parameter_keys(definition)
            if len(dep_values) > limits["max_sequence_items"]:
                raise ValueError(f"definition {ident} exceeds max_sequence_items")
            result = _Typed("sequence", [value.value for value in dep_values])
        elif op == "formal.evaluate":
            params = _validate_parameter_keys(
                definition, required={"input_name"}, allowed={"input_name"}
            )
            input_name = _bounded_string(
                params["input_name"], label="formal.evaluate input_name",
                max_bytes=limits["max_string_bytes"],
            )
            formal_limits = FormalLimits(
                max_steps=limits["max_expression_nodes"],
                max_depth=limits["max_expression_depth"],
                max_collection_items=limits["max_sequence_items"],
                max_value_nodes=limits["max_expression_nodes"],
                max_canonical_bytes=limits["max_output_bytes"],
            )
            evaluated = run_formal_program(
                dep_values[0].value,
                {input_name: dep_values[1].value},
                limits=formal_limits,
            )
            result = _Typed("record", evaluated)
        elif op == "canonical.encode":
            params = _validate_parameter_keys(
                definition,
                required={"terminal_newline"},
                allowed={"terminal_newline"},
            )
            terminal_newline = params["terminal_newline"]
            if not isinstance(terminal_newline, bool):
                raise TypeError("canonical.encode terminal_newline must be boolean")
            encoded = canonical_bytes(dep_values[0].value)
            if terminal_newline:
                encoded += b"\n"
            if len(encoded) > limits["max_output_bytes"]:
                raise ValueError(f"definition {ident} exceeds max_output_bytes")
            result = _Typed("bytes", encoded)
        elif op == "literal":
            params = _validate_parameter_keys(
                definition,
                required={"result_type", "value"},
                allowed={"result_type", "value"},
            )
            result_type = params["result_type"]
            if not isinstance(result_type, str):
                raise TypeError("literal result_type must be a string")
            raw = params["value"]
            if result_type == "bytes":
                value = _decode_bytes(raw)
                if len(value) > limits["max_output_bytes"]:
                    raise ValueError(f"definition {ident} exceeds max_output_bytes")
            elif result_type == "string":
                if not isinstance(raw, str):
                    raise TypeError("string literal must be a string")
                value = raw
                if len(value.encode("utf-8")) > limits["max_string_bytes"]:
                    raise ValueError(f"definition {ident} exceeds max_string_bytes")
            elif result_type == "bool":
                if not isinstance(raw, bool):
                    raise TypeError("bool literal must be true or false")
                value = raw
            elif result_type == "i32":
                value = i32(_int(raw))
            elif result_type == "u32":
                value = u32(_int(raw))
            elif result_type == "record":
                if not isinstance(raw, Mapping):
                    raise TypeError("record literal must be an object")
                try:
                    canonical_bytes(raw)
                except (TypeError, ValueError) as exc:
                    raise ValueError("record literal must contain finite JSON values") from exc
                value = dict(raw)
            else:
                raise ValueError(f"literal result type {result_type} is unsupported")
            result = _Typed(result_type, value)
        elif op == "state64.construct":
            params = _validate_parameter_keys(
                definition, required={"fields"}, allowed={"fields"}
            )
            fields = params["fields"]
            if not isinstance(fields, Mapping):
                raise ValueError("state64.construct fields must be an object")
            result = _Typed("state64", _state_from_json(fields))
        elif op == "hash.sha256":
            params = _validate_parameter_keys(definition, allowed={"prefix"})
            if len(dep_values) != 1 or dep_values[0].type_name != "bytes":
                raise TypeError("hash.sha256 requires one bytes dependency")
            if "prefix" in params and not isinstance(params["prefix"], bool):
                raise TypeError("hash.sha256 prefix must be boolean")
            digest = hashlib.sha256(dep_values[0].value).hexdigest()
            result = _Typed("string", ("sha256:" if params.get("prefix", True) else "") + digest)
        elif op == "assert.equal":
            _validate_parameter_keys(definition)
            if len(dep_values) != 2:
                raise ValueError("assert.equal requires two dependencies")
            if dep_values[0].value != dep_values[1].value:
                raise ValueError(f"assert.equal failed in definition {ident}")
            result = _Typed("bool", True)
        elif op == "emit.graph":
            params = _validate_parameter_keys(
                definition,
                allowed={
                    "chunk_bytes", "byte_order", "id_prefix", "key_base", "key_field",
                    "aux_base", "halt_last",
                },
            )
            if len(dep_values) != 1 or dep_values[0].type_name != "bytes":
                raise TypeError("emit.graph requires one bytes dependency")
            data = dep_values[0].value
            if not data:
                raise ValueError("emit.graph cannot lower empty bytes")
            if len(data) > limits["max_output_bytes"]:
                raise ValueError(f"definition {ident} exceeds max_output_bytes")
            chunk_size = _int(params.get("chunk_bytes", 4))
            if not 1 <= chunk_size <= 4:
                raise ValueError("emit.graph chunk_bytes must be in 1..4")
            byte_order = str(params.get("byte_order", "little"))
            if byte_order not in {"little", "big"}:
                raise ValueError("emit.graph byte_order must be little or big")
            count = math.ceil(len(data) / chunk_size)
            if count > limits["max_cells"]:
                raise ValueError(f"definition {ident} exceeds max_cells")
            prefix = params.get("id_prefix", "cell:emit")
            _bounded_string(
                prefix, label="emit.graph id_prefix", max_bytes=limits["max_string_bytes"]
            )
            width = max(1, len(str(count - 1)))
            _bounded_string(
                f"{prefix}:{count - 1:0{width}d}",
                label="emit.graph generated cell ID",
                max_bytes=limits["max_string_bytes"],
            )
            ids = [f"{prefix}:{i:0{width}d}" for i in range(count)]
            base = params.get("key_base", {})
            if not isinstance(base, Mapping):
                raise ValueError("emit.graph key_base must be an object")
            unknown_coords = sorted(set(base) - {"rho", "theta", "tick", "phi"})
            if unknown_coords:
                raise ValueError("emit.graph key_base has unknown coordinates: " + ", ".join(unknown_coords))
            coords_base = {
                name: _int(base.get(name, 0)) for name in ("rho", "theta", "tick", "phi")
            }
            field = params.get("key_field", "rho")
            if field not in {"rho", "theta", "tick", "phi"}:
                raise ValueError("emit.graph key_field is invalid")
            aux_base = _int(params.get("aux_base", 0))
            if not 0 <= aux_base <= 0xFFFFFFFF or aux_base + count - 1 > 0xFFFFFFFF:
                raise ValueError("emit.graph aux range exceeds u32")
            halt_last = params.get("halt_last", True)
            if not isinstance(halt_last, bool):
                raise TypeError("emit.graph halt_last must be boolean")
            coordinate_limits = {
                "rho": RHO_STATES,
                "theta": THETA_STATES,
                "tick": TIME_STATES,
                "phi": PHI_STATES,
            }
            for name, value in coords_base.items():
                upper = coordinate_limits[name]
                final = value + count - 1 if name == field else value
                if value < 0 or final >= upper:
                    raise ValueError(f"emit.graph {name} key range exceeds its canonical field")
            specs: list[_CellSpec] = []
            for index in range(count):
                offset = index * chunk_size
                chunk = data[offset:offset + chunk_size]
                coords = dict(coords_base)
                coords[field] += index
                hi, lo = pack_key_contiguous(**coords)
                if byte_order == "little":
                    payload = int.from_bytes(chunk.ljust(4, b"\0"), "little")
                else:
                    payload = int.from_bytes(chunk.rjust(4, b"\0"), "big")
                flags = len(chunk) << FLAG_EMIT_COUNT_SHIFT
                if byte_order == "big":
                    flags |= FLAG_EMIT_BIG_ENDIAN
                if halt_last and index == count - 1:
                    flags |= FLAG_EMIT_HALT
                successor = ids[index + 1] if index + 1 < count else ids[index]
                specs.append(_CellSpec(
                    ident=ids[index],
                    key_hi=hi,
                    key_lo=lo,
                    opcode=int(Opcode.EMIT),
                    flags=u32(flags),
                    args=(0, 0, 0, 0),
                    next_ids=(successor, successor),
                    payload=u32(payload),
                    aux=u32(aux_base + index),
                    source_definition=ident,
                    origin={
                        "definition": ident,
                        "byte_offset": offset,
                        "byte_count": len(chunk),
                        "byte_order": byte_order,
                    },
                ))
            result = _Typed("cell_graph", _Graph(tuple(specs), ids[0]))
        elif op == "program.construct":
            params = _validate_parameter_keys(
                definition,
                allowed={"entry", "flags", "seed", "default_ticks", "emit_bytes"},
            )
            graphs = [value.value for value in dep_values if value.type_name == "cell_graph"]
            states = [value.value for value in dep_values if value.type_name == "state64"]
            guards = [value.value for value in dep_values if value.type_name == "bool"]
            if len(graphs) != 1 or len(states) > 1:
                raise ValueError("program.construct requires one graph and at most one state")
            if guards and not all(guards):
                raise ValueError("program.construct guard dependency is false")
            graph = graphs[0]
            if len(graph.cells) > limits["max_cells"]:
                raise ValueError(f"definition {ident} exceeds max_cells")
            state = states[0] if states else State()
            entry = params.get("entry", graph.entry_id)
            _bounded_string(
                entry, label="program.construct entry", max_bytes=limits["max_string_bytes"]
            )
            flags = u32(_int(params.get("flags", 0))) | PROGRAM_FLAG_SEEDED_PROFILE
            flags &= ~PROGRAM_FLAG_EMIT_BYTES
            emit_bytes = params.get("emit_bytes", False)
            if not isinstance(emit_bytes, bool):
                raise TypeError("program.construct emit_bytes must be boolean")
            if emit_bytes:
                flags |= PROGRAM_FLAG_EMIT_BYTES
            default_ticks = _u32_value(
                params.get("default_ticks", len(graph.cells)),
                label="program.construct default_ticks",
            )
            result = _Typed("program", _ProgramSpec(
                graph=graph,
                state=state,
                entry_id=entry,
                seed=u32(_int(params.get("seed", 0))),
                default_ticks=default_ticks,
                flags=flags,
            ))
        else:
            raise ValueError(f"unknown seeded definition operation {op}")

        _validate_result_limits(result, limits, ident=ident)
        declared = str(definition.get("codomain", result.type_name))
        if result.type_name != declared:
            raise TypeError(f"definition {ident} produced {result.type_name}, declared {declared}")
        values[ident] = result

    root_value = values[root]
    if root_value.type_name != "program":
        raise TypeError("root definition must produce program")
    program, crosswalk = _lower(root_value.value)
    if len(program.cells) > budgets["max_cells"]:
        raise ValueError("lowered program exceeds budgets.max_cells")
    report = {
        "schema": "TOM-SEEDED-COMPILE-REPORT-1.0",
        "profile": SEEDED_PROFILE_ID,
        "tomagi_abi": "1.0",
        "seed": {
            "bytes": len(seed_bytes),
            "sha256": hashlib.sha256(seed_bytes).hexdigest(),
            "grammar_id": SEED_GRAMMAR_ID,
        },
        "root_definition": root,
        "definition_order": order,
        "evaluated_definition_order": selected_order,
        "definition_hashes": {ident: str(by_id[ident]["content_hash"]) for ident in order},
        "cell_count": len(program.cells),
        "entry": program.entry,
        "program_flags": program.flags,
        "crosswalk": list(crosswalk),
    }
    if resolved_sources:
        report["resolved_sources"] = resolved_sources
    return SeededCompilationResult(program, tuple(order), crosswalk, report)


def compile_document(
    document: Mapping[str, Any],
    *,
    seed_bytes: bytes | None = None,
    token_registry: Mapping[str, Any] | None = None,
    source_root: str | Path | None = None,
) -> Program:
    if document.get("compilation_profile") == SEEDED_PROFILE_ID:
        if seed_bytes is None:
            raise ValueError("seeded compile_document requires seed_bytes")
        return _compile_seeded_document(
            document,
            seed_bytes=seed_bytes,
            token_registry=token_registry,
            source_root=source_root,
        ).program
    return _compile_legacy_document(document)


def compile_file_result(source: str | Path, destination: str | Path) -> SeededCompilationResult | None:
    source_path = Path(source).resolve()
    destination_path = Path(destination)
    source_text = source_path.read_text(encoding="utf-8")
    document = json.loads(source_text)
    if not isinstance(document, Mapping):
        raise ValueError("TOMAGI source must be a JSON object")
    if document.get("compilation_profile") != SEEDED_PROFILE_ID:
        program = _compile_legacy_document(document)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        dump(program, destination_path)
        return None

    document = _strict_json_loads(source_text, label=f"source {source_path.name}")
    if not isinstance(document, Mapping):
        raise ValueError("TOMAGI source must be a JSON object")
    _validate_seeded_document_shape(document)
    seed_info = _validate_seed_genome_record(document)
    seed_path = (source_path.parent / seed_info["path"]).resolve()
    seed_bytes = seed_path.read_bytes()
    _validate_seed(seed_bytes)
    registry_path = (source_path.parent / seed_info["token_registry"]).resolve()
    token_registry = _strict_json_loads(
        registry_path.read_text(encoding="utf-8"), label=f"token registry {registry_path.name}"
    )
    if not isinstance(token_registry, Mapping):
        raise ValueError("canonical token registry must be a JSON object")

    result = _compile_seeded_document(
        document,
        seed_bytes=seed_bytes,
        token_registry=token_registry,
        source_root=source_path.parent,
    )
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    blob = dumps(result.program)
    destination_path.write_bytes(blob)
    sidecar = dict(result.report)
    sidecar.update({
        "source_file": source_path.name,
        "source_sha256": _sha256_bytes(source_path.read_bytes()),
        "program_file": destination_path.name,
        "program_bytes": len(blob),
        "program_sha256": _sha256_bytes(blob),
    })
    destination_path.with_suffix(destination_path.suffix + ".compile.json").write_bytes(
        canonical_bytes(sidecar) + b"\n"
    )
    return result


def compile_file(source: str | Path, destination: str | Path) -> Program:
    result = compile_file_result(source, destination)
    if result is not None:
        return result.program
    return load(destination)
