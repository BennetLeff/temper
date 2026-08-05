"""Markdown report generation for decision traces.

This module generates human-readable markdown reports from DecisionTrace objects,
providing clear documentation of all placement decisions for review and debugging.

Wave 4, Phase 5: the whole rendering pipeline now lives in the
``temper-io-types`` Rust crate (``explain.rs``); this module is a delegation
shim. Timestamp ``strftime`` and ``datetime`` arithmetic stay Python — the
shim pre-formats the two timestamp strings and the duration — everything
downstream is Rust. The pre-migration implementation is pinned verbatim as
``tests/explainability/explain_oracle/markdown_report_oracle.py``.

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

from pathlib import Path
from typing import Any

import temper_io_types as _rust

from temper_placer.explainability.decision import (
    Decision,
    DecisionPhase,
    DecisionTrace,
)


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
    start_str = trace.start_time.strftime("%Y-%m-%d %H:%M:%S")
    end_str = trace.end_time.strftime("%Y-%m-%d %H:%M:%S") if trace.end_time else None
    duration = (trace.end_time - trace.start_time).total_seconds() if trace.end_time else None
    return _rust.explain_render_markdown_report(
        trace, include_config, include_positions, start_str, end_str, duration,
        _max_decisions_per_component,
    )


def render_component_report(trace: DecisionTrace, subject: str) -> str:
    """Generate a focused report for a single component.

    Args:
        trace: The DecisionTrace
        subject: Component reference to report on

    Returns:
        Markdown report for just that component
    """
    return _rust.explain_render_component_report(trace, subject)


def save_markdown_report(trace: DecisionTrace, path: Path | str) -> None:
    """Save markdown report to file.

    Args:
        trace: DecisionTrace to render
        path: Output file path
    """
    report = render_markdown_report(trace)
    Path(path).write_text(report)
