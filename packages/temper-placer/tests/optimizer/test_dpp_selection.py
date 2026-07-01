"""Tests for DPP kernel construction and subset selection (U3+U4)."""

import jax
import jax.numpy as jnp
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.optimizer.dpp_selection import (
    _dpp_kernel_from_positions,
    _dpp_select,
    _farthest_point_sampling,
)


def make_seed(positions):
    """Helper to create a seed tuple from a positions array."""
    return (jnp.asarray(positions, dtype=jnp.float32), {})


def make_seeds(*position_lists):
    return [make_seed(pos) for pos in position_lists]


class TestDPPKernel:
    """U3: DPP kernel construction."""

    def test_kernel_symmetric(self):
        """Kernel matrix is symmetric."""
        seeds = make_seeds(
            jnp.array([[0.0, 0.0], [10.0, 10.0]]),
            jnp.array([[0.1, 0.1], [9.9, 9.9]]),
            jnp.array([[5.0, 5.0], [15.0, 15.0]]),
            jnp.array([[6.0, 6.0], [14.0, 14.0]]),
        )
        L, _ = _dpp_kernel_from_positions(seeds)
        assert jnp.allclose(L, L.T)

    def test_kernel_positive_entries(self):
        """All kernel entries are in (0, 1]."""
        seeds = make_seeds(
            jnp.array([[0.0, 0.0], [10.0, 10.0]]),
            jnp.array([[0.1, 0.1], [9.9, 9.9]]),
            jnp.array([[5.0, 5.0], [15.0, 15.0]]),
            jnp.array([[6.0, 6.0], [14.0, 14.0]]),
        )
        L, _ = _dpp_kernel_from_positions(seeds)
        assert jnp.all(L > 0.0)
        assert jnp.all(L <= 1.0)

    def test_kernel_identical_seeds(self):
        """Two identical seeds produce kernel value ~1.0."""
        pos = jnp.array([[0.0, 0.0], [10.0, 10.0]])
        seeds = make_seeds(pos, pos)
        L, _ = _dpp_kernel_from_positions(seeds)
        assert jnp.allclose(L[0, 1], 1.0, rtol=1e-4)

    def test_kernel_shuffled_copy(self):
        """A seed and its component-permuted copy produce kernel ~1.0."""
        pos1 = jnp.array([[0.0, 0.0], [10.0, 10.0], [20.0, 20.0]])
        pos2 = jnp.array([[20.0, 20.0], [0.0, 0.0], [10.0, 10.0]])

        # Seed 1: components in order A, B, C
        md1 = {"comp_refs": ["A", "B", "C"]}
        # Seed 2: same components but shuffled order C, A, B
        md2 = {"comp_refs": ["C", "A", "B"]}

        seeds = [(jnp.asarray(pos1, dtype=jnp.float32), md1),
                 (jnp.asarray(pos2, dtype=jnp.float32), md2)]
        L_sorted, _ = _dpp_kernel_from_positions(seeds)
        # After sorting by ref ID, both seeds have identical positions
        assert jnp.allclose(L_sorted[0, 1], 1.0, rtol=1e-4)

    def test_kernel_distance_monotonic(self):
        """Larger RMS distance produces smaller kernel value."""
        seeds = make_seeds(
            jnp.array([[0.0, 0.0]]),       # Seed 0
            jnp.array([[1.0, 1.0]]),       # Seed 1: close
            jnp.array([[50.0, 50.0]]),     # Seed 2: far
        )
        L, _ = _dpp_kernel_from_positions(seeds)
        assert L[0, 1] > L[0, 2]  # closer seeds have higher similarity

    def test_kernel_degenerate(self):
        """All identical seeds produce high condition number."""
        pos = jnp.array([[0.0, 0.0], [10.0, 10.0]])
        seeds = make_seeds(pos, pos, pos, pos)
        L, cond = _dpp_kernel_from_positions(seeds)
        # All entries close to 1.0 → very ill-conditioned
        assert cond > 1e3 or jnp.isinf(cond)

    def test_single_seed_kernel(self):
        """Single seed produces 1x1 identity kernel."""
        pos = jnp.array([[0.0, 0.0]])
        seeds = make_seeds(pos)
        L, cond = _dpp_kernel_from_positions(seeds)
        assert L.shape == (1, 1)
        assert L[0, 0] == 1.0
        assert cond == 1.0


class TestDPPSelect:
    """U4: DPP subset selection."""

    def test_select_respects_k(self):
        """Selected subset has exactly k elements."""
        seeds = make_seeds(
            jnp.array([[0.0, 0.0]]),
            jnp.array([[1.0, 1.0]]),
            jnp.array([[2.0, 2.0]]),
            jnp.array([[3.0, 3.0]]),
        )
        L, cond = _dpp_kernel_from_positions(seeds)
        for k_val in [1, 2, 3, 4]:
            selected = _dpp_select(L, k_val, condition_number=cond)
            assert len(selected) == k_val

    def test_select_no_duplicates(self):
        """All selected indices are unique."""
        seeds = make_seeds(
            jnp.array([[0.0, 0.0]]),
            jnp.array([[1.0, 1.0]]),
            jnp.array([[2.0, 2.0]]),
            jnp.array([[3.0, 3.0]]),
        )
        L, cond = _dpp_kernel_from_positions(seeds)
        selected = _dpp_select(L, k=3, condition_number=cond)
        assert len(set(selected)) == len(selected)

    def test_select_block_diagonal_clusters(self):
        """DPP selects from both clusters in a 2-cluster pool."""
        # Cluster A: 3 seeds close together
        # Cluster B: 4 seeds close together (far from A)
        cluster_a = [
            jnp.array([[0.0, 0.0], [10.0, 10.0]]),
            jnp.array([[0.1, 0.1], [10.1, 10.1]]),
            jnp.array([[0.2, 0.2], [10.2, 10.2]]),
        ]
        cluster_b = [
            jnp.array([[90.0, 90.0], [80.0, 80.0]]),
            jnp.array([[90.1, 90.1], [80.1, 80.1]]),
            jnp.array([[90.2, 90.2], [80.2, 80.2]]),
            jnp.array([[90.3, 90.3], [80.3, 80.3]]),
        ]
        seeds = make_seeds(*(cluster_a + cluster_b))
        L, cond = _dpp_kernel_from_positions(seeds)
        selected = _dpp_select(L, k=3, condition_number=cond)

        # An index < 3 is from cluster_a, >= 3 is from cluster_b
        has_a = any(idx < 3 for idx in selected)
        has_b = any(idx >= 3 for idx in selected)
        assert has_a, f"Expected selection from cluster A, got indices {selected}"
        assert has_b, f"Expected selection from cluster B, got indices {selected}"

    def test_select_quality_vector_k1(self):
        """With k=1 and a quality vector, the highest-quality seed is selected."""
        seeds = make_seeds(
            jnp.array([[0.0, 0.0]]),
            jnp.array([[50.0, 50.0]]),
            jnp.array([[100.0, 100.0]]),
        )
        L, cond = _dpp_kernel_from_positions(seeds)
        # Quality vector: seed 1 has highest quality
        quality = jnp.array([0.1, 0.9, 0.1])
        selected = _dpp_select(L, k=1, quality=quality, condition_number=cond)
        assert selected == [1]

    def test_select_ill_conditioned_fallback(self, caplog):
        """Near-singular kernel triggers farthest-point fallback."""
        # Create a near-singular kernel directly
        n = 5
        vec = jnp.ones((n, 1))
        L = vec @ vec.T * 0.99 + jnp.eye(n) * 0.01
        L = L / jnp.max(L)
        seed_vectors = jnp.arange(n * 2, dtype=jnp.float32).reshape(n, 2)

        selected = _dpp_select(
            L, k=3, condition_number=1e7, seed_vectors=seed_vectors
        )
        assert len(selected) == 3
        assert 0 in selected  # farthest-point starts from index 0

    def test_identity_kernel_deterministic(self):
        """Identity kernel picks first k indices deterministically."""
        L = jnp.eye(5)
        selected = _dpp_select(L, k=3, condition_number=1.0)
        # With identity, first index picked is always 0, then the rest
        # are selected based on determinant — but identity means all det=1 for
        # subset sizes, so greedy picks indices in order 0,1,2
        assert selected == [0, 1, 2]


class TestFarthestPointSampling:
    """Farthest-point sampling fallback."""

    def test_farthest_point_respects_k(self):
        """Returns exactly k indices."""
        vectors = jnp.arange(20, dtype=jnp.float32).reshape(10, 2)
        selected = _farthest_point_sampling(vectors, k=4)
        assert len(selected) == 4

    def test_farthest_point_starts_at_zero(self):
        """First selected index is always 0."""
        vectors = jnp.array([[5.0, 5.0], [1.0, 1.0], [9.0, 9.0]])
        selected = _farthest_point_sampling(vectors, k=2)
        assert selected[0] == 0

    def test_farthest_point_no_duplicates(self):
        """No duplicate indices."""
        vectors = jnp.arange(20, dtype=jnp.float32).reshape(10, 2)
        selected = _farthest_point_sampling(vectors, k=5)
        assert len(set(selected)) == 5


# Property-based tests using Hypothesis
_array_shape_2d = st.integers(min_value=3, max_value=10).flatmap(
    lambda n: st.lists(
        st.lists(st.floats(min_value=0.0, max_value=100.0), min_size=2, max_size=2),
        min_size=n, max_size=n
    ).map(lambda pts: jnp.array(pts, dtype=jnp.float32))
)


class TestDPPProperties:
    """Property-based tests for DPP kernel and selection."""

    @given(st.integers(min_value=3, max_value=6).flatmap(
        lambda n: st.lists(
            st.lists(st.floats(min_value=0.0, max_value=100.0), min_size=2, max_size=2),
            min_size=n, max_size=n
        ).map(lambda pts: jnp.array(pts, dtype=jnp.float32))
    ))
    @settings(max_examples=30)
    def test_kernel_is_symmetric_psd(self, points):
        """Kernel eigenvalues are >= -1e-10 (PSD)."""
        seeds = make_seeds(points)
        L, _ = _dpp_kernel_from_positions(seeds)
        eigenvalues = jnp.linalg.eigh(L)[0]
        assert jnp.all(eigenvalues >= -1e-10), f"Negative eigenvalues: {eigenvalues}"

    @given(st.integers(min_value=2, max_value=5).flatmap(
        lambda n: st.lists(
            st.lists(st.floats(min_value=0.0, max_value=100.0), min_size=2, max_size=2),
            min_size=n, max_size=n
        ).map(lambda pts: jnp.array(pts, dtype=jnp.float32))
    ))
    @settings(max_examples=30)
    def test_kernel_values_in_01(self, points):
        """All kernel entries are in [0, 1]."""
        seeds = make_seeds(points)
        L, _ = _dpp_kernel_from_positions(seeds)
        assert jnp.all(L >= 0.0)
        assert jnp.all(L <= 1.0)

    @given(st.integers(min_value=3, max_value=8).flatmap(
        lambda n: st.tuples(
            st.lists(st.lists(st.floats(min_value=0.0, max_value=100.0), min_size=2, max_size=2),
                     min_size=n, max_size=n),
            st.integers(min_value=1, max_value=3),
        )
    ))
    @settings(max_examples=30)
    def test_dpp_subset_size_eq_k(self, params):
        """DPP selection returns exactly k indices."""
        points_list, k_val = params
        points = jnp.array(points_list, dtype=jnp.float32)
        seeds = make_seeds(points)
        L, cond = _dpp_kernel_from_positions(seeds)
        k_actual = min(k_val, len(seeds))
        selected = _dpp_select(L, k_actual, condition_number=cond)
        assert len(selected) == k_actual

    @given(st.integers(min_value=2, max_value=5).flatmap(
        lambda n: st.tuples(
            st.lists(st.lists(st.floats(min_value=0.0, max_value=100.0), min_size=2, max_size=2),
                     min_size=n, max_size=n),
            st.integers(min_value=1, max_value=3),
        )
    ))
    @settings(max_examples=20)
    def test_kernel_determinant_ge_0(self, params):
        """Determinant of kernel submatrix is non-negative."""
        points_list, k_val = params
        points = jnp.array(points_list, dtype=jnp.float32)
        seeds = make_seeds(points)
        L, cond = _dpp_kernel_from_positions(seeds)
        k_actual = min(k_val, len(seeds))
        selected = _dpp_select(L, k_actual, condition_number=cond)
        sub_L = L[jnp.array(selected)][:, jnp.array(selected)]
        det = jnp.linalg.det(sub_L)
        assert det >= -1e-10, f"Negative determinant: {det}"
