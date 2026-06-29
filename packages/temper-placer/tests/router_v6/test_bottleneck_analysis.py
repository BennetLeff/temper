"""
Tests for Router V6 Stage 2.8: Identify Bottlenecks

Part of temper-pox8
"""


from temper_placer.router_v6.bottleneck_analysis import (
    Bottleneck,
    BottleneckAnalysis,
    BottleneckSeverity,
    identify_bottlenecks,
)
from temper_placer.router_v6.layer_capacity import LayerCapacity
from temper_placer.router_v6.routing_demand import RoutingDemand


def test_identify_bottlenecks_no_congestion():
    """Test bottleneck detection with ample capacity."""
    capacities = {
        "F.Cu": LayerCapacity(
            layer_name="F.Cu",
            total_cells=10000,
            free_cells=8000,
            blocked_cells=2000,
            min_channel_width=1.0,
            avg_channel_width=5.0,
            estimated_traces=100,
        ),
    }

    demand = RoutingDemand(
        total_nets=50,
        routable_nets=40,
        total_pins=200,
        signal_nets=35,
        power_nets=5,
        diff_pair_nets=0,
        avg_pins_per_net=5.0,
        max_pins_per_net=10,
    )

    analysis = identify_bottlenecks(capacities, demand)

    assert len(analysis.bottlenecks) == 1
    assert not analysis.has_critical_bottlenecks


def test_identify_bottlenecks_critical():
    """Test bottleneck detection with insufficient capacity."""
    capacities = {
        "F.Cu": LayerCapacity(
            layer_name="F.Cu",
            total_cells=1000,
            free_cells=500,
            blocked_cells=500,
            min_channel_width=0.5,
            avg_channel_width=1.0,
            estimated_traces=10,  # Very low capacity
        ),
    }

    demand = RoutingDemand(
        total_nets=200,
        routable_nets=180,
        total_pins=1000,
        signal_nets=170,
        power_nets=10,
        diff_pair_nets=0,
        avg_pins_per_net=5.0,
        max_pins_per_net=20,
    )

    analysis = identify_bottlenecks(capacities, demand)

    # Should detect critical bottleneck
    assert analysis.has_critical_bottlenecks
    assert analysis.worst_bottleneck is not None
    assert analysis.worst_bottleneck.severity in [
        BottleneckSeverity.CRITICAL,
        BottleneckSeverity.HIGH,
    ]


def test_bottleneck_severity_classification():
    """Test severity classification logic."""
    # No bottleneck (capacity >> demand)
    bottleneck_none = Bottleneck(
        layer_name="F.Cu",
        severity=BottleneckSeverity.NONE,
        capacity=100,
        demand=20,
        utilization=0.2,
    )
    assert not bottleneck_none.is_critical
    assert bottleneck_none.margin == 80

    # Critical bottleneck (capacity << demand)
    bottleneck_critical = Bottleneck(
        layer_name="B.Cu",
        severity=BottleneckSeverity.CRITICAL,
        capacity=10,
        demand=100,
        utilization=10.0,
    )
    assert bottleneck_critical.is_critical
    assert bottleneck_critical.margin == -90


def test_bottleneck_analysis_dataclass():
    """Test BottleneckAnalysis dataclass."""
    bottlenecks = [
        Bottleneck("F.Cu", BottleneckSeverity.LOW, 100, 50, 0.5),
        Bottleneck("B.Cu", BottleneckSeverity.HIGH, 20, 30, 1.5),
    ]

    analysis = BottleneckAnalysis(
        bottlenecks=bottlenecks,
        total_capacity=120,
        total_demand=80,
    )

    assert len(analysis.bottlenecks) == 2
    assert not analysis.has_critical_bottlenecks

    # Worst bottleneck should be B.Cu (highest utilization)
    worst = analysis.worst_bottleneck
    assert worst is not None
    assert worst.layer_name == "B.Cu"


def test_identify_bottlenecks_multiple_layers():
    """Test bottleneck detection with multiple layers."""
    capacities = {
        "F.Cu": LayerCapacity(
            "F.Cu", 10000, 8000, 2000, 1.0, 5.0, 80
        ),
        "In1.Cu": LayerCapacity(
            "In1.Cu", 10000, 9000, 1000, 2.0, 6.0, 100
        ),
        "B.Cu": LayerCapacity(
            "B.Cu", 10000, 7000, 3000, 1.0, 4.0, 60
        ),
    }

    demand = RoutingDemand(
        total_nets=150,
        routable_nets=120,
        total_pins=600,
        signal_nets=100,
        power_nets=20,
        diff_pair_nets=0,
        avg_pins_per_net=5.0,
        max_pins_per_net=15,
    )

    analysis = identify_bottlenecks(capacities, demand)

    assert len(analysis.bottlenecks) == 3
    assert analysis.total_capacity == 240


def test_bottleneck_empty_design():
    """Test bottleneck detection with empty design."""
    analysis = identify_bottlenecks({}, RoutingDemand(
        total_nets=0,
        routable_nets=0,
        total_pins=0,
        signal_nets=0,
        power_nets=0,
        diff_pair_nets=0,
        avg_pins_per_net=0.0,
        max_pins_per_net=0,
    ))

    assert len(analysis.bottlenecks) == 0
    assert not analysis.has_critical_bottlenecks
    assert analysis.worst_bottleneck is None
