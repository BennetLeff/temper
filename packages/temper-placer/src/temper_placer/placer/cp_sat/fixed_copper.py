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
  to ``.kicad_pcb``; they are recomputed on open). Encoded as the outline
  polygon's bounding rectangle expanded by the margin — a conservative
  superset of the fill. **Conservatism is potentially large for a big or
  diagonal pour** (a pour outline can span most of the board while its real
  fill is carved into islands by clearances); the task brief explicitly
  accepts this for v1 and notes that a polygon-exact zone encoding is the
  documented future tightening. Measured on the production board this still
  leaves large viable regions (see ``docs/evidence/2026-08-01-fixed-copper-
  constraint.md``).
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

If CP-SAT declares the placement feasible, every pad rect avoids every
``E``, hence avoids every ``S ⊕ margin``, hence every point of every pad is
at least ``margin`` from every point of every different-net fixed-copper
shape on a shared layer. The encoded predicate therefore *implies* the
exact geometric predicate: **no false negatives** (the encoding can never
accept a placement that shorts). The encoding *can* reject placements that
are exactly clear — that is the conservatism, bounded per item kind by the
corner-overhang expressions above (``(√2 − 1)·(half_extent + margin)`` for
segments/vias, unbounded for zones in the worst case, zero for pads).

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
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from temper_placer.placer.cp_sat.model import CpSatModel

logger = logging.getLogger(__name__)

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


@dataclass(frozen=True)
class PadRectLocal:
    """One pad of a *free* component, in the component's local (pre-
    rotation) placement frame.

    ``center`` is the pad's offset from the component placement centre (mm,
    solver frame) and ``half`` its local half-extents (mm). ``layers`` is
    the set of copper layers the pad occupies (all four for THT pads).
    """

    number: str
    net: str | None
    layers: frozenset[str]
    center: tuple[float, float]
    half: tuple[float, float]


@dataclass(frozen=True)
class FixedCopperItem:
    """One fixed-copper obstacle.

    ``rect`` is the *encoded* obstacle: the conservative axis-aligned box,
    already expanded by the margin, in mm. ``exact`` is the raw copper
    geometry consumed by the oracle/audit (see ``exact_clearance_mm``).
    ``slack_mm`` is the documented worst-case conservatism this item's box
    introduces over its exact shape (see module docstring).
    """

    kind: str  # "segment" | "via" | "zone" | "pad"
    net: str | None
    layers: frozenset[str]
    rect: tuple[float, float, float, float]  # (x0, y0, x1, y1) expanded, mm
    exact: Any
    slack_mm: float
    margin_mm: float
    label: str = ""


@dataclass
class FixedCopperAuditViolation:
    """A post-solve mismatch: an encoded-clear placement whose exact
    pad-to-copper clearance is below the margin (an encoding bug)."""

    ref: str
    pad_number: str
    item_label: str
    item_kind: str
    item_net: str | None
    required_mm: float
    actual_mm: float
    reason: str


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
    "encoded_pad_world_rect",
    "exact_clearance_mm",
    "pad_world_rect",
    "segment_slack_mm",
]


# ---------------------------------------------------------------------------
# Pad geometry
# ---------------------------------------------------------------------------


def _pin_copper_layers(pin: Any) -> frozenset[str]:
    """The copper layers a parsed Pin occupies.

    Through-hole pads (``layer == "all"`` or ``is_pth``) sit on all four
    copper layers; SMD pads on their declared copper layer.
    """
    if getattr(pin, "is_pth", False) or getattr(pin, "layer", None) == "all":
        return COPPER_LAYERS
    layer = getattr(pin, "layer", None)
    if layer in COPPER_LAYERS:
        return frozenset({layer})
    return frozenset()


def _local_pad_half(pin: Any) -> tuple[float, float]:
    """Conservative local half-extents (hw, hh) of one pin's copper,
    accounting for the pad's own intrinsic rotation.

    For an axis-aligned local rectangle the half-extents are exactly
    ``(width/2, height/2)``. If the pad carries a non-zero intrinsic
    rotation (``pad_rotation_deg``), the *axis-aligned bounding box* of the
    rotated rectangle is used — a conservative superset of the real copper.
    """
    hw = float(getattr(pin, "width", 1.0)) / 2.0
    hh = float(getattr(pin, "height", 1.0)) / 2.0
    phi = math.radians(float(getattr(pin, "pad_rotation_deg", 0.0)) % 180.0)
    if phi == 0.0:
        return (hw, hh)
    c, s = abs(math.cos(phi)), abs(math.sin(phi))
    return (hw * c + hh * s, hw * s + hh * c)


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
    """
    pads_by_ref: dict[str, list[PadRectLocal]] = {}
    for comp in netlist.components:
        ref = comp.ref
        if ref not in free_refs:
            continue
        pads: list[PadRectLocal] = []
        for pin in comp.pins:
            layers = _pin_copper_layers(pin) & copper_layers
            if not layers:
                continue
            hw, hh = _local_pad_half(pin)
            pads.append(
                PadRectLocal(
                    number=str(getattr(pin, "number", "")),
                    net=getattr(pin, "net", None),
                    layers=layers,
                    center=tuple(getattr(pin, "position", (0.0, 0.0))),
                    half=(hw, hh),
                )
            )
        pads_by_ref[ref] = pads
    return pads_by_ref


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
    """
    lx, ly = pad.center
    hw, hh = pad.half
    if rot_idx == 0:
        return (lx, ly, hw, hh)
    if rot_idx == 1:
        return (ly, -lx, hh, hw)
    if rot_idx == 2:
        return (-lx, -ly, hw, hh)
    return (-ly, lx, hh, hw)


def pad_world_rect(
    pad: PadRectLocal, center_mm: tuple[float, float], rot_idx: int
) -> tuple[float, float, float, float]:
    """The pad's world axis-aligned rectangle (x0, y0, x1, y1) in mm for a
    component placed at ``center_mm`` with quadrant rotation ``rot_idx``.

    This is the exact geometry the post-solve audit re-derives from resolved
    coordinates; the CP-SAT encoding below encodes the same rectangle
    affinely (offset + half-extent tables) so the two cannot drift.
    """
    ox, oy, hwx, hwy = _rotated(pad, rot_idx)
    cx, cy = center_mm
    return (cx + ox - hwx, cy + oy - hwy, cx + ox + hwx, cy + oy + hwy)


def _clamped_half_mm(half_mm: float) -> float:
    """The half-extent (mm) the CP-SAT encoder actually encodes for a pad of
    local half-extent ``half_mm``.

    ``_pad_rotation_tables_with`` clamps every half-extent to a minimum of
    ``_MIN_HALF_UNITS`` model units (0.01 mm) so the encoded interval stays
    strictly non-degenerate (CP-SAT intervals require positive size). A
    genuinely degenerate pad (zero-size rectangle) therefore encodes as a
    0.02 mm-wide box, NOT a point -- strictly more conservative than the
    exact geometry. This function mirrors that clamp in mm so the BMC
    test's encoded predicate and the encoder cannot drift apart.
    """
    return max(_MIN_HALF_MM, half_mm)


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
    """
    ox, oy, hwx, hwy = _rotated(pad, rot_idx)
    hwx = max(_MIN_HALF_MM, hwx)
    hwy = max(_MIN_HALF_MM, hwy)
    cx, cy = center_mm
    return (cx + ox - hwx, cy + oy - hwy, cx + ox + hwx, cy + oy + hwy)


# ---------------------------------------------------------------------------
# Fixed-copper item building
# ---------------------------------------------------------------------------


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
    """
    box = (
        min(p0[0], p1[0]) - width / 2.0 - margin,
        min(p0[1], p1[1]) - width / 2.0 - margin,
        max(p0[0], p1[0]) + width / 2.0 + margin,
        max(p0[1], p1[1]) + width / 2.0 + margin,
    )
    corners = [
        (box[0], box[1]),
        (box[2], box[1]),
        (box[2], box[3]),
        (box[0], box[3]),
    ]
    worst = 0.0
    for c in corners:
        excess = _point_segment_distance(c, p0, p1) - width / 2.0 - margin
        if excess > worst:
            worst = excess
    return worst


def _segment_item(start, end, width, net, layers, margin) -> FixedCopperItem:
    """Conservative box for a thick trace segment (see module docstring)."""
    (x1a, y1a), (x2a, y2a) = (float(start[0]), float(start[1])), (float(end[0]), float(end[1]))
    pad = width / 2.0 + margin
    x0, x1 = min(x1a, x2a) - pad, max(x1a, x2a) + pad
    y0, y1 = min(y1a, y2a) - pad, max(y1a, y2a) + pad
    return FixedCopperItem(
        kind="segment",
        net=net,
        layers=layers,
        rect=(x0, y0, x1, y1),
        exact={"p0": (x1a, y1a), "p1": (x2a, y2a), "width": width},
        slack_mm=segment_slack_mm((x1a, y1a), (x2a, y2a), width, margin),
        margin_mm=margin,
        label=f"segment {net} ({x1a:.2f},{y1a:.2f})-({x2a:.2f},{y2a:.2f})",
    )


def _via_item(position, diameter, net, layers, margin) -> FixedCopperItem:
    pad = diameter / 2.0 + margin
    x, y = float(position[0]), float(position[1])
    return FixedCopperItem(
        kind="via",
        net=net,
        layers=layers,
        rect=(x - pad, y - pad, x + pad, y + pad),
        exact={"center": (x, y), "diameter": diameter},
        slack_mm=(math.sqrt(2.0) - 1.0) * pad,
        margin_mm=margin,
        label=f"via {net} ({x:.2f},{y:.2f}) d={diameter:.2f}",
    )


def _zone_item(zone, margin) -> FixedCopperItem | None:
    """Conservative box for a zone (pour) outline.

    Returns ``None`` for zones with no usable polygon (degenerate/empty).
    """
    polygon = zone.polygon
    if not polygon or len(polygon) < 3:
        return None
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    margin = float(margin)
    layers = frozenset(zone.layers) & COPPER_LAYERS
    if not layers:
        return None
    net = zone.net_classes[0] if zone.net_classes else None
    # The bbox corner overhang vs the polygon is not bounded analytically
    # for an arbitrary outline (a long diagonal pour's bbox corner can be
    # arbitrarily far from the polygon), so slack is recorded as
    # unbounded-by-construction and the conservatism is documented, not
    # bounded. The soundness direction (bbox ⊇ polygon ⊕ margin) is what
    # the proof needs; the slack bound is the documented future tightening.
    return FixedCopperItem(
        kind="zone",
        net=net,
        layers=layers,
        rect=(min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin),
        exact={"polygon": list(polygon)},
        slack_mm=float("inf"),
        margin_mm=margin,
        label=f"zone {zone.name} net={net}",
    )


def _other_component_pad_item(
    comp: Any, pin: Any, margin: float, copper_layers: frozenset[str]
) -> FixedCopperItem | None:
    """One pinned component's pad as a fixed obstacle, in the solver frame.

    Uses the pinned component's ``initial_position``/``initial_rotation``
    (its solver-fixed placement), the same frame ``build_free_component_pads``
    uses for free components' pads.
    """
    layers = _pin_copper_layers(pin) & copper_layers
    if not layers:
        return None
    center = comp.initial_position
    if center is None:
        return None
    rot_idx = int(comp.initial_rotation or 0)
    hw, hh = _local_pad_half(pin)
    lx, ly = (float(pin.position[0]), float(pin.position[1]))
    if rot_idx == 0:
        ox, oy, hwx, hwy = lx, ly, hw, hh
    elif rot_idx == 1:
        ox, oy, hwx, hwy = ly, -lx, hh, hw
    elif rot_idx == 2:
        ox, oy, hwx, hwy = -lx, -ly, hw, hh
    else:
        ox, oy, hwx, hwy = -ly, lx, hh, hw
    cx, cy = float(center[0]), float(center[1])
    rect = (cx + ox - hwx, cy + oy - hwy, cx + ox + hwx, cy + oy + hwy)
    return FixedCopperItem(
        kind="pad",
        net=getattr(pin, "net", None),
        layers=layers,
        rect=(rect[0] - margin, rect[1] - margin, rect[2] + margin, rect[3] + margin),
        exact={"rect": rect},
        slack_mm=(math.sqrt(2.0) - 1.0) * margin,
        margin_mm=margin,
        label=f"pad {comp.ref}.{pin.number} net={pin.net}",
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
    """
    board = parse_result.board
    origin = tuple(board.origin) if board is not None else (0.0, 0.0)
    ox0, oy0 = float(origin[0]), float(origin[1])

    items: list[FixedCopperItem] = []

    # Traces (raw frame -> normalized).
    for t in parse_result.traces:
        if t.layer not in copper_layers:
            continue
        start = (t.start[0] - ox0, t.start[1] - oy0)
        end = (t.end[0] - ox0, t.end[1] - oy0)
        items.append(
            _segment_item(start, end, t.width, t.net, frozenset({t.layer}), margin_mm)
        )

    # Vias (raw frame -> normalized).
    for v in parse_result.vias:
        layers = frozenset(v.layers) & copper_layers
        if not layers:
            continue
        pos = (v.position[0] - ox0, v.position[1] - oy0)
        items.append(_via_item(pos, v.diameter, v.net, layers, margin_mm))

    # Zones (already normalized).
    for z in board.zones if board is not None else []:
        item = _zone_item(z, margin_mm)
        if item is not None:
            items.append(item)

    # Pinned components' pads.
    if include_other_pads:
        for comp in netlist.components:
            if comp.ref in free_refs:
                continue
            for pin in comp.pins:
                item = _other_component_pad_item(comp, pin, margin_mm, copper_layers)
                if item is not None:
                    items.append(item)

    return items


# ---------------------------------------------------------------------------
# CP-SAT encoding
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
    """One (pad, item) BoolOr disjunction, gated on *assumption*."""
    m = model
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


def _point_segment_distance(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    """Euclidean distance from a point to a segment."""
    px, py = p
    (ax, ay), (bx, by) = a, b
    dx, dy = bx - ax, by - ay
    if dx == 0.0 and dy == 0.0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _point_rect_distance(p: tuple[float, float], rect: tuple[float, float, float, float]) -> float:
    """Euclidean distance from a point to an axis-aligned rectangle (0 if inside)."""
    x, y = p
    x0, y0, x1, y1 = rect
    if x0 <= x <= x1 and y0 <= y <= y1:
        return 0.0
    return min(
        _point_segment_distance(p, (x0, y0), (x1, y0)),
        _point_segment_distance(p, (x1, y0), (x1, y1)),
        _point_segment_distance(p, (x1, y1), (x0, y1)),
        _point_segment_distance(p, (x0, y1), (x0, y0)),
    )


def _segments_intersect(a0, a1, b0, b1) -> bool:
    """True if segments a0-a1 and b0-b1 properly or improperly intersect."""
    (ax0, ay0), (ax1, ay1) = a0, a1
    (bx0, by0), (bx1, by1) = b0, b1

    def ccw(px, py, qx, qy, rx, ry) -> float:
        return (qx - px) * (ry - py) - (qy - py) * (rx - px)

    d1 = ccw(bx0, by0, bx1, by1, ax0, ay0)
    d2 = ccw(bx0, by0, bx1, by1, ax1, ay1)
    d3 = ccw(ax0, ay0, ax1, ay1, bx0, by0)
    d4 = ccw(ax0, ay0, ax1, ay1, bx1, by1)
    if ((d1 > 0 > d2) or (d1 < 0 < d2)) and ((d3 > 0 > d4) or (d3 < 0 < d4)):
        return True
    on_a = (d1 == 0 and min(bx0, bx1) <= ax0 <= max(bx0, bx1)
            and min(by0, by1) <= ay0 <= max(by0, by1))
    on_a_end = (d2 == 0 and min(bx0, bx1) <= ax1 <= max(bx0, bx1)
                and min(by0, by1) <= ay1 <= max(by0, by1))
    on_b = (d3 == 0 and min(ax0, ax1) <= bx0 <= max(ax0, ax1)
            and min(ay0, ay1) <= by0 <= max(ay0, ay1))
    on_b_end = (d4 == 0 and min(ax0, ax1) <= bx1 <= max(ax0, ax1)
                and min(ay0, ay1) <= by1 <= max(ay0, ay1))
    return on_a or on_a_end or on_b or on_b_end


def _rect_segment_distance(rect: tuple[float, float, float, float], a, b) -> float:
    """Euclidean distance from an axis-aligned rect to a segment (0 if they
    intersect). Exact for convex sets: check intersection, then min over
    vertex-to-opposite-set distances."""
    x0, y0, x1, y1 = rect
    if _segments_intersect(a, b, (x0, y0), (x1, y0)) or _segments_intersect(a, b, (x1, y0), (x1, y1)):
        return 0.0
    if _segments_intersect(a, b, (x1, y1), (x0, y1)) or _segments_intersect(a, b, (x0, y1), (x0, y0)):
        return 0.0
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    d = min(_point_segment_distance(c, a, b) for c in corners)
    d = min(d, _point_rect_distance(a, rect), _point_rect_distance(b, rect))
    return max(0.0, d)


def _rect_rect_gap(ra: tuple[float, float, float, float], rb: tuple[float, float, float, float]) -> float:
    """Gap (edge-to-edge) between two axis-aligned rectangles; 0 if they
    overlap or touch."""
    if (
        ra[0] <= rb[2] and rb[0] <= ra[2] and ra[1] <= rb[3] and rb[1] <= ra[3]
    ):
        return 0.0
    dx = max(0.0, max(rb[0] - ra[2], ra[0] - rb[2]))
    dy = max(0.0, max(rb[1] - ra[3], ra[1] - rb[3]))
    return math.hypot(dx, dy)  # exact Euclidean gap between the two boxes


def exact_clearance_mm(pad_rect: tuple[float, float, float, float], item: FixedCopperItem) -> float:
    """The exact copper-to-copper clearance between a pad's world rectangle
    and an item's raw copper shape (mm), 0 if they touch/overlap.

    This is the truthful oracle the BMC test and the post-solve audit share.
    """
    if item.kind == "segment":
        p0, p1 = item.exact["p0"], item.exact["p1"]
        return max(0.0, _rect_segment_distance(pad_rect, p0, p1) - item.exact["width"] / 2.0)
    if item.kind == "via":
        center = item.exact["center"]
        return max(0.0, _point_rect_distance(center, pad_rect) - item.exact["diameter"] / 2.0)
    if item.kind == "pad":
        return _rect_rect_gap(pad_rect, item.exact["rect"])
    if item.kind == "zone":
        from shapely.geometry import Polygon, box
        from shapely.prepared import prep

        poly = Polygon(item.exact["polygon"])
        if not poly.is_valid:
            poly = poly.buffer(0)
        p = prep(poly)
        pad = box(*pad_rect)
        if p.intersects(pad):
            return 0.0
        return float(pad.distance(poly))
    raise ValueError(f"unknown fixed-copper item kind {item.kind!r}")


def exact_overlap(pad_rect: tuple[float, float, float, float], item: FixedCopperItem) -> bool:
    """True if the pad overlaps the item's exact copper within the margin."""
    return exact_clearance_mm(pad_rect, item) < item.margin_mm


def encoded_overlap(pad_rect: tuple[float, float, float, float], item: FixedCopperItem) -> bool:
    """The encoded predicate: does the pad's world rect overlap the item's
    (margin-expanded) box? Mirrors ``_add_no_overlap``'s negation."""
    x0, y0, x1, y1 = pad_rect
    rx0, ry0, rx1, ry1 = item.rect
    return not (x1 <= rx0 or rx1 <= x0 or y1 <= ry0 or ry1 <= y0)


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
    """
    violations: list[FixedCopperAuditViolation] = []
    for ref, pads in pads_by_ref.items():
        center = resolved_positions_mm.get(ref)
        if center is None:
            violations.append(
                FixedCopperAuditViolation(
                    ref=ref,
                    pad_number="",
                    item_label="",
                    item_kind="",
                    item_net=None,
                    required_mm=0.0,
                    actual_mm=float("nan"),
                    reason=f"missing resolved position for {ref}",
                )
            )
            continue
        rot_idx = int(resolved_rotations.get(ref, 0))
        comp_nets = {p.net for p in pads if p.net}
        for pad in pads:
            rect = pad_world_rect(pad, center, rot_idx)
            for item in items:
                if not (pad.layers & item.layers):
                    continue
                if item.net is not None and item.net in comp_nets:
                    continue
                actual = exact_clearance_mm(rect, item)
                if actual < item.margin_mm:
                    violations.append(
                        FixedCopperAuditViolation(
                            ref=ref,
                            pad_number=pad.number,
                            item_label=item.label,
                            item_kind=item.kind,
                            item_net=item.net,
                            required_mm=item.margin_mm,
                            actual_mm=actual,
                            reason=(
                                f"{ref} pad {pad.number} is {actual:.4f}mm from "
                                f"{item.kind} ({item.net}) but {item.margin_mm}mm "
                                f"is required"
                            ),
                        )
                    )
    return violations
