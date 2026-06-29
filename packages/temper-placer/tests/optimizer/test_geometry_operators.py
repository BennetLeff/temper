"""
Tests for geometry-aware mutation operators (PowerSynth-style).

These tests verify the new operator pool added to NSGA-II for
PCB-domain-specific mutations.
"""

import jax
import jax.numpy as jnp
import numpy as np

from temper_placer.optimizer.nsga2 import (
    apply_mutation_pool,
    mutate_align_to_grid,
    mutate_push_to_edge,
    mutate_rotate_smart,
    mutate_slide_to_neighbor,
    mutate_swap_positions,
)


class TestSwapMutation:
    """Tests for mutate_swap_positions."""

    def test_swap_preserves_position_set(self):
        """Swap mutation doesn't lose or duplicate positions."""
        positions = jnp.array([[0.0, 0.0], [10.0, 10.0], [20.0, 20.0], [30.0, 30.0]])
        key = jax.random.PRNGKey(42)

        new_positions, applied = mutate_swap_positions(positions, key, rate=1.0)

        # Same number of components
        assert new_positions.shape == positions.shape

        # Same set of positions (just reordered)
        orig_set = set(map(tuple, np.array(positions)))
        new_set = set(map(tuple, np.array(new_positions)))
        assert orig_set == new_set

    def test_swap_rate_respected(self):
        """Swap mutation respects rate parameter."""
        positions = jnp.array([[0.0, 0.0], [10.0, 10.0]])

        # With rate=0, should never mutate
        applied_count = 0
        for i in range(100):
            key = jax.random.PRNGKey(i)
            _, applied = mutate_swap_positions(positions, key, rate=0.0)
            if applied:
                applied_count += 1
        assert applied_count == 0

    def test_swap_single_component_returns_unchanged(self):
        """Single component can't be swapped."""
        positions = jnp.array([[5.0, 5.0]])
        key = jax.random.PRNGKey(42)

        new_positions, applied = mutate_swap_positions(positions, key, rate=1.0)

        assert not applied
        assert jnp.allclose(new_positions, positions)


class TestSlideToNeighbor:
    """Tests for mutate_slide_to_neighbor."""

    def test_slide_moves_toward_neighbor(self):
        """Slide mutation moves component toward connected neighbor."""
        # Component 0 at origin, component 1 at (100, 0)
        positions = jnp.array([[0.0, 0.0], [100.0, 0.0]])
        # Component 0 strongly connected to component 1
        adjacency = jnp.array([[0.0, 10.0], [10.0, 0.0]])
        key = jax.random.PRNGKey(42)

        # Force mutation on component 0 by using det. key that selects it
        for i in range(100):
            key = jax.random.PRNGKey(i)
            new_positions, applied = mutate_slide_to_neighbor(
                positions, key, adjacency, rate=1.0, slide_fraction=0.3
            )
            if applied:
                # One component moved
                moved_0 = not jnp.allclose(new_positions[0], positions[0])
                moved_1 = not jnp.allclose(new_positions[1], positions[1])
                assert moved_0 or moved_1, "At least one should move"
                break

    def test_slide_with_no_connections_returns_unchanged(self):
        """No connections means no movement."""
        positions = jnp.array([[0.0, 0.0], [10.0, 10.0]])
        adjacency = jnp.zeros((2, 2))
        key = jax.random.PRNGKey(42)

        new_positions, applied = mutate_slide_to_neighbor(
            positions, key, adjacency, rate=1.0
        )

        # Should not apply (no neighbors to slide toward)
        assert not applied


class TestRotateSmart:
    """Tests for mutate_rotate_smart."""

    def test_rotate_changes_rotation(self):
        """Rotation mutation changes component orientation."""
        # Start with rotation 0 (one-hot)
        rotations = jnp.array([
            [1.0, 0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0, 0.0],
        ])

        rotation_changed = False
        for i in range(100):
            key = jax.random.PRNGKey(i)
            new_rotations, applied = mutate_rotate_smart(rotations, key, rate=1.0)
            if applied:
                # Check that at least one rotation changed
                orig_rot = jnp.argmax(rotations, axis=1)
                new_rot = jnp.argmax(new_rotations, axis=1)
                if not jnp.allclose(orig_rot, new_rot):
                    rotation_changed = True
                    break

        assert rotation_changed, "At least one rotation should change"

    def test_rotate_produces_valid_rotation(self):
        """Rotation stays in valid range [0, 3]."""
        rotations = jnp.array([[1.0, 0.0, 0.0, 0.0]])
        key = jax.random.PRNGKey(42)

        new_rotations, _ = mutate_rotate_smart(rotations, key, rate=1.0)

        # Argmax should be in [0, 3]
        rot_idx = int(jnp.argmax(new_rotations[0]))
        assert 0 <= rot_idx <= 3


class TestAlignToGrid:
    """Tests for mutate_align_to_grid."""

    def test_grid_snaps_correctly(self):
        """Grid alignment snaps to nearest grid point."""
        positions = jnp.array([[1.1, 2.2], [3.7, 4.9]])
        grid_size = 2.54  # 100 mil
        key = jax.random.PRNGKey(42)

        new_positions, applied = mutate_align_to_grid(
            positions, key, grid_size=grid_size, rate=1.0
        )

        if applied:
            # Check that modified positions are on grid
            for i in range(positions.shape[0]):
                if not jnp.allclose(positions[i], new_positions[i]):
                    # This position was snapped
                    x_on_grid = abs(new_positions[i, 0] % grid_size) < 0.01 or \
                                abs(new_positions[i, 0] % grid_size - grid_size) < 0.01
                    y_on_grid = abs(new_positions[i, 1] % grid_size) < 0.01 or \
                                abs(new_positions[i, 1] % grid_size - grid_size) < 0.01
                    assert x_on_grid and y_on_grid


class TestPushToEdge:
    """Tests for mutate_push_to_edge."""

    def test_push_moves_toward_edge(self):
        """Push mutation moves component toward nearest board edge."""
        # Component in center-ish position
        positions = jnp.array([[30.0, 40.0]])
        board_width = 100.0
        board_height = 100.0
        key = jax.random.PRNGKey(42)

        new_positions, applied = mutate_push_to_edge(
            positions, key, board_width, board_height, rate=1.0
        )

        if applied:
            # Component should have moved
            assert not jnp.allclose(positions, new_positions)

            # Distance to at least one edge should be smaller
            orig_min_dist = min(positions[0, 0], board_width - positions[0, 0],
                               positions[0, 1], board_height - positions[0, 1])
            new_min_dist = min(new_positions[0, 0], board_width - new_positions[0, 0],
                              new_positions[0, 1], board_height - new_positions[0, 1])
            assert new_min_dist < orig_min_dist

    def test_push_respects_thermal_mask(self):
        """Push with thermal mask only moves thermal components."""
        positions = jnp.array([[30.0, 30.0], [70.0, 70.0]])
        thermal_mask = jnp.array([True, False])  # Only first is thermal
        key = jax.random.PRNGKey(42)

        for i in range(50):
            key = jax.random.PRNGKey(i)
            new_positions, applied = mutate_push_to_edge(
                positions, key, 100.0, 100.0, thermal_mask, rate=1.0
            )
            if applied:
                # Only first component should move
                assert not jnp.allclose(new_positions[0], positions[0])
                # Second stays put (not thermal)
                assert jnp.allclose(new_positions[1], positions[1])
                break


class TestMutationPool:
    """Tests for apply_mutation_pool."""

    def test_pool_returns_valid_shapes(self):
        """Mutation pool returns correctly shaped arrays."""
        positions = jnp.array([[10.0, 20.0], [30.0, 40.0], [50.0, 60.0]])
        rotations = jnp.array([[1.0, 0.0, 0.0, 0.0]] * 3)
        key = jax.random.PRNGKey(42)

        new_positions, new_rotations = apply_mutation_pool(
            positions, rotations, key, 100.0, 100.0
        )

        assert new_positions.shape == positions.shape
        assert new_rotations.shape == rotations.shape

    def test_pool_uses_adjacency_when_provided(self):
        """Mutation pool can use adjacency for slide operator."""
        positions = jnp.array([[10.0, 10.0], [90.0, 90.0]])
        rotations = jnp.array([[1.0, 0.0, 0.0, 0.0]] * 2)
        adjacency = jnp.array([[0.0, 5.0], [5.0, 0.0]])
        key = jax.random.PRNGKey(42)

        # Run multiple times to ensure slide operator gets selected
        for i in range(100):
            key = jax.random.PRNGKey(i)
            new_positions, _ = apply_mutation_pool(
                positions, rotations, key, 100.0, 100.0,
                adjacency=adjacency,
                operator_weights=(0.0, 0.0, 1.0, 0.0, 0.0, 0.0)  # Force slide
            )
            # Should not crash and should potentially modify positions
            assert new_positions.shape == positions.shape

    def test_pool_produces_diverse_outputs(self):
        """Different runs should produce diverse mutations."""
        positions = jnp.array([[50.0, 50.0], [60.0, 60.0]])
        rotations = jnp.array([[1.0, 0.0, 0.0, 0.0]] * 2)

        outputs = set()
        for i in range(50):
            key = jax.random.PRNGKey(i)
            new_pos, new_rot = apply_mutation_pool(
                positions, rotations, key, 100.0, 100.0
            )
            # Hash the output
            outputs.add((tuple(np.array(new_pos).flatten()),
                        tuple(np.array(new_rot).flatten())))

        # Should have some diversity
        assert len(outputs) > 1, "Should produce at least 2 different outputs"


class TestLegalizeIndividualFast:
    """Tests for legalize_individual_fast in legalization.py."""

    def test_clamps_to_bounds(self):
        """Legalization clamps positions to board bounds."""
        from temper_placer.core.board import Board, LayerStackup
        from temper_placer.optimizer.legalization import legalize_individual_fast

        board = Board(
            width=100, height=100, origin=(0, 0),
            layer_stackup=LayerStackup.default_4layer()
        )
        # Position outside board
        positions = np.array([[-10.0, -10.0], [150.0, 150.0]])
        widths = np.array([5.0, 5.0])
        heights = np.array([5.0, 5.0])

        result = legalize_individual_fast(positions, widths, heights, board)

        # Should be clamped inside board
        assert result[0, 0] >= 0
        assert result[0, 1] >= 0
        assert result[1, 0] <= 100
        assert result[1, 1] <= 100

    def test_resolves_overlaps(self):
        """Legalization resolves overlapping components."""
        from temper_placer.core.board import Board, LayerStackup
        from temper_placer.optimizer.legalization import legalize_individual_fast

        board = Board(
            width=100, height=100, origin=(0, 0),
            layer_stackup=LayerStackup.default_4layer()
        )
        # Two components at same position (overlapping)
        positions = np.array([[50.0, 50.0], [50.0, 50.0]])
        widths = np.array([10.0, 10.0])
        heights = np.array([10.0, 10.0])

        result = legalize_individual_fast(positions, widths, heights, board, margin=0.5)

        # Should have pushed them apart
        dist = np.linalg.norm(result[0] - result[1])
        # Minimum separation should be w/2 + w/2 + margin = 10 + 0.5
        assert dist >= 10.0, f"Components too close: {dist}"


class TestFixedComponentHandling:
    """Tests for fixed component handling in mutation operators."""

    def test_mutation_pool_respects_fixed_mask(self):
        """Fixed components are not mutated by mutation pool."""
        positions = jnp.array([[10.0, 20.0], [30.0, 40.0], [50.0, 60.0]])
        rotations = jnp.array([[1.0, 0.0, 0.0, 0.0]] * 3)
        fixed_mask = jnp.array([True, False, True])  # Fix first and third
        key = jax.random.PRNGKey(42)

        # Run mutation multiple times
        for i in range(20):
            key = jax.random.PRNGKey(i)
            new_positions, new_rotations = apply_mutation_pool(
                positions, rotations, key, 100.0, 100.0,
                fixed_mask=fixed_mask
            )

            # Fixed components should not change
            assert jnp.allclose(new_positions[0], positions[0]), "Component 0 should be fixed"
            assert jnp.allclose(new_positions[2], positions[2]), "Component 2 should be fixed"
            assert jnp.allclose(new_rotations[0], rotations[0]), "Rotation 0 should be fixed"
            assert jnp.allclose(new_rotations[2], rotations[2]), "Rotation 2 should be fixed"

    def test_legalize_individual_fast_respects_fixed_mask(self):
        """Fixed components are not moved during legalization."""
        from temper_placer.core.board import Board, LayerStackup
        from temper_placer.optimizer.legalization import legalize_individual_fast

        board = Board(
            width=100, height=100, origin=(0, 0),
            layer_stackup=LayerStackup.default_4layer()
        )

        # Two overlapping components, first is fixed
        positions = np.array([[50.0, 50.0], [50.0, 50.0]])
        widths = np.array([10.0, 10.0])
        heights = np.array([10.0, 10.0])
        fixed_mask = np.array([True, False])

        result = legalize_individual_fast(
            positions, widths, heights, board, fixed_mask=fixed_mask, margin=0.5
        )

        # Fixed component should not move
        assert np.allclose(result[0], positions[0]), "Fixed component should not move"
        # Non-fixed component should be pushed away
        assert not np.allclose(result[1], positions[1]), "Non-fixed component should move"

    def test_both_fixed_components_stay_overlapped(self):
        """If both overlapping components are fixed, they stay overlapped."""
        from temper_placer.core.board import Board, LayerStackup
        from temper_placer.optimizer.legalization import legalize_individual_fast

        board = Board(
            width=100, height=100, origin=(0, 0),
            layer_stackup=LayerStackup.default_4layer()
        )

        # Two overlapping components, both fixed
        positions = np.array([[50.0, 50.0], [50.0, 50.0]])
        widths = np.array([10.0, 10.0])
        heights = np.array([10.0, 10.0])
        fixed_mask = np.array([True, True])

        result = legalize_individual_fast(
            positions, widths, heights, board, fixed_mask=fixed_mask, margin=0.5
        )

        # Both should stay at original positions (even though overlapping)
        assert np.allclose(result[0], positions[0])
        assert np.allclose(result[1], positions[1])

    def test_mixed_population_fixed_and_free(self):
        """Population with mix of fixed and free components works correctly."""
        positions = jnp.array([
            [10.0, 10.0],  # Fixed
            [20.0, 20.0],  # Free
            [30.0, 30.0],  # Free
            [40.0, 40.0],  # Fixed
        ])
        rotations = jnp.array([[1.0, 0.0, 0.0, 0.0]] * 4)
        fixed_mask = jnp.array([True, False, False, True])
        key = jax.random.PRNGKey(42)

        new_positions, new_rotations = apply_mutation_pool(
            positions, rotations, key, 100.0, 100.0,
            fixed_mask=fixed_mask
        )

        # Fixed components unchanged
        assert jnp.allclose(new_positions[0], positions[0])
        assert jnp.allclose(new_positions[3], positions[3])
        # Shape preserved
        assert new_positions.shape == positions.shape
        assert new_rotations.shape == rotations.shape
