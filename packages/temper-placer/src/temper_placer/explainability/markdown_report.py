"""Markdown report generation for decision traces.

This module generates human-readable markdown reports from DecisionTrace objects,
providing clear documentation of all placement decisions for review and debugging.

Example:
    >>> from temper_placer.explainability import DecisionTrace, Decision
    >>> from temper_placer.explainability.markdown_report import render_markdown_report
    >>>
    >>> trace = DecisionTrace()
    >>> trace.add(Decision(subject='Q1', value=(10, 20), reason='Initial'))
    >>>
    >>> report = render_markdown_report(trace)
    >>> print(report)
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from temper_placer.explainability.decision import (
    Decision,
    DecisionPhase,
    DecisionTrace,
)


def _format_value(value: Any) -> str:
    """Format a value for display in markdown.

    Args:
        value: Any value (position tuple, rotation, etc.)

    Returns:
        Human-readable string representation
    """
    if value is None:
        return "-"
    if isinstance(value, (list, tuple)) and len(value) == 2:
        # Position tuple
        return f"({value[0]:.1f}, {value[1]:.1f})"
    if isinstance(value, (list, tuple)) and len(value) == 3:
        # Position with rotation
        return f"({value[0]:.1f}, {value[1]:.1f}) @ {value[2]}°"
    if isinstance(value, dict):
        if "x" in value and "y" in value:
            x, y = value["x"], value["y"]
            rot = value.get("rotation", 0)
            return f"({x:.1f}, {y:.1f}) @ {rot}°"
        return str(value)
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _truncate(text: str, max_len: int = 60) -> str:
    """Truncate text to max length with ellipsis.

    Args:
        text: Text to truncate
        max_len: Maximum length

    Returns:
        Truncated string
    """
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _count_by_phase(decisions: list[Decision]) -> dict[str, int]:
    """Count decisions by phase.

    Args:
        decisions: List of decisions

    Returns:
        Dictionary mapping phase name to count
    """
    counter = Counter(d.phase.value for d in decisions)
    # Order by phase enum order
    return {
        phase.value: counter.get(phase.value, 0)
        for phase in DecisionPhase
        if counter.get(phase.value, 0) > 0
    }


def _count_by_type(decisions: list[Decision]) -> dict[str, int]:
    """Count decisions by type.

    Args:
        decisions: List of decisions

    Returns:
        Dictionary mapping type name to count
    """
    counter = Counter(d.decision_type.value for d in decisions)
    return dict(counter.most_common())


def _render_header(trace: DecisionTrace) -> list[str]:
    """Render the report header section.

    Args:
        trace: The decision trace

    Returns:
        List of markdown lines
    """
    lines = [
        "# Placement Decision Report",
        "",
        f"**Run ID**: `{trace.run_id}`",
        f"**Started**: {trace.start_time.strftime('%Y-%m-%d %H:%M:%S')}",
    ]

    if trace.end_time:
        lines.append(f"**Ended**: {trace.end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        duration = (trace.end_time - trace.start_time).total_seconds()
        lines.append(f"**Duration**: {duration:.1f} seconds")

    # Counts
    subjects = {d.subject for d in trace.decisions}
    lines.append(f"**Components**: {len(subjects)}")
    lines.append(f"**Total Decisions**: {len(trace.decisions)}")
    lines.append("")

    return lines


def _render_summary_metrics(trace: DecisionTrace) -> list[str]:
    """Render the summary metrics section.

    Args:
        trace: The decision trace

    Returns:
        List of markdown lines
    """
    if not trace.final_metrics:
        return []

    lines = [
        "## Summary Metrics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
    ]

    for metric, value in sorted(trace.final_metrics.items()):
        if isinstance(value, float):
            lines.append(f"| {metric} | {value:.4f} |")
        else:
            lines.append(f"| {metric} | {value} |")

    lines.append("")
    return lines


def _render_phase_summary(trace: DecisionTrace) -> list[str]:
    """Render the phase summary section.

    Args:
        trace: The decision trace

    Returns:
        List of markdown lines
    """
    phase_counts = _count_by_phase(trace.decisions)
    if not phase_counts:
        return []

    lines = [
        "## Phase Summary",
        "",
        "| Phase | Decisions |",
        "|-------|-----------|",
    ]

    for phase, count in phase_counts.items():
        lines.append(f"| {phase.title()} | {count} |")

    lines.append("")
    return lines


def _render_type_summary(trace: DecisionTrace) -> list[str]:
    """Render the decision type summary section.

    Args:
        trace: The decision trace

    Returns:
        List of markdown lines
    """
    type_counts = _count_by_type(trace.decisions)
    if not type_counts:
        return []

    lines = [
        "## Decision Types",
        "",
        "| Type | Count |",
        "|------|-------|",
    ]

    for dtype, count in type_counts.items():
        # Make type more readable
        readable = dtype.replace("_", " ").title()
        lines.append(f"| {readable} | {count} |")

    lines.append("")
    return lines


def _render_component_section(
    subject: str,
    decisions: list[Decision],
    max_decisions: int = 10,
) -> list[str]:
    """Render markdown section for one component.

    Args:
        subject: Component reference
        decisions: Decisions for this component
        max_decisions: Maximum number of decisions to show

    Returns:
        List of markdown lines
    """
    lines = [f"### {subject}", ""]

    if not decisions:
        lines.append("*No decisions recorded*")
        lines.append("")
        return lines

    # Final state
    final = decisions[-1]
    lines.append(f"**Final Value**: {_format_value(final.value)}")
    if final.reason:
        lines.append(f"**Final Reason**: {_truncate(final.reason)}")
    lines.append("")

    # Decision table
    lines.append("#### Decision History")
    lines.append("")
    lines.append("| # | Type | Epoch | Value | Reason |")
    lines.append("|---|------|-------|-------|--------|")

    # Show last N decisions
    shown_decisions = decisions[-max_decisions:]
    start_idx = len(decisions) - len(shown_decisions) + 1

    for i, d in enumerate(shown_decisions, start=start_idx):
        epoch = str(d.epoch) if d.epoch is not None else "-"
        dtype = d.decision_type.value.replace("_", " ").title()
        value = _format_value(d.value)
        reason = _truncate(d.reason, 40)
        lines.append(f"| {i} | {dtype} | {epoch} | {value} | {reason} |")

    if len(decisions) > max_decisions:
        lines.append(
            f"| ... | *{len(decisions) - max_decisions} earlier decisions omitted* | | | |"
        )

    lines.append("")

    # Binding constraints (from final decision)
    if final.constraint_refs:
        lines.append("**Binding Constraints**:")
        lines.append("")
        for ref in final.constraint_refs:
            lines.append(f"- `{ref}`")
        lines.append("")

    # Rejected alternatives (from all decisions)
    all_alts = [alt for d in decisions for alt in d.alternatives]
    if all_alts:
        lines.append("**Rejected Alternatives**:")
        lines.append("")
        for i, alt in enumerate(all_alts[:5], 1):
            value = _format_value(alt.value)
            reason = _truncate(alt.rejection_reason, 50)
            if alt.constraint_violated:
                lines.append(f"{i}. {value}: {reason} (`{alt.constraint_violated}`)")
            else:
                lines.append(f"{i}. {value}: {reason}")
        if len(all_alts) > 5:
            lines.append(f"   *...and {len(all_alts) - 5} more alternatives*")
        lines.append("")

    return lines


def _render_component_decisions(trace: DecisionTrace) -> list[str]:
    """Render the component decisions section.

    Args:
        trace: The decision trace

    Returns:
        List of markdown lines
    """
    subjects = sorted({d.subject for d in trace.decisions})
    if not subjects:
        return []

    lines = ["## Component Decisions", ""]

    for subject in subjects:
        decisions = trace.query_subject(subject)
        lines.extend(_render_component_section(subject, decisions))

    return lines


def _render_final_positions(trace: DecisionTrace) -> list[str]:
    """Render the final positions table.

    Args:
        trace: The decision trace

    Returns:
        List of markdown lines
    """
    if not trace.final_positions:
        return []

    lines = [
        "## Final Positions",
        "",
        "| Component | X | Y |",
        "|-----------|---|---|",
    ]

    for comp, pos in sorted(trace.final_positions.items()):
        lines.append(f"| {comp} | {pos[0]:.2f} | {pos[1]:.2f} |")

    lines.append("")
    return lines


def _render_config_snapshot(trace: DecisionTrace) -> list[str]:
    """Render the configuration snapshot section.

    Args:
        trace: The decision trace

    Returns:
        List of markdown lines
    """
    if not trace.config_snapshot:
        return []

    lines = [
        "## Configuration",
        "",
        "```yaml",
    ]

    for key, value in sorted(trace.config_snapshot.items()):
        lines.append(f"{key}: {value}")

    lines.append("```")
    lines.append("")
    return lines


def render_markdown_report(
    trace: DecisionTrace,
    include_config: bool = True,
    include_positions: bool = True,
    _max_decisions_per_component: int = 10,
) -> str:
    """Generate a complete markdown report from a decision trace.

    Args:
        trace: The DecisionTrace to render
        include_config: Whether to include config snapshot
        include_positions: Whether to include final positions table
        max_decisions_per_component: Max decisions to show per component

    Returns:
        Complete markdown report as a string
    """
    lines: list[str] = []

    # Header with basic info
    lines.extend(_render_header(trace))

    # Summary sections
    lines.extend(_render_summary_metrics(trace))
    lines.extend(_render_phase_summary(trace))
    lines.extend(_render_type_summary(trace))

    # Component decisions (the main content)
    lines.extend(_render_component_decisions(trace))

    # Final positions table
    if include_positions:
        lines.extend(_render_final_positions(trace))

    # Config snapshot
    if include_config:
        lines.extend(_render_config_snapshot(trace))

    return "\n".join(lines)


def render_component_report(trace: DecisionTrace, subject: str) -> str:
    """Generate a focused report for a single component.

    Args:
        trace: The DecisionTrace
        subject: Component reference to report on

    Returns:
        Markdown report for just that component
    """
    decisions = trace.query_subject(subject)

    lines = [
        f"# Decision Report: {subject}",
        "",
        f"**Run ID**: `{trace.run_id}`",
        f"**Total Decisions**: {len(decisions)}",
        "",
    ]

    lines.extend(_render_component_section(subject, decisions, max_decisions=50))

    return "\n".join(lines)


def save_markdown_report(trace: DecisionTrace, path: Path | str) -> None:
    """Save markdown report to file.

    Args:
        trace: DecisionTrace to render
        path: Output file path
    """
    report = render_markdown_report(trace)
    Path(path).write_text(report)
