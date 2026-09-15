#!/usr/bin/env python3
"""Summarize completed resident-count and separate word-cache measurements.

No benchmark is launched. Both complete input reports are validated before
any output is written. All raw trial fields are retained in the summary JSON.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
import statistics
import sys

MIB = 1024 ** 2
GIB = 1024 ** 3
PATTERNS = ("streaming", "seeded_coprime_affine_permutation")
FETCHES = ("integer_texture", "global")
BENCHMARK_SOURCE_COMMIT = "4d8992292a7fa0fc43fc050ec090512552f7d067"


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def number(value, label: str, positive: bool = False) -> float:
    require(type(value) in (int, float), f"{label}: expected a number")
    result = float(value)
    require(math.isfinite(result) and (result > 0 if positive else result >= 0),
            f"{label}: invalid measurement {value!r}")
    return result


def timing(value: dict, label: str, trials: int = 5) -> dict:
    values = value["samples_ms"]
    require(len(values) == trials, f"{label}: expected {trials} raw trials")
    samples = [number(x, label, positive=True) for x in values]
    observed = number(value["median_ms"], label, positive=True)
    require(math.isclose(observed, statistics.median(samples), rel_tol=1e-9, abs_tol=1e-9),
            f"{label}: reported median differs from raw trials")
    return {"median_ms": observed, "samples_ms": samples}


def load_complete(path: Path) -> tuple[dict, dict]:
    if not path.is_file():
        raise ValueError(f"waiting for complete report: {path}")
    payload = path.read_bytes()
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ValueError(f"report is not complete valid JSON: {path}: {error}") from error
    require(isinstance(data, dict), f"{path}: report must be an object")
    return data, {"filename": path.name, "bytes": len(payload),
                  "sha256": hashlib.sha256(payload).hexdigest()}


def summarize_counts(data: dict) -> dict:
    require(data.get("profile") == "R15-RESIDENT-EXACT-SPHERICAL-COUNT", "wrong resident report profile")
    require("correctness_failures" in data, "resident report lacks final completion field")
    rows = data["workloads"]
    expected = set(itertools.product(("uniform", "clustered", "great_circle"),
                                    (16384, 262144, 1048576), (256, 4096, 65536)))
    actual = {(row["family"], row["points"], row["queries"]) for row in rows}
    require(len(rows) == 27 and actual == expected, "resident full report must contain all 27 distinct cases")
    cases = []
    for row in rows:
        label = f"{row['family']}/{row['points']}/{row['queries']}"
        configurations = row["cpu_configurations"]
        require({c["threads"] for c in configurations} == {1, 4, 20},
                f"{label}: expected all CPU configurations 1/4/20")
        require(len(configurations) == 3, f"{label}: duplicate CPU configuration")
        cpu = []
        for config in configurations:
            cpu.append({"threads": config["threads"],
                        "s2": timing(config["s2"], label + "/s2"),
                        "bvh": timing(config["bvh_count"], label + "/bvh")})
        best_s2 = min(cpu, key=lambda c: c["s2"]["median_ms"])
        best_bvh = min(cpu, key=lambda c: c["bvh"]["median_ms"])
        require(math.isclose(row["best_s2_ms"], best_s2["s2"]["median_ms"], rel_tol=1e-9),
                f"{label}: incorrect best S2 summary")
        require(math.isclose(row["best_bvh_ms"], best_bvh["bvh"]["median_ms"], rel_tol=1e-9),
                f"{label}: incorrect best BVH summary")
        gpu = {key: timing(row[key], label + "/" + key)
               for key in ("texture_device", "global_device", "texture_host_complete", "global_host_complete")}
        uncertain = int(row["uncertain_points"])
        tf, gf = int(row["texture_fallback_queries"]), int(row["global_fallback_queries"])
        require(uncertain >= 0 and 0 <= tf <= row["queries"] and 0 <= gf <= row["queries"],
                f"{label}: invalid unresolved/fallback counts")
        require((uncertain == 0) == (tf == 0) and tf == gf,
                f"{label}: unresolved and texture/global fallback counts disagree")
        require(row["count_readback_bytes"] == 16 * row["queries"], f"{label}: count readback size mismatch")
        require(row["kernel_repetitions_per_sample"] == 5, f"{label}: unexpected repetition count")
        s2_ms = best_s2["s2"]["median_ms"]
        bvh_ms = best_bvh["bvh"]["median_ms"]
        tc = gpu["texture_host_complete"]["median_ms"]
        gc = gpu["global_host_complete"]["median_ms"]
        cases.append({"family": row["family"], "points": row["points"], "queries": row["queries"],
                      "hits": row["hits"], "all_results_equal": row["all_results_equal"],
                      "cpu_configurations": cpu,
                      "best_s2": {"threads": best_s2["threads"], **best_s2["s2"]},
                      "best_bvh": {"threads": best_bvh["threads"], **best_bvh["bvh"]},
                      **gpu, "uncertain_points": uncertain,
                      "texture_fallback_queries": tf, "global_fallback_queries": gf,
                      "device_only_count_is_complete": uncertain == 0,
                      "best_s2_over_texture_complete": s2_ms / tc,
                      "best_bvh_over_texture_complete": bvh_ms / tc,
                      "best_cpu_over_texture_complete": min(s2_ms, bvh_ms) / tc,
                      "best_s2_over_global_complete": s2_ms / gc,
                      "best_cpu_over_global_complete": min(s2_ms, bvh_ms) / gc,
                      "raw": row})
    failures = sum(not case["all_results_equal"] for case in cases)
    require(failures == data["correctness_failures"], "resident failure total does not match cases")
    return {"case_count": len(cases), "all_results_equal": failures == 0,
            "correctness_failures": failures,
            "texture_complete_wins_vs_best_s2": sum(c["best_s2_over_texture_complete"] > 1 for c in cases),
            "texture_complete_wins_vs_best_bvh": sum(c["best_bvh_over_texture_complete"] > 1 for c in cases),
            "texture_complete_wins_vs_best_cpu": sum(c["best_cpu_over_texture_complete"] > 1 for c in cases),
            "global_complete_wins_vs_best_cpu": sum(c["best_cpu_over_global_complete"] > 1 for c in cases),
            "texture_device_wins_vs_global": sum(c["texture_device"]["median_ms"] < c["global_device"]["median_ms"] for c in cases),
            "texture_complete_wins_vs_global": sum(c["texture_host_complete"]["median_ms"] < c["global_host_complete"]["median_ms"] for c in cases),
            "texture_complete_vs_best_s2_ratio_range": [min(c["best_s2_over_texture_complete"] for c in cases),
                                                        max(c["best_s2_over_texture_complete"] for c in cases)],
            "cases_with_unresolved_points": sum(c["uncertain_points"] > 0 for c in cases),
            "unresolved_point_total": sum(c["uncertain_points"] for c in cases),
            "texture_fallback_query_total": sum(c["texture_fallback_queries"] for c in cases),
            "initial_gpu_build_ms": rows[0]["gpu_build_ms"],
            "initial_source_upload_ms": rows[0]["source_upload_ms"],
            "metadata": {k: v for k, v in data.items() if k != "workloads"}, "cases": cases}


def summarize_words(data: dict) -> dict:
    require(data.get("profile") == "ATOMOS-WORD-CACHE-PHI-JK-R1", "wrong word-cache report profile")
    require("passed" in data and "completed_working_sets" in data, "word-cache report lacks final completion fields")
    require(data.get("S2_comparison") is False, "word-cache report must remain separate from S2")
    l2 = int(data["l2_bytes"])
    require(l2 > 0, "word-cache report has no L2 capacity")
    trials = int(data["trials_per_pattern_and_fetch"])
    epochs = int(data["epochs_per_trial"])
    require(trials > 0 and epochs > 0, "word-cache report has no measured trials/epochs")
    working_sets = []
    failures = []
    for row in data["working_sets"]:
        if row.get("failed"):
            failures.append(row)
            continue
        working = int(row["working_bytes"])
        records = int(row["record_count"])
        require(working == records * 32, "word-cache working bytes differ from source plus two state buffers")
        require(row["immutable_seed_bytes"] == records * 16 and
                row["persistent_state_bytes_two_buffers"] == records * 16, "word-cache state/source size mismatch")
        require(row["all_allocated_records_visited_per_epoch"] is True, "word-cache report lacks complete record coverage")
        require(row["free_after_bytes"] >= data["reserve_bytes"], "word-cache reserve was not preserved")
        groups = []
        for pattern, fetch in itertools.product(PATTERNS, FETCHES):
            selected = sorted((x for x in row["trials"] if x["pattern"] == pattern and x["fetch"] == fetch),
                              key=lambda x: x["trial"])
            require([x["trial"] for x in selected] == list(range(trials)), "word-cache trial coverage is incomplete")
            gpu_times, wall_times = [], []
            for trial in selected:
                gpu_times.append(number(trial["gpu_ms_sum"], "word GPU time", positive=True))
                wall_times.append(number(trial["measured_host_wall_ms"], "word wall time", positive=True))
                require(len(trial["epoch_gpu_ms"]) == epochs and len(trial["epochs"]) == epochs,
                        "word-cache epoch coverage is incomplete")
                require(all(e["visited_records"] == records for e in trial["epochs"]),
                        "word-cache epoch did not visit every allocated state record")
                require(trial["checksum_agreement"] is True and trial["sample_oracle_agreement"] is True,
                        "word-cache trial verification failed")
                require(trial["logical_record_state_bytes"] == working * epochs, "word-cache logical traffic mismatch")
                require(math.isclose(sum(trial["epoch_gpu_ms"]), trial["gpu_ms_sum"], rel_tol=1e-9, abs_tol=1e-6),
                        "word-cache per-epoch GPU times do not sum to trial time")
            groups.append({"pattern": pattern, "fetch": fetch,
                           "gpu_samples_ms": gpu_times, "gpu_median_ms": statistics.median(gpu_times),
                           "wall_samples_ms": wall_times, "wall_median_ms": statistics.median(wall_times),
                           "raw_trials": selected})
        require(len(row["trials"]) == 4 * trials, "word-cache report contains unclassified trials")
        comparisons = []
        for pattern in PATTERNS:
            texture = next(g for g in groups if g["pattern"] == pattern and g["fetch"] == "integer_texture")
            global_ = next(g for g in groups if g["pattern"] == pattern and g["fetch"] == "global")
            comparisons.append({"pattern": pattern,
                                "global_over_texture_gpu": global_["gpu_median_ms"] / texture["gpu_median_ms"],
                                "global_over_texture_wall": global_["wall_median_ms"] / texture["wall_median_ms"]})
        working_sets.append({"working_bytes": working, "working_mib": working / MIB,
                             "working_over_l2": working / l2, "record_count": records,
                             "groups": groups, "comparisons": comparisons, "raw": row})
    require(len(working_sets) == data["completed_working_sets"] and
            len(failures) == data["failed_working_sets"], "word-cache completion totals do not match")
    require(bool(data["passed"]) == (not failures), "word-cache passed flag disagrees with failures")
    require(working_sets, "word-cache full report contains no completed working sets")
    largest = max(working_sets, key=lambda x: x["working_bytes"])
    ratios = [c for w in working_sets for c in w["comparisons"]]
    return {"device": data["device"], "l2_bytes": l2, "l2_mib": l2 / MIB,
            "working_set_count": len(working_sets), "failed_working_sets": failures,
            "all_reported_checks_passed": data["passed"],
            "measured_trial_count": sum(len(w["raw"]["trials"]) for w in working_sets),
            "texture_gpu_wins_vs_global": sum(c["global_over_texture_gpu"] > 1 for c in ratios),
            "texture_wall_wins_vs_global": sum(c["global_over_texture_wall"] > 1 for c in ratios),
            "pattern_working_set_comparisons": len(ratios),
            "largest_working_bytes": largest["working_bytes"],
            "largest_working_over_l2": largest["working_over_l2"],
            "largest_working_memory_fraction": largest["raw"]["total_memory_fraction_for_working_set"],
            "metadata": {k: v for k, v in data.items() if k != "working_sets"}, "working_sets": working_sets}


def f(value) -> str:
    return format(value, ".4g")


def series(values) -> str:
    return " / ".join(f(x) for x in values)


def md_table(headers, rows) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(str(x).replace("|", "\\|") for x in row) + " |" for row in rows)
    return "\n".join(lines)


def cache_group(working: dict, pattern: str, fetch: str) -> dict:
    return next(g for g in working["groups"] if g["pattern"] == pattern and g["fetch"] == fetch)


def markdown(summary: dict) -> str:
    counts, words = summary["resident_counts"], summary["word_cache"]
    source = summary["sources"]
    lines = ["# Resident count and word-cache measurements", "",
             f"The resident count comparison contains **{counts['case_count']} cases**. "
             f"Exact answers {'matched in every case' if counts['all_results_equal'] else 'FAILED to match in some cases'}. "
             f"Texture with host-complete counts was faster than the best measured S2 configuration in "
             f"**{counts['texture_complete_wins_vs_best_s2']}/{counts['case_count']}** cases and than the best measured "
             f"CPU implementation in **{counts['texture_complete_wins_vs_best_cpu']}/{counts['case_count']}** cases.", "",
             "These wins apply to inclusive spherical COUNT queries over the exact supplied IEEE seeds. "
             "They are not ID-return, general-S2, physical-position-accuracy or photonics measurements. "
             "Best CPU means the lowest measured median among the reported 1/4/20-worker configurations; "
             "all configurations and trials are retained below and in the JSON.", "",
             "The separate word-cache probe executes bounded integer phi-expression and ASA/NA+JK state updates. "
             "It is **not an S2 comparison**. Working bytes include immutable records and BOTH persistent state buffers. "
             "Its CUDA-event sums and host wall times are reported separately.", "",
             "These are the preserved baseline word-cache measurements from `word_cache_full.json`. "
             "Later optimized probes require separate reports and do not replace these observations.", "",
             f"Device: **{words['device']}**. Reported L2: **{f(words['l2_mib'])} MiB** "
             f"({words['l2_bytes']:,} bytes). The largest tested working set was "
             f"**{f(words['largest_working_bytes']/GIB)} GiB**, "
             f"**{f(words['largest_working_over_l2'])} times L2**, and "
             f"**{100*words['largest_working_memory_fraction']:.2f}%** of reported device memory. "
             "The configured VRAM reserve remained available; this is an admitted-capacity sweep, not a claim of zero-headroom allocation.", "",
             "## All resident count cases", "",
             "Times are median milliseconds. CPU cells include chosen worker count. T/G mean integer texture/global loads. "
             "Device time is per resident launch (five launches per sample); complete time includes a launch, "
             "count readback and any exact host fallback. U is unresolved point total; Ft/Fg count queries needing "
             "texture/global fallback. A device-only result is a complete exact count only when U=0. Setup is excluded.", ""]
    rows = []
    for case in counts["cases"]:
        rows.append([case["family"], case["points"], case["queries"],
                     f"{f(case['best_s2']['median_ms'])} ({case['best_s2']['threads']})",
                     f"{f(case['best_bvh']['median_ms'])} ({case['best_bvh']['threads']})",
                     f(case["texture_device"]["median_ms"]), f(case["texture_host_complete"]["median_ms"]),
                     f(case["global_device"]["median_ms"]), f(case["global_host_complete"]["median_ms"]),
                     f"{case['uncertain_points']}/{case['texture_fallback_queries']}/{case['global_fallback_queries']}"])
    lines += [md_table(["Family", "Points", "Queries", "Best S2 ms (t)", "Best BVH ms (t)",
                        "T device", "T complete", "G device", "G complete", "U/Ft/Fg"], rows), "",
              f"There were {counts['unresolved_point_total']} unresolved point decisions across "
              f"{counts['cases_with_unresolved_points']} cases, requiring complete host fallback for "
              f"{counts['texture_fallback_query_total']} queries per access mode. Texture device time beat global loads "
              f"in {counts['texture_device_wins_vs_global']}/{counts['case_count']} cases; texture complete time did so "
              f"in {counts['texture_complete_wins_vs_global']}/{counts['case_count']}. "
              "The measured GPU advantage over CPU therefore does not establish a texture-cache advantage.", "",
              f"The first GPU construction cost **{counts['initial_gpu_build_ms']:.4f} ms**, including "
              f"**{counts['initial_source_upload_ms']:.4f} ms** reported source preparation/upload. "
              "This cold setup is excluded from the repeated-query timings; all later setup measurements are retained below.", "",
              "CPU S2 uses its public closest-point API with reused result buffers, then exact refinement and counting; "
              "that public API internally materializes candidates. The BVH count method allocates no ID list. "
              "GPU device-mode order alternates across trials. CPU/configuration order and the host-complete "
              "texture/global blocks are fixed. Results use warm, repeated input sets and five trials without "
              "confidence intervals; minimum medians are selection statistics, not universal speed guarantees.", "",
              "## Resident trials and setup", ""]
    for case in counts["cases"]:
        raw = case["raw"]
        lines += [f"<details><summary>{case['family']}: {case['points']:,} points, {case['queries']:,} queries</summary>", "",
                  f"Hits: {case['hits']:,}; exact equality: {case['all_results_equal']}. "
                  f"Build ms S2/BVH/GPU: {f(raw['s2_build_ms'])}/{f(raw['host_build_ms'])}/{f(raw['gpu_build_ms'])}. "
                  f"Source/query upload ms: {f(raw['source_upload_ms'])}/{f(raw['query_upload_ms'])}. "
                  f"Resident source/query bytes: {raw['source_resident_bytes']:,}/{raw['query_resident_bytes']:,}.", ""]
        trial_rows = []
        for config in case["cpu_configurations"]:
            for backend in ("s2", "bvh"):
                trial_rows.append([f"{backend} {config['threads']} workers", series(config[backend]["samples_ms"])])
        for backend in ("texture_device", "texture_host_complete", "global_device", "global_host_complete"):
            trial_rows.append([backend, series(case[backend]["samples_ms"])])
        lines += [md_table(["Method", "Every measured sample (ms)"], trial_rows), "", "</details>", ""]
    lines += ["## Word/state coverage and capacity", "",
              f"All **{words['working_set_count']} completed working sets** report every allocated record visited "
              f"in each epoch, across **{words['measured_trial_count']} measured trials**. "
              "Full CPU replay is performed only for the small sets flagged below. Larger sets compare complete "
              "aggregate digests across texture/global/pattern/trial paths plus independently replayed sampled words. "
              "Digest agreement can collide; it is not a byte-for-byte readback proof of every large state buffer.", ""]
    coverage = []
    for working in words["working_sets"]:
        r = working["raw"]
        coverage.append([working["working_bytes"], f(working["working_over_l2"]), r["record_count"],
                         r["immutable_seed_bytes"], r["persistent_state_bytes_two_buffers"],
                         r["device_requested_allocation_bytes"], r["free_after_bytes"], r["sampled_record_count"],
                         "full replay + digest" if r["full_CPU_oracle"] else "sample replay + digest"])
    lines += [md_table(["Working bytes", "L2 multiple", "Records/epoch", "Seed bytes", "Both state buffers",
                       "Requested allocation bytes", "Free after bytes", "Sampled records", "CPU coverage"], coverage), "",
              "The same record permutation covers all records exactly once per epoch. Two buffers hold prior and next "
              "state; zero-sign transitions may hold their value while still being visited. Reported allocation bytes "
              "include scratch, while working bytes count records plus both state buffers. The driver free-memory delta "
              "is an observation on a shared device, not an exclusive process peak-memory measurement.", "",
              "## Every word-cache timing trial", "",
              f"Each slash-separated list is trial order 0 through {words['metadata']['trials_per_pattern_and_fetch']-1}. "
              f"Times are milliseconds summed across {words['metadata']['epochs_per_trial']} measured epochs per trial. "
              "GPU sums exclude reset/warmup, checksum readback and sample verification. Host wall includes the measured "
              "epochs, digest readback/aggregation and per-epoch sample verification; reset/warmup are outside both. "
              "Raw per-epoch timings, checksums and setup costs remain in the JSON.", ""]
    for pattern in PATTERNS:
        lines += [f"### {pattern.replace('_', ' ')}", ""]
        trial_rows = []
        for working in words["working_sets"]:
            tx, gl = (cache_group(working, pattern, fetch) for fetch in FETCHES)
            trial_rows.append([f(working["working_mib"]), f(working["working_over_l2"]),
                               series(tx["gpu_samples_ms"]), series(gl["gpu_samples_ms"]),
                               series(tx["wall_samples_ms"]), series(gl["wall_samples_ms"])])
        lines += [md_table(["Working MiB", "L2 multiple", "Texture GPU trials", "Global GPU trials",
                           "Texture wall trials", "Global wall trials"], trial_rows), ""]
    lines += [f"Texture was faster than global loads in {words['texture_gpu_wins_vs_global']}/"
              f"{words['pattern_working_set_comparisons']} GPU-median comparisons and "
              f"{words['texture_wall_wins_vs_global']}/{words['pattern_working_set_comparisons']} wall-median comparisons. "
              "These are access-path comparisons for this word/state workload. Cache hit rates were not measured and "
              "no persisting-L2 access window was set. Logical GB/s counts specified record/state bytes; it is not a "
              "hardware DRAM-bandwidth measurement or proof that texture loads always win.", "",
              "## Source receipts", "",
              f"Measured benchmark source commit: `{summary['benchmark_source_commit']}`. "
              "The source revision identifies these measurements; it does not imply subsequent working-tree edits were measured.", "",
              f"[Resident raw report]({source['resident']['filename']}), "
              f"[word-cache raw report]({source['word_cache']['filename']}) and "
              "[derived summary with every raw trial](resident_summary.json).", "",
              f"Resident SHA-256: `{source['resident']['sha256']}`.", "",
              f"Word-cache SHA-256: `{source['word_cache']['sha256']}`.", ""]
    if words["failed_working_sets"]:
        lines += ["Failed working sets (not omitted):", "", json.dumps(words["failed_working_sets"], indent=2), ""]
    return "\n".join(lines)


def tex_escape(value) -> str:
    replacements = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
                    "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
                    "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    return "".join(replacements.get(c, c) for c in str(value))


def tex_table(columns: str, header: list[str], rows: list[list[str]], size: str = "scriptsize") -> str:
    head = " & ".join(header) + r" \\"
    return "\n".join([r"\begingroup", "\\" + size, r"\setlength{\tabcolsep}{2.5pt}",
                      r"\renewcommand{\arraystretch}{1.16}", r"\begin{longtable}{" + columns + "}",
                      r"\toprule", head, r"\midrule\endfirsthead", r"\toprule", head,
                      r"\midrule\endhead", r"\bottomrule\endfoot",
                      *(" & ".join(row) + r" \\" for row in rows), r"\end{longtable}", r"\endgroup"])


def tex_series(values) -> str:
    return r"\shortstack[r]{" + r"\\".join(f(x) for x in values) + "}"


def latex(summary: dict) -> str:
    c, w = summary["resident_counts"], summary["word_cache"]
    lines = [r"% Generated only from complete, validated reports by tools/summarize_resident.py.",
             r"\section{Measured resident counts and word working sets}", r"\label{sec:resident-results}",
             f"All {c['case_count']} resident count cases were measured; " +
             ("every complete answer matched." if c["all_results_equal"] else "some complete answers FAILED equality checks."),
             f"The texture path with complete host-visible counts beat the best measured S2 configuration in "
             f"{c['texture_complete_wins_vs_best_s2']} of {c['case_count']} cases and the best measured CPU implementation in "
             f"{c['texture_complete_wins_vs_best_cpu']} of {c['case_count']} cases.",
             r"These results concern inclusive spherical \emph{counts} over the supplied exact IEEE seeds. They are not ID-return, general-S2, physical-position-accuracy or photonics measurements.",
             r"The word-cache results below are the preserved baseline in \path{review/word_cache_full.json}; later optimizations require separate measurement records.",
             r"\subsection{Every resident count case}",
             r"All entries are median milliseconds; CPU cells show the chosen worker count in parentheses. T/G mean integer texture/global loads. Device time is per resident launch, with five launches per sample. Complete time includes launch, count readback and any host exact fallback. The last column is unresolved points / texture fallback queries / global fallback queries."]
    rows = []
    for case in c["cases"]:
        rows.append([tex_escape(case["family"]), str(case["points"]), str(case["queries"]),
                     f"{f(case['best_s2']['median_ms'])} ({case['best_s2']['threads']})",
                     f"{f(case['best_bvh']['median_ms'])} ({case['best_bvh']['threads']})",
                     f(case["texture_device"]["median_ms"]), f(case["texture_host_complete"]["median_ms"]),
                     f(case["global_device"]["median_ms"]), f(case["global_host_complete"]["median_ms"]),
                     f"{case['uncertain_points']}/{case['texture_fallback_queries']}/{case['global_fallback_queries']}"])
    lines += [tex_table("lrrrrrrrrr", ["Family", "$N$", "$Q$", "S2 best", "BVH best", "T dev.", "T comp.", "G dev.", "G comp.", "U/Ft/Fg"], rows),
              f"There were {c['unresolved_point_total']} unresolved point decisions across {c['cases_with_unresolved_points']} cases; "
              f"{c['texture_fallback_query_total']} queries per access mode required complete host fallback. Texture beat global loads "
              f"in {c['texture_device_wins_vs_global']} of {c['case_count']} device-time comparisons and "
              f"{c['texture_complete_wins_vs_global']} of {c['case_count']} complete-time comparisons. "
              "The GPU-over-CPU gain therefore does not establish a texture-cache advantage.",
              f"The first GPU construction cost {c['initial_gpu_build_ms']:.4f} ms, including "
              f"{c['initial_source_upload_ms']:.4f} ms reported source preparation/upload. This cold setup is excluded "
              "from repeated-query timings; later setup costs remain in the complete report.",
              r"Device-only counts are complete only where the unresolved count is zero. Every 1/4/20-worker configuration and raw trial is retained in \path{review/resident_summary.json}; best means the lowest measured median, not an unreported preferred configuration.",
              r"S2 uses its public closest-point API with reused candidate vectors, followed by exact refinement/counting. The BVH count avoids ID allocation. Setup is excluded. GPU device-mode order alternates; CPU/configuration and host-complete mode blocks have fixed order. Five warm trials provide no confidence interval or universal speed guarantee.",
              r"\subsection{Word/state coverage through the memory hierarchy}",
              tex_escape(w["device"]) + f" reports {f(w['l2_mib'])} MiB of L2 ({w['l2_bytes']} bytes). "
              f"The largest working set was {f(w['largest_working_bytes']/GIB)} GiB, "
              f"{f(w['largest_working_over_l2'])} times L2 and {100*w['largest_working_memory_fraction']:.2f}"
              + r"\% of reported device memory. The configured VRAM reserve remained available.",
              r"This is a separate bounded integer phi-expression and ASA/NA+JK word/state workload, \emph{not an S2 comparison}. Working bytes include immutable records plus both persistent state buffers. Every record is visited in every epoch; zero-sign holds may leave a value unchanged."]
    rows = []
    for working in w["working_sets"]:
        raw = working["raw"]
        rows.append([f(working["working_mib"]), f(working["working_over_l2"]), str(working["record_count"]),
                     f(raw["device_requested_allocation_bytes"]/MIB), str(raw["sampled_record_count"]),
                     "Full replay" if raw["full_CPU_oracle"] else "Sample replay"])
    lines += [tex_table("rrrrrl", ["Working MiB", "L2 multiple", "Records/epoch", "Allocated MiB", "Sampled", "CPU oracle"], rows),
              r"All epochs compare complete aggregate digests across access modes, traversal patterns and trials. Full CPU replay is restricted to the small sets flagged above; larger sets use sampled independent word replay. Digest agreement can collide and is not a byte-for-byte readback proof of every large buffer. Exact seed/state byte counts, free-memory observations and source receipts are retained in the summary JSON.",
              r"\subsection{Every word-cache timing trial}",
              f"Each cell lists trials in increasing trial order. Times are milliseconds for {w['metadata']['epochs_per_trial']} measured epochs per trial. "
              r"GPU sums exclude reset/warmup, digest readback and sampled verification. Host wall includes measured epochs, digest aggregation/readback and per-epoch sampled verification; reset/warmup are outside the timer. Raw per-epoch values remain in the JSON."]
    for pattern in PATTERNS:
        lines += [r"\Needspace{6\baselineskip}", r"\paragraph{" + tex_escape(pattern.replace("_", " ").capitalize()) + "}"]
        rows = []
        for working in w["working_sets"]:
            tx, gl = (cache_group(working, pattern, fetch) for fetch in FETCHES)
            rows.append([f(working["working_mib"]), f(working["working_over_l2"]),
                         tex_series(tx["gpu_samples_ms"]), tex_series(gl["gpu_samples_ms"]),
                         tex_series(tx["wall_samples_ms"]), tex_series(gl["wall_samples_ms"])])
        lines.append(tex_table("rrp{2.85cm}p{2.85cm}p{2.85cm}p{2.85cm}",
                               ["MiB", "L2 ratio", "Texture GPU", "Global GPU", "Texture wall", "Global wall"], rows))
    lines += [f"Texture beat global loads in {w['texture_gpu_wins_vs_global']} of {w['pattern_working_set_comparisons']} "
              f"GPU-median comparisons and {w['texture_wall_wins_vs_global']} of {w['pattern_working_set_comparisons']} wall-median comparisons. "
              r"Cache hit rates were not measured and no persisting-L2 window was set. Logical GB/s is workload throughput, not measured physical DRAM bandwidth or a universal texture advantage.",
              r"\paragraph{Reproducible source receipts.}",
              r"Measured benchmark source commit: \path{" + summary["benchmark_source_commit"] + r"}. Subsequent source edits are not implied to have been measured by this record.",
              r"All trials, setup timings and metadata are preserved in \path{review/resident_summary.json}. Its inputs are \path{review/resident_full.json} and \path{review/word_cache_full.json}.",
              r"\begin{small}\noindent Resident SHA-256: \path{" + summary["sources"]["resident"]["sha256"] + r"}.\par",
              r"\noindent Word-cache SHA-256: \path{" + summary["sources"]["word_cache"]["sha256"] + r"}.\end{small}", ""]
    if w["failed_working_sets"]:
        lines.append(r"\textbf{Some admitted working sets failed; see the retained failure records.}")
    return "\n\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    resident_data, resident_source = load_complete(root / "review/resident_full.json")
    cache_data, cache_source = load_complete(root / "review/word_cache_full.json")
    summary = {"schema": "ATOMOS_R15_RESIDENT_RESULTS_1",
               "benchmark_source_commit": BENCHMARK_SOURCE_COMMIT,
               "word_cache_report_role": "preserved baseline; later optimization reports remain separate",
               "sources": {"resident": resident_source, "word_cache": cache_source},
               "resident_counts": summarize_counts(resident_data), "word_cache": summarize_words(cache_data)}
    artifacts = {root / "review/RESIDENT_RESULTS.md": markdown(summary),
                 root / "review/resident_summary.json": json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
                 root / "docs/resident_results.tex": latex(summary)}
    staged = []
    try:
        for destination, text in artifacts.items():
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(destination.name + ".tmp")
            temporary.write_text(text, encoding="utf-8", newline="\n")
            staged.append((temporary, destination))
        for temporary, destination in staged:
            temporary.replace(destination)
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)
    counts, words = summary["resident_counts"], summary["word_cache"]
    print(f"Generated 3 artifacts: {counts['case_count']} count cases, "
          f"{words['working_set_count']} working sets, {words['measured_trial_count']} word-cache trials; "
          f"L2={words['l2_mib']:g} MiB; complete texture wins vs best S2/CPU="
          f"{counts['texture_complete_wins_vs_best_s2']}/{counts['texture_complete_wins_vs_best_cpu']}.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, TypeError, ValueError, OSError) as error:
        print(f"summarize_resident: {error}; no new benchmark was run", file=sys.stderr)
        raise SystemExit(1)
