"""Reproducible static comparison of the pre-fold and folded sm_120 binaries."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import re
import shutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
FOLDED = Path("C:/Users/Tom/.cache/ak1/bulk_fold_sm120/Release/atomos_cache_bulk.exe")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text(path):
    data = path.read_bytes()
    return data.decode("utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")


def functions(sass_path, resource_path):
    sass = text(sass_path)
    resources = text(resource_path)
    result = []
    chunks = re.split(r"\s*Function : (\S+)\s*", sass)
    for i in range(1, len(chunks), 2):
        name, body = chunks[i:i + 2]
        resource_match = re.search(r"Function " + re.escape(name) + r":\s*([^\r\n]+)", resources)
        resource = resource_match.group(1).strip() if resource_match else None
        result.append({
            "name": name,
            "scope": "actual_bulk_kernel" if "atomos_epoch_bulk_probe" in name else "included_production_kernel_not_launched_by_bulk_executable",
            "resources": resource,
            "static_ldg_constant": len(re.findall(r"\bLDG\.[^\s]*\.CONSTANT\b", body)),
            "static_ldg_all": len(re.findall(r"\bLDG\.", body)),
            "static_stg_all": len(re.findall(r"\bSTG\.", body)),
            "static_tld": len(re.findall(r"\bTLD(?:\.|\s)", body)),
            "static_cctl_ivall": len(re.findall(r"\bCCTL\.IVALL\b", body)),
        })
    assert len(result) == 4, "Expected actual bulk kernel plus three included production kernels"
    return result


def snapshot(source, name):
    target = HERE / name
    if target.exists():
        assert sha(source) == sha(target), "Do not overwrite changed snapshot"
    else:
        shutil.copyfile(source, target)
    return {"source": str(source), "snapshot": str(target), "sha256": sha(target), "bytes": target.stat().st_size}


def main():
    prefold = functions(HERE / "bulk_padded_prefold_sass.txt", HERE / "bulk_padded_prefold_resources.txt")
    folded = functions(HERE / "bulk_fold_sass.txt", HERE / "bulk_fold_resources.txt")
    assert all(item["static_ldg_constant"] == 12 for item in prefold)
    assert all(item["static_ldg_constant"] == 0 for item in folded)
    old_bulk = next(item for item in prefold if item["scope"] == "actual_bulk_kernel")
    new_bulk = next(item for item in folded if item["scope"] == "actual_bulk_kernel")
    assert new_bulk["static_ldg_all"] == 0 and new_bulk["static_stg_all"] == 0
    gpu_source = HERE / "rotation_probe_gpu.json"
    gpu = json.loads(text(gpu_source))
    assert gpu["capture_status"] == "passed" and gpu["comparison_status"] == "matched"
    gpu_utf8 = HERE / "rotation_probe_gpu_utf8.json"
    gpu_utf8.write_text(json.dumps(gpu, indent=2) + "\n", encoding="utf-8")
    report = {
        "schema": "atomos.rotation_fold_native.v1", "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "offline native code/resources plus root-executed value probe; no folded GPU execution or residency claim",
        "fixed_binary64_argument": "0x1.999999999999ap-2",
        "cos_constant": "0x1.d7954e7dba2f8p-1", "sin_constant": "0x1.8ec3ae92b676bp-2",
        "proof": {"path": str(HERE / "rotation_rounding.json"), "sha256": sha(HERE / "rotation_rounding.json"),
                  "kind": "exact rational analytic enclosure; not a binary proof"},
        "runtime_value_probe": {"path": str(gpu_source), "sha256": sha(gpu_source),
                                "utf8_copy": str(gpu_utf8), "status": "matched", "executed_by": "root agent"},
        "prefold_provenance": str(HERE / "rotation_prefold_provenance.json"),
        "prefold_executable_sha256": sha(HERE / "atomos_cache_bulk_padded_prefold.exe"),
        "comparison_pair": "padded pre-fold binary 6d8b0e82 versus same padded source after fixed-rotation folding",
        "older_unpadded_artifacts": "bulk_prefold_sass.txt/resources.txt refer to the earlier d4a67af1 binary (REG105); excluded from this controlled comparison",
        "folded_snapshots": [snapshot(FOLDED, "atomos_cache_bulk_folded.exe"),
                             snapshot(ROOT / "include/atomos/core.hpp", "core_folded.hpp"),
                             snapshot(ROOT / "experiments/cache_bulk.cu", "cache_bulk_folded.cu")],
        "toolchain": {"cuda": "12.8.61", "msvc": "19.44.35221.0", "host_toolset": "14.44.35207",
                      "architectures": ["sm_120", "compute_120"], "fmad": False,
                      "build_log": str(HERE / "bulk_fold_build.log")},
        "native_before": prefold, "native_after": folded,
        "coefficient_load_elimination": {"status": "passed", "actual_bulk_before": old_bulk["static_ldg_constant"],
                                        "actual_bulk_after": new_bulk["static_ldg_constant"],
                                        "actual_bulk_ldg_all_after": new_bulk["static_ldg_all"],
                                        "actual_bulk_stg_all_after": new_bulk["static_stg_all"]},
        "cpu_regression": {"baseline": "passed", "folded": "passed", "groups": 32, "assertions": 134521,
                           "baseline_log": str(HERE / "rotation_cpu_baseline_test.log"),
                           "folded_log": str(HERE / "rotation_cpu_fold_test.log"),
                           "new_case": "fixed rotation singularity/profile semantics at both signs and nearby available case"},
        "folded_gpu_correctness": "not_run_by_kernel_review", "folded_gpu_cache_effect": "not_run_by_kernel_review",
        "interpretation": "Replacing fixed sin/cos with identical binary64 constants removes all 12 coefficient loads from the actual TMA bulk kernel. Register allocation also changes, so any observed cache difference is the effect of the compiled change, not proof attributing every miss to coefficients alone.",
        "analysis_source_sha256": sha(Path(__file__).resolve()),
    }
    output = HERE / "rotation_fold_native.json"
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "actual_bulk_before": old_bulk, "actual_bulk_after": new_bulk}, indent=2))


if __name__ == "__main__":
    main()
