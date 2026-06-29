"""Topological graph for component relationship reasoning.

Before assigning coordinates, we reason about:
- Who must be adjacent to whom?
- Who must be separated from whom?
- What groups must stay together?

This module builds a graph representation that enables:
1. Early infeasibility detection (conflicting constraints)
2. Component clustering (connected components)
3. Constraint propagation (derive implicit relationships)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import networkx as nx


@dataclass
class TopologicalNode:
    """A node in the topological graph.

    Nodes represent components, groups (loops), or zones.
    """

    id: str
    node_type: str  # 'component', 'group', 'zone'
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class TopologicalEdge:
    """An edge in the topological graph.

    Edges represent relationships:
    - 'adjacent': components should be close (max_distance)
    - 'separated': components should be far (min_distance)
    - 'member_of': component belongs to group/zone
    """

    source: str
    target: str
    edge_type: str  # 'adjacent', 'separated', 'member_of'
    constraint_id: str  # Reference to originating PCL constraint
    distance: float | None = None  # For adjacent/separated constraints


class TopologicalGraph:
    """Graph for reasoning about placement topology.

    This is a directed multigraph (multiple edges between same nodes allowed).
    Used to reason about component relationships before assigning coordinates.

    Example usage:
        graph = TopologicalGraph()
        graph.add_component('Q1')
        graph.add_component('Q2')
        graph.add_adjacency('Q1', 'Q2', max_distance=5.0, constraint_id='c1')

        cluster = graph.get_adjacency_cluster('Q1')
        # Returns: {'Q1', 'Q2'}
    """

    def __init__(self):
        """Initialize empty topological graph."""
        self.graph = nx.MultiDiGraph()

    def add_component(self, ref: str, properties: dict[str, Any] | None = None):
        """Add a component node.

        Args:
            ref: Component reference (e.g., 'Q1', 'C1')
            properties: Optional metadata (footprint, value, etc.)
        """
        self.graph.add_node(
            ref,
            node_type="component",
            properties=properties or {},
        )

    def add_group(self, name: str, members: list[str]):
        """Add a group node (loop or functional module).

        Creates membership edges from each member to the group.

        Args:
            name: Group name (e.g., 'loop_commutation')
            members: Component refs in the group
        """
        self.graph.add_node(
            name,
            node_type="group",
            members=members,
        )

        # Add membership edges
        for member in members:
            self.graph.add_edge(
                member,
                name,
                edge_type="member_of",
                constraint_id="auto_generated",
            )

    def add_adjacency(
        self,
        a: str,
        b: str,
        max_distance: float,
        constraint_id: str,
    ):
        """Add adjacency constraint edge.

        Adjacency is symmetric - creates edges in both directions.

        Args:
            a: First component
            b: Second component
            max_distance: Maximum allowed distance (mm)
            constraint_id: ID of originating PCL constraint
        """
        # Forward edge
        self.graph.add_edge(
            a,
            b,
            edge_type="adjacent",
            distance=max_distance,
            constraint_id=constraint_id,
        )

        # Reverse edge (adjacency is symmetric)
        self.graph.add_edge(
            b,
            a,
            edge_type="adjacent",
            distance=max_distance,
            constraint_id=constraint_id,
        )

    def add_separation(
        self,
        a: str,
        b: str,
        min_distance: float,
        constraint_id: str,
    ):
        """Add separation constraint edge.

        Args:
            a: First component
            b: Second component
            min_distance: Minimum required distance (mm)
            constraint_id: ID of originating PCL constraint
        """
        self.graph.add_edge(
            a,
            b,
            edge_type="separated",
            distance=min_distance,
            constraint_id=constraint_id,
        )

    def get_neighbors(
        self,
        node: str,
        edge_type: str | None = None,
    ) -> list[str]:
        """Get neighboring nodes.

        Args:
            node: Source node
            edge_type: Optional filter by edge type ('adjacent', 'separated', etc.)

        Returns:
            List of neighbor node IDs
        """
        neighbors = []
        for _, target, data in self.graph.edges(node, data=True):
            if edge_type is None or data.get("edge_type") == edge_type:
                neighbors.append(target)
        return neighbors

    def get_adjacency_cluster(self, seed: str) -> set[str]:
        """Get all components transitively adjacent to seed.

        Uses BFS to find connected component in the adjacency subgraph.

        Args:
            seed: Starting component

        Returns:
            Set of component refs in the same adjacency cluster
        """
        cluster = {seed}
        frontier = [seed]

        while frontier:
            current = frontier.pop(0)
            for neighbor in self.get_neighbors(current, edge_type="adjacent"):
                if neighbor not in cluster:
                    cluster.add(neighbor)
                    frontier.append(neighbor)

        return cluster

    def find_separation_conflicts(self) -> list[tuple[str, str, str]]:
        """Find nodes that are both adjacent and separated.

        A conflict occurs when:
        - adjacent(A, B, max=5mm) AND separated(A, B, min=10mm)
        - This is impossible to satisfy

        Returns:
            List of (component_a, component_b, reason) tuples
        """
        conflicts = []

        # Check all adjacency edges
        for u, v, adj_data in self.graph.edges(data=True):
            if adj_data.get("edge_type") != "adjacent":
                continue

            adj_max = adj_data.get("distance", 0)

            # Look for separation edge between same nodes
            for _, target, sep_data in self.graph.edges(u, data=True):
                if target != v:
                    continue
                if sep_data.get("edge_type") != "separated":
                    continue

                sep_min = sep_data.get("distance", 0)

                # Conflict if max < min
                if adj_max < sep_min:
                    reason = f"adjacent({adj_max}) < separated({sep_min})"
                    conflicts.append((u, v, reason))

        return conflicts

    @staticmethod
    def from_pcl(pcl: "ConstraintCollection") -> "TopologicalGraph":
        """Build topological graph from PCL constraints.

        Extracts all component references and creates appropriate edges
        for each constraint type.

        Args:
            pcl: Parsed PCL constraint collection

        Returns:
            TopologicalGraph with nodes and edges from constraints
        """
        from temper_placer.pcl.constraints import (
            AdjacentConstraint,
            SeparatedConstraint,
        )

        graph = TopologicalGraph()

        # Extract all component refs
        component_refs = set()
        for constraint in pcl.constraints:
            # AdjacentConstraint, SeparatedConstraint
            if hasattr(constraint, "a"):
                component_refs.add(constraint.a)
            if hasattr(constraint, "b"):
                component_refs.add(constraint.b)

            # AlignedConstraint, EnclosingConstraint.inner, OnSideConstraint
            if hasattr(constraint, "components"):
                component_refs.update(constraint.components)

            # EnclosingConstraint.inner
            if hasattr(constraint, "inner"):
                component_refs.update(constraint.inner)

            # EnclosingConstraint.outer (zone name)
            if hasattr(constraint, "outer"):
                component_refs.add(constraint.outer)

        # Add all components as nodes
        for ref in component_refs:
            graph.add_component(ref)

        # Add constraint edges
        for constraint in pcl.constraints:
            if isinstance(constraint, AdjacentConstraint):
                graph.add_adjacency(
                    constraint.a,
                    constraint.b,
                    constraint.max_distance_mm,
                    constraint.id,
                )
            elif isinstance(constraint, SeparatedConstraint):
                graph.add_separation(
                    constraint.a,
                    constraint.b,
                    constraint.min_distance_mm,
                    constraint.id,
                )
            # TODO: Handle EnclosingConstraint, AlignedConstraint, OnSideConstraint
            # These need more complex representation (not just pairwise edges)

        return graph


def build_topological_graph(
    pcl: "ConstraintCollection",
) -> TopologicalGraph:
    """Build topological graph from PCL constraints.

    Convenience function that delegates to TopologicalGraph.from_pcl().

    Args:
        pcl: Parsed PCL constraint collection

    Returns:
        TopologicalGraph with nodes and edges from constraints
    """
    return TopologicalGraph.from_pcl(pcl)
