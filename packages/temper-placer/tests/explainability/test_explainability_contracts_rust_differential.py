"""Differential test (Phase-A U8): the explainability DATA CONTRACTS and the
markdown report generation, migrated to ``temper-orchestration`` pyclasses /
pyfunctions, vs the pinned pre-migration Python oracles.

Wave-4 Phase 5 moved the explainability COMPUTE (why/why_not/history/summary,
serialize dict-shapes, log kernels) into ``temper-io-types`` and left the
dataclasses/enums Python. Phase A U8 (plan ``2026-08-09-001``,
``explainability/{decision,trace,serialization,markdown_report}.py`` row:
``temper-orchestration`` → ``Decision``, ``Trace``, ``MarkdownReport``) moves
the DATA CONTRACTS themselves to Rust pyclasses in ``temper-orchestration``
and ports the markdown report generation (the ``MarkdownReport`` deliverable,
a deterministic-string candidate pinned byte-identical). The oracle is the
verbatim pre-migration module copy (``explain_oracle/decision_oracle.py`` /
``trace_oracle.py`` / ``markdown_report_oracle.py``).

Boundaries (argued in VERIFICATION.md): ``DecisionPhase`` / ``DecisionType``
stay Python Enum classes in ``decision.py`` (member identity, value
construction and class iteration ``list(DecisionPhase)`` are Python runtime
semantics — pyo3 has no metaclass hook, so a pyclass cannot be iterated as a
class); ``uuid``/``datetime`` default factories stay Python runtime semantics
(invoked from the pyclass constructors); the NL-generation kernels
(``why``/``why_not``/``history``/``summary``) and the serialize dict-shapes
stay single-source in ``temper-io-types`` and are called from the pyclass
methods (the pyclass exposes the same attribute surface the kernels read).

The RED arm (anti-vacuity): the shim's types MUST be the temper-orchestration
pyclasses — this file fails at import until the shims collapse.
"""

from __future__ import annotations

import random
from datetime import datetime

import temper_orchestration as _to

from temper_placer.explainability.decision import (
    DecisionPhase,
    DecisionType,
)
from temper_placer.explainability.markdown_report import (
    render_component_report,
    render_markdown_report,
)
from tests.explainability.explain_oracle import (
    decision_oracle as _doracle,
    markdown_report_oracle as _moracle,
    trace_oracle as _toracle,
)

# ---------------------------------------------------------------------------
# RED arm (G1): the shim MUST resolve to the temper-orchestration pyclasses.
# ---------------------------------------------------------------------------
assert _to.Decision.__module__ == "temper_orchestration"
assert _to.DecisionTrace.__module__ == "temper_orchestration"
assert _to.Alternative.__module__ == "temper_orchestration"
assert _to.Trace.__module__ == "temper_orchestration"
assert _to.Entry.__module__ == "temper_orchestration"

_FIXED_DT = datetime(2026, 8, 4, 12, 30, 45)


def _decision_kwargs(subject, value, reason, *, counter=0, phase=None, dtype=None,
                     previous=None, constraint_refs=None, alternatives=None,
                     epoch=None, iteration=None, loss=0.0):
    return dict(
        id=f"d-{subject}-{counter}",
        timestamp=_FIXED_DT,
        phase=phase if phase is not None else DecisionPhase.GEOMETRIC,
        decision_type=dtype if dtype is not None else DecisionType.POSITION_UPDATE,
        subject=subject,
        value=value,
        previous_value=previous,
        reason=reason,
        constraint_refs=constraint_refs if constraint_refs is not None else [],
        loss_contribution=loss,
        alternatives=alternatives if alternatives is not None else [],
        epoch=epoch,
        iteration=iteration,
    )


def _shim_decision(kwargs):
    return _to.Decision(**kwargs)


def _oracle_decision(kwargs):
    return _doracle.Decision(**kwargs)


def _fixture_kwargs_lists():
    rng = random.Random(0xC0FFEE)
    out = [[]]
    for _ in range(20):
        decisions = []
        for counter in range(rng.randint(0, 8)):
            subject = rng.choice(["Q1", "Q2", "U1", "VCC", "R5"])
            value = rng.choice([(rng.uniform(-50, 50), rng.uniform(-50, 50)),
                                rng.randint(0, 270), "L2", None,
                                {"x": 1.5, "y": 2.5, "rotation": 90}])
            alts = [
                _to.Alternative(
                    value=rng.choice([(1, 1), (2, 2), "L1", 90]),
                    rejection_reason=f"reject {rng.randint(1, 9)}",
                    constraint_violated=rng.choice([None, "", "clearance.hv_lv", "thermal.edge"]),
                    loss_if_chosen=rng.choice([None, rng.uniform(0.1, 5.0)]),
                )
                for _ in range(rng.randint(0, 3))
            ]
            decisions.append(_decision_kwargs(
                subject, value, f"because {rng.randint(1, 99)}",
                counter=counter,
                phase=rng.choice(list(DecisionPhase)),
                dtype=rng.choice(list(DecisionType)),
                previous=rng.choice([None, (0, 0)]),
                constraint_refs=rng.sample(["c1", "c2", "c3"], rng.randint(0, 3)),
                alternatives=alts,
                epoch=rng.choice([None, 0, 100]),
                iteration=rng.choice([None, 0, 3]),
                loss=rng.choice([0.0, 0.5, 1.75]),
            ))
        out.append(decisions)
    return out


def _shim_trace(kwargs_lists, **trace_kwargs):
    t = _to.DecisionTrace(run_id="run-u8", start_time=_FIXED_DT, **trace_kwargs)
    for k in kwargs_lists:
        t.decisions.append(_shim_decision(k))
    return t


def _oracle_trace(kwargs_lists, **trace_kwargs):
    t = _doracle.DecisionTrace(run_id="run-u8", start_time=_FIXED_DT, **trace_kwargs)
    for k in kwargs_lists:
        t.decisions.append(_oracle_decision(k))
    return t


# ---------------------------------------------------------------------------
# Construction defaults (uuid/datetime shapes, not values)
# ---------------------------------------------------------------------------

def test_construction_defaults_shape():
    """`Decision()` / `DecisionTrace()` construct with the dataclass defaults:
    uuid-shaped ids, datetimes, default enum members, empty containers."""
    d = _to.Decision()
    od = _doracle.Decision()
    assert len(d.id) == 8 and len(od.id) == 8
    assert isinstance(d.timestamp, datetime) and isinstance(od.timestamp, datetime)
    assert d.phase == DecisionPhase.GEOMETRIC
    assert d.decision_type == DecisionType.POSITION_UPDATE
    assert od.phase == _doracle.DecisionPhase.GEOMETRIC
    assert od.decision_type == _doracle.DecisionType.POSITION_UPDATE
    assert d.subject == od.subject == ""
    assert d.value is None and d.previous_value is None
    assert d.reason == od.reason == ""
    assert d.constraint_refs == [] and d.alternatives == []
    assert d.loss_contribution == od.loss_contribution == 0.0
    assert d.epoch is None and d.iteration is None

    t = _to.DecisionTrace()
    ot = _doracle.DecisionTrace()
    assert len(t.run_id) == 12 and len(ot.run_id) == 12
    assert isinstance(t.start_time, datetime) and isinstance(ot.start_time, datetime)
    assert t.end_time is None and ot.end_time is None
    assert t.config_snapshot == {} and t.decisions == [] and ot.decisions == []
    assert t.final_positions == {} and t.final_metrics == {}


def test_default_factories_are_per_instance():
    """default_factory containers are FRESH per construction (mutating one
    instance's list must not leak into another)."""
    a, b = _to.Decision(), _to.Decision()
    a.constraint_refs.append("x")
    assert b.constraint_refs == []
    ta, tb = _to.DecisionTrace(), _to.DecisionTrace()
    ta.decisions.append(_to.Decision(subject="Q1", value=1, reason="r"))
    assert len(tb.decisions) == 0


# ---------------------------------------------------------------------------
# to_dict parity
# ---------------------------------------------------------------------------

def test_decision_to_dict_byte_identical():
    for kwargs_list in _fixture_kwargs_lists():
        for k in kwargs_list:
            ours = repr(_shim_decision(k).to_dict())
            theirs = repr(_oracle_decision(k).to_dict())
            assert ours == theirs


def test_decision_trace_to_dict_byte_identical():
    for kwargs_list in _fixture_kwargs_lists():
        shim = _shim_trace(kwargs_list)
        oracle = _oracle_trace(kwargs_list)
        assert repr(shim.to_dict()) == repr(oracle.to_dict())


def test_decision_trace_to_dict_end_time_iso():
    shim = _shim_trace([], end_time=datetime(2026, 8, 4, 13, 0, 0))
    oracle = _oracle_trace([], end_time=datetime(2026, 8, 4, 13, 0, 0))
    assert shim.to_dict()["end_time"] == oracle.to_dict()["end_time"] == "2026-08-04T13:00:00"


# ---------------------------------------------------------------------------
# Query methods
# ---------------------------------------------------------------------------

def test_query_methods_identical():
    for kwargs_list in _fixture_kwargs_lists():
        shim = _shim_trace(kwargs_list)
        oracle = _oracle_trace(kwargs_list)
        for phase in list(DecisionPhase):
            assert repr(shim.query_phase(phase)) == repr(oracle.query_phase(phase))
        for dtype in list(DecisionType):
            assert repr(shim.query_type(dtype)) == repr(oracle.query_type(dtype))
        for subject in ["Q1", "VCC", "nobody"]:
            assert repr(shim.query_subject(subject)) == repr(oracle.query_subject(subject))
        for ref in ["c1", "c2", "c3", "thermal.edge"]:
            assert repr(shim.query_constraint(ref)) == repr(oracle.query_constraint(ref))


def test_query_subject_chronological_filter():
    shim = _shim_trace([
        _decision_kwargs("Q1", 1, "a", counter=0),
        _decision_kwargs("Q2", 2, "b", counter=1),
        _decision_kwargs("Q1", 3, "c", counter=2),
    ])
    oracle = _oracle_trace([
        _decision_kwargs("Q1", 1, "a", counter=0),
        _decision_kwargs("Q2", 2, "b", counter=1),
        _decision_kwargs("Q1", 3, "c", counter=2),
    ])
    assert [d.subject for d in shim.query_subject("Q1")] == [d.subject for d in oracle.query_subject("Q1")] == ["Q1", "Q1"]
    assert [d.value for d in shim.query_subject("Q1")] == [d.value for d in oracle.query_subject("Q1")] == [1, 3]


# ---------------------------------------------------------------------------
# finalize
# ---------------------------------------------------------------------------

def test_finalize_identical():
    shim = _shim_trace([])
    oracle = _oracle_trace([])
    positions = {"Q1": (1.0, 2.0)}
    metrics = {"loss": 1.5}
    shim.finalize(positions, metrics)
    oracle.finalize(positions, metrics)
    assert shim.end_time is not None and oracle.end_time is not None
    assert isinstance(shim.end_time, datetime) and isinstance(oracle.end_time, datetime)
    assert shim.final_positions == oracle.final_positions == positions
    assert shim.final_metrics == oracle.final_metrics == metrics


def test_finalize_falsy_positions_skipped():
    """`if positions:` — an empty dict is falsy and does NOT overwrite."""
    shim = _shim_trace([])
    shim.final_positions = {"keep": (1.0, 2.0)}
    shim.finalize({}, {"m": 1.0})
    assert shim.final_positions == {"keep": (1.0, 2.0)}
    assert shim.final_metrics == {"m": 1.0}


# ---------------------------------------------------------------------------
# repr parity (dataclass repr rendered by CPython repr of each field)
# ---------------------------------------------------------------------------

def test_repr_byte_identical():
    for kwargs_list in _fixture_kwargs_lists():
        for k in kwargs_list:
            assert repr(_shim_decision(k)) == repr(_oracle_decision(k))
        assert repr(_shim_trace(kwargs_list)) == repr(_oracle_trace(kwargs_list))


def test_alternative_repr_byte_identical():
    alts = [
        _to.Alternative(value=(1, 2), rejection_reason="r", constraint_violated="c", loss_if_chosen=0.25),
        _to.Alternative(value="L1", rejection_reason="rr"),
    ]
    oalts = [
        _doracle.Alternative(value=(1, 2), rejection_reason="r", constraint_violated="c", loss_if_chosen=0.25),
        _doracle.Alternative(value="L1", rejection_reason="rr"),
    ]
    for a, b in zip(alts, oalts):
        assert repr(a) == repr(b)


# ---------------------------------------------------------------------------
# Trace / Entry (the immutable monoid)
# ---------------------------------------------------------------------------

def _shim_entries():
    t = _to.Trace.empty()
    t = t.add("Q1", (1.0, 2.0), "initial")
    t = t.add("Q1", (3.0, 4.0), "thermal")
    t = t.add("Q2", "L2", "routed")
    return t


def _oracle_entries():
    t = _toracle.Trace.empty()
    t = t.add("Q1", (1.0, 2.0), "initial")
    t = t.add("Q1", (3.0, 4.0), "thermal")
    t = t.add("Q2", "L2", "routed")
    return t


def test_trace_construction_and_add_identical():
    shim, oracle = _shim_entries(), _oracle_entries()
    assert len(shim) == len(oracle) == 3
    assert bool(shim) == bool(oracle) is True
    assert repr(shim.entries) == repr(oracle.entries)
    assert repr(shim) == repr(oracle)


def test_trace_monoid_add_identical():
    """Composition + identity law against the oracle."""
    shim, oracle = _shim_entries(), _oracle_entries()
    empty_s, empty_o = _to.Trace.empty(), _toracle.Trace.empty()
    assert len(empty_s) == len(empty_o) == 0
    assert bool(empty_s) == bool(empty_o) is False
    # (a + b) == a + b, and empty() + t == t
    assert repr((empty_s + shim).entries) == repr((empty_o + oracle).entries) == repr(shim.entries)
    assert repr((shim + empty_s).entries) == repr(oracle.entries)


def test_trace_for_subject_identical():
    shim, oracle = _shim_entries(), _oracle_entries()
    assert repr(shim.for_subject("Q1").entries) == repr(oracle.for_subject("Q1").entries)
    assert [e.subject for e in shim.for_subject("Q1").entries] == ["Q1", "Q1"]
    assert len(shim.for_subject("nobody")) == 0


def test_trace_why_identical():
    """Trace.why delegates to the single-source NL-generation kernel in
    temper-io-types; both arms must agree byte-for-byte."""
    shim, oracle = _shim_entries(), _oracle_entries()
    assert shim.why("Q1") == oracle.why("Q1")
    assert shim.why("Q1", 1) == oracle.why("Q1", 1)
    assert shim.why("nobody") == oracle.why("nobody")
    assert shim.why("Q1", 3) == _toracle.Trace(shim.entries).why("Q1", 3)


def test_trace_repr_shapes_pinned():
    assert repr(_to.Trace.empty()) == "Trace(0 entries)"
    e = _to.Trace.empty().add("Q1", (1, 2), "why").entries[0]
    assert repr(e) == repr(_toracle.Entry("Q1", (1, 2), "why"))


# ---------------------------------------------------------------------------
# summary / why / why_not / history through the pyclass
# ---------------------------------------------------------------------------

def test_summary_identical():
    for kwargs_list in _fixture_kwargs_lists():
        shim = _shim_trace(kwargs_list)
        oracle = _oracle_trace(kwargs_list)
        ours = shim.summary()
        theirs = oracle.summary()
        assert _summary_key(ours) == _summary_key(theirs)


def test_summary_aggregation_pins():
    shim = _shim_trace([
        _decision_kwargs("Q1", 1, "r", counter=0, phase=DecisionPhase.GEOMETRIC,
                         dtype=DecisionType.ROTATION),
        _decision_kwargs("Q1", 2, "r", counter=1, phase=DecisionPhase.GEOMETRIC,
                         dtype=DecisionType.ROTATION),
        _decision_kwargs("Q2", 3, "r", counter=2, phase=DecisionPhase.ROUTING,
                         dtype=DecisionType.NET_ORDER),
    ])
    summary = shim.summary()
    assert summary["total_decisions"] == 3
    assert summary["component_count"] == 2
    assert summary["decisions_by_phase"] == {"geometric": 2, "routing": 1}
    assert summary["decisions_by_type"] == {"rotation": 2, "net_order": 1}


def test_why_why_not_history_identical():
    for kwargs_list in _fixture_kwargs_lists():
        shim = _shim_trace(kwargs_list)
        oracle = _oracle_trace(kwargs_list)
        for subject in ["Q1", "VCC", "nobody"]:
            assert shim.why(subject) == oracle.why(subject)
            for value in [(1, 1), (2, 2), "L1", 90, None]:
                assert shim.why_not(subject, value) == oracle.why_not(subject, value)
            ours = shim.history(subject)
            theirs = oracle.history(subject)
            assert len(ours) == len(theirs)
            for (v1, r1), (v2, r2) in zip(ours, theirs):
                assert r1 == r2
                assert _values_equal(v1, v2)


def _values_equal(a, b):
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return list(a) == list(b)
    return a == b


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


# ---------------------------------------------------------------------------
# Markdown report — deterministic-string byte-pin
# ---------------------------------------------------------------------------

def _markdown_trace(kwargs_lists, **trace_kwargs):
    t = _to.DecisionTrace(run_id="run-abc123", start_time=_FIXED_DT, **trace_kwargs)
    for k in kwargs_lists:
        t.decisions.append(_shim_decision(k))
    return t


def _markdown_oracle_trace(kwargs_lists, **trace_kwargs):
    t = _doracle.DecisionTrace(run_id="run-abc123", start_time=_FIXED_DT, **trace_kwargs)
    for k in kwargs_lists:
        t.decisions.append(_oracle_decision(k))
    return t


def _markdown_fixtures():
    rng = random.Random(0xADE1C)
    out = [[]]
    for _ in range(15):
        decisions = []
        for counter in range(rng.randint(0, 7)):
            subject = rng.choice(["Q1", "Q2", "U1", "VCC", "R5"])
            kind = rng.randint(0, 4)
            if kind == 0:
                value = (rng.uniform(-50, 50), rng.uniform(-50, 50))
            elif kind == 1:
                value = (rng.uniform(-50, 50), rng.uniform(-50, 50), rng.choice([0, 90, 180]))
            elif kind == 2:
                value = {"x": rng.uniform(-50, 50), "y": rng.uniform(-50, 50),
                         "rotation": rng.randint(0, 270)}
            elif kind == 3:
                value = rng.choice([1.23456, 90, "L2", None, True])
            else:
                value = rng.choice([(1, 2), (3, 4, 5), "path"])
            decisions.append(_decision_kwargs(
                subject, value, "because " + "y" * rng.randint(3, 90),
                counter=counter,
                phase=rng.choice(list(DecisionPhase)),
                dtype=rng.choice(list(DecisionType)),
                constraint_refs=rng.sample(["c1", "c2"], rng.randint(0, 2)),
                epoch=rng.choice([None, 0, 100]),
            ))
        out.append(decisions)
    return out


def test_render_markdown_byte_identical():
    for kwargs_list in _markdown_fixtures():
        for include_config, include_positions in [(True, True), (True, False),
                                                  (False, True), (False, False)]:
            shim = _markdown_trace(kwargs_list)
            oracle = _markdown_oracle_trace(kwargs_list)
            ours = render_markdown_report(
                shim, include_config=include_config, include_positions=include_positions
            )
            theirs = _moracle.render_markdown_report(
                oracle, include_config=include_config, include_positions=include_positions
            )
            assert ours == theirs


def test_render_component_report_byte_identical():
    for kwargs_list in _markdown_fixtures():
        shim = _markdown_trace(kwargs_list)
        oracle = _markdown_oracle_trace(kwargs_list)
        for subject in ["Q1", "VCC", "nobody"]:
            assert render_component_report(shim, subject) == _moracle.render_component_report(
                oracle, subject
            )


def test_markdown_deterministic_string_golden():
    """The report is a deterministic string: the SAME trace renders
    byte-identically on every call, and a fixed trace pins a fixed golden
    block (the byte-pin the U8 dispatch asks for)."""
    shim = _markdown_trace([
        _decision_kwargs("Q1", (10.0, 20.0), "Initial placement", counter=0),
        _decision_kwargs("Q1", (12.5, 18.0), "Moved for thermal clearance",
                         counter=1, constraint_refs=["thermal.edge"]),
    ], end_time=datetime(2026, 8, 4, 12, 31, 0))
    shim.final_positions = {"Q1": (12.5, 18.0)}
    shim.final_metrics = {"total_loss": 1.25}
    shim.config_snapshot = {"clearance": 0.2}

    oracle_trace = _markdown_oracle_trace([
        _decision_kwargs("Q1", (10.0, 20.0), "Initial placement", counter=0),
        _decision_kwargs("Q1", (12.5, 18.0), "Moved for thermal clearance",
                         counter=1, constraint_refs=["thermal.edge"]),
    ], end_time=datetime(2026, 8, 4, 12, 31, 0))
    oracle_trace.final_positions = {"Q1": (12.5, 18.0)}
    oracle_trace.final_metrics = {"total_loss": 1.25}
    oracle_trace.config_snapshot = {"clearance": 0.2}

    report = render_markdown_report(shim)
    assert report == render_markdown_report(shim)
    assert report == _moracle.render_markdown_report(oracle_trace)
    assert "# Placement Decision Report" in report
    assert "**Run ID**: `run-abc123`" in report
    assert "**Final Value**: (12.5, 18.0)" in report
    assert "thermal.edge" in report


# ---------------------------------------------------------------------------
# serialization round-trip through the pyclasses
# ---------------------------------------------------------------------------

def test_deserialize_roundtrip_through_pyclasses():
    """`deserialize_decision` / `deserialize_trace` construct the pyclasses;
    their attribute surface must match the oracle's round-trip."""
    from temper_placer.explainability.serialization import deserialize_decision as _dd
    from tests.explainability.explain_oracle import serialization_oracle as _soracle

    payload = {
        "id": "d5", "timestamp": "2026-08-04T12:00:00", "phase": "geometric",
        "decision_type": "position_update", "subject": "Q9", "value": [3, 4],
        "previous_value": None, "reason": "r", "constraint_refs": ["c1"],
        "loss_contribution": 0.5, "alternatives": [
            {"value": [5, 5], "rejection_reason": "rr", "constraint_violated": "cv",
             "loss_if_chosen": 0.1},
        ], "epoch": 3, "iteration": 7,
    }
    ours = _dd(payload)
    theirs = _soracle.deserialize_decision(payload)
    assert ours.id == theirs.id == "d5"
    assert ours.subject == theirs.subject == "Q9"
    assert ours.phase == theirs.phase
    assert ours.decision_type == theirs.decision_type
    assert ours.value == theirs.value == [3, 4]
    assert ours.constraint_refs == theirs.constraint_refs == ["c1"]
    assert ours.loss_contribution == theirs.loss_contribution
    assert ours.epoch == theirs.epoch == 3
    assert ours.iteration == theirs.iteration == 7
    assert len(ours.alternatives) == len(theirs.alternatives) == 1
    assert ours.alternatives[0].rejection_reason == theirs.alternatives[0].rejection_reason == "rr"
    assert repr(ours.to_dict()) == repr(theirs.to_dict())
