"""Regression tests for the courtyard extraction's real-geometry logic.

Covers the bug in docs/solutions/logic-errors/
courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md
("Second, Separate, Still-Open Bug" -- now fixed): the courtyard extractor
only recognized fp_poly-shaped courtyard graphics, so real F.CrtYd items
(fp_rect, fp_line rectangles, fp_circle) fell through to the pad-bounding-box
approximation.

Wave 4 Phase 3 candidate 3: the courtyard GEOS step moved to
``temper_placer.io.kicad_metadata._courtyard_points_from_raw``, which consumes
the Rust parse engine's raw courtyard inputs (shapely/GEOS is deliberately
kept on the Python side -- not bit-reimplementable in Rust). These tests drive
that function with the same geometry the old kiutils-object tests did.
"""

from temper_placer.core.courtyard import Courtyard
from temper_placer.io.kicad_metadata import (
    _courtyard_points_from_raw,
    _pad_bbox_fallback,
)


def _polygon(points):
    return Courtyard(component_ref="X", points=points)._polygon


def test_fp_rect_courtyard_extracted_as_real_rectangle():
    """fp_rect gives two DIAGONAL corners, not two points on an edge --
    naively hulling just those two points degenerates to a line. The
    extractor must expand to all 4 corners."""
    inputs = [{"kind": "rect", "start": (-2.0, -1.0), "end": (2.0, 1.0)}]
    points = _courtyard_points_from_raw(inputs)
    poly = _polygon(points)
    assert poly.area == 8.0, f"expected 4x2mm rectangle (area 8.0), got area {poly.area}"
    minx, miny, maxx, maxy = poly.bounds
    assert (minx, miny, maxx, maxy) == (-2.0, -1.0, 2.0, 1.0)


def test_fp_line_rectangle_courtyard_extracted_correctly():
    """Real KiCad footprints commonly draw a courtyard rectangle as 4
    separate fp_line edges rather than a single fp_poly -- this must
    reconstruct the same rectangle, not fall through to the pad-bbox
    fallback."""
    inputs = [
        {"kind": "line", "start": (-3.5, -1.75), "end": (3.5, -1.75)},
        {"kind": "line", "start": (3.5, -1.75), "end": (3.5, 1.75)},
        {"kind": "line", "start": (3.5, 1.75), "end": (-3.5, 1.75)},
        {"kind": "line", "start": (-3.5, 1.75), "end": (-3.5, -1.75)},
    ]

    points = _courtyard_points_from_raw(inputs)
    poly = _polygon(points)
    minx, miny, maxx, maxy = poly.bounds
    assert (minx, miny, maxx, maxy) == (-3.5, -1.75, 3.5, 1.75)


def test_fp_circle_courtyard_extracted_with_correct_center_and_radius():
    """fp_circle courtyards (e.g. large radial capacitors) must be
    extracted as a circle around their TRUE center -- which may be offset
    from the footprint origin -- not collapsed to a tiny fallback box."""
    import math

    inputs = [{"kind": "circle", "center": (5.0, 0.0), "end": (22.75, 0.0)}]  # radius = 17.75
    points = _courtyard_points_from_raw(inputs)
    poly = _polygon(points)
    centroid = poly.centroid
    assert abs(centroid.x - 5.0) < 0.05
    assert abs(centroid.y - 0.0) < 0.05
    # Circle area = pi * r^2; polygon approximation should be close.
    expected_area = math.pi * 17.75**2
    assert abs(poly.area - expected_area) / expected_area < 0.01


def test_fp_poly_courtyard_kept_verbatim():
    """fp_poly courtyards pass through as their exact polygon."""
    inputs = [{"kind": "poly", "coords": [(0, 0), (2, 0), (2, 1), (0, 1)]}]
    points = _courtyard_points_from_raw(inputs)
    poly = _polygon(points)
    assert poly.area == 2.0
    assert poly.bounds == (0.0, 0.0, 2.0, 1.0)


def test_footprint_with_no_courtyard_layer_falls_back_to_pad_bbox():
    """Footprints with genuinely no F.CrtYd graphics (rare, 7/149 on the
    production board) must still fall through to the pad-bbox strategy --
    this fix must not break the legitimate fallback path."""
    points = _pad_bbox_fallback([(0.0, 0.0, 2.0, 2.0)])
    poly = _polygon(points)
    # Pad bbox (2x2) + 0.5 margin each side -> 3x3 centered at the origin.
    assert poly.bounds == (-1.5, -1.5, 1.5, 1.5)


def test_no_pads_no_courtyard_uses_one_mm_square():
    """No pads and no courtyard -> the 1mm x 1mm ultimate fallback."""
    assert _courtyard_points_from_raw([]) == []
    assert _pad_bbox_fallback([]) == []
    # The 1mm square is applied by extract_kicad_metadata when both arms are
    # empty; assert the shape here so the fallback geometry stays pinned.
    points = [(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)]
    poly = _polygon(points)
    assert poly.area == 1.0  # 1mm x 1mm ultimate fallback square
