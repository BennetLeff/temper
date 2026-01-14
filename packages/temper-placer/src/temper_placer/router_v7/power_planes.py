"""
Power Plane Synthesis.

Generates copper pours for power nets by subtracting obstacles from the board area
and keeping regions connected to seeds.
"""

from __future__ import annotations

from shapely.geometry import Polygon, MultiPolygon, Point, box
from shapely.ops import unary_union


class PowerPlaneGenerator:
    def __init__(self, board_bounds: tuple[float, float, float, float]):
        """
        Args:
            board_bounds: (min_x, min_y, max_x, max_y)
        """
        self.board_poly = box(*board_bounds)
        self.obstacles = []

    def add_obstacle(self, obstacle: Polygon | MultiPolygon):
        """Add an obstacle that the plane must avoid."""
        self.obstacles.append(obstacle)

    def generate_plane(
        self, seeds: list[tuple[float, float]], clearance: float = 0.2
    ) -> list[Polygon]:
        """
        Generate plane polygons.

        Args:
            seeds: List of (x, y) coordinates that must be connected.
            clearance: Clearance around obstacles.

        Returns:
            List of Polygons representing the plane.
        """
        # 1. Combine Obstacles and Buffer
        if not self.obstacles:
            buffered_obstacles = Polygon()
        else:
            # Buffer each obstacle
            buffered = [o.buffer(clearance) for o in self.obstacles]
            buffered_obstacles = unary_union(buffered)

        # 2. Subtract from Board
        free_space = self.board_poly.difference(buffered_obstacles)

        # 3. Filter Regions
        # free_space might be MultiPolygon
        if isinstance(free_space, Polygon):
            regions = [free_space]
        else:
            regions = list(free_space.geoms)

        # Keep regions containing at least one seed
        # (Or should we keep all connected to ANY seed?
        # Yes, we want the plane to cover all reachable area)

        valid_regions = []
        for region in regions:
            # Check if any seed is inside
            # Use distance < epsilon to handle edge cases
            for seed in seeds:
                p = Point(seed)
                if region.contains(p) or region.distance(p) < 0.01:
                    valid_regions.append(region)
                    break

        return valid_regions
