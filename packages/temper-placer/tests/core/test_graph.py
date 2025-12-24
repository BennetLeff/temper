
import jax.numpy as jnp
import pytest

from temper_placer.core.graph import NetlistGraph, netlist_to_graph
from temper_placer.core.netlist import Component, Net, Netlist


def test_netlist_to_graph():
    """Verify conversion from netlist to graph features."""
    c1 = Component(ref="R1", footprint="0603", bounds=(1.6, 0.8)) # 2 pins
    c2 = Component(ref="U1", footprint="SOIC-8", bounds=(5, 4)) # 8 pins

    # Add pins
    for i in range(2): c1.pins.append(None)
    for i in range(8): c2.pins.append(None)

    nets = [Net(name="N1", pins=[("R1", "1"), ("U1", "1")])]
    netlist = Netlist(components=[c1, c2], nets=nets)

    graph = netlist_to_graph(netlist)

    # Nodes: [2, F]
    # Features: [Area, PinCount, IsFixed]
    assert graph.nodes.shape[0] == 2
    assert graph.nodes[0, 0] == pytest.approx(1.6 * 0.8)
    assert graph.nodes[0, 1] == 2
    assert graph.nodes[1, 1] == 8

    # Edges: [1, 2]
    assert graph.edges.shape[0] == 1 # 1 net connects 2 components
    assert 0 in graph.edges[0]
    assert 1 in graph.edges[0]

def test_graph_batching():
    """Verify that multiple graphs can be batched together."""
    from temper_placer.core.graph import batch_graphs

    # Graph 1 (2 nodes, 1 edge)
    g1 = NetlistGraph(
        nodes=jnp.ones((2, 3)),
        edges=jnp.array([[0, 1]]),
        edge_weights=jnp.ones(1)
    )

    # Graph 2 (3 nodes, 2 edges)
    g2 = NetlistGraph(
        nodes=jnp.zeros((3, 3)),
        edges=jnp.array([[0, 1], [1, 2]]),
        edge_weights=jnp.ones(2)
    )

    batched = batch_graphs([g1, g2])

    # Combined: 5 nodes, 3 edges
    assert batched.nodes.shape[0] == 5
    assert batched.edges.shape[0] == 3

    # Check edge index shifting
    # Second graph edges [0,1], [1,2] should become [2,3], [3,4]
    assert jnp.all(batched.edges[1:] == jnp.array([[2, 3], [3, 4]]))

