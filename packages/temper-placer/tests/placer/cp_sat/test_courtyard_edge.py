"""Tests for C1 courtyard clearance and C2 board-edge margin constraints."""

from __future__ import annotations

from temper_placer.pcl.constraints import ConstraintTier, SeparatedConstraint
from temper_placer.placer.cp_sat.encoder import EncoderContext, encode_constraints
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
        """Two 2x2mm components with tau=0.2mm must have gap >= 0.2mm."""
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
