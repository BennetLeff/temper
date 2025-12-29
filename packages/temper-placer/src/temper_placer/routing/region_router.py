"""
Quadtree-based region decomposition for hierarchical PCB routing.

This module implements spatial partitioning with ghost cell boundaries
to enable parallel-friendly routing of subregions.

Key classes:
- QuadTreeNode: A node in the quadtree (either internal or leaf)
- RoutingQuadTree: The complete quadtree with halo exchange
- RegionRouter: High-level API for region-based routing
"""

from dataclasses import dataclass, field
from typing import Iterator, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from temper_placer.routing.maze_router import GridCell, MazeRouter


@dataclass
class QuadTreeNode:
    """A node in the routing quadtree.
    
    Attributes:
        bounds: (x_min, y_min, x_max, y_max) defining the region
        children: List of 4 child nodes (SW, SE, NW, NE), or None for leaves
        halo: Number of ghost cells to copy from neighbors
        
    Ghost cell halos (populated after exchange_halos()):
        north_halo, south_halo, east_halo, west_halo: numpy arrays
    """
    bounds: tuple[int, int, int, int]  # x_min, y_min, x_max, y_max
    children: list["QuadTreeNode"] | None = None
    halo: int = 3
    
    # Ghost cell data from neighbors (populated by exchange_halos)
    north_halo: np.ndarray | None = None
    south_halo: np.ndarray | None = None
    east_halo: np.ndarray | None = None
    west_halo: np.ndarray | None = None
    
    # Local occupancy data for this region
    local_occupancy: np.ndarray | None = None
    
    @property
    def is_leaf(self) -> bool:
        """True if this is a leaf node (no children)."""
        return self.children is None
    
    @property
    def width(self) -> int:
        return self.bounds[2] - self.bounds[0]
    
    @property
    def height(self) -> int:
        return self.bounds[3] - self.bounds[1]
    
    def contains_point(self, x: int, y: int) -> bool:
        """Check if a point is within this node's bounds."""
        x0, y0, x1, y1 = self.bounds
        return x0 <= x < x1 and y0 <= y < y1


class RoutingQuadTree:
    """Quadtree spatial decomposition for region-based routing.
    
    Divides the routing grid into regions that can be routed independently,
    with ghost cells at boundaries to allow path continuity.
    
    Args:
        grid_size: (width, height) of the routing grid
        min_region_size: Minimum dimension for leaf nodes
        halo: Number of ghost cells at boundaries
    """
    
    def __init__(
        self,
        grid_size: tuple[int, int],
        min_region_size: int = 20,
        halo: int = 3,
    ):
        self.grid_size = grid_size
        self.min_region_size = min_region_size
        self.halo = halo
        
        # Global occupancy array (set by set_occupancy)
        self._occupancy: np.ndarray | None = None
        
        # Build the tree
        self.root = self._build_node(0, 0, grid_size[0], grid_size[1])
    
    def _build_node(self, x0: int, y0: int, x1: int, y1: int) -> QuadTreeNode:
        """Recursively build quadtree nodes."""
        width = x1 - x0
        height = y1 - y0
        
        # Leaf condition: both dimensions below min size
        if width <= self.min_region_size and height <= self.min_region_size:
            return QuadTreeNode(bounds=(x0, y0, x1, y1), halo=self.halo)
        
        # Subdivide into 4 children
        mid_x = (x0 + x1) // 2
        mid_y = (y0 + y1) // 2
        
        children = [
            self._build_node(x0, y0, mid_x, mid_y),      # SW (bottom-left)
            self._build_node(mid_x, y0, x1, mid_y),      # SE (bottom-right)
            self._build_node(x0, mid_y, mid_x, y1),      # NW (top-left)
            self._build_node(mid_x, mid_y, x1, y1),      # NE (top-right)
        ]
        
        return QuadTreeNode(
            bounds=(x0, y0, x1, y1),
            children=children,
            halo=self.halo,
        )
    
    def leaves(self) -> Iterator[QuadTreeNode]:
        """Iterate over all leaf nodes in the tree."""
        def _collect_leaves(node: QuadTreeNode) -> Iterator[QuadTreeNode]:
            if node.is_leaf:
                yield node
            else:
                for child in node.children:
                    yield from _collect_leaves(child)
        
        yield from _collect_leaves(self.root)
    
    def leaf_count(self) -> int:
        """Count the number of leaf nodes."""
        return sum(1 for _ in self.leaves())
    
    def set_occupancy(self, occupancy: np.ndarray) -> None:
        """Set the global occupancy array for halo exchange.
        
        Args:
            occupancy: 2D or 3D numpy array of occupancy data
        """
        self._occupancy = occupancy
        
        # Distribute to leaves
        for leaf in self.leaves():
            x0, y0, x1, y1 = leaf.bounds
            if occupancy.ndim == 2:
                leaf.local_occupancy = occupancy[x0:x1, y0:y1].copy()
            else:
                leaf.local_occupancy = occupancy[x0:x1, y0:y1, :].copy()
    
    def exchange_halos(self) -> None:
        """Exchange ghost cells between adjacent leaves.
        
        Populates north_halo, south_halo, east_halo, west_halo for each leaf.
        """
        if self._occupancy is None:
            raise ValueError("Must call set_occupancy() before exchange_halos()")
        
        occupancy = self._occupancy
        grid_w, grid_h = self.grid_size
        
        for leaf in self.leaves():
            x0, y0, x1, y1 = leaf.bounds
            halo = leaf.halo
            
            # East halo: cells just beyond x1
            if x1 < grid_w:
                halo_x1 = min(x1 + halo, grid_w)
                if occupancy.ndim == 2:
                    leaf.east_halo = occupancy[x1:halo_x1, y0:y1].copy()
                else:
                    leaf.east_halo = occupancy[x1:halo_x1, y0:y1, :].copy()
            else:
                leaf.east_halo = None
            
            # West halo: cells just before x0
            if x0 > 0:
                halo_x0 = max(x0 - halo, 0)
                if occupancy.ndim == 2:
                    leaf.west_halo = occupancy[halo_x0:x0, y0:y1].copy()
                else:
                    leaf.west_halo = occupancy[halo_x0:x0, y0:y1, :].copy()
            else:
                leaf.west_halo = None
            
            # North halo: cells just beyond y1
            if y1 < grid_h:
                halo_y1 = min(y1 + halo, grid_h)
                if occupancy.ndim == 2:
                    leaf.north_halo = occupancy[x0:x1, y1:halo_y1].copy()
                else:
                    leaf.north_halo = occupancy[x0:x1, y1:halo_y1, :].copy()
            else:
                leaf.north_halo = None
            
            # South halo: cells just before y0
            if y0 > 0:
                halo_y0 = max(y0 - halo, 0)
                if occupancy.ndim == 2:
                    leaf.south_halo = occupancy[x0:x1, halo_y0:y0].copy()
                else:
                    leaf.south_halo = occupancy[x0:x1, halo_y0:y0, :].copy()
            else:
                leaf.south_halo = None
    
    def find_leaf(self, x: int, y: int) -> QuadTreeNode | None:
        """Find the leaf node containing a point."""
        def _search(node: QuadTreeNode) -> QuadTreeNode | None:
            if not node.contains_point(x, y):
                return None
            if node.is_leaf:
                return node
            for child in node.children:
                result = _search(child)
                if result is not None:
                    return result
            return None
        
        return _search(self.root)


def route_region(
    leaf: QuadTreeNode,
    start: tuple[int, int],
    end: tuple[int, int],
    halo: int = 3,
    num_layers: int = 1,
) -> "list[GridCell] | None":
    """Route a path within a single region using A*.
    
    Args:
        leaf: The quadtree leaf node to route within
        start: (x, y) start position
        end: (x, y) end position
        halo: Ghost cell width for expanded bounds
        num_layers: Number of routing layers
    
    Returns:
        List of GridCells forming the path, or None if no path found
    """
    from temper_placer.routing.maze_router import MazeRouter
    
    x0, y0, x1, y1 = leaf.bounds
    
    # Expand bounds by halo
    region_x0 = max(0, x0 - halo)
    region_y0 = max(0, y0 - halo)
    region_x1 = x1 + halo  # Will be clipped by router
    region_y1 = y1 + halo
    
    # Create local router for this region
    region_width = region_x1 - region_x0
    region_height = region_y1 - region_y0
    
    router = MazeRouter(
        grid_size=(region_width, region_height),
        num_layers=num_layers,
        origin=(region_x0, region_y0),
    )
    
    # Translate coordinates to local
    local_start = (start[0] - region_x0, start[1] - region_y0)
    local_end = (end[0] - region_x0, end[1] - region_y0)
    
    # Route
    path = router.find_path(local_start, local_end, layer=0)
    
    if path is None:
        return None
    
    # Translate back to global coordinates
    from temper_placer.routing.maze_router import GridCell
    global_path = [
        GridCell(cell.x + region_x0, cell.y + region_y0, cell.layer)
        for cell in path
    ]
    
    return global_path


def stitch_paths(
    region_paths: dict[str, "list[GridCell]"],
    net_name: str,
) -> "list[GridCell]":
    """Merge paths from multiple regions for the same net.
    
    Args:
        region_paths: Dict mapping region key to path for that region
        net_name: Name of the net being stitched
    
    Returns:
        Merged path with duplicates removed
    """
    from temper_placer.routing.maze_router import GridCell
    
    # Collect all relevant paths
    net_paths = [
        path for key, path in region_paths.items()
        if key.startswith(net_name)
    ]
    
    if not net_paths:
        return []
    
    if len(net_paths) == 1:
        return net_paths[0]
    
    # Merge paths, removing duplicates while preserving order
    seen = set()
    merged = []
    
    for path in net_paths:
        for cell in path:
            key = (cell.x, cell.y, cell.layer)
            if key not in seen:
                seen.add(key)
                merged.append(cell)
    
    return merged


class RegionRouter:
    """High-level API for region-based routing.
    
    Wraps the quadtree and provides route_net() for single nets
    and route_all_nets() for entire netlists.
    """
    
    def __init__(
        self,
        grid_size: tuple[int, int],
        min_region_size: int = 20,
        halo: int = 3,
        num_layers: int = 1,
    ):
        self.grid_size = grid_size
        self.tree = RoutingQuadTree(grid_size, min_region_size, halo)
        self.halo = halo
        self.num_layers = num_layers
    
    def route_net(
        self,
        start: tuple[int, int],
        end: tuple[int, int],
    ) -> "list[GridCell] | None":
        """Route a single net using region decomposition.
        
        If the net spans multiple regions, routes each segment
        and stitches them together.
        """
        # Find which regions contain start and end
        start_leaf = self.tree.find_leaf(start[0], start[1])
        end_leaf = self.tree.find_leaf(end[0], end[1])
        
        if start_leaf is None or end_leaf is None:
            return None
        
        # Simple case: both in same region
        if start_leaf is end_leaf:
            return route_region(start_leaf, start, end, self.halo, self.num_layers)
        
        # Multi-region: route through each region
        # For now, fall back to global routing for cross-region nets
        from temper_placer.routing.maze_router import MazeRouter
        
        router = MazeRouter(grid_size=self.grid_size, num_layers=self.num_layers)
        return router.find_path(start, end, layer=0)
