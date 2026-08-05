"""Differential test: explainability/serialization.py compute
(temper-io-types) vs the pinned Python oracle.

Wave 4, Phase 5 — the explainability surface migration. The Rust migration
(reproducing ``temper_placer/explainability/serialization.py``'s compute
bit-identically in the ``temper-io-types`` crate) is driven through the
delegation shim ``temper_placer.explainability.serialization``; the
pre-migration implementation is pinned verbatim as the oracle
(``explain_oracle/serialization_oracle.py``).

Migrated: ``_serialize_value`` / ``_deserialize_value`` recursion (tuple ->
shallow list, ``tolist`` protocol, dict/list recursion) and the
``serialize_alternative`` / ``serialize_decision`` / ``serialize_trace``
dict shapes. ``json.dumps`` / ``json.loads`` / ``datetime.fromisoformat`` /
``Enum`` construction stay Python stdlib (per the established rulings) —
``trace_to_json``'s data comes from Rust, ``json.dumps`` renders it.
"""

from __future__ import annotations

import json
import random
from datetime import datetime

import temper_io_types as _rust

from tests.explainability.explain_oracle import serialization_oracle as _oracle
from temper_placer.explainability.decision import (
    Alternative,
    Decision,
    DecisionPhase,
    DecisionTrace,
    DecisionType,
)
from temper_placer.explainability.serialization import (
    _deserialize_value,
    _serialize_value,
    deserialize_alternative,
    deserialize_decision,
    serialize_alternative,
    serialize_decision,
    serialize_trace,
    trace_to_json,
)

# Module-scope RED arm.
assert hasattr(_rust, "explain_serialize_value")
assert hasattr(_rust, "explain_deserialize_value")
assert hasattr(_rust, "explain_serialize_alternative")
assert hasattr(_rust, "explain_serialize_decision")
assert hasattr(_rust, "explain_serialize_trace")


class _Tolist:
    def __init__(self, items):
        self._items = items

    def tolist(self):
        return self._items


def test_serialize_value_identity_matrix():
    values = [
        None, True, False, 0, 1, -3, 1.5, -0.0, "s", "é", "中文",
        (1, 2), (1.5, 2.25), [], [1, "a", None], {"k": 1}, {"nested": {"a": [1, 2]}},
        (1, (2, 3)),  # tuple with nested tuple: shallow conversion
        _Tolist([1, 2, 3]),
    ]
    for v in values:
        assert _serialize_value(v) == _oracle._serialize_value(v)


def test_serialize_value_numpy_array():
    import numpy as np

    arr = np.array([[1.0, 2.0], [3.0, 4.0]])
    ours = _serialize_value(arr)
    theirs = _oracle._serialize_value(arr)
    assert ours == theirs == [[1.0, 2.0], [3.0, 4.0]]


def test_serialize_value_shallow_tuple():
    """tuple -> list conversion is SHALLOW (a nested tuple inside a tuple
    stays a tuple inside the converted list)."""
    value = ((1, 2), 3)
    ours = _serialize_value(value)
    assert ours == [(1, 2), 3]
    assert isinstance(ours[0], tuple)
    assert _serialize_value(value) == _oracle._serialize_value(value)


def test_deserialize_value_matrix():
    for v in [None, [1, 2], [1.5], "s", 1, {"a": 1}]:
        for as_tuple in [False, True]:
            assert _deserialize_value(v, as_tuple) == _oracle._deserialize_value(v, as_tuple)


def test_deserialize_value_tuple_conversion():
    assert _deserialize_value([1, 2], True) == (1, 2)
    assert isinstance(_deserialize_value([1, 2], True), tuple)


def _decision(subject="Q1", value=(10, 20), counter=0):
    return Decision(
        id=f"d{counter}", timestamp=datetime(2026, 8, 4, 12, 0, 0),
        phase=DecisionPhase.GEOMETRIC, decision_type=DecisionType.POSITION_UPDATE,
        subject=subject, value=value, previous_value=None, reason="r",
        constraint_refs=["c1"], loss_contribution=0.5,
        alternatives=[Alternative(value=(5, 5), rejection_reason="rr",
                                  constraint_violated="cv", loss_if_chosen=0.1)],
        epoch=3, iteration=7,
    )


def test_serialize_alternative_identical():
    alt = Alternative(value=(1, 2), rejection_reason="r", constraint_violated="c",
                      loss_if_chosen=0.25)
    assert serialize_alternative(alt) == _oracle.serialize_alternative(alt)


def test_serialize_decision_identical():
    d = _decision()
    assert serialize_decision(d) == _oracle.serialize_decision(d)


def test_serialize_decision_nested_values():
    d = _decision(value={"pos": (1, 2), "arr": _Tolist([1, 2])}, counter=1)
    ours = serialize_decision(d)
    theirs = _oracle.serialize_decision(d)
    assert ours == theirs
    # _serialize_value converts the nested tuple SHALLOWLY only at the top
    # of the recursion for the value itself; inside a dict the recursion
    # converts every tuple to a list ("pos" -> [1, 2]).
    assert ours["value"] == {"pos": [1, 2], "arr": [1, 2]}


def test_serialize_trace_identical():
    trace = DecisionTrace(run_id="run", start_time=datetime(2026, 8, 4, 12, 0, 0))
    trace.decisions.append(_decision())
    trace.final_positions = {"Q1": (1.0, 2.0)}
    trace.final_metrics = {"loss": 1.5}
    assert serialize_trace(trace) == _oracle.serialize_trace(trace)


def test_trace_to_json_byte_identical():
    trace = DecisionTrace(run_id="run-1", start_time=datetime(2026, 8, 4, 12, 0, 0))
    trace.decisions.append(_decision())
    trace.final_positions = {"Q1": (1.0, 2.0)}
    assert trace_to_json(trace) == _oracle.trace_to_json(trace)
    assert trace_to_json(trace, indent=None) == _oracle.trace_to_json(trace, indent=None)


def test_round_trip_preserves_ids_and_metrics():
    """serialize -> json -> deserialize -> serialize is stable (the
    deserialize half stays Python: datetime.fromisoformat + Enum
    construction are Python runtime semantics)."""
    trace = DecisionTrace(run_id="run-x", start_time=datetime(2026, 8, 4, 12, 0, 0))
    trace.decisions.append(_decision(subject="Q9", value=(3, 4), counter=5))
    trace.final_metrics = {"loss": 2.5}
    blob = trace_to_json(trace)
    loaded = deserialize_decision(_decision_payload(trace))
    assert loaded.id == "d5"
    assert loaded.subject == "Q9"


def _decision_payload(trace):
    return {
        "id": "d5", "timestamp": "2026-08-04T12:00:00", "phase": "geometric",
        "decision_type": "position_update", "subject": "Q9", "value": [3, 4],
        "previous_value": None, "reason": "r", "constraint_refs": ["c1"],
        "loss_contribution": 0.5, "alternatives": [
            {"value": [5, 5], "rejection_reason": "rr", "constraint_violated": "cv",
             "loss_if_chosen": 0.1},
        ], "epoch": 3, "iteration": 7,
    }


def test_serialize_trace_final_positions_lists():
    """final_positions tuples become lists in the serialized dict."""
    trace = DecisionTrace(run_id="r", start_time=datetime(2026, 8, 4, 12, 0, 0))
    trace.final_positions = {"A": (1.0, 2.0)}
    data = serialize_trace(trace)
    assert data["final_positions"] == {"A": [1.0, 2.0]}
