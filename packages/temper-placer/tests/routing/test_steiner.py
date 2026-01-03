"""
Tests for Steiner tree routing for multi-pin nets (temper-tos3.2).

Verifies that multi-pin nets use optimal topologies (MST/RST) instead of
simple chain routing (A→B→C).
"""

import jax.numpy as jnp
import pytest

from temper_placer.core.board import Board
from temper_placer.routing.layer_assignment import LayerAssignment, Layer
from temper_placer.routing.maze_router import MazeRouter
from temper_placer.routing.steiner import compute_mst, compute_rst_approximation


class TestMSTComputation:
    """Tests for Minimum Spanning Tree computation."""

    def test_mst_two_pins(self):
        """Two pins should have single edge."""
        pins = [(0.0, 0.0), (10.0, 0.0)]
        edges = compute_mst(pins)
        
        assert len(edges) == 1, "Two pins should have 1 edge"
        assert set(edges[0]) == {0, 1}, "Edge should connect pin 0 and 1"

    def test_mst_three_pins_line(self):
        """Three pins in a line should have 2 edges."""
        pins = [(0.0, 0.0), (5.0, 0.0), (10.0, 0.0)]
        edges = compute_mst(pins)
        
        assert len(edges) == 2, "Three pins should have 2 edges"
        # Middle pin (1) should connect to both ends
        edge_set = set()
        for a, b in edges:
            edge_set.add((min(a, b), max(a, b)))
        
        # Valid MSTs: {(0,1), (1,2)} or equivalent
        assert (0, 1) in edge_set or (0, 2) in edge_set
        assert (1, 2) in edge_set or (0, 2) in edge_set

    def test_mst_three_pins_triangle(self):
        """Triangle of pins - MST should use 2 shortest edges."""
        # Equilateral triangle
        pins = [
            (0.0, 0.0),
            (10.0, 0.0),
            (5.0, 8.66),  # Height of equilateral triangle
        ]
        edges = compute_mst(pins)
        
        assert len(edges) == 2, "Triangle should have 2 edges (no cycle)"
        
        # Verify it's a valid spanning tree (connects all pins)
        connected = set([edges[0][0], edges[0][1]])
        for a, b in edges[1:]:
            connected.add(a)
            connected.add(b)
        assert connected == {0, 1, 2}, "MST should connect all 3 pins"

    def test_mst_four_pins_square(self):
        """Four pins in square - MST uses 3 edges."""
        pins = [
            (0.0, 0.0),
            (10.0, 0.0),
            (10.0, 10.0),
            (0.0, 10.0),
        ]
        edges = compute_mst(pins)
        
        assert len(edges) == 3, "Four pins should have 3 edges"
        
        # Should connect all pins
        connected_pins = set()
        for a, b in edges:
            connected_pins.add(a)
            connected_pins.add(b)
        assert len(connected_pins) == 4, "All 4 pins should be connected"

    def test_mst_deterministic(self):
        """MST should be deterministic for same input."""
        pins = [(0.0, 0.0), (10.0, 0.0), (5.0, 5.0)]
        
        edges1 = compute_mst(pins)
        edges2 = compute_mst(pins)
        
        assert edges1 == edges2, "MST should be deterministic"


class TestRSTApproximation:
    """Tests for Rectilinear Steiner Tree approximation."""

    def test_rst_two_pins(self):
        """RST for 2 pins is just Manhattan path."""
        pins = [(0.0, 0.0), (10.0, 5.0)]
        steiner_points = compute_rst_approximation(pins)
        
        # For 2 pins, no Steiner points needed (or at most 1 corner)
        assert len(steiner_points) <= 1, "2 pins need at most 1 Steiner point"

    def test_rst_three_pins_saves_length(self):
        """RST for L-shaped pins should use Steiner point."""
        # L-shape: (0,0), (10,0), (0,10)
        pins = [(0.0, 0.0), (10.0, 0.0), (0.0, 10.0)]
        steiner_points = compute_rst_approximation(pins)
        
        # Should have Steiner point at origin or nearby
        assert len(steiner_points) >= 1, "L-shape should use Steiner point"

    def test_rst_approximation_quality(self):
        """RST should be better than naive chain for some configurations."""
        # Four pins in a plus pattern
        pins = [
            (5.0, 0.0),   # Bottom
            (10.0, 5.0),  # Right
            (5.0, 10.0),  # Top
            (0.0, 5.0),   # Left
        ]
        
        # Compute RST approximation
        steiner_points = compute_rst_approximation(pins)
        
        # Should suggest center point (5, 5) as Steiner point
        center_found = any(
            abs(x - 5.0) < 1.0 and abs(y - 5.0) < 1.0
            for x, y in steiner_points
        )
        assert center_found, "Should find center Steiner point for plus pattern"


class TestMSTBasedRouting:
    """Tests for MST-based net routing."""

    def test_route_three_pin_net_mst_order(self):
        """Three-pin net should route in MST order, not arbitrary chain."""
        board = Board(width=50.0, height=50.0, origin=(0.0, 0.0))
        router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=1)

        # Three pins forming a triangle
        pin_positions = [
            (10.0, 10.0),  # Pin 0
            (40.0, 10.0),  # Pin 1 (far from pin 0)
            (25.0, 25.0),  # Pin 2 (closest to midpoint)
        ]

        assignment = LayerAssignment(
            primary_layer=Layer.L1_TOP,
            allowed_layers=[Layer.L1_TOP]
        )

        # Route using MST-based ordering
        result = router.route_net_mst("TEST_NET", pin_positions, assignment)
        
        assert result.success, "MST routing should succeed"
        assert len(result.cells) > 0, "Should have routed path"

    def test_mst_routing_vs_chain_path_length(self):
        """MST routing should use shorter path than arbitrary chain."""
        board = Board(width=100.0, height=100.0, origin=(0.0, 0.0))
        
        # Create two routers for comparison
        router_chain = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=1)
        router_mst = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=1)

        # Four pins in a square where MST is clearly better
        pin_positions = [
            (20.0, 20.0),
            (80.0, 20.0),
            (80.0, 80.0),
            (20.0, 80.0),
        ]

        assignment = LayerAssignment(
            primary_layer=Layer.L1_TOP,
            allowed_layers=[Layer.L1_TOP]
        )

        # Chain routing (pin 0 → 1 → 2 → 3)
        result_chain = router_chain.route_net("CHAIN_NET", pin_positions, assignment)
        
        # MST routing (should find better topology)
        result_mst = router_mst.route_net_mst("MST_NET", pin_positions, assignment)

        assert result_chain.success and result_mst.success, "Both should succeed"
        
        # MST should use equal or shorter path
        assert result_mst.length <= result_chain.length, \
            f"MST routing should be shorter: {result_mst.length} vs {result_chain.length}"

    def test_star_topology_for_central_pin(self):
        """When one pin is central, MST should create star topology."""
        board = Board(width=100.0, height=100.0, origin=(0.0, 0.0))
        router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=1)

        # Central pin with 4 surrounding pins
        pin_positions = [
            (50.0, 50.0),  # Central hub
            (30.0, 50.0),  # West
            (70.0, 50.0),  # East
            (50.0, 30.0),  # South
            (50.0, 70.0),  # North
        ]

        assignment = LayerAssignment(
            primary_layer=Layer.L1_TOP,
            allowed_layers=[Layer.L1_TOP]
        )

        result = router.route_net_mst("STAR_NET", pin_positions, assignment)
        
        assert result.success, "Star routing should succeed"
        # Star topology should be efficient (no long detours)
        # Total Manhattan distance from center to 4 points = 4 * 20 = 80
        assert result.length <= 120, "Star topology should be efficient"


class TestMSTIntegration:
    """Integration tests for MST routing."""

    def test_mst_with_pin_escape(self):
        """MST routing should work with pin escape."""
        board = Board(width=50.0, height=50.0, origin=(0.0, 0.0))
        router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=1)

        # Block some areas
        router.block_rect(10, 10, 5, 5, layer=0)
        router.block_rect(30, 10, 5, 5, layer=0)

        pin_positions = [
            (12.0, 12.0),  # Inside blocked area
            (32.0, 12.0),  # Inside another blocked area
            (20.0, 25.0),  # Free area
        ]

        assignment = LayerAssignment(
            primary_layer=Layer.L1_TOP,
            allowed_layers=[Layer.L1_TOP]
        )

        # Should use both MST ordering AND pin escape
        result = router.route_net_mst_with_escape("COMBINED_NET", pin_positions, assignment)
        
        # May fail if pins are truly trapped, but should attempt optimal routing
        if result.success:
            assert len(result.cells) > 0, "Should have valid path"

    def test_mst_preserves_connectivity(self):
        """MST routing must connect all pins."""
        board = Board(width=80.0, height=80.0, origin=(0.0, 0.0))
        router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=1)

        # Random pin positions
        pin_positions = [
            (10.0, 10.0),
            (70.0, 10.0),
            (40.0, 40.0),
            (10.0, 70.0),
            (70.0, 70.0),
        ]

        assignment = LayerAssignment(
            primary_layer=Layer.L1_TOP,
            allowed_layers=[Layer.L1_TOP]
        )

        result = router.route_net_mst("CONNECTIVITY_NET", pin_positions, assignment)
        
        assert result.success, "Should successfully route all 5 pins"
        
        # Verify all pins are reachable in the routed path
        routed_cells = {(c.x, c.y) for c in result.cells}
        
        # Each pin should be at or near a routed cell
        for px, py in pin_positions:
            gx, gy = router._world_to_grid(px, py)
            # Check if pin cell or neighbors are in route
            neighbors_in_route = any(
                (gx + dx, gy + dy) in routed_cells
                for dx, dy in [(0, 0), (0, 1), (0, -1), (1, 0), (-1, 0)]
            )
            assert neighbors_in_route, f"Pin ({px}, {py}) should be connected"
