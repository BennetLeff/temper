import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from temper_placer.router_v6.analysis.topological_ordering import TopologicalOrderer

def run_acyclic_experiment():
    """
    Scenario: Nested nets. Net 'INNER' is physically inside 'OUTER's pad hull.
    Outcome: INNER must be routed first.
    """
    print("\n--- Running Acyclic Experiment (Nesting) ---")
    nets = {
        "OUTER": [(0, 0), (20, 0), (20, 20), (0, 20)],
        "INNER": [(8, 8), (12, 12)]
    }
    
    orderer = TopologicalOrderer()
    auto_deps = orderer.detect_topological_constraints(nets)
    order, sccs = orderer.compute_order(nets, dependencies=auto_deps)
    
    print(f"Detected Dependencies: {auto_deps}")
    print(f"Topological Order: {order}")
    print(f"SCCs: {sccs}")
    
    assert order == ["INNER", "OUTER"]
    assert len(sccs) == 0
    print("✓ Acyclic Experiment PASSED")

def run_cyclic_experiment():
    """
    Scenario: Mutual blocking. 
    A must go before B (explicit), B must go before C (explicit), C must go before A (explicit).
    Outcome: SCC identified as {A, B, C}.
    """
    print("\n--- Running Cyclic Experiment (Tarjan's / SCC) ---")
    nets = {
        "A": [(0,0), (1,1)],
        "B": [(5,5), (6,6)],
        "C": [(10,10), (11,11)]
    }
    # Artificial cycle
    dependencies = [("A", "B"), ("B", "C"), ("C", "A")]
    
    orderer = TopologicalOrderer()
    order, sccs = orderer.compute_order(nets, dependencies=dependencies)
    
    print(f"Forced Dependencies: {dependencies}")
    print(f"Topological Order (Best Effort): {order}")
    print(f"Identified SCCs (Conflicts): {sccs}")
    
    assert len(sccs) == 1
    assert set(sccs[0]) == {"A", "B", "C"}
    print("✓ Cyclic Experiment PASSED")

def run_conflict_analysis_experiment():
    """
    Scenario: Intersecting nets.
    Net X crosses Net Y.
    Outcome: Dependency detected based on complexity scoring.
    """
    print("\n--- Running Conflict Analysis Experiment (Intersections) ---")
    # Horizontal net
    nets = {
        "HORIZ": [(0, 5), (10, 5)],
        "VERT": [(5, 0), (5, 10)]
    }
    
    orderer = TopologicalOrderer()
    conflicts = orderer.detect_conflicts(nets)
    order, _ = orderer.compute_order(nets, dependencies=conflicts)
    
    print(f"Detected Conflicts: {conflicts}")
    print(f"Topological Order: {order}")
    
    assert len(conflicts) > 0
    print("✓ Conflict Analysis Experiment PASSED")

if __name__ == "__main__":
    run_acyclic_experiment()
    run_cyclic_experiment()
    run_conflict_analysis_experiment()
