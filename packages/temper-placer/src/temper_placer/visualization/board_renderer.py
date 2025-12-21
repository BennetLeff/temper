"""
Board rendering with Plotly.

This module provides functions to render PCB board layouts using Plotly,
including component rectangles, zones, and annotations.

The rendering is designed to work with the visualization data models
and produce interactive HTML visualizations that can be:
- Displayed in Jupyter notebooks
- Served via WebSocket to a browser
- Exported as static HTML files
"""

from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING

# Plotly is an optional dependency for testing without full install
try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    go = None  # type: ignore
    make_subplots = None  # type: ignore

from temper_placer.visualization.model import (
    BoardView,
    ComponentStatus,
    ComponentView,
    ConstraintStatus,
    PadView,
    Rectangle,
    TraceView,
    ZoneView,
)

if TYPE_CHECKING:
    from temper_placer.core.loop import LoopCollection

# Color scheme for component status
STATUS_COLORS: dict[ComponentStatus, str] = {
    ComponentStatus.OK: "#4CAF50",  # Green
    ComponentStatus.WARNING: "#FF9800",  # Orange
    ComponentStatus.ERROR: "#F44336",  # Red
    ComponentStatus.FIXED: "#9E9E9E",  # Gray
}

# Color scheme for zones
ZONE_COLORS: dict[str, str] = {
    "keepout": "rgba(255, 0, 0, 0.2)",
    "copper": "rgba(255, 215, 0, 0.3)",
    "ground": "rgba(0, 128, 0, 0.2)",
    "hv": "rgba(255, 0, 255, 0.2)",
    "generic": "rgba(128, 128, 128, 0.2)",
}

# Default board colors
BOARD_BACKGROUND = "#1a472a"  # Dark green (PCB color)
BOARD_BORDER = "#2d5a3d"

# Colors for copper layers
LAYER_COLORS: dict[str, str] = {
    "F.Cu": "#FFD700",  # Gold for front copper
    "B.Cu": "#4169E1",  # Royal blue for back copper
    "*.Cu": "#CD853F",  # Peru (brownish) for through-hole
    "In1.Cu": "#FF6347",  # Tomato for inner layer 1
    "In2.Cu": "#32CD32",  # Lime green for inner layer 2
}

# Pad colors
PAD_COLORS: dict[str, str] = {
    "smd": "#C0C0C0",  # Silver for SMD
    "thru_hole": "#CD7F32",  # Bronze for through-hole
    "*.Cu": "#CD7F32",  # Bronze for through-hole
}


def check_plotly_available() -> None:
    """Raise ImportError if Plotly is not available."""
    if not PLOTLY_AVAILABLE:
        raise ImportError(
            "Plotly is required for visualization. Install with: pip install plotly>=5.18.0"
        )


def get_rectangle_shape(
    rect: Rectangle,
    fill_color: str,
    line_color: str = "#000000",
    line_width: float = 1.0,
    opacity: float = 0.8,
) -> dict[str, Any]:
    """
    Create a Plotly shape dict for a rotated rectangle.

    Args:
        rect: Rectangle to render.
        fill_color: Fill color (CSS color string).
        line_color: Border color.
        line_width: Border width in pixels.
        opacity: Fill opacity (0-1).

    Returns:
        Plotly shape dictionary.
    """
    corners = rect.corners
    # Create SVG path for the rectangle
    path = f"M {corners[0].x},{corners[0].y}"
    for corner in corners[1:]:
        path += f" L {corner.x},{corner.y}"
    path += " Z"

    return {
        "type": "path",
        "path": path,
        "fillcolor": fill_color,
        "line": {"color": line_color, "width": line_width},
        "opacity": opacity,
        "layer": "above",
    }


def get_component_shape(
    component: ComponentView,
    show_status_color: bool = True,
) -> dict[str, Any]:
    """
    Create a Plotly shape for a component.

    Args:
        component: ComponentView to render.
        show_status_color: Whether to color by status.

    Returns:
        Plotly shape dictionary.
    """
    fill_color = STATUS_COLORS.get(component.status, "#808080")
    if not show_status_color:
        fill_color = "#4A90D9"  # Default blue

    # Determine border based on status
    line_color = "#000000"
    line_width = 1.0
    if component.status == ComponentStatus.ERROR:
        line_color = "#FF0000"
        line_width = 2.0
    elif component.status == ComponentStatus.WARNING:
        line_color = "#FFA500"
        line_width = 1.5

    return get_rectangle_shape(
        rect=component.bounds,
        fill_color=fill_color,
        line_color=line_color,
        line_width=line_width,
        opacity=0.8,
    )


def get_zone_shape(zone: ZoneView) -> dict[str, Any]:
    """
    Create a Plotly shape for a zone.

    Args:
        zone: ZoneView to render.

    Returns:
        Plotly shape dictionary.
    """
    # Get color from zone type or use custom color
    fill_color = zone.color or ZONE_COLORS.get(zone.zone_type, ZONE_COLORS["generic"])

    # Create SVG path
    if not zone.polygon:
        return {}

    path = f"M {zone.polygon[0].x},{zone.polygon[0].y}"
    for point in zone.polygon[1:]:
        path += f" L {point.x},{point.y}"
    path += " Z"

    return {
        "type": "path",
        "path": path,
        "fillcolor": fill_color,
        "line": {"color": "rgba(0,0,0,0.3)", "width": 1, "dash": "dash"},
        "opacity": 0.5,
        "layer": "below",
    }


def get_trace_shapes(
    traces: tuple[TraceView, ...],
    layer_filter: str | None = None,
) -> list[dict[str, Any]]:
    """
    Create Plotly shapes for trace segments.

    Args:
        traces: Tuple of TraceView objects.
        layer_filter: If specified, only render traces on this layer.

    Returns:
        List of Plotly shape dictionaries (lines).
    """
    shapes = []
    for trace in traces:
        # Filter by layer if specified
        if layer_filter and trace.layer != layer_filter:
            continue

        # Get color based on layer
        color = LAYER_COLORS.get(trace.layer, LAYER_COLORS.get("F.Cu", "#FFD700"))

        # Scale width for visibility (minimum 0.5px rendered width)
        line_width = max(trace.width * 2, 0.5)

        shapes.append(
            {
                "type": "line",
                "x0": trace.start.x,
                "y0": trace.start.y,
                "x1": trace.end.x,
                "y1": trace.end.y,
                "line": {"color": color, "width": line_width},
                "layer": "above",
            }
        )

    return shapes


def get_pad_shapes(
    pads: tuple[PadView, ...],
    layer_filter: str | None = None,
) -> list[dict[str, Any]]:
    """
    Create Plotly shapes for pads.

    Args:
        pads: Tuple of PadView objects.
        layer_filter: If specified, only render pads on this layer.

    Returns:
        List of Plotly shape dictionaries.
    """
    import math

    shapes = []
    for pad in pads:
        # Filter by layer if specified (allow through-hole on any layer)
        if layer_filter and pad.layer != layer_filter and pad.layer != "*.Cu":
            continue

        # Get color based on layer/type
        if pad.layer == "*.Cu":
            color = PAD_COLORS.get("thru_hole", "#CD7F32")
        else:
            color = PAD_COLORS.get("smd", "#C0C0C0")

        px, py = pad.position.x, pad.position.y
        pw, ph = pad.size

        if pad.shape == "circle":
            # Circle pad - use the larger dimension as diameter
            radius = max(pw, ph) / 2
            shapes.append(
                {
                    "type": "circle",
                    "x0": px - radius,
                    "y0": py - radius,
                    "x1": px + radius,
                    "y1": py + radius,
                    "fillcolor": color,
                    "line": {"color": "#000000", "width": 0.5},
                    "opacity": 0.9,
                    "layer": "above",
                }
            )
        elif pad.shape == "oval":
            # Oval - approximate with ellipse
            shapes.append(
                {
                    "type": "circle",
                    "x0": px - pw / 2,
                    "y0": py - ph / 2,
                    "x1": px + pw / 2,
                    "y1": py + ph / 2,
                    "fillcolor": color,
                    "line": {"color": "#000000", "width": 0.5},
                    "opacity": 0.9,
                    "layer": "above",
                }
            )
        else:
            # Rectangle or roundrect - render as rectangle
            # Apply rotation if needed
            if pad.rotation != 0:
                angle_rad = math.radians(pad.rotation)
                cos_a = math.cos(angle_rad)
                sin_a = math.sin(angle_rad)

                # Corners relative to center
                hw, hh = pw / 2, ph / 2
                corners_rel = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]

                # Rotate and translate
                path = ""
                for i, (dx, dy) in enumerate(corners_rel):
                    rx = px + dx * cos_a - dy * sin_a
                    ry = py + dx * sin_a + dy * cos_a
                    if i == 0:
                        path = f"M {rx},{ry}"
                    else:
                        path += f" L {rx},{ry}"
                path += " Z"

                shapes.append(
                    {
                        "type": "path",
                        "path": path,
                        "fillcolor": color,
                        "line": {"color": "#000000", "width": 0.5},
                        "opacity": 0.9,
                        "layer": "above",
                    }
                )
            else:
                # Simple rectangle
                shapes.append(
                    {
                        "type": "rect",
                        "x0": px - pw / 2,
                        "y0": py - ph / 2,
                        "x1": px + pw / 2,
                        "y1": py + ph / 2,
                        "fillcolor": color,
                        "line": {"color": "#000000", "width": 0.5},
                        "opacity": 0.9,
                        "layer": "above",
                    }
                )

    return shapes


def create_trace_hover_data(
    traces: tuple[TraceView, ...],
) -> tuple[list[float], list[float], list[str]]:
    """
    Create hover data for traces (at midpoints).

    Args:
        traces: Tuple of traces.

    Returns:
        Tuple of (x_coords, y_coords, hover_texts).
    """
    x_coords = []
    y_coords = []
    hover_texts = []

    for trace in traces:
        # Midpoint of trace
        mid_x = (trace.start.x + trace.end.x) / 2
        mid_y = (trace.start.y + trace.end.y) / 2
        x_coords.append(mid_x)
        y_coords.append(mid_y)

        # Build hover text
        hover = "<b>Trace</b><br>"
        hover += f"Layer: {trace.layer}<br>"
        hover += f"Width: {trace.width:.3f} mm<br>"
        if trace.net:
            hover += f"Net: {trace.net}"
        hover_texts.append(hover)

    return x_coords, y_coords, hover_texts


def create_pad_hover_data(
    pads: tuple[PadView, ...],
) -> tuple[list[float], list[float], list[str]]:
    """
    Create hover data for pads.

    Args:
        pads: Tuple of pads.

    Returns:
        Tuple of (x_coords, y_coords, hover_texts).
    """
    x_coords = []
    y_coords = []
    hover_texts = []

    for pad in pads:
        x_coords.append(pad.position.x)
        y_coords.append(pad.position.y)

        # Build hover text
        hover = f"<b>Pad {pad.number}</b><br>"
        if pad.component_ref:
            hover += f"Component: {pad.component_ref}<br>"
        hover += f"Position: ({pad.position.x:.2f}, {pad.position.y:.2f})<br>"
        hover += f"Size: {pad.size[0]:.2f} x {pad.size[1]:.2f} mm<br>"
        hover += f"Shape: {pad.shape}<br>"
        hover += f"Layer: {pad.layer}<br>"
        if pad.net:
            hover += f"Net: {pad.net}"
        hover_texts.append(hover)

    return x_coords, y_coords, hover_texts


def create_component_annotations(
    components: tuple[ComponentView, ...],
    show_refs: bool = True,
    font_size: int = 10,
) -> list[dict[str, Any]]:
    """
    Create annotations for component reference designators.

    Args:
        components: Tuple of components to annotate.
        show_refs: Whether to show reference designators.
        font_size: Font size for labels.

    Returns:
        List of Plotly annotation dictionaries.
    """
    if not show_refs:
        return []

    annotations = []
    for comp in components:
        annotations.append(
            {
                "x": comp.position.x,
                "y": comp.position.y,
                "text": comp.ref,
                "showarrow": False,
                "font": {
                    "size": font_size,
                    "color": "#FFFFFF",
                    "family": "monospace",
                },
                "bgcolor": "rgba(0,0,0,0.5)",
                "borderpad": 2,
            }
        )
    return annotations


def create_component_hover_data(
    components: tuple[ComponentView, ...],
) -> tuple[list[float], list[float], list[str]]:
    """
    Create hover data for components.

    Args:
        components: Tuple of components.

    Returns:
        Tuple of (x_coords, y_coords, hover_texts).
    """
    x_coords = []
    y_coords = []
    hover_texts = []

    for comp in components:
        x_coords.append(comp.position.x)
        y_coords.append(comp.position.y)

        # Build hover text
        hover = f"<b>{comp.ref}</b>"
        if comp.value:
            hover += f" ({comp.value})"
        hover += "<br>"
        hover += f"Position: ({comp.position.x:.2f}, {comp.position.y:.2f})<br>"
        hover += f"Size: {comp.width:.2f} x {comp.height:.2f} mm<br>"
        hover += f"Rotation: {comp.rotation:.0f}°<br>"
        hover += f"Status: {comp.status.value}"
        if comp.footprint:
            hover += f"<br>Footprint: {comp.footprint}"
        if comp.zone:
            hover += f"<br>Zone: {comp.zone}"
        if comp.violations:
            hover += "<br><b>Violations:</b><br>"
            for v in comp.violations:
                hover += f"  • {v}<br>"
        hover_texts.append(hover)

    return x_coords, y_coords, hover_texts


def _add_legend_traces(
    fig: go.Figure,
    board: BoardView,
    show_traces: bool,
    show_pads: bool,
    show_status_colors: bool,
) -> None:
    """
    Add dummy traces for legend display.

    Creates invisible marker traces that appear in the legend to explain
    the color coding used in the visualization.

    Args:
        fig: Plotly figure to add traces to.
        board: BoardView being rendered.
        show_traces: Whether traces are being shown.
        show_pads: Whether pads are being shown.
        show_status_colors: Whether status colors are being shown.
    """
    # Use a position outside the visible area for legend markers
    legend_x = -100
    legend_y = -100

    # Component status legend (if showing status colors)
    if show_status_colors:
        for status, color in STATUS_COLORS.items():
            fig.add_trace(
                go.Scatter(
                    x=[legend_x],
                    y=[legend_y],
                    mode="markers",
                    marker={"size": 12, "color": color, "symbol": "square"},
                    name=f"Component: {status.value}",
                    showlegend=True,
                    legendgroup="components",
                    legendgrouptitle_text="Components",
                    hoverinfo="skip",
                )
            )

    # Trace layer legend (if showing traces)
    if show_traces and board.traces:
        # Only show legend for layers actually present
        layers_present = set(t.layer for t in board.traces)
        for layer, color in LAYER_COLORS.items():
            if layer in layers_present:
                layer_name = {
                    "F.Cu": "Front Copper",
                    "B.Cu": "Back Copper",
                    "*.Cu": "Through-hole",
                }.get(layer, layer)
                fig.add_trace(
                    go.Scatter(
                        x=[legend_x],
                        y=[legend_y],
                        mode="lines",
                        line={"color": color, "width": 3},
                        name=f"Trace: {layer_name}",
                        showlegend=True,
                        legendgroup="traces",
                        legendgrouptitle_text="Traces",
                        hoverinfo="skip",
                    )
                )

    # Pad type legend (if showing pads)
    if show_pads and board.pads:
        # Check which pad types are present
        has_smd = any(p.layer != "*.Cu" for p in board.pads)
        has_thru = any(p.layer == "*.Cu" for p in board.pads)

        if has_smd:
            fig.add_trace(
                go.Scatter(
                    x=[legend_x],
                    y=[legend_y],
                    mode="markers",
                    marker={"size": 10, "color": PAD_COLORS["smd"], "symbol": "square"},
                    name="Pad: SMD",
                    showlegend=True,
                    legendgroup="pads",
                    legendgrouptitle_text="Pads",
                    hoverinfo="skip",
                )
            )
        if has_thru:
            fig.add_trace(
                go.Scatter(
                    x=[legend_x],
                    y=[legend_y],
                    mode="markers",
                    marker={
                        "size": 10,
                        "color": PAD_COLORS["thru_hole"],
                        "symbol": "circle",
                    },
                    name="Pad: Through-hole",
                    showlegend=True,
                    legendgroup="pads",
                    legendgrouptitle_text="Pads",
                    hoverinfo="skip",
                )
            )


def render_board(
    board: BoardView,
    title: str | None = None,
    show_refs: bool = True,
    show_status_colors: bool = True,
    show_zones: bool = True,
    show_grid: bool = True,
    show_traces: bool = True,
    show_pads: bool = True,
    show_legend: bool = True,
    loops: LoopCollection | None = None,
    width: int = 800,
    height: int = 600,
) -> go.Figure:
    """
    Render a board view as a Plotly figure.

    Args:
        board: BoardView to render.
        title: Optional title for the figure.
        show_refs: Whether to show reference designators.
        show_status_colors: Whether to color components by status.
        show_zones: Whether to show board zones.
        show_grid: Whether to show background grid.
        show_traces: Whether to show copper traces.
        show_pads: Whether to show component pads.
        show_legend: Whether to show color legend.
        loops: Optional LoopCollection to overlay on the board.
        width: Figure width in pixels.
        height: Figure height in pixels.

    Returns:
        Plotly Figure object.

    Raises:
        ImportError: If Plotly is not installed.
    """
    check_plotly_available()

    fig = go.Figure()

    # Collect shapes
    shapes = []

    # Board outline
    shapes.append(
        {
            "type": "rect",
            "x0": 0,
            "y0": 0,
            "x1": board.width,
            "y1": board.height,
            "fillcolor": BOARD_BACKGROUND,
            "line": {"color": BOARD_BORDER, "width": 2},
            "layer": "below",
        }
    )

    # Add zones (below everything)
    if show_zones:
        for zone in board.zones:
            shape = get_zone_shape(zone)
            if shape:
                shapes.append(shape)

    # Add traces (above zones, below pads)
    if show_traces and board.traces:
        # Render back copper first, then front copper
        shapes.extend(get_trace_shapes(board.traces, layer_filter="B.Cu"))
        shapes.extend(get_trace_shapes(board.traces, layer_filter="F.Cu"))
        # Render any other layers
        for trace in board.traces:
            if trace.layer not in ("F.Cu", "B.Cu"):
                shapes.extend(get_trace_shapes((trace,)))

    # Add pads - SMD pads below components, through-hole pads above
    if show_pads and board.pads:
        # SMD pads first (below components)
        smd_pads = tuple(p for p in board.pads if p.layer != "*.Cu")
        shapes.extend(get_pad_shapes(smd_pads))

    # Add component shapes (on top of SMD pads)
    for comp in board.components:
        shapes.append(get_component_shape(comp, show_status_colors))

    # Add through-hole pads last (on top of components)
    if show_pads and board.pads:
        thru_pads = tuple(p for p in board.pads if p.layer == "*.Cu")
        shapes.extend(get_pad_shapes(thru_pads))

    # Add invisible scatter for component hover
    x_coords, y_coords, hover_texts = create_component_hover_data(board.components)
    fig.add_trace(
        go.Scatter(
            x=x_coords,
            y=y_coords,
            mode="markers",
            marker={"size": 1, "opacity": 0},
            hoverinfo="text",
            hovertext=hover_texts,
            showlegend=False,
            name="Components",
        )
    )

    # Add invisible scatter for trace hover
    if show_traces and board.traces:
        tx, ty, tt = create_trace_hover_data(board.traces)
        if tx:
            fig.add_trace(
                go.Scatter(
                    x=tx,
                    y=ty,
                    mode="markers",
                    marker={"size": 1, "opacity": 0},
                    hoverinfo="text",
                    hovertext=tt,
                    showlegend=False,
                    name="Traces",
                )
            )

    # Add invisible scatter for pad hover
    if show_pads and board.pads:
        px, py, pt = create_pad_hover_data(board.pads)
        if px:
            fig.add_trace(
                go.Scatter(
                    x=px,
                    y=py,
                    mode="markers",
                    marker={"size": 1, "opacity": 0},
                    hoverinfo="text",
                    hovertext=pt,
                    showlegend=False,
                    name="Pads",
                )
            )

    # Add loops if provided
    if loops:
        from .loop_viz import add_loops_to_plotly
        add_loops_to_plotly(fig, loops, board)

    # Add legend traces (dummy markers for legend display)
    if show_legend:
        _add_legend_traces(fig, board, show_traces, show_pads, show_status_colors)

    # Create annotations
    annotations = create_component_annotations(board.components, show_refs=show_refs)

    # Configure layout
    fig.update_layout(
        shapes=shapes,
        annotations=annotations,
        title={
            "text": title or board.title or "PCB Layout",
            "x": 0.5,
            "xanchor": "center",
        },
        xaxis={
            "title": "X (mm)",
            "range": [-5, board.width + 5],
            "scaleanchor": "y",
            "scaleratio": 1,
            "showgrid": show_grid,
            "gridcolor": "rgba(255,255,255,0.1)",
            "zeroline": False,
        },
        yaxis={
            "title": "Y (mm)",
            "range": [-5, board.height + 5],
            "showgrid": show_grid,
            "gridcolor": "rgba(255,255,255,0.1)",
            "zeroline": False,
        },
        width=width,
        height=height,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="#f5f5f5",
        hovermode="closest",
        margin={"l": 60, "r": 150 if show_legend else 20, "t": 60, "b": 60},
        showlegend=show_legend,
        legend={
            "orientation": "v",
            "yanchor": "top",
            "y": 1,
            "xanchor": "left",
            "x": 1.02,
            "bgcolor": "rgba(255,255,255,0.8)",
            "bordercolor": "#ccc",
            "borderwidth": 1,
        },
    )

    return fig


def render_board_with_violations(
    board: BoardView,
    constraints: ConstraintStatus,
    title: str | None = None,
    highlight_violations: bool = True,
    **kwargs: Any,
) -> go.Figure:
    """
    Render a board view with violation highlights.

    Args:
        board: BoardView to render.
        constraints: ConstraintStatus with violation information.
        title: Optional title for the figure.
        highlight_violations: Whether to highlight violation locations.
        **kwargs: Additional arguments passed to render_board.

    Returns:
        Plotly Figure object.
    """
    check_plotly_available()

    # Render base board
    fig = render_board(board, title=title, **kwargs)

    if not highlight_violations or not constraints.violations:
        return fig

    # Add violation markers
    violation_x = []
    violation_y = []
    violation_text = []

    for violation in constraints.violations:
        if violation.location:
            violation_x.append(violation.location.x)
            violation_y.append(violation.location.y)
            violation_text.append(
                f"<b>{violation.violation_type.value.upper()}</b><br>"
                f"Severity: {violation.severity:.2f}<br>"
                f"{violation.message}"
            )

    if violation_x:
        fig.add_trace(
            go.Scatter(
                x=violation_x,
                y=violation_y,
                mode="markers",
                marker={
                    "symbol": "x",
                    "size": 15,
                    "color": "#FF0000",
                    "line": {"width": 2, "color": "#FFFFFF"},
                },
                hoverinfo="text",
                hovertext=violation_text,
                name="Violations",
                showlegend=True,
            )
        )

    return fig


def render_board_comparison(
    board_before: BoardView,
    board_after: BoardView,
    title: str | None = None,
    width: int = 1200,
    height: int = 500,
) -> go.Figure:
    """
    Render a side-by-side comparison of two board states.

    Args:
        board_before: Initial board state.
        board_after: Final board state.
        title: Optional title for the figure.
        width: Total figure width in pixels.
        height: Figure height in pixels.

    Returns:
        Plotly Figure with two subplots.
    """
    check_plotly_available()

    fig = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=("Before Optimization", "After Optimization"),
        horizontal_spacing=0.1,
    )

    # Render both boards
    fig_before = render_board(board_before, show_refs=True)
    fig_after = render_board(board_after, show_refs=True)

    # Copy traces
    for trace in fig_before.data:
        trace.xaxis = "x1"
        trace.yaxis = "y1"
        fig.add_trace(trace, row=1, col=1)

    for trace in fig_after.data:
        trace.xaxis = "x2"
        trace.yaxis = "y2"
        fig.add_trace(trace, row=1, col=2)

    # Copy shapes to appropriate subplot
    all_shapes = []
    for shape in fig_before.layout.shapes:
        shape_dict = shape.to_plotly_json() if hasattr(shape, "to_plotly_json") else dict(shape)
        shape_dict["xref"] = "x1"
        shape_dict["yref"] = "y1"
        all_shapes.append(shape_dict)

    for shape in fig_after.layout.shapes:
        shape_dict = shape.to_plotly_json() if hasattr(shape, "to_plotly_json") else dict(shape)
        shape_dict["xref"] = "x2"
        shape_dict["yref"] = "y2"
        all_shapes.append(shape_dict)

    # Update layout
    fig.update_layout(
        shapes=all_shapes,
        title={
            "text": title or "Placement Comparison",
            "x": 0.5,
            "xanchor": "center",
        },
        width=width,
        height=height,
        showlegend=False,
        paper_bgcolor="#f5f5f5",
    )

    # Configure axes for both subplots
    for i in [1, 2]:
        board = board_before if i == 1 else board_after
        fig.update_xaxes(
            title_text="X (mm)",
            range=[-5, board.width + 5],
            scaleanchor=f"y{i}" if i == 1 else "y2",
            scaleratio=1,
            row=1,
            col=i,
        )
        fig.update_yaxes(
            title_text="Y (mm)",
            range=[-5, board.height + 5],
            row=1,
            col=i,
        )

    return fig


def board_to_html(
    board: BoardView,
    output_path: str | None = None,
    include_plotlyjs: bool = True,
    **kwargs: Any,
) -> str:
    """
    Render a board view to HTML.

    Args:
        board: BoardView to render.
        output_path: Optional path to write HTML file.
        include_plotlyjs: Whether to include Plotly.js in HTML.
        **kwargs: Additional arguments passed to render_board.

    Returns:
        HTML string.
    """
    check_plotly_available()

    fig = render_board(board, **kwargs)
    html = fig.to_html(include_plotlyjs=include_plotlyjs, full_html=True)

    if output_path:
        with open(output_path, "w") as f:
            f.write(html)

    return html


def board_to_json(board: BoardView, **kwargs: Any) -> str:
    """
    Render a board view to Plotly JSON.

    This JSON can be used to render the figure in JavaScript.

    Args:
        board: BoardView to render.
        **kwargs: Additional arguments passed to render_board.

    Returns:
        JSON string of the Plotly figure.
    """
    check_plotly_available()

    fig = render_board(board, **kwargs)
    return fig.to_json()
