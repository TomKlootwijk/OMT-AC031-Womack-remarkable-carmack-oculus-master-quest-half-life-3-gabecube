import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
import sdf_atlas as sdf


class SdfAtlasTests(unittest.TestCase):
    def test_known_klein_distance_differs_from_torus(self):
        c = sdf.prepare_config(sdf.default_config("geometry"))
        # Asymmetric center near the angular seam: nearest odd image reflects u.
        self.assertAlmostEqual(float(sdf.quotient_distance(.77, .99, [.23, .02])), .03, places=14)
        self.assertLess(float(sdf.evaluate_sdf(c, "na", .77, .99)), 0.)
        self.assertGreater(float(sdf.evaluate_sdf(c, "na", .23, .99)), 0.)
        torus_distance = math.hypot(min(abs(.77-.23), 1-abs(.77-.23)), .03)
        self.assertGreater(torus_distance, .18)

    def test_scalar_deck_reference_and_negative_seams(self):
        for profile in ("geometry", "nor_sites"):
            c = sdf.prepare_config(sdf.default_config(profile, 17, 96))
            for plane in sdf.PLANES:
                for u, v in ((.23, .02), (.77, .99), (-.27, -1.07), (1.31, 2.72), (.5, 0.)):
                    value = float(sdf.evaluate_sdf(c, plane, u, v))
                    self.assertAlmostEqual(value, sdf.reference_sdf_point(c, plane, u, v), places=12)
                    self.assertAlmostEqual(value, float(sdf.evaluate_sdf(c, plane, -u, v+1)), places=12)
                    self.assertAlmostEqual(value, float(sdf.evaluate_sdf(c, plane, -u, v-1)), places=12)

    def test_nor_sites_actual_scalar_and_exact_masks(self):
        for rows, angles in ((1,32), (3,64), (17,96)):
            c = sdf.prepare_config(sdf.default_config("nor_sites", rows, angles))
            raw, manifest = sdf.compile_atlas(c)
            self.assertEqual(raw[:8], b"AOSDF01\n")
            words = np.frombuffer(raw, dtype="<u4", offset=16).reshape(4, rows, angles//32)
            for plane, mask in enumerate((7,7,6,7)):
                self.assertTrue(np.all(words[plane] == mask))
            for name in sdf.PLANES:
                self.assertGreater(manifest["minimum_abs_sdf"][name], 0.)
            self.assertLess(sdf.reference_sdf_point(c, "asa", .5/rows, 0.), 0.)
            self.assertGreater(sdf.reference_sdf_point(c, "boundary", .5/rows, 0.), 0.)

    def test_geometry_compile_independent_all_bits_and_tails(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"geometry.bin"
            result = sdf.write_atlas(sdf.default_config("geometry", 17, 257), path)
            verified = sdf.verify_atlas(path)
            self.assertEqual(verified["verified_bits"], 4*17*257)
            self.assertEqual(result["atlas_sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertTrue(verified["independent_all_bits_verified"])
            for plane in verified["planes"].values():
                self.assertTrue(np.all((plane[:,-1] & np.uint32(0xfffffffe)) == 0))

    def test_nor_compile_verify(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"nor.bin"
            sdf.write_atlas(sdf.default_config("nor_sites", 9, 64), path)
            self.assertEqual(sdf.verify_atlas(path)["verified_bits"], 4*9*64)

    def test_hash_and_scalar_tampering_reject(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"nor.bin"
            sdf.write_atlas(sdf.default_config("nor_sites", 3, 32), path)
            raw=bytearray(path.read_bytes());raw[16]^=8;path.write_bytes(raw)
            with self.assertRaises(ValueError): sdf.verify_atlas(path)
            manifest_path=path.with_suffix(".json")
            manifest=json.loads(manifest_path.read_text());manifest["atlas_sha256"]=hashlib.sha256(raw).hexdigest()
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaises(AssertionError): sdf.verify_atlas(path)

    def test_false_topology_metadata_reject(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"nor.bin"
            sdf.write_atlas(sdf.default_config("nor_sites", 3, 32), path)
            meta=path.with_suffix(".json");m=json.loads(meta.read_text());m["topology"]="torus";meta.write_text(json.dumps(m))
            with self.assertRaises(ValueError): sdf.verify_atlas(path)

    def test_profile_validation(self):
        for angles in (1,31,33,65):
            with self.assertRaises(ValueError): sdf.prepare_config(sdf.default_config("nor_sites", 3, angles))
        c=sdf.default_config();c["planes"]["asa"][0]["radius"]=.5
        with self.assertRaises(ValueError): sdf.prepare_config(c)
        c=sdf.default_config();c["planes"]["asa"].append(dict(c["planes"]["asa"][0]))
        with self.assertRaises(ValueError): sdf.prepare_config(c)

    def test_capacity_sweep_dimensions_not_fixed_four_mib(self):
        for rows, expected in ((512,4<<20),(576,4608<<10),(608,4864<<10),(640,5<<20)):
            c=sdf.prepare_config(sdf.default_config("nor_sites", rows, 16384))
            self.assertEqual(c["rows"]*((c["angles"]+31)//32)*16,expected)
        with self.assertRaises(ValueError): sdf.prepare_config(sdf.default_config("nor_sites",65536,65536))

    def test_empty_plane_and_reproducibility(self):
        c=sdf.default_config("geometry",3,65);c["planes"]["boundary"]=[]
        raw,manifest=sdf.compile_atlas(c)
        self.assertIsNone(manifest["minimum_abs_sdf"]["boundary"])
        self.assertEqual((raw,manifest),sdf.compile_atlas(c))


if __name__ == "__main__":
    unittest.main()
