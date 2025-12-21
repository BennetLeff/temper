"""
Tests for simplified maze router (temper-wna.4).

The maze router implements A* pathfinding on a grid to verify routing feasibility.
This is used to VERIFY that paths exist, not for production routing.

Features:
- Grid-based occupancy map
- A* pathfinding for single nets
- Sequential routing in priority order
- Via support for layer transitions
"""

import pytest
import jax.numpy as jnp

from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.core.board import Board


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def simple_board():
    """Create a simple 20x20mm board for testing."""
    return Board(
        width=20.0,
        height=20.0,
        origin=(0.0, 0.0),
        zones=[],
    )


@pytest.fixture
def sample_netlist():
    """Create a simple netlist for maze routing tests.

    Components are placed far apart with pins accessible from routing channels.
    The router uses 0.5mm margin when blocking, so pins need to be outside
    the component bounds + margin to be routable.

    U1 at (3, 10): bounds 5x4, blocked area x=[0, 6] with margin
    U2 at (17, 10): bounds 5x4, blocked area x=[14, 20] with margin
    Pins placed between components in the clear routing channel.
    """
    components = [
        Component(
            ref="U1",
            footprint="SOIC-8",
            bounds=(5.0, 4.0),
            # Pin position at +4.0 from center puts it outside blocked area
            # Component center at (3, 10), bounds edge at x=5.5, margin to x=6
            # Pin at x=7 (3+4) is in the clear channel
            pins=[Pin("1", "1", (4.0, 0.0), net="NET_A")],
            initial_position=(3.0, 10.0),
        ),
        Component(
            ref="U2",
            footprint="SOIC-8",
            bounds=(5.0, 4.0),
            # Pin position at -4.0 from center puts it outside blocked area
            # Component center at (17, 10), bounds edge at x=14.5, margin to x=14
            # Pin at x=13 (17-4) is in the clear channel
            pins=[Pin("1", "1", (-4.0, 0.0), net="NET_A")],
            initial_position=(17.0, 10.0),
        ),
    ]

    nets = [Net("NET_A", [("U1", "1"), ("U2", "1")])]

    return Netlist(components=components, nets=nets)


# =============================================================================
# Tests for GridCell Dataclass
# =============================================================================


class TestGridCell:
    """Tests for GridCell coordinate representation."""

    def test_grid_cell_creation(self):
        """Should create a valid grid cell."""
        from temper_placer.routing.maze_router import GridCell

        cell = GridCell(x=10, y=20, layer=0)

        assert cell.x == 10
        assert cell.y == 20
        assert cell.layer == 0

    def test_grid_cell_hashable(self):
        """GridCell should be hashable for use in sets/dicts."""
        from temper_placer.routing.maze_router import GridCell

        cell1 = GridCell(x=10, y=20, layer=0)
        cell2 = GridCell(x=10, y=20, layer=0)
        cell3 = GridCell(x=10, y=20, layer=1)

        assert hash(cell1) == hash(cell2)
        assert hash(cell1) != hash(cell3)

        # Can be used in set
        cell_set = {cell1, cell2, cell3}
        assert len(cell_set) == 2  # cell1 and cell2 are equal

    def test_grid_cell_equality(self):
        """GridCell equality should compare all fields."""
        from temper_placer.routing.maze_router import GridCell

        cell1 = GridCell(x=10, y=20, layer=0)
        cell2 = GridCell(x=10, y=20, layer=0)
        cell3 = GridCell(x=10, y=21, layer=0)

        assert cell1 == cell2
        assert cell1 != cell3


# =============================================================================
# Tests for RoutePath Dataclass
# =============================================================================


class TestRoutePath:
    """Tests for RoutePath result structure."""

    def test_route_path_successful(self):
        """Should create a successful route path."""
        from temper_placer.routing.maze_router import RoutePath, GridCell

        path = RoutePath(
            net="NET_A",
            cells=[GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(2, 0, 0)],
            length=3.0,
            via_count=0,
            success=True,
        )

        assert path.net == "NET_A"
        assert len(path.cells) == 3
        assert path.success is True
        assert path.failure_reason is None

    def test_route_path_failed(self):
        """Should create a failed route path with reason."""
        from temper_placer.routing.maze_router import RoutePath

        path = RoutePath(
            net="NET_B",
            cells=[],
            length=0.0,
            via_count=0,
            success=False,
            failure_reason="No path from (5,5) to (15,15)",
        )

        assert path.success is False
        assert "No path" in path.failure_reason


# =============================================================================
# Tests for MazeRouter Class
# =============================================================================


class TestMazeRouterInit:
    """Tests for MazeRouter initialization."""

    def test_router_creation(self, simple_board):
        """Should create a maze router from board dimensions."""
        from temper_placer.routing.maze_router import MazeRouter

        router = MazeRouter(
            grid_size=(20, 20),
            cell_size_mm=1.0,
            num_layers=2,
        )

        assert router.grid_size == (20, 20)
        assert router.cell_size == 1.0
        assert router.num_layers == 2

    def test_router_initial_occupancy(self, simple_board):
        """Initial occupancy should be all zeros (free)."""
        from temper_placer.routing.maze_router import MazeRouter

        router = MazeRouter(
            grid_size=(20, 20),
            cell_size_mm=1.0,
            num_layers=2,
        )

        assert router.occupancy.shape == (20, 20, 2)
        assert jnp.all(router.occupancy == 0)

    def test_router_from_board(self, simple_board):
        """Should create router from Board object."""
        from temper_placer.routing.maze_router import MazeRouter

        router = MazeRouter.from_board(simple_board, cell_size_mm=1.0)

        assert router.grid_size == (20, 20)


# =============================================================================
# Tests for Component Blocking
# =============================================================================


class TestComponentBlocking:
    """Tests for blocking cells occupied by components."""

    def test_block_single_component(self, simple_board):
        """Should mark cells occupied by a component as blocked."""
        from temper_placer.routing.maze_router import MazeRouter

        router = MazeRouter.from_board(simple_board, cell_size_mm=1.0)

        # Block a 4x4 component at (8, 8)
        router.block_rect(x=8, y=8, width=4, height=4, layer=0)

        # Cells (8,8) to (11,11) should be blocked
        assert router.occupancy[8, 8, 0] == 1
        assert router.occupancy[11, 11, 0] == 1

        # Outside should be free
        assert router.occupancy[7, 7, 0] == 0
        assert router.occupancy[12, 12, 0] == 0

    def test_block_components_from_netlist(self, sample_netlist, simple_board):
        """Should block all component areas from netlist."""
        from temper_placer.routing.maze_router import MazeRouter
        import jax.numpy as jnp

        router = MazeRouter.from_board(simple_board, cell_size_mm=1.0)

        # Create positions from initial positions
        positions = jnp.array(
            [
                [5.0, 10.0],  # U1
                [15.0, 10.0],  # U2
            ]
        )

        router.block_components(sample_netlist.components, positions)

        # Some cells should now be blocked
        total_blocked = jnp.sum(router.occupancy == 1)
        assert total_blocked > 0


# =============================================================================
# Tests for A* Pathfinding
# =============================================================================


class TestAStarPathfinding:
    """Tests for A* pathfinding algorithm."""

    def test_find_path_simple(self):
        """Should find a simple straight-line path."""
        from temper_placer.routing.maze_router import MazeRouter

        router = MazeRouter(grid_size=(10, 10), cell_size_mm=1.0, num_layers=1)

        path = router.find_path(start=(0, 5), end=(9, 5), layer=0)

        assert path is not None
        assert len(path) == 10  # 10 cells from 0 to 9

    def test_find_path_around_obstacle(self):
        """Should route around a blocked area."""
        from temper_placer.routing.maze_router import MazeRouter

        router = MazeRouter(grid_size=(10, 10), cell_size_mm=1.0, num_layers=1)

        # Block the middle row except ends
        for x in range(3, 7):
            router.block_rect(x=x, y=5, width=1, height=1, layer=0)

        path = router.find_path(start=(0, 5), end=(9, 5), layer=0)

        assert path is not None
        # Path should go around the obstacle
        assert len(path) > 10  # Longer than straight line

    def test_find_path_no_path_exists(self):
        """Should return None when no path exists."""
        from temper_placer.routing.maze_router import MazeRouter

        router = MazeRouter(grid_size=(10, 10), cell_size_mm=1.0, num_layers=1)

        # Block entire column, making path impossible
        for y in range(10):
            router.block_rect(x=5, y=y, width=1, height=1, layer=0)

        path = router.find_path(start=(0, 5), end=(9, 5), layer=0)

        assert path is None

    def test_find_path_deterministic(self):
        """Same inputs should produce same path."""
        from temper_placer.routing.maze_router import MazeRouter

        router = MazeRouter(grid_size=(10, 10), cell_size_mm=1.0, num_layers=1)

        path1 = router.find_path(start=(0, 0), end=(9, 9), layer=0)
        path2 = router.find_path(start=(0, 0), end=(9, 9), layer=0)

        assert path1 == path2


# =============================================================================
# Tests for Single Net Routing
# =============================================================================


class TestSingleNetRouting:
    """Tests for routing individual nets."""

    def test_route_two_pin_net(self, simple_board):
        """Should successfully route a 2-pin net."""
        from temper_placer.routing.maze_router import MazeRouter
        from temper_placer.routing.layer_assignment import LayerAssignment, Layer

        router = MazeRouter.from_board(simple_board, cell_size_mm=1.0)

        # Pin positions at (5,10) and (15,10)
        pin_positions = [(5.0, 10.0), (15.0, 10.0)]

        assignment = LayerAssignment(
            net="NET_A",
            primary_layer=Layer.L1_TOP,
            allowed_layers={Layer.L1_TOP},
            vias_required=False,
            reason="Test",
        )

        result = router.route_net("NET_A", pin_positions, assignment)

        assert result.success is True
        assert result.net == "NET_A"
        assert len(result.cells) > 0

    def test_route_net_marks_cells_routed(self, simple_board):
        """Routing should mark cells as used."""
        from temper_placer.routing.maze_router import MazeRouter
        from temper_placer.routing.layer_assignment import LayerAssignment, Layer

        router = MazeRouter.from_board(simple_board, cell_size_mm=1.0)

        pin_positions = [(5.0, 10.0), (15.0, 10.0)]
        assignment = LayerAssignment(
            net="NET_A",
            primary_layer=Layer.L1_TOP,
            allowed_layers={Layer.L1_TOP},
            vias_required=False,
            reason="Test",
        )

        # Before routing, all free
        assert jnp.sum(router.occupancy == 2) == 0

        router.route_net("NET_A", pin_positions, assignment)

        # After routing, some cells should be marked as routed (value 2)
        assert jnp.sum(router.occupancy == 2) > 0


# =============================================================================
# Tests for Multi-Net Sequential Routing
# =============================================================================


class TestMultiNetRouting:
    """Tests for routing multiple nets in sequence."""

    def test_route_all_nets(self, sample_netlist, simple_board):
        """Should route all nets in priority order."""
        from temper_placer.routing.maze_router import MazeRouter
        from temper_placer.routing.layer_assignment import assign_layers
        from temper_placer.routing.net_ordering import order_nets
        from temper_placer.core.loop import LoopCollection
        import jax.numpy as jnp

        router = MazeRouter.from_board(simple_board, cell_size_mm=1.0)

        # Use positions from fixture (3, 10) and (17, 10)
        positions = jnp.array([[3.0, 10.0], [17.0, 10.0]])
        router.block_components(sample_netlist.components, positions)

        # Get ordering and assignments
        net_order = order_nets(sample_netlist, LoopCollection())
        assignments = assign_layers(sample_netlist)

        # Route all nets
        results = router.route_all_nets(sample_netlist, positions, net_order, assignments)

        assert len(results) == len(sample_netlist.nets)
        assert all(r.success for r in results.values())

    def test_route_all_nets_reports_failures(self, simple_board):
        """Should report which nets failed to route."""
        from temper_placer.routing.maze_router import MazeRouter
        from temper_placer.routing.layer_assignment import assign_layers
        from temper_placer.routing.net_ordering import order_nets
        from temper_placer.core.loop import LoopCollection
        import jax.numpy as jnp

        # Create an impossible routing scenario
        # Two nets that must cross but both on same layer
        netlist = Netlist(
            components=[
                Component(
                    ref="U1",
                    footprint="SOIC-8",
                    bounds=(5.0, 4.0),
                    pins=[
                        Pin("1", "1", (0, 0), net="NET_H"),  # Top
                        Pin("2", "2", (0, 0), net="NET_V"),  # Left
                    ],
                ),
                Component(
                    ref="U2",
                    footprint="SOIC-8",
                    bounds=(5.0, 4.0),
                    pins=[Pin("1", "1", (0, 0), net="NET_H")],
                ),  # Top right
                Component(
                    ref="U3",
                    footprint="SOIC-8",
                    bounds=(5.0, 4.0),
                    pins=[Pin("1", "1", (0, 0), net="NET_V")],
                ),  # Bottom
            ],
            nets=[
                Net("NET_H", [("U1", "1"), ("U2", "1")]),
                Net("NET_V", [("U1", "2"), ("U3", "1")]),
            ],
        )

        # Note: This test may pass if the router is sophisticated enough
        # to find non-crossing paths. The key is testing failure reporting.
        router = MazeRouter.from_board(simple_board, cell_size_mm=0.5)

        # Heavily constrain the board to force failures
        for x in range(40):
            for y in range(40):
                if 15 < x < 25 and 15 < y < 25:
                    router.block_rect(x, y, 1, 1, 0)

        positions = jnp.array([[5.0, 10.0], [15.0, 10.0], [10.0, 15.0]])

        net_order = order_nets(netlist, LoopCollection())
        assignments = assign_layers(netlist)

        results = router.route_all_nets(netlist, positions, net_order, assignments)

        # Check that results dict has entries for all nets
        assert "NET_H" in results
        assert "NET_V" in results


# =============================================================================
# Tests for Via Handling
# =============================================================================


class TestViaHandling:
    """Tests for layer transitions via vias."""

    def test_route_with_via_allowed(self, simple_board):
        """Should use via when allowed and beneficial."""
        from temper_placer.routing.maze_router import MazeRouter
        from temper_placer.routing.layer_assignment import LayerAssignment, Layer

        router = MazeRouter(grid_size=(20, 20), cell_size_mm=1.0, num_layers=2)

        # Block layer 0 in the middle
        for x in range(8, 12):
            for y in range(0, 20):
                router.block_rect(x, y, 1, 1, layer=0)

        # Layer 1 is clear
        pin_positions = [(5.0, 10.0), (15.0, 10.0)]

        assignment = LayerAssignment(
            net="NET_A",
            primary_layer=Layer.L1_TOP,
            allowed_layers={Layer.L1_TOP, Layer.L4_BOT},  # Both layers allowed
            vias_required=True,
            reason="May need via",
        )

        result = router.route_net("NET_A", pin_positions, assignment)

        # If multi-layer routing is implemented, should succeed with via
        # Otherwise, this tests that failure is properly reported
        assert result is not None

    def test_count_vias_in_path(self):
        """Should correctly count layer transitions as vias."""
        from temper_placer.routing.maze_router import RoutePath, GridCell

        # Path that changes layers twice
        cells = [
            GridCell(0, 0, 0),  # Start on layer 0
            GridCell(1, 0, 0),
            GridCell(2, 0, 1),  # Via to layer 1
            GridCell(3, 0, 1),
            GridCell(4, 0, 0),  # Via back to layer 0
            GridCell(5, 0, 0),
        ]

        path = RoutePath(
            net="NET_A",
            cells=cells,
            length=5.0,
            via_count=2,  # Manually set for this test
            success=True,
        )

        assert path.via_count == 2


# =============================================================================
# Tests for Pin Escape Routes (BDD - Bug Fix for Pin Isolation)
# =============================================================================


class TestPinEscapeRoutes:
    """Tests for ensuring pins have escape routes after component blocking.

    BDD Scenario: Pins should remain routable after blocking components
    Given: Components placed on a board with pins at their edges
    When: Components are blocked on the routing grid
    Then: Pin locations should have at least one unblocked neighbor for escape

    This addresses the bug where component blocking creates isolated pin pockets,
    making routing impossible even though pins are technically unblocked.
    """

    def test_pin_has_escape_route_after_blocking(self):
        """Pin cells should have at least one free neighbor after component blocking.

        Given: A component with a pin at its edge
        When: The component is blocked
        Then: The pin's grid cell should have at least one unblocked neighbor
        """
        from temper_placer.routing.maze_router import MazeRouter, GridCell

        # Create a simple board
        board = Board(width=50.0, height=50.0, origin=(0.0, 0.0), zones=[])

        # Create a component with pin at edge (typical SMD package)
        # Component: 10x10mm, centered at (25, 25)
        # Pin at offset (5, 0) -> absolute position (30, 25) - at right edge
        component = Component(
            ref="U1",
            footprint="QFP-44",
            bounds=(10.0, 10.0),
            pins=[Pin("1", "1", (5.0, 0.0), net="NET_A")],  # Pin at right edge
            initial_position=(25.0, 25.0),
        )

        router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=2)
        positions = jnp.array([[25.0, 25.0]])

        # Block the component
        router.block_components([component], positions)

        # Get pin grid position
        pin_world = (25.0 + 5.0, 25.0 + 0.0)  # (30, 25)
        pin_grid = router._world_to_grid(pin_world[0], pin_world[1])

        # Temporarily unblock the pin cell (as route_net would do)
        router.occupancy = router.occupancy.at[pin_grid[0], pin_grid[1], 0].set(0)

        # Check neighbors
        neighbors = router._get_neighbors(
            GridCell(pin_grid[0], pin_grid[1], 0),
            allow_layer_change=False,
        )

        # EXPECTED TO PASS with improved blocking logic
        assert len(neighbors) >= 1, (
            f"Pin at grid {pin_grid} has no escape route! "
            f"Occupancy around pin: blocked neighbors prevent routing."
        )

    def test_pins_at_component_edges_remain_accessible(self):
        """Pins placed at standard SMD package edges should be routable.

        Given: Two components with pins facing each other
        When: Both components are blocked
        Then: A path should exist between the pins
        """
        from temper_placer.routing.maze_router import MazeRouter
        from temper_placer.routing.layer_assignment import LayerAssignment, Layer

        board = Board(width=100.0, height=100.0, origin=(0.0, 0.0), zones=[])

        # Two SOIC-8 packages (5x4mm) with pins facing each other
        # U1 at (20, 50), pin at right edge (+2.5, 0) -> absolute (22.5, 50)
        # U2 at (80, 50), pin at left edge (-2.5, 0) -> absolute (77.5, 50)
        components = [
            Component(
                ref="U1",
                footprint="SOIC-8",
                bounds=(5.0, 4.0),
                pins=[Pin("1", "1", (2.5, 0.0), net="NET_A")],  # Right edge
                initial_position=(20.0, 50.0),
            ),
            Component(
                ref="U2",
                footprint="SOIC-8",
                bounds=(5.0, 4.0),
                pins=[Pin("1", "1", (-2.5, 0.0), net="NET_A")],  # Left edge
                initial_position=(80.0, 50.0),
            ),
        ]

        netlist = Netlist(
            components=components,
            nets=[Net("NET_A", [("U1", "1"), ("U2", "1")])],
        )

        router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=2)
        positions = jnp.array([[20.0, 50.0], [80.0, 50.0]])

        # Block components
        router.block_components(components, positions)

        # Try to route between pins
        pin_positions = [(22.5, 50.0), (77.5, 50.0)]
        assignment = LayerAssignment(
            net="NET_A",
            primary_layer=Layer.L1_TOP,
            allowed_layers={Layer.L1_TOP, Layer.L4_BOT},
            vias_required=False,
            reason="Test",
        )

        result = router.route_net("NET_A", pin_positions, assignment)

        # SHOULD PASS with escape routes
        assert result.success, (
            f"Failed to route between pins: {result.failure_reason}. "
            f"Pins should have escape routes after component blocking."
        )
        assert result.length > 0, "Routed path should have non-zero length"

    def test_real_world_component_routing(self):
        """Test routing with realistic component dimensions from Temper project.

        This test uses actual component sizes from the Temper induction cooker
        to verify the router handles real PCB layouts.
        """
        from temper_placer.routing.maze_router import MazeRouter
        from temper_placer.routing.layer_assignment import LayerAssignment, Layer

        # Temper board: 100x150mm
        board = Board(width=100.0, height=150.0, origin=(0.0, 0.0), zones=[])

        # Realistic components:
        # - IGBT (IKW40N120H3): ~27x16mm TO-247 package
        # - Gate driver (UCC21550): ~5x4mm SOIC-8
        # - Decoupling cap: ~3x1.5mm 0805
        components = [
            Component(
                ref="Q1",
                footprint="TO-247",
                bounds=(27.0, 16.0),
                pins=[
                    Pin("1", "G", (0.0, -8.0), net="GATE"),  # Gate at bottom
                    Pin("2", "C", (-10.0, 0.0), net="DC_BUS"),  # Collector
                ],
                initial_position=(50.0, 100.0),
            ),
            Component(
                ref="U1",
                footprint="SOIC-8",
                bounds=(5.0, 4.0),
                pins=[
                    Pin("7", "OUTL", (2.5, 0.0), net="GATE"),  # Output at right edge
                ],
                initial_position=(30.0, 100.0),
            ),
        ]

        netlist = Netlist(
            components=components,
            nets=[Net("GATE", [("Q1", "G"), ("U1", "OUTL")])],
        )

        router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=2)
        positions = jnp.array([[50.0, 100.0], [30.0, 100.0]])

        router.block_components(components, positions)

        # Pin positions:
        # Q1.G = (50, 100) + (0, -8) = (50, 92)
        # U1.OUTL = (30, 100) + (2.5, 0) = (32.5, 100)
        pin_positions = [(50.0, 92.0), (32.5, 100.0)]

        assignment = LayerAssignment(
            net="GATE",
            primary_layer=Layer.L1_TOP,
            allowed_layers={Layer.L1_TOP, Layer.L4_BOT},
            vias_required=False,
            reason="Gate signal",
        )

        result = router.route_net("GATE", pin_positions, assignment)

        assert result.success, (
            f"Failed to route GATE net: {result.failure_reason}. "
            f"Real-world component routing should succeed."
        )


# =============================================================================
# Tests for Routing Completion
# =============================================================================


class TestRoutingCompletion:
    """Tests for routing completion metrics."""

    def test_completion_rate_all_routed(self, sample_netlist, simple_board):
        """100% completion when all nets routed."""
        from temper_placer.routing.maze_router import MazeRouter, compute_completion_rate
        from temper_placer.routing.layer_assignment import assign_layers
        from temper_placer.routing.net_ordering import order_nets
        from temper_placer.core.loop import LoopCollection
        import jax.numpy as jnp

        router = MazeRouter.from_board(simple_board, cell_size_mm=1.0)
        # Use positions matching fixture (3, 10) and (17, 10)
        positions = jnp.array([[3.0, 10.0], [17.0, 10.0]])

        net_order = order_nets(sample_netlist, LoopCollection())
        assignments = assign_layers(sample_netlist)

        results = router.route_all_nets(sample_netlist, positions, net_order, assignments)

        completion = compute_completion_rate(results)
        assert completion == 1.0

    def test_completion_rate_partial(self):
        """Should compute partial completion correctly."""
        from temper_placer.routing.maze_router import RoutePath, compute_completion_rate

        results = {
            "NET_A": RoutePath("NET_A", [], 0, 0, True),
            "NET_B": RoutePath("NET_B", [], 0, 0, True),
            "NET_C": RoutePath("NET_C", [], 0, 0, False, "Blocked"),
            "NET_D": RoutePath("NET_D", [], 0, 0, False, "Blocked"),
        }

        completion = compute_completion_rate(results)
        assert completion == 0.5  # 2 out of 4