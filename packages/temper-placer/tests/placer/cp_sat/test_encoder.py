"""U3: Tests for the PCL→CP-SAT constraint encoder.

Verifies that each supported PCL constraint type compiles to correct
CP-SAT model constraints and that unsupported types log appropriate
warnings.
"""

from __future__ import annotations

import logging

import pytest

from temper_placer.pcl.constraints import (
    AdjacentConstraint,
    AlignedConstraint,
    Axis,
    BoardSide,
    ConstraintTier,
    EdgeType,
    EnclosingConstraint,
    OnSideConstraint,
    SeparatedConstraint,
)
from temper_placer.pcl.parser import ConstraintCollection
from temper_placer.placer.cp_sat.encoder import (
    TYPE_HANDLERS,
    UNSUPPORTED_TYPES,
    compile_pcl_to_cp_sat,
)
from temper_placer.placer.cp_sat.model import (
    SolveStatus,
    build_cp_sat_model,
    solve_cp_sat_model,
)

# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture
def two_components() -> dict:
    """Two 10×10 mm components for pairwise constraint tests."""
    return {
        "C1": {"width_mm": 10.0, "height_mm": 10.0},
        "C2": {"width_mm": 10.0, "height_mm": 10.0},
    }


@pytest.fixture
def three_components() -> dict:
    """Three small components for region-membership tests."""
    return {
        "R1": {"width_mm": 5.0, "height_mm": 5.0},
        "R2": {"width_mm": 5.0, "height_mm": 5.0},
        "C1": {"width_mm": 6.0, "height_mm": 6.0},
    }


@pytest.fixture
def one_component() -> dict:
    """Single 10×10 mm component for edge-anchoring tests."""
    return {"Q1": {"width_mm": 10.0, "height_mm": 10.0}}


@pytest.fixture
def small_board() -> tuple[float, float]:
    """100×100 mm board."""
    return 100.0, 100.0


# ======================================================================
# Helpers
# ======================================================================


def _run(model, ctx, timeout_s: float = 10.0):
    """Convenience: solve and return the result."""
    from temper_placer.placer.cp_sat.model import solve_cp_sat_model

    return solve_cp_sat_model(model, ctx, timeout_s=timeout_s, log_progress=False)


# ======================================================================
# Tests: SeparatedConstraint
# ======================================================================


class TestSeparatedConstraint:
    """SeparatedConstraint → add_chebyshev_clearance."""

    def test_compile_and_solve(self, two_components, small_board):
        """A separated pair should be solvable with Chebyshev clearance."""
        bw, bh = small_board
        model, ctx = build_cp_sat_model(two_components, bw, bh)

        constraint = SeparatedConstraint(
            a="C1",
            b="C2",
            min_distance_mm=20.0,
            tier=ConstraintTier.HARD,
            because="Test HV/LV separation for safety isolation",
        )

        coll = ConstraintCollection(constraints=[constraint])
        compile_pcl_to_cp_sat(coll, two_components, model, ctx)

        result = _run(model, ctx)
        assert result.status in (
            SolveStatus.OPTIMAL,
            SolveStatus.FEASIBLE,
        ), f"Solve failed: {result.status}"

        # The solver must respect the Chebyshev edge-to-edge clearance.
        # For 10×10 components with 20 mm clearance, at least one of the
        # four gap directions must be ≥ 20 mm.
        x_a, y_a = result.positions["C1"]
        x_b, y_b = result.positions["C2"]
        gap = max(
            x_b - (x_a + 10.0),  # C2 is right of C1
            x_a - (x_b + 10.0),  # C1 is right of C2
            y_b - (y_a + 10.0),  # C2 is above C1
            y_a - (y_b + 10.0),  # C1 is above C2
        )
        assert gap >= 20.0 - 0.2, (
            f"Chebyshev clearance {gap:.2f}mm < 20.0mm "
            f"(C1=({x_a:.1f},{y_a:.1f}), C2=({x_b:.1f},{y_b:.1f}))"
        )

    def test_assumption_var_collected(self, two_components, small_board):
        """A separated constraint should produce an assumption var."""
        bw, bh = small_board
        model, ctx = build_cp_sat_model(two_components, bw, bh)

        constraint = SeparatedConstraint(
            a="C1",
            b="C2",
            min_distance_mm=20.0,
            tier=ConstraintTier.HARD,
            because="Assumption test",
        )

        coll = ConstraintCollection(constraints=[constraint])
        compile_pcl_to_cp_sat(coll, two_components, model, ctx)

        assert len(ctx.assumption_vars) == 1
        assert ctx.assumption_vars[0].Name().startswith("assump_sep_")


# ======================================================================
# Tests: EnclosingConstraint
# ======================================================================


class TestEnclosingConstraint:
    """EnclosingConstraint → add_region_membership."""

    def test_compile_and_solve(self, three_components, small_board):
        """Components constrained to a zone should stay inside."""
        bw, bh = small_board
        # Include a synthetic zone entry in the components dict.
        comps = dict(three_components)
        comps["HV_ZONE"] = {
            "x_min": 0.0,
            "x_max": 80.0,
            "y_min": 0.0,
            "y_max": 80.0,
        }

        model, ctx = build_cp_sat_model(comps, bw, bh)

        constraint = EnclosingConstraint(
            outer="HV_ZONE",
            inner=["R1", "R2", "C1"],
            tier=ConstraintTier.HARD,
            because="All HV components must be inside the HV zone",
        )

        coll = ConstraintCollection(constraints=[constraint])
        compile_pcl_to_cp_sat(coll, comps, model, ctx)

        result = _run(model, ctx)
        assert result.status in (
            SolveStatus.OPTIMAL,
            SolveStatus.FEASIBLE,
        ), f"Solve failed: {result.status}"

        for ref in ("R1", "R2", "C1"):
            x, y = result.positions[ref]
            w = comps[ref]["width_mm"]
            h = comps[ref]["height_mm"]
            assert x >= 0.0 - 0.1, f"{ref} x={x} < 0"
            assert x + w <= 80.0 + 0.1, f"{ref} right edge {x+w} > 80"
            assert y >= 0.0 - 0.1, f"{ref} y={y} < 0"
            assert y + h <= 80.0 + 0.1, f"{ref} top edge {y+h} > 80"

    def test_assumption_var_collected(self, three_components, small_board):
        """An enclosing constraint should produce an assumption var."""
        bw, bh = small_board
        comps = dict(three_components)
        comps["HV_ZONE"] = {
            "x_min": 0.0,
            "x_max": 80.0,
            "y_min": 0.0,
            "y_max": 80.0,
        }

        model, ctx = build_cp_sat_model(comps, bw, bh)

        constraint = EnclosingConstraint(
            outer="HV_ZONE",
            inner=["R1", "R2"],
            tier=ConstraintTier.HARD,
            because="Assumption test for enclosing",
        )

        coll = ConstraintCollection(constraints=[constraint])
        compile_pcl_to_cp_sat(coll, comps, model, ctx)

        assert len(ctx.assumption_vars) == 1
        assert ctx.assumption_vars[0].Name().startswith("assump_enc_")


# ======================================================================
# Tests: OnSideConstraint
# ======================================================================


class TestOnSideConstraint:
    """OnSideConstraint → add_edge_anchoring."""

    def test_compile_and_solve(self, one_component, small_board):
        """Components should be placed within the max distance of the edge."""
        bw, bh = small_board
        model, ctx = build_cp_sat_model(one_component, bw, bh)

        constraint = OnSideConstraint(
            components=["Q1"],
            side=BoardSide.BOTTOM,
            edge=EdgeType.NEAR,
            max_distance_mm=15.0,
            tier=ConstraintTier.HARD,
            because="Q1 must be near the bottom edge for thermal management",
        )

        coll = ConstraintCollection(constraints=[constraint])
        compile_pcl_to_cp_sat(coll, one_component, model, ctx)

        result = _run(model, ctx)
        assert result.status in (
            SolveStatus.OPTIMAL,
            SolveStatus.FEASIBLE,
        ), f"Solve failed: {result.status}"

        x_q1, y_q1 = result.positions["Q1"]
        # y_start must be ≤ 15 mm from the bottom edge.
        assert y_q1 <= 15.0 + 0.1, (
            f"Q1 y={y_q1:.1f} > 15.0 from bottom edge"
        )

    def test_assumption_var_collected(self, one_component, small_board):
        """An on-side constraint should produce an assumption var."""
        bw, bh = small_board
        model, ctx = build_cp_sat_model(one_component, bw, bh)

        constraint = OnSideConstraint(
            components=["Q1"],
            side=BoardSide.BOTTOM,
            edge=EdgeType.NEAR,
            max_distance_mm=15.0,
            tier=ConstraintTier.HARD,
            because="Assumption test for on-side",
        )

        coll = ConstraintCollection(constraints=[constraint])
        compile_pcl_to_cp_sat(coll, one_component, model, ctx)

        assert len(ctx.assumption_vars) == 1
        assert ctx.assumption_vars[0].Name().startswith("assump_side_")

    def test_multiple_components(self, three_components, small_board):
        """Multiple components should all be near the edge."""
        bw, bh = small_board
        model, ctx = build_cp_sat_model(three_components, bw, bh)

        constraint = OnSideConstraint(
            components=["R1", "R2", "C1"],
            side=BoardSide.BOTTOM,
            edge=EdgeType.NEAR,
            max_distance_mm=20.0,
            tier=ConstraintTier.HARD,
            because="All test components must be near bottom edge",
        )

        coll = ConstraintCollection(constraints=[constraint])
        compile_pcl_to_cp_sat(coll, three_components, model, ctx)

        result = _run(model, ctx)
        assert result.status in (
            SolveStatus.OPTIMAL,
            SolveStatus.FEASIBLE,
        ), f"Solve failed: {result.status}"

        for ref in ("R1", "R2", "C1"):
            x, y = result.positions[ref]  # noqa: F841
            assert y <= 20.0 + 0.1, f"{ref} y={y:.1f} > 20.0 from bottom edge"
            assert y >= 0.0 - 0.1, f"{ref} y={y:.1f} < 0 (off board)"


# ======================================================================
# Tests: AdjacentConstraint
# ======================================================================


class TestAdjacentConstraint:
    """AdjacentConstraint → add_proximity."""

    def test_compile_and_solve(self, two_components, small_board):
        """Adjacent components should be placed within max_distance."""
        bw, bh = small_board
        model, ctx = build_cp_sat_model(two_components, bw, bh)

        constraint = AdjacentConstraint(
            a="C1",
            b="C2",
            max_distance_mm=15.0,
            tier=ConstraintTier.HARD,
            because="Commutation loop components must be close",
        )

        coll = ConstraintCollection(constraints=[constraint])
        compile_pcl_to_cp_sat(coll, two_components, model, ctx)

        result = _run(model, ctx)
        assert result.status in (
            SolveStatus.OPTIMAL,
            SolveStatus.FEASIBLE,
        ), f"Solve failed: {result.status}"

        x_a, y_a = result.positions["C1"]
        x_b, y_b = result.positions["C2"]

        # Chebyshev edge-to-edge separation must be ≤ max_distance.
        # The worst-case of the 4 proximity inequalities:
        #   x_b ≤ x_a + w_a + max_d  →  x_b - (x_a + 10) ≤ 15
        #   x_a ≤ x_b + w_b + max_d  →  x_a - (x_b + 10) ≤ 15
        #   y_b ≤ y_a + h_a + max_d  →  y_b - (y_a + 10) ≤ 15
        #   y_a ≤ y_b + h_b + max_d  →  y_a - (y_b + 10) ≤ 15
        span = max(
            x_b - (x_a + 10.0),
            x_a - (x_b + 10.0),
            y_b - (y_a + 10.0),
            y_a - (y_b + 10.0),
        )
        assert span <= 15.0 + 0.2, (
            f"Adjacency span {span:.2f}mm > 15.0mm "
            f"(C1=({x_a:.1f},{y_a:.1f}), C2=({x_b:.1f},{y_b:.1f}))"
        )

    def test_assumption_var_collected(self, two_components, small_board):
        """An adjacent constraint should produce an assumption var."""
        bw, bh = small_board
        model, ctx = build_cp_sat_model(two_components, bw, bh)

        constraint = AdjacentConstraint(
            a="C1",
            b="C2",
            max_distance_mm=15.0,
            tier=ConstraintTier.HARD,
            because="Assumption test for adjacent",
        )

        coll = ConstraintCollection(constraints=[constraint])
        compile_pcl_to_cp_sat(coll, two_components, model, ctx)

        assert len(ctx.assumption_vars) == 1
        assert ctx.assumption_vars[0].Name().startswith("assump_adj_")


# ======================================================================
# Tests: unsupported types
# ======================================================================


class TestUnsupportedConstraints:
    """Deferred constraint types should log warnings and be skipped."""

    def test_aligned_constraint_logs_warning(self, two_components, small_board, caplog):
        """AlignedConstraint should log a warning and not raise."""
        bw, bh = small_board
        model, ctx = build_cp_sat_model(two_components, bw, bh)

        constraint = AlignedConstraint(
            components=["C1", "C2"],
            axis=Axis.X,
            tier=ConstraintTier.SOFT,
            because="Alignment test for visual consistency",
        )

        coll = ConstraintCollection(constraints=[constraint])

        caplog.clear()
        with caplog.at_level(logging.WARNING):
            compile_pcl_to_cp_sat(coll, two_components, model, ctx)

        assert any(
            "not supported by CP-SAT v1" in rec.message
            for rec in caplog.records
        ), f"Expected warning not found. Records: {[r.message for r in caplog.records]}"

        # Model should still be solvable with just NoOverlap2D.
        result = _run(model, ctx)
        assert result.status in (
            SolveStatus.OPTIMAL,
            SolveStatus.FEASIBLE,
        ), f"Solve failed: {result.status}"

    def test_multiple_unsupported_log_warnings(
        self, two_components, small_board, caplog
    ):
        """Multiple unsupported constraints should each log a warning."""
        bw, bh = small_board
        model, ctx = build_cp_sat_model(two_components, bw, bh)

        coll = ConstraintCollection(
            constraints=[
                AlignedConstraint(
                    components=["C1", "C2"],
                    axis=Axis.X,
                    tier=ConstraintTier.SOFT,
                    because="Visual alignment test",
                ),
                AlignedConstraint(
                    components=["C1", "C2"],
                    axis=Axis.Y,
                    tier=ConstraintTier.SOFT,
                    because="Vertical alignment test",
                ),
            ]
        )

        caplog.clear()
        with caplog.at_level(logging.WARNING):
            compile_pcl_to_cp_sat(coll, two_components, model, ctx)

        warning_count = sum(
            1 for r in caplog.records if "not supported by CP-SAT v1" in r.message
        )
        assert warning_count == 2, (
            f"Expected 2 warnings, got {warning_count}"
        )

    def test_unsupported_types_defined(self):
        """UNSUPPORTED_TYPES should cover the 4 deferred types."""
        from temper_placer.pcl.constraints import ConstraintType

        expected = {
            ConstraintType.ALIGNED,
            ConstraintType.LOOP_AREA,
            ConstraintType.ANCHORED,
            ConstraintType.KEEPOUT,
        }
        assert UNSUPPORTED_TYPES == expected, (
            f"UNSUPPORTED_TYPES = {UNSUPPORTED_TYPES}, expected {expected}"
        )


# ======================================================================
# Tests: edge cases
# ======================================================================


class TestEdgeCases:
    """Boundary and error conditions."""

    def test_empty_constraint_collection(self, two_components, small_board):
        """An empty collection should still produce a solvable model."""
        bw, bh = small_board
        model, ctx = build_cp_sat_model(two_components, bw, bh)

        coll = ConstraintCollection(constraints=[])
        compile_pcl_to_cp_sat(coll, two_components, model, ctx)

        # NoOverlap2D + no side constraints should still be solvable.
        result = _run(model, ctx)
        assert result.status in (
            SolveStatus.OPTIMAL,
            SolveStatus.FEASIBLE,
        ), f"Solve failed: {result.status}"

        # No assumption vars from an empty collection.
        assert len(ctx.assumption_vars) == 0

    def test_multiple_constraint_types(self, two_components, small_board):
        """Multiple supported constraint types should compose."""
        bw, bh = small_board
        model, ctx = build_cp_sat_model(two_components, bw, bh)

        coll = ConstraintCollection(
            constraints=[
                AdjacentConstraint(
                    a="C1",
                    b="C2",
                    max_distance_mm=30.0,
                    tier=ConstraintTier.HARD,
                    because="Proximity in composed test",
                ),
                SeparatedConstraint(
                    a="C1",
                    b="C2",
                    min_distance_mm=5.0,
                    tier=ConstraintTier.HARD,
                    because="Separation in composed test",
                ),
            ]
        )

        compile_pcl_to_cp_sat(coll, two_components, model, ctx)

        result = _run(model, ctx)
        assert result.status in (
            SolveStatus.OPTIMAL,
            SolveStatus.FEASIBLE,
        ), f"Solve failed: {result.status}"

        # Both constraints should contribute assumption vars.
        assert len(ctx.assumption_vars) == 2

    def test_mixed_supported_and_unsupported(
        self, two_components, small_board, caplog
    ):
        """Supported and unsupported types should both be handled."""
        bw, bh = small_board
        model, ctx = build_cp_sat_model(two_components, bw, bh)

        coll = ConstraintCollection(
            constraints=[
                AdjacentConstraint(
                    a="C1",
                    b="C2",
                    max_distance_mm=30.0,
                    tier=ConstraintTier.HARD,
                    because="Proximity in mixed test",
                ),
                AlignedConstraint(
                    components=["C1", "C2"],
                    axis=Axis.X,
                    tier=ConstraintTier.SOFT,
                    because="Alignment in mixed test",
                ),
            ]
        )

        caplog.clear()
        with caplog.at_level(logging.WARNING):
            compile_pcl_to_cp_sat(coll, two_components, model, ctx)

        # One warning for the unsupported AlignedConstraint.
        assert any(
            "not supported by CP-SAT v1" in rec.message
            for rec in caplog.records
        )

        # Should still have 1 assumption var (from the AdjacentConstraint).
        assert len(ctx.assumption_vars) == 1

        # Solve should succeed
        result = _run(model, ctx)
        assert result.status in (
            SolveStatus.OPTIMAL,
            SolveStatus.FEASIBLE,
        ), f"Solve failed: {result.status}"


# ======================================================================
# Tests: roundtrip - encode, solve, verify
# ======================================================================


class TestRoundtrip:
    """Full encode → solve → verify cycle for each constraint type."""

    def test_roundtrip_separated(self, two_components, small_board):
        """Encode separated constraint, solve, and verify compliance."""
        bw, bh = small_board
        model, ctx = build_cp_sat_model(two_components, bw, bh)

        constraint = SeparatedConstraint(
            a="C1",
            b="C2",
            min_distance_mm=25.0,
            tier=ConstraintTier.HARD,
            because="Roundtrip test for HV/LV creepage clearance",
        )

        coll = ConstraintCollection(constraints=[constraint])
        compile_pcl_to_cp_sat(coll, two_components, model, ctx)

        result = _run(model, ctx, timeout_s=15.0)
        assert result.status in (
            SolveStatus.OPTIMAL,
            SolveStatus.FEASIBLE,
        ), f"Solve failed: {result.status}"

        # Verify Chebyshev clearance in solution.
        x_a, y_a = result.positions["C1"]
        x_b, y_b = result.positions["C2"]
        gap = max(
            x_b - (x_a + 10.0),
            x_a - (x_b + 10.0),
            y_b - (y_a + 10.0),
            y_a - (y_b + 10.0),
        )
        assert gap >= 25.0 - 0.2, (
            f"Roundtrip: Chebyshev clearance {gap:.2f}mm < 25.0mm"
        )

    def test_roundtrip_enclosing(self, three_components, small_board):
        """Encode enclosing constraint, solve, verify zone membership."""
        bw, bh = small_board
        comps = dict(three_components)
        comps["HV_ZONE"] = {
            "x_min": 10.0,
            "x_max": 90.0,
            "y_min": 10.0,
            "y_max": 90.0,
        }

        model, ctx = build_cp_sat_model(comps, bw, bh)

        constraint = EnclosingConstraint(
            outer="HV_ZONE",
            inner=["R1", "R2", "C1"],
            tier=ConstraintTier.HARD,
            because="Roundtrip test for HV zone enclosure",
        )

        coll = ConstraintCollection(constraints=[constraint])
        compile_pcl_to_cp_sat(coll, comps, model, ctx)

        result = _run(model, ctx, timeout_s=15.0)
        assert result.status in (
            SolveStatus.OPTIMAL,
            SolveStatus.FEASIBLE,
        ), f"Solve failed: {result.status}"

        for ref in ("R1", "R2", "C1"):
            x, y = result.positions[ref]
            w = comps[ref]["width_mm"]
            h = comps[ref]["height_mm"]
            assert x >= 10.0 - 0.1, f"{ref} x={x} < 10"
            assert x + w <= 90.0 + 0.1, f"{ref} right edge {x+w} > 90"
            assert y >= 10.0 - 0.1, f"{ref} y={y} < 10"
            assert y + h <= 90.0 + 0.1, f"{ref} top edge {y+h} > 90"

    def test_roundtrip_adjacent(self, two_components, small_board):
        """Encode adjacent constraint, solve, verify proximity."""
        bw, bh = small_board
        model, ctx = build_cp_sat_model(two_components, bw, bh)

        constraint = AdjacentConstraint(
            a="C1",
            b="C2",
            max_distance_mm=5.0,
            tier=ConstraintTier.HARD,
            because="Roundtrip test for commutation-loop adjacency",
        )

        coll = ConstraintCollection(constraints=[constraint])
        compile_pcl_to_cp_sat(coll, two_components, model, ctx)

        result = _run(model, ctx, timeout_s=15.0)
        assert result.status in (
            SolveStatus.OPTIMAL,
            SolveStatus.FEASIBLE,
        ), f"Solve failed: {result.status}"

        x_a, y_a = result.positions["C1"]
        x_b, y_b = result.positions["C2"]
        span = max(
            x_b - (x_a + 10.0),
            x_a - (x_b + 10.0),
            y_b - (y_a + 10.0),
            y_a - (y_b + 10.0),
        )
        assert span <= 5.0 + 0.2, (
            f"Roundtrip: adjacency span {span:.2f}mm > 5.0mm"
        )


# ======================================================================
# Tests: TYPE_HANDLERS dispatch table
# ======================================================================


class TestTypeHandlers:
    """The TYPE_HANDLERS dict should cover all supported types."""

    def test_supported_types_have_handlers(self):
        """Every supported type must have a registered handler."""
        from temper_placer.pcl.constraints import ConstraintType

        supported = {
            ConstraintType.SEPARATED,
            ConstraintType.ENCLOSING,
            ConstraintType.ON_SIDE,
            ConstraintType.ADJACENT,
        }
        registered = set(TYPE_HANDLERS.keys())
        assert supported == registered, (
            f"Mismatch: supported={supported}, registered={registered}"
        )

    def test_all_handlers_are_callable(self):
        """Every entry in TYPE_HANDLERS must be callable."""
        for ctype, handler in TYPE_HANDLERS.items():
            assert callable(handler), (
                f"Handler for {ctype} is not callable: {handler}"
            )
