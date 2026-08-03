"""Tests for scripts/check_transition_table_mutations.py (R40, U4).

Covers the gate's failure modes against synthetic sweep reports (no C build):
  - zero live mutants + full row coverage + fresh report -> PASS,
  - one live mutant -> FAIL naming the row and mutant,
  - a skipped row (rows_covered < rows_total) -> FAIL on coverage,
  - a mutation error -> FAIL,
  - a stale report -> TOOL ERROR (fail-closed, review fix: a scheduled or
    committed report must never satisfy the gate),
  - missing / malformed / wrong-schema report -> TOOL ERROR.
"""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_transition_table_mutations import (  # noqa: E402
    EXIT_OK,
    EXIT_TOOL_ERROR,
    EXIT_VIOLATION,
    SCHEMA_VERSION,
    run_gate,
)


def _fresh_report(**overrides):
    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "rows_total": 42,
        "rows_covered": 42,
        "rows_swept": 42,
        "mutants_total": 109,
        "killed": 109,
        "live": 0,
        "equivalent": 59,
        "errors": 0,
        "mutation_score": 1.0,
        "baseline_pass": True,
        "live_mutants": [],
        "errors_list": [],
    }
    report.update(overrides)
    return report


def _write(tmp_path, report):
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report))
    return str(path)


class TestGatePass:
    def test_zero_live_full_coverage_passes(self, tmp_path):
        report = _fresh_report()
        code, message = run_gate(_write(tmp_path, report))
        assert code == EXIT_OK
        assert "PASS" in message

    def test_equivalent_mutants_do_not_fail(self, tmp_path):
        report = _fresh_report(killed=103, equivalent=65, mutation_score=0.94)
        code, message = run_gate(_write(tmp_path, report))
        assert code == EXIT_OK


class TestGateViolations:
    def test_live_mutant_fails_naming_row_and_mutant(self, tmp_path):
        report = _fresh_report(
            killed=108,
            live=1,
            live_mutants=[{
                "row_index": 3,
                "from": "STATE_PAN_DET",
                "event": "PAN_DETECTED",
                "op": "guard_add",
                "mutated_target": "STATE_PREHEAT",
                "mutated_fault": "FAULT_OVER_TEMP",
                "reason": "assertion-gap",
                "evidence": "",
            }],
        )
        code, message = run_gate(_write(tmp_path, report))
        assert code == EXIT_VIOLATION
        assert "LIVE MUTANT" in message
        assert "row 3" in message
        assert "PAN_DETECTED" in message
        assert "guard_add" in message

    def test_skipped_row_fails_coverage(self, tmp_path):
        report = _fresh_report(rows_covered=41, rows_swept=41)
        code, message = run_gate(_write(tmp_path, report))
        assert code == EXIT_VIOLATION
        assert "row coverage" in message
        assert "41/42" in message

    def test_mutation_error_fails(self, tmp_path):
        report = _fresh_report(
            errors=1,
            errors_list=[{
                "row_index": 5,
                "event": "NEAR_TARGET",
                "op": "wrong_target",
                "evidence": "build failed: injected",
            }],
        )
        code, message = run_gate(_write(tmp_path, report))
        assert code == EXIT_VIOLATION
        assert "mutation error" in message
        assert "injected" in message

    def test_baseline_failure_is_tool_error(self, tmp_path):
        report = _fresh_report(baseline_pass=False)
        code, message = run_gate(_write(tmp_path, report))
        assert code == EXIT_TOOL_ERROR
        assert "baseline_pass" in message


class TestGateToolErrors:
    def test_missing_report_is_tool_error(self, tmp_path):
        code, message = run_gate(str(tmp_path / "nope.json"))
        assert code == EXIT_TOOL_ERROR
        assert "not found" in message

    def test_malformed_report_is_tool_error(self, tmp_path):
        path = tmp_path / "report.json"
        path.write_text("{not json")
        code, message = run_gate(str(path))
        assert code == EXIT_TOOL_ERROR
        assert "malformed" in message

    def test_wrong_schema_is_tool_error(self, tmp_path):
        report = _fresh_report(schema_version=99)
        code, message = run_gate(_write(tmp_path, report))
        assert code == EXIT_TOOL_ERROR
        assert "schema_version" in message

    def test_stale_report_fails_closed(self, tmp_path):
        """A report older than the window must never satisfy the gate."""
        stale = datetime.datetime.now(datetime.UTC) - datetime.timedelta(
            seconds=7200
        )
        report = _fresh_report(generated_at=stale.isoformat())
        code, message = run_gate(
            _write(tmp_path, report), max_age_seconds=3600
        )
        assert code == EXIT_TOOL_ERROR
        assert "stale" in message.lower()

    def test_fresh_report_within_window_passes(self, tmp_path):
        recent = datetime.datetime.now(datetime.UTC) - datetime.timedelta(
            seconds=30
        )
        report = _fresh_report(generated_at=recent.isoformat())
        code, message = run_gate(
            _write(tmp_path, report), max_age_seconds=3600
        )
        assert code == EXIT_OK

    def test_missing_generated_at_is_tool_error(self, tmp_path):
        report = _fresh_report()
        del report["generated_at"]
        code, message = run_gate(_write(tmp_path, report))
        assert code == EXIT_TOOL_ERROR
        assert "generated_at" in message
