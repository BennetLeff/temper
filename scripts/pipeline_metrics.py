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


def _compute_trends(records, board, stage, window, sigma_multiple, module=None):
    if not records:
        return {"board": board, "stage": stage, "error": "No records found"}
    filtered = [r for r in records if r.get("board") == board and r.get("stage") == stage]
    if module is not None:
        filtered = [r for r in filtered if r.get("module") == module]
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
    return {"board": board, "stage": stage, "module": module or "pipeline", "window_days": window.days,
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
    if result.get("module"):
        lines.insert(0, f"Module: {result['module']}")
    return "\n".join(lines)


def cmd_list(as_json):
    from temper_placer.regression.metrics_recorder import find_metrics_file, load_metrics
    repo_root = _find_repo_root()
    records = load_metrics(find_metrics_file(repo_root))
    pairs = set()
    for r in records:
        b, s, m = r.get("board", ""), r.get("stage", ""), r.get("module", "pipeline")
        if b and s:
            pairs.add((b, s, m))
    if as_json:
        print(json.dumps(
            [{"board": b, "stage": s, "module": m} for b, s, m in sorted(pairs)],
            indent=2))
    else:
        for b, s, m in sorted(pairs):
            print(f"{b} / {s} / {m}")


def cmd_trend(board, stage, window, sigma_multiple, as_json, metrics_file=None, module=None):
    from temper_placer.regression.metrics_recorder import find_metrics_file, load_metrics
    repo_root = _find_repo_root()
    fp = Path(metrics_file) if metrics_file else find_metrics_file(repo_root)
    records = load_metrics(fp)
    win = _parse_window(window)
    result = _compute_trends(records, board, stage, win, sigma_multiple, module)
    if as_json:
        print(json.dumps(result, indent=2))
    else:
        print(_format_table(result))
    if result.get("error"):
        return 2
    return 1 if result.get("has_regression") else 0


def cmd_record(board, commit, metrics_file=None, closure_json=None, from_stdin=False):
    from temper_placer.regression.closure_test import ClosureResult
    from temper_placer.regression.metrics_recorder import (
        find_metrics_file, record_closure_result, record_metrics,
        PipelineMetricsRecord)
    repo_root = _find_repo_root()
    fp = Path(metrics_file) if metrics_file else find_metrics_file(repo_root)

    if from_stdin:
        count = 0
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                rec_data = json.loads(line)
            except json.JSONDecodeError:
                print(f"WARNING: Skipping invalid JSON line: {line[:80]}...", file=sys.stderr)
                continue
            rec = PipelineMetricsRecord(
                board=rec_data.get("board", board),
                stage=rec_data.get("stage", "unknown"),
                module=rec_data.get("module", "pipeline"),
                metrics=rec_data.get("metrics", {}),
                git_commit=rec_data.get("git_commit", commit),
                timestamp=rec_data.get("timestamp", datetime.now(timezone.utc).isoformat()),
            )
            record_metrics(rec, fp)
            count += 1
        print(f"Recorded {count} metrics from stdin -> {fp}")
        return 0

    if closure_json:
        closure_path = Path(closure_json)
        if not closure_path.exists():
            print(f"ERROR: closure JSON not found: {closure_json}", file=sys.stderr)
            return 1
        try:
            with open(closure_path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"ERROR: Failed to parse closure JSON: {e}", file=sys.stderr)
            return 1
        result = ClosureResult(
            passed=data.get("passed", True),
            board_id=data.get("board_id", board),
            wall_clock_seconds=data.get("wall_clock_seconds", 0),
            benders_iterations=data.get("benders_iterations", 0),
            benders_cuts=data.get("benders_cuts", 0),
            router_completion_pct=data.get("router_completion_pct", 0.0),
            drc_errors=data.get("drc_errors", 0),
            drc_warnings=data.get("drc_warnings", 0),
            stages_exercised=data.get("stages_exercised", 0),
        )
        print(f"Read closure result: wall_clock={result.wall_clock_seconds:.1f}s, "
              f"completion={result.router_completion_pct:.1f}%, "
              f"drc_errors={result.drc_errors}")
    else:
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
    tp.add_argument("--module", default=None,
                    help="Filter by module (pipeline, loss-fn, router-bench, firmware)")
    tp.add_argument("--window", default="30d")
    tp.add_argument("--sigma-multiple", type=float, default=1.0)
    tp.add_argument("--json", action="store_true")
    tp.add_argument("--list", action="store_true")
    tp.add_argument("--metrics-file", default=None)
    rp = sp.add_parser("record")
    rp.add_argument("--board", required=True)
    rp.add_argument("--commit", default="")
    rp.add_argument("--metrics-file", default=None)
    rp.add_argument("--closure-json", default=None,
                    help="Path to closure-result.json produced by ci_closure_test.py")
    rp.add_argument("--from-stdin", action="store_true",
                    help="Read NDJSON records from stdin")
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
                         args.sigma_multiple, args.json, args.metrics_file,
                         args.module)
    elif args.command == "record":
        return cmd_record(args.board, args.commit, args.metrics_file,
                          args.closure_json, args.from_stdin)
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
