"""
Conflict resolver for overlapping placement constraints.

When multiple heuristics want to place components in conflicting positions,
the ConflictResolver provides strategies for resolution.

Wave 4: the per-pair overlap scan (``check_conflict``) and the nudge-candidate
selection (``_nudge_placement``'s dominant-axis primary + the four fallback
directions) are implemented in Rust in the ``temper-geometry`` crate
(``temper_geometry.overlap_check`` / ``nudge_candidates``); see
``packages/temper-geometry/src/heuristics.rs``. This module keeps
the public API, the strategy branching, the ``is_position_valid`` trial loop
and all message formatting. Pinned oracle:
``packages/temper-placer/tests/heuristics/_conflict_py_oracle.py``; differential:
``packages/temper-placer/tests/heuristics/test_heuristics_rust_differential.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from temper_placer.heuristics.base import ComponentPlacement, PlacementContext


class ResolutionStrategy(Enum):
    """Strategy for resolving placement conflicts."""

    HIGHER_PRIORITY_WINS = "higher_priority"  # Earlier heuristic placement kept
    HIGHER_CONFIDENCE_WINS = "higher_confidence"  # Higher confidence placement kept
    NUDGE = "nudge"  # Try to nudge the new placement to avoid overlap
    REJECT = "reject"  # Reject the new placement entirely


@dataclass
class Conflict:
    """
    Describes a conflict between two component placements.

    Attributes:
        component_a: First component reference
        component_b: Second component reference
        overlap_mm: Estimated overlap in mm
        resolution: How the conflict was resolved
        message: Human-readable description
    """

    component_a: str
    component_b: str
    overlap_mm: float
    resolution: str
    message: str


class ConflictResolver:
    """
    Resolves conflicts between component placements.

    The resolver tracks all placements and ensures no two components
    overlap. When a conflict is detected, it applies the configured
    resolution strategy.

    Example:
        resolver = ConflictResolver(strategy=ResolutionStrategy.NUDGE)
        resolver.add_placement(placement1)
        resolved = resolver.resolve(placement2)  # May be nudged or rejected
    """

    def __init__(
        self,
        strategy: ResolutionStrategy = ResolutionStrategy.HIGHER_PRIORITY_WINS,
        min_spacing_mm: float = 0.5,
    ):
        """
        Initialize the conflict resolver.

        Args:
            strategy: Default resolution strategy
            min_spacing_mm: Minimum spacing between components
        """
        self.strategy = strategy
        self.min_spacing_mm = min_spacing_mm
        self.placements: dict[str, ComponentPlacement] = {}
        self.conflicts: list[Conflict] = []

    def add_placement(self, placement: ComponentPlacement) -> None:
        """
        Add a placement (assumed to be from a higher-priority heuristic).

        These placements are considered "locked" and won't be moved.
        """
        self.placements[placement.ref] = placement

    def add_placements(self, placements: dict[str, ComponentPlacement]) -> None:
        """Add multiple placements."""
        for placement in placements.values():
            self.add_placement(placement)

    def check_conflict(
        self,
        placement: ComponentPlacement,
        width: float,
        height: float,
        context: PlacementContext,
    ) -> tuple[str, float] | None:
        """
        Check if a placement conflicts with existing placements.

        Args:
            placement: The proposed placement
            width, height: Component dimensions
            context: PlacementContext with netlist for looking up component bounds

        Returns:
            Tuple of (conflicting_ref, overlap_mm) or None if no conflict
        """
        from temper_geometry import overlap_check

        x, y = placement.position

        # Collect the existing placements in insertion order. The scan itself
        # (per-pair overlap arithmetic, first-conflict selection) is the Rust
        # kernel; this loop is object navigation (bounds lookup, position
        # extraction) and the ref/index alignment that maps the kernel's first
        # conflicting *index* back to a ref.
        refs: list[str] = []
        boxes: list[tuple[float, float, float, float]] = []
        for ref, existing in self.placements.items():
            if ref == placement.ref:
                continue

            # Get existing component bounds
            comp = context.netlist.get_component(ref)
            other_w, other_h = comp.bounds
            ox, oy = existing.position
            refs.append(ref)
            boxes.append((ox, oy, other_w, other_h))

        hit = overlap_check(x, y, width, height, boxes, self.min_spacing_mm)
        if hit is not None:
            idx, overlap = hit
            return (refs[idx], overlap)

        return None

    def resolve(
        self,
        placement: ComponentPlacement,
        width: float,
        height: float,
        context: PlacementContext,
    ) -> tuple[ComponentPlacement | None, Conflict | None]:
        """
        Resolve a placement against existing placements.

        Args:
            placement: The proposed placement
            width, height: Component dimensions
            context: PlacementContext

        Returns:
            Tuple of (resolved_placement, conflict) where:
            - resolved_placement is the final placement (possibly nudged), or None if rejected
            - conflict is the Conflict object if one occurred, or None
        """
        conflict_info = self.check_conflict(placement, width, height, context)

        if conflict_info is None:
            # No conflict, accept as-is
            return (placement, None)

        conflicting_ref, overlap_mm = conflict_info

        if self.strategy == ResolutionStrategy.HIGHER_PRIORITY_WINS:
            # Earlier placement wins, reject new placement
            conflict = Conflict(
                component_a=conflicting_ref,
                component_b=placement.ref,
                overlap_mm=overlap_mm,
                resolution="rejected",
                message=f"{placement.ref} rejected due to overlap with {conflicting_ref}",
            )
            self.conflicts.append(conflict)
            return (None, conflict)

        elif self.strategy == ResolutionStrategy.HIGHER_CONFIDENCE_WINS:
            existing = self.placements[conflicting_ref]
            if placement.confidence > existing.confidence:
                # New placement wins, but we can't move existing (it's locked)
                # So we nudge the new one instead
                return self._nudge_placement(
                    placement, width, height, context, conflicting_ref, overlap_mm
                )
            else:
                # Existing wins, reject new
                conflict = Conflict(
                    component_a=conflicting_ref,
                    component_b=placement.ref,
                    overlap_mm=overlap_mm,
                    resolution="rejected_lower_confidence",
                    message=f"{placement.ref} rejected (confidence {placement.confidence:.2f} < {existing.confidence:.2f})",
                )
                self.conflicts.append(conflict)
                return (None, conflict)

        elif self.strategy == ResolutionStrategy.NUDGE:
            return self._nudge_placement(
                placement, width, height, context, conflicting_ref, overlap_mm
            )

        else:  # REJECT
            conflict = Conflict(
                component_a=conflicting_ref,
                component_b=placement.ref,
                overlap_mm=overlap_mm,
                resolution="rejected",
                message=f"{placement.ref} rejected due to overlap with {conflicting_ref}",
            )
            self.conflicts.append(conflict)
            return (None, conflict)

    def _nudge_placement(
        self,
        placement: ComponentPlacement,
        width: float,
        height: float,
        context: PlacementContext,
        conflicting_ref: str,
        overlap_mm: float,
    ) -> tuple[ComponentPlacement | None, Conflict | None]:
        """
        Try to nudge a placement to avoid overlap.

        Tries 4 directions (up, down, left, right) and picks the first valid one.
        """
        from temper_geometry import nudge_candidates

        x, y = placement.position

        # Get conflicting component position to determine nudge direction
        conflicting_pos = self.placements[conflicting_ref].position

        # Candidate selection (dominant-axis primary + the four fallback
        # directions, in trial order) is the Rust kernel; the trial loop
        # (validity check, confidence reduction, re-conflict scan) stays here,
        # mirroring the sibling heuristics' "trial loop stays Python" split.
        candidates = nudge_candidates(
            x, y, conflicting_pos[0], conflicting_pos[1], overlap_mm, self.min_spacing_mm
        )

        for nudge_x, nudge_y in candidates:
            new_x = x + nudge_x
            new_y = y + nudge_y

            if context.is_position_valid(new_x, new_y, width, height):
                # Check if nudged position still conflicts
                nudged = ComponentPlacement(
                    ref=placement.ref,
                    position=(new_x, new_y),
                    rotation=placement.rotation,
                    confidence=placement.confidence * 0.9,  # Reduce confidence for nudged placement
                    placed_by=placement.placed_by,
                )

                # Check for new conflicts (recursive, but should converge)
                new_conflict = self.check_conflict(nudged, width, height, context)
                if new_conflict is None:
                    conflict = Conflict(
                        component_a=conflicting_ref,
                        component_b=placement.ref,
                        overlap_mm=overlap_mm,
                        resolution="nudged",
                        message=f"{placement.ref} nudged by ({nudge_x:.1f}, {nudge_y:.1f}) to avoid {conflicting_ref}",
                    )
                    self.conflicts.append(conflict)
                    return (nudged, conflict)

        # All nudges failed, reject
        conflict = Conflict(
            component_a=conflicting_ref,
            component_b=placement.ref,
            overlap_mm=overlap_mm,
            resolution="rejected_no_valid_nudge",
            message=f"{placement.ref} could not be nudged to avoid {conflicting_ref}",
        )
        self.conflicts.append(conflict)
        return (None, conflict)

    def get_all_conflicts(self) -> list[Conflict]:
        """Get all conflicts that have been recorded."""
        return self.conflicts.copy()

    def clear(self) -> None:
        """Clear all placements and conflicts."""
        self.placements.clear()
        self.conflicts.clear()
