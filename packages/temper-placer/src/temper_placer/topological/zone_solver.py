"""Zone assignment solver.

Assigns components to placement zones before geometric optimization.
Uses constraint satisfaction problem (CSP) approach with backtracking.

Example:
    zones = [Zone('HV_ZONE', (0,0,50,50)), Zone('MCU_ZONE', (60,0,110,50))]
    constraints = [EnclosingConstraint('HV_ZONE', ['Q1', 'Q2'], ...)]

    solver = ZoneSolver(zones, constraints, ['Q1', 'Q2', 'U1'])
    assignment = solver.solve()

    if assignment.conflicts:
        print("Infeasible zone assignment!")
    else:
        print(f"Q1 → {assignment.assignments['Q1']}")
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

import temper_placement_topology as _rust

if TYPE_CHECKING:
    from temper_placer.core.board import Zone
    from temper_placer.pcl.constraints import BaseConstraint


@dataclass
class ZoneAssignment:
    """Result of zone assignment.

    Attributes:
        assignments: Component ref → zone name mapping
        unassigned: Components that couldn't be assigned
        conflicts: List of (component, context, reason) tuples for failures
    """

    assignments: dict[str, str]
    unassigned: list[str]
    conflicts: list[tuple[str, str, str]]


class ZoneSolver:
    """Solve zone assignment as constraint satisfaction problem.

    Uses backtracking search with most-constrained-variable (MCV) heuristic.

    Attributes:
        zones: Dict of zone name → Zone object
        constraints: List of PCL constraints
        components: List of component refs to assign
    """

    def __init__(
        self,
        zones: list["Zone"],
        constraints: list["BaseConstraint"],
        components: list[str],
    ):
        """Initialize zone solver.

        Args:
            zones: List of available placement zones
            constraints: PCL constraints (EnclosingConstraint, etc.)
            components: Component refs to assign to zones
        """
        self.zones = {z.name: z for z in zones}
        self.constraints = constraints
        self.components = components

        # Build candidate zones for each component
        self._candidates = self._build_candidates()

    def _build_candidates(self) -> dict[str, set[str]]:
        """Determine candidate zones for each component.

        Without constraints, all components can go in any zone.
        EnclosingConstraint restricts component to specific zone.

        Returns:
            Dict mapping component ref → set of valid zone names
        """
        from temper_placer.pcl.constraints import EnclosingConstraint

        # Start with all zones as candidates
        candidates = {comp: set(self.zones.keys()) for comp in self.components}

        # Apply enclosing constraints
        for constraint in self.constraints:
            if isinstance(constraint, EnclosingConstraint):
                zone_name = constraint.outer

                # Skip if zone doesn't exist
                if zone_name not in self.zones:
                    # Mark components as having no valid zones
                    for comp in constraint.inner:
                        if comp in candidates:
                            candidates[comp] = set()
                    continue

                # Restrict components to this zone
                for comp in constraint.inner:
                    if comp in candidates:
                        # If already constrained to different zone, conflict
                        if candidates[comp] and zone_name not in candidates[comp]:
                            candidates[comp] = set()  # No valid zones
                        else:
                            candidates[comp] = {zone_name}

        return candidates

    def solve(self) -> ZoneAssignment:
        """Solve zone assignment using backtracking.

        Uses most-constrained-variable heuristic: assign components
        with fewest zone options first.

        Returns:
            ZoneAssignment with assignments or conflicts
        """
        # Check for components with no valid zones
        conflicts = []
        for comp, zones in self._candidates.items():
            if not zones:
                conflicts.append(
                    (
                        comp,
                        "zone_assignment",
                        "No valid zones (conflicting enclosing constraints or non-existent zone)",
                    )
                )

        if conflicts:
            return ZoneAssignment(
                assignments={},
                unassigned=self.components,
                conflicts=conflicts,
            )

        # Sort components by most constrained first (MCV heuristic).
        # Kept in Python: `sorted` is stable and its tie order is part of the
        # observable behaviour.
        sorted_components = sorted(
            self.components,
            key=lambda c: len(self._candidates[c]),
        )

        # Backtracking search.
        #
        # The candidate *order* is passed through exactly as this process's
        # `set` iteration yields it. That order is salted by PYTHONHASHSEED,
        # and because `_is_consistent` accepts everything, it decides the
        # answer outright -- the same 3 components over 5 zones assign to ZA,
        # ZD or ZB purely as a function of the seed. Sorting it here would
        # make the solver deterministic, which is a behaviour change no
        # differential against a live Python run could detect. Handing Rust
        # the live order instead keeps the composed behaviour bit-identical
        # to the pre-migration code on every run, hash seed included.
        zone_names: list[str] = []
        zone_index: dict[str, int] = {}
        candidate_indices: list[list[int]] = []
        for comp in sorted_components:
            row = []
            for name in self._candidates[comp]:
                if name not in zone_index:
                    zone_index[name] = len(zone_names)
                    zone_names.append(name)
                row.append(zone_index[name])
            candidate_indices.append(row)

        chosen = _rust.zone_backtrack(candidate_indices)
        assignment = (
            None
            if chosen is None
            else {comp: zone_names[z] for comp, z in zip(sorted_components, chosen, strict=True)}
        )

        if assignment is None:
            # No solution found (shouldn't happen with current constraints)
            return ZoneAssignment(
                assignments={},
                unassigned=self.components,
                conflicts=[("*", "backtracking", "No valid assignment found")],
            )

        return ZoneAssignment(
            assignments=assignment,
            unassigned=[],
            conflicts=[],
        )
