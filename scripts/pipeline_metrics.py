#!/usr/bin/env python3
"""Pipeline metrics CLI — time-series trend querying (R2).

Usage:
    python scripts/pipeline_metrics.py trend --board temper --stage closure
    python scripts/pipeline_metrics.py trend --board temper --stage closure --json
    python scripts/pipeline_metrics.py trend --list
"""

from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _find_repo_root() -> Path:
    p = Path.cwd()
    while not (p / ".git").exists() and p != p.parent:
        p = p.parent
    return p


def _setup_path(repo_root: Path) -> None:
    src_path = repo_root / "packages" / "temper-placer" / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))


def _parse_window(window: str) -> timedelta:
    num = int(window[:-1])
    unit = window[-1]
    if unit == "d":
        return timedelta(days=num)
    print(f"ERROR: Unsupported window unit '{window}' (use Nd, e.g. 30d)", file=sys.stderr)
    sys.exit(2)


def _compute_trends(
    records: list[dict], board: str, stage: str, window: timedelta, sigma_multiple: float
) -> dict:
    if not records:
        return {"board": board, "stage": stage, "error": "No records found"}

    filtered = [r for r in records if r.get("board") == board and r.get("stage") == stage]

    if not filtered:
        return {"board": board, "stage": stage, "error": "No records match board/stage"}

    now = datetime.now(timezone.utc)
    cutoff = now - window

    windowed: list[dict] = []
    for r in filtered:
        try:
            ts = datetime.fromisoformat(r["timestamp"])
        except (ValueError, KeyError):
            continue
        if ts >= cutoff:
            windowed.append(r)

    if len(windowed) < 2:
        return {
            "board": board,
            "stage": stage,
            "error": f"Need >=2 data points in window, have {len(windowed)}",
        }

    windowed.sort(key=lambda r: r["timestamp"])
    latest = windowed[-1]

    all_metric_keys: set[str] = set()
    for r in windowed:
        all_metric_keys.update(r.get("metrics", {}).keys())

    metrics_analysis: list[dict] = []
    has_regression = False

    for key in sorted(all_metric_keys):
        values = [
            r.get("metrics", {}).get(key)
            for r in windowed
            if r.get("metrics", {}).get(key) is not None
        ]
        if len(values) < 2:
            continue

        mu = sum(values) / len(values)
        variance = sum((v - mu) ** 2 for v in values) / max(1, len(values) - 1)
        sigma = math.sqrt(variance) if variance > 0 else 0.0

        current = latest.get("metrics", {}).get(key)
        if current is None:
            continue

        drift_sigma = abs(current - mu) / sigma if sigma > 0 else 0.0
        if drift_sigma > sigma_multiple:
            status = "REGRESSION"
            has_regression = True
        elif drift_sigma > sigma_multiple * 0.5:
            status = "WARN"
        else:
            status = "OK"

        metrics_analysis.append({
            "metric": key,
            "latest": current,
            "mean": round(mu, 4),
            "sigma": round(sigma, 4),
            "drift_sigma": round(drift_sigma, 4),
            "status": status,
            "data_points": len(values),
        })

    return {
        "board": board,
        "stage": stage,
        "window_days": window.days,
        "sigma_multiple": sigma_multiple,
        "data_points": len(windowed),
        "has_regression": has_regression,
        "metrics": metrics_analysis,
    }


def _format_table(result: dict) -> str:
    lines = [
        f"Board: {result['board']}, Stage: {result['stage']}",
        f"Window: {result.get('window_days', '?')}d, "
        f"Sigma multiple: {result.get('sigma_multiple', 1.0)}, "
        f"Data points: {result.get('data_points', 0)}",
        "",
        f"{'Metric':<24} {'Latest':>10} {'Mean':>10} {'Sigma':>10} {'Drift':>8} Status",
        "-" * 78,
    ]

    for m in result.get("metrics", []):
        lines.append(
            f"{m['metric']:<24} {m['latest']:>10.2f} {m['mean']:>10.2f} "
            f"{m['sigma']:>10.2f} {m['drift_sigma']:>7.2f}s "
            f"{m['status']}"
        )

    if result.get("error"):
        lines.append(f"\nERROR: {result['error']}")

    return "\n".join(lines)


def cmd_list(as_json: bool) -> None:
    from temper_placer.regression.metrics_recorder import find_metrics_file, load_metrics

    repo_root = _find_repo_root()
    filepath = find_metrics_file(repo_root)
    records = load_metrics(filepath)

    pairs: set[tuple[str, str]] = set()
    for r in records:
        b = r.get("board", "")
        s = r.get("stage", "")
        if b and s:
            pairs.add((b, s))

    if as_json:
        print(json.dumps(
            [{"board": b, "stage": s} for b, s in sorted(pairs)], indent=2
        ))
    else:
        for b, s in sorted(pairs):
            print(f"{b} / {s}")


def cmd_trend(
    board: str,
    stage: str,
    window: str,
    sigma_multiple: float,
    as_json: bool,
    metrics_file: str | None = None,
) -> int:
    from temper_placer.regression.metrics_recorder import find_metrics_file, load_metrics

    repo_root = _find_repo_root()
    filepath = Path(metrics_file) if metrics_file else find_metrics_file(repo_root)
    records = load_metrics(filepath)

    window_td = _parse_window(window)
    result = _compute_trends(records, board, stage, window_td, sigma_multiple)

    if as_json:
        print(json.dumps(result, indent=2))
    else:
        print(_format_table(result))

    if result.get("error"):
        return 2

    if result.get("has_regression"):
        return 1

    return 0


def cmd_record(
    board: str,
    commit: str,
    metrics_file: str | None = None,
) -> int:
    from temper_placer.regression.closure_test import ClosureResult
    from temper_placer.regression.metrics_recorder import (
        find_metrics_file,
        record_closure_result,
        record_metrics,
    )

    repo_root = _find_repo_root()
    filepath = Path(metrics_file) if metrics_file else find_metrics_file(repo_root)

    # Create a minimal record from CI environment
    result = ClosureResult(passed=True, board_id=board, wall_clock_seconds=0)
    record = record_closure_result(result, board_id=board, commit=commit)
    record_metrics(record, filepath)
    print(f"Recorded metrics for {board} (commit {commit[:8]}) -> {filepath}")
    return 0


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Pipeline quality metrics time-series recorder and analyzer",
        prog="pipeline_metrics",
    )
    subparsers = parser.add_subparsers(dest="command", help="Subcommands")

    trend_parser = subparsers.add_parser("trend", help="Compute trend statistics")
    trend_parser.add_argument("--board", default=None, help="Board ID")
    trend_parser.add_argument("--stage", default=None, help="Pipeline stage")
    trend_parser.add_argument("--window", default="30d", help="Analysis window (e.g. 30d)")
    trend_parser.add_argument("--sigma-multiple", type=float, default=1.0)
    trend_parser.add_argument("--json", action="store_true", help="JSON output")
    trend_parser.add_argument("--list", action="store_true", help="List available boards/stages")
    trend_parser.add_argument("--metrics-file", default=None, help="Path to pipeline_metrics.jsonl")

    record_parser = subparsers.add_parser("record", help="Record a metrics entry")
    record_parser.add_argument("--board", required=True, help="Board ID")
    record_parser.add_argument("--commit", default="", help="Git commit SHA")
    record_parser.add_argument("--metrics-file", default=None, help="Path to pipeline_metrics.jsonl")

    args = parser.parse_args()

    repo_root = _find_repo_root()
    _setup_path(repo_root)

    if args.command == "trend":
        if args.list:
            cmd_list(as_json=args.json)
            return 0
        if not args.board:
            print("ERROR: --board is required for trend analysis", file=sys.stderr)
            return 1
        if not args.stage:
            print("ERROR: --stage is required for trend analysis", file=sys.stderr)
            return 1
        return cmd_trend(
            board=args.board,
            stage=args.stage,
            window=args.window,
            sigma_multiple=args.sigma_multiple,
            as_json=args.json,
            metrics_file=args.metrics_file,
        )
    elif args.command == "record":
        return cmd_record(
            board=args.board,
            commit=args.commit,
            metrics_file=args.metrics_file,
        )
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
