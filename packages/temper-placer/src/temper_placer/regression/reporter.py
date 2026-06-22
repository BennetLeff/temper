"""Regression reporter — produces per-board pass/fail summary."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MetricDelta:
    """A single metric comparison result."""

    name: str
    baseline: float
    current: float
    delta: float
    regression: bool = False

    @property
    def delta_display(self) -> str:
        sign = "+" if self.delta > 0 else ""
        return f"{sign}{self.delta}"

    def message(self) -> str:
        return f"{self.name}: {self.current} vs baseline {self.baseline} ({self.delta_display})"


@dataclass
class BoardResult:
    """Result for a single board."""

    board_id: str
    passed: bool
    metrics: dict[str, Any] = field(default_factory=dict)
    baseline_metrics: dict[str, Any] = field(default_factory=dict)
    deltas: list[MetricDelta] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""


@dataclass
class RegressionReporter:
    """Collects and reports regression results."""

    results: list[BoardResult] = field(default_factory=list)

    def add_result(self, result: BoardResult) -> None:
        self.results.append(result)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.passed and not r.skipped)

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.skipped)

    @property
    def has_failures(self) -> bool:
        return self.failed > 0

    def summary(self) -> str:
        lines = ["=== Regression Suite Results ==="]
        lines.append(f"Total: {self.total}, Passed: {self.passed}, Failed: {self.failed}, Skipped: {self.skipped}")
        lines.append("")

        for result in self.results:
            status = "SKIP" if result.skipped else ("PASS" if result.passed else "FAIL")
            lines.append(f"  [{status}] {result.board_id}")

            if result.skipped and result.skip_reason:
                lines.append(f"         Reason: {result.skip_reason}")

            for delta in result.deltas:
                if delta.regression:
                    lines.append(f"         REGRESSION: {delta.message()}")

            for warning in result.warnings:
                lines.append(f"         WARNING: {warning}")

            for error in result.errors:
                lines.append(f"         ERROR: {error}")

        return "\n".join(lines)
