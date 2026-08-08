"""Tests for core.state module (additional coverage)."""

import numpy as np

from temper_placer.core.state import PlacementState


class TestPlacementStateFromDict:
    """Tests for PlacementState.from_positions_dict."""

    def test_from_positions_dict_with_order(self):
        """Creating from dict with explicit component_order."""
        positions_dict = {"U1": (10.0, 20.0), "R1": (30.0, 40.0), "C1": (50.0, 60.0)}
        state = PlacementState.from_positions_dict(
            positions_dict, component_order=["U1", "R1", "C1"]
        )
        assert state.n_components == 3
        assert state.positions.shape == (3, 2)
        assert np.allclose(state.positions[0], [10.0, 20.0])
        assert np.allclose(state.positions[1], [30.0, 40.0])
        assert np.allclose(state.positions[2], [50.0, 60.0])

    def test_from_positions_dict_with_logits(self):
        """With explicit rotation logits."""
        positions_dict = {"U1": (10.0, 20.0)}
        logits = np.array([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32)
        state = PlacementState.from_positions_dict(
            positions_dict,
            component_order=["U1"],
            rotation_logits=logits,
        )
        assert np.allclose(state.rotation_logits, logits)

    def test_from_positions_dict_missing_component(self):
        """Component in order but not in dict gets (0,0)."""
        positions_dict = {"U1": (10.0, 20.0)}
        state = PlacementState.from_positions_dict(
            positions_dict, component_order=["U1", "R1"]
        )
        assert np.allclose(state.positions[1], [0.0, 0.0])

    def test_from_positions_dict_no_order_raises(self):
        """ValueError if neither netlist nor component_order given."""
        import pytest
        with pytest.raises(ValueError, match="component_order"):
            PlacementState.from_positions_dict({"U1": (10.0, 20.0)})
