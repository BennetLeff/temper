"""Zone parsing: non-rectangular warning + polygon extraction.

Wave 4 Phase 3 candidate 3: board/zone geometry moved to the Rust parse
engine (``temper_design_bundle_python.parse_engine``); these tests drive it
through synthetic board files and assert the same invariants the old
kiutils-mock tests did (L-shaped zone warns, rectangular zone does not, and
the zone polygon survives into ``ParseResult.board.zones``).
"""

from pathlib import Path

from temper_placer.io.kicad_parser import parse_kicad_pcb


def _board_with_zone(points: list[tuple[float, float]], name: str) -> str:
    """A one-zone board with an Edge.Cuts outline and no footprints."""
    pts = "\n".join(f"        (xy {x} {y})" for x, y in points)
    return (
        "(kicad_pcb (version 20211014) (generator test)\n"
        "  (general (thickness 1.6))\n"
        '  (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (44 "Edge.Cuts" user))\n'
        '  (net 0 "")\n'
        '  (net 1 "GND")\n'
        "  (gr_line (start 0 0) (end 200 0) (layer \"Edge.Cuts\"))\n"
        "  (gr_line (start 200 0) (end 200 200) (layer \"Edge.Cuts\"))\n"
        "  (gr_line (start 200 200) (end 0 200) (layer \"Edge.Cuts\"))\n"
        "  (gr_line (start 0 200) (end 0 0) (layer \"Edge.Cuts\"))\n"
        f'  (zone (net 1) (net_name "GND") (layer "F.Cu")\n'
        f'    (name "{name}")\n'
        "    (polygon\n"
        "      (pts\n"
        f"{pts}\n"
        "      )\n"
        "    )\n"
        "  )\n"
        ")\n"
    )


def test_zone_parsing_l_shape_warning(tmp_path: Path):
    # Define an L-shaped zone
    # Bounds: 0,0 to 100,100 (area 10000)
    # Polygon: (0,0), (100,0), (100,20), (20,20), (20,100), (0,100)
    # Area = 100*20 + 20*80 = 2000 + 1600 = 3600
    # Bbox area = 10000
    # Mismatch = (10000 - 3600) / 10000 = 0.64 > 0.05 -> Warning!
    path = tmp_path / "l_shape.kicad_pcb"
    path.write_text(
        _board_with_zone(
            [(0, 0), (100, 0), (100, 20), (20, 20), (20, 100), (0, 100)], "L_Zone"
        )
    )

    result = parse_kicad_pcb(path)
    warnings = result.warnings

    assert len(result.board.zones) == 1
    zone = result.board.zones[0]
    assert zone.name == "L_Zone"
    # Check if warning was generated
    assert any("Approximating polygon" in w for w in warnings)
    assert any("L_Zone" in w for w in warnings)

    # Check that polygon attribute is populated
    assert zone.polygon is not None
    assert len(zone.polygon) == 6


def test_zone_parsing_rectangular_no_warning(tmp_path: Path):
    path = tmp_path / "rect_zone.kicad_pcb"
    path.write_text(
        _board_with_zone([(0, 0), (100, 0), (100, 100), (0, 100)], "Rect_Zone")
    )

    result = parse_kicad_pcb(path)
    warnings = result.warnings

    assert len(result.board.zones) == 1
    # Should be no warnings about approximation
    assert not any("Approximating polygon" in w for w in warnings)
