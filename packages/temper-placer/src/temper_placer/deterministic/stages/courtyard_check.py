from dataclasses import dataclass
from typing import Dict, List, Tuple
from ..state import BoardState
from .base import Stage
from ..geometry.courtyard import Courtyard, check_overlap


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

    courtyards: Dict[str, Courtyard]
    board_width: float = 100.0  # Board width in mm
    board_height: float = 150.0  # Board height in mm
    margin: float = 5.0  # Keep components this far from board edges
    max_iterations: int = 500
    nudge_step: float = 0.2  # Increased from 0.1

    @property
    def name(self) -> str:
        return "courtyard_check"

    def _clamp_position(self, pos: Tuple[float, float]) -> Tuple[float, float]:
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
        component_refs = list(placements.keys())

        # Iterative resolution
        for _ in range(self.max_iterations):
            collisions = self._find_collisions(placements)

            # Apply repulsive force
            import logging

            logger = logging.getLogger(__name__)
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

        return replace(state, placements=tuple(placements.items()))

    def _find_collisions(self, placements: Dict[str, Tuple[float, float]]) -> List[Tuple[str, str]]:
        collisions = []
        refs = list(placements.keys())

        for i in range(len(refs)):
            ref1 = refs[i]
            if ref1 not in self.courtyards:
                continue

            for j in range(i + 1, len(refs)):
                ref2 = refs[j]
                if ref2 not in self.courtyards:
                    continue

                # Check overlap
                # TODO: Get rotation from state (assume 0 for now as per pipeline)
                if check_overlap(
                    self.courtyards[ref1],
                    placements[ref1],
                    0,
                    self.courtyards[ref2],
                    placements[ref2],
                    0,
                ):
                    collisions.append((ref1, ref2))

        return collisions
