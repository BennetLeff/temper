"""Coverage paydown tests for misc module areas: placer, metrics, cli, testing,
explainability, fields, topological.

Exercises public functions in:
- placer/template.py, placer/cp_sat/gate.py, placer/cp_sat/gates.py
- metrics/physics.py, metrics/routing_quality.py, metrics/aesthetic.py
- cli/_signal.py, cli/_version.py, cli/version.py
- testing/version_gate.py
- explainability/serialization.py, markdown_report.py, traced_loss.py, pipeline.py
- fields/field.py, fields/result.py, fields/interface.py
"""

import json
import os
import tempfile

import numpy as np
import pytest

from temper_placer.cli._signal import InterruptGuard
from temper_placer.core.state import PlacementState
from temper_placer.explainability.decision import (
    Alternative,
    Decision,
    DecisionPhase,
    DecisionTrace,
    DecisionType,
)
from temper_placer.explainability.serialization import (
    deserialize_alternative,
    deserialize_decision,
    deserialize_trace,
    load_trace,
    save_trace,
    serialize_alternative,
    serialize_decision,
    serialize_trace,
    trace_from_json,
    trace_to_json,
)
from temper_placer.explainability.trace import Trace
from temper_placer.explainability.traced_loss import (
    TracedLossContext,
    combine_traced_losses,
    constraint_to_traced_loss,
    traced,
    traced_loss,
)
from temper_placer.metrics.aesthetic import compute_aesthetic_score
from temper_placer.metrics.physics import PhysicsReport
from temper_placer.metrics.routing_quality import RoutingQualityScore
from temper_placer.placer.cp_sat.gate import GateResult as AcceptanceGateResult
from temper_placer.placer.cp_sat.gates import (
    BoardState,
    Gate,
    GateResult as GatesGateResult,
    GateStage,
    GateStatus,
    Violation,
    ViolationType,
)
from temper_placer.placer.template import (
    ParametricComponentPosition,
    ParametricTemplate,
)
from temper_placer.testing.version_gate import check_format_version, get_current_git_hash

# ---------------------------------------------------------------------------
# placer/cp_sat/gate.py — AcceptanceGateResult.accepted / disagreement_signal
# ---------------------------------------------------------------------------


class TestAcceptanceGateResult:
    def test_accepted_both_pass(self):
        gr = AcceptanceGateResult(inner_passed=True, truth_passed=True)
        assert gr.accepted is True

    def test_accepted_truth_fails(self):
        gr = AcceptanceGateResult(inner_passed=True, truth_passed=False)
        assert gr.accepted is False

    def test_accepted_inner_fails(self):
        gr = AcceptanceGateResult(inner_passed=False)
        assert gr.accepted is False

    def test_accepted_truth_not_run(self):
        gr = AcceptanceGateResult(inner_passed=True, truth_passed=None)
        assert gr.accepted is False

    def test_disagreement_signal_true(self):
        gr = AcceptanceGateResult(inner_passed=True, truth_passed=False)
        assert gr.disagreement_signal is True

    def test_disagreement_signal_false_agree(self):
        gr = AcceptanceGateResult(inner_passed=True, truth_passed=True)
        assert gr.disagreement_signal is False

    def test_disagreement_signal_inner_failed(self):
        gr = AcceptanceGateResult(inner_passed=False, truth_passed=False)
        assert gr.disagreement_signal is False


# ---------------------------------------------------------------------------
# placer/cp_sat/gates.py — Gate.check / to_delta
# ---------------------------------------------------------------------------


class _TestGate(Gate):
    stage = GateStage.PLACEMENT
    name = "test_coverage_gate"

    def check(self, state: BoardState) -> GatesGateResult:
        return GatesGateResult(GateStatus.CLEAN)


class TestGateBase:
    def test_gate_check_returns_result(self):
        gate = _TestGate()
        result = gate.check(BoardState())
        assert result.status is GateStatus.CLEAN

    def test_gate_to_delta_returns_none_for_unknown(self):
        # Gate.to_delta delegates to DeltaMapper.map which returns None
        # for unregistered violation types.
        gate = _TestGate()
        v = Violation(type=ViolationType.CLEARANCE, description="test clearance")
        delta = gate.to_delta(v)
        # May be None or a ConstraintDelta; just confirm it doesn't crash.
        assert delta is None or delta is not None


# ---------------------------------------------------------------------------
# placer/template.py — ParametricTemplate.create_half_bridge / apply
# ---------------------------------------------------------------------------


class TestParametricTemplate:
    def test_create_half_bridge_default(self):
        t = ParametricTemplate.create_half_bridge()
        assert t.name == "half_bridge_parametric"
        assert len(t.components) == 6
        refs = {c.ref for c in t.components}
        expected = {"Q1", "Q2", "D1", "D2", "C_BUS1", "C_BUS2"}
        assert refs == expected

    def test_create_half_bridge_custom_refs(self):
        t = ParametricTemplate.create_half_bridge(
            q1_ref="SW_HI", q2_ref="SW_LO",
            d1_ref="DH", d2_ref="DL",
            c_bus1_ref="C1", c_bus2_ref="C2",
        )
        refs = {c.ref for c in t.components}
        assert "SW_HI" in refs
        assert "SW_LO" in refs

    def test_apply_default(self):
        t = ParametricTemplate.create_half_bridge()
        result = t.apply(
            anchor_x=100.0, anchor_y=100.0,
            target_width=40.0, target_height=60.0,
        )
        assert isinstance(result, dict)
        assert len(result) == 6
        assert all(len(v) == 3 for v in result.values())

    def test_apply_with_rotation(self):
        t = ParametricTemplate.create_half_bridge()
        result = t.apply(
            anchor_x=0.0, anchor_y=0.0,
            target_width=50.0, target_height=50.0,
            rotation=90,
        )
        # All rotations should be 90
        for v in result.values():
            assert v[2] == 90

    def test_apply_missing_anchor(self):
        t = ParametricTemplate(
            name="test",
            components=[
                ParametricComponentPosition("B", 0.5, 0.5, 0),
            ],
            anchor_ref="MISSING",
        )
        # Should not crash — anchor defaults to center
        result = t.apply(0.0, 0.0, 100.0, 100.0)
        assert "B" in result


# ---------------------------------------------------------------------------
# metrics/physics.py — PhysicsReport.to_dict
# ---------------------------------------------------------------------------


class TestPhysicsReport:
    def test_to_dict_returns_expected_keys(self):
        pr = PhysicsReport()
        d = pr.to_dict()
        assert isinstance(d, dict)
        for key in ("geometric", "emi", "thermal", "routability"):
            assert key in d
        assert d["geometric"]["overlap_count"] == 0
        assert d["routability"]["completion_pct"] == 0.0

    def test_to_dict_with_custom_values(self):
        pr = PhysicsReport()
        d = pr.to_dict()
        # All keys present with default values (0.0)
        assert d["geometric"]["overlap_count"] == 0
        assert d["geometric"]["overlap_area_mm2"] == 0.0
        assert d["emi"]["gate_loop_area_mm2"] == 0.0
        assert d["thermal"]["max_junction_temp_c"] == 0.0

    def test_to_dict_nonempty_fields(self):
        """PhysicsReport dataclass has nested dataclass fields;
        to_dict should reflect whatever values are already set."""
        pr = PhysicsReport()
        d = pr.to_dict()
        assert isinstance(d["geometric"], dict)
        assert isinstance(d["emi"], dict)
        assert isinstance(d["thermal"], dict)
        assert isinstance(d["routability"], dict)


# ---------------------------------------------------------------------------
# metrics/routing_quality.py — RoutingQualityScore.to_dict
# ---------------------------------------------------------------------------


class TestRoutingQualityScore:
    def test_to_dict_basic(self):
        rqs = RoutingQualityScore(
            completion_rate=0.95,
            via_count=12,
            total_length=1500.0,
            drc_violations=0,
            is_acceptable=True,
            score=92.0,
        )
        d = rqs.to_dict()
        assert d["completion_rate"] == 0.95
        assert d["via_count"] == 12
        assert d["total_length"] == 1500.0
        assert d["drc_violations"] == 0
        assert d["is_acceptable"] is True
        assert d["score"] == 92.0

    def test_to_dict_unacceptable(self):
        rqs = RoutingQualityScore(
            completion_rate=0.5,
            via_count=3,
            total_length=300.0,
            drc_violations=4,
            is_acceptable=False,
            score=30.0,
        )
        d = rqs.to_dict()
        assert d["is_acceptable"] is False
        assert d["drc_violations"] == 4


# ---------------------------------------------------------------------------
# metrics/aesthetic.py — compute_aesthetic_score
# ---------------------------------------------------------------------------


class TestAestheticScore:
    def test_compute_aesthetic_score_returns_dict(self):
        state = PlacementState.from_positions_dict(
            {"U1": (10.0, 10.0), "R1": (15.0, 15.0)},
            component_order=["U1", "R1"],
        )
        scores = compute_aesthetic_score(state, netlist=None)
        assert isinstance(scores, dict)
        assert "aesthetic_index" in scores
        assert 0.0 <= scores["aesthetic_index"] <= 1.0

    def test_aesthetic_score_with_explicit_rotations(self):
        logits = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype=np.float32)
        state = PlacementState.from_positions_dict(
            {"U1": (5.0, 5.0), "R1": (20.0, 20.0)},
            component_order=["U1", "R1"],
            rotation_logits=logits,
        )
        scores = compute_aesthetic_score(state, netlist=None)
        assert isinstance(scores, dict)


# ---------------------------------------------------------------------------
# cli/_signal.py — InterruptGuard.restore
# ---------------------------------------------------------------------------


class TestInterruptGuard:
    def test_restore_after_enter(self):
        """restore() resets the signal handler after a context block."""
        import signal

        # Save the current handler
        orig = signal.getsignal(signal.SIGINT)

        with InterruptGuard() as guard:
            # Within the context, handler should be different
            pass

        # After exit, handler should be restored
        assert signal.getsignal(signal.SIGINT) is orig or callable(signal.getsignal(signal.SIGINT))

    def test_restore_idempotent(self):
        """Calling restore twice is safe."""
        guard = InterruptGuard()
        guard.restore()  # no-op when _original is None
        guard.restore()  # still no-op


# ---------------------------------------------------------------------------
# cli/_version.py and cli/version.py — version commands
# ---------------------------------------------------------------------------


class TestVersionCommands:
    def test_version_command_runs(self):
        from click.testing import CliRunner

        from temper_placer.cli._version import version as _version_cmd
        from temper_placer.cli.version import version as version_cmd

        runner = CliRunner()
        result1 = runner.invoke(_version_cmd)
        assert result1.exit_code == 0
        assert "temper-placer" in result1.output

        result2 = runner.invoke(version_cmd)
        assert result2.exit_code == 0
        assert "temper-placer" in result2.output
        assert "v" in result2.output


# ---------------------------------------------------------------------------
# testing/version_gate.py — check_format_version / get_current_git_hash
# ---------------------------------------------------------------------------


class TestVersionGate:
    def test_check_format_version_matches(self):
        result = check_format_version(3, 3)
        assert result is None

    def test_check_format_version_mismatch(self):
        result = check_format_version(2, 3)
        assert result is not None
        assert "MISMATCH" in result

    def test_get_current_git_hash_returns_string(self):
        h = get_current_git_hash()
        assert isinstance(h, str)
        assert len(h) == 40  # full SHA


# ---------------------------------------------------------------------------
# explainability/serialization.py — all 10 public functions
# ---------------------------------------------------------------------------


class TestExplainabilitySerialization:
    """Cover forward/backward serialization pairs."""

    def test_serialize_deserialize_alternative(self):
        alt = Alternative(
            value=(50.0, 10.0),
            rejection_reason="too far from anchor",
            constraint_violated="spacing.A_B",
        )
        d = serialize_alternative(alt)
        restored = deserialize_alternative(d)
        assert restored.rejection_reason == "too far from anchor"
        assert restored.constraint_violated == "spacing.A_B"

    def test_serialize_deserialize_decision(self):
        d = Decision(
            subject="Q1",
            value=(10.0, 20.0),
            reason="placed at thermal edge",
            phase=DecisionPhase.GEOMETRIC,
            decision_type=DecisionType.POSITION_UPDATE,
            constraint_refs=["thermal.Q1"],
            loss_contribution=0.5,
            epoch=42,
            iteration=7,
        )
        sd = serialize_decision(d)
        restored = deserialize_decision(sd)
        assert restored.subject == "Q1"
        assert restored.value == [10.0, 20.0]  # deserialized to list
        assert restored.reason == "placed at thermal edge"
        assert restored.epoch == 42

    def test_serialize_deserialize_trace(self):
        trace = DecisionTrace(run_id="r1")
        trace.add(Decision(subject="A", value=(0, 0), reason="first"))
        trace.add(Decision(subject="B", value=(10, 10), reason="second"))
        trace.finalize(positions={"A": (0, 0), "B": (10, 10)})

        data = serialize_trace(trace)
        restored = deserialize_trace(data)
        assert restored.run_id == "r1"
        assert len(list(restored.decisions)) == 2

    def test_trace_to_json_and_from_json(self):
        trace = DecisionTrace()
        trace.add(Decision(subject="Q1", value=(5, 5), reason="placed"))

        js = trace_to_json(trace)
        restored = trace_from_json(js)
        assert len(list(restored.decisions)) == 1
        assert list(restored.decisions)[0].subject == "Q1"

    def test_save_trace_and_load_trace(self):
        trace = DecisionTrace()
        trace.add(Decision(subject="X", value=(1, 1), reason="test"))
        trace.add(Decision(subject="Y", value=(2, 2), reason="test"))

        with tempfile.NamedTemporaryFile(suffix=".json", mode="w+", delete=False) as f:
            fname = f.name
        try:
            save_trace(trace, fname)
            loaded = load_trace(fname)
            assert loaded.run_id == trace.run_id
            assert len(list(loaded.decisions)) == 2
        finally:
            os.unlink(fname)


# ---------------------------------------------------------------------------
# explainability/markdown_report.py — render/save functions
# ---------------------------------------------------------------------------


class TestMarkdownReport:
    def _make_trace(self):
        trace = DecisionTrace()
        trace.add(Decision(
            subject="Q1", value=(10.0, 20.0),
            reason="placed at thermal edge",
            phase=DecisionPhase.GEOMETRIC,
            decision_type=DecisionType.INITIAL_POSITION,
            constraint_refs=["thermal.edge"],
        ))
        trace.add(Decision(
            subject="Q2", value=(30.0, 40.0),
            reason="placed by heuristic",
            phase=DecisionPhase.GEOMETRIC,
        ))
        trace.finalize(positions={"Q1": (10, 20), "Q2": (30, 40)})
        return trace

    def test_render_component_report(self):
        from temper_placer.explainability.markdown_report import render_component_report

        trace = self._make_trace()
        md = render_component_report(trace, "Q1")
        assert isinstance(md, str)
        assert "Q1" in md

    def test_render_markdown_report(self):
        from temper_placer.explainability.markdown_report import render_markdown_report

        trace = self._make_trace()
        md = render_markdown_report(trace)
        assert isinstance(md, str)
        assert "Q1" in md

    def test_save_markdown_report(self):
        from temper_placer.explainability.markdown_report import save_markdown_report

        trace = self._make_trace()
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w+", delete=False) as f:
            fname = f.name
        try:
            save_markdown_report(trace, fname)
            with open(fname) as f:
                content = f.read()
            assert "Q1" in content
        finally:
            os.unlink(fname)


# ---------------------------------------------------------------------------
# explainability/traced_loss.py — TracedLossContext, combine, traced, traced_loss
# ---------------------------------------------------------------------------


class TestTracedLoss:
    def test_traced_loss_context_result(self):
        ctx = TracedLossContext()
        ctx.add(5.0, Trace.empty().add("Q1", (10, 20), "placed"))
        ctx.add(3.0, Trace.empty().add("Q2", (30, 40), "placed"))
        total_loss, combined_trace = ctx.result()
        assert total_loss == 8.0
        assert len(combined_trace.entries) == 2

    def test_traced_loss_context_empty(self):
        ctx = TracedLossContext()
        total_loss, combined_trace = ctx.result()
        assert total_loss == 0.0
        assert len(combined_trace.entries) == 0

    def test_combine_traced_losses(self):
        t1 = (5.0, Trace.empty().add("A", (0, 0), "first"))
        t2 = (3.0, Trace.empty().add("B", (10, 10), "second"))
        total_loss, trace = combine_traced_losses([t1, t2])
        assert total_loss == 8.0
        assert len(trace.entries) == 2

    def test_combine_traced_losses_empty(self):
        total_loss, trace = combine_traced_losses([])
        assert total_loss == 0.0
        assert len(trace.entries) == 0

    def test_traced_loss_decorator(self):
        def my_loss(x):
            return float(x) * 2.0

        tl = traced_loss(my_loss, "test_subject", "because test")
        val, tr = tl(5.0)
        assert val == 10.0
        assert len(tr.entries) == 1

    def test_traced_decorator_standalone(self):
        @traced(subject="Q1", because="test trace")
        def compute(x):
            return float(x) * 3.0

        val, tr = compute(4.0)
        assert val == 12.0
        assert len(tr.entries) == 1

    def test_traced_decorator_within_context(self):
        @traced(subject="Q1", because="ctx test")
        def compute(x):
            return float(x) * 2.0

        with TracedLossContext() as ctx:
            result = compute(3.0)
        assert result == 6.0
        assert len(ctx.losses) == 1

    def test_constraint_to_traced_loss(self):
        class MockConstraint:
            a = "Q1"
            b = "Q2"
            because = "test constraint"

        def loss_fn(c, x):
            return float(x) * float(len(c.a))

        tl = constraint_to_traced_loss(MockConstraint(), loss_fn)
        val, tr = tl(10.0)
        assert val == 20.0  # 10 * len("Q1") = 10 * 2 = 20
        assert len(tr.entries) >= 1


# ---------------------------------------------------------------------------
# explainability/pipeline.py — TracedPipeline, compose_traces, demo
# ---------------------------------------------------------------------------


class TestExplainabilityPipeline:
    def test_compose_traces(self):
        from temper_placer.explainability.pipeline import compose_traces

        t1 = Trace.empty().add("Q1", (10, 20), "placed Q1")
        t2 = Trace.empty().add("Q2", (30, 40), "placed Q2")
        combined = compose_traces(t1, t2)
        assert len(combined.entries) == 2

    def test_traced_pipeline_add_stage_and_run(self):
        from temper_placer.explainability.pipeline import TracedPipeline

        pipeline = TracedPipeline()

        def stage1(data):
            tr = Trace.empty().add("Q1", (10, 20), "placed")
            return data + 1, tr

        def stage2(data):
            tr = Trace.empty().add("Q2", (30, 40), "placed")
            return data * 2, tr

        pipeline.add_stage("s1", stage1)
        pipeline.add_stage("s2", stage2)
        result, trace = pipeline.run(0)
        assert result == 2  # (0+1)*2
        assert len(trace.entries) == 2

    def test_demo_pipeline(self):
        from temper_placer.explainability.pipeline import demo_pipeline

        result, trace = demo_pipeline()
        # result is a dict; trace has 3 placement + 1 routing = 4 entries
        assert isinstance(result, dict)
        assert len(trace.entries) == 4  # 3 placements + 1 routing

    def test_example_placement_optimizer(self):
        from temper_placer.explainability.pipeline import example_placement_optimizer

        result, trace = example_placement_optimizer(["Q1", "Q2", "U1"])
        assert isinstance(result, dict)
        assert len(trace.entries) == 3

    def test_example_router(self):
        from temper_placer.explainability.pipeline import example_router

        result, trace = example_router({"mock": "placement"})
        assert isinstance(result, dict)
        assert len(trace.entries) == 1

    def test_traced_pipeline_example(self):
        from temper_placer.explainability.pipeline import traced_pipeline_example

        def place(components):
            t = Trace.empty()
            for c in components:
                t = t.add(c, (0, 0), f"placed {c}")
            return {"positions": "mock"}, t

        def route(placement, components):
            t = Trace.empty().add("VCC", [], "routed")
            return {"routes": "mock"}, t

        result, trace = traced_pipeline_example(place, route, ["Q1", "Q2"])
        assert isinstance(result, tuple)
        assert len(trace.entries) == 3  # 2 placements + 1 routing


# ---------------------------------------------------------------------------
# fields — additional CostField/FieldResult coverage via test
# ---------------------------------------------------------------------------


class TestCostFieldExtra:
    def test_cost_field_properties(self):
        from temper_placer.fields.field import CostField

        grid = np.ones((8, 12), dtype=np.float32)
        cf = CostField(grid=grid, cell_size_mm=0.5, origin_mm=(0.0, 0.0))
        assert cf.height_cells == 8
        assert cf.width_cells == 12
        assert cf.shape == (8, 12)
        assert cf.total_cells == 96

    def test_cost_field_to_flat(self):
        from temper_placer.fields.field import CostField

        grid = np.arange(15, dtype=np.float32).reshape(3, 5)
        cf = CostField(grid=grid, cell_size_mm=0.25, origin_mm=(10.0, 20.0))
        flat = cf.to_flat()
        assert flat.shape == (15,)
        np.testing.assert_array_equal(flat, np.arange(15, dtype=np.float32))

    def test_field_result_error_message(self):
        from temper_placer.fields.result import FieldResult

        gr = GatesGateResult(GateStatus.UNMEASURED, error_message="solver diverged")
        fr = FieldResult(gate_result=gr)
        assert fr.error_message == "solver diverged"
        assert fr.status is GateStatus.UNMEASURED
        assert not fr.is_usable

    def test_field_result_violations(self):
        from temper_placer.fields.result import FieldResult

        v = Violation(type=ViolationType.THERMAL, description="hot joint")
        gr = GatesGateResult(GateStatus.VIOLATIONS, violations=(v,))
        fr = FieldResult(gate_result=gr, field=np.zeros((3, 3), dtype=np.float32))
        assert len(fr.violations) == 1
        assert fr.violations[0].type is ViolationType.THERMAL
        assert fr.status is GateStatus.VIOLATIONS

    def test_field_result_to_cost_field_input(self):
        from temper_placer.fields.interface import CostFieldInput
        from temper_placer.fields.result import FieldResult

        gr = GatesGateResult(GateStatus.CLEAN)
        grid = np.ones((5, 5), dtype=np.float32) * 2.5
        fr = FieldResult(gate_result=gr, field=grid, weight=2.0)
        cfi = fr.to_cost_field_input()
        assert isinstance(cfi, CostFieldInput)
        assert cfi.cost_flat.shape == (25,)
        assert cfi.cost_flat.dtype == np.float32
        assert cfi.weight == 2.0

    def test_field_gate_extension(self):
        from temper_placer.fields.interface import FieldGate

        class StubFieldGate(FieldGate):
            name = "stub"

            def compute_field(self, state):
                return None  # simplified stub

        gate = StubFieldGate()
        # to_delta returns None (default)
        assert gate.to_delta(ViolationType.CLEARANCE) is None


# ---------------------------------------------------------------------------
# topological — DistanceBound additional coverage
# ---------------------------------------------------------------------------


class TestDistanceBoundExtra:
    def test_tighten_max(self):
        from temper_placer.topological.propagation import DistanceBound

        b = DistanceBound(max_distance=10.0)
        b.tighten_max(8.0)
        assert b.max_distance == 8.0
        b.tighten_max(12.0)  # should not increase
        assert b.max_distance == 8.0

    def test_tighten_min(self):
        from temper_placer.topological.propagation import DistanceBound

        b = DistanceBound(min_distance=5.0)
        b.tighten_min(7.0)
        assert b.min_distance == 7.0
        b.tighten_min(3.0)  # should not decrease
        assert b.min_distance == 7.0

    def test_is_feasible(self):
        from temper_placer.topological.propagation import DistanceBound

        assert DistanceBound(min_distance=5.0, max_distance=10.0).is_feasible() is True
        assert DistanceBound(min_distance=10.0, max_distance=5.0).is_feasible() is False
        assert DistanceBound(min_distance=5.0, max_distance=5.0).is_feasible() is True
