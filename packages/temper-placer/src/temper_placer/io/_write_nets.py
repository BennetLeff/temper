"""Internal: net utilities for KiCad board writing."""

from __future__ import annotations

from pathlib import Path

from kiutils.board import Board as KiBoard


def build_net_name_to_index_map(pcb_path: Path) -> dict[str, int]:
    """Build a mapping from net name to net index from a KiCad PCB file."""
    net_name_to_index: dict[str, int] = {}
    ki_board = KiBoard.from_file(str(pcb_path))
    if hasattr(ki_board, "nets") and ki_board.nets:
        for net in ki_board.nets:
            if hasattr(net, "name") and hasattr(net, "number"):
                net_name_to_index[net.name] = net.number
    return net_name_to_index
