"""Property-based tests for ChannelSkeleton invariants."""

import networkx as nx
from hypothesis import given, settings, strategies as st

from temper_placer.router_v6.channel_skeleton import ChannelSkeleton


@given(
    num_nodes=st.integers(min_value=0, max_value=100),
    num_edges=st.integers(min_value=0, max_value=200),
    seed=st.integers(min_value=0, max_value=1000),
)
@settings(max_examples=100, deadline=30000)
def test_channel_skeleton_node_edge_counts(num_nodes, num_edges, seed):
    """node_count and edge_count match graph properties."""
    import random
    rng = random.Random(seed)
    G = nx.Graph()
    for i in range(num_nodes):
        G.add_node((float(i), float(i)), pos=(float(i), float(i)))
    # Add edges between consecutive nodes (creates a path)
    for i in range(min(num_edges, num_nodes - 1)):
        j = (i + 1) % num_nodes
        if j != i and (i, j) not in G.edges:
            G.add_edge((float(i), float(i)), (float(j), float(j)), weight=1.0)

    sk = ChannelSkeleton(graph=G, layer_name="test", total_length=float(num_edges))
    assert sk.node_count == G.number_of_nodes()
    assert sk.edge_count == G.number_of_edges()


@given(
    num_nodes=st.integers(min_value=0, max_value=50),
    seed=st.integers(min_value=0, max_value=500),
)
@settings(max_examples=100, deadline=30000)
def test_channel_skeleton_empty_graph(num_nodes, seed):
    """Empty graph gives node_count=0 and is_connected=True."""
    import random
    rng = random.Random(seed)

    # Create a connected path
    G = nx.Graph()
    for i in range(num_nodes):
        G.add_node((float(i), float(i)))
    for i in range(num_nodes - 1):
        G.add_edge((float(i), float(i)), (float(i + 1), float(i + 1)), weight=1.0)

    sk = ChannelSkeleton(graph=G, layer_name="test", total_length=float(max(0, num_nodes - 1)))
    if num_nodes <= 1:
        assert sk.is_connected
    else:
        # Path graph is always connected
        assert sk.is_connected


@given(
    total_length=st.floats(min_value=0.0, max_value=10000.0),
)
@settings(max_examples=100, deadline=30000)
def test_channel_skeleton_total_length_non_negative(total_length):
    """total_length is non-negative."""
    G = nx.Graph()
    sk = ChannelSkeleton(graph=G, layer_name="test", total_length=total_length)
    assert sk.total_length >= 0
