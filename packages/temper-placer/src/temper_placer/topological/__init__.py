"""Topological reasoning for placement.

Topological placement reasons about component relationships (adjacency, separation)
BEFORE assigning coordinates. This catches impossible layouts early and identifies
natural component clusters.

Phases:
- Phase 0: Build topological graph from PCL constraints
- Phase 1: Propagate constraints to infer implicit relationships
- Phase 2: Check constraint satisfiability (detect conflicts)
- Phase 3: Identify component clusters that must stay together
- Phase 4: Assign components to zones

This module bridges PCL constraints and geometric optimization.
"""

from temper_placer.topological.graph import (
    TopologicalGraph,
    TopologicalNode,
    TopologicalEdge,
    build_topological_graph,
)
from temper_placer.topological.propagation import (
    DistanceBound,
    ConstraintPropagator,
)

__all__ = [
    "TopologicalGraph",
    "TopologicalNode",
    "TopologicalEdge",
    "build_topological_graph",
    "DistanceBound",
    "ConstraintPropagator",
]
