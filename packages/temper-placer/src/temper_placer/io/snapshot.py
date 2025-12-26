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


def save_json_snapshot(
    state: Any,  # PipelineState
    path: Path,
) -> None:
    """Save pipeline state to a JSON file."""
    data = {
        "phase": state.current_phase.value,
        "iteration": state.iteration,
        "success": state.success,
        "elapsed_time_s": state.elapsed_time_s,
    }

    if state.placement_state:
        ps = state.placement_state
        positions = np.array(ps.positions).tolist()
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
    """Render current placement state to an SVG file."""
    if not state.board or not state.netlist:
        return

    board = state.board
    netlist = state.netlist
    
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
        for c in netlist.components:
            positions.append(c.initial_position or (0.0, 0.0))
        positions = np.array(positions)
        rotations = np.zeros(len(positions))

    scale_x = width / board.width
    scale_y = height / board.height
    scale = min(scale_x, scale_y) * 0.9
    
    offset_x = (width - board.width * scale) / 2
    offset_y = (height - board.height * scale) / 2

    def to_svg(x: float, y: float) -> tuple[float, float]:
        return (offset_x + x * scale, offset_y + y * scale)

    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">']
    
    # Board
    bx, by = to_svg(0, 0)
    bw, bh = board.width * scale, board.height * scale
    lines.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" fill="#eee" stroke="#333" stroke-width="2"/>')
    
    # Zones
    colors = ["#ffcccc", "#ccffcc", "#ccccff", "#ffffcc", "#ffccff", "#ccffff"]
    for i, zone in enumerate(board.zones):
        zx, zy = to_svg(zone.bounds[0], zone.bounds[1])
        zw = (zone.bounds[2] - zone.bounds[0]) * scale
        zh = (zone.bounds[3] - zone.bounds[1]) * scale
        color = colors[i % len(colors)]
        lines.append(f'<rect x="{zx}" y="{zy}" width="{zw}" height="{zh}" fill="{color}" fill-opacity="0.3" stroke="none"/>')
        lines.append(f'<text x="{zx + 5}" y="{zy + 15}" font-family="sans-serif" font-size="12" fill="#666">{zone.name}</text>')

    # Components
    for i, comp in enumerate(netlist.components):
        pos = positions[i]
        rot = rotations[i]
        cx, cy = to_svg(pos[0], pos[1])
        cw, ch = comp.width * scale, comp.height * scale
        transform = f"rotate({rot}, {cx}, {cy})"
        rx, ry = cx - cw / 2, cy - ch / 2
        lines.append(f'<g transform="{transform}">')
        lines.append(f'<rect x="{rx}" y="{ry}" width="{cw}" height="{ch}" fill="#6699ff" stroke="#003366" stroke-width="1"/>')
        lines.append(f'<text x="{cx}" y="{cy}" font-family="sans-serif" font-size="10" text-anchor="middle" dominant-baseline="middle" fill="white">{comp.ref}</text>')
        lines.append('</g>')

    lines.append("</svg>")
    with open(path, "w") as f:
        f.write("\n".join(lines))