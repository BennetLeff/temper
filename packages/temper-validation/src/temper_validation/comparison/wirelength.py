from dataclasses import dataclass

__all__ = ["manhattan_wirelength", "steiner_wirelength", "compare_wirelength", "WirelengthResult"]


@dataclass
class WirelengthResult:
    """Result of wirelength comparison."""

    optimized: float
    reference: float
    ratio: float
    margin: float
    verdict: str


def manhattan_wirelength(placement, net):
    """
    Calculate Manhattan wirelength for a net.

    Args:
        placement: Placement object with components and their pins
        net: Net object with list of pins to connect

    Returns:
        Total Manhattan wirelength: sum of dx + dy for all pin pairs
    """
    # Build pin position lookup from placement
    pin_positions = {}
    for component in placement.components:
        for pin in component.pins:
            pin_positions[pin.name] = (pin.position.x, pin.position.y)

    # Get positions for pins in the net
    pins = [pin_positions[pin.name] for pin in net.pins]

    total = 0
    for i in range(len(pins)):
        for j in range(i + 1, len(pins)):
            dx = abs(pins[i][0] - pins[j][0])
            dy = abs(pins[i][1] - pins[j][1])
            total += dx + dy
    return total


def steiner_wirelength(placement, net):
    """
    Calculate Steiner tree wirelength approximation using MST.

    Args:
        placement: Placement object with components and their pins
        net: Net object with list of pins to connect

    Returns:
        Approximate Steiner wirelength: MST length using Manhattan distances
    """
    # Build pin position lookup from placement
    pin_positions = {}
    for component in placement.components:
        for pin in component.pins:
            pin_positions[pin.name] = (pin.position.x, pin.position.y)

    # Get positions for pins in the net
    pins = [pin_positions[pin.name] for pin in net.pins]
    n = len(pins)

    if n <= 1:
        return 0

    # Build adjacency matrix with Manhattan distances
    distances = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            dx = abs(pins[i][0] - pins[j][0])
            dy = abs(pins[i][1] - pins[j][1])
            dist = dx + dy
            distances[i][j] = dist
            distances[j][i] = dist

    # Prim's algorithm for MST
    visited = [False] * n
    min_dist = [float("inf")] * n
    min_dist[0] = 0
    total = 0

    for _ in range(n):
        u = -1
        for i in range(n):
            if not visited[i] and (u == -1 or min_dist[i] < min_dist[u]):
                u = i
        visited[u] = True
        total += min_dist[u]
        for v in range(n):
            if not visited[v] and distances[u][v] < min_dist[v]:
                min_dist[v] = distances[u][v]

    return total


def compare_wirelength(optimized, reference, nets):
    """
    Compare wirelength between optimized and reference placements.

    Args:
        optimized: Placement object with optimized component positions
        reference: Placement object with reference component positions
        nets: List of Net objects to analyze

    Returns:
        WirelengthResult with:
        - optimized: Total wirelength of optimized placement
        - reference: Total wirelength of reference placement
        - ratio: optimized / reference
        - margin: 0.1 (10% tolerance)
        - verdict: "PASS" if ratio < 1.1 else "FAIL"
    """
    # Calculate total wirelength for each placement
    optimized_total = sum(manhattan_wirelength(optimized, net) for net in nets)
    reference_total = sum(manhattan_wirelength(reference, net) for net in nets)

    # Compute ratio and verdict
    if reference_total == 0:
        ratio = 1.0 if optimized_total == 0 else float("inf")
    else:
        ratio = optimized_total / reference_total

    margin = 0.1
    verdict = "PASS" if ratio < (1.0 + margin) else "FAIL"

    return WirelengthResult(
        optimized=optimized_total,
        reference=reference_total,
        ratio=ratio,
        margin=margin,
        verdict=verdict,
    )
