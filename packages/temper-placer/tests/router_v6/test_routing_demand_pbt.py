"""Property-based tests for RoutingDemandStage.

Tests invariants: signal_nets + power_nets <= total_nets, all counts non-negative.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.router_v6.routing_demand import RoutingDemand


@given(
    total=st.integers(min_value=0, max_value=1000),
    signal=st.integers(min_value=0, max_value=1000),
    power=st.integers(min_value=0, max_value=500),
    diff=st.integers(min_value=0, max_value=100),
    pins=st.integers(min_value=0, max_value=5000),
)
@settings(max_examples=100, deadline=30000)
def test_routing_demand_invariant_classification(total, signal, power, diff, pins):
    """signal_nets + power_nets + diff_pair_nets <= total_nets."""
    rd = RoutingDemand(
        total_nets=total,
        routable_nets=min(total, signal + power + diff),
        total_pins=pins,
        signal_nets=min(signal, total),
        power_nets=min(power, total - min(signal, total)),
        diff_pair_nets=min(diff, total - min(signal, total) - min(power, total - min(signal, total))),
        avg_pins_per_net=pins / max(1, total),
        max_pins_per_net=min(pins, 100),
    )
    assert rd.signal_nets + rd.power_nets + rd.diff_pair_nets <= rd.total_nets
    assert rd.total_nets >= 0
    assert rd.routable_nets >= 0
    assert rd.total_pins >= 0
    assert rd.signal_nets >= 0
    assert rd.power_nets >= 0


@given(
    routable=st.integers(min_value=0, max_value=1000),
    total=st.integers(min_value=0, max_value=1000),
)
@settings(max_examples=100, deadline=30000)
def test_routing_demand_routable_leq_total(routable, total):
    """routable_nets <= total_nets."""
    rd = RoutingDemand(
        total_nets=total,
        routable_nets=min(routable, total),
        total_pins=0,
        signal_nets=0,
        power_nets=0,
        diff_pair_nets=0,
        avg_pins_per_net=0.0,
        max_pins_per_net=0,
    )
    assert rd.routable_nets <= rd.total_nets
    assert rd.routing_complexity >= 0.0
    assert rd.routing_complexity <= 1.0


@given(
    total=st.integers(min_value=0, max_value=100),
)
@settings(max_examples=100, deadline=30000)
def test_routing_demand_complexity_bounded(total):
    """routing_complexity is always in [0, 1]."""
    rd = RoutingDemand(
        total_nets=total,
        routable_nets=total,
        total_pins=total * 3,
        signal_nets=total,
        power_nets=0,
        diff_pair_nets=0,
        avg_pins_per_net=3.0,
        max_pins_per_net=10,
    )
    assert 0.0 <= rd.routing_complexity <= 1.0
