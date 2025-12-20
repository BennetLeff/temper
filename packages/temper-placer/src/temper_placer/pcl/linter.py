"""
PCL constraint linter.

Detects impossible constraint combinations, invalid references,
and other issues before optimization.
"""

from dataclasses import dataclass, field
from typing import Any
import math

from temper_placer.pcl.constraints import (
    AdjacentConstraint,
    AlignedConstraint,
    AnchoredConstraint,
    BaseConstraint,
    EnclosingConstraint,
    LoopAreaConstraint,
    OnSideConstraint,
    SeparatedConstraint,
)
from temper_placer.core.netlist import Netlist
from temper_placer.core.board import Board


@dataclass
class LintError:
    """A linting error that prevents valid placement."""

    message: str
    constraint_ids: list[str] | None = None
    severity: str = "error"


@dataclass
class LintWarning:
    """A linting warning that flags suspicious constraints."""

    message: str
    constraint_ids: list[str] | None = None
    severity: str = "warning"


@dataclass
class LintResult:
    """Result of linting a constraint set."""

    errors: list[LintError] = field(default_factory=list)
    warnings: list[LintWarning] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """Lint passes if there are no errors (warnings are OK)."""
        return len(self.errors) == 0


def lint_constraints(
    constraints: list[BaseConstraint],
    netlist: Netlist,
    board: Board,
) -> LintResult:
    """
    Lint a set of PCL constraints.

    Args:
        constraints: List of PCL constraints to lint.
        netlist: Netlist for component reference validation.
        board: Board for geometry validation.

    Returns:
        LintResult with errors and warnings.
    """
    result = LintResult()

    # Build component ref set for validation
    valid_refs = {comp.ref for comp in netlist.components}

    # Check each constraint
    for constraint in constraints:
        # Check invalid component references
        _check_invalid_refs(constraint, valid_refs, result)

        # Check constraint-specific issues
        if isinstance(constraint, AlignedConstraint):
            _check_aligned_constraint(constraint, result)
        elif isinstance(constraint, AdjacentConstraint):
            _check_adjacent_constraint(constraint, board, result)

    # Check for contradictions between constraints
    _check_contradictions(constraints, result)

    # Check for circular adjacencies
    _check_circular_adjacencies(constraints, result)

    return result


def _check_invalid_refs(
    constraint: BaseConstraint,
    valid_refs: set[str],
    result: LintResult,
) -> None:
    """Check for invalid component references in a constraint."""
    refs_to_check: list[str] = []

    if isinstance(constraint, AdjacentConstraint):
        refs_to_check = [constraint.a, constraint.b]
    elif isinstance(constraint, SeparatedConstraint):
        refs_to_check = [constraint.a, constraint.b]
    elif isinstance(constraint, EnclosingConstraint):
        refs_to_check = constraint.inner
    elif isinstance(constraint, AlignedConstraint):
        refs_to_check = constraint.components
    elif isinstance(constraint, OnSideConstraint):
        refs_to_check = constraint.components
    elif isinstance(constraint, AnchoredConstraint):
        refs_to_check = [constraint.component]

    for ref in refs_to_check:
        if ref not in valid_refs:
            result.errors.append(
                LintError(
                    message=f"Component '{ref}' not found in netlist",
                    constraint_ids=[constraint.id] if hasattr(constraint, "id") else None,
                )
            )


def _check_aligned_constraint(
    constraint: AlignedConstraint,
    result: LintResult,
) -> None:
    """Check aligned constraint has multiple components."""
    if len(constraint.components) < 2:
        result.errors.append(
            LintError(
                message=f"Aligned constraint requires at least 2 components, got {len(constraint.components)}",
                constraint_ids=[constraint.id] if hasattr(constraint, "id") else None,
            )
        )


def _check_adjacent_constraint(
    constraint: AdjacentConstraint,
    board: Board,
    result: LintResult,
) -> None:
    """Check adjacent constraint for unreasonable distances."""
    # Board diagonal is the maximum possible distance
    board_diagonal = math.sqrt(board.width**2 + board.height**2)

    if constraint.max_distance_mm > board_diagonal * 1.1:  # Allow 10% margin
        result.warnings.append(
            LintWarning(
                message=(
                    f"Adjacent max_distance ({constraint.max_distance_mm:.1f}mm) exceeds "
                    f"board diagonal ({board_diagonal:.1f}mm). This constraint may be trivially satisfied."
                ),
                constraint_ids=[constraint.id] if hasattr(constraint, "id") else None,
            )
        )


def _check_contradictions(
    constraints: list[BaseConstraint],
    result: LintResult,
) -> None:
    """
    Check for contradictory constraints.

    Examples:
    - adjacent(A, B, max=5mm) AND separated(A, B, min=20mm)
    """
    # Build maps: (a, b) -> (distance, constraint_id)
    adjacency_map: dict[tuple[str, str], tuple[float, str]] = {}
    separation_map: dict[tuple[str, str], tuple[float, str]] = {}

    for constraint in constraints:
        if isinstance(constraint, AdjacentConstraint):
            key = tuple(sorted([constraint.a, constraint.b]))
            if key not in adjacency_map or constraint.max_distance_mm < adjacency_map[key][0]:
                adjacency_map[key] = (constraint.max_distance_mm, constraint.id)

        elif isinstance(constraint, SeparatedConstraint):
            # Handle pairwise separation
            key = tuple(sorted([constraint.a, constraint.b]))
            if (
                key not in separation_map
                or constraint.min_distance_mm > separation_map[key][0]
            ):
                separation_map[key] = (constraint.min_distance_mm, constraint.id)

    # Check for contradictions
    for key, (max_distance, adj_id) in adjacency_map.items():
        if key in separation_map:
            min_distance, sep_id = separation_map[key]
            if min_distance > max_distance:
                a, b = key
                result.errors.append(
                    LintError(
                        message=(
                            f"Contradiction: components '{a}' and '{b}' must be adjacent "
                            f"(≤{max_distance:.1f}mm) but also separated (≥{min_distance:.1f}mm)"
                        ),
                        constraint_ids=[adj_id, sep_id],
                    )
                )


def _check_circular_adjacencies(
    constraints: list[BaseConstraint],
    result: LintResult,
) -> None:
    """
    Check for circular adjacency chains (A→B→C→A).

    This is a warning, not an error, since it might be geometrically satisfiable
    depending on distances.
    """
    # Build adjacency graph
    adjacency_graph: dict[str, set[str]] = {}

    for constraint in constraints:
        if isinstance(constraint, AdjacentConstraint):
            a, b = constraint.a, constraint.b
            if a not in adjacency_graph:
                adjacency_graph[a] = set()
            if b not in adjacency_graph:
                adjacency_graph[b] = set()
            adjacency_graph[a].add(b)
            adjacency_graph[b].add(a)

    # DFS to detect cycles
    visited = set()
    path: list[str] = []

    def has_cycle(node: str, parent: str | None) -> bool:
        visited.add(node)
        path.append(node)

        for neighbor in adjacency_graph.get(node, set()):
            if neighbor == parent:
                continue  # Don't revisit parent (undirected graph)

            if neighbor in path:
                # Found cycle
                cycle_start = path.index(neighbor)
                cycle = path[cycle_start:] + [neighbor]
                result.warnings.append(
                    LintWarning(
                        message=f"Circular adjacency detected: {' → '.join(cycle)}",
                        constraint_ids=None,
                    )
                )
                return True

            if neighbor not in visited:
                if has_cycle(neighbor, node):
                    return True

        path.pop()
        return False

    # Check all connected components
    for node in adjacency_graph:
        if node not in visited:
            has_cycle(node, None)
