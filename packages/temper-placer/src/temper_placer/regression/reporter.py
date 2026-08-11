"""Regression reporter — produces per-board pass/fail summary.

This module is a delegation shim. The metric-delta computation and the
verdict/result formatting moved to ``temper-orchestration``'s ``reporter``
module (Wave-4 tail-tooling migration): ``MetricDelta`` (``delta_display``,
``message()``, the sign-prefixed delta rendering), ``BoardResult``,
``BatteryVerdictReport`` and ``RegressionReporter`` (the ``total`` /
``passed`` / ``failed`` / ``skipped`` / ``has_failures`` counting and the
``summary()`` / ``battery_report()`` renderers) are Rust pyclasses; this
module re-exports them so the public API is unchanged (``runner.py``,
``cli.py`` and the test suites construct them identically). The helps-battery
*decision* that produces the verdicts and ``budget_exceeded`` stays in
``validation/_thermal_battery.py`` (the verdict thresholds are out of this
module's scope — the reporter only renders what it is handed). The
pre-migration module is pinned VERBATIM as
``tests/regression/_reporter_py_oracle.py`` (content-hash registered in
``scripts/oracle_hashes.json``); bit-identical parity is pinned by
``tests/regression/test_reporter_rust_differential.py``.
"""

from __future__ import annotations

import temper_orchestration as _to

BatteryVerdictReport = _to.BatteryVerdictReport
MetricDelta = _to.MetricDelta
BoardResult = _to.BoardResult
RegressionReporter = _to.RegressionReporter

__all__ = ["BatteryVerdictReport", "BoardResult", "MetricDelta", "RegressionReporter"]
