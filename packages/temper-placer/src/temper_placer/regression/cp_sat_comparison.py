"""CP-SAT comparison primitives for regression testing.

Extracted from the now-retired parity test harness (U4).  These dataclasses
and functions survive as CP-SAT regression infrastructure — comparing CP-SAT
placements against each other (across solver parameter changes, model revisions,
or board updates), NOT against JAX.

Wave 4 Phase 4 (regression slice): ``compare_metric_dicts`` — the entire
Pareto-style per-metric comparison, the wirelength ratio/tolerance rule, the
``:.2f``/``:.3f``/``:.4f`` detail strings and the summary line — moved to
``temper_design_bundle_python.compare_metric_dicts``
(packages/temper-design-bundle/src/cp_sat_comparison.rs). The dataclasses
(``MetricComparison``, ``ParityComparisonResult``) stay Python as the public
API; this module is now a delegation shim. Design boundaries are argued in
``packages/temper-design-bundle/VERIFICATION.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_TDB = None


def _tdb():
    global _TDB
    if _TDB is None:
        import temper_design_bundle_python  # type: ignore[import-untyped]

        _TDB = temper_design_bundle_python
    return _TDB


@dataclass
class MetricComparison:
    """Result of comparing a single metric between two placements.

    Attributes:
        name: Metric name (e.g., 'clearance_3mm').
        cp_sat_value: Value from the CP-SAT (or candidate) placement.
        jax_value: Value from the JAX (or baseline) placement.
        passed: True if the comparison condition is satisfied.
        detail: Human-readable comparison string.
    """

    name: str
    cp_sat_value: float
    jax_value: float
    passed: bool
    detail: str = ""


@dataclass
class ParityComparisonResult:
    """Aggregated result of a parity comparison across all metrics.

    Attributes:
        passed: True iff all per-metric comparisons pass.
        comparisons: List of per-metric MetricComparison objects.
        summary: Human-readable summary string.
    """

    passed: bool
    comparisons: list[MetricComparison] = field(default_factory=list)
    summary: str = ""


def compare_metric_dicts(
    candidate_scores: dict[str, Any],
    baseline_scores: dict[str, Any],
    *,
    wirelength_metric: str = "total_manhattan_wirelength",
) -> ParityComparisonResult:
    """Compare two score dicts per-metric and return a structured result.

    Comparison rules (Pareto-style gate):
      - Clearance metrics (clearance_3mm, clearance_6mm): candidate >= baseline
      - thermal_score: candidate >= baseline
      - wirelength (if present): candidate <= baseline (within 5% tolerance)
      - All others: higher-is-better by default

    Args:
        candidate_scores: Score dict from the candidate placer (e.g., CP-SAT).
        baseline_scores: Score dict from the baseline placer (e.g., JAX).
        wirelength_metric: Key in the score dict for wirelength.

    Returns:
        ParityComparisonResult with per-metric breakdown and overall pass/fail.

    Wave 4 Phase 4: the comparison + detail/summary string composition runs
    in ``temper_design_bundle_python.compare_metric_dicts`` (bit-identical,
    pinned by the differential); this wrapper only maps the returned records
    onto the public dataclasses.
    """
    result = _tdb().compare_metric_dicts(
        candidate_scores, baseline_scores, wirelength_metric
    )
    comparisons = [
        MetricComparison(
            name=comp["name"],
            cp_sat_value=comp["cp_sat_value"],
            jax_value=comp["jax_value"],
            passed=comp["passed"],
            detail=comp["detail"],
        )
        for comp in result["comparisons"]
    ]
    return ParityComparisonResult(
        passed=result["passed"],
        comparisons=comparisons,
        summary=result["summary"],
    )
