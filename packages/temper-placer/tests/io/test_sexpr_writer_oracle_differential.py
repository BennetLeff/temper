"""Pinned-oracle checks for the retired S-expression writer migration.

Wave 4, Phase 3 (formats/IO). The oracle
(``tests/io/_sexpr_writer_py_oracle.py``) pins the pre-migration writer --
kiutils' ``Board.to_sexpr()`` -- verbatim, plus a captured output constant
for the minimal corpus board (see the oracle's header for the measured
lossiness of kiutils' object-model projection).

The Rust export was differential-only and is retired. The pinned oracle is
kept and checked independently so its captured kiutils output cannot drift;
the Rust writer's pure kernels remain covered by their Rust unit tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.io._sexpr_writer_py_oracle import (
    KIUTILS_MINIMAL_BOARD_SEXPR,
)
from tests.io._sexpr_writer_py_oracle import (
    board_to_sexpr as _oracle_board_to_sexpr,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
CORPUS = [
    ("temper", REPO_ROOT / "power_pcb_dataset" / "corpus" / "temper" / "temper.kicad_pcb"),
    ("minimal", REPO_ROOT / "power_pcb_dataset" / "corpus" / "minimal" / "minimal_board.kicad_pcb"),
    (
        "rp2040",
        REPO_ROOT / "power_pcb_dataset" / "corpus" / "rp2040_designguide" / "RP2040-Guide.kicad_pcb",
    ),
    (
        "bitaxe",
        REPO_ROOT / "power_pcb_dataset" / "corpus" / "bitaxe_ultra" / "bitaxeUltra.kicad_pcb",
    ),
    (
        "piantor",
        REPO_ROOT / "power_pcb_dataset" / "corpus" / "piantor_right" / "keyboard_pcb.kicad_pcb",
    ),
    ("pcb", REPO_ROOT / "pcb" / "temper.kicad_pcb"),
]

@pytest.mark.parametrize("name,path", CORPUS, ids=[c[0] for c in CORPUS])
def test_oracle_board_to_sexpr_runs(name: str, path):
    """The oracle arm itself must still load every corpus board (fail
    loudly if kiutils' from_sexpr chokes on a board the Rust writer
    handles)."""
    _oracle_board_to_sexpr(path.read_text())


def test_oracle_function_reproduces_pinned_capture():
    """Drift detection on the oracle arm: the verbatim kiutils writer must
    keep producing the pinned capture for the minimal board.

    The comparison normalizes `(tedit <hex>)` values: the minimal board has
    no tedit tokens, and kiutils' `Footprint.tedit` DEFAULTS to
    `datetime.now()` (kiutils/footprint.py:729), so the emitted tedit hex is
    wall-clock time and differs run to run. Everything else -- the lossy
    re-emission of the whole board -- must match the pin byte-for-byte."""
    import re

    minimal = (
        REPO_ROOT / "power_pcb_dataset" / "corpus" / "minimal" / "minimal_board.kicad_pcb"
    ).read_text()
    actual = _oracle_board_to_sexpr(minimal)
    tedit = re.compile(r"\(tedit [0-9a-f]+\)")
    assert tedit.sub("(tedit <now>)", actual) == tedit.sub(
        "(tedit <now>)", KIUTILS_MINIMAL_BOARD_SEXPR
    )


def test_declared_route_move_rejects_empty_chain_declaration():
    import temper_design_bundle_python as tdb

    board = '''(kicad_pcb
      (net 41 "discharge.r_snub1-p2")
      (footprint "R" (layer "F.Cu") (at 118.64 249.56 270)
        (property "Reference" "R14"))
      (segment (start 112 218) (end 118.64 252.5225) (width 5) (layer "In3.Cu") (net 41) (tstamp 11111111-1111-1111-1111-111111111111))
      (via (at 118.64 252.5225) (size 2) (drill 1) (layers "In3.Cu" "F.Cu") (net 41) (tstamp 33333333-3333-3333-3333-333333333333)))'''
    with pytest.raises(ValueError, match="non-empty"):
        tdb.parse_engine.replace_declared_route_and_move_footprint_py(
            board,
            "R14",
            41,
            "In3.Cu",
            5.0,
            (112.0, 218.0),
            "33333333-3333-3333-3333-333333333333",
            "2",
            2.0,
            1.0,
            [],
            4.0,
        )


def test_rust_j1_block_replacement_matches_retired_python_oracle(tmp_path):
    """The predecessor mutator remains an oracle, never the active builder."""
    import temper_design_bundle_python as tdb

    predecessor = REPO_ROOT / "docs/evidence/k1-j1-domain-refloorplan-20260831"
    source = REPO_ROOT / "pcb/temper.kicad_pcb"
    expected_path = tmp_path / "python-oracle.kicad_pcb"
    namespace = {"__name__": "retired_j1_builder_oracle"}
    exec((predecessor / "build_authority.py").read_text(), namespace)
    namespace["build"](source, expected_path, 237.0, True)

    replacement = (predecessor / "approved-j1-board-footprint.kicad_sexpr").read_text().rstrip("\n").lstrip(" ")
    actual = tdb.parse_engine.replace_footprint_block_by_reference_py(
        source.read_text(), "J1", replacement
    )
    assert actual == expected_path.read_text()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (("(at 118.64 249.56 270)", "(at 119.64 249.56 270)"), "not co-located"),
        (("(layers \"In3.Cu\" \"F.Cu\")", "(layers \"In3.Cu\" \"In4.Cu\")"), "does not reach"),
    ],
)
def test_declared_route_move_rejects_disconnected_pad_or_layer_span(mutation, message):
    import temper_design_bundle_python as tdb

    board = '''(kicad_pcb
      (net 41 "discharge.r_snub1-p2")
      (footprint "R" (layer "F.Cu") (at 118.64 249.56 270)
        (property "Reference" "R14")
        (pad "2" smd circle (at 2.9625 0) (size 2 2) (layers "F.Cu" "F.Mask") (net 41 "discharge.r_snub1-p2")))
      (segment (start 112 218) (end 118.64 252.5225) (width 5) (layer "In3.Cu") (net 41) (tstamp 11111111-1111-1111-1111-111111111111))
      (via (at 118.64 252.5225) (size 2) (drill 1) (layers "In3.Cu" "F.Cu") (net 41) (tstamp 33333333-3333-3333-3333-333333333333)))'''
    with pytest.raises(ValueError, match=message):
        tdb.parse_engine.replace_declared_route_and_move_footprint_py(
            board.replace(*mutation), "R14", 41, "In3.Cu", 5.0,
            (112.0, 218.0), "33333333-3333-3333-3333-333333333333",
            "2", 2.0, 1.0, ["11111111-1111-1111-1111-111111111111"], 4.0,
        )
