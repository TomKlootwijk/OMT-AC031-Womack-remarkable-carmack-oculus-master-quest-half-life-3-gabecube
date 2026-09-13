#!/usr/bin/env python3
"""Run a bounded, sequential CUDA cache comparison with preserved correctness evidence.

The default 24-configuration design varies every read/layout/block combination at
the default carveout, then compares max-L1 at block 128. Optional larger and tail
shapes add six configurations each. --full-factorial instead tests all 36
read/layout/block/cache combinations at the default shape. No GPU command runs
with --plan. Times are CUDA event kernel times, never CPU/GPU end-to-end ratios.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
import platform
import random
import shutil
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from reference import verify_execution_metadata, verify_run

DEFAULT_EXE = Path("C:/Users/Tom/.cache/ak1/gpu128/Release/atomos_cuda.exe")
READS = ("texture", "texture-packed", "global")
LAYOUTS = ("linear", "morton8")
BLOCKS = (64, 128, 256)
EPOCHS = 3
FIXTURE_SEED = 130
AXES = ("rows", "angles", "read", "layout", "block_size", "cache")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def configuration(rows: int, angles: int, read: str, layout: str, block: int, cache: str) -> dict:
    return dict(rows=rows, angles=angles, read=read, layout=layout, block_size=block, cache=cache)


def configuration_id(config: dict) -> str:
    return "_".join(str(config[key]) for key in AXES)


def configurations(args: argparse.Namespace) -> list[dict]:
    result = []
    for read, layout, block in itertools.product(READS, LAYOUTS, BLOCKS):
        for cache in (("default", "max-l1") if args.full_factorial else ("default",)):
            result.append(configuration(128, 1024, read, layout, block, cache))
    if not args.full_factorial:
        result.extend(configuration(128, 1024, read, layout, 128, "max-l1")
                      for read, layout in itertools.product(READS, LAYOUTS))
    for enabled, rows, angles in ((args.include_large, 1024, 1024), (args.include_tails, 17, 257)):
        if enabled:
            result.extend(configuration(rows, angles, read, layout, 128, "max-l1")
                          for read, layout in itertools.product(READS, LAYOUTS))
    if len(result) > 36 or len({configuration_id(c) for c in result}) != len(result):
        raise ValueError("configuration plan exceeds the unique 36-configuration bound")
    return result


def command(exe: Path, config: dict, device: int, output: Path | None = None) -> list[str]:
    result = [str(exe), "--rows", str(config["rows"]), "--angles", str(config["angles"]),
              "--epochs", str(EPOCHS), "--seed", str(FIXTURE_SEED), "--mode", "recurrent",
              "--profile", "mixed", "--fringe", "off", "--read", config["read"],
              "--layout", config["layout"], "--block-size", str(config["block_size"]),
              "--cache", config["cache"], "--device", str(device)]
    if output is not None:
        result.extend(("--out", str(output)))
    return result


def schedule(configs: list[dict], trials: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    result = []
    for trial in range(trials):
        order = list(configs)
        rng.shuffle(order)
        result.extend(dict(trial=trial + 1, configuration=configuration_id(c), config=c) for c in order)
    return result


def validate_summary(summary: dict, config: dict, device: dict) -> None:
    verify_execution_metadata(summary, expected_backend="cuda", expected_read=config["read"],
                              expected_device=device)
    expected = dict(schema="atomOS-v3.6-K1-run", rows=config["rows"], angles=config["angles"],
                    epochs=EPOCHS, seed=FIXTURE_SEED, layout=config["layout"], mode="recurrent",
                    profile="mixed", fringe=False)
    for key, value in expected.items():
        if type(summary.get(key)) is not type(value) or summary[key] != value:
            raise ValueError(f"summary {key} differs from the invoked configuration")
    words = (config["angles"] + 31) // 32
    stored = ((config["rows"] + 7) // 8 * 8) * ((words + 7) // 8 * 8)
    lanes = config["rows"] * words
    if summary.get("committed_lane_epochs") != lanes * EPOCHS:
        raise ValueError("summary does not record every committed lane epoch")
    kernel = summary["device"].get("kernel", {})
    name = {"texture": "atomos_epoch_texture", "texture-packed": "atomos_epoch_packed",
            "global": "atomos_epoch_global"}[config["read"]]
    expected_kernel = dict(name=name, block_size=config["block_size"],
                           max_l1_requested=config["cache"] == "max-l1",
                           grid_blocks=(lanes + config["block_size"] - 1) // config["block_size"],
                           mask_bytes=16 * stored)
    for key, value in expected_kernel.items():
        if type(kernel.get(key)) is not type(value) or kernel[key] != value:
            raise ValueError(f"kernel {key} differs from the invoked configuration")
    times = summary.get("compute_ms")
    if not isinstance(times, list) or len(times) != EPOCHS:
        raise ValueError("missing three measured CUDA epoch times")
    if any(type(t) not in (int, float) or not math.isfinite(t) or t < 0 for t in times):
        raise ValueError("invalid CUDA event timing")
    counts = [summary.get("checks_" + name) for name in ("pass", "fail", "undefined")]
    if any(type(v) is not int or v < 0 for v in counts) or counts[1] != 0 or sum(counts) != lanes * EPOCHS * 6:
        raise ValueError("invalid invariant counts or failed fixture invariant")


def aggregate(configs: list[dict], runs: list[dict]) -> tuple[list[dict], list[dict]]:
    rows = []
    for config in configs:
        selected = [run for run in runs if run["configuration"] == configuration_id(config)]
        trial_medians = [run["median_compute_ms"] for run in selected]
        rows.append(dict(configuration=configuration_id(config), **config, trials=len(selected),
                         median_ms=statistics.median(trial_medians), min_ms=min(trial_medians),
                         max_ms=max(trial_medians), trial_medians_ms=trial_medians,
                         representative_run=selected[0]["representative_run"]))
    comparisons = []
    for left, right in itertools.combinations(rows, 2):
        different = [key for key in AXES if left[key] != right[key]]
        if len(different) != 1 or different[0] in ("rows", "angles"):
            continue
        comparisons.append(dict(axis=different[0], left=left["configuration"], right=right["configuration"],
                                left_median_ms=left["median_ms"], right_median_ms=right["median_ms"],
                                left_over_right_ratio=left["median_ms"] / right["median_ms"]
                                if right["median_ms"] > 0 else None))
    return rows, comparisons


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, default=DEFAULT_EXE)
    parser.add_argument("--out", type=Path, help="New evidence directory; existing paths are refused")
    parser.add_argument("--device", type=int, default=0)
    parser.add_argument("--trials", type=int, default=5, help="Trials per configuration, 1..5; default 5")
    parser.add_argument("--shuffle-seed", type=int, default=20260913)
    parser.add_argument("--include-large", action="store_true", help="Add six 1024x1024 configurations")
    parser.add_argument("--include-tails", action="store_true", help="Add six 17x257 configurations")
    parser.add_argument("--full-factorial", action="store_true", help="All 36 combinations at 128x1024")
    parser.add_argument("--plan", action="store_true", help="Print the plan without invoking tools or the GPU")
    parser.add_argument("--timeout", type=float, default=120.0, help="Maximum seconds per CUDA process")
    args = parser.parse_args()
    if not 0 <= args.device <= 1024 or not 1 <= args.trials <= 5:
        parser.error("device must be 0..1024 and trials must be 1..5")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("timeout must be finite and positive")
    if args.full_factorial and (args.include_large or args.include_tails):
        parser.error("--full-factorial cannot be combined with extra shapes (36-configuration bound)")
    configs = configurations(args)
    execution_order = schedule(configs, args.trials, args.shuffle_seed)
    exe = args.exe.resolve()
    if args.plan:
        print(json.dumps(dict(configurations=configs, configuration_count=len(configs),
                              trials=args.trials, epoch_count=EPOCHS, cuda_processes=len(execution_order),
                              shuffle_seed=args.shuffle_seed, order=execution_order,
                              example_command=command(exe, configs[0], args.device)), indent=2))
        return 0
    evidence = (args.out or ROOT / "results" / ("cache_benchmark_" + str(time.time_ns()))).resolve()
    try:
        evidence.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        print(f"Cannot create new evidence directory: {exc}", file=sys.stderr)
        return 1
    (evidence / "commands").mkdir()
    (evidence / "representative_runs").mkdir()
    status = dict(schema="atomOS-v3.6-K1-cache-benchmark", status="running", started_utc=utc_now(),
                  executable=str(exe), fixture=dict(seed=FIXTURE_SEED, mode="recurrent", fringe=False,
                                                    profile="mixed", epochs=EPOCHS),
                  configurations=configs, trials=args.trials, shuffle_seed=args.shuffle_seed,
                  order=execution_order, commands=[], runs=[], independent_verifications={},
                  methodology={
                      "ordering": "Sequential processes; a seeded independent shuffle each trial",
                      "warmup": "One uncommitted warmup launch in every CUDA backend constructor",
                      "timing": "CUDA event kernel times; three epochs -> one median per trial; median/min/max across trial medians",
                      "correctness": "Every launch checks candidates on the host before commit. One exported run per configuration is independently checked in Python before any trial for that configuration is accepted.",
                      "scope": "Finite synthetic workload; no direct cache-hit counters or guarantee of cache residency; no end-to-end CPU/GPU comparison",
                      "carveout": "max-l1 is a CUDA preference request, not cache pinning or a guarantee of effective partition size",
                      "default_design": "24 configurations; block size varied at default carveout, cache compared at block 128. Optional shape comparisons use max-l1/block128. --full-factorial covers 36 default-shape combinations.",
                  })

    def save() -> None:
        write_json(evidence / "benchmark.json", status)

    def run_tool(argv: list[str], label: str, *, required: bool = True, timeout: float = 30.0) -> str:
        stdout = evidence / "commands" / (label + ".stdout.log")
        stderr = evidence / "commands" / (label + ".stderr.log")
        record = dict(command=argv, started_utc=utc_now(), stdout=str(stdout.relative_to(evidence)),
                      stderr=str(stderr.relative_to(evidence)))
        status["commands"].append(record)
        save()
        start = time.perf_counter()
        try:
            with stdout.open("w", encoding="utf-8") as out, stderr.open("w", encoding="utf-8") as err:
                result = subprocess.run(argv, cwd=ROOT, stdout=out, stderr=err, text=True, timeout=timeout)
            record["exit_code"] = result.returncode
        except (OSError, subprocess.TimeoutExpired) as exc:
            record.update(exit_code=None, error=str(exc))
            if required:
                raise RuntimeError(f"{label}: {exc}") from exc
        finally:
            record["process_wall_seconds"] = time.perf_counter() - start
            record["finished_utc"] = utc_now()
            save()
        if required and record["exit_code"] != 0:
            raise RuntimeError(f"{label} exited {record['exit_code']}; see {stdout} and {stderr}")
        return stdout.read_text(encoding="utf-8") if stdout.exists() else ""

    def tool_record(name: str, version_args: list[str]) -> None:
        path = shutil.which(name)
        if not path:
            status["tools"][name] = dict(status="unavailable")
            return
        status["tools"][name] = dict(path=path, sha256=sha256(Path(path)))
        run_tool([path, *version_args], "tool_" + name, required=False)

    try:
        if not exe.is_file():
            status.update(status="not_run", reason="CUDA executable unavailable", finished_utc=utc_now())
            save()
            print(f"NOT RUN: CUDA executable unavailable. Evidence: {evidence}")
            return 3
        status["executable_sha256"] = sha256(exe)
        status["host"] = dict(platform=platform.platform(), python=sys.version, python_executable=sys.executable)
        status["source_sha256"] = {str(path.relative_to(ROOT)): sha256(path) for path in
                                    (ROOT / "cuda/kernel.cu", ROOT / "include/atomos/core.hpp",
                                     ROOT / "include/atomos/host.hpp", ROOT / "src/main.cpp",
                                     ROOT / "CMakeLists.txt", ROOT / "python/reference.py", Path(__file__))}
        cache = exe.parent.parent / "CMakeCache.txt" if exe.parent.name == "Release" else exe.parent / "CMakeCache.txt"
        if cache.is_file():
            shutil.copyfile(cache, evidence / "CMakeCache.txt")
            status["cmake_cache"] = dict(path=str(cache), sha256=sha256(cache))
        status["tools"] = {}
        for tool, version_args in (("nvcc", ["--version"]), ("cmake", ["--version"]),
                                   ("nvidia-smi", ["--query-gpu=name,uuid,driver_version,pstate,temperature.gpu,clocks.sm,clocks.mem,memory.used,memory.free", "--format=csv"])):
            tool_record(tool, version_args)
        device = json.loads(run_tool([str(exe), "--probe", "--device", str(args.device)], "device_probe"))
        status["device"] = device
        save()
        reference_counts = {}
        semantic_digests = {}
        representatives = {}
        for position, item in enumerate(execution_order, start=1):
            config, config_id, trial = item["config"], item["configuration"], item["trial"]
            label = f"run_{position:03d}_trial{trial}_{config_id}"
            first = config_id not in representatives
            output = evidence / "representative_runs" / config_id if first else None
            print(f"[{position}/{len(execution_order)}] trial {trial}: {config_id}", flush=True)
            summary = json.loads(run_tool(command(exe, config, args.device, output), label, timeout=args.timeout))
            validate_summary(summary, config, device)
            shape_key = f"{config['rows']}x{config['angles']}"
            counts = [summary["checks_" + name] for name in ("pass", "fail", "undefined")]
            if first:
                if json.loads((output / "summary.json").read_text(encoding="utf-8")) != summary:
                    raise ValueError("exported and stdout summaries differ")
                verified = verify_run(output, expected_backend="cuda", expected_read=config["read"], expected_device=device)
                if verified["invariant_counts"][1] != 0:
                    raise ValueError("independent verification found a failed fixture invariant")
                digest = verified["integer_semantic_sha256"]
                if shape_key in semantic_digests and semantic_digests[shape_key] != digest:
                    raise ValueError("integer semantic digest differs across cache/read/layout/block configurations")
                semantic_digests[shape_key] = digest
                representatives[config_id] = str(output.relative_to(evidence))
                status["independent_verifications"][config_id] = dict(path=representatives[config_id], **verified)
                reference_counts[config_id] = counts
            if counts != reference_counts[config_id]:
                raise ValueError("invariant counts differ from the independently verified representative")
            status["runs"].append(dict(position=position, trial=trial, configuration=config_id,
                                       representative_run=representatives[config_id],
                                       correctness="passed", compute_ms=summary["compute_ms"],
                                       median_compute_ms=statistics.median(summary["compute_ms"]),
                                       summary_log=f"commands/{label}.stdout.log",
                                       kernel=summary["device"]["kernel"]))
            save()
        if sha256(exe) != status["executable_sha256"]:
            raise ValueError("CUDA executable changed during the benchmark; timing evidence refused")
        status["semantic_sha256_by_shape"] = semantic_digests
        status["aggregates"], status["comparisons"] = aggregate(configs, status["runs"])
        fields = ["configuration", *AXES, "trials", "median_ms", "min_ms", "max_ms", "representative_run"]
        with (evidence / "aggregates.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(status["aggregates"])
        status.update(status="passed", finished_utc=utc_now())
        save()
        print(f"PASS: {len(configs)} independently verified configurations, {len(status['runs'])} measured processes. Evidence: {evidence}")
        return 0
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, OverflowError) as exc:
        status.update(status="failed", reason=str(exc), finished_utc=utc_now())
        save()
        print(f"FAIL: {exc}\nEvidence: {evidence}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
