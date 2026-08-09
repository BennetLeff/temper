from __future__ import annotations

from dataclasses import dataclass, field

import temper_geometry as _tg


@dataclass
class TopologicalGraph:
    """Adjacency graph representing topological relationships between components.

    This structure is used to reason about placement before assigning coordinates.
    """

    nodes: list[str] = field(default_factory=list)
    # (a, b, max_distance_mm)
    adjacency_edges: list[tuple[str, str, float]] = field(default_factory=list)
    # (a, b, min_distance_mm)
    separation_edges: list[tuple[str, str, float]] = field(default_factory=list)
    # outer zone/component -> [inner components]
    enclosure: dict[str, list[str]] = field(default_factory=dict)

    def add_node(self, ref: str) -> None:
        """Add a component reference as a node."""
        if ref not in self.nodes:
            self.nodes.append(ref)

    def add_adjacency(self, a: str, b: str, max_dist: float) -> None:
        """Add an adjacency requirement."""
        self.add_node(a)
        self.add_node(b)
        self.adjacency_edges.append((a, b, max_dist))

    def add_separation(self, a: str, b: str, min_dist: float) -> None:
        """Add a separation requirement."""
        self.add_node(a)
        self.add_node(b)
        self.separation_edges.append((a, b, min_dist))

    def add_enclosure(self, outer: str, inner: str) -> None:
        """Add an enclosure requirement."""
        self.add_node(outer)
        self.add_node(inner)
        if outer not in self.enclosure:
            self.enclosure[outer] = []
        if inner not in self.enclosure[outer]:
            self.enclosure[outer].append(inner)

    def get_clusters(self) -> list[set[str]]:
        """Identify connected components in the adjacency graph.

        Connected components represent clusters of components that must stay
        relatively close to each other.

        The union-find kernel runs in Rust
        (``temper_geometry.topology_connected_components``) and reproduces the
        oracle's partition AND group order: groups are emitted in
        first-appearance order of each component in ``self.nodes``, and each
        group's members in node order.
        """
        edge_a = [a for a, _, _ in self.adjacency_edges]
        edge_b = [b for _, b, _ in self.adjacency_edges]
        groups = _tg.topology_connected_components_py(self.nodes, edge_a, edge_b)
        return [{self.nodes[i] for i in group} for group in groups]


@dataclass
class ComponentCluster:
    """A cluster of components that stay together."""

    name: str
    components: set[str]
    parent_zone: str | None = None


@dataclass
class TopologicalSolution:
    """Output of the topological placement phase."""

    clusters: list[ComponentCluster] = field(default_factory=list)
    cluster_adjacencies: list[tuple[str, str]] = field(default_factory=list)
    cluster_separations: list[tuple[str, str, float]] = field(default_factory=list)
    feasible: bool = True
    infeasibility_reasons: list[str] = field(default_factory=list)


class UnionFind:
    """Disjoint-set / union-find data structure.

    Stays Python (R3 verdict): this is a *stateful* incremental API
    (``find`` / ``union`` mutate instance state between calls) over
    arbitrary hashable keys, with no separable numeric kernel — a Rust
    port would be a pyclass holding state for no compute gain. See
    ``packages/temper-geometry/VERIFICATION.md``.
    """

    def __init__(self):
        self._parent = {}

    def find(self, x):
        if x not in self._parent:
            self._parent[x] = x
        if self._parent[x] != x:
            self._parent[x] = self.find(self._parent[x])
        return self._parent[x]

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[ra] = rb

    def get_components(self) -> dict[int, list[int]]:
        """Return disjoint sets grouped by root, keyed by root."""
        components: dict[int, list[int]] = {}
        for elem in self._parent:
            root = self.find(elem)
            if root not in components:
                components[root] = []
            components[root].append(elem)
        return components
