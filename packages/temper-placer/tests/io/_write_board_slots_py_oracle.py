"""VERBATIM pin of the isolation-slot GrLine construction embedded in
``temper_placer/io/_write_board.py`` at origin/main ``5e528b8aa`` (the
Wave-4 Phase-3 formats/IO migration base).

The sibling oracle ``_write_board_py_oracle.py`` (which pinned the two
GEOMETRY kernels of ``_write_board.py`` — reorient_pad_angle,
preserve_rotation_offset) was RETIRED by FREEZE on 2026-08-20: its golden
vectors now live in ``write_board_geometry.rs``'s own ``#[cfg(test)]``
corpus. This file pins the additional per-slot GrLine construction from
``add_isolation_slots_to_pcb`` as a separate oracle, so neither pin ever
needs editing. This function is a
STATEMENT-FOR-STATEMENT extraction of the construction embedded in
``add_isolation_slots_to_pcb``'s loop (lines 487-492), with the originating
line range cited. DO NOT "improve", reformat, or keep it in sync with the
post-migration source: its whole value is that it is frozen.

``test_write_board_slots_rust_differential.py`` asserts the migrated Rust
implementation (``temper_io_types.kicad_write_geometry.gr_line_sexpr_py``)
reproduces this file's output byte-for-byte through kiutils' own round-trip
(``GrLine.from_sexpr(rust).to_sexpr()``).
"""

from __future__ import annotations

from kiutils.items.common import Position
from kiutils.items.gritems import GrLine


def gr_line_to_sexpr(
    start: tuple[float, float],
    end: tuple[float, float],
    layer: str,
    width: float,
) -> str:
    """Verbatim extraction of ``add_isolation_slots_to_pcb``'s slot-line
    construction (lines 487-492):

        slot_line = GrLine(
            start=Position(X=abs_start_x, Y=abs_start_y),
            end=Position(X=abs_end_x, Y=abs_end_y),
            layer="Edge.Cuts",
            width=slot.width_mm,
        )
    """
    slot_line = GrLine(
        start=Position(X=start[0], Y=start[1]),
        end=Position(X=end[0], Y=end[1]),
        layer=layer,
        width=width,
    )
    return slot_line.to_sexpr()
