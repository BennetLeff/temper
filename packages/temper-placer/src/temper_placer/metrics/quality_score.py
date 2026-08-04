"""
Composite quality score for placement evaluation.

Combines multiple metrics into a single 0-100 score for easy comparison
of different placements.

The scoring arithmetic runs in the ``temper-quality-oracle`` Rust kernels
(``placement_score_py`` / ``drc_score_py`` / ``overall_score_py`` /
``interpret_score_py``, Wave 4 Phase A #5); this module keeps the public
API, the dataclasses, and the input plumbing.
"""

from __future__ import annotations

from dataclasses import dataclass

import temper_quality_oracle as _tqo

from temper_placer.metrics.routing_quality import RoutingQualityScore, evaluate_routing_quality
from temper_placer.router_v6.verifier import VerificationResult
from temper_placer.validation.drc_runner import DrcResult
from temper_placer.validation.metrics import PlacementMetrics


@dataclass
class QualityInputs:
    """Inputs for quality score computation."""

    # Hard constraints (binary)
    drc_violations: int = 0
    overlap_loss: float = 0.0
    boundary_loss: float = 0.0

    # Routing (optional)
    routing_completion_pct: float = 100.0

    # Efficiency
    hpwl_mm: float = 0.0
    hpwl_target_mm: float | None = None

    # Safety/compliance
    hv_clearance_ok: bool = True
    thermal_compliance: bool = True
    zone_compliance_pct: float = 100.0


@dataclass
class QualityScore:
    """
    Composite quality score for a placement.

    Attributes:
        overall: Overall score (0-100).
        placement_score: Placement quality subscore (0-100).
        drc_score: DRC subscore (0-100).
        routing_score: Routing quality subscore (0-100), or None if not routed.
        interpretation: Human-readable interpretation ('poor', 'ok', 'good', 'excellent').
        pass_quality: True if score >= 60 (minimum acceptable).
        routing_quality: Detailed routing quality metrics, or None if not routed.
    """

    overall: float
    placement_score: float
    drc_score: float
    routing_score: float | None
    interpretation: str
    pass_quality: bool
    routing_quality: RoutingQualityScore | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "overall": self.overall,
            "placement_score": self.placement_score,
            "drc_score": self.drc_score,
            "routing_score": self.routing_score,
            "routing_quality": self.routing_quality.to_dict() if self.routing_quality else None,
            "interpretation": self.interpretation,
            "pass_quality": self.pass_quality,
        }


def compute_quality_score(
    placement_metrics: PlacementMetrics,
    drc_result: DrcResult,
    routing_result: VerificationResult | None = None,
) -> QualityScore:
    """
    Compute composite quality score from placement, DRC, and routing metrics.

    Scoring breakdown (without routing):
    - Placement: 50% (overlap, boundary, clearance, wirelength)
    - DRC: 50% (errors, warnings)

    Scoring breakdown (with routing):
    - Placement: 40%
    - DRC: 40%
    - Routing: 20% (completion rate, via count, drc)

    Args:
        placement_metrics: Computed placement metrics.
        drc_result: DRC result from kicad-cli.
        routing_result: Optional routing verification result.

    Returns:
        QualityScore with overall score and interpretation.
    """
    # Compute placement score (0-100) — Rust kernel (temper-quality-oracle)
    placement_score = _tqo.placement_score_py(
        placement_metrics.overlap_count,
        placement_metrics.boundary_violations,
        placement_metrics.hv_lv_violations,
        placement_metrics.keepout_violations,
        placement_metrics.clearance_violations,
        placement_metrics.zone_violations,
        placement_metrics.total_wirelength,
        getattr(placement_metrics, "avg_net_length", 0.0),
    )

    # Compute DRC score (0-100) — Rust kernel (temper-quality-oracle)
    drc_score = _tqo.drc_score_py(drc_result.error_count, drc_result.warning_count)

    # Compute routing score if available (0-100)
    routing_score = None
    routing_quality = None
    if routing_result is not None:
        routing_quality = evaluate_routing_quality(routing_result, drc_result)
        routing_score = routing_quality.score

    # Compute overall weighted score — Rust kernel (temper-quality-oracle)
    overall = _tqo.overall_score_py(placement_score, drc_score, routing_score)

    # Determine interpretation — Rust kernel (temper-quality-oracle)
    interpretation = _tqo.interpret_score_py(overall)
    pass_quality = overall >= 60

    return QualityScore(
        overall=overall,
        placement_score=placement_score,
        drc_score=drc_score,
        routing_score=routing_score,
        routing_quality=routing_quality,
        interpretation=interpretation,
        pass_quality=pass_quality,
    )


def _compute_placement_score(metrics: PlacementMetrics) -> float:
    """
    Compute placement quality score (0-100) — Rust kernel.
    """
    return _tqo.placement_score_py(
        metrics.overlap_count,
        metrics.boundary_violations,
        metrics.hv_lv_violations,
        metrics.keepout_violations,
        metrics.clearance_violations,
        metrics.zone_violations,
        metrics.total_wirelength,
        getattr(metrics, "avg_net_length", 0.0),
    )


def _compute_drc_score(drc_result: DrcResult) -> float:
    """
    Compute DRC quality score (0-100) — Rust kernel.
    """
    return _tqo.drc_score_py(drc_result.error_count, drc_result.warning_count)


def _compute_routing_score(
    result: VerificationResult, placement_metrics: PlacementMetrics
) -> float:
    """
    Compute routing quality score (0-100).
    """
    score = 0.0
    # Completion rate: 70 points max
    score += result.completion_rate * 70

    # Wirelength ratio: 20 points max
    if result.total_wirelength > 0 and placement_metrics.total_wirelength > 0:
        wl_ratio = result.total_wirelength / placement_metrics.total_wirelength
        wl_ratio = max(1.0, min(2.0, wl_ratio))
        wl_score = 20 * (2.0 - wl_ratio)
        score += wl_score

    # Via count: 10 points max
    if result.total_vias <= 50:
        via_score = 10 * (1.0 - result.total_vias / 50)
        score += via_score

    return max(0.0, min(100.0, score))


def interpret_score(score: float) -> str:
    """Human-readable interpretation — Rust kernel."""
    return _tqo.interpret_score_py(score)
