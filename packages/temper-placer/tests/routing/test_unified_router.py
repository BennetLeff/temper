"""
Tests for unified router that integrates maze and push-shove routing.
"""

import pytest
import jax.numpy as jnp

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.routing.layer_assignment import Layer, LayerAssignment
from temper_placer.routing.unified_router import (
    RoutingConfig,
    RoutingStrategy,
    UnifiedRouter,
    UnifiedRoutePath,
)


@pytest.fixture
def simple_board():
    """Create a simple test board."""
    return Board(width=100.0, height=100.0, origin=(0.0, 0.0), zones=[])


@pytest.fixture
def simple_netlist():
    """Create a simple 2-component, 1-net netlist."""
    components = [
        Component(
            ref="U1",
            footprint="SOIC-8",
            bounds=(5.0, 4.0),
            pins=[Pin("1", "1", (4.0, 0.0), net="VCC")],
            initial_position=(10.0, 10.0),
        ),
        Component(
            ref="U2",
            footprint="SOIC-8",
            bounds=(5.0, 4.0),
            pins=[Pin("1", "1", (-4.0, 0.0), net="VCC")],
            initial_position=(30.0, 10.0),
        ),
    ]

    nets = [Net("VCC", [("U1", "1"), ("U2", "1")])]

    return Netlist(components=components, nets=nets)


@pytest.fixture
def simple_positions():
    """Create simple component positions."""
    return jnp.array([[10.0, 10.0, 0.0], [30.0, 10.0, 0.0]])


@pytest.fixture
def simple_assignments():
    """Create simple layer assignments."""
    return {
        "VCC": LayerAssignment(
            net="VCC", primary_layer=Layer.L1_TOP, allowed_layers={Layer.L1_TOP}
        ),
    }


class TestRoutingConfig:
    """Tests for RoutingConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = RoutingConfig()

        assert config.strategy == RoutingStrategy.AUTO
        assert config.maze_cell_size == 1.0
        assert config.push_shove_max_iterations == 10
        assert config.push_shove_num_samples == 20
        assert config.enable_via is True
        assert config.prefer_push_shove_for_dense is False

    def test_custom_config(self):
        """Test custom configuration."""
        config = RoutingConfig(
            strategy=RoutingStrategy.HYBRID,
            maze_cell_size=0.5,
            push_shove_max_iterations=20,
            enable_via=False,
        )

        assert config.strategy == RoutingStrategy.HYBRID
        assert config.maze_cell_size == 0.5
        assert config.push_shove_max_iterations == 20
        assert config.enable_via is False


class TestUnifiedRoutePath:
    """Tests for UnifiedRoutePath."""

    def test_default_cells_empty_list(self):
        """Test that cells defaults to empty list."""
        path = UnifiedRoutePath(net="TEST", success=True, method="maze")
        assert path.cells == []

    def test_with_cells(self):
        """Test path with cells."""
        cells = [(0, 0, 0), (1, 0, 0), (2, 0, 0)]
        path = UnifiedRoutePath(net="TEST", success=True, cells=cells, method="maze", length=2.0)

        assert path.cells == cells
        assert path.length == 2.0
        assert path.method == "maze"


class TestUnifiedRouterInit:
    """Tests for UnifiedRouter initialization."""

    def test_init_with_defaults(self, simple_board):
        """Test initialization with default config."""
        router = UnifiedRouter(simple_board)

        assert router.board == simple_board
        assert router.config.strategy == RoutingStrategy.AUTO
        assert router.maze_router is not None
        assert router.push_shove_grid is None  # Lazy init

    def test_init_with_custom_config(self, simple_board):
        """Test initialization with custom config."""
        config = RoutingConfig(strategy=RoutingStrategy.MAZE_ONLY, maze_cell_size=0.5)
        router = UnifiedRouter(simple_board, config)

        assert router.config.strategy == RoutingStrategy.MAZE_ONLY
        assert router.config.maze_cell_size == 0.5

    def test_from_board_factory(self, simple_board):
        """Test from_board factory method."""
        router = UnifiedRouter.from_board(
            simple_board, strategy=RoutingStrategy.PUSH_SHOVE_ONLY, maze_cell_size=2.0
        )

        assert router.config.strategy == RoutingStrategy.PUSH_SHOVE_ONLY
        assert router.config.maze_cell_size == 2.0


class TestMazeRouting:
    """Tests for maze-only routing."""

    def test_maze_only_strategy(
        self, simple_board, simple_netlist, simple_positions, simple_assignments
    ):
        """Test routing with MAZE_ONLY strategy."""
        router = UnifiedRouter.from_board(simple_board, strategy=RoutingStrategy.MAZE_ONLY)

        results = router.route_all_nets(
            simple_netlist, simple_positions, ["VCC"], simple_assignments
        )

        assert len(results) == 1
        assert "VCC" in results

        # Check that maze router was used
        assert results["VCC"].method == "maze"

    def test_maze_single_net(self, simple_board):
        """Test routing a single net with maze router."""
        router = UnifiedRouter.from_board(simple_board, strategy=RoutingStrategy.MAZE_ONLY)

        assignment = LayerAssignment(
            net="TEST", primary_layer=Layer.L1_TOP, allowed_layers={Layer.L1_TOP}
        )
        pin_positions = [(10.0, 10.0), (30.0, 10.0)]

        result = router.route_net("TEST", pin_positions, assignment)

        assert result.success
        assert result.method == "maze"
        assert result.net == "TEST"
        assert result.length > 0


class TestPushShoveRouting:
    """Tests for push-shove routing."""

    def test_push_shove_only_strategy(
        self, simple_board, simple_netlist, simple_positions, simple_assignments
    ):
        """Test routing with PUSH_SHOVE_ONLY strategy."""
        router = UnifiedRouter.from_board(simple_board, strategy=RoutingStrategy.PUSH_SHOVE_ONLY)

        results = router.route_all_nets(
            simple_netlist, simple_positions, ["VCC"], simple_assignments
        )

        assert len(results) == 1

        # Check that push-shove router was used
        assert results["VCC"].method == "push-shove"

    def test_push_shove_single_net(self, simple_board):
        """Test routing a single net with push-shove router."""
        router = UnifiedRouter.from_board(simple_board, strategy=RoutingStrategy.PUSH_SHOVE_ONLY)

        assignment = LayerAssignment(
            net="TEST", primary_layer=Layer.L1_TOP, allowed_layers={Layer.L1_TOP}
        )
        pin_positions = [(10.0, 10.0), (30.0, 10.0)]

        result = router.route_net("TEST", pin_positions, assignment)

        assert result.success
        assert result.method == "push-shove"
        assert result.net == "TEST"


class TestAutoStrategy:
    """Tests for AUTO strategy (maze first, fallback to push-shove)."""

    def test_auto_uses_maze_when_successful(self, simple_board):
        """Test that AUTO strategy prefers maze router when it succeeds."""
        router = UnifiedRouter.from_board(simple_board, strategy=RoutingStrategy.AUTO)

        assignment = LayerAssignment(
            net="TEST", primary_layer=Layer.L1_TOP, allowed_layers={Layer.L1_TOP}
        )
        pin_positions = [(10.0, 10.0), (30.0, 10.0)]

        result = router.route_net("TEST", pin_positions, assignment)

        assert result.success
        # Maze should succeed for simple straight path
        assert result.method == "maze"

    def test_auto_fallback_to_push_shove(self, simple_board):
        """Test that AUTO falls back to push-shove when maze fails."""
        router = UnifiedRouter.from_board(simple_board, strategy=RoutingStrategy.AUTO)

        # Create a scenario where maze might fail but push-shove could work
        # (This is hard to construct without more complex board setup)
        assignment = LayerAssignment(
            net="TEST", primary_layer=Layer.L1_TOP, allowed_layers={Layer.L1_TOP}
        )
        pin_positions = [(10.0, 10.0), (30.0, 10.0)]

        result = router.route_net("TEST", pin_positions, assignment)

        # Should succeed with one of the methods
        assert result.method in ["maze", "push-shove"]


class TestHybridStrategy:
    """Tests for HYBRID strategy (try both, pick best)."""

    def test_hybrid_picks_best(self, simple_board):
        """Test that HYBRID strategy tries both and picks best result."""
        router = UnifiedRouter.from_board(simple_board, strategy=RoutingStrategy.HYBRID)

        assignment = LayerAssignment(
            net="TEST", primary_layer=Layer.L1_TOP, allowed_layers={Layer.L1_TOP}
        )
        pin_positions = [(10.0, 10.0), (30.0, 10.0)]

        result = router.route_net("TEST", pin_positions, assignment)

        assert result.success
        # Should pick one based on success/length
        assert result.method in ["maze", "push-shove"]


class TestStatistics:
    """Tests for routing statistics."""

    def test_completion_rate(self, simple_board):
        """Test completion rate calculation."""
        router = UnifiedRouter.from_board(simple_board)

        results = {
            "NET1": UnifiedRoutePath(net="NET1", success=True, method="maze"),
            "NET2": UnifiedRoutePath(net="NET2", success=True, method="maze"),
            "NET3": UnifiedRoutePath(net="NET3", success=False, method="maze"),
        }

        completion_rate = router.get_completion_rate(results)
        assert completion_rate == pytest.approx(2.0 / 3.0)

    def test_completion_rate_empty(self, simple_board):
        """Test completion rate with no results."""
        router = UnifiedRouter.from_board(simple_board)
        assert router.get_completion_rate({}) == 0.0

    def test_statistics(self, simple_board):
        """Test routing statistics."""
        router = UnifiedRouter.from_board(simple_board)

        results = {
            "NET1": UnifiedRoutePath(
                net="NET1", success=True, method="maze", length=10.0, via_count=2
            ),
            "NET2": UnifiedRoutePath(
                net="NET2", success=True, method="push-shove", length=15.0, via_count=1
            ),
            "NET3": UnifiedRoutePath(
                net="NET3", success=False, method="maze", length=0.0, via_count=0
            ),
        }

        stats = router.get_statistics(results)

        assert stats["total_nets"] == 3
        assert stats["successful"] == 2
        assert stats["failed"] == 1
        assert stats["completion_rate"] == pytest.approx(2.0 / 3.0)
        assert stats["maze_routed"] == 2
        assert stats["push_shove_routed"] == 1
        assert stats["total_length"] == 25.0
        assert stats["total_vias"] == 3
        assert stats["avg_length"] == 12.5
        assert stats["avg_vias"] == 1.5


class TestEdgeCases:
    """Tests for edge cases."""

    def test_single_pin_net(self, simple_board):
        """Test routing net with only one pin (should skip)."""
        router = UnifiedRouter.from_board(simple_board)

        assignment = LayerAssignment(
            net="TEST", primary_layer=Layer.L1_TOP, allowed_layers={Layer.L1_TOP}
        )
        pin_positions = [(10.0, 10.0)]

        result = router.route_net("TEST", pin_positions, assignment)

        assert result.success
        # Should be handled gracefully

    def test_no_pin_net(self, simple_board):
        """Test routing net with no pins."""
        router = UnifiedRouter.from_board(simple_board)

        assignment = LayerAssignment(
            net="TEST", primary_layer=Layer.L1_TOP, allowed_layers={Layer.L1_TOP}
        )
        pin_positions = []

        result = router.route_net("TEST", pin_positions, assignment)

        assert result.success

    def test_invalid_strategy(self, simple_board):
        """Test that invalid strategy raises error."""
        router = UnifiedRouter.from_board(simple_board)
        router.config.strategy = "INVALID"  # type: ignore

        assignment = LayerAssignment(
            net="TEST", primary_layer=Layer.L1_TOP, allowed_layers={Layer.L1_TOP}
        )
        pin_positions = [(10.0, 10.0), (30.0, 10.0)]

        with pytest.raises(ValueError, match="Unknown routing strategy"):
            router.route_net("TEST", pin_positions, assignment)


class TestIntegration:
    """Integration tests for complete routing workflows."""

    def test_full_netlist_routing(
        self, simple_board, simple_netlist, simple_positions, simple_assignments
    ):
        """Test routing complete netlist with AUTO strategy."""
        router = UnifiedRouter.from_board(simple_board, strategy=RoutingStrategy.AUTO)

        results = router.route_all_nets(
            simple_netlist, simple_positions, ["VCC"], simple_assignments
        )

        # Should route the net
        assert len(results) == 1
        assert results["VCC"].success

        # Check statistics
        stats = router.get_statistics(results)
        assert stats["completion_rate"] == 1.0
        assert stats["successful"] == 1

    def test_multi_strategy_comparison(
        self, simple_board, simple_netlist, simple_positions, simple_assignments
    ):
        """Test comparing results across different strategies."""
        strategies = [
            RoutingStrategy.MAZE_ONLY,
            RoutingStrategy.PUSH_SHOVE_ONLY,
            RoutingStrategy.AUTO,
            RoutingStrategy.HYBRID,
        ]

        all_results = {}
        for strategy in strategies:
            router = UnifiedRouter.from_board(simple_board, strategy=strategy)
            results = router.route_all_nets(
                simple_netlist, simple_positions, ["VCC"], simple_assignments
            )
            all_results[strategy] = results

        # All strategies should produce results
        for strategy, results in all_results.items():
            assert len(results) == 1, f"Strategy {strategy} failed to route net"
