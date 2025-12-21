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
    hv_lv_clearance_score,
    loop_area_score,
    thermal_score,
    total_wirelength,
    zone_compliance_score,
)
<<<<<<< HEAD
from temper_placer.metrics.quality_score import QualityScore, compute_quality_score
=======
from temper_placer.metrics.quality_score import QualityInputs, compute_quality_score, interpret_score
>>>>>>> 2d319f0 (feat(placer): NSGA-II, Crawler, NetCentroidLoss, and structural refinements)

__all__ = [
    "total_wirelength",
    "thermal_score",
    "zone_compliance_score",
    "hv_lv_clearance_score",
    "loop_area_score",
    "congestion_score",
    "compactness_score",
    "connectivity_clustering_score",
    "compute_quality_report",
<<<<<<< HEAD
    "QualityScore",
    "compute_quality_score",
=======
    "QualityInputs",
    "compute_quality_score",
    "interpret_score",
>>>>>>> 2d319f0 (feat(placer): NSGA-II, Crawler, NetCentroidLoss, and structural refinements)
]
