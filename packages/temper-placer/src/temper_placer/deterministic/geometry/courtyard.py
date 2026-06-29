from dataclasses import dataclass, field

from shapely.affinity import rotate, translate
from shapely.geometry import Polygon


@dataclass
class Courtyard:
    """
    Represents the physical courtyard (keepout area) of a component.
    """
    component_ref: str
    points: list[tuple[float, float]]  # Local coordinates relative to component center

    # Cache the shapely polygon
    _polygon: Polygon = field(init=False, repr=False)

    def __post_init__(self):
        if len(self.points) < 3:
            # Fallback for invalid/empty courtyards: small box
            self.points = [(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)]
        self._polygon = Polygon(self.points)

    def get_global_polygon(self, x: float, y: float, rotation_idx: int) -> Polygon:
        """
        Transform local courtyard to global coordinates.
        rotation_idx: 0=0deg, 1=90deg, 2=180deg, 3=270deg (CCW)
        """
        # Rotate first (relative to 0,0 center)
        # 90 degrees CCW * rotation_idx
        angle = rotation_idx * 90.0
        rotated = rotate(self._polygon, angle, origin=(0, 0))

        # Translate to global position
        return translate(rotated, xoff=x, yoff=y)

def check_overlap(c1: Courtyard, pos1: tuple[float, float], rot1: int,
                  c2: Courtyard, pos2: tuple[float, float], rot2: int) -> bool:
    """Check if two courtyards overlap at given positions/rotations."""
    poly1 = c1.get_global_polygon(pos1[0], pos1[1], rot1)
    poly2 = c2.get_global_polygon(pos2[0], pos2[1], rot2)

    # Check intersection
    return poly1.intersects(poly2) and not poly1.touches(poly2)
