"""
Routing quality evaluation for Temper PCB designs.

Computes metrics to assess the quality of a routed board, including
completion rate, via usage, wirelength, and DRC compliance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import temper_quality_oracle as _tqo

if TYPE_CHECKING:
    from temper_placer.router_v6.verifier import VerificationResult
    from temper_placer.validation.drc_runner import DrcResult


@dataclass
class RoutingQualityScore:
    """
    Quality score for a routed PCB.

    Attributes:
        completion_rate: Fraction of nets successfully routed (0.0-1.0).
        via_count: Total number of vias used.
        total_length: Total routed wirelength in mm.
        drc_violations: Number of DRC errors found.
        is_acceptable: True if completion >= 0.8 and drc_violations == 0.
        score: Composite score (0-100).
    """

    completion_rate: float
    via_count: int
    total_length: float
    drc_violations: int
    is_acceptable: bool
    score: float

    def to_dict(self) -> dict:
        """Convert to dictionary for reporting."""
        return {
            "completion_rate": self.completion_rate,
            "via_count": self.via_count,
            "total_length": self.total_length,
            "drc_violations": self.drc_violations,
            "is_acceptable": self.is_acceptable,
            "score": self.score,
        }


def evaluate_routing_quality(
    routing_result: VerificationResult,
    drc_result: DrcResult,
) -> RoutingQualityScore:
    """
    Evaluate the quality of a routing solution.

    Threshold for acceptability:
    - completion_rate >= 0.8 (80% of nets routed)
    - drc_violations == 0 (No DRC errors)

    Args:
        routing_result: Result from routing verification.
        drc_result: Result from Design Rule Check.

    Returns:
        RoutingQualityScore with metrics and acceptability status.
    """
    completion = routing_result.completion_rate
    vias = routing_result.total_vias
    length = routing_result.total_wirelength
    drc = drc_result.error_count

    # Acceptability threshold
    is_acceptable = completion >= 0.8 and drc == 0

    # Composite score (0-100), computed in Rust (temper-quality-oracle).
    # 1. Completion: 60% of score
    # 2. DRC: 20% of score (all or nothing for errors)
    # 3. Efficiency: 20% of score (based on via density and wirelength)
    # For Temper, we expect roughly 2 vias per net on average as 'good'
    # and total length related to HPWL (but we use a simple heuristic here)
    net_count = len(routing_result.routed_nets) + len(routing_result.failed_nets)
    score = _tqo.routing_quality_score_py(completion, vias, drc, net_count)

    return RoutingQualityScore(
        completion_rate=completion,
        via_count=vias,
        total_length=length,
        drc_violations=drc,
        is_acceptable=is_acceptable,
        score=float(score),
    )
