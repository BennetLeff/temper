#!/usr/bin/env python3
"""PR Performance Comparison — the Wave 4 performance A/B gate (R1b / R2).

Compares the PR's performance records against a committed baseline and
**exits non-zero on regression**. Computes a rolling-window median baseline
from the last N baseline entries for each (module, board, stage) tuple and
produces a Markdown delta table for posting as a PR comment.

This is a hard gate, not a report. It fails closed on every path where the
comparison cannot be *made*, because a comparison that silently degrades to
"no news" is indistinguishable from a passing one:

  - no PR records at all                      -> exit 1
  - the baseline file is missing or empty     -> exit 1
  - a PR record has no baseline row           -> exit 1 (NO_BASELINE)
  - any metric regresses beyond its margin    -> exit 1

Prior to 2026-08-04 none of those held: ``main()`` returned 0 unconditionally,
a missing baseline rendered as an em-dash table row, and the caller carried
``continue-on-error: true``. The comparison had in fact been crashing on every
run since the profiler began emitting NDJSON (``json.load`` expects an array);
the mask hid the traceback and the job reported success. See
docs/evidence/2026-08-04-perf-ab-harness-noise-floor.md.

Metric direction is read from the metric name:

  - ``_ms`` / ``_seconds`` / ``_ratio``  -> lower is better (TIMING_MARGIN)
  - ``_pct`` / ``completion_rate``       -> higher is better (COMPLETION_MARGIN)
  - anything else                        -> informational, never gated

Usage:
    python scripts/pr_perf_compare.py \\
        --pr-metrics pr-metrics.jsonl \\
        --baseline-jsonl baseline.jsonl
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

DEFAULT_WINDOW = 5

# Margins. Justified by measurement, not assumption -- see
# docs/evidence/2026-08-04-perf-ab-harness-noise-floor.md:
#   * CI wall-clock series (n=19 main-branch deltas, the gate's own rolling
#     arithmetic): sd 4.6%, worst excursion 9.9%; a genuine regression in the
#     same series measured +50.7%. A 20% margin sits cleanly between them.
#   * perf_ab ratio metric (n=20 fresh processes): worst excursion 7.72%.
# TIMING_MARGIN therefore carries ~2x headroom over the worst measured CI
# excursion. Do not lower it without re-measuring; do not raise it to make a
# regression pass.
TIMING_MARGIN = 0.20
COMPLETION_MARGIN = 0.10
IMPROVEMENT_THRESHOLD = 0.10

LOWER_IS_BETTER_SUFFIXES = ("_ms", "_seconds", "_ratio")
HIGHER_IS_BETTER_SUFFIXES = ("_pct",)
HIGHER_IS_BETTER_NAMES = ("completion_rate",)


class PerfGateError(RuntimeError):
    """Raised when the comparison cannot be made. Always fails the gate."""


def _parse_records(text: str, source: str) -> list[dict[str, Any]]:
    """Parse a JSON array or an NDJSON stream into a list of record dicts.

    Strict by design. The profiler writes NDJSON to stdout, and a producer that
    also prints progress to stdout silently corrupts the stream -- which is
    exactly how this comparison came to crash on every CI run while reporting
    success. A non-JSON line is an error naming the line, not a skipped record.
    """
    stripped = text.strip()
    if not stripped:
        return []

    try:
        whole = json.loads(stripped)
    except json.JSONDecodeError:
        whole = None
    if isinstance(whole, list):
        records = whole
    elif isinstance(whole, dict):
        records = [whole]
    else:
        records = []
        for lineno, line in enumerate(stripped.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError as err:
                raise PerfGateError(
                    f"{source}: line {lineno} is not JSON ({err}). The metrics "
                    f"stream is corrupt -- a producer is most likely printing "
                    f"progress to stdout. Offending line: {line[:120]!r}"
                ) from err
            records.append(parsed)

    for record in records:
        if not isinstance(record, dict):
            raise PerfGateError(f"{source}: expected JSON objects, got {type(record).__name__}")
    return records


def _read(path: str, source: str) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        raise PerfGateError(f"{source}: file not found: {path}")
    return _parse_records(p.read_text(), source)


def load_pr_metrics(path: str) -> list[dict[str, Any]]:
    """Load the PR's performance records (JSON array or NDJSON)."""
    return _read(path, "PR metrics")


def load_baseline_records(path: str) -> list[dict[str, Any]]:
    """Load the committed baseline records (JSON array or NDJSON)."""
    return _read(path, "baseline")


def _key(record: dict[str, Any]) -> tuple[str, str, str]:
    return (
        record.get("module", "pipeline"),
        record.get("board", ""),
        record.get("stage", ""),
    )


def load_main_baselines(
    records: list[dict[str, Any]],
    window: int = DEFAULT_WINDOW,
) -> dict[tuple[str, str, str], dict[str, float]]:
    """Compute median baseline for each (module, board, stage) from records."""
    groups: dict[tuple[str, str, str], list[dict]] = {}
    for r in records:
        key = _key(r)
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


def _status_for(mk: str, delta_pct: float) -> str:
    """Classify one metric delta. Unrecognised metric names are informational."""
    if mk in HIGHER_IS_BETTER_NAMES or mk.endswith(HIGHER_IS_BETTER_SUFFIXES):
        if delta_pct < 0 and abs(delta_pct) > COMPLETION_MARGIN * 100:
            return "REGRESSION"
        if delta_pct > IMPROVEMENT_THRESHOLD * 100:
            return "IMPROVED"
        return "OK"
    if mk.endswith(LOWER_IS_BETTER_SUFFIXES):
        if delta_pct > TIMING_MARGIN * 100:
            return "REGRESSION"
        if delta_pct < -IMPROVEMENT_THRESHOLD * 100:
            return "IMPROVED"
        return "OK"
    return "OK"


def compare(
    pr_metrics: list[dict[str, Any]],
    baselines: dict[tuple[str, str, str], dict[str, float]],
) -> list[dict[str, Any]]:
    """Compare PR metrics against baselines and return delta entries."""
    results: list[dict[str, Any]] = []
    for pr_entry in pr_metrics:
        key = _key(pr_entry)
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
            deltas[mk] = {
                "main": round(base_val, 6),
                "pr": round(pr_float, 6),
                "delta_pct": round(delta_pct, 1),
                "status": _status_for(mk, delta_pct),
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


def gate_failures(results: list[dict[str, Any]]) -> list[str]:
    """Return the human-readable reasons this comparison fails the gate."""
    failures: list[str] = []
    for res in results:
        label = f"{res['module']}/{res['board']}/{res['stage']}"
        if res["status"] == "NO_BASELINE":
            failures.append(
                f"{label}: no baseline row. Capture one into the committed "
                f"baseline before merging -- an unbaselined module is not "
                f"covered by the performance A/B."
            )
            continue
        for mk, delta in sorted(res["deltas"].items()):
            if delta["status"] == "REGRESSION":
                failures.append(
                    f"{label}: {mk} regressed {delta['delta_pct']:+.1f}% "
                    f"(baseline {delta['main']} -> PR {delta['pr']})"
                )
    return failures


def format_markdown(results: list[dict[str, Any]], failures: list[str]) -> str:
    """Format comparison results as a Markdown table for PR comments."""
    lines: list[str] = []
    lines.append("## Performance Comparison")
    lines.append("")
    lines.append("| Module | Board | Stage | Metric | Baseline | PR | Delta | Status |")
    lines.append("|--------|-------|-------|--------|----------|----|-------|--------|")

    for res in results:
        if res["status"] == "NO_BASELINE":
            lines.append(
                f"| {res['module']} | {res['board']} | {res['stage']} | "
                f"— | — | — | No baseline | 🔴 NO_BASELINE |"
            )
            continue

        for mk, delta in sorted(res["deltas"].items()):
            icon = ""
            if delta["status"] == "REGRESSION":
                icon = "🔴"
            elif delta["status"] == "IMPROVED":
                icon = "🟢"
            direction = "+" if delta["delta_pct"] >= 0 else ""
            lines.append(
                f"| {res['module']} | {res['board']} | {res['stage']} | {mk} | "
                f"{delta['main']} | {delta['pr']} | "
                f"{direction}{delta['delta_pct']}% {icon} | "
                f"{delta['status']} |"
            )

    if failures:
        lines.append("")
        lines.append("### 🔴 Performance A/B gate FAILED")
        lines.append("")
        lines.extend(f"- {reason}" for reason in failures)
        lines.append("")
        lines.append(
            f"Margins: timing/ratio {TIMING_MARGIN:.0%}, completion "
            f"{COMPLETION_MARGIN:.0%}. Do not widen a margin to make this pass "
            "— see docs/evidence/2026-08-04-perf-ab-harness-noise-floor.md for "
            "the measurements that set them."
        )
    else:
        lines.append("")
        lines.append("✅ Performance A/B gate passed — no regression beyond noise.")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="PR performance comparison against a committed JSONL baseline")
    parser.add_argument("--pr-metrics", required=True,
                        help="Path to PR metrics (JSON array or NDJSON)")
    parser.add_argument("--baseline-jsonl", "--main-jsonl", dest="baseline_jsonl",
                        required=True,
                        help="Path to the committed baseline JSONL")
    parser.add_argument("--window", type=int, default=DEFAULT_WINDOW,
                        help=f"Rolling window size for baseline median (default: {DEFAULT_WINDOW})")
    parser.add_argument("--json", action="store_true",
                        help="Output results as JSON")
    parser.add_argument("--report-file", type=Path, default=None,
                        help="Also write the Markdown report to this file "
                             "(written even when the gate fails)")
    args = parser.parse_args(argv)

    try:
        pr_metrics = load_pr_metrics(args.pr_metrics)
        if not pr_metrics:
            raise PerfGateError(
                "PR metrics are empty. The performance A/B produced no records, "
                "so nothing was compared -- failing closed rather than reporting "
                "a vacuous pass."
            )

        baseline_records = load_baseline_records(args.baseline_jsonl)
        if not baseline_records:
            raise PerfGateError(
                f"baseline {args.baseline_jsonl} is empty. Every PR record would "
                "be unbaselined, so the comparison cannot be made -- failing "
                "closed."
            )
    except PerfGateError as err:
        report = (
            "## Performance Comparison\n\n"
            f"### 🔴 Performance A/B gate FAILED\n\n- {err}\n"
        )
        print(report)
        if args.report_file:
            args.report_file.write_text(report)
        print(f"FAIL: {err}", file=sys.stderr)
        return 1

    baselines = load_main_baselines(baseline_records, args.window)
    results = compare(pr_metrics, baselines)
    failures = gate_failures(results)
    report = format_markdown(results, failures)

    if args.json:
        print(json.dumps({"results": results, "failures": failures}, indent=2))
    else:
        print(report)
    if args.report_file:
        args.report_file.write_text(report)

    if failures:
        print("FAIL: performance A/B gate failed", file=sys.stderr)
        for reason in failures:
            print(f"  - {reason}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
