"""
KiCad trace and via writer for internal routing.

This module converts routing results from the internal MazeRouter (GridCells)
into KiCad PCB segments and vias using kiutils.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
import uuid

from kiutils.board import Board as KiBoard
from kiutils.items.brditems import Segment, Via
from kiutils.items.common import Position

if TYPE_CHECKING:
    from temper_placer.routing.maze_router import RoutePath, GridCell


def write_traces_to_pcb(
    template_pcb: Path,
    output_pcb: Path,
    routing_results: dict[str, RoutePath],
    cell_size: float,
    origin: tuple[float, float],
    clear_existing: bool = True,
) -> int:
    """
    Write maze router results to a KiCad PCB file.

    Args:
        template_pcb: Path to input PCB.
        output_pcb: Path for output PCB.
        routing_results: Results from MazeRouter.
        cell_size: Grid cell size in mm.
        origin: Board origin (ox, oy) in mm.
        clear_existing: If True, remove all existing traces/vias first.

    Returns:
        Number of items (segments + vias) added.
    """
    try:
        ki_board = KiBoard.from_file(str(template_pcb))
    except Exception as e:
        raise ValueError(f"Failed to load PCB: {e}")

    if clear_existing:
        ki_board.traceItems = []

    # Map grid layers to KiCad layers
    # For a 2-layer board: 0 -> F.Cu, 1 -> B.Cu
    layer_map = {0: "F.Cu", 1: "B.Cu"}

    items_added = 0
    ox, oy = origin

    # Map net names to kiutils Net objects
    net_lookup = {net.name: net for net in ki_board.nets}

    for net_name, result in routing_results.items():
        if not result.success or not result.cells:
            continue

        net_obj = net_lookup.get(net_name)
        cells = result.cells

        for i in range(len(cells) - 1):
            curr = cells[i]
            next_cell = cells[i + 1]

            # Convert grid to world (center of cell)
            p1_x = curr.x * cell_size + ox + cell_size / 2
            p1_y = curr.y * cell_size + oy + cell_size / 2
            p2_x = next_cell.x * cell_size + ox + cell_size / 2
            p2_y = next_cell.y * cell_size + oy + cell_size / 2

            if curr.layer == next_cell.layer:
                # Add segment
                segment = Segment()
                segment.start = Position(X=p1_x, Y=p1_y)
                segment.end = Position(X=p2_x, Y=p2_y)
                segment.width = 0.2  # Default 0.2mm width
                segment.layer = layer_map.get(curr.layer, "F.Cu")
                segment.net = net_obj.number if net_obj else 0
                segment.tstamp = str(uuid.uuid4())
                ki_board.traceItems.append(segment)
                items_added += 1
            else:
                # Layer change: add via at same x,y (if needed)
                # Note: In maze router, layer change doesn't move x,y
                via = Via()
                via.at = Position(X=p1_x, Y=p1_y)
                via.size = 0.6
                via.drill = 0.3
                via.layers = ["F.Cu", "B.Cu"]
                via.net = net_obj.number if net_obj else 0
                via.tstamp = str(uuid.uuid4())
                ki_board.traceItems.append(via)
                items_added += 1

                # Still need a segment if next_cell also moves x,y?
                # MazeRouter neighbors are 4-connected OR same-cell layer change.
                # So if layer changes, x,y stays same.
                if curr.x != next_cell.x or curr.y != next_cell.y:
                    # Should not normally happen with current MazeRouter neighbors
                    segment = Segment()
                    segment.start = Position(X=p1_x, Y=p1_y)
                    segment.end = Position(X=p2_x, Y=p2_y)
                    segment.width = 0.2
                    segment.layer = layer_map.get(next_cell.layer, "F.Cu")
                    segment.net = net_obj.number if net_obj else 0
                    segment.tstamp = str(uuid.uuid4())
                    ki_board.traceItems.append(segment)
                    items_added += 1

    # Ensure output directory exists
    output_pcb.parent.mkdir(parents=True, exist_ok=True)
    ki_board.to_file(str(output_pcb))

    return items_added
