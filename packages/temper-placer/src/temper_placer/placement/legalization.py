"""
Placement Legalizer.

Resolves component overlaps using force-directed displacement.
"""

from __future__ import annotations

import math

from temper_placer.placement.audit import PlacementAuditor
from temper_placer.router_v6.stage0_data import ParsedPCB


class Legalizer:
    def __init__(self, pcb: ParsedPCB, step_size: float = 0.5, max_iterations: int = 100):
        self.pcb = pcb
        self.step_size = step_size
        self.max_iterations = max_iterations
        self.auditor = PlacementAuditor(pcb)

    def legalize(self) -> bool:
        """
        Run legalization loop. Returns True if converged (no overlaps).
        """
        for _i in range(self.max_iterations):
            # 1. Check collisions
            # Re-build courtyards every step because positions change
            self.auditor.courtyards = self.auditor._build_courtyards()
            collisions = self.auditor.check_collisions()

            if not collisions:
                return True

            # 2. Apply forces
            # Accumulate displacement vectors
            displacements = {c.ref: (0.0, 0.0) for c in self.pcb.components}

            for c in collisions:
                # Vector from center to center
                # Use current positions, not initial_position if we haven't updated yet?
                # Actually audit uses pcb.components values.

                # Get centroids
                poly1 = self.auditor.courtyards[c.ref1]
                poly2 = self.auditor.courtyards[c.ref2]

                p1 = poly1.centroid
                p2 = poly2.centroid

                dx = p1.x - p2.x
                dy = p1.y - p2.y
                dist = math.sqrt(dx * dx + dy * dy)

                if dist < 0.001:
                    # Coincident centers - random push
                    dx = 1.0
                    dy = 0.0
                    dist = 1.0

                # Normalize
                ux = dx / dist
                uy = dy / dist

                # Force magnitude proportional to overlap area
                # Heuristic: sqrt(area) gives linear dimension
                force = math.sqrt(c.area) * self.step_size

                # Push apart
                # Ref1 gets +force, Ref2 gets -force
                # Check if fixed
                comp1 = next(comp for comp in self.pcb.components if comp.ref == c.ref1)
                comp2 = next(comp for comp in self.pcb.components if comp.ref == c.ref2)

                if not comp1.fixed:
                    dx1, dy1 = displacements[c.ref1]
                    displacements[c.ref1] = (dx1 + ux * force, dy1 + uy * force)

                if not comp2.fixed:
                    dx2, dy2 = displacements[c.ref2]
                    displacements[c.ref2] = (dx2 - ux * force, dy2 - uy * force)

            # 3. Update positions
            moved = False
            for comp in self.pcb.components:
                disp = displacements.get(comp.ref, (0.0, 0.0))
                if abs(disp[0]) > 0.001 or abs(disp[1]) > 0.001:
                    cx, cy = comp.initial_position
                    comp.initial_position = (cx + disp[0], cy + disp[1])
                    moved = True

            if not moved:
                # Stuck?
                break

        return False
