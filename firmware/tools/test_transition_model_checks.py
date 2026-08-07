"""Host pytest for transition_model_checks.py (U2).

Includes a mutation harness (synthetic bad edges injected into the model in
memory, per KTD8) demonstrating each property can fail -- so a passing
property check is known to bite, not vacuous.

Run: uv run python -m pytest firmware/tools/test_transition_model_checks.py -v
"""

from __future__ import annotations

import copy
import dataclasses

import pytest

from transition_model import Edge, FAULT_NONE, build_model
from transition_model_checks import run_all_checks


@pytest.fixture(scope="module")
def model():
    return build_model()


def _mutate(model, key, edge_overrides):
    """Return a shallow-mutated copy of *model* with model.edges[key]
    replaced by dataclasses.replace(model.edges[key], **edge_overrides)."""
    mutant = copy.copy(model)
    mutant.edges = dict(model.edges)
    original = mutant.edges[key]
    mutant.edges[key] = dataclasses.replace(original, **edge_overrides)
    return mutant


def _mutate_new_edge(model, key, edge):
    mutant = copy.copy(model)
    mutant.edges = dict(model.edges)
    mutant.edges[key] = edge
    return mutant


def _result(results, name):
    return next(r for r in results if r.name == name)


class TestHappyPath:
    """Scenario 1: all four properties pass on the current manifest."""

    def test_all_properties_pass(self, model):
        results = run_all_checks(model)
        for r in results:
            assert r.passed, f"{r.name} failed unexpectedly: {[v.message for v in r.violations]}"

    def test_evidence_counts_are_nonzero(self, model):
        results = run_all_checks(model)
        for r in results:
            assert r.evidence_count > 0


class TestP2Bites:
    """Scenario 2: a synthetic edge (STATE_HEATING, EVENT_OVER_TEMP) ->
    STATE_HEATING (instead of STATE_FAULT) fails P2, naming the row."""

    def test_over_temp_self_loop_fails_p2(self, model):
        key = ("STATE_HEATING", "EVENT_OVER_TEMP")
        mutant = _mutate(model, key, {"to_state": "STATE_HEATING", "fault": FAULT_NONE})
        results = run_all_checks(mutant)
        p2 = _result(results, "P2")
        assert not p2.passed
        assert any(v.edge.from_state == "STATE_HEATING" and v.edge.event == "EVENT_OVER_TEMP"
                   for v in p2.violations)


class TestP1Bites:
    """Scenario 3: a synthetic row (STATE_FAULT, EVENT_OVER_TEMP) ->
    STATE_PREHEAT fails P1."""

    def test_fault_to_preheat_fails_p1(self, model):
        key = ("STATE_FAULT", "EVENT_OVER_TEMP")
        new_edge = Edge(from_state="STATE_FAULT", event="EVENT_OVER_TEMP",
                         to_state="STATE_PREHEAT", fault=FAULT_NONE)
        mutant = _mutate_new_edge(model, key, new_edge)
        results = run_all_checks(mutant)
        p1 = _result(results, "P1")
        assert not p1.passed
        assert any(v.edge.from_state == "STATE_FAULT" and v.edge.to_state == "STATE_PREHEAT"
                   for v in p1.violations)


class TestP3Bites:
    """Scenario 4: a row with a fault target but FAULT_NONE fails P3."""

    def test_fault_target_without_code_fails_p3(self, model):
        key = ("STATE_HEATING", "EVENT_OVER_TEMP")
        mutant = _mutate(model, key, {"fault": FAULT_NONE})  # still targets STATE_FAULT
        results = run_all_checks(mutant)
        p3 = _result(results, "P3")
        assert not p3.passed
        assert any(v.edge.from_state == "STATE_HEATING" and v.edge.to_state == "STATE_FAULT"
                   for v in p3.violations)

    def test_fault_code_on_non_fault_target_fails_p3(self, model):
        key = ("STATE_HEATING", "EVENT_STOP_BUTTON")  # targets STATE_COOLDOWN, benign
        mutant = _mutate(model, key, {"fault": "FAULT_OVER_TEMP"})
        results = run_all_checks(mutant)
        p3 = _result(results, "P3")
        assert not p3.passed

    def test_self_loop_persists_rows_do_not_trip_p3(self, model):
        # Documented scoping: the FAULT/RUNAWAY_FAULT self-loop persists
        # rows carry FAULT_NONE and are exempted from P3's "target implies
        # code" direction -- they must NOT appear as violations on the
        # unmutated model (covered by TestHappyPath, restated explicitly
        # here for the scoping decision).
        results = run_all_checks(model)
        p3 = _result(results, "P3")
        offending = [v for v in p3.violations
                     if v.edge.from_state == v.edge.to_state]
        assert offending == []


class TestP4Bites:
    def test_edge_to_unknown_state_fails_p4(self, model):
        key = ("STATE_IDLE", "EVENT_START_BUTTON")
        mutant = _mutate(model, key, {"to_state": "STATE_DOES_NOT_EXIST"})
        results = run_all_checks(mutant)
        p4 = _result(results, "P4")
        assert not p4.passed


class TestDerivedSensorFaultEventSet:
    def test_matches_plan_documented_set(self, model):
        from transition_model import derived_sensor_fault_events
        from power_active_mapping import FAULTED_STATES
        events = derived_sensor_fault_events(model, FAULTED_STATES)
        expected = {
            "EVENT_SELFTEST_FAIL", "EVENT_PREHEAT_TIMEOUT", "EVENT_OVER_TEMP",
            "EVENT_OVER_CURRENT", "EVENT_FAN_FAILURE", "EVENT_PROBE_OPEN",
            "EVENT_PROBE_SHORT", "EVENT_THERMAL_RUNAWAY", "EVENT_COOLDOWN_OVERHEAT",
        }
        assert events == expected

    def test_fault_reset_persists_excluded(self, model):
        from transition_model import derived_sensor_fault_events
        from power_active_mapping import FAULTED_STATES
        events = derived_sensor_fault_events(model, FAULTED_STATES)
        assert "EVENT_FAULT_RESET_PERSISTS" not in events
