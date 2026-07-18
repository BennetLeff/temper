"""Regression tests for _extract_courtyards' real-geometry extraction.

Covers the bug in docs/solutions/logic-errors/
courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md
("Second, Separate, Still-Open Bug" -- now fixed): _extract_courtyards'
"Strategy 1" only recognized courtyard graphic items exposing `.points`
or `.coordinates` (an fp_poly-only shape). Real KiCad footprints almost
always draw F.CrtYd using fp_rect, fp_line rectangles, or fp_circle --
none of which have those attributes -- so Strategy 1 matched 0/149
footprints on the real production board despite 142/149 having real
courtyard graphics, silently falling through to a pad-bounding-box
approximation for all of them. That approximation is centered on the
footprint origin and ignores courtyard margin entirely, which is
especially wrong for components (like large radial capacitors) whose
mechanical body/keepout extends well past their pads.
"""

from kiutils.items.fpitems import FpCircle, FpLine, FpRect
from kiutils.footprint import Footprint

from temper_placer.io.kicad_metadata import _extract_courtyards


class _FakeBoard:
    def __init__(self, footprints):
        self.footprints = footprints


def _footprint(ref: str, graphic_items: list) -> Footprint:
    fp = Footprint(entryName=ref)
    fp.properties = {"Reference": ref}
    fp.graphicItems = graphic_items
    fp.pads = []
    return fp


def test_fp_rect_courtyard_extracted_as_real_rectangle():
    """fp_rect gives two DIAGONAL corners, not two points on an edge --
    naively hulling just those two points degenerates to a line. The
    extractor must expand to all 4 corners."""
    rect = FpRect()
    rect.start.X, rect.start.Y = -2.0, -1.0
    rect.end.X, rect.end.Y = 2.0, 1.0
    rect.layer = "F.CrtYd"

    board = _FakeBoard([_footprint("R1", [rect])])
    courtyards = _extract_courtyards(board)

    poly = courtyards["R1"]._polygon
    assert poly.area == 8.0, f"expected 4x2mm rectangle (area 8.0), got area {poly.area}"
    minx, miny, maxx, maxy = poly.bounds
    assert (minx, miny, maxx, maxy) == (-2.0, -1.0, 2.0, 1.0)


def test_fp_line_rectangle_courtyard_extracted_correctly():
    """Real KiCad footprints commonly draw a courtyard rectangle as 4
    separate fp_line edges rather than a single fp_poly -- this must
    reconstruct the same rectangle, not fall through to the pad-bbox
    fallback."""
    def _line(x1, y1, x2, y2):
        line = FpLine()
        line.start.X, line.start.Y = x1, y1
        line.end.X, line.end.Y = x2, y2
        line.layer = "F.CrtYd"
        return line

    lines = [
        _line(-3.5, -1.75, 3.5, -1.75),
        _line(3.5, -1.75, 3.5, 1.75),
        _line(3.5, 1.75, -3.5, 1.75),
        _line(-3.5, 1.75, -3.5, -1.75),
    ]

    board = _FakeBoard([_footprint("D1", lines)])
    courtyards = _extract_courtyards(board)

    poly = courtyards["D1"]._polygon
    minx, miny, maxx, maxy = poly.bounds
    assert (minx, miny, maxx, maxy) == (-3.5, -1.75, 3.5, 1.75)


def test_fp_circle_courtyard_extracted_with_correct_center_and_radius():
    """fp_circle courtyards (e.g. large radial capacitors) must be
    extracted as a circle around their TRUE center -- which may be offset
    from the footprint origin -- not collapsed to a tiny fallback box."""
    circle = FpCircle()
    circle.center.X, circle.center.Y = 5.0, 0.0
    circle.end.X, circle.end.Y = 22.75, 0.0  # radius = 17.75
    circle.layer = "F.CrtYd"

    board = _FakeBoard([_footprint("C1", [circle])])
    courtyards = _extract_courtyards(board)

    poly = courtyards["C1"]._polygon
    centroid = poly.centroid
    assert abs(centroid.x - 5.0) < 0.05
    assert abs(centroid.y - 0.0) < 0.05
    # Circle area = pi * r^2; polygon approximation should be close.
    import math
    expected_area = math.pi * 17.75**2
    assert abs(poly.area - expected_area) / expected_area < 0.01


def test_footprint_with_no_courtyard_layer_falls_back_to_pad_bbox():
    """Footprints with genuinely no F.CrtYd graphics (rare, 7/149 on the
    production board) must still fall through to the pad-bbox strategy --
    this fix must not break the legitimate fallback path."""
    fp = _footprint("U1", [])
    # No pads either -> ultimate 1mm x 1mm fallback.
    board = _FakeBoard([fp])
    courtyards = _extract_courtyards(board)

    poly = courtyards["U1"]._polygon
    assert poly.area == 1.0  # 1mm x 1mm ultimate fallback square
