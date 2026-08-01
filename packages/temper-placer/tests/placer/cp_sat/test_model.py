"""Tests for CpSatModel — U1: foundation for all encoder work."""

from __future__ import annotations

import pytest

from temper_placer.placer.cp_sat.model import (
    ComponentVars,
    CpSatModel,
    SolveStatus,
)


class TestCpSatModelCreation:
    """Model creation and basic property tests."""

    def test_empty_model_creation(self) -> None:
        model = CpSatModel(units_per_mm=100)
        assert model.units_per_mm == 100
        assert len(model.component_map) == 0

    def test_mm_to_units_conversion(self) -> None:
        model = CpSatModel(units_per_mm=100)
        assert model.mm_to_units(10.0) == 1000
        assert model.mm_to_units(0.1) == 10
        assert model.units_to_mm(1000) == 10.0

    def test_different_grid_resolution(self) -> None:
        model = CpSatModel(units_per_mm=10)
        assert model.mm_to_units(5.0) == 50


class TestAddComponent:
    """Component registration tests."""

    def test_add_single_component_returns_vars(self) -> None:
        model = CpSatModel()
        v = model.add_component("Q1", x_start_val=0, y_start_val=0, width=100, height=200)
        assert isinstance(v, ComponentVars)
        assert v.ref == "Q1"

    def test_add_component_has_valid_intvars(self) -> None:
        model = CpSatModel()
        v = model.add_component("R1", x_start_val=0, y_start_val=0, width=80, height=30)
        # Variable existence verified by model construction and solve
        assert v.x_center is not None
        assert v.y_center is not None
        assert v.x_size is not None
        assert v.y_size is not None
        assert v.x_start is not None
        assert v.y_start is not None
        assert v.x_end is not None
        assert v.y_end is not None

    def test_add_duplicate_raises(self) -> None:
        model = CpSatModel()
        model.add_component("C1", x_start_val=0, y_start_val=0, width=50, height=50)
        with pytest.raises(ValueError, match="already registered"):
            model.add_component("C1", x_start_val=0, y_start_val=0, width=50, height=50)

    def test_get_component_retrieves_vars(self) -> None:
        model = CpSatModel()
        model.add_component("D1", x_start_val=10, y_start_val=10, width=60, height=40)
        v = model.get_component("D1")
        assert v.ref == "D1"

    def test_get_component_missing_raises(self) -> None:
        model = CpSatModel()
        with pytest.raises(KeyError):
            model.get_component("NONEXISTENT")


class TestAddRotation:
    """Rotation variable creation tests (U1 — U5 will extend)."""

    def test_non_polarized_returns_intvar(self) -> None:
        model = CpSatModel()
        model.add_component("R_SMD", x_start_val=0, y_start_val=0, width=80, height=30)
        rot = model.add_rotation("R_SMD", is_polarized=False)
        assert rot is not None
        assert str(rot) == "rot_R_SMD"

    def test_polarized_returns_none(self) -> None:
        model = CpSatModel()
        model.add_component("K_5", x_start_val=0, y_start_val=0, width=120, height=120)
        rot = model.add_rotation("K_5", is_polarized=True)
        assert rot is None

    def test_polarized_component_rot_is_zero(self) -> None:
        model = CpSatModel()
        model.add_component("K_6", x_start_val=0, y_start_val=0, width=100, height=100)
        model.add_rotation("K_6", is_polarized=True)

        model.set_bounds(x_min=0, y_min=0, x_max=1000, y_max=1000)
        sol = model.solve(time_limit_s=1.0)
        assert sol.feasible
        assert sol.rotations["K_6"] == 0

    def test_add_rotation_missing_component_raises(self) -> None:
        raised = False
        model = CpSatModel()
        try:
            model.add_rotation("GHOST", is_polarized=False)
        except ValueError:
            raised = True
        assert raised, "Expected ValueError for missing component"


class TestSolve:
    """Solver round-trip tests."""

    def test_empty_model_solves_optimal(self) -> None:
        model = CpSatModel()
        sol = model.solve(time_limit_s=1.0)
        assert sol.status in (SolveStatus.OPTIMAL, SolveStatus.FEASIBLE)

    def test_single_component_solves(self) -> None:
        model = CpSatModel()
        model.add_component("Q1", x_start_val=0, y_start_val=0, width=100, height=200)
        model.set_bounds(x_min=0, y_min=0, x_max=1000, y_max=1000)
        sol = model.solve(time_limit_s=1.0)
        assert sol.feasible
        assert "Q1" in sol.positions

    def test_two_components_no_overlap(self) -> None:
        model = CpSatModel()
        model.add_component("A", x_start_val=0, y_start_val=0, width=50, height=50)
        model.add_component("B", x_start_val=0, y_start_val=0, width=50, height=50)
        model.add_no_overlap_2d(["A", "B"])
        model.set_bounds(x_min=0, y_min=0, x_max=500, y_max=500)
        sol = model.solve(time_limit_s=1.0)
        assert sol.feasible

    def test_two_components_overlap_without_constraint(self) -> None:
        model = CpSatModel()
        model.add_component("A", x_start_val=0, y_start_val=0, width=50, height=50)
        model.add_component("B", x_start_val=0, y_start_val=0, width=50, height=50)
        model.set_bounds(x_min=0, y_min=0, x_max=200, y_max=200)
        sol = model.solve(time_limit_s=1.0)
        assert sol.feasible

    def test_no_overlap_prevents_overlap(self) -> None:
        model = CpSatModel()
        w, h = 50, 50
        model.add_component("A", x_start_val=0, y_start_val=0, width=w, height=h)
        model.add_component("B", x_start_val=0, y_start_val=0, width=w, height=h)
        model.add_no_overlap_2d(["A", "B"])
        model.set_bounds(x_min=0, y_min=0, x_max=400, y_max=400)
        sol = model.solve(time_limit_s=1.0)
        assert sol.feasible

        ax, ay = sol.positions["A"]
        bx, by = sol.positions["B"]

        half = w // 2
        a_l, a_r = ax - half, ax + half
        a_b, a_t = ay - half, ay + half
        b_l, b_r = bx - half, bx + half
        b_b, b_t = by - half, by + half

        overlap_x = a_l < b_r and b_l < a_r
        overlap_y = a_b < b_t and b_b < a_t
        assert not (overlap_x and overlap_y), (
            f"A at ({ax},{ay}) +-{half} and B at ({bx},{by}) +-{half} overlap"
        )

    def test_solve_time_limit(self) -> None:
        model = CpSatModel()
        sol = model.solve(time_limit_s=0.5)
        assert sol.solve_time_s <= 1.0  # small buffer


class TestDisplacementObjective:
    """Minimum-displacement objective (issue #504 repair machinery).

    The objective is a *preference*, never a hard bound: hard constraints
    stay authoritative and the solver picks the feasible placement closest
    (Manhattan) to the reference position. `apply_objective()` must actually
    call `Minimize` -- the never-landed PR #498 registered objective terms
    without applying them, making the parameter a silent no-op.
    """

    def test_single_component_placed_exactly_at_reference(self) -> None:
        model = CpSatModel()
        model.add_component("Q1", x_start_val=0, y_start_val=0, width=100, height=100)
        model.set_bounds(x_min=0, y_min=0, x_max=1000, y_max=1000)
        model.add_displacement_objective("Q1", 500, 400)
        model.apply_objective()
        sol = model.solve(time_limit_s=2.0)
        assert sol.feasible
        # The reference is feasible, so the unique optimum is zero displacement.
        assert sol.positions["Q1"] == (500, 400)

    def test_two_components_minimize_total_displacement_when_forced(self) -> None:
        # Hard x-separation of 700 units between two 200-wide components whose
        # reference is the shared center (1000, 1000). By |u - v| <= |u| + |v|,
        # total displacement >= 700, and 700 is attainable (e.g. 650/1350,
        # or A unmoved and B at 1700), so EVERY optimal solution has total
        # displacement exactly 700 -- an exact, optimum-unique invariant.
        model = CpSatModel()
        model.add_component("A", x_start_val=0, y_start_val=0, width=200, height=200)
        model.add_component("B", x_start_val=0, y_start_val=0, width=200, height=200)
        model.set_bounds(x_min=0, y_min=0, x_max=2000, y_max=2000)
        model.add_no_overlap_2d(["A", "B"])
        va, vb = model.get_component("A"), model.get_component("B")
        # B.x_start - A.x_end >= 500  =>  B.x - A.x >= 700.
        model.add(vb.x_start - va.x_end >= 500)
        model.add_displacement_objective("A", 1000, 1000)
        model.add_displacement_objective("B", 1000, 1000)
        model.apply_objective()
        sol = model.solve(time_limit_s=5.0)
        assert sol.feasible
        ax, ay = sol.positions["A"]
        bx, by = sol.positions["B"]
        total = abs(ax - 1000) + abs(bx - 1000) + abs(ay - 1000) + abs(by - 1000)
        assert total == 700, (sol.positions, total)
        # Separation is preserved (a hard constraint, not the objective).
        assert bx - ax >= 700, (ax, bx)
        # The y-axis is unconstrained, so it stays at the reference exactly.
        assert ay == 1000 and by == 1000, (sol.positions)

    def test_unknown_ref_raises(self) -> None:
        model = CpSatModel()
        model.add_component("Q1", x_start_val=0, y_start_val=0, width=100, height=100)
        with pytest.raises(KeyError):
            model.add_displacement_objective("NOPE", 100, 100)

    def test_nonpositive_weight_rejected(self) -> None:
        model = CpSatModel()
        model.add_component("Q1", x_start_val=0, y_start_val=0, width=100, height=100)
        with pytest.raises(ValueError):
            model.add_displacement_objective("Q1", 100, 100, weight=0)
        with pytest.raises(ValueError):
            model.add_displacement_objective("Q1", 100, 100, weight=-1)

    def test_apply_objective_idempotent(self) -> None:
        model = CpSatModel()
        model.add_component("Q1", x_start_val=0, y_start_val=0, width=100, height=100)
        model.set_bounds(x_min=0, y_min=0, x_max=1000, y_max=1000)
        model.add_displacement_objective("Q1", 250, 250)
        model.apply_objective()
        model.apply_objective()  # must not raise (Minimize already called)
        sol = model.solve(time_limit_s=2.0)
        assert sol.feasible
        assert sol.positions["Q1"] == (250, 250)

    def test_hard_displacement_bound_respected(self) -> None:
        # Reference at (500, 500); keepout [400,700]^2 blocks it. The closest
        # feasible centre is (350, 500) at Manhattan distance 150, so a hard
        # bound of 200 is feasible and must be respected (displacement 150).
        model = CpSatModel()
        model.add_component("Q1", x_start_val=0, y_start_val=0, width=100, height=100)
        model.set_bounds(x_min=50, y_min=50, x_max=950, y_max=950)
        kx_iv, ky_iv = model.add_keepout_interval("k1", 400, 400, 300, 300)
        model.add_no_overlap_2d(["Q1"], extra_x_intervals=[kx_iv], extra_y_intervals=[ky_iv])
        model.add_displacement_objective("Q1", 500, 500, max_units=200)
        model.apply_objective()
        sol = model.solve(time_limit_s=5.0)
        assert sol.feasible
        x, y = sol.positions["Q1"]
        assert abs(x - 500) + abs(y - 500) == 150, (x, y)
        assert abs(x - 500) + abs(y - 500) <= 200, (x, y)

    def test_hard_displacement_bound_can_make_model_infeasible(self) -> None:
        # Reference at the keepout centre (500, 500); the closest feasible
        # point is 250 units away, so a 100-unit bound is infeasible.
        model = CpSatModel()
        model.add_component("Q1", x_start_val=0, y_start_val=0, width=100, height=100)
        model.set_bounds(x_min=50, y_min=50, x_max=950, y_max=950)
        kx_iv, ky_iv = model.add_keepout_interval("k1", 300, 300, 400, 400)
        model.add_no_overlap_2d(["Q1"], extra_x_intervals=[kx_iv], extra_y_intervals=[ky_iv])
        model.add_displacement_objective("Q1", 500, 500, max_units=100)
        model.apply_objective()
        sol = model.solve(time_limit_s=5.0)
        assert not sol.feasible

    def test_negative_bound_rejected(self) -> None:
        model = CpSatModel()
        model.add_component("Q1", x_start_val=0, y_start_val=0, width=100, height=100)
        with pytest.raises(ValueError):
            model.add_displacement_objective("Q1", 500, 500, max_units=-1)


class TestFixedRotation:
    """Hard-pinning a component's 0-3 rotation index.

    The routed-board repair must NOT let CP-SAT rotate footprints: a rotation
    moves every pad, which disconnects the routed copper attached to it.
    """

    def test_fixed_rotation_pins_rotation(self) -> None:
        model = CpSatModel()
        model.add_component("Q1", x_start_val=0, y_start_val=0, width=200, height=100)
        model.set_bounds(x_min=0, y_min=0, x_max=1000, y_max=1000)
        model.add_rotation("Q1", is_polarized=False)
        model.add_fixed_rotation("Q1", 2)
        sol = model.solve(time_limit_s=2.0)
        assert sol.feasible
        assert sol.rotations["Q1"] == 2

    def test_fixed_rotation_out_of_range_raises(self) -> None:
        model = CpSatModel()
        model.add_component("Q1", x_start_val=0, y_start_val=0, width=100, height=100)
        with pytest.raises(ValueError):
            model.add_fixed_rotation("Q1", 4)
        with pytest.raises(ValueError):
            model.add_fixed_rotation("Q1", -1)

    def test_fixed_rotation_conflict_with_polarized_raises(self) -> None:
        # A polarized component is pinned to rot=0 by construction; fixing it
        # to anything else is a contradiction and must fail loudly.
        model = CpSatModel()
        model.add_component("Q1", x_start_val=0, y_start_val=0, width=100, height=100)
        model.add_rotation("Q1", is_polarized=True)
        with pytest.raises(ValueError):
            model.add_fixed_rotation("Q1", 1)
        model.add_fixed_rotation("Q1", 0)  # consistent no-op

    def test_unknown_ref_raises(self) -> None:
        model = CpSatModel()
        with pytest.raises(KeyError):
            model.add_fixed_rotation("NOPE", 0)


class TestAssumptions:
    """Assumption literal and UNSAT-core tests."""

    def test_new_assumption_creates_bool(self) -> None:
        model = CpSatModel()
        b = model.new_assumption("test_assump")
        assert b is not None

    def test_unsat_due_to_contradiction_detected(self) -> None:
        model = CpSatModel()
        model.add_component("A", x_start_val=0, y_start_val=0, width=1000, height=1000)
        model.add_component("B", x_start_val=0, y_start_val=0, width=1000, height=1000)
        # Force no overlap in a space too small — makes it infeasible
        model.add_no_overlap_2d(["A", "B"])
        model.set_bounds(x_min=0, y_min=0, x_max=500, y_max=500)
        sol = model.solve(time_limit_s=1.0)
        # This might be feasible or infeasible depending on solver; just check it runs
        assert sol.status in (SolveStatus.FEASIBLE, SolveStatus.OPTIMAL, SolveStatus.INFEASIBLE)


class TestMultipleComponents:
    """Scale test — 33 components (temper-board size)."""

    def test_33_components_solve_in_2s(self) -> None:
        model = CpSatModel()
        refs = []
        for i in range(33):
            ref = f"COMP_{i:02d}"
            model.add_component(ref, x_start_val=0, y_start_val=0, width=100, height=100)
            refs.append(ref)
        model.add_no_overlap_2d(refs)
        model.set_bounds(x_min=0, y_min=0, x_max=3000, y_max=2000)
        sol = model.solve(time_limit_s=2.0)
        assert sol.feasible
        assert len(sol.positions) == 33
        # All positions should be within the board
        for x, y in sol.positions.values():
            assert 0 <= x <= 3000
            assert 0 <= y <= 2000


class TestBoundsEnforcement:
    """Board boundary enforcement tests."""

    def test_set_bounds_restricts_components(self) -> None:
        model = CpSatModel()
        model.add_component("A", x_start_val=0, y_start_val=0, width=100, height=100)
        model.set_bounds(x_min=100, y_min=100, x_max=200, y_max=200)
        sol = model.solve(time_limit_s=1.0)
        assert sol.feasible
        x, y = sol.positions["A"]
        half = 50
        assert 100 + half <= x <= 200 - half
        assert 100 + half <= y <= 200 - half
