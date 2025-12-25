"""
Tests for boundary-aware legalization.

TDD tests for vtv5.1: Ensure legalization keeps components within board bounds.
"""

import numpy as np
import pytest
import jax.numpy as jnp

from temper_placer.optimizer.legalization import clamp_to_bounds, project_to_drc_feasible
from temper_placer.core.state import PlacementState
from temper_placer.core.netlist import Netlist, Component
from temper_placer.core.board import Board
from temper_placer.losses.base import LossContext


class TestClampToBounds:
    """Tests for the clamp_to_bounds function."""

    def test_clamp_oob_components(self):
        """Components outside board are clamped inside."""
        # 50x50mm board at origin (0, 0)
        positions = np.array([
            [60.0, 25.0],  # OOB right
            [-5.0, 25.0],  # OOB left
            [25.0, 55.0],  # OOB top
            [25.0, -5.0],  # OOB bottom
            [25.0, 25.0],  # Inside - should stay
        ])
        widths = np.array([10.0, 10.0, 10.0, 10.0, 10.0])  # 10mm wide components
        heights = np.array([10.0, 10.0, 10.0, 10.0, 10.0])

        clamped = clamp_to_bounds(
            positions=positions,
            widths=widths,
            heights=heights,
            board=Board(width=50.0, height=50.0),
        )

        # All should now be inside board (center + half_extent <= board_edge)
        # For a 10mm wide component, center should be in [5, 45]
        assert clamped[0, 0] == 45.0  # Was 60, clamped to 45
        assert clamped[1, 0] == 5.0   # Was -5, clamped to 5
        assert clamped[2, 1] == 45.0  # Was 55, clamped to 45
        assert clamped[3, 1] == 5.0   # Was -5, clamped to 5
        assert clamped[4, 0] == 25.0  # Was inside, unchanged
        assert clamped[4, 1] == 25.0

    def test_clamp_respects_fixed_mask(self):
        """Fixed components should not be clamped."""
        positions = np.array([
            [60.0, 25.0],  # OOB but fixed
            [-5.0, 25.0],  # OOB but movable
        ])
        widths = np.array([10.0, 10.0])
        heights = np.array([10.0, 10.0])
        fixed_mask = np.array([True, False])

        clamped = clamp_to_bounds(
            positions=positions,
            widths=widths,
            heights=heights,
            board=Board(width=50.0, height=50.0),
            fixed_mask=fixed_mask,
        )

        assert clamped[0, 0] == 60.0  # Fixed - not clamped
        assert clamped[1, 0] == 5.0   # Movable - clamped

    def test_clamp_with_margin(self):
        """Margin adds extra distance from board edge."""
        positions = np.array([[25.0, 25.0]])  # Center of 50x50 board
        widths = np.array([40.0])   # 40mm wide - fills most of board
        heights = np.array([10.0])

        # Without margin, center can be in [20, 30] (half_width = 20)
        clamped_no_margin = clamp_to_bounds(
            positions=positions,
            widths=widths,
            heights=heights,
            board=Board(width=50.0, height=50.0),
            margin=0.0,
        )
        assert clamped_no_margin[0, 0] == 25.0  # Fits

        # With 5mm margin, center must be in [25, 25]
        positions_edge = np.array([[22.0, 25.0]])  # Near left edge
        clamped_with_margin = clamp_to_bounds(
            positions=positions_edge,
            widths=widths,
            heights=heights,
            board=Board(width=50.0, height=50.0),
            margin=5.0,
        )
        assert clamped_with_margin[0, 0] == 25.0  # Clamped to center


class TestProjectToDRCFeasible:
    """Tests for the full legalization pipeline."""

    def create_test_context(self, n_components: int = 5, board_size: float = 50.0):
        """Create a minimal LossContext for testing."""
        components = [
            Component(ref=f"U{i}", footprint="Test", bounds=(10.0, 10.0))
            for i in range(n_components)
        ]
        netlist = Netlist(components=components, nets=[])
        board = Board(width=board_size, height=board_size, origin=(0.0, 0.0))
        return LossContext.from_netlist_and_board(
            netlist=netlist,
            board=board,
        )

    def test_legalization_respects_boundaries(self):
        """Legalization clamps all components inside board."""
        positions = jnp.array([
            [60.0, 25.0],  # OOB right
            [25.0, 60.0],  # OOB top
            [25.0, 25.0],  # Inside
        ])
        rotation_logits = jnp.zeros((3, 4))
        state = PlacementState(positions, rotation_logits)
        context = self.create_test_context(n_components=3)

        result = project_to_drc_feasible(state, context)

        # All should be inside board
        for i in range(3):
            pos = result.positions[i]
            hw, hh = 5.0, 5.0  # Half of 10x10mm component
            assert pos[0] >= hw, f"Component {i} too far left"
            assert pos[0] <= 50.0 - hw, f"Component {i} too far right"
            assert pos[1] >= hh, f"Component {i} too far down"
            assert pos[1] <= 50.0 - hh, f"Component {i} too far up"

    def test_boundary_clamping_after_overlap_resolution(self):
        """Ensure boundary clamping happens AFTER overlap resolution."""
        # Two overlapping components near the board edge
        # Overlap resolution might push one OOB - final clamp should fix it
        positions = jnp.array([
            [45.0, 25.0],  # Near right edge
            [48.0, 25.0],  # Overlapping, will be pushed right
        ])
        rotation_logits = jnp.zeros((2, 4))
        state = PlacementState(positions, rotation_logits)
        context = self.create_test_context(n_components=2)

        result = project_to_drc_feasible(state, context)

        # Component pushed right should still be inside bounds
        for i in range(2):
            pos = result.positions[i]
            assert pos[0] <= 45.0, f"Component {i} is outside right bound"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
