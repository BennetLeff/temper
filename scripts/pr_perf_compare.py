#!/usr/bin/env python3
"""PR Performance Comparison — compare PR metrics against main-branch JSONL baseline.

Computes a rolling-window median baseline from the last N main-branch entries
for each (module, board, stage) tuple and produces a Markdown delta table for
posting as a PR comment.

Usage:
    python scripts/pr_perf_compare.py \\
        --pr-metrics pr-metrics.json \\
        --main-jsonl pipeline_metrics.jsonl
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

DEFAULT_WINDOW = 5
TIMING_MARGIN = 0.20
COMPLETION_MARGIN = 0.10
IMPROVEMENT_THRESHOLD = 0.10


def load_pr_metrics(path: str) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    with open(p) as f:
        return json.load(f)


def load_main_baselines(
    records: list[dict[str, Any]],
    window: int = DEFAULT_WINDOW,
) -> dict[tuple[str, str, str], dict[str, float]]:
    """Compute median baseline for each (module, board, stage) from main records."""
    groups: dict[tuple[str, str, str], list[dict]] = {}
    for r in records:
        key = (r.get("module", "pipeline"), r.get("board", ""), r.get("stage", ""))
        if key[1] and key[2]:
            groups.setdefault(key, []).append(r)

    baselines: dict[tuple[str, str, str], dict[str, float]] = {}
    for key, group in groups.items():
        group.sort(key=lambda r: r.get("timestamp", ""))
        recent = group[-window:]
        metric_collect: dict[str, list[float]] = {}
        for r in recent:
            for mk, mv in (r.get("metrics") or {}).items():
                if isinstance(mv, (int, float)):
                    metric_collect.setdefault(mk, []).append(float(mv))

        medians: dict[str, float] = {}
        for mk, vals in metric_collect.items():
            medians[mk] = statistics.median(vals) if vals else 0.0
        baselines[key] = medians

    return baselines


def compare(
    pr_metrics: list[dict[str, Any]],
    baselines: dict[tuple[str, str, str], dict[str, float]],
) -> list[dict[str, Any]]:
    """Compare PR metrics against baselines and return delta entries."""
    results: list[dict[str, Any]] = []
    for pr_entry in pr_metrics:
        key = (
            pr_entry.get("module", "pipeline"),
            pr_entry.get("board", ""),
            pr_entry.get("stage", ""),
        )
        baseline = baselines.get(key, {})
        if not baseline:
            results.append({
                "module": key[0],
                "board": key[1],
                "stage": key[2],
                "status": "NO_BASELINE",
                "deltas": {},
            })
            continue

        deltas: dict[str, dict[str, Any]] = {}
        for mk, pr_val in (pr_entry.get("metrics") or {}).items():
            base_val = baseline.get(mk)
            if base_val is None:
                continue
            pr_float = float(pr_val)
            if base_val <= 0:
                continue
            delta_pct = ((pr_float - base_val) / base_val) * 100

            # Determine status
            if mk.endswith("_pct") or mk == "completion_rate":
                delta = abs(delta_pct)
                if delta_pct < 0 and delta > COMPLETION_MARGIN * 100:
                    status = "REGRESSION"
                elif delta_pct > IMPROVEMENT_THRESHOLD * 100:
                    status = "IMPROVED"
                else:
                    status = "OK"
            elif mk.endswith("_ms") or mk.endswith("_seconds"):
                delta = delta_pct
                if delta > TIMING_MARGIN * 100:
                    status = "REGRESSION"
                elif delta < -IMPROVEMENT_THRESHOLD * 100:
                    status = "IMPROVED"
                else:
                    status = "OK"
            else:
                status = "OK"

            deltas[mk] = {
                "main": round(base_val, 2),
                "pr": round(pr_float, 2),
                "delta_pct": round(delta_pct, 1),
                "status": status,
            }

        worst = "OK"
        for d in deltas.values():
            if d["status"] == "REGRESSION":
                worst = "REGRESSION"
                break
            if d["status"] == "IMPROVED" and worst == "OK":
                worst = "IMPROVED"

        results.append({
            "module": key[0],
            "board": key[1],
            "stage": key[2],
            "status": worst,
            "deltas": deltas,
        })

    return results


def format_markdown(results: list[dict[str, Any]]) -> str:
    """Format comparison results as a Markdown table for PR comments."""
    lines: list[str] = []
    lines.append("## Performance Comparison")
    lines.append("")
    lines.append("| Module | Board | Metric | Main | PR | Delta | Status |")
    lines.append("|--------|-------|--------|------|----|-------|--------|")

    has_regression = False
    for res in results:
        if res["status"] == "NO_BASELINE":
            lines.append(
                f"| {res['module']} | {res['board']} | {res['stage']} | "
                f"— | — | No baseline | — |"
            )
            continue

        for mk, delta in sorted(res["deltas"].items()):
            icon = ""
            if delta["status"] == "REGRESSION":
                icon = "🔴"
                has_regression = True
            elif delta["status"] == "IMPROVED":
                icon = "🟢"
            direction = "+" if delta["delta_pct"] >= 0 else ""
            lines.append(
                f"| {res['module']} | {res['board']} | {mk} | "
                f"{delta['main']} | {delta['pr']} | "
                f"{direction}{delta['delta_pct']}% {icon} | "
                f"{delta['status']} |"
            )

    if has_regression:
        lines.append("")
        lines.append("⚠️ Performance regression detected. "
                     "Check the metrics above for slowdowns.")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="PR performance comparison against main-branch JSONL baseline")
    parser.add_argument("--pr-metrics", required=True,
                        help="Path to PR metrics JSON array")
    parser.add_argument("--main-jsonl", required=True,
                        help="Path to main-branch pipeline_metrics.jsonl")
    parser.add_argument("--window", type=int, default=DEFAULT_WINDOW,
                        help=f"Rolling window size for baseline median (default: {DEFAULT_WINDOW})")
    parser.add_argument("--json", action="store_true",
                        help="Output results as JSON")
    args = parser.parse_args()

    pr_metrics = load_pr_metrics(args.pr_metrics)
    if not pr_metrics:
        print("No PR metrics found — skipping comparison.")
        print("")
        print("## Performance Comparison")
        print("")
        print("No profiling data available for this PR.")
        return 0

    # Load main-branch JSONL
    main_path = Path(args.main_jsonl)
    main_records: list[dict[str, Any]] = []
    if main_path.exists():
        with open(main_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        main_records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

    baselines = load_main_baselines(main_records, args.window)
    results = compare(pr_metrics, baselines)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(format_markdown(results))

    return 0


if __name__ == "__main__":
    sys.exit(main())
