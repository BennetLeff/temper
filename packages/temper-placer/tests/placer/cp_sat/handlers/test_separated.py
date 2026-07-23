"""Property-based tests for the Separated constraint handler."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.pcl.constraints import ConstraintTier, SeparatedConstraint
from temper_placer.placer.cp_sat.encoder import EncoderContext
from temper_placer.placer.cp_sat.handlers.separated import encode_separated
from temper_placer.placer.cp_sat.model import CpSatModel


class TestSeparatedHandlerStructural:
    @given(
        min_distance_mm=st.floats(min_value=0.5, max_value=20.0),
        num_a=st.integers(min_value=1, max_value=3),
        num_b=st.integers(min_value=1, max_value=3),
    )
    @settings(max_examples=100)
    def test_handler_returns_assumptions_for_resolvable_refs(
        self,
        min_distance_mm: float,
        num_a: int,
        num_b: int,
    ) -> None:
        model = CpSatModel(units_per_mm=100)
        for i in range(max(num_a, num_b) + 2):
            model.add_component(f"C{i}", 0, 0, 200, 200)
            model.add_rotation(f"C{i}", is_polarized=True)

        constraint = SeparatedConstraint(
            a=f"C{0}",
            b=f"C{1}",
            min_distance_mm=min_distance_mm,
            tier=ConstraintTier.HARD,
            because="Isolation requirement per safety analysis",
        )
        ctx = EncoderContext(
            board_w_mm=100.0, board_h_mm=100.0, board_x_max_units=10000, board_y_max_units=10000
        )
        labels = encode_separated(constraint, model.component_map, model, ctx)

        # Structural assertions: must return a list of assumption variables
        assert isinstance(labels, list)
        for v in labels:
            assert hasattr(v, "Index")

        # At least one assumption per pair (a, b) that resolves

        # At least one assumption per pair (a, b) that resolves
        assert len(labels) >= 1

    def test_handler_is_registered(self) -> None:
        from temper_placer.pcl.constraints import ConstraintType
        from temper_placer.placer.cp_sat.handlers._registry import HANDLER_REGISTRY

        assert ConstraintType.SEPARATED in HANDLER_REGISTRY
        assert HANDLER_REGISTRY[ConstraintType.SEPARATED] is encode_separated

    def test_handler_satisfies_protocol(self) -> None:
        from temper_placer.placer.cp_sat.handlers._protocol import ConstraintHandler

        assert isinstance(encode_separated, ConstraintHandler)
