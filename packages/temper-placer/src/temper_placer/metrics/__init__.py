"""
Quality metrics for placement comparison.

This module provides metrics to evaluate and compare placement quality.
All metrics return normalized scores in [0, 1] where higher is better
(except wirelength which returns raw mm value).
"""

from temper_placer.metrics.quality import (
    compactness_score,
    compute_quality_report,
    congestion_score,
    connectivity_clustering_score,
    dual_rail_clearance_report,
    hv_lv_clearance_score,
    loop_area_score,
    thermal_score,
    total_wirelength,
    zone_compliance_score,
)
from temper_placer.metrics.external_oracle import (
    score_placement,
)
from temper_placer.metrics.quality_score import (
    QualityInputs,
    compute_quality_score,
    interpret_score,
)
from temper_placer.metrics.routing_quality import (
    RoutingQualityScore,
    evaluate_routing_quality,
)

__all__ = [
    "total_wirelength",
    "thermal_score",
    "zone_compliance_score",
    "dual_rail_clearance_report",
    "hv_lv_clearance_score",
    "loop_area_score",
    "congestion_score",
    "compactness_score",
    "connectivity_clustering_score",
    "compute_quality_report",
    "score_placement",
    "QualityInputs",
    "compute_quality_score",
    "interpret_score",
    "RoutingQualityScore",
    "evaluate_routing_quality",
]
