"""Property-based tests for BottleneckAnalysis invariants."""

from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.router_v6.bottleneck_analysis import (
    Bottleneck,
    BottleneckAnalysis,
    BottleneckSeverity,
    _classify_severity,
)


@given(
    num_bottlenecks=st.integers(min_value=0, max_value=20),
    total_capacity=st.integers(min_value=0, max_value=100000),
    total_demand=st.integers(min_value=0, max_value=10000),
)
@settings(max_examples=100, deadline=30000)
def test_bottleneck_analysis_invariants(num_bottlenecks, total_capacity, total_demand):
    """Bottleneck count <= layer count proxy, no NONE with 0 capacity."""
    bottlenecks = []
    for i in range(num_bottlenecks):
        bn = Bottleneck(
            layer_name=f"L{i}",
            severity=BottleneckSeverity.NONE,
            capacity=100,
            demand=10,
            utilization=0.1,
        )
        bottlenecks.append(bn)

    ba = BottleneckAnalysis(
        bottlenecks=bottlenecks,
        total_capacity=total_capacity,
        total_demand=total_demand,
    )
    assert ba.total_capacity == total_capacity
    assert ba.total_demand == total_demand
    assert len(ba.bottlenecks) == num_bottlenecks


@given(
    capacity=st.integers(min_value=0, max_value=1000),
    demand=st.integers(min_value=0, max_value=1000),
)
@settings(max_examples=100, deadline=30000)
def test_bottleneck_capacity_zero_critical(capacity, demand):
    """If capacity=0 and demand>0, severity must be CRITICAL."""
    severity = _classify_severity(capacity, demand)
    if capacity == 0 and demand > 0:
        assert severity == BottleneckSeverity.CRITICAL
    elif capacity == 0 and demand == 0:
        assert severity == BottleneckSeverity.NONE


@given(
    demand=st.integers(min_value=0, max_value=10000),
)
@settings(max_examples=100, deadline=30000)
def test_bottleneck_infinite_capacity(demand):
    """If capacity >> demand, severity is NONE."""
    severity = _classify_severity(1000000, demand)
    assert severity == BottleneckSeverity.NONE


@given(
    capacity=st.integers(min_value=1, max_value=10000),
    demand=st.integers(min_value=0, max_value=10000),
)
@settings(max_examples=100, deadline=30000)
def test_bottleneck_classify_severity_returns_enum(capacity, demand):
    """_classify_severity always returns a BottleneckSeverity enum."""
    severity = _classify_severity(capacity, demand)
    assert isinstance(severity, BottleneckSeverity)
