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

Wave 4, Phase 4: the compute is migrated to Rust in the
``temper-constraint-compiler`` crate (see ``packages/temper-constraint-compiler/
VERIFICATION.md``). This module is a delegation shim: the compiled filter and
scorer are Rust pyclasses holding pre-compiled constraint data (marshalled
once via ``constraints._payload``), the helper methods delegate to Rust
pyfunctions, and ``validate`` reassembles the Rust-computed error list into
``ValidationError`` objects. The pre-migration implementation is pinned
verbatim as the differential oracle (``tests/constraints/
_compiler_py_oracle.py``).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist

import temper_constraint_compiler as _rust  # type: ignore[import-untyped]

from temper_placer._constraint_types import PlacementConstraints
from temper_placer.constraints._payload import build_payload

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
        compiled = _rust.CompiledSlotFilter(  # type: ignore[attr-defined]
            build_payload(self.constraints, self.board_bounds)
        )

        def filter_slot(
            slot: tuple[float, float],
            component: str,
            placements: dict[str, tuple[float, float]],
        ) -> bool:
            return compiled(slot, component, placements)

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
        compiled = _rust.CompiledSlotScorer(  # type: ignore[attr-defined]
            build_payload(self.constraints, self.board_bounds)
        )

        def score_slot(
            slot: tuple[float, float],
            component: str,
            placements: dict[str, tuple[float, float]],
        ) -> float:
            return compiled(slot, component, placements)

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
        # The oracle iterates these SETS; the shim passes the same sets' exact
        # iteration order (same process, same elements => same order) so the
        # typo-suggestion first-match and the "Available zones:" join match
        # bit-for-bit (see VERIFICATION.md).
        component_refs = {c.ref for c in netlist.components}
        zone_names = {z.name for z in self.constraints.zones}
        error_dicts = _rust.validate_constraints(  # type: ignore[attr-defined]
            build_payload(self.constraints, self.board_bounds),
            list(component_refs),
            list(zone_names),
        )
        return [
            ValidationError(
                constraint_type=ed["constraint_type"],
                message=ed["message"],
                component=ed["component"],
                suggestion=ed["suggestion"],
            )
            for ed in error_dicts
        ]

    # Helper methods — all compute in Rust (bit-identical formulas).

    def _distance(self, p1: tuple[float, float], p2: tuple[float, float]) -> float:
        """Euclidean distance between two points."""
        return _rust.constraint_distance(p1, p2)  # type: ignore[attr-defined]

    def _centroid(self, points: list[tuple[float, float]]) -> tuple[float, float]:
        """Compute centroid of point set (Neumaier-compensated sum, like
        CPython's builtin ``sum``)."""
        return _rust.constraint_centroid(points)  # type: ignore[attr-defined]

    def _min_edge_distance(self, slot: tuple[float, float]) -> float:
        """Minimum distance from slot to any board edge."""
        return _rust.constraint_min_edge_distance(slot, self.board_bounds)  # type: ignore[attr-defined]

    def _in_escape_zone(self, slot: tuple[float, float], comp_pos: tuple[float, float], ec) -> bool:
        """Check if slot is within escape clearance zone."""
        clearance = ec.clearance_mm if ec.clearance_mm is not None else 3.0
        return self._distance(slot, comp_pos) < clearance

    def _in_corridor(self, slot: tuple[float, float], corridor, placements: dict) -> bool:
        """Check if slot is within routing corridor."""
        if corridor.from_component not in placements or corridor.to_component not in placements:
            return False
        p1 = placements[corridor.from_component]
        p2 = placements[corridor.to_component]
        return self._point_to_segment_distance(slot, p1, p2) < corridor.width_mm / 2

    def _point_to_segment_distance(
        self,
        p: tuple[float, float],
        a: tuple[float, float],
        b: tuple[float, float],
    ) -> float:
        """Compute minimum distance from point to line segment."""
        return _rust.constraint_point_to_segment_distance(p, a, b)  # type: ignore[attr-defined]

    def _in_zone(self, slot: tuple[float, float], zone) -> bool:
        """Check if slot is within zone bounds."""
        return _rust.constraint_in_zone(slot, zone.bounds)  # type: ignore[attr-defined]

    def _find_similar(self, name: str, options: set[str]) -> str | None:
        """Find similar component name in options.

        ``options`` is iterated in the caller's set order (first prefix match
        wins); ``list(options)`` preserves that exact order for Rust.
        """
        return _rust.constraint_find_similar(name, list(options))  # type: ignore[attr-defined]
