"""
Tests for Router V6 Stage 2.6: Calculate Per-Layer Capacity

Part of temper-cmzd
"""

import pytest
from shapely.geometry import MultiPolygon, box

from temper_placer.router_v6.channel_skeleton import extract_channel_skeleton
from temper_placer.router_v6.channel_widths import compute_channel_widths
from temper_placer.router_v6.layer_capacity import LayerCapacity, calculate_layer_capacity
from temper_placer.router_v6.occupancy_grid import build_occupancy_grid
from temper_placer.router_v6.routing_space import RoutingSpace


def test_calculate_capacity_basic():
    """Test basic capacity calculation."""
    routing_space = RoutingSpace(
        layer_name="F.Cu",
        available_area=MultiPolygon([box(0, 0, 50, 50)]),
        total_area=2500.0,
        obstacle_area=0.0,
        routing_area=2500.0,
    )

    grid = build_occupancy_grid(routing_space, cell_size=1.0)
    skeleton = extract_channel_skeleton(routing_space)
    widths = compute_channel_widths(routing_space, skeleton)
    
    capacity = calculate_layer_capacity(grid, widths)

    assert capacity.layer_name == "F.Cu"
    assert capacity.total_cells > 0
    assert capacity.free_cells > 0


def test_capacity_ratios():
    """Test utilization and available ratios."""
    routing_space = RoutingSpace(
        layer_name="F.Cu",
        available_area=MultiPolygon([box(0, 0, 30, 30)]),
        total_area=900.0,
        obstacle_area=0.0,
        routing_area=900.0,
    )

    grid = build_occupancy_grid(routing_space, cell_size=1.0)
    skeleton = extract_channel_skeleton(routing_space)
    widths = compute_channel_widths(routing_space, skeleton)
    
    capacity = calculate_layer_capacity(grid, widths)

    # Ratios should sum to ~1.0
    assert 0.0 <= capacity.utilization_ratio <= 1.0
    assert 0.0 <= capacity.available_ratio <= 1.0
    assert abs((capacity.utilization_ratio + capacity.available_ratio) - 1.0) < 0.01


def test_capacity_trace_estimation():
    """Test trace capacity estimation."""
    routing_space = RoutingSpace(
        layer_name="F.Cu",
        available_area=MultiPolygon([box(0, 0, 100, 100)]),
        total_area=10000.0,
        obstacle_area=0.0,
        routing_area=10000.0,
    )

    grid = build_occupancy_grid(routing_space, cell_size=0.5)
    skeleton = extract_channel_skeleton(routing_space)
    widths = compute_channel_widths(routing_space, skeleton)
    
    capacity = calculate_layer_capacity(grid, widths)

    # Should estimate some trace capacity
    assert capacity.estimated_traces >= 0


def test_capacity_dataclass():
    """Test LayerCapacity dataclass."""
    capacity = LayerCapacity(
        layer_name="F.Cu",
        total_cells=10000,
        free_cells=7000,
        blocked_cells=3000,
        min_channel_width=1.0,
        avg_channel_width=5.0,
        estimated_traces=50,
    )

    assert capacity.utilization_ratio == pytest.approx(0.3, abs=0.01)
    assert capacity.available_ratio == pytest.approx(0.7, abs=0.01)


def test_capacity_with_constraints():
    """Test capacity with different trace width constraints."""
    routing_space = RoutingSpace(
        layer_name="F.Cu",
        available_area=MultiPolygon([box(0, 0, 40, 40)]),
        total_area=1600.0,
        obstacle_area=0.0,
        routing_area=1600.0,
    )

    grid = build_occupancy_grid(routing_space, cell_size=1.0)
    skeleton = extract_channel_skeleton(routing_space)
    widths = compute_channel_widths(routing_space, skeleton)
    
    # Wide traces/clearance
    capacity_wide = calculate_layer_capacity(
        grid, widths, min_trace_width=0.5, min_clearance=0.5
    )
    
    # Narrow traces/clearance  
    capacity_narrow = calculate_layer_capacity(
        grid, widths, min_trace_width=0.1, min_clearance=0.1
    )

    # Narrower constraints should allow more traces
    assert capacity_narrow.estimated_traces >= capacity_wide.estimated_traces
