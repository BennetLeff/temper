#!/usr/bin/env python3
"""Pipeline metrics CLI -- time-series trend querying (R2)."""

from __future__ import annotations

import json, math, sys
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
    print(f"ERROR: Unsupported window unit '{window}' (use Nd)", file=sys.stderr)
    sys.exit(2)


def _compute_trends(records, board, stage, window, sigma_multiple):
    if not records:
        return {"board": board, "stage": stage, "error": "No records found"}
    filtered = [r for r in records if r.get("board") == board and r.get("stage") == stage]
    if not filtered:
        return {"board": board, "stage": stage, "error": "No records match board/stage"}
    now = datetime.now(timezone.utc)
    cutoff = now - window
    windowed = []
    for r in filtered:
        try:
            ts = datetime.fromisoformat(r["timestamp"])
        except (ValueError, KeyError):
            continue
        if ts >= cutoff:
            windowed.append(r)
    if len(windowed) < 2:
        return {"board": board, "stage": stage,
                "error": f"Need >=2 data points, have {len(windowed)}"}
    windowed.sort(key=lambda r: r["timestamp"])
    latest = windowed[-1]
    all_keys = set()
    for r in windowed:
        all_keys.update(r.get("metrics", {}).keys())
    metrics_list = []
    has_regression = False
    for key in sorted(all_keys):
        values = [r.get("metrics", {}).get(key) for r in windowed
                  if r.get("metrics", {}).get(key) is not None]
        if len(values) < 2:
            continue
        mu = sum(values) / len(values)
        variance = sum((v - mu) ** 2 for v in values) / max(1, len(values) - 1)
        sigma = math.sqrt(variance) if variance > 0 else 0.0
        current = latest.get("metrics", {}).get(key)
        if current is None:
            continue
        drift = abs(current - mu) / sigma if sigma > 0 else 0.0
        if drift > sigma_multiple:
            status = "REGRESSION"; has_regression = True
        elif drift > sigma_multiple * 0.5:
            status = "WARN"
        else:
            status = "OK"
        metrics_list.append({"metric": key, "latest": current, "mean": round(mu, 4),
                             "sigma": round(sigma, 4), "drift_sigma": round(drift, 4),
                             "status": status, "data_points": len(values)})
    return {"board": board, "stage": stage, "window_days": window.days,
            "sigma_multiple": sigma_multiple, "data_points": len(windowed),
            "has_regression": has_regression, "metrics": metrics_list}


def _format_table(result):
    lines = [
        f"Board: {result['board']}, Stage: {result['stage']}",
        f"Window: {result.get('window_days', '?')}d, "
        f"Sigma multiple: {result.get('sigma_multiple', 1.0)}, "
        f"Data points: {result.get('data_points', 0)}", "",
        f"{'Metric':<24} {'Latest':>10} {'Mean':>10} {'Sigma':>10} {'Drift':>8} Status",
        "-" * 78]
    for m in result.get("metrics", []):
        lines.append(f"{m['metric']:<24} {m['latest']:>10.2f} {m['mean']:>10.2f} "
                     f"{m['sigma']:>10.2f} {m['drift_sigma']:>7.2f}s {m['status']}")
    if result.get("error"):
        lines.append(f"\nERROR: {result['error']}")
    return "\n".join(lines)


def cmd_list(as_json):
    from temper_placer.regression.metrics_recorder import find_metrics_file, load_metrics
    repo_root = _find_repo_root()
    records = load_metrics(find_metrics_file(repo_root))
    pairs = set()
    for r in records:
        b, s = r.get("board", ""), r.get("stage", "")
        if b and s:
            pairs.add((b, s))
    if as_json:
        print(json.dumps([{"board": b, "stage": s} for b, s in sorted(pairs)], indent=2))
    else:
        for b, s in sorted(pairs):
            print(f"{b} / {s}")


def cmd_trend(board, stage, window, sigma_multiple, as_json, metrics_file=None):
    from temper_placer.regression.metrics_recorder import find_metrics_file, load_metrics
    repo_root = _find_repo_root()
    fp = Path(metrics_file) if metrics_file else find_metrics_file(repo_root)
    records = load_metrics(fp)
    win = _parse_window(window)
    result = _compute_trends(records, board, stage, win, sigma_multiple)
    if as_json:
        print(json.dumps(result, indent=2))
    else:
        print(_format_table(result))
    if result.get("error"):
        return 2
    return 1 if result.get("has_regression") else 0


def cmd_record(board, commit, metrics_file=None):
    from temper_placer.regression.closure_test import ClosureResult
    from temper_placer.regression.metrics_recorder import (
        find_metrics_file, record_closure_result, record_metrics)
    repo_root = _find_repo_root()
    fp = Path(metrics_file) if metrics_file else find_metrics_file(repo_root)
    result = ClosureResult(passed=True, board_id=board, wall_clock_seconds=0)
    record = record_closure_result(result, board_id=board, commit=commit)
    record_metrics(record, fp)
    print(f"Recorded metrics for {board} (commit {commit[:8]}) -> {fp}")
    return 0


def main():
    import argparse
    p = argparse.ArgumentParser(prog="pipeline_metrics",
        description="Pipeline quality metrics time-series recorder and analyzer")
    sp = p.add_subparsers(dest="command")
    tp = sp.add_parser("trend")
    tp.add_argument("--board", default=None)
    tp.add_argument("--stage", default=None)
    tp.add_argument("--window", default="30d")
    tp.add_argument("--sigma-multiple", type=float, default=1.0)
    tp.add_argument("--json", action="store_true")
    tp.add_argument("--list", action="store_true")
    tp.add_argument("--metrics-file", default=None)
    rp = sp.add_parser("record")
    rp.add_argument("--board", required=True)
    rp.add_argument("--commit", default="")
    rp.add_argument("--metrics-file", default=None)
    args = p.parse_args()
    repo_root = _find_repo_root()
    _setup_path(repo_root)
    if args.command == "trend":
        if args.list:
            cmd_list(as_json=args.json); return 0
        if not args.board:
            print("ERROR: --board required", file=sys.stderr); return 1
        if not args.stage:
            print("ERROR: --stage required", file=sys.stderr); return 1
        return cmd_trend(args.board, args.stage, args.window,
                         args.sigma_multiple, args.json, args.metrics_file)
    elif args.command == "record":
        return cmd_record(args.board, args.commit, args.metrics_file)
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
