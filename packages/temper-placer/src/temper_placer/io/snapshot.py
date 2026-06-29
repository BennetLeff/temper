"""
Snapshot utilities for pipeline debugging and visualization.

This module provides functions to save the pipeline state as JSON and SVG
snapshots at various stages of the placement process.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist


def save_json_snapshot(
    state: Any,  # PipelineState (typed as Any to avoid circular import)
    path: Path,
) -> None:
    """
    Save pipeline state to a JSON file.

    Args:
        state: PipelineState object.
        path: Output JSON path.
    """
    data = {
        "phase": state.current_phase.value,
        "iteration": state.iteration,
        "success": state.success,
        "elapsed_time_s": state.elapsed_time_s,
    }

    # Add placements if available
    if state.placement_state:
        # Convert JAX/NumPy arrays to lists
        ps = state.placement_state
        positions = np.array(ps.positions).tolist()

        # Get rotations
        # If rotation_logits present, get argmax
        rotations = []
        if ps.rotation_logits is not None:
            indices = np.argmax(np.array(ps.rotation_logits), axis=-1)
            rotations = [int(i) * 90 for i in indices]
        else:
            rotations = [0] * len(positions)

        data["placements"] = [
            {"x": x, "y": y, "rotation": r}
            for (x, y), r in zip(positions, rotations)
        ]
    elif state.deterministic_result:
        # NumPy result
        dr = state.deterministic_result
        positions = dr.positions.tolist()
        rotations = dr.rotations.tolist()

        data["placements"] = [
            {"x": x, "y": y, "rotation": r}
            for (x, y), r in zip(positions, rotations)
        ]

    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def save_svg_snapshot(
    state: Any,  # PipelineState
    path: Path,
    width: int = 800,
    height: int = 600,
) -> None:
    """
    Render current placement state to an SVG file.

    Args:
        state: PipelineState object.
        path: Output SVG path.
        width: SVG view width.
        height: SVG view height.
    """
    if not state.board or not state.netlist:
        return

    board: Board = state.board
    netlist: Netlist = state.netlist

    # Determine placements
    positions = []
    rotations = []

    if state.placement_state:
        positions = np.array(state.placement_state.positions)
        if state.placement_state.rotation_logits is not None:
            indices = np.argmax(np.array(state.placement_state.rotation_logits), axis=-1)
            rotations = indices * 90.0
        else:
            rotations = np.zeros(len(positions))
    elif state.deterministic_result:
        positions = state.deterministic_result.positions
        rotations = state.deterministic_result.rotations
    else:
        # Try initial positions from netlist
        positions: list = []
        for c in netlist.components:
            if c.initial_position:
                positions.append(c.initial_position)
            else:
                positions.append((0.0, 0.0))
        positions = np.array(positions)
        rotations = np.zeros(len(positions))

    if len(positions) != netlist.n_components:
        # Fallback if counts mismatch (shouldn't happen in valid state)
        return

    # Coordinate transformation: Board coordinates to SVG coordinates
    # Board: (0,0) at top-left or bottom-left depending on convention, usually Y down in SVG
    # We map board.width -> svg width, board.height -> svg height (preserving aspect ratio)

    scale_x = width / board.width
    scale_y = height / board.height
    scale = min(scale_x, scale_y) * 0.9  # 90% fill

    offset_x = (width - board.width * scale) / 2
    offset_y = (height - board.height * scale) / 2

    def to_svg(x: float, y: float) -> tuple[float, float]:
        return (
            offset_x + x * scale,
            offset_y + y * scale,  # Assuming board Y matches SVG Y (Y down)
        )

    lines = []
    lines.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">')

    # 1. Draw Board Outline
    bx, by = to_svg(0, 0)
    bw, bh = board.width * scale, board.height * scale
    lines.append(
        f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" '
        f'fill="#eee" stroke="#333" stroke-width="2"/>')

    # 2. Draw Zones
    colors = ["#ffcccc", "#ccffcc", "#ccccff", "#ffffcc", "#ffccff", "#ccffff"]
    for i, zone in enumerate(board.zones):
        zx, zy = to_svg(zone.bounds[0], zone.bounds[1])
        zw = (zone.bounds[2] - zone.bounds[0]) * scale
        zh = (zone.bounds[3] - zone.bounds[1]) * scale
        color = colors[i % len(colors)]
        lines.append(
            f'<rect x="{zx}" y="{zy}" width="{zw}" height="{zh}" '
            f'fill="{color}" fill-opacity="0.3" stroke="none"/>')
        # Zone label
        lines.append(
            f'<text x="{zx + 5}" y="{zy + 15}" font-family="sans-serif" '
            f'font-size="12" fill="#666">{zone.name}</text>')

    # 3. Draw Components
    for i, comp in enumerate(netlist.components):
        pos = positions[i]
        rot = rotations[i]

        # Component center
        cx, cy = to_svg(pos[0], pos[1])

        # Dimensions scaled
        cw = comp.width * scale
        ch = comp.height * scale

        # SVG rotation transform
        transform = f"rotate({rot}, {cx}, {cy})"

        # Rect centered at cx, cy
        rx = cx - cw / 2
        ry = cy - ch / 2

        lines.append(
            f'<g transform="{transform}">'
            f'<rect x="{rx}" y="{ry}" width="{cw}" height="{ch}" '
            f'fill="#6699ff" stroke="#003366" stroke-width="1"/>'
            f'<text x="{cx}" y="{cy}" font-family="sans-serif" '
            f'font-size="10" text-anchor="middle" dominant-baseline="middle" '
            f'fill="white">{comp.ref}</text>'
            f'</g>'
        )

    lines.append("</svg>")

    with open(path, "w") as f:
        f.write("\n".join(lines))
