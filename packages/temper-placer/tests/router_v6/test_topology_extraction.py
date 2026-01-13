"""
Tests for Router V6 Stage 3.9: Extract Topology Solution

Part of temper-8qm8
"""

import pytest

from temper_placer.router_v6.topology_extraction import (
    NetTopology,
    TopologyGraph,
    extract_topology_solution,
)
from temper_placer.router_v6.topology_solver import SolverStatus, TopologicalSolution


def test_extract_empty_solution():
    """Test extracting from empty solution."""
    solution = TopologicalSolution(
        status=SolverStatus.SATISFIABLE,
        assignment={},
        solver_time_ms=1.0,
    )
    
    topology = extract_topology_solution(solution, ["NET1", "NET2"])
    
    assert topology.routed_net_count == 0


def test_extract_with_routing_variables():
    """Test extracting topology with routing variables."""
    solution = TopologicalSolution(
        status=SolverStatus.SATISFIABLE,
        assignment={
            "route_NET1_A_to_B": True,
            "route_NET1_B_to_C": True,
            "route_NET2_X_to_Y": True,
        },
        solver_time_ms=1.0,
    )
    
    topology = extract_topology_solution(solution, ["NET1", "NET2"])
    
    assert topology.routed_net_count == 2
    
    # NET1 should have a path graph
    net1_topo = topology.get_topology("NET1")
    assert net1_topo is not None
    assert net1_topo.path_graph.number_of_edges() == 2


def test_extract_with_channel_variables():
    """Test extracting topology with channel usage variables."""
    solution = TopologicalSolution(
        status=SolverStatus.SATISFIABLE,
        assignment={
            "uses_NET1_CH1": True,
            "uses_NET1_CH2": True,
            "uses_NET2_CH3": True,
        },
        solver_time_ms=1.0,
    )
    
    topology = extract_topology_solution(solution, ["NET1", "NET2"])
    
    net1_topo = topology.get_topology("NET1")
    assert net1_topo is not None
    assert len(net1_topo.uses_channels) == 2
    assert "CH1" in net1_topo.uses_channels
    assert "CH2" in net1_topo.uses_channels


def test_extract_unsatisfiable_solution():
    """Test extracting from unsatisfiable solution."""
    solution = TopologicalSolution(
        status=SolverStatus.UNSATISFIABLE,
        assignment={},
        solver_time_ms=10.0,
    )
    
    topology = extract_topology_solution(solution, ["NET1"])
    
    assert topology.routed_net_count == 0


def test_net_topology_dataclass():
    """Test NetTopology dataclass."""
    import networkx as nx
    
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
    import networkx as nx
    
    net1_graph = nx.DiGraph()
    net1_topo = NetTopology("NET1", net1_graph, [], 10.0)
    
    net2_graph = nx.DiGraph()
    net2_topo = NetTopology("NET2", net2_graph, [], 15.0)
    
    topology = TopologyGraph(net_topologies={
        "NET1": net1_topo,
        "NET2": net2_topo,
    })
    
    assert topology.routed_net_count == 2
    assert topology.get_topology("NET1") == net1_topo
    assert topology.get_topology("NET2") == net2_topo
    assert topology.get_topology("NET3") is None
