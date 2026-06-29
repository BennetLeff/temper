"""Autoprof experiment loop for the GPBM measurement framework.

Consumes PipelineProfiler data to identify bottlenecks and produce
before/after delta tables for iterative optimization.

Usage:
    from temper_placer.profiling.autoprof import AutoprofExperiment

    exp = AutoprofExperiment(baseline_path="baseline_v1.json")
    exp.measure(pipeline_fn, boards=["piantor"])
    report = exp.compare()
    print(report.to_markdown())
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class DeltaRow:
    stage_name: str
    before_p95_ms: float
    after_p95_ms: float
    delta_pct: float
    direction: str  # "faster", "slower", "same"

    @classmethod
    def from_timings(cls, name: str, before: float, after: float, threshold: float = 5.0) -> "DeltaRow":
        if before <= 0:
            before = 0.001
        delta_pct = ((after - before) / before) * 100.0
        if abs(delta_pct) < 1.0:
            direction = "same"
        elif delta_pct < 0:
            direction = "faster"
        else:
            direction = "slower"
        return cls(
            stage_name=name,
            before_p95_ms=round(before, 3),
            after_p95_ms=round(after, 3),
            delta_pct=round(delta_pct, 2),
            direction=direction,
        )


@dataclass
class AutoprofReport:
    delta_table: list[DeltaRow] = field(default_factory=list)
    bottleneck_stage: str = ""
    total_before_ms: float = 0.0
    total_after_ms: float = 0.0
    boards_tested: int = 0
    experiment_type: str = "autoprof"

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_type": self.experiment_type,
            "bottleneck_stage": self.bottleneck_stage,
            "total_before_ms": round(self.total_before_ms, 3),
            "total_after_ms": round(self.total_after_ms, 3),
            "boards_tested": self.boards_tested,
            "delta_table": [
                {
                    "stage": r.stage_name,
                    "before_p95_ms": r.before_p95_ms,
                    "after_p95_ms": r.after_p95_ms,
                    "delta_pct": r.delta_pct,
                    "direction": r.direction,
                }
                for r in self.delta_table
            ],
        }

    def to_pipeline_metrics_record(
        self, board: str = "all", module: str = "autoprof"
    ) -> "PipelineMetricsRecord":
        from temper_placer.regression.metrics_recorder import PipelineMetricsRecord

        metrics: dict[str, float] = {}
        for row in self.delta_table:
            metrics[f"{row.stage_name}_before_p95_ms"] = row.before_p95_ms
            metrics[f"{row.stage_name}_after_p95_ms"] = row.after_p95_ms
            metrics[f"{row.stage_name}_delta_pct"] = row.delta_pct
        metrics["total_before_ms"] = self.total_before_ms
        metrics["total_after_ms"] = self.total_after_ms
        metrics["boards_tested"] = float(self.boards_tested)

        return PipelineMetricsRecord(
            board=board,
            stage=self.bottleneck_stage,
            module=module,
            metrics=metrics,
        )

    def to_markdown(self) -> str:
        lines = ["## Autoprof Experiment Results\n"]
        lines.append(f"**Bottleneck stage:** `{self.bottleneck_stage}`  ")
        lines.append(f"**Boards tested:** {self.boards_tested}  ")
        lines.append(f"**Total time:** {self.total_before_ms:.1f}ms -> {self.total_after_ms:.1f}ms\n")
        lines.append("| Stage | Before (p95 ms) | After (p95 ms) | Delta % | Direction |")
        lines.append("|-------|----------------|---------------|--------|-----------|")
        for r in self.delta_table:
            emoji = {"faster": "✅", "slower": "🔴", "same": "➖"}.get(r.direction, "")
            lines.append(
                f"| {r.stage_name} | {r.before_p95_ms} | {r.after_p95_ms} | {r.delta_pct:+.1f}% | {emoji} {r.direction} |"
            )
        return "\n".join(lines)


class AutoprofExperiment:
    def __init__(self, baseline_path: str | Path | None = None, threshold_pct: float = 5.0):
        self._baseline_path = baseline_path
        self._threshold_pct = threshold_pct
        self._current_profile: dict[str, Any] = {}
        self._baseline_profile: dict[str, Any] = {}

    def measure(self, pipeline_fn: Callable[[], Any], boards: list[str] | None = None) -> None:
        from temper_placer.profiling.instrumentation import PipelineProfiler

        profiler = PipelineProfiler()
        profiler.start()
        try:
            pipeline_fn()
        finally:
            profiler.stop()
        self._current_profile = profiler.report.to_dict()
        if boards:
            self._current_profile["boards"] = boards

    def load_baseline(self, path: str | Path) -> None:
        with open(path) as f:
            self._baseline_profile = json.load(f)

    def compare(self) -> AutoprofReport:
        current_stages = self._current_profile.get("stages", {})
        baseline_stages = self._baseline_profile.get("stages", {})

        all_stages = sorted(set(current_stages) | set(baseline_stages))

        delta_rows = []
        for name in all_stages:
            before = baseline_stages.get(name, {}).get("wall_time_ms", 0.0)
            after = current_stages.get(name, {}).get("wall_time_ms", 0.0)
            delta_rows.append(DeltaRow.from_timings(name, before, after, self._threshold_pct))

        bottleneck = ""
        if delta_rows:
            bottleneck = delta_rows[0].stage_name

        total_before = self._baseline_profile.get("total_wall_time_ms", 0.0)
        total_after = self._current_profile.get("total_wall_time_ms", 0.0)
        boards = len(self._current_profile.get("boards", []))

        return AutoprofReport(
            delta_table=delta_rows,
            bottleneck_stage=bottleneck,
            total_before_ms=total_before,
            total_after_ms=total_after,
            boards_tested=max(boards, 1),
        )

    def save_baseline(self, path: str | Path) -> None:
        with open(path, "w") as f:
            json.dump(self._current_profile, f, indent=2)

    def append_to_measurements(self, path: str | Path) -> None:
        from temper_placer.regression.metrics_recorder import (
            PipelineMetricsRecord,
            record_metrics,
        )

        report = self.compare()
        metrics: dict[str, float] = {}
        for row in report.delta_table:
            metrics[f"{row.stage_name}_before_p95_ms"] = row.before_p95_ms
            metrics[f"{row.stage_name}_after_p95_ms"] = row.after_p95_ms
            metrics[f"{row.stage_name}_delta_pct"] = row.delta_pct
        metrics["total_before_ms"] = report.total_before_ms
        metrics["total_after_ms"] = report.total_after_ms
        metrics["boards_tested"] = float(report.boards_tested)

        rec = PipelineMetricsRecord(
            board="all",
            stage=report.bottleneck_stage,
            module="autoprof",
            metrics=metrics,
        )
        record_metrics(rec, Path(path))
