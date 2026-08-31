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
