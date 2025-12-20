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
from temper_placer.topological.zone_solver import (
    ZoneAssignment,
    ZoneSolver,
)
from temper_placer.topological.initial_placement import (
    InitialPlacement,
    PlacementError,
    place_components_in_zone,
    identify_clusters,
    place_cluster,
    generate_initial_placement,
)
from temper_placer.topological.force_refinement import (
    compute_adjacency_force,
    compute_separation_force,
    compute_boundary_force,
    apply_force_refinement,
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
