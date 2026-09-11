#!/usr/bin/env python3
"""Board-side component extraction for the firmware-assumption oracle.

Parses ``pcb/temper.kicad_pcb`` -- the board file, the physical truth --
and locates every registered component by its ``Sheetpath`` property
(NOT by refdes: refdes are assigned by the placer and renumber freely;
the ``Sheetpath`` (``tank.c_tank3``, ``rtd_pan.r_ref``) is the stable
identity that ties a placed footprint back to its ``elec/src/*.ato``
declaration).

Reads, per footprint:

- the footprint library id (``temper:C_Axial_...``) -- the physical part
  class on the board;
- the raw ``Value`` property (a netlist-populated board carries the part
  value here; this board's values are all the ``"?"`` placeholder, so the
  caller falls back to a registry footprint->value decode);
- the position ``(at x y)``;
- the board outline (all ``Edge.Cuts`` geometry), so a component present
  in the file but staged OUTSIDE the outline -- the exact defect class
  this oracle exists for: ``tank.c_tank3`` sits at (20.0, 272.75) while
  the outline spans y in [20, 254] -- is classified ABSENT, not placed.
  A plain refdes/value lookup would PASS an off-outline component; this
  extractor's outline test is what makes the defect visible.

Per-component disposition (``disposition(sheetpath)``):

- ``placed``       -- footprint present AND its position is inside the
                      board outline.
- ``off_outline``  -- footprint present in the file but its position is
                      outside the board outline (treated as absent by the
                      oracle: the part is not on the board).
- ``absent``       -- no footprint with that Sheetpath in the file at all.

Value classification (``value_state(sheetpath)``):

- ``value``        -- the ``Value`` property parsed to base SI units, or
                      (when the property is the ``"?"`` placeholder) the
                      registry footprint-decode passed in via
                      ``footprint_values``.
- ``value_unknown``-- placed, but no parseable value and no footprint
                      decode available.

Fail-closed contract (never an empty success): an unreadable board, a
non-s-expression file, a file that is not a ``kicad_pcb`` document, or a
board with NO Edge.Cuts geometry all raise :exc:`BoardParseError` -- the
caller must turn that into an explicit UNMEASURED/error, never a pass.

This is a deliberate pure-stdlib s-expression reader (same pattern as
``scripts/check_pad_orientation.py``), NOT kiutils: the firmware CI path
installs only ``firmware/tools/requirements.txt`` (jinja2 + pyyaml), and
this gate must be able to run there.

Host pytest: ``firmware/tools/test_board_component_extractor.py``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from board_derivation_lib import parse_si_value


class BoardParseError(Exception):
    """The board file could not be read/parsed -- never a silent pass."""


# ---------------------------------------------------------------------------
# Minimal s-expression reader. Deliberately not kiutils -- see module
# docstring. Same pattern as scripts/check_pad_orientation.py.
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+')


def parse_sexpr(text: str) -> list:
    """Parse an s-expression document into nested lists of str."""
    stack: list[list] = []
    cur: list = []
    for tok in _TOKEN_RE.findall(text):
        if tok == "(":
            stack.append(cur)
            cur = []
        elif tok == ")":
            if not stack:
                raise BoardParseError("unbalanced ')' in board file")
            parent = stack.pop()
            parent.append(cur)
            cur = parent
        else:
            cur.append(tok[1:-1] if tok.startswith('"') else tok)
    if stack:
        raise BoardParseError("unbalanced '(' in board file")
    return cur


def _children(node: list, key: str) -> list[list]:
    return [c for c in node if isinstance(c, list) and c and c[0] == key]


def _child(node: list, key: str) -> list | None:
    found = _children(node, key)
    return found[0] if found else None


# ---------------------------------------------------------------------------
# Board outline
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Point:
    x: float
    y: float


def _point_on_segment(pt: Point, a: Point, b: Point, tol: float = 1e-9) -> bool:
    """True when *pt* lies on the closed segment [a, b] (cross product
    ~ 0 and inside the segment's bounding box). KiCad coordinates are in
    mm; 1e-9 is far below any placement precision."""
    cross = (pt.y - a.y) * (b.x - a.x) - (pt.x - a.x) * (b.y - a.y)
    if abs(cross) > tol:
        return False
    return (
        min(a.x, b.x) - tol <= pt.x <= max(a.x, b.x) + tol
        and min(a.y, b.y) - tol <= pt.y <= max(a.y, b.y) + tol
    )


def _point_in_polygon(pt: Point, polygon: list[Point]) -> bool:
    """Point-in-polygon test: a point exactly ON the outline (a corner or
    an edge -- the outline's boundary belongs to the board) is inside;
    otherwise the standard even/odd ray-casting crossing count (the
    y-down KiCad board frame does not matter for a crossing count)."""
    for i in range(len(polygon)):
        if _point_on_segment(pt, polygon[i], polygon[(i + 1) % len(polygon)]):
            return True
    inside = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        xi, yi = polygon[i].x, polygon[i].y
        xj, yj = polygon[j].x, polygon[j].y
        if (yi > pt.y) != (yj > pt.y):
            x_cross = xi + (pt.y - yi) / (yj - yi) * (xj - xi)
            if pt.x < x_cross:
                inside = not inside
        j = i
    return inside


def _edge_cuts_polygon(board: list) -> list[Point]:
    """Collect the board outline from every Edge.Cuts item.

    Handles ``gr_poly`` (the current board's outline is a single
    rectangle), and ``gr_line``/``segment``/``gr_arc`` endpoints. Falls
    back to the bounding box of all Edge.Cuts vertices when the items do
    not form a single closed polygon -- the outline membership test is a
    conservative presence check, and a degenerate outline must never
    silently pass an off-board component.
    """
    vertices: list[Point] = []
    edge_cuts_polys: list[list[Point]] = []

    def _add(p: Point) -> None:
        if p not in vertices:
            vertices.append(p)

    for item in board:
        if not isinstance(item, list) or not item:
            continue
        kind = item[0]
        if kind not in ("gr_poly", "gr_line", "gr_arc", "segment"):
            continue
        layer = None
        for tok in item[1:]:
            if isinstance(tok, list) and tok and tok[0] == "layer":
                layer = tok[1] if len(tok) > 1 else None
                break
        if layer != "Edge.Cuts":
            continue

        if kind == "gr_poly":
            pts = _child(item, "pts")
            if pts is not None:
                poly = [
                    Point(float(xy[1]), float(xy[2]))
                    for xy in _children(pts, "xy")
                    if len(xy) >= 3
                ]
                if len(poly) >= 3:
                    edge_cuts_polys.append(poly)
                    for p in poly:
                        _add(p)
                    continue

        for sub in item[1:]:
            if not isinstance(sub, list) or not sub:
                continue
            if sub[0] == "start" and len(sub) >= 3:
                _add(Point(float(sub[1]), float(sub[2])))
            elif sub[0] == "end" and len(sub) >= 3:
                _add(Point(float(sub[1]), float(sub[2])))
            elif sub[0] == "mid" and len(sub) >= 3:
                _add(Point(float(sub[1]), float(sub[2])))

    if edge_cuts_polys:
        # The first closed Edge.Cuts polygon is the board outline.
        return edge_cuts_polys[0]

    if not vertices:
        raise BoardParseError("board has no Edge.Cuts geometry -- outline unknown, "
                              "component presence cannot be determined")

    # Otherwise: bounding box of all Edge.Cuts vertices -- a conservative
    # presence screen (an off-outline component is outside the box too).
    xs = [p.x for p in vertices]
    ys = [p.y for p in vertices]
    return [
        Point(min(xs), min(ys)),
        Point(max(xs), min(ys)),
        Point(max(xs), max(ys)),
        Point(min(xs), max(ys)),
    ]


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlacedComponent:
    sheetpath: str
    refdes: str
    footprint: str
    value_raw: str
    position: Point
    inside_outline: bool


@dataclass
class BoardReport:
    """Extraction result for one board file.

    ``components`` is keyed by ``Sheetpath`` property. ``disposition`` /
    ``value_state`` are helpers the oracle calls per registered component.
    """

    board_path: Path
    outline: list[Point]
    components: dict[str, PlacedComponent] = field(default_factory=dict)
    footprint_values: dict[str, float] = field(default_factory=dict)

    def disposition(self, sheetpath: str) -> str:
        """One of ``placed`` / ``off_outline`` / ``absent``."""
        comp = self.components.get(sheetpath)
        if comp is None:
            return "absent"
        return "placed" if comp.inside_outline else "off_outline"

    def value_state(self, sheetpath: str) -> tuple[str, float | None]:
        """``("value", float)`` when the component's value is derivable
        (parsed Value property, else registry footprint decode), else
        ``("value_unknown", None)``."""
        comp = self.components.get(sheetpath)
        if comp is None:
            return "value_unknown", None
        parsed = parse_si_value(comp.value_raw)
        if parsed is not None:
            return "value", parsed
        decoded = self.footprint_values.get(comp.footprint)
        if decoded is not None:
            return "value", decoded
        return "value_unknown", None


def extract_board(
    board_path: Path,
    *,
    footprint_values: dict[str, float] | None = None,
) -> BoardReport:
    """Parse *board_path* and return every placed component keyed by
    Sheetpath, plus the Edge.Cuts outline.

    *footprint_values* maps a footprint library id to its decoded value
    (base SI units) -- the oracle builds it from the registry's
    board-component decode table. Raises :exc:`BoardParseError` on any
    unreadable/unparseable board or on a missing outline.
    """
    if footprint_values is None:
        footprint_values = {}
    try:
        text = board_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise BoardParseError(f"cannot read {board_path}: {exc}") from exc

    doc = parse_sexpr(text)
    if not doc or not isinstance(doc[0], list):
        raise BoardParseError(f"{board_path} is not an s-expression document")
    board = doc[0]
    if not board or board[0] != "kicad_pcb":
        raise BoardParseError(f"{board_path} is not a kicad_pcb document")

    outline = _edge_cuts_polygon(board)

    components: dict[str, PlacedComponent] = {}
    for node in _children(board, "footprint") + _children(board, "module"):
        at = _child(node, "at")
        if at is None or len(at) < 3:
            continue
        props: dict[str, str] = {}
        for prop in _children(node, "property"):
            if len(prop) >= 3:
                props[prop[1]] = prop[2]

        sheetpath = props.get("Sheetpath")
        if not sheetpath:
            continue  # unregistered footprints (e.g. mounting holes) are not our concern

        footprint = node[1] if len(node) > 1 else ""
        position = Point(float(at[1]), float(at[2]))
        components[sheetpath] = PlacedComponent(
            sheetpath=sheetpath,
            refdes=props.get("Reference", ""),
            footprint=footprint,
            value_raw=props.get("Value", ""),
            position=position,
            inside_outline=_point_in_polygon(position, outline),
        )

    return BoardReport(
        board_path=board_path,
        outline=outline,
        components=components,
        footprint_values=dict(footprint_values),
    )
