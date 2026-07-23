"""Property-based tests for the Keepout constraint handler."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.pcl.constraints import ConstraintTier, KeepoutConstraint
from temper_placer.placer.cp_sat.encoder import EncoderContext
from temper_placer.placer.cp_sat.handlers.keepout import encode_keepout
from temper_placer.placer.cp_sat.model import CpSatModel


class TestKeepoutHandlerStructural:
    @given(
        margin_mm=st.floats(min_value=0.0, max_value=5.0),
    )
    @settings(max_examples=100)
    def test_handler_returns_assumptions(self, margin_mm: float) -> None:
        model = CpSatModel(units_per_mm=100)
        model.add_component("A", 0, 0, 200, 200)
        model.add_rotation("A", is_polarized=True)

        constraint = KeepoutConstraint(
            zone_name="NO_FLY",
            tier=ConstraintTier.HARD,
            margin_mm=margin_mm,
            because="No components allowed in keepout for safety isolation zone",
        )
        ctx = EncoderContext(
            board_w_mm=20.0,
            board_h_mm=20.0,
            board_x_max_units=2000,
            board_y_max_units=2000,
            zones={"NO_FLY": (4.0, 4.0, 6.0, 6.0)},
        )
        labels = encode_keepout(constraint, model.component_map, model, ctx)
        assert isinstance(labels, list)
        assert len(labels) == 1
        for v in labels:
            assert hasattr(v, "Index")

    def test_handler_is_registered(self) -> None:
        from temper_placer.pcl.constraints import ConstraintType
        from temper_placer.placer.cp_sat.handlers._registry import HANDLER_REGISTRY

        assert ConstraintType.KEEPOUT in HANDLER_REGISTRY
