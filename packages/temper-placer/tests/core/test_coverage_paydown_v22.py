"""Coverage paydown v22: explainability/logger, placer/cp_sat (model, gates,
netclass_constraints, unsat), and validation (validation_gates, preflight).

Targets are the remaining uncovered entries in buckets NOT owned by the
concurrent router_v6/deterministic/heuristics/regression/io unit:

- ``explainability/logger.py`` — DecisionLogger delegation shim (14 methods)
- ``placer/cp_sat/model.py`` — OR-Tools CpModel wrapper (17 of 19 methods;
  ``mm_to_units``/``units_to_mm`` skipped: ``temper_constraints`` extension
  is absent from the shared venv)
- ``placer/cp_sat/gates.py`` — gate ``check()`` fail-closed entry paths
- ``placer/cp_sat/netclass_constraints.py`` — auto-generated SEPARATED pairs
- ``placer/cp_sat/unsat.py`` — UNSAT-core extraction
- ``validation/validation_gates.py`` — four gates + orchestration
- ``validation/preflight.py`` — zone/component/tool preflight checks
"""

from types import SimpleNamespace

import pytest

from temper_placer.explainability.decision import DecisionPhase, DecisionType
from temper_placer.explainability.logger import DecisionLogger
from temper_placer.placer.cp_sat.gates import (
    BoardState,
    DrcGate,
    Gate,
    GateResult,
    GateStatus,
    IECCreepageGate,
    PhysicsGate,
    QualityGate,
    RoutingGate,
    StackupGate,
)
from temper_placer.placer.cp_sat.model import (
    CpSatModel,
    CpSolverSolution,
    SolveStatus,
)

# ---------------------------------------------------------------------------
# explainability/logger.py — DecisionLogger (14 allowlisted methods)
# ---------------------------------------------------------------------------


class TestDecisionLogger:
    def test_enable_disable_is_enabled(self):
        logger = DecisionLogger()
        assert logger.is_enabled() is True
        logger.disable()
        assert logger.is_enabled() is False
        logger.enable()
        assert logger.is_enabled() is True

    def test_set_phase_epoch_iteration(self):
        logger = DecisionLogger()
        logger.set_phase(DecisionPhase.ROUTING)
        logger.set_epoch(42)
        logger.set_iteration(7)
        assert logger.current_phase is DecisionPhase.ROUTING
        assert logger.current_epoch == 42
        assert logger.current_iteration == 7

    def test_phase_context_manager_restores(self):
        logger = DecisionLogger()
        logger.set_phase(DecisionPhase.GEOMETRIC)
        with logger.phase(DecisionPhase.SEMANTIC):
            assert logger.current_phase is DecisionPhase.SEMANTIC
        assert logger.current_phase is DecisionPhase.GEOMETRIC

    def test_epoch_context_manager_restores(self):
        logger = DecisionLogger()
        logger.set_epoch(1)
        with logger.epoch(500):
            assert logger.current_epoch == 500
        assert logger.current_epoch == 1

    def test_log_position(self):
        logger = DecisionLogger()
        logger.set_phase(DecisionPhase.GEOMETRIC)
        logger.set_epoch(7)
        logger.set_iteration(3)
        logger.log_position(
            "C1", (10.0, 20.0), previous=(0.0, 0.0), reason="gradient update",
        )
        assert len(logger.trace.decisions) == 1
        d = logger.trace.decisions[0]
        assert d.subject == "C1"
        assert d.value == (10.0, 20.0)
        assert d.previous_value == (0.0, 0.0)
        assert d.reason == "gradient update"
        assert d.decision_type is DecisionType.POSITION_UPDATE
        assert d.epoch == 7
        assert d.iteration == 3

    def test_log_rotation(self):
        logger = DecisionLogger()
        logger.log_rotation("C1", 2, previous=0, reason="polarity")
        assert len(logger.trace.decisions) == 1
        d = logger.trace.decisions[0]
        assert d.subject == "C1"
        assert d.value == 2
        assert d.decision_type is DecisionType.ROTATION

    def test_log_heuristic(self):
        logger = DecisionLogger()
        logger.log_heuristic("thermal_edge", "C1", (1.0, 2.0), confidence=0.9)
        assert len(logger.trace.decisions) == 1
        d = logger.trace.decisions[0]
        assert d.value == (1.0, 2.0)
        assert "thermal_edge" in d.reason

    def test_log_constraint_application(self):
        logger = DecisionLogger()
        logger.log_constraint_application("thermal.edge", ["C1", "C2"], "moved_to_edge")
        assert len(logger.trace.decisions) == 1
        d = logger.trace.decisions[0]
        assert "thermal.edge" in d.reason
        assert "C1" in d.reason and "C2" in d.reason

    def test_disabled_log_methods_are_noops(self):
        logger = DecisionLogger()
        logger.disable()
        logger.log_position("C1", (1.0, 1.0))
        logger.log_rotation("C1", 1)
        logger.log_heuristic("h", "C1", (2.0, 2.0))
        logger.log_constraint_application("c", ["C1"], "moved")
        assert len(logger.trace.decisions) == 0

    def test_should_log(self):
        logger = DecisionLogger()
        assert logger.should_log(0, interval=100) is True
        assert logger.should_log(50, interval=100) is False
        assert logger.should_log(100, interval=100) is True
        assert logger.should_log(99, interval=100, is_final=True) is True

    def test_significant_change(self):
        logger = DecisionLogger()
        # distance 5.0 against thresholds straddling it
        assert logger.significant_change((0.0, 0.0), (3.0, 4.0), threshold=5.0) is True
        assert logger.significant_change((0.0, 0.0), (3.0, 4.0), threshold=6.0) is False
        assert logger.significant_change((0.0, 0.0), (0.1, 0.0), threshold=0.5) is False


# ---------------------------------------------------------------------------
# placer/cp_sat/model.py — CpSatModel / CpSolverSolution
# ---------------------------------------------------------------------------


class TestCpSatModel:
    def _model(self):
        return CpSatModel(units_per_mm=100)

    def test_add_component_and_maps(self):
        m = self._model()
        c = m.add_component("U1", 0, 0, 200, 300)
        assert c.ref == "U1"
        assert [v.ref for v in m.components] == ["U1"]
        assert list(m.component_map.keys()) == ["U1"]
        assert m.get_component("U1") is c

    def test_add_component_duplicate_raises(self):
        m = self._model()
        m.add_component("U1", 0, 0, 100, 100)
        with pytest.raises(ValueError):
            m.add_component("U1", 0, 0, 100, 100)

    def test_get_component_missing_raises(self):
        m = self._model()
        with pytest.raises(KeyError):
            m.get_component("NOPE")

    def test_add_rotation_nonpolarized(self):
        m = self._model()
        m.add_component("U1", 0, 0, 200, 300)
        rot = m.add_rotation("U1", is_polarized=False)
        assert rot is not None
        assert m._components["U1"].rot_ref is rot

    def test_add_rotation_polarized(self):
        m = self._model()
        m.add_component("U1", 0, 0, 200, 300)
        assert m.add_rotation("U1", is_polarized=True) is None
        assert "U1" in m._rotation_pinned_refs

    def test_add_rotation_missing_raises(self):
        m = self._model()
        with pytest.raises(ValueError):
            m.add_rotation("NOPE", is_polarized=False)

    def test_add_no_overlap_2d(self):
        m = self._model()
        m.add_component("U1", 0, 0, 100, 100)
        m.add_component("U2", 0, 0, 100, 100)
        assumption = m.add_no_overlap_2d(["U1", "U2"])
        assert assumption is not None

    def test_add_keepout_interval(self):
        m = self._model()
        ix, iy = m.add_keepout_interval("k1", 0, 0, 50, 50)
        assert ix is not None and iy is not None
        assert len(m._keepout_intervals_x) == 1
        assert len(m._keepout_intervals_y) == 1

    def test_add_objective_term(self):
        m = self._model()
        v = m.new_int_var(0, 10, "v")
        m.add_objective_term(v, 2)
        assert len(m._objective_terms) == 1

    def test_new_assumption(self):
        m = self._model()
        a = m.new_assumption("edge_margin_X")
        assert len(m._assumptions) == 1
        assert m._assumption_labels[a.Index()] == "edge_margin_X"

    def test_new_int_var_and_new_bool_var(self):
        m = self._model()
        v = m.new_int_var(0, 5, "v")
        b = m.new_bool_var("b")
        assert v is not None and b is not None

    def test_add_constraint_enforced(self):
        m = self._model()
        v = m.new_int_var(0, 10, "v")
        a = m.new_assumption("a")
        m.add_constraint_enforced(v >= 3, a)

    def test_add_multiplication_equality(self):
        m = self._model()
        t = m.new_int_var(0, 100, "prod")
        a = m.new_int_var(0, 10, "a")
        b = m.new_int_var(0, 10, "b")
        m.add_multiplication_equality(t, a, b)

    def test_add_abs_diff_le(self):
        m = self._model()
        a = m.new_int_var(0, 10, "a")
        b = m.new_int_var(0, 10, "b")
        d = m.add_abs_diff_le(a, b, 5, "d")
        assert d is not None

    def test_add(self):
        m = self._model()
        v = m.new_int_var(0, 10, "v")
        m.add(v >= 1)

    def test_set_bounds(self):
        m = self._model()
        m.add_component("U1", 0, 0, 100, 100)
        m.set_bounds(0, 0, 500, 500)
        # one edge-margin assumption per component
        assert len(m._assumptions) == 1

    def test_solve_feasible(self):
        m = self._model()
        m.add_component("U1", 0, 0, 100, 100)
        m.set_bounds(0, 0, 1000, 1000)
        sol = m.solve(time_limit_s=5.0)
        assert sol.feasible is True
        assert "U1" in sol.positions

    def test_solve_infeasible(self):
        m = self._model()
        m.add_component("U1", 0, 0, 100, 100)
        m.set_bounds(0, 0, 1000, 1000)
        # Force infeasibility: x_start >= 2000 exceeds the 1_000_000 upper
        # bound domain by construction? No — use a contradictory constraint.
        m.add(m.get_component("U1").x_center >= 100)
        m.add(m.get_component("U1").x_center <= -100)
        sol = m.solve(time_limit_s=5.0)
        assert sol.feasible is False


class TestCpSolverSolutionFeasible:
    def test_feasible_property(self):
        s = CpSolverSolution(
            status=SolveStatus.OPTIMAL,
            objective_value=0.0,
            positions={},
            rotations={},
            sizes={},
            solve_time_s=0.0,
        )
        assert s.feasible is True

        inf = CpSolverSolution(
            status=SolveStatus.INFEASIBLE,
            objective_value=0.0,
            positions={},
            rotations={},
            sizes={},
            solve_time_s=0.0,
        )
        assert inf.feasible is False


# ---------------------------------------------------------------------------
# placer/cp_sat/gates.py — gate check() fail-closed entry paths
# ---------------------------------------------------------------------------


class TestGateChecks:
    def test_gate_base_check_raises(self):
        with pytest.raises(NotImplementedError):
            Gate().check(BoardState())

    def test_drc_gate_check_no_pcb(self):
        result = DrcGate().check(BoardState())
        assert result.status is GateStatus.UNMEASURED
        assert "No PCB" in result.error_message

    def test_routing_gate_check_no_pcb(self):
        result = RoutingGate().check(BoardState())
        assert result.status is GateStatus.UNMEASURED
        assert "No routed PCB" in result.error_message

    def test_stackup_gate_check_no_routing(self):
        result = StackupGate().check(BoardState())
        assert result.status is GateStatus.UNMEASURED
        assert "No routing data" in result.error_message

    def test_iec_creepage_gate_check_no_pcb(self):
        result = IECCreepageGate().check(BoardState())
        assert result.status is GateStatus.UNMEASURED
        assert "No routed PCB" in result.error_message

    def test_physics_gate_check_no_pcb(self):
        result = PhysicsGate().check(BoardState())
        assert result.status is GateStatus.UNMEASURED
        assert "No routed PCB" in result.error_message

    def test_quality_gate_check_no_pcb(self):
        result = QualityGate().check(BoardState())
        assert result.status is GateStatus.UNMEASURED
        assert "No routed PCB" in result.error_message

    def test_gate_result_contract(self):
        result = GateResult(GateStatus.CLEAN)
        assert result.status is GateStatus.CLEAN


# ---------------------------------------------------------------------------
# placer/cp_sat/netclass_constraints.py
# ---------------------------------------------------------------------------


class TestNetclassSeparatedConstraints:
    def test_generate_cross_class_constraints(self):
        # FIXED 2026-08-17 (docs/evidence/2026-08-17-netclass-classifier-
        # manifest-and-ieccreepagegate-liveness.md): a bare `DesignRules()`
        # has empty `net_classes`/`net_class_assignments`/`class_pairs`.
        # That was harmless pre-fix, because `_resolve_component_net_class`
        # classified nets via the standalone `classify_net_type()` keyword
        # heuristic and never consulted `design_rules` at all. Post-fix,
        # classification goes through `design_rules.get_rules_for_net()` --
        # the whole point of the fix is that it IS authoritative,
        # design_rules-sourced data (manifest/kicad_pro-backed
        # `TEMPER_NET_ASSIGNMENTS`), so an empty `DesignRules()` now
        # resolves every net to "Default" (no classes to match) and the
        # cross-class pair this test exercises silently disappears (both
        # sides fall to the same bucket). `create_temper_design_rules()`
        # populates the real table, matching every other test in this
        # module/suite and the function's real caller
        # (`_encoder_core.encode_constraints`, which always passes
        # `netclass_rules_data.design_rules`, never a bare `DesignRules()`).
        from temper_placer.core.design_rules import create_temper_design_rules
        from temper_placer.core.netlist import Component, Netlist, Pin
        from temper_placer.placer.cp_sat.netclass_constraints import (
            generate_netclass_separated_constraints,
        )

        q1 = Component(
            "Q1", "TO247", (10, 10),
            pins=[Pin("1", "1", (0.0, 0.0), net="DC_BUS+")],
            net_class="HighVoltage",
        )
        u1 = Component(
            "U1", "QFP100", (20, 20),
            pins=[Pin("1", "1", (0.0, 0.0), net="VCC")],
            net_class="Signal",
        )
        netlist = Netlist(components=[q1, u1])
        constraints = generate_netclass_separated_constraints(
            netlist, [q1, u1], create_temper_design_rules()
        )
        assert len(constraints) == 1
        assert {constraints[0].a, constraints[0].b} == {"Q1", "U1"}

    def test_generate_single_class_returns_empty(self):
        from temper_placer.core.design_rules import DesignRules
        from temper_placer.core.netlist import Component, Netlist, Pin
        from temper_placer.placer.cp_sat.netclass_constraints import (
            generate_netclass_separated_constraints,
        )

        q1 = Component(
            "Q1", "TO247", (10, 10),
            pins=[Pin("1", "1", (0.0, 0.0), net="DC_BUS+")],
            net_class="HighVoltage",
        )
        q2 = Component(
            "Q2", "TO247", (30, 10),
            pins=[Pin("1", "1", (0.0, 0.0), net="SW_NODE")],
            net_class="HighVoltage",
        )
        netlist = Netlist(components=[q1, q2])
        constraints = generate_netclass_separated_constraints(
            netlist, [q1, q2], DesignRules()
        )
        assert constraints == []


# ---------------------------------------------------------------------------
# placer/cp_sat/unsat.py
# ---------------------------------------------------------------------------


class TestUnsatCore:
    def test_extract_unsat_core(self):
        from ortools.sat.python import cp_model

        from temper_placer.pcl.constraints import ConstraintType
        from temper_placer.placer.cp_sat.unsat import (
            UnsatConstraint,
            extract_unsat_core,
        )

        model = cp_model.CpModel()
        x = model.NewIntVar(0, 10, "x")
        a = model.NewBoolVar("a")
        b = model.NewBoolVar("b")
        model.AddAssumption(a)
        model.AddAssumption(b)
        model.Add(x >= 5).OnlyEnforceIf(a)
        model.Add(x <= 2).OnlyEnforceIf(b)

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 5.0
        assert solver.Solve(model) == cp_model.INFEASIBLE

        constraint_map = {
            a.Index(): UnsatConstraint("A", ConstraintType.SEPARATED, "because A", a.Index()),
            b.Index(): UnsatConstraint("B", ConstraintType.SEPARATED, None, b.Index()),
        }
        report = extract_unsat_core(solver, model, [a, b], constraint_map)
        assert {c.name for c in report.sufficient_core} == {"A", "B"}
        assert {c.name for c in report.minimal_core} == {"A", "B"}


# ---------------------------------------------------------------------------
# validation/validation_gates.py
# ---------------------------------------------------------------------------


def _good_metrics():
    return SimpleNamespace(
        overlap_loss=0.0,
        boundary_loss=0.0,
        hv_clearance_violations=0,
        zone_violations=0,
        convergence_epoch=100,
        routing_completion_percent=100.0,
        drc_errors=0,
        failure_rate=0.01,
        loss_cv=0.1,
        creepage_estimate=6.0,
        spice_gate_overshoot=0.0,
        spice_power_ripple=0.0,
    )


class TestValidationGates:
    def test_placement_complete_gate_check(self):
        from temper_placer.validation.validation_gates import PlacementCompleteGate

        result = PlacementCompleteGate().check(_good_metrics())
        assert result.status.value == "pass"
        assert result.gate_name == "placement_complete"

    def test_routing_complete_gate_check(self):
        from temper_placer.validation.validation_gates import RoutingCompleteGate

        result = RoutingCompleteGate().check(_good_metrics())
        assert result.gate_name == "routing_complete"
        assert result.status.value in ("pass", "fail")

    def test_production_ready_gate_check(self):
        from temper_placer.validation.validation_gates import ProductionReadyGate

        result = ProductionReadyGate().check(_good_metrics())
        assert result.gate_name == "production_ready"
        assert result.status.value in ("pass", "fail")

    def test_validated_gate_check(self):
        from temper_placer.validation.validation_gates import ValidatedGate

        result = ValidatedGate().check(_good_metrics())
        assert result.gate_name == "validated"
        assert result.status.value in ("pass", "fail")

    def test_check_all_gates(self):
        from temper_placer.validation.validation_gates import check_all_gates

        result = check_all_gates(_good_metrics())
        assert result.placement_complete is not None
        assert result.routing_complete is not None
        assert result.production_ready is not None
        assert result.validated is not None
        assert result.all_passed is True


# ---------------------------------------------------------------------------
# validation/preflight.py
# ---------------------------------------------------------------------------


def _constraints():
    from temper_placer.core.board import Zone
    from temper_placer.io.config_loader import PlacementConstraints

    return PlacementConstraints(
        board_width_mm=100.0,
        board_height_mm=80.0,
        zones=[Zone("HV", (0, 0, 50, 80)), Zone("LV", (50, 0, 100, 80))],
        zone_assignments={"Q1": "HV", "U1": "LV"},
    )


def _netlist():
    from temper_placer.core.netlist import Component, Netlist

    return Netlist(
        components=[
            Component("Q1", "TO247", (10, 10), net_class="HighVoltage"),
            Component("U1", "QFP100", (20, 20), net_class="Signal"),
        ]
    )


class TestPreflight:
    def test_check_zones_fit_on_board(self):
        from temper_placer.validation.preflight import check_zones_fit_on_board

        result = check_zones_fit_on_board(_constraints())
        assert result.passed is True

    def test_check_zones_outside_board(self):
        from temper_placer.core.board import Zone
        from temper_placer.io.config_loader import PlacementConstraints
        from temper_placer.validation.preflight import check_zones_fit_on_board

        c = PlacementConstraints(
            board_width_mm=100.0,
            board_height_mm=80.0,
            zones=[Zone("HV", (0, 0, 50, 200))],  # extends past height
        )
        result = check_zones_fit_on_board(c)
        assert result.passed is False
        assert any(i.code == "ZONE_003" for i in result.issues)

    def test_check_components_have_zones(self):
        from temper_placer.validation.preflight import check_components_have_zones

        result = check_components_have_zones(_netlist(), _constraints())
        assert result.passed is True

    def test_check_impossible_constraints(self):
        from temper_placer.validation.preflight import check_impossible_constraints

        result = check_impossible_constraints(_netlist(), _constraints())
        assert result.passed is True

    def test_check_kicad_cli(self):
        from temper_placer.validation.preflight import check_kicad_cli

        result = check_kicad_cli()
        assert result.passed is True
        assert len(result.issues) == 1

    def test_check_ngspice(self):
        from temper_placer.validation.preflight import check_ngspice

        result = check_ngspice()
        assert result.passed is True
        assert len(result.issues) == 1

    def test_check_external_tools(self):
        from temper_placer.validation.preflight import check_external_tools

        result = check_external_tools()
        assert result.passed is True
        assert len(result.issues) == 2

    def test_run_all_preflight_checks(self):
        from temper_placer.validation.preflight import run_all_preflight_checks

        result = run_all_preflight_checks(_netlist(), _constraints())
        assert result.passed is True
