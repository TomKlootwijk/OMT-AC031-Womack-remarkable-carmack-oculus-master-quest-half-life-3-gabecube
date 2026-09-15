"""Bind the historical imported wrapper to final immutable-wrapper CUDA replay.

This reruns only short wrapper cases. The complete preserved GPU replay is composed
with byte-identical per-seed native transport and unchanged query-path functions.
"""
from copy import deepcopy
import ast
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import struct
import sys
from datetime import datetime, timezone

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
sys.path.insert(0, str(ROOT / "python"))
import orbit_native as current
from orbit_seed import digest, load


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rejected(action, error):
    try: action()
    except error: return True
    raise AssertionError("Immutable/domain API unexpectedly accepted mutation/query")


def functions(path):
    result = {}
    tree = ast.parse(Path(path).read_text())
    for node in tree.body:
        if isinstance(node, ast.FunctionDef): result[node.name] = ast.dump(node, include_attributes=False)
        if isinstance(node, ast.ClassDef) and node.name == "NativeOrbit":
            for child in node.body:
                if isinstance(child, ast.FunctionDef):
                    result["NativeOrbit." + child.name] = ast.dump(child, include_attributes=False)
    return result


def main():
    before_path, after_path = OUT / "previous_orbit_native.py", ROOT / "python/orbit_native.py"
    before_hash, after_hash = sha(before_path), sha(after_path)
    assert before_hash == "8b0e06ebb599b0dabe5720557418ea3953ec38c54d2d7174f6a458424b4d1c67"
    assert after_hash == "a5e58821b8960e3d60c38a0402659441de995302957334b6c356900b8a6cf092"
    spec = importlib.util.spec_from_file_location("previous_orbit_native", before_path)
    previous = importlib.util.module_from_spec(spec); spec.loader.exec_module(previous)
    unchanged = ["numeric_model", "NativeOrbit._read", "NativeOrbit.command", "NativeOrbit._time",
                 "NativeOrbit.query", "NativeOrbit.batch", "NativeOrbit.transition",
                 "NativeOrbit.stats", "NativeOrbit.reset", "NativeOrbit.close"]
    a, b = functions(before_path), functions(after_path)
    for name in unchanged: assert a[name] == b[name], name
    binary = ROOT / "bin/cuda/orbit_worker.exe"
    binary_hash = sha(binary)
    assert binary_hash == "f6b640d5f984c5e2226794649fd22391c1819ad1e7ee2df5db3a81e527262ef3"
    full = json.loads((ROOT / "results/optimization_replay_cuda/summary.json").read_text())
    assert full["status"] == "passed" and full["worker_sha256"] == binary_hash
    january = {k: v for k, v in full["objects"].items() if k.startswith("january:")}
    february = {k: v for k, v in full["objects"].items() if k.startswith("february:")}
    assert sum(v["samples"] for v in january.values()) == 8064
    assert all(v["changed_prediction_rows"] == 0 and v["max_prediction_difference_m"] == 0 for v in january.values())
    assert sum(v["samples"] for v in february.values()) == 7489
    assert all(v["max_prediction_difference_m"] <= .01 for v in february.values())
    report = {"status": "running", "started_utc": datetime.now(timezone.utc).isoformat(),
              "previous_wrapper_sha256": before_hash, "current_wrapper_sha256": after_hash,
              "cuda_worker_sha256": binary_hash, "query_functions_ast_identical": unchanged,
              "scope": __doc__, "objects": {}, "complete_replay": {
                  "report": "results/optimization_replay_cuda/summary.json",
                  "wrapper_imported_at_start_sha256": before_hash,
                  "hash_at_completion_is_not_import_identity": True,
                  "january": {"samples": 8064, "comparison": "same CUDA backend", "exact_prediction_rows": 8064,
                              "maximum_prediction_difference_m": 0., "objects": january},
                  "february": {"samples": 7489, "comparison": "current CUDA versus preserved CPU",
                               "acceptance_m": .01,
                               "maximum_prediction_difference_m": max(v["max_prediction_difference_m"] for v in february.values()),
                               "objects": february}},
              "composition": "The full historical GPU execution used the same native binary and exactly the same eight model payloads. Final wrapper query/response methods are AST-identical; only model-view/hash immutability and editable-copy access changed. Short final-wrapper CUDA queries verify those APIs and transport in execution. This is a composed equivalence check, not a repeated all-epoch final-wrapper GPU run."}
    payloads = OUT / "payloads"; payloads.mkdir(exist_ok=True)
    short_times = [-.125, .125, 300., 300., -0., 0.]
    total_queries = 0
    for label, directory in [("january", "seeds"), ("february", "confirmation_seeds")]:
        for path in sorted((ROOT / "examples/orbit" / directory).glob("*.orbseed")):
            seed = load(path); m = seed["model"]; name = seed["object"]["id"]; key = label + ":" + name
            model_hash = digest(m)
            assert full["objects"][key]["model_sha256"] == model_hash
            old_payload, new_payload = previous.numeric_model(m).encode("ascii"), current.numeric_model(m).encode("ascii")
            assert old_payload == new_payload
            (payloads / (label + "_" + name + ".txt")).write_bytes(new_payload)
            lower, upper = m["domain_s"]
            times = [lower, upper, *short_times, -.125]
            with previous.NativeOrbit(binary, m, "cuda") as old, current.NativeOrbit(binary, m, "cuda") as new:
                old_file, new_file = old._model_path.read_bytes(), new._model_path.read_bytes()
                assert old_file == new_file
                prior = old.batch(short_times)
                actual = new.batch(times)
                assert all(row["status"] == "ok" for row in prior + actual)
                for t, row in zip(times, actual):
                    assert struct.pack("<d", t) == struct.pack("<d", row["time_s"])
                for reference, row in zip(prior, actual[2:8]):
                    assert struct.pack("<6d", *reference["state_gcrs"]) == struct.pack("<6d", *row["state_gcrs"])
                    assert reference["reused_in_batch"] == row["reused_in_batch"]
                assert actual[5]["reused_in_batch"] and actual[-1]["reused_in_batch"]
                assert actual[5]["rk_steps"] == actual[-1]["rk_steps"] == 0
                original_state = deepcopy(m["state_gcrs"])
                rejected(lambda: new.model["domain_s"].__setitem__(1, upper + 1), (TypeError, AttributeError))
                rejected(lambda: setattr(new, "model", {}), AttributeError)
                rejected(lambda: setattr(new, "model_sha256", "changed"), AttributeError)
                edited = new.copy_model(); edited["state_gcrs"][0] += 123.; edited["domain_s"][1] += 1.
                m["state_gcrs"][0] += 456.; m["domain_s"][1] += 2.
                assert digest(new.copy_model()) == new.model_sha256 == model_hash
                zero = new.query(0.)
                assert struct.pack("<6d", *zero["state_gcrs"]) == struct.pack("<6d", *original_state)
                rejected(lambda: new.query(math.nextafter(upper, math.inf)), ValueError)
                rejected(lambda: new.query(math.nextafter(lower, -math.inf)), ValueError)
                outside = [new.command("QUERY " + repr(t))["queries"][0] for t in
                           [math.nextafter(lower, -math.inf), math.nextafter(upper, math.inf)]]
                assert all(row["status"] == "outside_model_domain" and row["rk_steps"] == 0 for row in outside)
                device = new.command("QUERY 0")["device"]
            item = {"seed_file": path.relative_to(ROOT).as_posix(), "seed_file_sha256": sha(path),
                    "model_sha256": model_hash, "numeric_model_payloads_byte_identical": True,
                    "numeric_model_lf_bytes": len(new_payload), "numeric_model_lf_sha256": hashlib.sha256(new_payload).hexdigest(),
                    "actual_worker_input_bytes": len(new_file), "actual_worker_input_sha256": hashlib.sha256(new_file).hexdigest(),
                    "actual_worker_inputs_byte_identical": True, "current_cuda_times_s": times,
                    "current_cuda_results": actual, "previous_wrapper_short_results": prior,
                    "short_states_same_cuda_binary_exact": True, "immutability_api_passed": True,
                    "outside_domain_results": outside, "device": device}
            report["objects"][key] = item
            total_queries += len(times) + len(short_times) + 4
            (OUT / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
            print(key, "payload identical; CUDA boundaries/fractions/reuse/sign-zero/immutable API passed", flush=True)
    assert len(report["objects"]) == 8
    assert sha(after_path) == after_hash and sha(before_path) == before_hash and sha(binary) == binary_hash
    report.update(status="passed", completed_utc=datetime.now(timezone.utc).isoformat(),
                  objects_checked=8, queried_records_including_rejected=total_queries,
                  source_hashes={name: sha(ROOT / "python" / name) for name in
                                 ["orbit_native.py", "orbit_seed.py", "orbit_dynamics.py", "orbit_precision.py"]},
                  verification_script_sha256=sha(__file__))
    (OUT / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print("passed", OUT / "summary.json", flush=True)


if __name__ == "__main__": main()
