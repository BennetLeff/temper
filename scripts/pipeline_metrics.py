#!/usr/bin/env python3
"""Pipeline metrics CLI -- time-series trend, SPC and SLO querying (R2/R11-R15)."""

from __future__ import annotations

import json
import math
import sys
from datetime import UTC, datetime, timedelta
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


def _setup_scripts_path() -> None:
    """Make sibling scripts (``slo_evaluator``, ``spc_rules``) importable.

    Running ``python scripts/pipeline_metrics.py`` already puts ``scripts/``
    at ``sys.path[0]``, but importing this module by path (as the CLI tests
    do) does not.
    """
    scripts_dir = str(Path(__file__).resolve().parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)


def _observability_activated(repo_root: Path) -> bool:
    """Read the silent-room flag from ``observability_state.json``.

    R13/R14: SPC and SLO evaluation always runs and always reports, but a
    violation only sets a non-zero exit code once the observability platform
    has been activated. A missing or unreadable state file means "not yet
    activated" -- fail *open* on the gate, never on the measurement.
    """
    path = repo_root / "power_pcb_dataset" / "metrics" / "observability_state.json"
    try:
        with open(path) as f:
            return bool(json.load(f).get("activated", False))
    except (OSError, json.JSONDecodeError):
        return False


def _load_records(repo_root: Path, metrics_file):
    from temper_placer.regression.metrics_recorder import find_metrics_file, load_metrics

    fp = Path(metrics_file) if metrics_file else find_metrics_file(repo_root)
    records = load_metrics(fp)
    records.sort(key=lambda r: r.get("timestamp", ""))
    return fp, records


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
    now = datetime.now(UTC)
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


def _format_slo_table(payload):
    lines = [
        f"SLO definitions: {payload['slo_file']}",
        f"Metrics:         {payload['metrics_file']}",
        f"Activated:       {payload['activated']}"
        + ("" if payload["activated"] else "  (silent room -- violations report but do not block)"),
        "",
        f"{'Stage':<12} {'Metric':<20} {'Type':>5} {'Observed':>12} {'Threshold':>12} "
        f"{'n':>4} {'Sev':<6} Status",
        "-" * 96,
    ]
    for r in payload["results"]:
        lines.append(
            f"{r['stage']:<12} {r['metric']:<20} {r['type']:>5} {r['observed']:>12.2f} "
            f"{r['threshold']:>12.2f} {r['data_points']:>4} {r['severity']:<6} {r['status']}"
        )
    lines.append("")
    lines.append(f"any_block={payload['any_block']}  any_warn={payload['any_warn']}")
    return "\n".join(lines)


def cmd_slo(slo_file, as_json, metrics_file=None):
    """Evaluate ``slo_definitions.yaml`` against the recorded metric series.

    Exit code is 1 only when a ``block``-severity SLO is violated AND the
    observability platform is activated (R14). ``warn`` violations and
    silent-room violations report but exit 0.
    """
    _setup_scripts_path()
    from slo_evaluator import evaluate_all, load_slo_definitions

    repo_root = _find_repo_root()
    fp, records = _load_records(repo_root, metrics_file)

    # ``evaluate_all`` keys purely on the record's ``stage`` field and takes
    # the last ``window`` values, so the grouping must preserve chronological
    # order (``_load_records`` sorts by timestamp).
    by_stage = {}
    for r in records:
        by_stage.setdefault(r.get("stage", ""), []).append(r)

    results = evaluate_all(load_slo_definitions(slo_file), by_stage)

    activated = _observability_activated(repo_root)
    any_block = any(r["violated"] and r["severity"] == "block" for r in results)
    any_warn = any(r["violated"] and r["severity"] == "warn" for r in results)

    payload = {
        "activated": activated,
        "any_block": any_block,
        "any_warn": any_warn,
        "slo_file": str(slo_file),
        "metrics_file": str(fp),
        "results": results,
    }
    if as_json:
        print(json.dumps(payload, indent=2))
    else:
        print(_format_slo_table(payload))
    return 1 if (activated and any_block) else 0


def _format_spc_table(payload):
    lines = [
        f"Metrics:   {payload['metrics_file']}",
        f"Board:     {payload['board']}",
        f"Window:    {payload['window']}",
        f"Activated: {payload['activated']}"
        + ("" if payload["activated"] else "  (silent room -- violations report but do not block)"),
        "",
        f"{'Stage':<12} {'Metric':<20} {'Latest':>12} {'Mean':>12} {'Sigma':>12} "
        f"{'n':>4} Violations",
        "-" * 96,
    ]
    for r in payload["results"]:
        lines.append(
            f"{r['stage']:<12} {r['metric']:<20} {r['latest']:>12.2f} {r['mean']:>12.2f} "
            f"{r['sigma']:>12.2f} {r['data_points']:>4} "
            f"{', '.join(r['violations']) or '-'}"
        )
    lines.append("")
    lines.append(f"any_violation={payload['any_violation']}")
    return "\n".join(lines)


def cmd_spc(board, stage, window, as_json, summary, metrics_file=None):
    """Evaluate the Western Electric SPC rules over the recorded series.

    Exit code is 1 only when a rule fires AND the observability platform is
    activated (R13/R14); during the silent room violations are reported with
    exit 0. ``summary`` emits trend direction only, for the non-blocking
    health digest.
    """
    _setup_scripts_path()
    from spc_rules import compute_control_limits, evaluate_rules

    repo_root = _find_repo_root()
    fp, records = _load_records(repo_root, metrics_file)

    series = {}
    for r in records:
        if board is not None and r.get("board") != board:
            continue
        rec_stage = r.get("stage", "")
        if stage is not None and rec_stage != stage:
            continue
        for key, value in (r.get("metrics") or {}).items():
            if value is None:
                continue
            series.setdefault((rec_stage, key), []).append(float(value))

    results = []
    any_violation = False
    for (rec_stage, metric), values in sorted(series.items()):
        windowed = values[-window:] if window > 0 else values
        fired = [name for name, hit in evaluate_rules(windowed).items() if hit]
        if fired:
            any_violation = True
        mean, sigma = compute_control_limits(windowed) if windowed else (0.0, 0.0)
        latest = windowed[-1] if windowed else 0.0
        entry = {
            "stage": rec_stage,
            "metric": metric,
            "latest": latest,
            "mean": round(mean, 4),
            "sigma": round(sigma, 4),
            "data_points": len(windowed),
            "violations": fired,
        }
        if summary:
            # Non-blocking trend direction for the health digest: where the
            # latest point sits relative to the control mean, in sigmas.
            drift = (latest - mean) / sigma if sigma > 0 else 0.0
            entry["direction"] = "rising" if drift > 1 else "falling" if drift < -1 else "flat"
            entry["drift_sigma"] = round(drift, 4)
        results.append(entry)

    activated = _observability_activated(repo_root)
    payload = {
        "activated": activated,
        "any_violation": any_violation,
        "board": board,
        "stage": stage,
        "window": window,
        "metrics_file": str(fp),
        "results": results,
    }
    if as_json:
        print(json.dumps(payload, indent=2))
    else:
        print(_format_spc_table(payload))
    return 1 if (activated and any_violation) else 0


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
        PipelineMetricsRecord,
        find_metrics_file,
        record_closure_result,
        record_metrics,
    )
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
                timestamp=rec_data.get("timestamp", datetime.now(UTC).isoformat()),
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
    spcp = sp.add_parser("spc",
        help="Western Electric SPC rules over the recorded series")
    spcp.add_argument("--board", default=None)
    spcp.add_argument("--stage", default=None)
    spcp.add_argument("--window", type=int, default=20,
                      help="Number of most-recent runs in the control window")
    spcp.add_argument("--json", action="store_true")
    spcp.add_argument("--summary", action="store_true",
                      help="Emit trend direction only (non-blocking health digest)")
    spcp.add_argument("--metrics-file", default=None)
    slop = sp.add_parser("slo",
        help="Evaluate slo_definitions.yaml against the recorded series")
    slop.add_argument("--slo-file", required=True)
    slop.add_argument("--json", action="store_true")
    slop.add_argument("--metrics-file", default=None)
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
    elif args.command == "spc":
        return cmd_spc(args.board, args.stage, args.window, args.json,
                       args.summary, args.metrics_file)
    elif args.command == "slo":
        return cmd_slo(args.slo_file, args.json, args.metrics_file)
    elif args.command == "record":
        return cmd_record(args.board, args.commit, args.metrics_file,
                          args.closure_json, args.from_stdin)
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
