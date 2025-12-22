"""
Loss curve plotting with Plotly.

This module provides functions to render training loss curves using Plotly,
including total loss, per-term breakdown, and curriculum phase boundaries.
"""

from __future__ import annotations

from typing import Any

# Plotly is an optional dependency for testing without full install
try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    go = None  # type: ignore
    make_subplots = None  # type: ignore

from temper_placer.visualization.model import LossHistory

# Color palette for loss terms
LOSS_TERM_COLORS: dict[str, str] = {
    "overlap": "#F44336",  # Red
    "boundary": "#2196F3",  # Blue
    "wirelength": "#4CAF50",  # Green
    "clearance": "#FF9800",  # Orange
    "thermal": "#9C27B0",  # Purple
    "zone": "#00BCD4",  # Cyan
    "drc": "#E91E63",  # Pink
    "spread": "#795548",  # Brown
    "loop_area": "#607D8B",  # Blue Gray
    "congestion": "#FFEB3B",  # Yellow
    "total": "#000000",  # Black
}

# Default color for unknown terms
DEFAULT_COLOR = "#9E9E9E"


def check_plotly_available() -> None:
    """Raise ImportError if Plotly is not available."""
    if not PLOTLY_AVAILABLE:
        raise ImportError(
            "Plotly is required for visualization. Install with: pip install plotly>=5.18.0"
        )


def get_term_color(term_name: str) -> str:
    """Get color for a loss term."""
    return LOSS_TERM_COLORS.get(term_name.lower(), DEFAULT_COLOR)


def render_loss_curves(
    history: LossHistory,
    title: str | None = None,
    show_breakdown: bool = True,
    show_phases: bool = True,
    log_scale: bool = False,
    width: int = 800,
    height: int = 400,
) -> go.Figure:
    """
    Render loss curves as a Plotly figure.

    Args:
        history: LossHistory with training data.
        title: Optional title for the figure.
        show_breakdown: Whether to show per-term breakdown.
        show_phases: Whether to show phase boundary lines.
        log_scale: Whether to use log scale for y-axis.
        width: Figure width in pixels.
        height: Figure height in pixels.

    Returns:
        Plotly Figure object.

    Raises:
        ImportError: If Plotly is not installed.
    """
    check_plotly_available()

    fig = go.Figure()

    if not history.data_points:
        # Empty figure with message
        fig.add_annotation(
            text="No training data yet",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font={"size": 16, "color": "#666666"},
        )
        fig.update_layout(
            title=title or "Training Loss",
            width=width,
            height=height,
        )
        return fig

    epochs = history.epochs
    losses = history.losses

    # Add total loss curve
    fig.add_trace(
        go.Scatter(
            x=epochs,
            y=losses,
            mode="lines",
            name="Total Loss",
            line={"color": LOSS_TERM_COLORS["total"], "width": 2},
            hovertemplate="Epoch: %{x}<br>Loss: %{y:.4f}<extra></extra>",
        )
    )

    # Add breakdown curves
    if show_breakdown:
        terms = history.loss_terms
        for term in terms:
            term_history = history.get_term_history(term)
            fig.add_trace(
                go.Scatter(
                    x=epochs,
                    y=term_history,
                    mode="lines",
                    name=term.replace("_", " ").title(),
                    line={"color": get_term_color(term), "width": 1.5, "dash": "dot"},
                    hovertemplate=f"{term}: " + "%{y:.4f}<extra></extra>",
                    visible="legendonly",  # Hidden by default, click legend to show
                )
            )

    # Add phase boundaries
    if show_phases and history.phase_boundaries:
        for i, boundary in enumerate(history.phase_boundaries):
            phase_name = (
                history.phase_names[i] if i < len(history.phase_names) else f"Phase {i + 1}"
            )
            fig.add_vline(
                x=boundary,
                line={"color": "rgba(128,128,128,0.5)", "width": 1, "dash": "dash"},
                annotation={
                    "text": phase_name,
                    "textangle": -90,
                    "font": {"size": 10, "color": "#666666"},
                },
            )

    # Configure layout
    fig.update_layout(
        title={
            "text": title or "Training Loss",
            "x": 0.5,
            "xanchor": "center",
        },
        xaxis={
            "title": "Epoch",
            "showgrid": True,
            "gridcolor": "rgba(128,128,128,0.2)",
        },
        yaxis={
            "title": "Loss",
            "type": "log" if log_scale else "linear",
            "showgrid": True,
            "gridcolor": "rgba(128,128,128,0.2)",
        },
        width=width,
        height=height,
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
        },
        hovermode="x unified",
        plot_bgcolor="white",
        paper_bgcolor="#f5f5f5",
        margin={"l": 60, "r": 20, "t": 80, "b": 60},
    )

    return fig


def render_loss_breakdown_bar(
    history: LossHistory,
    epoch: int | None = None,
    title: str | None = None,
    width: int = 400,
    height: int = 300,
) -> go.Figure:
    """
    Render a bar chart showing loss breakdown at a specific epoch.

    Args:
        history: LossHistory with training data.
        epoch: Epoch to show (default: latest).
        title: Optional title for the figure.
        width: Figure width in pixels.
        height: Figure height in pixels.

    Returns:
        Plotly Figure object.
    """
    check_plotly_available()

    fig = go.Figure()

    if not history.data_points:
        fig.add_annotation(
            text="No data",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
        )
        return fig

    # Get data point for specified epoch
    if epoch is None:
        data_point = history.data_points[-1]
    else:
        matching = [p for p in history.data_points if p.epoch == epoch]
        data_point = matching[0] if matching else history.data_points[-1]

    # Extract breakdown
    breakdown = data_point.breakdown
    if not breakdown:
        fig.add_annotation(
            text="No breakdown data",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
        )
        return fig

    terms = list(breakdown.keys())
    values = list(breakdown.values())
    colors = [get_term_color(t) for t in terms]

    fig.add_trace(
        go.Bar(
            x=terms,
            y=values,
            marker_color=colors,
            text=[f"{v:.3f}" for v in values],
            textposition="auto",
            hovertemplate="%{x}: %{y:.4f}<extra></extra>",
        )
    )

    fig.update_layout(
        title={
            "text": title or f"Loss Breakdown (Epoch {data_point.epoch})",
            "x": 0.5,
            "xanchor": "center",
        },
        xaxis={"title": "Loss Term"},
        yaxis={"title": "Value"},
        width=width,
        height=height,
        showlegend=False,
        plot_bgcolor="white",
        paper_bgcolor="#f5f5f5",
    )

    return fig


def render_loss_heatmap(
    history: LossHistory,
    title: str | None = None,
    width: int = 800,
    height: int = 400,
) -> go.Figure:
    """
    Render a heatmap showing loss term evolution over time.

    Args:
        history: LossHistory with training data.
        title: Optional title for the figure.
        width: Figure width in pixels.
        height: Figure height in pixels.

    Returns:
        Plotly Figure object.
    """
    check_plotly_available()

    fig = go.Figure()

    if not history.data_points or not history.loss_terms:
        fig.add_annotation(
            text="No breakdown data",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
        )
        return fig

    # Build matrix
    terms = history.loss_terms
    epochs = history.epochs
    z_data = []

    for term in terms:
        term_values = history.get_term_history(term)
        # Normalize to [0, 1] for better visualization
        max_val = max(term_values) if term_values else 1.0
        if max_val > 0:
            normalized = [v / max_val for v in term_values]
        else:
            normalized = term_values
        z_data.append(normalized)

    fig.add_trace(
        go.Heatmap(
            z=z_data,
            x=epochs,
            y=[t.replace("_", " ").title() for t in terms],
            colorscale="RdYlGn_r",  # Red (high) to Green (low)
            hovertemplate="Epoch: %{x}<br>%{y}: %{z:.3f}<extra></extra>",
        )
    )

    fig.update_layout(
        title={
            "text": title or "Loss Term Evolution (Normalized)",
            "x": 0.5,
            "xanchor": "center",
        },
        xaxis={"title": "Epoch"},
        yaxis={"title": "Loss Term"},
        width=width,
        height=height,
        plot_bgcolor="white",
        paper_bgcolor="#f5f5f5",
    )

    return fig


def render_training_dashboard(
    history: LossHistory,
    title: str | None = None,
    width: int = 1000,
    height: int = 900,
) -> go.Figure:
    """
    Render a comprehensive training dashboard with multiple views.

    Args:
        history: LossHistory with training data.
        title: Optional title for the figure.
        width: Figure width in pixels.
        height: Figure height in pixels.

    Returns:
        Plotly Figure with multiple subplots.
    """
    check_plotly_available()

    fig = make_subplots(
        rows=3,
        cols=2,
        subplot_titles=(
            "Training Loss",
            "Loss Breakdown (Latest)",
            "Loss Term Evolution",
            "Convergence Confidence",
            "Learning Rate / Temperature",
            "Relative Improvement (EMA)",
        ),
        specs=[
            [{"type": "scatter"}, {"type": "bar"}],
            [{"type": "heatmap"}, {"type": "scatter"}],
            [{"type": "scatter"}, {"type": "scatter"}],
        ],
        vertical_spacing=0.1,
        horizontal_spacing=0.1,
    )

    if not history.data_points:
        fig.add_annotation(
            text="No training data yet",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font={"size": 20},
        )
        fig.update_layout(width=width, height=height)
        return fig

    epochs = history.epochs
    losses = history.losses

    # 1. Loss curve (top-left)
    fig.add_trace(
        go.Scatter(
            x=epochs,
            y=losses,
            mode="lines",
            name="Total Loss",
            line={"color": "#000000", "width": 2},
            showlegend=False,
        ),
        row=1,
        col=1,
    )

    # Add term breakdown to loss curve
    for term in history.loss_terms:
        term_history = history.get_term_history(term)
        fig.add_trace(
            go.Scatter(
                x=epochs,
                y=term_history,
                mode="lines",
                name=term,
                line={"color": get_term_color(term), "width": 1, "dash": "dot"},
                showlegend=False,
                visible="legendonly",
            ),
            row=1,
            col=1,
        )

    # 2. Bar chart (top-right)
    latest = history.data_points[-1]
    if latest.breakdown:
        terms = list(latest.breakdown.keys())
        values = list(latest.breakdown.values())
        colors = [get_term_color(t) for t in terms]

        fig.add_trace(
            go.Bar(
                x=terms,
                y=values,
                marker_color=colors,
                showlegend=False,
            ),
            row=1,
            col=2,
        )

    # 3. Heatmap (middle-left)
    if history.loss_terms:
        z_data = []
        for term in history.loss_terms:
            term_values = history.get_term_history(term)
            max_val = max(term_values) if term_values else 1.0
            if max_val > 0:
                normalized = [v / max_val for v in term_values]
            else:
                normalized = term_values
            z_data.append(normalized)

        fig.add_trace(
            go.Heatmap(
                z=z_data,
                x=epochs,
                y=history.loss_terms,
                colorscale="RdYlGn_r",
                showscale=False,
            ),
            row=2,
            col=1,
        )

    # 4. Convergence Confidence (middle-right)
    conf_data = [p.convergence_confidence for p in history.data_points if p.convergence_confidence is not None]
    if conf_data:
        conf_epochs = [p.epoch for p in history.data_points if p.convergence_confidence is not None]
        fig.add_trace(
            go.Scatter(
                x=conf_epochs,
                y=conf_data,
                mode="lines",
                name="Confidence",
                line={"color": "#4CAF50", "width": 2},
                showlegend=False,
            ),
            row=2,
            col=2,
        )
        fig.update_yaxes(range=[0, 1.05], row=2, col=2)

    # 5. Learning rate / temperature (bottom-left)
    lr_data = [p.learning_rate for p in history.data_points if p.learning_rate]
    temp_data = [p.temperature for p in history.data_points if p.temperature]

    if lr_data:
        lr_epochs = [p.epoch for p in history.data_points if p.learning_rate is not None]
        fig.add_trace(
            go.Scatter(
                x=lr_epochs,
                y=lr_data,
                mode="lines",
                name="Learning Rate",
                line={"color": "#2196F3"},
                showlegend=False,
            ),
            row=3,
            col=1,
        )

    if temp_data:
        temp_epochs = [p.epoch for p in history.data_points if p.temperature is not None]
        fig.add_trace(
            go.Scatter(
                x=temp_epochs,
                y=temp_data,
                mode="lines",
                name="Temperature",
                line={"color": "#F44336", "dash": "dash"},
                yaxis="y8",  # Note: subplot numbering might be different now
                showlegend=False,
            ),
            row=3,
            col=1,
        )

    # 6. Relative Improvement EMA (bottom-right)
    imp_data = [p.improvement_ema for p in history.data_points if p.improvement_ema is not None]
    if imp_data:
        imp_epochs = [p.epoch for p in history.data_points if p.improvement_ema is not None]
        fig.add_trace(
            go.Scatter(
                x=imp_epochs,
                y=imp_data,
                mode="lines",
                name="Improvement EMA",
                line={"color": "#FF9800"},
                showlegend=False,
            ),
            row=3,
            col=2,
        )
        fig.update_yaxes(type="log", row=3, col=2)

    # Update layout
    fig.update_layout(
        title={
            "text": title or "Training Dashboard",
            "x": 0.5,
            "xanchor": "center",
        },
        width=width,
        height=height,
        showlegend=False,
        plot_bgcolor="white",
        paper_bgcolor="#f5f5f5",
    )

    return fig


def loss_history_to_html(
    history: LossHistory,
    output_path: str | None = None,
    include_plotlyjs: bool = True,
    dashboard: bool = False,
    **kwargs: Any,
) -> str:
    """
    Render loss history to HTML.

    Args:
        history: LossHistory to render.
        output_path: Optional path to write HTML file.
        include_plotlyjs: Whether to include Plotly.js in HTML.
        dashboard: Whether to render full dashboard.
        **kwargs: Additional arguments passed to render function.

    Returns:
        HTML string.
    """
    check_plotly_available()

    if dashboard:
        fig = render_training_dashboard(history, **kwargs)
    else:
        fig = render_loss_curves(history, **kwargs)

    html = fig.to_html(include_plotlyjs=include_plotlyjs, full_html=True)

    if output_path:
        with open(output_path, "w") as f:
            f.write(html)

    return html


def loss_history_to_json(
    history: LossHistory,
    dashboard: bool = False,
    **kwargs: Any,
) -> str:
    """
    Render loss history to Plotly JSON.

    Args:
        history: LossHistory to render.
        dashboard: Whether to render full dashboard.
        **kwargs: Additional arguments passed to render function.

    Returns:
        JSON string of the Plotly figure.
    """
    check_plotly_available()

    if dashboard:
        fig = render_training_dashboard(history, **kwargs)
    else:
        fig = render_loss_curves(history, **kwargs)

    return fig.to_json()
