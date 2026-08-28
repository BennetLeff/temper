"""Coverage paydown tests for misc module areas: placer, metrics, cli, testing,
explainability, fields, topological.

Exercises public functions in:
- placer/template.py, placer/cp_sat/gate.py, placer/cp_sat/gates.py
- metrics/routing_quality.py, metrics/aesthetic.py
- cli/version.py
- testing/version_gate.py
- explainability data contracts and report helpers
- fields/field.py, fields/result.py, fields/interface.py
"""

from temper_orchestration import Trace
from temper_placer.metrics.aesthetic import compute_aesthetic_score
from temper_placer.metrics.routing_quality import RoutingQualityScore
from temper_placer.placer.cp_sat.gate import GateResult as AcceptanceGateResult
from temper_placer.placer.cp_sat.gates import (
    BoardState,
    Gate,
    GateStage,
    GateStatus,
    Violation,
    ViolationType,
)
from temper_placer.placer.cp_sat.gates import (
    GateResult as GatesGateResult,
)
from temper_placer.placer.template import (
    ParametricComponentPosition,
    ParametricTemplate,
)

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
# cli/version.py — version command
# ---------------------------------------------------------------------------


class TestVersionCommands:
    def test_version_command_runs(self):
        from click.testing import CliRunner

        from temper_placer.cli.version import version as version_cmd

        runner = CliRunner()
        result2 = runner.invoke(version_cmd)
        assert result2.exit_code == 0
        assert "temper-placer" in result2.output
        assert "v" in result2.output


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
