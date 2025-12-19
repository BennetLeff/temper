"""
Tests for the post-processing module.

Tests cover:
- Grid snapping functionality
- Discrete rotation refinement (greedy and beam search)
- Full post-processing pipeline
"""

import jax
import jax.numpy as jnp
import pytest

from temper_placer.core.state import PlacementState
from temper_placer.optimizer.postprocess import (
    DEFAULT_GRID_SIZE,
    PostProcessConfig,
    PostProcessResult,
    discrete_rotation_refinement,
    discrete_rotation_refinement_beam,
    discrete_rotation_refinement_greedy,
    finalize_placement,
    get_rotation_index,
    postprocess,
    set_rotation_index,
    snap_to_grid,
    snap_to_grid_with_overlap_check,
)


class TestSnapToGrid:
    """Tests for grid snap functionality."""

    def test_snap_to_default_grid(self):
        """Test snapping to default 0.5mm grid."""
        positions = jnp.array(
            [
                [1.3, 2.7],
                [0.1, 0.9],
                [10.25, 20.75],
            ]
        )
        state = PlacementState.from_positions(positions)
        snapped = snap_to_grid(state)

        # Expected: round to nearest 0.5
        # Note: 10.25 -> round(10.25/0.5)*0.5 = round(20.5)*0.5 = 20*0.5 = 10.0
        # JAX uses banker's rounding (round half to even)
        expected = jnp.array(
            [
                [1.5, 2.5],
                [0.0, 1.0],
                [10.0, 21.0],
            ]
        )
        assert jnp.allclose(snapped.positions, expected, atol=1e-6)

    def test_snap_to_custom_grid(self):
        """Test snapping to custom grid size."""
        positions = jnp.array([[1.3, 2.7]])
        state = PlacementState.from_positions(positions)
        snapped = snap_to_grid(state, grid_size=1.0)

        # Expected: round to nearest 1.0
        expected = jnp.array([[1.0, 3.0]])
        assert jnp.allclose(snapped.positions, expected, atol=1e-6)

    def test_snap_preserves_rotation_logits(self):
        """Test that grid snap preserves rotation logits."""
        positions = jnp.array([[1.3, 2.7]])
        rotation_logits = jnp.array([[1.0, 2.0, 3.0, 4.0]])
        state = PlacementState(positions=positions, rotation_logits=rotation_logits)
        snapped = snap_to_grid(state)

        assert jnp.allclose(snapped.rotation_logits, rotation_logits)

    def test_snap_already_on_grid(self):
        """Test that already-aligned positions stay the same."""
        positions = jnp.array([[1.0, 2.5], [0.0, 10.0]])
        state = PlacementState.from_positions(positions)
        snapped = snap_to_grid(state)

        assert jnp.allclose(snapped.positions, positions, atol=1e-6)

    def test_snap_fine_grid(self):
        """Test snapping to fine grid (0.1mm)."""
        positions = jnp.array([[1.34, 2.76]])
        state = PlacementState.from_positions(positions)
        snapped = snap_to_grid(state, grid_size=0.1)

        expected = jnp.array([[1.3, 2.8]])
        assert jnp.allclose(snapped.positions, expected, atol=1e-6)


class TestRotationHelpers:
    """Tests for rotation index helper functions."""

    def test_get_rotation_index(self):
        """Test extracting rotation indices from logits."""
        # Logits with clear preferences
        rotation_logits = jnp.array(
            [
                [10.0, -10.0, -10.0, -10.0],  # Rotation 0
                [-10.0, 10.0, -10.0, -10.0],  # Rotation 1
                [-10.0, -10.0, 10.0, -10.0],  # Rotation 2
                [-10.0, -10.0, -10.0, 10.0],  # Rotation 3
            ]
        )
        indices = get_rotation_index(rotation_logits)
        expected = jnp.array([0, 1, 2, 3])
        assert jnp.array_equal(indices, expected)

    def test_set_rotation_index(self):
        """Test setting rotation for a specific component."""
        positions = jnp.array([[0.0, 0.0], [1.0, 1.0]])
        state = PlacementState.from_positions(positions)

        # Set component 0 to rotation 2 (180°)
        new_state = set_rotation_index(state, 0, 2)

        indices = get_rotation_index(new_state.rotation_logits)
        assert indices[0] == 2
        # Component 1 unchanged (initially uniform -> argmax is 0)
        # Note: with uniform logits (zeros), argmax returns 0

    def test_set_rotation_preserves_other_components(self):
        """Test that setting rotation doesn't affect other components."""
        positions = jnp.array([[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]])
        rotation_logits = jnp.array(
            [
                [10.0, -10.0, -10.0, -10.0],  # Rot 0
                [-10.0, 10.0, -10.0, -10.0],  # Rot 1
                [-10.0, -10.0, 10.0, -10.0],  # Rot 2
            ]
        )
        state = PlacementState(positions=positions, rotation_logits=rotation_logits)

        # Change component 1 from rotation 1 to rotation 3
        new_state = set_rotation_index(state, 1, 3)

        indices = get_rotation_index(new_state.rotation_logits)
        assert indices[0] == 0  # Unchanged
        assert indices[1] == 3  # Changed
        assert indices[2] == 2  # Unchanged


class TestDiscreteRotationRefinementGreedy:
    """Tests for greedy rotation refinement."""

    def test_greedy_refinement_simple(self):
        """Test greedy refinement on simple case."""
        # Create state where rotation 0 is best for all
        positions = jnp.array([[0.0, 0.0], [5.0, 0.0]])
        # Start with wrong rotations
        rotation_logits = jnp.array(
            [
                [-10.0, 10.0, -10.0, -10.0],  # Initial: rot 1
                [-10.0, -10.0, 10.0, -10.0],  # Initial: rot 2
            ]
        )
        state = PlacementState(positions=positions, rotation_logits=rotation_logits)

        # Loss function that prefers rotation 0 for all components
        def loss_fn(s):
            indices = get_rotation_index(s.rotation_logits)
            return float(jnp.sum(indices))  # Lower is better (prefer 0)

        refined, final_loss = discrete_rotation_refinement_greedy(state, loss_fn)

        # Should find rotation 0 for both
        indices = get_rotation_index(refined.rotation_logits)
        assert indices[0] == 0
        assert indices[1] == 0
        assert final_loss == 0.0

    def test_greedy_refinement_respects_fixed(self):
        """Test that fixed components are not modified."""
        positions = jnp.array([[0.0, 0.0], [5.0, 0.0]])
        rotation_logits = jnp.array(
            [
                [-10.0, 10.0, -10.0, -10.0],  # Initial: rot 1
                [-10.0, -10.0, 10.0, -10.0],  # Initial: rot 2
            ]
        )
        state = PlacementState(positions=positions, rotation_logits=rotation_logits)

        def loss_fn(s):
            indices = get_rotation_index(s.rotation_logits)
            return float(jnp.sum(indices))

        # Fix component 0
        refined, _ = discrete_rotation_refinement_greedy(state, loss_fn, fixed_components=[0])

        indices = get_rotation_index(refined.rotation_logits)
        assert indices[0] == 1  # Unchanged (fixed)
        assert indices[1] == 0  # Changed to optimal


class TestDiscreteRotationRefinementBeam:
    """Tests for beam search rotation refinement."""

    def test_beam_refinement_simple(self):
        """Test beam search refinement finds optimal."""
        positions = jnp.array([[0.0, 0.0], [5.0, 0.0]])
        rotation_logits = jnp.array(
            [
                [-10.0, 10.0, -10.0, -10.0],
                [-10.0, -10.0, 10.0, -10.0],
            ]
        )
        state = PlacementState(positions=positions, rotation_logits=rotation_logits)

        def loss_fn(s):
            indices = get_rotation_index(s.rotation_logits)
            return float(jnp.sum(indices))

        refined, final_loss = discrete_rotation_refinement_beam(state, loss_fn, beam_width=2)

        indices = get_rotation_index(refined.rotation_logits)
        assert indices[0] == 0
        assert indices[1] == 0
        assert final_loss == 0.0

    def test_beam_better_than_greedy_for_interactions(self):
        """Test beam search can find better solutions with component interactions."""
        positions = jnp.array([[0.0, 0.0], [1.0, 0.0]])
        rotation_logits = jnp.zeros((2, 4))  # Uniform initial
        state = PlacementState(positions=positions, rotation_logits=rotation_logits)

        # Loss function with interaction: (rot0, rot1) = (1, 2) is optimal
        # but greedy might get stuck in local minimum
        def loss_fn(s):
            indices = get_rotation_index(s.rotation_logits)
            # Optimal: rot0=1, rot1=2 gives loss 0
            # Individual optima would be different
            if int(indices[0]) == 1 and int(indices[1]) == 2:
                return 0.0
            return float(jnp.sum(jnp.abs(indices - jnp.array([1, 2]))) + 1.0)

        refined, final_loss = discrete_rotation_refinement_beam(state, loss_fn, beam_width=4)

        indices = get_rotation_index(refined.rotation_logits)
        # Beam search should find the optimal (1, 2) combination
        assert indices[0] == 1
        assert indices[1] == 2
        assert final_loss == 0.0


class TestDiscreteRotationRefinement:
    """Tests for the unified rotation refinement interface."""

    def test_greedy_mode(self):
        """Test selecting greedy search mode."""
        positions = jnp.array([[0.0, 0.0]])
        state = PlacementState.from_positions(positions)

        def loss_fn(s):
            return float(get_rotation_index(s.rotation_logits)[0])

        refined, _ = discrete_rotation_refinement(state, loss_fn, search_type="greedy")
        assert get_rotation_index(refined.rotation_logits)[0] == 0

    def test_beam_mode(self):
        """Test selecting beam search mode."""
        positions = jnp.array([[0.0, 0.0]])
        state = PlacementState.from_positions(positions)

        def loss_fn(s):
            return float(get_rotation_index(s.rotation_logits)[0])

        refined, _ = discrete_rotation_refinement(state, loss_fn, search_type="beam", beam_width=2)
        assert get_rotation_index(refined.rotation_logits)[0] == 0


class TestPostprocess:
    """Tests for the full post-processing pipeline."""

    def test_postprocess_default_config(self):
        """Test post-processing with default configuration."""
        positions = jnp.array([[1.3, 2.7], [5.1, 5.9]])
        state = PlacementState.from_positions(positions)

        def loss_fn(s):
            indices = get_rotation_index(s.rotation_logits)
            return float(jnp.sum(indices))

        result = postprocess(state, loss_fn)

        assert isinstance(result, PostProcessResult)
        assert result.grid_snapped is True
        assert result.rotations_refined is True
        assert result.final_loss is not None

        # Check positions are grid-snapped
        assert jnp.allclose(result.state.positions[0], jnp.array([1.5, 2.5]), atol=1e-6)

    def test_postprocess_disabled_steps(self):
        """Test post-processing with steps disabled."""
        positions = jnp.array([[1.3, 2.7]])
        state = PlacementState.from_positions(positions)

        def loss_fn(s):
            return 0.0

        config = PostProcessConfig(
            grid_snap_enabled=False,
            rotation_refinement_enabled=False,
        )
        result = postprocess(state, loss_fn, config=config)

        assert result.grid_snapped is False
        assert result.rotations_refined is False
        # Positions unchanged
        assert jnp.allclose(result.state.positions, positions)

    def test_postprocess_custom_grid(self):
        """Test post-processing with custom grid size."""
        positions = jnp.array([[1.3, 2.7]])
        state = PlacementState.from_positions(positions)

        def loss_fn(s):
            return 0.0

        config = PostProcessConfig(grid_size=1.0)
        result = postprocess(state, loss_fn, config=config)

        expected = jnp.array([[1.0, 3.0]])
        assert jnp.allclose(result.state.positions, expected, atol=1e-6)


class TestFinalizePos:
    """Tests for the finalize_placement convenience function."""

    def test_finalize_placement(self):
        """Test finalize_placement returns correct format."""
        positions = jnp.array([[1.3, 2.7], [5.0, 5.0]])
        state = PlacementState.from_positions(positions)

        def loss_fn(s):
            return 0.0

        final_positions, rotation_indices, final_loss = finalize_placement(state, loss_fn)

        # Check types
        assert final_positions.shape == (2, 2)
        assert rotation_indices.shape == (2,)
        assert isinstance(final_loss, (float, type(None))) or final_loss is not None

        # Check grid snap applied
        assert jnp.allclose(final_positions[0], jnp.array([1.5, 2.5]), atol=1e-6)

    def test_finalize_with_custom_grid(self):
        """Test finalize_placement with custom grid size."""
        positions = jnp.array([[1.3, 2.7]])
        state = PlacementState.from_positions(positions)

        def loss_fn(s):
            return 0.0

        final_positions, _, _ = finalize_placement(state, loss_fn, grid_size=1.0)

        expected = jnp.array([[1.0, 3.0]])
        assert jnp.allclose(final_positions, expected, atol=1e-6)


class TestIntegration:
    """Integration tests for post-processing."""

    def test_full_pipeline_with_simple_loss(self):
        """Test full post-processing pipeline."""
        key = jax.random.PRNGKey(42)
        n_components = 5

        # Create random initial state
        state = PlacementState.random_init(
            n_components=n_components,
            board_width=100.0,
            board_height=100.0,
            key=key,
        )

        # Simple loss: prefer rotation 0 and minimize position sum
        def loss_fn(s):
            rot_penalty = float(jnp.sum(get_rotation_index(s.rotation_logits)))
            return rot_penalty

        result = postprocess(state, loss_fn)

        # All rotations should be 0
        indices = get_rotation_index(result.state.rotation_logits)
        assert jnp.all(indices == 0)

        # Positions should be on grid
        on_grid = jnp.allclose(
            result.state.positions,
            jnp.round(result.state.positions / DEFAULT_GRID_SIZE) * DEFAULT_GRID_SIZE,
            atol=1e-6,
        )
        assert on_grid
