"""
HTML report generation for placement optimization results.

This module generates standalone HTML reports containing:
- Final placement visualization
- Loss curve plots
- Constraint satisfaction summary
- Component placement table
- Validation results (DRC, SPICE)

Usage:
    from temper_placer.visualization import generate_report

    report = generate_report(
        board_view=board_view,
        loss_history=loss_history,
        constraints=constraints,
        output_path="placement_report.html",
    )
"""

from __future__ import annotations

import html
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .model import (
    BoardView,
    ComponentStatus,
    ConstraintStatus,
    LossHistory,
)

if TYPE_CHECKING:
    from temper_placer.core.loop import LoopCollection

logger = logging.getLogger(__name__)

# Check for optional dependencies
import importlib.util  # noqa: E402

PLOTLY_AVAILABLE = importlib.util.find_spec("plotly") is not None


@dataclass
class ReportConfig:
    """Configuration for report generation."""

    # General settings
    title: str = "Placement Optimization Report"
    include_timestamp: bool = True

    # Chart settings
    board_chart_height: int = 600
    loss_chart_height: int = 400

    # Table settings
    max_components_in_table: int = 100  # Limit for large designs
    show_all_loss_terms: bool = True

    # Content sections
    include_board_view: bool = True
    include_loss_curves: bool = True
    include_constraint_summary: bool = True
    include_component_table: bool = True
    include_validation_results: bool = True


@dataclass
class ValidationResults:
    """Container for validation results to include in report."""

    drc_passed: bool | None = None
    drc_errors: list[str] | None = None
    drc_warnings: list[str] | None = None

    spice_passed: bool | None = None
    spice_errors: list[str] | None = None
    spice_warnings: list[str] | None = None

    def __post_init__(self):
        if self.drc_errors is None:
            self.drc_errors = []
        if self.drc_warnings is None:
            self.drc_warnings = []
        if self.spice_errors is None:
            self.spice_errors = []
        if self.spice_warnings is None:
            self.spice_warnings = []


def generate_report(
    board_view: BoardView,
    loss_history: LossHistory | None = None,
    constraints: ConstraintStatus | None = None,
    validation: ValidationResults | None = None,
    loops: LoopCollection | None = None,
    config: ReportConfig | None = None,
    output_path: str | None = None,
) -> str:
    """
    Generate an HTML report for placement optimization results.

    Args:
        board_view: Final board state with component positions.
        loss_history: Optional loss history for plotting curves.
        constraints: Optional constraint status summary.
        validation: Optional validation results (DRC, SPICE).
        loops: Optional LoopCollection for loop analysis.
        config: Optional report configuration.
        output_path: Optional path to write HTML file. If None, returns HTML string.

    Returns:
        HTML string containing the complete report.

    Raises:
        ImportError: If Plotly is not installed.
    """
    if config is None:
        config = ReportConfig()

    # Build sections
    sections = []

    # Header
    sections.append(_generate_header(config))

    # Summary stats
    sections.append(_generate_summary_section(board_view, loss_history, constraints))

    # Board visualization
    if config.include_board_view:
        sections.append(_generate_board_section(board_view, config, loops))

    # Loss curves
    if config.include_loss_curves and loss_history:
        sections.append(_generate_loss_section(loss_history, config))

    # Loop Analysis section
    if loops:
        from .loop_viz import render_loop_summary_table
        sections.append(render_loop_summary_table(loops, board_view))

    # Constraint summary
    if config.include_constraint_summary and constraints:
        sections.append(_generate_constraint_section(constraints))

    # Component table
    if config.include_component_table:
        sections.append(_generate_component_table(board_view, config))

    # Validation results
    if config.include_validation_results and validation:
        sections.append(_generate_validation_section(validation))

    # Footer
    sections.append(_generate_footer())

    # Combine into full HTML
    html_content = _wrap_in_html_document(sections, config)

    # Write to file if path provided
    if output_path:
        path = Path(output_path)
        path.write_text(html_content)
        logger.info(f"Report written to {path}")

    return html_content


def _generate_header(config: ReportConfig) -> str:
    """Generate the report header section."""
    timestamp = ""
    if config.include_timestamp:
        timestamp = (
            f'<p class="timestamp">Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>'
        )

    return f"""
    <header>
        <h1>{html.escape(config.title)}</h1>
        {timestamp}
    </header>
    """


def _generate_summary_section(
    board_view: BoardView,
    loss_history: LossHistory | None,
    constraints: ConstraintStatus | None,
) -> str:
    """Generate the summary statistics section."""
    n_components = len(board_view.components)
    board_area = board_view.width * board_view.height

    # Calculate component coverage
    component_area = sum(c.width * c.height for c in board_view.components)
    coverage_pct = (component_area / board_area * 100) if board_area > 0 else 0

    # Final loss
    final_loss = "N/A"
    epochs = "N/A"
    if loss_history and loss_history.data_points:
        final_loss = f"{loss_history.data_points[-1].total_loss:.4f}"
        epochs = str(len(loss_history.data_points))

    # Constraint status
    status_class = "status-ok"
    status_text = "Valid"
    if constraints:
        if constraints.overlap_count > 0 or constraints.boundary_violations > 0:
            status_class = "status-error"
            status_text = "Violations Found"
        elif constraints.clearance_violations > 0 or constraints.thermal_warnings > 0:
            status_class = "status-warning"
            status_text = "Warnings"

    return f"""
    <section class="summary">
        <h2>Summary</h2>
        <div class="stats-grid">
            <div class="stat-box">
                <span class="stat-value">{n_components}</span>
                <span class="stat-label">Components</span>
            </div>
            <div class="stat-box">
                <span class="stat-value">{board_view.width:.1f} x {board_view.height:.1f}</span>
                <span class="stat-label">Board Size (mm)</span>
            </div>
            <div class="stat-box">
                <span class="stat-value">{coverage_pct:.1f}%</span>
                <span class="stat-label">Area Coverage</span>
            </div>
            <div class="stat-box">
                <span class="stat-value">{final_loss}</span>
                <span class="stat-label">Final Loss</span>
            </div>
            <div class="stat-box">
                <span class="stat-value">{epochs}</span>
                <span class="stat-label">Epochs</span>
            </div>
            <div class="stat-box {status_class}">
                <span class="stat-value">{status_text}</span>
                <span class="stat-label">Placement Status</span>
            </div>
        </div>
    </section>
    """


def _generate_board_section(
    board_view: BoardView, config: ReportConfig, loops: LoopCollection | None = None
) -> str:
    """Generate the board visualization section."""
    if not PLOTLY_AVAILABLE:
        return """
        <section class="board-view">
            <h2>Board Visualization</h2>
            <p class="error">Plotly not installed. Install with: pip install plotly</p>
        </section>
        """

    # Import board renderer
    try:
        from .board_renderer import render_board

        fig = render_board(board_view, loops=loops)
        fig.update_layout(height=config.board_chart_height)
        chart_html = fig.to_html(full_html=False, include_plotlyjs="cdn")
    except Exception as e:
        logger.warning(f"Failed to render board: {e}")
        chart_html = f'<p class="error">Failed to render board: {html.escape(str(e))}</p>'

    return f"""
    <section class="board-view">
        <h2>Board Visualization</h2>
        <div class="chart-container">
            {chart_html}
        </div>
    </section>
    """


def _generate_loss_section(loss_history: LossHistory, config: ReportConfig) -> str:
    """Generate the loss curves section."""
    if not PLOTLY_AVAILABLE:
        return """
        <section class="loss-curves">
            <h2>Loss Curves</h2>
            <p class="error">Plotly not installed. Install with: pip install plotly</p>
        </section>
        """

    if not loss_history.data_points:
        return """
        <section class="loss-curves">
            <h2>Loss Curves</h2>
            <p class="info">No loss history available.</p>
        </section>
        """

    try:
        from .loss_plots import render_training_dashboard

        fig = render_training_dashboard(loss_history)
        fig.update_layout(height=config.loss_chart_height)
        chart_html = fig.to_html(full_html=False, include_plotlyjs="cdn")
    except Exception as e:
        logger.warning(f"Failed to render loss curves: {e}")
        chart_html = f'<p class="error">Failed to render loss curves: {html.escape(str(e))}</p>'

    return f"""
    <section class="loss-curves">
        <h2>Loss Curves</h2>
        <div class="chart-container">
            {chart_html}
        </div>
    </section>
    """


def _generate_constraint_section(constraints: ConstraintStatus) -> str:
    """Generate the constraint status section."""
    # Build violation list
    violations_html = ""
    if constraints.violations:
        violation_items = []
        for v in constraints.violations:
            severity_class = "severity-high" if v.severity > 0.5 else "severity-medium"
            if v.severity < 0.1:
                severity_class = "severity-low"

            components = ", ".join(v.component_refs) if v.component_refs else "N/A"
            message = v.message if v.message else f"{v.violation_type.value} violation"

            violation_items.append(f"""
                <tr class="{severity_class}">
                    <td>{v.violation_type.value.title()}</td>
                    <td>{v.severity:.3f}</td>
                    <td>{html.escape(components)}</td>
                    <td>{html.escape(message)}</td>
                </tr>
            """)

        violations_html = f"""
        <h3>Active Violations</h3>
        <table class="violations-table">
            <thead>
                <tr>
                    <th>Type</th>
                    <th>Severity</th>
                    <th>Components</th>
                    <th>Message</th>
                </tr>
            </thead>
            <tbody>
                {"".join(violation_items)}
            </tbody>
        </table>
        """
    else:
        violations_html = '<p class="success">No constraint violations detected.</p>'

    # Summary counts
    summary_items = [
        ("Overlaps", constraints.overlap_count, constraints.overlap_count > 0),
        (
            "Boundary Violations",
            constraints.boundary_violations,
            constraints.boundary_violations > 0,
        ),
        (
            "Clearance Violations",
            constraints.clearance_violations,
            constraints.clearance_violations > 0,
        ),
        ("Thermal Warnings", constraints.thermal_warnings, constraints.thermal_warnings > 0),
        ("DRC Errors", constraints.drc_errors, constraints.drc_errors > 0),
    ]

    summary_html = "".join(
        f'<li class="{"error" if is_error else "ok"}">{name}: {count}</li>'
        for name, count, is_error in summary_items
    )

    return f"""
    <section class="constraints">
        <h2>Constraint Summary</h2>
        <ul class="constraint-summary">
            {summary_html}
        </ul>
        {violations_html}
    </section>
    """


def _generate_component_table(board_view: BoardView, config: ReportConfig) -> str:
    """Generate the component placement table."""
    components = board_view.components
    n_total = len(components)

    # Limit components if needed
    if n_total > config.max_components_in_table:
        components = components[: config.max_components_in_table]
        truncation_note = f'<p class="info">Showing first {config.max_components_in_table} of {n_total} components.</p>'
    else:
        truncation_note = ""

    # Build table rows
    rows = []
    for comp in components:
        status_class = {
            ComponentStatus.OK: "status-ok",
            ComponentStatus.WARNING: "status-warning",
            ComponentStatus.ERROR: "status-error",
            ComponentStatus.FIXED: "status-fixed",
        }.get(comp.status, "")

        violations = ", ".join(comp.violations) if comp.violations else "-"

        rows.append(f"""
            <tr class="{status_class}">
                <td>{html.escape(comp.ref)}</td>
                <td>{comp.position.x:.2f}</td>
                <td>{comp.position.y:.2f}</td>
                <td>{comp.rotation:.0f}</td>
                <td>{comp.width:.2f} x {comp.height:.2f}</td>
                <td>{html.escape(comp.footprint or "-")}</td>
                <td>{comp.status.value}</td>
                <td>{html.escape(violations)}</td>
            </tr>
        """)

    return f"""
    <section class="component-table">
        <h2>Component Placements</h2>
        {truncation_note}
        <table class="placements-table">
            <thead>
                <tr>
                    <th>Ref</th>
                    <th>X (mm)</th>
                    <th>Y (mm)</th>
                    <th>Rotation</th>
                    <th>Size (mm)</th>
                    <th>Footprint</th>
                    <th>Status</th>
                    <th>Violations</th>
                </tr>
            </thead>
            <tbody>
                {"".join(rows)}
            </tbody>
        </table>
    </section>
    """


def _generate_validation_section(validation: ValidationResults) -> str:
    """Generate the validation results section."""
    sections = []

    # DRC results
    if validation.drc_passed is not None:
        drc_status = "PASSED" if validation.drc_passed else "FAILED"
        drc_class = "success" if validation.drc_passed else "error"

        drc_details = ""
        if validation.drc_errors:
            drc_details += '<h4>Errors:</h4><ul class="error-list">'
            drc_details += "".join(f"<li>{html.escape(e)}</li>" for e in validation.drc_errors)
            drc_details += "</ul>"
        if validation.drc_warnings:
            drc_details += '<h4>Warnings:</h4><ul class="warning-list">'
            drc_details += "".join(f"<li>{html.escape(w)}</li>" for w in validation.drc_warnings)
            drc_details += "</ul>"

        sections.append(f"""
            <div class="validation-result">
                <h3>DRC Validation: <span class="{drc_class}">{drc_status}</span></h3>
                {drc_details if drc_details else '<p class="info">No DRC issues found.</p>'}
            </div>
        """)

    # SPICE results
    if validation.spice_passed is not None:
        spice_status = "PASSED" if validation.spice_passed else "FAILED"
        spice_class = "success" if validation.spice_passed else "error"

        spice_details = ""
        if validation.spice_errors:
            spice_details += '<h4>Errors:</h4><ul class="error-list">'
            spice_details += "".join(f"<li>{html.escape(e)}</li>" for e in validation.spice_errors)
            spice_details += "</ul>"
        if validation.spice_warnings:
            spice_details += '<h4>Warnings:</h4><ul class="warning-list">'
            spice_details += "".join(
                f"<li>{html.escape(w)}</li>" for w in validation.spice_warnings
            )
            spice_details += "</ul>"

        sections.append(f"""
            <div class="validation-result">
                <h3>SPICE Validation: <span class="{spice_class}">{spice_status}</span></h3>
                {spice_details if spice_details else '<p class="info">No SPICE issues found.</p>'}
            </div>
        """)

    if not sections:
        return ""

    return f"""
    <section class="validation">
        <h2>Validation Results</h2>
        {"".join(sections)}
    </section>
    """


def _generate_footer() -> str:
    """Generate the report footer."""
    return """
    <footer>
        <p>Generated by temper-placer visualization module</p>
    </footer>
    """


def _wrap_in_html_document(sections: list[str], config: ReportConfig) -> str:
    """Wrap sections in a complete HTML document."""
    content = "\n".join(sections)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(config.title)}</title>
    <style>
        {_get_css_styles()}
    </style>
</head>
<body>
    <div class="container">
        {content}
    </div>
</body>
</html>
"""


def _get_css_styles() -> str:
    """Get CSS styles for the report."""
    return """
        :root {
            --color-primary: #2563eb;
            --color-success: #16a34a;
            --color-warning: #ca8a04;
            --color-error: #dc2626;
            --color-bg: #f8fafc;
            --color-card: #ffffff;
            --color-border: #e2e8f0;
            --color-text: #1e293b;
            --color-text-muted: #64748b;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background-color: var(--color-bg);
            color: var(--color-text);
            line-height: 1.6;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 2rem;
        }

        header {
            text-align: center;
            margin-bottom: 2rem;
            padding-bottom: 1rem;
            border-bottom: 2px solid var(--color-border);
        }

        header h1 {
            color: var(--color-primary);
            margin-bottom: 0.5rem;
        }

        .timestamp {
            color: var(--color-text-muted);
            font-size: 0.875rem;
        }

        section {
            background: var(--color-card);
            border-radius: 8px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }

        h2 {
            color: var(--color-text);
            margin-bottom: 1rem;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid var(--color-border);
        }

        h3 {
            color: var(--color-text);
            margin: 1rem 0 0.5rem;
        }

        h4 {
            color: var(--color-text-muted);
            font-size: 0.875rem;
            margin: 0.75rem 0 0.25rem;
        }

        /* Summary stats grid */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 1rem;
        }

        .stat-box {
            background: var(--color-bg);
            border-radius: 6px;
            padding: 1rem;
            text-align: center;
        }

        .stat-value {
            display: block;
            font-size: 1.5rem;
            font-weight: 600;
            color: var(--color-primary);
        }

        .stat-label {
            display: block;
            font-size: 0.75rem;
            color: var(--color-text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .stat-box.status-ok .stat-value { color: var(--color-success); }
        .stat-box.status-warning .stat-value { color: var(--color-warning); }
        .stat-box.status-error .stat-value { color: var(--color-error); }

        /* Charts */
        .chart-container {
            width: 100%;
            overflow-x: auto;
        }

        /* Tables */
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.875rem;
        }

        th, td {
            padding: 0.75rem;
            text-align: left;
            border-bottom: 1px solid var(--color-border);
        }

        th {
            background: var(--color-bg);
            font-weight: 600;
            color: var(--color-text-muted);
            text-transform: uppercase;
            font-size: 0.75rem;
            letter-spacing: 0.05em;
        }

        tbody tr:hover {
            background: var(--color-bg);
        }

        /* Status classes */
        .status-ok { }
        .status-warning td:first-child { border-left: 3px solid var(--color-warning); }
        .status-error td:first-child { border-left: 3px solid var(--color-error); }
        .status-fixed td:first-child { border-left: 3px solid var(--color-text-muted); }

        .severity-high td { color: var(--color-error); }
        .severity-medium td { color: var(--color-warning); }
        .severity-low td { color: var(--color-text-muted); }

        /* Constraint summary */
        .constraint-summary {
            list-style: none;
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem 1.5rem;
            margin-bottom: 1rem;
        }

        .constraint-summary li {
            padding: 0.25rem 0.75rem;
            border-radius: 4px;
            font-size: 0.875rem;
        }

        .constraint-summary li.ok {
            background: #dcfce7;
            color: var(--color-success);
        }

        .constraint-summary li.error {
            background: #fee2e2;
            color: var(--color-error);
        }

        /* Validation results */
        .validation-result {
            margin-bottom: 1rem;
            padding: 1rem;
            background: var(--color-bg);
            border-radius: 6px;
        }

        .validation-result h3 {
            margin-top: 0;
        }

        .error-list, .warning-list {
            margin-left: 1.5rem;
        }

        .error-list li { color: var(--color-error); }
        .warning-list li { color: var(--color-warning); }

        /* Utility classes */
        .success { color: var(--color-success); }
        .warning { color: var(--color-warning); }
        .error { color: var(--color-error); }
        .info { color: var(--color-text-muted); font-style: italic; }

        /* Loop analysis */
        .loop-summary-table .exceeded {
            background: #fee2e2;
            color: var(--color-error);
        }
        .loop-summary-table .ok {
            background: #dcfce7;
            color: var(--color-success);
        }

        /* Footer */
        footer {
            text-align: center;
            padding: 1rem;
            color: var(--color-text-muted);
            font-size: 0.875rem;
        }

        /* Responsive */
        @media (max-width: 768px) {
            .container {
                padding: 1rem;
            }

            .stats-grid {
                grid-template-columns: repeat(2, 1fr);
            }

            table {
                font-size: 0.75rem;
            }

            th, td {
                padding: 0.5rem;
            }
        }
    """
