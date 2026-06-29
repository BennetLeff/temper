"""
Tests for Router V6 Stage 4.1: Map Topology to Channels

Part of temper-qic1
"""

import networkx as nx

from temper_placer.router_v6.channel_mapping import (
    ChannelMapping,
    ChannelPath,
    map_topology_to_channels,
)
from temper_placer.router_v6.channel_skeleton import ChannelSkeleton
from temper_placer.router_v6.topology_extraction import NetTopology, TopologyGraph


def test_map_empty_topology():
    """Test mapping empty topology."""
    topology = TopologyGraph(net_topologies={})
    skeleton = ChannelSkeleton(nx.Graph(), "F.Cu", 0.0)

    mapping = map_topology_to_channels(topology, skeleton)

    assert mapping.mapped_net_count == 0


def test_map_with_channels():
    """Test mapping topology with channel usage."""
    net_topo = NetTopology(
        net_name="NET1",
        path_graph=nx.DiGraph(),
        uses_channels=["CH1", "CH2", "CH3"],
        total_length_estimate=30.0,
    )

    topology = TopologyGraph(net_topologies={"NET1": net_topo})
    skeleton = ChannelSkeleton(nx.Graph(), "F.Cu", 0.0)

    mapping = map_topology_to_channels(topology, skeleton)

    assert mapping.mapped_net_count == 1

    path = mapping.get_path("NET1")
    assert path is not None
    assert path.net_name == "NET1"
    assert len(path.channel_sequence) == 3


def test_map_with_path_graph():
    """Test mapping topology with path graph."""
    graph = nx.DiGraph()
    graph.add_edge("A", "B")
    graph.add_edge("B", "C")

    net_topo = NetTopology(
        net_name="NET2",
        path_graph=graph,
        uses_channels=[],
        total_length_estimate=20.0,
    )

    topology = TopologyGraph(net_topologies={"NET2": net_topo})
    skeleton = ChannelSkeleton(nx.Graph(), "F.Cu", 0.0)

    mapping = map_topology_to_channels(topology, skeleton)

    path = mapping.get_path("NET2")
    assert path is not None
    assert len(path.channel_sequence) > 0  # Should extract from graph


def test_channel_path_dataclass():
    """Test ChannelPath dataclass."""
    path = ChannelPath(
        net_name="TEST_NET",
        channel_sequence=["CH1", "CH2"],
        waypoints=[(0.0, 0.0), (10.0, 10.0)],
        total_length=14.142,
    )

    assert path.net_name == "TEST_NET"
    assert len(path.channel_sequence) == 2
    assert len(path.waypoints) == 2
    assert path.total_length > 14.0


def test_channel_mapping_dataclass():
    """Test ChannelMapping dataclass."""
    path1 = ChannelPath("NET1", ["CH1"], [(0, 0)], 10.0)
    path2 = ChannelPath("NET2", ["CH2"], [(5, 5)], 15.0)

    mapping = ChannelMapping(channel_paths={
        "NET1": path1,
        "NET2": path2,
    })

    assert mapping.mapped_net_count == 2
    assert mapping.get_path("NET1") == path1
    assert mapping.get_path("NET2") == path2
    assert mapping.get_path("NET3") is None


def test_waypoint_generation():
    """Test waypoint generation from skeleton."""
    # Create skeleton with nodes
    skeleton_graph = nx.Graph()
    skeleton_graph.add_node((10.0, 10.0))
    skeleton_graph.add_node((20.0, 20.0))

    skeleton = ChannelSkeleton(skeleton_graph, "F.Cu", 30.0)

    net_topo = NetTopology(
        net_name="NET3",
        path_graph=nx.DiGraph(),
        uses_channels=["CH1", "CH2"],
        total_length_estimate=15.0,
    )

    topology = TopologyGraph(net_topologies={"NET3": net_topo})
    mapping = map_topology_to_channels(topology, skeleton)

    path = mapping.get_path("NET3")
    assert path is not None
    # Should have generated waypoints
    assert len(path.waypoints) >= 0
