"""Stub for the ``temper_orchestration`` extension (temper-orchestration
crate, Wave-4 Phase-5 cli/adapters/temper-workflow slice).

Mirrors the temper_design_bundle_python stub convention: the pyo3 extension
is imported by the delegation shims (``temper_placer.cli.timing``,
``temper_placer.cli.trace_commands``,
``temper_workflow.routing.route_and_measure``); the mypy gate resolves this
stub through ``mypy_path = "packages/temper-placer/stubs"``.
"""

from __future__ import annotations

from typing import Any


def compare_stage(
    baseline_ms: float, current_ms: float, margin: float, floor_ms: float
) -> tuple[float, float, float, float, bool]:
    """The timing_check stage-comparison block: (delta_ms, delta_pct,
    effective_baseline, threshold_ms, passed)."""


def p95(values: list[float]) -> float:
    """round(sorted(values)[int(len(values) * 0.95)], 3) — raises
    IndexError on an empty list."""


def filter_decisions(decisions: Any, subject: Any) -> list[int]:
    """Original indices of the decisions whose d.get("subject") == subject."""


def find_rejected_alternative(
    decisions: Any, subject: Any, value: Any
) -> tuple[int, int] | None:
    """(decision_index, alternative_index) of the first match, or None."""


def measure_copper_length(
    traces: list[tuple[str | None, float, float, float, float]],
) -> tuple[float, list[tuple[str, float]]]:
    """(total_wirelength_mm, [(net, length), ...]) in first-seen net order."""
