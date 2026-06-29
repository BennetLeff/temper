"""
Compile declarative constraints to executable functions.

This module provides the ConstraintCompiler class that transforms constraints
from YAML config into filter and scorer functions for deterministic placement.

Architecture:
    PlacementConstraints → ConstraintCompiler → {filter_fn, scorer_fn}

Filters (hard constraints):
    - Reject invalid placements outright
    - Return bool: True = valid, False = invalid

Scorers (soft constraints):
    - Rank valid placements
    - Return float: lower = better, 0 = perfect
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist

from temper_placer.io.config_loader import PlacementConstraints

# Type aliases for clarity
SlotFilter = Callable[[tuple[float, float], str, dict[str, tuple[float, float]]], bool]
SlotScorer = Callable[[tuple[float, float], str, dict[str, tuple[float, float]]], float]


@dataclass
class ValidationError:
    """Constraint validation error with helpful context."""

    constraint_type: str
    message: str
    component: str | None = None
    suggestion: str | None = None

    def __str__(self) -> str:
        """Format error with suggestion if available."""
        msg = f"{self.constraint_type}: {self.message}"
        if self.component:
            msg += f" (component: {self.component})"
        if self.suggestion:
            msg += f"\n  → {self.suggestion}"
        return msg


class ConstraintCompiler:
    """Compile constraints to slot selection functions.

    Transforms declarative constraints (proximity rules, spacing, thermal, etc.)
    into executable filter and scorer functions for deterministic placement.

    Example:
        >>> constraints = load_constraints("config.yaml")
        >>> compiler = ConstraintCompiler(constraints)
        >>> filter_fn = compiler.compile_to_slot_filter()
        >>> scorer_fn = compiler.compile_to_slot_scorer()
        >>>
        >>> # Use in placement
        >>> if filter_fn((10, 20), "U_MCU", placements):
        >>>     score = scorer_fn((10, 20), "U_MCU", placements)
    """

    def __init__(
        self,
        constraints: PlacementConstraints,
        board_bounds: tuple[float, float, float, float] | None = None,
    ):
        """Initialize compiler.

        Args:
            constraints: Parsed constraints from YAML
            board_bounds: (x0, y0, x1, y1) board boundaries in mm
        """
        self.constraints = constraints
        self.board_bounds = board_bounds or (
            0,
            0,
            constraints.board_width_mm,
            constraints.board_height_mm,
        )

    def compile_to_slot_filter(self) -> SlotFilter:
        """Create filter that rejects invalid slots (hard constraints).

        The filter checks hard constraints like:
        - Component spacing rules (tier="hard")
        - Escape clearances (tier="hard")
        - Routing corridors with keep_clear=True
        - Zone boundaries (if zone is required)

        Returns:
            Filter function: (slot, component, placements) -> bool
                True = valid slot, False = rejected
        """

        def filter_slot(
            slot: tuple[float, float],
            component: str,
            placements: dict[str, tuple[float, float]],
        ) -> bool:
            x, y = slot

            # 1. Component spacing rules (hard constraint)
            for rule in self.constraints.component_spacing_rules:
                if component not in (rule.component_a, rule.component_b):
                    continue
                # Only apply hard tier rules in filter
                if rule.tier != "hard":
                    continue

                other = rule.component_b if component == rule.component_a else rule.component_a
                if other in placements:
                    dist = self._distance(slot, placements[other])
                    if dist < rule.min_separation_mm:
                        return False

            # 2. Proximity rules (hard mode) - must be close
            for group in self.constraints.component_groups:
                if component not in group.components:
                    continue

                for rule in group.proximity_rules:
                    if rule.tier != "hard":
                        continue
                    if component not in (rule.component_a, rule.component_b):
                        continue

                    other = rule.component_b if component == rule.component_a else rule.component_a
                    if other in placements:
                        dist = self._distance(slot, placements[other])
                        if dist > rule.max_distance_mm:
                            return False  # Too far - reject

            # 3. Escape clearance (hard mode)
            for ec in self.constraints.escape_clearances:
                if ec.tier != "hard":
                    continue
                if ec.component in placements and self._in_escape_zone(slot, placements[ec.component], ec):
                    return False

            # 4. Routing corridors (keep_clear + hard tier)
            for corridor in self.constraints.routing_corridors:
                if not corridor.keep_clear or corridor.tier != "hard":
                    continue
                if self._in_corridor(slot, corridor, placements):
                    return False

            # 5. Zone membership (if zone is required)
            required_zone = self.constraints.get_zone_for_component(component)
            if required_zone:
                zone = next((z for z in self.constraints.zones if z.name == required_zone), None)
                if zone and not self._in_zone(slot, zone):
                    return False

            return True

        return filter_slot

    def compile_to_slot_scorer(self) -> SlotScorer:
        """Create scorer that ranks valid slots (soft constraints).

        The scorer accumulates penalties for:
        - Proximity violations (groups want to be close)
        - Thermal edge preference
        - Group spread (keep groups tight)
        - Soft spacing rules
        - Soft escape clearances
        - Routing corridor violations

        Returns:
            Scorer function: (slot, component, placements) -> float
                Lower score = better placement, 0 = perfect
        """

        def score_slot(
            slot: tuple[float, float],
            component: str,
            placements: dict[str, tuple[float, float]],
        ) -> float:
            score = 0.0

            # 1. Proximity rules - prefer being close to related components (soft only)
            for group in self.constraints.component_groups:
                if component not in group.components:
                    continue

                for rule in group.proximity_rules:
                    # Only apply soft tier rules in scorer
                    if rule.tier != "soft":
                        continue
                    if component not in (rule.component_a, rule.component_b):
                        continue

                    other = rule.component_b if component == rule.component_a else rule.component_a
                    if other in placements:
                        dist = self._distance(slot, placements[other])
                        if dist > rule.max_distance_mm:
                            # Penalty scales with violation
                            score += (dist - rule.max_distance_mm) * 10.0

            # 2. Thermal edge preference
            for thermal in self.constraints.thermal_constraints:
                if component not in thermal.components:
                    continue
                if thermal.prefer_edge:
                    edge_dist = self._min_edge_distance(slot)
                    if edge_dist > thermal.max_distance_from_edge_mm:
                        score += (edge_dist - thermal.max_distance_from_edge_mm) * 5.0

            # 3. Group spread - keep groups tight
            for group in self.constraints.component_groups:
                if component not in group.components:
                    continue

                placed = [placements[c] for c in group.components if c in placements]
                if placed:
                    centroid = self._centroid(placed)
                    dist = self._distance(slot, centroid)
                    if dist > group.max_spread_mm / 2:
                        score += dist * group.weight * 0.1

            # 4. Component spacing rules (soft only in scorer)
            for rule in self.constraints.component_spacing_rules:
                # Only apply soft tier rules in scorer
                if rule.tier != "soft":
                    continue
                if component not in (rule.component_a, rule.component_b):
                    continue

                other = rule.component_b if component == rule.component_a else rule.component_a
                if other in placements:
                    dist = self._distance(slot, placements[other])
                    if dist < rule.min_separation_mm:
                        # Weight acts as penalty multiplier
                        score += (rule.min_separation_mm - dist) * rule.weight

            # 5. Escape clearance (soft mode) - prefer not blocking escapes
            for ec in self.constraints.escape_clearances:
                if ec.tier != "soft":
                    continue
                if ec.component in placements and self._in_escape_zone(slot, placements[ec.component], ec):
                    score += 50.0  # Strong penalty

            # 6. Routing corridors (soft mode)
            for corridor in self.constraints.routing_corridors:
                if corridor.tier != "soft":
                    continue
                if self._in_corridor(slot, corridor, placements):
                    penalty = 20.0 if corridor.keep_clear else 10.0
                    score += penalty

            return score

        return score_slot

    def validate(self, _board: Board | None, netlist: Netlist) -> list[ValidationError]:
        """Validate constraints against actual board/netlist.

        Checks for:
        - Component references that don't exist
        - Invalid zone assignments
        - Malformed routing corridors

        Args:
            board: Board geometry (optional)
            netlist: Component netlist with refs

        Returns:
            List of validation errors with suggestions
        """
        errors = []

        component_refs = {c.ref for c in netlist.components}

        # Check escape clearances reference valid components
        for ec in self.constraints.escape_clearances:
            if ec.component not in component_refs:
                similar = self._find_similar(ec.component, component_refs)
                errors.append(
                    ValidationError(
                        constraint_type="EscapeClearance",
                        message=f"Component '{ec.component}' not found in netlist",
                        component=ec.component,
                        suggestion=f"Did you mean: {similar}?" if similar else None,
                    )
                )

        # Check routing corridors
        for corridor in self.constraints.routing_corridors:
            if corridor.from_component not in component_refs:
                similar = self._find_similar(corridor.from_component, component_refs)
                errors.append(
                    ValidationError(
                        constraint_type="RoutingCorridor",
                        message=f"from_component '{corridor.from_component}' not found",
                        component=corridor.from_component,
                        suggestion=f"Did you mean: {similar}?" if similar else None,
                    )
                )
            if corridor.to_component not in component_refs:
                similar = self._find_similar(corridor.to_component, component_refs)
                errors.append(
                    ValidationError(
                        constraint_type="RoutingCorridor",
                        message=f"to_component '{corridor.to_component}' not found",
                        component=corridor.to_component,
                        suggestion=f"Did you mean: {similar}?" if similar else None,
                    )
                )

        # Check component spacing rules
        for rule in self.constraints.component_spacing_rules:
            if rule.component_a not in component_refs:
                errors.append(
                    ValidationError(
                        constraint_type="ComponentSpacingRule",
                        message=f"component_a '{rule.component_a}' not found",
                        component=rule.component_a,
                    )
                )
            if rule.component_b not in component_refs:
                errors.append(
                    ValidationError(
                        constraint_type="ComponentSpacingRule",
                        message=f"component_b '{rule.component_b}' not found",
                        component=rule.component_b,
                    )
                )

        # Check zone assignments
        zone_names = {z.name for z in self.constraints.zones}
        for comp_ref, zone_name in self.constraints.zone_assignments.items():
            if comp_ref not in component_refs:
                errors.append(
                    ValidationError(
                        constraint_type="ZoneAssignment",
                        message=f"Component '{comp_ref}' assigned to zone but not in netlist",
                        component=comp_ref,
                    )
                )
            if zone_name not in zone_names:
                errors.append(
                    ValidationError(
                        constraint_type="ZoneAssignment",
                        message=f"Zone '{zone_name}' not defined",
                        component=comp_ref,
                        suggestion=f"Available zones: {', '.join(zone_names)}",
                    )
                )

        # Check component groups
        for group in self.constraints.component_groups:
            for comp_ref in group.components:
                if comp_ref not in component_refs:
                    errors.append(
                        ValidationError(
                            constraint_type="ComponentGroup",
                            message=f"Component '{comp_ref}' in group '{group.name}' not in netlist",
                            component=comp_ref,
                        )
                    )

        return errors

    # Helper methods

    def _distance(self, p1: tuple[float, float], p2: tuple[float, float]) -> float:
        """Euclidean distance between two points."""
        return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)

    def _centroid(self, points: list[tuple[float, float]]) -> tuple[float, float]:
        """Compute centroid of point set."""
        if not points:
            return (0.0, 0.0)
        return (
            sum(p[0] for p in points) / len(points),
            sum(p[1] for p in points) / len(points),
        )

    def _min_edge_distance(self, slot: tuple[float, float]) -> float:
        """Minimum distance from slot to any board edge."""
        x, y = slot
        x0, y0, x1, y1 = self.board_bounds
        return min(x - x0, x1 - x, y - y0, y1 - y)

    def _in_escape_zone(self, slot: tuple[float, float], comp_pos: tuple[float, float], ec) -> bool:
        """Check if slot is within escape clearance zone.

        Args:
            slot: Candidate position
            comp_pos: Position of component requiring clearance
            ec: EscapeClearance constraint

        Returns:
            True if slot violates escape clearance
        """
        clearance = ec.clearance_mm if ec.clearance_mm is not None else 3.0
        dist = self._distance(slot, comp_pos)
        return dist < clearance

    def _in_corridor(self, slot: tuple[float, float], corridor, placements: dict) -> bool:
        """Check if slot is within routing corridor.

        Args:
            slot: Candidate position
            corridor: RoutingCorridor constraint
            placements: Already-placed components

        Returns:
            True if slot is inside corridor
        """
        if corridor.from_component not in placements or corridor.to_component not in placements:
            return False

        p1 = placements[corridor.from_component]
        p2 = placements[corridor.to_component]

        # Point-to-line-segment distance
        dist = self._point_to_segment_distance(slot, p1, p2)
        return dist < corridor.width_mm / 2

    def _point_to_segment_distance(
        self,
        p: tuple[float, float],
        a: tuple[float, float],
        b: tuple[float, float],
    ) -> float:
        """Compute minimum distance from point to line segment.

        Uses perpendicular projection with endpoint clamping.

        Args:
            p: Point to measure from
            a: Segment start
            b: Segment end

        Returns:
            Minimum distance in mm
        """
        # Vector from a to b
        ab_x = b[0] - a[0]
        ab_y = b[1] - a[1]

        # Vector from a to p
        ap_x = p[0] - a[0]
        ap_y = p[1] - a[1]

        # Length squared of ab
        ab_len_sq = ab_x * ab_x + ab_y * ab_y

        if ab_len_sq == 0:
            # a and b are the same point
            return self._distance(p, a)

        # Projection parameter (0 = at a, 1 = at b)
        t = max(0, min(1, (ap_x * ab_x + ap_y * ab_y) / ab_len_sq))

        # Closest point on segment
        closest_x = a[0] + t * ab_x
        closest_y = a[1] + t * ab_y

        return self._distance(p, (closest_x, closest_y))

    def _in_zone(self, slot: tuple[float, float], zone) -> bool:
        """Check if slot is within zone bounds.

        Args:
            slot: Candidate position
            zone: Zone constraint

        Returns:
            True if slot is inside zone
        """
        x, y = slot
        x0, y0, x1, y1 = zone.bounds
        return x0 <= x <= x1 and y0 <= y <= y1

    def _find_similar(self, name: str, options: set[str]) -> str | None:
        """Find similar component name in options.

        Uses simple prefix matching for typo detection.

        Args:
            name: Name to search for
            options: Set of valid names

        Returns:
            Most similar option or None
        """
        if not name or len(name) < 2:
            return None

        # Try prefix matching (at least 3 chars)
        prefix_len = min(3, len(name))
        for opt in options:
            if len(opt) < prefix_len:
                continue
            if opt[:prefix_len].lower() == name[:prefix_len].lower():
                return opt

        # Try suffix matching (component number)
        if "_" in name:
            suffix = name.split("_")[-1]
            for opt in options:
                if "_" in opt and opt.split("_")[-1] == suffix:
                    return opt

        return None
