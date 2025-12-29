"""
Tests for pin escape routing functionality (temper-tos3.1).

This module tests the two-stage routing approach:
1. Stage 1 (Pin Escape): Find shortest path from pin to nearest unblocked cell
2. Stage 2 (Net Connection): Route between escape points using existing A*
"""

import jax.numpy as jnp
import pytest

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Netlist, Net,Pin
from temper_placer.routing.layer_assignment import LayerAssignment, Layer
from temper_placer.routing.maze_router import MazeRouter


class TestPinEscapeBasics:
    """Basic pin escape routing tests."""

    def test_pin_escape_from_blocked_cell(self):
        """Pin cell blocked by component body requires escape."""
        board = Board(width=50.0, height=50.0, origin=(0.0, 0.0))
        router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=1)

        # Create a component with a pin
        component = Component(
            ref="U1",
            attributes={"value": "TEST"},
            footprint="TEST",
            bounds=(10.0, 10.0),
            pins=[
                Pin(name="1", number="1", position=(0.0, 0.0)),  # Center pin (blocked)
            ],
        )

        # Block component body (but not escape routes)
        position = jnp.array([[25.0, 25.0]])
        router.block_components([component], position, margin=0.5, escape_length=0)

        # Pin cell should now be blocked
        pin_gx, pin_gy = router._world_to_grid(25.0, 25.0)
        assert router.occupancy[pin_gx, pin_gy, 0] == -1, "Pin cell should be blocked"

        # Test escape point finding
        escape_point = router._find_escape_point((25.0, 25.0), radius=5)
        
        # Escape point should exist and be unblocked
        assert escape_point is not None, "Should find an escape point"
        escape_gx, escape_gy = escape_point
        assert router.occupancy[escape_gx, escape_gy, 0] != -1, "Escape point should not be blocked"

    def test_pin_escape_from_unblocked_cell(self):
        """Pin already in free cell doesn't need escape."""
        board = Board(width=50.0, height=50.0, origin=(0.0, 0.0))
        router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=1)

        # Pin in open space
        pin_pos = (25.0, 25.0)
        pin_gx, pin_gy = router._world_to_grid(*pin_pos)
        
        # Verify it's not blocked
        assert router.occupancy[pin_gx, pin_gy, 0] != -1

        # Escape from free cell should return self
        escape_point = router._find_escape_point(pin_pos, radius=5)
        assert escape_point == (pin_gx, pin_gy), "Free pin should escape to itself"

    def test_pin_escape_impossible_trapped(self):
        """Pin completely surrounded by obstacles returns None."""
        board = Board(width=50.0, height=50.0, origin=(0.0, 0.0))
        router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=1)

        # Block a large area
        for x in range(20, 30):
            for y in range(20, 30):
                if x < 49 and y < 49:  # Bounds check
                    router.occupancy[x, y, 0] = -1

        # Try to escape from center of blocked region
        escape_point = router._find_escape_point((24.5, 24.5), radius=5)
        
        # Should fail to find escape within radius
        assert escape_point is None, "Should not find escape when trapped"

    def test_pin_escape_prefers_shortest_distance(self):
        """Escape point should be closest unblocked cell."""
        board = Board(width=50.0, height=50.0, origin=(0.0, 0.0))
        router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=1)

        # Block a 5x5 region with one small opening
        center_gx, center_gy = 25, 25
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                router.occupancy[center_gx + dx, center_gy + dy, 0] = -1

        # Create one escape hole to the right (closest)
        router.occupancy[center_gx + 3, center_gy, 0] = 0

        pin_pos = (center_gx * 1.0, center_gy * 1.0)  # Convert to world coords
        escape_point = router._find_escape_point(pin_pos, radius=5)

        assert escape_point is not None
        # Should escape to the nearby hole
        escape_gx, escape_gy = escape_point
        distance = abs(escape_gx - center_gx) + abs(escape_gy - center_gy)
        assert distance <= 3, "Should find nearby escape hole"


class TestPinEscapeRouting:
    """Tests for full net routing with pin escape."""

    def test_route_net_with_escape(self):
        """Route net where pin escape is needed."""
        board = Board(width=50.0, height=50.0, origin=(0.0, 0.0))
        router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=1)

        # Create components with blocked pin cells
        component = Component(
            ref="U1",
            attributes={"value": "TEST"},
            footprint="TEST",
            bounds=(6.0, 6.0),
            pins=[Pin(name="1", number="1", position=(0.0, 0.0))],
        )

        # Block two components
        pos1 = jnp.array([[15.0, 25.0]])
        pos2 = jnp.array([[35.0, 25.0]])
        
        router.block_components([component], pos1, margin=0.5, escape_length=0)
        router.block_components([component], pos2, margin=0.5, escape_length=0)

        # Route between two pins (both need escape)
        pin_positions = [(15.0, 25.0), (35.0, 25.0)]
        assignment = LayerAssignment(
            primary_layer=Layer.L1_TOP,
            allowed_layers=[Layer.L1_TOP]
        )

        result = router.route_net_with_escape("TEST_NET", pin_positions, assignment)
        
        # Should succeed with escape routing
        assert result.success, f"Routing should succeed with escape, got: {result.failure_reason}"
        assert len(result.cells) > 0, "Should have a path"

    def test_route_net_escape_failure_reason(self):
        """Routing failure when pin is trapped returns pin_blocked."""
        board = Board(width=30.0, height=30.0, origin=(0.0, 0.0))
        router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=1)

        # Block entire board except tiny region
        for x in range(30):
            for y in range(30):
                router.occupancy[x, y, 0] = -1

        # Try to route from trapped pin
        pin_positions = [(15.0, 15.0), (16.0, 16.0)]
        assignment = LayerAssignment(
            primary_layer=Layer.L1_TOP,
            allowed_layers=[Layer.L1_TOP]
        )

        result = router.route_net_with_escape("TRAPPED_NET", pin_positions, assignment)
        
        assert not result.success, "Routing should fail when pins are trapped"
        assert result.failure_reason == "pin_blocked", "Should report pin_blocked failure"

    def test_route_multi_pin_net_with_escape(self):
        """Route 3+ pin net where all pins need escape."""
        board = Board(width=60.0, height=60.0, origin=(0.0, 0.0))
        router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=1)

        # Create multiple components
        component = Component(
            ref="U1",
            attributes={"value": "TEST"},
            footprint="TEST",
            bounds=(4.0, 4.0),
            pins=[Pin(name="1", number="1", position=(0.0, 0.0))],
        )

        positions = [
            jnp.array([[15.0, 30.0]]),
            jnp.array([[30.0, 30.0]]),
            jnp.array([[45.0, 30.0]]),
        ]
        
        for pos in positions:
            router.block_components([component], pos, margin=0.5, escape_length=0)

        # Route 3-pin net
        pin_positions = [(15.0, 30.0), (30.0, 30.0), (45.0, 30.0)]
        assignment = LayerAssignment(
            primary_layer=Layer.L1_TOP,
            allowed_layers=[Layer.L1_TOP]
        )

        result = router.route_net_with_escape("MULTI_PIN_NET", pin_positions, assignment)
        
        assert result.success, "3-pin net routing with escape should succeed"
        assert len(result.cells) > 0, "Should have routed path"


class TestPinEscapeIntegration:
    """Integration tests with real netlist."""

    def test_escape_improves_routing_completion(self):
        """Pin escape should improve routing completion on blocked boards."""
        board = Board(width=80.0, height=80.0, origin=(0.0, 0.0))
        router_no_escape = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=2)
        router_with_escape = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=2)

        # Create densely packed components
        component = Component(
            ref="R",
            attributes={"value": "10k"},
            footprint="0805",
            bounds=(2.0, 1.25),
            pins=[
                Pin(name="1", number="1", position=(-0.95, 0.0)),
                Pin(name="2", number="2", position=(0.95, 0.0)),
            ],
        )

        # Place 4 components in a grid
        pos_list = []
        for i, x in enumerate([20.0, 30.0, 50.0, 60.0]):
            pos_list.append(jnp.array([[x, 40.0]]))

        # Block components (no escape routes)
        for i, pos in enumerate(pos_list):
            router_no_escape.block_components([component], pos, margin=0.3, escape_length=0)
            router_with_escape.block_components([component], pos, margin=0.3, escape_length=0)

        # Create netlist with nets between components
        nets = [
            Net(name="NET1", pins=[("R1", "2"), ("R2", "1")]),
            Net(name="NET2", pins=[("R2", "2"), ("R3", "1")]),
            Net(name="NET3", pins=[("R3", "2"), ("R4", "1")]),
        ]

        # Try routing without escape
        assignment = LayerAssignment(
            primary_layer=Layer.L1_TOP,
            allowed_layers=[Layer.L1_TOP, Layer.L4_BOTTOM]
        )

        results_no_escape = {}
        results_with_escape = {}

        pin_pos_map = {
            ("R1", "2"): (20.0 + 0.95, 40.0),
            ("R2", "1"): (30.0 - 0.95, 40.0),
            ("R2", "2"): (30.0 + 0.95, 40.0),
            ("R3", "1"): (50.0 - 0.95, 40.0),
            ("R3", "2"): (50.0 + 0.95, 40.0),
            ("R4", "1"): (60.0 - 0.95, 40.0),
        }

        for net in nets:
            pin_positions = [pin_pos_map[pin] for pin in net.pins]
            
            # Without escape (regular routing)
            result_no_esc = router_no_escape.route_net(net.name, pin_positions, assignment)
            results_no_escape[net.name] = result_no_esc
            
            # With escape
            result_with_esc = router_with_escape.route_net_with_escape(net.name, pin_positions, assignment)
            results_with_escape[net.name] = result_with_esc

        # Count successes
        success_no_escape = sum(1 for r in results_no_escape.values() if r.success)
        success_with_escape = sum(1 for r in results_with_escape.values() if r.success)

        # Pin escape should improve or maintain routing success
        assert success_with_escape >= success_no_escape, \
            f"Escape routing should not reduce success rate: {success_with_escape} vs {success_no_escape}"
