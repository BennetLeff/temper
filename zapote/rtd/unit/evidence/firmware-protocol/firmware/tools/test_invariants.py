"""Host pytest for invariants.py (U5) and the seed invariant set (U6).

Every invariant carries a named counter-example mutation (KTD8) -- the
proven-non-vacuity discipline applied to proofs: a passing invariant is
only meaningful if the check is known to be capable of failing.

Run: uv run python -m pytest firmware/tools/test_invariants.py -v
"""

from __future__ import annotations

import copy
import dataclasses

import pytest

from invariants import (
    evaluate_all,
    evaluate_invariant,
    load_invariant_specs,
    reachable_excluding_expansion,
)
from transition_model import Edge, FAULT_NONE, INIT_STATE, build_model


@pytest.fixture(scope="module")
def model():
    return build_model()


@pytest.fixture(scope="module")
def specs():
    return load_invariant_specs()


def _mutate(model, key, **overrides):
    mutant = copy.copy(model)
    mutant.edges = dict(model.edges)
    mutant.edges[key] = dataclasses.replace(mutant.edges[key], **overrides)
    return mutant


def _spec(specs, invariant_id):
    return next(s for s in specs if s["id"] == invariant_id)


# ---------------------------------------------------------------------------
# U6: the seed invariant set on the current (real) manifest.
# ---------------------------------------------------------------------------

class TestSeedInvariantsHappyPath:
    """Scenario 1: all invariants verify on the current manifest -- the
    plan's four seed invariants (U6) plus I-RUNAWAY-REACHES-SAFE-STATE
    (the task-directed runaway-to-safe-state property)."""

    def test_all_five_declared(self, specs):
        assert {s["id"] for s in specs} == {
            "I-OVERTEMP-DISABLES", "I-SENSOR-FAULT-BLOCKS-HEATING",
            "I-FAULT-EXITS", "I-NO-REENTRY", "I-RUNAWAY-REACHES-SAFE-STATE",
        }

    def test_all_verify_on_current_manifest(self, model, specs):
        results = evaluate_all(model, specs)
        for r in results:
            assert r.passed, f"{r.invariant_id} failed: {[v.detail for v in r.violations]}"

    def test_evidence_nonzero(self, model, specs):
        results = evaluate_all(model, specs)
        for r in results:
            assert r.evidence_count > 0


class TestIOvertempDisablesBites:
    """Scenario 2: (STATE_HEATING, EVENT_OVER_TEMP) -> STATE_HEATING fails
    I-OVERTEMP-DISABLES."""

    def test_over_temp_self_loop_fails(self, model, specs):
        spec = _spec(specs, "I-OVERTEMP-DISABLES")
        mutant = _mutate(model, ("STATE_HEATING", "EVENT_OVER_TEMP"),
                          to_state="STATE_HEATING", fault=FAULT_NONE)
        result = evaluate_invariant(mutant, spec)
        assert not result.passed
        assert any(v.edge and v.edge.event == "EVENT_OVER_TEMP" for v in result.violations)

    def test_cooldown_overheat_self_loop_fails(self, model, specs):
        spec = _spec(specs, "I-OVERTEMP-DISABLES")
        mutant = _mutate(model, ("STATE_COOLDOWN", "EVENT_COOLDOWN_OVERHEAT"),
                          to_state="STATE_COOLDOWN", fault=FAULT_NONE)
        result = evaluate_invariant(mutant, spec)
        assert not result.passed


class TestINoReentryAndIFaultExitsBite:
    """Scenario 3: (STATE_FAULT, EVENT_FAULT_RESET_CLEARED) -> STATE_HEATING
    fails BOTH I-NO-REENTRY and I-FAULT-EXITS."""

    def test_fails_no_reentry(self, model, specs):
        spec = _spec(specs, "I-NO-REENTRY")
        mutant = _mutate(model, ("STATE_FAULT", "EVENT_FAULT_RESET_CLEARED"),
                          to_state="STATE_HEATING")
        result = evaluate_invariant(mutant, spec)
        assert not result.passed
        assert any("STATE_HEATING" in v.detail for v in result.violations)

    def test_fails_fault_exits(self, model, specs):
        spec = _spec(specs, "I-FAULT-EXITS")
        mutant = _mutate(model, ("STATE_FAULT", "EVENT_FAULT_RESET_CLEARED"),
                          to_state="STATE_HEATING")
        result = evaluate_invariant(mutant, spec)
        assert not result.passed


class TestSensorFaultBlocksHeatingBites:
    """Scenario for I-SENSOR-FAULT-BLOCKS-HEATING: a sensor-fault event
    from a power-active state that stays power-active fails the
    invariant."""

    def test_probe_open_targeting_heating_fails(self, model, specs):
        spec = _spec(specs, "I-SENSOR-FAULT-BLOCKS-HEATING")
        mutant = _mutate(model, ("STATE_HEATING", "EVENT_PROBE_OPEN"),
                          to_state="STATE_HEATING", fault=FAULT_NONE)
        result = evaluate_invariant(mutant, spec)
        assert not result.passed


class TestRunawayReachesSafeStateBites:
    """The task-directed safety property: from every reachable state, a
    runaway condition leads to a safe/de-energized state. KTD8
    counter-example: if a wildcard edge were mistakenly routed to a
    power-active state instead of STATE_RUNAWAY_FAULT, the invariant must
    catch it -- proving the check is not vacuously true by construction."""

    def test_wildcard_edge_to_power_active_state_fails(self, model, specs):
        spec = _spec(specs, "I-RUNAWAY-REACHES-SAFE-STATE")
        mutant = _mutate(model, ("STATE_PREHEAT", "EVENT_RUNAWAY_ABSOLUTE_TEMP"),
                          to_state="STATE_HEATING")
        result = evaluate_invariant(mutant, spec)
        assert not result.passed
        assert any(v.edge and v.edge.from_state == "STATE_PREHEAT" for v in result.violations)

    def test_wildcard_edge_to_non_faulted_benign_state_fails(self, model, specs):
        spec = _spec(specs, "I-RUNAWAY-REACHES-SAFE-STATE")
        mutant = _mutate(model, ("STATE_IDLE", "EVENT_RUNAWAY_RISE_RATE"),
                          to_state="STATE_IDLE")
        result = evaluate_invariant(mutant, spec)
        assert not result.passed

    def test_holds_from_every_one_of_the_nine_states(self, model, specs):
        spec = _spec(specs, "I-RUNAWAY-REACHES-SAFE-STATE")
        result = evaluate_invariant(model, spec)
        assert result.passed
        # 9 states x 2 wildcard events = 18 edges of evidence.
        assert result.evidence_count == len(model.states) * 2


class TestFaultCodeDisciplineBites:
    """Scenario 4: a synthetic row adding a fault code to a benign
    transition fails the code discipline I-FAULT-EXITS relies on (P3's
    discipline, exercised here at the invariant layer via I-OVERTEMP-
    DISABLES's require_fault_not clause, which is the load-bearing half of
    that discipline for this invariant)."""

    def test_over_temp_with_fault_none_fails(self, model, specs):
        spec = _spec(specs, "I-OVERTEMP-DISABLES")
        mutant = _mutate(model, ("STATE_PREHEAT", "EVENT_OVER_TEMP"), fault=FAULT_NONE)
        result = evaluate_invariant(mutant, spec)
        assert not result.passed


# ---------------------------------------------------------------------------
# U5: the invariants engine itself, demonstrated with a trivial invariant.
# ---------------------------------------------------------------------------

class TestStateInductionEngine:
    """Scenario 1 (U5): a trivial invariant ('state is one of the 9
    states') verifies over the full model with per-edge evidence."""

    def test_trivial_invariant_verifies(self, model):
        spec = {
            "id": "TEST-TRIVIAL-ALL-STATES",
            "kind": "state_induction",
            "predicate": {"state_in": "all_states"},
        }
        result = evaluate_invariant(model, spec)
        assert result.passed
        assert result.base_case_holds is True
        assert result.evidence_count == len(model.edges)

    def test_base_case_failure(self, model):
        """Scenario 2 (U5): an invariant false at STATE_INIT fails at the
        base case."""
        spec = {
            "id": "TEST-EMPTY-PREDICATE",
            "kind": "state_induction",
            "predicate": {"state_in": []},
        }
        result = evaluate_invariant(model, spec)
        assert not result.passed
        assert result.base_case_holds is False
        assert any("base case" in v.detail for v in result.violations)

    def test_inductive_step_failure_via_runaway_interlock(self, model):
        """Scenario 3 (U5): the inductive step fails on an edge -- here,
        demonstrated by the real KTD2 interlock edges (every state can
        transition to STATE_RUNAWAY_FAULT), which is exactly the
        "wildcard transition" this whole plan exists to make visible to a
        model: a predicate excluding STATE_RUNAWAY_FAULT cannot be an
        invariant of this machine, and the induction engine catches it."""
        spec = {
            "id": "TEST-EXCLUDES-RUNAWAY-FAULT",
            "kind": "state_induction",
            "predicate": {"state_in": [s for s in model.states if s != "STATE_RUNAWAY_FAULT"]},
        }
        result = evaluate_invariant(model, spec)
        assert not result.passed
        assert result.base_case_holds  # STATE_INIT is fine
        assert any(v.edge and v.edge.to_state == "STATE_RUNAWAY_FAULT" for v in result.violations)

    def test_derived_flag_power_active_evaluates_per_state(self, model):
        """Scenario 4 (U5): an invariant over a derived flag (power_active)
        evaluates correctly on states that do and do not carry it."""
        spec = {
            "id": "TEST-POWER-ACTIVE-FLAG",
            "kind": "state_induction",
            "predicate": {"state_in": "power_active"},
        }
        result = evaluate_invariant(model, spec)
        # STATE_INIT does not carry power_active -- base case correctly false.
        assert result.base_case_holds is False
        # A state that legitimately carries the flag (STATE_PREHEAT) must
        # not itself be reported as a base-case violation (only STATE_INIT
        # is checked as the base case).
        assert all("STATE_PREHEAT" not in v.detail for v in result.violations
                   if "base case" in v.detail)


class TestReachableExcludingExpansion:
    def test_stop_state_included_but_not_expanded(self, model):
        # From STATE_FAULT, STATE_INIT is reachable but its own outgoing
        # edges (e.g. -> STATE_IDLE) must not be followed.
        reached = reachable_excluding_expansion(model, "STATE_FAULT", frozenset({INIT_STATE}))
        assert INIT_STATE in reached
        assert "STATE_IDLE" not in reached

    def test_dead_end_runaway_fault_reaches_only_itself(self, model):
        reached = reachable_excluding_expansion(model, "STATE_RUNAWAY_FAULT", frozenset({INIT_STATE}))
        assert reached == frozenset({"STATE_RUNAWAY_FAULT"})


class TestLoadInvariantSpecs:
    def test_no_duplicate_ids(self, specs):
        ids = [s["id"] for s in specs]
        assert len(ids) == len(set(ids))

    def test_every_spec_has_a_known_kind(self, specs):
        for s in specs:
            assert s["kind"] in {"edge", "exit_set", "path", "state_induction"}
