"""Differential test: the ``_write_modules.py`` annotation constructions
(``temper_io_types.kicad_write_geometry.gr_rect_sexpr_py`` /
``gr_text_sexpr_py``) vs the pinned Python oracle.

Wave 4, Phase 3 (formats/IO) — migrates ``add_bounding_boxes_to_pcb``'s
GrRect construction and ``add_silkscreen_labels``'s GrText construction.
The value read is now supplied by the live parse-engine footprint extraction
boundary. The pad-bounding-box reduction (`component_bounds_py`) and the
reference read (`get_footprint_reference_py`) were ported earlier; the
per-pad rotation stays Python (the `rotate_local_to_world` SSOT — B1). See
``kicad_write_geometry.rs`` / ``write_types.rs`` module docstrings for what
was and was not ported, and why.

The Rust kernels return parsed s-expression trees that kiutils'
`GrRect.from_sexpr` / `GrText.from_sexpr` consume; the oracle constructs the
kiutils dataclasses directly (verbatim pin, ``_write_modules_py_oracle.py``,
origin/main ``5e528b8aa``). Both arms serialise through kiutils' OWN
`to_sexpr`, so the byte comparison pins semantic content, not formatting.

RED before GREEN: this file is written and committed BEFORE the kernels are
registered into the built extension, so every test here fails at collection.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from kiutils.board import Board as KiBoard
from kiutils.items.gritems import GrRect, GrText
import temper_design_bundle_python as _tdb
from temper_io_types import kicad_write_geometry as _GEOM

import tests.io._write_modules_py_oracle as _oracle
from temper_placer.io import _write_modules as shipped

# Rust symbols under test — must exist or this file fails to collect (RED).
GR_RECT = _GEOM.gr_rect_sexpr_py
GR_TEXT = _GEOM.gr_text_sexpr_py


def _rust_gr_rect_text(x_min, y_min, x_max, y_max, layer, width):
    return GrRect.from_sexpr(GR_RECT(x_min, y_min, x_max, y_max, layer, width)).to_sexpr()


def _rust_gr_text_text(text, x, y, layer):
    return GrText.from_sexpr(GR_TEXT(text, x, y, layer)).to_sexpr()


@pytest.mark.parametrize(
    "x_min,y_min,x_max,y_max,layer,width",
    [
        (1.0, 2.0, 3.0, 4.0, "Dwgs.User", 0.2),
        (0.0, 0.0, 10.5, 10.5, "Dwgs.User", 0.3),
        (-5.25, -5.25, 5.25, 5.25, "F.Fab", 0.15),
        (1.23456789, -0.0001, 123456789012.0, 0.5, "B.SilkS", 1.0),
        (0.5, 0.5, 1.5, 1.5, "Dwgs.User", 0.0),
    ],
)
def test_gr_rect_matches_oracle_byte_identical(x_min, y_min, x_max, y_max, layer, width):
    py_text = _oracle.gr_rect_to_sexpr(x_min, y_min, x_max, y_max, layer, width)
    rust_text = _rust_gr_rect_text(x_min, y_min, x_max, y_max, layer, width)
    assert rust_text == py_text


@pytest.mark.parametrize(
    "text,x,y,layer",
    [
        ("R1", 5.0, 6.0, "F.SilkS"),
        ("U1", 0.0, 0.0, "F.SilkS"),
        ("C1", -3.5, 7.25, "B.SilkS"),
        ("A long value 100k 5%", 1.23456789, -0.0001, "F.SilkS"),
        ("Q\"1", 2.0, 3.0, "F.SilkS"),  # quote in text
    ],
)
def test_gr_text_matches_oracle_byte_identical(text, x, y, layer):
    py_text = _oracle.gr_text_to_sexpr(text, x, y, layer)
    rust_text = _rust_gr_text_text(text, x, y, layer)
    assert rust_text == py_text


# ---------------------------------------------------------------------------
# Shipped-module delegation proof + end-to-end round trips (D7)
# ---------------------------------------------------------------------------


def _board_with_footprint(tmp_path: Path, ref: str = "U1", value: str = "100k") -> Path:
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
        f'  (footprint "Test:PART" (layer "F.Cu")\n'
        f"    (tstamp 00000000-0000-0000-0000-000000000001)\n"
        f"    (at 10.0 20.0)\n"
        f'    (property "Reference" "{ref}" (at 0 0 0) (layer "F.SilkS"))\n'
        f'    (property "Value" "{value}" (at 0 0 0) (layer "F.Fab"))\n'
        f'    (pad "1" smd rect (at 0 0) (size 1.0 1.5) (layers "F.Cu" "F.Paste" "F.Mask"))\n'
        f'    (pad "2" smd rect (at 2.0 0) (size 1.0 1.5) (layers "F.Cu" "F.Paste" "F.Mask"))\n'
        "  )\n"
        ")\n"
    )
    pcb = tmp_path / "board.kicad_pcb"
    pcb.write_text(content, encoding="utf-8")
    return pcb


def test_add_bounding_boxes_delegates_to_rust(tmp_path):
    """The SHIPPED `add_bounding_boxes_to_pcb` must reach the Rust
    `gr_rect_sexpr_py` kernel. The shim swallows per-item construction
    errors (`except Exception: pass` — pre-migration behaviour), so a
    monkeypatched boom yields boxes_added == 0 where the working kernel
    would have added one — the raise is proven by calling the kernel
    directly, the wiring by the count."""
    sentinel = RuntimeError("REACHED_RUST_GR_RECT")

    def boom(*_a, **_k):
        raise sentinel

    original = _GEOM.gr_rect_sexpr_py
    _GEOM.gr_rect_sexpr_py = boom
    try:
        with pytest.raises(RuntimeError, match="REACHED_RUST_GR_RECT"):
            _GEOM.gr_rect_sexpr_py(0.0, 0.0, 1.0, 1.0, "Dwgs.User", 0.2)
        pcb = _board_with_footprint(tmp_path)
        n = shipped.add_bounding_boxes_to_pcb(pcb)
        assert n == 0  # the Rust kernel raised inside the swallowed try/except
    finally:
        _GEOM.gr_rect_sexpr_py = original


def test_add_silkscreen_labels_delegates_to_rust(tmp_path):
    """The SHIPPED `add_silkscreen_labels` reaches the Rust
    `extract_footprint_info_py` kernel for value reads — the footprint
    data (position, value, pads) is read via Rust, not kiutils."""
    sentinel = RuntimeError("REACHED_RUST_FOOTPRINT_INFO")

    def boom(*_a, **_k):
        raise sentinel

    original = _tdb.parse_engine.extract_footprint_info_py
    _tdb.parse_engine.extract_footprint_info_py = boom
    try:
        pcb = _board_with_footprint(tmp_path, ref="U1", value="100k")
        with pytest.raises(RuntimeError, match="REACHED_RUST_FOOTPRINT_INFO"):
            shipped.add_silkscreen_labels(pcb)
    finally:
        _tdb.parse_engine.extract_footprint_info_py = original


def test_add_bounding_boxes_round_trips_through_parse(tmp_path):
    """D7 re-parse parity: the written board re-parses to a gr_rect on the
    requested layer spanning the component's pad-inclusive bounds + margin."""
    pcb = _board_with_footprint(tmp_path)
    n = shipped.add_bounding_boxes_to_pcb(pcb)
    assert n == 1

    board = KiBoard.from_file(str(pcb))
    rects = [g for g in board.graphicItems if isinstance(g, GrRect)]
    assert len(rects) == 1
    r = rects[0]
    assert r.layer == "Dwgs.User"
    assert r.width == 0.2
    # pads at (0,0) & (2,0), size 1.0x1.5 -> bounds (-0.5,-0.75)-(2.5,0.75),
    # footprint at (10,20) -> world (9.5,19.25)-(12.5,20.75), +0.3 margin.
    assert float(r.start.X) == pytest.approx(9.2)
    assert float(r.start.Y) == pytest.approx(18.95)
    assert float(r.end.X) == pytest.approx(12.8)
    assert float(r.end.Y) == pytest.approx(21.05)


def test_add_silkscreen_labels_round_trips_through_parse(tmp_path):
    """D7 re-parse parity: references/values/outlines land as gr_text on
    F.SilkS and gr_rect on F.Fab with the expected content."""
    pcb = _board_with_footprint(tmp_path, ref="U1", value="100k")
    counts = shipped.add_silkscreen_labels(pcb)
    assert counts["references"] == 1
    assert counts["values"] == 1
    assert counts["outlines"] == 1

    board = KiBoard.from_file(str(pcb))
    texts = [g for g in board.graphicItems if isinstance(g, GrText)]
    rects = [g for g in board.graphicItems if isinstance(g, GrRect)]
    silk_texts = [t for t in texts if t.layer == "F.SilkS"]
    assert [t.text for t in silk_texts] == ["U1", "100k"]
    fab_rects = [r for r in rects if r.layer == "F.Fab"]
    assert len(fab_rects) == 1


def test_add_silkscreen_labels_skips_empty_value(tmp_path):
    """`add_values and value` — an empty-string Value produces no value
    text (the reference and outline still land)."""
    pcb = _board_with_footprint(tmp_path, ref="U1", value="")
    counts = shipped.add_silkscreen_labels(pcb)
    assert counts["references"] == 1
    assert counts["values"] == 0
    assert counts["outlines"] == 1
