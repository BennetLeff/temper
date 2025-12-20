"""
Tests for PCL constraint linter.

The linter detects impossible constraint combinations and provides
actionable error messages.
"""

import pytest

from temper_placer.pcl.constraints import (
    AdjacentConstraint,
    AlignedConstraint,
    Axis,
    ConstraintTier,
    SeparatedConstraint,
)
from temper_placer.pcl.linter import (
    LintError,
    LintResult,
    LintWarning,
    lint_constraints,
)
from temper_placer.core.netlist import Component, Netlist
from temper_placer.core.board import Board


def _create_simple_netlist(component_refs: list[str]) -> Netlist:
    """Create a minimal netlist for testing."""
    from temper_placer.core.netlist import Component

    components = [
        Component(
            ref=ref,
            footprint="TestFootprint",
            bounds=(5.0, 3.0),
            pins=[],
            net_class="Signal",
        )
        for ref in component_refs
    ]
    return Netlist(components=components, nets=[])


def _create_simple_board(width: float, height: float) -> Board:
    """Create a minimal board for testing."""
    return Board(
        width=width,
        height=height,
        zones=[],
        keepout_regions=[],
    )


class TestContradictions:
    """Test detection of contradictory constraints."""

    def test_adjacent_and_separated_contradiction(self):
        """Adjacent with small distance + separated with large distance = contradiction."""
        constraints = [
            AdjacentConstraint(
                a="Q1",
                b="Q2",
                max_distance_mm=5.0,
                tier=ConstraintTier.HARD,
                because="Must be close for commutation loop",
            ),
            SeparatedConstraint(
                a="Q1",
                b="Q2",
                min_distance_mm=20.0,
                tier=ConstraintTier.HARD,
                because="Need separation for isolation",
            ),
        ]
        netlist = _create_simple_netlist(["Q1", "Q2"])
        board = _create_simple_board(100, 80)

        result = lint_constraints(constraints, netlist, board)

        assert not result.passed
        assert len(result.errors) == 1
        error = result.errors[0]
        assert "contradiction" in error.message.lower()
        assert "Q1" in error.message
        assert "Q2" in error.message
        assert error.constraint_ids is not None
        assert len(error.constraint_ids) == 2

    def test_no_contradiction_when_distances_compatible(self):
        """Adjacent max=20mm + separated min=5mm is OK."""
        constraints = [
            AdjacentConstraint(
                a="Q1",
                b="Q2",
                max_distance_mm=20.0,
                tier=ConstraintTier.STRONG,
                because="Should be close",
            ),
            SeparatedConstraint(
                a="Q1",
                b="Q2",
                min_distance_mm=5.0,
                tier=ConstraintTier.STRONG,
                because="Need some clearance",
            ),
        ]
        netlist = _create_simple_netlist(["Q1", "Q2"])
        board = _create_simple_board(100, 80)

        result = lint_constraints(constraints, netlist, board)

        assert result.passed
        assert len(result.errors) == 0


class TestCircularDependencies:
    """Test detection of circular adjacency chains."""

    def test_detects_simple_circular_adjacency(self):
        """A→B→C→A creates circular adjacency."""
        constraints = [
            AdjacentConstraint(
                a="A",
                b="B",
                max_distance_mm=5.0,
                tier=ConstraintTier.HARD,
                because="A should be near B",
            ),
            AdjacentConstraint(
                a="B",
                b="C",
                max_distance_mm=5.0,
                tier=ConstraintTier.HARD,
                because="B should be near C",
            ),
            AdjacentConstraint(
                a="C",
                b="A",
                max_distance_mm=5.0,
                tier=ConstraintTier.HARD,
                because="C should be near A",
            ),
        ]
        netlist = _create_simple_netlist(["A", "B", "C"])
        board = _create_simple_board(100, 80)

        result = lint_constraints(constraints, netlist, board)

        # Circular adjacency is a warning, not error (might be satisfiable)
        assert len(result.warnings) >= 1
        warning = result.warnings[0]
        assert "circular" in warning.message.lower() or "cycle" in warning.message.lower()

    def test_no_warning_for_acyclic_adjacency(self):
        """A→B→C is fine (no cycle)."""
        constraints = [
            AdjacentConstraint(
                a="A",
                b="B",
                max_distance_mm=5.0,
                tier=ConstraintTier.HARD,
                because="A should be near B",
            ),
            AdjacentConstraint(
                a="B",
                b="C",
                max_distance_mm=5.0,
                tier=ConstraintTier.HARD,
                because="B should be near C",
            ),
        ]
        netlist = _create_simple_netlist(["A", "B", "C"])
        board = _create_simple_board(100, 80)

        result = lint_constraints(constraints, netlist, board)

        # No cycle warnings
        cycle_warnings = [
            w
            for w in result.warnings
            if "circular" in w.message.lower() or "cycle" in w.message.lower()
        ]
        assert len(cycle_warnings) == 0


class TestInvalidReferences:
    """Test detection of invalid component/zone references."""

    def test_detects_invalid_component_ref(self):
        """Constraint references component not in netlist."""
        constraints = [
            AdjacentConstraint(
                a="Q1",
                b="Q_NONEXISTENT",
                max_distance_mm=5.0,
                tier=ConstraintTier.HARD,
                because="Test constraint",
            ),
        ]
        netlist = _create_simple_netlist(["Q1", "Q2"])
        board = _create_simple_board(100, 80)

        result = lint_constraints(constraints, netlist, board)

        assert not result.passed
        assert len(result.errors) >= 1
        error = result.errors[0]
        assert "Q_NONEXISTENT" in error.message
        assert "not found" in error.message.lower() or "invalid" in error.message.lower()

    def test_passes_when_all_refs_valid(self):
        """All component refs exist in netlist."""
        constraints = [
            AdjacentConstraint(
                a="Q1",
                b="Q2",
                max_distance_mm=5.0,
                tier=ConstraintTier.HARD,
                because="Test constraint",
            ),
        ]
        netlist = _create_simple_netlist(["Q1", "Q2", "Q3"])
        board = _create_simple_board(100, 80)

        result = lint_constraints(constraints, netlist, board)

        # No invalid reference errors
        ref_errors = [e for e in result.errors if "not found" in e.message.lower()]
        assert len(ref_errors) == 0


class TestUnreasonableDistances:
    """Test detection of distances larger than board."""

    def test_warns_on_max_distance_exceeds_board(self):
        """Adjacent max_distance > board diagonal is suspicious."""
        constraints = [
            AdjacentConstraint(
                a="Q1",
                b="Q2",
                max_distance_mm=500.0,  # Board is 100x80mm
                tier=ConstraintTier.STRONG,
                because="Test constraint",
            ),
        ]
        netlist = _create_simple_netlist(["Q1", "Q2"])
        board = _create_simple_board(100, 80)  # Diagonal ~128mm

        result = lint_constraints(constraints, netlist, board)

        # Should have warning about unreasonable distance
        assert len(result.warnings) >= 1
        warning = result.warnings[0]
        assert "distance" in warning.message.lower()
        assert "board" in warning.message.lower() or "unreasonable" in warning.message.lower()

    def test_no_warning_for_reasonable_distances(self):
        """Adjacent max_distance < board diagonal is fine."""
        constraints = [
            AdjacentConstraint(
                a="Q1",
                b="Q2",
                max_distance_mm=50.0,  # Well within 100x80mm board
                tier=ConstraintTier.STRONG,
                because="Test constraint",
            ),
        ]
        netlist = _create_simple_netlist(["Q1", "Q2"])
        board = _create_simple_board(100, 80)

        result = lint_constraints(constraints, netlist, board)

        # No distance warnings
        dist_warnings = [w for w in result.warnings if "distance" in w.message.lower()]
        assert len(dist_warnings) == 0


class TestAlignmentValidation:
    """Test aligned constraint validation."""

    def test_aligned_requires_multiple_components(self):
        """Aligned constraint with single component is invalid during construction."""
        # AlignedConstraint.__init__ raises ValueError for < 2 components
        with pytest.raises(ValueError, match="at least 2 components"):
            AlignedConstraint(
                components=["Q1"],  # Only one component
                axis=Axis.X,
                tier=ConstraintTier.SOFT,
                because="Test alignment for single component",
            )

    def test_aligned_passes_with_multiple_components(self):
        """Aligned constraint with 2+ components is valid."""
        constraints = [
            AlignedConstraint(
                components=["Q1", "Q2", "Q3"],
                axis=Axis.X,
                tier=ConstraintTier.SOFT,
                because="Test alignment",
            ),
        ]
        netlist = _create_simple_netlist(["Q1", "Q2", "Q3"])
        board = _create_simple_board(100, 80)

        result = lint_constraints(constraints, netlist, board)

        # No alignment errors
        align_errors = [e for e in result.errors if "aligned" in e.message.lower()]
        assert len(align_errors) == 0


class TestLintResult:
    """Test LintResult data structure."""

    def test_empty_result_passes(self):
        """Result with no errors/warnings passes."""
        result = LintResult(errors=[], warnings=[])
        assert result.passed

    def test_result_with_errors_fails(self):
        """Result with errors does not pass."""
        result = LintResult(
            errors=[
                LintError(
                    message="Test error",
                    constraint_ids=["test-1"],
                )
            ],
            warnings=[],
        )
        assert not result.passed

    def test_result_with_only_warnings_passes(self):
        """Warnings don't prevent passing."""
        result = LintResult(
            errors=[],
            warnings=[
                LintWarning(
                    message="Test warning",
                    constraint_ids=["test-1"],
                )
            ],
        )
        assert result.passed
