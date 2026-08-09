from dataclasses import dataclass, field

import temper_geometry as _tg
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
        rotation_idx: 0=0deg, 1=90deg, 2=180deg, 3=270deg, matching a
        footprint's raw KiCad board rotation (``fp.position.angle``).

        Uses ``temper_placer.geometry.kicad_transform``'s sanctioned
        KiCad rotation convention (R(-theta), not the R(+theta)/CCW this
        used before -- see that module's docstring for the confirming
        evidence). For a courtyard polygon symmetric about its own local
        origin (the common case: an axis-aligned rectangle centered on the
        footprint origin) the sign is a no-op; for an asymmetric/offset
        courtyard polygon it is not.

        Wave 4: the per-vertex rotate+translate affine transform runs in Rust
        (``temper_geometry.courtyard_global_points``), reproducing shapely's
        ``affinity.rotate`` then ``affinity.translate`` arithmetic exactly
        (including the ``abs(cosp)<2.5e-16`` hard zeroing and the
        ``angle * pi / 180.0`` degrees->radians conversion). The polygon
        BOOLEAN (``intersects``/``touches`` in ``check_overlap``) stays with
        GEOS here -- that is a geometry-engine library boundary, not a
        kernel. See ``packages/temper-geometry/VERIFICATION.md``.
        """
        flat = [coord for pt in self.points for coord in pt]
        out = _tg.courtyard_global_points_py(flat, rotation_idx, x, y)
        pts = [(out[i], out[i + 1]) for i in range(0, len(out), 2)]
        return Polygon(pts)


def check_overlap(
    c1: Courtyard,
    pos1: tuple[float, float],
    rot1: int,
    c2: Courtyard,
    pos2: tuple[float, float],
    rot2: int,
) -> bool:
    """Check if two courtyards overlap at given positions/rotations."""
    poly1 = c1.get_global_polygon(pos1[0], pos1[1], rot1)
    poly2 = c2.get_global_polygon(pos2[0], pos2[1], rot2)

    # Check intersection
    return poly1.intersects(poly2) and not poly1.touches(poly2)
