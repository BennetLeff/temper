"""Provenance headers for pipeline-written PCBs (plan 2026-07-15-001, U5).

Every board the placer/router pipeline writes carries a verifiable
provenance block -- SHA-256 hashes of the inputs it was derived from, plus a
timestamp -- embedded as KiCad title-block comments (the same slot
`scripts/gen_schematics.py` uses for its own generated-artifact header,
per that plan's coordination note). Hashing reuses the Rust crate's own
`sha256_hex` (the same function `Provenance` is built from) rather than a
second, independent hashing implementation in Python.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from kiutils.board import Board

PROVENANCE_COMMENT_SLOT = 9
"""KiCad title blocks support numbered comments 1-9; provenance uses the
last slot so it doesn't collide with a human-authored title/comment."""


@dataclass(frozen=True)
class Provenance:
    board_sha256: str
    netlist_sha256: str
    config_sha256: str | None
    generated_at: str

    def as_comment(self) -> str:
        config_part = f" config={self.config_sha256}" if self.config_sha256 else ""
        return (
            f"provenance: board={self.board_sha256} "
            f"netlist={self.netlist_sha256}{config_part} "
            f"at={self.generated_at}"
        )


def compute_provenance(
    input_board_path: Path,
    netlist_path: Path,
    config_path: Path | None = None,
) -> Provenance:
    """Hashes the inputs an output board is derived from.

    Args:
        input_board_path: The board this pipeline stage read (its state
            before this stage's modification -- not the file being written).
        netlist_path: The atopile netlist export the board is checked/built
            against.
        config_path: The placement config in effect, if any.

    Raises:
        FileNotFoundError: Any required input path doesn't exist.
    """
    import temper_design_bundle_python as _tdb

    board_sha256 = _tdb.sha256_hex(input_board_path.read_bytes())
    netlist_sha256 = _tdb.sha256_hex(netlist_path.read_bytes())
    config_sha256 = _tdb.sha256_hex(config_path.read_bytes()) if config_path else None
    return Provenance(
        board_sha256=board_sha256,
        netlist_sha256=netlist_sha256,
        config_sha256=config_sha256,
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )


def embed_provenance(board: Board, provenance: Provenance) -> None:
    """Writes `provenance` into `board`'s title block, creating one if absent.

    Mutates `board` in place; call `board.to_file(...)` afterward as usual.
    """
    if board.titleBlock is None:
        from kiutils.items.common import TitleBlock

        board.titleBlock = TitleBlock()
    board.titleBlock.comments[PROVENANCE_COMMENT_SLOT] = provenance.as_comment()
