"""
Placement Auditor.

Checks for physical collisions between components (courtyard overlap).
"""

from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import Polygon

from temper_placer.core.pin_geometry import pin_world_position
from temper_placer.router_v6.stage0_data import ParsedPCB


@dataclass
class Collision:
    ref1: str
    ref2: str
    area: float
    center: tuple[float, float]


class PlacementAuditor:
    def __init__(self, pcb: ParsedPCB):
        self.pcb = pcb
        self.courtyards = self._build_courtyards()

    def _build_courtyards(self) -> dict[str, Polygon]:
        """Extract courtyards for all components."""
        courtyards = {}
        for comp in self.pcb.components:
            # Get position and rotation
            x, y = comp.initial_position or (0.0, 0.0)
            comp.initial_rotation * 90.0 if comp.initial_rotation is not None else 0.0

            # Default courtyard: Bounding box of pins + margin
            # Ideally we parse the 'courtyard' layer from footprint, but let's approximate
            # with pins hull + 0.5mm margin for now if explicit courtyard is missing.

            # Simplified: Use a fixed size box if parsing fails, but we should try to be accurate.
            # In router_v6, we don't have footprint geometry fully loaded in ParsedPCB unless
            # we use the raw ki_board object. But ParsedPCB structure is what we have.

            # Let's compute hull of pins.
            points = []
        if hasattr(comp, "pins"):
            for pin in comp.pins:
                abs_pos = pin_world_position(pin, comp)
                points.append(abs_pos)

            if not points:
                # Fallback: 5x5mm box
                s = 2.5
                points = [(x - s, y - s), (x + s, y - s), (x + s, y + s), (x - s, y + s)]

            # Create Polygon from hull
            from shapely.geometry import MultiPoint

            hull = MultiPoint(points).convex_hull

            # Buffer by 0.5mm (Courtyard margin)
            courtyard = hull.buffer(0.5)
            courtyards[comp.ref] = courtyard

        return courtyards

    def check_collisions(self) -> list[Collision]:
        """Find all overlapping pairs."""
        collisions = []
        refs = list(self.courtyards.keys())

        for i in range(len(refs)):
            for j in range(i + 1, len(refs)):
                ref1 = refs[i]
                ref2 = refs[j]
                poly1 = self.courtyards[ref1]
                poly2 = self.courtyards[ref2]

                if poly1.intersects(poly2):
                    intersection = poly1.intersection(poly2)
                    area = intersection.area
                    if area > 0.01:  # Ignore touching
                        collisions.append(
                            Collision(
                                ref1=ref1,
                                ref2=ref2,
                                area=area,
                                center=(intersection.centroid.x, intersection.centroid.y),
                            )
                        )
        return collisions
