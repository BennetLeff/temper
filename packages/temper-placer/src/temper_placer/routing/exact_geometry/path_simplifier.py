"""
Path Simplifier (SDF-Verified Decimation).

Optimizes routing paths by greedily removing redundant nodes while verifying
clearance using the Signed Distance Field (SDF).

Algorithm:
    1. Start with path [P0, P1, ..., Pn]
    2. Try to connect P_i directly to P_{i+2}
    3. Check if segment (P_i, P_{i+2}) is valid using SDF
    4. If valid, remove P_{i+1}
    5. Repeat until no more nodes can be removed
"""

from __future__ import annotations

import numpy as np
from temper_placer.router_v6.astar_pathfinding import RoutePath, RoutePath3D
from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.routing.geometry_fields.sdf_builder import SDFGrid


class PathSimplifier:
    """Greedy path simplifier using SDF for validation."""

    def __init__(
        self,
        sdf_grids: dict[str, SDFGrid],
        step_size_mm: float = 0.1,  # Resolution for sampling checks
        min_clearance_margin: float = 0.0,  # SDF > this value is valid
        occupancy_grids: dict[str, OccupancyGrid] | None = None,  # Dynamic obstacles
    ):
        self.sdf_grids = sdf_grids
        self.step_size_mm = step_size_mm
        self.min_clearance_margin = min_clearance_margin
        self.occupancy_grids = occupancy_grids

    def simplify_path(
        self,
        path: RoutePath | RoutePath3D,
        required_clearance_override: float | None = None,
        net_id: int = -1,  # ID of the net being simplified
    ) -> RoutePath | RoutePath3D:
        """Simplify a route path."""
        # Use instance default if no override
        min_clearance = (
            required_clearance_override
            if required_clearance_override is not None
            else self.min_clearance_margin
        )

        if isinstance(path, RoutePath3D):
            # Decompose 3D path into 2D segments per layer
            simplified_segments = []

            # Group by layer
            if not path.segments:
                return path

            current_layer = None
            current_chunk = []

            for i in range(len(path.segments)):
                x, y, layer = path.segments[i]

                if layer != current_layer:
                    if current_chunk and current_layer:
                        # Simplify previous chunk
                        simp_chunk = self._simplify_2d_segment(
                            current_chunk, current_layer, min_clearance, net_id
                        )
                        simplified_segments.extend(
                            [(p[0], p[1], current_layer) for p in simp_chunk]
                        )

                    # Start new chunk
                    current_layer = layer
                    current_chunk = [(x, y)]
                else:
                    current_chunk.append((x, y))

            # Process last chunk
            if current_chunk and current_layer:
                simp_chunk = self._simplify_2d_segment(
                    current_chunk, current_layer, min_clearance, net_id
                )
                simplified_segments.extend([(p[0], p[1], current_layer) for p in simp_chunk])

            # Filter duplicates from stitching (consecutive identical points)
            final_segments = []
            if simplified_segments:
                final_segments.append(simplified_segments[0])
                for i in range(1, len(simplified_segments)):
                    p_curr = simplified_segments[i]
                    p_prev = final_segments[-1]
                    # Check if different (distance > epsilon)
                    if (p_curr[0] - p_prev[0]) ** 2 + (p_curr[1] - p_prev[1]) ** 2 > 1e-6:
                        final_segments.append(p_curr)

            # Recalculate length
            length = 0.0
            for i in range(len(final_segments) - 1):
                p1 = final_segments[i]
                p2 = final_segments[i + 1]
                length += ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5

            return RoutePath3D(
                net_name=path.net_name,
                segments=final_segments,
                via_positions=path.via_positions,
                path_length=length,
                via_count=path.via_count,
                forced_segment_count=path.forced_segment_count,
            )

        else:
            # 2D Path
            points = path.coordinates
            simp_points = self._simplify_2d_segment(points, path.layer_name, min_clearance, net_id)

            # Recalculate length
            length = 0.0
            for i in range(len(simp_points) - 1):
                p1 = simp_points[i]
                p2 = simp_points[i + 1]
                length += ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5

            return RoutePath(
                net_name=path.net_name,
                coordinates=simp_points,
                layer_name=path.layer_name,
                path_length=length,
                forced_segment_count=path.forced_segment_count,
            )

    def _simplify_2d_segment(
        self, points: list[tuple[float, float]], layer: str, min_clearance: float, net_id: int
    ) -> list[tuple[float, float]]:
        """Greedily remove redundant points if the shortcut is valid."""
        if len(points) < 3:
            return points

        sdf = self.sdf_grids.get(layer)
        if not sdf:
            return points  # Can't check safety, return original

        # Get optional occupancy grid
        occ_grid = self.occupancy_grids.get(layer) if self.occupancy_grids else None

        # Simplification loop
        result = [points[0]]
        current_idx = 0

        while current_idx < len(points) - 1:
            # Look ahead as far as possible
            next_idx = current_idx + 1
            best_idx = next_idx

            max_lookahead = len(points)

            for check_idx in range(current_idx + 2, max_lookahead):
                # Check segment current -> check
                start = points[current_idx]
                end = points[check_idx]

                if self._check_segment_safety(start, end, sdf, min_clearance, occ_grid, net_id):
                    best_idx = check_idx
                else:
                    break

            # Add the best reachable point
            result.append(points[best_idx])
            current_idx = best_idx

            if current_idx == len(points) - 1:
                break

        return result

    def _check_segment_safety(
        self,
        p1: tuple[float, float],
        p2: tuple[float, float],
        sdf: SDFGrid,
        min_clearance: float,
        occupancy_grid: OccupancyGrid | None = None,
        net_id: int = -1,
    ) -> bool:
        """Check if a line segment maintains required clearance and avoids dynamic obstacles."""
        x1, y1 = p1
        x2, y2 = p2

        dist = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        if dist < 1e-6:
            return True

        # Sample points along the segment
        num_samples = int(np.ceil(dist / self.step_size_mm))
        num_samples = max(2, num_samples)  # At least endpoints

        for i in range(num_samples + 1):
            t = i / num_samples
            px = x1 + t * (x2 - x1)
            py = y1 + t * (y2 - y1)

            # 1. Static Clearance Check
            clearance = sdf.get_distance(px, py)
            # print(f"DEBUG: Check ({px:.2f}, {py:.2f}) clearance={clearance:.4f} vs margin={min_clearance}")
            if clearance < min_clearance:
                return False

            # 2. Dynamic Occupancy Check
            if occupancy_grid:
                # Convert world to grid coords
                gx = int((px - occupancy_grid.origin[0]) / occupancy_grid.cell_size)
                gy = int((py - occupancy_grid.origin[1]) / occupancy_grid.cell_size)

                # Bounds check
                if 0 <= gx < occupancy_grid.width_cells and 0 <= gy < occupancy_grid.height_cells:
                    cell_val = occupancy_grid.grid[gy, gx]

                    # If cell is occupied by ANOTHER net (and not free/0)
                    if cell_val != 0 and cell_val != net_id:
                        return False

        return True

        # Sample points along the segment
        num_samples = int(np.ceil(dist / self.step_size_mm))
        num_samples = max(2, num_samples)  # At least endpoints

        for i in range(num_samples + 1):
            t = i / num_samples
            px = x1 + t * (x2 - x1)
            py = y1 + t * (y2 - y1)

            clearance = sdf.get_distance(px, py)

            # Strict check: Must be > margin
            # print(f"DEBUG: Check ({px:.2f}, {py:.2f}) clearance={clearance:.4f} vs margin={min_clearance}")
            if clearance < min_clearance:
                return False

        return True

        # Sample points along the segment
        num_samples = int(np.ceil(dist / self.step_size_mm))
        num_samples = max(2, num_samples)  # At least endpoints

        for i in range(num_samples + 1):
            t = i / num_samples
            px = x1 + t * (x2 - x1)
            py = y1 + t * (y2 - y1)

            clearance = sdf.get_distance(px, py)

            # Strict check: Must be > margin
            print(
                f"DEBUG: Check ({px:.2f}, {py:.2f}) clearance={clearance:.4f} vs margin={self.min_clearance_margin}"
            )
            if clearance < self.min_clearance_margin:
                return False

        return True
