"""Behavior and independent replay checks for actual SRK-R1 equation inputs."""
from pathlib import Path
import copy
import csv
import json
import random
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from self_reference import (INPUT_FIELDS, TRACE_FIELDS, WORD, compile_lut, load_document,
                            parse_document, parse_expression, replay, transition, write_compiled)


def document(**changes):
    trajectory = {"id": 0, "q0": 0, "drive": 5, "present": 15, "asa_mask": 15,
                  "na_mask": 15, "boundary_mask": 0, "steps": 4}
    trajectory.update(changes)
    return {"version": "3.6.1.6", "profile": "SRK-R1",
            "equations": {"x": "q | d", "j": "y", "k": "0"},
            "trajectories": [trajectory]}


def scalar_lut(table, words):
    """Bit-at-a-time LUT oracle, independent from the full-word expression evaluator."""
    result = 0
    for bit in range(32):
        index = 0
        for word in words:
            index = (index << 1) | ((word >> bit) & 1)
        result |= ((table >> index) & 1) << bit
    return result


class EquationTests(unittest.TestCase):
    def test_literals_precedence_and_complement_are_word_semantics(self):
        values = {"q": 0xA50F8000, "d": 0xF00F00AA}
        cases = {
            "0": 0, "1": WORD, "~0": WORD, "~1": 0,
            "q | d & ~q": values["q"] | values["d"],
            "(q | d) & ~(q & d)": values["q"] ^ values["d"],
            "~~q": values["q"],
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(parse_expression(source, ("q", "d")).evaluate(values), expected)

    def test_exact_truth_table_input_order(self):
        for source, table in (("q", 12), ("d", 10), ("q | d", 14), ("q ^ d", 6)):
            self.assertEqual(compile_lut(parse_expression(source, ("q", "d"))), table)
        for source, table in (("q", 240), ("y", 204), ("d", 170), ("1", 255)):
            self.assertEqual(compile_lut(parse_expression(source, ("q", "y", "d"))), table)

    def test_parser_rejects_executable_or_ambiguous_syntax(self):
        invalid = ["__import__('os')", "q.real", "q[0]", "q + d", "q << 1", "not q",
                   "q and d", "q if d else 0", "True", "False", "2", "1.0", "-1", "y", "", "q,d"]
        for source in invalid:
            with self.subTest(source=source), self.assertRaises(ValueError):
                parse_expression(source, ("q", "d"))

    def test_word_ast_agrees_with_independent_scalar_lut(self):
        rng = random.Random(3616)
        sources = ["q", "~q", "q ^ d", "(q | d) & ~y", "(~q & y) | (q & d)",
                   "(q & ~y) | (~q & d)", "~(q ^ (y | d))", "1"]
        for source in sources:
            expression = parse_expression(source, ("q", "y", "d"))
            table = compile_lut(expression)
            for _ in range(64):
                values = {name: rng.getrandbits(32) for name in expression.variables}
                self.assertEqual(expression.evaluate(values), scalar_lut(table, list(values.values())))

    def test_partial_equation_override_and_canonical_hash(self):
        original = parse_document(document())[0]
        equivalent = parse_document(document(equations={"x": " ( q | d ) "}))[0]
        changed = parse_document(document(equations={"k": "y"}))[0]
        self.assertEqual(original.equation_hash, equivalent.equation_hash)
        self.assertNotEqual(original.equation_hash, changed.equation_hash)
        self.assertEqual(equivalent.equations["j"].source, "y")
        other_drive = parse_document(document(drive=6))[0]
        self.assertEqual(original.equation_hash, other_drive.equation_hash)
        self.assertNotEqual(original.specification_hash, other_drive.specification_hash)

    def test_input_domains_duplicates_and_missing_equations(self):
        for changes in ({"q0": 16}, {"steps": 0}, {"steps": -1}, {"drive": WORD + 1},
                        {"q0": True}, {"id": 1 << 64}, {"steps": 1 << 64}, {"typo": 0}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                parse_document(document(**changes))
        duplicate = document()
        duplicate["trajectories"] *= 2
        with self.assertRaises(ValueError):
            parse_document(duplicate)
        missing = document()
        del missing["equations"]["k"]
        with self.assertRaises(ValueError):
            parse_document(missing)
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "input.json"
            source.write_text('{"version":"3.6.1.6","version":"3.6.1.6"}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
                load_document(source)

    def test_latch_fixed_point_and_toggle_cycle(self):
        latch = replay(parse_document(document()))["trajectories"][0]
        self.assertEqual(latch["final_state"], 5)
        self.assertEqual(latch["orbit"], {"kind": "fixed_point", "entry_step": 1,
                         "period": 1, "first_repeat_step": 2, "repeated_state": 5})
        toggle = replay(parse_document(document(drive=15, equations={"k": "y"})))["trajectories"][0]
        self.assertEqual(toggle["orbit"]["kind"], "cycle")
        self.assertEqual(toggle["orbit"]["period"], 2)
        self.assertEqual(toggle["final_state"], 0)
        limited = replay(parse_document(document(steps=1)))["trajectories"][0]
        self.assertEqual(limited["orbit"]["kind"], "no_repeat_observed")

    def test_whole_word_absorption_is_not_per_bit_clearing(self):
        trajectory = parse_document(document(q0=2, drive=15, boundary_mask=8))[0]
        row = transition(trajectory, 2, 0)
        self.assertEqual((row["asa"], row["na"], row["hits"], row["output"]), (15, 15, 1, 0))
        self.assertEqual(row["after"], 2)

    def test_jk_uses_old_q_synchronously_and_masks_only_after(self):
        trajectory = parse_document(document(q0=10, drive=0, equations={"j": "~q", "k": "q"}))[0]
        row = transition(trajectory, 10, 0)
        self.assertEqual(row["j"], WORD ^ 10)
        self.assertEqual(row["k"], 10)
        self.assertEqual(row["after"], 5)
        high = parse_document(document(q0=1 << 31, present=1 << 31,
                                       asa_mask=WORD, na_mask=WORD, equations={"j": "1", "k": "1"}))[0]
        self.assertEqual(transition(high, 1 << 31, 0)["after"], 0)
        self.assertEqual(transition(high, 0, 1)["after"], 1 << 31)

    def test_boundary_absorption_does_not_override_explicit_j_equation(self):
        trajectory = parse_document(document(q0=0, drive=15, boundary_mask=8,
                                              equations={"j": "1", "k": "0"}))[0]
        row = transition(trajectory, 0, 0)
        self.assertEqual(row["output"], 0)
        self.assertEqual(row["after"], 15)

    def test_compilation_and_every_trace_field_mutation_rejected(self):
        trajectories = parse_document(document())
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            write_compiled(trajectories, folder / "input.csv")
            with (folder / "input.csv").open(newline="") as stream:
                reader = csv.DictReader(stream)
                self.assertEqual(tuple(reader.fieldnames), INPUT_FIELDS)
                row = next(reader)
                self.assertEqual((row["x_lut"], row["j_lut"], row["k_lut"]), ("14", "204", "0"))
            path = folder / "trace.csv"
            replay(trajectories, trace_path=path)
            report = replay(trajectories, actual_path=path)
            self.assertTrue(report["native_trace_verified"])
            self.assertEqual(report["field_comparisons"], 4 * len(TRACE_FIELDS))
            with path.open(newline="") as stream:
                rows = list(csv.DictReader(stream))
            for field in TRACE_FIELDS:
                damaged = copy.deepcopy(rows)
                damaged[1][field] = str(int(damaged[1][field]) ^ 1)
                mutation = folder / (field + ".csv")
                with mutation.open("w", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=TRACE_FIELDS)
                    writer.writeheader()
                    writer.writerows(damaged)
                with self.subTest(field=field), self.assertRaises(ValueError):
                    replay(trajectories, actual_path=mutation)
            for name, altered in (("short", rows[:-1]), ("long", rows + rows[-1:]),
                                  ("reordered", list(reversed(rows)))):
                mutation = folder / (name + ".csv")
                with mutation.open("w", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=TRACE_FIELDS)
                    writer.writeheader()
                    writer.writerows(altered)
                with self.subTest(name=name), self.assertRaises(ValueError):
                    replay(trajectories, actual_path=mutation)

    def test_examples_have_real_feedback_and_reproducible_compilation(self):
        examples = load_document(ROOT / "examples" / "self_reference" / "equations.json")
        summary = replay(examples)
        self.assertEqual(summary["transitions"], 34)
        self.assertEqual([item["orbit"]["kind"] for item in summary["trajectories"]],
                         ["fixed_point", "cycle", "fixed_point", "cycle", "cycle", "fixed_point"])
        # For id 4, literal substitution gives q: 10 -> 6 -> 2 -> 6.
        state = 10
        expected_states = [6, 2, 6]
        for step, expected in enumerate(expected_states):
            state = transition(examples[4], state, step)["after"]
            self.assertEqual(state, expected)
        self.assertEqual(summary["trajectories"][4]["orbit"]["entry_step"], 1)
        self.assertEqual(summary["trajectories"][4]["orbit"]["period"], 2)
        self.assertEqual(summary["trajectories"][-1]["finite_state_count"], 1)

    def test_cli_reference_and_existing_output_protection(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "new_result"
            command = [sys.executable, str(ROOT / "tools" / "self_reference.py"),
                       "--input", str(ROOT / "examples" / "self_reference" / "equations.json"),
                       "--out", str(out)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            summary = json.loads((out / "summary.json").read_text())
            self.assertEqual(summary["native_execution"], "not_run")
            self.assertFalse(summary["native_trace_verified"])
            self.assertTrue((out / "equations.json").is_file())
            original = (out / "summary.json").read_bytes()
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual((out / "summary.json").read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
