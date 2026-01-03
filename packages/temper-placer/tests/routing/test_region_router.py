"""
TDD tests for quadtree region-based routing.

Phase 1: Quadtree Construction
Phase 2: Ghost Cell Exchange
Phase 3: Region Routing
Phase 4: Path Stitching
Phase 5: Integration Tests
"""

import pytest
import numpy as np
from dataclasses import dataclass


# ============================================================================
# Phase 1: Quadtree Construction Tests
# ============================================================================

class TestQuadTreeConstruction:
    """Tests for building the quadtree spatial decomposition."""
    
    def test_single_leaf_for_small_grid(self):
        """Grid smaller than min_region_size -> single leaf."""
        from temper_placer.routing.region_router import RoutingQuadTree
        
        tree = RoutingQuadTree(grid_size=(15, 15), min_region_size=20)
        
        # Should be a single leaf, no children
        assert tree.root.is_leaf
        assert tree.root.bounds == (0, 0, 15, 15)
    
    def test_four_children_for_large_grid(self):
        """100x100 with min_size=50 -> 4 leaves."""
        from temper_placer.routing.region_router import RoutingQuadTree
        
        tree = RoutingQuadTree(grid_size=(100, 100), min_region_size=50)
        
        assert not tree.root.is_leaf
        assert len(tree.root.children) == 4
        # Each child should be a leaf
        for child in tree.root.children:
            assert child.is_leaf
    
    def test_recursive_subdivision(self):
        """100x100 with min_size=25 -> 16 leaves."""
        from temper_placer.routing.region_router import RoutingQuadTree
        
        tree = RoutingQuadTree(grid_size=(100, 100), min_region_size=25)
        
        leaves = list(tree.leaves())
        assert len(leaves) == 16
    
    def test_bounds_cover_entire_grid(self):
        """Union of all leaf bounds == original grid."""
        from temper_placer.routing.region_router import RoutingQuadTree
        
        tree = RoutingQuadTree(grid_size=(100, 100), min_region_size=25)
        
        # Check that all grid cells are covered by exactly one leaf
        covered = set()
        for leaf in tree.leaves():
            x0, y0, x1, y1 = leaf.bounds
            for x in range(x0, x1):
                for y in range(y0, y1):
                    assert (x, y) not in covered, f"Cell ({x},{y}) covered twice"
                    covered.add((x, y))
        
        # All cells should be covered
        for x in range(100):
            for y in range(100):
                assert (x, y) in covered, f"Cell ({x},{y}) not covered"
    
    def test_no_gaps_between_siblings(self):
        """Adjacent leaves share exact boundary line."""
        from temper_placer.routing.region_router import RoutingQuadTree
        
        tree = RoutingQuadTree(grid_size=(100, 100), min_region_size=50)
        leaves = list(tree.leaves())
        
        # Sort by position to find adjacent pairs
        # For a 2x2 grid of leaves, check that boundaries align
        assert len(leaves) == 4
        
        # Get all x and y boundaries
        x_boundaries = set()
        y_boundaries = set()
        for leaf in leaves:
            x0, y0, x1, y1 = leaf.bounds
            x_boundaries.add(x0)
            x_boundaries.add(x1)
            y_boundaries.add(y0)
            y_boundaries.add(y1)
        
        # Should have exactly 3 x-boundaries: 0, 50, 100
        assert x_boundaries == {0, 50, 100}
        assert y_boundaries == {0, 50, 100}

    def test_leaf_count_for_non_power_of_two(self):
        """Non-power-of-2 grids still subdivide correctly."""
        from temper_placer.routing.region_router import RoutingQuadTree
        
        tree = RoutingQuadTree(grid_size=(75, 60), min_region_size=20)
        
        leaves = list(tree.leaves())
        # Should have multiple leaves covering the grid
        assert len(leaves) >= 4
        
        # All leaves should have valid bounds
        for leaf in leaves:
            x0, y0, x1, y1 = leaf.bounds
            assert x0 >= 0 and y0 >= 0
            assert x1 <= 75 and y1 <= 60
            assert x1 > x0 and y1 > y0


# ============================================================================
# Phase 2: Ghost Cell Exchange Tests
# ============================================================================

class TestHaloExchange:
    """Tests for copying ghost cells between adjacent regions."""
    
    def test_halo_copied_from_neighbor(self):
        """East neighbor's west edge -> my east_halo."""
        from temper_placer.routing.region_router import RoutingQuadTree
        
        tree = RoutingQuadTree(grid_size=(100, 100), min_region_size=50, halo=3)
        
        # Create test occupancy data
        occupancy = np.zeros((100, 100), dtype=np.int32)
        occupancy[48:52, 25] = 1  # Mark some cells at boundary
        
        tree.set_occupancy(occupancy)
        tree.exchange_halos()
        
        # West leaf should have east_halo containing data from east neighbor
        leaves = sorted(tree.leaves(), key=lambda l: l.bounds[0])  # Sort by x
        west_leaf = leaves[0]
        
        assert west_leaf.east_halo is not None
        assert west_leaf.east_halo.shape[0] == 3  # halo width
    
    def test_boundary_halo_is_none(self):
        """Edge leaves have None for off-grid halos."""
        from temper_placer.routing.region_router import RoutingQuadTree
        
        tree = RoutingQuadTree(grid_size=(100, 100), min_region_size=50, halo=3)
        
        leaves = list(tree.leaves())
        
        # Find corner leaf (should have 2 None halos)
        for leaf in leaves:
            x0, y0, x1, y1 = leaf.bounds
            if x0 == 0:
                assert leaf.west_halo is None
            if y0 == 0:
                assert leaf.south_halo is None
            if x1 == 100:
                assert leaf.east_halo is None
            if y1 == 100:
                assert leaf.north_halo is None
    
    def test_halo_size_matches_parameter(self):
        """halo=3 -> 3-cell wide strip copied."""
        from temper_placer.routing.region_router import RoutingQuadTree
        
        tree = RoutingQuadTree(grid_size=(100, 100), min_region_size=50, halo=5)
        occupancy = np.ones((100, 100), dtype=np.int32)
        tree.set_occupancy(occupancy)
        tree.exchange_halos()
        
        for leaf in tree.leaves():
            if leaf.east_halo is not None:
                assert leaf.east_halo.shape[0] == 5
            if leaf.north_halo is not None:
                assert leaf.north_halo.shape[1] == 5


# ============================================================================
# Phase 3: Region Routing Invariants
# ============================================================================

class TestRegionRouting:
    """Tests for routing within individual regions."""
    
    def test_path_within_region_bounds_plus_halo(self):
        """All cells in path are inside region + halo."""
        from temper_placer.routing.region_router import RoutingQuadTree, route_region
        from temper_placer.routing.maze_router import MazeRouter
        
        tree = RoutingQuadTree(grid_size=(100, 100), min_region_size=50, halo=3)
        
        # Route a simple net within one region
        leaf = list(tree.leaves())[0]
        x0, y0, x1, y1 = leaf.bounds
        
        # Create a simple net fully contained in this region
        start = (x0 + 5, y0 + 5)
        end = (x1 - 5, y1 - 5)
        
        path = route_region(leaf, start, end, halo=3)
        
        assert path is not None
        for cell in path:
            # Cell should be within bounds + halo
            assert cell.x >= x0 - 3 and cell.x < x1 + 3
            assert cell.y >= y0 - 3 and cell.y < y1 + 3
    
    def test_single_region_no_conflicts(self):
        """Routing single net in empty region produces no conflicts."""
        from temper_placer.routing.region_router import RoutingQuadTree, route_region
        
        tree = RoutingQuadTree(grid_size=(50, 50), min_region_size=50, halo=3)
        
        leaf = list(tree.leaves())[0]
        path = route_region(leaf, (5, 5), (45, 45), halo=3)
        
        assert path is not None
        # Check for self-intersection
        cells = [(c.x, c.y, c.layer) for c in path]
        assert len(cells) == len(set(cells)), "Path has duplicate cells"


# ============================================================================
# Phase 4: Path Stitching Tests
# ============================================================================

class TestPathStitching:
    """Tests for merging paths from adjacent regions."""
    
    def test_paths_connect_at_boundary(self):
        """Net spanning 2 regions has continuous path."""
        from temper_placer.routing.region_router import RoutingQuadTree, stitch_paths
        from temper_placer.routing.maze_router import GridCell
        
        # Create two partial paths that should connect
        path1 = [GridCell(x, 25, 0) for x in range(48, 51)]  # Ends at boundary
        path2 = [GridCell(x, 25, 0) for x in range(50, 55)]  # Starts at boundary
        
        merged = stitch_paths({"net1_region0": path1, "net1_region1": path2}, net_name="net1")
        
        # Should be continuous
        assert len(merged) > 0
        for i in range(1, len(merged)):
            dx = abs(merged[i].x - merged[i-1].x)
            dy = abs(merged[i].y - merged[i-1].y)
            assert dx + dy <= 1, f"Gap between cells {i-1} and {i}"
    
    def test_no_duplicate_cells_after_merge(self):
        """Merged path has unique cells only."""
        from temper_placer.routing.region_router import stitch_paths
        from temper_placer.routing.maze_router import GridCell
        
        # Overlapping paths at boundary
        path1 = [GridCell(x, 25, 0) for x in range(45, 52)]
        path2 = [GridCell(x, 25, 0) for x in range(50, 60)]
        
        merged = stitch_paths({"net1_r0": path1, "net1_r1": path2}, net_name="net1")
        
        cells = [(c.x, c.y, c.layer) for c in merged]
        assert len(cells) == len(set(cells)), "Merged path has duplicates"


# ============================================================================
# Phase 5: Integration Tests
# ============================================================================

class TestRegionVsGlobal:
    """Compare region-based routing to global routing."""
    
    def test_same_nets_routed(self):
        """Region router routes same nets as global."""
        from temper_placer.routing.region_router import RegionRouter
        from temper_placer.routing.maze_router import MazeRouter
        
        # Create simple test netlist
        grid_size = (100, 100)
        
        # Global routing
        global_router = MazeRouter(grid_size=grid_size, num_layers=1)
        global_path = global_router.find_path((10, 10), (90, 90))
        
        # Region routing
        region_router = RegionRouter(grid_size=grid_size, min_region_size=50)
        region_path = region_router.route_net((10, 10), (90, 90))
        
        # Both should succeed
        assert global_path is not None
        assert region_path is not None
    
    def test_path_lengths_reasonable(self):
        """Region routing doesn't produce much longer paths."""
        from temper_placer.routing.region_router import RegionRouter
        from temper_placer.routing.maze_router import MazeRouter
        
        grid_size = (100, 100)
        
        global_router = MazeRouter(grid_size=grid_size, num_layers=1)
        global_path = global_router.find_path((10, 10), (90, 90))
        
        region_router = RegionRouter(grid_size=grid_size, min_region_size=50)
        region_path = region_router.route_net((10, 10), (90, 90))
        
        # Region path should be within 20% of global path length
        assert len(region_path) <= len(global_path) * 1.2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
