"""
Tests for grid coordinate conversion utilities (temper-cqv1).
"""

import pytest

from temper_placer.routing.grid_converter import (
    compute_path_length,
    count_vias_in_path,
    extract_vias,
    grid_to_world,
)
from temper_placer.routing.maze_router import GridCell


class TestGridToWorld:
    """Tests for grid-to-world coordinate conversion."""

    def test_origin_zero(self):
        """Cell center should be offset by half cell size from grid position."""
        cell = GridCell(x=10, y=20, layer=0)
        x, y = grid_to_world(cell, origin=(0, 0), cell_size=0.5)
        
        # Cell (10, 20) with size 0.5: center at (10*0.5 + 0.25, 20*0.5 + 0.25)
        assert x == pytest.approx(5.25)
        assert y == pytest.approx(10.25)

    def test_origin_offset(self):
        """Origin offset should shift all coordinates."""
        cell = GridCell(x=0, y=0, layer=0)
        x, y = grid_to_world(cell, origin=(10.0, 20.0), cell_size=1.0)
        
        # Cell (0, 0) with origin (10, 20): center at (10 + 0.5, 20 + 0.5)
        assert x == pytest.approx(10.5)
        assert y == pytest.approx(20.5)

    def test_different_cell_sizes(self):
        """Larger cell sizes should produce larger coordinates."""
        cell = GridCell(x=5, y=5, layer=0)
        
        # With 0.5mm cells
        x1, y1 = grid_to_world(cell, origin=(0, 0), cell_size=0.5)
        assert x1 == pytest.approx(2.75)  # 5*0.5 + 0.25
        assert y1 == pytest.approx(2.75)
        
        # With 1.0mm cells
        x2, y2 = grid_to_world(cell, origin=(0, 0), cell_size=1.0)
        assert x2 == pytest.approx(5.5)  # 5*1.0 + 0.5
        assert y2 == pytest.approx(5.5)

    def test_layer_does_not_affect_xy(self):
        """Layer parameter should not affect x, y coordinates."""
        cell_l0 = GridCell(x=3, y=4, layer=0)
        cell_l1 = GridCell(x=3, y=4, layer=1)
        
        pos_l0 = grid_to_world(cell_l0, origin=(0, 0), cell_size=1.0)
        pos_l1 = grid_to_world(cell_l1, origin=(0, 0), cell_size=1.0)
        
        assert pos_l0 == pos_l1


class TestExtractVias:
    """Tests for via extraction from paths."""

    def test_no_layer_change(self):
        """Path on single layer should have no vias."""
        cells = [
            GridCell(0, 0, 0),
            GridCell(1, 0, 0),
            GridCell(2, 0, 0),
        ]
        vias = extract_vias(cells)
        assert vias == []

    def test_single_layer_transition(self):
        """Single layer change should produce one via."""
        cells = [
            GridCell(0, 0, 0),  # L0
            GridCell(1, 0, 0),  # L0
            GridCell(1, 0, 1),  # L1 - via here
            GridCell(2, 0, 1),  # L1
        ]
        vias = extract_vias(cells)
        assert vias == [2]  # Via at index 2

    def test_multiple_layer_transitions(self):
        """Multiple layer changes should produce multiple vias."""
        cells = [
            GridCell(0, 0, 0),  # L0
            GridCell(1, 0, 1),  # L1 - via 1
            GridCell(2, 0, 1),  # L1
            GridCell(3, 0, 0),  # L0 - via 2
            GridCell(4, 0, 0),  # L0
        ]
        vias = extract_vias(cells)
        assert vias == [1, 3]

    def test_empty_path(self):
        """Empty path should have no vias."""
        assert extract_vias([]) == []

    def test_single_cell_path(self):
        """Single-cell path should have no vias."""
        assert extract_vias([GridCell(5, 5, 0)]) == []


class TestComputePathLength:
    """Tests for path length calculation."""

    def test_straight_horizontal_path(self):
        """Horizontal path length should be dx * cell_size."""
        cells = [GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(2, 0, 0)]
        length = compute_path_length(cells, cell_size=0.5)
        
        # 2 steps * 0.5mm = 1.0mm
        assert length == pytest.approx(1.0)

    def test_straight_vertical_path(self):
        """Vertical path length should be dy * cell_size."""
        cells = [GridCell(0, 0, 0), GridCell(0, 1, 0), GridCell(0, 2, 0)]
        length = compute_path_length(cells, cell_size=0.5)
        
        assert length == pytest.approx(1.0)

    def test_manhattan_path(self):
        """L-shaped path should use Manhattan distance."""
        cells = [
            GridCell(0, 0, 0),  # Start
            GridCell(1, 0, 0),  # Right 1
            GridCell(1, 1, 0),  # Up 1
        ]
        length = compute_path_length(cells, cell_size=1.0)
        
        # 1 right + 1 up = 2mm
        assert length == pytest.approx(2.0)

    def test_layer_change_no_extra_length(self):
        """Via (same x,y, different layer) should not add physical length."""
        cells = [
            GridCell(0, 0, 0),
            GridCell(1, 0, 0),  # 1 step
            GridCell(1, 0, 1),  # Via: no horizontal/vertical movement
            GridCell(2, 0, 1),  # 1 step
        ]
        length = compute_path_length(cells, cell_size=1.0)
        
        # Only horizontal steps count: 2mm
        assert length == pytest.approx(2.0)

    def test_empty_path(self):
        """Empty path should have zero length."""
        assert compute_path_length([], cell_size=1.0) == 0.0

    def test_single_cell_path(self):
        """Single-cell path should have zero length."""
        assert compute_path_length([GridCell(5, 5, 0)], cell_size=1.0) == 0.0

    def test_different_cell_sizes(self):
        """Path length should scale with cell size."""
        cells = [GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(2, 0, 0)]
        
        # With 0.5mm cells
        length_small = compute_path_length(cells, cell_size=0.5)
        assert length_small == pytest.approx(1.0)
        
        # With 1.0mm cells
        length_large = compute_path_length(cells, cell_size=1.0)
        assert length_large == pytest.approx(2.0)


class TestCountVias:
    """Tests for via counting functionality."""

    def test_count_matches_extraction(self):
        """count_vias_in_path should equal len(extract_vias)."""
        cells = [
            GridCell(0, 0, 0),
            GridCell(1, 0, 1),  # Via 1
            GridCell(2, 0, 1),
            GridCell(3, 0, 0),  # Via 2
        ]
        
        via_indices = extract_vias(cells)
        via_count = count_vias_in_path(cells)
        
        assert via_count == len(via_indices) == 2

    def test_zero_vias(self):
        """Single-layer path should have zero vias."""
        cells = [GridCell(i, 0, 0) for i in range(10)]
        assert count_vias_in_path(cells) == 0

    def test_multiple_vias(self):
        """Complex path with multiple layer transitions."""
        cells = [
            GridCell(0, 0, 0),  # L0
            GridCell(1, 0, 0),  # L0
            GridCell(1, 0, 1),  # L1 - via 1
            GridCell(2, 0, 1),  # L1
            GridCell(2, 0, 0),  # L0 - via 2
            GridCell(3, 0, 0),  # L0
            GridCell(3, 0, 1),  # L1 - via 3
        ]
        assert count_vias_in_path(cells) == 3
