"""R1a: behavioural A/B of the Phase-C-tail pipeline-contract port.

Rust Orchestration Engine plan 2026-08-09-001, Phase-C residual: the
``temper_placer.pipeline`` contract tail migrates to the ``temper-orchestration``
crate as pyclasses — ``dag_types.py`` → ``dag_types`` (``StageResult``),
``dag_observability.py`` → ``dag`` (``StageEvent``, ``PipelineExecutionLog``),
``bottleneck_report.py`` → ``bottleneck`` (``BottleneckNetEntry``,
``BottleneckRegion``, ``CongestionHeatmapData``, ``BottleneckReport``,
``DeclaredArtifact``) and ``metrics_observer.py`` → ``metrics``
(``MetricsObserver``, ``CrossValidationError``, ``CanaryCheckError``). Each
Python module keeps its full public API as a delegation shim.

The pre-migration modules are pinned VERBATIM as the oracles
(``tests/pipeline/_dag_types_py_oracle.py`` etc., content-hash-pinned below).
Both arms are driven with IDENTICAL inputs; every assertion is bit-exact
(``repr()`` string equality for whole objects and per-field signatures — repr
is the exactest discriminator for int-vs-float type identity, dict reprs,
tuple/list shapes and floats alike).

Anti-vacuity: ``test_oracle_and_port_are_different_implementations`` asserts
the port is genuinely the Rust pyclasses (``__module__``), not the shim
resolving back onto itself.

Documented boundaries exercised by the differential (see VERIFICATION.md,
Phase-C tail section, for the full list): explicit ``None`` passed to a
container-typed constructor argument is treated as the omitted sentinel
(fresh container); ``StageEvent.timestamp``/``MetricsObserver.canary_value``
explicit ``None`` is treated as the omitted default; the scalar fields
coerce to ``f64`` on assignment (``5`` → ``5.0``); ``total_nets`` is a
machine int (i64) for the port's constructor. The differential drives the
declared types only.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

import pytest
import temper_orchestration as _to
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.pipeline import bottleneck_report as _bottleneck
from temper_placer.pipeline import dag_observability as _dag
from temper_placer.pipeline import dag_types as _dag_types
from temper_placer.pipeline import metrics_observer as _metrics
from tests.pipeline import _bottleneck_report_py_oracle as _oracle_bottleneck
from tests.pipeline import _dag_observability_py_oracle as _oracle_dag
from tests.pipeline import _dag_types_py_oracle as _oracle_types
from tests.pipeline import _metrics_observer_py_oracle as _oracle_metrics

# ---------------------------------------------------------------------------
# The oracles must stay verbatim
# ---------------------------------------------------------------------------

_ORACLE_PINS = [
    ("_dag_types_py_oracle.py", "686e0ed7d14c2336c52dfb18948d6fae1da3dc23b3cb431d30da90156701b69a"),
    ("_dag_observability_py_oracle.py", "843e6b9cdd46acf097eff1b35d52adfec2427046827203d7ced644a8e229e22c"),
    ("_bottleneck_report_py_oracle.py", "9ff50c45ac8eeeb30f73a2837268c4837ab53147c7c24a95c60c1e916a8b7995"),
    ("_metrics_observer_py_oracle.py", "fcf63debb2e9f320f3af5f16359e2821a36cc6ce8356e5cff27d0cd727d5cf2d"),
]
_BODY_MARKER = "# --- BEGIN PINNED BODY ---\n"


def test_oracle_bodies_match_pinned_digests() -> None:
    """The oracles are evidence only while they are unmodified."""
    for name, digest in _ORACLE_PINS:
        text = (Path(__file__).with_name(name)).read_text(encoding="utf-8")
        assert _BODY_MARKER in text, f"{name}: oracle header marker missing"
        body = text.split(_BODY_MARKER, 1)[1]
        computed = hashlib.sha256(body.encode("utf-8")).hexdigest()
        assert computed == digest, (
            f"{name}: the pinned oracle body changed; it must stay verbatim "
            f"(expected {digest}, got {computed})"
        )


def test_oracle_and_port_are_different_implementations() -> None:
    """Anti-vacuity: the port must be the Rust pyclasses, not the shim."""
    for shim_cls, oracle_cls in [
        (_dag_types.StageResult, _oracle_types.StageResult),
        (_dag.StageEvent, _oracle_dag.StageEvent),
        (_dag.PipelineExecutionLog, _oracle_dag.PipelineExecutionLog),
        (_bottleneck.BottleneckNetEntry, _oracle_bottleneck.BottleneckNetEntry),
        (_bottleneck.BottleneckRegion, _oracle_bottleneck.BottleneckRegion),
        (_bottleneck.CongestionHeatmapData, _oracle_bottleneck.CongestionHeatmapData),
        (_bottleneck.BottleneckReport, _oracle_bottleneck.BottleneckReport),
        (_bottleneck.DeclaredArtifact, _oracle_bottleneck.DeclaredArtifact),
        (_metrics.MetricsObserver, _oracle_metrics.MetricsObserver),
    ]:
        assert shim_cls is not oracle_cls
        assert shim_cls.__module__ == "temper_orchestration"
    # The metrics exceptions are Rust-hosted (still ValueError subclasses).
    assert _metrics.CrossValidationError is not _oracle_metrics.CrossValidationError
    assert _metrics.CanaryCheckError is not _oracle_metrics.CanaryCheckError
    assert _metrics.CrossValidationError.__module__ == "temper_orchestration"
    assert _metrics.CanaryCheckError.__module__ == "temper_orchestration"
    assert issubclass(_metrics.CrossValidationError, ValueError)
    assert issubclass(_metrics.CanaryCheckError, ValueError)
    # The exceptions that stayed Python stay on the shim.
    assert _dag_types.DAGError.__module__ == "temper_placer.pipeline.dag_types"
    assert _dag_types.DAGExprError.__module__ == "temper_placer.pipeline.dag_types"
    # The shims still carry the `_rs` delegation seam.
    for mod in (_dag_types, _dag, _bottleneck, _metrics):
        assert hasattr(mod, "_rs")
        assert mod._rs is _to


# ---------------------------------------------------------------------------
# dag_types — StageResult
# ---------------------------------------------------------------------------


def _stage_result_cases():
    return [
        {},
        {"outputs": {"a": 1, "b": [1, 2]}},
        {"outputs": {"nested": {"k": (1, 2)}}},
        {"duration_s": 1.5},
        {"outputs": {"a": 1}, "duration_s": 3.5},
        {"outputs": {}},
        {"outputs": {"x": float("nan")}},
    ]


def test_stage_result_constructor_and_repr_match() -> None:
    for kw in _stage_result_cases():
        o = _oracle_types.StageResult(**kw)
        p = _dag_types.StageResult(**kw)
        assert repr(o) == repr(p), (kw, repr(o), repr(p))


def test_stage_result_success_matches() -> None:
    for outputs in (None, {}, {"a": 1}, {"a": []}, [], {"x": None}):
        o = _oracle_types.StageResult.success(outputs)
        p = _dag_types.StageResult.success(outputs)
        assert repr(o) == repr(p), (outputs, repr(o), repr(p))


def test_stage_result_success_keeps_truthy_dict_identity() -> None:
    outputs = {"a": 1}
    assert _dag_types.StageResult.success(outputs).outputs is outputs
    assert _dag_types.StageResult.success().outputs == {}


def test_stage_result_eq_matches() -> None:
    cases = [
        ({"a": 1}, 0.0, {"a": 1}, 0.0),
        ({"a": 1}, 0.0, {"a": 2}, 0.0),
        ({"a": 1}, 0.0, {"a": 1}, 1.0),
        ({"a": 1}, 0.0, {"a": 1.0}, 0.0),  # 1 == 1.0 in Python
        ({}, float("nan"), {}, float("nan")),  # NaN != NaN
    ]
    for a1, d1, a2, d2 in cases:
        o1, o2 = _oracle_types.StageResult(a1, d1), _oracle_types.StageResult(a2, d2)
        p1, p2 = _dag_types.StageResult(a1, d1), _dag_types.StageResult(a2, d2)
        assert (o1 == o2) == (p1 == p2), (a1, d1, a2, d2)
    # Cross-class / non-instance operands are never equal.
    o = _oracle_types.StageResult()
    p = _dag_types.StageResult()
    assert (o == 5) == (p == 5) is False
    assert (o == "x") == (p == "x") is False


def test_stage_result_unhashable() -> None:
    with pytest.raises(TypeError):
        hash(_oracle_types.StageResult())
    with pytest.raises(TypeError):
        hash(_dag_types.StageResult())


# ---------------------------------------------------------------------------
# dag — StageEvent / PipelineExecutionLog
# ---------------------------------------------------------------------------

_EVENT_KWARGS = [
    {"name": "s1", "kind": "load"},
    {"name": "s1", "kind": "load", "iteration": 3},
    {"name": "s1", "kind": "complete", "duration_s": 0.5, "reason": "done", "outputs": {"routed": 42}},
    {"name": "e", "kind": "error", "error": "boom", "feedback_contract": "sidecar", "feedback_attempt": 2},
    {"name": "t", "kind": "load", "timestamp": 1234.5},
    {
        "name": "all",
        "kind": "x",
        "iteration": 1,
        "duration_s": 0.0,
        "reason": "",
        "outputs": {},
        "error": None,
        "feedback_contract": None,
        "feedback_attempt": None,
        "timestamp": 9.9,
    },
    {"name": "out", "kind": "complete", "outputs": {"pos": (1.0, 2.0)}, "timestamp": 2.0},
]


def _with_ts(kw):
    """Inject a fixed timestamp where the case omitted one — the default
    timestamp factory is nondeterministic (tested separately)."""
    kw = dict(kw)
    kw.setdefault("timestamp", 1234.5)
    return kw


def test_stage_event_constructor_and_repr_match() -> None:
    for kw in _EVENT_KWARGS:
        o = _oracle_dag.StageEvent(**_with_ts(kw))
        p = _dag.StageEvent(**_with_ts(kw))
        assert repr(o) == repr(p), (kw, repr(o), repr(p))


def test_stage_event_default_timestamp_is_float_now() -> None:
    import time

    o = _oracle_dag.StageEvent("s", "k")
    p = _dag.StageEvent("s", "k")
    assert isinstance(o.timestamp, float)
    assert isinstance(p.timestamp, float)
    assert abs(p.timestamp - time.time()) < 1.0


def test_stage_event_eq_matches() -> None:
    for kw in _EVENT_KWARGS:
        kw = _with_ts(kw)
        o1 = _oracle_dag.StageEvent(**kw)
        p1 = _dag.StageEvent(**kw)
        # Same-arm equality is bit-exact.
        o2 = _oracle_dag.StageEvent(**kw)
        p2 = _dag.StageEvent(**kw)
        assert (o1 == o2) == (p1 == p2)
        assert repr(o1) == repr(p1)
        # A differing field breaks equality in both arms.
        kw2 = dict(kw)
        kw2["name"] = kw.get("name", "") + "X"
        assert (o1 == _oracle_dag.StageEvent(**kw2)) == (p1 == _dag.StageEvent(**kw2))


def test_stage_event_unhashable() -> None:
    with pytest.raises(TypeError):
        hash(_oracle_dag.StageEvent("s", "k"))
    with pytest.raises(TypeError):
        hash(_dag.StageEvent("s", "k"))


@dataclasses.dataclass
class _NestedPayload:
    a: int
    b: tuple


def _build_log(cls, ev_cls):
    event = ev_cls(
        name="stage_0", kind="load_pcb", iteration=0, duration_s=0.5,
        outputs={"routed": 42}, timestamp=1.0,
    )
    full = ev_cls(
        name="full", kind="complete", duration_s=0.25, reason="ok",
        outputs={"pos": (1.0, 2.0), "nested": {"a": [1, 2], "inner": _NestedPayload(3, (4, 5))}},
        error="err", feedback_contract="sidecar", feedback_attempt=2, timestamp=2.0,
    )
    return cls(
        dag_topology=[{"from": "a", "to": "b"}],
        stage_order=["a", "b"],
        stage_timings={"a": 1.0},
        retry_counts={"a": 1},
        feedback_activations=[{"contract": "sidecar"}],
        success=True,
        total_duration_s=3.5,
        events=[event, full],
    )


def test_pipeline_execution_log_to_dict_matches() -> None:
    o = _build_log(_oracle_dag.PipelineExecutionLog, _oracle_dag.StageEvent)
    p = _build_log(_dag.PipelineExecutionLog, _dag.StageEvent)
    assert repr(o.to_dict()) == repr(p.to_dict())
    assert json.dumps(o.to_dict()) == json.dumps(p.to_dict())


def test_pipeline_execution_log_to_dict_none_filter_matches() -> None:
    o = _oracle_dag.PipelineExecutionLog(events=[_oracle_dag.StageEvent("simple", "pass", timestamp=1.0)])
    p = _dag.PipelineExecutionLog(events=[_dag.StageEvent("simple", "pass", timestamp=1.0)])
    o_evt, p_evt = o.to_dict()["events"][0], p.to_dict()["events"][0]
    assert set(o_evt) == set(p_evt)
    assert "error" not in o_evt and "error" not in p_evt
    assert "feedback_contract" not in o_evt and "feedback_contract" not in p_evt
    assert repr(o_evt) == repr(p_evt)


def test_pipeline_execution_log_to_dict_places_containers_raw() -> None:
    o = _oracle_dag.PipelineExecutionLog(stage_order=["a"], retry_counts={"a": 1})
    p = _dag.PipelineExecutionLog(stage_order=["a"], retry_counts={"a": 1})
    assert o.to_dict()["stage_order"] is o.stage_order
    assert p.to_dict()["stage_order"] is p.stage_order
    assert o.to_dict()["retry_counts"] is o.retry_counts
    assert p.to_dict()["retry_counts"] is p.retry_counts


def test_pipeline_execution_log_repr_matches() -> None:
    o = _build_log(_oracle_dag.PipelineExecutionLog, _oracle_dag.StageEvent)
    p = _build_log(_dag.PipelineExecutionLog, _dag.StageEvent)
    assert repr(o) == repr(p)


def test_pipeline_execution_log_eq_matches() -> None:
    o1 = _build_log(_oracle_dag.PipelineExecutionLog, _oracle_dag.StageEvent)
    p1 = _build_log(_dag.PipelineExecutionLog, _dag.StageEvent)
    o2 = _build_log(_oracle_dag.PipelineExecutionLog, _oracle_dag.StageEvent)
    p2 = _build_log(_dag.PipelineExecutionLog, _dag.StageEvent)
    assert (o1 == o2) == (p1 == p2)
    assert (o1 == _oracle_dag.PipelineExecutionLog()) == (p1 == _dag.PipelineExecutionLog())
    assert (o1 == 5) == (p1 == 5)


def test_pipeline_execution_log_default_factory_independence() -> None:
    o1, o2 = _oracle_dag.PipelineExecutionLog(), _oracle_dag.PipelineExecutionLog()
    p1, p2 = _dag.PipelineExecutionLog(), _dag.PipelineExecutionLog()
    o1.stage_order.append("x")
    p1.stage_order.append("x")
    o1.stage_timings["k"] = 1.0
    p1.stage_timings["k"] = 1.0
    assert o2.stage_order == [] and p2.stage_order == []
    assert o2.stage_timings == {} and p2.stage_timings == {}


def test_write_execution_log_json_matches(tmp_path: Path) -> None:
    from temper_placer.pipeline import dag_observability as shim_dag

    o = _build_log(_oracle_dag.PipelineExecutionLog, _oracle_dag.StageEvent)
    p = _build_log(_dag.PipelineExecutionLog, _dag.StageEvent)
    o_path = _oracle_dag.write_execution_log_json(o, tmp_path / "o")
    p_path = shim_dag.write_execution_log_json(p, tmp_path / "p")
    assert o_path.read_text() == p_path.read_text()
    assert json.loads(o_path.read_text()) == json.loads(p_path.read_text())


# ---------------------------------------------------------------------------
# bottleneck_report — the four dataclasses + DeclaredArtifact
# ---------------------------------------------------------------------------


def test_bottleneck_region_type_identity_matches() -> None:
    """Constructor stores ints as ints, floats as floats (repr is exact)."""
    for args in [(0, 0, 10, 10), (0.0, 0.0, 10.5, 10.5), (0, 0.0, 10, 10.0)]:
        o = _oracle_bottleneck.BottleneckRegion(*args, affected_components=["U1"])
        p = _bottleneck.BottleneckRegion(*args, affected_components=["U1"])
        assert repr(o) == repr(p), (args, repr(o), repr(p))
        assert json.dumps(o.to_dict()) == json.dumps(p.to_dict())


def test_bottleneck_net_entry_roundtrip_matches() -> None:
    d = {
        "net_name": "NET1",
        "net_class": "Signal",
        "failure_reason": "congestion",
        "pin_positions": [[10.0, 20.0], [30.0, 40.0]],
    }
    o = _oracle_bottleneck.BottleneckNetEntry.from_dict(d)
    p = _bottleneck.BottleneckNetEntry.from_dict(d)
    assert repr(o) == repr(p)
    assert repr(o.to_dict()) == repr(p.to_dict())
    assert isinstance(p.pin_positions[0], tuple)
    assert isinstance(p.to_dict()["pin_positions"][0], list)


def test_bottleneck_region_from_dict_matches() -> None:
    d = {"x_min": 1, "y_min": 2.5, "x_max": 3, "y_max": 4, "affected_components": ("Q1", "Q2")}
    o = _oracle_bottleneck.BottleneckRegion.from_dict(d)
    p = _bottleneck.BottleneckRegion.from_dict(d)
    assert repr(o) == repr(p)
    assert repr(o.to_dict()) == repr(p.to_dict())


def test_bottleneck_heatmap_roundtrip_matches() -> None:
    d = {"net_class": "Signal", "grid": [[0.1, 0.2], [0.3, 0.4]], "cell_size": 1}
    o = _oracle_bottleneck.CongestionHeatmapData.from_dict(d)
    p = _bottleneck.CongestionHeatmapData.from_dict(d)
    assert repr(o) == repr(p)
    assert repr(o.to_dict()) == repr(p.to_dict())


_BOTTLENECK_REPORT_DICT = {
    "schema_version": "1.0.0",
    "failed_nets": [
        {
            "net_name": "N1",
            "net_class": "Signal",
            "failure_reason": "congestion",
            "pin_positions": [[1.0, 2.0], [3.0, 4.0]],
        }
    ],
    "routed_nets": ["N2", "N3"],
    "congestion_heatmaps": {
        "Signal": {"net_class": "Signal", "grid": [[0.5, 0.25]], "cell_size": 1.0}
    },
    "bottleneck_regions": [
        {"x_min": 0, "y_min": 0, "x_max": 10, "y_max": 10, "affected_components": ["U1"]}
    ],
    "routability_ratio": 1,
    "total_nets": 3,
}


def test_bottleneck_report_from_dict_matches() -> None:
    o = _oracle_bottleneck.BottleneckReport.from_dict(_BOTTLENECK_REPORT_DICT)
    p = _bottleneck.BottleneckReport.from_dict(_BOTTLENECK_REPORT_DICT)
    assert repr(o) == repr(p)
    assert o.to_dict() == p.to_dict()
    assert o.to_json() == p.to_json()
    # int -> float coercion happens in from_dict for both arms.
    assert isinstance(o.routability_ratio, float) and isinstance(p.routability_ratio, float)
    assert o.routability_ratio == p.routability_ratio == 1.0
    assert o.total_nets == p.total_nets == 3
    assert o.routed_count == p.routed_count == 2
    assert o.failed_count == p.failed_count == 1


def test_bottleneck_report_to_json_roundtrip_matches(tmp_path: Path) -> None:
    o = _oracle_bottleneck.BottleneckReport.from_dict(_BOTTLENECK_REPORT_DICT)
    p = _bottleneck.BottleneckReport.from_dict(_BOTTLENECK_REPORT_DICT)
    o_path, p_path = tmp_path / "o.json", tmp_path / "p.json"
    o.write(o_path)
    p.write(p_path)
    assert o_path.read_text() == p_path.read_text()
    o2 = _oracle_bottleneck.BottleneckReport.read(o_path)
    p2 = _bottleneck.BottleneckReport.read(p_path)
    assert repr(o2) == repr(p2)
    assert o2 == _oracle_bottleneck.BottleneckReport.from_dict(_BOTTLENECK_REPORT_DICT)
    assert p2 == _bottleneck.BottleneckReport.from_dict(_BOTTLENECK_REPORT_DICT)


def test_bottleneck_report_from_dict_defaults_match() -> None:
    o = _oracle_bottleneck.BottleneckReport.from_dict({})
    p = _bottleneck.BottleneckReport.from_dict({})
    assert repr(o) == repr(p)
    assert o.schema_version == p.schema_version == "1.0.0"
    assert o.routability_ratio == p.routability_ratio == 0.0
    assert o.total_nets == p.total_nets == 0
    assert o.routed_count == p.routed_count == 0


def test_bottleneck_from_dict_missing_key_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        _oracle_bottleneck.BottleneckNetEntry.from_dict({})
    with pytest.raises(KeyError):
        _bottleneck.BottleneckNetEntry.from_dict({})
    with pytest.raises(KeyError):
        _oracle_bottleneck.BottleneckRegion.from_dict({})
    with pytest.raises(KeyError):
        _bottleneck.BottleneckRegion.from_dict({})


def test_bottleneck_report_constructor_defaults_match() -> None:
    o = _oracle_bottleneck.BottleneckReport()
    p = _bottleneck.BottleneckReport()
    assert repr(o) == repr(p)


def test_bottleneck_report_constructor_raw_type_identity() -> None:
    """The constructor stores values raw (int stays int), unlike from_dict."""
    o = _oracle_bottleneck.BottleneckReport(routability_ratio=1, total_nets=3)
    p = _bottleneck.BottleneckReport(routability_ratio=1, total_nets=3)
    assert repr(o) == repr(p)
    assert isinstance(o.routability_ratio, int) and isinstance(p.routability_ratio, int)


def test_declared_artifact_matches() -> None:
    o = _oracle_bottleneck.DeclaredArtifact("bottleneck", "out/bottleneck_report.json")
    p = _bottleneck.DeclaredArtifact("bottleneck", "out/bottleneck_report.json")
    assert repr(o) == repr(p)
    assert (o == _oracle_bottleneck.DeclaredArtifact("bottleneck", "out/bottleneck_report.json")) is (
        p == _bottleneck.DeclaredArtifact("bottleneck", "out/bottleneck_report.json")
    ) is True
    assert (o == _oracle_bottleneck.DeclaredArtifact("x", "y")) == (
        p == _bottleneck.DeclaredArtifact("x", "y")
    )
    # Frozen-dataclass hash is a function of the field tuple — equal fields
    # hash equally across the arms (same process).
    assert hash(o) == hash(p)
    with pytest.raises(dataclasses.FrozenInstanceError):
        o.output_path = "x"
    with pytest.raises(AttributeError):
        p.output_path = "x"


# ---------------------------------------------------------------------------
# metrics_observer — MetricsObserver + the two exceptions
# ---------------------------------------------------------------------------


def _frozen_metrics_datetime():
    from temper_placer.regression import metrics_recorder as rec_mod

    class _FixedDatetime:
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 1, 1, 12, 0, 0, tzinfo=tz)

    return mock.patch.object(rec_mod, "datetime", _FixedDatetime)


def test_metrics_on_stage_complete_jsonl_identical(tmp_path: Path) -> None:
    execution_log = _dag.PipelineExecutionLog(stage_timings={"load": 0.5})
    o = _oracle_metrics.MetricsObserver(
        output_dir=tmp_path / "o", execution_log=execution_log, board="test-board"
    )
    p = _metrics.MetricsObserver(
        output_dir=tmp_path / "p", execution_log=execution_log, board="test-board"
    )
    with _frozen_metrics_datetime():
        o.on_stage_complete("load", 0.5, {"drc_errors_before": 10, "drc_errors_after": 3})
        p.on_stage_complete("load", 0.5, {"drc_errors_before": 10, "drc_errors_after": 3})
    o_line = (tmp_path / "o" / "pipeline_metrics.jsonl").read_text()
    p_line = (tmp_path / "p" / "pipeline_metrics.jsonl").read_text()
    assert o_line == p_line
    assert '"drc_delta": 7' in o_line
    assert '"board": "test-board"' in o_line


def test_metrics_on_stage_complete_no_outputs_matches(tmp_path: Path) -> None:
    execution_log = _dag.PipelineExecutionLog()
    o = _oracle_metrics.MetricsObserver(output_dir=tmp_path / "o", execution_log=execution_log)
    p = _metrics.MetricsObserver(output_dir=tmp_path / "p", execution_log=execution_log)
    with _frozen_metrics_datetime():
        o.on_stage_complete("route", 1.25, {})
        p.on_stage_complete("route", 1.25, {})
    assert (tmp_path / "o" / "pipeline_metrics.jsonl").read_text() == (
        tmp_path / "p" / "pipeline_metrics.jsonl"
    ).read_text()


def test_metrics_on_stage_start_records_and_complete_strips(tmp_path: Path) -> None:
    import time

    execution_log = _dag.PipelineExecutionLog()
    o = _oracle_metrics.MetricsObserver(output_dir=tmp_path / "o", execution_log=execution_log)
    p = _metrics.MetricsObserver(output_dir=tmp_path / "p", execution_log=execution_log)
    for obs in (o, p):
        obs.on_stage_start("load", 0, {})
        assert "load" in obs._stage_start_times
        # Back-date the start time so the caller's duration matches the
        # elapsed monotonic span (within tolerance) — the real-flow path.
        obs._stage_start_times["load"] = time.monotonic() - 0.5
        obs.on_stage_complete("load", 0.5, {})
        assert "load" not in obs._stage_start_times


def test_metrics_cross_validation_error_message_identical(tmp_path: Path) -> None:
    execution_log = _dag.PipelineExecutionLog(stage_timings={"load": 5.0})
    o = _oracle_metrics.MetricsObserver(output_dir=tmp_path / "o", execution_log=execution_log)
    p = _metrics.MetricsObserver(output_dir=tmp_path / "p", execution_log=execution_log)
    with pytest.raises(_oracle_metrics.CrossValidationError) as oe:
        o._cross_validate_against(start_t=None, stage_name="load", caller_duration_s=1.0)
    with pytest.raises(_metrics.CrossValidationError) as pe:
        p._cross_validate_against(start_t=None, stage_name="load", caller_duration_s=1.0)
    assert str(oe.value) == str(pe.value)
    assert isinstance(pe.value, ValueError)


def test_metrics_cross_validation_passes_within_tolerance(tmp_path: Path) -> None:
    execution_log = _dag.PipelineExecutionLog(stage_timings={"load": 0.5})
    o = _oracle_metrics.MetricsObserver(output_dir=tmp_path / "o", execution_log=execution_log)
    p = _metrics.MetricsObserver(output_dir=tmp_path / "p", execution_log=execution_log)
    o._cross_validate_against(start_t=None, stage_name="load", caller_duration_s=0.5)
    p._cross_validate_against(start_t=None, stage_name="load", caller_duration_s=0.5)


def test_metrics_canary_error_message_identical(tmp_path: Path) -> None:
    from temper_placer.regression.metrics_recorder import PipelineMetricsRecord

    execution_log = _dag.PipelineExecutionLog()
    o = _oracle_metrics.MetricsObserver(output_dir=tmp_path / "o", execution_log=execution_log)
    p = _metrics.MetricsObserver(output_dir=tmp_path / "p", execution_log=execution_log)
    record = PipelineMetricsRecord(
        board="b", stage="s", stage_name="s", metrics={"__pipeline_liveness__": 1, "wall_time_ms": 5}
    )
    with pytest.raises(_oracle_metrics.CanaryCheckError) as oe:
        o._check_canary(record)
    with pytest.raises(_metrics.CanaryCheckError) as pe:
        p._check_canary(record)
    assert str(oe.value) == str(pe.value)
    assert isinstance(pe.value, ValueError)


def test_metrics_mock_seam_preserved(tmp_path: Path) -> None:
    """mock.patch.object on the internal hooks still intercepts (the U1
    test seam): on_stage_complete dispatches through instance lookup."""
    execution_log = _dag.PipelineExecutionLog()
    p = _metrics.MetricsObserver(output_dir=tmp_path / "p", execution_log=execution_log, board="b")
    with mock.patch.object(p, "_write") as mock_write, mock.patch.object(
        p, "_validate_schema"
    ), mock.patch.object(p, "_cross_validate_against"), mock.patch.object(p, "_check_canary"):
        p.on_stage_complete("load", 0.5, {})
        mock_write.assert_called_once()


# ---------------------------------------------------------------------------
# G4 — Property-based tests (with non-vacuity guards)
# ---------------------------------------------------------------------------

_IMPL = {
    "stage_result_success": lambda outputs: _dag_types.StageResult.success(outputs),
    "stage_result_outputs": lambda sr: sr.outputs,
    "stage_result_duration": lambda sr: sr.duration_s,
    "make_net_entry": lambda d: _bottleneck.BottleneckNetEntry.from_dict(d),
    "net_entry_to_dict": lambda e: e.to_dict(),
    "net_entry_pin_positions": lambda e: e.pin_positions,
    "make_report": lambda d: _bottleneck.BottleneckReport.from_dict(d),
    "report_to_dict": lambda r: r.to_dict(),
    "report_from_dict": lambda d: _bottleneck.BottleneckReport.from_dict(d),
    "report_eq": lambda a, b: a == b,
    "report_routed_count": lambda r: r.routed_count,
    "make_log": lambda events: _dag.PipelineExecutionLog(events=events),
    "make_event": lambda name, kind, ts: _dag.StageEvent(name=name, kind=kind, timestamp=ts),
    "log_to_dict": lambda log: log.to_dict(),
    "make_artifact": lambda a, b: _bottleneck.DeclaredArtifact(a, b),
    "artifact_hash": lambda a: hash(a),
    "artifact_eq": lambda a, b: a == b,
    "event_eq": lambda a, b: a == b,
    "event_ne": lambda a, b: a != b,
}

_FINITE = {"allow_nan": False, "allow_infinity": False}


@pytest.fixture
def _restore_impl():
    saved = dict(_IMPL)
    yield
    _IMPL.clear()
    _IMPL.update(saved)


@given(
    outputs=st.one_of(
        st.none(),
        st.dictionaries(st.text(min_size=1, max_size=20), st.integers(min_value=-100, max_value=100), max_size=8),
    )
)
@settings(max_examples=50, deadline=30000)
def test_p1_stage_result_success_truthiness(outputs):
    """P1. `success(outputs)` yields `outputs or {}` and duration 0.0."""
    sr = _IMPL["stage_result_success"](outputs)
    assert _IMPL["stage_result_outputs"](sr) == ({} if not outputs else outputs)
    assert _IMPL["stage_result_duration"](sr) == 0.0
    if outputs:
        assert _IMPL["stage_result_outputs"](sr) is outputs


def test_p1_fails_for_always_empty_mutant(_restore_impl):
    _IMPL["stage_result_success"] = lambda outputs: _dag_types.StageResult.success({})  # noqa: ARG005
    with pytest.raises(AssertionError):
        test_p1_stage_result_success_truthiness.hypothesis.inner_test({"a": 1})


@given(
    positions=st.lists(
        st.tuples(
            st.floats(min_value=-1000.0, max_value=1000.0, **_FINITE),
            st.floats(min_value=-1000.0, max_value=1000.0, **_FINITE),
        ),
        max_size=5,
    )
)
@settings(max_examples=50, deadline=30000)
def test_p2_net_entry_tuple_shape_preserved(positions):
    """P2. from_dict turns pin_positions into tuples; to_dict back into
    lists, preserving order and values."""
    d = {
        "net_name": "N",
        "net_class": "C",
        "failure_reason": "R",
        "pin_positions": [[x, y] for x, y in positions],
    }
    entry = _IMPL["make_net_entry"](d)
    assert all(isinstance(p, tuple) for p in _IMPL["net_entry_pin_positions"](entry))
    assert list(_IMPL["net_entry_pin_positions"](entry)) == [tuple(p) for p in positions]
    dd = _IMPL["net_entry_to_dict"](entry)
    assert all(isinstance(p, list) for p in dd["pin_positions"])
    assert [tuple(p) for p in dd["pin_positions"]] == positions


def test_p2_fails_for_tuple_keeping_mutant(_restore_impl):
    _IMPL["net_entry_to_dict"] = lambda e: {
        "net_name": e.net_name,
        "net_class": e.net_class,
        "failure_reason": e.failure_reason,
        "pin_positions": list(e.pin_positions),  # wrong: tuples, not lists
    }
    with pytest.raises(AssertionError):
        test_p2_net_entry_tuple_shape_preserved.hypothesis.inner_test([(1.0, 2.0)])


@given(
    net_names=st.lists(st.text(min_size=1, max_size=20), max_size=6),
    position=st.tuples(
        st.floats(min_value=-1000.0, max_value=1000.0, **_FINITE),
        st.floats(min_value=-1000.0, max_value=1000.0, **_FINITE),
    ),
)
@settings(max_examples=50, deadline=30000)
def test_p3_report_roundtrip_and_counts(net_names, position):
    """P3. from_dict(to_dict(x)) == x; routed_count == len(routed_nets)."""
    d = {
        "schema_version": "1.0.0",
        "failed_nets": [],
        "routed_nets": net_names,
        "congestion_heatmaps": {},
        "bottleneck_regions": [],
        "routability_ratio": 0.5,
        "total_nets": len(net_names),
    }
    report = _IMPL["make_report"](d)
    restored = _IMPL["report_from_dict"](_IMPL["report_to_dict"](report))
    assert _IMPL["report_eq"](report, restored)
    assert _IMPL["report_routed_count"](restored) == len(net_names)


def test_p3_fails_for_swapped_roundtrip_mutant(_restore_impl):
    _IMPL["report_to_dict"] = lambda r: {
        "schema_version": r.schema_version,
        "failed_nets": [],
        "routed_nets": list(reversed(r.routed_nets)),  # wrong: reversed
        "congestion_heatmaps": {},
        "bottleneck_regions": [],
        "routability_ratio": r.routability_ratio,
        "total_nets": r.total_nets,
    }
    with pytest.raises(AssertionError):
        test_p3_report_roundtrip_and_counts.hypothesis.inner_test(["a", "b"], (1.0, 2.0))


@given(names=st.lists(st.text(min_size=1, max_size=20), max_size=5))
@settings(max_examples=50, deadline=30000)
def test_p4_log_event_order_and_none_filter(names):
    """P4. to_dict preserves event order; None-typed fields are filtered."""
    events = [_IMPL["make_event"](n, "k", 1.0) for n in names]
    log = _IMPL["make_log"](events)
    d = _IMPL["log_to_dict"](log)
    assert [e["name"] for e in d["events"]] == names
    assert all("error" not in e for e in d["events"])
    assert all("feedback_contract" not in e for e in d["events"])
    assert all(e["kind"] == "k" for e in d["events"])


def test_p4_fails_for_order_dropping_mutant(_restore_impl):
    _IMPL["log_to_dict"] = lambda log: {
        "dag_topology": log.dag_topology,
        "stage_order": log.stage_order,
        "stage_timings": log.stage_timings,
        "retry_counts": log.retry_counts,
        "feedback_activations": log.feedback_activations,
        "success": log.success,
        "total_duration_s": log.total_duration_s,
        "events": [{"name": e.name, "kind": e.kind, "error": e.error} for e in log.events],  # wrong: error key kept
    }
    with pytest.raises(AssertionError):
        test_p4_log_event_order_and_none_filter.hypothesis.inner_test(["b", "a"])


@given(name=st.text(max_size=30), description=st.text(max_size=30))
@settings(max_examples=50, deadline=30000)
def test_p5_declared_artifact_hash_and_eq(name, description):
    """P5. Equal field tuples hash equally and compare equal."""
    a1 = _IMPL["make_artifact"](name, description)
    a2 = _IMPL["make_artifact"](name, description)
    assert _IMPL["artifact_hash"](a1) == _IMPL["artifact_hash"](a2)
    assert _IMPL["artifact_eq"](a1, a2)


def test_p5_fails_for_identity_hash_mutant(_restore_impl):
    _IMPL["artifact_hash"] = lambda a: id(a)
    with pytest.raises(AssertionError):
        test_p5_declared_artifact_hash_and_eq.hypothesis.inner_test("x", "y")


@given(
    name=st.text(min_size=1, max_size=20),
    kind=st.text(min_size=1, max_size=20),
    ts=st.floats(min_value=0.0, max_value=1e9, **_FINITE),
)
@settings(max_examples=50, deadline=30000)
def test_p6_stage_event_eq_symmetry(name, kind, ts):
    """P6. StageEvent equality is symmetric and distinguishes fields."""
    e1 = _IMPL["make_event"](name, kind, ts)
    e2 = _IMPL["make_event"](name, kind, ts)
    e3 = _IMPL["make_event"](name + "!", kind, ts)
    assert _IMPL["event_eq"](e1, e2)
    assert _IMPL["event_eq"](e2, e1)
    assert not _IMPL["event_eq"](e1, e3)
    assert _IMPL["event_ne"](e1, e3)


def test_p6_fails_for_identity_eq_mutant(_restore_impl):
    _IMPL["event_eq"] = lambda a, b: a is b
    with pytest.raises(AssertionError):
        test_p6_stage_event_eq_symmetry.hypothesis.inner_test("a", "b", 1.0)


# ---------------------------------------------------------------------------
# Metamorphic relations
# ---------------------------------------------------------------------------


def test_m1_bottleneck_report_roundtrip_idempotent() -> None:
    """M1. from_dict(to_dict(x)) is idempotent — applying it twice equals
    applying it once."""
    d = json.loads(json.dumps(_BOTTLENECK_REPORT_DICT))
    once = _bottleneck.BottleneckReport.from_dict(d)
    twice = _bottleneck.BottleneckReport.from_dict(once.to_dict())
    assert once == twice
    assert repr(once) == repr(twice)


def test_m2_log_event_append_prefix_invariant() -> None:
    """M2. Appending an event preserves every prior event's serialized shape
    and only grows the events list by one."""
    e1 = _dag.StageEvent(name="a", kind="load", timestamp=1.0)
    e2 = _dag.StageEvent(name="b", kind="complete", timestamp=2.0)
    log = _dag.PipelineExecutionLog(events=[e1])
    before = log.to_dict()
    log.events.append(e2)
    after = log.to_dict()
    assert len(after["events"]) == len(before["events"]) + 1
    assert before["events"] == after["events"][:-1]
    assert after["events"][-1]["name"] == "b"


def test_m3_net_entry_order_preserved_through_roundtrip() -> None:
    """M3. Permuting pin_positions permutes to_dict's list correspondingly
    (order-preserving transform), and from_dict inverts it exactly."""
    positions = [(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)]
    d = {"net_name": "N", "net_class": "C", "failure_reason": "R", "pin_positions": positions}
    entry = _bottleneck.BottleneckNetEntry.from_dict(d)
    # Reversed input -> reversed output, in both to_dict and from_dict.
    rev = _bottleneck.BottleneckNetEntry.from_dict(
        {"net_name": "N", "net_class": "C", "failure_reason": "R", "pin_positions": list(reversed(positions))}
    )
    assert list(reversed(entry.pin_positions)) == rev.pin_positions
    assert list(reversed(entry.to_dict()["pin_positions"])) == rev.to_dict()["pin_positions"]


def test_m4_stage_result_success_duration_invariant() -> None:
    """M4. success() fixes duration_s at 0.0 and never mutates its input."""
    for outputs in ({}, {"a": 1}, {"b": 2}):
        snapshot = dict(outputs)
        sr = _dag_types.StageResult.success(outputs)
        assert sr.duration_s == 0.0
        assert outputs == snapshot
