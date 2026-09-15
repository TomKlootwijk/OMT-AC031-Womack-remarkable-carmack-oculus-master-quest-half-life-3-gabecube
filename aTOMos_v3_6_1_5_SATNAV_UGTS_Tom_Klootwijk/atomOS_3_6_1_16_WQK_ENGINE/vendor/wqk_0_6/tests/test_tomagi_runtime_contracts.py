from __future__ import annotations

import hashlib
import json
import os
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from tomagi.canonical import attach_hash
from tomagi.compiler import compile_document
from tomagi.core import Cell, Opcode, Program, State, i32, run, u32
from tomagi.format import HEADER_SIZE, dumps, loads
from tomagi.formal import evaluate, rational


def _lit(value):
    return {"op": "lit", "value": value}


def _comparison(op: str, left, right):
    return {"op": op, "left": _lit(left), "right": _lit(right)}


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
        "provenance": {"source": "fixed-width runtime contract regression"},
    })


def _seeded_source(*, fields: dict | None = None, default_ticks: int = 1) -> dict:
    seed = (ROOT / "TOM_seed_genome_2026-09-01.txt").read_bytes()
    definitions = [
        _definition(
            "seed", kind="canonical-seed", domain="none", codomain="bytes",
            dependencies=[], phase="parse", order=0, op="seed.bytes", parameters={},
        ),
        _definition(
            "tokens", kind="seed-parse", domain="bytes", codomain="record",
            dependencies=["seed"], phase="resolve", order=0, op="seed.tokens",
            parameters={},
        ),
        _definition(
            "bytes", kind="literal-bytes", domain="seed-record", codomain="bytes",
            dependencies=["tokens"], phase="construct", order=0, op="literal",
            parameters={"result_type": "bytes", "value": "x"},
        ),
        _definition(
            "state", kind="initial-state", domain="seed-record", codomain="state64",
            dependencies=["tokens"], phase="construct", order=1,
            op="state64.construct", parameters={"fields": fields or {}},
        ),
        _definition(
            "guard", kind="literal-guard", domain="seed-record", codomain="bool",
            dependencies=["tokens"], phase="guard", order=0, op="literal",
            parameters={"result_type": "bool", "value": True},
        ),
        _definition(
            "graph", kind="byte-emission", domain="bytes", codomain="cell_graph",
            dependencies=["bytes"], phase="event", order=0, op="emit.graph",
            parameters={},
        ),
        _definition(
            "program", kind="artifact-program", domain="state-graph-guard",
            codomain="program", dependencies=["state", "graph", "guard"],
            phase="lineage", order=0, op="program.construct",
            parameters={"default_ticks": default_ticks, "emit_bytes": True},
        ),
    ]
    return {
        "tomagi_version": "1.0.0",
        "compilation_profile": "TOM-SEEDED-COMPILATION-1.0",
        "seed_genome": {
            "path": "TOM_seed_genome_2026-09-01.txt",
            "bytes": len(seed),
            "sha256": hashlib.sha256(seed).hexdigest(),
            "grammar_id": "TOM-SEED-GRAMMAR-1.0",
            "token_registry": "spec/tom_seed_token_registry_1_0.json",
        },
        "root_definition": "program",
        "budgets": {
            "max_definitions": 8,
            "max_cells": 4,
            "max_output_bytes": 512,
            "max_sequence_items": 16,
            "max_repeat": 1,
            "max_expression_depth": 16,
            "max_expression_nodes": 128,
            "max_string_bytes": 256,
        },
        "definitions": definitions,
    }


def _compile_seeded(source: dict) -> Program:
    seed = (ROOT / "TOM_seed_genome_2026-09-01.txt").read_bytes()
    registry = json.loads(
        (ROOT / "spec/tom_seed_token_registry_1_0.json").read_text(encoding="utf-8")
    )
    return compile_document(source, seed_bytes=seed, token_registry=registry)


def _one_cell_program(**overrides) -> Program:
    cell_values = {
        "key_hi": 0,
        "key_lo": 0,
        "opcode": int(Opcode.NOP),
        "next0": 0,
        "next1": 0,
    }
    cell_values.update(overrides.pop("cell", {}))
    program_values = {
        "cells": [Cell(**cell_values)],
        "entry": 0,
        "seed": 0,
        "default_ticks": 1,
        "initial_state": State(),
    }
    program_values.update(overrides)
    return Program(**program_values)


class FormalEqualityContractTests(unittest.TestCase):
    def test_boolean_and_number_values_are_not_equal(self):
        unequal_pairs = (
            (True, 1),
            (False, 0),
            ([True], [1]),
            ({"value": False}, {"value": 0}),
        )
        for left, right in unequal_pairs:
            with self.subTest(left=left, right=right):
                self.assertFalse(evaluate(_comparison("eq", left, right)))
                self.assertTrue(evaluate(_comparison("ne", left, right)))

    def test_exact_integer_and_rational_numeric_equality_is_preserved(self):
        self.assertTrue(evaluate(_comparison("eq", 1, rational(1))))
        self.assertFalse(evaluate(_comparison("ne", -2, rational(-2))))


class FixedWidthCompilationContractTests(unittest.TestCase):
    def test_state64_fields_narrow_before_execution_and_round_trip(self):
        program = _compile_seeded(_seeded_source(fields={
            "rho": 1 << 32,
            "residual": 1 << 31,
            "sheet": -1,
            "lineage": (1 << 32) + 7,
        }))
        self.assertEqual(program.initial_state.rho, 0)
        self.assertEqual(program.initial_state.residual, -(1 << 31))
        self.assertEqual(program.initial_state.sheet, 0xFFFFFFFF)
        self.assertEqual(program.initial_state.lineage, 7)

        loaded = loads(dumps(program))
        self.assertEqual(program.initial_state.words(), loaded.initial_state.words())
        self.assertEqual(run(program, trace=True), run(loaded, trace=True))

    def test_legacy_cell_and_header_words_narrow_canonically(self):
        document = {
            "tomagi_version": "1.0.0",
            "seed": (1 << 32) + 3,
            "flags": -2,
            "default_ticks": 1,
            "initial_state": {"rho": 1 << 32, "sheet": -1},
            "cells": [{
                "id": "cell:0",
                "key": 0,
                "op": "NOP",
                "flags": -1,
                "args": [1 << 32, -(1 << 31) - 1, 1 << 31, -(1 << 32) - 1],
                "next": ["cell:0", "cell:0"],
                "payload": (1 << 32) + 1,
                "aux": -1,
            }],
        }
        program = compile_document(document)
        cell = program.cells[0]
        self.assertEqual(program.seed, 3)
        self.assertEqual(program.flags, u32(-2))
        self.assertEqual(program.initial_state.rho, 0)
        self.assertEqual(program.initial_state.sheet, 0xFFFFFFFF)
        self.assertEqual(cell.flags, 0xFFFFFFFF)
        self.assertEqual(
            (cell.arg0, cell.arg1, cell.arg2, cell.arg3),
            (0, i32(-(1 << 31) - 1), -(1 << 31), -1),
        )
        self.assertEqual((cell.payload, cell.aux), (1, 0xFFFFFFFF))

        loaded = loads(dumps(program))
        self.assertEqual(program.cells, loaded.cells)
        self.assertEqual(program.initial_state.words(), loaded.initial_state.words())

    def test_default_ticks_rejects_values_outside_u32(self):
        with self.assertRaisesRegex(ValueError, "u32 range"):
            _compile_seeded(_seeded_source(default_ticks=1 << 32))
        with self.assertRaisesRegex(ValueError, "u32 range"):
            compile_document({
                "tomagi_version": "1.0.0",
                "default_ticks": 1 << 32,
                "cells": [{"id": "cell:0", "key": 0, "op": "NOP"}],
            })
        with self.assertRaisesRegex(ValueError, "u32 range"):
            _one_cell_program(default_ticks=1 << 32)


class ProgramValidationContractTests(unittest.TestCase):
    def test_program_rejects_invalid_opcodes_and_negative_successors(self):
        with self.assertRaisesRegex(ValueError, "opcode"):
            _one_cell_program(cell={"opcode": 16})
        with self.assertRaisesRegex(ValueError, "successor"):
            _one_cell_program(cell={"next0": -1})

    def test_binary_loader_applies_program_cell_validation(self):
        blob = bytearray(dumps(_one_cell_program()))
        struct.pack_into("<I", blob, HEADER_SIZE + 2 * 4, 16)
        with self.assertRaisesRegex(ValueError, "opcode"):
            loads(bytes(blob))

        blob = bytearray(dumps(_one_cell_program()))
        struct.pack_into("<I", blob, HEADER_SIZE + 8 * 4, 0xFFFFFFFF)
        with self.assertRaisesRegex(ValueError, "successor"):
            loads(bytes(blob))


class GPUParityContractTests(unittest.TestCase):
    @staticmethod
    def _extreme_programs() -> list[Program]:
        minimum = -(1 << 31)
        maximum = (1 << 31) - 1
        return [
            _one_cell_program(
                initial_state=State(phi=1),
                cell={"opcode": int(Opcode.PHI), "arg0": maximum},
            ),
            _one_cell_program(
                initial_state=State(tick=1),
                cell={"opcode": int(Opcode.TIME), "arg0": maximum},
            ),
            _one_cell_program(
                initial_state=State(rho=1),
                cell={
                    "opcode": int(Opcode.CONE),
                    "arg0": minimum,
                    "arg1": maximum,
                },
            ),
            _one_cell_program(
                initial_state=State(rho=1),
                cell={
                    "opcode": int(Opcode.SPHERE),
                    "arg0": minimum,
                    "arg3": -1,
                },
            ),
            _one_cell_program(
                initial_state=State(rho=1 << 20, theta=minimum, phi=minimum),
                cell={"opcode": int(Opcode.KLEIN)},
            ),
            _one_cell_program(
                initial_state=State(phi=maximum, branch=1),
                cell={"opcode": int(Opcode.LSYS), "arg0": maximum},
            ),
            _one_cell_program(
                cell={"opcode": int(Opcode.JIT1), "arg0": minimum},
            ),
        ]

    def test_extreme_i32_transition_oracles_are_explicit(self):
        minimum = -(1 << 31)
        maximum = (1 << 31) - 1

        state, _ = run(_one_cell_program(
            initial_state=State(phi=1),
            cell={"opcode": int(Opcode.PHI), "arg0": maximum},
        ))
        self.assertEqual((state.phi, state.branch), (0, 0))

        state, _ = run(_one_cell_program(
            initial_state=State(tick=1),
            cell={"opcode": int(Opcode.TIME), "arg0": maximum},
        ))
        self.assertEqual((state.tick, state.branch), (0, 0))

        state, _ = run(_one_cell_program(
            initial_state=State(rho=1),
            cell={
                "opcode": int(Opcode.CONE),
                "arg0": minimum,
                "arg1": maximum,
            },
        ))
        self.assertEqual((state.residual, state.branch), (0, 1))

        state, _ = run(_one_cell_program(
            initial_state=State(rho=1),
            cell={
                "opcode": int(Opcode.SPHERE),
                "arg0": minimum,
                "arg3": -1,
            },
        ))
        self.assertEqual((state.residual, state.branch), (-maximum, 1))

        state, _ = run(_one_cell_program(
            initial_state=State(rho=1 << 20, theta=minimum, phi=minimum),
            cell={"opcode": int(Opcode.KLEIN)},
        ))
        self.assertEqual((state.theta, state.phi), (1 << 17, 0))

        state, _ = run(_one_cell_program(
            initial_state=State(phi=maximum, branch=1),
            cell={"opcode": int(Opcode.LSYS), "arg0": maximum},
        ))
        self.assertEqual(state.phi, 4094)

        state, _ = run(_one_cell_program(
            cell={"opcode": int(Opcode.JIT1), "arg0": minimum},
        ))
        self.assertEqual(state.rho, minimum)

    @unittest.skipIf(os.name == "nt", "the checked C executable is a WSL binary")
    def test_extreme_i32_oracles_match_c_backend(self):
        executable = ROOT / "build/tomagi-c"
        if not executable.is_file():
            self.skipTest("C backend is not built")
        with tempfile.TemporaryDirectory() as directory:
            for index, program in enumerate(self._extreme_programs()):
                with self.subTest(index=index, opcode=program.cells[0].opcode):
                    expected, _ = run(program)
                    path = Path(directory) / f"extreme-{index}.tmg"
                    path.write_bytes(dumps(program))
                    actual = json.loads(subprocess.check_output(
                        [str(executable), str(path)], text=True
                    ))
                    self.assertEqual(
                        actual,
                        {
                            name: getattr(expected, name)
                            for name in expected.__dataclass_fields__
                        },
                    )

    def test_gpu_sources_keep_overflow_safe_helpers_and_radix_guard(self):
        contracts = {
            "tomagi_step.wgsl": (
                ("fn addDivmod", "fn wideSubI32", "0u-c.args.x", "a0<0 || a0>=64"),
                ("select(-a0", "abs(a3)", "bitcast<u32>(-bitcast<i32>(s.q.w))"),
            ),
            "tomagi_step.comp": (
                ("ivec2 addDivmod", "WideI32 wideSubI32", "0u-c.args.x", "a0<0 || a0>=64"),
                ("?a0:-a0", "abs(a3)", "uint(-int(s.q.w))"),
            ),
            "tomagi_step.cl": (
                ("int2 add_divmod", "WideI32 wide_sub_i32", "0u-c.args.x", "a.x<0||a.x>=64"),
                ("?a.x:-a.x", "abs(a.w)", "as_uint(-as_int(s.q.w))"),
            ),
        }
        for filename, (required, forbidden) in contracts.items():
            source = (ROOT / "src/gpu" / filename).read_text(encoding="utf-8")
            with self.subTest(filename=filename):
                for marker in required:
                    self.assertIn(marker, source)
                for marker in forbidden:
                    self.assertNotIn(marker, source)


if __name__ == "__main__":
    unittest.main()
