"""Tests for pipeline output provenance (plan 2026-07-15-001, unit U5)."""

from __future__ import annotations

from pathlib import Path

from kiutils.board import Board
from kiutils.items.common import TitleBlock

from temper_placer.io.provenance import (
    PROVENANCE_COMMENT_SLOT,
    Provenance,
    compute_provenance,
    embed_provenance,
)


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
    board = Board.create_new()
    assert board.titleBlock is None

    provenance = Provenance(
        board_sha256="a" * 64,
        netlist_sha256="b" * 64,
        config_sha256=None,
        generated_at="2026-07-15T00:00:00+00:00",
    )
    embed_provenance(board, provenance)

    assert board.titleBlock is not None
    comment = board.titleBlock.comments[PROVENANCE_COMMENT_SLOT]
    assert "a" * 64 in comment
    assert "b" * 64 in comment
    assert "config=" not in comment


def test_embed_provenance_reuses_existing_title_block():
    board = Board.create_new()
    board.titleBlock = TitleBlock(title="Temper Induction Board")

    provenance = Provenance(
        board_sha256="c" * 64,
        netlist_sha256="d" * 64,
        config_sha256="e" * 64,
        generated_at="2026-07-15T00:00:00+00:00",
    )
    embed_provenance(board, provenance)

    assert board.titleBlock.title == "Temper Induction Board"
    comment = board.titleBlock.comments[PROVENANCE_COMMENT_SLOT]
    assert "c" * 64 in comment
    assert "d" * 64 in comment
    assert "e" * 64 in comment
