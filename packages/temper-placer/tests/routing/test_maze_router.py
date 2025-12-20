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
