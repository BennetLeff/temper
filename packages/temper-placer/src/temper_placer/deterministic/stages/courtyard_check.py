from dataclasses import dataclass

from ..geometry.courtyard import Courtyard
from ..state import BoardState
from .base import Stage


@dataclass
class CourtyardCheckStage(Stage):
    """
    Checks for and resolves component courtyard overlaps (Solder Mask Bridges).

    This stage runs after placement to ensure that no two components have colliding
    courtyards. If collisions are found, it nudges components apart.

    Board boundary clamping (DRC-FIX-4):
    After each nudge, positions are clamped to stay within board boundaries.
    This prevents components from drifting outside the board area during
    overlap resolution, which would cause via_dangling DRC violations.
    """

    courtyards: dict[str, Courtyard]
    board_width: float = 100.0  # Board width in mm
    board_height: float = 150.0  # Board height in mm
    margin: float = 5.0  # Keep components this far from board edges
    max_iterations: int = 500
    nudge_step: float = 0.2  # Increased from 0.1

    @property
    def name(self) -> str:
        return "courtyard_check"

    def _clamp_position(self, pos: tuple[float, float]) -> tuple[float, float]:
        """Clamp position to valid board area within margins.

        Args:
            pos: (x, y) position in mm

        Returns:
            Clamped (x, y) position within [margin, board_dim - margin]
        """
        x_min = self.margin
        x_max = self.board_width - self.margin
        y_min = self.margin
        y_max = self.board_height - self.margin

        return (max(x_min, min(x_max, pos[0])), max(y_min, min(y_max, pos[1])))

    def run(self, state: BoardState) -> BoardState:
        if not state.placements:
            return state

        # Convert placements to mutable dict
        placements = dict(state.placements)
        list(placements.keys())

        # Iterative resolution
        for _ in range(self.max_iterations):
            collisions = self._find_collisions(placements)

            # Apply repulsive force
            import logging

            logging.getLogger(__name__)
            if len(collisions) > 0:
                print(
                    f"DEBUG: CourtyardCheck Iteration {_}: Found {len(collisions)} overlapping pairs"
                )

            for ref1, ref2 in collisions:
                pos1 = placements[ref1]
                pos2 = placements[ref2]

                # Vector from c1 to c2
                dx = pos2[0] - pos1[0]
                dy = pos2[1] - pos1[1]
                dist = (dx**2 + dy**2) ** 0.5

                if dist < 1e-6:
                    # Overlapping centers - nudge strictly x/y
                    dx, dy = 1.0, 0.0
                    dist = 1.0

                # Add small random noise to break limit cycles
                import random

                noise_x = (random.random() - 0.5) * 0.05
                noise_y = (random.random() - 0.5) * 0.05

                # Normalize force
                fx = (dx / dist) * self.nudge_step + noise_x
                fy = (dy / dist) * self.nudge_step + noise_y

                # decay nudge step slightly? No, keep constant pressure for now

                # Move ref1 away from ref2
                # Check if locked? (Assuming dynamic components for now)

                # Move ref1
                placements[ref1] = (pos1[0] - fx, pos1[1] - fy)
                # Move ref2
                placements[ref2] = (pos2[0] + fx, pos2[1] + fy)

                # Clamp positions to board bounds (DRC-FIX-4)
                # This prevents components from drifting outside the board area
                placements[ref1] = self._clamp_position(placements[ref1])
                placements[ref2] = self._clamp_position(placements[ref2])

        # Final check
        final_collisions = self._find_collisions(placements)
        if final_collisions:
            print(
                f"DEBUG: CourtyardCheck Failed to resolve {len(final_collisions)} pairs after {self.max_iterations} iterations"
            )
            for r1, r2 in final_collisions:
                print(f"DEBUG: Conflict: {r1} <-> {r2}")

        # Update state
        from dataclasses import replace

        return replace(state, placements=frozenset(placements.items()))

    def _find_collisions(self, placements: dict[str, tuple[float, float]]) -> list[tuple[str, str]]:
        """Find courtyard collisions using spatial indexing for O(n log n) performance.

        Optimization: Use R-tree spatial index to avoid O(n²) pairwise checks.
        Also cache transformed polygons to avoid repeated Shapely operations.
        """
        collisions: list[tuple[str, str]] = []
        refs = list(placements.keys())

        # Cache transformed polygons (major optimization - avoids 1M+ Shapely calls)
        transformed_polys = {}
        for ref in refs:
            if ref in self.courtyards:
                pos = placements[ref]
                # Assume rotation = 0 (as per pipeline comment)
                transformed_polys[ref] = self.courtyards[ref].get_global_polygon(pos[0], pos[1], 0)

        # Build spatial index using bounding boxes
        from shapely.strtree import STRtree

        # Create list of (polygon, ref) pairs for STRtree
        polys_with_refs = [(poly, ref) for ref, poly in transformed_polys.items()]

        if not polys_with_refs:
            return collisions

        # Build R-tree index
        tree = STRtree([poly for poly, _ in polys_with_refs])

        # Query for intersections (O(n log n) instead of O(n²))
        checked_pairs = set()
        for poly, ref1 in polys_with_refs:
            # Query spatial index for candidates (uses bounding box)
            candidates = tree.query(poly)

            for candidate_poly in candidates:
                # Find ref2 for this polygon
                ref2 = None
                for p, r in polys_with_refs:
                    if p is candidate_poly:
                        ref2 = r
                        break

                if ref2 is None or ref1 == ref2:
                    continue

                # Avoid checking same pair twice
                pair = tuple(sorted([ref1, ref2]))
                if pair in checked_pairs:
                    continue
                checked_pairs.add(pair)

                # Exact intersection test (after bounding box filter)
                if poly.intersects(candidate_poly) and not poly.touches(candidate_poly):
                    collisions.append((ref1, ref2))

        return collisions
