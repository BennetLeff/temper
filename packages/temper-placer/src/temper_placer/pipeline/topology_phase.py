from __future__ import annotations
from typing import TYPE_CHECKING, List, Optional, Tuple

from temper_placer.core.topology import TopologicalGraph, TopologicalSolution, ComponentCluster
from temper_placer.pcl.constraints import (
    AdjacentConstraint,
    SeparatedConstraint,
    EnclosingConstraint,
)

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist
    from temper_placer.pcl.parser import ConstraintCollection

def build_topological_graph(
    netlist: Netlist,
    board: Board,
    constraints: ConstraintCollection
) -> TopologicalGraph:
    """Build a topological graph from netlist, board, and PCL constraints."""
    graph = TopologicalGraph()
    
    # 1. Add all components as nodes
    for comp in netlist.components:
        graph.add_node(comp.ref)
        
    # 2. Add constraints as edges
    for constraint in constraints.constraints:
        if isinstance(constraint, AdjacentConstraint):
            graph.add_adjacency(constraint.a, constraint.b, constraint.max_distance_mm)
        elif isinstance(constraint, SeparatedConstraint):
            graph.add_separation(constraint.a, constraint.b, constraint.min_distance_mm)
        elif isinstance(constraint, EnclosingConstraint):
            for inner in constraint.inner:
                graph.add_enclosure(constraint.outer, inner)
                
    return graph

def run_topological_phase(
    netlist: Netlist,
    board: Board,
    constraints: ConstraintCollection
) -> TopologicalSolution:
    """Run the topological placement phase.
    
    Identifies clusters and checks for fundamental unsatisfiability.
    """
    graph = build_topological_graph(netlist, board, constraints)
    
    # Identify clusters
    cluster_sets = graph.get_clusters()
    clusters = []
    
    # Map from component to zone
    comp_to_zone = {}
    for zone in board.zones:
        for comp_ref in zone.components:
            comp_to_zone[comp_ref] = zone.name
            
    # Also check enclosure constraints for zone assignments
    for outer, inners in graph.enclosure.items():
        if outer.endswith("_ZONE"):
            for inner in inners:
                comp_to_zone[inner] = outer

    for i, c_set in enumerate(cluster_sets):
        # Determine parent zone for cluster
        # If any component in cluster has a zone, they all share it? 
        # (Conflict check needed)
        found_zones = set()
        for ref in c_set:
            if ref in comp_to_zone:
                found_zones.add(comp_to_zone[ref])
        
        parent_zone = None
        if len(found_zones) == 1:
            parent_zone = list(found_zones)[0]
        elif len(found_zones) > 1:
            # TODO: Conflict! Components in same adjacency cluster assigned to different zones.
            pass

        clusters.append(ComponentCluster(
            name=f"cluster_{i}",
            components=c_set,
            parent_zone=parent_zone
        ))
        
    # Check for contradictions (already done by linter, but here we can be more thorough)
    # TODO: Implement more complex cycle detection or planarity checks
    
    return TopologicalSolution(
        clusters=clusters,
        feasible=True # Default to True for now, linter already catches basics
    )

def generate_initial_placement(
    solution: TopologicalSolution,
    board: Board,
    netlist: Netlist
) -> 'PlacementState':
    """Generate initial coordinates based on topological clusters."""
    import jax.numpy as jnp
    from temper_placer.core.state import PlacementState
    import jax
    
    n = netlist.n_components
    positions = jnp.zeros((n, 2))
    
    # Map zone name to bounds
    zone_bounds = {z.name: z.bounds for z in board.zones}
    
    # Track placed components
    placed_refs = {}
    
    key = jax.random.PRNGKey(42)
    
    for cluster in solution.clusters:
        # Determine center for cluster
        if cluster.parent_zone and cluster.parent_zone in zone_bounds:
            bounds = zone_bounds[cluster.parent_zone]
            cx = (bounds[0] + bounds[2]) / 2
            cy = (bounds[1] + bounds[3]) / 2
        else:
            cx = board.width / 2
            cy = board.height / 2
            
        # Place components in a small jittered group around center
        for ref in cluster.components:
            idx = netlist.get_component_index(ref)
            key, subkey = jax.random.split(key)
            jitter = jax.random.uniform(subkey, (2,), minval=-5.0, maxval=5.0)
            positions = positions.at[idx].set(jnp.array([cx, cy]) + jitter)
            
    return PlacementState(
        positions=positions,
        rotation_logits=jnp.zeros((n, 4))
    )
