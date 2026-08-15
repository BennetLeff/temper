"""``F.Fab`` body geometry -- a component's real, physical solid envelope.

**Why this exists, distinct from ``core/courtyard.py``'s ``Courtyard``.**
KiCad's ``F.CrtYd`` courtyard is a *keep-out* boundary -- by convention it is
drawn LARGER than the part's real body (typically +0.25mm margin), so two
courtyards touching is not necessarily a manufacturing problem. ``F.Fab`` is
the part's true physical outline: the solid the datasheet describes. Two
``F.Fab`` bodies overlapping is not a convention question -- it is two
solids trying to occupy the same volume, which is physically unassemblable.

This distinction is exactly what
``docs/evidence/2026-08-13-courtyard-collision-characterization-and-remediation-plan.md``
(PR #1158, independently re-deriving and cross-validating PR #1154's
finding against live ``kicad-cli``) measured for all 8 of the board's
tracked ``courtyards_overlap`` pairs: 6 are real ``F.Fab`` body collisions
(0.15mm-7.73mm of interpenetration), 2 are courtyard-only touches with real
air gaps between the actual bodies (0.19mm/0.39mm clear). A guard built on
courtyard geometry cannot make that distinction and would either miss real
collisions (if it used a shrunk box) or flag benign touches as failures (if
it used the true courtyard) -- see ``body_collision.py``, which uses this
module's geometry as its post-solve fail-closed check.

**Geometry kernel reuse (not fresh arithmetic).** Local-to-world transform
delegates to the exact same compiled kernel ``Courtyard.get_global_polygon``
uses, ``temper_geometry.courtyard_global_points_py`` -- the KiCad-sanctioned
``R(-theta)`` rotation convention (proven correct by cross-validation
against live ``kicad-cli`` DRC output for all 8 tracked pairs plus 57
additional pairs in PR #1158, and independently re-verified for this module
against the live board -- see ``body_collision.py`` module docstring for the
reproduction). ``rotation_idx`` is a 0-3 quadrant index (``angle / 90``),
**not degrees** -- the exact confusion that produced four wrong answers on
this board in one day (see PR #1167's rename of
``Component.initial_rotation`` to ``initial_rotation_quadrant`` for the full
incident list). The polygon boolean (intersection area) stays with GEOS/
shapely -- a geometry-engine library boundary, not a kernel, same posture as
``Courtyard.check_overlap``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import temper_geometry as _tg
from shapely.geometry import Polygon


@dataclass
class FabBody:
    """The ``F.Fab`` physical body envelope of one component, in local
    (footprint-frame) coordinates -- position/rotation-independent.

    ``points`` are the merged outline of every ``F.Fab``/``B.Fab`` graphic
    item on the footprint (poly/circle/rect/line/arc, hull-and-union merged
    exactly as ``kicad_metadata._courtyard_points_from_raw`` merges
    ``F.CrtYd`` shapes -- reused, not reimplemented; see
    ``io.fab_body_extraction``).
    """

    component_ref: str
    points: list[tuple[float, float]]

    _polygon: Polygon = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if len(self.points) < 3:
            # No usable F.Fab geometry parsed for this footprint. A caller
            # must not silently treat this as "clear of everything" -- see
            # body_collision.py's audit, which excludes refs with no real
            # geometry from the pairwise check entirely rather than passing
            # them through a fabricated small box (unlike Courtyard, whose
            # fallback box is appropriate for a *keep-out*, never for a
            # *body* -- a fabricated body would either manufacture false
            # collisions or (worse) mask real ones).
            self.points = []
            return
        self._polygon = Polygon(self.points)

    @property
    def has_geometry(self) -> bool:
        return len(self.points) >= 3

    def get_global_polygon(self, x: float, y: float, rotation_idx: int) -> Polygon:
        """World-frame ``F.Fab`` body polygon at the given center/rotation.

        ``rotation_idx`` is the 0-3 quadrant index (``angle_deg / 90``), the
        same contract ``Courtyard.get_global_polygon`` and
        ``CpSatPlacementResult.rotations`` use -- NOT degrees.
        """
        if not self.has_geometry:
            raise ValueError(
                f"FabBody({self.component_ref!r}) has no parsed F.Fab geometry -- "
                "callers must check has_geometry before requesting a polygon "
                "(see body_collision.py's audit, which excludes such refs "
                "up front rather than falling back to a fabricated shape)"
            )
        flat = [coord for pt in self.points for coord in pt]
        out = _tg.courtyard_global_points_py(flat, rotation_idx, x, y)
        pts = [(out[i], out[i + 1]) for i in range(0, len(out), 2)]
        return Polygon(pts)
