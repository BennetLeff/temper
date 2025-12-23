"""
Tests for overlap loss per-component calculation (temper-p11g.4).

Verifies that per-component overlap values sum to total overlap.
"""

import pytest
import jax.numpy as jnp
from temper_placer.losses.overlap import _compute_pairwise_overlaps_vectorized


class TestOverlapPerComponentConsistency:
    """Test that per-component overlaps are consistent with total."""
    
    def test_per_component_sums_to_total_two_components(self):
        """Per-component overlaps should sum to total for 2 overlapping components."""
        # Create 2 overlapping components
        # Component 0 at (0, 0) with 2x2 size
        # Component 1 at (1, 0) with 2x2 size
        # They overlap by 1mm in X direction
        positions = jnp.array([[0.0, 0.0], [1.0, 0.0]], dtype=jnp.float32)
        widths = jnp.array([2.0, 2.0], dtype=jnp.float32)
        heights = jnp.array([2.0, 2.0], dtype=jnp.float32)
        
        total, per_comp = _compute_pairwise_overlaps_vectorized(
            positions, widths, heights, margin=0.0
        )
        
        # Sum of per-component should equal total
        per_comp_sum = float(jnp.sum(per_comp))
        total_val = float(total)
        
        assert abs(per_comp_sum - total_val) < 1e-5, \
            f"Per-component sum ({per_comp_sum}) != total ({total_val})"
    
    def test_per_component_sums_to_total_three_components(self):
        """Per-component overlaps should sum to total for 3 overlapping components."""
        # Create 3 components in a line, each overlapping with neighbors
        positions = jnp.array([
            [0.0, 0.0],
            [1.5, 0.0],  # Overlaps with 0
            [3.0, 0.0],  # Overlaps with 1
        ], dtype=jnp.float32)
        widths = jnp.array([2.0, 2.0, 2.0], dtype=jnp.float32)
        heights = jnp.array([2.0, 2.0, 2.0], dtype=jnp.float32)
        
        total, per_comp = _compute_pairwise_overlaps_vectorized(
            positions, widths, heights, margin=0.0
        )
        
        per_comp_sum = float(jnp.sum(per_comp))
        total_val = float(total)
        
        assert abs(per_comp_sum - total_val) < 1e-5, \
            f"Per-component sum ({per_comp_sum}) != total ({total_val})"
    
    def test_per_component_no_overlap(self):
        """When no overlap, both total and per-component should be zero."""
        # Create 2 non-overlapping components
        positions = jnp.array([[0.0, 0.0], [10.0, 0.0]], dtype=jnp.float32)
        widths = jnp.array([2.0, 2.0], dtype=jnp.float32)
        heights = jnp.array([2.0, 2.0], dtype=jnp.float32)
        
        total, per_comp = _compute_pairwise_overlaps_vectorized(
            positions, widths, heights, margin=0.0
        )
        
        assert float(total) == 0.0
        assert jnp.all(per_comp == 0.0)
    
    def test_per_component_complete_overlap(self):
        """When components completely overlap, per-component sums to total."""
        # Create 2 components at same position
        positions = jnp.array([[5.0, 5.0], [5.0, 5.0]], dtype=jnp.float32)
        widths = jnp.array([2.0, 2.0], dtype=jnp.float32)
        heights = jnp.array([2.0, 2.0], dtype=jnp.float32)
        
        total, per_comp = _compute_pairwise_overlaps_vectorized(
            positions, widths, heights, margin=0.0
        )
        
        per_comp_sum = float(jnp.sum(per_comp))
        total_val = float(total)
        
        # Both should be non-zero and equal
        assert total_val > 0
        assert abs(per_comp_sum - total_val) < 1e-5
    
    def test_per_component_with_margin(self):
        """Per-component should sum to total even with margin."""
        positions = jnp.array([[0.0, 0.0], [2.0, 0.0]], dtype=jnp.float32)
        widths = jnp.array([2.0, 2.0], dtype=jnp.float32)
        heights = jnp.array([2.0, 2.0], dtype=jnp.float32)
        
        # With 0.5mm margin, components should overlap
        total, per_comp = _compute_pairwise_overlaps_vectorized(
            positions, widths, heights, margin=0.5
        )
        
        per_comp_sum = float(jnp.sum(per_comp))
        total_val = float(total)
        
        assert abs(per_comp_sum - total_val) < 1e-5
    
    def test_per_component_asymmetric_sizes(self):
        """Per-component should work with different component sizes."""
        positions = jnp.array([[0.0, 0.0], [1.0, 0.0]], dtype=jnp.float32)
        widths = jnp.array([2.0, 3.0], dtype=jnp.float32)  # Different widths
        heights = jnp.array([2.0, 1.5], dtype=jnp.float32)  # Different heights
        
        total, per_comp = _compute_pairwise_overlaps_vectorized(
            positions, widths, heights, margin=0.0
        )
        
        per_comp_sum = float(jnp.sum(per_comp))
        total_val = float(total)
        
        assert abs(per_comp_sum - total_val) < 1e-5
    
    def test_per_component_many_components(self):
        """Per-component should work with many components."""
        # Create 10 components in a grid
        n = 10
        positions = jnp.array([
            [float(i % 3) * 1.5, float(i // 3) * 1.5]
            for i in range(n)
        ], dtype=jnp.float32)
        widths = jnp.ones(n, dtype=jnp.float32) * 2.0
        heights = jnp.ones(n, dtype=jnp.float32) * 2.0
        
        total, per_comp = _compute_pairwise_overlaps_vectorized(
            positions, widths, heights, margin=0.0
        )
        
        per_comp_sum = float(jnp.sum(per_comp))
        total_val = float(total)
        
        assert abs(per_comp_sum - total_val) < 1e-4  # Slightly higher tolerance for many components
