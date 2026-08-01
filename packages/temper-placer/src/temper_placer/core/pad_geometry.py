"""Shape-correct, rotation-aware pad geometry -- the single shared model.

**The bug this replaces.** Every consumer of pad geometry on this codebase
used to compute ``radius = max(width, height) / 2`` and treat every pad as a
circle of that radius, regardless of its declared KiCad shape
(``circle``/``oval``/``rect``/``roundrect``). That formula describes no
KiCad pad shape except ``circle``:

- it **under-reports** extent at the corners of a square/near-square
  ``rect``/``roundrect`` pad (a circle never contains a rectangle) -- worst
  measured case on ``pcb/temper.kicad_pcb``: an 8x8mm ``rect`` pad whose
  corners lie 1.657mm outside the modeled circle;
- it **over-reports** extent on the short axis of an elongated pad -- a
  9x4.8mm pad was modeled with a 4.5mm radius where its true half-extent on
  the short axis is 2.4mm.

Both directions have produced wrong safety answers (false FAILs on the
mains<->SELV isolation gate, an INFEASIBLE CP-SAT barrier verdict computed on
the same wrong geometry). See
``docs/plans/2026-07-28-002-fix-pad-geometry-model-plan.md``.

**The fix: an exact closed form, not a better approximation.** Every one of
KiCad's four pad shapes this board uses is the Minkowski sum of an
axis-aligned "core" rectangle and a disk of some shape-dependent corner
radius ``r``:

    circle:    core = 0 x 0,                      r = width / 2 (width==height)
    oval:      core = (w-2r) x (h-2r), r = min(w, h) / 2
    rect:      core = w x h,                      r = 0
    roundrect: core = (w-2r) x (h-2r), r = roundrect_ratio * min(w, h)

This is not an approximation for any of the four -- it is literally how
KiCad defines each shape. The support function (the shape's extent in a
given direction) of a Minkowski sum is the sum of the parts' support
functions: a disk of radius ``r`` contributes ``r`` in every direction, and
an axis-aligned rectangle of half-extents ``(hw, hh)`` has the closed-form
support function ``hw*|dx| + hh*|dy|`` for a *local*-frame unit direction
``(dx, dy)`` (exact -- this is the maximum of the dot product of the
direction with each of the rectangle's 4 corners). So:

    h(d) = hw*|dx| + hh*|dy| + r

is the pad's EXACT half-extent in local-frame direction ``d``, for all four
shapes uniformly. Rotation is applied by rotating the *query* direction into
the pad's local frame before evaluating this formula -- also exact, not an
approximation, since rotating a Minkowski sum by theta is the same as
Minkowski-summing the rotated parts.

**Never-under-report proof (R2).** For any point p on the pad's true
boundary, in a given direction d = p/|p|, |p| = h(d) by definition of the
support function, so no boundary point of the true shape ever exceeds
h(d) in its own direction. A circle of radius ``sup_d h(d)`` (this module's
``pad_bounding_radius``) therefore *circumscribes* the true shape exactly:
for any point p in the true pad, |p| = h(p/|p|) <= sup_d h(d). This is not
merely conservative -- it is the tight (smallest possible) circumscribing
radius, achieved exactly at the direction towards a true corner.

**Rotation invariance of the isotropic bound.** ``pad_bounding_radius``
does not take a rotation argument because a supremum over *all* directions
is unchanged by rotating which direction is which -- the set of achievable
support values is rotation-invariant. This is a proof, not an omission: R3
("pad rotation must be honoured, not assumed away") is satisfied for the
isotropic bound by showing it cannot be affected by rotation, not by
skipping the question.

**roundrect_ratio, when unknown.** If a caller does not have the pad's real
``roundrect_rratio`` (KiCad's own default is 0.25), passing
``DEFAULT_ROUNDRECT_RATIO`` is *always* safe regardless of the true ratio:
for any query direction exactly along a local axis (dx=0 or dy=0), the
support value ``h(d) = width/2`` or ``height/2`` is completely independent
of ``r`` (the ``r`` terms cancel: ``(size/2 - r) + r = size/2``). Off-axis,
using ``r_used <= r_true`` (i.e. assuming *less* rounding than reality)
always yields ``h_used(d) >= h_true(d)`` -- proof: substituting
``hw_true = hw_used - (r_true - r_used)`` into the support formula gives
``h_true(d) = h_used(d) + (r_true - r_used)*(1 - |dx| - |dy|)``, and
``|dx| + |dy| >= 1`` for any unit vector, so the correction term is always
<= 0 when ``r_true >= r_used``. Since 0.25 is KiCad's own default and this
board's actual roundrect pads carry ratios at or below that in the
sample checked, 0.25 is used only as a fallback when a caller has no better
number -- exact per-pad ratios should be threaded through wherever available
(see ``temper_placer.core.netlist.Pin.roundrect_ratio``).
"""

from __future__ import annotations

import logging
import math

import temper_geometry as _tg

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_ROUNDRECT_RATIO",
    "KNOWN_SHAPES",
    "pad_axis_radius",
    "pad_bounding_radius",
    "pad_core_half_extents",
    "pad_core_polygon",
    "pad_corner_radius",
    "pad_pair_distance",
    "pad_polygon",
    "pad_support_radius",
]

# KiCad's own default roundrect_rratio (the ratio shown in the pad properties
# dialog when a pad is first switched to "Rounded rectangle").
DEFAULT_ROUNDRECT_RATIO = 0.25

# Shapes this module models exactly. "thru_hole" is this codebase's own
# rename (see io/_parse_modules.py) for a round plated-through-hole pad --
# geometrically identical to "circle".
KNOWN_SHAPES = frozenset({"circle", "oval", "rect", "roundrect", "thru_hole"})


def _normalize_shape(shape: str) -> str:
    return "circle" if shape == "thru_hole" else shape


def _warn_unknown_shape(shape: str) -> None:
    """Emit the once-per-call warning for unrecognized pad shapes (the
    Rust core computes the same safe r=0 fallback; the warning is Python-
    side so logs stay grep-visible in CI)."""
    if _normalize_shape(shape) not in KNOWN_SHAPES:
        logger.warning(
            "pad_geometry: unrecognized pad shape %r -- falling back to a sharp "
            "rectangular corner (r=0), which is safe (never under-reports) but "
            "not shape-exact. Known shapes: %s",
            shape,
            sorted(KNOWN_SHAPES),
        )


def pad_corner_radius(
    width: float,
    height: float,
    shape: str,
    roundrect_ratio: float = DEFAULT_ROUNDRECT_RATIO,
) -> float:
    """Return the exact Minkowski-sum corner (disk) radius ``r`` for *shape*.

    See module docstring for the closed-form derivation. Unrecognized shapes
    (e.g. KiCad ``custom``, not present on ``pcb/temper.kicad_pcb`` as of
    this writing) fall back to ``r = 0`` -- i.e. treated as the pad's full
    ``width x height`` bounding rectangle with sharp corners, which is a
    documented, safe (never-under-reporting) but not shape-exact fallback;
    see ``pad_bounding_radius``'s docstring for why r=0 is always safe.

    Computed in the ``temper-geometry`` Rust crate (``pad_geometry.rs``)
    with the exact f64 operation order of the former pure-Python closed
    form.
    """
    _warn_unknown_shape(shape)
    return _tg.pad_corner_radius_py(width, height, shape, roundrect_ratio)


def pad_core_half_extents(
    width: float,
    height: float,
    shape: str,
    roundrect_ratio: float = DEFAULT_ROUNDRECT_RATIO,
) -> tuple[float, float]:
    """Return the (half-width, half-height) of the pad's core rectangle.

    The core rectangle is the ``width x height`` box shrunk by the corner
    radius on each side (``max(..., 0.0)`` guards a corner radius larger
    than half the pad -- should not happen for well-formed KiCad data, but
    never allowed to go negative and flip the sign of the support formula).
    """
    _warn_unknown_shape(shape)
    return _tg.pad_core_half_extents_py(width, height, shape, roundrect_ratio)


def pad_support_radius(
    width: float,
    height: float,
    shape: str,
    direction_rad: float,
    rotation_rad: float = 0.0,
    roundrect_ratio: float = DEFAULT_ROUNDRECT_RATIO,
) -> float:
    """Return the pad's exact half-extent in world direction *direction_rad*.

    ``rotation_rad`` is the pad's total world rotation (component rotation
    plus, if applicable, the pad's own intrinsic rotation -- KiCad pads can
    carry an independent ``(at x y angle)`` on top of the footprint's own
    angle). The query direction is rotated into the pad's local
    (pre-rotation) frame by ``-rotation_rad`` before evaluating the closed
    form -- exact for any rotation, not just axis-aligned multiples of 90
    degrees (R3: rotation must be honoured, not assumed away).
    """
    _warn_unknown_shape(shape)
    return _tg.pad_support_radius_py(
        width, height, shape, direction_rad, rotation_rad, roundrect_ratio
    )


def pad_axis_radius(
    width: float,
    height: float,
    shape: str,
    axis: int,
    rotation_rad: float = 0.0,
    roundrect_ratio: float = DEFAULT_ROUNDRECT_RATIO,
) -> float:
    """Return the pad's exact half-extent along a *world* axis (0=X, 1=Y).

    This is the quantity a barrier/corridor/keepout check actually needs:
    the worst-case (largest) distance the pad's copper reaches from its
    center along one global axis, given the pad has been rotated by
    ``rotation_rad``. A thin wrapper over ``pad_support_radius`` for the
    two axis-aligned directions.
    """
    if axis not in (0, 1):
        raise ValueError(f"axis must be 0 (X) or 1 (Y), got {axis!r}")
    _warn_unknown_shape(shape)
    return _tg.pad_axis_radius_py(width, height, shape, axis, rotation_rad, roundrect_ratio)


def pad_bounding_radius(
    width: float,
    height: float,
    shape: str,
    roundrect_ratio: float = DEFAULT_ROUNDRECT_RATIO,
) -> float:
    """Return the pad's exact, tight, rotation-invariant circumscribing radius.

    ``sup_d h(d) = hypot(hw, hh) + r`` (Cauchy-Schwarz: ``hw*|dx| + hh*|dy|
    <= hypot(hw, hh)`` for any unit ``(dx, dy)``, with equality exactly at
    the direction proportional to ``(hw, hh)``, i.e. towards a true corner).
    This is the single-number, rotation-independent conservative bound the
    router's hot paths (A* grid cell sizing, congestion, obstacle-map
    fallback, escape-via clearance) use in place of a full per-pad polygon
    operation -- see module docstring "Rotation invariance of the isotropic
    bound" for why skipping rotation here is provably correct rather than an
    oversight.
    """
    _warn_unknown_shape(shape)
    return _tg.pad_bounding_radius_py(width, height, shape, roundrect_ratio)


def pad_core_polygon(
    width: float,
    height: float,
    shape: str,
    cx: float,
    cy: float,
    rotation_rad: float = 0.0,
    roundrect_ratio: float = DEFAULT_ROUNDRECT_RATIO,
):
    """Return the pad's **core** as an EXACT world-space Shapely geometry.

    The core is the rectangle the pad's corner disk is Minkowski-summed with
    (module docstring). Unlike ``pad_polygon`` it involves no arc
    approximation at all, because a (possibly degenerate) rotated rectangle
    is exactly representable: a ``Polygon`` when both half-extents are
    positive, a ``LineString`` when one collapses (``oval``), a ``Point``
    when both do (``circle``). Shapely handles all three uniformly in
    ``.distance()``, which is what makes :func:`pad_pair_distance` exact.
    """
    from shapely.affinity import rotate, translate
    from shapely.geometry import LineString, Point, box

    hw, hh = pad_core_half_extents(width, height, shape, roundrect_ratio)
    if hw <= 0.0 and hh <= 0.0:
        core = Point(0.0, 0.0)
    elif hh <= 0.0:
        core = LineString([(-hw, 0.0), (hw, 0.0)])
    elif hw <= 0.0:
        core = LineString([(0.0, -hh), (0.0, hh)])
    else:
        core = box(-hw, -hh, hw, hh)

    rotated = rotate(core, math.degrees(rotation_rad), origin=(0, 0), use_radians=False)
    return translate(rotated, xoff=cx, yoff=cy)


def pad_pair_distance(
    pad_a: tuple[float, float, str, float, float, float, float],
    pad_b: tuple[float, float, str, float, float, float, float],
) -> float:
    """EXACT copper-to-copper distance between two pads. 0.0 if they overlap.

    Each pad is ``(width, height, shape, cx, cy, rotation_rad,
    roundrect_ratio)``.

    **Why this is exact rather than approximate.** Every KiCad pad shape this
    module models is ``core ⊕ D_r`` -- a rectangle Minkowski-summed with a
    disk of radius ``r`` (module docstring). Writing the sum as a sublevel
    set, ``S ⊕ D_r = {x : dist(x, S) <= r}``, gives directly

        dist(A ⊕ D_ra, B ⊕ D_rb) = max(0, dist(A, B) - ra - rb)

    and ``dist(A, B)`` between two rotated rectangles (or their degenerate
    segment/point forms) is computed exactly by Shapely on
    :func:`pad_core_polygon`. No arc is ever polygonised, so unlike
    ``pad_polygon`` -- whose circumscribing buffer is deliberately short of
    the truth by up to ``r * (1/cos(pi/(2*quad_segs)) - 1)`` -- this function
    has no shape-dependent error term at all.

    That matters at zero margin. On ``pcb/temper.kicad_pcb`` the K1
    HV<->SELV pad pair sits at exactly 8.000mm against an 8.000mm REINFORCED
    creepage requirement; ``pad_polygon`` at ``quad_segs=32`` reports
    7.9989mm and would manufacture a violation out of the approximation.
    This function reports 8.000mm.
    """
    wa, ha, sa, cxa, cya, rota, rra = pad_a
    wb, hb, sb, cxb, cyb, rotb, rrb = pad_b
    core_a = pad_core_polygon(wa, ha, sa, cxa, cya, rota, rra)
    core_b = pad_core_polygon(wb, hb, sb, cxb, cyb, rotb, rrb)
    gap = core_a.distance(core_b)
    ra = pad_corner_radius(wa, ha, sa, rra)
    rb = pad_corner_radius(wb, hb, sb, rrb)
    return max(gap - ra - rb, 0.0)


def pad_polygon(
    width: float,
    height: float,
    shape: str,
    cx: float,
    cy: float,
    rotation_rad: float = 0.0,
    roundrect_ratio: float = DEFAULT_ROUNDRECT_RATIO,
    quad_segs: int = 16,
):
    """Return an exact-or-conservative Shapely polygon for the pad, in world space.

    For ``rect`` (r=0) this is an exact rotated rectangle -- no
    approximation at all. For ``circle``/``oval``/``roundrect`` (r>0), the
    true boundary includes circular arcs that a polygon can only
    approximate; Shapely's ``buffer()`` places its polygon vertices ON the
    true arc and connects them with chords that cut slightly INSIDE the
    arc (i.e. an inscribed approximation) -- using it directly would
    under-report extent near the midpoint between two adjacent vertices,
    violating R2. This is corrected by inflating the buffer radius so the
    polygon *circumscribes* the true arc instead: for ``quad_segs``
    segments per quarter-circle, the chord's closest approach to the true
    arc at radius ``r`` is ``r_buffer * cos(pi / (2*quad_segs))`` at the
    midpoint between vertices; solving ``r_buffer * cos(pi/(2*quad_segs)) =
    r`` for ``r_buffer`` guarantees the buffered polygon contains the true
    disk of radius ``r`` everywhere, not just at the sampled vertices.
    """
    from shapely.affinity import rotate, translate
    from shapely.geometry import box

    hw, hh = pad_core_half_extents(width, height, shape, roundrect_ratio)
    r = pad_corner_radius(width, height, shape, roundrect_ratio)

    if r <= 0.0:
        core = box(-hw, -hh, hw, hh)
        poly = core
    else:
        r_buffer = r / math.cos(math.pi / (2 * quad_segs))
        if hw <= 0.0 and hh <= 0.0:
            # Pure circle (or a fully-rounded oval degenerating to one) --
            # buffer a point directly rather than a degenerate zero-area box
            # (Shapely accepts it, but this is clearer and avoids relying on
            # buffering a degenerate box producing a clean circle).
            from shapely.geometry import Point

            poly = Point(0.0, 0.0).buffer(r_buffer, quad_segs=quad_segs)
        else:
            core = box(-hw, -hh, hw, hh)
            poly = core.buffer(r_buffer, quad_segs=quad_segs, join_style="round")

    rotated = rotate(poly, math.degrees(rotation_rad), origin=(0, 0), use_radians=False)
    return translate(rotated, xoff=cx, yoff=cy)
