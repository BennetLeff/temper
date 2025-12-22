"""
Composite quality score for placement evaluation.

Combines multiple metrics into a single 0-100 score for easy comparison
of different placements.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from temper_placer.routing.verifier import VerificationResult
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
    hpwl_target_mm: Optional[float] = None
    
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
    """

    overall: float
    placement_score: float
    drc_score: float
    routing_score: float | None
    interpretation: str
    pass_quality: bool

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "overall": self.overall,
            "placement_score": self.placement_score,
            "drc_score": self.drc_score,
            "routing_score": self.routing_score,
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
    - Routing: 20% (completion rate, wirelength ratio)

    Args:
        placement_metrics: Computed placement metrics.
        drc_result: DRC result from kicad-cli.
        routing_result: Optional routing verification result.

    Returns:
        QualityScore with overall score and interpretation.
    """
    # Compute placement score (0-100)
    placement_score = _compute_placement_score(placement_metrics)

    # Compute DRC score (0-100)
    drc_score = _compute_drc_score(drc_result)

    # Compute routing score if available (0-100)
    routing_score = None
    if routing_result is not None:
        routing_score = _compute_routing_score(routing_result, placement_metrics)

    # Compute overall weighted score
    if routing_score is None:
        # No routing: 50/50 placement/DRC
        overall = 0.5 * placement_score + 0.5 * drc_score
    else:
        # With routing: 40/40/20 placement/DRC/routing
        overall = 0.4 * placement_score + 0.4 * drc_score + 0.2 * routing_score

    # Determine interpretation
    interpretation = interpret_score(overall)
    pass_quality = overall >= 60

    return QualityScore(
        overall=overall,
        placement_score=placement_score,
        drc_score=drc_score,
        routing_score=routing_score,
        interpretation=interpretation,
        pass_quality=pass_quality,
    )


def _compute_placement_score(metrics: PlacementMetrics) -> float:
    """
    Compute placement quality score (0-100).
    """
    score = 100.0

    # Critical violations (block routing or violate safety)
    score -= metrics.overlap_count * 20
    score -= metrics.boundary_violations * 15
    score -= metrics.hv_lv_violations * 25
    score -= metrics.keepout_violations * 10

    # Medium violations (sub-optimal but not critical)
    score -= (metrics.clearance_violations - metrics.hv_lv_violations) * 5
    score -= metrics.zone_violations * 10

    # Wirelength penalty
    if metrics.total_wirelength > 0:
        # Assume avg net length > 50mm is problematic
        avg_len = metrics.total_wirelength / max(1, metrics.overlap_count + 1) # This was avg_net_length
        # Wait, metrics has avg_net_length?
        avg_len = getattr(metrics, "avg_net_length", 0.0)
        if avg_len > 50:
            score -= min(10, (avg_len - 50) / 10)

    return max(0.0, min(100.0, score))


def _compute_drc_score(drc_result: DrcResult) -> float:
    """
    Compute DRC quality score (0-100).
    """
    score = 100.0
    score -= drc_result.error_count * 15
    score -= drc_result.warning_count * 3
    return max(0.0, min(100.0, score))


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
    """Human-readable interpretation."""
    if score >= 90:
        return "excellent"
    elif score >= 80:
        return "good"
    elif score >= 60:
        return "ok"
    else:
        return "poor"
