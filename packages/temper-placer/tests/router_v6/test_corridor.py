"""Tests for coarse-to-fine corridor extraction."""

import numpy as np

from temper_placer.router_v6.corridor import extract_corridor_mask


def test_corridor_mask_single_cell():
    """Single-cell coarse path: corridor is factor^2 + buffer."""
    path = [(2, 3)]
    mask = extract_corridor_mask(
        coarse_path=path,
        coarse_factor=4,
        buffer_cells=2,
        fine_rows=100,
        fine_cols=200,
    )
    assert mask.shape == (100, 200)
    assert mask.dtype == np.bool_
    # Check that the expanded region is correct
    # Coarse cell (2,3) maps to fine (8..11, 12..15) + buffer 2
    assert mask[12, 8]   # inside
    assert mask[15, 11]  # inside
    assert mask[12, 7]   # buffer edge
    assert mask[10, 8]   # buffer top
    assert mask[17, 13]  # buffer bottom-right


def test_corridor_mask_multi_cell():
    """Multi-cell coarse path: corridor covers all expanded cells."""
    path = [(0, 0), (0, 1), (1, 1)]
    mask = extract_corridor_mask(
        coarse_path=path,
        coarse_factor=4,
        buffer_cells=0,
        fine_rows=20,
        fine_cols=20,
    )
    # First cell (0,0): fine (0..3, 0..3)
    assert mask[0, 0]
    assert mask[3, 3]
    # Second cell (0,1): fine (0..3, 4..7)
    assert mask[5, 2]
    # Third cell (1,1): fine (4..7, 4..7)
    assert mask[6, 6]
    # Outside all cells
    assert not mask[10, 10]


def test_corridor_mask_edge_clamping():
    """Path near grid edge: buffer clamped to bounds."""
    path = [(0, 0)]
    mask = extract_corridor_mask(
        coarse_path=path,
        coarse_factor=4,
        buffer_cells=100,
        fine_rows=10,
        fine_cols=10,
    )
    # With huge buffer, the entire grid should be covered
    assert np.all(mask)


def test_corridor_mask_empty_path():
    """Empty coarse path: empty corridor mask."""
    mask = extract_corridor_mask(
        coarse_path=[],
        coarse_factor=4,
        buffer_cells=2,
        fine_rows=100,
        fine_cols=200,
    )
    assert not np.any(mask)


def test_corridor_mask_buffer():
    """Buffer expands correctly around coarse cell."""
    path = [(0, 0)]
    mask = extract_corridor_mask(
        coarse_path=path,
        coarse_factor=4,
        buffer_cells=3,
        fine_rows=100,
        fine_cols=100,
    )
    # Coarse (0,0) -> fine (0..3, 0..3) + buffer 3
    # Top-left should be at (-3, -3) but clamped to 0
    assert mask[0, 0]
    # Right edge: 3 + 3 = 6, bottom edge: 3 + 3 = 6
    assert mask[6, 6]
    # Outside
    assert not mask[7, 6]
    assert not mask[6, 7]
