#!/usr/bin/env python3
"""PR pipeline scorecard: compare two pipeline_metrics.jsonl files.

Produces a markdown table of per-stage wall-time deltas and DRC drift,
optionally in machine-readable JSON.

U8 from the pipeline observability plan.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


# @req(2026-06-28-011, U8-1): Load metrics files in same JSONL format as pipeline_metrics.py
def load_metrics(filepath: Path) -> list[dict[str, Any]]:
    """Load a pipeline_metrics.jsonl file into a list of record dicts."""
    if not filepath.exists():
        return []
    records: list[dict[str, Any]] = []
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


# @req(2026-06-28-011, U8-2): Group records by stage_name and compute deltas
def compute_scorecard(baseline: list[dict], current: list[dict]) -> list[dict]:
    """Compare baseline and current metrics, returning per-stage rows."""
    baseline_by_stage: dict[str, dict] = {}
    for r in baseline:
        sn = r.get("stage_name", r.get("stage", "unknown"))
        baseline_by_stage[sn] = r

    current_by_stage: dict[str, dict] = {}
    for r in current:
        sn = r.get("stage_name", r.get("stage", "unknown"))
        current_by_stage[sn] = r

    all_stages = sorted(set(baseline_by_stage.keys()) | set(current_by_stage.keys()))

    rows: list[dict] = []
    for stage in all_stages:
        b = baseline_by_stage.get(stage)
        c = current_by_stage.get(stage)

        row: dict[str, Any] = {"stage": stage}

        if b is None:
            row["status"] = "new"
            c_wall = _get_wall_time(c)
            row["current_ms"] = int(c_wall) if c_wall is not None else None
            row["baseline_ms"] = None
            row["delta_pct"] = None
            row["drc_delta"] = c.get("drc_delta") if c else None
        elif c is None:
            row["status"] = "removed"
            b_wall = _get_wall_time(b)
            row["baseline_ms"] = int(b_wall) if b_wall is not None else None
            row["current_ms"] = None
            row["delta_pct"] = None
            row["drc_delta"] = None
        else:
            row["status"] = "ok"
            b_wall = _get_wall_time(b)
            c_wall = _get_wall_time(c)
            row["baseline_ms"] = int(b_wall) if b_wall is not None else None
            row["current_ms"] = int(c_wall) if c_wall is not None else None

            if b_wall is not None and b_wall > 0 and c_wall is not None:
                row["delta_pct"] = round((c_wall - b_wall) / b_wall * 100, 1)
            else:
                row["delta_pct"] = None

            row["drc_delta"] = c.get("drc_delta")

        rows.append(row)

    return rows


def _get_wall_time(record: dict | None) -> float | None:
    """Extract wall_time_ms from a metrics record."""
    if record is None:
        return None
    return record.get("metrics", {}).get("wall_time_ms")


# @req(2026-06-28-011, U8-3): Formatted markdown table output
def format_markdown(rows: list[dict]) -> str:
    """Format scorecard rows as a markdown table."""
    lines = [
        "| Stage | Baseline (ms) | Current (ms) | Delta | Drift |",
        "|-------|---------------|--------------|-------|-------|",
    ]
    for r in rows:
        stage_name = r["stage"]
        if r["status"] == "new":
            stage_cell = f"**{stage_name}** (new)"
        elif r["status"] == "removed":
            stage_cell = f"~~{stage_name}~~ (removed)"
        else:
            stage_cell = stage_name

        baseline = str(r["baseline_ms"]) if r["baseline_ms"] is not None else "-"
        current = str(r["current_ms"]) if r["current_ms"] is not None else "-"

        if r["delta_pct"] is not None:
            sign = "+" if r["delta_pct"] >= 0 else ""
            delta = f"{sign}{r['delta_pct']}%"
        elif r["status"] in ("new", "removed"):
            delta = "N/A"
        else:
            delta = "N/A"

        if r["drc_delta"] is not None:
            sign = "+" if r["drc_delta"] > 0 else ""
            drift = f"{sign}{r['drc_delta']} drc"
        else:
            drift = "-"

        lines.append(f"| {stage_cell} | {baseline} | {current} | {delta} | {drift} |")

    return "\n".join(lines)


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(
        prog="pr_scorecard",
        description="Compare two pipeline_metrics.jsonl files and produce a PR scorecard",
    )
    p.add_argument(
        "--baseline",
        required=True,
        type=Path,
        help="Path to baseline pipeline_metrics.jsonl",
    )
    p.add_argument(
        "--current",
        required=True,
        type=Path,
        help="Path to current (PR) pipeline_metrics.jsonl",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON instead of markdown",
    )
    args = p.parse_args()

    baseline_records = load_metrics(args.baseline)
    current_records = load_metrics(args.current)

    rows = compute_scorecard(baseline_records, current_records)

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print("## Pipeline Scorecard")
        print()
        print(format_markdown(rows))

    return 0


if __name__ == "__main__":
    sys.exit(main())
