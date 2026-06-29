"""Property-based tests for RoutingSpace invariants."""

from hypothesis import given, settings
from hypothesis import strategies as st
from shapely.geometry import MultiPolygon, box

from temper_placer.router_v6.routing_space import RoutingSpace


@given(
    routing_area=st.floats(min_value=0.0, max_value=10000.0),
    total_area=st.floats(min_value=0.1, max_value=10000.0),
    obstacle_area=st.floats(min_value=0.0, max_value=10000.0),
)
@settings(max_examples=100, deadline=30000)
def test_routing_space_area_non_negative(routing_area, total_area, obstacle_area):
    """Routing area and obstacle area are non-negative."""
    poly = box(0, 0, total_area ** 0.5, total_area ** 0.5)
    rs = RoutingSpace(
        layer_name="test",
        available_area=MultiPolygon([poly]),
        total_area=total_area,
        obstacle_area=obstacle_area,
        routing_area=routing_area,
    )
    assert rs.routing_area >= 0
    assert rs.obstacle_area >= 0
    assert rs.total_area > 0


@given(
    total=st.floats(min_value=1.0, max_value=10000.0),
    obs=st.floats(min_value=0.0, max_value=10000.0),
)
@settings(max_examples=100, deadline=30000)
def test_routing_space_utilization_bounded(total, obs):
    """utilization_ratio is in [0, 1]."""
    rs = RoutingSpace(
        layer_name="test",
        available_area=MultiPolygon([box(0, 0, 1, 1)]),
        total_area=total,
        obstacle_area=min(obs, total),
        routing_area=max(0, total - min(obs, total)),
    )
    assert 0.0 <= rs.utilization_ratio <= 1.0
    assert 0.0 <= rs.available_ratio <= 1.0
    # Allow float tolerance
    assert abs(rs.utilization_ratio + rs.available_ratio - 1.0) < 1e-6 or total == 0


@given(
    total=st.floats(min_value=0.0, max_value=100.0),
)
@settings(max_examples=100, deadline=30000)
def test_routing_space_zero_total_area(total):
    """Zero total area gives zero ratios."""
    rs = RoutingSpace(
        layer_name="test",
        available_area=MultiPolygon(),
        total_area=total,
        obstacle_area=0.0,
        routing_area=0.0,
    )
    if total == 0:
        assert rs.utilization_ratio == 0.0
        assert rs.available_ratio == 0.0
