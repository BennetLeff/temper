"""Tests for uncovered DecisionTrace query methods and Decision.to_dict.

Covers query_* and to_dict methods that may not be directly exercised by
the differential rust tests.
"""

from temper_placer.explainability.decision import (
    Alternative,
    Decision,
    DecisionPhase,
    DecisionTrace,
    DecisionType,
)


class TestDecisionToDict:
    """Test Decision.to_dict() serialization."""

    def test_to_dict_basic(self):
        d = Decision(
            subject="Q1",
            value=(10.0, 20.0),
            reason="test decision",
            constraint_refs=["thermal.Q1"],
            phase=DecisionPhase.GEOMETRIC,
            decision_type=DecisionType.POSITION_UPDATE,
        )
        result = d.to_dict()
        assert result["subject"] == "Q1"
        assert result["value"] == (10.0, 20.0)
        assert result["reason"] == "test decision"
        assert result["constraint_refs"] == ["thermal.Q1"]
        assert result["phase"] == "geometric"
        assert result["decision_type"] == "position_update"

    def test_to_dict_with_alternatives(self):
        alt = Alternative(
            value=(50.0, 10.0),
            rejection_reason="Violates clearance",
            constraint_violated="clearance.hv_lv",
        )
        d = Decision(
            subject="Q1",
            value=(45.0, 12.0),
            reason="chosen",
            alternatives=[alt],
        )
        result = d.to_dict()
        assert len(result["alternatives"]) == 1
        assert result["alternatives"][0]["constraint_violated"] == "clearance.hv_lv"


class TestDecisionTraceQuery:
    """Test DecisionTrace query methods."""

    def _make_trace(self):
        trace = DecisionTrace()
        trace.add(Decision(subject="Q1", phase=DecisionPhase.GEOMETRIC,
                           decision_type=DecisionType.POSITION_UPDATE,
                           reason="placed Q1", constraint_refs=["thermal.Q1"]))
        trace.add(Decision(subject="Q2", phase=DecisionPhase.GEOMETRIC,
                           decision_type=DecisionType.POSITION_UPDATE,
                           reason="placed Q2", constraint_refs=["spacing.Q1_Q2"]))
        trace.add(Decision(subject="Q1", phase=DecisionPhase.ROUTING,
                           decision_type=DecisionType.ROTATION,
                           reason="rotated Q1"))
        trace.finalize(positions={"Q1": (10, 20), "Q2": (30, 40)})
        return trace

    def test_query_subject(self):
        trace = self._make_trace()
        results = trace.query_subject("Q1")
        assert len(results) == 2
        assert all(d.subject == "Q1" for d in results)

    def test_query_phase(self):
        trace = self._make_trace()
        results = trace.query_phase(DecisionPhase.GEOMETRIC)
        assert len(results) == 2

    def test_query_type(self):
        trace = self._make_trace()
        results = trace.query_type(DecisionType.ROTATION)
        assert len(results) == 1
        assert results[0].reason == "rotated Q1"

    def test_query_constraint(self):
        trace = self._make_trace()
        results = trace.query_constraint("thermal.Q1")
        assert len(results) == 1
        assert results[0].subject == "Q1"

    def test_finalize(self):
        trace = DecisionTrace()
        trace.finalize(positions={"A": (0, 0)}, metrics={"loss": 0.5})
        assert trace.final_positions == {"A": (0, 0)}
        assert trace.final_metrics == {"loss": 0.5}
        assert trace.end_time is not None

    def test_to_dict(self):
        trace = self._make_trace()
        d = trace.to_dict()
        assert d["run_id"] == trace.run_id
        assert len(d["decisions"]) == 3
        assert "Q1" in d["final_positions"]

    def test_summary(self):
        trace = self._make_trace()
        s = trace.summary()
        assert isinstance(s, dict)

    def test_why(self):
        trace = self._make_trace()
        explanation = trace.why("Q1")
        assert isinstance(explanation, str)
        assert "Q1" in explanation

    def test_why_not(self):
        trace = DecisionTrace()
        trace.add(Decision(subject="Q1", value=(10, 20), reason="chosen",
                           alternatives=[
                               Alternative(value=(50, 10),
                                           rejection_reason="Too far from anchor",
                                           constraint_violated="proximity.Q1")
                           ]))
        result = trace.why_not("Q1", (50, 10))
        assert isinstance(result, str)

    def test_history(self):
        trace = DecisionTrace()
        trace.add(Decision(subject="Q1", value=(10, 20), reason="first"))
        trace.add(Decision(subject="Q1", value=(15, 25), previous_value=(10, 20),
                           reason="second"))
        h = trace.history("Q1")
        assert len(h) == 2
