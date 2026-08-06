"""
Tests for Router V6 Stage 3.9 topology graph types.

Part of temper-8qm8

``extract_topology_solution`` / ``_extract_net_topology`` were retired --
``_pipeline_route`` builds ``TopologyGraph`` / ``NetTopology`` directly from the
Rust solver result -- so the four tests that drove that parsing are gone.  These
two cover the dataclasses, which are still live.
"""

import networkx as nx

from temper_placer.router_v6.topology_extraction import NetTopology, TopologyGraph


def test_net_topology_dataclass():
    """Test NetTopology dataclass."""
    graph = nx.DiGraph()
    graph.add_edge("A", "B")

    net_topo = NetTopology(
        net_name="TEST_NET",
        path_graph=graph,
        uses_channels=["CH1", "CH2"],
        total_length_estimate=25.5,
    )

    assert net_topo.net_name == "TEST_NET"
    assert net_topo.path_graph.number_of_edges() == 1
    assert len(net_topo.uses_channels) == 2
    assert net_topo.total_length_estimate == 25.5


def test_topology_graph_dataclass():
    """Test TopologyGraph dataclass."""
    net1_graph = nx.DiGraph()
    net1_topo = NetTopology("NET1", net1_graph, [], 10.0)

    net2_graph = nx.DiGraph()
    net2_topo = NetTopology("NET2", net2_graph, [], 15.0)

    topology = TopologyGraph(
        net_topologies={
            "NET1": net1_topo,
            "NET2": net2_topo,
        }
    )

    assert topology.routed_net_count == 2
    assert topology.get_topology("NET1") == net1_topo
    assert topology.get_topology("NET2") == net2_topo
    assert topology.get_topology("NET3") is None
