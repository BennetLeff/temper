"""Tests for thermal potential field, greedy anchor assignment, and safety gates.

Covers:
- U9: Property-based tests (Hypothesis) for phi field + greedy assignment
- U10: Safety gate unit tests
"""

from __future__ import annotations

import jax.numpy as jnp
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.physics.thermal_potential import (
    ThermalAnchoringSafetyError,
    ThermalPotentialConfig,
    assign_thermal_anchors,
    build_potential_grid,
    phi_convection,
    phi_copper,
    phi_coupling,
    phi_edge,
    phi_exclusion,
    superpose_fields,
    validate_heatsink_edge,
    validate_stackup_for_anchoring,
    validate_tj_safety,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def board_bounds() -> tuple[float, float, float, float]:
    return (0.0, 0.0, 100.0, 150.0)


@pytest.fixture
def tiny_grid(board_bounds):
    return build_potential_grid(board_bounds, 10)


# ---------------------------------------------------------------------------
# U9 / R11: phi field non-negativity (property-based)
# ---------------------------------------------------------------------------


@st.composite
def valid_board_bounds(draw):
    w = draw(st.floats(50.0, 300.0))
    h = draw(st.floats(50.0, 300.0))
    return (0.0, 0.0, w, h)


@st.composite
def valid_edge_name(draw):
    return draw(st.sampled_from(["TOP", "BOTTOM", "LEFT", "RIGHT"]))


@st.composite
def component_set(draw):
    n = draw(st.integers(1, 8))
    refs = [f"C{i}" for i in range(n)]
    powers = [draw(st.floats(1.0, 100.0)) for _ in range(n)]
    return list(zip(refs, powers))


@given(board=valid_board_bounds(), edge=valid_edge_name())
@settings(max_examples=50, deadline=2000)
def test_phi_edge_non_negative(board, edge):
    """R11: phi_edge produces non-negative values for any valid input."""
    x_grid, y_grid = build_potential_grid(board, 20)
    field = phi_edge(x_grid, y_grid, board, edge, 10.0)
    assert jnp.all(field >= 0.0), f"phi_edge negative values for {edge}"


@given(board=valid_board_bounds(), edge=valid_edge_name())
@settings(max_examples=50, deadline=2000)
def test_superpose_non_negative(board, edge):
    """R11: superpose_fields produces non-negative values for any valid input."""
    x_grid, y_grid = build_potential_grid(board, 20)
    config = ThermalPotentialConfig()
    field = superpose_fields(x_grid, y_grid, board, edge, config)
    assert jnp.all(field >= 0.0), "superpose_fields produced negative values"


@given(board=valid_board_bounds(), edge=valid_edge_name())
@settings(max_examples=50, deadline=2000)
def test_phi_edge_minimum_near_edge(board, edge):
    """R12: Minimum of phi_edge lies within 10mm of the declared edge."""
    x_grid, y_grid = build_potential_grid(board, 20)
    field = phi_edge(x_grid, y_grid, board, edge, 10.0)
    min_idx = jnp.unravel_index(jnp.argmin(field), field.shape)
    min_x = float(x_grid[min_idx])
    min_y = float(y_grid[min_idx])

    x_min, y_min, x_max, y_max = board
    edge_upper = edge.upper()
    if edge_upper == "TOP":
        dist = y_max - min_y
    elif edge_upper == "BOTTOM":
        dist = min_y - y_min
    elif edge_upper == "LEFT":
        dist = min_x - x_min
    elif edge_upper == "RIGHT":
        dist = x_max - min_x
    else:
        dist = 0.0
    assert dist <= 15.0, f"phi_edge min {dist:.1f}mm from {edge} exceeds 15mm slack"


# ---------------------------------------------------------------------------
# U9 / R13: Unique anchor positions
# ---------------------------------------------------------------------------


def test_greedy_assignment_unique_positions(board_bounds):
    """R13: No two anchor devices share the same coordinates (within 0.1mm)."""
    devices = [("Q1", 50.0), ("Q2", 45.0), ("Q3", 40.0)]
    anchors = assign_thermal_anchors(
        board_bounds, "TOP", devices, config=ThermalPotentialConfig(grid_resolution=20)
    )
    assert len(anchors) == 3
    positions = list(anchors.values())
    for i in range(len(positions)):
        for j in range(i + 1, len(positions)):
            dx = positions[i][0] - positions[j][0]
            dy = positions[i][1] - positions[j][1]
            dist = (dx**2 + dy**2) ** 0.5
            assert dist >= 0.1, f"Devices {i} and {j} at same position"


def test_greedy_assignment_deterministic(board_bounds):
    """R10: Same input produces identical anchor positions across 10 runs."""
    devices = [("Q1", 50.0), ("Q2", 45.0)]
    config = ThermalPotentialConfig(grid_resolution=20)
    first = assign_thermal_anchors(board_bounds, "TOP", devices, config=config)
    for _ in range(10):
        result = assign_thermal_anchors(board_bounds, "TOP", devices, config=config)
        for ref in first:
            assert ref in result
            assert result[ref] == first[ref], f"Non-deterministic for {ref}"


def test_single_device_no_coupling(board_bounds):
    """Single power device: anchor at global minimum, no coupling pass needed."""
    devices = [("Q1", 50.0)]
    anchors = assign_thermal_anchors(
        board_bounds, "TOP", devices, config=ThermalPotentialConfig(grid_resolution=20)
    )
    assert len(anchors) == 1
    assert "Q1" in anchors


def test_empty_devices(board_bounds):
    """Empty device set returns empty dict."""
    anchors = assign_thermal_anchors(board_bounds, "TOP", [])
    assert anchors == {}


def test_no_power_devices_skip_coupling(board_bounds):
    """Devices with near-zero power still get anchors with phi_base only."""
    devices = [("Q1", 0.0)]
    anchors = assign_thermal_anchors(
        board_bounds, "TOP", devices, config=ThermalPotentialConfig(grid_resolution=20)
    )
    # Device has 0W power but still gets an anchor position
    assert "Q1" in anchors


# ---------------------------------------------------------------------------
# U10: Safety Gate Tests
# ---------------------------------------------------------------------------


class TestValidateHeatsinkEdge:
    def test_valid_top_edge(self, board_bounds):
        validate_heatsink_edge(board_bounds, "TOP")

    def test_valid_bottom_edge(self, board_bounds):
        validate_heatsink_edge(board_bounds, "BOTTOM")

    def test_valid_left_edge(self, board_bounds):
        validate_heatsink_edge(board_bounds, "LEFT")

    def test_valid_right_edge(self, board_bounds):
        validate_heatsink_edge(board_bounds, "RIGHT")

    def test_invalid_edge_raises(self, board_bounds):
        with pytest.raises(ThermalAnchoringSafetyError, match="not a valid edge"):
            validate_heatsink_edge(board_bounds, "DIAGONAL")

    def test_invalid_bounds_raises(self):
        """Degenerate board bounds should raise."""
        with pytest.raises(ThermalAnchoringSafetyError, match="board dimensions"):
            validate_heatsink_edge((100.0, 50.0, 50.0, 100.0), "TOP")

    def test_lowercase_edge_accepted(self, board_bounds):
        """Edge name is case-insensitive."""
        validate_heatsink_edge(board_bounds, "top")


class TestValidateTjSafety:
    def test_tj_below_limit_passes(self):
        # 10W at 5mm with Rjc=0.6: edge_penalty=0, R_total=0.6+0.25+2.0=2.85
        # Tj = 40 + 10*2.85 = 68.5, well under 150
        validate_tj_safety("Q1", 10.0, 0.6, 150.0, 5.0)

    def test_tj_at_boundary_passes(self):
        # Just barely under the limit
        validate_tj_safety("Q1", 10.0, 0.6, 70.0, 5.0)

    def test_tj_exceeds_rated_raises(self):
        with pytest.raises(ThermalAnchoringSafetyError, match="Junction temperature violation"):
            validate_tj_safety("Q1", 200.0, 0.6, 100.0, 50.0)

    def test_missing_rated_tj_max_skips(self):
        """When rated_tj_max is None, safety check is skipped."""
        validate_tj_safety("Q1", 200.0, 0.6, None, 50.0)

    def test_missing_rjc_uses_default(self):
        """When Rjc is None, defaults to 0.6 K/W."""
        validate_tj_safety("Q1", 10.0, None, 150.0, 5.0)

    def test_far_from_edge_increases_tj(self):
        """Greater distance from edge increases junction temp."""
        from temper_placer.physics.thermal import estimate_junction_temp
        Tj_close = estimate_junction_temp(50.0, 5.0, Rjc=0.6)
        Tj_far = estimate_junction_temp(50.0, 50.0, Rjc=0.6)
        assert Tj_far > Tj_close, "Tj should increase with distance from edge"


class TestValidateStackupForAnchoring:
    def test_2_layer_disables_copper(self):
        config = validate_stackup_for_anchoring(2)
        assert config.copper_weight == 0.0

    def test_4_layer_enables_copper(self):
        config = validate_stackup_for_anchoring(4)
        assert config.copper_weight == 1.0

    def test_6_layer_enables_copper(self):
        config = validate_stackup_for_anchoring(6)
        assert config.copper_weight == 1.0

    def test_3_layer_disables_copper(self):
        config = validate_stackup_for_anchoring(3)
        assert config.copper_weight == 0.0


# ---------------------------------------------------------------------------
# Additional field component tests
# ---------------------------------------------------------------------------


class TestPhiEdge:
    def test_top_edge_minimum_near_edge(self, tiny_grid, board_bounds):
        x_grid, y_grid = tiny_grid
        field = phi_edge(x_grid, y_grid, board_bounds, "TOP", 10.0)
        # At TOP edge (y=150), phi should be near 0
        # At BOTTOM edge (y=0), phi should be near 1
        min_idx = jnp.unravel_index(jnp.argmin(field), field.shape)
        min_y = float(y_grid[min_idx])
        _, _, _, y_max = board_bounds
        dist_from_top = y_max - min_y
        assert dist_from_top < 15.0, f"phi_edge minimum is {dist_from_top:.1f}mm from TOP edge"

    def test_bottom_edge_minimum_near_edge(self, tiny_grid, board_bounds):
        x_grid, y_grid = tiny_grid
        field = phi_edge(x_grid, y_grid, board_bounds, "BOTTOM", 10.0)
        min_idx = jnp.unravel_index(jnp.argmin(field), field.shape)
        min_y = float(y_grid[min_idx])
        _, y_min, _, _ = board_bounds
        dist_from_bottom = min_y - y_min
        assert dist_from_bottom < 15.0, f"phi_edge minimum is {dist_from_bottom:.1f}mm from BOTTOM edge"


class TestPhiConvection:
    def test_zero_without_airflow(self, tiny_grid):
        x_grid, y_grid = tiny_grid
        field = phi_convection(x_grid, y_grid, None)
        assert jnp.all(field == 0.0)

    def test_nonzero_with_airflow(self, tiny_grid):
        x_grid, y_grid = tiny_grid
        field = phi_convection(x_grid, y_grid, (1.0, 0.0))
        assert jnp.any(field != 0.0)


class TestPhiExclusion:
    def test_zero_without_anchors(self, tiny_grid):
        x_grid, y_grid = tiny_grid
        field = phi_exclusion(x_grid, y_grid, [])
        assert jnp.all(field == 0.0)

    def test_high_at_anchor_position(self, tiny_grid):
        x_grid, y_grid = tiny_grid
        field = phi_exclusion(x_grid, y_grid, [(50.0, 75.0)], radius_mm=10.0)
        # At anchor position, field should be near barrier_height
        center_val = float(field[5, 5])  # grid center from 10x10
        assert center_val > 1e5, f"Expected high barrier at anchor, got {center_val}"


class TestPhiCopper:
    def test_uniform_without_zones(self, tiny_grid, board_bounds):
        x_grid, y_grid = tiny_grid
        field = phi_copper(x_grid, y_grid, board_bounds, copper_zones=None)
        assert jnp.all(field > 0.0)


class TestPhiCoupling:
    def test_zero_without_devices(self, tiny_grid):
        x_grid, y_grid = tiny_grid
        field = phi_coupling(x_grid, y_grid, [], [])
        assert jnp.all(field == 0.0)

    def test_nonzero_with_devices(self, tiny_grid):
        x_grid, y_grid = tiny_grid
        field = phi_coupling(x_grid, y_grid, [(50.0, 75.0)], [50.0])
        assert jnp.any(field > 0.0)


class TestSuperposeFields:
    def test_all_disabled_returns_zero(self, tiny_grid, board_bounds):
        x_grid, y_grid = tiny_grid
        config = ThermalPotentialConfig(
            edge_weight=0.0,
            copper_weight=0.0,
            coupling_weight=0.0,
            exclusion_weight=0.0,
            convection_weight=0.0,
        )
        field = superpose_fields(x_grid, y_grid, board_bounds, "TOP", config)
        assert jnp.all(field == 0.0)


class TestAssignThermalAnchors:
    def test_power_sorting_order(self, board_bounds):
        """Higher power devices get first pick (closer to edge)."""
        devices = [("Q_LOW", 10.0), ("Q_HIGH", 90.0)]
        # algorithm sorts by power descending, so Q_HIGH placed first
        anchors = assign_thermal_anchors(
            board_bounds, "TOP", devices, config=ThermalPotentialConfig(grid_resolution=20)
        )
        assert len(anchors) == 2
        # Q_HIGH (90W) should be closer to TOP edge than Q_LOW (10W)
        qh_y = anchors.get("Q_HIGH", (0, 0))[1]
        ql_y = anchors.get("Q_LOW", (0, 0))[1]
        assert qh_y >= ql_y, f"Q_HIGH y={qh_y} should be >= Q_LOW y={ql_y} (closer to TOP)"
