import pytest
import networkx as nx
from temper_placer.router_v6.analysis.topological_ordering import TopologicalOrderer
from temper_placer.router_v6.stage0_data import DesignRules
from temper_placer.core.netlist import Net, Component, Pin
from temper_placer.core.board import Board

def test_ordering_by_density():
    """Test that high-density nets are prioritized."""
    # Net A: Short, tight net in a crowded area
    # Net B: Long net that can detour easily
    
    # We need a dummy PCB-like structure or just mock what the Orderer needs
    # Let's assume the Orderer takes pcb.nets and component positions
    
    # Mock data
    nets = {
        "NET_A": [(10, 10), (12, 10)], # Small bbox, 2 pins
        "NET_B": [(0, 0), (50, 50)]    # Large bbox, 2 pins
    }
    
    orderer = TopologicalOrderer()
    order, _ = orderer.compute_order(nets)
    
    # NET_A should be first because it's more "constrained" (smaller bbox area)
    assert order[0] == "NET_A"
    assert order[1] == "NET_B"

def test_ordering_by_terminal_count():
    """Test that nets with more terminals are prioritized."""
    nets = {
        "NET_A": [(10, 10), (20, 10)],              # 2 pins
        "NET_B": [(10, 20), (20, 20), (15, 25)]     # 3 pins
    }
    
    orderer = TopologicalOrderer()
    order, _ = orderer.compute_order(nets)
    
    # NET_B should be first (more complex connectivity)
    assert order[0] == "NET_B"
    assert order[1] == "NET_A"

def test_constraint_graph_loop_prevention():
    """Test that the orderer handles dependencies gracefully."""
    # If we implement explicit dependencies (A before B), check it works
    nets = {
        "A": [(0,0), (1,1)],
        "B": [(2,2), (3,3)]
    }
    dependencies = [("B", "A")] # B must come BEFORE A
    
    orderer = TopologicalOrderer()
    order, _ = orderer.compute_order(nets, dependencies=dependencies)
    
    assert order.index("B") < order.index("A")

def test_ordering_by_radial_proximity():
    """Test that center-nets are prioritized when centroid is provided."""
    nets = {
        "CENTRAL": [(24, 24), (26, 26)], # Near center (25, 25)
        "PERIPHERAL": [(0, 0), (2, 2)]    # Far from center
    }
    board_centroid = (25.0, 25.0)
    
    orderer = TopologicalOrderer()
    order, _ = orderer.compute_order(nets, board_centroid=board_centroid)
    
    assert order[0] == "CENTRAL"
    assert order[1] == "PERIPHERAL"

def test_ordering_by_nesting():
    """Test that nested nets are routed first."""
    nets = {
        "OUTER": [(0, 0), (10, 0), (10, 10), (0, 10)], # Large square
        "INNER": [(4, 4), (6, 6)]                      # Small square inside
    }
    
    orderer = TopologicalOrderer()
    auto_deps = orderer.detect_topological_constraints(nets)
    
    # Check that INNER -> OUTER dependency was detected
    assert ("INNER", "OUTER") in auto_deps
    
    order, _ = orderer.compute_order(nets, dependencies=auto_deps)
    assert order[0] == "INNER"
    assert order[1] == "OUTER"

def test_cycle_detection():
    """Test that cycles are identified as Strongly Connected Components."""
    nets = {
        "A": [(0,0), (1,1)],
        "B": [(2,2), (3,3)],
        "C": [(4,4), (5,5)]
    }
    # Create a cycle A -> B -> C -> A
    dependencies = [("A", "B"), ("B", "C"), ("C", "A")]
    
    orderer = TopologicalOrderer()
    order, sccs = orderer.compute_order(nets, dependencies=dependencies)
    
    # Should identify the SCC {A, B, C}
    assert len(sccs) == 1
    assert set(sccs[0]) == {"A", "B", "C"}
    # Order should still be produced (best effort)
    assert len(order) == 3
