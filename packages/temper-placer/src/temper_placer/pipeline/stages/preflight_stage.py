"""Preflight stage: runs feasibility checks on board + netlist + constraints."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from temper_placer.pipeline.dag_types import DataContext, StageResult


class PreflightStage:
    def __call__(self, state: Any, context: DataContext) -> StageResult:
        start = time.time()
        from temper_placer.pipeline.preflight import PreflightChecker
        from temper_placer.pipeline.state import PipelineError, PipelinePhase

        @dataclass
        class MockFabPreset:
            min_clearance: float = 0.2

        board = context["board"]
        netlist = context["netlist"]
        constraints = context["constraints"]

        print("Running preflight feasibility checks...")
        checker = PreflightChecker()
        report = checker.run(board, netlist, constraints, MockFabPreset())
        print(report.summary())

        state.preflight_report = report

        elapsed = time.time() - start
        if not report.passed:
            raise PipelineError(f"Preflight checks failed: {report.summary()}", phase=PipelinePhase.PREFLIGHT)

        return StageResult(
            outputs={"preflight_report": report},
            duration_s=elapsed,
        )
