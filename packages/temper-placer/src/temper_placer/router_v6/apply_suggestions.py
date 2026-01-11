"""
Router V6 Feedback F.4: Apply Suggestions with Damping

Applies placement suggestions with damping to prevent oscillation.
Part of temper-8hx1 (Feedback Loop & Co-Optimization)
"""

from __future__ import annotations

from dataclasses import dataclass

from temper_placer.router_v6.placement_suggestions import PlacementSuggestions


@dataclass
class AppliedAdjustment:
    """A placement adjustment that was applied."""

    component_id: str
    original_position: tuple[float, float]
    suggested_position: tuple[float, float]
    applied_position: tuple[float, float]
    damping_factor: float  # How much suggestion was dampened (0.0-1.0)


@dataclass
class AdjustmentResult:
    """Result of applying placement adjustments."""

    adjustments: list[AppliedAdjustment]
    
    @property
    def adjustment_count(self) -> int:
        """Number of adjustments applied."""
        return len(self.adjustments)
    
    @property
    def total_movement(self) -> float:
        """Total movement distance across all adjustments (mm)."""
        total = 0.0
        for adj in self.adjustments:
            dx = adj.applied_position[0] - adj.original_position[0]
            dy = adj.applied_position[1] - adj.original_position[1]
            total += (dx**2 + dy**2)**0.5
        return total


def apply_suggestions_with_damping(
    suggestions: PlacementSuggestions,
    current_positions: dict[str, tuple[float, float]],
    damping_factor: float = 0.5,  # Conservative default
    min_priority_threshold: float = 0.5,
) -> AdjustmentResult:
    """
    Apply placement suggestions with damping to prevent oscillation.

    Damping reduces the magnitude of adjustments to ensure gradual
    convergence and avoid oscillation between states.

    Args:
        suggestions: Placement suggestions from F.3
        current_positions: Current component positions
        damping_factor: How much to dampen movements (0.0-1.0)
        min_priority_threshold: Minimum priority to apply

    Returns:
        AdjustmentResult with applied adjustments

    Example:
        >>> from temper_placer.router_v6.placement_suggestions import PlacementSuggestions
        >>> suggestions = PlacementSuggestions(suggestions=[])
        >>> positions = {}
        >>> result = apply_suggestions_with_damping(suggestions, positions)
        >>> result.adjustment_count >= 0
        True
    """
    adjustments = []
    
    # Filter for high-priority suggestions
    filtered_suggestions = [
        s for s in suggestions.suggestions
        if s.priority >= min_priority_threshold
    ]
    
    for suggestion in filtered_suggestions:
        comp_id = suggestion.component_id
        
        # Get current position
        current_pos = current_positions.get(comp_id)
        if current_pos is None:
            continue
        
        # Calculate damped position
        applied_pos = _calculate_damped_position(
            current_pos,
            suggestion.suggested_position,
            damping_factor,
        )
        
        adjustments.append(AppliedAdjustment(
            component_id=comp_id,
            original_position=current_pos,
            suggested_position=suggestion.suggested_position,
            applied_position=applied_pos,
            damping_factor=damping_factor,
        ))
    
    return AdjustmentResult(adjustments=adjustments)


def _calculate_damped_position(
    current: tuple[float, float],
    suggested: tuple[float, float],
    damping: float,
) -> tuple[float, float]:
    """
    Calculate damped position between current and suggested.

    Args:
        current: Current position
        suggested: Suggested position
        damping: Damping factor (0.0 = no movement, 1.0 = full movement)

    Returns:
        Damped position
    """
    # Linear interpolation with damping
    new_x = current[0] + (suggested[0] - current[0]) * damping
    new_y = current[1] + (suggested[1] - current[1]) * damping
    
    return (new_x, new_y)


def update_component_positions(
    current_positions: dict[str, tuple[float, float]],
    adjustment_result: AdjustmentResult,
) -> dict[str, tuple[float, float]]:
    """
    Update component positions based on applied adjustments.

    Args:
        current_positions: Current positions
        adjustment_result: Applied adjustments

    Returns:
        Updated positions dictionary
    """
    updated = current_positions.copy()
    
    for adjustment in adjustment_result.adjustments:
        updated[adjustment.component_id] = adjustment.applied_position
    
    return updated
