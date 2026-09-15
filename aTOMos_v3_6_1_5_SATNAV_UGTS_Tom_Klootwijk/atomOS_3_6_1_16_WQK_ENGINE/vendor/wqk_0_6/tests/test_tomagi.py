from __future__ import annotations

import json
import os
import struct
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _c_backend_command(executable: Path, program: Path, *args: str) -> list[str]:
    if os.name != "nt":
        return [str(executable), str(program), *args]

    def wsl_path(path: Path) -> str:
        resolved = str(path.resolve()).replace("\\", "/")
        if len(resolved) < 3 or resolved[1:3] != ":/":
            raise RuntimeError(f"cannot map Windows path into WSL: {resolved}")
        return f"/mnt/{resolved[0].lower()}/{resolved[3:]}"

    return ["wsl.exe", wsl_path(executable), wsl_path(program), *args]

from tomagi.canonical import attach_hash, canonical_bytes, content_hash, verify_hash
from tomagi.compiler import compile_document, definition_order
from tomagi.core import (
    Cell,
    Opcode,
    Program,
    State,
    STATUS_CONE,
    STATUS_EMIT,
    STATUS_HALT,
    STATUS_SPHERE,
    STATUS_WRAP,
    STATUS_ZERO,
    FLAG_KLEIN_FLIP_SHEET,
    FLAG_KLEIN_SOURCE_HALF_TURN,
    FLAG_PHI_BRANCH_HALF,
    PHI_STATES,
    RHO_STATES,
    THETA_STATES,
    TIME_STATES,
    key_as_u64,
    mix32,
    pack_key_contiguous,
    pack_key_morton,
    run,
    step,
    unpack_key_contiguous,
    unpack_key_morton,
    zero_field,
)
from tomagi.format import CELL_SIZE, HEADER_SIZE, STATE_SIZE, dumps, loads
from tomagi.knowledge import active_bit_positions, nineteen_demo, regular_pulse_geometry


def one_cell(op: Opcode, *, state: State | None = None, args=(0, 0, 0, 0),
             flags=0, payload=0, aux=0) -> tuple[Program, State]:
    cell = Cell(0, 0, int(op), flags, *args, 0, 0, payload, aux)
    initial = state or State()
    program = Program([cell], 0, 0xA5A5A5A5, 1, initial)
    return program, replace(initial)


class CanonicalTests(unittest.TestCase):
    def test_canonical_hash_is_stable_and_semantic(self):
        a = {"b": 2, "a": [1, 3]}
        b = {"a": [1, 3], "b": 2}
        self.assertEqual(canonical_bytes(a), canonical_bytes(b))
        r = attach_hash({"id": "d", "kind": "literal", "parameters": a})
        self.assertTrue(verify_hash(r))
        r["parameters"] = b
        self.assertTrue(verify_hash(r))
        r["kind"] = "changed"
        self.assertFalse(verify_hash(r))

    def test_definition_order_and_cycle_rejection(self):
        defs = [
            attach_hash({"id": "b", "kind": "op", "domain": {}, "codomain": {},
                         "dependencies": ["a"], "parameters": {}}),
            attach_hash({"id": "a", "kind": "literal", "domain": {}, "codomain": {},
                         "dependencies": [], "parameters": {}}),
        ]
        self.assertEqual(definition_order(defs), ["a", "b"])
        cyclic = [
            {"id": "a", "dependencies": ["b"]},
            {"id": "b", "dependencies": ["a"]},
        ]
        with self.assertRaisesRegex(ValueError, "cycle"):
            definition_order(cyclic)


class KeyTests(unittest.TestCase):
    def test_contiguous_reference_key(self):
        q = (949111, 0, 1920, 227)
        hi, lo = pack_key_contiguous(*q)
        self.assertEqual(key_as_u64(hi, lo), 0xE7B77000007800E3)
        self.assertEqual(unpack_key_contiguous(hi, lo), q)

    def test_morton_reference_key(self):
        q = (949111, 0, 1920, 227)
        hi, lo = pack_key_morton(*q)
        self.assertEqual(key_as_u64(hi, lo), 0x88823BB88099128B)
        self.assertEqual(unpack_key_morton(hi, lo), q)

    def test_modular_roundtrip(self):
        q = (-1, THETA_STATES + 7, TIME_STATES + 8, PHI_STATES + 9)
        hi, lo = pack_key_contiguous(*q)
        self.assertEqual(unpack_key_contiguous(hi, lo),
                         (RHO_STATES - 1, 7, 8, 9))


class PrimitiveOperatorTests(unittest.TestCase):
    def test_sdf0_is_zero_only_on_declared_domain(self):
        k0 = pack_key_contiguous(1, 2, 3, 4)
        k1 = pack_key_contiguous(5, 6, 7, 8)
        self.assertEqual(zero_field([k0], *k0), 0)
        self.assertIsNone(zero_field([k0], *k1))
        p, s = one_cell(Opcode.SDF0)
        step(p, s)
        self.assertEqual(s.residual, 0)
        self.assertEqual(s.branch, 1)
        self.assertTrue(s.status & STATUS_ZERO)

    def test_mix32_is_reproducible(self):
        self.assertEqual(mix32(0), 0)
        self.assertEqual(mix32(0x12345678), 0xF5E71C96)
        self.assertEqual(mix32(0xFFFFFFFF), 0x6768824A)

    def test_jit1_is_deterministic_and_bipolar(self):
        p, s0 = one_cell(Opcode.JIT1, state=State(phi=100), args=(3, 0, 0, 0), flags=3, aux=7)
        a = replace(s0)
        b = replace(s0)
        step(p, a)
        step(p, b)
        self.assertEqual(a.words(), b.words())
        self.assertIn(a.phi, (97, 103))
        self.assertIn(a.branch, (0, 1))

    def test_kin2_change_of_change(self):
        p, s = one_cell(Opcode.KIN2, state=State(rho=10, theta=20, tick=30, phi=40,
                                                 vrho=1, vtheta=2, vtick=3, vphi=4),
                        args=(5, -1, 2, -3))
        step(p, s)
        self.assertEqual((s.vrho, s.vtheta, s.vtick, s.vphi), (6, 1, 5, 1))
        self.assertEqual((s.rho, s.theta, s.tick, s.phi), (16, 21, 35, 41))

    def test_phi_half_branch(self):
        p, s = one_cell(Opcode.PHI, state=State(phi=2000), args=(100, 0, 0, 0),
                        flags=FLAG_PHI_BRANCH_HALF)
        step(p, s)
        self.assertEqual(s.phi, 2100)
        self.assertEqual(s.branch, 1)

    def test_reflective_klein_wrap(self):
        p, s = one_cell(Opcode.KLEIN,
                        state=State(rho=RHO_STATES + 8, theta=7, phi=1995,
                                    orientation=0, sheet=0),
                        flags=FLAG_KLEIN_FLIP_SHEET)
        step(p, s)
        self.assertEqual(s.rho, 8)
        self.assertEqual(s.theta, THETA_STATES // 2 - 7)
        self.assertEqual(s.phi, (-1995) % PHI_STATES)
        self.assertEqual((s.orientation, s.sheet, s.branch), (1, 1, 1))
        self.assertTrue(s.status & STATUS_WRAP)

    def test_source_half_turn_is_distinct(self):
        p, s = one_cell(Opcode.KLEIN,
                        state=State(rho=RHO_STATES + 1, theta=9, phi=3),
                        flags=FLAG_KLEIN_SOURCE_HALF_TURN)
        step(p, s)
        self.assertEqual(s.theta, (9 + THETA_STATES // 2) % THETA_STATES)

    def test_cone_relation(self):
        p, s = one_cell(Opcode.CONE, state=State(rho=100, theta=20),
                        args=(50, 150, 20, 10))
        step(p, s)
        self.assertLessEqual(s.residual, 0)
        self.assertEqual(s.branch, 1)
        self.assertTrue(s.status & STATUS_CONE)

    def test_sphere_shell_relation(self):
        p, s = one_cell(Opcode.SPHERE, state=State(rho=100, phi=200),
                        args=(100, 5, 200, 8))
        step(p, s)
        self.assertLessEqual(s.residual, 0)
        self.assertTrue(s.status & STATUS_SPHERE)

    def test_lsystem_chirality(self):
        p0, s0 = one_cell(Opcode.LSYS, state=State(phi=100, branch=1, orientation=0,
                                                   vrho=9, vtheta=-9, vtick=3, vphi=-3),
                          args=(64, 1, 0, 0))
        step(p0, s0)
        self.assertEqual(s0.phi, 164)
        self.assertEqual((s0.vrho, s0.vtheta, s0.vtick, s0.vphi), (4, -4, 1, -1))
        p1, s1 = one_cell(Opcode.LSYS, state=State(phi=100, branch=1, orientation=1),
                          args=(64, 0, 0, 0))
        step(p1, s1)
        self.assertEqual(s1.phi, 36)


class FormatCompilerTests(unittest.TestCase):
    def test_record_sizes(self):
        self.assertEqual(HEADER_SIZE, 128)
        self.assertEqual(STATE_SIZE, struct.calcsize("<16I"))
        self.assertEqual(CELL_SIZE, struct.calcsize("<12I"))

    def test_binary_roundtrip(self):
        p, _ = one_cell(Opcode.EMIT, state=State(rho=-4, lineage=123), payload=42, flags=1)
        blob = dumps(p)
        self.assertEqual(len(blob), HEADER_SIZE + CELL_SIZE)
        q = loads(blob)
        self.assertEqual(q.initial_state.words(), p.initial_state.words())
        self.assertEqual(q.cells[0].words(), p.cells[0].words())

    def test_example_schema(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema not installed")
        schema = json.loads((ROOT / "spec/tomagi.schema.json").read_text())
        for name in ("polar_loop.json", "exact19_rule.json"):
            doc = json.loads((ROOT / "examples" / name).read_text())
            jsonschema.Draft202012Validator(schema).validate(doc)

    def test_compile_rejects_bad_hash(self):
        doc = json.loads((ROOT / "examples/polar_loop.json").read_text())
        doc["definitions"][0]["kind"] = "tampered"
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            compile_document(doc)


class EndToEndTests(unittest.TestCase):
    def test_polar_loop_reference_result(self):
        doc = json.loads((ROOT / "examples/polar_loop.json").read_text())
        p = compile_document(doc)
        state, trace = run(p, trace=True)
        self.assertEqual(len(trace), 8)
        self.assertEqual(state.output, 0x50595241)  # PYRA
        self.assertEqual(state.rho, 8)
        self.assertEqual(state.theta, 39)
        self.assertEqual(state.phi, 2181)
        self.assertEqual(state.sheet, 1)
        self.assertEqual(state.lineage, 3655609768)
        self.assertTrue(state.status & STATUS_HALT)
        self.assertTrue(state.status & STATUS_EMIT)

    def test_compiled_exact19_accept_and_reject(self):
        doc = json.loads((ROOT / "examples/exact19_rule.json").read_text())
        p = compile_document(doc)
        accepted, _ = run(p)
        self.assertEqual(accepted.output, 19)
        rejected, _ = run(p, state=replace(p.initial_state, rho=18, cell=p.entry))
        self.assertEqual(rejected.output, 0)

    def test_nineteen_source_projection(self):
        result = nineteen_demo().output
        self.assertEqual(result["binary"], "10011")
        self.assertEqual(result["active_bit_positions"], [0, 1, 4])
        self.assertEqual(result["active_bit_count"], 3)
        self.assertEqual(result["profile_segments"], ["ne", "gen", "tien"])
        self.assertTrue(result["equal_feature_counts"])
        self.assertEqual(result["projection"]["kind"], "triangle")

    def test_catalog_and_crosswalk_cover_project_sources(self):
        ops = json.loads((ROOT / "spec/operator_catalog.json").read_text())
        cross = json.loads((ROOT / "spec/source_crosswalk.json").read_text())
        self.assertEqual(ops["count"], 43)
        self.assertEqual(cross["count"], 319)
        sources = {row["source"].split(":", 1)[0] for row in cross["rows"]}
        self.assertTrue({"SRC-A", "SRC-B", "SRC-C", "SRC-D", "SRC-E", "SRC-F", "SRC-G"}.issubset(sources))

    def test_c_backend_matches_python_when_available(self):
        exe = ROOT / "build/tomagi-c"
        program_path = ROOT / "examples/polar_loop.tmg"
        if not exe.exists() or not program_path.exists():
            self.skipTest("C backend or compiled example not built")
        expected = json.loads((ROOT / "examples/polar_loop.expected.json").read_text())["state"]
        actual = json.loads(subprocess.check_output(
            _c_backend_command(exe, program_path), text=True
        ))
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
