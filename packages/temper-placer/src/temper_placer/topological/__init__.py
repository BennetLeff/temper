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
- Phase 5: Generate initial (x, y) coordinates

This module bridges PCL constraints and geometric optimization.
"""

from temper_placer.topological.force_refinement import (
    apply_force_refinement,
    compute_adjacency_force,
    compute_boundary_force,
    compute_separation_force,
)
from temper_placer.topological.graph import (
    TopologicalEdge,
    TopologicalGraph,
    TopologicalNode,
    build_topological_graph,
)
from temper_placer.topological.initial_placement import (
    InitialPlacement,
    PlacementError,
    generate_initial_placement,
    identify_clusters,
    place_cluster,
    place_components_in_zone,
)
from temper_placer.topological.propagation import (
    ConstraintPropagator,
    DistanceBound,
)
from temper_placer.topological.zone_solver import (
    ZoneAssignment,
    ZoneSolver,
)

__all__ = [
    # Graph
    "TopologicalGraph",
    "TopologicalNode",
    "TopologicalEdge",
    "build_topological_graph",
    # Propagation
    "DistanceBound",
    "ConstraintPropagator",
    # Zone solver
    "ZoneAssignment",
    "ZoneSolver",
    # Initial placement
    "InitialPlacement",
    "PlacementError",
    "place_components_in_zone",
    "identify_clusters",
    "place_cluster",
    "generate_initial_placement",
    # Force refinement
    "compute_adjacency_force",
    "compute_separation_force",
    "compute_boundary_force",
    "apply_force_refinement",
]
