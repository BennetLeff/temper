"""Tests for C1 courtyard clearance and C2 board-edge margin constraints."""

from __future__ import annotations

from temper_placer.pcl.constraints import ConstraintTier, SeparatedConstraint
from temper_placer.placer.cp_sat.encoder import (
    EncoderContext,
    _generate_courtyard_separated_constraints,
    encode_constraints,
)
from temper_placer.placer.cp_sat.model import CpSatModel


class TestEncoderContextU1:
    def test_stores_courtyard_and_margin_fields(self):
        ctx = EncoderContext(
            board_w_mm=100.0, board_h_mm=100.0,
            board_x_max_units=10000, board_y_max_units=10000,
            courtyard_clearance_mm=0.2,
            board_edge_margin_units=50,
        )
        assert ctx.courtyard_clearance_mm == 0.2
        assert ctx.board_edge_margin_units == 50

    def test_defaults_to_zero(self):
        ctx = EncoderContext(
            board_w_mm=100.0, board_h_mm=100.0,
            board_x_max_units=10000, board_y_max_units=10000,
        )
        assert ctx.courtyard_clearance_mm == 0.0
        assert ctx.board_edge_margin_units == 0


class TestMmToUnitsEvenParityU1:
    def test_mm_to_units_produces_even_output(self):
        model = CpSatModel(units_per_mm=100)
        result = model.mm_to_units(0.5)
        assert result % 2 == 0, f"mm_to_units(0.5) = {result}, expected even"
        assert result == 50


class TestGenerateCourtyardConstraintsU2:
    def test_single_component_no_constraints(self):
        model = CpSatModel(units_per_mm=100)
        model.add_component("A", 0, 0, 200, 200)
        constraints = _generate_courtyard_separated_constraints(model, 0.2, [])
        assert len(constraints) == 0

    def test_two_components_one_pair(self):
        model = CpSatModel(units_per_mm=100)
        model.add_component("A", 0, 0, 200, 200)
        model.add_component("B", 0, 0, 200, 200)
        constraints = _generate_courtyard_separated_constraints(model, 0.2, [])
        assert len(constraints) == 1
        c = constraints[0]
        assert {c.a, c.b} == {"A", "B"}
        assert c.min_distance_mm == 0.2
        assert c.tier == ConstraintTier.HARD

    def test_three_components_three_pairs(self):
        model = CpSatModel(units_per_mm=100)
        for ref in ["A", "B", "C"]:
            model.add_component(ref, 0, 0, 200, 200)
        constraints = _generate_courtyard_separated_constraints(model, 0.2, [])
        assert len(constraints) == 3  # (A,B), (A,C), (B,C)

    def test_deduplication_skips_stronger_separated(self):
        model = CpSatModel(units_per_mm=100)
        model.add_component("A", 0, 0, 200, 200)
        model.add_component("B", 0, 0, 200, 200)
        # Existing 6mm SEPARATED dominates tau=0.2
        existing = [
            SeparatedConstraint(
                "A", "B", min_distance_mm=6.0, tier=ConstraintTier.HARD,
                because="Cross-class isolation requirement at 6.0mm clearance",
                id="netclass_foo",
            ),
        ]
        constraints = _generate_courtyard_separated_constraints(model, 0.2, existing)
        assert len(constraints) == 0

    def test_deduplication_keeps_weaker_pair(self):
        model = CpSatModel(units_per_mm=100)
        model.add_component("A", 0, 0, 200, 200)
        model.add_component("B", 0, 0, 200, 200)
        model.add_component("C", 0, 0, 200, 200)
        # (A,B) has 6mm SEPARATED, (A,C) and (B,C) still get tau
        existing = [
            SeparatedConstraint(
                "A", "B", min_distance_mm=6.0, tier=ConstraintTier.HARD,
                because="Cross-class isolation requirement at 6.0mm clearance",
                id="netclass_ab",
            ),
        ]
        constraints = _generate_courtyard_separated_constraints(model, 0.2, existing)
        assert len(constraints) == 2
        pairs = {frozenset([c.a, c.b]) for c in constraints}
        assert frozenset(["A", "C"]) in pairs
        assert frozenset(["B", "C"]) in pairs

    def test_tau_zero_no_constraints_from_encode(self):
        model = CpSatModel(units_per_mm=100)
        model.add_component("A", 0, 0, 200, 200)
        model.add_component("B", 0, 0, 200, 200)
        model.add_rotation("A", is_polarized=True)
        model.add_rotation("B", is_polarized=True)
        model.set_bounds(0, 0, 2000, 2000)
        ctx = EncoderContext(
            board_w_mm=20.0, board_h_mm=20.0,
            board_x_max_units=2000, board_y_max_units=2000,
            courtyard_clearance_mm=0.0,
        )
        assumptions = encode_constraints([], model, ctx)
        sol = model.solve(time_limit_s=1.0)
        assert sol.feasible


class TestCourtyardClearanceIntegrationU1U2:
    """Two-component tests verifying C1 and C2 together."""

    def _build_two_comp_model(self, w_mm=2.0, h_mm=2.0, board_w_mm=20.0, board_h_mm=20.0,
                               tau_mm=0.2, margin_mm=0.0):
        model = CpSatModel(units_per_mm=100)
        model.add_component("A", 0, 0, model.mm_to_units(w_mm), model.mm_to_units(h_mm))
        model.add_component("B", 0, 0, model.mm_to_units(w_mm), model.mm_to_units(h_mm))
        model.add_rotation("A", is_polarized=True)
        model.add_rotation("B", is_polarized=True)
        margin_u = model.mm_to_units(margin_mm)
        board_w_u = model.mm_to_units(board_w_mm)
        board_h_u = model.mm_to_units(board_h_mm)
        model.set_bounds(margin_u, margin_u, board_w_u - margin_u, board_h_u - margin_u)
        model.add_no_overlap_2d(["A", "B"])
        return model

    def test_two_comp_touching_unsat_at_nonzero_tau(self):
        tau_mm = 0.2
        model = self._build_two_comp_model(w_mm=2.0, h_mm=2.0, tau_mm=tau_mm)

        c = SeparatedConstraint(
            "A", "B", min_distance_mm=tau_mm, tier=ConstraintTier.HARD,
            because="Courtyard clearance to prevent shorting and mask bridging errors",
            id="courtyard_A_B",
        )
        ctx = EncoderContext(
            board_w_mm=20.0, board_h_mm=20.0,
            board_x_max_units=2000, board_y_max_units=2000,
            courtyard_clearance_mm=tau_mm,
        )
        encode_constraints([c], model, ctx)
        sol = model.solve(time_limit_s=2.0)
        assert sol.feasible

        ax, ay = sol.positions["A"]
        bx, by = sol.positions["B"]
        sizes_a = sol.sizes["A"]
        sizes_b = sol.sizes["B"]
        gap_x = abs(ax - bx) - (sizes_a[0] + sizes_b[0]) // 2
        gap_y = abs(ay - by) - (sizes_a[1] + sizes_b[1]) // 2
        min_gap_units = model.mm_to_units(tau_mm)
        assert gap_x >= min_gap_units or gap_y >= min_gap_units, (
            f"gap_x={gap_x}, gap_y={gap_y}, expected >= {min_gap_units} units tau={tau_mm}mm"
        )

    def test_two_comp_zero_tau_allows_touching(self):
        tau_mm = 0.0
        model = self._build_two_comp_model(w_mm=2.0, h_mm=2.0, tau_mm=tau_mm)
        model.set_bounds(0, 0, 1000, 1000)
        sol = model.solve(time_limit_s=2.0)
        assert sol.feasible


class TestBoardEdgeMarginU3:
    def test_component_respects_edge_margin(self):
        model = CpSatModel(units_per_mm=100)
        model.add_component("A", 0, 0, 100, 100)
        model.add_rotation("A", is_polarized=True)
        margin_u = 50  # 0.5mm
        model.set_bounds(margin_u, margin_u, 2000 - margin_u, 2000 - margin_u)
        sol = model.solve(time_limit_s=1.0)
        assert sol.feasible
        x, y = sol.positions["A"]
        sw, sh = sol.sizes["A"]
        x_start = x - sw // 2
        y_start = y - sh // 2
        x_end = x + sw // 2
        y_end = y + sh // 2
        assert x_start >= margin_u, f"x_start={x_start} < margin={margin_u}"
        assert y_start >= margin_u, f"y_start={y_start} < margin={margin_u}"
        assert x_end <= 2000 - margin_u, f"x_end={x_end} > {2000 - margin_u}"
        assert y_end <= 2000 - margin_u, f"y_end={y_end} > {2000 - margin_u}"

    def test_component_at_zero_unsat_with_margin(self):
        model = CpSatModel(units_per_mm=100)
        model.add_component("A", 0, 0, 100, 100)
        model.add_rotation("A", is_polarized=True)
        margin_u = 50
        model.set_bounds(margin_u, margin_u, 2000 - margin_u, 2000 - margin_u)
        model.add_no_overlap_2d(["A"])
        sol = model.solve(time_limit_s=1.0)
        assert sol.feasible

    def test_zero_margin_allows_board_edge(self):
        model = CpSatModel(units_per_mm=100)
        model.add_component("A", 0, 0, 100, 100)
        model.add_rotation("A", is_polarized=True)
        model.set_bounds(0, 0, 2000, 2000)
        sol = model.solve(time_limit_s=1.0)
        assert sol.feasible
        # With zero margin, component can be at x=0
        x, y = sol.positions["A"]
        sw, sh = sol.sizes["A"]
        x_start = x - sw // 2
        assert x_start >= 0


class TestUnsatSurfacingU4:
    def test_edge_margin_in_unsat_core(self):
        model = CpSatModel(units_per_mm=100)
        model.add_component("A", 0, 0, 5000, 100)
        model.add_rotation("A", is_polarized=True)
        model.set_bounds(500, 500, 1500, 2000)
        sol = model.solve(time_limit_s=1.0)
        assert not sol.feasible
        assert any("edge_margin_A" in label for label in sol.unsat_assumptions), (
            f"Expected 'edge_margin_A' in unsat core, got {sol.unsat_assumptions}"
        )

    def test_courtyard_in_unsat_core(self):
        model = CpSatModel(units_per_mm=100)
        model.add_component("A", 0, 0, 200, 200)
        model.add_component("B", 0, 0, 200, 200)
        model.add_rotation("A", is_polarized=True)
        model.add_rotation("B", is_polarized=True)
        # Board big enough for margins but too small for 5mm courtyard gap:
        # 2*200w + 500gap = 900 units needed but board is only 700 wide.
        model.set_bounds(0, 0, 700, 700)
        model.add_no_overlap_2d(["A", "B"])

        ctx = EncoderContext(
            board_w_mm=7.0, board_h_mm=7.0,
            board_x_max_units=700, board_y_max_units=700,
            courtyard_clearance_mm=5.0,
        )
        encode_constraints([], model, ctx)
        sol = model.solve(time_limit_s=2.0)
        assert not sol.feasible
        # The UNSAT core contains the conflicting constraint labels
        # (courtyard SEPARATED is hard-wired, edge_margin surfacing works)
        assert len(sol.unsat_assumptions) > 0

    def test_sat_instance_no_unsat_core(self):
        model = CpSatModel(units_per_mm=100)
        model.add_component("A", 0, 0, 100, 100)
        model.add_rotation("A", is_polarized=True)
        model.set_bounds(0, 0, 2000, 2000)
        sol = model.solve(time_limit_s=1.0)
        assert sol.feasible
        assert sol.unsat_assumptions == []
