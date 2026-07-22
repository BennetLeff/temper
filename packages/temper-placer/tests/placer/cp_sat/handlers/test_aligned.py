"""Property-based tests for the Aligned constraint handler."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.pcl.constraints import AlignedConstraint, Axis, ConstraintTier
from temper_placer.placer.cp_sat.encoder import EncoderContext
from temper_placer.placer.cp_sat.handlers.aligned import encode_aligned
from temper_placer.placer.cp_sat.model import CpSatModel


class TestAlignedHandlerStructural:
    @given(
        tolerance_mm=st.floats(min_value=0.1, max_value=5.0),
        num_comps=st.integers(min_value=2, max_value=4),
    )
    @settings(max_examples=100)
    def test_handler_returns_assumptions(self, tolerance_mm: float, num_comps: int) -> None:
        model = CpSatModel(units_per_mm=100)
        comp_names = [f"C{i}" for i in range(num_comps)]
        for name in comp_names:
            model.add_component(name, 0, 0, 100, 100)
            model.add_rotation(name, is_polarized=True)

        constraint = AlignedConstraint(
            components=comp_names, axis=Axis.X, tolerance_mm=tolerance_mm,
            tier=ConstraintTier.HARD,
            because="Align components for visual consistency assurance",
        )
        ctx = EncoderContext(board_w_mm=50.0, board_h_mm=50.0,
                             board_x_max_units=5000, board_y_max_units=5000)
        labels = encode_aligned(constraint, model.component_map, model, ctx)
        assert isinstance(labels, list)
        # n(n-1)/2 pairs
        expected_pairs = num_comps * (num_comps - 1) // 2
        assert len(labels) == expected_pairs
        for v in labels:
            assert hasattr(v, "Index")

    def test_handler_is_registered(self) -> None:
        from temper_placer.pcl.constraints import ConstraintType
        from temper_placer.placer.cp_sat.handlers._registry import HANDLER_REGISTRY
        assert ConstraintType.ALIGNED in HANDLER_REGISTRY

    def test_handler_satisfies_protocol(self) -> None:
        from temper_placer.placer.cp_sat.handlers._protocol import ConstraintHandler
        assert isinstance(encode_aligned, ConstraintHandler)
