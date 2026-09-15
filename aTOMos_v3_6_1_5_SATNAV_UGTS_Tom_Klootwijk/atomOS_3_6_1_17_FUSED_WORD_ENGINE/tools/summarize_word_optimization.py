#!/usr/bin/env python3
"""Compare completed word-cache reports without running any GPU or CPU benchmark.

Only equal workloads with equal per-trial, per-epoch digests are paired.
Every raw report is retained in the derived JSON; different maxima stay separate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys

from summarize_resident import (
    FETCHES, GIB, MIB, PATTERNS, f, load_complete, md_table, require,
    series, summarize_words, tex_escape, tex_table,
)

BASELINE_COMMIT = "4d8992292a7fa0fc43fc050ec090512552f7d067"
OPTIMIZED_COMMIT = "59a7e7d37be24d381cc4be4c7b2a793778995ecf"
OPTIMIZED_SOURCE_SHA256 = "742c25e582bd2d5c4d0868051b61a03d6d224d477029caaff949ba552b2890d2"
REPORTS = {
    "full": ("word_cache_full.json", "word_cache_optimized_full.json"),
    "modulus": ("word_cache_baseline_modulus.json", "word_cache_optimized_modulus.json"),
    "quick": ("word_cache_quick.json", "word_cache_optimized_quick.json"),
}
SHARED_METADATA = (
    "profile", "device", "compute_capability", "total_memory_bytes", "l2_bytes",
    "max_texture_1d_linear_elements", "multiprocessors", "seed", "epochs_per_trial",
    "trials_per_pattern_and_fetch", "chunk_logical_bytes", "warm_epochs", "reserve_bytes",
    "persisting_L2_window", "texture_cache_hit_rate_measured", "S2_comparison",
)
SHARED_LAYOUT = (
    "working_bytes", "record_count", "immutable_seed_bytes", "persistent_state_bytes_two_buffers",
    "bank_count", "records_per_full_bank", "full_CPU_oracle", "sampled_record_count",
    "all_allocated_records_visited_per_epoch",
)


def capacity(data: dict) -> dict:
    completed = [x for x in data["working_sets"] if not x.get("failed")]
    largest = max(completed, key=lambda x: x["working_bytes"])
    return {
        "requested_max_working_bytes": data["requested_max_working_bytes"],
        "admitted_max_working_bytes": data["admitted_max_working_bytes"],
        "initial_free_memory_bytes": data["initial_free_memory_bytes"],
        "total_memory_bytes": data["total_memory_bytes"],
        "l2_bytes": data["l2_bytes"], "reserve_bytes": data["reserve_bytes"],
        "largest_working_bytes": largest["working_bytes"],
        "largest_working_mib": largest["working_bytes"] / MIB,
        "largest_working_over_l2": largest["working_bytes"] / data["l2_bytes"],
        "largest_working_fraction_of_total": largest["working_bytes"] / data["total_memory_bytes"],
        "largest_record_count": largest["record_count"], "largest_bank_count": largest["bank_count"],
        "largest_seed_bytes": largest["immutable_seed_bytes"],
        "largest_both_state_bytes": largest["persistent_state_bytes_two_buffers"],
        "largest_device_requested_allocation_bytes": largest["device_requested_allocation_bytes"],
        "largest_free_before_bytes": largest["free_before_bytes"],
        "largest_free_after_bytes": largest["free_after_bytes"],
        "largest_observed_free_memory_delta_bytes": largest["observed_free_memory_delta_bytes"],
        "largest_sampled_record_count": largest["sampled_record_count"],
        "largest_full_CPU_oracle": largest["full_CPU_oracle"],
    }


def compare_reports(label: str, baseline: dict, optimized: dict) -> dict:
    # Validate completion, full record coverage, timing totals and each report's own oracles.
    bs, os = summarize_words(baseline), summarize_words(optimized)
    require(baseline["passed"] is True and optimized["passed"] is True,
            f"{label}: benchmark reports include failures; no successful comparison may be generated")
    require(optimized.get("implementation") == "exact-address-and-warp-reduction-v2",
            f"{label}: optimized report has an unexpected implementation")
    for key in SHARED_METADATA:
        require(baseline[key] == optimized[key], f"{label}: workload/device metadata differs: {key}")
    bsets = {x["working_bytes"]: x for x in baseline["working_sets"]}
    osets = {x["working_bytes"]: x for x in optimized["working_sets"]}
    require(len(bsets) == len(baseline["working_sets"]) and len(osets) == len(optimized["working_sets"]),
            f"{label}: duplicate working size")
    common = sorted(bsets.keys() & osets.keys())
    require(common, f"{label}: no equal working sizes to compare")
    paired = []
    digest_checks = 0
    for size in common:
        b, o = bsets[size], osets[size]
        for key in SHARED_LAYOUT:
            require(b[key] == o[key], f"{label}/{size}: layout or oracle coverage differs: {key}")
        for pattern in PATTERNS:
            for fetch in FETCHES:
                def trials(row):
                    return sorted((x for x in row["trials"] if x["pattern"] == pattern and x["fetch"] == fetch),
                                  key=lambda x: x["trial"])
                bt, ot = trials(b), trials(o)
                require(len(bt) == len(ot) == baseline["trials_per_pattern_and_fetch"],
                        f"{label}/{size}/{pattern}/{fetch}: incomplete trial pairs")
                evidence = []
                for before, after in zip(bt, ot):
                    for key in ("trial", "pattern", "fetch", "multiplier", "offset", "logical_record_state_bytes"):
                        require(before[key] == after[key], f"{label}/{size}: trial input differs: {key}")
                    require(before["epochs"] == after["epochs"],
                            f"{label}/{size}/{pattern}/{fetch}/{before['trial']}: epoch digest mismatch")
                    digest_checks += len(before["epochs"])
                    evidence.append({"trial": before["trial"], "all_epoch_digests_equal": True,
                                     "final_epoch_digest_equal": True, "epochs": before["epochs"]})
                bg, og = ([x["gpu_ms_sum"] for x in ts] for ts in (bt, ot))
                bw, ow = ([x["measured_host_wall_ms"] for x in ts] for ts in (bt, ot))
                bgm, ogm, bwm, owm = (statistics.median(xs) for xs in (bg, og, bw, ow))
                paired.append({"working_bytes": size, "working_mib": size / MIB,
                               "working_over_l2": size / baseline["l2_bytes"],
                               "pattern": pattern, "fetch": fetch,
                               "baseline_gpu_median_ms": bgm, "optimized_gpu_median_ms": ogm,
                               "baseline_over_optimized_gpu": bgm / ogm,
                               "baseline_wall_median_ms": bwm, "optimized_wall_median_ms": owm,
                               "baseline_over_optimized_wall": bwm / owm,
                               "baseline_gpu_trials_ms": bg, "optimized_gpu_trials_ms": og,
                               "baseline_wall_trials_ms": bw, "optimized_wall_trials_ms": ow,
                               "digest_evidence": evidence})
    return {
        "label": label, "shared_metadata": {k: baseline[k] for k in SHARED_METADATA},
        "matched_working_bytes": common, "matched_size_count": len(common),
        "baseline_only_working_bytes": sorted(bsets.keys() - osets.keys()),
        "optimized_only_working_bytes": sorted(osets.keys() - bsets.keys()),
        "comparison_count": len(paired), "per_trial_epoch_digest_pair_count": digest_checks,
        "all_paired_epoch_digests_equal": True,
        "optimized_gpu_wins": sum(x["baseline_over_optimized_gpu"] > 1 for x in paired),
        "optimized_wall_wins": sum(x["baseline_over_optimized_wall"] > 1 for x in paired),
        "gpu_ratio_range": [min(x["baseline_over_optimized_gpu"] for x in paired),
                            max(x["baseline_over_optimized_gpu"] for x in paired)],
        "wall_ratio_range": [min(x["baseline_over_optimized_wall"] for x in paired),
                             max(x["baseline_over_optimized_wall"] for x in paired)],
        "baseline_capacity": capacity(baseline), "optimized_capacity": capacity(optimized),
        "baseline_validation": {k: v for k, v in bs.items() if k not in ("working_sets", "metadata")},
        "optimized_validation": {k: v for k, v in os.items() if k not in ("working_sets", "metadata")},
        "pairs": paired, "raw_baseline": baseline, "raw_optimized": optimized,
    }


def comparison_rows(rows, tex=False):
    return [[f(p["working_mib"]), f(p["working_over_l2"]),
             f(p["baseline_gpu_median_ms"]), f(p["optimized_gpu_median_ms"]),
             f(p["baseline_over_optimized_gpu"]), f(p["baseline_wall_median_ms"]),
             f(p["optimized_wall_median_ms"]), f(p["baseline_over_optimized_wall"])] for p in rows]


HEADERS = ["MiB", "L2 ratio", "B GPU", "O GPU", "B/O GPU", "B wall", "O wall", "B/O wall"]


def markdown(summary: dict) -> str:
    full = summary["comparisons"]["full"]
    lines = ["# Word-cache implementation comparison", "",
             f"The optimized implementation passed all report checks. At **{full['matched_size_count']} identical working sizes**, "
             f"it was faster in **{full['optimized_gpu_wins']}/{full['comparison_count']} GPU-median** comparisons and "
             f"**{full['optimized_wall_wins']}/{full['comparison_count']} host-wall-median** comparisons. "
             f"The GPU baseline/optimized ratio spans **{f(full['gpu_ratio_range'][0])}–{f(full['gpu_ratio_range'][1])}**; "
             "ratios below one are regressions.", "",
             "This is the bounded integer phi-expression, ASA/NA+JK and digest workload. It is **not an S2 comparison** "
             "or a measurement of general spatial queries. Texture and global paths receive the same implementation changes. "
             "Changing arithmetic/address cost does not demonstrate a cache-hit improvement.", "",
             "The optimized source uses direct streaming addresses, checked power-of-two bank shift/mask addressing, "
             "an exact integer reciprocal with one remainder correction for non-power-of-two affine domains, "
             "proved-safe 32-bit coefficient arithmetic and warp digest reductions. The recurrence, seeds, masks, "
             "reset/warm policy, checksum meaning and independent 64-bit CPU oracle remain the same.", "",
             "Every paired size has equal seed, measured/warm epoch counts, trial count, chunk size and bank layout. "
             "Every paired trial has equal address parameters and **every epoch's** XOR, modulo-2^64 sum and visit-count digest. "
             "The final epoch is included. Complete digests can collide; larger state buffers still use independent sampled "
             "CPU replay rather than a full byte-for-byte readback. All raw reports and trials remain in the summary JSON.", "",
             "## Resident memory extent", "",
             "The following maxima are independent observations. A maximum is paired only if its actual byte size occurs "
             "in both reports. Memory extent is not CUDA active-warp occupancy, cache residency or zero-headroom VRAM saturation.", ""]
    caprows = []
    for mode in ("baseline", "optimized"):
        c = full[mode + "_capacity"]
        caprows.append([mode, c["largest_working_bytes"], f(c["largest_working_bytes"] / GIB),
                        f(c["largest_working_over_l2"]), f(100 * c["largest_working_fraction_of_total"]) + "%",
                        c["largest_record_count"], c["largest_bank_count"], c["largest_device_requested_allocation_bytes"],
                        c["largest_free_after_bytes"]])
    lines += [md_table(["Run", "Working bytes", "GiB", "L2 multiple", "Total memory", "Records/epoch", "Banks",
                       "Requested allocation bytes", "Free after bytes"], caprows), "",
              f"Actual reported L2: **{full['shared_metadata']['l2_bytes']:,} bytes "
              f"({f(full['shared_metadata']['l2_bytes']/MIB)} MiB)**. Working bytes are 16N immutable bytes plus "
              "two 8N-byte state buffers. Every record is visited every measured epoch. Requested allocation includes scratch; "
              "free-memory deltas also reflect a shared desktop and are not exclusive process peak measurements.", ""]
    for label, report in summary["comparisons"].items():
        md = report["shared_metadata"]
        lines += ["## " + {"full": "Full paired sweep", "modulus": "Non-power-of-two modulus check", "quick": "Four-size quick check"}[label], "",
                  f"{report['matched_size_count']} matched sizes; {report['comparison_count']} size/pattern/fetch comparisons; "
                  f"{report['per_trial_epoch_digest_pair_count']} equal per-trial epoch digest pairs. "
                  f"{md['epochs_per_trial']} measured epochs, {md['trials_per_pattern_and_fetch']} trials per path, "
                  f"{md['warm_epochs']} warm epoch(s), {md['chunk_logical_bytes']:,}-byte chunks, seed `{md['seed']}`. "
                  f"Optimized wins: GPU {report['optimized_gpu_wins']}/{report['comparison_count']}, "
                  f"wall {report['optimized_wall_wins']}/{report['comparison_count']}.", "",
                  f"Unpaired baseline bytes: `{report['baseline_only_working_bytes']}`. "
                  f"Unpaired optimized bytes: `{report['optimized_only_working_bytes']}`. These are retained, not relabeled or paired.", "",
                  "All times are median milliseconds across the full measured epoch sequence. B/O is baseline divided by optimized; "
                  "values greater than one favor optimized. GPU sums exclude reset/warm, digest readback and sample verification. "
                  "Host wall includes measured epochs, digest readback/aggregation and sample checks; reset/warm are outside.", ""]
        for pattern in PATTERNS:
            for fetch in FETCHES:
                rows = [x for x in report["pairs"] if x["pattern"] == pattern and x["fetch"] == fetch]
                lines += ["### " + pattern.replace("_", " ") + " / " + fetch.replace("_", " "), "",
                          md_table(HEADERS, comparison_rows(rows)), ""]
        lines += ["<details><summary>Every measured baseline and optimized trial</summary>", ""]
        rows = [[f(p["working_mib"]), p["pattern"], p["fetch"], series(p["baseline_gpu_trials_ms"]),
                 series(p["optimized_gpu_trials_ms"]), series(p["baseline_wall_trials_ms"]),
                 series(p["optimized_wall_trials_ms"])] for p in report["pairs"]]
        lines += [md_table(["MiB", "Pattern", "Fetch", "B GPU trials", "O GPU trials", "B wall trials", "O wall trials"], rows),
                  "", "</details>", ""]
    lines += ["## Interpretation and receipts", "",
              "Baseline and optimized executions were separate runs, so desktop activity, scheduling and device clocks can differ. "
              "Few repeated trials supply no confidence interval or universal speed guarantee. In particular, quick checks have "
              "one trial per path. The 3 MiB check exercises the general reciprocal path with 10 epochs and two trials; "
              "the four quick sizes alone are all powers of two. Hardware counters and profiler evidence are reported separately. "
              "This report does not infer cache hit rates or physical DRAM bandwidth from logical bytes/time.", "",
             f"Baseline source commit: `{summary['baseline_source_commit']}`. Optimized source commit: "
             f"`{summary['optimized_source_commit']}`. Optimized measured CUDA source SHA-256: "
              f"`{summary['optimized_cuda_source']['sha256']}`. All input bytes are pinned below; raw files remain unchanged.", ""]
    lines += [md_table(["Input", "Bytes", "SHA-256"],
                       [[x["filename"], x["bytes"], x["sha256"]] for x in summary["sources"].values()]), ""]
    return "\n".join(lines)


def latex(summary: dict) -> str:
    full = summary["comparisons"]["full"]
    lines = [r"% Generated from complete reports by tools/summarize_word_optimization.py.",
             r"\section{Measured exact word-kernel optimization}\label{sec:word-optimization}",
             f"Across {full['matched_size_count']} equal working sizes, the optimized implementation beat baseline "
             f"in {full['optimized_gpu_wins']} of {full['comparison_count']} GPU-median comparisons and "
             f"{full['optimized_wall_wins']} of {full['comparison_count']} host-wall-median comparisons. "
             f"GPU baseline/optimized ratios range from {f(full['gpu_ratio_range'][0])} to {f(full['gpu_ratio_range'][1])}.",
             r"This is the bounded integer phi-expression, ASA/NA+JK and digest workload, \emph{not an S2 comparison}. "
             r"Both load paths receive direct streaming addresses, exact bank shift/mask indexing, integer reciprocal remainder "
             r"with one correction, proved-safe 32-bit coefficient arithmetic and warp digest reductions. "
             r"Seeds, recurrence, masks, reset/warm policy and independent 64-bit CPU oracle are unchanged.",
             r"Pairs require equal working bytes, seed, epoch/trial/warm counts, chunk size and bank layout. "
             r"Every corresponding trial's address parameters and every epoch's XOR, modular-sum and visit-count digest match, "
             r"including the final epoch. Digest collisions remain possible; large sets retain sampled CPU replay. "
             r"All raw trials and unmatched sizes are retained in \path{review/word_optimization_summary.json}.",
             r"\subsection{Memory extent and matching}"]
    for mode in ("baseline", "optimized"):
        c = full[mode + "_capacity"]
        lines.append(tex_escape(mode.capitalize()) + f" maximum: {c['largest_working_bytes']} working bytes "
                     f"({f(c['largest_working_bytes']/GIB)} GiB), {f(c['largest_working_over_l2'])} times the "
                     f"reported {f(c['l2_bytes']/MIB)} MiB L2, "
                     f"{100*c['largest_working_fraction_of_total']:.2f}" + r"\% of reported device memory. "
                     f"It covers {c['largest_record_count']} records over {c['largest_bank_count']} banks per epoch; "
                     f"allocation requests total {c['largest_device_requested_allocation_bytes']} bytes and "
                     f"{c['largest_free_after_bytes']} bytes were reported free after allocation.")
    lines += [r"Working bytes include 16N immutable bytes and both 8N-byte state buffers. Every record is visited each epoch. "
              r"The maxima are independent observations; they are paired only when their actual sizes match. "
              r"This extent is not active-warp occupancy, measured cache residency or zero-headroom allocation. "
              r"Shared-device free-memory changes are not exclusive process peak measurements."]
    titles = {"full": "All full-sweep comparisons", "modulus": "Non-power-of-two check: 3 MiB", "quick": "Four-size quick check"}
    for label, report in summary["comparisons"].items():
        md = report["shared_metadata"]
        lines += [r"\subsection{" + titles[label] + "}",
                  f"{report['matched_size_count']} paired sizes and {report['per_trial_epoch_digest_pair_count']} "
                  f"equal trial/epoch digest pairs; {md['epochs_per_trial']} measured epochs, "
                  f"{md['trials_per_pattern_and_fetch']} trials per path and {md['warm_epochs']} warm epoch(s). "
                  f"Chunks contain {md['chunk_logical_bytes']} logical bytes. "
                  f"GPU/wall wins: {report['optimized_gpu_wins']}/{report['comparison_count']} and "
                  f"{report['optimized_wall_wins']}/{report['comparison_count']}.",
                  r"Table entries are median milliseconds for all measured epochs. B/O means baseline divided by optimized; "
                  r"ratios above one favor optimized. GPU time excludes reset/warm, digest readback and sampled checks. "
                  r"Wall time includes measured epochs and those checks, with reset/warm outside."]
        for pattern in PATTERNS:
            for fetch in FETCHES:
                rows = [x for x in report["pairs"] if x["pattern"] == pattern and x["fetch"] == fetch]
                lines += [r"\Needspace{6\baselineskip}", r"\paragraph{" +
                          tex_escape(pattern.replace("_", " ") + " / " + fetch.replace("_", " ")) + "}",
                          tex_table("rrrrrrrr", HEADERS, comparison_rows(rows))]
        if report["baseline_only_working_bytes"] or report["optimized_only_working_bytes"]:
            lines.append("Unpaired baseline bytes: " + tex_escape(str(report["baseline_only_working_bytes"])) +
                         "; unpaired optimized bytes: " + tex_escape(str(report["optimized_only_working_bytes"])) + ".")
    lines += [r"\subsection{Scope and reproducibility}",
              r"Baseline and optimized runs were separate; scheduling, device clocks and desktop activity may differ. "
              r"The few trials give no confidence interval. Quick checks have one trial per path; the 3 MiB reciprocal "
              r"check has ten epochs and two trials. Cache-hit and traffic counters belong to separate profiling evidence. "
              r"Logical bytes/time does not measure physical DRAM bandwidth or a universal texture advantage.",
              r"Baseline source commit: \path{" + summary["baseline_source_commit"] + "}. "
              r"Optimized source commit: \path{" + summary["optimized_source_commit"] + "}. "
              r"Optimized CUDA source SHA-256: \path{" + summary["optimized_cuda_source"]["sha256"] + "}.",
              r"All six raw report receipts, every trial and per-epoch digest are preserved in "
              r"\path{review/word_optimization_summary.json}; readable details are in \path{review/WORD_OPTIMIZATION.md}."]
    return "\n\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    comparisons, sources = {}, {}
    for label, filenames in REPORTS.items():
        raw = []
        for mode, filename in zip(("baseline", "optimized"), filenames):
            data, receipt = load_complete(root / "review" / filename)
            raw.append(data)
            sources[label + "_" + mode] = receipt
        comparisons[label] = compare_reports(label, *raw)
    require(comparisons["quick"]["matched_working_bytes"] == [65536, 262144, 1048576, 4194304],
            "quick reports do not contain the expected four matched sizes")
    modulus = comparisons["modulus"]
    require(modulus["matched_working_bytes"] == [3 * MIB] and
            modulus["shared_metadata"]["epochs_per_trial"] == 10 and
            modulus["shared_metadata"]["trials_per_pattern_and_fetch"] == 2,
            "modulus reports do not match the expected 3 MiB / 10 epoch / 2 trial check")
    source_path = root / "cuda/word_cache_benchmark.cu"
    payload = source_path.read_bytes()
    require(hashlib.sha256(payload).hexdigest() == OPTIMIZED_SOURCE_SHA256,
            "current CUDA source differs from the measured optimized source; preserve its pinned receipt")
    summary = {"schema": "ATOMOS_R15_WORD_OPTIMIZATION_RESULTS_1", "baseline_source_commit": BASELINE_COMMIT,
               "optimized_source_commit": OPTIMIZED_COMMIT,
               "optimized_cuda_source": {"path": "cuda/word_cache_benchmark.cu", "bytes": len(payload),
                                         "sha256": hashlib.sha256(payload).hexdigest()},
               "sources": sources, "comparisons": comparisons}
    artifacts = {root / "review/WORD_OPTIMIZATION.md": markdown(summary),
                 root / "review/word_optimization_summary.json": json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
                 root / "docs/word_optimization.tex": latex(summary)}
    staged = []
    try:
        for destination, content in artifacts.items():
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(destination.name + ".tmp")
            temporary.write_text(content, encoding="utf-8", newline="\n")
            staged.append((temporary, destination))
        for temporary, destination in staged:
            temporary.replace(destination)
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)
    for label, comparison in comparisons.items():
        print(f"{label}: {comparison['matched_size_count']} paired sizes; "
              f"{comparison['per_trial_epoch_digest_pair_count']} matching trial/epoch digests; "
              f"GPU/wall optimized wins {comparison['optimized_gpu_wins']}/{comparison['comparison_count']} "
              f"and {comparison['optimized_wall_wins']}/{comparison['comparison_count']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, TypeError, ValueError, OSError) as error:
        print(f"summarize_word_optimization: {error}; no benchmark was run", file=sys.stderr)
        raise SystemExit(1)
