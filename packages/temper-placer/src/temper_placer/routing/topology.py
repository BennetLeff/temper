"""
Power net topology analysis for island detection and stitching.

Uses Union-Find for efficient connected component detection and
MST for optimal via placement.

Part of temper-glwf
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from temper_placer.routing.constraints import DRCOracle


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
            self.parent[x] = self.find(self.parent[x])  # Path compression
        return self.parent[x]
    
    def union(self, x: int, y: int) -> bool:
        """Union by rank. Returns True if merged."""
        px, py = self.find(x), self.find(y)
        if px == py:
            return False
        
        # Union by rank
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
        for x in self.parent:
            root = self.find(x)
            if root not in components:
                components[root] = []
            components[root].append(x)
        return components


@dataclass
class PowerPad:
    """A pad belonging to a power net."""
    id: int
    x: float
    y: float
    layer: int
    net: str
    component: str


@dataclass
class Island:
    """A connected component of pads on a power net."""
    id: int
    net: str
    pads: list[PowerPad]
    centroid: tuple[float, float]
    
    @classmethod
    def from_pads(cls, island_id: int, pads: list[PowerPad]) -> "Island":
        """Create island and compute centroid."""
        if not pads:
            return cls(island_id, "", [], (0, 0))
        
        cx = sum(p.x for p in pads) / len(pads)
        cy = sum(p.y for p in pads) / len(pads)
        return cls(
            id=island_id,
            net=pads[0].net,
            pads=pads,
            centroid=(cx, cy),
        )


@dataclass
class StitchingVia:
    """A via to connect islands."""
    x: float
    y: float
    from_layer: int
    to_layer: int
    net: str
    connects_islands: tuple[int, int]


def detect_islands(
    pads: list[PowerPad],
    connection_radius: float = 0.0,
) -> list[Island]:
    """Detect isolated islands of pads on a net.
    
    Pads are connected if:
    1. They're on the same layer AND within connection_radius
    2. OR they explicitly share a trace/via (not checked here)
    
    For power nets that should use planes, pads on the same layer
    are typically NOT connected unless there's a copper pour.
    
    Args:
        pads: List of pads on a power net
        connection_radius: Distance within which pads are connected (0 = only exact overlap)
        
    Returns:
        List of Island objects (each is a connected component)
    """
    if not pads:
        return []
    
    uf = UnionFind()
    
    # Each pad starts as its own component
    for pad in pads:
        uf.find(pad.id)
    
    # Connect pads that are close enough on the same layer
    for i, p1 in enumerate(pads):
        for p2 in pads[i+1:]:
            if p1.layer == p2.layer:
                dist = np.sqrt((p1.x - p2.x)**2 + (p1.y - p2.y)**2)
                if dist <= connection_radius:
                    uf.union(p1.id, p2.id)
    
    # Group into islands
    components = uf.get_components()
    pad_by_id = {p.id: p for p in pads}
    
    islands = []
    for i, (root, member_ids) in enumerate(components.items()):
        island_pads = [pad_by_id[mid] for mid in member_ids if mid in pad_by_id]
        islands.append(Island.from_pads(i, island_pads))
    
    return islands


def compute_stitching_vias(
    islands: list[Island],
    plane_layer: int,
    drc_oracle: "DRCOracle | None" = None,
) -> list[StitchingVia]:
    """Compute minimal vias to connect all islands.
    
    Uses MST (Prim's algorithm) to find minimum spanning tree of island centroids,
    then places vias along the MST edges.
    
    Args:
        islands: List of islands to connect
        plane_layer: Layer where the power plane exists
        drc_oracle: Optional oracle for via placement validation
        
    Returns:
        List of StitchingVia objects
    """
    if len(islands) <= 1:
        return []
    
    net = islands[0].net
    
    # Build distance matrix between island centroids
    n = len(islands)
    dist = np.zeros((n, n))
    for i in range(n):
        for j in range(i+1, n):
            cx1, cy1 = islands[i].centroid
            cx2, cy2 = islands[j].centroid
            d = np.sqrt((cx1 - cx2)**2 + (cy1 - cy2)**2)
            dist[i, j] = dist[j, i] = d
    
    # Prim's MST
    in_mst = [False] * n
    in_mst[0] = True
    mst_edges: list[tuple[int, int]] = []
    
    for _ in range(n - 1):
        min_dist = float('inf')
        min_edge = (-1, -1)
        
        for i in range(n):
            if not in_mst[i]:
                continue
            for j in range(n):
                if in_mst[j]:
                    continue
                if dist[i, j] < min_dist:
                    min_dist = dist[i, j]
                    min_edge = (i, j)
        
        if min_edge[0] >= 0:
            mst_edges.append(min_edge)
            in_mst[min_edge[1]] = True
    
    # Place vias at island centroids for each MST edge
    vias = []
    for i, j in mst_edges:
        # Place via at midpoint between island centroids
        cx1, cy1 = islands[i].centroid
        cx2, cy2 = islands[j].centroid
        via_x = (cx1 + cx2) / 2
        via_y = (cy1 + cy2) / 2
        
        # Determine layers (from surface to plane)
        from_layer = 0  # F.Cu typically
        if islands[i].pads:
            from_layer = islands[i].pads[0].layer
        
        # Validate with DRC oracle if available
        if drc_oracle:
            valid, _ = drc_oracle.can_place_via((via_x, via_y), 0.6, net)
            if not valid:
                # Try alternative positions (offset by 1mm)
                for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                    alt_x, alt_y = via_x + dx, via_y + dy
                    valid, _ = drc_oracle.can_place_via((alt_x, alt_y), 0.6, net)
                    if valid:
                        via_x, via_y = alt_x, alt_y
                        break
        
        via = StitchingVia(
            x=via_x,
            y=via_y,
            from_layer=from_layer,
            to_layer=plane_layer,
            net=net,
            connects_islands=(i, j),
        )
        vias.append(via)
    
    return vias


def analyze_power_net_topology(
    pads: list[PowerPad],
    plane_layer: int = 1,
    drc_oracle: "DRCOracle | None" = None,
) -> tuple[list[Island], list[StitchingVia]]:
    """Full topology analysis for a power net.
    
    1. Detect isolated islands
    2. Compute minimal stitching vias
    
    Args:
        pads: All pads on the power net
        plane_layer: Layer where power plane exists (1 = In1.Cu)
        drc_oracle: Optional for via validation
        
    Returns:
        (islands, stitching_vias)
    """
    islands = detect_islands(pads, connection_radius=0.0)
    vias = compute_stitching_vias(islands, plane_layer, drc_oracle)
    return islands, vias
