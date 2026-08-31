"""Tests for uncovered Trace methods.

Covers Trace.empty(), Trace.add(), Trace.for_subject(), and Trace.why().
"""

from temper_orchestration import Trace


class TestTraceEmpty:
    """Test Trace.empty() and monoid identity."""

    def test_empty_returns_empty_trace(self):
        t = Trace.empty()
        assert len(t.entries) == 0
        assert bool(t) is False

    def test_empty_is_monoid_identity(self):
        t1 = Trace.empty().add("Q1", (10, 20), "reason")
        # empty() + t1 == t1
        combined = Trace.empty() + t1
        assert len(combined.entries) == 1


class TestTraceAdd:
    """Test Trace.add() immutable append."""

    def test_add_single_entry(self):
        t = Trace.empty().add("Q1", (10.0, 20.0), "placed")
        assert len(t.entries) == 1
        e = t.entries[0]
        assert e.subject == "Q1"
        assert e.value == (10.0, 20.0)
        assert e.because == "placed"

    def test_add_multiple_entries(self):
        t = Trace.empty()
        t = t.add("Q1", (10, 20), "first")
        t = t.add("Q2", (30, 40), "second")
        t = t.add("Q1", (15, 25), "third")
        assert len(t.entries) == 3

    def test_add_is_immutable(self):
        t1 = Trace.empty()
        t2 = t1.add("Q1", (10, 20), "reason")
        assert len(t1.entries) == 0
        assert len(t2.entries) == 1


class TestTraceForSubject:
    """Test Trace.for_subject() filtering."""

    def test_for_subject_filters(self):
        t = Trace.empty()
        t = t.add("Q1", (10, 20), "r1")
        t = t.add("Q2", (30, 40), "r2")
        t = t.add("Q1", (15, 25), "r3")

        q1 = t.for_subject("Q1")
        assert len(q1.entries) == 2
        assert all(e.subject == "Q1" for e in q1.entries)

    def test_for_subject_nonexistent(self):
        t = Trace.empty().add("Q1", (10, 20), "r1")
        q2 = t.for_subject("NONEXISTENT")
        assert len(q2.entries) == 0


class TestTraceWhy:
    """Test Trace.why() NL generation."""

    def test_why_generates_explanation(self):
        t = Trace.empty()
        t = t.add("Q1", (45.2, 12.3), "Minimize commutation loop")
        t = t.add("Q1", (43.8, 11.9), "Thermal edge constraint")

        explanation = t.why("Q1")
        assert isinstance(explanation, str)
        assert "Q1" in explanation
        # Should mention the latest reason
        assert "Thermal edge constraint" in explanation or "commutation" in explanation.lower()


class TestTraceCompose:
    """Test Trace.__add__() composition."""

    def test_add_composes(self):
        t1 = Trace.empty().add("Q1", (10, 20), "r1")
        t2 = Trace.empty().add("Q2", (30, 40), "r2")
        combined = t1 + t2
        assert len(combined.entries) == 2
        assert combined.entries[0].subject == "Q1"
        assert combined.entries[1].subject == "Q2"

    def test_add_empty_left(self):
        t = Trace.empty().add("Q1", (10, 20), "r1")
        combined = Trace.empty() + t
        assert len(combined.entries) == 1

    def test_add_empty_right(self):
        t = Trace.empty().add("Q1", (10, 20), "r1")
        combined = t + Trace.empty()
        assert len(combined.entries) == 1
