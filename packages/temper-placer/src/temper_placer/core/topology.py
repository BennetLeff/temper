from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

@dataclass
class TopologicalGraph:
    """Adjacency graph representing topological relationships between components.
    
    This structure is used to reason about placement before assigning coordinates.
    """
    nodes: List[str] = field(default_factory=list)
    # (a, b, max_distance_mm)
    adjacency_edges: List[Tuple[str, str, float]] = field(default_factory=list)
    # (a, b, min_distance_mm)
    separation_edges: List[Tuple[str, str, float]] = field(default_factory=list)
    # outer zone/component -> [inner components]
    enclosure: Dict[str, List[str]] = field(default_factory=dict)

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

    def get_clusters(self) -> List[Set[str]]:
        """Identify connected components in the adjacency graph.
        
        Connected components represent clusters of components that must stay
        relatively close to each other.
        """
        parent = {node: node for node in self.nodes}

        def find(i):
            if parent[i] == i:
                return i
            parent[i] = find(parent[i])
            return parent[i]

        def union(i, j):
            root_i = find(i)
            root_j = find(j)
            if root_i != root_j:
                parent[root_i] = root_j

        # Union connected nodes
        for a, b, _ in self.adjacency_edges:
            union(a, b)

        # Group by root
        clusters_dict: Dict[str, Set[str]] = {}
        for node in self.nodes:
            root = find(node)
            if root not in clusters_dict:
                clusters_dict[root] = set()
            clusters_dict[root].add(node)

        return list(clusters_dict.values())

@dataclass
class ComponentCluster:
    """A cluster of components that stay together."""
    name: str
    components: Set[str]
    parent_zone: Optional[str] = None

@dataclass
class TopologicalSolution:
    """Output of the topological placement phase."""
    clusters: List[ComponentCluster] = field(default_factory=list)
    cluster_adjacencies: List[Tuple[str, str]] = field(default_factory=list)
    cluster_separations: List[Tuple[str, str, float]] = field(default_factory=list)
    feasible: bool = True
    infeasibility_reasons: List[str] = field(default_factory=list)
