"""Differential test: explainability/markdown_report.py compute
(temper-io-types) vs the pinned Python oracle.

Wave 4, Phase 5 — the explainability surface migration. The Rust migration
(reproducing ``temper_placer/explainability/markdown_report.py``
bit-identically in the ``temper-io-types`` crate) is driven through the
delegation shim ``temper_placer.explainability.markdown_report``; the
pre-migration implementation is pinned verbatim as the oracle
(``explain_oracle/markdown_report_oracle.py``).

The whole rendering pipeline (header, summary metrics, phase/type tables,
per-component sections, final positions, config snapshot) is Rust. Reports
are compared byte-identical. Timestamp ``strftime`` stays Python (the shim
pre-formats the two timestamp strings); everything downstream is Rust.
"""

from __future__ import annotations

import random
from datetime import datetime

import temper_io_types as _rust

from temper_placer.explainability.decision import (
    Alternative,
    Decision,
    DecisionPhase,
    DecisionTrace,
    DecisionType,
)
from temper_placer.explainability.markdown_report import (
    render_component_report,
    render_markdown_report,
)
from tests.explainability.explain_oracle import markdown_report_oracle as _oracle

# Module-scope RED arm.
assert hasattr(_rust, "explain_render_markdown_report")
assert hasattr(_rust, "explain_render_component_report")

_FIXED_DT = datetime(2026, 8, 4, 12, 30, 45)


def _decision(subject, value, reason, *, phase=None, dtype=None, constraint_refs=None,
              alternatives=None, epoch=None, counter=0):
    return Decision(
        id=f"d-{counter}",
        timestamp=_FIXED_DT,
        phase=phase or DecisionPhase.GEOMETRIC,
        decision_type=dtype or DecisionType.POSITION_UPDATE,
        subject=subject,
        value=value,
        reason=reason,
        constraint_refs=constraint_refs or [],
        alternatives=alternatives or [],
        epoch=epoch,
    )


def _trace(decisions, *, metrics=None, positions=None, config=None, end_time=None):
    t = DecisionTrace(run_id="run-abc123", start_time=_FIXED_DT, end_time=end_time)
    t.decisions.extend(decisions)
    if metrics:
        t.final_metrics = metrics
    if positions:
        t.final_positions = positions
    if config:
        t.config_snapshot = config
    return t


def _fixture_traces() -> list[DecisionTrace]:
    rng = random.Random(0xADE1C)
    out = []
    # Empty trace.
    out.append(_trace([]))
    # Trace with end time (duration line).
    out.append(_trace([], end_time=datetime(2026, 8, 4, 12, 35, 0)))
    # Metrics, positions, config.
    out.append(_trace(
        [],
        metrics={"total_loss": 1.25, "overlap": 0.0, "count": 3, "ok": True},
        positions={"Q1": (10.0, 20.0), "R2": (-1.5, 2.25)},
        config={"clearance": 0.2, "iterations": 1000, "enabled": True, "name": "main"},
    ))
    # Multi-subject decisions.
    for _ in range(20):
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
            alts = [
                Alternative(
                    value=rng.choice([(1, 1), 45, "L1"]),
                    rejection_reason="rejected " + "x" * rng.randint(5, 80),
                    constraint_violated=rng.choice([None, "", "clearance.hv_lv"]),
                )
                for _ in range(rng.randint(0, 3))
            ]
            decisions.append(_decision(
                subject, value, "because " + "y" * rng.randint(3, 90),
                phase=rng.choice(list(DecisionPhase)),
                dtype=rng.choice(list(DecisionType)),
                constraint_refs=rng.sample(["c1", "c2"], rng.randint(0, 2)),
                alternatives=alts,
                epoch=rng.choice([None, 0, 100]),
                counter=counter,
            ))
        t = _trace(decisions)
        if rng.random() < 0.5:
            t.final_metrics = {"loss": rng.uniform(0, 10)}
        if rng.random() < 0.4:
            t.final_positions = {f"C{i}": (rng.uniform(-10, 10), rng.uniform(-10, 10))
                                 for i in range(rng.randint(1, 4))}
        if rng.random() < 0.4:
            t.config_snapshot = {f"k{i}": rng.randint(0, 100) for i in range(rng.randint(0, 4))}
        if rng.random() < 0.3:
            t.end_time = datetime(2026, 8, 4, 13, 0, 0)
        out.append(t)
    return out


def test_render_markdown_byte_identical():
    for trace in _fixture_traces():
        for include_config, include_positions in [(True, True), (True, False),
                                                  (False, True), (False, False)]:
            ours = render_markdown_report(
                trace, include_config=include_config, include_positions=include_positions
            )
            theirs = _oracle.render_markdown_report(
                trace, include_config=include_config, include_positions=include_positions
            )
            assert ours == theirs


def test_render_component_report_byte_identical():
    for trace in _fixture_traces():
        for subject in ["Q1", "VCC", "nobody"]:
            ours = render_component_report(trace, subject)
            theirs = _oracle.render_component_report(trace, subject)
            assert ours == theirs


def test_header_lines_pinned():
    trace = _fixture_traces()[0]
    text = render_markdown_report(trace)
    assert text.startswith("# Placement Decision Report")
    assert "**Run ID**: `run-abc123`" in text
    assert "**Started**: 2026-08-04 12:30:45" in text
    assert "**Components**: 0" in text


def test_duration_line_pinned():
    trace = _trace([], end_time=datetime(2026, 8, 4, 12, 35, 0))
    text = render_markdown_report(trace)
    assert "**Ended**: 2026-08-04 12:35:00" in text
    assert "**Duration**: 255.0 seconds" in text


def test_value_formatting_pins():
    """Position tuples, position+rotation, dict, float, bool, None."""
    trace = _trace([
        _decision("A", (10.0, 20.0), "r", counter=0),
        _decision("B", (1.5, 2.5, 90), "r", counter=1),
        _decision("C", {"x": 3.25, "y": 4.75, "rotation": 180}, "r", counter=2),
        _decision("D", 1.23456, "r", counter=3),
        _decision("E", None, "r", counter=4),
        _decision("F", True, "r", counter=5),
    ])
    text = render_component_report(trace, "A")
    assert "**Final Value**: (10.0, 20.0)" in text
    text = render_component_report(trace, "B")
    assert "**Final Value**: (1.5, 2.5) @ 90°" in text
    text = render_component_report(trace, "C")
    assert "**Final Value**: (3.2, 4.8) @ 180°" in text
    text = render_component_report(trace, "D")
    assert "**Final Value**: 1.23" in text
    text = render_component_report(trace, "E")
    assert "**Final Value**: -" in text
    text = render_component_report(trace, "F")
    assert "**Final Value**: True" in text


def test_truncation_pins():
    long_reason = "x" * 100
    trace = _trace([_decision("Q1", (1, 2), long_reason, counter=0)])
    text = render_component_report(trace, "Q1")
    assert "**Final Reason**: " + "x" * 57 + "..." in text
    assert "x" * 100 not in text


def test_decision_history_table_indexing():
    """The '# ' column starts at 1 below the per-component cap; the
    '... omitted' row appears when the cap (50 for component reports) is
    exceeded. Both branches are pinned against the oracle."""
    decisions = [_decision("Q1", (i, i), f"r{i}", counter=i) for i in range(12)]
    trace = _trace(decisions)
    text = render_component_report(trace, "Q1")
    assert "| 1 |" in text
    assert "| 12 |" in text
    assert "earlier decisions omitted" not in text  # 12 <= 50 cap
    many = [_decision("Q1", (i, i), f"r{i}", counter=i) for i in range(60)]
    text2 = render_component_report(_trace(many), "Q1")
    assert "| 11 |" in text2  # start_idx = 60 - 50 + 1
    assert "| 60 |" in text2
    assert "earlier decisions omitted" in text2


def test_phase_and_type_tables_ordered():
    """Phase summary follows DecisionPhase enum order; type summary by
    count descending."""
    trace = _trace([
        _decision("A", 1, "r", phase=DecisionPhase.ROUTING, dtype=DecisionType.NET_ORDER, counter=0),
        _decision("B", 2, "r", phase=DecisionPhase.SEMANTIC, dtype=DecisionType.ROTATION, counter=1),
        _decision("C", 3, "r", phase=DecisionPhase.SEMANTIC, dtype=DecisionType.ROTATION, counter=2),
    ])
    text = render_markdown_report(trace)
    semantic_idx = text.index("Semantic")
    routing_idx = text.index("Routing")
    assert semantic_idx < routing_idx
    # Type table: rotation (2) before net order (1).
    rotation_idx = text.index("Rotation")
    net_order_idx = text.index("Net Order")
    assert rotation_idx < net_order_idx
