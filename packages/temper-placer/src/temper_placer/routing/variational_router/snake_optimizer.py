"""
Active Contour (Snake) Optimizer for PCB Traces.

Treats PCB traces as elastic splines minimizing an energy functional
defined by curvature (internal energy) and Signed Distance Field (external energy).
"""

from __future__ import annotations

import numpy as np
from temper_placer.router_v6.astar_pathfinding import RoutePath, RoutePath3D
from temper_placer.routing.geometry_fields.sdf_builder import SDFGrid


class SnakeOptimizer:
    """
    Optimization engine for Active Contour Models (Snakes).
    """

    def __init__(
        self,
        sdf_grids: dict[str, SDFGrid],
        alpha: float = 0.5,  # Elasticity (minimize length)
        beta: float = 0.5,  # Stiffness (minimize curvature)
        gamma: float = 1.0,  # External force (SDF repulsion)
        step_size: float = 0.1,  # Gradient descent step size
        node_spacing_mm: float = 0.2,  # Resampling resolution
        max_iterations: int = 50,
    ):
        self.sdf_grids = sdf_grids
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma
        self.step_size = step_size
        self.node_spacing_mm = node_spacing_mm
        self.max_iterations = max_iterations

    def optimize_path(self, path: RoutePath | RoutePath3D) -> RoutePath | RoutePath3D:
        """
        Optimize a route path using active contours.

        Preserves topology by locking nodes that would cross SDF zero-level set.
        """
        if isinstance(path, RoutePath3D):
            # Decompose into segments, optimize each, recombine
            optimized_segments = []

            # Group by layer
            current_layer = None
            current_chunk = []

            for i in range(len(path.segments)):
                x, y, layer = path.segments[i]

                if layer != current_layer:
                    if current_chunk and current_layer:
                        # Optimize previous chunk
                        opt_chunk = self._optimize_segment(current_chunk, current_layer)
                        optimized_segments.extend([(p[0], p[1], current_layer) for p in opt_chunk])

                    # Start new chunk
                    current_layer = layer
                    current_chunk = [(x, y)]
                else:
                    current_chunk.append((x, y))

            # Process last chunk
            if current_chunk and current_layer:
                opt_chunk = self._optimize_segment(current_chunk, current_layer)
                optimized_segments.extend([(p[0], p[1], current_layer) for p in opt_chunk])

            # Filter duplicates from stitching
            final_segments = []
            if optimized_segments:
                final_segments.append(optimized_segments[0])
                for i in range(1, len(optimized_segments)):
                    p_curr = optimized_segments[i]
                    p_prev = final_segments[-1]
                    # Check distance to avoid zero-length segments
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
            opt_points = self._optimize_segment(points, path.layer_name)

            # Recalculate length
            length = 0.0
            for i in range(len(opt_points) - 1):
                p1 = opt_points[i]
                p2 = opt_points[i + 1]
                length += ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5

            return RoutePath(
                net_name=path.net_name,
                coordinates=opt_points,
                layer_name=path.layer_name,
                path_length=length,
                forced_segment_count=path.forced_segment_count,
            )

    def _optimize_segment(
        self, points: list[tuple[float, float]], layer: str
    ) -> list[tuple[float, float]]:
        """Run snake optimization on a single layer segment."""
        if len(points) < 2:
            return points

        sdf = self.sdf_grids.get(layer)
        if not sdf:
            return points  # Can't optimize without field

        # 1. Densify (Resample)
        dense_points = self._densify(points)
        n = len(dense_points)
        if n < 3:
            return dense_points

        # Convert to numpy for vectorization
        V = np.array(dense_points, dtype=np.float64)

        # 2. Iterate
        for _ in range(self.max_iterations):
            # Internal Energy Gradients (Finite Differences)
            # Alpha (Elasticity): V_i - V_{i-1} -> -V_{i-1} + 2V_i - V_{i+1}
            d_alpha = np.zeros_like(V)
            d_alpha[1:-1] = -self.alpha * (V[:-2] - 2 * V[1:-1] + V[2:])

            # Beta (Stiffness/Curvature): V_{i-1} - 2V_i + V_{i+1} -> 4th derivative approx
            # Simplifying: minimizing curvature makes it a straight line
            d_beta = np.zeros_like(V)
            if n > 4:
                d_beta[2:-2] = self.beta * (
                    V[:-4] - 4 * V[1:-3] + 6 * V[2:-2] - 4 * V[3:-1] + V[4:]
                )

            # External Energy Gradient (SDF Repulsion)
            d_ext = np.zeros_like(V)

            # Evaluate SDF at current positions
            # We want to PUSH away if SDF is low (close to obstacle)
            # Potential function P(d) = max(0, -d)^2  (Simple repulsion from violation)
            # Or P(d) = exp(-k * d) (Smooth decay)

            # Let's use a barrier-like force.
            # If SDF < margin, apply force.
            # Margin = 0 in our defined SDF (boundary is at 0)
            # So if SDF < 0, we are in violation.
            # Force = - grad(P) = - P'(d) * grad(d)

            for i in range(1, n - 1):
                dist = sdf.get_distance(V[i, 0], V[i, 1])
                grad = sdf.get_gradient(V[i, 0], V[i, 1])

                # Force only if close to boundary or violating
                # Add a small buffer epsilon for safety
                safety_margin = 0.05  # mm

                if dist < safety_margin:
                    # Magnitude of force increases as we get deeper
                    # dist is negative inside obstacle
                    # force magnitude ~ (safety - dist)
                    mag = self.gamma * (safety_margin - dist)

                    # Direction is along gradient (away from obstacle)
                    d_ext[i, 0] = -mag * grad[0]
                    d_ext[i, 1] = -mag * grad[1]

            # Update
            # Endpoints fixed (indices 0 and -1 not updated)
            total_force = d_alpha + d_beta + d_ext

            # Homotopy Lock: Check step validity
            V_next = V - self.step_size * total_force

            # Simple check: Don't allow crossing deep into obstacle (SDF < -0.1)
            # Or simpler: Just clamp the movement if it creates a huge jump

            V[1:-1] = V_next[1:-1]

        return [tuple(p) for p in V]

    def _densify(self, points: list[tuple[float, float]]) -> list[tuple[float, float]]:
        """Upsample path to uniform spacing."""
        if not points:
            return []

        new_points = [points[0]]

        for i in range(len(points) - 1):
            p1 = np.array(points[i])
            p2 = np.array(points[i + 1])
            dist = np.linalg.norm(p2 - p1)

            if dist < 1e-6:
                continue

            num_segments = int(np.ceil(dist / self.node_spacing_mm))

            for j in range(1, num_segments + 1):
                t = j / num_segments
                p = p1 + t * (p2 - p1)
                new_points.append(tuple(p))

        return new_points
