
from temper_placer.core.decision import Alternative, Decision, DecisionTrace


def test_decision_trace_serialization():
    trace = DecisionTrace(run_id="test-run")

    decision = Decision(
        id="d1",
        subject="Q1",
        value={"x": 10, "y": 20},
        reason="Test",
        alternatives_considered=[
            Alternative(value={"x": 0, "y": 0}, rejection_reason="Too far")
        ]
    )

    trace.add_decision(decision)

    json_data = trace.to_json()
    assert "test-run" in json_data
    assert "Q1" in json_data
    assert "Too far" in json_data

def test_decision_trace_query():
    trace = DecisionTrace(run_id="test-run")
    trace.add_decision(Decision(id="d1", subject="Q1", value=1))
    trace.add_decision(Decision(id="d2", subject="Q2", value=2))

    results = trace.query("Q1")
    assert len(results) == 1
    assert results[0].id == "d1"

def test_why_not():
    trace = DecisionTrace(run_id="test-run")
    decision = Decision(
        id="d1",
        subject="Q1",
        value=1,
        alternatives_considered=[
            Alternative(value=0, rejection_reason="Invalid")
        ]
    )
    trace.add_decision(decision)

    reason = trace.why_not("Q1", 0)
    assert "Invalid" in reason

    reason = trace.why_not("Q1", 2)
    assert "not explicitly considered" in reason
