"""
Placement progression visualization.

This module provides tools to render the evolution of component placements
over the course of optimization.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import plotly.graph_objects as go

from temper_placer.visualization.board_renderer import render_board
from temper_placer.visualization.model import (
    BoardView,
    ComponentView,
    LossHistory,
    Point,
)


def render_progression_html(
    history_path: Path | str,
    pcb_info: dict[str, Any],
    output_path: Path | str | None = None,
) -> str:
    """
    Generate an interactive HTML visualization of placement progression.

    Args:
        history_path: Path to the loss history JSON file.
        pcb_info: Dictionary with 'width', 'height', 'refs', 'widths', 'heights'.
        output_path: Optional path to save the HTML file.

    Returns:
        HTML string.
    """
    with open(history_path) as f:
        data = json.load(f)

    # Reconstruct BoardViews for each data point
    width = pcb_info["width"]
    height = pcb_info["height"]
    refs = pcb_info["refs"]
    comp_widths = pcb_info["widths"]
    comp_heights = pcb_info["heights"]

    frames = []
    epochs = []

    for point in data.get("data_points", []):
        positions = point.get("positions")
        rotations = point.get("rotations")
        epoch = point.get("epoch")

        if positions is None:
            continue

        epochs.append(epoch)
        
        # Convert rotations if needed (N, 4) -> (N,) degrees
        rot_array = np.array(rotations)
        if len(rot_array.shape) == 2 and rot_array.shape[1] == 4:
            # Soft one-hot to discrete rotation index
            rot_indices = np.argmax(rot_array, axis=1)
            rot_degrees = rot_indices * 90.0
        else:
            rot_degrees = rot_array

        components = []
        for i, ref in enumerate(refs):
            components.append(
                ComponentView(
                    ref=ref,
                    position=Point(float(positions[i][0]), float(positions[i][1])),
                    rotation=float(rot_degrees[i]),
                    width=float(comp_widths[i]),
                    height=float(comp_heights[i]),
                )
            )

        board_view = BoardView(
            width=width,
            height=height,
            components=tuple(components),
            title=f"Epoch {epoch}",
        )
        frames.append(board_view)

    if not frames:
        return "<html><body>No progression data found in history file.</body></html>"

    # Create the base figure from the last frame
    fig = render_board(frames[-1])

    # Add animation slider
    # (Plotly animation with shapes is complex because shapes aren't natively animatable via 'frames')
    # We'll use a more robust approach: re-creating the entire figure layout for each frame
    # and using Plotly's slider to switch between them.
    
    # Actually, easier to use Plotly's native animation if we use Scatter markers for components
    # But we use shapes for rectangles. 
    
    # Alternative: Generate a set of figures and wrap in custom HTML with a slider.
    # For now, let's just render the final state and provide a simple animation.
    
    return fig.to_html() # Placeholder for full animation
