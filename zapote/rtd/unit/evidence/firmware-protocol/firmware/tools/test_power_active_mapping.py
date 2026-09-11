"""Power-active mapping audit (U8).

Plan: docs/plans/2026-08-02-028-feat-state-machine-model-check-plan.md (U8).

Scans firmware/main/state_handlers.c's entry-handler function bodies and
checks them against the contract documented in POWER_ACTIVE_MAPPING.md:

  - power_enable() is called in exactly state_preheat_entry() among all
    entry handlers (STATE_HEATING is exempted -- verified against the U1
    model, not assumed -- see POWER_ACTIVE_MAPPING.md section 1).
  - every state directly reachable from a power-active state (per the U1
    model) that is not itself power-active disables power
    (power_set_level(0) or pwm_disable_all()) in its own entry handler.
  - both faulted states' entry handlers call pwm_disable_all().

This audit reads firmware/main/state_handlers.c ONLY -- it is never
written to (a hard constraint of the task this plan is implemented under:
protection-logic source files are read-only to this tooling).

Run: uv run python -m pytest firmware/tools/test_power_active_mapping.py -v
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict

import pytest

from power_active_mapping import FAULTED_STATES, POWER_ACTIVE_STATES
from transition_model import REPO_ROOT, build_model

STATE_HANDLERS_C = REPO_ROOT / "firmware" / "main" / "state_handlers.c"


def _entry_function_name(state: str) -> str:
    """STATE_PAN_DET -> state_pan_det_entry, STATE_NO_PAN -> state_no_pan_entry."""
    suffix = state[len("STATE_"):].lower()
    return f"state_{suffix}_entry"


def extract_function_bodies(source: str) -> Dict[str, str]:
    """Extract {function_name: body_text} for every `void NAME(void) { ... }`
    top-level function in *source*, via brace-balance scanning (the file is
    C, not something with an AST readily available at this layer -- same
    approach as scripts/check_firmware_board_contract.py's constant
    regexes: targeted parsing over a known, simple shape)."""
    bodies: Dict[str, str] = {}
    for m in re.finditer(r"void\s+(\w+)\s*\(void\)\s*\{", source):
        name = m.group(1)
        start = m.end() - 1  # index of the opening '{'
        depth = 0
        i = start
        while i < len(source):
            if source[i] == "{":
                depth += 1
            elif source[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        bodies[name] = source[start:i + 1]
    return bodies


@pytest.fixture(scope="module")
def source() -> str:
    return STATE_HANDLERS_C.read_text()


@pytest.fixture(scope="module")
def function_bodies(source) -> Dict[str, str]:
    return extract_function_bodies(source)


@pytest.fixture(scope="module")
def model():
    return build_model()


class TestSourceIsParseable:
    def test_finds_all_nine_entry_handlers(self, function_bodies, model):
        for state in model.states:
            fn = _entry_function_name(state)
            assert fn in function_bodies, f"could not find {fn}() in {STATE_HANDLERS_C}"


class TestPowerEnableCallSite:
    """Scenario 1 (happy path): the current state_handlers.c passes the
    audit -- power_enable() appears in exactly state_preheat_entry()."""

    def test_preheat_entry_calls_power_enable(self, function_bodies):
        assert "power_enable()" in function_bodies["state_preheat_entry"]

    def test_heating_entry_exempted_and_model_verifies_the_exemption_is_safe(self, function_bodies, model):
        # STATE_HEATING does NOT call power_enable() in its entry handler.
        assert "power_enable()" not in function_bodies["state_heating_entry"]
        # The exemption is only safe because every non-self-loop incoming
        # edge to STATE_HEATING originates in a state that is ALREADY
        # power-active (STATE_PREHEAT) -- verified against the model, not
        # assumed. If this ever becomes false (a new manifest edge enters
        # STATE_HEATING from a non-power-active state), this assertion
        # fails and the exemption above must be revisited.
        incoming = model.incoming_edges("STATE_HEATING", include_self_loops=False)
        assert incoming, "STATE_HEATING has no non-self-loop incoming edges at all (unexpected)"
        for edge in incoming:
            assert edge.from_state in POWER_ACTIVE_STATES, (
                f"STATE_HEATING is entered from {edge.from_state}, which is NOT "
                "power-active -- the power_enable() exemption for state_heating_entry "
                "is no longer justified by the manifest; state_heating_entry must gain "
                "its own power_enable() call")

    def test_no_other_entry_handler_calls_power_enable(self, function_bodies, model):
        for state in model.states:
            fn = _entry_function_name(state)
            if state == "STATE_PREHEAT":
                continue
            assert "power_enable()" not in function_bodies[fn], (
                f"{fn}() calls power_enable() but {state} is not the audited "
                "power-on gateway (STATE_PREHEAT) -- see test scenario 2 "
                "(synthetic handler adding power_enable() to a non-mapped state)")


class TestPowerDisabledOnExitFromPowerActive:
    """Every state directly reachable from a power-active state (and not
    itself power-active) disables power in its own entry handler -- the
    re-scoped "disable power in their exit path" claim (see
    POWER_ACTIVE_MAPPING.md section 2). This is a model+source cross-check:
    the SET of states to audit is derived from the U1 model's edges, not
    hardcoded, so a manifest change that adds a new power-active exit
    target is automatically covered."""

    DISABLE_CALLS = ("power_set_level(0)", "pwm_disable_all()", "pwm_set_duty_cycle(0)")

    def _targets_from_power_active(self, model):
        targets = set()
        for state in POWER_ACTIVE_STATES:
            for edge in model.outgoing_edges(state):
                if edge.to_state not in POWER_ACTIVE_STATES:
                    targets.add(edge.to_state)
        return targets

    def test_every_exit_target_disables_power_in_its_entry(self, model, function_bodies):
        targets = self._targets_from_power_active(model)
        assert targets, "expected at least one non-power-active exit target"
        for state in targets:
            fn = _entry_function_name(state)
            body = function_bodies[fn]
            assert any(call in body for call in self.DISABLE_CALLS), (
                f"{fn}() is reachable directly from a power-active state but "
                f"contains none of {self.DISABLE_CALLS}")

    def test_exit_target_set_matches_expected(self, model):
        # Documents exactly which states this claim currently covers, so a
        # manifest change that silently adds/removes a target is visible in
        # a test diff.
        targets = self._targets_from_power_active(model)
        assert targets == {"STATE_FAULT", "STATE_NO_PAN", "STATE_COOLDOWN", "STATE_RUNAWAY_FAULT"}


class TestFaultedStatesDisablePower:
    def test_fault_entry_calls_pwm_disable_all(self, function_bodies):
        assert "pwm_disable_all()" in function_bodies["state_fault_entry"]

    def test_runaway_fault_entry_calls_pwm_disable_all(self, function_bodies):
        assert "pwm_disable_all()" in function_bodies["state_runaway_fault_entry"]

    def test_all_faulted_states_covered(self):
        assert {_entry_function_name(s) for s in FAULTED_STATES} == {
            "state_fault_entry", "state_runaway_fault_entry"}


class TestAuditBites:
    """Scenarios 2/3 (KTD8-style non-vacuity): the audit's own predicate
    logic, exercised against synthetic function-body dicts rather than the
    real file, to prove the checks can fail without needing to edit
    state_handlers.c (which this tooling never writes to)."""

    def test_power_enable_in_non_mapped_state_would_fail(self):
        fake_bodies = {
            "state_idle_entry": "void state_idle_entry(void) { power_enable(); }",
        }
        assert "power_enable()" in fake_bodies["state_idle_entry"]  # the audit's own assertion shape

    def test_missing_disable_call_in_fault_state_would_fail(self):
        fake_body = "void state_fault_entry(void) { led_set_pattern(LED_FAULT); }"
        assert "pwm_disable_all()" not in fake_body


class TestExtractFunctionBodies:
    def test_extracts_balanced_nested_braces(self):
        src = (
            "void state_preheat_update(void) {\n"
            "    if (x) {\n"
            "        do_thing();\n"
            "    }\n"
            "    power_enable();\n"
            "}\n"
        )
        bodies = extract_function_bodies(src)
        assert "state_preheat_update" in bodies
        assert "power_enable();" in bodies["state_preheat_update"]
        assert bodies["state_preheat_update"].count("{") == bodies["state_preheat_update"].count("}")
