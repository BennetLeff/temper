"""
Constraint status panel rendering.

This module provides functions to render constraint violation status
as a Plotly figure for display in the visualization dashboard.

The panel shows:
- Overall status indicator (valid/invalid)
- Summary counts by violation category
- Detailed list of individual violations
- Links to affected components for highlighting
"""

from __future__ import annotations

import json
from typing import Any

from .model import (
    ConstraintStatus,
    Violation,
    ViolationType,
)

# Check if Plotly is available (optional dependency)
try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    go = None  # type: ignore
    make_subplots = None  # type: ignore


# Color scheme for violation types
VIOLATION_COLORS: dict[ViolationType, str] = {
    ViolationType.OVERLAP: "#e74c3c",  # Red
    ViolationType.BOUNDARY: "#e67e22",  # Orange
    ViolationType.CLEARANCE: "#f1c40f",  # Yellow
    ViolationType.THERMAL: "#9b59b6",  # Purple
    ViolationType.ZONE: "#3498db",  # Blue
    ViolationType.DRC: "#c0392b",  # Dark red
}

# Severity color gradient
SEVERITY_COLORS = {
    "low": "#f39c12",  # Warning yellow
    "medium": "#e67e22",  # Orange
    "high": "#e74c3c",  # Red
    "critical": "#c0392b",  # Dark red
}

# Status indicator colors
STATUS_COLORS = {
    "valid": "#27ae60",  # Green
    "invalid": "#e74c3c",  # Red
    "warning": "#f39c12",  # Yellow
}


def _check_plotly() -> None:
    """Check if Plotly is available, raise ImportError if not."""
    if not PLOTLY_AVAILABLE:
        raise ImportError("Plotly is required for visualization. Install with: pip install plotly")


def get_severity_level(severity: float) -> str:
    """
    Convert numeric severity (0-1) to categorical level.

    Args:
        severity: Severity value between 0 and 1.

    Returns:
        Severity level string: 'low', 'medium', 'high', or 'critical'.
    """
    if severity < 0.25:
        return "low"
    elif severity < 0.5:
        return "medium"
    elif severity < 0.75:
        return "high"
    else:
        return "critical"


def get_severity_color(severity: float) -> str:
    """
    Get color for a severity level.

    Args:
        severity: Severity value between 0 and 1.

    Returns:
        Hex color string.
    """
    return SEVERITY_COLORS[get_severity_level(severity)]


def render_status_indicator(
    status: ConstraintStatus,
    width: int = 200,
    height: int = 200,
) -> Any:
    """
    Render a status indicator (checkmark or X) as a Plotly figure.

    Args:
        status: Current constraint status.
        width: Figure width in pixels.
        height: Figure height in pixels.

    Returns:
        Plotly Figure object.
    """
    _check_plotly()

    fig = go.Figure()

    # Determine status
    if status.is_valid and len(status.violations) == 0:
        # All good - green checkmark
        color = STATUS_COLORS["valid"]
        symbol = "✓"
        label = "VALID"
    elif status.is_valid:
        # Warnings but no errors
        color = STATUS_COLORS["warning"]
        symbol = "⚠"
        label = "WARNING"
    else:
        # Errors present
        color = STATUS_COLORS["invalid"]
        symbol = "✗"
        label = "INVALID"

    # Add status symbol
    fig.add_annotation(
        x=0.5,
        y=0.6,
        text=symbol,
        font={"size": 72, "color": color},
        showarrow=False,
        xref="paper",
        yref="paper",
    )

    # Add status label
    fig.add_annotation(
        x=0.5,
        y=0.2,
        text=label,
        font={"size": 24, "color": color, "family": "Arial Black"},
        showarrow=False,
        xref="paper",
        yref="paper",
    )

    # Configure layout
    fig.update_layout(
        width=width,
        height=height,
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis={"visible": False},
        yaxis={"visible": False},
    )

    return fig


def render_violation_summary_bar(
    status: ConstraintStatus,
    width: int = 400,
    height: int = 250,
    title: str = "Violations by Category",
) -> Any:
    """
    Render a bar chart showing violation counts by category.

    Args:
        status: Current constraint status.
        width: Figure width in pixels.
        height: Figure height in pixels.
        title: Chart title.

    Returns:
        Plotly Figure object.
    """
    _check_plotly()

    # Category data
    categories = ["Overlap", "Boundary", "Clearance", "Thermal", "DRC"]
    counts = [
        status.overlap_count,
        status.boundary_violations,
        status.clearance_violations,
        status.thermal_warnings,
        status.drc_errors,
    ]
    colors = [
        VIOLATION_COLORS[ViolationType.OVERLAP],
        VIOLATION_COLORS[ViolationType.BOUNDARY],
        VIOLATION_COLORS[ViolationType.CLEARANCE],
        VIOLATION_COLORS[ViolationType.THERMAL],
        VIOLATION_COLORS[ViolationType.DRC],
    ]

    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            x=categories,
            y=counts,
            marker_color=colors,
            text=counts,
            textposition="outside",
            hovertemplate="<b>%{x}</b><br>Count: %{y}<extra></extra>",
        )
    )

    fig.update_layout(
        title={"text": title, "x": 0.5},
        width=width,
        height=height,
        margin={"l": 40, "r": 20, "t": 50, "b": 40},
        yaxis={"title": "Count", "rangemode": "tozero"},
        xaxis={"title": ""},
        showlegend=False,
    )

    return fig


def render_violation_list(
    violations: list[Violation],
    max_items: int = 10,
    width: int = 500,
    height: int = 300,
    title: str = "Active Violations",
) -> Any:
    """
    Render a table of individual violations.

    Args:
        violations: List of Violation objects.
        max_items: Maximum number of items to show.
        width: Figure width in pixels.
        height: Figure height in pixels.
        title: Table title.

    Returns:
        Plotly Figure object with table.
    """
    _check_plotly()

    # Sort by severity (highest first) and limit
    sorted_violations = sorted(violations, key=lambda v: v.severity, reverse=True)
    display_violations = sorted_violations[:max_items]

    # Prepare table data
    types = []
    components = []
    messages = []
    severities = []
    colors = []

    for v in display_violations:
        types.append(v.violation_type.value.upper())
        components.append(", ".join(v.component_refs) if v.component_refs else "-")
        messages.append(v.message[:50] + "..." if len(v.message) > 50 else v.message)
        severities.append(f"{v.severity:.2f}")
        colors.append(get_severity_color(v.severity))

    # Handle empty violations
    if not display_violations:
        types = ["-"]
        components = ["-"]
        messages = ["No violations"]
        severities = ["-"]
        colors = [STATUS_COLORS["valid"]]

    fig = go.Figure()

    fig.add_trace(
        go.Table(
            header={
                "values": ["Type", "Components", "Message", "Severity"],
                "fill_color": "#2c3e50",
                "font": {"color": "white", "size": 12},
                "align": "left",
            },
            cells={
                "values": [types, components, messages, severities],
                "fill_color": [
                    ["white"] * len(types),  # Type column
                    ["white"] * len(types),  # Components column
                    ["white"] * len(types),  # Message column
                    colors,  # Severity column with colors
                ],
                "font": {"color": "black", "size": 11},
                "align": "left",
                "height": 25,
            },
        )
    )

    # Add "more items" note if truncated
    subtitle = ""
    if len(violations) > max_items:
        subtitle = f"<br><sub>(showing {max_items} of {len(violations)} violations)</sub>"

    fig.update_layout(
        title={"text": f"{title}{subtitle}", "x": 0.5},
        width=width,
        height=height,
        margin={"l": 10, "r": 10, "t": 50, "b": 10},
    )

    return fig


def render_constraint_status(
    status: ConstraintStatus,
    width: int = 800,
    height: int = 500,
    title: str = "Constraint Status",
    show_indicator: bool = True,
    show_summary: bool = True,
    show_list: bool = True,
) -> Any:
    """
    Render complete constraint status panel.

    This is the main rendering function that combines:
    - Status indicator (valid/invalid)
    - Summary bar chart by category
    - Detailed violation list

    Args:
        status: Current constraint status.
        width: Figure width in pixels.
        height: Figure height in pixels.
        title: Panel title.
        show_indicator: Whether to show status indicator.
        show_summary: Whether to show summary bar chart.
        show_list: Whether to show violation list.

    Returns:
        Plotly Figure object.
    """
    _check_plotly()

    # Determine layout based on what's shown
    n_panels = sum([show_indicator, show_summary, show_list])

    if n_panels == 0:
        # Empty figure
        fig = go.Figure()
        fig.update_layout(width=width, height=height)
        return fig

    # Create subplots
    specs: list[list[dict[str, Any] | None]]
    if n_panels == 1:
        specs = [[{"type": "xy" if show_summary else "table"}]]
        rows, cols = 1, 1
    elif n_panels == 2:
        if show_indicator and show_summary:
            specs = [[{"type": "xy"}, {"type": "xy"}]]
            rows, cols = 1, 2
        elif show_indicator and show_list:
            specs = [[{"type": "xy"}, {"type": "table"}]]
            rows, cols = 1, 2
        else:  # show_summary and show_list
            specs = [[{"type": "xy"}], [{"type": "table"}]]
            rows, cols = 2, 1
    else:  # n_panels == 3
        specs = [[{"type": "xy"}, {"type": "xy"}], [{"type": "table", "colspan": 2}, None]]
        rows, cols = 2, 2

    # Column widths depend on layout
    if cols == 2 and rows == 1:
        column_widths = [0.3, 0.7] if show_indicator else [0.5, 0.5]
    elif cols == 2:
        column_widths = [0.3, 0.7]
    else:
        column_widths = None

    fig = make_subplots(
        rows=rows,
        cols=cols,
        specs=specs,
        column_widths=column_widths,
        vertical_spacing=0.15,
        horizontal_spacing=0.1,
    )

    current_row, current_col = 1, 1

    # Add status indicator
    if show_indicator:
        # Determine status
        if status.is_valid and len(status.violations) == 0:
            color = STATUS_COLORS["valid"]
            symbol = "✓"
            label = "VALID"
        elif status.is_valid:
            color = STATUS_COLORS["warning"]
            symbol = "⚠"
            label = "WARNING"
        else:
            color = STATUS_COLORS["invalid"]
            symbol = "✗"
            label = "INVALID"

        # Add as annotation (simpler than trace for single symbol)
        # Note: Plotly uses "x domain" for first subplot, "x2 domain" for second, etc.
        xref = "x domain" if current_col == 1 else f"x{current_col} domain"
        yref = "y domain" if current_row == 1 else f"y{current_row} domain"
        fig.add_annotation(
            x=0.5,
            y=0.7,
            text=f"<b style='font-size:48px'>{symbol}</b>",
            font={"size": 48, "color": color},
            showarrow=False,
            xref=xref,
            yref=yref,
        )
        fig.add_annotation(
            x=0.5,
            y=0.3,
            text=f"<b>{label}</b>",
            font={"size": 20, "color": color},
            showarrow=False,
            xref=xref,
            yref=yref,
        )

        if cols == 2:
            current_col = 2
        else:
            current_row += 1

    # Add summary bar chart
    if show_summary:
        categories = ["Overlap", "Boundary", "Clearance", "Thermal", "DRC"]
        counts = [
            status.overlap_count,
            status.boundary_violations,
            status.clearance_violations,
            status.thermal_warnings,
            status.drc_errors,
        ]
        colors = [
            VIOLATION_COLORS[ViolationType.OVERLAP],
            VIOLATION_COLORS[ViolationType.BOUNDARY],
            VIOLATION_COLORS[ViolationType.CLEARANCE],
            VIOLATION_COLORS[ViolationType.THERMAL],
            VIOLATION_COLORS[ViolationType.DRC],
        ]

        fig.add_trace(
            go.Bar(
                x=categories,
                y=counts,
                marker_color=colors,
                text=counts,
                textposition="outside",
                hovertemplate="<b>%{x}</b><br>Count: %{y}<extra></extra>",
                showlegend=False,
            ),
            row=current_row,
            col=current_col,
        )

        if rows == 2 and current_row == 1:
            current_row = 2
            current_col = 1

    # Add violation list
    if show_list:
        violations = list(status.violations)
        sorted_violations = sorted(violations, key=lambda v: v.severity, reverse=True)
        display_violations = sorted_violations[:10]

        # Prepare table data
        types = []
        components = []
        messages = []
        sev_strs = []
        sev_colors = []

        for v in display_violations:
            types.append(v.violation_type.value.upper())
            components.append(", ".join(v.component_refs) if v.component_refs else "-")
            messages.append(v.message[:40] + "..." if len(v.message) > 40 else v.message)
            sev_strs.append(f"{v.severity:.2f}")
            sev_colors.append(get_severity_color(v.severity))

        if not display_violations:
            types = ["-"]
            components = ["-"]
            messages = ["No violations"]
            sev_strs = ["-"]
            sev_colors = [STATUS_COLORS["valid"]]

        fig.add_trace(
            go.Table(
                header={
                    "values": ["Type", "Components", "Message", "Severity"],
                    "fill_color": "#2c3e50",
                    "font": {"color": "white", "size": 11},
                    "align": "left",
                },
                cells={
                    "values": [types, components, messages, sev_strs],
                    "fill_color": [
                        ["white"] * len(types),
                        ["white"] * len(types),
                        ["white"] * len(types),
                        sev_colors,
                    ],
                    "font": {"color": "black", "size": 10},
                    "align": "left",
                    "height": 22,
                },
            ),
            row=current_row,
            col=1,
        )

    # Configure layout
    fig.update_layout(
        title={"text": title, "x": 0.5, "font": {"size": 16}},
        width=width,
        height=height,
        margin={"l": 20, "r": 20, "t": 60, "b": 20},
        showlegend=False,
    )

    # Hide axes for indicator panel
    if show_indicator:
        fig.update_xaxes(visible=False, row=1, col=1)
        fig.update_yaxes(visible=False, row=1, col=1)

    return fig


def get_affected_component_refs(status: ConstraintStatus) -> list[str]:
    """
    Get list of component references affected by violations.

    Useful for highlighting components in the board view.

    Args:
        status: Current constraint status.

    Returns:
        List of unique component reference designators.
    """
    refs: set[str] = set()
    for violation in status.violations:
        refs.update(violation.component_refs)
    return sorted(refs)


def get_violations_by_component(
    status: ConstraintStatus,
) -> dict[str, list[Violation]]:
    """
    Group violations by component reference.

    Args:
        status: Current constraint status.

    Returns:
        Dict mapping component ref to list of violations.
    """
    by_component: dict[str, list[Violation]] = {}
    for violation in status.violations:
        for ref in violation.component_refs:
            if ref not in by_component:
                by_component[ref] = []
            by_component[ref].append(violation)
    return by_component


def get_violations_by_type(
    status: ConstraintStatus,
) -> dict[ViolationType, list[Violation]]:
    """
    Group violations by type.

    Args:
        status: Current constraint status.

    Returns:
        Dict mapping violation type to list of violations.
    """
    by_type: dict[ViolationType, list[Violation]] = {}
    for violation in status.violations:
        vtype = violation.violation_type
        if vtype not in by_type:
            by_type[vtype] = []
        by_type[vtype].append(violation)
    return by_type


def constraint_status_to_html(
    status: ConstraintStatus,
    width: int = 800,
    height: int = 500,
    full_html: bool = False,
) -> str:
    """
    Render constraint status to HTML string.

    Args:
        status: Current constraint status.
        width: Figure width in pixels.
        height: Figure height in pixels.
        full_html: If True, include full HTML document tags.

    Returns:
        HTML string.
    """
    _check_plotly()
    fig = render_constraint_status(status, width=width, height=height)
    return fig.to_html(full_html=full_html, include_plotlyjs="cdn")


def constraint_status_to_json(status: ConstraintStatus) -> str:
    """
    Convert constraint status to JSON for WebSocket transmission.

    Includes both raw data and pre-computed summaries for the frontend.

    Args:
        status: Current constraint status.

    Returns:
        JSON string.
    """
    data = status.to_dict()

    # Add additional computed fields for frontend convenience
    data["affected_components"] = get_affected_component_refs(status)
    data["violations_by_type"] = {
        vtype.value: len(violations) for vtype, violations in get_violations_by_type(status).items()
    }

    return json.dumps(data)
