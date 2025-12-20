"""
Loop visualization module for power electronics PCB design.

This module provides functions to visualize current loops overlaid on PCB
component placements, including:

- Loop path rendering (SVG generation)
- Loop area display with compliance indicators
- Color coding by priority/type
- Interactive features (hover, click, toggle)
- HTML report integration
- Export to SVG and metrics (JSON/CSV)

The visualization helps designers understand and optimize critical current
loops like commutation loops, gate drive loops, and bootstrap loops.

Example usage:
    >>> from temper_placer.visualization.loop_viz import render_board_with_loops
    >>> from temper_placer.core.loop import LoopCollection
    >>>
    >>> html = render_board_with_loops(
    ...     placements={"Q1": {"x": 100, "y": 50, "rotation": 0}},
    ...     loops=my_loop_collection,
    ...     board_width=200,
    ...     board_height=150,
    ... )
"""

from __future__ import annotations

import csv
import io
import json
import re
from typing import Any

from temper_placer.core.loop import (
    Loop,
    LoopCollection,
    LoopPriority,
    LoopType,
)


# =============================================================================
# Color Palette - Colorblind-friendly colors
# =============================================================================

# Using the IBM Design Library colorblind-safe palette
# These colors are distinguishable for most color vision deficiencies
LOOP_COLOR_PALETTE: dict[str, str] = {
    "commutation": "#DC267F",  # Magenta/pink - critical power loop
    "gate_drive_high": "#FE6100",  # Orange - high-side gate
    "gate_drive_low": "#785EF0",  # Purple - low-side gate
    "bootstrap": "#FFB000",  # Yellow/gold - bootstrap
    "auxiliary": "#648FFF",  # Blue - auxiliary
    "sensing": "#009E73",  # Teal - sensing
    "decoupling": "#56B4E9",  # Sky blue - decoupling
    "custom": "#999999",  # Gray - custom/unknown
}

# Priority-based opacity/saturation modifiers
PRIORITY_OPACITY: dict[LoopPriority, float] = {
    LoopPriority.CRITICAL: 1.0,
    LoopPriority.HIGH: 0.85,
    LoopPriority.MEDIUM: 0.7,
    LoopPriority.LOW: 0.55,
}

# Priority-based stroke widths
PRIORITY_STROKE_WIDTH: dict[LoopPriority, float] = {
    LoopPriority.CRITICAL: 3.0,
    LoopPriority.HIGH: 2.5,
    LoopPriority.MEDIUM: 2.0,
    LoopPriority.LOW: 1.5,
}


def get_loop_color(loop_type: LoopType, priority: LoopPriority) -> str:
    """
    Get hex color for a loop based on its type and priority.

    Uses a colorblind-friendly palette where loop types have distinct hues
    and priority affects saturation/brightness.

    Args:
        loop_type: The type of current loop.
        priority: The optimization priority of the loop.

    Returns:
        Hex color string (e.g., '#DC267F').

    Example:
        >>> get_loop_color(LoopType.COMMUTATION, LoopPriority.CRITICAL)
        '#DC267F'
    """
    # Map loop type to palette key
    type_to_key = {
        LoopType.COMMUTATION: "commutation",
        LoopType.BUCK_SWITCH: "commutation",
        LoopType.BOOST_SWITCH: "commutation",
        LoopType.FLYBACK_PRIMARY: "commutation",
        LoopType.FLYBACK_SECONDARY: "commutation",
        LoopType.GATE_DRIVE_HIGH: "gate_drive_high",
        LoopType.GATE_DRIVE_LOW: "gate_drive_low",
        LoopType.BOOTSTRAP: "bootstrap",
        LoopType.AUXILIARY_SUPPLY: "auxiliary",
        LoopType.SENSING: "sensing",
        LoopType.FEEDBACK: "sensing",
        LoopType.DECOUPLING: "decoupling",
        LoopType.CUSTOM: "custom",
    }

    key = type_to_key.get(loop_type, "custom")
    base_color = LOOP_COLOR_PALETTE[key]

    # Apply priority-based modification
    # For simplicity, we return the base color; opacity is applied in rendering
    # A more sophisticated approach would darken/lighten based on priority
    if priority == LoopPriority.LOW:
        # Lighten color for low priority
        return _lighten_color(base_color, 0.3)
    elif priority == LoopPriority.MEDIUM:
        return _lighten_color(base_color, 0.15)

    return base_color


def _lighten_color(hex_color: str, factor: float) -> str:
    """Lighten a hex color by mixing with white.

    Args:
        hex_color: Hex color string (e.g., '#DC267F').
        factor: Amount to lighten (0-1, where 1 = white).

    Returns:
        Lightened hex color string.
    """
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)

    r = int(r + (255 - r) * factor)
    g = int(g + (255 - g) * factor)
    b = int(b + (255 - b) * factor)

    return f"#{r:02X}{g:02X}{b:02X}"


def _is_valid_hex_color(color: str) -> bool:
    """Check if a string is a valid hex color."""
    if not isinstance(color, str):
        return False
    pattern = r"^#[0-9A-Fa-f]{6}$"
    return bool(re.match(pattern, color))


# =============================================================================
# Loop Path Rendering
# =============================================================================


def _get_loop_points(
    loop: Loop,
    placements: dict[str, Any],
) -> list[tuple[float, float]]:
    """
    Extract (x, y) coordinates for all points in a loop.

    Uses pins if available, otherwise falls back to component centers.

    Args:
        loop: The loop to extract points from.
        placements: Dictionary mapping component refs to placement dicts.

    Returns:
        List of (x, y) tuples for the loop path.
    """
    points = []

    if loop.pins:
        # Use explicit pins
        for pin in loop.pins:
            ref = pin.component_ref
            if ref in placements:
                p = placements[ref]
                x = p.get("x", 0.0)
                y = p.get("y", 0.0)
                # Could add pin offset here if we had pin geometry
                points.append((float(x), float(y)))
    elif loop.components:
        # Use component centers
        for ref in loop.components:
            if ref in placements:
                p = placements[ref]
                x = p.get("x", 0.0)
                y = p.get("y", 0.0)
                points.append((float(x), float(y)))

    return points


def render_loop_path(
    loop: Loop,
    placements: dict[str, Any],
    color: str,
) -> str:
    """
    Generate SVG polygon/path connecting all pins in a loop.

    Creates a closed polygon path that visually represents the current loop
    on the PCB. The path connects all component pins/centers in order.

    Args:
        loop: The Loop object to render.
        placements: Dictionary mapping component refs to placement dicts.
            Each placement should have 'x' and 'y' keys.
        color: Hex color for the loop stroke (e.g., '#FF0000').

    Returns:
        SVG string containing the loop path element.

    Example:
        >>> svg = render_loop_path(my_loop, placements, "#FF0000")
        >>> assert "<polygon" in svg
    """
    # Validate color
    if not _is_valid_hex_color(color):
        color = "#808080"  # Default gray for invalid colors

    points = _get_loop_points(loop, placements)

    if len(points) < 2:
        # Not enough points to render
        return f"<!-- Loop '{loop.name}' has insufficient placement data -->"

    # Determine stroke width based on priority
    stroke_width = PRIORITY_STROKE_WIDTH.get(loop.priority, 2.0)

    # Build points string for polygon
    points_str = " ".join(f"{x},{y}" for x, y in points)

    # Get component refs for data attribute
    components = loop.get_component_refs()
    components_json = json.dumps(components)

    # Generate SVG polygon with interactivity attributes
    svg = f'''<polygon
        id="loop-{loop.name}"
        points="{points_str}"
        fill="none"
        stroke="{color}"
        stroke-width="{stroke_width}"
        stroke-linejoin="round"
        stroke-linecap="round"
        opacity="0.8"
        class="loop-path loop-{loop.priority.value}"
        data-loop="{loop.name}"
        data-components='{components_json}'
        onclick="highlightLoopComponents('{loop.name}')"
    >
        <title>{loop.name}: {loop.description}</title>
    </polygon>'''

    return svg


# =============================================================================
# Loop Area Display
# =============================================================================


def render_loop_area_indicator(loop: Loop) -> str:
    """
    Render an HTML indicator showing loop area compliance status.

    Shows current area vs. max area with a visual indicator:
    - Green checkmark if compliant
    - Red warning if over limit
    - Gray if area not yet computed

    Args:
        loop: The Loop object to display.

    Returns:
        HTML string with the area indicator.

    Example:
        >>> loop.set_current_area(300.0)  # Under 500mm² max
        >>> html = render_loop_area_indicator(loop)
        >>> assert "compliant" in html.lower() or "300" in html
    """
    current_area = loop.get_current_area()
    max_area = loop.max_area_mm2

    if current_area is None:
        # Area not computed
        return f"""<span class="loop-area-indicator unknown" title="Area not yet computed">
            <span class="area-status">—</span>
            <span class="area-values">N/A / {max_area:.0f} mm²</span>
        </span>"""

    # Calculate percentage
    percentage = (current_area / max_area) * 100 if max_area > 0 else 0
    is_compliant = current_area <= max_area

    if is_compliant:
        status_class = "compliant"
        status_icon = "✓"
        status_text = "Pass"
    else:
        status_class = "warning violation"
        status_icon = "✗"
        status_text = "Fail"

    return f'''<span class="loop-area-indicator {status_class}" title="{status_text}">
        <span class="area-status">{status_icon}</span>
        <span class="area-values">{current_area:.0f} / {max_area:.0f} mm²</span>
        <span class="area-percentage">({percentage:.0f}%)</span>
    </span>'''


# =============================================================================
# Loop Legend
# =============================================================================


def render_loop_legend(collection: LoopCollection) -> str:
    """
    Render an HTML legend showing all loops with their colors.

    The legend shows each loop with:
    - Color swatch
    - Loop name
    - Compliance status indicator

    Loops are sorted by priority (CRITICAL first).

    Args:
        collection: The LoopCollection to display.

    Returns:
        HTML string with the loop legend.

    Example:
        >>> html = render_loop_legend(my_collection)
        >>> assert "commutation" in html
    """
    if not collection.loops:
        return '<div class="loop-legend empty">No loops defined</div>'

    # Sort by priority (CRITICAL first)
    priority_order = {
        LoopPriority.CRITICAL: 0,
        LoopPriority.HIGH: 1,
        LoopPriority.MEDIUM: 2,
        LoopPriority.LOW: 3,
    }
    sorted_loops = sorted(collection.loops, key=lambda l: priority_order.get(l.priority, 4))

    items = []
    for loop in sorted_loops:
        color = get_loop_color(loop.loop_type, loop.priority)
        compliance = loop.is_area_compliant()

        # Compliance indicator
        if compliance is True:
            check = '<span class="compliance-check pass">✓</span>'
        elif compliance is False:
            check = '<span class="compliance-check fail warning">✗</span>'
        else:
            check = '<span class="compliance-check unknown">?</span>'

        items.append(f'''<div class="legend-item" data-loop="{loop.name}">
            <span class="color-swatch" style="background-color: {color};"></span>
            <span class="loop-name">{loop.name}</span>
            <span class="loop-priority">({loop.priority.value})</span>
            {check}
        </div>''')

    return f"""<div class="loop-legend">
        <h4>Current Loops</h4>
        {"".join(items)}
    </div>"""


# =============================================================================
# Loop Summary Table
# =============================================================================


def render_loop_summary_table(collection: LoopCollection) -> str:
    """
    Render an HTML table with detailed loop information.

    Columns: Name, Type, Priority, Max Area, Current Area, Status

    Args:
        collection: The LoopCollection to display.

    Returns:
        HTML string with the summary table.
    """
    if not collection.loops:
        return '<table class="loop-summary"><tr><td>No loops defined</td></tr></table>'

    # Sort by priority
    priority_order = {
        LoopPriority.CRITICAL: 0,
        LoopPriority.HIGH: 1,
        LoopPriority.MEDIUM: 2,
        LoopPriority.LOW: 3,
    }
    sorted_loops = sorted(collection.loops, key=lambda l: priority_order.get(l.priority, 4))

    rows = []
    for loop in sorted_loops:
        current_area = loop.get_current_area()
        area_str = f"{current_area:.1f}" if current_area is not None else "—"

        compliance = loop.is_area_compliant()
        if compliance is True:
            status = '<span class="status-pass">Pass</span>'
        elif compliance is False:
            status = '<span class="status-fail warning">Fail</span>'
        else:
            status = '<span class="status-unknown">Unknown</span>'

        rows.append(f'''<tr data-loop="{loop.name}">
            <td class="loop-name">{loop.name}</td>
            <td class="loop-type">{loop.loop_type.value}</td>
            <td class="loop-priority">{loop.priority.value}</td>
            <td class="max-area">{loop.max_area_mm2:.1f}</td>
            <td class="current-area">{area_str}</td>
            <td class="status">{status}</td>
        </tr>''')

    return f"""<table class="loop-summary">
        <thead>
            <tr>
                <th>Name</th>
                <th>Type</th>
                <th>Priority</th>
                <th>Max Area (mm²)</th>
                <th>Current Area (mm²)</th>
                <th>Status</th>
            </tr>
        </thead>
        <tbody>
            {"".join(rows)}
        </tbody>
    </table>"""


# =============================================================================
# Interactive Controls
# =============================================================================


def render_loop_toggle_controls(collection: LoopCollection) -> str:
    """
    Render HTML checkboxes to toggle loop visibility.

    Each loop gets a checkbox that can show/hide its path in the visualization.

    Args:
        collection: The LoopCollection to create controls for.

    Returns:
        HTML string with toggle controls.
    """
    if not collection.loops:
        return '<div class="loop-toggles">No loops defined</div>'

    controls = []
    for loop in collection.loops:
        color = get_loop_color(loop.loop_type, loop.priority)
        controls.append(f'''<label class="loop-toggle" data-loop="{loop.name}">
            <input type="checkbox" 
                   id="toggle-{loop.name}" 
                   name="loop-toggle" 
                   value="{loop.name}"
                   checked
                   onchange="toggleLoopVisibility('{loop.name}', this.checked)">
            <span class="color-swatch" style="background-color: {color};"></span>
            {loop.name}
        </label>''')

    return f"""<div class="loop-toggles">
        <h4>Show/Hide Loops</h4>
        {"".join(controls)}
    </div>"""


# =============================================================================
# Full Board Visualization
# =============================================================================


def render_board_with_loops(
    placements: dict[str, Any],
    loops: LoopCollection,
    board_width: float,
    board_height: float,
    show_components: bool = True,
    show_labels: bool = True,
) -> str:
    """
    Render full board SVG with components and all loops overlaid.

    The SVG includes:
    - Board outline
    - Component rectangles (if show_components=True)
    - Component labels (if show_labels=True)
    - All loop paths, rendered with lower priority loops first (underneath)

    Args:
        placements: Dictionary mapping component refs to placement dicts.
        loops: LoopCollection with all loops to display.
        board_width: Board width in mm.
        board_height: Board height in mm.
        show_components: Whether to show component rectangles.
        show_labels: Whether to show component reference labels.

    Returns:
        HTML string containing the complete SVG visualization.
    """
    # Add margin for visibility
    margin = 10
    viewbox = f"{-margin} {-margin} {board_width + 2 * margin} {board_height + 2 * margin}"

    elements = []

    # Board outline
    elements.append(f'''<rect 
        x="0" y="0" 
        width="{board_width}" height="{board_height}"
        fill="#1a472a" 
        stroke="#2d5a3d" 
        stroke-width="1"/>''')

    # Component rectangles and labels
    if show_components:
        for ref, p in placements.items():
            x = p.get("x", 0)
            y = p.get("y", 0)
            # Default component size (would come from footprint in real use)
            w = p.get("width", 10)
            h = p.get("height", 5)

            elements.append(f'''<rect 
                x="{x - w / 2}" y="{y - h / 2}" 
                width="{w}" height="{h}"
                fill="#4A90D9" 
                stroke="#000" 
                stroke-width="0.5"
                opacity="0.8"
                class="component"
                data-ref="{ref}"/>''')

            if show_labels:
                elements.append(f'''<text 
                    x="{x}" y="{y}"
                    text-anchor="middle"
                    dominant-baseline="middle"
                    font-size="4"
                    font-family="monospace"
                    fill="white">{ref}</text>''')

    # Render loops - lower priority first so higher priority renders on top
    priority_order = {
        LoopPriority.LOW: 0,
        LoopPriority.MEDIUM: 1,
        LoopPriority.HIGH: 2,
        LoopPriority.CRITICAL: 3,
    }
    sorted_loops = sorted(loops.loops, key=lambda l: priority_order.get(l.priority, 0))

    for loop in sorted_loops:
        color = get_loop_color(loop.loop_type, loop.priority)
        elements.append(render_loop_path(loop, placements, color))

    svg_content = "\n".join(elements)

    return f'''<svg 
        xmlns="http://www.w3.org/2000/svg"
        viewBox="{viewbox}"
        width="100%"
        height="auto"
        class="board-with-loops">
        <style>
            .loop-path:hover {{ opacity: 1; stroke-width: 4; }}
            .component:hover {{ opacity: 1; }}
        </style>
        {svg_content}
    </svg>'''


# =============================================================================
# Report Section Generation
# =============================================================================


def generate_loop_report_section(collection: LoopCollection) -> str:
    """
    Generate a complete collapsible HTML section for loop visualization.

    The section includes:
    - Summary statistics
    - Loop legend with compliance indicators
    - Summary table with all loop details
    - Physics metadata (di/dt, frequency)

    Args:
        collection: The LoopCollection to report on.

    Returns:
        HTML string with the complete report section.
    """
    summary = collection.summary()

    # Build physics info for loops with events
    physics_rows = []
    for loop in collection.loops:
        if loop.events.di_dt or loop.events.frequency_hz:
            di_dt = f"{loop.events.di_dt:.1e} A/s" if loop.events.di_dt else "—"
            freq = f"{loop.events.frequency_hz:.0f} Hz" if loop.events.frequency_hz else "—"
            if loop.events.frequency_hz and loop.events.frequency_hz >= 1000:
                freq = f"{loop.events.frequency_hz / 1000:.0f} kHz"
            peak = f"{loop.events.peak_current_a:.1f} A" if loop.events.peak_current_a else "—"
            physics_rows.append(f"""<tr>
                <td>{loop.name}</td>
                <td>{di_dt}</td>
                <td>{freq}</td>
                <td>{peak}</td>
            </tr>""")

    physics_table = ""
    if physics_rows:
        physics_table = f"""<h4>Physics Metadata</h4>
        <table class="physics-table">
            <thead>
                <tr><th>Loop</th><th>di/dt</th><th>Frequency</th><th>Peak Current</th></tr>
            </thead>
            <tbody>{"".join(physics_rows)}</tbody>
        </table>"""

    return f"""<details class="loop-report-section collapse" open>
        <summary><h3>Loop Analysis ({summary["total_loops"]} loops)</h3></summary>
        
        <div class="loop-summary-stats">
            <p>
                <strong>Total:</strong> {summary["total_loops"]} |
                <strong>Critical:</strong> {summary["critical_count"]} |
                <strong>Compliant:</strong> {summary["compliant_count"]} |
                <strong>Non-compliant:</strong> {summary["non_compliant_count"]}
            </p>
            {f'<p class="violation-warning">Total area violation: {summary["total_area_violation_mm2"]:.1f} mm²</p>' if summary["total_area_violation_mm2"] > 0 else ""}
        </div>

        {render_loop_legend(collection)}
        
        {render_loop_summary_table(collection)}
        
        {physics_table}
    </details>"""


# =============================================================================
# Metrics Export
# =============================================================================


def export_loop_metrics(collection: LoopCollection, format: str = "json") -> dict | str:
    """
    Export loop metrics as JSON or CSV.

    JSON format returns a dictionary with all loop data.
    CSV format returns a string with comma-separated values.

    Args:
        collection: The LoopCollection to export.
        format: Either "json" or "csv".

    Returns:
        Dictionary (for JSON) or string (for CSV).
    """
    loops_data = []
    for loop in collection.loops:
        current_area = loop.get_current_area()
        loops_data.append(
            {
                "name": loop.name,
                "loop_type": loop.loop_type.value,
                "priority": loop.priority.value,
                "max_area_mm2": loop.max_area_mm2,
                "current_area_mm2": current_area,
                "compliant": loop.is_area_compliant(),
                "components": loop.get_component_refs(),
                "di_dt": loop.events.di_dt,
                "frequency_hz": loop.events.frequency_hz,
                "peak_current_a": loop.events.peak_current_a,
            }
        )

    if format == "json":
        return {
            "collection_name": collection.name,
            "description": collection.description,
            "summary": collection.summary(),
            "loops": loops_data,
        }
    elif format == "csv":
        output = io.StringIO()
        if loops_data:
            # Use only scalar fields for CSV
            fieldnames = [
                "name",
                "loop_type",
                "priority",
                "max_area_mm2",
                "current_area_mm2",
                "compliant",
            ]
            writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(loops_data)
        return output.getvalue()
    else:
        raise ValueError(f"Unknown format: {format}. Use 'json' or 'csv'.")


# =============================================================================
# SVG Export
# =============================================================================


def export_loops_svg(
    loops: LoopCollection,
    placements: dict[str, Any],
    width: float,
    height: float,
    background_color: str | None = None,
    show_components: bool = False,
    show_labels: bool = False,
) -> str:
    """
    Export loops as a standalone SVG file.

    Creates a complete SVG document with proper namespace that can be
    saved as a .svg file and opened in any SVG viewer.

    Args:
        loops: LoopCollection to render.
        placements: Component placement dictionary.
        width: Board width in mm.
        height: Board height in mm.
        background_color: Optional background fill color.
        show_components: Whether to show component rectangles.
        show_labels: Whether to show component labels.

    Returns:
        Complete SVG document string.
    """
    margin = 10
    viewbox = f"{-margin} {-margin} {width + 2 * margin} {height + 2 * margin}"

    elements = []

    # Background
    if background_color:
        elements.append(f'''<rect 
            x="{-margin}" y="{-margin}" 
            width="{width + 2 * margin}" height="{height + 2 * margin}"
            fill="{background_color}"/>''')

    # Board outline
    elements.append(f'''<rect 
        x="0" y="0" 
        width="{width}" height="{height}"
        fill="none" 
        stroke="#333" 
        stroke-width="0.5"/>''')

    # Components (if requested)
    if show_components:
        for ref, p in placements.items():
            x = p.get("x", 0)
            y = p.get("y", 0)
            w = p.get("width", 10)
            h = p.get("height", 5)

            elements.append(f'''<rect 
                x="{x - w / 2}" y="{y - h / 2}" 
                width="{w}" height="{h}"
                fill="#ccc" 
                stroke="#666" 
                stroke-width="0.3"/>''')

            if show_labels:
                elements.append(f'''<text 
                    x="{x}" y="{y}"
                    text-anchor="middle"
                    dominant-baseline="middle"
                    font-size="3"
                    font-family="sans-serif"
                    fill="#333">{ref}</text>''')

    # Loops
    priority_order = {
        LoopPriority.LOW: 0,
        LoopPriority.MEDIUM: 1,
        LoopPriority.HIGH: 2,
        LoopPriority.CRITICAL: 3,
    }
    sorted_loops = sorted(loops.loops, key=lambda l: priority_order.get(l.priority, 0))

    for loop in sorted_loops:
        color = get_loop_color(loop.loop_type, loop.priority)
        elements.append(render_loop_path(loop, placements, color))

    svg_content = "\n".join(elements)

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     viewBox="{viewbox}"
     width="{width + 2 * margin}mm"
     height="{height + 2 * margin}mm">
    {svg_content}
</svg>'''


# =============================================================================
# Animation
# =============================================================================


def render_animated_loop(
    loop: Loop,
    placements: dict[str, Any],
    animate: bool = True,
) -> str:
    """
    Render a loop with optional current flow animation.

    When animated, shows a dashed stroke with moving dashes to indicate
    current direction and flow.

    Args:
        loop: The Loop to render.
        placements: Component placement dictionary.
        animate: Whether to include animation (True) or static (False).

    Returns:
        SVG string with optional animation.
    """
    color = get_loop_color(loop.loop_type, loop.priority)
    points = _get_loop_points(loop, placements)

    if len(points) < 2:
        return f"<!-- Loop '{loop.name}' has insufficient placement data -->"

    stroke_width = PRIORITY_STROKE_WIDTH.get(loop.priority, 2.0)
    points_str = " ".join(f"{x},{y}" for x, y in points)

    if animate:
        # Animated version with moving dashes
        return f'''<polygon
            id="loop-{loop.name}-animated"
            points="{points_str}"
            fill="none"
            stroke="{color}"
            stroke-width="{stroke_width}"
            stroke-dasharray="5,3"
            stroke-linejoin="round"
            opacity="0.8"
            class="loop-animated">
            <animate 
                attributeName="stroke-dashoffset"
                from="0"
                to="16"
                dur="0.5s"
                repeatCount="indefinite"/>
            <title>{loop.name}: {loop.description}</title>
        </polygon>'''
    else:
        # Static version (same as regular render but without interactivity)
        return f'''<polygon
            id="loop-{loop.name}"
            points="{points_str}"
            fill="none"
            stroke="{color}"
            stroke-width="{stroke_width}"
            stroke-linejoin="round"
            opacity="0.8">
            <title>{loop.name}: {loop.description}</title>
        </polygon>'''
