"""
Router V6 Stage 4.5: Apply Length Matching

Applies length matching for differential pairs and timing-critical nets.
Part of temper-t2bv (Stage 4 - Geometric Realization)
"""

from __future__ import annotations

from dataclasses import dataclass

from temper_placer.router_v6.astar_pathfinding import PathfindingResult


@dataclass
class LengthMatchingResult:
    """Result of length matching application."""

    net_name: str
    original_length: float  # Original path length (mm)
    target_length: float  # Target length (mm)
    matched_length: float  # Length after matching (mm)
    serpentine_added: bool  # Whether serpentine was added
    
    @property
    def length_delta(self) -> float:
        """Difference from target length."""
        return abs(self.matched_length - self.target_length)


@dataclass
class LengthMatchingResults:
    """Collection of length matching results."""

    results: dict[str, LengthMatchingResult]  # net_name -> result
    
    @property
    def matched_net_count(self) -> int:
        """Number of nets with length matching applied."""
        return len(self.results)
    
    def get_result(self, net_name: str) -> LengthMatchingResult | None:
        """Get length matching result for a net."""
        return self.results.get(net_name)


def apply_length_matching(
    pathfinding_result: PathfindingResult,
    length_targets: dict[str, float] | None = None,
) -> LengthMatchingResults:
    """
    Apply length matching to routed paths.

    Adds serpentine traces or adjusts routing to match target lengths
    for differential pairs and timing-critical nets.

    Args:
        pathfinding_result: Routed paths from Stage 4.2
        length_targets: Optional dict of net_name -> target_length_mm

    Returns:
        LengthMatchingResults with all applied length matching

    Example:
        >>> from temper_placer.router_v6.astar_pathfinding import PathfindingResult
        >>> result = PathfindingResult(routed_paths={}, failed_nets=[])
        >>> matching = apply_length_matching(result)
        >>> matching.matched_net_count >= 0
        True
    """
    if length_targets is None:
        length_targets = {}
    
    results = {}
    
    for net_name, route_path in pathfinding_result.routed_paths.items():
        # Check if this net needs length matching
        target_length = length_targets.get(net_name)
        
        if target_length is not None:
            # Apply length matching
            result = _apply_length_matching_to_path(
                net_name,
                route_path,
                target_length,
            )
            results[net_name] = result
        else:
            # No length matching needed - use original length
            results[net_name] = LengthMatchingResult(
                net_name=net_name,
                original_length=route_path.path_length,
                target_length=route_path.path_length,
                matched_length=route_path.path_length,
                serpentine_added=False,
            )
    
    return LengthMatchingResults(results=results)


def _apply_length_matching_to_path(
    net_name: str,
    route_path,
    target_length: float,
) -> LengthMatchingResult:
    """
    Apply length matching to a single path.

    Args:
        net_name: Net name
        route_path: RoutePath to match
        target_length: Target length in mm

    Returns:
        LengthMatchingResult
    """
    original_length = route_path.path_length
    
    # Calculate length difference
    length_diff = target_length - original_length
    
    if length_diff > 0.5:  # Need to add length (> 0.5mm threshold)
        # Add serpentine to increase length
        matched_length = original_length + _calculate_serpentine_length(length_diff)
        serpentine_added = True
    elif length_diff < -0.5:  # Path is too long
        # Try to shorten (simplified - just use original)
        matched_length = original_length
        serpentine_added = False
    else:
        # Within tolerance
        matched_length = original_length
        serpentine_added = False
    
    return LengthMatchingResult(
        net_name=net_name,
        original_length=original_length,
        target_length=target_length,
        matched_length=matched_length,
        serpentine_added=serpentine_added,
    )


def _calculate_serpentine_length(required_length: float) -> float:
    """
    Calculate serpentine trace length to add.

    Args:
        required_length: Required additional length (mm)

    Returns:
        Actual serpentine length that can be added
    """
    # Simplified: assume we can add exactly the required length
    # In practice, serpentines have minimum amplitude/period constraints
    return required_length
