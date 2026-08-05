"""Differential test: explainability/decision.py compute (temper-io-types)
vs the pinned Python oracle.

Wave 4, Phase 5 — the explainability surface migration. The Rust migration
(reproducing ``temper_placer/explainability/decision.py``'s compute
bit-identically in the ``temper-io-types`` crate) is driven through the
delegation shim ``temper_placer.explainability.decision``; the
pre-migration implementation is pinned verbatim as the oracle
(``explain_oracle/decision_oracle.py``).

The enums and dataclasses stay Python (Enum member identity, dataclass
field access and ``uuid``/``datetime`` defaults are Python runtime
semantics); the migrated compute is ``DecisionTrace.why`` / ``why_not`` /
``history`` / ``summary`` — subject filtering, alternative matching, message
building and aggregation. ``unique_subjects`` in ``summary`` is computed
Python-side because set iteration order is a hash-randomized Python runtime
semantic (the guide's iteration-order trap) — the differential's in-process
arms see the same set order on both sides.

Both arms are driven with IDENTICAL Decision objects (constructed once);
the oracle arm wraps them in the verbatim oracle DecisionTrace whose
methods are the pinned implementation.
"""

from __future__ import annotations

import random
from datetime import datetime

import temper_io_types as _rust

from tests.explainability.explain_oracle import decision_oracle as _oracle
from temper_placer.explainability.decision import (
    Alternative,
    Decision,
    DecisionPhase,
    DecisionTrace,
    DecisionType,
)

# Module-scope RED arm.
assert hasattr(_rust, "explain_decision_trace_why")
assert hasattr(_rust, "explain_decision_trace_why_not")
assert hasattr(_rust, "explain_decision_trace_history")
assert hasattr(_rust, "explain_decision_trace_summary")

_FIXED_DT = datetime(2026, 8, 4, 12, 30, 45)


def _decision(subject, value, reason, *, phase=None, dtype=None, previous=None,
              constraint_refs=None, alternatives=None, epoch=None, iteration=None,
              counter=None):
    return Decision(
        id=f"d-{subject}-{counter if counter is not None else 0}",
        timestamp=_FIXED_DT,
        phase=phase or DecisionPhase.GEOMETRIC,
        decision_type=dtype or DecisionType.POSITION_UPDATE,
        subject=subject,
        value=value,
        previous_value=previous,
        reason=reason,
        constraint_refs=constraint_refs or [],
        alternatives=alternatives or [],
        epoch=epoch,
        iteration=iteration,
    )


def _shim_trace(decisions):
    t = DecisionTrace(run_id="run-1", start_time=_FIXED_DT)
    t.decisions.extend(decisions)
    return t


def _oracle_trace(decisions):
    t = _oracle.DecisionTrace(run_id="run-1", start_time=_FIXED_DT)
    t.decisions.extend(decisions)
    return t


def _fixture_decisions() -> list[list[Decision]]:
    rng = random.Random(0xD3C1510)
    out = [[]]
    # Single.
    out.append([_decision("Q1", (10, 20), "initial", counter=0)])
    for _ in range(25):
        decisions = []
        counter = 0
        for _ in range(rng.randint(0, 8)):
            subject = rng.choice(["Q1", "Q2", "U1", "VCC", "R5"])
            value = rng.choice([(rng.uniform(-50, 50), rng.uniform(-50, 50)),
                                rng.randint(0, 270), "L2", None])
            alts = [
                Alternative(
                    value=rng.choice([(1, 1), (2, 2), "L1", 90]),
                    rejection_reason=f"reject {rng.randint(1, 9)}",
                    constraint_violated=rng.choice([None, "clearance.hv_lv", "thermal.edge"]),
                    loss_if_chosen=rng.choice([None, rng.uniform(0.1, 5.0)]),
                )
                for _ in range(rng.randint(0, 3))
            ]
            decisions.append(_decision(
                subject, value, f"because {rng.randint(1, 99)}",
                phase=rng.choice(list(DecisionPhase)),
                dtype=rng.choice(list(DecisionType)),
                previous=rng.choice([None, (0, 0)]),
                constraint_refs=rng.sample(["c1", "c2", "c3"], rng.randint(0, 3)),
                alternatives=alts,
                epoch=rng.choice([None, 0, 100]),
                iteration=rng.choice([None, 0, 3]),
                counter=counter,
            ))
            counter += 1
        out.append(decisions)
    return out


def test_why_byte_identical():
    for decisions in _fixture_decisions():
        shim_trace = _shim_trace(decisions)
        oracle_trace = _oracle_trace(decisions)
        for subject in ["Q1", "VCC", "nobody"]:
            assert shim_trace.why(subject) == oracle_trace.why(subject)


def test_why_message_shape():
    trace = _shim_trace([_decision("Q1", (10, 20), "initial", counter=0)])
    text = trace.why("Q1")
    assert text.startswith("Q1 is at ")
    assert text.endswith(" because: initial")
    assert "Constraints:" not in text


def test_why_constraint_refs_appended():
    trace = _shim_trace([
        _decision("Q1", (1, 2), "r", constraint_refs=["thermal.Q1", "clearance"], counter=0),
    ])
    assert "(Constraints: thermal.Q1, clearance)" in trace.why("Q1")


def test_why_not_byte_identical():
    for decisions in _fixture_decisions():
        shim_trace = _shim_trace(decisions)
        oracle_trace = _oracle_trace(decisions)
        for subject in ["Q1", "VCC", "nobody"]:
            for value in [(1, 1), (2, 2), "L1", 90, None, [1, 1], "L2", (1, 2)]:
                assert shim_trace.why_not(subject, value) == oracle_trace.why_not(subject, value)


def test_why_not_list_tuple_matching():
    """list and tuple compare equal for alternative matching."""
    trace = _shim_trace([
        _decision("Q1", (9, 9), "r", alternatives=[
            Alternative(value=(5, 5), rejection_reason="too close"),
        ], counter=0),
    ])
    assert "too close" in trace.why_not("Q1", [5, 5])
    assert "No record of" in trace.why_not("Q1", (7, 7))


def test_why_not_loss_formatted_4dp():
    trace = _shim_trace([
        _decision("Q1", (9, 9), "r", alternatives=[
            Alternative(value=(5, 5), rejection_reason="r", loss_if_chosen=1.23456),
        ], counter=0),
    ])
    assert "(Loss if chosen: 1.2346)" in trace.why_not("Q1", (5, 5))


def test_history_byte_identical():
    for decisions in _fixture_decisions():
        shim_trace = _shim_trace(decisions)
        oracle_trace = _oracle_trace(decisions)
        for subject in ["Q1", "VCC", "nobody"]:
            ours = shim_trace.history(subject)
            theirs = oracle_trace.history(subject)
            assert len(ours) == len(theirs)
            for (v1, r1), (v2, r2) in zip(ours, theirs):
                assert r1 == r2
                assert _values_equal(v1, v2)


def _values_equal(a, b):
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return list(a) == list(b)
    return a == b


def test_summary_byte_identical():
    for decisions in _fixture_decisions():
        shim_trace = _shim_trace(decisions)
        oracle_trace = _oracle_trace(decisions)
        ours = shim_trace.summary()
        theirs = oracle_trace.summary()
        assert _summary_key(ours) == _summary_key(theirs)


def _summary_key(s):
    return (
        s["run_id"],
        s["total_decisions"],
        s["component_count"],
        tuple(sorted(s["unique_subjects"])),
        tuple(sorted(s["decisions_by_phase"].items())),
        tuple(sorted(s["decisions_by_type"].items())),
        s["duration_seconds"],
        tuple(sorted(s["final_metrics"].items())),
    )


def test_summary_aggregation_pins():
    trace = _shim_trace([
        _decision("Q1", 1, "r", phase=DecisionPhase.GEOMETRIC, dtype=DecisionType.ROTATION, counter=0),
        _decision("Q1", 2, "r", phase=DecisionPhase.GEOMETRIC, dtype=DecisionType.ROTATION, counter=1),
        _decision("Q2", 3, "r", phase=DecisionPhase.ROUTING, dtype=DecisionType.NET_ORDER, counter=2),
    ])
    summary = trace.summary()
    assert summary["total_decisions"] == 3
    assert summary["component_count"] == 2
    assert summary["decisions_by_phase"] == {"geometric": 2, "routing": 1}
    assert summary["decisions_by_type"] == {"rotation": 2, "net_order": 1}


def test_summary_duration_none_when_not_finalized():
    trace = _shim_trace([_decision("Q1", 1, "r", counter=0)])
    assert trace.summary()["duration_seconds"] is None


def test_summary_duration_after_finalize():
    trace = _shim_trace([_decision("Q1", 1, "r", counter=0)])
    trace.end_time = datetime(2026, 8, 4, 12, 31, 0)
    assert trace.summary()["duration_seconds"] == 15.0
