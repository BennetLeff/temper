"""Differential test: Rust S-expression writer vs the pinned kiutils oracle.

Wave 4, Phase 3 (formats/IO). The oracle
(``tests/io/_sexpr_writer_py_oracle.py``) pins the pre-migration writer --
kiutils' ``Board.to_sexpr()`` -- verbatim, plus a captured output constant
for the minimal corpus board (see the oracle's header for the measured
lossiness of kiutils' object-model projection).

What "comparing the Rust writer against the oracle" means here is
deliberate and honest: kiutils' to_sexpr re-emits from a lossy object
model (on the temper board it drops 1388 leaves -- 99 fp_text
(at/effects/font/layer/size/thickness) groups -- and adds 67, including 33
phantom (tedit ...) tokens; it only reproduces the input token tree on the
rp2040 board). The Rust writer is therefore never reconciled *to* the
oracle's bytes: the D7 acceptance criterion is the Rust writer's re-parse
parity with the INPUT text. The assertions below pin both facts:

- Where kiutils is faithful (rp2040), the two writers agree on the
  re-parsed tree -- a genuine input-by-input differential.
- Where kiutils is lossy (temper, minimal, bitaxe, piantor, pcb), the Rust
  writer still reproduces the input tree exactly, and the oracle is pinned
  to the specific lossy output so that reference cannot silently drift.
- The oracle function must keep reproducing its pinned capture (drift
  detection on the oracle arm itself).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import temper_design_bundle_python as _tdb

from tests.io._sexpr_writer_py_oracle import (
    KIUTILS_MINIMAL_BOARD_SEXPR,
    board_to_sexpr as _oracle_board_to_sexpr,
)

_PARSE_ENGINE = _tdb.parse_engine

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

# Boards on which kiutils' own to_sexpr round trip reproduces the input
# token tree (measured 2026-08-20: only rp2040). On these the differential
# can assert Rust tree == oracle tree directly.
KIUTILS_FAITHFUL = {"rp2040"}


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


def test_rust_and_oracle_agree_where_kiutils_is_faithful():
    """The shared-ground differential: on rp2040 -- the one corpus board
    whose token tree kiutils' round trip reproduces -- the Rust writer and
    the oracle must produce trees that both equal the input tree (and
    therefore each other)."""
    text = (REPO_ROOT / "power_pcb_dataset" / "corpus" / "rp2040_designguide" / "RP2040-Guide.kicad_pcb").read_text()
    original_tree = _PARSE_ENGINE.tokenize(text)
    rust_tree = _PARSE_ENGINE.tokenize(_PARSE_ENGINE.write_board_sexpr_py(text))
    oracle_tree = _PARSE_ENGINE.tokenize(_oracle_board_to_sexpr(text))
    assert rust_tree == original_tree, "Rust writer must reproduce the input tree (D7)"
    assert oracle_tree == original_tree, "oracle premise: kiutils is faithful on rp2040"
    assert rust_tree == oracle_tree


@pytest.mark.parametrize("name,path", CORPUS, ids=[c[0] for c in CORPUS])
def test_rust_writer_is_strictly_more_faithful_than_kiutils(name: str, path):
    """Everywhere kiutils is lossy, the Rust writer still reproduces the
    input tree exactly (D7), and the oracle's divergence is pinned by the
    captured-output constant rather than silently re-measured each run."""
    text = path.read_text()
    original_tree = _PARSE_ENGINE.tokenize(text)
    rust_tree = _PARSE_ENGINE.tokenize(_PARSE_ENGINE.write_board_sexpr_py(text))
    assert rust_tree == original_tree, (
        f"Rust writer must reproduce the {name} input tree exactly (D7)"
    )
    if name not in KIUTILS_FAITHFUL:
        oracle_tree = _PARSE_ENGINE.tokenize(_oracle_board_to_sexpr(text))
        assert oracle_tree != original_tree, (
            f"premise changed: kiutils now reproduces the {name} tree; "
            "move it to KIUTILS_FAITHFUL and assert Rust == oracle there"
        )
