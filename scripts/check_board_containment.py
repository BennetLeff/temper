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


def extract_outline(board):
    """The board outline polygon from the Edge.Cuts layer.

    Handles the canonical case (a single ``gr_poly`` on Edge.Cuts, which is
    what ``pcb/temper.kicad_pcb`` carries) and falls back to assembling
    ``gr_line`` segments into a ring. Fails closed if neither yields a
    polygon with area -- a board whose outline cannot be determined must
    never be reported as "everything is inside it".
    """
    Polygon, _box, _rotate, _translate = _require_shapely()

    polys = []
    segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for item in board.graphicItems:
        if getattr(item, "layer", None) != EDGE_LAYER:
            continue
        coords = getattr(item, "coordinates", None)
        if coords:
            pts = [(p.X, p.Y) for p in coords]
            if len(pts) >= 3:
                polys.append(Polygon(pts))
            continue
        start = getattr(item, "start", None)
        end = getattr(item, "end", None)
        if start is not None and end is not None:
            segments.append(((start.X, start.Y), (end.X, end.Y)))

    if polys:
        outline = max(polys, key=lambda p: p.area)
    elif segments:
        outline = _ring_from_segments(segments, Polygon)
    else:
        raise GateError(
            f"no {EDGE_LAYER} outline found on the board -- the board's "
            "extent is undetermined, so containment cannot be checked"
        )

    if not outline.is_valid:
        outline = outline.buffer(0)
    if outline.is_empty or outline.area <= 0:
        raise GateError(
            f"the {EDGE_LAYER} outline encloses no area -- containment "
            "cannot be checked against a degenerate outline"
        )
    return outline


def _ring_from_segments(segments, Polygon):
    """Assemble gr_line segments into the largest closed ring found."""
    remaining = list(segments)
    best = None
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
            poly = Polygon(chain)
            if best is None or poly.area > best.area:
                best = poly
    if best is None:
        raise GateError(
            f"{EDGE_LAYER} segments do not form a closed outline -- "
            "containment cannot be checked against an open outline"
        )
    return best


def _close(a, b, tol: float = 1e-6) -> bool:
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


def _pad_polygons(footprint, box, rotate, translate, place, shapely_angle):
    """Absolute copper polygon for each pad of *footprint*.

    A pad's ``size`` is its extent in the pad's own frame; its effective
    board rotation is its own ``angle`` when KiCad wrote one (KiCad stores
    the pad angle already composed with the footprint's) and the
    footprint's rotation otherwise.
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
        rect = box(-half_x, -half_y, half_x, half_y)
        rect = rotate(rect, shapely_angle(angle), origin=(0, 0))
        ax, ay = place(
            pad.position.X,
            pad.position.Y,
            footprint.position.X,
            footprint.position.Y,
            fp_angle,
        )
        yield pad.number, translate(rect, ax, ay), (ax, ay)


def analyze_board(board_path: Path) -> ContainmentReport:
    """Check every footprint's copper against the board outline."""
    Polygon, box, rotate, translate = _require_shapely()
    place, shapely_angle = _require_kicad_transform()

    board = load_board(board_path)
    outline = extract_outline(board)

    violations: list[Violation] = []
    pads_checked = 0
    for footprint in board.footprints:
        props = footprint.properties or {}
        ref = props.get("Reference") or "<no Reference>"
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
