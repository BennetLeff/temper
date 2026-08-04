"""Constraint propagation solver.

Propagates distance bounds through the topological graph to derive implicit constraints.
Uses Floyd-Warshall-like algorithm with triangle inequality.

Example:
    If A adjacent B (≤5mm) and B adjacent C (≤3mm), then A-C must be ≤8mm.
    This catches infeasibility early and generates implicit constraints.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

import temper_placement_topology as _rust

if TYPE_CHECKING:
    from temper_placer.topological.graph import TopologicalGraph


@dataclass
class DistanceBound:
    """Distance bound between two components.

    Represents the constraint: min_distance ≤ distance ≤ max_distance

    Attributes:
        min_distance: Minimum required distance (from separation constraints)
        max_distance: Maximum allowed distance (from adjacency constraints)
    """

    min_distance: float = 0.0
    max_distance: float = float("inf")

    def tighten_max(self, new_max: float) -> None:
        """Tighten maximum bound (take minimum).

        Args:
            new_max: Proposed new maximum distance
        """
        self.max_distance = min(self.max_distance, new_max)

    def tighten_min(self, new_min: float) -> None:
        """Tighten minimum bound (take maximum).

        Args:
            new_min: Proposed new minimum distance
        """
        self.min_distance = max(self.min_distance, new_min)

    def is_feasible(self) -> bool:
        """Check if bounds are feasible (min ≤ max).

        Returns:
            True if feasible, False if impossible to satisfy
        """
        return self.min_distance <= self.max_distance


class ConstraintPropagator:
    """Propagate constraints through topological graph.

    Uses Floyd-Warshall-like algorithm to derive implicit distance bounds
    from explicit adjacency and separation constraints.

    Time complexity: O(n³) where n = number of components

    Example:
        graph = TopologicalGraph()
        # ... add components and constraints ...

        propagator = ConstraintPropagator(graph)
        if not propagator.propagate():
            # Constraints are infeasible
            for a, b, bound in propagator.get_infeasible_pairs():
                print(f'{a}-{b}: impossible (min={bound.min_distance}, max={bound.max_distance})')
    """

    def __init__(self, graph: "TopologicalGraph"):
        """Initialize propagator from topological graph.

        Args:
            graph: Topological graph with adjacency/separation edges
        """
        self.graph = graph

        # Build node index
        self.nodes = list(graph.graph.nodes())
        self.node_idx = {node: i for i, node in enumerate(self.nodes)}

        # Initialize bounds matrix (n×n)
        n = len(self.nodes)
        self.bounds = [[DistanceBound() for _ in range(n)] for _ in range(n)]

        # Populate from explicit constraints
        self._init_from_edges()

    def _init_from_edges(self) -> None:
        """Initialize bounds from explicit graph edges."""
        for u, v, data in self.graph.graph.edges(data=True):
            edge_type = data.get("edge_type")
            distance = data.get("distance")

            if edge_type == "adjacent":
                # Adjacency constraint: max distance
                i, j = self.node_idx[u], self.node_idx[v]
                self.bounds[i][j].tighten_max(distance)
                # Adjacency is symmetric
                self.bounds[j][i].tighten_max(distance)

            elif edge_type == "separated":
                # Separation constraint: min distance
                i, j = self.node_idx[u], self.node_idx[v]
                self.bounds[i][j].tighten_min(distance)
                # Separation is NOT necessarily symmetric in graph, but distance is
                self.bounds[j][i].tighten_min(distance)

    def _edge_index_lists(self) -> tuple[list[tuple], list[tuple]]:
        """Adjacency/separation edges as ``(i, j, distance)`` in graph order."""
        adjacent: list[tuple] = []
        separated: list[tuple] = []
        for u, v, data in self.graph.graph.edges(data=True):
            edge_type = data.get("edge_type")
            if edge_type == "adjacent":
                adjacent.append((self.node_idx[u], self.node_idx[v], float(data["distance"])))
            elif edge_type == "separated":
                separated.append((self.node_idx[u], self.node_idx[v], float(data["distance"])))
        return adjacent, separated

    def propagate(self, max_iterations: int = 100) -> bool:
        """Propagate constraints using triangle inequality.

        Iteratively applies triangle inequality:
        - max(i,j) ≤ max(i,k) + max(k,j) for all k
        - min(i,j) ≥ min(i,k) - max(k,j) when positive

        Args:
            max_iterations: Maximum propagation iterations (stops early if converged)

        Returns:
            True if constraints are feasible, False if impossible
        """
        n = len(self.nodes)
        adjacent, separated = self._edge_index_lists()

        feasible, mins, maxs = _rust.propagate_bounds(n, adjacent, separated, max_iterations)

        # Rehydrate the matrix so `get_bound` / `get_infeasible_pairs` keep
        # returning the same mutable DistanceBound objects the API promises.
        for i in range(n):
            row = self.bounds[i]
            base = i * n
            for j in range(n):
                bound = row[j]
                bound.min_distance = mins[base + j]
                bound.max_distance = maxs[base + j]

        return feasible

    def get_bound(self, a: str, b: str) -> DistanceBound:
        """Get propagated distance bound between two components.

        Args:
            a: First component ref
            b: Second component ref

        Returns:
            DistanceBound after propagation
        """
        i = self.node_idx[a]
        j = self.node_idx[b]
        return self.bounds[i][j]

    def get_infeasible_pairs(self) -> list[tuple[str, str, DistanceBound]]:
        """Get all component pairs with infeasible bounds.

        Returns:
            List of (component_a, component_b, bound) for infeasible pairs
        """
        infeasible = []
        n = len(self.nodes)

        for i in range(n):
            for j in range(i + 1, n):  # Only check upper triangle (symmetric)
                if not self.bounds[i][j].is_feasible():
                    infeasible.append(
                        (
                            self.nodes[i],
                            self.nodes[j],
                            self.bounds[i][j],
                        )
                    )

        return infeasible
