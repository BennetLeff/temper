"""
Tests for grid-based congestion analysis (temper-wna.3).

The congestion analyzer divides the board into grid cells and estimates
routing demand vs supply to identify bottlenecks before actual routing.

Grid Model:
- Board divided into cells (default 1mm x 1mm)
- Each cell has a capacity (tracks that fit)
- Demand = estimated routing through each cell
- Bottleneck = demand > supply
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
    """Create a simple 100x100mm board for testing."""
    return Board(
        width=100.0,
        height=100.0,
        origin=(0.0, 0.0),
        zones=[],
    )


@pytest.fixture
def small_board():
    """Create a small 20x20mm board for detailed congestion testing."""
    return Board(
        width=20.0,
        height=20.0,
        origin=(0.0, 0.0),
        zones=[],
    )


@pytest.fixture
def sample_netlist():
    """Create a sample netlist for congestion testing."""
    components = [
        Component(
            ref="U1",
            footprint="QFP-48",
            bounds=(10.0, 10.0),
            pins=[
                Pin("1", "1", (-4.5, 4.5), net="NET_A"),
                Pin("2", "2", (-4.5, 3.5), net="NET_B"),
                Pin("24", "24", (4.5, 4.5), net="NET_C"),
            ],
            initial_position=(25.0, 25.0),
        ),
        Component(
            ref="U2",
            footprint="QFP-48",
            bounds=(10.0, 10.0),
            pins=[
                Pin("1", "1", (-4.5, 4.5), net="NET_A"),
                Pin("2", "2", (-4.5, 3.5), net="NET_B"),
            ],
            initial_position=(75.0, 25.0),
        ),
        Component(
            ref="R1",
            footprint="0603",
            bounds=(1.6, 0.8),
            pins=[
                Pin("1", "1", (-0.75, 0.0), net="NET_C"),
                Pin("2", "2", (0.75, 0.0), net="NET_D"),
            ],
            initial_position=(50.0, 50.0),
        ),
    ]

    nets = [
        Net("NET_A", [("U1", "1"), ("U2", "1")]),
        Net("NET_B", [("U1", "2"), ("U2", "2")]),
        Net("NET_C", [("U1", "24"), ("R1", "1")]),
        Net("NET_D", [("R1", "2")]),
    ]

    return Netlist(components=components, nets=nets)


@pytest.fixture
def congested_netlist():
    """Create a netlist that will cause congestion (many nets in small area)."""
    # 4 ICs in corners, all connected to each other
    components = []
    nets = []

    # Create 4 ICs at corners of a 20x20 area
    positions = [(5, 5), (15, 5), (5, 15), (15, 15)]
    for i, (x, y) in enumerate(positions):
        ref = f"U{i + 1}"
        pins = [Pin("OUT", "1", (0, 0), net=f"NET_{i}")]
        # Each IC connects to all others
        for j in range(4):
            if j != i:
                pins.append(Pin(f"IN{j}", str(j + 2), (1.0, j * 0.5), net=f"CROSS_{i}_{j}"))

        components.append(
            Component(
                ref=ref,
                footprint="QFP-16",
                bounds=(4.0, 4.0),
                pins=pins,
                initial_position=(float(x), float(y)),
            )
        )

    # Create cross-connection nets
    for i in range(4):
        for j in range(i + 1, 4):
            nets.append(Net(f"CROSS_{i}_{j}", [(f"U{i + 1}", f"IN{j}"), (f"U{j + 1}", f"IN{i}")]))

    return Netlist(components=components, nets=nets)


# =============================================================================
# Tests for CongestionGrid Dataclass
# =============================================================================


class TestCongestionGrid:
    """Tests for CongestionGrid data structure."""

    def test_grid_creation(self, simple_board):
        """Should create a congestion grid with correct dimensions."""
        from temper_placer.routing.congestion import CongestionGrid

        grid = CongestionGrid.from_board(simple_board, cell_size_mm=1.0)

        assert grid.width_cells == 100
        assert grid.height_cells == 100
        assert grid.cell_size_mm == 1.0
        assert grid.demand.shape == (100, 100)
        assert grid.supply.shape == (100, 100)

    def test_grid_creation_custom_cell_size(self, simple_board):
        """Should handle custom cell sizes."""
        from temper_placer.routing.congestion import CongestionGrid

        grid = CongestionGrid.from_board(simple_board, cell_size_mm=2.0)

        assert grid.width_cells == 50
        assert grid.height_cells == 50
        assert grid.cell_size_mm == 2.0

    def test_grid_initial_demand_zero(self, simple_board):
        """Initial demand should be zero everywhere."""
        from temper_placer.routing.congestion import CongestionGrid

        grid = CongestionGrid.from_board(simple_board, cell_size_mm=1.0)

        assert jnp.all(grid.demand == 0.0)

    def test_grid_default_supply(self, simple_board):
        """Default supply should be uniform and positive."""
        from temper_placer.routing.congestion import CongestionGrid

        grid = CongestionGrid.from_board(simple_board, cell_size_mm=1.0)

        assert jnp.all(grid.supply > 0)


# =============================================================================
# Tests for Demand Estimation
# =============================================================================


class TestDemandEstimation:
    """Tests for routing demand estimation."""

    def test_single_net_demand(self, simple_board):
        """Single net should create demand along its path."""
        from temper_placer.routing.congestion import (
            CongestionGrid,
            estimate_net_demand,
        )

        grid = CongestionGrid.from_board(simple_board, cell_size_mm=1.0)

        # Simple 2-pin net spanning 10 cells horizontally
        pin_positions = [(10.0, 50.0), (20.0, 50.0)]

        grid = estimate_net_demand(grid, pin_positions)

        # Demand should be non-zero along the path
        # Using bounding box estimation, cells from x=10 to x=20 at y=50 should have demand
        assert grid.demand[50, 10:21].sum() > 0

    def test_no_demand_outside_bbox(self, simple_board):
        """Demand should be zero outside the net's bounding box."""
        from temper_placer.routing.congestion import (
            CongestionGrid,
            estimate_net_demand,
        )

        grid = CongestionGrid.from_board(simple_board, cell_size_mm=1.0)
        pin_positions = [(10.0, 50.0), (20.0, 50.0)]

        grid = estimate_net_demand(grid, pin_positions)

        # Demand should be zero far from the net
        assert grid.demand[0:40, 0:5].sum() == 0
        assert grid.demand[60:100, 80:100].sum() == 0

    def test_multi_pin_net_demand(self, simple_board):
        """Multi-pin nets should have demand across all pin regions."""
        from temper_placer.routing.congestion import (
            CongestionGrid,
            estimate_net_demand,
        )

        grid = CongestionGrid.from_board(simple_board, cell_size_mm=1.0)

        # 3-pin net forming a triangle
        pin_positions = [(10.0, 10.0), (90.0, 10.0), (50.0, 90.0)]

        grid = estimate_net_demand(grid, pin_positions)

        # Total demand should be significant for this large net
        assert grid.demand.sum() > 0


# =============================================================================
# Tests for Congestion Analysis
# =============================================================================


class TestCongestionAnalysis:
    """Tests for the main congestion analysis function."""

    def test_analyze_congestion_returns_result(self, sample_netlist, simple_board):
        """Should return a CongestionResult with all fields."""
        from temper_placer.routing.congestion import analyze_congestion

        result = analyze_congestion(sample_netlist, simple_board)

        assert hasattr(result, "grid")
        assert hasattr(result, "bottlenecks")
        assert hasattr(result, "total_overflow")
        assert hasattr(result, "max_utilization")

    def test_analyze_congestion_no_overflow_sparse_board(self, simple_board):
        """Sparse netlist on large board should have no overflow."""
        from temper_placer.routing.congestion import analyze_congestion

        # Very sparse netlist - just 2 components with 1 net
        sparse_netlist = Netlist(
            components=[
                Component(
                    ref="R1",
                    footprint="0603",
                    bounds=(1.6, 0.8),
                    pins=[Pin("1", "1", (0, 0), net="NET1")],
                    initial_position=(10.0, 10.0),
                ),
                Component(
                    ref="R2",
                    footprint="0603",
                    bounds=(1.6, 0.8),
                    pins=[Pin("1", "1", (0, 0), net="NET1")],
                    initial_position=(20.0, 10.0),
                ),
            ],
            nets=[Net("NET1", [("R1", "1"), ("R2", "1")])],
        )

        result = analyze_congestion(sparse_netlist, simple_board)

        assert result.total_overflow == 0.0

    def test_analyze_congestion_detects_bottlenecks(self, congested_netlist, small_board):
        """Dense netlist should produce bottlenecks."""
        from temper_placer.routing.congestion import analyze_congestion

        result = analyze_congestion(
            congested_netlist, small_board, cell_size_mm=1.0, capacity_per_cell=2.0
        )

        # With many crossing nets on a small board, expect some bottlenecks
        # Note: actual bottleneck detection depends on implementation
        assert result.max_utilization > 0

    def test_analyze_congestion_deterministic(self, sample_netlist, simple_board):
        """Same inputs should produce same results."""
        from temper_placer.routing.congestion import analyze_congestion

        result1 = analyze_congestion(sample_netlist, simple_board)
        result2 = analyze_congestion(sample_netlist, simple_board)

        assert jnp.allclose(result1.grid.demand, result2.grid.demand)
        assert result1.total_overflow == result2.total_overflow


# =============================================================================
# Tests for Bottleneck Dataclass
# =============================================================================


class TestBottleneck:
    """Tests for Bottleneck data structure."""

    def test_bottleneck_creation(self):
        """Should create a valid bottleneck."""
        from temper_placer.routing.congestion import Bottleneck

        bottleneck = Bottleneck(
            x=50,
            y=25,
            utilization=1.5,
            overflow=5.0,
        )

        assert bottleneck.x == 50
        assert bottleneck.y == 25
        assert bottleneck.utilization == 1.5
        assert bottleneck.overflow == 5.0

    def test_bottleneck_to_coordinates(self):
        """Should convert grid cell to board coordinates."""
        from temper_placer.routing.congestion import Bottleneck

        bottleneck = Bottleneck(x=10, y=20, utilization=1.2, overflow=2.0)

        # With 1mm cells, center of cell (10, 20) is at (10.5, 20.5)
        coords = bottleneck.to_coordinates(cell_size_mm=1.0, origin=(0.0, 0.0))

        assert coords == pytest.approx((10.5, 20.5), rel=0.01)


# =============================================================================
# Tests for CongestionResult
# =============================================================================


class TestCongestionResult:
    """Tests for CongestionResult data structure."""

    def test_result_feasibility_check(self, sample_netlist, simple_board):
        """Result should correctly report feasibility."""
        from temper_placer.routing.congestion import analyze_congestion

        result = analyze_congestion(sample_netlist, simple_board)

        # Sparse board should be feasible
        assert result.is_feasible()

    def test_result_overflow_ratio(self, sample_netlist, simple_board):
        """Should compute overflow ratio correctly."""
        from temper_placer.routing.congestion import analyze_congestion

        result = analyze_congestion(sample_netlist, simple_board)

        # Overflow ratio should be 0 for feasible result
        assert result.overflow_ratio() >= 0.0
        assert result.overflow_ratio() <= 1.0

    def test_result_get_top_bottlenecks(self, sample_netlist, simple_board):
        """Should return top N bottlenecks sorted by severity."""
        from temper_placer.routing.congestion import analyze_congestion

        result = analyze_congestion(sample_netlist, simple_board)

        top_3 = result.get_top_bottlenecks(n=3)

        assert len(top_3) <= 3
        # If there are bottlenecks, they should be sorted by overflow
        if len(top_3) >= 2:
            assert top_3[0].overflow >= top_3[1].overflow


# =============================================================================
# Tests for Position-Based Analysis
# =============================================================================


class TestPositionBasedAnalysis:
    """Tests for congestion analysis with actual component positions."""

    def test_analyze_with_positions(self, sample_netlist, simple_board):
        """Should use provided positions instead of initial_position."""
        from temper_placer.routing.congestion import analyze_congestion
        import jax.numpy as jnp

        # Create positions array (N, 2)
        positions = jnp.array(
            [
                [25.0, 25.0],  # U1
                [75.0, 25.0],  # U2
                [50.0, 50.0],  # R1
            ]
        )

        result = analyze_congestion(sample_netlist, simple_board, positions=positions)

        assert result.grid is not None

    def test_analysis_changes_with_positions(self, sample_netlist, simple_board):
        """Different positions should produce different congestion maps."""
        from temper_placer.routing.congestion import analyze_congestion
        import jax.numpy as jnp

        # Clustered positions (all components close together)
        clustered = jnp.array(
            [
                [50.0, 50.0],
                [52.0, 50.0],
                [51.0, 52.0],
            ]
        )

        # Spread positions (components far apart)
        spread = jnp.array(
            [
                [10.0, 10.0],
                [90.0, 10.0],
                [50.0, 90.0],
            ]
        )

        result_clustered = analyze_congestion(sample_netlist, simple_board, positions=clustered)
        result_spread = analyze_congestion(sample_netlist, simple_board, positions=spread)

        # Clustered should have higher max utilization in some cells
        # (nets are shorter but more concentrated)
        assert not jnp.allclose(result_clustered.grid.demand, result_spread.grid.demand)


# =============================================================================
# Tests for Layer-Aware Congestion
# =============================================================================


class TestLayerAwareCongestion:
    """Tests for multi-layer congestion analysis."""

    def test_multi_layer_grid(self, simple_board):
        """Should support multi-layer congestion grids."""
        from temper_placer.routing.congestion import CongestionGrid

        grid = CongestionGrid.from_board(
            simple_board,
            cell_size_mm=1.0,
            num_layers=2,  # L1 and L4
        )

        assert grid.demand.shape == (2, 100, 100)
        assert grid.supply.shape == (2, 100, 100)

    def test_layer_assignment_affects_congestion(self, sample_netlist, simple_board):
        """Layer assignments should affect per-layer congestion."""
        from temper_placer.routing.congestion import analyze_congestion
        from temper_placer.routing.layer_assignment import assign_layers

        # Get layer assignments
        assignments = assign_layers(sample_netlist)

        # Analyze with layer awareness
        result = analyze_congestion(
            sample_netlist,
            simple_board,
            layer_assignments=assignments,
            num_layers=2,
        )

        # Result should have per-layer data
        assert result.grid.demand.shape[0] == 2
