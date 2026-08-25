"""Differential: pre-migration kiutils Zone construction vs Rust text path.

Pins ``zone_manager``'s de-kiutils'd zone writing against the exact
behavior it replaced:

1. Per-zone parity — ``power_plane_zone_sexpr_py`` output, materialised
   through the Rust writer's own parser/serializer
   (``write_board_sexpr_py``), must serialize identically to kiutils'
   ``Zone(...).to_sexpr()`` for the pre-migration construction (thermal
   reliefs, config clearance/min_thickness/thermal gap/bridge, priority,
   ``<net>_plane`` name, no tstamp).
2. End-to-end parity — ``add_power_planes_to_text`` on a real board's
   text must produce zones that parse back (kiutils) to the same field
   values the old ``Board.from_file → mutate → to_file`` path produced.
"""

import math

import pytest
import temper_design_bundle_python as _tdb
from kiutils.board import Board as KiBoard
from kiutils.items.common import Position
from kiutils.items.zones import FillSettings, Zone, ZonePolygon
from kiutils.utils import sexpr as _sexpr
from temper_io_types import kicad_write_geometry as _GEOM

from temper_placer.io.zone_manager import (
    PlaneConfig,
    add_power_planes_to_text,
    get_board_outline_from_text,
)

MINIMAL_BOARD = """(kicad_pcb
  (version 20221018)
  (generator pcbnew)
  (layers
    (0 "F.Cu" signal)
    (1 "In1.Cu" power)
    (2 "In2.Cu" power)
    (31 "B.Cu" signal)
  )
  (net 0 "")
  (net 1 "GND")
  (net 2 "+5V")
  (gr_line (start 0 0) (end 100 0) (layer "Edge.Cuts") (width 0.05))
  (gr_line (start 100 0) (end 100 80) (layer "Edge.Cuts") (width 0.05))
  (gr_line (start 100 80) (end 0 80) (layer "Edge.Cuts") (width 0.05))
  (gr_line (start 0 80) (end 0 0) (layer "Edge.Cuts") (width 0.05))
)
"""

EMPTY_BOARD = """(kicad_pcb
  (version 20221018)
  (generator pcbnew)
  (layers
    (0 "F.Cu" signal)
    (1 "In1.Cu" power)
    (2 "In2.Cu" power)
    (31 "B.Cu" signal)
  )
  (net 0 "")
)
"""


def _legacy_zone(config: PlaneConfig, net_code: int, outline):
    """The exact pre-migration ``zone_manager.create_zone`` body."""
    positions = [Position(x, y) for x, y in outline]
    zone_polygon = ZonePolygon(coordinates=positions)

    zone = Zone()
    zone.net = net_code
    zone.netName = config.net_name
    zone.layers = [config.layer]
    zone.name = f"{config.net_name}_plane"
    zone.priority = config.priority
    zone.connectPads = "thermal_reliefs"
    zone.clearance = config.clearance
    zone.minThickness = config.min_thickness
    zone.fillSettings = FillSettings(
        yes=True, thermalGap=config.thermal_gap, thermalBridgeWidth=config.thermal_bridge_width
    )
    zone.polygons = [zone_polygon]
    return zone


def _board_from_text(text: str) -> KiBoard:
    """Parse .kicad_pcb text into a kiutils Board (test-only kiutils use)."""
    return KiBoard.from_sexpr(_sexpr.parse_sexp(text))


def _collapse_integral_floats(text: str) -> str:
    """Normalize the Rust writer's documented integral-decimal-collapse.

    The tokenizer collapses ``0.0`` to ``0`` (num_to_atom / KiAtom
    integral-decimal-collapse, shipped with PR #1421); values are
    identical on re-parse. This normalizes kiutils' ``0.0`` rendering so
    byte comparison isolates *semantic* deltas.
    """
    import re

    return re.sub(r"(\d)\.0(?=[\s)])", r"\1", text)


def test_zone_construction_matches_legacy_kiutils_bytes():
    outline = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    config = PlaneConfig(
        layer="In1.Cu",
        net_name="GND",
        priority=1,
        clearance=0.4,
        min_thickness=0.25,
        thermal_gap=0.6,
        thermal_bridge_width=0.7,
    )

    legacy = _legacy_zone(config, net_code=3, outline=outline).to_sexpr()

    rust_items = _GEOM.power_plane_zone_sexpr_py(
        config.net_name,
        3,
        config.layer,
        config.priority,
        config.clearance,
        config.min_thickness,
        config.thermal_gap,
        config.thermal_bridge_width,
        outline,
    )
    rust_text = _tdb.parse_engine.append_items_to_board_py(EMPTY_BOARD, [rust_items])
    # Pull the zone back out of the serialized document.
    parsed = _board_from_text(rust_text)
    assert len(parsed.zones) == 1
    assert _collapse_integral_floats(parsed.zones[0].to_sexpr()) == _collapse_integral_floats(legacy)


def test_add_power_planes_end_to_end_matches_legacy_board():
    content = MINIMAL_BOARD

    # Legacy path: Board.from_file equivalent -> mutate -> to_file.
    legacy_board = _board_from_text(content)
    outline_legacy = []
    for item in legacy_board.graphicItems:
        if getattr(item, "layer", None) == "Edge.Cuts" and hasattr(item, "start"):
            outline_legacy.append((item.start.X, item.start.Y))
            outline_legacy.append((item.end.X, item.end.Y))
    unique_points = list(set(outline_legacy))
    cx = sum(p[0] for p in unique_points) / len(unique_points)
    cy = sum(p[1] for p in unique_points) / len(unique_points)
    outline_legacy = sorted(unique_points, key=lambda p: math.atan2(p[1] - cy, p[0] - cx))

    gnd_config = PlaneConfig(layer="In1.Cu", net_name="GND", priority=0)
    vcc_config = PlaneConfig(layer="In2.Cu", net_name="+5V", priority=0)
    legacy_board.zones.append(_legacy_zone(gnd_config, 1, outline_legacy))
    legacy_board.zones.append(_legacy_zone(vcc_config, 2, outline_legacy))

    # New path: raw text -> Rust tree mutation -> text.
    new_text, result = add_power_planes_to_text(content)

    assert result.zones_added == 2
    assert result.nets_covered == ["GND", "+5V"]
    assert result.layers_used == ["In1.Cu", "In2.Cu"]
    assert not result.warnings

    new_board = _board_from_text(new_text)
    assert len(new_board.zones) == len(legacy_board.zones)

    for new_zone, legacy_zone in zip(new_board.zones, legacy_board.zones):
        assert new_zone.netName == legacy_zone.netName
        assert new_zone.net == legacy_zone.net
        assert new_zone.layers == legacy_zone.layers
        assert new_zone.name == legacy_zone.name
        assert new_zone.priority == legacy_zone.priority
        assert new_zone.connectPads == legacy_zone.connectPads
        assert new_zone.clearance == legacy_zone.clearance
        assert new_zone.minThickness == legacy_zone.minThickness
        assert new_zone.fillSettings is not None
        assert new_zone.fillSettings.yes == legacy_zone.fillSettings.yes
        assert new_zone.fillSettings.thermalGap == legacy_zone.fillSettings.thermalGap
        assert (
            new_zone.fillSettings.thermalBridgeWidth
            == legacy_zone.fillSettings.thermalBridgeWidth
        )
        new_pts = [(p.X, p.Y) for p in new_zone.polygons[0].coordinates]
        legacy_pts = [(p.X, p.Y) for p in legacy_zone.polygons[0].coordinates]
        assert new_pts == legacy_pts


def test_outline_extraction_matches_kiutils():
    board = _board_from_text(MINIMAL_BOARD)
    legacy_points = []
    for item in board.graphicItems:
        if getattr(item, "layer", None) == "Edge.Cuts" and hasattr(item, "start"):
            legacy_points.append((item.start.X, item.start.Y))
            legacy_points.append((item.end.X, item.end.Y))

    rust_lines = _tdb.parse_engine.extract_board_outline_py(MINIMAL_BOARD)
    rust_points = []
    for sx, sy, ex, ey in rust_lines:
        rust_points.extend([(sx, sy), (ex, ey)])

    assert sorted(rust_points) == sorted(legacy_points)
    assert get_board_outline_from_text(MINIMAL_BOARD) is not None


def test_writer_round_trip_idempotent():
    _, result = add_power_planes_to_text(MINIMAL_BOARD)
    assert result.zones_added == 2
    once = _tdb.parse_engine.write_board_sexpr_py(MINIMAL_BOARD)
    twice = _tdb.parse_engine.write_board_sexpr_py(once)
    assert once == twice


def test_missing_nets_produce_warnings_not_zones():
    board_no_vcc = MINIMAL_BOARD.replace('  (net 2 "+5V")\n', "")
    new_text, result = add_power_planes_to_text(board_no_vcc)
    assert result.zones_added == 1
    assert result.nets_covered == ["GND"]
    assert "No VCC nets found" in result.warnings[0]
    assert len(_board_from_text(new_text).zones) == 1


@pytest.mark.parametrize(
    "clearance,min_thickness,gap,bridge,priority",
    [
        (0.3, 0.25, 0.5, 0.5, 0),
        (0.4, 0.3, 0.6, 0.7, 2),
        (0.127, 0.254, 1.0, 1.0, 1),
    ],
)
def test_zone_parameter_matrix_matches_legacy(clearance, min_thickness, gap, bridge, priority):
    outline = [(1.5, -2.5), (20.0, 0.125), (0.0, 30.75)]
    config = PlaneConfig(
        layer="In2.Cu",
        net_name="+5V",
        priority=priority,
        clearance=clearance,
        min_thickness=min_thickness,
        thermal_gap=gap,
        thermal_bridge_width=bridge,
    )
    legacy = _legacy_zone(config, net_code=7, outline=outline).to_sexpr()

    rust_items = _GEOM.power_plane_zone_sexpr_py(
        config.net_name,
        7,
        config.layer,
        config.priority,
        config.clearance,
        config.min_thickness,
        config.thermal_gap,
        config.thermal_bridge_width,
        outline,
    )
    rust_text = _tdb.parse_engine.append_items_to_board_py(EMPTY_BOARD, [rust_items])
    parsed = _board_from_text(rust_text)
    assert len(parsed.zones) == 1
    assert _collapse_integral_floats(parsed.zones[0].to_sexpr()) == _collapse_integral_floats(legacy)
