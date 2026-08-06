"""
Router V6 Feedback F.3: Generate Placement Suggestions

Generates placement adjustment suggestions based on congestion analysis.
Part of temper-o35p (Feedback Loop & Co-Optimization)

Wave 4 Phase B: ``generate_placement_suggestions``, ``_find_affected_components``
and ``_calculate_suggested_position`` delegate to ``temper_geometry``
(``placement_suggestions_generate_py`` / ``placement_find_affected_py`` /
``placement_suggested_position_py``). All three kernels accept an arbitrary
region/positions shape (no baked-in assumption about how the caller built
them), so this is a full substitution.
"""

from __future__ import annotations

from dataclasses import dataclass

import temper_geometry as _tg

from temper_placer.router_v6.congestion_analysis import CongestionMap


@dataclass
class PlacementSuggestion:
    """A suggested placement adjustment."""

    component_id: str
    current_position: tuple[float, float]
    suggested_position: tuple[float, float]
    reason: str  # Why this move is suggested
    priority: float  # 0.0-1.0, higher = more important


@dataclass
class PlacementSuggestions:
    """Collection of placement suggestions."""

    suggestions: list[PlacementSuggestion]

    @property
    def suggestion_count(self) -> int:
        """Number of suggestions."""
        return len(self.suggestions)

    def get_high_priority_suggestions(self, threshold: float = 0.7) -> list[PlacementSuggestion]:
        """Get suggestions above priority threshold."""
        return [s for s in self.suggestions if s.priority >= threshold]


def generate_placement_suggestions(
    congestion_map: CongestionMap,
    component_positions: dict[str, tuple[float, float]] | None = None,
) -> PlacementSuggestions:
    """
    Generate placement suggestions based on congestion analysis.

    Proposes component movements to reduce congestion in critical regions.

    Args:
        congestion_map: Congestion analysis from F.2
        component_positions: Optional dict of component_id -> (x, y)

    Returns:
        PlacementSuggestions with proposed adjustments

    Example:
        >>> from temper_placer.router_v6.congestion_analysis import CongestionMap
        >>> congestion = CongestionMap(regions=[])
        >>> suggestions = generate_placement_suggestions(congestion)
        >>> suggestions.suggestion_count >= 0
        True
    """
    region_rows = [
        (
            region.center[0],
            region.center[1],
            region.radius,
            region.severity.value,
            region.failed_net_count,
            region.bottleneck_score,
        )
        for region in congestion_map.regions
    ]

    out = _tg.placement_suggestions_generate_py(region_rows, component_positions)

    suggestions = [
        PlacementSuggestion(
            component_id=component_id,
            current_position=current_position,
            suggested_position=suggested_position,
            reason=reason,
            priority=priority,
        )
        for (component_id, current_position, suggested_position, reason, priority) in out
    ]

    return PlacementSuggestions(suggestions=suggestions)


def _find_affected_components(
    region,
    component_positions: dict[str, tuple[float, float]],
) -> list[tuple[str, tuple[float, float]]]:
    """
    Find components affected by congested region.

    Args:
        region: Congested region
        component_positions: Component positions

    Returns:
        List of (component_id, position) tuples
    """
    region_row = (
        region.center[0],
        region.center[1],
        region.radius,
        region.severity.value,
        region.failed_net_count,
        region.bottleneck_score,
    )
    return _tg.placement_find_affected_py(region_row, component_positions)


def _calculate_suggested_position(
    current_pos: tuple[float, float],
    congestion_center: tuple[float, float],
    severity: str,
) -> tuple[float, float]:
    """
    Calculate suggested new position.

    Args:
        current_pos: Current component position
        congestion_center: Center of congested region
        severity: Congestion severity

    Returns:
        Suggested new position
    """
    return _tg.placement_suggested_position_py(current_pos, congestion_center, severity)
