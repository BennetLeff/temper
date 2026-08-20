"""Differential test: the ``_write_board.py`` isolation-slot GrLine
construction (``temper_io_types.kicad_write_geometry.gr_line_sexpr_py``) vs
the pinned Python oracle.

Wave 4, Phase 3 (formats/IO) — migrates ``add_isolation_slots_to_pcb``'s
per-slot GrLine construction. The two geometry kernels of ``_write_board.py``
(reorient_pad_angles, preserve_rotation_offset) and the write-result types /
reference helper were ported earlier; the Board-tree plumbing (load, footprint
position mutation, save) remains the documented JUSTIFIED-KEEP boundary — see
``write_board_geometry.rs`` / ``kicad_write_geometry.rs`` module docstrings.

The Rust kernel returns the parsed s-expression tree kiutils' `GrLine.from_sexpr`
consumes; the oracle constructs the kiutils dataclass directly (verbatim pin,
``_write_board_slots_py_oracle.py``, origin/main ``5e528b8aa`` — a separate
file because the sibling ``_write_board_py_oracle.py`` was retired by FREEZE
on 2026-08-20). Both arms serialise through kiutils' OWN `to_sexpr`.

RED before GREEN: this file is written and committed BEFORE the kernel is
registered into the built extension, so every test here fails at collection.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from kiutils.board import Board as KiBoard
from kiutils.items.gritems import GrLine
from temper_io_types import kicad_write_geometry as _GEOM

import tests.io._write_board_slots_py_oracle as _oracle
from temper_placer.io import _write_board as shipped

# Rust symbol under test — must exist or this file fails to collect (RED).
GR_LINE = _GEOM.gr_line_sexpr_py


def _rust_gr_line_text(start, end, layer, width):
    return GrLine.from_sexpr(GR_LINE(start[0], start[1], end[0], end[1], layer, width)).to_sexpr()


@pytest.mark.parametrize(
    "start,end,layer,width",
    [
        ((1.0, 2.0), (3.0, 4.0), "Edge.Cuts", 1.5),
        ((-2.0, -2.5), (-2.0, 7.5), "Edge.Cuts", 1.5),
        ((0.0, 0.0), (10.5, 10.5), "Edge.Cuts", 0.8),
        ((1.23456789, -0.0001), (123456789012.0, 0.5), "Edge.Cuts", 2.0),
    ],
)
def test_gr_line_matches_oracle_byte_identical(start, end, layer, width):
    py_text = _oracle.gr_line_to_sexpr(start, end, layer, width)
    rust_text = _rust_gr_line_text(start, end, layer, width)
    assert rust_text == py_text


def _slot(name="q1_gate_isolation", component_ref="Q1", start_offset=(-2.0, -2.5), end_offset=(-2.0, 7.5), width_mm=1.5):
    return SimpleNamespace(
        name=name,
        component_ref=component_ref,
        start_offset=start_offset,
        end_offset=end_offset,
        width_mm=width_mm,
    )


def _board_with_footprint(tmp_path: Path) -> Path:
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
        '  (footprint "Test:PART" (layer "F.Cu")\n'
        "    (tstamp 00000000-0000-0000-0000-000000000001)\n"
        "    (at 10.0 20.0 0.0)\n"
        '    (property "Reference" "Q1" (at 0 0 0) (layer "F.SilkS"))\n'
        '    (pad "1" thru_hole circle (at 0 0) (size 1.0 1.0) (drill 0.5) (layers "F.Cu" "B.Cu"))\n'
        "  )\n"
        ")\n"
    )
    pcb = tmp_path / "board.kicad_pcb"
    pcb.write_text(content, encoding="utf-8")
    return pcb


def test_add_isolation_slots_delegates_to_rust(tmp_path):
    """The SHIPPED `add_isolation_slots_to_pcb` must reach the Rust
    `gr_line_sexpr_py` kernel. The shim swallows per-slot construction
    errors into warnings (pre-migration behaviour), so a monkeypatched boom
    yields slots_added == 0 with a warning where the working kernel would
    have added one; the raise itself is proven by calling the kernel
    directly."""
    sentinel = RuntimeError("REACHED_RUST_GR_LINE")

    def boom(*_a, **_k):
        raise sentinel

    original = _GEOM.gr_line_sexpr_py
    _GEOM.gr_line_sexpr_py = boom
    try:
        with pytest.raises(RuntimeError, match="REACHED_RUST_GR_LINE"):
            _GEOM.gr_line_sexpr_py(0.0, 0.0, 1.0, 1.0, "Edge.Cuts", 1.5)
        pcb = _board_with_footprint(tmp_path)
        out = tmp_path / "out.kicad_pcb"
        result = shipped.add_isolation_slots_to_pcb(pcb, [_slot()], output_path=out)
        assert result.slots_added == 0
        assert any("Failed to add slot" in w for w in result.warnings)
    finally:
        _GEOM.gr_line_sexpr_py = original


def test_add_isolation_slots_round_trips_through_parse(tmp_path):
    """D7 re-parse parity: the slot line lands on Edge.Cuts spanning the
    component-relative offsets rotated by the footprint angle (0 here), and
    the result counts are reported."""
    pcb = _board_with_footprint(tmp_path)
    out = tmp_path / "out.kicad_pcb"
    result = shipped.add_isolation_slots_to_pcb(pcb, [_slot()], output_path=out)
    assert result.slots_added == 1
    assert result.slots_skipped == 0
    assert result.warnings == []

    board = KiBoard.from_file(str(out))
    lines = [g for g in board.graphicItems if isinstance(g, GrLine)]
    assert len(lines) == 1
    line = lines[0]
    assert line.layer == "Edge.Cuts"
    assert float(line.width) == 1.5
    # component at (10, 20), angle 0: slot (-2,-2.5) -> (-2,7.5) + origin.
    assert (float(line.start.X), float(line.start.Y)) == (8.0, 17.5)
    assert (float(line.end.X), float(line.end.Y)) == (8.0, 27.5)


def test_add_isolation_slots_missing_component_warns(tmp_path):
    """A slot referencing a component absent from the board warns and is
    skipped — pre-migration behaviour, still exercised."""
    pcb = _board_with_footprint(tmp_path)
    out = tmp_path / "out.kicad_pcb"
    result = shipped.add_isolation_slots_to_pcb(pcb, [_slot(component_ref="R99")], output_path=out)
    assert result.slots_added == 0
    assert result.slots_skipped == 1
    assert any("R99" in w for w in result.warnings)
