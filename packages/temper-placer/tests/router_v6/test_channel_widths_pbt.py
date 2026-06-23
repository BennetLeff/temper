"""Property-based tests for ChannelWidths invariants."""

from hypothesis import given, settings, strategies as st

from temper_placer.router_v6.channel_widths import ChannelWidths


@given(
    min_width=st.floats(min_value=0.0, max_value=100.0),
    max_width=st.floats(min_value=0.0, max_value=100.0),
    avg_width=st.floats(min_value=0.0, max_value=100.0),
)
@settings(max_examples=100, deadline=30000)
def test_channel_widths_min_leq_max(min_width, max_width, avg_width):
    """min_width <= max_width."""
    cw = ChannelWidths(
        layer_name="test",
        node_widths={},
        edge_widths={},
        min_width=min(min_width, max_width),
        max_width=max(max_width, min_width),
        avg_width=max(min_width, min(max_width, avg_width)),
    )
    assert cw.min_width <= cw.max_width


@given(
    min_w=st.floats(min_value=0.0, max_value=20.0),
    max_w=st.floats(min_value=0.0, max_value=20.0),
)
@settings(max_examples=100, deadline=30000)
def test_channel_widths_bottleneck_equals_min(min_w, max_w):
    """bottleneck_width equals min_width."""
    cw = ChannelWidths(
        layer_name="test",
        node_widths={},
        edge_widths={},
        min_width=min_w,
        max_width=max(max_w, min_w),
        avg_width=(min_w + max(max_w, min_w)) / 2,
    )
    assert cw.bottleneck_width == min_w


@given(
    node_key=st.tuples(st.floats(min_value=-100, max_value=100), st.floats(min_value=-100, max_value=100)),
    width=st.floats(min_value=0.0, max_value=10.0),
)
@settings(max_examples=100, deadline=30000)
def test_channel_widths_get_node_width(node_key, width):
    """get_node_width returns stored width or 0.0 for missing."""
    cw = ChannelWidths(
        layer_name="test",
        node_widths={node_key: width},
        edge_widths={},
        min_width=width,
        max_width=width,
        avg_width=width,
    )
    assert cw.get_node_width(node_key) == width
    assert cw.get_node_width((999.0, 999.0)) == 0.0


@given(
    widths=st.lists(st.floats(min_value=0.0, max_value=10.0), min_size=1, max_size=50),
)
@settings(max_examples=100, deadline=30000)
def test_channel_widths_statistics(widths):
    """min <= avg <= max for a set of widths (within float tolerance)."""
    min_w = min(widths)
    max_w = max(widths)
    avg_w = sum(widths) / len(widths)
    cw = ChannelWidths(
        layer_name="test",
        node_widths={},
        edge_widths={},
        min_width=min_w,
        max_width=max_w,
        avg_width=avg_w,
    )
    assert cw.min_width <= cw.max_width
    assert cw.min_width <= cw.avg_width + 1e-12
    assert cw.avg_width <= cw.max_width + 1e-12
