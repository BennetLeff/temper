"""Topological data structures for routing analysis."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class UnionFind:
    """Union-Find data structure for connected components.

    Optimized with path compression and union by rank.
    """

    parent: dict[int, int] = field(default_factory=dict)
    rank: dict[int, int] = field(default_factory=dict)

    def find(self, x: int) -> int:
        """Find root with path compression."""
        if x not in self.parent:
            self.parent[x] = x
            self.rank[x] = 0
            return x

        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, x: int, y: int) -> bool:
        """Union by rank. Returns True if merged."""
        px, py = self.find(x), self.find(y)
        if px == py:
            return False

        if self.rank[px] < self.rank[py]:
            px, py = py, px
        self.parent[py] = px
        if self.rank[px] == self.rank[py]:
            self.rank[px] += 1
        return True

    def connected(self, x: int, y: int) -> bool:
        """Check if two elements are connected."""
        return self.find(x) == self.find(y)

    def get_components(self) -> dict[int, list[int]]:
        """Get all connected components."""
        components: dict[int, list[int]] = {}
        elements = list(self.parent.keys())
        for elem in elements:
            root = self.find(elem)
            if root not in components:
                components[root] = []
            components[root].append(elem)
        return components
