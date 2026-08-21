"""Differential test: the ``kicad_exporter.py`` board-item additions
(``temper_io_types.kicad_write_geometry.find_net_code_py`` and the reused
``segment_sexpr_py`` / ``via_sexpr_py``) vs the pinned Python oracle.

Wave 4, Phase 3 (formats/IO) — migrates ``add_segments_to_board`` /
``add_vias_to_board`` / ``export_from_geometry``'s net-code lookup and
Segment/Via constructions. The two geometry kernels of ``kicad_exporter.py``
(snap_to_nearest_pad, _generate_connector_segments) were ported earlier;
see ``kicad_write_geometry.rs``'s module docstring for the full boundary.

The Rust kernels return parsed s-expression trees that kiutils'
`Segment.from_sexpr` / `Via.from_sexpr` consume; the oracle constructs the
kiutils dataclasses directly (verbatim pin,
``_kicad_exporter_items_py_oracle.py``, origin/main ``5e528b8aa`` — a
separate file because the sibling ``_kicad_exporter_py_oracle.py`` is itself
a frozen pin). The exporter tstamps are random `uuid.uuid4()` in the
pre-migration code and stay random (deliberately not determinized); the
oracle parameterises them.

RED before GREEN: this file is written and committed BEFORE
``find_net_code_py`` is registered into the built extension, so every test
here fails at collection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from kiutils.board import Board as KiBoard
from kiutils.items.brditems import Segment, Via
from temper_io_types import kicad_write_geometry as _GEOM

import tests.io._kicad_exporter_items_py_oracle as _oracle
from temper_placer.io import kicad_exporter as shipped
from temper_placer.io.export_types import TraceSegment, TraceVia

# Rust symbols under test — must exist or this file fails to collect (RED).
FIND_NET_CODE = _GEOM.find_net_code_py

TSTAMP = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _net(number, name):
    from types import SimpleNamespace

    return SimpleNamespace(number=number, name=name)


# ---------------------------------------------------------------------------
# find_net_code
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "nets,net_name,expected",
    [
        ([_net(0, ""), _net(1, "GND"), _net(2, "3V3")], "GND", 1),
        ([_net(0, ""), _net(1, "GND"), _net(2, "3V3")], "3V3", 2),
        ([_net(0, ""), _net(1, "GND")], "NOPE", 0),  # no match -> 0
        ([], "GND", 0),  # empty nets -> 0
        ([_net(1, "GND"), _net(2, "GND")], "GND", 1),  # first match wins
        ([_net(0, "")], "", 0),  # empty net name matches the empty net
    ],
)
def test_find_net_code_matches_oracle(nets, net_name, expected):
    assert FIND_NET_CODE(nets, net_name) == _oracle.find_net_code(nets, net_name) == expected


# ---------------------------------------------------------------------------
# segment / via construction byte-identity (via the existing 3.4 kernels)
# ---------------------------------------------------------------------------


def test_segment_construction_matches_oracle_byte_identical():
    start, end, width, layer, net = (1.5, 2.5), (3.5, 4.5), 0.254, "F.Cu", 2
    py_text = _oracle.segment_to_sexpr(start, end, width, layer, net, TSTAMP)
    rust_text = Segment.from_sexpr(
        _GEOM.segment_sexpr_py(start[0], start[1], end[0], end[1], width, layer, net, TSTAMP)
    ).to_sexpr()
    assert rust_text == py_text


def test_via_construction_matches_oracle_byte_identical():
    pos, size, drill, layers, net = (1.5, 2.5), 0.6, 0.3, ["F.Cu", "B.Cu"], 2
    py_text = _oracle.via_to_sexpr(pos, size, drill, layers, net, TSTAMP)
    rust_text = Via.from_sexpr(
        _GEOM.via_sexpr_py(pos[0], pos[1], size, drill, layers, net, TSTAMP)
    ).to_sexpr()
    assert rust_text == py_text


# ---------------------------------------------------------------------------
# Delegation proofs
# ---------------------------------------------------------------------------


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


def test_add_segments_to_board_delegates_to_rust(tmp_path):
    """The SHIPPED `add_segments_to_board` must reach the Rust
    `find_net_code_py` kernel. A monkeypatched boom propagates (there is no
    try/except around the construction)."""
    sentinel = RuntimeError("REACHED_RUST_FIND_NET_CODE")

    def boom(*_a, **_k):
        raise sentinel

    original = _GEOM.find_net_code_py
    _GEOM.find_net_code_py = boom
    try:
        with pytest.raises(RuntimeError, match="REACHED_RUST_FIND_NET_CODE"):
            _GEOM.find_net_code_py([], "GND")
        board = KiBoard.from_file(str(_template(tmp_path)))
        with pytest.raises(RuntimeError, match="REACHED_RUST_FIND_NET_CODE"):
            shipped.add_segments_to_board(
                board, [TraceSegment(net="GND", start=(0, 0), end=(1, 1), width=0.25, layer="F.Cu")]
            )
    finally:
        _GEOM.find_net_code_py = original


def test_add_vias_to_board_delegates_to_rust(tmp_path):
    """Same proof for `add_vias_to_board` via `find_net_code_py`."""
    sentinel = RuntimeError("REACHED_RUST_FIND_NET_CODE_VIA")

    def boom(*_a, **_k):
        raise sentinel

    original = _GEOM.find_net_code_py
    _GEOM.find_net_code_py = boom
    try:
        board = KiBoard.from_file(str(_template(tmp_path)))
        with pytest.raises(RuntimeError, match="REACHED_RUST_FIND_NET_CODE_VIA"):
            shipped.add_vias_to_board(
                board, [TraceVia(net="GND", position=(1, 1), size=0.8, drill=0.4, layers=["F.Cu", "In1.Cu"])]
            )
    finally:
        _GEOM.find_net_code_py = original


# ---------------------------------------------------------------------------
# End-to-end round trips (D7)
# ---------------------------------------------------------------------------


def test_add_segments_and_vias_round_trips_through_parse(tmp_path):
    """add_segments_to_board + add_vias_to_board on a real board: the net
    codes resolve from the board's nets and the items re-parse with the
    expected geometry."""
    board = KiBoard.from_file(str(_template(tmp_path)))
    n = shipped.add_segments_to_board(
        board,
        [TraceSegment(net="GND", start=(1.5, 2.5), end=(3.5, 4.5), width=0.254, layer="F.Cu")],
    )
    nv = shipped.add_vias_to_board(
        board,
        [TraceVia(net="3V3", position=(5.0, 6.0), size=0.6, drill=0.3, layers=["F.Cu", "B.Cu"])],
    )
    assert n == 1 and nv == 1

    out = tmp_path / "out.kicad_pcb"
    board.to_file(str(out))
    reloaded = KiBoard.from_file(str(out))
    segments = [t for t in reloaded.traceItems if isinstance(t, Segment)]
    vias = [t for t in reloaded.traceItems if isinstance(t, Via)]
    assert len(segments) == 1 and len(vias) == 1
    assert segments[0].net == 1  # GND
    assert (float(segments[0].start.X), float(segments[0].start.Y)) == (1.5, 2.5)
    assert vias[0].net == 2  # 3V3
    assert vias[0].layers == ["F.Cu", "B.Cu"]


@dataclass
class _RoutePathStub:
    """Duck-typed RoutePath consumed by path_to_segments/path_to_vias."""

    net: str
    cells: list[Any] = field(default_factory=list)
    cell_size: float = 0.2
    layer_name: str = "F.Cu"
    segments: list[Any] = field(default_factory=list)
    coordinates: list[Any] = field(default_factory=list)


def test_export_routed_pcb_round_trips_through_parse(tmp_path):
    """D7 re-parse parity for the full export_routed_pcb path: a routed net
    lands as segments/vias on the correct layers with the correct net codes
    and geometry."""
    from temper_placer.router_v6.grid_types import GridCell

    template = _template(tmp_path)
    out = tmp_path / "out.kicad_pcb"
    routes = {
        "GND": _RoutePathStub(
            net="GND",
            cells=[
                GridCell(0, 0, 0),
                GridCell(1, 0, 0),
                GridCell(2, 0, 0),
                GridCell(2, 0, 1),  # layer transition -> via
            ],
            cell_size=1.0,
        )
    }
    result = shipped.export_routed_pcb(
        template,
        routes,
        out,
        trace_widths={"GND": 0.5},
        origin=(0, 0),
        cell_size=1.0,
        auto_fill_zones=False,
    )
    assert result.nets_exported == 1
    assert result.nets_failed == 0
    assert result.segments_added >= 1  # collinear cells simplify to one segment
    assert result.vias_added >= 1

    reloaded = KiBoard.from_file(str(out))
    segments = [t for t in reloaded.traceItems if isinstance(t, Segment)]
    vias = [t for t in reloaded.traceItems if isinstance(t, Via)]
    assert all(s.net == 1 for s in segments)  # GND
    assert all(v.net == 1 for v in vias)
    assert all(float(s.width) == 0.5 for s in segments)  # net trace width
    layers = {s.layer for s in segments}
    assert layers == {"F.Cu"}  # layer 0 -> F.Cu (grid 0 cells)
