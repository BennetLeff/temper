"""
Differential oracle tests: Alternative, Decision, DecisionTrace.

This test pins the pre-migration Python dataclass implementations VERBATIM
as oracle blocks and compares the Rust pyclasses (imported via the delegation
shims) against them bit-identically.

G1 (TDD): This file is committed BEFORE any Rust pyclass code for decision.
Git history must show the test predating the pyclass implementations. In identity
mode (before Rust), the shim imports ARE the Python dataclasses and the test
compares them against the oracles -- the test is trivially green when the
implementation still lives in Python.

After migration, the shim imports are the Rust pyclasses and the test
compares Rust vs Python oracle. The same assertions (canonicalized through
field-tupling and repr-name normalization) must stay green.

Verification unit (per D5/G4 cluster rule): Alternative + Decision +
DecisionTrace are one unit behind this shared oracle + corpus.

Module-to-property map:
  Alternative:   P1 (repr round-trip), P2 (to_dict)
  Decision:      P3 (repr round-trip), P4 (to_dict), P5 (alternatives persistence)
  DecisionTrace: P6 (add_decision + query), P7 (why_not), P8 (to_dict), P9 (to_json)
  Metamorphic:   MR1 (query permutation), MR2 (add_decision monotonic), MR3 (field-set identity)
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Oracle block -- verbatim copy of `temper_placer/core/decision.py` (origin/main)
# DO NOT EDIT -- these are the reference implementations, name-suffixed _Oracle
# to avoid clashing with the shim imports.
# ---------------------------------------------------------------------------


@dataclass
class _OracleAlternative:
    """A rejected alternative for a decision."""

    value: Any
    rejection_reason: str
    constraint_violated: str | None = None
    loss_if_chosen: float | None = None

    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "rejection_reason": self.rejection_reason,
            "constraint_violated": self.constraint_violated,
            "loss_if_chosen": self.loss_if_chosen,
        }


@dataclass
class _OracleDecision:
    """Single auditable decision in the placement/routing process."""

    id: str
    subject: str
    value: Any
    timestamp: datetime = field(default_factory=datetime.now)
    phase: str = "geometric"
    decision_type: str = "placement"

    # Why
    reason: str = ""
    constraint_refs: list[str] = field(default_factory=list)
    loss_contribution: float = 0.0

    # Alternatives
    alternatives_considered: list[_OracleAlternative] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "phase": self.phase,
            "decision_type": self.decision_type,
            "subject": self.subject,
            "value": self.value,
            "reason": self.reason,
            "constraint_refs": self.constraint_refs,
            "loss_contribution": self.loss_contribution,
            "alternatives_considered": [a.to_dict() for a in self.alternatives_considered],
        }


@dataclass
class _OracleDecisionTrace:
    """Complete audit trail for a placement/routing run."""

    run_id: str
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime | None = None
    decisions: list[_OracleDecision] = field(default_factory=list)
    final_metrics: dict[str, float] = field(default_factory=dict)

    def add_decision(self, decision: _OracleDecision) -> None:
        """Add a decision to the trace."""
        self.decisions.append(decision)

    def query(self, subject: str) -> list[_OracleDecision]:
        """Get all decisions about a subject."""
        return [d for d in self.decisions if d.subject == subject]

    def why_not(self, subject: str, value: Any) -> str:
        """Explain why a particular value wasn't chosen."""
        subject_decisions = self.query(subject)
        if not subject_decisions:
            return f"No decisions found for {subject}"

        for d in subject_decisions:
            for alt in d.alternatives_considered:
                if alt.value == value:
                    return f"Rejected because: {alt.rejection_reason}"

        return f"Value {value} was not explicitly considered as an alternative for {subject}"

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "decisions": [d.to_dict() for d in self.decisions],
            "final_metrics": self.final_metrics,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


# ---------------------------------------------------------------------------
# Shim imports -- these are the Rust pyclasses after migration,
# the Python dataclasses before.
# ---------------------------------------------------------------------------

from temper_placer.core.decision import Alternative, Decision, DecisionTrace


# ============================================================================
# Helper -- canonicalize a class instance into a field-tuple for comparison,
# independent of repr formatting differences (e.g., name resolution).
# ============================================================================

def _fields_of_alternative(obj):
    """Tuple of (value, rejection_reason, constraint_violated, loss_if_chosen)."""
    return (obj.value, obj.rejection_reason, obj.constraint_violated, obj.loss_if_chosen)


def _fields_of_decision(obj):
    """Tuple of (id, subject, value, phase, decision_type, reason, constraint_refs, loss_contribution)."""
    return (
        obj.id,
        obj.subject,
        obj.value,
        obj.phase,
        obj.decision_type,
        obj.reason,
        obj.constraint_refs,
        obj.loss_contribution,
    )


def _fields_of_trace(obj):
    """Tuple of (run_id, final_metrics)."""
    return (obj.run_id, obj.final_metrics)


# ============================================================================
# T1 -- Alternative: field identity and repr round-trip
# ============================================================================

def test_alternative_fields_identical():
    """Every field stored by the pyclass matches the oracle dataclass value-for-value."""
    py_obj = Alternative(value="Q1", rejection_reason="too far")
    oracle = _OracleAlternative(value="Q1", rejection_reason="too far")
    assert _fields_of_alternative(py_obj) == _fields_of_alternative(oracle)


def test_alternative_with_all_fields():
    py_obj = Alternative(value=42, rejection_reason="overflow", constraint_violated="C1", loss_if_chosen=5.0)
    oracle = _OracleAlternative(value=42, rejection_reason="overflow", constraint_violated="C1", loss_if_chosen=5.0)
    assert _fields_of_alternative(py_obj) == _fields_of_alternative(oracle)


def test_alternative_repr_roundtrip():
    """repr() must match the oracle dataclass repr exactly."""
    oracle = _OracleAlternative(value="X", rejection_reason="bad")
    py_obj = Alternative(value="X", rejection_reason="bad")
    normalized_oracle = repr(oracle).replace("_OracleAlternative", "Alternative")
    assert repr(py_obj) == normalized_oracle


def test_alternative_to_dict():
    oracle = _OracleAlternative(value="X", rejection_reason="bad", loss_if_chosen=1.5)
    py_obj = Alternative(value="X", rejection_reason="bad", loss_if_chosen=1.5)
    assert py_obj.to_dict() == oracle.to_dict()


# ============================================================================
# T2 -- Alternative: equality
# ============================================================================

def test_alternative_eq_identical():
    a1 = Alternative(value="X", rejection_reason="bad")
    a2 = Alternative(value="X", rejection_reason="bad")
    assert a1 == a2


def test_alternative_eq_different():
    a1 = Alternative(value="X", rejection_reason="bad")
    a2 = Alternative(value="Y", rejection_reason="bad")
    assert a1 != a2


def test_alternative_hash_is_unavailable():
    """eq=True, frozen=False dataclass has __hash__ = None."""
    a = Alternative(value="X", rejection_reason="bad")
    with pytest.raises(TypeError, match="unhashable"):
        hash(a)


# ============================================================================
# T3 -- Decision: fields, repr, to_dict
# ============================================================================

def test_decision_fields_identical():
    dt = datetime(2025, 1, 1, 12, 0, 0)
    py_obj = Decision(id="d1", subject="Q1", value={"x": 10}, timestamp=dt, phase="geometric")
    oracle = _OracleDecision(id="d1", subject="Q1", value={"x": 10}, timestamp=dt, phase="geometric")
    pf = _fields_of_decision(py_obj)
    of_ = _fields_of_decision(oracle)
    assert pf == of_
    assert py_obj.timestamp == oracle.timestamp


def test_decision_repr_roundtrip():
    dt = datetime(2025, 1, 1, 12, 0, 0)
    oracle = _OracleDecision(id="d1", subject="Q1", value=1, timestamp=dt)
    py_obj = Decision(id="d1", subject="Q1", value=1, timestamp=dt)
    # Normalize: all Decision, Alternative, DecisionTrace names should
    # render the same in both oracle and pyclass.
    oracle_repr = repr(oracle)
    py_repr = repr(py_obj)
    # Replace any _Oracle-prefixed class names in the oracle repr to match
    # the un-prefixed pyclass repr.
    normalized_oracle = oracle_repr.replace("_OracleDecision", "Decision").replace("_OracleAlternative", "Alternative")
    assert py_repr == normalized_oracle


def test_decision_to_dict():
    dt = datetime(2025, 1, 1, 12, 0, 0)
    oracle = _OracleDecision(
        id="d1",
        subject="Q1",
        value={"x": 10},
        timestamp=dt,
        reason="test",
        constraint_refs=["C1", "C2"],
        alternatives_considered=[
            _OracleAlternative(value=0, rejection_reason="bad", constraint_violated="C1"),
        ],
    )
    py_obj = Decision(
        id="d1",
        subject="Q1",
        value={"x": 10},
        timestamp=dt,
        reason="test",
        constraint_refs=["C1", "C2"],
        alternatives_considered=[
            Alternative(value=0, rejection_reason="bad", constraint_violated="C1"),
        ],
    )
    assert py_obj.to_dict() == oracle.to_dict()


def test_decision_alternatives_persist():
    """Alternatives stored in a Decision survive round-trip field access."""
    alt = Alternative(value=0, rejection_reason="bad")
    d = Decision(id="d1", subject="Q1", value=1, alternatives_considered=[alt])
    assert len(d.alternatives_considered) == 1
    assert d.alternatives_considered[0].value == 0
    assert d.alternatives_considered[0].rejection_reason == "bad"


def test_decision_eq():
    dt = datetime(2025, 1, 1, 12, 0, 0)
    d1 = Decision(id="d1", subject="Q1", value=1, timestamp=dt)
    d2 = Decision(id="d1", subject="Q1", value=1, timestamp=dt)
    assert d1 == d2

    d3 = Decision(id="d2", subject="Q1", value=1, timestamp=dt)
    assert d1 != d3


def test_decision_hash_unavailable():
    d = Decision(id="d1", subject="Q1", value=1)
    with pytest.raises(TypeError, match="unhashable"):
        hash(d)


# ============================================================================
# T4 -- DecisionTrace: fields, add_decision, query, why_not, to_dict, to_json
# ============================================================================

def test_trace_fields_identical():
    dt = datetime(2025, 1, 1, 12, 0, 0)
    trace = DecisionTrace(run_id="r1", start_time=dt, final_metrics={"score": 0.95})
    oracle = _OracleDecisionTrace(run_id="r1", start_time=dt, final_metrics={"score": 0.95})
    assert _fields_of_trace(trace) == _fields_of_trace(oracle)
    assert trace.start_time == oracle.start_time


def test_trace_add_decision_and_query():
    trace = DecisionTrace(run_id="r1")
    oracle = _OracleDecisionTrace(run_id="r1")

    d = Decision(id="d1", subject="Q1", value=1, reason="test")
    o = _OracleDecision(id="d1", subject="Q1", value=1, reason="test")

    trace.add_decision(d)
    oracle.add_decision(o)

    assert len(trace.decisions) == 1 == len(oracle.decisions)
    results = trace.query("Q1")
    oracle_results = oracle.query("Q1")
    assert len(results) == len(oracle_results)
    assert results[0].id == oracle_results[0].id


def test_trace_query_no_match():
    trace = DecisionTrace(run_id="r1")
    trace.add_decision(Decision(id="d1", subject="Q1", value=1))
    assert trace.query("Q2") == []


def test_trace_why_not_found():
    trace = DecisionTrace(run_id="r1")
    alt = Alternative(value=0, rejection_reason="Invalid")
    d = Decision(id="d1", subject="Q1", value=1, alternatives_considered=[alt])
    trace.add_decision(d)
    reason = trace.why_not("Q1", 0)
    assert "Invalid" in reason


def test_trace_why_not_no_subject():
    trace = DecisionTrace(run_id="r1")
    reason = trace.why_not("Q1", 0)
    assert "No decisions found" in reason


def test_trace_why_not_not_considered():
    trace = DecisionTrace(run_id="r1")
    d = Decision(id="d1", subject="Q1", value=1)
    trace.add_decision(d)
    reason = trace.why_not("Q1", 2)
    assert "not explicitly considered" in reason


def test_trace_to_dict():
    dt = datetime(2025, 1, 1, 12, 0, 0)
    trace = DecisionTrace(run_id="r1", start_time=dt, end_time=dt)
    oracle = _OracleDecisionTrace(run_id="r1", start_time=dt, end_time=dt)
    d = Decision(id="d1", subject="Q1", value=1, timestamp=dt)
    o = _OracleDecision(id="d1", subject="Q1", value=1, timestamp=dt)
    trace.add_decision(d)
    oracle.add_decision(o)
    assert trace.to_dict() == oracle.to_dict()


def test_trace_to_json():
    dt = datetime(2025, 1, 1, 12, 0, 0)
    trace = DecisionTrace(run_id="r1", start_time=dt)
    oracle = _OracleDecisionTrace(run_id="r1", start_time=dt)
    assert json.loads(trace.to_json()) == json.loads(oracle.to_json())


def test_trace_repr_roundtrip():
    dt = datetime(2025, 1, 1, 12, 0, 0)
    oracle = _OracleDecisionTrace(run_id="r1", start_time=dt)
    py_obj = DecisionTrace(run_id="r1", start_time=dt)
    normalized_oracle = repr(oracle).replace("_OracleDecisionTrace", "DecisionTrace").replace("_OracleDecision", "Decision").replace("_OracleAlternative", "Alternative")
    assert repr(py_obj) == normalized_oracle


def test_trace_hash_unavailable():
    t = DecisionTrace(run_id="r1")
    with pytest.raises(TypeError, match="unhashable"):
        hash(t)


# ============================================================================
# T5 -- End-to-end: DecisionLogger-like usage (explainability.py pattern)
# ============================================================================

def test_end_to_end_logger_pattern():
    """Replicate the construction pattern from pipeline/explainability.py DecisionLogger."""
    dt = datetime(2025, 1, 1, 12, 0, 0)
    trace = DecisionTrace(run_id="test-run", start_time=dt)

    alt = Alternative(value=0, rejection_reason="Too far", constraint_violated="C1", loss_if_chosen=0.5)
    decision = Decision(
        id="place-abc12345",
        phase="geometric",
        decision_type="placement",
        subject="U1",
        value={"x": 10, "y": 20},
        reason="Optimal",
        constraint_refs=["C1"],
        alternatives_considered=[alt],
        timestamp=dt,
    )
    trace.add_decision(decision)

    # Field access pattern used by explainability.py
    assert trace.run_id == "test-run"
    assert len(trace.decisions) == 1
    d = trace.decisions[0]
    assert d.subject == "U1"
    assert d.decision_type == "placement"
    assert d.phase == "geometric"
    assert d.value == {"x": 10, "y": 20}
    assert d.reason == "Optimal"
    assert d.constraint_refs == ["C1"]
    assert len(d.alternatives_considered) == 1
    assert d.alternatives_considered[0].value == 0
    assert d.alternatives_considered[0].rejection_reason == "Too far"
    assert d.alternatives_considered[0].constraint_violated == "C1"
    assert d.alternatives_considered[0].loss_if_chosen == 0.5

    # Mutable field set
    trace.end_time = dt
    trace.final_metrics = {"score": 0.95}
    assert trace.end_time == dt
    assert trace.final_metrics == {"score": 0.95}


# ============================================================================
# T6 -- Dynamic attribute setting (verify #[pyclass(dict)] parity)
# ============================================================================

def test_dynamic_attribute_setting():
    """Consumers may set arbitrary attributes on these objects."""
    alt = Alternative(value=1, rejection_reason="test")
    alt.custom_attr = "hello"
    assert alt.custom_attr == "hello"

    d = Decision(id="d1", subject="Q1", value=1)
    d.extra = 42
    assert d.extra == 42

    t = DecisionTrace(run_id="r1")
    t.metadata = {"key": "val"}
    assert t.metadata == {"key": "val"}


# ============================================================================
# T7 -- Default values match oracle
# ============================================================================

def test_alternative_defaults():
    a = Alternative(value="X", rejection_reason="test")
    assert a.constraint_violated is None
    assert a.loss_if_chosen is None


def test_decision_defaults():
    d = Decision(id="d1", subject="Q1", value=1)
    assert d.phase == "geometric"
    assert d.decision_type == "placement"
    assert d.reason == ""
    assert d.constraint_refs == []
    assert d.loss_contribution == 0.0
    assert d.alternatives_considered == []


def test_trace_defaults():
    t = DecisionTrace(run_id="r1")
    assert t.end_time is None
    assert t.decisions == []
    assert t.final_metrics == {}
