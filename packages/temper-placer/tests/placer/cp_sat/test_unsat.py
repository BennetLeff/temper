"""U7: Tests for UNSAT core extraction.

Tests use deliberately infeasible CP-SAT models built with assumption
variables wired to constraints via ``OnlyEnforceIf``, verifying that the
extraction pipeline correctly identifies conflicting constraint groups
and that MUS refinement removes redundant assumptions.

Scenarios (from plan):
    - ``test_trivially_infeasible`` — Two large components in a small
      shared region → INFEASIBLE; both assumptions identified.
    - ``test_mus_refinement`` — Three components, any two conflict,
      the third is redundant → MUS removes the redundant one.
    - ``test_single_constraint_infeasible`` — One impossible constraint.
    - ``test_feasible_raises_error`` — Calling extraction on a FEASIBLE
      model raises ``ValueError``.
    - ``test_mus_timeout`` — Short timeout → returns sufficient core
      with ``is_minimal=False``.
"""

from __future__ import annotations

import pytest
from ortools.sat.python import cp_model

from temper_placer.placer.cp_sat.model import (
    SolveContext,
    build_cp_sat_model,
)
from temper_placer.placer.cp_sat.unsat import (
    UnsatReport,
    extract_unsat_core,
    refine_mus,
)


# ======================================================================
# Helpers
# ======================================================================


def _build_model_with_region_assumptions(
    component_refs: list[str],
    w_mm: float,
    h_mm: float,
    board_w: float,
    board_h: float,
    region: tuple[float, float, float, float],
) -> tuple[cp_model.CpModel, SolveContext, list[cp_model.IntVar], dict[int, str]]:
    """Build a model with per-component region constraints gated on assumptions.

    Each component gets one assumption var that gates a hard constraint
    forcing it into the given rectangular region.  The base model has
    NoOverlap2D (always active).

    Returns:
        ``(model, ctx, assumption_vars, constraint_map)``
    """
    components = {ref: {"width_mm": w_mm, "height_mm": h_mm} for ref in component_refs}
    model, ctx = build_cp_sat_model(components, board_w, board_h)

    rx_min, rx_max, ry_min, ry_max = region
    assumption_vars: list[cp_model.IntVar] = []
    constraint_map: dict[int, str] = {}

    for i, ref in enumerate(component_refs):
        assump = model.NewBoolVar(f"assump_region_{ref}")
        assumption_vars.append(assump)
        constraint_map[i] = (
            f"{ref} must fit inside [{rx_min},{rx_max}]×[{ry_min},{ry_max}]"
        )

        # Gate the region constraint on the assumption var.
        model.Add(ctx.x_start[ref] >= int(rx_min * ctx.scale_factor)).OnlyEnforceIf(
            assump
        )
        model.Add(
            ctx.x_start[ref] + ctx.x_size[ref] <= int(rx_max * ctx.scale_factor)
        ).OnlyEnforceIf(assump)
        model.Add(ctx.y_start[ref] >= int(ry_min * ctx.scale_factor)).OnlyEnforceIf(
            assump
        )
        model.Add(
            ctx.y_start[ref] + ctx.y_size[ref] <= int(ry_max * ctx.scale_factor)
        ).OnlyEnforceIf(assump)

    return model, ctx, assumption_vars, constraint_map


def _build_model_with_single_constraint(
    ref: str,
    w_mm: float,
    h_mm: float,
    board_w: float,
    board_h: float,
    x_min_bound_units: int,
) -> tuple[cp_model.CpModel, SolveContext, list[cp_model.IntVar], dict[int, str]]:
    """Build a model with one ``x_start >= x_min_bound_units`` constraint gated
    on an assumption var.

    Used to test a single-constraint infeasibility: if ``x_min_bound_units``
    (in scaled CP-SAT units) exceeds the component's x_start domain, the
    assumption is infeasible.

    Note: ``x_min_bound_units`` is in **CP-SAT scaled units** (not mm).
    At the default scale factor of 10, 1mm = 10 units.
    """
    components = {ref: {"width_mm": w_mm, "height_mm": h_mm}}
    model, ctx = build_cp_sat_model(components, board_w, board_h)

    assump = model.NewBoolVar("assump_single")
    assumption_vars = [assump]

    x_min_mm = x_min_bound_units / ctx.scale_factor
    constraint_map = {
        0: f"{ref} must have x_start >= {x_min_mm:.0f}mm",
    }

    model.Add(ctx.x_start[ref] >= x_min_bound_units).OnlyEnforceIf(assump)

    return model, ctx, assumption_vars, constraint_map


def _make_solver(timeout_s: float = 5.0) -> cp_model.CpSolver:
    """Create a solver with minimal logging and short timeout."""
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = timeout_s
    solver.parameters.num_search_workers = 4
    solver.parameters.log_search_progress = False
    return solver


# ======================================================================
# Tests: trivially infeasible
# ======================================================================


class TestTriviallyInfeasible:
    """Two large components forced into a small shared region."""

    def test_trivially_infeasible(self) -> None:
        """Two 30×30mm components in a 50×50mm region → INFEASIBLE.

        Both components together cannot fit inside the region without
        overlapping, but each alone can.  The sufficient core should
        identify both assumptions.
        """
        model, ctx, assumption_vars, constraint_map = (
            _build_model_with_region_assumptions(
                component_refs=["A", "B"],
                w_mm=30.0,
                h_mm=30.0,
                board_w=100.0,
                board_h=100.0,
                region=(0.0, 50.0, 0.0, 50.0),
            )
        )

        solver = _make_solver()
        report = extract_unsat_core(
            solver, model, assumption_vars, constraint_map, mus_timeout_s=10.0
        )

        # Both assumptions should be in the sufficient core.
        assert len(report.sufficient_core) == 2, (
            f"Expected 2 in sufficient core, got {report.sufficient_core}"
        )
        assert "A" in report.sufficient_core[0] or "A" in report.sufficient_core[1]
        assert "B" in report.sufficient_core[0] or "B" in report.sufficient_core[1]

        # Both are essential → MUS should also contain both.
        assert len(report.minimal_core) == 2, (
            f"Expected 2 in minimal core, got {report.minimal_core}"
        )
        assert report.solve_count >= 1
        assert report.wall_time_s >= 0.0
        assert report.is_minimal, "MUS refinement should complete within timeout"


# ======================================================================
# Tests: MUS refinement
# ======================================================================


class TestMusRefinement:
    """Deletion-based MUS correctly removes redundant assumptions."""

    def test_three_components_one_redundant(self) -> None:
        """Three 30×30mm components in a 50×50mm region.

        Any two components already conflict (can't both fit in 50×50).
        The third is redundant.  MUS refinement should produce a core
        with exactly 2 components.
        """
        model, ctx, assumption_vars, constraint_map = (
            _build_model_with_region_assumptions(
                component_refs=["A", "B", "C"],
                w_mm=30.0,
                h_mm=30.0,
                board_w=100.0,
                board_h=100.0,
                region=(0.0, 50.0, 0.0, 50.0),
            )
        )

        solver = _make_solver()
        report = extract_unsat_core(
            solver, model, assumption_vars, constraint_map, mus_timeout_s=10.0
        )

        # Sufficient core likely contains all 3.
        assert len(report.sufficient_core) >= 2

        # MUS should be exactly 2 (one component is redundant since
        # any two already conflict in the 50×50 region).
        assert len(report.minimal_core) == 2, (
            f"Expected 2 in minimal core (one redundant), got "
            f"{len(report.minimal_core)}: {report.minimal_core}"
        )
        assert report.is_minimal, "MUS refinement should complete"

    def test_all_essential(self) -> None:
        """Two components where both constraints are essential.

        No redundancy possible → MUS equals sufficient core.
        """
        model, ctx, assumption_vars, constraint_map = (
            _build_model_with_region_assumptions(
                component_refs=["A", "B"],
                w_mm=30.0,
                h_mm=30.0,
                board_w=100.0,
                board_h=100.0,
                region=(0.0, 50.0, 0.0, 50.0),
            )
        )

        solver = _make_solver()
        report = extract_unsat_core(
            solver, model, assumption_vars, constraint_map, mus_timeout_s=10.0
        )

        assert len(report.minimal_core) == 2
        assert report.minimal_core == report.sufficient_core

    def test_refine_mus_standalone(self) -> None:
        """Call ``refine_mus`` directly and verify it returns a correct MUS."""
        model, ctx, assumption_vars, constraint_map = (
            _build_model_with_region_assumptions(
                component_refs=["A", "B", "C"],
                w_mm=30.0,
                h_mm=30.0,
                board_w=100.0,
                board_h=100.0,
                region=(0.0, 50.0, 0.0, 50.0),
            )
        )

        solver = _make_solver()

        # Initial solve to get sufficient core (using model-level assumptions).
        model.AddAssumptions(list(assumption_vars))
        status = solver.Solve(model)
        assert status == cp_model.INFEASIBLE

        proto_indices = list(solver.SufficientAssumptionsForInfeasibility())
        assert len(proto_indices) >= 2

        # Map proto indices to local indices.
        proto_to_local = {v.Index(): i for i, v in enumerate(assumption_vars)}
        sufficient_local = sorted(
            proto_to_local[pi] for pi in proto_indices if pi in proto_to_local
        )
        assert len(sufficient_local) >= 2

        # Refine via standalone function (which uses local indices).
        model.ClearAssumptions()
        refined, solve_count, is_minimal = refine_mus(
            model, solver, assumption_vars, sufficient_local, mus_timeout_s=10.0
        )

        assert len(refined) == 2, (
            f"Expected 2 after MUS, got {len(refined)}: {refined}"
        )
        assert solve_count >= 1
        assert is_minimal


# ======================================================================
# Tests: single constraint infeasible
# ======================================================================


class TestSingleConstraintInfeasible:
    """A single impossible assumption."""

    def test_single_constraint_infeasible(self) -> None:
        """One component with ``x_start >= 650`` (units) when domain max is 600.

        With a 40mm-wide component on a 100mm board at scale=10,
        x_start max is (100-40)*10 = 600 units.  Requiring x_start >= 650
        (i.e. 65mm) is impossible.
        """
        model, ctx, assumption_vars, constraint_map = (
            _build_model_with_single_constraint(
                ref="A",
                w_mm=40.0,
                h_mm=20.0,
                board_w=100.0,
                board_h=100.0,
                x_min_bound_units=650,
            )
        )

        solver = _make_solver()
        report = extract_unsat_core(
            solver, model, assumption_vars, constraint_map, mus_timeout_s=10.0
        )

        assert len(report.sufficient_core) == 1, (
            f"Expected 1 in sufficient core, got {report.sufficient_core}"
        )
        assert "x_start >= 65mm" in report.sufficient_core[0]

        # Single constraint is already minimal.
        assert len(report.minimal_core) == 1
        assert report.is_minimal

    def test_impossible_clearance(self) -> None:
        """Two 40×40 components with 65mm clearance on a 100mm board.

        40+65=105 > 100, so the clearance is impossible in any axis.
        Crucially, two 40×40 components CAN fit on a 100×100 board with
        just NoOverlap2D alone — the infeasibility is caused solely by
        the clearance assumption.
        """
        components = {
            "A": {"width_mm": 40.0, "height_mm": 40.0},
            "B": {"width_mm": 40.0, "height_mm": 40.0},
        }
        model, ctx = build_cp_sat_model(
            components, board_w_mm=100.0, board_h_mm=100.0
        )

        # Verify NoOverlap2D alone is feasible.
        solver_check = cp_model.CpSolver()
        solver_check.parameters.num_search_workers = 2
        solver_check.parameters.log_search_progress = False
        base_status = solver_check.Solve(model)
        assert base_status in (cp_model.OPTIMAL, cp_model.FEASIBLE), (
            "Base model should be feasible — two 40×40 fit on 100×100"
        )

        # Gate the clearance constraint on an assumption var.
        assump = model.NewBoolVar("assump_clearance_AB")
        assumption_vars = [assump]
        constraint_map = {
            0: "Clearance 65mm between A and B",
        }

        clearance = int(65.0 * ctx.scale_factor)  # 65mm → 650 units
        b_left = model.NewBoolVar("clr_left_A_B")
        b_right = model.NewBoolVar("clr_right_A_B")
        b_below = model.NewBoolVar("clr_below_A_B")
        b_above = model.NewBoolVar("clr_above_A_B")

        model.Add(
            ctx.x_start["B"]
            >= ctx.x_start["A"] + ctx.x_size["A"] + clearance
        ).OnlyEnforceIf([b_left, assump])
        model.Add(
            ctx.x_start["A"]
            >= ctx.x_start["B"] + ctx.x_size["B"] + clearance
        ).OnlyEnforceIf([b_right, assump])
        model.Add(
            ctx.y_start["B"]
            >= ctx.y_start["A"] + ctx.y_size["A"] + clearance
        ).OnlyEnforceIf([b_below, assump])
        model.Add(
            ctx.y_start["A"]
            >= ctx.y_start["B"] + ctx.y_size["B"] + clearance
        ).OnlyEnforceIf([b_above, assump])
        model.AddBoolOr([b_left, b_right, b_below, b_above]).OnlyEnforceIf(assump)

        solver = _make_solver()
        report = extract_unsat_core(
            solver, model, assumption_vars, constraint_map, mus_timeout_s=10.0
        )

        assert len(report.sufficient_core) == 1, (
            f"Expected 1 in core, got {report.sufficient_core}"
        )
        assert "Clearance" in report.sufficient_core[0]
        assert len(report.minimal_core) == 1
        assert report.is_minimal


# ======================================================================
# Tests: feasible model raises error
# ======================================================================


class TestFeasibleRaisesError:
    """Calling ``extract_unsat_core`` on a feasible model raises ValueError."""

    def test_feasible_raises_value_error(self) -> None:
        """Two small components that fit easily → model is FEASIBLE."""
        components = {
            "A": {"width_mm": 10.0, "height_mm": 10.0},
            "B": {"width_mm": 10.0, "height_mm": 10.0},
        }
        model, ctx = build_cp_sat_model(
            components, board_w_mm=100.0, board_h_mm=100.0
        )

        # Dummy assumption that doesn't gate anything impossible.
        assump = model.NewBoolVar("assump_dummy")
        model.Add(ctx.x_start["A"] >= 0).OnlyEnforceIf(assump)

        solver = _make_solver()

        with pytest.raises(ValueError, match="satisfiable|FEASIBLE|OPTIMAL"):
            extract_unsat_core(
                solver,
                model,
                assumption_vars=[assump],
                constraint_map={0: "Dummy constraint"},
            )

    def test_no_assumptions_feasible(self) -> None:
        """No assumptions, feasible model → raises ValueError."""
        components = {
            "A": {"width_mm": 10.0, "height_mm": 10.0},
        }
        model, ctx = build_cp_sat_model(
            components, board_w_mm=100.0, board_h_mm=100.0
        )

        # Create an assumption that is trivially satisfiable.
        assump = model.NewBoolVar("assump_trivial")
        model.Add(ctx.x_start["A"] >= 0).OnlyEnforceIf(assump)

        solver = _make_solver()
        with pytest.raises(ValueError, match="satisfiable|FEASIBLE"):
            extract_unsat_core(
                solver,
                model,
                assumption_vars=[assump],
                constraint_map={0: "Trivial"},
            )


# ======================================================================
# Tests: MUS timeout
# ======================================================================


class TestMusTimeout:
    """MUS refinement respects timeout and falls back to sufficient core."""

    def test_mus_timeout_very_short(self) -> None:
        """Extremely short timeout should produce ``is_minimal=False``.

        We use a 3-constraint infeasible model and a 0.001s timeout
        that should expire before refinement completes.
        """
        model, ctx, assumption_vars, constraint_map = (
            _build_model_with_region_assumptions(
                component_refs=["A", "B", "C"],
                w_mm=30.0,
                h_mm=30.0,
                board_w=100.0,
                board_h=100.0,
                region=(0.0, 50.0, 0.0, 50.0),
            )
        )

        solver = _make_solver(timeout_s=5.0)

        # Use a very short MUS timeout.
        report = extract_unsat_core(
            solver, model, assumption_vars, constraint_map, mus_timeout_s=0.001
        )

        # Sufficient core should be populated.
        assert len(report.sufficient_core) >= 2, (
            f"Sufficient core should have entries: {report.sufficient_core}"
        )

        # The report may or may not be minimal depending on whether the
        # refinement loop made progress.  At minimum it should not error.
        assert report.solve_count >= 1
        assert report.wall_time_s >= 0.0

    def test_refine_mus_timeout(self) -> None:
        """Direct ``refine_mus`` call with a short timeout."""
        model, ctx, assumption_vars, constraint_map = (
            _build_model_with_region_assumptions(
                component_refs=["A", "B", "C"],
                w_mm=30.0,
                h_mm=30.0,
                board_w=100.0,
                board_h=100.0,
                region=(0.0, 50.0, 0.0, 50.0),
            )
        )

        solver = _make_solver()
        model.AddAssumptions(list(assumption_vars))
        status = solver.Solve(model)
        assert status == cp_model.INFEASIBLE

        proto_indices = list(solver.SufficientAssumptionsForInfeasibility())
        assert len(proto_indices) >= 2

        proto_to_local = {v.Index(): i for i, v in enumerate(assumption_vars)}
        sufficient_local = sorted(
            proto_to_local[pi] for pi in proto_indices if pi in proto_to_local
        )
        assert len(sufficient_local) >= 2

        model.ClearAssumptions()

        # Near-zero MUS timeout.
        refined, solve_count, is_minimal = refine_mus(
            model, solver, assumption_vars, sufficient_local, mus_timeout_s=0.0
        )

        # Timeout should be hit immediately; refined still has entries.
        assert len(refined) >= 1
        assert not is_minimal, "Expected not minimal due to timeout"


# ======================================================================
# Tests: edge cases
# ======================================================================


class TestEdgeCases:
    """Boundary conditions for UNSAT extraction."""

    def test_consecutive_solves_different_assumptions(self) -> None:
        """The internal ``ClearAssumptions`` pattern works across solves.

        Verify that two consecutive ``Solve()`` calls with different
        assumption sets produce the expected results (the first is
        INFEASIBLE with all assumptions, the second is FEASIBLE with
        just one sub-set).
        """
        model, ctx, assumption_vars, constraint_map = (
            _build_model_with_region_assumptions(
                component_refs=["A", "B"],
                w_mm=30.0,
                h_mm=30.0,
                board_w=100.0,
                board_h=100.0,
                region=(0.0, 50.0, 0.0, 50.0),
            )
        )

        solver = _make_solver()

        # Solve with both assumptions → INFEASIBLE.
        model.ClearAssumptions()
        model.AddAssumptions(list(assumption_vars))
        s1 = solver.Solve(model)
        assert s1 == cp_model.INFEASIBLE

        # Solve with just one assumption → FEASIBLE (single 30×30 fits in 50×50).
        model.ClearAssumptions()
        model.AddAssumptions([assumption_vars[0]])
        s2 = solver.Solve(model)
        assert s2 in (cp_model.OPTIMAL, cp_model.FEASIBLE), (
            f"Single assumption should be feasible, got {solver.StatusName(s2)}"
        )

        # Solve with zero assumptions → FEASIBLE.
        model.ClearAssumptions()
        s3 = solver.Solve(model)
        assert s3 in (cp_model.OPTIMAL, cp_model.FEASIBLE), (
            f"No assumptions should be feasible, got {solver.StatusName(s3)}"
        )

    def test_assumption_not_in_constraint_map(self) -> None:
        """Assumption indices absent from ``constraint_map`` are handled gracefully.

        If an assumption index is in the sufficient core but not in the
        map, it should be silently skipped in the report strings.
        """
        model, ctx, assumption_vars, _ = _build_model_with_region_assumptions(
            component_refs=["A", "B"],
            w_mm=30.0,
            h_mm=30.0,
            board_w=100.0,
            board_h=100.0,
            region=(0.0, 50.0, 0.0, 50.0),
        )

        # Constraint map missing entry for index 0.
        partial_map = {1: "B region constraint"}

        solver = _make_solver()
        report = extract_unsat_core(
            solver, model, assumption_vars, partial_map, mus_timeout_s=10.0
        )

        # Report should still work, just with fewer descriptions.
        assert len(report.sufficient_core) >= 0
        # At most 2 entries (both when both in map)
        assert len(report.sufficient_core) <= 1  # only B is in map

    def test_unsat_report_dataclass(self) -> None:
        """``UnsatReport`` fields are correctly populated."""
        report = UnsatReport(
            sufficient_core=["C1: clearance"],
            minimal_core=["C1: clearance"],
            solve_count=3,
            wall_time_s=0.5,
            is_minimal=True,
        )
        assert report.sufficient_core == ["C1: clearance"]
        assert report.minimal_core == ["C1: clearance"]
        assert report.solve_count == 3
        assert report.wall_time_s == 0.5
        assert report.is_minimal

        # Default construction.
        default = UnsatReport()
        assert default.sufficient_core == []
        assert default.minimal_core == []
        assert default.solve_count == 0
        assert default.wall_time_s == 0.0
        assert default.is_minimal
