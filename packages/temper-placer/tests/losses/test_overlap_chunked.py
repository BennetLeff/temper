
import jax
import jax.numpy as jnp
import pytest

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Netlist
from temper_placer.losses.base import LossContext
from temper_placer.losses.overlap import (
    OverlapLoss,
    _compute_pairwise_overlaps_chunked,
    _compute_pairwise_overlaps_vectorized,
)


def create_random_setup(n_components, seed=42):
    key = jax.random.PRNGKey(seed)
    pos_key, bounds_key = jax.random.split(key)

    positions = jax.random.uniform(pos_key, (n_components, 2), minval=0.0, maxval=100.0)
    # 5x5mm components
    bounds_vals = jax.random.uniform(bounds_key, (n_components, 2), minval=2.0, maxval=10.0)

    components = [
        Component(ref=f"C{i}", footprint="test", bounds=(float(bounds_vals[i, 0]), float(bounds_vals[i, 1])))
        for i in range(n_components)
    ]
    netlist = Netlist(components=components, nets=[])
    board = Board(100.0, 100.0)
    context = LossContext.from_netlist_and_board(netlist, board)

    # rotations
    rotations = jnp.eye(4)[jnp.zeros(n_components, dtype=jnp.int32)]

    return positions, rotations, context

def test_chunked_overlap_matches_vectorized():
    """Verify chunked matches vectorized on a medium-sized board."""
    n = 60 # Above threshold (50)
    positions, rotations, context = create_random_setup(n)

    widths = context.bounds[:, 0]
    heights = context.bounds[:, 1]
    margin = 0.0

    total_v, per_comp_v = _compute_pairwise_overlaps_vectorized(positions, widths, heights, margin)
    total_c, per_comp_c = _compute_pairwise_overlaps_chunked(positions, widths, heights, margin)

    assert jnp.allclose(total_v, total_c, rtol=1e-4)
    assert jnp.allclose(per_comp_v, per_comp_c, rtol=1e-4)

def test_overlap_threshold_boundary():
    """Verify identical results at the threshold (49 vs 50)."""
    margin = 0.0

    # Test N=49
    p49, r49, c49 = create_random_setup(49)
    w49, h49 = c49.bounds[:, 0], c49.bounds[:, 1]
    total49_v, _ = _compute_pairwise_overlaps_vectorized(p49, w49, h49, margin)
    total49_c, _ = _compute_pairwise_overlaps_chunked(p49, w49, h49, margin)
    assert jnp.allclose(total49_v, total49_c, rtol=1e-4)

    # Test N=50
    p50, r50, c50 = create_random_setup(50)
    w50, h50 = c50.bounds[:, 0], c50.bounds[:, 1]
    total50_v, _ = _compute_pairwise_overlaps_vectorized(p50, w50, h50, margin)
    total50_c, _ = _compute_pairwise_overlaps_chunked(p50, w50, h50, margin)
    assert jnp.allclose(total50_v, total50_c, rtol=1e-4)

@pytest.mark.slow
def test_overlap_memory_scaling():
    """
    Very basic check that large N doesn't crash and completes.
    True memory scaling tests require external profilers, but we can verify completion.
    """
    for n in [10, 50, 100, 200]:
        positions, rotations, context = create_random_setup(n)
        loss_fn = OverlapLoss()
        # This should use chunked for n >= 50
        result = loss_fn(positions, rotations, context)
        assert jnp.isfinite(result.value)

def test_per_component_breakdown_chunked():
    """Verify per_component_overlap is correctly computed in chunked mode."""
    n = 60
    positions, rotations, context = create_random_setup(n)

    widths = context.bounds[:, 0]
    heights = context.bounds[:, 1]

    # Run chunked
    _, per_comp_c = _compute_pairwise_overlaps_chunked(positions, widths, heights, 0.0)

    # Verify sum of per_component is 2x total (since each pair i,j added to both i and j)
    total_c, _ = _compute_pairwise_overlaps_chunked(positions, widths, heights, 0.0)
    assert jnp.allclose(jnp.sum(per_comp_c), 2.0 * total_c, rtol=1e-4)
