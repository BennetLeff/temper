"""Aggregate quality score calculation module."""

from dataclasses import dataclass

__all__ = [
    "AggregateScoreResult",
    "calculate_aggregate_score",
]


@dataclass
class AggregateScoreResult:
    """Result of aggregate quality score calculation."""

    total_score: float
    max_score: float
    wirelength_weight: float
    drc_weight: float
    routing_weight: float
    wirelength_score: float
    drc_score: float
    routing_score: float
    verdict: str


# Default weights (from epic specification)
DEFAULT_WIRELENGTH_WEIGHT = 0.3
DEFAULT_DRC_WEIGHT = 0.4
DEFAULT_ROUTING_WEIGHT = 0.3

# Pass threshold
PASS_THRESHOLD = 80.0


def normalize_wirelength_ratio(ratio: float) -> float:
    """
    Normalize wirelength ratio to 0-100 score.

    Lower ratio is better. Conversion:
    - ratio = 1.0 (perfect) → 100.0
    - ratio = 1.1 (10% worse) → 90.9
    - ratio = 0.9 (10% better) → 111.1 (capped at 100)
    - ratio = 2.0 (2x worse) → 50.0

    Args:
        ratio: Wirelength ratio (optimized / reference)

    Returns:
        Normalized score (0.0 to 100.0)
    """
    # Invert ratio and scale to 100
    # ratio < 1.0 = better than reference
    # ratio > 1.0 = worse than reference
    score = (1.0 / ratio) * 100.0

    # Cap at 100.0 (can't be better than perfect)
    return min(100.0, score)


def normalize_routing_completion(completion_rate: float) -> float:
    """
    Normalize routing completion rate to 0-100 score.

    Args:
        completion_rate: Routing completion rate (0.0 to 1.0)

    Returns:
        Normalized score (0.0 to 100.0)
    """
    return completion_rate * 100.0


def normalize_weights(
    wirelength_weight: float | None = None,
    drc_weight: float | None = None,
    routing_weight: float | None = None,
) -> tuple[float, float, float]:
    """
    Normalize weights to sum to 1.0.

    Args:
        wirelength_weight: Wirelength weight (optional)
        drc_weight: DRC weight (optional)
        routing_weight: Routing weight (optional)

    Returns:
        Tuple of (wirelength_weight, drc_weight, routing_weight)
    """
    # Use defaults if not provided
    wl = wirelength_weight if wirelength_weight is not None else DEFAULT_WIRELENGTH_WEIGHT
    drc = drc_weight if drc_weight is not None else DEFAULT_DRC_WEIGHT
    rt = routing_weight if routing_weight is not None else DEFAULT_ROUTING_WEIGHT

    # Normalize to sum to 1.0
    total = wl + drc + rt
    if total == 0:
        # Prevent division by zero - use defaults
        return (DEFAULT_WIRELENGTH_WEIGHT, DEFAULT_DRC_WEIGHT, DEFAULT_ROUTING_WEIGHT)

    return (wl / total, drc / total, rt / total)


def calculate_aggregate_score(
    wirelength_result, drc_result, routing_result, weights: dict | None = None
) -> AggregateScoreResult:
    """
    Calculate aggregate quality score from individual metrics.

    Args:
        wirelength_result: WirelengthResult from wirelength comparison
        drc_result: DRCComplianceResult from DRC check
        routing_result: RoutingFeasibilityResult from routing check
        weights: Optional custom weights dict with keys:
                 'wirelength', 'drc', 'routing'

    Returns:
        AggregateScoreResult with weighted average score
    """
    # Get custom weights or use defaults
    if weights:
        wl_weight = weights.get("wirelength", DEFAULT_WIRELENGTH_WEIGHT)
        drc_weight = weights.get("drc", DEFAULT_DRC_WEIGHT)
        rt_weight = weights.get("routing", DEFAULT_ROUTING_WEIGHT)
    else:
        wl_weight = DEFAULT_WIRELENGTH_WEIGHT
        drc_weight = DEFAULT_DRC_WEIGHT
        rt_weight = DEFAULT_ROUTING_WEIGHT

    # Normalize weights
    wl_weight, drc_weight, rt_weight = normalize_weights(wl_weight, drc_weight, rt_weight)

    # Normalize individual scores to 0-100 range
    wl_score = normalize_wirelength_ratio(wirelength_result.ratio)
    drc_score = drc_result.score
    rt_score = normalize_routing_completion(routing_result.completion_rate)

    # Calculate weighted average
    total_score = (wl_score * wl_weight) + (drc_score * drc_weight) + (rt_score * rt_weight)

    # Determine verdict
    verdict = "PASS" if total_score >= PASS_THRESHOLD else "FAIL"

    return AggregateScoreResult(
        total_score=total_score,
        max_score=100.0,
        wirelength_weight=wl_weight,
        drc_weight=drc_weight,
        routing_weight=rt_weight,
        wirelength_score=wl_score,
        drc_score=drc_score,
        routing_score=rt_score,
        verdict=verdict,
    )
