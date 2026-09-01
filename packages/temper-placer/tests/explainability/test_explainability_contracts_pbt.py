"""Property-based tests (G4) + metamorphic relations (G5) for the Phase-A U8
explainability data contracts in ``temper-orchestration`` (Rust Orchestration
Engine plan 2026-08-09-001, ``explainability/{decision,trace,
serialization}.py`` row).

Module-to-property map (G4 — every migrated behavior reached):
- Trace monoid  -> P1 (identity law), P2 (add appends), MR1 (composition
  order-preservation), MR2 (identity under ``why`` output).
- Decision      -> P3 (to_dict -> test-local deserialize_decision round-trip).
- DecisionTrace -> P4 (summary aggregation), P5 (query_subject
  chronological filter), MR4 (summary scale invariance).
- The MarkdownReport binding was differential-only and is intentionally not
  included in this data-contract property suite.

Non-vacuity: every property routes its observable through the ``_IMPL``
indirection and has a ``test_pN_fails_for_<mutant>`` companion re-running it
via ``hypothesis.inner_test`` against a degenerate Python stand-in and
asserting AssertionError.
"""

from __future__ import annotations

from datetime import datetime

import pytest
import temper_io_types as _rust
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.explainability.decision import (
    Decision,
    DecisionPhase,
    DecisionTrace,
    DecisionType,
)
from temper_orchestration import Trace

_FIXED_DT = datetime(2026, 8, 4, 12, 30, 45)


def _deserialize_decision(data):
    """Test-local Python persistence adapter for the orchestration pyclass."""
    try:
        phase = DecisionPhase(data.get("phase", "geometric"))
    except ValueError:
        phase = DecisionPhase.GEOMETRIC
    try:
        dtype = DecisionType(data.get("decision_type", "position_update"))
    except ValueError:
        dtype = DecisionType.POSITION_UPDATE
    timestamp_value = data.get("timestamp")
    if timestamp_value:
        try:
            timestamp = datetime.fromisoformat(timestamp_value)
        except ValueError:
            timestamp = datetime.now()
    else:
        timestamp = datetime.now()
    return Decision(
        id=data.get("id", ""), timestamp=timestamp, phase=phase,
        decision_type=dtype, subject=data.get("subject", ""),
        value=data.get("value"),
        previous_value=data.get("previous_value"),
        reason=data.get("reason", ""), constraint_refs=data.get("constraint_refs", []),
        loss_contribution=data.get("loss_contribution", 0.0), alternatives=[],
        epoch=data.get("epoch"), iteration=data.get("iteration"),
    )

_IMPL = {
    "trace_empty": lambda: Trace.empty(),
    "trace_add": lambda t, s, v, b: t.add(s, v, b),
    "trace_add_entries": lambda a, b: a + b,
    "entries": lambda t: t.entries,
    "len": lambda t: len(t),
    "why": lambda t, s: t.why(s),
    "decision": lambda **kw: Decision(**kw),
    "to_dict": lambda d: d.to_dict(),
    "deserialize": lambda payload: _deserialize_decision(payload),
    "make_trace": lambda decisions: _trace(decisions),
    "summary": lambda t: t.summary(),
    "query_subject": lambda t, s: t.query_subject(s),
    "compose": lambda *ts: _compose_traces(*ts),
}


def _compose_traces(*traces):
    """Compose through the live orchestration Trace monoid API."""
    result = Trace.empty()
    for trace in traces:
        result = result + trace
    return result

_FINITE = {"allow_nan": False, "allow_infinity": False}


def _subject():
    return st.sampled_from(["Q1", "Q2", "U1", "VCC"])


def _value():
    return st.one_of(
        st.tuples(st.floats(min_value=-50.0, max_value=50.0, **_FINITE),
                  st.floats(min_value=-50.0, max_value=50.0, **_FINITE)),
        st.integers(min_value=0, max_value=270),
        st.sampled_from(["L1", "F.Cu", "path", None]),
    )


def _entries_strategy():
    return st.lists(
        st.tuples(_subject(), _value(), st.text(min_size=1, max_size=20)),
        max_size=10,
    )


def _trace(entries):
    t = _IMPL["trace_empty"]()
    for subject, value, because in entries:
        t = _IMPL["trace_add"](t, subject, value, because)
    return t


def _decision(subject, value, *, reason="r", phase=None, dtype=None, counter=0):
    return _IMPL["decision"](
        id=f"d-{subject}-{counter}",
        timestamp=_FIXED_DT,
        phase=phase if phase is not None else DecisionPhase.GEOMETRIC,
        decision_type=dtype if dtype is not None else DecisionType.POSITION_UPDATE,
        subject=subject,
        value=value,
        reason=reason,
        constraint_refs=[],
        alternatives=[],
        epoch=None,
        iteration=None,
    )


@pytest.fixture
def _restore_impl():
    saved = dict(_IMPL)
    yield
    _IMPL.clear()
    _IMPL.update(saved)


# ---------------------------------------------------------------------------
# G4 — P1: Trace monoid identity law
# ---------------------------------------------------------------------------

@given(entries=_entries_strategy())
@settings(max_examples=50, deadline=30000)
def test_p1_trace_monoid_identity(entries):
    """P1. `empty() + t == t == t + empty()` — the monoid identity law, on
    the entry sequence and the length."""
    t = _trace(entries)
    lhs = _IMPL["trace_add_entries"](_IMPL["trace_empty"](), t)
    rhs = _IMPL["trace_add_entries"](t, _IMPL["trace_empty"]())
    for side in (lhs, rhs):
        assert [e.subject for e in _IMPL["entries"](side)] == [e.subject for e in _IMPL["entries"](t)]
        assert len(_IMPL["entries"](side)) == _IMPL["len"](t) == len(entries)


def test_p1_fails_for_dropped_entries_mutant(_restore_impl):
    """A concat that DROPS the left operand's entries violates P1 (an empty
    identity concat would return only the right side's entries)."""
    _IMPL["trace_add_entries"] = lambda _a, b: b
    with pytest.raises(AssertionError):
        test_p1_trace_monoid_identity.hypothesis.inner_test([("Q1", (1, 2), "r")])


# ---------------------------------------------------------------------------
# G4 — P2: Trace.add appends exactly one entry
# ---------------------------------------------------------------------------

@given(entries=_entries_strategy(), s=_subject(), v=_value(), b=st.text(min_size=1, max_size=20))
@settings(max_examples=50, deadline=30000)
def test_p2_trace_add_appends(entries, s, v, b):
    """P2. `t.add(s, v, b)` appends exactly one entry with the given fields
    and keeps the prior entries in order."""
    t = _trace(entries)
    out = _IMPL["trace_add"](t, s, v, b)
    seq = _IMPL["entries"](out)
    assert len(seq) == len(entries) + 1
    assert [e.subject for e in seq[:-1]] == [e.subject for e in _IMPL["entries"](t)]
    last = seq[-1]
    assert last.subject == s
    assert last.value == v
    assert last.because == b


def test_p2_fails_for_overwrite_mutant(_restore_impl):
    """An add that REPLACES the trace instead of appending violates P2."""
    _IMPL["trace_add"] = lambda t, s, v, b: t  # noqa: ARG005
    with pytest.raises(AssertionError):
        test_p2_trace_add_appends.hypothesis.inner_test([], "Q1", (1, 2), "r")


# ---------------------------------------------------------------------------
# G4 — P3: Decision.to_dict -> deserialize_decision round-trip
# ---------------------------------------------------------------------------

@given(s=_subject(), v=_value(), r=st.text(min_size=1, max_size=30))
@settings(max_examples=50, deadline=30000)
def test_p3_decision_roundtrip(s, v, r):
    """P3. `deserialize_decision(d.to_dict())` reproduces every explicit
    field — the pyclass serialization surface is lossless for the declared
    fields."""
    d = _IMPL["decision"](
        id=f"id-{s}",
        timestamp=_FIXED_DT,
        phase=DecisionPhase.ROUTING,
        decision_type=DecisionType.PATH_SELECTION,
        subject=s,
        value=v,
        previous_value=None,
        reason=r,
        constraint_refs=["c1", "c2"],
        loss_contribution=0.5,
        alternatives=[],
        epoch=3,
        iteration=7,
    )
    back = _IMPL["deserialize"](_IMPL["to_dict"](d))
    assert back.id == d.id
    assert back.subject == d.subject
    assert back.phase == d.phase
    assert back.decision_type == d.decision_type
    assert back.value == d.value
    assert back.reason == d.reason
    assert back.constraint_refs == d.constraint_refs
    assert back.loss_contribution == d.loss_contribution
    assert back.epoch == d.epoch == 3
    assert back.iteration == d.iteration == 7


def test_p3_fails_for_dropped_subject_mutant(_restore_impl):
    """A deserialize that drops the subject violates P3."""
    real = _IMPL["deserialize"]
    _IMPL["deserialize"] = lambda payload: _with(drop="subject", base=real, payload=payload)
    with pytest.raises(AssertionError):
        test_p3_decision_roundtrip.hypothesis.inner_test("Q1", (1, 2), "reason")


def _with(*, drop, base, payload):
    altered = dict(payload)
    altered.pop(drop, None)
    return base(altered)


# ---------------------------------------------------------------------------
# G4 — P4: DecisionTrace.summary aggregation
# ---------------------------------------------------------------------------

@given(entries=st.lists(
    st.tuples(_subject(), _value(), st.sampled_from(list(DecisionPhase))),
    max_size=12,
))
@settings(max_examples=50, deadline=30000)
def test_p4_summary_counts(entries):
    """P4. `summary()`'s counts are consistent with the decisions list:
    total_decisions == len(decisions), the per-phase and per-type buckets sum
    to the total, and unique_subjects is exactly the subject set."""
    trace = DecisionTrace(run_id="run", start_time=_FIXED_DT)
    for i, (s, v, phase) in enumerate(entries):
        trace.decisions.append(_decision(s, v, phase=phase, counter=i))
    summary = _IMPL["summary"](trace)
    n = len(entries)
    assert summary["total_decisions"] == n
    assert sum(summary["decisions_by_phase"].values()) == n
    assert sum(summary["decisions_by_type"].values()) == n
    assert sorted(summary["unique_subjects"]) == sorted({s for s, _, _ in entries})
    assert summary["component_count"] == len({s for s, _, _ in entries})
    assert summary["duration_seconds"] is None


def test_p4_fails_for_offbyone_mutant(_restore_impl):
    """A summary that under-counts the total violates P4 (vacuity guard)."""
    real = _IMPL["summary"]

    def mutant(t):
        s = real(t)
        s["total_decisions"] = max(0, s["total_decisions"] - 1)
        return s

    _IMPL["summary"] = mutant
    with pytest.raises(AssertionError):
        test_p4_summary_counts.hypothesis.inner_test([("Q1", (1, 2), DecisionPhase.GEOMETRIC)])


# ---------------------------------------------------------------------------
# G4 — P5: query_subject is a chronological subject filter
# ---------------------------------------------------------------------------

@given(entries=st.lists(
    st.tuples(_subject(), _value(), st.integers(min_value=0, max_value=100)),
    max_size=12,
))
@settings(max_examples=50, deadline=30000)
def test_p5_query_subject_filter(entries):
    """P5. `query_subject(s)` returns exactly the decisions whose subject is
    ``s``, in insertion order."""
    trace = DecisionTrace(run_id="run", start_time=_FIXED_DT)
    for i, (s, v, _counter) in enumerate(entries):
        trace.decisions.append(_decision(s, v, counter=i))
    for s in ("Q1", "Q2", "nobody"):
        got = _IMPL["query_subject"](trace, s)
        expected = [d.value for d in trace.decisions if d.subject == s]
        assert [d.value for d in got] == expected
        assert all(d.subject == s for d in got)


def test_p5_fails_for_unsorted_mutant(_restore_impl):
    """A filter that returns decisions in reverse order violates P5."""
    real = _IMPL["query_subject"]

    def mutant(t, s):
        return real(t, s)[::-1]

    _IMPL["query_subject"] = mutant
    with pytest.raises(AssertionError):
        test_p5_query_subject_filter.hypothesis.inner_test(
            [("Q1", 1, 0), ("Q1", 2, 1), ("Q2", 3, 2)]
        )


# ---------------------------------------------------------------------------
# G5 — MR1: trace composition is order-preserving
# ---------------------------------------------------------------------------

@given(a=_entries_strategy(), b=_entries_strategy(), c=_entries_strategy())
@settings(max_examples=50, deadline=30000)
def test_mr1_compose_order_preserved(a, b, c):
    """MR1. ``compose_traces(a, b, c)`` concatenates the entry sequences in
    argument order — no reordering, no dedup."""
    ta, tb, tc = _trace(a), _trace(b), _trace(c)
    combined = _IMPL["compose"](ta, tb, tc)
    seq = [e.subject for e in _IMPL["entries"](combined)]
    assert seq == [s for s, _, _ in a] + [s for s, _, _ in b] + [s for s, _, _ in c]
    assert len(seq) == len(a) + len(b) + len(c)


def test_mr1_fails_for_dedup_mutant(_restore_impl):
    """A compose that deduplicates subjects violates MR1 (order + count)."""
    real = _IMPL["compose"]
    _IMPL["compose"] = lambda *ts: _dedup(real, *ts)
    with pytest.raises(AssertionError):
        test_mr1_compose_order_preserved.hypothesis.inner_test(
            [("Q1", 1, "a")], [("Q1", 2, "b")], [("Q2", 3, "c")]
        )


def _dedup(real, *ts):
    out = real(*ts)
    seen = set()
    kept = []
    for e in out.entries:
        if e.subject not in seen:
            seen.add(e.subject)
            kept.append(e)
    return Trace(tuple(kept))


# ---------------------------------------------------------------------------
# G5 — MR2: monoid identity is invisible to `why`
# ---------------------------------------------------------------------------

@given(entries=_entries_strategy(), s=_subject())
@settings(max_examples=50, deadline=30000)
def test_mr2_identity_why_invariant(entries, s):
    """MR2. ``t.why(s) == (t + empty()).why(s) == (empty() + t).why(s)`` —
    the identity element does not change the NL output for any subject."""
    t = _trace(entries)
    lhs = _IMPL["trace_add_entries"](_IMPL["trace_empty"](), t)
    rhs = _IMPL["trace_add_entries"](t, _IMPL["trace_empty"]())
    expected = _IMPL["why"](t, s)
    assert _IMPL["why"](lhs, s) == expected
    assert _IMPL["why"](rhs, s) == expected


def test_mr2_fails_for_object_identity_mutant(_restore_impl):
    """A why() whose output depends on the trace's object identity violates
    MR2 — `empty() + t` is a DIFFERENT object than `t`, so the identity-concat
    output invariance breaks."""
    real = _IMPL["why"]

    def mutant(t, s):
        return real(t, s) + f"#{id(t)}"

    _IMPL["why"] = mutant
    with pytest.raises(AssertionError):
        test_mr2_identity_why_invariant.hypothesis.inner_test(
            [("Q1", (1, 2), "a"), ("Q1", (3, 4), "b")], "Q1"
        )


# ---------------------------------------------------------------------------
# G5 — MR4: summary scales with duplicated decisions
# ---------------------------------------------------------------------------

@given(entries=st.lists(st.tuples(_subject(), _value()), max_size=6))
@settings(max_examples=50, deadline=30000)
def test_mr4_summary_scale_invariance(entries):
    """MR4. Duplicating every decision doubles total_decisions and each
    per-phase / per-type bucket (the summary is a linear aggregation)."""
    trace = DecisionTrace(run_id="run-s", start_time=_FIXED_DT)
    for i, (s, v) in enumerate(entries):
        trace.decisions.append(_decision(s, v, counter=i))
    single = _IMPL["summary"](trace)
    for i, (s, v) in enumerate(entries):
        trace.decisions.append(_decision(s, v, counter=i + 100))
    doubled = _IMPL["summary"](trace)
    assert doubled["total_decisions"] == 2 * single["total_decisions"]
    for phase, count in single["decisions_by_phase"].items():
        assert doubled["decisions_by_phase"][phase] == 2 * count
    for dtype, count in single["decisions_by_type"].items():
        assert doubled["decisions_by_type"][dtype] == 2 * count


def test_mr4_fails_for_capped_count_mutant(_restore_impl):
    """A summary that caps total_decisions at some fixed value violates MR4."""
    real = _IMPL["summary"]

    def mutant(t):
        s = real(t)
        s["total_decisions"] = min(s["total_decisions"], 1)
        return s

    _IMPL["summary"] = mutant
    with pytest.raises(AssertionError):
        test_mr4_summary_scale_invariance.hypothesis.inner_test(
            [("Q1", (1, 2)), ("Q2", (3, 4)), ("Q1", (5, 6))]
        )
