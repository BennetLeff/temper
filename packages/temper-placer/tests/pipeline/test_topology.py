
import pytest
from temper_placer.pipeline.topology_phase import build_topological_graph, run_topological_phase
from temper_placer.core.netlist import Netlist, Component
from temper_placer.core.board import Board
from temper_placer.pcl import ConstraintCollection, AdjacentConstraint, ConstraintTier

@pytest.fixture
def mock_design():
    c1 = Component(ref="U1", footprint="F", bounds=(5, 5))
    c2 = Component(ref="R1", footprint="F", bounds=(2, 1))
    c3 = Component(ref="C1", footprint="F", bounds=(1, 1))
    
    netlist = Netlist(components=[c1, c2, c3])
    board = Board(width=100, height=100)
    
    return netlist, board

def test_build_topological_graph(mock_design):
    netlist, board = mock_design
    constraints = ConstraintCollection(constraints=[
        AdjacentConstraint(a="U1", b="R1", max_distance_mm=5.0, tier=ConstraintTier.HARD, because="Reason for this constraint")
    ])
    
    graph = build_topological_graph(netlist, board, constraints)
    assert len(graph.nodes) == 3
    assert len(graph.adjacency_edges) == 1
    assert graph.adjacency_edges[0][0] == "U1"
    assert graph.adjacency_edges[0][1] == "R1"

def test_cluster_identification(mock_design):
    netlist, board = mock_design
    # U1-R1 connected, C1 isolated
    constraints = ConstraintCollection(constraints=[
        AdjacentConstraint(a="U1", b="R1", max_distance_mm=5.0, tier=ConstraintTier.HARD, because="Reason for this constraint")
    ])
    
    solution = run_topological_phase(netlist, board, constraints)
    assert len(solution.clusters) == 2 # {U1, R1} and {C1}
    
    cluster_members = [c.components for c in solution.clusters]
    assert {"U1", "R1"} in cluster_members
    assert {"C1"} in cluster_members

def test_initial_placement_generation(mock_design):
    from temper_placer.pipeline.topology_phase import generate_initial_placement
    netlist, board = mock_design
    constraints = ConstraintCollection(constraints=[
        AdjacentConstraint(a="U1", b="R1", max_distance_mm=5.0, tier=ConstraintTier.HARD, because="Reason for this constraint")
    ])
    
    solution = run_topological_phase(netlist, board, constraints)
    state = generate_initial_placement(solution, board, netlist)
    
    assert state.positions.shape == (3, 2)
    
    # U1 and R1 should be close to each other (since they are in same cluster)
    idx_u1 = netlist.get_component_index("U1")
    idx_r1 = netlist.get_component_index("R1")
    
    dist = ((state.positions[idx_u1] - state.positions[idx_r1])**2).sum()**0.5
    assert dist < 15.0 # Cluster jitter is +/- 5mm, so max dist is roughly 10*sqrt(2)
