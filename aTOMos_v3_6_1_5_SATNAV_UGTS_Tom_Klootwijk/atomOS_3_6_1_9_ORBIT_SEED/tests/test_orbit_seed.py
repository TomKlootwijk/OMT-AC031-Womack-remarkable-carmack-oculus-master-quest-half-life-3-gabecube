"""Seed contracts and horizon cases; physical forecasts validated against real data separately."""
from copy import deepcopy
import math
import json
from pathlib import Path
import sys
import random
import struct
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from orbit_query import find_events
from orbit_seed import (HEADER, default_feedback, default_query, default_stations,
                        bitplanes_to_words, words_to_bitplanes, digest, inspect_bytes,
                        pack_bytes, transition_ast, unpack_bytes, validate)


def fixture():
    model = json.loads((Path(__file__).resolve().parents[1] / "examples/orbit/models/G05.json").read_text())["model"]
    model["state_gcrs"][1] = -0.
    return {"profile": "ORBIT-SEED-R1", "version": "3.6.1.9", "object": {"id": "format_fixture", "orbit_class": "synthetic"},
            "model": model,
            "stations": default_stations(), "query": default_query(), "feedback": default_feedback(),
            "provenance": {"role": "Format fixture, not a physical prediction"}}


class SeedTests(unittest.TestCase):
    def test_bitplanes_preserve_every_bit_and_lane(self):
        words = [1 << bit for bit in range(64)]
        data = words_to_bitplanes(words)
        self.assertEqual(list(struct.unpack("<64Q", data)), words)
        self.assertEqual(bitplanes_to_words(data, 64), words)
        rng = random.Random(3619)
        for count in (0, 1, 63, 64, 65, 129):
            words = [rng.getrandbits(64) for _ in range(count)]
            self.assertEqual(bitplanes_to_words(words_to_bitplanes(words), count), words)

    def test_bitplanes_reject_padding_and_wrong_length(self):
        data = bytearray(words_to_bitplanes([0]))
        data[0] = 2
        with self.assertRaises(ValueError): bitplanes_to_words(data, 1)
        with self.assertRaises(ValueError): bitplanes_to_words(bytes(511), 1)
        with self.assertRaises(ValueError): words_to_bitplanes([-1])

    def test_codec_compatibility_and_full_numeric_bit_patterns(self):
        seed = fixture()
        seed["provenance"]["numeric_fixture"] = [-0., 0., float.fromhex("0x0.0000000000001p-1022"),
            float.fromhex("0x1.fffffffffffffp+1023"), -(1 << 63), (1 << 64) - 1]
        legacy = pack_bytes(seed, codec="canonical-zlib")
        planes = pack_bytes(seed, codec="bitplanes64-zlib")
        self.assertEqual(inspect_bytes(planes)["codec"], "bitplanes64-zlib")
        self.assertEqual(digest(unpack_bytes(legacy)), digest(unpack_bytes(planes)))
        self.assertEqual(pack_bytes(unpack_bytes(planes)), planes)
        self.assertEqual(pack_bytes(unpack_bytes(legacy), codec="canonical-zlib"), legacy)
        self.assertEqual(inspect_bytes(planes)["seed_sha256"], inspect_bytes(legacy)["seed_sha256"])

    def test_exact_binary_roundtrip_and_key_order(self):
        seed = fixture()
        data = pack_bytes(seed)
        other = {k: seed[k] for k in reversed(seed)}
        self.assertEqual(pack_bytes(other), data)
        self.assertEqual(unpack_bytes(data), seed)
        self.assertEqual(math.copysign(1., unpack_bytes(data)["model"]["state_gcrs"][1]), -1.)
        self.assertNotEqual(digest(seed["model"]), digest(seed))

    def test_tamper_every_payload_region(self):
        data = pack_bytes(fixture())
        for index in (0, 8, 10, 12, 16, 20, HEADER.size, len(data) - 1):
            bad = bytearray(data); bad[index] ^= 1
            with self.assertRaises((ValueError, UnicodeError)): unpack_bytes(bytes(bad))
        for bad in (data[:-1], data + b"x", data[:HEADER.size - 1]):
            with self.assertRaises(ValueError): unpack_bytes(bad)

    def test_unknown_fields_nonfinite_and_missing_sets(self):
        for change in (lambda s: s.update(extra=1), lambda s: s["query"].update(end_s=float("nan")),
                       lambda s: s["feedback"]["sets"].pop(),
                       lambda s: s["feedback"]["equations"].update(x="q + d")):
            seed = fixture(); change(seed)
            with self.assertRaises(ValueError): pack_bytes(seed)

    def test_r2_rejects_ignored_legacy_force_and_frame_fields(self):
        for container, field in (("force", "j2"), ("force", "c22"), ("frame", "xp_rad")):
            seed = fixture()
            self.assertEqual(seed["model"]["profile"], "ORBIT-DYNAMICS-R2")
            seed["model"][container][field] = 0.
            with self.assertRaises(ValueError): pack_bytes(seed)

    def test_encoder_rejects_decoder_structural_limit_violations(self):
        for value in ([""] * 100001, [[""] * 99999] * 3):
            for codec in ("canonical-zlib", "bitplanes64-zlib"):
                seed = fixture(); seed["provenance"]["oversized"] = value
                with self.assertRaises(ValueError): pack_bytes(seed, codec=codec)

    def test_both_vacuum_sets_have_whole_word_effect(self):
        f = default_feedback()
        f["equations"] = {"x": "d", "j": "y", "k": "~y"}
        f["sets"][0]["boundary_mask"] = 4
        a = transition_ast(f, 31, 5)
        self.assertEqual(a["stages"][0]["output"], 0)
        self.assertEqual(a["after"], 0)
        f["sets"][0]["boundary_mask"] = 0
        f["sets"][1]["boundary_mask"] = 4
        b = transition_ast(f, 31, 5)
        self.assertEqual(b["stages"][0]["output"], 5)
        self.assertEqual(b["stages"][1]["output"], 0)
        self.assertEqual(b["after"], 0)
        f["sets"][1]["boundary_mask"] = 0
        self.assertEqual(transition_ast(f, 31, 5)["after"], 5)

    def test_jk_toggle_is_synchronous(self):
        f = default_feedback(); f["equations"].update(j="1", k="1")
        self.assertEqual(transition_ast(f, 5, 0)["after"], 26)


class HorizonTests(unittest.TestCase):
    def test_visible_hidden(self):
        for value, expected in ((.4, "visible_over_searched_interval"), (-.4, "hidden_over_searched_interval")):
            result = find_events(lambda t: (value, 0.), 0., 1000., 100.)
            self.assertEqual(result["classification"], expected)
            self.assertEqual(result["events"], [])

    def test_short_pass_caught_by_derivative_extremum(self):
        result = find_events(lambda t: (.0001 - (t - 50.)**2 / 1.e6, -2 * (t - 50.) / 1.e6), 0., 100., 100., 1.e-7)
        self.assertEqual([e["kind"] for e in result["events"]], ["rise", "set"])
        self.assertAlmostEqual(result["events"][0]["time_s"], 40., places=6)
        self.assertAlmostEqual(result["events"][1]["time_s"], 60., places=6)

    def test_grazing_is_explicit(self):
        result = find_events(lambda t: (-(t - 50.)**2 / 1.e6, -2 * (t - 50.) / 1.e6), 0., 100., 100.)
        self.assertEqual(result["grazing_candidates_s"], [50.])
        self.assertIn("no certified", result["coverage"])

    def test_multiple_crossings_and_invalid_domain(self):
        result = find_events(lambda t: (math.sin(t), math.cos(t)), .1, 15., .5, 1.e-7)
        self.assertEqual(len(result["events"]), 4)
        for i, row in enumerate(result["events"], 1): self.assertAlmostEqual(row["time_s"], i * math.pi, places=6)
        with self.assertRaises(ValueError): find_events(lambda t: (1., 0.), 0., 1., 0.)


if __name__ == "__main__": unittest.main()
