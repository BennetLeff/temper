"""
Router V6 Stage 4.8: Length Matching for Groups

Applies length matching for differential pairs and timing-critical net groups.
Adds serpentines to equalize lengths within specified tolerances.
"""

from __future__ import annotations

from dataclasses import dataclass

from temper_placer.router_v6.astar_pathfinding import PathfindingResult
from temper_placer.router_v6.length_group_inference import LengthGroup


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
    length_groups: list[LengthGroup] | None = None,
    individual_targets: dict[str, float] | None = None,
) -> LengthMatchingResults:
    """
    Apply length matching to routed paths using group and individual constraints.

    Args:
        pathfinding_result: Routed paths from Stage 4.2
        length_groups: Optional list of groups requiring matched lengths
        individual_targets: Optional dict of net_name -> target_length_mm

    Returns:
        LengthMatchingResults
    """
    if length_groups is None:
        length_groups = []
    if individual_targets is None:
        individual_targets = {}

    results = {}
    processed_nets = set()

    # 1. Process Length Groups
    for group in length_groups:
        group_results = equalize_group_lengths(group, pathfinding_result)
        for res in group_results:
            results[res.net_name] = res
            processed_nets.add(res.net_name)

    # 2. Process Individual Targets
    for net_name, target in individual_targets.items():
        if net_name in processed_nets:
            continue

        route_path = pathfinding_result.get_path(net_name)
        if route_path:
            results[net_name] = _apply_length_matching_to_path(
                net_name,
                route_path.path_length,
                target,
                0.1 # Default tight tolerance for explicit targets
            )
            processed_nets.add(net_name)

    # 3. Fill in Remaining Nets
    for net_name, route_path in pathfinding_result.routed_paths.items():
        if net_name not in processed_nets:
            results[net_name] = LengthMatchingResult(
                net_name=net_name,
                original_length=route_path.path_length,
                target_length=route_path.path_length,
                matched_length=route_path.path_length,
                serpentine_added=False,
            )

    return LengthMatchingResults(results=results)


def equalize_group_lengths(
    group: LengthGroup,
    pathfinding_result: PathfindingResult,
) -> list[LengthMatchingResult]:
    """
    Equalize lengths of all nets within a group to the longest net's length.
    """
    group_nets = []
    max_len = 0.0

    if group.target_length_mm is not None:
        max_len = group.target_length_mm

    # Find maximum length in group
    for net_name in group.nets:
        path = pathfinding_result.get_path(net_name)
        if path:
            group_nets.append((net_name, path.path_length))
            if group.target_length_mm is None:
                max_len = max(max_len, path.path_length)

    results = []
    for net_name, length in group_nets:
        # Match to max_len within group tolerance (max_skew_mm)
        res = _apply_length_matching_to_path(
            net_name,
            length,
            max_len,
            group.max_skew_mm
        )
        results.append(res)

    return results


def _apply_length_matching_to_path(
    net_name: str,
    original_length: float,
    target_length: float,
    tolerance: float,
) -> LengthMatchingResult:
    """
    Apply length matching to a single path.
    """
    # Calculate length difference
    length_diff = target_length - original_length

    if length_diff > tolerance:  # Need to add length
        # Add serpentine to increase length
        added = _calculate_serpentine_length(length_diff)
        if added > 0:
            matched_length = original_length + added
            serpentine_added = True
        else:
            # Insufficient space for serpentine — cannot match
            matched_length = original_length
            serpentine_added = False
    elif length_diff < -tolerance:  # Path is too long
        # Cannot easily shorten paths in Stage 4.8 realization
        # (should have been addressed in Stage 3 topology)
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


def _calculate_serpentine_length(
    required_length: float,
    available_space_mm: float = 5.0,
    cell_size_mm: float = 0.1,
) -> float:
    """
    Calculate achievable serpentine trace length using real geometry.

    Uses serpentine parameter calculation to determine whether the
    required additional length is physically realisable given the
    available perpendicular routing space.

    Args:
        required_length: How much additional length is needed (mm)
        available_space_mm: Perpendicular space available for meanders
        cell_size_mm: Grid cell size for discretisation

    Returns:
        Achievable additional length (mm), or 0.0 if serpentine is
        infeasible (insufficient space, deficit too small, etc.).
    """
    if required_length <= 0:
        return 0.0

    from temper_placer.routing.serpentine import calculate_serpentine_params

    amplitude_mm, _frequency_check = calculate_serpentine_params(
        required_length,
        available_space_mm=available_space_mm,
        cell_size_mm=cell_size_mm,
    )

    # ``calculate_serpentine_params`` returns (0.0, 0) when there is
    # not enough space for even a single-amplitude meander.
    if amplitude_mm < cell_size_mm:
        return 0.0

    # Each serpentine cycle adds 2 × amplitude (out + back) of
    # Manhattan length.  Compute the frequency required to meet (or
    # approximate) the deficit, clamped to avoid excessive zigzagging.
    frequency = max(1, int(required_length / (2.0 * amplitude_mm)))
    frequency = min(frequency, 10)

    achievable = 2.0 * amplitude_mm * frequency
    return achievable
