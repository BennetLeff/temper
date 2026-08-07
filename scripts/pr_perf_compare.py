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

  - ``_ms`` / ``_seconds`` / ``_ratio``  -> lower is better (timing margin)
  - ``_pct`` / ``completion_rate``       -> higher is better (COMPLETION_MARGIN)
  - anything else                        -> informational, never gated

The timing margin is PER BENCHMARK, not one constant. A single 20% figure was
measured on two benchmarks and then applied to seventeen; three of the arms
added since have fixed-commit noise above 20%, and they were failing PRs that
could not have touched them. See the block comment on
PER_BENCHMARK_TIMING_MARGIN below and
docs/evidence/2026-08-05-perf-ab-per-benchmark-margin.md.

Usage:
    python scripts/pr_perf_compare.py \\
        --pr-metrics pr-metrics.jsonl \\
        --baseline-jsonl baseline.jsonl

    # re-derive the margin table after appending CI-measured baseline rows
    python scripts/pr_perf_compare.py \\
        --derive-margins --baseline-jsonl baseline.jsonl
"""

from __future__ import annotations

import argparse
import json
import math
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
# excursion. It remains the DEFAULT and the FLOOR: no benchmark is gated
# tighter than 20%, because 20% is the only figure validated across the whole
# harness. Do not lower it without re-measuring; do not raise it to make a
# regression pass.
TIMING_MARGIN = 0.20
COMPLETION_MARGIN = 0.10
IMPROVEMENT_THRESHOLD = 0.10

# --------------------------------------------------------------------------
# Per-benchmark margins
# --------------------------------------------------------------------------
# One constant for every benchmark was wrong, and measurably so. See
# docs/evidence/2026-08-05-perf-ab-per-benchmark-margin.md.
#
# The 20% figure above was derived from two benchmarks (cell_capacity_batch,
# hard_blocked_batch) and then applied to seventeen. The harness has since
# grown arms whose per-call work is microseconds, and their fixed-commit
# run-to-run spread is nothing like 7.72%. Measured on CI at a FIXED COMMIT --
# two groups of five independent runs, main @ db89355a and main @ 516b0e1d, so
# every difference within a group is noise by construction and none of it can
# be real performance change:
#
#     physics-emi/predict                    worst excursion 42.8%
#     parse-engine/parse_kicad_pcb           worst excursion 32.5%
#     board-netlist/contracts_construction   worst excursion 30.9%
#     drc-geometry/point_rect                worst excursion 26.0%
#     physics-heat_removal/build_h_field     worst excursion 24.4%
#     physics-safety/filter_delay            worst excursion 14.7%
#     bottleneck-geometry/hard_blocked_batch worst excursion 11.5%
#     loaders/loaders                        worst excursion 10.9%
#     ... 9 further arms                     worst excursion <= 8.4%
#
# Seven of those exceed the 20% margin outright, which is why PRs that could
# not touch the benchmark named were failing on it (#722, #760, and the #778
# triage bucket: #721, #731, #737, #755).
#
# These are LOWER BOUNDS on each arm's true noise: n=10 samples the tail
# thinly, and doubling the sample from 5 to 10 moved five arms across a
# threshold. Expect further captures to widen margins, not narrow them.
#
# Derivation, applied identically to every arm and reproducible with
# `python3 scripts/pr_perf_compare.py --derive-margins`:
#
#   1. Group the committed baseline by (module, stage) AND git_commit. Only
#      groups of 3+ rows sharing one commit are used. This is the whole point:
#      spread WITHIN a commit is noise; spread ACROSS commits may be real
#      performance change, and treating it as noise would absorb genuine
#      regressions into the margin.
#   2. Leave-one-out, which is the gate's own arithmetic: score each row
#      against the median of the OTHER rows in its group. Take the worst
#      absolute excursion over every row of every group.
#      Two-sided, not upward-only: the two arms run back to back in one
#      process, so a scheduling excursion lands on whichever arm is running.
#      physics-emi's 42.8% happened to hit the oracle arm (ratio fell); the
#      same event on the rust arm raises the ratio by as much.
#   3. margin = max(TIMING_MARGIN, ceil_to_1pct(NOISE_HEADROOM x excursion)).
#      NOISE_HEADROOM = 2.0 is the doc's own standard, not a new one: it set
#      20% against a worst measured excursion of 9.9%.
#   4. If that margin exceeds MAX_GATEABLE_MARGIN the benchmark is NOT GATED
#      (see UNGATEABLE_BENCHMARKS).
#
# Widening a margin is still not a way to make a failure pass. It is only
# admissible via step 3, from fixed-commit rows measured on CI, and
# test_pr_perf_compare.py re-derives this table from the committed baseline on
# every run -- so a hand-edited number that the measurement does not support
# fails the suite.

# The smallest genuine regression in the repo's own metric history
# (docs/evidence/2026-08-04-perf-ab-harness-noise-floor.md: the regime shift
# measured +50.7% to +72.4%). A margin at or above this cannot distinguish
# noise from the real-regression class.
REAL_REGRESSION_FLOOR = 0.507

# Headroom over measured noise. The doc's own ratio: 20% margin against a 9.9%
# worst excursion.
NOISE_HEADROOM = 2.0

# How far below the real-regression class a margin must sit to be worth
# gating on. This factor is a judgement and is named as one: 50.7% is a single
# observed value, and a gate that only fires above ~50% catches nothing the
# one historical example did not already contain. At 1.5 the largest gateable
# margin is 33.8%, which keeps physics-heat_removal/build_h_field (derived
# 48.7%) out. At 1.0 it would be admitted at a 49% margin -- nominally gated,
# practically inert. Excluding it and saying so is the more honest report.
MIN_SEPARATION = 1.5
MAX_GATEABLE_MARGIN = REAL_REGRESSION_FLOOR / MIN_SEPARATION

# Derived by the procedure above from the committed baseline. Only entries that
# differ from TIMING_MARGIN are listed; everything else uses the 20% default.
PER_BENCHMARK_TIMING_MARGIN: dict[tuple[str, str], float] = {
    # worst fixed-commit excursion 14.6% -> 2 x 14.6 = 29.2 -> 30%
    ("bottleneck-geometry", "hard_blocked_batch"): 0.30,
    # worst fixed-commit excursion 10.9% -> 2 x 10.9 = 21.7 -> 22%
    ("loaders", "loaders"): 0.22,
    # worst fixed-commit excursion 15.9% -> 2 x 15.9 = 31.8 -> 32%
    ("physics-copper_coverage", "copper_masks"): 0.32,
    # worst fixed-commit excursion 14.7% -> 2 x 14.7 = 29.4 -> 30%
    ("physics-safety", "filter_delay"): 0.30,
}

# Benchmarks whose measured fixed-commit noise leaves no usable band between
# noise and the real-regression class. They are measured and REPORTED on every
# run -- as ADVISORY, with their delta visible -- but they never fail the gate,
# because there is no margin that would separate signal from noise for them.
#
# Naming this is the point. Inventing a 62% or an 86% "margin" for these would
# look principled and detect nothing, which is the failure mode
# scripts/check_vacuous_gates.py exists because of.
#
# The fix for each is to reduce its variance, not to widen its margin: all
# three are dominated by single-shot scheduling excursions on arms whose timed
# region is tens of microseconds. Raising perf_ab.py's DEFAULT_REPEATS for
# these arms, or having them median several in-process re-measurements, should
# bring them back under MAX_GATEABLE_MARGIN -- at which point the test below
# fails and forces them back into the gated set.
UNGATEABLE_BENCHMARKS: dict[tuple[str, str], str] = {
    ("physics-emi", "predict"):
        "fixed-commit excursion 42.8% -> margin 86%, above the 33.8% max "
        "gateable margin",
    ("parse-engine", "parse_kicad_pcb"):
        "fixed-commit excursion 32.5% -> margin 66%, above the 33.8% max "
        "gateable margin",
    ("board-netlist", "contracts_construction"):
        "fixed-commit excursion 44.8% -> margin 90%, above the 33.8% max "
        "gateable margin",
    ("drc-geometry", "point_rect"):
        "fixed-commit excursion 26.0% -> margin 53%, above the 33.8% max "
        "gateable margin",
    ("drc-inflate", "drc_proxy_score"):
        "fixed-commit excursion 32.0% -> margin 64%, above the 33.8% max "
        "gateable margin",
    ("drc-inflate", "smooth_relu_array"):
        "fixed-commit excursion 36.8% -> margin 74%, above the 33.8% max "
        "gateable margin",
    ("physics-heat_removal", "build_h_field"):
        "fixed-commit excursion 24.4% -> margin 49%, above the 33.8% max "
        "gateable margin (and only 1.04x below the 50.7% real-regression floor)",
}

# Minimum rows sharing one commit before a group counts as a noise sample.
MIN_NOISE_GROUP = 3

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


def measure_fixed_commit_noise(
    records: list[dict[str, Any]],
    metric: str = "rust_over_oracle_ratio",
    min_group: int = MIN_NOISE_GROUP,
) -> dict[tuple[str, str], dict[str, float]]:
    """Worst leave-one-out excursion per benchmark, measured at a FIXED COMMIT.

    This is the only defensible noise estimate available from the baseline
    file. Rows are grouped by (module, stage) *and* ``git_commit``; only groups
    of ``min_group`` or more rows count. Within one commit the code is
    identical, so every difference is measurement noise -- across commits it
    might be real performance change, and using that spread as the margin would
    be circular: it would absorb genuine regressions into the band and make the
    gate weakest exactly where it is already weakest.

    The statistic is the same one ``docs/evidence/2026-08-04-perf-ab-harness-
    noise-floor.md`` reports as "worst rolling delta", computed with the gate's
    own arithmetic: each sample against the median of the others, which is what
    a PR run faces against a trailing-window median baseline.

    Returns ``{(module, stage): {"worst_pct", "n", "groups"}}``. Benchmarks
    with no qualifying group are absent -- callers must treat that as "not
    measured", never as "no noise".
    """
    by_key_commit: dict[tuple[str, str], dict[str, list[float]]] = {}
    for r in records:
        value = (r.get("metrics") or {}).get(metric)
        if not isinstance(value, (int, float)):
            continue
        key = (r.get("module", ""), r.get("stage", ""))
        if not key[0] or not key[1]:
            continue
        commit = str(r.get("git_commit", ""))
        if not commit:
            continue
        by_key_commit.setdefault(key, {}).setdefault(commit, []).append(float(value))

    measured: dict[tuple[str, str], dict[str, float]] = {}
    for key, commits in by_key_commit.items():
        worst = 0.0
        total = 0
        groups = 0
        for values in commits.values():
            if len(values) < min_group:
                continue
            groups += 1
            total += len(values)
            for i, value in enumerate(values):
                others = values[:i] + values[i + 1:]
                median = statistics.median(others)
                if median <= 0:
                    continue
                worst = max(worst, abs(value - median) / median * 100)
        if groups:
            measured[key] = {"worst_pct": worst, "n": float(total), "groups": float(groups)}
    return measured


def derive_margin(worst_pct: float) -> float:
    """Margin implied by a measured worst excursion (steps 3-4 above)."""
    return max(TIMING_MARGIN, math.ceil(NOISE_HEADROOM * worst_pct) / 100)


def derive_margin_table(
    records: list[dict[str, Any]],
) -> tuple[dict[tuple[str, str], float], dict[tuple[str, str], float]]:
    """Re-derive (gated margins, ungateable margins) from baseline records.

    The committed ``PER_BENCHMARK_TIMING_MARGIN`` and ``UNGATEABLE_BENCHMARKS``
    are this function's output, frozen into source so that every change to them
    is a reviewed diff rather than a silent runtime widening. The test suite
    calls this against the committed baseline and fails if the two disagree.
    """
    gated: dict[tuple[str, str], float] = {}
    ungateable: dict[tuple[str, str], float] = {}
    for key, stats in measure_fixed_commit_noise(records).items():
        margin = derive_margin(stats["worst_pct"])
        if margin > MAX_GATEABLE_MARGIN:
            ungateable[key] = margin
        elif margin != TIMING_MARGIN:
            gated[key] = margin
    return gated, ungateable


def margin_for(key: tuple[str, str] | None) -> float:
    """Timing/ratio margin for one benchmark, defaulting to TIMING_MARGIN.

    An unknown key gets the default rather than a wider band: a benchmark that
    has never been characterised is gated at the only figure the harness has
    validated, which is the fail-closed direction.
    """
    if key is None:
        return TIMING_MARGIN
    return PER_BENCHMARK_TIMING_MARGIN.get(key, TIMING_MARGIN)


def _status_for(
    mk: str,
    delta_pct: float,
    key: tuple[str, str] | None = None,
) -> str:
    """Classify one metric delta. Unrecognised metric names are informational.

    ``key`` is the ``(module, stage)`` benchmark identity, which selects the
    per-benchmark margin. Omitting it applies the default 20% -- the behaviour
    every caller had before per-benchmark margins existed.
    """
    if mk in HIGHER_IS_BETTER_NAMES or mk.endswith(HIGHER_IS_BETTER_SUFFIXES):
        if delta_pct < 0 and abs(delta_pct) > COMPLETION_MARGIN * 100:
            return "REGRESSION"
        if delta_pct > IMPROVEMENT_THRESHOLD * 100:
            return "IMPROVED"
        return "OK"
    if mk.endswith(LOWER_IS_BETTER_SUFFIXES):
        if key is not None and key in UNGATEABLE_BENCHMARKS:
            # Measured, reported, never gated -- and never labelled IMPROVED
            # either. physics-emi's own noise produced a -42.8% reading on
            # unmodified code; calling that an improvement is the same error
            # as calling the mirror-image reading a regression.
            return "ADVISORY"
        if delta_pct > margin_for(key) * 100:
            return "REGRESSION"
        if delta_pct < -IMPROVEMENT_THRESHOLD * 100:
            return "IMPROVED"
        return "OK"
    return "OK"


def compare(
    pr_metrics: list[dict[str, Any]],
    baselines: dict[tuple[str, str, str], dict[str, float]],
    main_benchmarks: set[tuple[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Compare PR metrics against baselines and return delta entries."""
    results: list[dict[str, Any]] = []
    for pr_entry in pr_metrics:
        key = _key(pr_entry)
        baseline = baselines.get(key, {})
        if not baseline:
            # A benchmark with no baseline row is one of two very different
            # things, and conflating them made adding a benchmark impossible.
            #
            #   NEW_BENCHMARK -- the (module, stage) does not exist on main at
            #     all, so this PR is its first appearance. No baseline CAN
            #     exist yet: the gate reads the baseline from main (so a PR
            #     cannot move its own goalposts), and main cannot carry a row
            #     for code it does not have. Reported, not failed.
            #
            #   NO_BASELINE -- the benchmark DOES exist on main and still has
            #     no row. That is the vacuity case this gate exists for: a
            #     module shipped without coverage. Fails closed.
            #
            # main_benchmarks is None when the caller did not supply main's
            # registry; then every unbaselined key stays NO_BASELINE, so the
            # conservative behaviour is what you get by default.
            is_new = (
                main_benchmarks is not None
                and (key[0], key[2]) not in main_benchmarks
            )
            results.append({
                "module": key[0],
                "board": key[1],
                "stage": key[2],
                "status": "NEW_BENCHMARK" if is_new else "NO_BASELINE",
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
            bench = (key[0], key[2])
            deltas[mk] = {
                "main": round(base_val, 6),
                "pr": round(pr_float, 6),
                "delta_pct": round(delta_pct, 1),
                "status": _status_for(mk, delta_pct, bench),
                "margin_pct": round(margin_for(bench) * 100, 1),
            }

        # Precedence: a REGRESSION anywhere outranks everything; ADVISORY
        # outranks IMPROVED so an ungateable arm is never summarised as a win.
        worst = "OK"
        for d in deltas.values():
            if d["status"] == "REGRESSION":
                worst = "REGRESSION"
                break
            if d["status"] == "ADVISORY":
                worst = "ADVISORY"
            elif d["status"] == "IMPROVED" and worst == "OK":
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
        if res["status"] == "NEW_BENCHMARK":
            # First appearance on this PR -- no baseline can exist yet. Not a
            # failure; the row is captured from this run and landed on main.
            continue
        if res["status"] == "NO_BASELINE":
            failures.append(
                f"{label}: no baseline row, and this benchmark already exists "
                f"on main. Capture one into the committed baseline before "
                f"merging -- an unbaselined module is not covered by the "
                f"performance A/B."
            )
            continue
        for mk, delta in sorted(res["deltas"].items()):
            if delta["status"] == "REGRESSION":
                failures.append(
                    f"{label}: {mk} regressed {delta['delta_pct']:+.1f}% "
                    f"(baseline {delta['main']} -> PR {delta['pr']}; this "
                    f"benchmark's margin is {delta.get('margin_pct', TIMING_MARGIN * 100):.0f}%)"
                )
    return failures


def advisory_notes(results: list[dict[str, Any]]) -> list[str]:
    """Lines for benchmarks that are measured but cannot be gated.

    Reported on every run, passing or failing. An exclusion nobody sees is an
    exclusion nobody revisits, and these three are meant to be revisited: the
    remedy is to reduce their variance, not to keep excusing it.
    """
    notes: list[str] = []
    for res in results:
        bench = (res["module"], res["stage"])
        reason = UNGATEABLE_BENCHMARKS.get(bench)
        if reason is None:
            continue
        for mk, delta in sorted(res["deltas"].items()):
            if delta["status"] != "ADVISORY":
                continue
            notes.append(
                f"{res['module']}/{res['board']}/{res['stage']}: {mk} "
                f"{delta['delta_pct']:+.1f}% (baseline {delta['main']} -> PR "
                f"{delta['pr']}) — NOT GATED: {reason}"
            )
    return notes


def format_markdown(
    results: list[dict[str, Any]],
    failures: list[str],
    advisories: list[str] | None = None,
) -> str:
    """Format comparison results as a Markdown table for PR comments."""
    lines: list[str] = []
    lines.append("## Performance Comparison")
    lines.append("")
    lines.append(
        "| Module | Board | Stage | Metric | Baseline | PR | Delta | Margin | Status |"
    )
    lines.append(
        "|--------|-------|-------|--------|----------|----|-------|--------|--------|"
    )

    for res in results:
        if res["status"] == "NO_BASELINE":
            lines.append(
                f"| {res['module']} | {res['board']} | {res['stage']} | "
                f"— | — | — | No baseline | — | 🔴 NO_BASELINE |"
            )
            continue

        bench = (res["module"], res["stage"])
        for mk, delta in sorted(res["deltas"].items()):
            icon = ""
            if delta["status"] == "REGRESSION":
                icon = "🔴"
            elif delta["status"] == "IMPROVED":
                icon = "🟢"
            elif delta["status"] == "ADVISORY":
                icon = "⚪"
            direction = "+" if delta["delta_pct"] >= 0 else ""
            if bench in UNGATEABLE_BENCHMARKS:
                margin = "not gated"
            elif mk.endswith(LOWER_IS_BETTER_SUFFIXES):
                margin = f"{delta.get('margin_pct', TIMING_MARGIN * 100):.0f}%"
            else:
                margin = "—"
            lines.append(
                f"| {res['module']} | {res['board']} | {res['stage']} | {mk} | "
                f"{delta['main']} | {delta['pr']} | "
                f"{direction}{delta['delta_pct']}% {icon} | {margin} | "
                f"{delta['status']} |"
            )

    if advisories:
        lines.append("")
        lines.append("### ⚪ Measured but NOT gated")
        lines.append("")
        lines.extend(f"- {note}" for note in advisories)
        lines.append("")
        lines.append(
            "These benchmarks' own run-to-run noise at a fixed commit is "
            "comparable to the smallest real regression on record (+50.7%), so "
            "no margin separates signal from noise for them. Reducing their "
            "variance is the fix; widening a margin is not. See "
            "docs/evidence/2026-08-05-perf-ab-per-benchmark-margin.md."
        )

    if failures:
        lines.append("")
        lines.append("### 🔴 Performance A/B gate FAILED")
        lines.append("")
        lines.extend(f"- {reason}" for reason in failures)
        lines.append("")
        lines.append(
            f"Margins are PER BENCHMARK (default {TIMING_MARGIN:.0%}, completion "
            f"{COMPLETION_MARGIN:.0%}); the one applied is in the Margin column. "
            "Do not widen a margin to make this pass. A margin may only be "
            "raised from fixed-commit rows measured on CI, via "
            "`python3 scripts/pr_perf_compare.py --derive-margins` — the test "
            "suite re-derives this table from the committed baseline and "
            "rejects any number the measurement does not support. See "
            "docs/evidence/2026-08-05-perf-ab-per-benchmark-margin.md and "
            "docs/evidence/2026-08-04-perf-ab-harness-noise-floor.md."
        )
    else:
        lines.append("")
        lines.append("✅ Performance A/B gate passed — no regression beyond noise.")

    return "\n".join(lines)


def _print_derived_margins(baseline_path: str) -> int:
    """Print the margin table implied by the committed baseline.

    Fails closed (exit 1) when the baseline carries no fixed-commit group at
    all: "nothing to measure" must not print an empty, authoritative-looking
    table that someone then pastes over a table derived from real data.
    """
    try:
        records = load_baseline_records(baseline_path)
    except PerfGateError as err:
        print(f"FAIL: {err}", file=sys.stderr)
        return 1

    measured = measure_fixed_commit_noise(records)
    if not measured:
        print(
            f"FAIL: {baseline_path} has no group of {MIN_NOISE_GROUP}+ rows "
            "sharing one git_commit, so fixed-commit noise cannot be measured. "
            "Capture repeated runs of one commit via the workflow_dispatch "
            "path on .github/workflows/pr-perf-check.yml.",
            file=sys.stderr,
        )
        return 1

    gated, ungateable = derive_margin_table(records)
    print(f"# Derived from {baseline_path}")
    print(f"# NOISE_HEADROOM={NOISE_HEADROOM}, floor={TIMING_MARGIN:.0%}, "
          f"max gateable={MAX_GATEABLE_MARGIN:.1%} "
          f"(={REAL_REGRESSION_FLOOR:.1%} / {MIN_SEPARATION})")
    print()
    print(f"{'benchmark':46} {'n':>4} {'grp':>4} {'worst%':>8} {'margin':>8}  verdict")
    for key, stats in sorted(measured.items(), key=lambda kv: -kv[1]["worst_pct"]):
        margin = derive_margin(stats["worst_pct"])
        if key in ungateable:
            verdict = "UNGATEABLE"
        elif key in gated:
            verdict = "per-benchmark margin"
        else:
            verdict = "default"
        print(f"{key[0] + '/' + key[1]:46} {int(stats['n']):>4} "
              f"{int(stats['groups']):>4} {stats['worst_pct']:>8.1f} "
              f"{margin:>8.0%}  {verdict}")
    print()
    print("PER_BENCHMARK_TIMING_MARGIN = {")
    for key, margin in sorted(gated.items()):
        print(f"    {key!r}: {margin},")
    print("}")
    print("UNGATEABLE_BENCHMARKS = {")
    for key, margin in sorted(ungateable.items()):
        print(f"    {key!r}: {margin:.0%} > {MAX_GATEABLE_MARGIN:.1%},")
    print("}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="PR performance comparison against a committed JSONL baseline")
    parser.add_argument("--pr-metrics", default=None,
                        help="Path to PR metrics (JSON array or NDJSON)")
    parser.add_argument("--baseline-jsonl", "--main-jsonl", dest="baseline_jsonl",
                        default=None,
                        help="Path to the committed baseline JSONL")
    parser.add_argument(
        "--derive-margins", action="store_true",
        help=(
            "Re-derive the per-benchmark margin table from the fixed-commit "
            "groups in --baseline-jsonl and print it. This is how a margin is "
            "legitimately changed: append CI-measured rows, re-derive, paste "
            "the result into PER_BENCHMARK_TIMING_MARGIN / "
            "UNGATEABLE_BENCHMARKS. Does not read --pr-metrics."
        ),
    )
    parser.add_argument(
        "--main-benchmarks", type=Path, default=None,
        help=(
            "File listing main's benchmark keys, one 'module\\tstage' per "
            "line. Used to tell a benchmark that is NEW to main (no baseline "
            "can exist yet) from one that exists on main and is missing its "
            "row (the vacuity case). Omit it and every unbaselined key stays "
            "NO_BASELINE, which is the conservative default."
        ),
    )
    parser.add_argument("--window", type=int, default=DEFAULT_WINDOW,
                        help=f"Rolling window size for baseline median (default: {DEFAULT_WINDOW})")
    parser.add_argument("--json", action="store_true",
                        help="Output results as JSON")
    parser.add_argument("--report-file", type=Path, default=None,
                        help="Also write the Markdown report to this file "
                             "(written even when the gate fails)")
    args = parser.parse_args(argv)

    if args.derive_margins:
        if not args.baseline_jsonl:
            parser.error("--derive-margins requires --baseline-jsonl")
        return _print_derived_margins(args.baseline_jsonl)

    missing = [
        flag for flag, value in
        (("--pr-metrics", args.pr_metrics), ("--baseline-jsonl", args.baseline_jsonl))
        if not value
    ]
    if missing:
        parser.error(f"the following arguments are required: {', '.join(missing)}")

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
    main_benchmarks: set[tuple[str, str]] | None = None
    if args.main_benchmarks is not None and args.main_benchmarks.exists():
        main_benchmarks = set()
        for line in args.main_benchmarks.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) == 2:
                main_benchmarks.add((parts[0], parts[1]))

    results = compare(pr_metrics, baselines, main_benchmarks)
    failures = gate_failures(results)
    advisories = advisory_notes(results)
    report = format_markdown(results, failures, advisories)

    if args.json:
        print(json.dumps(
            {"results": results, "failures": failures, "advisories": advisories},
            indent=2,
        ))
    else:
        print(report)
    if args.report_file:
        args.report_file.write_text(report)

    for note in advisories:
        print(f"ADVISORY (not gated): {note}", file=sys.stderr)

    if failures:
        print("FAIL: performance A/B gate failed", file=sys.stderr)
        for reason in failures:
            print(f"  - {reason}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
