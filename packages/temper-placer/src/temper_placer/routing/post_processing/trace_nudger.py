"""
Post-processing: Force-directed path smoothing to fix DRC violations.

Uses repulsive forces to nudge paths away from obstacles and each other
while preserving pad connectivity.
"""
from dataclasses import dataclass
import math
from typing import Optional

from temper_placer.router_v6.astar_pathfinding import RoutePath, RoutePath3D
from temper_placer.routing.push_shove import (
    Path, Segment, segment_sdf, detect_collision
)


@dataclass
class SmoothingResult:
    """Result of force-directed smoothing."""
    smoothed_paths: dict[str, RoutePath]
    violations_before: int
    violations_after: int
    iterations_used: int
    converged: bool


def distance_point_to_segment(
    point: tuple[float, float],
    seg: Segment
) -> tuple[float, tuple[float, float]]:
    """
    Compute distance from point to line segment and closest point.

    Returns:
        (distance, closest_point_on_segment)
    """
    px, py = point
    ax, ay = seg.start
    bx, by = seg.end

    bax = bx - ax
    bay = by - ay
    pax = px - ax
    pay = py - ay

    ba_len_sq = bax * bax + bay * bay

    if ba_len_sq < 1e-10:  # Degenerate
        dist = math.sqrt(pax * pax + pay * pay)
        return dist, (ax, ay)

    t = (pax * bax + pay * bay) / ba_len_sq
    t = max(0.0, min(1.0, t))

    closest_x = ax + t * bax
    closest_y = ay + t * bay

    dx = px - closest_x
    dy = py - closest_y
    dist = math.sqrt(dx * dx + dy * dy)

    return dist, (closest_x, closest_y)


def compute_repulsive_force(
    point: tuple[float, float],
    other_paths: list[RoutePath],
    clearance: float,
    force_range: float = 0.5  # mm
) -> tuple[float, float]:
    """
    Compute repulsive force on point from nearby path segments.

    Args:
        point: Position to compute force at
        other_paths: Paths that repel this point
        clearance: Required clearance distance
        force_range: Distance at which force becomes negligible

    Returns:
        (force_x, force_y) force vector
    """
    total_fx, total_fy = 0.0, 0.0

    for other_path in other_paths:
        coords = other_path.coordinates
        for i in range(len(coords) - 1):
            seg = Segment(coords[i], coords[i + 1])

            dist, closest = distance_point_to_segment(point, seg)

            if dist < force_range:
                # Direction away from segment
                if dist < 1e-6:
                    # Coincident - use arbitrary perpendicular direction
                    dx, dy = closest[1] - closest[0], -(closest[0] - point[0])
                    norm = math.sqrt(dx*dx + dy*dy)
                    if norm > 1e-6:
                        dir_x, dir_y = dx / norm, dy / norm
                    else:
                        dir_x, dir_y = 1.0, 0.0
                else:
                    dir_x = (point[0] - closest[0]) / dist
                    dir_y = (point[1] - closest[1]) / dist

                # Force magnitude: inverse square law with clearance threshold
                violation = max(clearance - dist, 0.0)
                if violation > 0:
                    # Strong force if violating clearance
                    magnitude = 10.0 * violation
                else:
                    # Weak force as warning
                    magnitude = 0.1 * (1.0 / max(dist, 0.01)**2)

                total_fx += dir_x * magnitude
                total_fy += dir_y * magnitude

    return (total_fx, total_fy)


def smooth_path_force_directed(
    path: RoutePath,
    other_paths: list[RoutePath],
    clearance: float,
    iterations: int = 100,
    step_size: float = 0.005,  # mm per iteration
    damping: float = 0.9,
    convergence_threshold: float = 0.001  # mm
) -> tuple[RoutePath, bool]:
    """
    Smooth path using force-directed relaxation.

    Moves each interior vertex away from nearby obstacles/paths while
    keeping endpoints fixed (pad connectivity).

    Args:
        path: Path to smooth
        other_paths: Paths that repel this one
        clearance: Required clearance
        iterations: Max iterations
        step_size: Gradient descent step size
        damping: Velocity damping (0-1)
        convergence_threshold: Stop if max vertex movement < this

    Returns:
        (smoothed_path, converged)
    """
    coords = list(path.coordinates)
    velocities = [(0.0, 0.0) for _ in coords]

    # Fix endpoints (pads)
    first_coord = coords[0]
    last_coord = coords[-1]

    converged = False

    for iter_num in range(iterations):
        max_movement = 0.0

        # Update interior vertices
        for i in range(1, len(coords) - 1):
            force_x, force_y = compute_repulsive_force(
                coords[i], other_paths, clearance
            )

            # Add spring force to neighbors (preserve connectivity)
            prev = coords[i - 1]
            next_coord = coords[i + 1]

            # Spring to prev
            to_prev_x = prev[0] - coords[i][0]
            to_prev_y = prev[1] - coords[i][1]
            dist_prev = math.sqrt(to_prev_x**2 + to_prev_y**2)
            if dist_prev > clearance * 0.5:
                # Pull back if stretching too far
                spring_fx = to_prev_x * 0.5
                spring_fy = to_prev_y * 0.5
                force_x += spring_fx
                force_y += spring_fy

            # Spring to next
            to_next_x = next_coord[0] - coords[i][0]
            to_next_y = next_coord[1] - coords[i][1]
            dist_next = math.sqrt(to_next_x**2 + to_next_y**2)
            if dist_next > clearance * 0.5:
                spring_fx = to_next_x * 0.5
                spring_fy = to_next_y * 0.5
                force_x += spring_fx
                force_y += spring_fy

            # Update velocity with damping
            vx, vy = velocities[i]
            vx = vx * damping + force_x * step_size
            vy = vy * damping + force_y * step_size
            velocities[i] = (vx, vy)

            # Update position
            new_x = coords[i][0] + vx
            new_y = coords[i][1] + vy
            movement = math.sqrt(vx**2 + vy**2)
            max_movement = max(max_movement, movement)

            coords[i] = (new_x, new_y)

        # Restore endpoints
        coords[0] = first_coord
        coords[-1] = last_coord

        # Check convergence
        if max_movement < convergence_threshold:
            converged = True
            break

    # Compute new path length
    new_length = sum(
        math.sqrt((coords[i+1][0] - coords[i][0])**2 +
                  (coords[i+1][1] - coords[i][1])**2)
        for i in range(len(coords) - 1)
    )

    return RoutePath(
        net_name=path.net_name,
        coordinates=coords,
        layer_name=path.layer_name,
        path_length=new_length,
        forced_segment_count=path.forced_segment_count
    ), converged


def smooth_all_paths(
    routed_paths: dict[str, RoutePath],
    design_rules,
    max_iterations: int = 200
) -> SmoothingResult:
    """
    Apply force-directed smoothing to all routed paths.

    Args:
        routed_paths: Dict of net_name -> RoutePath
        design_rules: Design rules with clearance
        max_iterations: Max iterations per path

    Returns:
        SmoothingResult with before/after statistics
    """
    clearance = design_rules.default_clearance_mm

    # Count initial violations
    violations_before = 0
    for net1, path1 in routed_paths.items():
        for net2, path2 in routed_paths.items():
            if net1 >= net2:
                continue
            # Convert to push_shove Path for collision check
            p1 = path_to_push_shove(path1)
            p2 = path_to_push_shove(path2)
            if detect_collision(p1, p2):
                violations_before += 1

    # Smooth each path
    smoothed = {}
    total_iters = 0
    all_converged = True

    import sys
    total_paths = len(routed_paths)
    for idx, (net_name, path) in enumerate(routed_paths.items(), 1):
        print(f"      Smoothing {net_name} ({idx}/{total_paths})...", flush=True)
        sys.stdout.flush()
        other_paths = [p for n, p in routed_paths.items() if n != net_name]

        smoothed_path, converged = smooth_path_force_directed(
            path, other_paths, clearance,
            iterations=max_iterations,
            step_size=0.005
        )

        smoothed[net_name] = smoothed_path
        all_converged = all_converged and converged

    # Count final violations
    violations_after = 0
    for net1, path1 in smoothed.items():
        for net2, path2 in smoothed.items():
            if net1 >= net2:
                continue
            p1 = path_to_push_shove(path1)
            p2 = path_to_push_shove(path2)
            if detect_collision(p1, p2):
                violations_after += 1

    return SmoothingResult(
        smoothed_paths=smoothed,
        violations_before=violations_before,
        violations_after=violations_after,
        iterations_used=max_iterations,
        converged=all_converged
    )


def path_to_push_shove(route_path: RoutePath) -> Path:
    """Convert RoutePath to push_shove.Path for collision detection."""
    segments = [
        Segment(route_path.coordinates[i], route_path.coordinates[i+1])
        for i in range(len(route_path.coordinates) - 1)
    ]
    return Path(
        segments=segments,
        width=0.2,  # Default trace width
        clearance=0.2,  # Default clearance
        net=route_path.net_name
    )
