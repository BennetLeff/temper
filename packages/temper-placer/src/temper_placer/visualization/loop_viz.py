"""
Loop visualization utilities for Plotly and HTML reports.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from temper_placer.core.loop import Loop, LoopCollection, LoopType

if TYPE_CHECKING:
    import plotly.graph_objects as go

    from .model import BoardView

logger = logging.getLogger(__name__)

# Default colors for loop types
LOOP_COLORS = {
    LoopType.COMMUTATION: "#e74c3c",  # Red
    LoopType.GATE_DRIVE_HIGH: "#3498db",  # Blue
    LoopType.GATE_DRIVE_LOW: "#2980b9",  # Dark blue
    LoopType.BOOTSTRAP: "#f39c12",  # Orange
    LoopType.SENSING: "#9b59b6",  # Purple
    LoopType.DECOUPLING: "#1abc9c",  # Teal
    LoopType.CUSTOM: "#95a5a6",  # Gray
}


def get_loop_points(loop: Loop, board_view: BoardView) -> list[tuple[float, float]]:
    """
    Get the sequence of points (x, y) forming the loop from placements.

    Args:
        loop: Loop object.
        board_view: BoardView with component and pad positions.

    Returns:
        List of (x, y) coordinates forming the loop path.
    """
    points = []
    comp_map = {c.ref: c for c in board_view.components}

    # Build pad map for efficient lookup
    pad_map = {}
    for p in board_view.pads:
        if p.component_ref:
            pad_map[(p.component_ref, p.number)] = p

    # 1. Try explicit pin path
    if loop.pins:
        for pin in loop.pins:
            key = (pin.component_ref, pin.pin_name)
            pad = pad_map.get(key)
            if pad:
                points.append((pad.position.x, pad.position.y))
            else:
                comp = comp_map.get(pin.component_ref)
                if comp:
                    # Fallback to component center
                    points.append((comp.position.x, comp.position.y))

    # 2. Fallback to components list if no pins or failed lookup
    if not points and loop.components:
        for ref in loop.components:
            comp = comp_map.get(ref)
            if comp:
                points.append((comp.position.x, comp.position.y))

    # Close the loop
    if points and (len(points) < 2 or points[0] != points[-1]):
        points.append(points[0])

    return points


def calculate_loop_area(points: list[tuple[float, float]]) -> float:
    """
    Calculate area of a closed loop using the shoelace formula.

    Args:
        points: List of (x, y) coordinates.

    Returns:
        Area in mm².
    """
    n = len(points)
    if n < 3:
        return 0.0

    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += points[i][0] * points[j][1]
        area -= points[j][0] * points[i][1]

    return abs(area) / 2.0


def add_loops_to_plotly(
    fig: go.Figure,
    loops: LoopCollection,
    board_view: BoardView
) -> None:
    """
    Add loop paths as traces to an existing Plotly figure.

    Args:
        fig: Plotly figure to modify.
        loops: Collection of loops to render.
        board_view: BoardView used for coordinate lookup.
    """
    import plotly.graph_objects as go

    for loop in loops.loops:
        points = get_loop_points(loop, board_view)
        if not points:
            continue

        x, y = zip(*points)
        color = LOOP_COLORS.get(loop.loop_type, LOOP_COLORS[LoopType.CUSTOM])

        # Current area
        area = calculate_loop_area(points)
        is_violation = area > loop.max_area_mm2

        # Status text for hover
        status = "OK" if not is_violation else "EXCEEDED"

        # Add trace
        fig.add_trace(
            go.Scatter(
                x=x,
                y=y,
                mode="lines+markers",
                line={
                    "color": color,
                    "width": 2 if is_violation else 1.5,
                    "dash": "dash"
                },
                marker={"size": 4, "color": color},
                name=f"Loop: {loop.name}",
                hoverinfo="text",
                hovertext=(
                    f"<b>{loop.name}</b><br>"
                    f"Type: {loop.loop_type.value}<br>"
                    f"Area: {area:.1f} mm² (max: {loop.max_area_mm2:.1f})<br>"
                    f"Status: {status}"
                ),
                legendgroup="loops",
                legendgrouptitle_text="Critical Loops",
                opacity=0.8
            )
        )


def render_loop_summary_table(
    loops: LoopCollection,
    board_view: BoardView,
) -> str:
    """
    Generate HTML summary table for loops.

    Args:
        loops: Loop collection.
        board_view: Board view for area calculation.

    Returns:
        HTML string.
    """
    rows = []
    for loop in loops.loops:
        points = get_loop_points(loop, board_view)
        area = calculate_loop_area(points)

        is_ok = area <= loop.max_area_mm2
        status_icon = "✓" if is_ok else "✗"
        status_class = "ok" if is_ok else "exceeded"

        margin = loop.max_area_mm2 - area
        margin_pct = (margin / loop.max_area_mm2 * 100) if loop.max_area_mm2 > 0 else 0

        rows.append(f"""
            <tr class="{status_class}">
                <td>{loop.name}</td>
                <td>{loop.loop_type.value}</td>
                <td>{loop.priority.value}</td>
                <td>{area:.1f}</td>
                <td>{loop.max_area_mm2:.1f}</td>
                <td>{margin_pct:.0f}%</td>
                <td>{status_icon}</td>
            </tr>
        """)

    return f"""
    <section class="loop-summary-section">
        <h2>Loop Analysis</h2>
        <table class="loop-summary-table">
            <thead>
                <tr>
                    <th>Loop Name</th>
                    <th>Type</th>
                    <th>Priority</th>
                    <th>Actual Area (mm²)</th>
                    <th>Max Area (mm²)</th>
                    <th>Margin</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody>
                {"".join(rows)}
            </tbody>
        </table>
    </section>
    """
