"""Audit recorded cold-cache profiles and final CPU evidence without GPU execution."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
CPU = Path("C:/Users/Tom/.cache/ak1/cpu_fold_final/evidence_1789299038566882500")
METRIC = "l1tex__t_sectors_pipe_tex_mem_texture_op_ld"


def read(path):
    data = path.read_bytes()
    return json.loads(data.decode("utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"))


def record(path):
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def shape_key(run):
    command = run["command"]
    return (int(command[command.index("--rows") + 1]), int(command[command.index("--angles") + 1]),
            command[command.index("--layout") + 1])


def main():
    profiles = read(HERE / "fold_initial_profiles.json")
    before = read(HERE / "padded_before_fold_profiles.json")
    rows = []
    for run in profiles["runs"]:
        command = run["command"]
        assert command[command.index("--cache-control") + 1] == "all"
        assert command[command.index("--replay-mode") + 1] == "kernel"
        assert command[command.index("--launch-skip") + 1] == "1"
        assert command[command.index("--launch-count") + 1] == "1"
        assert run["exit_code"] == 0
        summary_file = Path(run["csv"]).with_suffix(".stdout")
        summary = read(ROOT / summary_file)
        assert summary["status"] == "passed" and summary["candidate_verification"] == "passed"
        assert summary["host_tile_coverage_verified"] and summary["sm_mapping_verified"]
        assert summary["phase_order_scope"] == "whole_cooperative_grid"
        metrics = run["metrics"]
        sectors = metrics[METRIC + ".sum"]["value"]
        hits = metrics[METRIC + "_lookup_hit.sum"]["value"]
        misses = metrics[METRIC + "_lookup_miss.sum"]["value"]
        floor = summary["mask_bytes"] // 32
        assert summary["mask_bytes"] % 32 == 0
        assert hits + misses == sectors and misses == floor
        for mapping in summary["sm_mappings"]:
            assert mapping["before"] == mapping["after"]
            assert len(set(mapping["before"])) == summary["multiprocessors"]
        pair = next((old for old in before["runs"] if shape_key(old) == shape_key(run)), None)
        old_miss = pair["metrics"][METRIC + "_lookup_miss.sum"]["value"] if pair else None
        rows.append({"rows": run["rows"], "angles": run["angles"], "layout": run["layout"],
                     "mask_bytes": summary["mask_bytes"], "sectors": sectors, "hits": hits, "misses": misses,
                     "compulsory_32_byte_sector_floor": floor, "excess_misses": misses - floor,
                     "padded_prefold_misses": old_miss,
                     "miss_reduction_from_matched_prefold": old_miss - misses if old_miss is not None else None,
                     "maximum_assigned_mask_bytes_per_sm": summary["maximum_assigned_mask_bytes"],
                     "warm_texels": summary["warm_texel_reads_per_epoch"],
                     "work_texels": summary["work_texel_reads_per_epoch"],
                     "post_texels": summary["post_texel_reads_per_epoch"],
                     "candidate_verification": "passed", "observed_sm_mapping": "unique and unchanged at entry/exit",
                     "raw_counter_file": str(ROOT / run["csv"]), "kernel_summary": str(ROOT / summary_file)})
    validation = read(CPU / "validation.json")
    proofs = read(CPU / "proofs.json")
    assert validation["status"] == validation["cpu"] == validation["proofs"] == "passed"
    assert len(validation["runs"]) == 48 and len(proofs["obligations"]) == 15
    assert all(item["passed"] for item in proofs["obligations"])
    report = {
        "schema": "atomos.fold_scope_review.v1", "created_utc": datetime.now(timezone.utc).isoformat(),
        "read_only_gpu_review": "passed", "profile_binary_sha256": profiles["sha256"],
        "cold_cache_rows": rows,
        "supported_claim": "The complete 4 MiB dictionary, partitioned across SM-local texture caches, showed only compulsory cold texture-sector misses through a real verified epoch and a full retention probe in the measured cooperative harness, in both layouts.",
        "count_interpretation": "At maximum size, 4194304/32 = 131072 unique sectors. The entire warm/work/post kernel records 131072 misses and 262678 hits, with hits+misses=393750. Relative to the compulsory-sector floor there are zero excess misses. Given cold starting caches, full unique-sector coverage, and no independent dictionary-refill path, this supports all subsequent demand reuses hitting; counters were collected for the whole kernel, not isolated phases.",
        "scope_limits": [
            "Dictionary residency is distributed across the SM-local caches, not a 4 MiB cache per SM.",
            "This is empirical retention in the measured cooperative warm/work/post launch, not documented hardware pinning or persistence across arbitrary later work.",
            "Warm-up and post-work probing are explicit extra reads; full unpadded runs issue three logical texture passes.",
            "The fixed-constant source change removes coefficient loads and changes register allocation. These records establish the compiled change's effect; they do not uniquely attribute every avoided miss to a coefficient line.",
            "No ordinary LDG/STG instructions remain in the actual bulk kernel, but dynamic LSU global-load metrics remain nonzero; bulk and synchronization traffic are still present.",
            "Profiled CUDA-event compute_ms includes profiling effects. Use unprofiled measurements for performance comparisons."
        ],
        "primary_documentation": [
            {"url": "https://docs.nvidia.com/nsight-compute/ProfilingGuide/#cache-control", "claim": "Cache control all flushes GPU caches before replay passes."},
            {"url": "https://docs.nvidia.com/nsight-compute/ProfilingGuide/", "claim": "L1 sector accounting uses 32-byte sectors; sector hit rate describes requested sectors that do not miss."}
        ],
        "cpu_full_validation": {
            "command": ["C:/Users/Tom/miniconda3/python.exe", "tools/validate.py", "--proofs", "--build", "C:/Users/Tom/.cache/ak1/cpu_fold_final"],
            "exit_code": 0, "ctest_cases_passed": 7, "python_tests_passed": 37,
            "symbolic_obligations_passed": 15, "independently_verified_runs": 48,
            "evidence": str(CPU), "validation_record": record(CPU / "validation.json"),
            "proof_record": record(CPU / "proofs.json"),
            "console_log": record(HERE / "cpu_fold_final_validation.log"),
            "gpu_status": validation["gpu"],
            "artifact_hashes": [record(path) for path in [
                ROOT / "include/atomos/core.hpp", ROOT / "tests/test_core.cpp", ROOT / "python/reference.py", ROOT / "tests/test_reference.py",
                CPU.parent / "Release/atomos_cpu.exe", CPU.parent / "Release/atomos_tests.exe"]]
        },
        "analysis_source": record(Path(__file__).resolve()),
    }
    output = HERE / "fold_scope_review.json"
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "cold_cache_rows": rows, "cpu_status": "passed"}, indent=2))


if __name__ == "__main__":
    main()
