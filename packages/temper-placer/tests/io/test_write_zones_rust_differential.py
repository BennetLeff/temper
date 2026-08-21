"""Differential test: the ``_write_zones.py`` zone-construction kernel
(``temper_io_types.kicad_write_geometry.zone_sexpr_py``) vs the pinned
Python oracle.

Wave 4, Phase 3 (formats/IO) — migrates ``_write_zones.write_zones_to_pcb``'s
per-zone construction. See ``packages/temper-io-types/src/kicad_write_geometry.rs``'s
module docstring for what was and was not ported, and why.

The Rust kernel returns the parsed s-expression tree that kiutils'
``Zone.from_sexpr`` consumes; the oracle constructs the kiutils ``Zone``
dataclass directly (verbatim pin, ``_write_zones_py_oracle.py``, origin/main
``5e528b8aa``). Both are serialised through kiutils' OWN ``to_sexpr`` — float
rendering and quoting are kiutils' machinery on both arms, so the byte
comparison pins the semantic content (field set, ordering, defaults) rather
than formatting. Floats are compared byte-for-byte.

RED before GREEN: this file is written and committed BEFORE
``zone_sexpr_py`` is registered into the built extension, so
``kicad_write_geometry.zone_sexpr_py`` does not exist yet and every test here
fails at collection.

The delegation and end-to-end tests at the bottom are a SEPARATE proof from
the bit-exactness tests above: monkeypatching the Rust symbol to raise and
calling the shipped ``write_zones_to_pcb`` proves the production code path
was rewired, and the write → re-parse round trip proves the zone survives
the full load/append/save cycle (D7).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from kiutils.board import Board as KiBoard
from kiutils.items.common import Position
from kiutils.items.zones import Zone, ZonePolygon
from temper_io_types import kicad_write_geometry as _GEOM

import tests.io._write_zones_py_oracle as _oracle
from temper_placer.io import _write_zones as shipped

# Rust symbol under test — must exist or this file fails to collect (RED).
ZONE_SEXPR = _GEOM.zone_sexpr_py

TSTAMP = "f53a6155-46e3-4c13-9c0c-b17c8c6bb7ef"


def _rust_zone_text(net_name, net, layer, pts):
    """The Rust-built zone, materialised through kiutils, serialised by
    kiutils' own to_sexpr."""
    zone = Zone.from_sexpr(
        ZONE_SEXPR(net_name, net, layer, TSTAMP, [(p[0], p[1]) for p in pts])
    )
    return zone.to_sexpr()


@pytest.mark.parametrize(
    "net_name,net,layer,pts",
    [
        ("GND", 2, "B.Cu", [(1.0, 2.0), (3.5, 4.25)]),
        ("3V3", 5, "F.Cu", [(0.0, 0.0)]),
        ("", 0, "B.Cu", [(-1.5, 2.25)]),  # empty net name, net index 0
        ("GND", 1, "F&B.Cu", [(1.0, 1.0)]),  # F&B.Cu switches layer_token
        ('A"B', 3, "In1.Cu", [(1.0, 2.0)]),  # quote in net name
        ("GND", 4, "B.Cu", []),  # empty polygon
        ("N1", 7, "B.Cu", [(1.23456789, -0.0001), (123456789012.0, 0.5)]),
        ("HV", 12, "In2.Cu", [(1.0, 2.0), (3.0, 4.0), (5.0, 6.0), (7.0, 8.0)]),
    ],
)
def test_zone_sexpr_matches_oracle_byte_identical(net_name, net, layer, pts):
    py_text = _oracle.zone_to_sexpr(net_name, net, layer, TSTAMP, pts)
    rust_text = _rust_zone_text(net_name, net, layer, pts)
    assert rust_text == py_text


def test_zone_sexpr_round_trip_fields_match_oracle():
    """Field-level parity of the materialised zone (not just its serialised
    text): the from_sexpr materialisation must carry the same net, net name,
    layers, tstamp, coordinates and defaults as the oracle construction."""
    pts = [(1.0, 2.0), (3.5, 4.25)]
    oracle_zone = Zone(
        netName="GND",
        net=2,
        layers=["B.Cu"],
        tstamp=TSTAMP,
        polygons=[ZonePolygon(coordinates=[Position(p[0], p[1]) for p in pts])],
        minThickness=0.254,
    )
    rust_zone = Zone.from_sexpr(ZONE_SEXPR("GND", 2, "B.Cu", TSTAMP, pts))
    assert rust_zone.net == oracle_zone.net
    assert rust_zone.netName == oracle_zone.netName
    assert rust_zone.layers == oracle_zone.layers
    assert rust_zone.tstamp == oracle_zone.tstamp
    assert rust_zone.minThickness == oracle_zone.minThickness
    assert rust_zone.hatch.style == oracle_zone.hatch.style
    assert rust_zone.hatch.pitch == oracle_zone.hatch.pitch
    assert rust_zone.clearance == oracle_zone.clearance
    assert [(p.X, p.Y) for p in rust_zone.polygons[0].coordinates] == [
        (p.X, p.Y) for p in oracle_zone.polygons[0].coordinates
    ]


# ---------------------------------------------------------------------------
# Shipped-module delegation proof + end-to-end round trip (D7)
# ---------------------------------------------------------------------------


def _minimal_board(tmp_path: Path) -> Path:
    """A minimal parseable .kicad_pcb template (2 copper layers — the
    4-layer validator warns rather than raises for those)."""
    content = (
        "(kicad_pcb (version 20240108) (generator pcbnew)\n"
        "  (general (thickness 1.6))\n"
        '  (paper "A4")\n'
        "  (layers\n"
        '    (0 "F.Cu" signal)\n'
        '    (31 "B.Cu" signal)\n'
        '    (44 "Edge.Cuts" user)\n'
        "  )\n"
        "  (setup (pad_to_mask_clearance 0))\n"
        ")\n"
    )
    template = tmp_path / "template.kicad_pcb"
    template.write_text(content, encoding="utf-8")
    return template


def test_write_zones_to_pcb_delegates_to_rust():
    """The SHIPPED `write_zones_to_pcb` must reach the Rust `zone_sexpr_py`
    kernel, not just have a differential proving the kernel is correct in
    isolation. Monkeypatch the Rust symbol to raise; call the shipped entry
    point; the raise must propagate (it surfaces as a per-zone warning —
    the kernel call is inside the try/except — so assert the warning, and
    also assert the exception type by calling the kernel directly)."""
    sentinel = RuntimeError("REACHED_RUST_ZONE_SEXPR")

    def boom(*_a, **_k):
        raise sentinel

    original = _GEOM.zone_sexpr_py
    _GEOM.zone_sexpr_py = boom
    try:
        with pytest.raises(RuntimeError, match="REACHED_RUST_ZONE_SEXPR"):
            _GEOM.zone_sexpr_py("GND", 1, "B.Cu", TSTAMP, [(1.0, 2.0)])
        # The shipped writer swallows per-zone construction errors into
        # warnings (pre-migration behaviour) — prove the kernel is on the
        # path by observing the warning text.
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            template = _minimal_board(Path(td))
            out = Path(td) / "out.kicad_pcb"
            result = shipped.write_zones_to_pcb(
                template,
                out,
                [{"net_name": "GND", "layer": "B.Cu", "polygon_pts": [(1.0, 2.0)]}],
                net_name_to_index={"GND": 1},
            )
            assert result.components_updated == 0
            assert any("Failed to add zone for GND" in w for w in result.warnings)
    finally:
        _GEOM.zone_sexpr_py = original


def test_write_zones_to_pcb_round_trips_through_parse(tmp_path):
    """D7 re-parse parity for the zone write path: write zones to a template,
    re-load the output with kiutils, and assert the zone's semantic content
    (net, net name, layers, coordinates) survived the full cycle."""
    template = _minimal_board(tmp_path)
    out = tmp_path / "out.kicad_pcb"

    result = shipped.write_zones_to_pcb(
        template,
        out,
        [
            {"net_name": "GND", "layer": "B.Cu", "polygon_pts": [(1.0, 2.0), (3.5, 4.25)]},
            {"net_name": "3V3", "layer": "F.Cu", "polygon_pts": [(0.0, 0.0)]},
        ],
        net_name_to_index={"GND": 2, "3V3": 5},
    )
    assert result.components_updated == 2
    assert result.warnings == []

    ki_board = KiBoard.from_file(str(out))
    assert len(ki_board.zones) == 2

    gnd, v33 = ki_board.zones
    assert gnd.netName == "GND"
    assert gnd.net == 2
    assert gnd.layers == ["B.Cu"]
    assert gnd.tstamp is not None
    assert [(float(p.X), float(p.Y)) for p in gnd.polygons[0].coordinates] == [
        (1.0, 2.0),
        (3.5, 4.25),
    ]
    assert v33.netName == "3V3"
    assert v33.net == 5
    assert v33.layers == ["F.Cu"]


def test_write_zones_to_pcb_builds_net_map_when_not_provided(tmp_path):
    """`net_name_to_index=None` falls back to building the map from the
    template's nets — the pre-migration code path, still exercised."""
    content = (
        "(kicad_pcb (version 20240108) (generator pcbnew)\n"
        "  (general (thickness 1.6))\n"
        '  (paper "A4")\n'
        "  (layers\n"
        '    (0 "F.Cu" signal)\n'
        '    (31 "B.Cu" signal)\n'
        '    (44 "Edge.Cuts" user)\n'
        "  )\n"
        "  (setup (pad_to_mask_clearance 0))\n"
        '  (net 0 "")\n'
        '  (net 1 "GND")\n'
        ")\n"
    )
    template = tmp_path / "template.kicad_pcb"
    template.write_text(content, encoding="utf-8")
    out = tmp_path / "out.kicad_pcb"

    result = shipped.write_zones_to_pcb(
        template,
        out,
        [{"net_name": "GND", "layer": "B.Cu", "polygon_pts": [(1.0, 2.0)]}],
    )
    assert result.components_updated == 1
    ki_board = KiBoard.from_file(str(out))
    assert ki_board.zones[0].net == 1  # resolved from the template's net list
