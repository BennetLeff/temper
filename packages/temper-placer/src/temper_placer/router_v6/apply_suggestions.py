"""
Router V6 Feedback F.4: Apply Suggestions with Damping

Applies placement suggestions with damping to prevent oscillation.
Part of temper-8hx1 (Feedback Loop & Co-Optimization)

Wave 4 Phase B: ``_calculate_damped_position``, ``AdjustmentResult.total_movement``
and ``update_component_positions`` delegate to ``temper_geometry``
(``apply_damped_position_py`` / ``apply_total_movement_py`` /
``apply_update_positions_py``) -- all three kernels operate on the exact
values this module already has in hand (a position pair, a list of
original/applied position pairs, a positions dict plus applied-position
pairs), so each is a full substitution.

``apply_suggestions_with_damping`` itself does **not** delegate to
``apply_suggestions_damped_py``. That kernel does not accept a pre-built
``PlacementSuggestions`` at all -- it takes the source congestion regions and
*regenerates* the suggestions internally via its own copy of
``generate_placement_suggestions``'s logic, then applies damping to that
regenerated list. Its own module doc says as much: the identity-guard
comment on the ``current_positions.get(comp_id) is None`` branch notes it is
"unreachable" there because "this function is only ever called with the one
dict the differential passes for both steps" (i.e. the SAME positions dict
used to generate the suggestions). This module's real signature takes an
already-built ``suggestions: PlacementSuggestions`` that may have been
generated at an earlier time, filtered, or built by hand -- there is no way
to recover the originating regions from it, and the kernel's assumption that
regenerating from ``current_positions`` reproduces the same list the caller
actually passed does not hold in general. Delegating here would silently
substitute freshly-regenerated suggestions for whatever the caller supplied,
which the differential's own single call-shape (regions + one positions
dict, reused for both steps) cannot distinguish from a correct port.
"""

from __future__ import annotations

from dataclasses import dataclass

import temper_geometry as _tg

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
        moves = [(adj.original_position, adj.applied_position) for adj in self.adjustments]
        return _tg.apply_total_movement_py(moves)


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
        s for s in suggestions.suggestions if s.priority >= min_priority_threshold
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

        adjustments.append(
            AppliedAdjustment(
                component_id=comp_id,
                original_position=current_pos,
                suggested_position=suggestion.suggested_position,
                applied_position=applied_pos,
                damping_factor=damping_factor,
            )
        )

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
    return _tg.apply_damped_position_py(current, suggested, damping)


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
    applied = [
        (adjustment.component_id, adjustment.applied_position)
        for adjustment in adjustment_result.adjustments
    ]
    return _tg.apply_update_positions_py(current_positions, applied)
