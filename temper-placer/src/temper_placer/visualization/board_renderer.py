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

from typing import Any, Dict, List, Optional, Tuple

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
    Point,
    Rectangle,
    ViolationType,
    ZoneView,
)


# Color scheme for component status
STATUS_COLORS: Dict[ComponentStatus, str] = {
    ComponentStatus.OK: "#4CAF50",  # Green
    ComponentStatus.WARNING: "#FF9800",  # Orange
    ComponentStatus.ERROR: "#F44336",  # Red
    ComponentStatus.FIXED: "#9E9E9E",  # Gray
}

# Color scheme for zones
ZONE_COLORS: Dict[str, str] = {
    "keepout": "rgba(255, 0, 0, 0.2)",
    "copper": "rgba(255, 215, 0, 0.3)",
    "ground": "rgba(0, 128, 0, 0.2)",
    "hv": "rgba(255, 0, 255, 0.2)",
    "generic": "rgba(128, 128, 128, 0.2)",
}

# Default board colors
BOARD_BACKGROUND = "#1a472a"  # Dark green (PCB color)
BOARD_BORDER = "#2d5a3d"


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
) -> Dict[str, Any]:
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
) -> Dict[str, Any]:
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


def get_zone_shape(zone: ZoneView) -> Dict[str, Any]:
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


def create_component_annotations(
    components: Tuple[ComponentView, ...],
    show_refs: bool = True,
    font_size: int = 10,
) -> List[Dict[str, Any]]:
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
    components: Tuple[ComponentView, ...],
) -> Tuple[List[float], List[float], List[str]]:
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
        hover = f"<b>{comp.ref}</b><br>"
        hover += f"Position: ({comp.position.x:.2f}, {comp.position.y:.2f})<br>"
        hover += f"Size: {comp.width:.2f} x {comp.height:.2f} mm<br>"
        hover += f"Rotation: {comp.rotation:.0f}°<br>"
        hover += f"Status: {comp.status.value}"
        if comp.footprint:
            hover += f"<br>Footprint: {comp.footprint}"
        if comp.zone:
            hover += f"<br>Zone: {comp.zone}"
        if comp.violations:
            hover += f"<br><b>Violations:</b><br>"
            for v in comp.violations:
                hover += f"  • {v}<br>"
        hover_texts.append(hover)

    return x_coords, y_coords, hover_texts


def render_board(
    board: BoardView,
    title: Optional[str] = None,
    show_refs: bool = True,
    show_status_colors: bool = True,
    show_zones: bool = True,
    show_grid: bool = True,
    width: int = 800,
    height: int = 600,
) -> "go.Figure":
    """
    Render a board view as a Plotly figure.

    Args:
        board: BoardView to render.
        title: Optional title for the figure.
        show_refs: Whether to show reference designators.
        show_status_colors: Whether to color components by status.
        show_zones: Whether to show board zones.
        show_grid: Whether to show background grid.
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

    # Add zones (below components)
    if show_zones:
        for zone in board.zones:
            shape = get_zone_shape(zone)
            if shape:
                shapes.append(shape)

    # Add component shapes
    for comp in board.components:
        shapes.append(get_component_shape(comp, show_status_colors))

    # Add invisible scatter for hover
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
        )
    )

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
        margin={"l": 60, "r": 20, "t": 60, "b": 60},
    )

    return fig


def render_board_with_violations(
    board: BoardView,
    constraints: ConstraintStatus,
    title: Optional[str] = None,
    highlight_violations: bool = True,
    **kwargs: Any,
) -> "go.Figure":
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
    title: Optional[str] = None,
    width: int = 1200,
    height: int = 500,
) -> "go.Figure":
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
        shape_dict = dict(shape)
        shape_dict["xref"] = "x1"
        shape_dict["yref"] = "y1"
        all_shapes.append(shape_dict)

    for shape in fig_after.layout.shapes:
        shape_dict = dict(shape)
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
    output_path: Optional[str] = None,
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
