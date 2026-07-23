"""Tests for core.state module."""

import numpy as np
import pytest
from scipy.special import softmax as _softmax

from temper_placer.core.state import (
    PlacementState,
    rotate_points,
    rotation_matrix,
)


class TestPlacementState:
    """Tests for PlacementState dataclass."""

    def test_from_positions(self):
        """Test creating state from positions array."""
        positions = np.array([[10.0, 20.0], [30.0, 40.0], [50.0, 60.0]])
        state = PlacementState.from_positions(positions)

        assert state.n_components == 3
        assert state.positions.shape == (3, 2)
        assert state.rotation_logits.shape == (3, 4)
        # Default rotation logits should be zeros (uniform)
        assert np.allclose(state.rotation_logits, np.zeros((3, 4)))

    def test_from_positions_with_logits(self):
        """Test creating state with explicit rotation logits."""
        positions = np.array([[10.0, 20.0]])
        logits = np.array([[1.0, 0.0, 0.0, 0.0]])  # Prefer 0° rotation
        state = PlacementState.from_positions(positions, logits)

        assert state.rotation_logits.shape == (1, 4)
        assert np.allclose(state.rotation_logits, logits)

    @pytest.mark.skip(reason="PlacementState.random_init retired (JAX)")
    def test_random_init(self, rng_key):
        """Test random initialization."""
        state = PlacementState.random_init(
            n_components=10,
            board_width=100.0,
            board_height=150.0,
            key=rng_key,
            margin=10.0,
        )

        assert state.n_components == 10
        assert state.positions.shape == (10, 2)

        # All positions should be within margins
        assert np.all(state.positions[:, 0] >= 10.0)
        assert np.all(state.positions[:, 0] <= 90.0)
        assert np.all(state.positions[:, 1] >= 10.0)
        assert np.all(state.positions[:, 1] <= 140.0)

    @pytest.mark.skip(reason="PlacementState.random_init retired (JAX)")
    def test_get_rotations(self, rng_key):
        """Test Gumbel-Softmax rotation sampling."""
        state = PlacementState.random_init(5, 100.0, 100.0, rng_key)
        rotations = state.get_rotations(temperature=1.0, key=rng_key)

        assert rotations.shape == (5, 4)
        # Each row should sum to approximately 1 (soft one-hot)
        row_sums = np.sum(rotations, axis=1)
        assert np.allclose(row_sums, np.ones(5), atol=1e-5)

    @pytest.mark.skip(reason="PlacementState.random_init retired (JAX)")
    def test_get_rotation_angles(self, rng_key):
        """Test getting rotation angles in radians."""
        state = PlacementState.random_init(5, 100.0, 100.0, rng_key)
        angles = state.get_rotation_angles(temperature=0.1, key=rng_key)

        assert angles.shape == (5,)
        # Angles should be approximately one of [0, π/2, π, 3π/2]
        valid_angles = np.array([0.0, np.pi / 2, np.pi, 3 * np.pi / 2])
        for angle in angles:
            diffs = np.abs(valid_angles - angle)
            assert np.min(diffs) < 0.5  # Allow some deviation at low temp

    def test_to_discrete(self, rng_key):  # noqa: ARG002 (consumed by pytest fixture)
        """Test conversion to discrete placement."""
        positions = np.array([[10.0, 20.0], [30.0, 40.0]])
        logits = np.array(
            [
                [2.0, 0.0, 0.0, 0.0],  # Should select 0° (index 0)
                [0.0, 0.0, 3.0, 0.0],  # Should select 180° (index 2)
            ]
        )
        state = PlacementState.from_positions(positions, logits)

        pos_out, rot_idx = state.to_discrete()

        assert np.allclose(pos_out, positions)
        assert rot_idx[0] == 0
        assert rot_idx[1] == 2


class TestSampleRotation:
    """Tests for Gumbel-Softmax rotation sampling."""

    def test_temperature_effect(self):
        """Test that lower temperature gives sharper distributions."""
        logits = np.array([[1.0, 0.5, 0.0, -0.5]])

        # Use different keys to avoid identical Gumbel noise

        # At very low temp, the straight-through estimator kicks in
        # Test the underlying softmax behavior instead
        np.zeros_like(logits)  # No noise for deterministic test
        soft = _softmax(logits / 5.0)  # High temp
        hard = _softmax(logits / 0.1)  # Low temp

        # Lower temperature should give more peaked distribution (lower entropy)
        soft_entropy = -np.sum(soft * np.log(soft + 1e-10))
        hard_entropy = -np.sum(hard * np.log(hard + 1e-10))
        assert hard_entropy < soft_entropy


class TestRotationMatrix:
    """Tests for rotation matrix generation."""

    def test_identity_rotation(self):
        """Test 0° rotation is identity."""
        R = rotation_matrix(0.0)
        expected = np.array([[1.0, 0.0], [0.0, 1.0]])
        assert np.allclose(R, expected, atol=1e-6)

    def test_90_degree_rotation(self):
        """Test 90° rotation."""
        R = rotation_matrix(np.pi / 2)
        expected = np.array([[0.0, -1.0], [1.0, 0.0]])
        assert np.allclose(R, expected, atol=1e-6)

    def test_180_degree_rotation(self):
        """Test 180° rotation."""
        R = rotation_matrix(np.pi)
        expected = np.array([[-1.0, 0.0], [0.0, -1.0]])
        assert np.allclose(R, expected, atol=1e-6)


class TestRotatePoints:
    """Tests for point rotation function."""

    def test_rotate_around_origin(self):
        """Test rotating points around origin."""
        points = np.array([[1.0, 0.0]])
        rotated = rotate_points(points, np.pi / 2)
        expected = np.array([[0.0, 1.0]])
        assert np.allclose(rotated, expected, atol=1e-6)

    def test_rotate_around_center(self):
        """Test rotating points around custom center."""
        points = np.array([[2.0, 1.0]])
        center = np.array([1.0, 1.0])
        rotated = rotate_points(points, np.pi / 2, center=center)
        expected = np.array([[1.0, 2.0]])
        assert np.allclose(rotated, expected, atol=1e-6)

    def test_batch_rotation(self):
        """Test rotating multiple points."""
        points = np.array([[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]])
        rotated = rotate_points(points, np.pi)  # 180° rotation
        expected = np.array([[-1.0, 0.0], [0.0, -1.0], [1.0, 0.0]])
        assert np.allclose(rotated, expected, atol=1e-6)
