"""Property-based tests for the OnSide constraint handler."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.pcl.constraints import BoardSide, ConstraintTier, EdgeType, OnSideConstraint
from temper_placer.placer.cp_sat.encoder import EncoderContext
from temper_placer.placer.cp_sat.handlers.onside import encode_onside
from temper_placer.placer.cp_sat.model import CpSatModel


class TestOnSideHandlerStructural:
    @given(
        side=st.sampled_from(list(BoardSide)),
        max_distance_mm=st.floats(min_value=0.5, max_value=5.0),
    )
    @settings(max_examples=100)
    def test_handler_returns_assumptions(self, side: BoardSide, max_distance_mm: float) -> None:
        model = CpSatModel(units_per_mm=100)
        model.add_component("J1", 0, 0, 200, 200)
        model.add_rotation("J1", is_polarized=True)

        constraint = OnSideConstraint(
            components=["J1"],
            side=side,
            edge=EdgeType.FLUSH,
            max_distance_mm=max_distance_mm,
            tier=ConstraintTier.HARD,
            because="Connector must be on board edge for external accessibility",
        )
        ctx = EncoderContext(
            board_w_mm=50.0, board_h_mm=50.0, board_x_max_units=5000, board_y_max_units=5000
        )
        labels = encode_onside(constraint, model.component_map, model, ctx)
        assert isinstance(labels, list)
        assert len(labels) == 1
        for v in labels:
            assert hasattr(v, "Index")

    def test_handler_is_registered(self) -> None:
        from temper_placer.pcl.constraints import ConstraintType
        from temper_placer.placer.cp_sat.handlers._registry import HANDLER_REGISTRY

        assert ConstraintType.ON_SIDE in HANDLER_REGISTRY
