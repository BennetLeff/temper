"""Tests for pipeline output provenance (plan 2026-07-15-001, unit U5)."""

from __future__ import annotations

from pathlib import Path

from temper_placer.io.provenance import (
    PROVENANCE_COMMENT_SLOT,
    Provenance,
    compute_provenance,
    embed_provenance,
)

MINIMAL_BOARD = """(kicad_pcb (version 20211014) (generator kiutils)
  (general
    (thickness 1.6)
  )
  (paper "A4")
)
"""


def _write(path: Path, content: str) -> Path:
    path.write_text(content)
    return path


def test_compute_provenance_hashes_are_non_empty(tmp_path: Path):
    board = _write(tmp_path / "board.kicad_pcb", "board-v1")
    netlist = _write(tmp_path / "default.net", "netlist-v1")
    config = _write(tmp_path / "config.yaml", "config-v1")

    provenance = compute_provenance(board, netlist, config)

    assert len(provenance.board_sha256) == 64
    assert len(provenance.netlist_sha256) == 64
    assert provenance.config_sha256 is not None
    assert len(provenance.config_sha256) == 64
    assert provenance.generated_at


def test_config_is_optional(tmp_path: Path):
    board = _write(tmp_path / "board.kicad_pcb", "board-v1")
    netlist = _write(tmp_path / "default.net", "netlist-v1")

    provenance = compute_provenance(board, netlist)

    assert provenance.config_sha256 is None
    assert "config=" not in provenance.as_comment()


def test_identical_inputs_yield_identical_hashes(tmp_path: Path):
    board = _write(tmp_path / "board.kicad_pcb", "board-v1")
    netlist = _write(tmp_path / "default.net", "netlist-v1")

    first = compute_provenance(board, netlist)
    second = compute_provenance(board, netlist)

    assert first.board_sha256 == second.board_sha256
    assert first.netlist_sha256 == second.netlist_sha256


def test_changing_an_input_changes_only_its_hash(tmp_path: Path):
    board = _write(tmp_path / "board.kicad_pcb", "board-v1")
    netlist = _write(tmp_path / "default.net", "netlist-v1")
    before = compute_provenance(board, netlist)

    _write(netlist, "netlist-v2")
    after = compute_provenance(board, netlist)

    assert after.board_sha256 == before.board_sha256
    assert after.netlist_sha256 != before.netlist_sha256


def test_embed_provenance_creates_title_block_when_absent():
    provenance = Provenance(
        board_sha256="a" * 64,
        netlist_sha256="b" * 64,
        config_sha256=None,
        generated_at="2026-07-15T00:00:00+00:00",
    )
    out = embed_provenance(MINIMAL_BOARD, provenance)

    assert "a" * 64 in out
    assert "b" * 64 in out
    assert "config=" not in out
    # The comment lands in title-block slot 9 with the provenance text.
    assert f'(comment {PROVENANCE_COMMENT_SLOT} "provenance: board=' in out
    # Re-parse parity: the output is still a single (kicad_pcb ...) document
    # whose title_block carries exactly the one comment.
    import temper_design_bundle_python as _tdb

    # tokenize returns the ROOT node -- the (kicad_pcb ...) list itself.
    root = _tdb.parse_engine.tokenize(out)
    assert root[0] == "kicad_pcb"
    title_block = next(child for child in root if child and child[0] == "title_block")
    comments = [c for c in title_block if c and c[0] == "comment"]
    assert len(comments) == 1
    assert comments[0][1] == PROVENANCE_COMMENT_SLOT
    assert comments[0][2].startswith("provenance: board=")


def test_embed_provenance_reuses_existing_title_block():
    board = MINIMAL_BOARD.replace(
        '  (paper "A4")\n',
        '  (paper "A4")\n  (title_block\n    (title "Temper Induction Board")\n  )\n',
    )
    provenance = Provenance(
        board_sha256="c" * 64,
        netlist_sha256="d" * 64,
        config_sha256="e" * 64,
        generated_at="2026-07-15T00:00:00+00:00",
    )
    out = embed_provenance(board, provenance)

    assert "Temper Induction Board" in out
    assert "c" * 64 in out
    assert "d" * 64 in out
    assert "e" * 64 in out
    assert f'(comment {PROVENANCE_COMMENT_SLOT} "provenance: board=' in out
