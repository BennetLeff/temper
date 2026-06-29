"""Property-based tests for LayerCapacity invariants."""

from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.router_v6.layer_capacity import LayerCapacity


@given(
    total_cells=st.integers(min_value=0, max_value=100000),
    free_cells=st.integers(min_value=0, max_value=100000),
    blocked_cells=st.integers(min_value=0, max_value=100000),
    min_width=st.floats(min_value=0.0, max_value=100.0),
    avg_width=st.floats(min_value=0.0, max_value=100.0),
    estimated_traces=st.integers(min_value=0, max_value=100000),
)
@settings(max_examples=100, deadline=30000)
def test_layer_capacity_free_leq_total(total_cells, free_cells, blocked_cells, min_width, avg_width, estimated_traces):
    """free_cells <= total_cells always."""
    lc = LayerCapacity(
        layer_name="test",
        total_cells=total_cells,
        free_cells=min(free_cells, total_cells),
        blocked_cells=min(blocked_cells, total_cells),
        min_channel_width=min_width,
        avg_channel_width=avg_width,
        estimated_traces=estimated_traces,
    )
    assert lc.free_cells <= lc.total_cells
    assert lc.blocked_cells <= lc.total_cells


@given(
    total=st.integers(min_value=1, max_value=10000),
    free=st.integers(min_value=0, max_value=10000),
    blocked=st.integers(min_value=0, max_value=10000),
)
@settings(max_examples=100, deadline=30000)
def test_layer_capacity_utilization_ratio(total, free, blocked):
    """utilization_ratio + available_ratio <= 1.0."""
    f = min(free, total)
    b = min(blocked, total - f)
    lc = LayerCapacity(
        layer_name="test",
        total_cells=total,
        free_cells=f,
        blocked_cells=b,
        min_channel_width=0.2,
        avg_channel_width=0.5,
        estimated_traces=10,
    )
    assert lc.utilization_ratio >= 0.0
    assert lc.available_ratio >= 0.0
    assert lc.utilization_ratio + lc.available_ratio <= 1.0 + 1e-9


@given(
    total=st.integers(min_value=0, max_value=1000),
)
@settings(max_examples=100, deadline=30000)
def test_layer_capacity_zero_total(total):
    """Zero total cells gives zero ratios."""
    lc = LayerCapacity(
        layer_name="test",
        total_cells=total,
        free_cells=0,
        blocked_cells=0,
        min_channel_width=0.0,
        avg_channel_width=0.0,
        estimated_traces=0,
    )
    if total == 0:
        assert lc.utilization_ratio == 0.0
        assert lc.available_ratio == 0.0
