"""DRC-Loss Correlation Analysis.

This module analyzes the correlation between optimizer loss components
and KiCad DRC violations to inform weight selection.
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Sequence
import math
import statistics


@dataclass
class PlacementResult:
    """Metrics for a single placement."""

    quality_level: str
    overlap_loss: float
    boundary_loss: float
    wirelength_loss: float
    total_loss: float


@dataclass
class DRCResult:
    """DRC violation counts by type."""

    courtyards_overlap: int
    edge_clearance: int
    pad_clearance: int
    total_errors: int


@dataclass
class CorrelationReport:
    """Results of correlation analysis."""

    correlations: List[Dict[str, Any]]
    recommendations: Dict[str, float]


def analyze_drc_correlation(
    placements: List[PlacementResult],
    drc_results: List[DRCResult],
) -> CorrelationReport:
    """
    Analyze correlation between loss components and DRC violations.

    Args:
        placements: List of placement results with loss metrics
        drc_results: List of DRC results with violation counts

    Returns:
        CorrelationReport with correlations and weight recommendations
    """
    if not placements or not drc_results or len(placements) != len(drc_results):
        return CorrelationReport(
            correlations=[],
            recommendations={
                "overlap": 100.0,
                "boundary": 50.0,
                "wirelength": 10.0,
            },
        )

    # Extract data for correlation analysis
    overlap_losses = [p.overlap_loss for p in placements]
    boundary_losses = [p.boundary_loss for p in placements]
    wirelength_losses = [p.wirelength_loss for p in placements]

    courtyard_overlaps = [float(d.courtyards_overlap) for d in drc_results]
    edge_clearances = [float(d.edge_clearance) for d in drc_results]
    pad_clearances = [float(d.pad_clearance) for d in drc_results]

    correlations = []

    # Always compute correlations (even with insufficient data for meaningful stats)
    # Overlap loss vs courtyards overlap
    overlap_corr = compute_correlation(overlap_losses, courtyard_overlaps)
    correlations.append(
        {
            "loss_component": "overlap_loss",
            "pearson_r": overlap_corr["pearson"],
            "spearman_rho": overlap_corr["spearman"],
            "p_value": overlap_corr["p_value"],
            "drc_type": "courtyards_overlap",
        }
    )

    # Boundary loss vs edge clearance
    boundary_corr = compute_correlation(boundary_losses, edge_clearances)
    correlations.append(
        {
            "loss_component": "boundary_loss",
            "pearson_r": boundary_corr["pearson"],
            "spearman_rho": boundary_corr["spearman"],
            "p_value": boundary_corr["p_value"],
            "drc_type": "edge_clearance",
        }
    )

    # Wirelength loss vs total errors (weak correlation expected)
    total_errors = [float(d.total_errors) for d in drc_results]
    wirelength_corr = compute_correlation(wirelength_losses, total_errors)
    correlations.append(
        {
            "loss_component": "wirelength_loss",
            "pearson_r": wirelength_corr["pearson"],
            "spearman_rho": wirelength_corr["spearman"],
            "p_value": wirelength_corr["p_value"],
            "drc_type": "total_errors",
        }
    )

    # Generate weight recommendations based on correlation strength
    recommendations = generate_recommendations(correlations)

    return CorrelationReport(correlations=correlations, recommendations=recommendations)


def compute_correlation(x: Sequence[float], y: Sequence[float]) -> Dict[str, float]:
    """
    Compute Pearson and Spearman correlation coefficients.

    Args:
        x: First variable
        y: Second variable

    Returns:
        Dict with 'pearson', 'spearman', and 'p_value' keys
    """
    if len(x) != len(y) or len(x) < 2:
        return {"pearson": float("nan"), "spearman": float("nan"), "p_value": 1.0}

    n = len(x)

    # Pearson correlation
    mean_x = statistics.mean(x)
    mean_y = statistics.mean(y)

    numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
    sum_sq_x = sum((x[i] - mean_x) ** 2 for i in range(n))
    sum_sq_y = sum((y[i] - mean_y) ** 2 for i in range(n))

    if sum_sq_x == 0 or sum_sq_y == 0:
        pearson = 0.0
    else:
        pearson = numerator / math.sqrt(sum_sq_x * sum_sq_y)

    # Spearman correlation (rank-based) - avoid recursion
    spearman = compute_spearman_non_recursive(x, y)

    # Simple p-value approximation (not statistically rigorous)
    if n >= 3 and not math.isnan(pearson):
        # t-statistic for correlation
        t_stat = (
            pearson * math.sqrt((n - 2) / (1 - pearson**2)) if abs(pearson) < 1 else float("inf")
        )
        # Rough p-value approximation
        p_value = 2 * (1 - 0.95) if abs(t_stat) > 2 else 0.5
    else:
        p_value = 1.0

    return {
        "pearson": pearson,
        "spearman": spearman,
        "p_value": p_value,
    }


def compute_spearman_non_recursive(x: Sequence[float], y: Sequence[float]) -> float:
    """Compute Spearman rank correlation coefficient without recursion."""
    if len(x) != len(y) or len(x) < 2:
        return float("nan")

    # Convert to ranks
    x_ranks = rank_data(x)
    y_ranks = rank_data(y)

    # Compute Pearson correlation on ranks manually to avoid recursion
    n = len(x_ranks)
    mean_x = statistics.mean(x_ranks)
    mean_y = statistics.mean(y_ranks)

    numerator = sum((x_ranks[i] - mean_x) * (y_ranks[i] - mean_y) for i in range(n))
    sum_sq_x = sum((x_ranks[i] - mean_x) ** 2 for i in range(n))
    sum_sq_y = sum((y_ranks[i] - mean_y) ** 2 for i in range(n))

    if sum_sq_x == 0 or sum_sq_y == 0:
        return 0.0
    else:
        return numerator / math.sqrt(sum_sq_x * sum_sq_y)


def compute_spearman(x: Sequence[float], y: Sequence[float]) -> float:
    """Compute Spearman rank correlation coefficient."""
    return compute_spearman_non_recursive(x, y)


def rank_data(data: Sequence[float]) -> List[float]:
    """Convert data to ranks (average ranks for ties)."""
    # Create (value, original_index) pairs
    indexed_data = [(value, i) for i, value in enumerate(data)]
    # Sort by value
    indexed_data.sort(key=lambda x: x[0])

    # Assign ranks
    ranks = [0.0] * len(data)
    for rank, (value, original_index) in enumerate(indexed_data, 1):
        ranks[original_index] = float(rank)

    return ranks


def generate_recommendations(correlations: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    Generate weight recommendations based on correlation analysis.

    Args:
        correlations: List of correlation results

    Returns:
        Dict mapping loss component names to recommended weights
    """
    recommendations = {}

    # Base weights
    base_weights = {
        "overlap": 100.0,
        "boundary": 50.0,
        "wirelength": 10.0,
    }

    # Find strongest correlation for each loss type
    for loss_type in ["overlap", "boundary", "wirelength"]:
        loss_name = f"{loss_type}_loss"
        correlation = next((c for c in correlations if c["loss_component"] == loss_name), None)

        if correlation and not math.isnan(correlation["pearson_r"]):
            # Scale weight based on correlation strength
            correlation_strength = abs(correlation["pearson_r"])
            base_weight = base_weights[loss_type]

            # Scale between 0.5x and 2x base weight
            scale_factor = 0.5 + (correlation_strength * 1.5)
            recommendations[loss_type] = base_weight * scale_factor
        else:
            # Use base weight if no correlation data
            recommendations[loss_type] = base_weights[loss_type]

    return recommendations
