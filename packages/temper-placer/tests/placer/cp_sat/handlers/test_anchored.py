"""Property-based tests for the Anchored constraint handler."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.pcl.constraints import AnchoredConstraint, ConstraintTier
from temper_placer.placer.cp_sat.encoder import EncoderContext
from temper_placer.placer.cp_sat.handlers.anchored import encode_anchored
from temper_placer.placer.cp_sat.model import CpSatModel


class TestAnchoredHandlerStructural:
    @given(
        pos_x=st.floats(min_value=1.0, max_value=40.0),
        pos_y=st.floats(min_value=1.0, max_value=40.0),
    )
    @settings(max_examples=100)
    def test_handler_returns_assumptions_with_position(self, pos_x: float, pos_y: float) -> None:
        model = CpSatModel(units_per_mm=100)
        model.add_component("U1", 0, 0, 200, 200)
        model.add_rotation("U1", is_polarized=True)

        constraint = AnchoredConstraint(
            component="U1", tier=ConstraintTier.HARD,
            position=(pos_x, pos_y),
            because="MCU must be in designated location for enclosure",
        )
        ctx = EncoderContext(board_w_mm=50.0, board_h_mm=50.0,
                             board_x_max_units=5000, board_y_max_units=5000)
        labels = encode_anchored(constraint, model.component_map, model, ctx)
        assert isinstance(labels, list)
        assert len(labels) == 1
        for v in labels:
            assert hasattr(v, "Index")

    @given(
        rx_min=st.floats(min_value=0.0, max_value=20.0),
        ry_min=st.floats(min_value=0.0, max_value=20.0),
        rw=st.floats(min_value=5.0, max_value=30.0),
        rh=st.floats(min_value=5.0, max_value=30.0),
    )
    @settings(max_examples=100)
    def test_handler_returns_assumptions_with_region(
        self, rx_min: float, ry_min: float, rw: float, rh: float,
    ) -> None:
        model = CpSatModel(units_per_mm=100)
        model.add_component("U1", 0, 0, 200, 200)
        model.add_rotation("U1", is_polarized=True)

        constraint = AnchoredConstraint(
            component="U1", tier=ConstraintTier.HARD,
            region=(rx_min, ry_min, rx_min + rw, ry_min + rh),
            because="MCU must be in designated region for enclosure fit",
        )
        ctx = EncoderContext(board_w_mm=50.0, board_h_mm=50.0,
                             board_x_max_units=5000, board_y_max_units=5000)
        labels = encode_anchored(constraint, model.component_map, model, ctx)
        assert isinstance(labels, list)
        assert len(labels) == 1

    def test_handler_is_registered(self) -> None:
        from temper_placer.pcl.constraints import ConstraintType
        from temper_placer.placer.cp_sat.handlers._registry import HANDLER_REGISTRY
        assert ConstraintType.ANCHORED in HANDLER_REGISTRY
