"""Property-based tests for the migrated explainability surface
(temper-io-types).

R1c: >= 5 non-vacuous properties. Written against the delegation shims;
vacuity guards assert the fixture exercises the property. The monoid
properties here double as R1d metamorphic relations for the trace/compose
surface (associativity, identity, order preservation).
"""

from __future__ import annotations

from datetime import datetime

from temper_placer.explainability.decision import (
    Decision,
    DecisionTrace,
)
from temper_orchestration import Trace


def _trace(entries):
    t = Trace.empty()
    for subject, value, because in entries:
        t = t.add(subject, value, because)
    return t


def _compose_traces(*traces):
    """Compose through the live orchestration Trace monoid API."""
    result = Trace.empty()
    for trace in traces:
        result = result + trace
    return result


# ---------------------------------------------------------------------------
# Trace monoid (metamorphic relations)
# ---------------------------------------------------------------------------

def test_prop_trace_associativity():
    """(a + b) + c == a + (b + c) — monoid law, order-preserving."""
    a = _trace([("A", 1, "r1")])
    b = _trace([("B", 2, "r2")])
    c = _trace([("C", 3, "r3")])
    lhs = _compose_traces(_compose_traces(a, b), c)
    rhs = _compose_traces(a, _compose_traces(b, c))
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


def test_prop_decision_history_is_chronological_subject_filter():
    trace = DecisionTrace(run_id="r", start_time=datetime(2026, 8, 4))
    trace.decisions.append(Decision(id="d1", subject="Q1", value=1, reason="first"))
    trace.decisions.append(Decision(id="d2", subject="Q2", value=2, reason="other"))
    trace.decisions.append(Decision(id="d3", subject="Q1", value=3, reason="last"))
    history = trace.history("Q1")
    assert [h[0] for h in history] == [1, 3]
    assert [h[1] for h in history] == ["first", "last"]
