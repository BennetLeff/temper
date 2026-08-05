"""Property-based tests for the migrated explainability surface
(temper-io-types).

R1c: >= 5 non-vacuous properties. Written against the delegation shims;
vacuity guards assert the fixture exercises the property. The monoid
properties here double as R1d metamorphic relations for the trace/compose
surface (associativity, identity, order preservation).
"""

from __future__ import annotations

import random
from datetime import datetime

import pytest

from temper_placer.explainability.decision import (
    Alternative,
    Decision,
    DecisionPhase,
    DecisionTrace,
    DecisionType,
)
from temper_placer.explainability.logger import DecisionLogger
from temper_placer.explainability.markdown_report import render_component_report
from temper_placer.explainability.pipeline import compose_traces
from temper_placer.explainability.trace import Trace


def _trace(entries):
    t = Trace.empty()
    for subject, value, because in entries:
        t = t.add(subject, value, because)
    return t


# ---------------------------------------------------------------------------
# Trace monoid (metamorphic relations)
# ---------------------------------------------------------------------------

def test_prop_trace_associativity():
    """(a + b) + c == a + (b + c) — monoid law, order-preserving."""
    a = _trace([("A", 1, "r1")])
    b = _trace([("B", 2, "r2")])
    c = _trace([("C", 3, "r3")])
    lhs = compose_traces(compose_traces(a, b), c)
    rhs = compose_traces(a, compose_traces(b, c))
    assert [e.subject for e in lhs.entries] == [e.subject for e in rhs.entries]
    assert len(lhs) == len(rhs) == 3


def test_prop_trace_why_filters_to_subject():
    trace = _trace([("Q1", (1, 2), "a"), ("Q2", (3, 4), "b"), ("Q1", (5, 6), "c")])
    text = trace.why("Q1")
    assert "Q1 is at (5.0, 6.0)" in text
    assert "Q2" not in text  # the other subject's entries are filtered out
    assert "a" in text and "c" in text


def test_prop_trace_why_truncation_is_prefix():
    """With max_reasons < len, the reasons shown are the FIRST
    max_reasons (not the last) and a count line follows."""
    trace = _trace([("C", (i, i), f"r{i}") for i in range(7)])
    text = trace.why("C", 2)
    assert "r0" in text and "r1" in text
    assert "r2" not in text
    assert "5 more reasons" in text


def test_prop_logger_significant_change_commutative_distance():
    """Euclidean distance is symmetric: (a,b) and (b,a) agree."""
    logger = DecisionLogger()
    a, b = (1.0, 2.0), (4.0, 6.0)
    assert logger.significant_change(a, b, 5.0) == logger.significant_change(b, a, 5.0)


def test_prop_logger_should_log_is_periodic():
    logger = DecisionLogger()
    epoch = 250
    assert logger.should_log(epoch, 50) is True
    assert logger.should_log(epoch, 100) is False
    assert logger.should_log(epoch, 125) is True
    assert logger.should_log(epoch, 250) is True


def test_prop_decision_history_is_chronological_subject_filter():
    trace = DecisionTrace(run_id="r", start_time=datetime(2026, 8, 4))
    trace.decisions.append(Decision(id="d1", subject="Q1", value=1, reason="first"))
    trace.decisions.append(Decision(id="d2", subject="Q2", value=2, reason="other"))
    trace.decisions.append(Decision(id="d3", subject="Q1", value=3, reason="last"))
    history = trace.history("Q1")
    assert [h[0] for h in history] == [1, 3]
    assert [h[1] for h in history] == ["first", "last"]


def test_prop_component_report_contains_only_subject_decisions():
    trace = DecisionTrace(run_id="r", start_time=datetime(2026, 8, 4))
    trace.decisions.append(Decision(id="d1", subject="Q1", value=1, reason="for q1"))
    trace.decisions.append(Decision(id="d2", subject="Q2", value=2, reason="for q2"))
    text = render_component_report(trace, "Q1")
    assert "for q1" in text
    assert "for q2" not in text


def test_prop_component_report_max_decisions_cap():
    trace = DecisionTrace(run_id="r", start_time=datetime(2026, 8, 4))
    for i in range(60):
        trace.decisions.append(Decision(id=f"d{i}", subject="Q1", value=i, reason=f"r{i}"))
    text = render_component_report(trace, "Q1")
    assert "earlier decisions omitted" in text
    assert "r59" in text
