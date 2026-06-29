"""Routing feasibility detection module."""

from dataclasses import dataclass

__all__ = [
    "RoutingResult",
    "RoutingFeasibilityResult",
    "calculate_routing_completion",
    "get_routing_verdict",
    "evaluate_routing_feasibility",
]


@dataclass
class RoutingResult:
    """Result of routing a single net."""

    net_name: str
    success: bool
    wirelength: float | None = None
    via_count: int = 0


@dataclass
class RoutingFeasibilityResult:
    """Result of routing feasibility evaluation."""

    total_nets: int
    routed_nets: int
    failed_nets: int
    completion_rate: float
    average_wirelength: float
    total_vias: int
    verdict: str


# Verdict threshold
COMPLETION_THRESHOLD = 0.95  # 95%


def calculate_routing_completion(nets: list, attempts: list[RoutingResult]) -> float:
    """
    Calculate routing completion rate.

    Args:
        nets: List of Net objects
        attempts: List of RoutingResult for each net attempt

    Returns:
        Completion rate (0.0 to 1.0), where 1.0 = 100%
    """
    if not nets:
        # No nets = 100% complete
        return 1.0

    total_nets = len(nets)

    # Create lookup dict for attempts by net name
    attempts_by_net = {attempt.net_name: attempt for attempt in attempts}

    routed_count = 0
    for net in nets:
        attempt = attempts_by_net.get(net.name)
        if attempt and attempt.success:
            routed_count += 1

    return routed_count / total_nets


def get_routing_verdict(completion_rate: float) -> str:
    """
    Get routing verdict from completion rate.

    Args:
        completion_rate: Routing completion rate (0.0 to 1.0)

    Returns:
        "PASS" if completion >= 95%, "FAIL" otherwise
    """
    return "PASS" if completion_rate >= COMPLETION_THRESHOLD else "FAIL"


def evaluate_routing_feasibility(
    nets: list, attempts: list[RoutingResult]
) -> RoutingFeasibilityResult:
    """
    Evaluate routing feasibility and generate result.

    Args:
        nets: List of Net objects
        attempts: List of RoutingResult for each net attempt

    Returns:
        RoutingFeasibilityResult with completion, wirelength, vias, verdict
    """
    total_nets = len(nets)

    if not nets:
        # Empty case - treat as perfect
        return RoutingFeasibilityResult(
            total_nets=0,
            routed_nets=0,
            failed_nets=0,
            completion_rate=1.0,
            average_wirelength=0.0,
            total_vias=0,
            verdict="PASS",
        )

    # Create lookup dict for attempts by net name
    attempts_by_net = {attempt.net_name: attempt for attempt in attempts}

    routed_count = 0
    failed_count = 0
    total_wirelength = 0.0
    total_vias = 0

    for net in nets:
        attempt = attempts_by_net.get(net.name)

        if attempt:
            if attempt.success:
                routed_count += 1
                if attempt.wirelength is not None:
                    total_wirelength += attempt.wirelength
                total_vias += attempt.via_count
            else:
                failed_count += 1
        else:
            # No attempt = counted as failed
            failed_count += 1

    # Calculate completion rate
    completion_rate = routed_count / total_nets if total_nets > 0 else 1.0

    # Calculate average wirelength (only for routed nets)
    average_wirelength = total_wirelength / routed_count if routed_count > 0 else 0.0

    # Get verdict
    verdict = get_routing_verdict(completion_rate)

    return RoutingFeasibilityResult(
        total_nets=total_nets,
        routed_nets=routed_count,
        failed_nets=failed_count,
        completion_rate=completion_rate,
        average_wirelength=average_wirelength,
        total_vias=total_vias,
        verdict=verdict,
    )
