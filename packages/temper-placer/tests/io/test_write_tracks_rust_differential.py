"""Differential test: the ``_write_tracks.py`` Segment/Via constructions
(``temper_io_types.kicad_write_geometry.segment_sexpr_py`` /
``via_sexpr_py``) vs the pinned Python oracle.

Wave 4, Phase 3 (formats/IO) — migrates ``write_routes_to_pcb``'s per-segment
and per-via constructions. The emission-order keys, net-index resolution and
stable-tstamp derivation were ported earlier; see
``kicad_write_geometry.rs``'s module docstring for the full boundary.

The Rust kernels return parsed s-expression trees that kiutils'
`Segment.from_sexpr` / `Via.from_sexpr` consume; the oracle constructs the
kiutils dataclasses directly (verbatim pin, ``_write_tracks_py_oracle.py``,
origin/main ``5e528b8aa``). Both arms serialise through kiutils' OWN
`to_sexpr`, so the byte comparison pins semantic content — and, because the
written board is a shipped artifact whose content hash is recorded as
measurement provenance, byte-identity here means the output file is
unchanged.

RED before GREEN: this file is written and committed BEFORE the kernels are
registered into the built extension, so every test here fails at collection.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from kiutils.items.brditems import Segment, Via
from temper_io_types import kicad_write_geometry as _GEOM

import tests.io._write_tracks_py_oracle as _oracle
from temper_placer.io import _write_tracks as shipped

# Rust symbols under test — must exist or this file fails to collect (RED).
SEGMENT = _GEOM.segment_sexpr_py
VIA = _GEOM.via_sexpr_py

TSTAMP = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _rust_segment_text(start, end, width, layer, net):
    return Segment.from_sexpr(SEGMENT(start[0], start[1], end[0], end[1], width, layer, net, TSTAMP)).to_sexpr()


def _rust_via_text(pos, size, drill, layers, net):
    return Via.from_sexpr(VIA(pos[0], pos[1], size, drill, list(layers), net, TSTAMP)).to_sexpr()


@pytest.mark.parametrize(
    "start,end,width,layer,net",
    [
        ((1.5, 2.5), (3.5, 4.5), 0.254, "F.Cu", 2),
        ((0.0, 0.0), (10.0, 10.0), 1.0, "B.Cu", 0),
        ((-5.25, -5.25), (5.25, 5.25), 0.5, "In1.Cu", 7),
        ((1.23456789, -0.0001), (123456789012.0, 0.5), 0.762, "In2.Cu", 162),
        ((1.0, 2.0), (1.0, 2.0), 0.1, "F.Cu", 1),  # zero-length
    ],
)
def test_segment_matches_oracle_byte_identical(start, end, width, layer, net):
    py_text = _oracle.segment_to_sexpr(start, end, width, layer, net, TSTAMP)
    rust_text = _rust_segment_text(start, end, width, layer, net)
    assert rust_text == py_text


@pytest.mark.parametrize(
    "pos,size,drill,layers,net",
    [
        ((1.5, 2.5), 0.6, 0.3, ["F.Cu", "B.Cu"], 2),
        ((0.0, 0.0), 1.0, 0.5, ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"], 5),
        ((-3.5, 7.25), 0.4, 0.2, ["F.Cu", "B.Cu"], 0),
        ((1.23456789, -0.0001), 0.6, 0.3, ["F.Cu", "B.Cu"], 162),
    ],
)
def test_via_matches_oracle_byte_identical(pos, size, drill, layers, net):
    py_text = _oracle.via_to_sexpr(pos, size, drill, layers, net, TSTAMP)
    rust_text = _rust_via_text(pos, size, drill, layers, net)
    assert rust_text == py_text


def _route(net, layer, start, end, width):
    from temper_placer.core.board import Trace

    return Trace(start=start, end=end, width=width, layer=layer, net=net)


def _via(net, position, width, drill, layers):
    from temper_placer.core.board import Via

    return Via(position=position, width=width, drill=drill, layers=tuple(layers), net=net)


def _template(tmp_path: Path) -> Path:
    content = (
        "(kicad_pcb (version 20240108) (generator pcbnew)\n"
        "  (general (thickness 1.6))\n"
        '  (paper "A4")\n'
        "  (layers\n"
        '    (0 "F.Cu" signal)\n'
        '    (1 "In1.Cu" signal)\n'
        '    (2 "In2.Cu" signal)\n'
        '    (31 "B.Cu" signal)\n'
        '    (44 "Edge.Cuts" user)\n'
        "  )\n"
        "  (setup (pad_to_mask_clearance 0))\n"
        '  (net 0 "")\n'
        '  (net 1 "GND")\n'
        '  (net 2 "3V3")\n'
        ")\n"
    )
    template = tmp_path / "template.kicad_pcb"
    template.write_text(content, encoding="utf-8")
    return template


def test_write_routes_delegates_to_rust_segment(tmp_path):
    """The SHIPPED `write_routes_to_pcb` must reach the Rust
    `segment_sexpr_py` kernel. The shim swallows per-segment construction
    errors into warnings (pre-migration behaviour), so a monkeypatched boom
    yields traces_added == 0 with a warning where the working kernel would
    have added one; the raise itself is proven by calling the kernel
    directly."""
    sentinel = RuntimeError("REACHED_RUST_SEGMENT")

    def boom(*_a, **_k):
        raise sentinel

    original = _GEOM.segment_sexpr_py
    _GEOM.segment_sexpr_py = boom
    try:
        with pytest.raises(RuntimeError, match="REACHED_RUST_SEGMENT"):
            _GEOM.segment_sexpr_py(0.0, 0.0, 1.0, 1.0, 0.254, "F.Cu", 1, TSTAMP)
        template = _template(tmp_path)
        out = tmp_path / "out.kicad_pcb"
        result = shipped.write_routes_to_pcb(
            template,
            out,
            frozenset({_route("GND", "F.Cu", (1.0, 1.0), (2.0, 2.0), 0.254)}),
            net_name_to_index={"GND": 1},
        )
        assert result.components_updated == 0
        assert any("Failed to add trace" in w for w in result.warnings)
    finally:
        _GEOM.segment_sexpr_py = original


def test_write_routes_delegates_to_rust_via(tmp_path):
    """Same proof for `via_sexpr_py` (vias are added after segments; a
    single route still emits, then the via construction raises into a
    warning)."""
    sentinel = RuntimeError("REACHED_RUST_VIA")

    def boom(*_a, **_k):
        raise sentinel

    original = _GEOM.via_sexpr_py
    _GEOM.via_sexpr_py = boom
    try:
        with pytest.raises(RuntimeError, match="REACHED_RUST_VIA"):
            _GEOM.via_sexpr_py(0.0, 0.0, 0.6, 0.3, ["F.Cu", "B.Cu"], 1, TSTAMP)
        template = _template(tmp_path)
        out = tmp_path / "out.kicad_pcb"
        result = shipped.write_routes_to_pcb(
            template,
            out,
            frozenset({_route("GND", "F.Cu", (1.0, 1.0), (2.0, 2.0), 0.254)}),
            vias=frozenset({_via("GND", (3.0, 3.0), 0.6, 0.3, ["F.Cu", "B.Cu"])}),
            net_name_to_index={"GND": 1},
        )
        # The segment succeeds; the via fails into a warning.
        assert result.components_updated == 1
        assert any("Failed to add via" in w for w in result.warnings)
    finally:
        _GEOM.via_sexpr_py = original


def test_write_routes_round_trips_through_parse(tmp_path):
    """D7 re-parse parity: routes + vias written through the shim re-parse
    with the same geometry, net, width/drill and layers."""
    template = _template(tmp_path)
    out = tmp_path / "out.kicad_pcb"

    result = shipped.write_routes_to_pcb(
        template,
        out,
        frozenset({_route("GND", "F.Cu", (1.5, 2.5), (3.5, 4.5), 0.254)}),
        vias=frozenset({_via("3V3", (5.0, 6.0), 0.6, 0.3, ["F.Cu", "B.Cu"])}),
        net_name_to_index={"GND": 1, "3V3": 2},
    )
    assert result.components_updated == 1  # traces
    assert result.warnings == []

    from kiutils.board import Board as KiBoard

    board = KiBoard.from_file(str(out))
    segments = [t for t in board.traceItems if isinstance(t, Segment)]
    vias = [t for t in board.traceItems if isinstance(t, Via)]
    assert len(segments) == 1
    assert len(vias) == 1

    seg = segments[0]
    assert (float(seg.start.X), float(seg.start.Y)) == (1.5, 2.5)
    assert (float(seg.end.X), float(seg.end.Y)) == (3.5, 4.5)
    assert float(seg.width) == 0.254
    assert seg.layer == "F.Cu"
    assert seg.net == 1

    via = vias[0]
    assert (float(via.position.X), float(via.position.Y)) == (5.0, 6.0)
    assert float(via.size) == 0.6
    assert float(via.drill) == 0.3
    assert via.layers == ["F.Cu", "B.Cu"]
    assert via.net == 2
