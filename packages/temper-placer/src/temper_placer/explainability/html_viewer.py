"""Interactive HTML viewer for decision traces.

This module generates standalone HTML reports with embedded CSS and JavaScript
for exploring placement and routing decisions interactively.

The HTML viewer provides:
- Timeline visualization of all decisions
- Component detail cards showing decision history
- Phase and constraint summaries
- Search and filter functionality
- Click-to-explore interactivity
- Alternatives and why-not explanations

Example:
    >>> trace = DecisionTrace()
    >>> # ... add decisions ...
    >>> save_html_report(trace, "report.html", title="Placement Decisions")
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import TYPE_CHECKING

from temper_placer.explainability.decision import (
    Decision,
    DecisionTrace,
    DecisionType,
)

if TYPE_CHECKING:
    pass


def generate_html_report(trace: DecisionTrace, title: str | None = None) -> str:
    """Generate a complete HTML report for a decision trace.

    Args:
        trace: The decision trace to visualize
        title: Optional custom title (defaults to "Decision Trace - {run_id}")

    Returns:
        Complete HTML document as a string
    """
    if title is None:
        title = f"Decision Trace - {trace.run_id}"

    # Collect component subjects
    subjects = sorted(
        set(
            d.subject
            for d in trace.decisions
            if d.decision_type
            in (
                DecisionType.INITIAL_POSITION,
                DecisionType.POSITION_UPDATE,
                DecisionType.ROTATION,
            )
        )
    )

    # Generate HTML sections
    timeline_html = render_decision_timeline(trace.decisions)
    phase_summary_html = render_phase_summary(trace)
    constraint_summary_html = render_constraint_summary(trace)
    search_panel_html = render_search_panel(trace)

    # Component cards
    component_cards_html = ""
    for subject in subjects:
        decisions = trace.query_subject(subject)
        component_cards_html += render_component_card(subject, decisions)

    # Final metrics
    metrics_html = ""
    if trace.final_metrics:
        metrics_html = "<div class='metrics'>"
        metrics_html += "<h3>Final Metrics</h3>"
        metrics_html += "<table>"
        for key, value in trace.final_metrics.items():
            metrics_html += f"<tr><td>{html.escape(key)}</td><td>{value:.4f}</td></tr>"
        metrics_html += "</table>"
        metrics_html += "</div>"

    # Build complete HTML
    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(title)}</title>
    <style>
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
            padding: 20px;
        }}
        header {{
            background: #2c3e50;
            color: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
        }}
        h1 {{
            margin-bottom: 10px;
        }}
        .subtitle {{
            color: #bdc3c7;
            font-size: 14px;
        }}
        main {{
            display: grid;
            grid-template-columns: 300px 1fr;
            gap: 20px;
            max-width: 1400px;
            margin: 0 auto;
        }}
        aside {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            height: fit-content;
            position: sticky;
            top: 20px;
        }}
        article {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h2 {{
            color: #2c3e50;
            margin-bottom: 15px;
            border-bottom: 2px solid #3498db;
            padding-bottom: 10px;
        }}
        h3 {{
            color: #34495e;
            margin: 20px 0 10px 0;
            font-size: 18px;
        }}
        .search-box {{
            width: 100%;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 4px;
            margin-bottom: 15px;
            font-size: 14px;
        }}
        .filter-group {{
            margin-bottom: 15px;
        }}
        .filter-group label {{
            display: block;
            margin-bottom: 5px;
            font-weight: 600;
            font-size: 12px;
            text-transform: uppercase;
            color: #7f8c8d;
        }}
        .filter-group select {{
            width: 100%;
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 14px;
        }}
        .decision {{
            border-left: 4px solid #3498db;
            padding: 15px;
            margin-bottom: 15px;
            background: #f8f9fa;
            border-radius: 4px;
            cursor: pointer;
            transition: all 0.2s;
        }}
        .decision:hover {{
            background: #e8f4f8;
            transform: translateX(5px);
        }}
        .decision.hidden {{
            display: none;
        }}
        .decision-id {{
            font-size: 12px;
            color: #7f8c8d;
            font-family: monospace;
        }}
        .decision-subject {{
            font-weight: 600;
            color: #2c3e50;
            font-size: 16px;
            margin: 5px 0;
        }}
        .decision-reason {{
            color: #555;
            margin: 5px 0;
        }}
        .decision-meta {{
            font-size: 12px;
            color: #7f8c8d;
            margin-top: 5px;
        }}
        .badge {{
            display: inline-block;
            padding: 3px 8px;
            border-radius: 3px;
            font-size: 11px;
            font-weight: 600;
            margin-right: 5px;
            text-transform: uppercase;
        }}
        .badge-phase {{
            background: #3498db;
            color: white;
        }}
        .badge-type {{
            background: #9b59b6;
            color: white;
        }}
        .badge-epoch {{
            background: #e67e22;
            color: white;
        }}
        .component-card {{
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            background: #fafafa;
        }}
        .component-card h3 {{
            color: #2c3e50;
            margin-top: 0;
        }}
        .position {{
            font-family: monospace;
            background: #34495e;
            color: #ecf0f1;
            padding: 5px 10px;
            border-radius: 4px;
            display: inline-block;
            margin: 5px 0;
        }}
        .constraint-ref {{
            display: inline-block;
            background: #e8f4f8;
            color: #2980b9;
            padding: 3px 8px;
            border-radius: 3px;
            font-size: 12px;
            margin: 2px;
            font-family: monospace;
        }}
        .alternative {{
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 10px;
            margin: 10px 0;
            border-radius: 4px;
        }}
        .alternative-value {{
            font-weight: 600;
            color: #856404;
        }}
        .rejection-reason {{
            color: #721c24;
            margin-top: 5px;
        }}
        .summary-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 10px 0;
        }}
        .summary-table th {{
            background: #ecf0f1;
            padding: 10px;
            text-align: left;
            font-weight: 600;
            border-bottom: 2px solid #bdc3c7;
        }}
        .summary-table td {{
            padding: 10px;
            border-bottom: 1px solid #ecf0f1;
        }}
        .summary-table tr:hover {{
            background: #f8f9fa;
        }}
        .metrics {{
            background: #d5f4e6;
            border: 1px solid #27ae60;
            border-radius: 8px;
            padding: 15px;
            margin: 20px 0;
        }}
        .metrics table {{
            width: 100%;
        }}
        .metrics td {{
            padding: 5px;
        }}
        .metrics td:first-child {{
            font-weight: 600;
            color: #27ae60;
        }}
        .empty-state {{
            text-align: center;
            padding: 40px;
            color: #7f8c8d;
        }}
        .clickable {{
            cursor: pointer;
            transition: background 0.2s;
        }}
        .clickable:hover {{
            background: #e8f4f8;
        }}
        @media (max-width: 768px) {{
            main {{
                grid-template-columns: 1fr;
            }}
            aside {{
                position: static;
            }}
        }}
    </style>
</head>
<body>
    <header>
        <h1>{html.escape(title)}</h1>
        <div class="subtitle">
            Run ID: {html.escape(trace.run_id)} | 
            Decisions: {len(trace.decisions)} | 
            Components: {len(subjects)}
        </div>
    </header>

    <main>
        <aside>
            <h2>Explore</h2>
            {search_panel_html}
            {phase_summary_html}
            {constraint_summary_html}
        </aside>

        <article>
            {metrics_html}
            
            <section id="timeline">
                <h2>Decision Timeline</h2>
                {timeline_html if trace.decisions else '<div class="empty-state">No decisions recorded</div>'}
            </section>

            <section id="components">
                <h2>Component Details</h2>
                {component_cards_html if subjects else '<div class="empty-state">No component decisions</div>'}
            </section>
        </article>
    </main>

    <script>
        // Search functionality
        const searchBox = document.getElementById('search-input');
        if (searchBox) {{
            searchBox.addEventListener('input', function(e) {{
                const query = e.target.value.toLowerCase();
                const decisions = document.querySelectorAll('.decision');
                decisions.forEach(dec => {{
                    const text = dec.textContent.toLowerCase();
                    if (text.includes(query)) {{
                        dec.classList.remove('hidden');
                    }} else {{
                        dec.classList.add('hidden');
                    }}
                }});
            }});
        }}

        // Phase filter
        const phaseFilter = document.getElementById('phase-filter');
        if (phaseFilter) {{
            phaseFilter.addEventListener('change', function(e) {{
                const phase = e.target.value;
                const decisions = document.querySelectorAll('.decision');
                decisions.forEach(dec => {{
                    if (phase === 'all' || dec.dataset.phase === phase) {{
                        dec.classList.remove('hidden');
                    }} else {{
                        dec.classList.add('hidden');
                    }}
                }});
            }});
        }}

        // Type filter
        const typeFilter = document.getElementById('type-filter');
        if (typeFilter) {{
            typeFilter.addEventListener('change', function(e) {{
                const type = e.target.value;
                const decisions = document.querySelectorAll('.decision');
                decisions.forEach(dec => {{
                    if (type === 'all' || dec.dataset.type === type) {{
                        dec.classList.remove('hidden');
                    }} else {{
                        dec.classList.add('hidden');
                    }}
                }});
            }});
        }}

        // Constraint click handler
        document.querySelectorAll('[data-constraint]').forEach(el => {{
            el.addEventListener('click', function() {{
                const constraint = this.dataset.constraint;
                const decisions = document.querySelectorAll('.decision');
                decisions.forEach(dec => {{
                    if (dec.textContent.includes(constraint)) {{
                        dec.classList.remove('hidden');
                        dec.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                    }} else {{
                        dec.classList.add('hidden');
                    }}
                }});
            }});
        }});
    </script>
</body>
</html>"""

    return html_doc


def render_decision_timeline(decisions: list[Decision]) -> str:
    """Render a timeline of decisions in chronological order.

    Args:
        decisions: List of decisions to render

    Returns:
        HTML string for the timeline
    """
    if not decisions:
        return '<div class="empty-state">No decisions to display</div>'

    html_parts = []
    for decision in decisions:
        phase_badge = f'<span class="badge badge-phase">{decision.phase.value}</span>'
        type_badge = f'<span class="badge badge-type">{decision.decision_type.value}</span>'
        epoch_badge = (
            f'<span class="badge badge-epoch">Epoch {decision.epoch}</span>'
            if decision.epoch is not None
            else ""
        )

        value_str = _format_value(decision.value)

        html_parts.append(f'''
        <div class="decision" data-phase="{decision.phase.value}" data-type="{decision.decision_type.value}" data-decision-id="{html.escape(decision.id)}">
            <div class="decision-id">{html.escape(decision.id)}</div>
            <div class="decision-subject">{html.escape(decision.subject)}</div>
            <div class="decision-reason">{html.escape(decision.reason)}</div>
            <div class="decision-meta">
                {phase_badge}
                {type_badge}
                {epoch_badge}
                {_render_constraints(decision.constraint_refs)}
            </div>
            {_render_alternatives(decision.alternatives)}
        </div>
        ''')

    return "\n".join(html_parts)


def render_component_card(component: str, decisions: list[Decision]) -> str:
    """Render a detailed card for a single component.

    Args:
        component: Component reference (e.g., "Q1")
        decisions: All decisions about this component

    Returns:
        HTML string for the component card
    """
    if not decisions:
        return f"""
        <div class="component-card">
            <h3>{html.escape(component)}</h3>
            <p class="empty-state">No decisions found for this component</p>
        </div>
        """

    # Get final decision
    final = decisions[-1]
    final_value = _format_value(final.value)

    # Build history
    history_html = "<div><strong>Decision History:</strong><ol>"
    for i, dec in enumerate(decisions, 1):
        history_html += f"<li>{html.escape(dec.reason)}"
        if dec.epoch is not None:
            history_html += f' <span class="badge badge-epoch">Epoch {dec.epoch}</span>'
        history_html += "</li>"
    history_html += "</ol></div>"

    # Constraints
    all_constraints = set()
    for dec in decisions:
        all_constraints.update(dec.constraint_refs)

    constraints_html = ""
    if all_constraints:
        constraints_html = "<div><strong>Constraints:</strong><br>"
        constraints_html += _render_constraints(list(all_constraints))
        constraints_html += "</div>"

    return f"""
    <div class="component-card">
        <h3>{html.escape(component)}</h3>
        <div><strong>Final State:</strong> <span class="position">{html.escape(final_value)}</span></div>
        <div><strong>Reason:</strong> {html.escape(final.reason)}</div>
        {constraints_html}
        {history_html}
    </div>
    """


def render_phase_summary(trace: DecisionTrace) -> str:
    """Render a summary of decisions by phase.

    Args:
        trace: The decision trace

    Returns:
        HTML string for phase summary
    """
    if not trace.decisions:
        return '<div class="empty-state">No phases</div>'

    phase_counts: dict[str, int] = {}
    for decision in trace.decisions:
        phase = decision.phase.value
        phase_counts[phase] = phase_counts.get(phase, 0) + 1

    html_parts = ["<h3>By Phase</h3>", '<table class="summary-table">']
    for phase, count in sorted(phase_counts.items()):
        html_parts.append(f'''
        <tr class="clickable" data-phase="{phase}">
            <td>{html.escape(phase)}</td>
            <td>{count}</td>
        </tr>
        ''')
    html_parts.append("</table>")

    return "\n".join(html_parts)


def render_constraint_summary(trace: DecisionTrace) -> str:
    """Render a summary of constraints referenced in decisions.

    Args:
        trace: The decision trace

    Returns:
        HTML string for constraint summary
    """
    if not trace.decisions:
        return ""

    constraint_counts: dict[str, set[str]] = {}
    for decision in trace.decisions:
        for constraint in decision.constraint_refs:
            if constraint not in constraint_counts:
                constraint_counts[constraint] = set()
            if decision.subject:
                constraint_counts[constraint].add(decision.subject)

    if not constraint_counts:
        return ""

    html_parts = ["<h3>Constraints</h3>", '<table class="summary-table">']
    for constraint, components in sorted(constraint_counts.items()):
        components_str = ", ".join(sorted(components)[:5])
        if len(components) > 5:
            components_str += f" +{len(components) - 5} more"
        html_parts.append(f'''
        <tr class="clickable" data-constraint="{html.escape(constraint)}">
            <td><span class="constraint-ref">{html.escape(constraint)}</span></td>
            <td style="font-size: 11px;">{html.escape(components_str)}</td>
        </tr>
        ''')
    html_parts.append("</table>")

    return "\n".join(html_parts)


def render_search_panel(trace: DecisionTrace) -> str:
    """Render search and filter controls.

    Args:
        trace: The decision trace

    Returns:
        HTML string for search panel
    """
    # Collect unique phases and types
    phases = sorted(set(d.phase.value for d in trace.decisions))
    types = sorted(set(d.decision_type.value for d in trace.decisions))

    phase_options = '<option value="all">All Phases</option>'
    for phase in phases:
        phase_options += f'<option value="{phase}">{phase}</option>'

    type_options = '<option value="all">All Types</option>'
    for dtype in types:
        type_options += f'<option value="{dtype}">{dtype}</option>'

    return f"""
    <input type="text" id="search-input" class="search-box" placeholder="Search decisions...">
    
    <div class="filter-group">
        <label for="phase-filter">Filter by Phase</label>
        <select id="phase-filter">
            {phase_options}
        </select>
    </div>

    <div class="filter-group">
        <label for="type-filter">Filter by Type</label>
        <select id="type-filter">
            {type_options}
        </select>
    </div>
    """


def save_html_report(
    trace: DecisionTrace, output_path: Path | str, title: str | None = None
) -> None:
    """Generate and save an HTML report to a file.

    Args:
        trace: The decision trace to visualize
        output_path: Where to save the HTML file
        title: Optional custom title
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    html_content = generate_html_report(trace, title=title)
    output_path.write_text(html_content, encoding="utf-8")


# =============================================================================
# Helper functions
# =============================================================================


def _format_value(value) -> str:
    """Format a decision value for display."""
    if isinstance(value, tuple) and len(value) == 2:
        return f"({value[0]:.1f}, {value[1]:.1f})"
    elif isinstance(value, list):
        return ", ".join(str(v) for v in value)
    elif value is None:
        return "None"
    else:
        return str(value)


def _render_constraints(constraint_refs: list[str]) -> str:
    """Render constraint references as badges."""
    if not constraint_refs:
        return ""
    return " ".join(
        f'<span class="constraint-ref">{html.escape(c)}</span>' for c in constraint_refs
    )


def _render_alternatives(alternatives: list) -> str:
    """Render rejected alternatives."""
    if not alternatives:
        return ""

    html_parts = ['<div style="margin-top: 10px;"><strong>Alternatives Rejected:</strong></div>']
    for alt in alternatives:
        value_str = _format_value(alt.value)
        html_parts.append(f"""
        <div class="alternative">
            <div class="alternative-value">❌ {html.escape(value_str)}</div>
            <div class="rejection-reason">{html.escape(alt.rejection_reason)}</div>
            {f'<div style="font-size: 11px; color: #856404;">Constraint: {html.escape(alt.constraint_violated)}</div>' if alt.constraint_violated else ""}
            {f'<div style="font-size: 11px; color: #856404;">Loss: {alt.loss_if_chosen:.4f}</div>' if alt.loss_if_chosen is not None else ""}
        </div>
        """)

    return "\n".join(html_parts)
