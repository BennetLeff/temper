"""Provenance headers for pipeline-written PCBs (plan 2026-07-15-001, U5).

Every board the placer/router pipeline writes carries a verifiable
provenance block -- SHA-256 hashes of the inputs it was derived from, plus a
timestamp -- embedded as KiCad title-block comments (the same slot
`scripts/gen_schematics.py` uses for its own generated-artifact header,
per that plan's coordination note). Hashing reuses the Rust crate's own
`sha256_hex` (the same function `Provenance` is built from) rather than a
second, independent hashing implementation in Python.

The embedding itself (Wave 4 Phase 3, formats/IO) is a Rust kernel:
`embed_provenance` takes raw `.kicad_pcb` text, parses it with the
kiutils-exact tokenizer, mutates the `(title_block ...)` node in the
`KiNode` tree, and serializes back with the Rust S-expression writer --
kiutils is no longer imported anywhere in this module (the R4 gate).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

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


def embed_provenance(board_text: str, provenance: Provenance) -> str:
    """Embeds `provenance` into raw `.kicad_pcb` text as title-block comment 9.

    Rust kernel (Wave 4 Phase 3, formats/IO): the text is parsed with the
    kiutils-exact tokenizer, the `(title_block ...)` node is mutated
    (created when absent -- the comment slot overwrites an existing entry,
    other comments and fields are preserved), and the tree is serialized
    back to text with the Rust S-expression writer (see
    ``sexpr_writer.rs``). Re-parse parity is the contract: the output
    re-parses to the input tree plus the comment.

    kiutils leaves this path entirely (parent R4): no `Board` object is
    built or mutated, and no kiutils import remains in this module.

    Args:
        board_text: Raw ``.kicad_pcb`` text -- e.g. kiutils'
            ``Board.to_sexpr()`` output or the bytes of an existing board
            file.
        provenance: The provenance record to embed.

    Returns:
        The rewritten board text with the provenance comment embedded.

    Raises:
        ValueError: The text is not a parseable ``(kicad_pcb ...)`` document
            (fail closed -- never return half-mutated text).
    """
    import temper_design_bundle_python as _tdb

    return _tdb.parse_engine.embed_title_block_comment_py(
        board_text, PROVENANCE_COMMENT_SLOT, provenance.as_comment()
    )
