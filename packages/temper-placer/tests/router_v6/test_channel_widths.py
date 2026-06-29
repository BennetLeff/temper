"""
Tests for Router V6 Stage 2.4: Compute Channel Widths

Part of temper-7qu7
"""

from shapely.geometry import MultiPolygon, box

from temper_placer.router_v6.channel_skeleton import extract_channel_skeleton
from temper_placer.router_v6.channel_widths import ChannelWidths, compute_channel_widths
from temper_placer.router_v6.routing_space import RoutingSpace


def test_compute_widths_simple_corridor():
    """Test width computation in a simple rectangular corridor."""
    # 20x10mm corridor
    routing_space = RoutingSpace(
        layer_name="F.Cu",
        available_area=MultiPolygon([box(0, 0, 20, 10)]),
        total_area=200.0,
        obstacle_area=0.0,
        routing_area=200.0,
    )

    skeleton = extract_channel_skeleton(routing_space)
    widths = compute_channel_widths(routing_space, skeleton)

    assert widths.layer_name == "F.Cu"
    assert len(widths.node_widths) > 0
    assert widths.min_width > 0.0
    assert widths.max_width >= widths.min_width
    assert widths.avg_width > 0.0


def test_widths_bottleneck_property():
    """Test bottleneck width property."""
    routing_space = RoutingSpace(
        layer_name="F.Cu",
        available_area=MultiPolygon([box(0, 0, 50, 50)]),
        total_area=2500.0,
        obstacle_area=0.0,
        routing_area=2500.0,
    )

    skeleton = extract_channel_skeleton(routing_space)
    widths = compute_channel_widths(routing_space, skeleton)

    # Bottleneck should equal min_width
    assert widths.bottleneck_width == widths.min_width


def test_widths_empty_space():
    """Test width computation with no routing space."""
    routing_space = RoutingSpace(
        layer_name="F.Cu",
        available_area=MultiPolygon(),  # Empty
        total_area=100.0,
        obstacle_area=100.0,
        routing_area=0.0,
    )

    skeleton = extract_channel_skeleton(routing_space)
    widths = compute_channel_widths(routing_space, skeleton)

    assert widths.min_width == 0.0
    assert widths.max_width == 0.0
    assert widths.avg_width == 0.0
    assert len(widths.node_widths) == 0


def test_widths_dataclass_properties():
    """Test ChannelWidths dataclass."""
    widths = ChannelWidths(
        layer_name="F.Cu",
        node_widths={(0.0, 0.0): 5.0, (10.0, 10.0): 3.0},
        edge_widths={((0.0, 0.0), (10.0, 10.0)): 3.0},
        min_width=3.0,
        max_width=5.0,
        avg_width=4.0,
    )

    assert widths.bottleneck_width == 3.0
    assert widths.get_node_width((0.0, 0.0)) == 5.0
    assert widths.get_node_width((10.0, 10.0)) == 3.0
    assert widths.get_node_width((99.0, 99.0)) == 0.0  # Not in dict


def test_widths_statistics():
    """Test that width statistics are computed correctly."""
    routing_space = RoutingSpace(
        layer_name="F.Cu",
        available_area=MultiPolygon([box(0, 0, 100, 50)]),
        total_area=5000.0,
        obstacle_area=0.0,
        routing_area=5000.0,
    )

    skeleton = extract_channel_skeleton(routing_space)
    widths = compute_channel_widths(routing_space, skeleton)

    # All statistics should be positive
    assert widths.min_width > 0.0
    assert widths.max_width > 0.0
    assert widths.avg_width > 0.0

    # Average should be between min and max
    assert widths.min_width <= widths.avg_width <= widths.max_width


def test_widths_with_sampling():
    """Test width computation with different sample distances."""
    routing_space = RoutingSpace(
        layer_name="F.Cu",
        available_area=MultiPolygon([box(0, 0, 30, 20)]),
        total_area=600.0,
        obstacle_area=0.0,
        routing_area=600.0,
    )

    skeleton = extract_channel_skeleton(routing_space)

    # Fine sampling
    widths_fine = compute_channel_widths(routing_space, skeleton, sample_distance=0.5)

    # Coarse sampling
    widths_coarse = compute_channel_widths(routing_space, skeleton, sample_distance=5.0)

    # Both should produce valid results
    assert widths_fine.min_width > 0.0
    assert widths_coarse.min_width > 0.0

    # Fine sampling may find narrower bottlenecks
    assert widths_fine.min_width <= widths_coarse.min_width + 1.0  # Allow small tolerance


def test_widths_node_lookup():
    """Test get_node_width method."""
    routing_space = RoutingSpace(
        layer_name="F.Cu",
        available_area=MultiPolygon([box(0, 0, 40, 40)]),
        total_area=1600.0,
        obstacle_area=0.0,
        routing_area=1600.0,
    )

    skeleton = extract_channel_skeleton(routing_space)
    widths = compute_channel_widths(routing_space, skeleton)

    # Should be able to look up width for actual nodes
    for node in skeleton.graph.nodes():
        width = widths.get_node_width(node)
        assert width >= 0.0  # Width should be non-negative
