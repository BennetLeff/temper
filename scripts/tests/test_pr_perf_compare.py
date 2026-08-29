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
    MAX_GATEABLE_MARGIN,
    MIN_NOISE_GROUP,
    NOISE_HEADROOM,
    PER_BENCHMARK_TIMING_MARGIN,
    REAL_REGRESSION_FLOOR,
    TIMING_MARGIN,
    UNGATEABLE_BENCHMARKS,
    PerfGateError,
    _parse_records,
    _status_for,
    advisory_notes,
    compare,
    derive_margin_table,
    format_markdown,
    gate_failures,
    load_main_baselines,
    main,
    margin_for,
    measure_fixed_commit_noise,
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
    """The false positive, reproduced. This is the behaviour being fixed.

    A one-row baseline makes the "median" that row, so the full CI spread
    lands against the margin and the PR #544 runtime no-op reads +26.6% raw --
    past the 20% floor that produced the original false positive. Whether the
    gate actually trips is a margin question, so the classification here uses
    the floor margin directly; hard_blocked_batch's per-benchmark margin has
    since been widened to 30% (re-derived from fixed-commit CI noise on
    2026-08-05), which absorbs this reading -- that absorption is what the
    companion five-row test's "+15.7%, OK" pin is about.
    """
    baselines = load_main_baselines(
        [_record(_CI_HARD_BLOCKED[0], stage="hard_blocked_batch")]
    )
    results = compare(
        [_record(_PR544_HARD_BLOCKED, stage="hard_blocked_batch")], baselines
    )
    delta = results[0]["deltas"]["rust_over_oracle_ratio"]
    assert delta["delta_pct"] == pytest.approx(26.6, abs=0.1)
    # Unsmoothed, it trips the 20% floor -- the original false positive.
    assert _status_for("rust_over_oracle_ratio", delta["delta_pct"]) == "REGRESSION"
    # ... but hard_blocked_batch's derived margin now absorbs it.
    assert margin_for(("bottleneck-geometry", "hard_blocked_batch")) >= 0.30
    assert delta["status"] == "OK"
    assert gate_failures(results) == []


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


def _unbaselined_entry(module="new-mod", stage="new_stage"):
    return [{
        "module": module, "board": "synthetic", "stage": stage,
        "metrics": {"rust_over_oracle_ratio": 0.5},
    }]


def test_new_benchmark_does_not_fail_the_gate() -> None:
    """A benchmark absent from main's registry is its first appearance.

    No baseline CAN exist: the gate reads the baseline from main (so a PR
    cannot move its own goalposts) and main does not have this code. Failing
    here made adding any benchmark impossible in one PR.
    """
    results = compare(
        _unbaselined_entry(), {}, main_benchmarks={("existing-mod", "existing_stage")}
    )
    assert results[0]["status"] == "NEW_BENCHMARK"
    assert gate_failures(results) == []


def test_benchmark_on_main_without_a_baseline_row_still_fails() -> None:
    """The vacuity case must keep failing closed.

    A module that exists on main and ships without a baseline row is not
    covered by the performance A/B. That is what this gate is for, and the
    NEW_BENCHMARK carve-out must not widen to cover it.
    """
    results = compare(
        _unbaselined_entry(), {}, main_benchmarks={("new-mod", "new_stage")}
    )
    assert results[0]["status"] == "NO_BASELINE"
    failures = gate_failures(results)
    assert len(failures) == 1
    assert "already exists on main" in failures[0]


def test_absent_registry_degrades_to_the_strict_behaviour() -> None:
    """No registry supplied -> every unbaselined key stays NO_BASELINE.

    A fetch failure in CI must not silently turn the gate permissive.
    """
    results = compare(_unbaselined_entry(), {}, main_benchmarks=None)
    assert results[0]["status"] == "NO_BASELINE"
    assert len(gate_failures(results)) == 1


# ---------------------------------------------------------------------------
# Measurement-regime identity (U1 / R5-R8)
# ---------------------------------------------------------------------------


def _regime_record(ratio: float, regime: str, *, commit: str = "deadbeef", ts: str = "2026-08-04T00:00:00") -> dict:
    row = _record(ratio, ts=ts)
    row["git_commit"] = commit
    row["measurement_regime"] = {
        "fingerprint": regime,
        "metadata": {"fixture": regime},
    }
    return row


def test_legacy_rows_have_a_stable_legacy_regime_identity():
    baseline = load_main_baselines([_record(0.10)])
    pr = _regime_record(0.105, "legacy-v2")
    results = compare([pr], baseline)
    assert results[0]["status"] == "OK"
    assert results[0]["measurement_regime"] == "legacy-v2"


def test_incompatible_regime_fails_closed_without_using_old_rows():
    baseline = load_main_baselines([_regime_record(0.50, "old-regime")])
    results = compare([_regime_record(0.60, "new-regime")], baseline)
    assert results[0]["status"] == "INCOMPATIBLE_BASELINE"
    assert results[0]["available_regimes"] == ["old-regime"]
    failures = gate_failures(results)
    assert len(failures) == 1
    assert "INCOMPATIBLE_BASELINE" in failures[0]
    assert "recapture" in failures[0].lower()
    report = format_markdown(results, failures)
    assert "old-regime" in report
    assert "new-regime" in report


def test_mixed_regimes_select_only_the_current_regime_window():
    records = [
        _regime_record(0.90, "old-regime", ts="2026-08-04T00:00:01"),
        _regime_record(0.91, "old-regime", ts="2026-08-04T00:00:02"),
        _regime_record(0.50, "new-regime", ts="2026-08-04T00:00:03"),
    ]
    baselines = load_main_baselines(records)
    result = compare([_regime_record(0.55, "new-regime")], baselines)[0]
    assert result["status"] == "OK"
    assert result["deltas"]["rust_over_oracle_ratio"]["main"] == 0.5


def test_fixed_commit_noise_does_not_mix_regimes():
    records = [
        _regime_record(1.00, "old-regime", commit="same", ts="2026-08-04T00:00:01"),
        _regime_record(1.01, "old-regime", commit="same", ts="2026-08-04T00:00:02"),
        _regime_record(1.50, "old-regime", commit="same", ts="2026-08-04T00:00:03"),
        _regime_record(0.50, "new-regime", commit="same", ts="2026-08-04T00:00:04"),
    ]
    measured = measure_fixed_commit_noise(records)
    # The singleton new regime is not a qualifying group and cannot dilute or
    # inflate the old-regime group's noise calculation.
    assert measured[("bottleneck-geometry", "cell_capacity_batch")]["n"] == 3
    assert measured[("bottleneck-geometry", "cell_capacity_batch")]["groups"] == 1


def test_fixed_commit_margin_uses_newest_regime_not_legacy_noise():
    key = ("bottleneck-geometry", "cell_capacity_batch")
    records = [
        _regime_record(1.0, "legacy-v2", commit="legacy", ts="2026-08-04T00:00:01"),
        _regime_record(1.0, "legacy-v2", commit="legacy", ts="2026-08-04T00:00:02"),
        _regime_record(2.0, "legacy-v2", commit="legacy", ts="2026-08-04T00:00:03"),
        _regime_record(1.0, "current-regime", commit="current", ts="2026-08-05T00:00:01"),
        _regime_record(1.0, "current-regime", commit="current", ts="2026-08-05T00:00:02"),
        _regime_record(1.05, "current-regime", commit="current", ts="2026-08-05T00:00:03"),
    ]

    measured = measure_fixed_commit_noise(records)
    assert measured.regimes[key]["legacy-v2"]["worst_pct"] == pytest.approx(100.0)
    assert measured.regimes[key]["current-regime"]["worst_pct"] == pytest.approx(5.0)
    assert measured[key]["worst_pct"] == pytest.approx(5.0)

    _, ungateable = derive_margin_table(records)
    assert key not in ungateable


def test_fixed_commit_margin_does_not_fall_back_to_legacy_before_current_group_is_ready():
    key = ("bottleneck-geometry", "cell_capacity_batch")
    records = [
        _regime_record(1.0, "legacy-v2", commit="legacy", ts="2026-08-04T00:00:01"),
        _regime_record(1.0, "legacy-v2", commit="legacy", ts="2026-08-04T00:00:02"),
        _regime_record(2.0, "legacy-v2", commit="legacy", ts="2026-08-04T00:00:03"),
        _regime_record(1.0, "current-regime", commit="current", ts="2026-08-05T00:00:01"),
    ]

    measured = measure_fixed_commit_noise(records)

    assert measured.regimes[key]["legacy-v2"]["worst_pct"] == pytest.approx(100.0)
    assert key in measured  # legacy mapping remains API-compatible
    assert key not in measured.active
    assert key not in derive_margin_table(records)[1]


# ---------------------------------------------------------------------------
# Per-benchmark margins (2026-08-05)
#
# One constant for seventeen benchmarks produced false regressions on arms
# whose own fixed-commit noise exceeded it. These tests pin the derivation so
# the table cannot drift from the measurement in EITHER direction: too tight
# and the false positives come back, too wide and the gate stops biting.
# See docs/evidence/2026-08-05-perf-ab-per-benchmark-margin.md.
# ---------------------------------------------------------------------------

_BASELINE_PATH = (
    Path(__file__).resolve().parents[2]
    / "power_pcb_dataset/metrics/perf_ab_baseline.jsonl"
)

_REDERIVE = (
    "Re-derive with `python3 scripts/pr_perf_compare.py --derive-margins "
    "--baseline-jsonl power_pcb_dataset/metrics/perf_ab_baseline.jsonl` and "
    "paste the result into scripts/pr_perf_compare.py."
)


def _baseline_records() -> list[dict]:
    return _parse_records(_BASELINE_PATH.read_text(), str(_BASELINE_PATH))


def test_fixed_commit_noise_is_actually_measurable():
    """The derivation must rest on repeated runs of ONE commit.

    Spread across commits may be real performance change; using it as the
    margin would absorb genuine regressions into the band. If the baseline ever
    stops carrying same-commit groups, every margin below is unfounded and this
    must fail rather than silently fall back to cross-commit spread.
    """
    measured = measure_fixed_commit_noise(_baseline_records())
    assert measured, (
        "the committed baseline carries no group of "
        f"{MIN_NOISE_GROUP}+ rows sharing one git_commit, so per-benchmark "
        "noise cannot be measured at all. Capture repeated runs of a single "
        "commit via workflow_dispatch on .github/workflows/pr-perf-check.yml."
    )
    for key, stats in measured.items():
        assert stats["n"] >= MIN_NOISE_GROUP, key


def test_committed_margins_match_the_measurement():
    """PER_BENCHMARK_TIMING_MARGIN is exactly what the baseline implies.

    Hand-editing a margin upward to make a failure pass is the thing the gate's
    own output forbids. This test is the mechanical form of that rule: the
    number has to come out of the measurement.
    """
    gated, _ = derive_margin_table(_baseline_records())
    assert PER_BENCHMARK_TIMING_MARGIN == gated, _REDERIVE


def test_ungateable_set_matches_the_measurement():
    """UNGATEABLE_BENCHMARKS is exactly the measured-ungateable set.

    Both directions matter. A benchmark cannot be excused from the gate
    without a measurement saying no margin separates its noise from the
    real-regression class -- that is what stops the exclusion list from
    becoming a place to park inconvenient failures. And a benchmark whose
    variance has since been reduced must be re-gated, not left excused.
    """
    _, ungateable = derive_margin_table(_baseline_records())
    assert set(UNGATEABLE_BENCHMARKS) == set(ungateable), _REDERIVE


def test_no_gated_margin_reaches_the_real_regression_class():
    """Every gated margin stays clear of the smallest real regression on record.

    A margin at or above +50.7% cannot tell noise from a genuine regression, so
    a benchmark carrying one is not gated in any meaningful sense.
    """
    for key, margin in PER_BENCHMARK_TIMING_MARGIN.items():
        assert margin <= MAX_GATEABLE_MARGIN, key
        assert margin < REAL_REGRESSION_FLOOR, key
    assert TIMING_MARGIN <= MAX_GATEABLE_MARGIN


def test_no_benchmark_is_gated_tighter_than_its_measured_noise():
    """A margin below ~2x a benchmark's own noise is a false-positive factory.

    This is the defect being fixed, stated as an invariant: the 20% default was
    below the fixed-commit noise of physics-safety, loaders, and the three
    ungateable arms, and each of them failed PRs that could not have touched
    them.
    """
    measured = measure_fixed_commit_noise(_baseline_records())
    for key, stats in measured.items():
        if key in UNGATEABLE_BENCHMARKS:
            continue
        applied = margin_for(key)
        assert applied * 100 >= NOISE_HEADROOM * stats["worst_pct"], (
            f"{key} is gated at {applied:.0%} but its worst measured "
            f"fixed-commit excursion is {stats['worst_pct']:.1f}%. " + _REDERIVE
        )


def _gated_benchmarks() -> list[tuple[str, str]]:
    measured = measure_fixed_commit_noise(_baseline_records())
    return sorted(k for k in measured if k not in UNGATEABLE_BENCHMARKS)


def _window(module: str, stage: str, base: float) -> list[dict]:
    return [
        {"module": module, "board": "synthetic", "stage": stage,
         "timestamp": f"2026-08-05T00:00:0{i}", "git_commit": "base",
         "metrics": {"rust_over_oracle_ratio": base}}
        for i in range(DEFAULT_WINDOW)
    ]


def _pr_row(module: str, stage: str, ratio: float) -> list[dict]:
    return [{"module": module, "board": "synthetic", "stage": stage,
             "metrics": {"rust_over_oracle_ratio": ratio}}]


@pytest.mark.parametrize("bench", _gated_benchmarks())
def test_a_real_scale_regression_still_fails_every_gated_benchmark(bench):
    """THE BITE PROOF. A regression at the real-regression scale must fail.

    +50.7% is the smallest genuine regression in the repo's own metric history
    (docs/evidence/2026-08-04-perf-ab-harness-noise-floor.md). Widening margins
    to stop false positives is only defensible if the gate still catches this,
    so it is asserted for every gated benchmark on every run -- not
    demonstrated once and trusted thereafter.
    """
    module, stage = bench
    base = 0.400000
    results = compare(
        _pr_row(module, stage, base * (1 + REAL_REGRESSION_FLOOR)),
        load_main_baselines(_window(module, stage, base)),
    )
    assert results[0]["deltas"]["rust_over_oracle_ratio"]["status"] == "REGRESSION"
    assert gate_failures(results), f"{bench} no longer bites at +50.7%"


def test_the_widened_benchmarks_still_bite_just_above_their_margin():
    """Widening is bounded: a delta just past the new margin still fails."""
    for (module, stage), margin in PER_BENCHMARK_TIMING_MARGIN.items():
        base = 0.500000
        baselines = load_main_baselines(_window(module, stage, base))
        over = compare(
            _pr_row(module, stage, base * (1 + margin) * 1.01), baselines
        )
        assert gate_failures(over), (module, stage)
        under = compare(
            _pr_row(module, stage, base * (1 + margin) * 0.99), baselines
        )
        assert not gate_failures(under), (module, stage)


def test_default_margin_still_applies_to_an_uncharacterised_benchmark():
    """An unknown key is gated at 20%, not excused.

    A benchmark nobody has characterised must not fall through into the
    permissive branch -- that is how a per-benchmark table would otherwise
    become a way to opt out of the gate by omission.
    """
    assert margin_for(("brand-new", "arm")) == TIMING_MARGIN
    assert margin_for(None) == TIMING_MARGIN
    assert _status_for("rust_over_oracle_ratio", 20.1, ("brand-new", "arm")) == "REGRESSION"


def _ungateable_case(delta_ratio: float):
    module, stage = next(iter(UNGATEABLE_BENCHMARKS))
    base = 0.400000
    return compare(
        _pr_row(module, stage, base * delta_ratio),
        load_main_baselines(_window(module, stage, base)),
    )


def test_ungateable_benchmark_reports_advisory_and_never_fails():
    results = _ungateable_case(2.0)  # +100%, far past any margin
    assert results[0]["deltas"]["rust_over_oracle_ratio"]["status"] == "ADVISORY"
    assert gate_failures(results) == []
    notes = advisory_notes(results)
    assert len(notes) == 1
    assert "NOT GATED" in notes[0]


def test_ungateable_benchmark_never_claims_an_improvement():
    """physics-emi's own noise produced -42.8% on unmodified code.

    Reporting that as an IMPROVED is the same error as reporting its mirror
    image as a regression, and a gate that always shows a green arrow stops
    being read.
    """
    results = _ungateable_case(0.5)  # -50%
    assert results[0]["deltas"]["rust_over_oracle_ratio"]["status"] == "ADVISORY"
    assert results[0]["status"] == "ADVISORY"


def test_advisories_appear_in_the_report_even_when_the_gate_passes():
    """An exclusion nobody sees is an exclusion nobody revisits."""
    results = _ungateable_case(1.5)
    report = format_markdown(results, [], advisory_notes(results))
    assert "NOT gated" in report
    assert "Performance A/B gate passed" in report
    assert "not gated" in report  # the Margin column


def test_ungateable_arms_are_a_minority_of_the_harness():
    """The gate must not become a report by attrition.

    Excluding a benchmark is legitimate when the measurement demands it, but if
    most of the harness were excused the gate would be vacuous -- the failure
    mode scripts/check_vacuous_gates.py exists because of.
    """
    measured = measure_fixed_commit_noise(_baseline_records())
    gated = [k for k in measured if k not in UNGATEABLE_BENCHMARKS]
    assert len(gated) > len(UNGATEABLE_BENCHMARKS), (
        f"only {len(gated)} of {len(measured)} benchmarks are gated"
    )


def test_ungateable_entries_are_all_registered_benchmarks():
    """No stale exclusion for a benchmark that no longer exists."""
    measured = set(measure_fixed_commit_noise(_baseline_records()))
    assert set(UNGATEABLE_BENCHMARKS) <= measured
    assert set(PER_BENCHMARK_TIMING_MARGIN) <= measured


def test_derive_margins_fails_closed_without_fixed_commit_groups(tmp_path):
    """A baseline with no repeated commit cannot produce a margin table.

    Printing an empty table would invite someone to paste it over one derived
    from real data, silently returning every benchmark to the default.
    """
    thin = tmp_path / "thin.jsonl"
    thin.write_text("".join(
        json.dumps({
            "module": "m", "board": "synthetic", "stage": "s",
            "git_commit": f"c{i}", "timestamp": f"2026-08-05T00:00:0{i}",
            "metrics": {"rust_over_oracle_ratio": 0.5},
        }) + "\n" for i in range(5)
    ))
    assert main(["--derive-margins", "--baseline-jsonl", str(thin)]) == 1


def test_derive_margins_reproduces_the_committed_table(capsys):
    """The documented re-derivation command actually works end to end."""
    assert main(["--derive-margins", "--baseline-jsonl", str(_BASELINE_PATH)]) == 0
    out = capsys.readouterr().out
    assert "UNGATEABLE" in out
    for module, stage in UNGATEABLE_BENCHMARKS:
        assert f"{module}/{stage}" in out
