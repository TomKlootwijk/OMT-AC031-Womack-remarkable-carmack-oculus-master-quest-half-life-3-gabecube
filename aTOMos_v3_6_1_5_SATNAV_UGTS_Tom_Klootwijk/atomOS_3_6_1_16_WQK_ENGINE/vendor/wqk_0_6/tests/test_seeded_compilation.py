from __future__ import annotations

import copy
import hashlib
import json
import math
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from tomagi.canonical import attach_hash, canonical_bytes
from tomagi.compiler import compile_document, compile_file_result
from tomagi.core import PROGRAM_FLAG_EMIT_BYTES, run
from tomagi.format import dumps
from tomagi.formal import make_program
from tomagi.materialize import materialize_trace


class _SeededFixture:
    @classmethod
    def setUpClass(cls) -> None:
        cls.source_path = ROOT / "examples/world03/world03_release_artifact.literal.json"
        cls.program_path = ROOT / "examples/world03/world03_release_artifact.tmg"
        cls.source = json.loads(cls.source_path.read_text(encoding="utf-8"))
        cls.seed = (ROOT / "TOM_seed_genome_2026-09-01.txt").read_bytes()
        cls.registry = json.loads(
            (ROOT / "spec/tom_seed_token_registry_1_0.json").read_text(encoding="utf-8")
        )

    def compile(
        self,
        source: dict | None = None,
        registry: dict | None = None,
        **kwargs,
    ):
        return compile_document(
            self.source if source is None else source,
            seed_bytes=self.seed,
            token_registry=self.registry if registry is None else registry,
            **kwargs,
        )

    @staticmethod
    def mutate_definition(source: dict, ident: str, mutation) -> None:
        for index, definition in enumerate(source["definitions"]):
            if definition["id"] == ident:
                changed = copy.deepcopy(definition)
                mutation(changed)
                source["definitions"][index] = attach_hash(changed)
                return
        raise AssertionError(f"missing fixture definition {ident}")


class SeededCompilationValidationTests(_SeededFixture, unittest.TestCase):

    def test_current_seeded_artifact_remains_byte_identical(self):
        program = self.compile()
        self.assertEqual(dumps(program), self.program_path.read_bytes())

    def test_file_compile_loads_registry_and_preserves_program_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "artifact.tmg"
            result = compile_file_result(self.source_path, destination)
            self.assertIsNotNone(result)
            self.assertEqual(destination.read_bytes(), self.program_path.read_bytes())
            self.assertTrue(destination.with_suffix(".tmg.compile.json").is_file())

    def test_seeded_compile_requires_exact_registry(self):
        with self.assertRaisesRegex(ValueError, "canonical token registry"):
            compile_document(self.source, seed_bytes=self.seed)

        changed = copy.deepcopy(self.registry)
        changed["purpose"] += " tampered"
        changed = attach_hash(changed)
        with self.assertRaisesRegex(ValueError, "not the canonical TOM seed token registry"):
            self.compile(registry=changed)

    def test_seed_tokens_are_exact_registered_tokens(self):
        source = copy.deepcopy(self.source)
        self.mutate_definition(
            source, "tom:seed", lambda definition: definition.update(seed_tokens=["OM"])
        )
        with self.assertRaisesRegex(ValueError, "unregistered seed token"):
            self.compile(source)

    def test_exact_seed_grammar_id_is_required(self):
        source = copy.deepcopy(self.source)
        source["seed_genome"]["grammar_id"] = "TOM-SEED-GRAMMAR-BOGUS"
        with self.assertRaisesRegex(ValueError, "grammar_id"):
            self.compile(source)

    def test_definition_provenance_is_required(self):
        source = copy.deepcopy(self.source)

        def remove_provenance(definition: dict) -> None:
            definition.pop("provenance")

        self.mutate_definition(source, "doc:bytes", remove_provenance)
        with self.assertRaisesRegex(ValueError, "provenance"):
            self.compile(source)

    def test_declared_domain_signature_is_enforced(self):
        source = copy.deepcopy(self.source)
        self.mutate_definition(
            source, "doc:bytes", lambda definition: definition.update(domain="bytes")
        )
        with self.assertRaisesRegex(TypeError, "domain 'bytes' requires dependencies"):
            self.compile(source)

    def test_operation_kind_is_enforced(self):
        source = copy.deepcopy(self.source)
        self.mutate_definition(
            source, "doc:emit", lambda definition: definition.update(kind="literal-output")
        )
        with self.assertRaisesRegex(ValueError, "kind .* incompatible"):
            self.compile(source)

    def test_document_and_definition_output_budgets_are_enforced(self):
        source = copy.deepcopy(self.source)
        source["budgets"]["max_output_bytes"] -= 1
        with self.assertRaisesRegex(ValueError, "max_output_bytes"):
            self.compile(source)

        source = copy.deepcopy(self.source)
        self.mutate_definition(
            source,
            "doc:bytes",
            lambda definition: definition["limits"].update(max_output_bytes=1),
        )
        with self.assertRaisesRegex(ValueError, "max_output_bytes"):
            self.compile(source)

    def test_definition_and_cell_budgets_are_enforced(self):
        source = copy.deepcopy(self.source)
        source["budgets"]["max_definitions"] = len(source["definitions"]) - 1
        with self.assertRaisesRegex(ValueError, "max_definitions"):
            self.compile(source)

        source = copy.deepcopy(self.source)
        self.mutate_definition(
            source,
            "doc:emit",
            lambda definition: definition["parameters"].update(chunk_bytes=3),
        )
        expected_cells = math.ceil(source["budgets"]["max_output_bytes"] / 3)
        self.assertGreater(expected_cells, source["budgets"]["max_cells"])
        with self.assertRaisesRegex(ValueError, "max_cells"):
            self.compile(source)

    def test_operation_parameters_and_key_ranges_are_closed(self):
        source = copy.deepcopy(self.source)
        self.mutate_definition(
            source,
            "doc:emit",
            lambda definition: definition["parameters"].update(chunk_byte=4),
        )
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            self.compile(source)

        source = copy.deepcopy(self.source)

        def negative_key(definition: dict) -> None:
            definition["parameters"]["key_base"]["rho"] = -1

        self.mutate_definition(source, "doc:emit", negative_key)
        with self.assertRaisesRegex(ValueError, "rho key range"):
            self.compile(source)

    def test_unselected_definition_shape_and_limits_are_still_validated(self):
        source = copy.deepcopy(self.source)
        source["definitions"].append(attach_hash({
            "id": "unused:bad-hash-shape",
            "kind": "computed-hash",
            "domain": "bytes",
            "codomain": "string",
            "dependencies": ["doc:bytes"],
            "phase": "event",
            "order": 0,
            "operation": {"op": "hash.sha256"},
            "parameters": {"prefix": "not-a-boolean"},
            "limits": {},
            "provenance": {"source": "unselected validation test"},
        }))
        with self.assertRaisesRegex(TypeError, "hash prefix must be boolean"):
            self.compile(source)

    def test_non_finite_canonical_json_is_rejected(self):
        with self.assertRaises(ValueError):
            canonical_bytes({"value": float("nan")})
        with self.assertRaises(ValueError):
            canonical_bytes({"value": float("inf")})

    def test_machine_readable_schema_accepts_all_current_seeded_sources(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema unavailable")
        schema = json.loads(
            (ROOT / "spec/tom_seeded_program.schema.json").read_text(encoding="utf-8")
        )
        validator = jsonschema.Draft202012Validator(schema)
        for path in sorted(ROOT.glob("examples/*/*.literal.json")):
            with self.subTest(path=path):
                validator.validate(json.loads(path.read_text(encoding="utf-8")))


def _definition(
    ident: str,
    *,
    kind: str,
    domain: str,
    codomain: str,
    dependencies: list[str],
    phase: str,
    order: int,
    op: str,
    parameters: dict,
) -> dict:
    return attach_hash({
        "id": ident,
        "kind": kind,
        "domain": domain,
        "codomain": codomain,
        "dependencies": dependencies,
        "phase": phase,
        "order": order,
        "operation": {"op": op},
        "parameters": parameters,
        "limits": {},
        "provenance": {"source": "seeded compiler generic-operation test"},
    })


def _source_parameters(
    path: Path,
    *,
    verify_content_hash: bool = True,
    canonical_newline: bool = True,
) -> dict:
    raw = path.read_bytes()
    return {
        "path": path.name,
        "bytes": len(raw),
        "sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
        "canonical_newline": canonical_newline,
        "verify_content_hash": verify_content_hash,
    }


def _generic_source_tree(root: Path, seed: bytes, registry: dict) -> dict:
    formal_program = make_program({
        "op": "record",
        "fields": {
            "count": {"op": "len", "value": {"op": "ref", "name": "records"}},
            "records": {"op": "ref", "name": "records"},
        },
    })
    input_record = attach_hash({"id": "observation:one", "value": 7})
    formal_path = root / "formal_program.json"
    input_path = root / "input_record.json"
    formal_path.write_bytes(canonical_bytes(formal_program) + b"\n")
    input_path.write_bytes(canonical_bytes(input_record) + b"\n")
    (root / "seed.txt").write_bytes(seed)
    (root / "registry.json").write_bytes(canonical_bytes(registry) + b"\n")

    definitions = [
        _definition(
            "seed", kind="canonical-seed", domain="none", codomain="bytes",
            dependencies=[], phase="parse", order=0, op="seed.bytes", parameters={},
        ),
        _definition(
            "tokens", kind="seed-parse", domain="bytes", codomain="record",
            dependencies=["seed"], phase="parse", order=1, op="seed.tokens", parameters={},
        ),
        _definition(
            "source:formal", kind="literal-json-source", domain="seed-record",
            codomain="record", dependencies=["tokens"], phase="parse", order=2,
            op="source.json", parameters=_source_parameters(formal_path),
        ),
        _definition(
            "source:item", kind="literal-json-source", domain="seed-record",
            codomain="record", dependencies=["tokens"], phase="parse", order=3,
            op="source.json", parameters=_source_parameters(input_path),
        ),
        _definition(
            "items", kind="record-sequence", domain="record-sequence",
            codomain="sequence", dependencies=["source:item"], phase="normalize", order=0,
            op="sequence.construct", parameters={},
        ),
        _definition(
            "evaluated", kind="formal-evaluation", domain="formal-program-sequence",
            codomain="record", dependencies=["source:formal", "items"],
            phase="resolve", order=0, op="formal.evaluate",
            parameters={"input_name": "records"},
        ),
        _definition(
            "encoded", kind="canonical-encoding", domain="record", codomain="bytes",
            dependencies=["evaluated"], phase="construct", order=0,
            op="canonical.encode", parameters={"terminal_newline": True},
        ),
        _definition(
            "state", kind="initial-state", domain="seed-record", codomain="state64",
            dependencies=["tokens"], phase="construct", order=1,
            op="state64.construct", parameters={"fields": {}},
        ),
        _definition(
            "guard", kind="literal-guard", domain="seed-record", codomain="bool",
            dependencies=["tokens"], phase="guard", order=0, op="literal",
            parameters={"result_type": "bool", "value": True},
        ),
        _definition(
            "emitted", kind="byte-emission", domain="bytes", codomain="cell_graph",
            dependencies=["encoded"], phase="event", order=0,
            op="emit.graph", parameters={},
        ),
        _definition(
            "program", kind="artifact-program", domain="state-graph-guard",
            codomain="program", dependencies=["state", "emitted", "guard"],
            phase="lineage", order=0, op="program.construct",
            parameters={"emit_bytes": True},
        ),
    ]
    return {
        "$schema": "../../spec/tom_seeded_program.schema.json",
        "tomagi_version": "1.0.0",
        "compilation_profile": "TOM-SEEDED-COMPILATION-1.0",
        "title": "Generic formal seeded chain test",
        "seed_genome": {
            "path": "seed.txt",
            "bytes": len(seed),
            "sha256": hashlib.sha256(seed).hexdigest(),
            "grammar_id": "TOM-SEED-GRAMMAR-1.0",
            "token_registry": "registry.json",
        },
        "root_definition": "program",
        "budgets": {
            "max_definitions": 32,
            "max_cells": 2048,
            "max_output_bytes": 8192,
            "max_sequence_items": 128,
            "max_repeat": 128,
            "max_expression_depth": 64,
            "max_expression_nodes": 4096,
            "max_string_bytes": 1024,
        },
        "definitions": definitions,
    }


class GenericSeededOperationTests(_SeededFixture, unittest.TestCase):
    def test_program_emit_flag_is_controlled_only_by_emit_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _generic_source_tree(root, self.seed, self.registry)

            def disable_emission(definition: dict) -> None:
                definition["parameters"].update({
                    "flags": PROGRAM_FLAG_EMIT_BYTES,
                    "emit_bytes": False,
                })

            self.mutate_definition(source, "program", disable_emission)
            program = self.compile(source, source_root=root)
            self.assertFalse(program.flags & PROGRAM_FLAG_EMIT_BYTES)

    def test_shipped_formal_authority_chain_is_byte_identical(self):
        source = ROOT / "examples/learner05/learner05_formal_authority.literal.json"
        expected_program = ROOT / "examples/learner05/learner05_formal_authority.tmg"
        expected_output = (
            ROOT / "validation/learner05/learner05_formal_authority.materialized.json"
        )
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / expected_program.name
            result = compile_file_result(source, destination)
            self.assertIsNotNone(result)
            self.assertEqual(destination.read_bytes(), expected_program.read_bytes())
            self.assertEqual(
                destination.with_suffix(".tmg.compile.json").read_bytes(),
                expected_program.with_suffix(".tmg.compile.json").read_bytes(),
            )
            self.assertEqual(len(result.report["resolved_sources"]), 20)
            _, trace = run(result.program, trace=True)
            artifact, _ = materialize_trace(result.program, trace)
            self.assertEqual(artifact, expected_output.read_bytes())

    def test_generic_formal_chain_compiles_executes_and_reports_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _generic_source_tree(root, self.seed, self.registry)
            try:
                import jsonschema
            except ImportError:
                jsonschema = None
            if jsonschema is not None:
                schema = json.loads(
                    (ROOT / "spec/tom_seeded_program.schema.json").read_text(
                        encoding="utf-8"
                    )
                )
                jsonschema.Draft202012Validator(schema).validate(source)
            source_path = root / "chain.literal.json"
            source_path.write_bytes(canonical_bytes(source) + b"\n")
            result = compile_file_result(source_path, root / "chain.tmg")
            self.assertIsNotNone(result)
            _, trace = run(result.program, trace=True)
            artifact, _ = materialize_trace(result.program, trace)
            decoded = json.loads(artifact)
            self.assertEqual(decoded["value"]["count"], 1)
            self.assertEqual(decoded["value"]["records"][0]["value"], 7)
            self.assertEqual(
                [item["path"] for item in result.report["resolved_sources"]],
                ["formal_program.json", "input_record.json"],
            )

    def test_source_json_requires_explicit_root_and_canonical_seed_dependency(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _generic_source_tree(root, self.seed, self.registry)
            with self.assertRaisesRegex(ValueError, "explicit source_root"):
                self.compile(source)

            self.mutate_definition(
                source,
                "source:item",
                lambda definition: definition.update(dependencies=["source:formal"]),
            )
            with self.assertRaisesRegex(ValueError, "directly on canonical seed.tokens"):
                self.compile(source, source_root=root)

    def test_source_json_rejects_escape_hash_newline_and_content_hash_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            source = _generic_source_tree(root, self.seed, self.registry)
            self.mutate_definition(
                source, "source:item",
                lambda definition: definition["parameters"].update(path="../outside.json"),
            )
            with self.assertRaisesRegex(ValueError, "escapes source_root"):
                self.compile(source, source_root=root)

            source = _generic_source_tree(root, self.seed, self.registry)
            self.mutate_definition(
                source, "source:item",
                lambda definition: definition["parameters"].update(
                    path=str((root / "input_record.json").resolve())
                ),
            )
            with self.assertRaisesRegex(ValueError, "must be relative"):
                self.compile(source, source_root=root)

            source = _generic_source_tree(root, self.seed, self.registry)
            self.mutate_definition(
                source, "source:item",
                lambda definition: definition["parameters"].update(bytes=1),
            )
            with self.assertRaisesRegex(ValueError, "byte length mismatch"):
                self.compile(source, source_root=root)

            source = _generic_source_tree(root, self.seed, self.registry)
            self.mutate_definition(
                source, "source:item",
                lambda definition: definition["parameters"].update(
                    sha256="sha256:" + "0" * 64
                ),
            )
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                self.compile(source, source_root=root)

            source = _generic_source_tree(root, self.seed, self.registry)
            item_path = root / "input_record.json"
            item = json.loads(item_path.read_text(encoding="utf-8"))
            item_path.write_text(json.dumps(item, indent=2) + "\n", encoding="utf-8")
            self.mutate_definition(
                source, "source:item",
                lambda definition: definition.update(
                    parameters=_source_parameters(item_path)
                ),
            )
            with self.assertRaisesRegex(ValueError, "not canonical JSON plus LF"):
                self.compile(source, source_root=root)

            source = _generic_source_tree(root, self.seed, self.registry)
            item_path = root / "input_record.json"
            item = json.loads(item_path.read_text(encoding="utf-8"))
            item["content_hash"] = "sha256:" + "0" * 64
            item_path.write_bytes(canonical_bytes(item) + b"\n")
            self.mutate_definition(
                source, "source:item",
                lambda definition: definition.update(
                    parameters=_source_parameters(item_path)
                ),
            )
            with self.assertRaisesRegex(ValueError, "content hash mismatch"):
                self.compile(source, source_root=root)

            source = _generic_source_tree(root, self.seed, self.registry)
            item_path = root / "input_record.json"
            item_path.write_bytes(b'{"value":NaN}\n')
            self.mutate_definition(
                source, "source:item",
                lambda definition: definition.update(parameters=_source_parameters(
                    item_path, verify_content_hash=False, canonical_newline=False
                )),
            )
            with self.assertRaisesRegex(ValueError, "non-finite JSON number"):
                self.compile(source, source_root=root)

            source = _generic_source_tree(root, self.seed, self.registry)
            item_path = root / "input_record.json"
            item_path.write_bytes(b"\xff")
            self.mutate_definition(
                source, "source:item",
                lambda definition: definition.update(parameters=_source_parameters(
                    item_path, verify_content_hash=False, canonical_newline=False
                )),
            )
            with self.assertRaisesRegex(ValueError, "strict UTF-8"):
                self.compile(source, source_root=root)

    def test_generic_operation_shapes_and_formal_program_hash_are_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _generic_source_tree(root, self.seed, self.registry)
            self.mutate_definition(
                source, "items", lambda definition: definition.update(dependencies=[])
            )
            with self.assertRaisesRegex(TypeError, "one or more record dependencies"):
                self.compile(source, source_root=root)

            source = _generic_source_tree(root, self.seed, self.registry)
            formal_path = root / "formal_program.json"
            formal_program = json.loads(formal_path.read_text(encoding="utf-8"))
            formal_program["content_hash"] = "sha256:" + "0" * 64
            formal_path.write_bytes(canonical_bytes(formal_program) + b"\n")

            def accept_tampered_program(definition: dict) -> None:
                definition["parameters"] = _source_parameters(
                    formal_path, verify_content_hash=False
                )

            self.mutate_definition(source, "source:formal", accept_tampered_program)
            with self.assertRaisesRegex(ValueError, "program content hash mismatch"):
                self.compile(source, source_root=root)


class MaterializedTraceValidationTests(_SeededFixture, unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.program = compile_document(
            cls.source, seed_bytes=cls.seed, token_registry=cls.registry
        )
        _, cls.trace = run(cls.program, trace=True)

    def test_valid_trace_and_valid_prefix_materialize(self):
        data, records = materialize_trace(self.program, self.trace)
        self.assertEqual(len(records), len(self.trace))
        prefix, prefix_records = materialize_trace(self.program, self.trace[:1])
        self.assertEqual(prefix, data[:4])
        self.assertEqual(len(prefix_records), 1)

    def test_reordered_or_duplicated_trace_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "deterministic replay"):
            materialize_trace(self.program, list(reversed(self.trace)))
        with self.assertRaisesRegex(ValueError, "deterministic replay"):
            materialize_trace(self.program, [self.trace[0], self.trace[0]])

    def test_tampered_or_incomplete_trace_row_is_rejected(self):
        tampered = [dict(row) for row in self.trace]
        tampered[0]["lineage"] ^= 1
        with self.assertRaisesRegex(ValueError, "lineage does not match"):
            materialize_trace(self.program, tampered)

        incomplete = [dict(row) for row in self.trace]
        incomplete[0].pop("opcode")
        with self.assertRaisesRegex(ValueError, "missing field opcode"):
            materialize_trace(self.program, incomplete)

        augmented = [dict(row) for row in self.trace]
        augmented[0]["claimed_source"] = 1
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            materialize_trace(self.program, augmented)


if __name__ == "__main__":
    unittest.main()
