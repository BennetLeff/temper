"""
Visualization module for temper-placer.

This module provides browser-based live visualization during optimization:
- Board view: component rectangles, zones, keep-out areas
- Loss curves: total and per-term losses over iterations
- Constraint status: which constraints are satisfied/violated
- Animation: placement evolution over training

Implementation:
- Plotly for rendering (interactive zoom, hover info)
- WebSocket server for real-time updates
- HTML dashboard served locally

The visualizer runs in a separate thread/process and receives updates
from the optimizer via a queue or WebSocket connection.

Usage:
    # In optimizer
    vis = Visualizer(board, netlist, port=8080)
    vis.start()

    for step in training_loop:
        vis.update(state, losses, step)

    vis.stop()
"""

# Data models for visualization state
# Board rendering (requires Plotly)
from temper_placer.visualization.board_renderer import (
    PLOTLY_AVAILABLE,
    STATUS_COLORS,
    ZONE_COLORS,
    board_to_html,
    board_to_json,
    render_board,
    render_board_comparison,
    render_board_with_violations,
)

# LiveVisualizer integration for training loop
from temper_placer.visualization.live import (
    LiveVisualizer,
    LiveVisualizerConfig,
    create_visualizer,
)

# Loss curve plotting (requires Plotly)
from temper_placer.visualization.loss_plots import (
    LOSS_TERM_COLORS,
    loss_history_to_html,
    loss_history_to_json,
    render_loss_breakdown_bar,
    render_loss_curves,
    render_loss_heatmap,
    render_training_dashboard,
)
from temper_placer.visualization.model import (
    BoardView,
    # Enums
    ComponentStatus,
    # Component and board views
    ComponentView,
    ConstraintStatus,
    # Loss tracking
    LossDataPoint,
    LossHistory,
    # Geometry primitives
    Point,
    Rectangle,
    # Constraint tracking
    Violation,
    ViolationType,
    # Top-level state
    VisualizationState,
    ZoneView,
    create_board_view_from_state,
    # Factory functions
    create_component_view,
    create_loss_data_point_from_metrics,
)

# HTML report generation
from temper_placer.visualization.report import (
    ReportConfig,
    ValidationResults,
    generate_report,
)

# WebSocket server for live updates (requires websockets)
from temper_placer.visualization.server import (
    WEBSOCKETS_AVAILABLE,
    LiveServer,
    MessageType,
    MockLiveServer,
    ServerConfig,
    ServerState,
    create_server,
)

# Constraint status panel (requires Plotly)
from temper_placer.visualization.status import (
    SEVERITY_COLORS,
    VIOLATION_COLORS,
    constraint_status_to_html,
    constraint_status_to_json,
    get_affected_component_refs,
    get_severity_color,
    get_severity_level,
    get_violations_by_component,
    get_violations_by_type,
    render_constraint_status,
    render_status_indicator,
    render_violation_list,
    render_violation_summary_bar,
)

# Coordinate validation utilities
from temper_placer.visualization.validation import (
    CoordinateDiscrepancy,
    ValidationResult,
    check_components_in_bounds,
    check_trace_connectivity,
    compute_coordinate_statistics,
    export_coordinates_csv,
    validate_coordinates,
)

__all__ = [
    # Enums
    "ComponentStatus",
    "ViolationType",
    # Geometry primitives
    "Point",
    "Rectangle",
    # Component and board views
    "ComponentView",
    "ZoneView",
    "BoardView",
    # Loss tracking
    "LossDataPoint",
    "LossHistory",
    # Constraint tracking
    "Violation",
    "ConstraintStatus",
    # Top-level state
    "VisualizationState",
    # Factory functions
    "create_component_view",
    "create_board_view_from_state",
    "create_loss_data_point_from_metrics",
    # Board rendering
    "PLOTLY_AVAILABLE",
    "render_board",
    "render_board_with_violations",
    "render_board_comparison",
    "board_to_html",
    "board_to_json",
    "STATUS_COLORS",
    "ZONE_COLORS",
    # Loss plotting
    "render_loss_curves",
    "render_loss_breakdown_bar",
    "render_loss_heatmap",
    "render_training_dashboard",
    "loss_history_to_html",
    "loss_history_to_json",
    "LOSS_TERM_COLORS",
    # Constraint status panel
    "render_status_indicator",
    "render_violation_summary_bar",
    "render_violation_list",
    "render_constraint_status",
    "get_affected_component_refs",
    "get_violations_by_component",
    "get_violations_by_type",
    "constraint_status_to_html",
    "constraint_status_to_json",
    "get_severity_level",
    "get_severity_color",
    "VIOLATION_COLORS",
    "SEVERITY_COLORS",
    # WebSocket server
    "WEBSOCKETS_AVAILABLE",
    "LiveServer",
    "MockLiveServer",
    "ServerConfig",
    "ServerState",
    "MessageType",
    "create_server",
    # LiveVisualizer
    "LiveVisualizer",
    "LiveVisualizerConfig",
    "create_visualizer",
    # HTML report generation
    "generate_report",
    "ReportConfig",
    "ValidationResults",
    # Coordinate validation
    "CoordinateDiscrepancy",
    "ValidationResult",
    "validate_coordinates",
    "export_coordinates_csv",
    "check_components_in_bounds",
    "check_trace_connectivity",
    "compute_coordinate_statistics",
]
