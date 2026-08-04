"""Tests for the performance A/B gate (scripts/pr_perf_compare.py).

Every test here exists because the corresponding path used to pass silently.
Prior to 2026-08-04 the script returned 0 unconditionally, a missing baseline
rendered as an em-dash table row, and an NDJSON metrics stream crashed it --
under a `continue-on-error: true` mask that reported the job as green.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pr_perf_compare import (  # noqa: E402
    COMPLETION_MARGIN,
    DEFAULT_WINDOW,
    IMPROVEMENT_THRESHOLD,
    TIMING_MARGIN,
    PerfGateError,
    _parse_records,
    _status_for,
    compare,
    gate_failures,
    load_main_baselines,
    main,
)


def _record(ratio: float, *, stage: str = "cell_capacity_batch", ts: str = "2026-08-04T00:00:00") -> dict:
    return {
        "schema_version": 2,
        "timestamp": ts,
        "git_commit": "deadbeef",
        "board": "synthetic",
        "stage": stage,
        "module": "bottleneck-geometry",
        "metrics": {"rust_over_oracle_ratio": ratio, "rust_wall_us": 100.0},
    }


def _write(tmp_path: Path, name: str, records: list[dict]) -> Path:
    path = tmp_path / name
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    return path


# ---------------------------------------------------------------------------
# Stream parsing -- the defect that crashed every CI run
# ---------------------------------------------------------------------------


def test_parses_ndjson_stream():
    text = json.dumps(_record(0.1)) + "\n" + json.dumps(_record(0.2)) + "\n"
    assert len(_parse_records(text, "src")) == 2


def test_parses_legacy_json_array():
    text = json.dumps([_record(0.1), _record(0.2)])
    assert len(_parse_records(text, "src")) == 2


def test_progress_output_in_the_stream_is_an_error_not_a_skipped_line():
    """A producer printing progress to stdout corrupts the metrics stream.

    That is how the comparison came to crash on every run. Skipping the bad
    line would have hidden it; naming it fails the gate loudly.
    """
    text = "Router V6 Benchmark Suite\n" + json.dumps(_record(0.1)) + "\n"
    with pytest.raises(PerfGateError, match="not JSON"):
        _parse_records(text, "PR metrics")


def test_blank_stream_parses_to_nothing():
    assert _parse_records("   \n\n", "src") == []


# ---------------------------------------------------------------------------
# Metric direction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("metric", ["wall_time_ms", "runtime_seconds", "rust_over_oracle_ratio"])
def test_lower_is_better_metrics_regress_when_they_rise(metric):
    assert _status_for(metric, TIMING_MARGIN * 100 + 0.1) == "REGRESSION"
    assert _status_for(metric, TIMING_MARGIN * 100 - 0.1) == "OK"
    assert _status_for(metric, -IMPROVEMENT_THRESHOLD * 100 - 0.1) == "IMPROVED"


@pytest.mark.parametrize("metric", ["completion_pct", "completion_rate"])
def test_higher_is_better_metrics_regress_when_they_fall(metric):
    assert _status_for(metric, -COMPLETION_MARGIN * 100 - 0.1) == "REGRESSION"
    assert _status_for(metric, -COMPLETION_MARGIN * 100 + 0.1) == "OK"
    assert _status_for(metric, IMPROVEMENT_THRESHOLD * 100 + 0.1) == "IMPROVED"


def test_unrecognised_metric_names_are_informational_not_gated():
    """`_wall_us` figures are machine-dependent and must never fail a gate."""
    assert _status_for("rust_wall_us", 500.0) == "OK"
    assert _status_for("drc_errors", 500.0) == "OK"


# ---------------------------------------------------------------------------
# Fail-closed behaviour
# ---------------------------------------------------------------------------


def test_missing_baseline_row_fails_the_gate():
    results = compare([_record(0.2)], {})
    assert results[0]["status"] == "NO_BASELINE"
    failures = gate_failures(results)
    assert len(failures) == 1
    assert "no baseline row" in failures[0]


def test_regression_beyond_margin_fails_the_gate():
    baselines = load_main_baselines([_record(0.10)])
    results = compare([_record(0.10 * (1 + TIMING_MARGIN) + 0.001)], baselines)
    assert gate_failures(results)


def test_regression_within_margin_passes():
    baselines = load_main_baselines([_record(0.10)])
    results = compare([_record(0.10 * (1 + TIMING_MARGIN) - 0.001)], baselines)
    assert not gate_failures(results)


def test_main_exits_nonzero_on_regression(tmp_path):
    baseline = _write(tmp_path, "baseline.jsonl", [_record(0.10)])
    pr = _write(tmp_path, "pr.jsonl", [_record(0.50)])
    assert main(["--pr-metrics", str(pr), "--baseline-jsonl", str(baseline)]) == 1


def test_main_exits_zero_when_within_noise(tmp_path):
    baseline = _write(tmp_path, "baseline.jsonl", [_record(0.10)])
    pr = _write(tmp_path, "pr.jsonl", [_record(0.105)])
    assert main(["--pr-metrics", str(pr), "--baseline-jsonl", str(baseline)]) == 0


def test_main_fails_closed_on_empty_baseline(tmp_path):
    baseline = tmp_path / "baseline.jsonl"
    baseline.write_text("")
    pr = _write(tmp_path, "pr.jsonl", [_record(0.10)])
    assert main(["--pr-metrics", str(pr), "--baseline-jsonl", str(baseline)]) == 1


def test_main_fails_closed_on_absent_baseline(tmp_path):
    pr = _write(tmp_path, "pr.jsonl", [_record(0.10)])
    assert main(["--pr-metrics", str(pr), "--baseline-jsonl", str(tmp_path / "nope.jsonl")]) == 1


def test_main_fails_closed_on_empty_pr_metrics(tmp_path):
    """No records means nothing was compared -- that is a failure, not a pass."""
    baseline = _write(tmp_path, "baseline.jsonl", [_record(0.10)])
    pr = tmp_path / "pr.jsonl"
    pr.write_text("")
    assert main(["--pr-metrics", str(pr), "--baseline-jsonl", str(baseline)]) == 1


def test_main_fails_closed_on_unbaselined_module(tmp_path):
    baseline = _write(tmp_path, "baseline.jsonl", [_record(0.10, stage="cell_capacity_batch")])
    pr = _write(tmp_path, "pr.jsonl", [_record(0.10, stage="a_brand_new_kernel")])
    assert main(["--pr-metrics", str(pr), "--baseline-jsonl", str(baseline)]) == 1


def test_main_fails_closed_on_corrupt_pr_stream(tmp_path):
    baseline = _write(tmp_path, "baseline.jsonl", [_record(0.10)])
    pr = tmp_path / "pr.jsonl"
    pr.write_text("Router V6 Benchmark Suite\n" + json.dumps(_record(0.10)) + "\n")
    assert main(["--pr-metrics", str(pr), "--baseline-jsonl", str(baseline)]) == 1


def test_report_file_is_written_even_when_the_gate_fails(tmp_path):
    baseline = _write(tmp_path, "baseline.jsonl", [_record(0.10)])
    pr = _write(tmp_path, "pr.jsonl", [_record(0.50)])
    report = tmp_path / "report.md"
    assert main([
        "--pr-metrics", str(pr),
        "--baseline-jsonl", str(baseline),
        "--report-file", str(report),
    ]) == 1
    body = report.read_text()
    assert body.startswith("## Performance Comparison")
    assert "gate FAILED" in body


def test_report_file_is_written_when_the_baseline_is_missing(tmp_path):
    """The PR comment must still say why, or the failure is unactionable."""
    pr = _write(tmp_path, "pr.jsonl", [_record(0.10)])
    report = tmp_path / "report.md"
    assert main([
        "--pr-metrics", str(pr),
        "--baseline-jsonl", str(tmp_path / "nope.jsonl"),
        "--report-file", str(report),
    ]) == 1
    assert "gate FAILED" in report.read_text()


# ---------------------------------------------------------------------------
# Baseline windowing
# ---------------------------------------------------------------------------


def test_baseline_is_the_median_of_the_trailing_window():
    records = [
        _record(r, ts=f"2026-08-04T00:00:0{i}")
        for i, r in enumerate([9.0, 9.0, 0.1, 0.2, 0.3, 0.4, 0.5])
    ]
    baselines = load_main_baselines(records, window=5)
    key = ("bottleneck-geometry", "synthetic", "cell_capacity_batch")
    # The two 9.0 outliers fall outside the 5-entry window.
    assert baselines[key]["rust_over_oracle_ratio"] == pytest.approx(0.3)


def test_records_without_board_or_stage_are_not_baselines():
    assert load_main_baselines([{"module": "m", "metrics": {"x_ms": 1.0}}]) == {}


# ---------------------------------------------------------------------------
# Baseline WIDTH -- the defect that produced false positives on clean PRs
#
# The window logic above was always correct. What was wrong is that the
# committed baseline could never fill it: .github/workflows/pr-perf-check.yml
# triggered on `pull_request` only, so no row was ever measured on main and the
# file sat at n=1 per (module, board, stage). A one-row "median" is that row,
# so no smoothing happened at all and the full CI variance landed against the
# 20% margin.
# ---------------------------------------------------------------------------

# Verbatim CI readings of `rust_over_oracle_ratio` for
# bottleneck-geometry/synthetic/hard_blocked_batch, taken from
# power_pcb_dataset/metrics/perf_ab_baseline.jsonl. The first is the lone row
# the baseline shipped with; the rest are later CI runs of code that does not
# touch the benchmarked module. The reading under test, 0.416550, is PR #544 --
# a one-line `typing.cast()` in router_v6/channel_widths.py, which compiles to
# `return val` and cannot move a bottleneck-geometry benchmark.
_CI_HARD_BLOCKED = [0.328949, 0.368897, 0.343520, 0.360175, 0.367011]
_PR544_HARD_BLOCKED = 0.416550


def test_single_row_baseline_reports_a_runtime_no_op_as_a_regression():
    """The false positive, reproduced. This is the behaviour being fixed."""
    baselines = load_main_baselines(
        [_record(_CI_HARD_BLOCKED[0], stage="hard_blocked_batch")]
    )
    results = compare(
        [_record(_PR544_HARD_BLOCKED, stage="hard_blocked_batch")], baselines
    )
    delta = results[0]["deltas"]["rust_over_oracle_ratio"]
    assert delta["delta_pct"] == pytest.approx(26.6, abs=0.1)
    assert delta["status"] == "REGRESSION"
    assert gate_failures(results)


def test_five_row_baseline_absorbs_the_same_reading():
    """Same reading, same margin, baseline widened to the full window."""
    baselines = load_main_baselines(
        [
            _record(r, stage="hard_blocked_batch", ts=f"2026-08-04T00:00:0{i}")
            for i, r in enumerate(_CI_HARD_BLOCKED)
        ]
    )
    results = compare(
        [_record(_PR544_HARD_BLOCKED, stage="hard_blocked_batch")], baselines
    )
    delta = results[0]["deltas"]["rust_over_oracle_ratio"]
    assert delta["delta_pct"] == pytest.approx(15.7, abs=0.1)
    assert delta["status"] == "OK"
    assert gate_failures(results) == []
    # And the fix is the baseline, not a loosened margin.
    assert TIMING_MARGIN == 0.20


def test_committed_baseline_fills_the_rolling_window():
    """The committed baseline must carry a full window per benchmark key.

    A key with fewer than DEFAULT_WINDOW rows gets no smoothing, which is what
    made an unrelated PR look like a 26.6% regression. New benchmarks land with
    one row by necessity; the capture path on main
    (.github/workflows/pr-perf-check.yml, `push: branches: [main]`) is what
    fills them in, and this test is the reminder that it has to happen.
    """
    baseline_path = (
        Path(__file__).resolve().parents[2]
        / "power_pcb_dataset/metrics/perf_ab_baseline.jsonl"
    )
    records = _parse_records(baseline_path.read_text(), str(baseline_path))
    assert records, "the committed baseline is empty -- the gate fails closed"

    counts: dict[tuple[str, str, str], int] = {}
    for r in records:
        key = (r.get("module", ""), r.get("board", ""), r.get("stage", ""))
        counts[key] = counts.get(key, 0) + 1

    thin = {k: n for k, n in counts.items() if n < DEFAULT_WINDOW}
    assert not thin, (
        f"these benchmark keys have fewer than {DEFAULT_WINDOW} baseline rows "
        f"and are therefore unsmoothed: {thin}. Capture more rows from main "
        f"(run pr-perf-check.yml via workflow_dispatch, or wait for a main "
        f"push in its trigger paths) and append them. Do NOT capture locally: "
        f"darwin measures ~-11% against the Linux CI container on identical "
        f"code."
    )
