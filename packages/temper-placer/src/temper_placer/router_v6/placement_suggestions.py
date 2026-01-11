"""
Router V6 Feedback F.3: Generate Placement Suggestions

Generates placement adjustment suggestions based on congestion analysis.
Part of temper-o35p (Feedback Loop & Co-Optimization)
"""

from __future__ import annotations

from dataclasses import dataclass

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
    if component_positions is None:
        component_positions = {}
    
    suggestions = []
    
    # Analyze each congested region
    for region in congestion_map.regions:
        # Only generate suggestions for significant congestion
        if region.bottleneck_score < 0.5:
            continue
        
        # Find components in or near this region
        affected_components = _find_affected_components(
            region,
            component_positions,
        )
        
        # Generate movement suggestions for these components
        for comp_id, comp_pos in affected_components:
            # Suggest moving away from congested region
            suggested_pos = _calculate_suggested_position(
                comp_pos,
                region.center,
                region.severity.value,
            )
            
            # Calculate priority based on congestion severity
            priority = min(1.0, region.bottleneck_score * 1.2)
            
            suggestions.append(PlacementSuggestion(
                component_id=comp_id,
                current_position=comp_pos,
                suggested_position=suggested_pos,
                reason=f"Reduce {region.severity.value} congestion (score: {region.bottleneck_score:.2f})",
                priority=priority,
            ))
    
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
    affected = []
    
    for comp_id, comp_pos in component_positions.items():
        # Check if component is in or near the congested region
        dx = comp_pos[0] - region.center[0]
        dy = comp_pos[1] - region.center[1]
        distance = (dx**2 + dy**2)**0.5
        
        # Include components within 2x region radius
        if distance < region.radius * 2:
            affected.append((comp_id, comp_pos))
    
    return affected


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
    # Move away from congestion center
    dx = current_pos[0] - congestion_center[0]
    dy = current_pos[1] - congestion_center[1]
    distance = (dx**2 + dy**2)**0.5
    
    if distance < 0.1:
        # Already at center, move arbitrarily
        dx, dy = 5.0, 0.0
        distance = 5.0
    
    # Normalize direction
    dx_norm = dx / distance
    dy_norm = dy / distance
    
    # Move distance based on severity
    move_distance = {
        "critical": 10.0,
        "high": 7.0,
        "medium": 5.0,
        "low": 3.0,
    }.get(severity, 3.0)
    
    # Calculate new position
    new_x = current_pos[0] + dx_norm * move_distance
    new_y = current_pos[1] + dy_norm * move_distance
    
    return (new_x, new_y)
