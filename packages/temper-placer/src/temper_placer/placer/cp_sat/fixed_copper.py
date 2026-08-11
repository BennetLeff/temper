"""Pad-vs-fixed-copper NoOverlap constraint for CP-SAT placement (issue #523, R24).

**The gap this closes.** The placer's constraint vocabulary separates
*components* from *fixed geometry* only at the whole-component level:
``SeparatedConstraint`` separates courtyard boxes, ``KeepoutConstraint``
keeps components out of named zones, and ``NoOverlap2D`` keeps components
off each other. Nothing constrains a *pad* of a placed component against the
board's *pre-existing routed copper* (traces, vias, pours, other components'
pads). The RT314012 relay blocker that motivated this module was exactly
that hole: a pad landing on a pre-existing B.Cu track of a different net is
a physical SHORT (5 ``shorting_items``, measured in the two issue-#523
spikes), and no clearance/domain mechanism was even applicable because the
net was not domain-declared and the separated pairs were component-component
only.

**What this module adds.** A new constraint class: for every *free* (being
placed) component, every pad's copper rectangle (pad local geometry +
component rotation, in the same placement frame the solver uses everywhere
else) must not overlap any fixed-copper item of a *different* net, on any
*shared* copper layer, with a small margin (default 0.05 mm, matching the
verified grid search of the issue-#523 spikes).

**Encoding — conservative axis-aligned boxes, one BoolOr per (pad, item)
pair.** CP-SAT works on integer-scaled axis-aligned intervals, so every
fixed-copper item is encoded as the axis-aligned bounding rectangle of its
exact copper shape, expanded by the margin:

* *Trace segment* — exact copper is a thick segment (stadium: the segment
  swept by a disc of radius ``width/2``). Encoded as
  ``bbox(segment) ⊕ (width/2 + margin)`` — the axis-aligned box around the
  segment endpoints expanded by the half-width plus margin. The stadium is
  a subset of that box, so clearing the box implies clearing the real
  copper within margin (soundness, below). Conservatism introduced: the
  corner regions of the box that the stadium does not cover. **The corner
  overhang is NOT bounded by ``(√2 − 1)·(width/2 + margin)`` in general** —
  that closed form is exact only for an axis-aligned segment, where every
  box corner is at most ``√2·(width/2 + margin)`` from the nearest
  endpoint. For a *diagonal* segment the far corners of the bbox can be
  arbitrarily far from the actual thin track (proportional to the segment
  length: up to roughly ``L/√2`` for a 45° segment of length ``L``), so
  this module computes the slack *per segment* as the exact worst-case
  corner overhang (max over the four bbox corners of
  ``dist(corner, segment) − width/2 − margin``, see ``segment_slack_mm``)
  rather than trusting the axis-aligned closed form. This is still a
  *sound* upper bound — the exact max-excess over all box points is
  achieved at a corner because distance to a convex set is convex and the
  box is a rectangle — and it is *truthful*: the BMC conservatism sweep
  (``TestFixedCopperSoundnessBMC::test_conservatism_within_documented_slack``)
  checks observed excess against exactly this per-item number, and would
  have failed against the axis-aligned-only closed form (it did). A
  degenerate (zero-length) segment is encoded as its expanded endpoint box,
  i.e. as a disc of radius ``width/2 + margin`` bounded by the box.
* *Via* — exact copper is a disc of radius ``diameter/2``. Encoded as the
  square ``bbox(centre) ⊕ (diameter/2 + margin)``. Corner conservatism is
  ``(√2 − 1)·(diameter/2 + margin)``.
* *Zone (pour outline)* — exact copper is the zone's fill region, which the
  parser sees only as the zone *outline* polygon (fills are not persisted
  to ``.kicad_pcb``; they are recomputed on open). **Convex zones** (any
  orientation, diagonal edges allowed) use the polygon-exact per-edge
  half-plane encoding below — the direct generalization of the #567
  rectilinear path. **Non-convex zones** fall back to the outline polygon's
  bounding rectangle expanded by the margin — a conservative superset of
  the fill (the half-plane proof below requires the zone to lie inside
  every edge's interior half-plane, which fails exactly for reflex
  vertices; the bbox is the documented sound fallback). Measured on the
  production board every one of the 96 zone items is convex, so the bbox
  fallback is unreachable there (verified 2026-08-04, see
  ``docs/evidence/2026-08-04-convex-zone-encoding.md``).
* *Other components' pads* — exact copper is the pad's own axis-aligned
  box (rotated to the pinned component's placement rotation). Encoded as
  that box expanded by the margin in both axes. The expansion is the square
  of half-side ``margin`` around the rect, which strictly contains the
  exact margin region (the rect swept by a *disc* of radius ``margin``);
  the corner overhang is ``(√2 − 1)·margin``, so the pad item's slack is
  ``(√2 − 1)·margin``, not zero.

Per (pad, item) pair whose copper layers intersect and whose nets differ,
the encoder adds a single ``BoolOr`` over four linear literals — the pad's
world rectangle lies entirely left/right/below/above the item's expanded
box:

    pad.x_min >= item.x1   OR   pad.x_max <= item.x0
    OR  pad.y_min >= item.y1   OR   pad.y_max <= item.y0

The pad's world rectangle is affine in the component's placement centre:
``pad.x_min = x_center + ox_r − hwx_r`` where ``ox_r``/``hwx_r`` are the
pad's rotated offset and half-extent for the solver's rotation index r,
selected by an ``AddElement`` table over the four quadrant rotations
(rot=1/3 swap the local half-extents, matching the model's own
``x_size``/``y_size`` rotation tables and the KiCad R(−θ) convention —
see ``geometry/kicad_transform.py`` and
``isolation_barrier.py::_project_onto_barrier_axis``). A degenerate pad
with zero half-extent is handled by clamping the half-extent to a minimum
of 1 model unit (0.01 mm) so the interval stays non-degenerate; the 0.05 mm
margin absorbs the clamp.

**Zone half-plane encoding (#567 → general convex, issue #651).** A convex
polygon is the intersection of its edge half-planes, so a pad is disjoint
from it iff the pad lies wholly outside AT LEAST ONE edge half-plane —
encoded as a single ``BoolOr`` over one literal per edge, where each edge
literal is the pad's clearance of that edge's half-plane:

* *Axis-aligned edge* (x = c or y = c): the pad clears iff its whole
  extent is beyond the line shifted out by the margin, e.g.
  ``pad.x_min >= c + margin`` (one ``("x", coord, sign)`` entry, the #567
  form — exact for convex rectilinear zones).
* *Diagonal edge* (any other direction): the pad clears iff the pad's
  minimum of the edge's outward linear form ``a·x + b·y`` is at least the
  edge's shifted offset ``r``. For a pad whose world rectangle is
  ``[x_center+ox−hwx, x_center+ox+hwx] × [y_center+oy−hwy, y_center+oy+hwy]``,
  that minimum is achieved at the corner in direction (−a, −b):

      min over pad of (a·x + b·y)
        = a·(x_center+ox) + b·(y_center+oy) − |a|·hwx − |b|·hwy

  which is a single linear expression in the model's integer variables
  (``x_center``/``y_center`` plus the rotation-table vars), so each
  diagonal edge contributes ONE linear literal — no per-corner disjunction
  is needed, because the pad is an axis-aligned rectangle and the minimum
  of a linear form over a rectangle is attained at a single corner whose
  identity is fixed by the sign of the coefficients. Coefficients
  ``(a, b)`` are the edge direction computed at 100× the model resolution
  (0.0001 mm — sub-0.1 mm edges keep their true slope, see the two
  soundness bugs in the 2026-08-04 evidence doc) and scaled to integer
  model-unit coefficients (CP-SAT requires integer coefficients); the
  offset ``r`` is computed at the same fine scale from the quantized
  vertices, rounded UP (conservative), and the margin shift embeds the
  integer-grid headroom (the rectilinear #567 path predates the headroom
  and is margin-only; the diagonal path is the stronger, headroom-
  protected form — see below).

**Convex-zone soundness (R24 item 1 — Chebyshev-style).** Let ``Z`` be the
convex polygon, ``E_i = {n_i·p <= d_i}`` its edge half-planes with outward
unit normals ``n_i`` (``Z ⊆ E_i`` for every edge — this is exactly what
convexity buys, and it is what fails for a reflex vertex). The margin
region ``Z ⊕ disc(margin) = ∩_i {n_i·p <= d_i + margin}`` (for a convex
polygon the disc-dilation equals the intersection of the edge half-planes
shifted outward by the margin — the standard offset-polygon identity). If
the encoded predicate declares a pad clear, some edge literal holds, i.e.
the pad's minimum of ``n_i·p`` is at least ``d_i + margin``, i.e. every
pad point satisfies ``n_i·p >= d_i + margin``. Then for every pad point
``p`` and every zone point ``q``:

    n_i·(p − q) = n_i·p − n_i·q >= (d_i + margin) − d_i = margin

so by Cauchy–Schwarz ``|p − q| >= n_i·(p − q) >= margin`` (n_i is unit).
Hence ``dist(pad, Z) >= margin``: **encoded-clear implies exact-clear —
no false negatives, in the continuous sense**. The integer grid erodes
this by the quantization terms below, which the diagonal edges' embedded
headroom (``margin + _GRID_HEADROOM_MM``) fully covers; the rectilinear
#567 path keeps the documented <= 0.015 mm residual that the post-solve
audit catches.

**Conservatism of the convex-zone encoding (encoded-overlap but
exact-clear).** Two sources: (1) at each vertex the offset polygon's
corner is the intersection of the two shifted edge lines, which pokes
beyond the true disc-dilation's circular arc; a pad sitting in that
corner wedge (within the shifted half-planes but beyond the arc) is
rejected although exactly clear. For an interior angle θ the wedge depth
is ``margin·(1/sin(θ/2) − 1)`` (measured max on the production board's
sharpest zone vertex, 28.7°, is 0.15 mm). (2) a pad large relative to the
polygon can poke into every edge's strip while staying far from the
polygon (e.g. a 10 mm pad next to a 15 mm triangle measured 19 mm of
excess) — unbounded in the worst case, exactly like the bbox fallback,
and the reason ``slack_mm`` stays ``inf`` for zones. Both directions are
safe (over-constraining); the run-C unlock only needs the C27-vs-DC_BUS_RTN
encoded-clear count to jump from 0 toward the exact 14,973, which the
diagonal half-plane encoding does (see ``docs/evidence/2026-08-04-convex-
zone-encoding.md``).

**Soundness (R24 item 1 — Chebyshev-style).** Let ``E`` be the encoded
obstacle (the expanded box above) and ``S`` the exact copper shape. For
every item kind, ``E ⊇ S ⊕ margin``:

* segment: ``S ⊕ margin = stadium(width/2 + margin) ⊆ bbox(segment) ⊕
  (width/2 + margin) = E`` (a shape is always contained in its own
  axis-aligned bounding box).
* via: ``disc(d/2 + margin) ⊆ square E``, same argument.
* zone: ``polygon ⊕ margin ⊆ bbox(polygon) ⊕ margin = E``.
* pad: ``rect ⊕ disc(margin) ⊆ rect ⊕ square(margin) = E`` (the square
  expansion strictly contains the disc expansion; this is where the pad
  item's ``(√2 − 1)·margin`` slack comes from).

**The integer-grid term that this containment alone does NOT cover.**
``E ⊇ S ⊕ margin`` is a statement in continuous mm; the encoding then
quantizes everything to the 0.01 mm integer grid. ``_add_no_overlap``
converts ``E`` with ``mm_to_units`` (round-half-even) and the pad's world
rect is ``x_center + ox + hwx`` with ``ox``/``hwx`` themselves
``mm_to_units``-rounded. Each conversion can round the *wrong way* by up
to 0.5 unit (pad edges carry two such terms, so up to 1 unit = 0.01 mm on
a pad edge; an item edge up to 0.5 unit). In the worst case the encoded
predicate could therefore accept a placement whose exact clearance is
``margin − 0.015 mm`` — measured in practice on the real board (K3 pad 3
at 0.040 mm from a PWR_RTN pad with margin 0.05 mm; the post-solve audit
caught it, see ``docs/evidence/2026-08-01-fixed-copper-constraint.md``).
**Fix:** every item's encoded box additionally embeds
``_GRID_HEADROOM_MM = 0.02 mm`` (2 units) of expansion beyond the margin,
so the effective containment is ``E ⊇ S ⊕ (margin + headroom)`` and the
worst-case quantization erosion (1.5 units) can never push the guaranteed
clearance below the physical ``margin`` (0.5 unit of the headroom stays
unspent). The audit and the BMC oracle compare against the *physical*
``margin`` (``item.margin_mm``), not the headroom-inflated box, so a
solve that passes the encoding necessarily clears every item by at least
``margin``.

If CP-SAT declares the placement feasible, every pad rect avoids every
``E``, hence avoids every ``S ⊕ margin``, hence every point of every pad is
at least ``margin`` from every point of every different-net fixed-copper
shape on a shared layer. The encoded predicate therefore *implies* the
exact geometric predicate: **no false negatives** (the encoding can never
accept a placement that shorts). The encoding *can* reject placements that
are exactly clear — that is the conservatism, bounded per item kind by the
corner-overhang expressions above (``(√2 − 1)·(half_extent + margin +
headroom)`` for segments/vias, ``(√2 − 1)·(margin + headroom)`` for pads,
unbounded for zones in the worst case).

**Net / layer filtering.** An item is an obstacle for a component only if
(a) the item's copper layers intersect the pad's copper layers (THT pads
are on all four copper layers; SMD pads on their declared one) and (b) the
item's net is not one of the component's own nets (a pad landing on its
own net's copper is the intended future connection, not a short). Zones on
a component's own net are likewise not obstacles.

**Post-solve audit (R24 item 3).** ``audit_fixed_copper`` recomputes the
*exact* pad-to-copper clearance from the resolved placement coordinates and
rotation indices, independent of whatever the solver claims, using the same
oracle the BMC test sweeps against (``exact_clearance_mm``). A violation
(clearance below the margin for a different-net, shared-layer pair) means
the soundness proof above failed for this solve — an encoding bug — and is
a hard failure (``solve_placement`` raises when ``fixed_copper=`` is given
and a feasible solve produces audit violations).

**BMC-exhaustive validation (R24 item 2):** see
``tests/placer/cp_sat/test_fixed_copper.py::TestFixedCopperSoundnessBMC`` —
an exhaustive sweep of the encoded predicate (reimplemented as pure Python
matching ``encode_fixed_copper_constraints`` line-for-line) against the
exact oracle (``exact_clearance_mm``, imported, not reimplemented) over pad
sizes × item kinds × relative positions covering touching/overlapping/clear
at 0.9×/1.0×/1.1× margin × all four pad rotations, asserting both
directions: encoded-clear ⇒ exact-clear (soundness, zero counterexamples),
and encoded-overlap ⇒ exact-clearance within the documented slack bound.

**Coordinate frames.** ``parse_kicad_pcb`` is inconsistent: component
positions and zone polygons are origin-normalized, but ``ParseResult.traces``
and ``.vias`` are raw board coordinates. ``build_fixed_copper_items``
therefore subtracts ``board.origin`` from every trace and via before
building items, so all items live in the solver's normalized frame. This
is load-bearing; see the evidence doc.

---

**Phase E batch E2 (rust-orchestration-engine plan 2026-08-09-001):** the
build orchestration — ``build_free_component_pads`` /
``build_fixed_copper_items`` / ``audit_fixed_copper`` — and the
``PadRectLocal`` / ``FixedCopperItem`` / ``FixedCopperAuditViolation``
contract dataclasses move to ``temper-design-bundle`` (the
``temper_design_bundle_python.fixed_copper_builder`` submodule) as the
``FixedCopperBuilder`` pyclass plus the three contract pyclasses. This
module keeps the pre-migration public API (``__all__``) unchanged and
re-exports the pyclasses (the pure-delegation pattern, mirroring
``core/net_types.py``). See the ``fixed_copper_builder.rs`` module docstring
for the full split.

What stays Python (the ortools boundary, plan D4 KEEP verdict):

- ``encode_fixed_copper_constraints`` / ``_pad_rotation_tables_with`` /
  ``_add_no_overlap`` — they build ``ortools.CpModel`` calls directly
  (``NewBoolVar`` / ``AddBoolOr`` / ``OnlyEnforceIf`` / ``AddElement`` via
  ``CpSatModel.model_ref``); that is the CP-SAT solver boundary.
- The pure geometry predicates (``pad_world_rect`` /
  ``encoded_pad_world_rect`` / ``exact_clearance_mm`` / ``exact_overlap`` /
  ``encoded_overlap`` / ``encoded_overlap_edges`` / ``segment_slack_mm``)
  — one-line delegations to the pinned ``temper-geometry`` kernels, kept
  here so the encode path and the BMC tests consume the same object API.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import temper_design_bundle_python as _tdb
import temper_geometry as _tg

if TYPE_CHECKING:
    from temper_placer.placer.cp_sat.model import CpSatModel

logger = logging.getLogger(__name__)

# Phase E batch E2: the contract pyclasses + build orchestration live in the
# Rust `fixed_copper_builder` submodule; these names re-export the pyclasses
# (the pure-delegation pattern). Attribute access rather than `import
# temper_design_bundle_python.fixed_copper_builder` — the submodule is
# registered as a parent attribute, not inserted into `sys.modules` (the
# established convention across this crate's shims).
_fcb = _tdb.fixed_copper_builder
FixedCopperAuditViolation = _fcb.FixedCopperAuditViolation
FixedCopperItem = _fcb.FixedCopperItem
PadRectLocal = _fcb.PadRectLocal

# The four copper layers of the temper 4-layer stackup (KiCad names).
COPPER_LAYERS = frozenset({"F.Cu", "B.Cu", "In1.Cu", "In2.Cu"})

# Default pad-to-copper margin (mm), matching the verified issue-#523 grid
# search (MARGIN in the spike's k3_search.py).
DEFAULT_MARGIN_MM = 0.05

# Minimum encoded half-extent in model units for a pad (1 unit = 0.01 mm):
# CP-SAT intervals require strictly positive sizes, and a genuinely
# degenerate pad (zero-size rectangle) still occupies a physical pad. The
# margin (50 units) absorbs the clamp.
_MIN_HALF_UNITS = 1
# The same floor in mm. The solver is always built with units_per_mm=100
# (see _encoder_solve.py), so 1 unit == 0.01 mm. Kept as a named constant
# rather than `_MIN_HALF_UNITS / 100.0` so the BMC test's mirror of the
# encoded predicate and the encoder share one definition.
_MIN_HALF_MM = 0.01

# Integer-grid soundness headroom (mm) added to every encoded item box on
# top of the physical margin. The encoding quantizes to a 0.01 mm integer
# grid: a pad edge is ``x_center + ox + hwx`` with ``ox``/``hwx`` each
# ``mm_to_units``-rounded (round-half-even, error <= 0.5 unit per term), so
# the encoded pad edge can lie up to 1 unit (0.01 mm) *inside* the true pad
# edge, and an item edge converted with the same rounding can lie up to 0.5
# unit *inside* the true item edge. Without a headroom the encoded
# predicate could accept a placement whose exact clearance is margin -
# 0.015 mm -- measured in practice on the real board (K3 pad 3 at 0.040 mm
# from a PWR_RTN pad with margin 0.05 mm; the post-solve audit caught it).
# Expanding every item box by 2 units (0.02 mm) beyond the margin restores
# the exact-margin guarantee with 0.005 mm to spare (see module docstring's
# soundness section).
_GRID_HEADROOM_MM = 0.02

# The solver is always built with units_per_mm=100 (see _encoder_solve.py),
# so 1 model unit == 0.01 mm. The diagonal-edge zone half-planes (issue
# #651) are computed in model units so their coefficients are integers
# (CP-SAT requires integer linear coefficients).
_UNITS_PER_MM = 100


def _mm_to_units(mm: float) -> int:
    """Mirror of ``CpSatModel.mm_to_units`` (round-half-even on mm*100, then
    floor-modulo even-parity), for the fixed 100 units/mm the solver always
    uses. Bit-exact against the ``temper-constraints`` Rust impl for the
    values it pins (see encoder.rs's unit tests); the even-parity adjustment
    exists so sizes stay even for the model's midpoint constraint. The
    diagonal-edge builder uses this so the half-plane vertices sit on the
    same integer grid as the pad variables the CP-SAT encoding uses.

    Computed in the ``temper-geometry`` Rust crate (``fixed_copper.rs``)
    with the exact round-half-even + even-parity operation order of the
    former pure-Python body.
    """
    return _tg.fixed_copper_mm_to_units_py(mm)


# Diagonal-edge half-planes are computed at 100x the model resolution
# (0.0001 mm) so a short edge keeps its true slope after integerization.
# Quantizing the edge direction to the 0.01 mm model grid destroys the
# slope of sub-0.1 mm edges (a 0.025 mm arc edge at the rounded end of the
# +15V_LS strip becomes exactly horizontal), which rotates the half-plane
# enough to exclude polygon vertices -- UNSOUND (measured 2026-08-04, 1,534
# cells on the real board). At 0.0001 mm resolution the direction error is
# <= ~0.0001 mm of line shift, absorbed by the margin headroom.
_FINE_UNITS_PER_MM = 10_000
# Scale factor from fine to model units (10000 / 100).
_FINE_TO_MODEL = _FINE_UNITS_PER_MM // _UNITS_PER_MM


def _mm_to_fine_units(mm: float) -> int:
    """Round a mm coordinate to the fine (0.0001 mm) integer grid used by
    the diagonal half-plane builder. Round-half-even (Python round); no
    even-parity adjustment -- that exists only for model *sizes* (the
    midpoint constraint), not for vertices.

    Computed in the ``temper-geometry`` Rust crate.
    """
    return _tg.fixed_copper_mm_to_fine_units_py(mm)


__all__ = [
    "COPPER_LAYERS",
    "DEFAULT_MARGIN_MM",
    "FixedCopperAuditViolation",
    "FixedCopperItem",
    "PadRectLocal",
    "audit_fixed_copper",
    "build_fixed_copper_items",
    "build_free_component_pads",
    "encode_fixed_copper_constraints",
    "encoded_overlap",
    "encoded_overlap_edges",
    "encoded_pad_world_rect",
    "exact_clearance_mm",
    "pad_world_rect",
    "segment_slack_mm",
]


# ---------------------------------------------------------------------------
# Pad geometry (pure predicates — one-line delegations to the pinned
# temper-geometry kernels)
# ---------------------------------------------------------------------------


def _rotated(pad: PadRectLocal, rot_idx: int) -> tuple[float, float, float, float]:
    """World-frame (offset_x, offset_y, half_w, half_h) of a pad under one
    of the model's four quadrant rotations.

    Uses the exact hand-unrolled closed form of the repo's sanctioned KiCad
    R(−θ) convention (``geometry/kicad_transform.py``;
    ``isolation_barrier.py::_project_onto_barrier_axis``) so the integer
    model never sees ``cos(90°)=6.1e-17``-style float noise:
        rot 0: (lx, ly), halves (hw, hh)
        rot 1: (ly, −lx), halves (hh, hw)
        rot 2: (−lx, −ly), halves (hw, hh)
        rot 3: (−ly, lx), halves (hh, hw)

    Computed in the ``temper-geometry`` Rust crate.
    """
    lx, ly = pad.center
    hw, hh = pad.half
    return _tg.fixed_copper_rotated_py(lx, ly, hw, hh, rot_idx)


def pad_world_rect(
    pad: PadRectLocal, center_mm: tuple[float, float], rot_idx: int
) -> tuple[float, float, float, float]:
    """The pad's world axis-aligned rectangle (x0, y0, x1, y1) in mm for a
    component placed at ``center_mm`` with quadrant rotation ``rot_idx``.

    This is the exact geometry the post-solve audit re-derives from resolved
    coordinates; the CP-SAT encoding below encodes the same rectangle
    affinely (offset + half-extent tables) so the two cannot drift.

    Computed in the ``temper-geometry`` Rust crate.
    """
    lx, ly = pad.center
    hw, hh = pad.half
    cx, cy = center_mm
    return _tg.fixed_copper_pad_world_rect_py(lx, ly, hw, hh, rot_idx, cx, cy)


def encoded_pad_world_rect(
    pad: PadRectLocal, center_mm: tuple[float, float], rot_idx: int
) -> tuple[float, float, float, float]:
    """The pad's world rectangle as the CP-SAT ENCODER represents it (mm).

    Identical to ``pad_world_rect`` except the half-extents are clamped to
    ``_MIN_HALF_MM`` (0.01 mm) before the world transform, mirroring
    ``_pad_rotation_tables_with``'s ``max(_MIN_HALF_UNITS, ...)`` exactly.
    The BMC soundness sweep must evaluate the *encoded* predicate (this
    rect) against the *exact* oracle (``exact_clearance_mm`` on
    ``pad_world_rect``), so a degenerate pad is a 0.02 mm box in the
    encoding but a point in the oracle -- and the clamp is precisely what
    keeps the encoded predicate sound at the boundary (the point sits at
    exactly the margin distance and the clamped box still overlaps).

    Computed in the ``temper-geometry`` Rust crate.
    """
    lx, ly = pad.center
    hw, hh = pad.half
    cx, cy = center_mm
    return _tg.fixed_copper_encoded_pad_world_rect_py(lx, ly, hw, hh, rot_idx, cx, cy)


def segment_slack_mm(p0, p1, width, margin) -> float:
    """Exact worst-case conservatism of a segment's bbox encoding (mm).

    The encoded box is ``bbox(segment) ⊕ (width/2 + margin)``. A point in
    the box that is *not* within the stadium (the exact copper swept by a
    disc of radius ``width/2``) can have its exact clearance measured above
    the margin by up to ``dist(point, segment) − width/2 − margin``. The
    maximum over all points in the box is achieved at a box corner
    (distance to a convex set is convex, and the box is a convex polygon,
    so the max is at a vertex). This returns that exact per-segment
    maximum, so the documented slack is truthful for every orientation —
    including diagonal segments, where the axis-aligned-only closed form
    ``(√2 − 1)·(width/2 + margin)`` under-reports (see module docstring).

    Computed in the ``temper-geometry`` Rust crate.
    """
    return _tg.fixed_copper_segment_slack_mm_py(p0, p1, width, margin)


def _rectilinear_convex_edges(
    polygon: list[tuple[float, float]], margin: float
) -> tuple | None:
    """Return per-edge half-plane separations for a convex axis-aligned
    polygon, or ``None`` if the polygon is not rectilinear/convex.

    Computed in the ``temper-geometry`` Rust crate (``fixed_copper.rs``)
    with the exact winding/convexity/edge-classification logic of the
    former pure-Python body.
    """
    return _tg.fixed_copper_rectilinear_convex_edges_py(list(polygon), margin)


def _convex_polygon_edges(
    polygon: list[tuple[float, float]], margin_mm: float
) -> tuple | None:
    """Per-edge half-plane separations for ANY convex polygon — axis-aligned
    or diagonal edges — or ``None`` if the polygon is non-convex/degenerate.

    Computed in the ``temper-geometry`` Rust crate (``fixed_copper.rs``).
    """
    return _tg.fixed_copper_convex_polygon_edges_py(list(polygon), margin_mm)


# ---------------------------------------------------------------------------
# Fixed-copper build orchestration — Phase E batch E2: delegates to the Rust
# FixedCopperBuilder pyclass (temper_design_bundle_python.fixed_copper_builder).
# ---------------------------------------------------------------------------


def build_free_component_pads(
    netlist: Any, free_refs: set[str], copper_layers: frozenset[str] = COPPER_LAYERS
) -> dict[str, list[PadRectLocal]]:
    """Build per-pad local geometry for every *free* component.

    Pads whose copper layers fall entirely outside ``copper_layers`` are
    dropped (they cannot conflict with any copper item). Every remaining
    pad keeps its net for the same-net skip rule and its layer set for the
    shared-layer rule.

    Args:
        netlist: parsed ``Netlist`` whose ``components`` carry ``pins``.
        free_refs: refs being placed by the solve; only these get pads.
        copper_layers: universe of copper layers to consider.

    Returns:
        ``{ref: [PadRectLocal, ...]}`` for the free refs (order stable).

    Phase E batch E2: the orchestration runs in Rust
    (``FixedCopperBuilder::build_free_component_pads``); the returned pads
    are the design-bundle ``PadRectLocal`` pyclass, exposing the identical
    fields.
    """
    return (
        _fcb.FixedCopperBuilder(
            netlist=netlist,
            free_refs=free_refs,
            copper_layers=copper_layers,
        ).build_free_component_pads()
    )


def build_fixed_copper_items(
    parse_result: Any,
    netlist: Any,
    free_refs: set[str],
    margin_mm: float = DEFAULT_MARGIN_MM,
    include_other_pads: bool = True,
    copper_layers: frozenset[str] = COPPER_LAYERS,
) -> list[FixedCopperItem]:
    """Build the fixed-copper obstacle list from a parsed board.

    Traces and vias are origin-normalized here (the parser leaves them in
    raw board coordinates while components and zones are normalized — see
    module docstring). Zones on a free component's own net are excluded
    here only when they match *every* free component's nets; the per-pair
    same-net skip is enforced at encode time because each component has its
    own net set (a zone on K2's coil net must still be an obstacle for K3).

    Args:
        parse_result: ``ParseResult`` with ``.traces``, ``.vias`` and a
            ``.board`` (``board.origin`` normalizes traces/vias; ``board.zones``
            are already normalized).
        netlist: parsed ``Netlist`` (source of pinned components' pads).
        free_refs: refs being placed; their own pads are NOT obstacles, and
            their nets exempt matching items.
        margin_mm: pad-to-copper clearance margin (default 0.05).
        include_other_pads: if True, pinned components' pads are obstacles
            too (a placed pad landing on another component's pad is a
            short). Default on; the component-component NoOverlap2D already
            separates bounds boxes, but pad-level is tighter.
        copper_layers: universe of copper layers considered.

    Returns:
        List of ``FixedCopperItem`` in a stable order (traces, vias, zones,
        then other pads).

    Phase E batch E2: the orchestration runs in Rust
    (``FixedCopperBuilder::build_fixed_copper_items``); the returned items
    are the design-bundle ``FixedCopperItem`` pyclass, exposing the
    identical fields.
    """
    return (
        _fcb.FixedCopperBuilder(
            netlist=netlist,
            free_refs=free_refs,
            parse_result=parse_result,
            margin_mm=margin_mm,
            include_other_pads=include_other_pads,
            copper_layers=copper_layers,
        ).build_fixed_copper_items()
    )


# ---------------------------------------------------------------------------
# CP-SAT encoding — the ortools boundary (plan D4 KEEP verdict); stays Python.
# ---------------------------------------------------------------------------


def encode_fixed_copper_constraints(
    model: CpSatModel,
    pads_by_ref: dict[str, list[PadRectLocal]],
    items: list[FixedCopperItem],
    free_refs: set[str] | None = None,
) -> list[str]:
    """Encode every (free pad, fixed item) no-overlap disjunction.

    For each free component, a single assumption literal
    ``fixed_copper_<ref>`` gates every one of that component's disjunctions
    (via ``OnlyEnforceIf``), so an infeasible solve's unsat core can name
    the component(s) blocked by fixed copper.

    Returns:
        The assumption labels created (one per free component with pads).

    Phase E batch E2: this is the ortools-coupled surface that stays Python
    (see the module docstring's split note).
    """
    refs = free_refs if free_refs is not None else set(pads_by_ref)
    labels: list[str] = []
    for ref in sorted(refs):
        pads = pads_by_ref.get(ref, [])
        if not pads:
            continue
        comp_nets = {p.net for p in pads if p.net}
        assumption = model.new_assumption(f"fixed_copper_{ref}")
        labels.append(f"fixed_copper_{ref}")
        for pad in pads:
            rot_ref = model.get_component(ref).rot_ref
            if rot_ref is None:
                raise ValueError(
                    f"fixed-copper encode: component {ref!r} has no rotation "
                    "variable (polarized refs must be encoded with rot=0 tables)"
                )
            ox, oy, hwx, hwy = _pad_rotation_tables_with(model, rot_ref, pad)
            cv = model.get_component(ref)
            for item in items:
                if not (pad.layers & item.layers):
                    continue
                if item.net is not None and item.net in comp_nets:
                    continue
                _add_no_overlap(model, assumption, cv, ox, oy, hwx, hwy, pad, item)
    return labels


def _pad_rotation_tables_with(
    model: CpSatModel, rot_ref: Any, pad: PadRectLocal
) -> tuple[Any, Any, Any, Any]:
    """Rotation tables keyed on an explicit rot_ref variable (element vars
    are affine in the component centre and the rotation index)."""
    m = model
    vals_ox = [m.mm_to_units(_rotated(pad, r)[0]) for r in range(4)]
    vals_oy = [m.mm_to_units(_rotated(pad, r)[1]) for r in range(4)]
    vals_hwx = [max(_MIN_HALF_UNITS, m.mm_to_units(_rotated(pad, r)[2])) for r in range(4)]
    vals_hwy = [max(_MIN_HALF_UNITS, m.mm_to_units(_rotated(pad, r)[3])) for r in range(4)]

    def _table(name: str, vals: list[int]):
        v = m.new_int_var(min(vals), max(vals), name)
        m.model_ref.AddElement(rot_ref, vals, v)
        return v

    return (
        _table(f"fc_ox_{pad.number}", vals_ox),
        _table(f"fc_oy_{pad.number}", vals_oy),
        _table(f"fc_hwx_{pad.number}", vals_hwx),
        _table(f"fc_hwy_{pad.number}", vals_hwy),
    )


def _add_no_overlap(
    model: CpSatModel,
    assumption: Any,
    cv: Any,
    ox: Any,
    oy: Any,
    hwx: Any,
    hwy: Any,
    pad: PadRectLocal,
    item: FixedCopperItem,
) -> None:
    """One (pad, item) BoolOr disjunction, gated on *assumption*.

    Zone items with a polygon-exact ``edges`` set use one BoolOr over the
    per-edge half-plane separations (exact for convex rectilinear zones);
    everything else uses the 4-way axis-aligned bbox disjunction.
    """
    m = model
    if item.kind == "zone" and item.edges:
        literals: list[Any] = []
        for entry in item.edges:
            if entry[0] == "n":
                # Diagonal edge half-plane (issue #651): the pad clears iff
                #   min over pad of (a*x + b*y) >= r
                # where (a, b) is the outward-normal edge direction in model
                # units (integers) and r the integer offset (margin +
                # headroom shifted, ceil-rounded). The min over the pad's
                # world rectangle [x_center+ox-hwx, x_center+ox+hwx] x
                # [y_center+oy-hwy, y_center+oy+hwy] is attained at the
                # corner in direction (-a, -b):
                #   a*(x_center+ox) + b*(y_center+oy) - |a|*hwx - |b|*hwy
                # -- a single linear expression, no per-corner disjunction.
                _, a, b, r = entry
                lit = m.model_ref.NewBoolVar(f"fc_zone_{pad.number}_n{a}{b}")
                m.model_ref.Add(
                    a * (cv.x_center + ox)
                    + b * (cv.y_center + oy)
                    - abs(a) * hwx
                    - abs(b) * hwy
                    >= r
                ).OnlyEnforceIf(lit)
            else:
                axis, coord, sign = entry
                c = m.mm_to_units(coord)
                lit = m.model_ref.NewBoolVar(f"fc_zone_{pad.number}_{axis}{sign}")
                if axis == "x":
                    if sign > 0:
                        # pad.x_min >= c : x_center + ox - hwx >= c
                        m.model_ref.Add(cv.x_center + ox - hwx >= c).OnlyEnforceIf(lit)
                    else:
                        # pad.x_max <= c : x_center + ox + hwx <= c
                        m.model_ref.Add(cv.x_center + ox + hwx <= c).OnlyEnforceIf(lit)
                else:
                    if sign > 0:
                        m.model_ref.Add(cv.y_center + oy - hwy >= c).OnlyEnforceIf(lit)
                    else:
                        m.model_ref.Add(cv.y_center + oy + hwy <= c).OnlyEnforceIf(lit)
            literals.append(lit)
        m.model_ref.AddBoolOr(literals).OnlyEnforceIf(assumption)
        return
    rx0, ry0, rx1, ry1 = (m.mm_to_units(v) for v in item.rect)
    x_lo = m.model_ref.NewBoolVar(f"fc_xlo_{pad.number}_{item.kind}")
    x_hi = m.model_ref.NewBoolVar(f"fc_xhi_{pad.number}_{item.kind}")
    y_lo = m.model_ref.NewBoolVar(f"fc_ylo_{pad.number}_{item.kind}")
    y_hi = m.model_ref.NewBoolVar(f"fc_yhi_{pad.number}_{item.kind}")
    # pad.x_max <= item.x0 : x_center + ox + hwx <= rx0
    m.model_ref.Add(cv.x_center + ox + hwx <= rx0).OnlyEnforceIf(x_lo)
    # pad.x_min >= item.x1 : x_center + ox - hwx >= rx1
    m.model_ref.Add(cv.x_center + ox - hwx >= rx1).OnlyEnforceIf(x_hi)
    # pad.y_max <= item.y0 : y_center + oy + hwy <= ry0
    m.model_ref.Add(cv.y_center + oy + hwy <= ry0).OnlyEnforceIf(y_lo)
    # pad.y_min >= item.y1 : y_center + oy - hwy >= ry1
    m.model_ref.Add(cv.y_center + oy - hwy >= ry1).OnlyEnforceIf(y_hi)
    m.model_ref.AddBoolOr([x_lo, x_hi, y_lo, y_hi]).OnlyEnforceIf(assumption)


# ---------------------------------------------------------------------------
# Exact oracle + post-solve audit (R24 item 3)
# ---------------------------------------------------------------------------


def exact_clearance_mm(pad_rect: tuple[float, float, float, float], item: FixedCopperItem) -> float:
    """The exact copper-to-copper clearance between a pad's world rectangle
    and an item's raw copper shape (mm), 0 if they touch/overlap.

    This is the truthful oracle the BMC test and the post-solve audit share.

    Computed in the ``temper-geometry`` Rust crate for all four item kinds
    (see the module docstring for the zone kernel's one documented gap vs
    shapely).
    """
    if item.kind == "segment":
        p0, p1 = item.exact["p0"], item.exact["p1"]
        return _tg.fixed_copper_exact_clearance_mm_py(pad_rect, "segment", p0=p0, p1=p1, width=item.exact["width"])
    if item.kind == "via":
        return _tg.fixed_copper_exact_clearance_mm_py(
            pad_rect, "via", center=item.exact["center"], diameter=item.exact["diameter"]
        )
    if item.kind == "pad":
        return _tg.fixed_copper_exact_clearance_mm_py(pad_rect, "pad", other_rect=item.exact["rect"])
    if item.kind == "zone":
        return _tg.fixed_copper_exact_clearance_mm_py(pad_rect, "zone", polygon=item.exact["polygon"])
    raise ValueError(f"unknown fixed-copper item kind {item.kind!r}")


def exact_overlap(pad_rect: tuple[float, float, float, float], item: FixedCopperItem) -> bool:
    """True if the pad overlaps the item's exact copper within the margin."""
    return exact_clearance_mm(pad_rect, item) < item.margin_mm


def encoded_overlap(pad_rect: tuple[float, float, float, float], item: FixedCopperItem) -> bool:
    """The encoded predicate: does the pad's world rect overlap the item's
    (margin-expanded) box? Mirrors ``_add_no_overlap``'s negation."""
    if item.kind == "zone" and item.edges:
        return encoded_overlap_edges(pad_rect, item)
    x0, y0, x1, y1 = pad_rect
    rx0, ry0, rx1, ry1 = item.rect
    return not (x1 <= rx0 or rx1 <= x0 or y1 <= ry0 or ry1 <= y0)


def encoded_overlap_edges(pad_rect: tuple[float, float, float, float], item: FixedCopperItem) -> bool:
    """The polygon-exact encoded predicate for a zone with ``edges``.

    The pad clears the zone iff it satisfies at least one edge half-plane
    (outside at least one edge line, shifted out by the margin) -- the exact
    analogue of ``_add_no_overlap``'s zone path: encoded overlap means the
    pad fails EVERY edge separation.

    Axis-aligned edges are evaluated in mm directly (the #567 mirror); a
    diagonal edge is evaluated on the model's integer grid -- the pad rect
    is quantized with the same ``_mm_to_units`` the half-plane builder used
    for the vertices, then the min of ``a*x + b*y`` over the unit rect is
    compared to ``r``. This mirrors ``_add_no_overlap``'s diagonal path
    within the component-rounding-order discrepancy (<= ~1.5 units, covered
    by the diagonal edges' embedded grid headroom).
    """
    assert item.edges is not None  # encoded_overlap guards before dispatching
    x0, y0, x1, y1 = pad_rect
    for entry in item.edges:
        if entry[0] == "n":
            _, a, b, r = entry
            # Quantize the pad rect to the model grid, mirroring the
            # encoder's per-component rounding for the pad's world edges.
            px = _mm_to_units(x0) if a >= 0 else _mm_to_units(x1)
            py = _mm_to_units(y0) if b >= 0 else _mm_to_units(y1)
            if a * px + b * py >= r:
                return False  # cleared via this edge -> no overlap
            continue
        axis, coord, sign = entry
        if axis == "x":
            if sign > 0:
                if x0 >= coord:
                    return False  # cleared via this edge -> no overlap
            else:
                if x1 <= coord:
                    return False
        else:
            if sign > 0:
                if y0 >= coord:
                    return False
            else:
                if y1 <= coord:
                    return False
    return True  # fails every separation -> overlaps


def audit_fixed_copper(
    pads_by_ref: dict[str, list[PadRectLocal]],
    items: list[FixedCopperItem],
    resolved_positions_mm: dict[str, tuple[float, float]],
    resolved_rotations: dict[str, int],
) -> list[FixedCopperAuditViolation]:
    """R24 item-3 audit: recompute exact pad-to-copper clearance from the
    *resolved* placement coordinates, independent of the solver's claim.

    For every free ref with a resolved position, every pad, and every
    different-net shared-layer item, computes ``exact_clearance_mm`` and
    flags a violation when it is below the item's margin. By the module
    docstring's soundness proof, a SAT solve must produce zero violations;
    any violation means the encoding is unsound for this solve (a bug) and
    the caller should hard-fail.

    Args:
        pads_by_ref: free components' pads (from
            ``build_free_component_pads``).
        items: fixed-copper obstacles (from ``build_fixed_copper_items``).
        resolved_positions_mm: ``{ref: (x_mm, y_mm)}`` solved positions.
        resolved_rotations: ``{ref: rotation_index}`` solved rotations.

    Returns:
        List of violations; empty means every pad clears every applicable
        item by at least the item's margin.

    Phase E batch E2: the audit orchestration runs in Rust
    (``FixedCopperBuilder::audit_fixed_copper``); the returned violations
    are the design-bundle ``FixedCopperAuditViolation`` pyclass, exposing
    the identical fields.
    """
    return _fcb.FixedCopperBuilder.audit_fixed_copper(
        pads_by_ref, items, resolved_positions_mm, resolved_rotations
    )
