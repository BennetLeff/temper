"""
Differential Pair Routing Engine (Phase 10).

Routes coupled pairs (P/N) by searching in the configuration space of the pair center.
Ensures constant spacing and phase matching.
"""

from __future__ import annotations

import math
from heapq import heappush, heappop
from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.router_v6.astar_pathfinding import RoutePath, _astar_route


class DiffPairRouter:
    def __init__(self, grid: OccupancyGrid):
        self.grid = grid

    def route_pair_with_fanout(
        self,
        start_p: tuple[float, float],
        start_n: tuple[float, float],
        end_p: tuple[float, float],
        end_n: tuple[float, float],
        width: float,
        gap: float,
    ) -> tuple[RoutePath, RoutePath] | None:
        """
        Route pair with fan-out/fan-in legs.
        """
        # 1. Determine Gather Points (Heuristic: 2mm away from pads in routing direction)
        # Assuming horizontal flow Left->Right for prototype
        # Real implementation should detect component orientation.

        # Start Center
        scx = (start_p[0] + start_n[0]) / 2
        scy = (start_p[1] + start_n[1]) / 2

        # End Center
        ecx = (end_p[0] + end_n[0]) / 2
        ecy = (end_p[1] + end_n[1]) / 2

        # Direction
        dx = ecx - scx
        dy = ecy - scy

        # Gather distance
        fanout_dist = 4.0  # mm

        # Normalize direction
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 0.001:
            return None
        ux, uy = dx / dist, dy / dist

        # Gather Center Start/End
        # We move fanout_dist along the vector connecting start/end centers
        g_start_center = (scx + ux * fanout_dist, scy + uy * fanout_dist)
        g_end_center = (ecx - ux * fanout_dist, ecy - uy * fanout_dist)

        # 2. Route Coupled Middle Section
        # This determines exactly where the coupled traces end up
        mid_result = self.route_pair(g_start_center, g_end_center, width, gap)
        if not mid_result:
            return None

        mid_p, mid_n = mid_result

        if not mid_p or not mid_n:
            return None

        # 3. Route Fan-outs (Start -> Mid Start)
        # Mid path starts at index 0
        mid_start_p = mid_p.coordinates[0]
        mid_start_n = mid_n.coordinates[0]

        # Use Dummy Channel Path for _astar_route
        from dataclasses import dataclass

        @dataclass
        class MockChannelPath:
            waypoints: list[tuple[float, float]]
            preferred_layer: str = "F.Cu"  # Assuming F.Cu

        # P Fan-out
        fo_start_p = _astar_route(
            "Fanout_P_Start",
            MockChannelPath([start_p, mid_start_p]),
            self.grid,
            use_lazy_theta_star=True,
        )
        # N Fan-out
        fo_start_n = _astar_route(
            "Fanout_N_Start",
            MockChannelPath([start_n, mid_start_n]),
            self.grid,
            use_lazy_theta_star=True,
        )

        # 4. Route Fan-ins (Mid End -> End)
        mid_end_p = mid_p.coordinates[-1]
        mid_end_n = mid_n.coordinates[-1]

        fo_end_p = _astar_route(
            "Fanout_P_End", MockChannelPath([mid_end_p, end_p]), self.grid, use_lazy_theta_star=True
        )
        fo_end_n = _astar_route(
            "Fanout_N_End", MockChannelPath([mid_end_n, end_n]), self.grid, use_lazy_theta_star=True
        )

        if not (fo_start_p and fo_start_n and fo_end_p and fo_end_n):
            return None

        # 5. Stitch
        # Combine coordinates: FanOut + Mid + FanIn
        # Be careful not to duplicate join points

        full_coords_p = fo_start_p.coordinates[:-1] + mid_p.coordinates + fo_end_p.coordinates[1:]
        full_coords_n = fo_start_n.coordinates[:-1] + mid_n.coordinates + fo_end_n.coordinates[1:]

        # Recalc length
        final_p = RoutePath("Diff_P", full_coords_p, self.grid.layer_name, 0.0)
        final_n = RoutePath("Diff_N", full_coords_n, self.grid.layer_name, 0.0)
        self._calc_len(final_p)
        self._calc_len(final_n)

        return final_p, final_n

    def route_pair(
        self,
        start_center: tuple[float, float],
        end_center: tuple[float, float],
        width: float,
        gap: float,
    ) -> tuple[RoutePath, RoutePath] | None:
        """
        Route a differential pair.

        Args:
            start_center: (x, y) of pair center at start
            end_center: (x, y) of pair center at end
            width: Trace width (individual)
            gap: Edge-to-edge gap -> Center-to-center pitch = width + gap

        Returns:
            (RoutePath P, RoutePath N)
        """
        pitch = width + gap
        half_pitch = pitch / 2.0

        # Convert to grid
        sx, sy = self.grid.world_to_grid(start_center[0], start_center[1])
        gx, gy = self.grid.world_to_grid(end_center[0], end_center[1])

        # A* State: (x, y, orientation)
        # Orientation: 0=Right(+X), 1=Down(+Y), 2=Left(-X), 3=Up(-Y)
        # Start orientation? Try all valid ones or infer from direction.
        start_orientation = 0  # Default right
        if abs(gx - sx) < abs(gy - sy):
            start_orientation = 1 if gy > sy else 3
        else:
            start_orientation = 0 if gx > sx else 2

        start_node = (sx, sy, start_orientation)

        # Priority Queue
        frontier = []
        heappush(frontier, (0, start_node))
        came_from = {start_node: None}
        cost_so_far = {start_node: 0}

        final_node = None

        while frontier:
            _, current = heappop(frontier)
            cx, cy, cori = current

            # Goal Check (approximate position match, orientation doesn't matter)
            if cx == gx and cy == gy:
                final_node = current
                break

            # Generate Moves: Forward, Turn Left, Turn Right
            moves = []

            # Forward
            dx, dy = self._get_dir(cori)
            moves.append((cx + dx, cy + dy, cori, 1.0))

            # Turn Left (Cost penalty)
            left_ori = (cori - 1) % 4
            dx, dy = self._get_dir(left_ori)
            moves.append((cx + dx, cy + dy, left_ori, 1.5))

            # Turn Right
            right_ori = (cori + 1) % 4
            dx, dy = self._get_dir(right_ori)
            moves.append((cx + dx, cy + dy, right_ori, 1.5))

            for nx, ny, nori, move_cost in moves:
                next_node = (nx, ny, nori)

                # Validity Check
                if not self._is_valid_pair(nx, ny, nori, half_pitch):
                    continue

                new_cost = cost_so_far[current] + move_cost

                if next_node not in cost_so_far or new_cost < cost_so_far[next_node]:
                    cost_so_far[next_node] = new_cost
                    # Heuristic: Euclidean to goal
                    h = math.sqrt((gx - nx) ** 2 + (gy - ny) ** 2)
                    priority = new_cost + h
                    heappush(frontier, (priority, next_node))
                    came_from[next_node] = current

        if not final_node:
            return None

        # Reconstruct Path (Center)
        center_path = []
        curr = final_node
        while curr:
            center_path.append(curr)
            curr = came_from[curr]
        center_path.reverse()

        # Generate P and N paths
        coords_p = []
        coords_n = []

        for x, y, ori in center_path:
            wx, wy = self.grid.grid_to_world(x, y)

            # Perpendicular vector
            pdx, pdy = 0.0, 0.0
            if ori == 0:
                pdy = 1.0  # Right -> Perp is Down? Or Up? Let's say Down (+Y)
            elif ori == 1:
                pdx = -1.0  # Down -> Perp is Right? No, Left (-X)
            elif ori == 2:
                pdy = -1.0  # Left -> Perp is Up (-Y)
            elif ori == 3:
                pdx = 1.0  # Up -> Perp is Right (+X)

            # Wait, this rotation logic needs to be consistent.
            # Right Hand Rule? Z is up.
            # Forward X. Left is Y.
            # If Ori=0 (+X), Left is +Y. Right is -Y.

            # Let's fix relative to direction
            # P is "Left", N is "Right"? Or vice versa.
            # Let's use offsets.

            # Unit vector for direction
            dx, dy = self._get_dir(ori)

            # Perpendicular (-dy, dx) is Left. (dy, -dx) is Right.
            lx, ly = -dy, dx
            rx, ry = dy, -dx

            px = wx + lx * half_pitch
            py = wy + ly * half_pitch

            nx = wx + rx * half_pitch
            ny = wy + ry * half_pitch

            coords_p.append((px, py))
            coords_n.append((nx, ny))

        # Create RoutePaths
        # Need net names? Just placeholder.
        path_p = RoutePath("Diff_P", coords_p, self.grid.layer_name, 0.0)
        path_n = RoutePath("Diff_N", coords_n, self.grid.layer_name, 0.0)

        # Calculate lengths
        self._calc_len(path_p)
        self._calc_len(path_n)

        return path_p, path_n

    def _get_dir(self, ori):
        if ori == 0:
            return (1, 0)
        if ori == 1:
            return (0, 1)
        if ori == 2:
            return (-1, 0)
        if ori == 3:
            return (0, -1)
        return (0, 0)

    def _is_valid_pair(self, x, y, ori, half_pitch_mm):
        # Convert center position to world coordinates
        wx, wy = self.grid.grid_to_world(x, y)

        # Get direction vectors
        dx, dy = self._get_dir(ori)
        # Perp (-dy, dx) for left, (dy, -dx) for right
        lx, ly = -dy, dx  # Left
        rx, ry = dy, -dx  # Right

        # P position (left side) - use actual float positions
        px = wx + lx * half_pitch_mm
        py = wy + ly * half_pitch_mm

        # N position (right side) - use actual float positions
        nx = wx + rx * half_pitch_mm
        ny = wy + ry * half_pitch_mm

        # Convert to grid cells for free check
        px_cell, py_cell = self.grid.world_to_grid(px, py)
        nx_cell, ny_cell = self.grid.world_to_grid(nx, ny)

        # Check grid bounds and obstacles at actual positions
        if not self.grid.is_free(px_cell, py_cell):
            return False
        if not self.grid.is_free(nx_cell, ny_cell):
            return False

        return True

    def _calc_len(self, path):
        l = 0.0
        for i in range(len(path.coordinates) - 1):
            p1 = path.coordinates[i]
            p2 = path.coordinates[i + 1]
            l += math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)
        path.path_length = l
