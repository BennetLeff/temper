
import networkx as nx
import pytest

from temper_placer.core.netlist import Net
from temper_placer.router_v6.channel_skeleton import ChannelSkeleton
from temper_placer.router_v6.constraint_model import ModelBuilder, NetChannelVar, ViaVar


@pytest.fixture
def mock_skeletons():
    # Layer 1 Skeleton
    g1 = nx.Graph()
    g1.add_node((0, 0))
    g1.add_node((10, 0))
    g1.add_edge((0, 0), (10, 0)) # Edge 1

    sk1 = ChannelSkeleton(graph=g1, layer_name="L1", total_length=10.0)

    # Layer 2 Skeleton (same nodes)
    g2 = nx.Graph()
    g2.add_node((0, 0))
    g2.add_node((10, 0))
    g2.add_edge((0, 0), (10, 0)) # Edge 1

    sk2 = ChannelSkeleton(graph=g2, layer_name="L2", total_length=10.0)

    return {"L1": sk1, "L2": sk2}

@pytest.fixture
def mock_nets():
    return [
        Net(name="NET1", pins=[]),
        Net(name="NET2", pins=[])
    ]

def test_model_variable_count(mock_skeletons, mock_nets):
    builder = ModelBuilder(mock_skeletons, mock_nets)
    model = builder.build()

    # Check variable count
    # Nets: 2
    # Layers: 2
    # Edges per layer: 1
    # Channel vars = 2 nets * 2 layers * 1 edge = 4

    # Nodes: 2 unique locations ((0,0), (10,0))
    # Via vars = 2 nets * 2 nodes = 4

    # Total = 8
    assert model.variable_count == 8

def test_channel_vars(mock_skeletons, mock_nets):
    builder = ModelBuilder(mock_skeletons, mock_nets)
    model = builder.build()

    # Check specific var existence
    # L1 edge 0
    # Net 0
    # ID depends on sorted nodes and index
    # Note: Edge enumeration order in nx is not guaranteed stable across runs unless added deterministically,
    # but in this simple case it's fine.

    # We can iterate model.variables and count types
    channel_vars = [v for v in model.variables if isinstance(v, NetChannelVar)]
    assert len(channel_vars) == 4

    via_vars = [v for v in model.variables if isinstance(v, ViaVar)]
    assert len(via_vars) == 4

def test_via_vars_unique_nodes(mock_skeletons, mock_nets):
    # Add a node only in L2
    mock_skeletons["L2"].graph.add_node((5, 5))

    builder = ModelBuilder(mock_skeletons, mock_nets)
    model = builder.build()

    # Unique nodes: (0,0), (10,0), (5,5) -> 3 nodes
    # Via vars = 2 nets * 3 nodes = 6

    via_vars = [v for v in model.variables if isinstance(v, ViaVar)]
    assert len(via_vars) == 6
