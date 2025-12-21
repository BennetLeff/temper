<<<<<<< HEAD
"""
Composite quality score for placement evaluation.

Combines multiple metrics into a single 0-100 score for easy comparison
of different placements.
"""

from __future__ import annotations

from dataclasses import dataclass

from temper_placer.routing.verifier import VerificationResult
from temper_placer.validation.drc_runner import DrcResult
from temper_placer.validation.metrics import PlacementMetrics


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
    if overall >= 90:
        interpretation = "excellent"
    elif overall >= 80:
        interpretation = "good"
    elif overall >= 60:
        interpretation = "ok"
    else:
        interpretation = "poor"

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

    Deductions:
    - Overlaps: -20 per overlap (severe)
    - Boundary violations: -15 per violation (severe)
    - HV-LV clearance violations: -25 per violation (critical)
    - Other clearance violations: -5 per violation
    - Zone violations: -10 per violation
    - Keepout violations: -10 per violation
    - Wirelength penalty: deduct for excessive wirelength (relative to ideal)

    Score is clamped to [0, 100].
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

    # Wirelength penalty (less critical, aesthetic)
    # Assume wirelength > 2x ideal is problematic
    # For simplicity, just penalize if avg net length > 50mm
    if metrics.avg_net_length > 50:
        score -= min(10, (metrics.avg_net_length - 50) / 10)

    return max(0.0, min(100.0, score))


def _compute_drc_score(drc_result: DrcResult) -> float:
    """
    Compute DRC quality score (0-100).

    Deductions:
    - DRC errors: -15 per error (must fix)
    - DRC warnings: -3 per warning (should fix)

    Score is clamped to [0, 100].
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

    Based on:
    - Completion rate (most important): 0-70 points
    - Wirelength ratio (routed / HPWL): 0-20 points
    - Via count (fewer is better): 0-10 points

    Args:
        result: Routing verification result.
        placement_metrics: Placement metrics (for HPWL baseline).

    Returns:
        Routing score (0-100).
    """
    score = 0.0

    # Completion rate: 70 points max
    # 100% completion = 70 points, linear scaling
    score += result.completion_rate * 70

    # Wirelength ratio: 20 points max
    # Ratio of 1.0 (optimal) = 20 points, degrades linearly
    # Ratio > 2.0 = 0 points
    if result.total_wirelength > 0 and placement_metrics.total_wirelength > 0:
        wl_ratio = result.total_wirelength / placement_metrics.total_wirelength
        # Clamp ratio to [1.0, 2.0]
        wl_ratio = max(1.0, min(2.0, wl_ratio))
        # Score: 20 points at 1.0, 0 points at 2.0
        wl_score = 20 * (2.0 - wl_ratio)
        score += wl_score

    # Via count: 10 points max
    # Fewer vias = better (estimate: 0 vias = 10 points, 100 vias = 0 points)
    if result.total_vias <= 50:
        via_score = 10 * (1.0 - result.total_vias / 50)
        score += via_score

    return max(0.0, min(100.0, score))
=======
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

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
    hpwl_target_mm: Optional[float] = None  # If None, skip this component
    
    # Safety/compliance
    hv_clearance_ok: bool = True
    thermal_compliance: bool = True
    zone_compliance_pct: float = 100.0


def compute_quality_score(inputs: QualityInputs) -> float:
    """
    Compute composite placement quality score (0-100).
    
    Weight breakdown:
    - 40 pts: DRC pass (hard gate - 0 if any violations)
    - 20 pts: Routing completion percentage
    - 15 pts: Wirelength efficiency (HPWL vs target)
    - 10 pts: HV clearance compliance
    - 10 pts: Thermal compliance  
    - 5 pts: Zone compliance percentage
    
    Returns:
        Score from 0-100. 
        Interpretation: 0-60=poor, 60-80=acceptable, 80+=good
    """
    score = 0.0
    
    # Hard gate: DRC must pass
    if inputs.drc_violations == 0 and inputs.overlap_loss < 1.0 and inputs.boundary_loss < 1.0:
        score += 40.0
    
    # Routing completion
    score += 20.0 * (inputs.routing_completion_pct / 100.0)
    
    # Wirelength efficiency
    if inputs.hpwl_target_mm and inputs.hpwl_mm > 0:
        efficiency = min(1.0, inputs.hpwl_target_mm / inputs.hpwl_mm)
        score += 15.0 * efficiency
    else:
        score += 15.0  # Full points if not measuring
    
    # Safety compliance
    score += 10.0 if inputs.hv_clearance_ok else 0.0
    score += 10.0 if inputs.thermal_compliance else 0.0
    
    # Zone compliance
    score += 5.0 * (inputs.zone_compliance_pct / 100.0)
    
    return score


def interpret_score(score: float) -> str:
    """Human-readable interpretation."""
    if score >= 80:
        return "good"
    elif score >= 60:
        return "acceptable"
    else:
        return "poor"
>>>>>>> 2d319f0 (feat(placer): NSGA-II, Crawler, NetCentroidLoss, and structural refinements)
