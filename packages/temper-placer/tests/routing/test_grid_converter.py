"""
Tests for grid coordinate conversion utilities (temper-cqv1).
"""

import pytest
import numpy as np

from temper_placer.routing.grid_converter import (
    compute_path_length,
    count_vias_in_path,
    extract_vias,
    grid_to_world,
)
from temper_placer.routing.maze_router import GridCell
from temper_placer.routing.grid import GridConverter, GridCell as NewGridCell


class TestGridConverterNew:
    """Tests for the new GridConverter class (temper-mr01.7)."""

    @pytest.fixture
    def converter(self):
        """Create a GridConverter for testing."""
        return GridConverter(
            grid_size=(100, 100),
            cell_size=0.2,
            origin=(0.0, 0.0),
        )

    def test_world_to_grid_basic(self, converter):
        """Test basic world to grid conversion."""
        gx, gy = converter.world_to_grid(5.0, 3.0)
        assert gx == 25
        assert gy == 15

    def test_world_to_grid_rounding(self, converter):
        """Test that rounding is used for nearest cell."""
        gx, gy = converter.world_to_grid(0.05, 0.05)
        assert gx == 0
        assert gy == 0

        gx, gy = converter.world_to_grid(0.11, 0.11)
        assert gx == 1
        assert gy == 1

    def test_world_to_grid_clamping(self, converter):
        """Test clamping for coordinates outside grid."""
        gx, gy = converter.world_to_grid(-1.0, -1.0)
        assert gx == 0
        assert gy == 0

        gx, gy = converter.world_to_grid(25.0, 25.0)
        assert gx == 99
        assert gy == 99

    def test_world_to_grid_cell(self, converter):
        """Test conversion to GridCell."""
        cell = converter.world_to_grid_cell(5.0, 3.0, layer=2)
        assert cell == NewGridCell(25, 15, 2)

    def test_grid_to_world(self, converter):
        """Test grid to world conversion."""
        wx, wy = converter.grid_to_world(25, 15)
        assert abs(wx - 5.0) < 0.001
        assert abs(wy - 3.0) < 0.001

    def test_clamp_to_grid(self, converter):
        """Test clamping coordinates."""
        gx, gy = converter.clamp_to_grid(-5, -5)
        assert gx == 0
        assert gy == 0

        gx, gy = converter.clamp_to_grid(150, 150)
        assert gx == 99
        assert gy == 99

    def test_is_valid_cell(self, converter):
        """Test validity checking."""
        assert converter.is_valid_cell(50, 50) is True
        assert converter.is_valid_cell(100, 50) is False
        assert converter.is_valid_cell(-1, 50) is False

    def test_distance_cells(self, converter):
        """Test Manhattan distance calculation."""
        dist = converter.distance_cells(0, 0, 10, 5)
        assert dist == 15

    def test_distance_world(self, converter):
        """Test Euclidean distance calculation."""
        dist = converter.distance_world(0, 0, 3, 4)
        assert abs(dist - 5.0) < 0.001

    def test_frozen_immutability(self):
        """Test that GridConverter is frozen (immutable)."""
        converter = GridConverter(
            grid_size=(100, 100),
            cell_size=0.2,
            origin=(0.0, 0.0),
        )
        with pytest.raises(Exception):
            converter.grid_size = (50, 50)


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


class TestDifficultyCalculator:
    """Tests for difficulty calculation functions (temper-mr01.4)."""

    @pytest.fixture
    def occupancy_grid(self):
        """Create a simple occupancy grid for testing."""
        occ = np.zeros((10, 10, 2), dtype=np.int32)
        occ[5, 5, 0] = -1  # Blocked cell at (5, 5, L0)
        occ[5, 6, 0] = -1  # Another blocked cell
        return occ

    @pytest.fixture
    def density_map(self):
        """Create a simple density map for testing."""
        dm = np.zeros((10, 10, 2), dtype=np.float32)
        dm[5, 5, 0] = 1.0  # High density at (5, 5)
        dm[5, 6, 0] = 0.5  # Medium density
        return dm

    def test_compute_proximity_difficulty_no_blocked(self, occupancy_grid):
        """Cell with no blocked neighbors has zero difficulty."""
        from temper_placer.routing.difficulty import compute_proximity_difficulty
        from temper_placer.routing.maze_router import GridCell

        cell = GridCell(0, 0, 0)
        diff = compute_proximity_difficulty(cell, occupancy_grid, (10, 10))
        assert diff == 0.0

    def test_compute_proximity_difficulty_adjacent_blocked(self, occupancy_grid):
        """Cell adjacent to blocked cell has positive difficulty."""
        from temper_placer.routing.difficulty import compute_proximity_difficulty
        from temper_placer.routing.maze_router import GridCell

        # Cell at (4, 5) is adjacent to blocked cell at (5, 5)
        cell = GridCell(4, 5, 0)
        diff = compute_proximity_difficulty(cell, occupancy_grid, (10, 10))
        assert diff == 0.5

    def test_compute_proximity_difficulty_multiple_blocked(self, occupancy_grid):
        """Cell adjacent to multiple blocked cells sums difficulties."""
        from temper_placer.routing.difficulty import compute_proximity_difficulty
        from temper_placer.routing.maze_router import GridCell

        # Cell at (4, 6) is adjacent to blocked cell at (5, 6) only
        cell = GridCell(4, 6, 0)
        diff = compute_proximity_difficulty(cell, occupancy_grid, (10, 10))
        assert diff == 0.5  # Only one blocked neighbor

        # Create a cell that is adjacent to two blocked cells
        # Block cells at (5, 5) and (5, 3), test cell at (5, 4)
        occ = np.zeros((10, 10, 2), dtype=np.int32)
        occ[5, 5, 0] = -1
        occ[5, 3, 0] = -1
        cell = GridCell(5, 4, 0)  # Adjacent to both blocked cells (5, 5) above, (5, 3) below
        diff = compute_proximity_difficulty(cell, occ, (10, 10))
        assert diff == 1.0  # 0.5 + 0.5

    def test_compute_proximity_different_layers(self, occupancy_grid):
        """Blocked cells on other layers don't affect difficulty."""
        from temper_placer.routing.difficulty import compute_proximity_difficulty
        from temper_placer.routing.maze_router import GridCell

        # Cell at (4, 5) on layer 1, blocked cells are on layer 0
        cell = GridCell(4, 5, 1)
        diff = compute_proximity_difficulty(cell, occupancy_grid, (10, 10))
        assert diff == 0.0  # No blocked neighbors on layer 1

    def test_compute_density_difficulty_none_map(self):
        """None density map returns zero difficulty."""
        from temper_placer.routing.difficulty import compute_density_difficulty
        from temper_placer.routing.maze_router import GridCell

        cell = GridCell(5, 5, 0)
        diff = compute_density_difficulty(cell, None)
        assert diff == 0.0

    def test_compute_density_difficulty_high_density(self, density_map):
        """High density cell has difficulty of 1.0."""
        from temper_placer.routing.difficulty import compute_density_difficulty
        from temper_placer.routing.maze_router import GridCell

        cell = GridCell(5, 5, 0)
        diff = compute_density_difficulty(cell, density_map)
        assert diff == 1.0  # density * weight (1.0 * 1.0)

    def test_compute_density_difficulty_weight(self, density_map):
        """Density difficulty can be scaled with weight."""
        from temper_placer.routing.difficulty import compute_density_difficulty
        from temper_placer.routing.maze_router import GridCell

        cell = GridCell(5, 5, 0)
        diff = compute_density_difficulty(cell, density_map, weight=2.0)
        assert diff == 2.0  # density * weight (1.0 * 2.0)

    def test_get_cell_difficulty_combined(self, occupancy_grid, density_map):
        """get_cell_difficulty combines proximity and density."""
        from temper_placer.routing.difficulty import get_cell_difficulty
        from temper_placer.routing.maze_router import GridCell

        # Cell at (4, 5): adjacent to blocked (0.5) + density at (4, 5) is 0
        cell = GridCell(4, 5, 0)
        diff = get_cell_difficulty(cell, density_map, occupancy_grid, (10, 10))
        assert diff == 0.5

        # Cell at (5, 6): adjacent to blocked (0.5) + density 0.5 = 1.0
        cell = GridCell(5, 6, 0)
        diff = get_cell_difficulty(cell, density_map, occupancy_grid, (10, 10))
        assert diff == 1.0

    def test_compute_density_map_empty_positions(self):
        """Empty positions produce zero density map."""
        from temper_placer.routing.difficulty import compute_density_map

        dm = compute_density_map(
            positions=None,
            grid_size=(10, 10),
            cell_size=1.0,
            origin=(0.0, 0.0),
            radius_mm=10.0,
            num_layers=2,
        )
        assert dm.shape == (10, 10, 2)
        assert np.all(dm == 0.0)

    def test_compute_density_map_with_components(self):
        """Density map reflects component positions."""
        from temper_placer.routing.difficulty import compute_density_map

        positions = np.array([[5.0, 5.0]])
        dm = compute_density_map(
            positions=positions,
            grid_size=(10, 10),
            cell_size=1.0,
            origin=(0.0, 0.0),
            radius_mm=2.0,
            num_layers=1,
        )
        # Cell (5, 5) should have high density
        assert dm[5, 5, 0] > 0.5
        # Cell (0, 0) should have zero density
        assert dm[0, 0, 0] == 0.0

    def test_compute_density_map_correct_shape(self):
        """Density map has correct 3D shape."""
        from temper_placer.routing.difficulty import compute_density_map

        positions = np.array([[5.0, 5.0]])
        dm = compute_density_map(
            positions=positions,
            grid_size=(20, 15),
            cell_size=0.5,
            origin=(0.0, 0.0),
            radius_mm=5.0,
            num_layers=4,
        )
        assert dm.shape == (20, 15, 4)


class TestNeighborGeneration:
    """Tests for neighbor generation functions (temper-mr01.8)."""

    @pytest.fixture
    def occupancy_grid(self):
        """Create a simple occupancy grid for testing."""
        occ = np.zeros((10, 10, 2), dtype=np.int32)
        occ[5, 5, 0] = -1  # Blocked cell at (5, 5, L0)
        occ[5, 5, 1] = -1  # Blocked cell at (5, 5, L1)
        occ[7, 7, 0] = 2   # Occupied cell at (7, 7, L0)
        return occ

    def test_get_cardinal_neighbors_basic(self, occupancy_grid):
        """Basic cardinal neighbor generation."""
        from temper_placer.routing.neighbors import get_cardinal_neighbors
        from temper_placer.routing.maze_router import GridCell

        cell = GridCell(5, 4, 0)
        neighbors = get_cardinal_neighbors(cell, occupancy_grid, (10, 10), soft_blocking=True)
        
        # Should have 3 neighbors (blocked cell at 5,5 is not included)
        assert len(neighbors) == 3
        neighbor_coords = [(n.x, n.y) for n in neighbors]
        assert (5, 3) in neighbor_coords  # Down
        assert (6, 4) in neighbor_coords  # Right
        assert (4, 4) in neighbor_coords  # Left
        assert (5, 5) not in neighbor_coords  # Up (blocked)

    def test_get_cardinal_neighbors_strict_mode(self, occupancy_grid):
        """Strict mode blocks occupied cells."""
        from temper_placer.routing.neighbors import get_cardinal_neighbors
        from temper_placer.routing.maze_router import GridCell

        cell = GridCell(6, 7, 0)  # Next to occupied cell at (7, 7)
        
        # Soft blocking: occupied cell is allowed
        neighbors_soft = get_cardinal_neighbors(cell, occupancy_grid, (10, 10), soft_blocking=True)
        assert (7, 7) in [(n.x, n.y) for n in neighbors_soft]
        
        # Strict blocking: occupied cell is blocked
        neighbors_strict = get_cardinal_neighbors(cell, occupancy_grid, (10, 10), soft_blocking=False)
        assert (7, 7) not in [(n.x, n.y) for n in neighbors_strict]

    def test_get_cardinal_neighbors_plane_layer(self, occupancy_grid):
        """Plane layers have no cardinal neighbors."""
        from temper_placer.routing.neighbors import get_cardinal_neighbors
        from temper_placer.routing.maze_router import GridCell

        cell = GridCell(5, 5, 0)
        neighbors = get_cardinal_neighbors(cell, occupancy_grid, (10, 10), is_plane_layer=True)
        
        # No horizontal movement on plane layer
        assert len(neighbors) == 0

    def test_get_cardinal_neighbors_boundary(self, occupancy_grid):
        """Boundary cells have fewer neighbors."""
        from temper_placer.routing.neighbors import get_cardinal_neighbors
        from temper_placer.routing.maze_router import GridCell

        cell = GridCell(0, 0, 0)  # Corner
        neighbors = get_cardinal_neighbors(cell, occupancy_grid, (10, 10), soft_blocking=True)
        
        # Only 2 neighbors from corner (right and up)
        assert len(neighbors) == 2
        assert (1, 0) in [(n.x, n.y) for n in neighbors]
        assert (0, 1) in [(n.x, n.y) for n in neighbors]

    def test_get_layer_neighbors_basic(self, occupancy_grid):
        """Basic layer neighbor generation."""
        from temper_placer.routing.neighbors import get_layer_neighbors
        from temper_placer.routing.maze_router import GridCell

        cell = GridCell(5, 4, 0)
        neighbors = get_layer_neighbors(cell, occupancy_grid, (10, 10), soft_blocking=True, num_layers=2)
        
        # Should have 1 layer neighbor (same x,y, layer 1)
        assert len(neighbors) == 1
        assert neighbors[0].x == 5
        assert neighbors[0].y == 4
        assert neighbors[0].layer == 1

    def test_get_layer_neighbors_blocked(self, occupancy_grid):
        """Blocked cells on other layers are not included."""
        from temper_placer.routing.neighbors import get_layer_neighbors
        from temper_placer.routing.maze_router import GridCell

        cell = GridCell(5, 5, 0)  # Above blocked cell at (5, 5)
        neighbors = get_layer_neighbors(cell, occupancy_grid, (10, 10), soft_blocking=True, num_layers=2)
        
        # Cell (5, 5) is blocked on both layers, so no layer neighbors
        assert len(neighbors) == 0

    def test_get_all_neighbors_combined(self, occupancy_grid):
        """get_all_neighbors combines cardinal and layer neighbors."""
        from temper_placer.routing.neighbors import get_all_neighbors
        from temper_placer.routing.maze_router import GridCell

        cell = GridCell(5, 4, 0)
        neighbors = get_all_neighbors(
            cell=cell,
            occupancy=occupancy_grid,
            grid_size=(10, 10),
            soft_blocking=True,
            is_plane_layer=False,
            allow_layer_change=True,
            num_layers=2,
        )
        
        # 3 cardinal + 1 layer = 4 total
        assert len(neighbors) == 4

    def test_get_all_neighbors_no_layer_change(self, occupancy_grid):
        """get_all_neighbors without layer changes."""
        from temper_placer.routing.neighbors import get_all_neighbors
        from temper_placer.routing.maze_router import GridCell

        cell = GridCell(5, 4, 0)
        neighbors = get_all_neighbors(
            cell=cell,
            occupancy=occupancy_grid,
            grid_size=(10, 10),
            soft_blocking=True,
            is_plane_layer=False,
            allow_layer_change=False,
            num_layers=2,
        )
        
        # Only 3 cardinal neighbors
        assert len(neighbors) == 3

    def test_count_neighbors(self, occupancy_grid):
        """count_neighbors returns correct count."""
        from temper_placer.routing.neighbors import count_neighbors
        from temper_placer.routing.maze_router import GridCell

        cell = GridCell(5, 4, 0)
        count = count_neighbors(
            cell=cell,
            occupancy=occupancy_grid,
            grid_size=(10, 10),
            soft_blocking=True,
            allow_layer_change=True,
            num_layers=2,
        )
        
        assert count == 4

    def test_count_neighbors_isolated(self, occupancy_grid):
        """Isolated cell has zero neighbors."""
        from temper_placer.routing.neighbors import count_neighbors
        from temper_placer.routing.maze_router import GridCell

        # Create a grid with all cells blocked
        occ = np.full((5, 5, 2), -1, dtype=np.int32)
        occ[2, 2, 0] = 0  # Single free cell
        
        cell = GridCell(2, 2, 0)
        count = count_neighbors(
            cell=cell,
            occupancy=occ,
            grid_size=(5, 5),
            soft_blocking=True,
            allow_layer_change=True,
            num_layers=2,
        )
        
        # All neighbors blocked
        assert count == 0
