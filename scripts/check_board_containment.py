#!/usr/bin/env python3
"""Board-containment gate: every footprint's copper lies inside Edge.Cuts.

Why this gate exists
--------------------
The board-defect mutation corpus (R38, ``scripts/check_board_defect_corpus.py``)
seeds an *off-board component* defect -- a footprint moved outside the
Edge.Cuts outline -- and asserts that some gate fails on the result. Until
this file existed, no gate did. The corpus's manifest named
``courtyards_overlap`` and ``copper_edge_clearance`` as the class's "owning
gates", describing them as "the standing proxy for the R26 containment
invariant until R26 lands". Measured 2026-08-04, both proxies are vacuous
for this class:

  * ``copper_edge_clearance`` never fired on the off-board seed at all --
    not on today's board (12 -> 12) and not even on the board the corpus
    was originally seeded against (15 -> 15). It measures copper that is
    too CLOSE to the edge; copper that has left the board entirely is
    simply far from the edge, so the rule has nothing to say.
  * ``courtyards_overlap`` fired on the seed-era board (14 -> 29) only
    because that board's C26 was at rotation 0, so moving it to the seeded
    coordinate laid its 40mm-pitch axial body flat across a populated
    region and collided with 15 other courtyards. After the #517 placement
    re-solve moved all 169 footprints, C26 sits at rotation 270, the same
    move drops it into empty space past the bottom edge, and the count does
    not change (11 -> 11).

What this gate does NOT cover
-----------------------------
It detects a footprint MOVED outside the outline. It is structurally blind to a
footprint DELETED from the board, because `analyze_board` iterates
`board.footprints` -- a deleted footprint is never iterated, produces no
violation, and the gate exits 0. `footprints_checked` is reported but not
asserted against any expected inventory.

That distinction is not academic. Measured 2026-08-04 over all 169 footprints
(507 kicad-cli runs): deleting a component and moving it off-board produce
BYTE-IDENTICAL DRC signatures, so at the ratchet's resolution they are the same
event; 66 of 169 deletions reduce the total error count with zero penalised
above the nondeterminism floor, the most profitable being C4 at -46. See
`docs/plans/2026-08-04-*-drc-count-ratchet-*`.

Deletion is caught elsewhere -- `scripts/check_footprint_drift.py` and
`packages/temper-placer/src/temper_placer/validation/netlist_reconciliation.py`
both compare the board's footprint inventory against the netlist. This gate
deliberately does not duplicate that check; it records the boundary so that
"the off-board class is covered" is not misread as "component loss is covered".

Worse than "does not fire": with the component off the board, its copper
stops colliding with the rest of the layout, so the board's DRC numbers
IMPROVE. Measured on today's board, moving C26 off-outline moves
``hole_clearance`` 105 -> 102, ``shorting_items`` 200 -> 197 and
``solder_mask_bridge`` 154 -> 151 -- a net -9 errors. Under a
count-based ratchet, deleting a component from the board is rewarded. A
containment invariant is the only thing that makes that class visible.

What is checked
---------------
For every footprint on the board, every pad's copper polygon -- the pad
rectangle at its true size, rotated by the footprint's rotation using the
sanctioned KiCad convention (``temper_placer.geometry.kicad_transform``,
R(-theta); see ``scripts/check_no_raw_rotation_trig.py`` for why that
formula is never retyped locally) and translated to the footprint's board
position -- must be covered by the Edge.Cuts outline polygon.

Pad copper, not courtyard, is the checked surface. A courtyard is a
keep-out annotation and legitimately overhangs the outline on edge-mounted
parts (connectors, headers); pad copper outside the outline is not
manufacturable at all and is the exact, unambiguous signature of the
off-board-component class R26 names ("every component inside the outline").

Footprints with no pads (fiducials, logos, mounting-hole graphics) are not
silently skipped -- their origin point is required to be inside the
outline instead, so no footprint on the board goes unchecked.

Validation of the geometry
--------------------------
Run against the board this repo carried at 54372bbf (the commit the defect
corpus was seeded from), this gate reports C27's two pads fully outside the
outline at (20.0, 272.75) and (60.0, 272.75) -- independently rediscovering
the "tank cap staged off-outline at (at 20.0 272.75)" that
``scripts/board_defect_corpus.yaml`` and
``temper_placer/validation/netlist_reconciliation.py`` both document as a
real, known defect of that board. On today's committed board it reports
zero violations. Both halves are asserted in
``scripts/tests/test_check_board_containment.py``.

Exit codes:
  0 - every footprint's copper is inside the outline
  1 - at least one footprint has copper outside the outline
  2 - GATE ERROR: board missing/unparseable, no Edge.Cuts outline, or the
      sanctioned rotation module is unavailable -- never reported as a pass

Usage:
  uv run python scripts/check_board_containment.py
  uv run python scripts/check_board_containment.py --board path/to.kicad_pcb
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "packages/temper-placer/src"))

EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_GATE_ERROR = 2

DEFAULT_BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"

# Edge.Cuts is KiCad's board-outline layer. Only closed outlines drawn on it
# bound the manufactured board.
EDGE_LAYER = "Edge.Cuts"


class GateError(RuntimeError):
    """The gate could not run a trustworthy check -- fail closed (exit 2),
    never reported as a pass."""


@dataclass(frozen=True)
class Violation:
    """One piece of copper (or one pad-less footprint origin) outside the
    board outline."""

    ref: str
    sheetpath: str | None
    pad: str | None
    position_mm: tuple[float, float]
    outside_area_mm2: float
    fully_outside: bool

    @property
    def detail(self) -> str:
        what = f"pad {self.pad}" if self.pad is not None else "footprint origin"
        where = "fully outside" if self.fully_outside else "straddling"
        x, y = self.position_mm
        return (
            f"{self.ref} ({self.sheetpath or 'no sheetpath'}) {what} at "
            f"({x:.3f}, {y:.3f}) is {where} the board outline "
            f"[{self.outside_area_mm2:.4f} mm^2 of copper outside]"
        )


@dataclass
class ContainmentReport:
    board: str
    footprints_checked: int
    pads_checked: int
    outline_bounds_mm: tuple[float, float, float, float]
    violations: list[Violation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    def refs_outside(self) -> set[str]:
        """Reference designators with at least one violation -- the corpus's
        per-class assertion keys on this."""
        return {v.ref for v in self.violations}


def _require_shapely():
    try:
        from shapely.affinity import rotate, translate
        from shapely.geometry import Polygon, box
    except ImportError as exc:  # pragma: no cover - environment failure
        raise GateError(f"shapely is not installed: {exc}") from exc
    return Polygon, box, rotate, translate


KICAD_TRANSFORM_PATH = (
    REPO_ROOT
    / "packages/temper-placer/src/temper_placer/geometry/kicad_transform.py"
)


def _load_kicad_transform_by_path():
    """Load the sanctioned rotation module from its file, bypassing the
    ``temper_placer`` package ``__init__`` (which imports compiled Rust)."""
    import importlib.util

    if not KICAD_TRANSFORM_PATH.exists():
        raise GateError(
            f"sanctioned rotation module not found at {KICAD_TRANSFORM_PATH} "
            "-- this gate will not retype KiCad's footprint rotation formula "
            "locally (see check_no_raw_rotation_trig.py)"
        )
    spec = importlib.util.spec_from_file_location(
        "_temper_kicad_transform", KICAD_TRANSFORM_PATH
    )
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise GateError(f"could not load {KICAD_TRANSFORM_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.rotate_local_to_world_deg, module.shapely_rotation_angle_deg


def _require_kicad_transform():
    """The sanctioned footprint-child rotation convention. Retyping this
    formula locally is exactly what scripts/check_no_raw_rotation_trig.py
    exists to prevent (it was independently reimplemented wrongly 12 times
    and concealed real clearance hazards on 18 components)."""
    try:
        from temper_placer.geometry.kicad_transform import (
            rotate_local_to_world_deg,
            shapely_rotation_angle_deg,
        )
    except ImportError:
        # ``temper_placer/__init__.py`` pulls in the compiled Rust design
        # bundle. This gate is pure geometry over kiutils + shapely and has
        # no need of it, so fall back to loading the sanctioned rotation
        # module directly from its file. This is still the ONE sanctioned
        # implementation -- the formula is never retyped here -- it just
        # skips a package __init__ that would otherwise make a
        # rectangle-containment check depend on a multi-crate Rust build.
        rotate_local_to_world_deg, shapely_rotation_angle_deg = _load_kicad_transform_by_path()

    def place(local_x, local_y, origin_x, origin_y, theta_deg):
        rx, ry = rotate_local_to_world_deg(local_x, local_y, theta_deg)
        return (origin_x + rx, origin_y + ry)

    return place, shapely_rotation_angle_deg


def load_board(board_path: Path):
    """Parse the board with kiutils -- the same library the board-defect
    mutator, check_footprint_drift.py and check_copper_net_consistency.py
    already read this board with."""
    if not board_path.exists():
        raise GateError(f"board not found: {board_path}")
    try:
        from kiutils.board import Board
    except ImportError as exc:  # pragma: no cover - environment failure
        raise GateError(f"kiutils is not installed: {exc}") from exc
    try:
        return Board.from_file(str(board_path))
    except Exception as exc:  # kiutils raises plain Exception on malformed input
        raise GateError(f"could not parse {board_path}: {exc}") from exc


# Edge.Cuts items that carry no outline geometry. Anything on Edge.Cuts
# that is neither handled below nor named here raises, rather than being
# skipped: silently dropping a primitive is how this gate came to read a
# whole board's outline as "open" (see extract_outline's SHAPE-TYPE BLIND
# SPOT note).
_EDGE_ANNOTATION_TYPES = frozenset({"GrText", "GrTextBox"})

# Segment-join tolerance, in mm.
#
# KiCad stores board coordinates as integer NANOMETRES; 1e-6 mm is exactly
# one internal unit, so a file can legitimately carry a one-unit seam where
# two segments are meant to meet. The previous value WAS 1e-6 mm, which put
# the comparison exactly on that quantum -- and float64 lost:
# power_pcb_dataset/corpus/piantor_right/keyboard_pcb.kicad_pcb joins at
# y=113.600001 vs y=113.6, whose difference evaluates to
# 1.0000000116860974e-06, i.e. 1.17e-14 mm ABOVE a tolerance meant to
# admit it. That single rejected join opened the 40-segment main outline,
# and (before the fail-closed change in _rings_from_segments) the gate
# silently substituted the largest ring that DID close -- a 0.8 x 12.2 mm
# internal milled slot -- then reported all 310 pads on a 138.8 x 89.8 mm
# keyboard as "outside the board".
#
# 1e-3 mm = 1 micrometre = 1000 KiCad internal units, and is still 100x
# below the finest feature any PCB process in this project's fab envelope
# can hold (0.1 mm minimum trace/space, docs/evidence/2026-08-13-jlcpcb-
# fab-capability-envelope.md). It cannot merge two outline vertices that
# are genuinely distinct, and it is not a design rule -- it is a
# file-parsing seam tolerance.
_JOIN_TOL_MM = 1e-3


def _rect_ring(item) -> list[tuple[float, float]]:
    """The four corners of a ``gr_rect``.

    SHAPE-TYPE BLIND SPOT, fixed 2026-08-18. ``GrRect`` exposes ``start``
    and ``end`` just like ``GrLine`` does, so the old ``start``/``end``
    fallback turned an entire rectangular board outline into ONE straight
    segment along its diagonal -- a 2-point chain, which can never close.
    Both ``power_pcb_dataset/corpus/temper`` (``(gr_rect (start 0 0)
    (end 100 150))``, line 544) and ``power_pcb_dataset/corpus/minimal``
    (line 94, written by pcbnew itself) carry their whole outline as a
    single ``gr_rect``, and both were reported as having an open outline.
    This is the mirror image of the already-documented parser gap in
    docs/solutions/logic-errors/polygon-edge-cuts-parser-invisible-bbox-
    2026-07-15.md, where a different parser handled ``gr_rect``/``gr_line``
    and dropped ``gr_poly``.
    """
    x0, y0 = item.start.X, item.start.Y
    x1, y1 = item.end.X, item.end.Y
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _circle_ring(item, facets: int = 64) -> list[tuple[float, float]]:
    """A ``gr_circle`` outline as a polygon ring.

    ``GrCircle`` has ``center``/``end`` and NO ``start``, so the old
    fallback dropped it entirely and silently. A round board would have
    read as having no outline at all.
    """
    cx, cy = item.center.X, item.center.Y
    radius = math.hypot(item.end.X - cx, item.end.Y - cy)
    if radius <= 0:
        return []
    return [
        (cx + radius * math.cos(2 * math.pi * i / facets),
         cy + radius * math.sin(2 * math.pi * i / facets))
        for i in range(facets)
    ]


def extract_outline(board):
    """The board outline polygon from the Edge.Cuts layer.

    Handles ``gr_poly`` (what ``pcb/temper.kicad_pcb`` carries), ``gr_rect``
    and ``gr_circle`` as closed shapes in their own right, and assembles
    everything else that exposes ``start``/``end`` (``gr_line``, and
    ``gr_arc`` by its chord -- see the LIMITATION note) into closed rings.
    The largest resulting polygon is the outline. Fails closed if nothing
    yields a polygon with area -- a board whose outline cannot be determined
    must never be reported as "everything is inside it".

    LIMITATION, known and deliberately not fixed here: ``gr_arc`` is
    reduced to the straight chord between its endpoints; the ``mid`` bulge
    is discarded. On a convex corner fillet the chord cuts INSIDE the true
    edge, so the outline is under-measured and the gate can only
    over-report, never under-report. On a CONCAVE arc the polarity flips
    and it could under-report; no board in this repo or in
    ``power_pcb_dataset/corpus/`` has one today (checked 2026-08-18).
    ``power_pcb_dataset/corpus/rp2040_designguide`` parses only because its
    four 2.54 mm corner arcs' chords happen to meet its four ``gr_line``
    endpoints exactly -- that is luck, not support.
    """
    Polygon, _box, _rotate, _translate = _require_shapely()

    polys = []
    segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for item in board.graphicItems:
        if getattr(item, "layer", None) != EDGE_LAYER:
            continue
        kind = type(item).__name__
        coords = getattr(item, "coordinates", None)
        if coords:
            pts = [(p.X, p.Y) for p in coords]
            if len(pts) >= 3:
                polys.append(Polygon(pts))
            continue
        if kind == "GrRect":
            polys.append(Polygon(_rect_ring(item)))
            continue
        if kind == "GrCircle":
            ring = _circle_ring(item)
            if len(ring) >= 3:
                polys.append(Polygon(ring))
            continue
        if kind in _EDGE_ANNOTATION_TYPES:
            continue
        start = getattr(item, "start", None)
        end = getattr(item, "end", None)
        if start is not None and end is not None:
            segments.append(((start.X, start.Y), (end.X, end.Y)))
            continue
        raise GateError(
            f"unhandled {EDGE_LAYER} primitive {kind!r}: this gate does not "
            "know how to turn it into outline geometry, and refusing is the "
            "only safe answer -- an Edge.Cuts item skipped silently is an "
            "outline read smaller than the real board, which reports real "
            "copper as off-board (or, if it was the whole outline, reports "
            "the board as having none). Teach extract_outline the shape, or "
            "name it in _EDGE_ANNOTATION_TYPES if it is annotation."
        )

    candidates = list(polys)
    if segments:
        # Both sources are pooled rather than `polys or segments`: a board
        # whose outline is gr_line segments and whose internal slots are
        # gr_rect would otherwise have had the SLOTS win outright.
        candidates.extend(_rings_from_segments(segments, Polygon))
    if not candidates:
        raise GateError(
            f"no {EDGE_LAYER} outline found on the board -- the board's "
            "extent is undetermined, so containment cannot be checked"
        )
    outline = max(candidates, key=lambda p: p.area)

    if not outline.is_valid:
        outline = outline.buffer(0)
    if outline.is_empty or outline.area <= 0:
        raise GateError(
            f"the {EDGE_LAYER} outline encloses no area -- containment "
            "cannot be checked against a degenerate outline"
        )
    return outline


def _rings_from_segments(segments, Polygon):
    """Every closed ring the Edge.Cuts segments form.

    FAIL-CLOSED ON AN OPEN CONTOUR, changed 2026-08-18. This used to return
    the largest ring that closed and raise only when NOTHING closed. That
    made "the board's main outline did not close" a non-event whenever any
    smaller contour did: on
    ``power_pcb_dataset/corpus/piantor_right/keyboard_pcb.kicad_pcb`` the
    40-segment outline (9604.3 mm^2) failed to close over a 1 nm seam and a
    9.8 mm^2 milled slot silently became "the board", so the gate reported
    310 of 310 pads outside it and the corpus specificity run recorded that
    as a single ``<no Reference>`` finding. An outline that cannot be
    assembled is a gate error, never a smaller board.
    """
    remaining = list(segments)
    rings = []
    while remaining:
        chain = list(remaining.pop(0))
        progressed = True
        while progressed:
            progressed = False
            for i, (a, b) in enumerate(remaining):
                if _close(chain[-1], a):
                    chain.append(b)
                elif _close(chain[-1], b):
                    chain.append(a)
                elif _close(chain[0], b):
                    chain.insert(0, a)
                elif _close(chain[0], a):
                    chain.insert(0, b)
                else:
                    continue
                remaining.pop(i)
                progressed = True
                break
        if len(chain) >= 4 and _close(chain[0], chain[-1]):
            rings.append(Polygon(chain))
            continue
        raise GateError(
            f"{EDGE_LAYER} segments do not form a closed outline -- "
            "containment cannot be checked against an open outline. An "
            f"open contour of {len(chain)} point(s) runs from {chain[0]} to "
            f"{chain[-1]} (gap "
            f"{abs(chain[0][0] - chain[-1][0]):.9f}, "
            f"{abs(chain[0][1] - chain[-1][1]):.9f} mm; join tolerance "
            f"{_JOIN_TOL_MM} mm)."
        )
    return rings


def _close(a, b, tol: float = _JOIN_TOL_MM) -> bool:
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


def _pad_copper(pad, box, half_x: float, half_y: float):
    """The pad's copper in its own frame, by KiCad pad shape.

    Only the two shapes whose true outline is SMALLER than their bounding
    box in a way that matters are modelled exactly -- ``circle`` and
    ``oval``. Everything else (``rect``, ``roundrect``, ``trapezoid``,
    ``custom``) keeps the bounding box, which over-states copper and is
    therefore fail-closed: it can raise a false alarm, never miss real
    copper.

    Why ``circle`` had to be fixed (measured 2026-08-18). Modelling a
    circular pad as its circumscribing square adds ~21% phantom area, all
    of it in four corners the pad does not have. On
    ``power_pcb_dataset/corpus/bitaxe_ultra`` that produced FOUR false
    positives -- H7/H8/H9/H10, the corner ``MountingHole_3mm_Pad_Via``
    parts, whose 6 mm annular ring sits inside the rounded board corner
    while the square stand-in's corner pokes past it. Per pad: 0.96-1.23
    mm^2 reported outside as a square, 0.000000 mm^2 (``covers`` True) as
    the real circle. docs/evidence/2026-08-07-fault-injection-coverage-
    number.md:111-120 hypothesised these were real annular-ring overhang
    and left it "not resolved to certainty"; they are not, and it is.
    """
    shape = (getattr(pad, "shape", None) or "").lower()
    if shape == "circle":
        from shapely.geometry import Point

        # max, not min: a well-formed circle pad has size.X == size.Y, and
        # on a malformed one the larger radius is the fail-closed choice.
        return Point(0.0, 0.0).buffer(max(half_x, half_y), quad_segs=64)
    if shape == "oval":
        from shapely.geometry import LineString

        # A KiCad oval is a stadium: radius is the SHORT half-axis, swept
        # along the long one. This is exact, not an approximation.
        radius = min(half_x, half_y)
        reach_x, reach_y = half_x - radius, half_y - radius
        spine = LineString([(-reach_x, -reach_y), (reach_x, reach_y)])
        return spine.buffer(radius, quad_segs=64)
    return box(-half_x, -half_y, half_x, half_y)


def _pad_polygons(footprint, box, rotate, translate, place, shapely_angle):
    """Absolute copper polygon for each pad of *footprint*.

    A pad's ``size`` is its extent in the pad's own frame; its effective
    board rotation is its own ``angle`` when KiCad wrote one (KiCad stores
    the pad angle already composed with the footprint's) and the
    footprint's rotation otherwise. The shape within that extent comes from
    ``_pad_copper``.
    """
    fp_angle = footprint.position.angle or 0.0
    for pad in footprint.pads:
        if pad.size is None:
            continue
        pad_angle = pad.position.angle
        angle = fp_angle if pad_angle is None else pad_angle
        half_x, half_y = pad.size.X / 2.0, pad.size.Y / 2.0
        if half_x <= 0 or half_y <= 0:
            continue
        rect = _pad_copper(pad, box, half_x, half_y)
        rect = rotate(rect, shapely_angle(angle), origin=(0, 0))
        ax, ay = place(
            pad.position.X,
            pad.position.Y,
            footprint.position.X,
            footprint.position.Y,
            fp_angle,
        )
        yield pad.number, translate(rect, ax, ay), (ax, ay)


def _footprint_ref(footprint) -> str:
    """The footprint's reference designator, from either KiCad encoding.

    KiCad 9 writes ``(property "Reference" "R1" ...)``; KiCad <= 8 writes
    ``(fp_text reference "R1" ...)``. Reading only the first made EVERY
    footprint on a KiCad-8-era board anonymous: measured 2026-08-18,
    ``power_pcb_dataset/corpus/bitaxe_ultra`` has 0 ``property "Reference"``
    and 137 ``fp_text reference``, ``piantor_right`` 0 and 36. Because
    ``ContainmentReport.refs_outside()`` returns a SET, all 310 of
    piantor_right's violations then collapsed into the single string
    ``<no Reference>`` -- which is how a whole-board failure was recorded in
    docs/evidence/2026-08-07-fault-injection-coverage-number.md:109 as "1
    containment finding". A gate that cannot name what it flags cannot be
    triaged, and undercounts itself.
    """
    ref = (footprint.properties or {}).get("Reference")
    if ref:
        return ref
    for item in footprint.graphicItems or []:
        if getattr(item, "type", None) == "reference":
            text = getattr(item, "text", None)
            if text:
                return text
    return "<no Reference>"


def analyze_board(board_path: Path) -> ContainmentReport:
    """Check every footprint's copper against the board outline."""
    Polygon, box, rotate, translate = _require_shapely()
    place, shapely_angle = _require_kicad_transform()

    board = load_board(board_path)
    outline = extract_outline(board)

    violations: list[Violation] = []
    pads_checked = 0
    if not board.footprints:
        # A board with no footprints would sail through every loop below and
        # report zero violations -- a pass that checked nothing. This gate's
        # whole purpose is that a vacuous pass is worse than a failure.
        raise GateError(
            f"{board_path} declares no footprints; refusing to report a "
            f"containment pass over an empty inventory"
        )

    for footprint in board.footprints:
        props = footprint.properties or {}
        ref = _footprint_ref(footprint)
        sheetpath = props.get("Sheetpath")

        pad_polys = list(_pad_polygons(footprint, box, rotate, translate, place, shapely_angle))
        if not pad_polys:
            # Pad-less footprint (fiducial, logo, mounting-hole graphic):
            # check its origin so nothing on the board goes unchecked.
            from shapely.geometry import Point

            origin = Point(footprint.position.X, footprint.position.Y)
            if not outline.covers(origin):
                violations.append(
                    Violation(
                        ref=ref,
                        sheetpath=sheetpath,
                        pad=None,
                        position_mm=(footprint.position.X, footprint.position.Y),
                        outside_area_mm2=0.0,
                        fully_outside=True,
                    )
                )
            continue

        for number, poly, centre in pad_polys:
            pads_checked += 1
            if outline.covers(poly):
                continue
            violations.append(
                Violation(
                    ref=ref,
                    sheetpath=sheetpath,
                    pad=number,
                    position_mm=centre,
                    outside_area_mm2=poly.difference(outline).area,
                    fully_outside=not outline.intersects(poly),
                )
            )

    return ContainmentReport(
        board=str(board_path),
        footprints_checked=len(board.footprints),
        pads_checked=pads_checked,
        outline_bounds_mm=tuple(outline.bounds),
        violations=violations,
    )


def _print_report(report: ContainmentReport) -> None:
    x0, y0, x1, y1 = report.outline_bounds_mm
    print(f"board: {report.board}")
    print(f"outline (Edge.Cuts) bounds: ({x0:.2f}, {y0:.2f}) - ({x1:.2f}, {y1:.2f}) mm")
    print(f"checked: {report.footprints_checked} footprints, {report.pads_checked} pads")

    if report.ok:
        print("\nBoard containment: PASS -- all copper inside the board outline")
        return

    print(f"\nBoard containment: FAIL -- {len(report.violations)} violation(s)")
    for violation in sorted(
        report.violations, key=lambda v: (-v.outside_area_mm2, v.ref, v.pad or "")
    ):
        print(f"  [outside-outline] {violation.detail}")

    try:
        from _lib.github_summary import get_github_summary_path
    except ImportError:
        return
    summary = get_github_summary_path()
    if summary:
        with open(summary, "a") as handle:
            handle.write(
                "### Board Containment Gate -- FAILED\n"
                f"{len(report.violations)} piece(s) of copper outside the "
                "board outline\n\n"
            )
            for violation in report.violations[:200]:
                handle.write(f"- `[outside-outline]` {violation.detail}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--board", type=Path, default=DEFAULT_BOARD)
    args = parser.parse_args(argv)

    try:
        report = analyze_board(args.board)
    except GateError as exc:
        print("=== BOARD CONTAINMENT GATE ERROR ===", file=sys.stderr)
        print(f"Reason: {exc}", file=sys.stderr)
        print(
            "GATE RESULT: ERROR -- not PASSED, not a violation. The gate "
            "could not run a trustworthy check.",
            file=sys.stderr,
        )
        return EXIT_GATE_ERROR

    _print_report(report)
    return EXIT_OK if report.ok else EXIT_VIOLATION


if __name__ == "__main__":
    sys.exit(main())
