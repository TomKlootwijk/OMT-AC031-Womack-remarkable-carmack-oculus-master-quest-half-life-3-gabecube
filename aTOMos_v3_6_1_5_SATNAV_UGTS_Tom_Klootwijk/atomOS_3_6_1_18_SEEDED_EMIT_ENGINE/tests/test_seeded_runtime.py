"""Meaningful admission/tampering checks for the native artifact verifier.

Passing these CPU tests does not claim GPU execution; root runs the native path
and passes its actual files to verify_seeded_runtime.py separately.
"""
from pathlib import Path
import copy
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_seeded_fixtures as build
import verify_seeded_runtime as verify


class SeededRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = verify.replay_reference("world03")
        r = cls.reference
        cls.ticks = r["executed_steps"] + 3
        cls.native = {"profile": "ATOMOS-EMIT-JOURNAL-R1", "status": "complete",
                      "owner_id": 1, "generation": 1, "start_epoch": 0,
                      "end_epoch": cls.ticks, "error": 0,
                      "program_flags": r["program_flags"], "program_bytes": r["program_bytes"],
                      "event_count": len(r["events"]), "output_bytes": len(r["output"]),
                      "artifact_written": True, "expanded_source_bytes_equal_input": True,
                      "final_state_words": r["final_state_words"], "events": r["events"]}

    def check(self, native=None, output=None, ticks=None):
        return verify.compare_native(self.reference, self.native if native is None else native,
                                     self.reference["output"] if output is None else output,
                                     self.ticks if ticks is None else ticks)

    def test_complete_reference_accepted(self):
        self.assertEqual(self.check()["compared_events"], 866)

    def test_completion_evidence_requires_literal_true(self):
        for field in ("artifact_written", "expanded_source_bytes_equal_input"):
            for replacement in (None, False, 0, 1, "true"):
                with self.subTest(field=field, replacement=replacement):
                    row = copy.deepcopy(self.native)
                    if replacement is None:
                        del row[field]
                    else:
                        row[field] = replacement
                    with self.assertRaises(ValueError):
                        self.check(row)

    def test_every_event_field_is_checked(self):
        for field in verify.EVENT_FIELDS:
            with self.subTest(field=field):
                row = copy.deepcopy(self.native)
                value = row["events"][431][field]
                row["events"][431][field] = "big" if field == "byte_order" else value ^ 1
                with self.assertRaises(ValueError):
                    self.check(row)

    def test_truncated_duplicated_and_reordered_journals_reject(self):
        for kind in ("truncated", "duplicated", "reordered"):
            with self.subTest(kind=kind):
                row = copy.deepcopy(self.native)
                if kind == "truncated":
                    row["events"].pop()
                elif kind == "duplicated":
                    row["events"][5] = copy.deepcopy(row["events"][4])
                else:
                    row["events"][5], row["events"][6] = row["events"][6], row["events"][5]
                row["event_count"] = len(row["events"])
                with self.assertRaises(ValueError):
                    self.check(row)

    def test_middle_byte_and_truncated_output_reject(self):
        output = bytearray(self.reference["output"])
        output[1234] ^= 1
        for wrong in (bytes(output), self.reference["output"][:-1]):
            with self.assertRaises(ValueError):
                self.check(output=wrong)

    def test_all_final_state_words_checked(self):
        for word in range(16):
            with self.subTest(word=word):
                row = copy.deepcopy(self.native)
                row["final_state_words"][word] ^= 1
                with self.assertRaises(ValueError):
                    self.check(row)

    def test_prefix_fault_and_epoch_mismatch_reject(self):
        for field, value in (("status", "prefix"), ("status", "faulted"), ("error", 1),
                             ("end_epoch", self.ticks - 1), ("start_epoch", 1)):
            row = copy.deepcopy(self.native)
            row[field] = value
            with self.assertRaises(ValueError):
                self.check(row)
        with self.assertRaises(ValueError):
            self.check(ticks=1)

    def test_boolean_integer_and_duplicate_json_key_reject(self):
        row = copy.deepcopy(self.native)
        row["events"][0]["epoch"] = False
        with self.assertRaises(ValueError):
            self.check(row)
        with self.assertRaises(ValueError):
            build.strict_json('{"status":"complete","status":"prefix"}')

    def test_pinned_seed_and_definition_tampering_reject(self):
        compiler, _, _, _, _, canonical = build.imports()
        source = build.SOURCES / build.SPECS["world03"]["source"]
        document = build.strict_json(source.read_bytes())
        seed = (build.SOURCES / "TOM_seed_genome_2026-09-01.txt").read_bytes()
        registry = build.strict_json((build.SOURCES / "spec/tom_seed_token_registry_1_0.json").read_bytes())
        with self.assertRaises(ValueError):
            compiler.compile_document(document, seed_bytes=seed + b"\n", token_registry=registry, source_root=source.parent)
        damaged = copy.deepcopy(document)
        damaged["definitions"][2]["parameters"]["value"]["data"] += "A"
        with self.assertRaises(ValueError):
            compiler.compile_document(damaged, seed_bytes=seed, token_registry=registry, source_root=source.parent)
        damaged = copy.deepcopy(document)
        damaged["definitions"][-1]["dependencies"][0] = "missing:definition"
        damaged["definitions"][-1] = canonical.attach_hash(damaged["definitions"][-1])
        with self.assertRaises(ValueError):
            compiler.compile_document(damaged, seed_bytes=seed, token_registry=registry, source_root=source.parent)

    def test_source_byte_receipt_tampering_rejects_before_formal_evaluation(self):
        compiler, _, _, _, _, _ = build.imports()
        source = build.SOURCES / build.SPECS["family_authority"]["source"]
        document = build.strict_json(source.read_bytes())
        seed = (build.SOURCES / "TOM_seed_genome_2026-09-01.txt").read_bytes()
        registry = build.strict_json((build.SOURCES / "spec/tom_seed_token_registry_1_0.json").read_bytes())
        first = next(d for d in document["definitions"] if d["operation"]["op"] == "source.json")
        with tempfile.TemporaryDirectory(prefix="r18-admission-") as temp:
            target = Path(temp) / first["parameters"]["path"]
            target.write_bytes((source.parent / first["parameters"]["path"]).read_bytes() + b" ")
            with self.assertRaisesRegex(ValueError, "byte|SHA|length"):
                compiler.compile_document(document, seed_bytes=seed, token_registry=registry, source_root=temp)


if __name__ == "__main__":
    unittest.main()
