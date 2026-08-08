"""Host pytest for transition_manifest_crosscheck.py (U3).

Run: uv run python -m pytest firmware/tools/test_transition_manifest_crosscheck.py -v
"""

from __future__ import annotations

import pytest

from transition_manifest_crosscheck import (
    RowDivergence,
    crosscheck_codegen_drift,
    crosscheck_explicit_rows,
    crosscheck_wildcard_rows,
    run_crosscheck,
)
from transition_model import build_model


@pytest.fixture(scope="module")
def crosscheck_report():
    return run_crosscheck()


class TestCurrentTree:
    """Scenario 1 (adjusted for the real, discovered divergence -- see
    module docstring / crosscheck output): the two manifests are compared
    row-for-row and the codegen output matches. As of this plan's
    implementation, exactly ONE real (non-KTD2) divergence exists on the
    current tree: the STATE_FAULT/EVENT_FAULT_RESET_PERSISTS row's fault
    code (production declares FAULT_NONE; the test-side list declares
    FAULT_OVER_TEMP for its own two-step test-mechanics reasons -- see
    firmware/test/gen_transition_table.py's comment on that row). This is
    reported, not silently treated as a KTD2 exception, per KTD4's literal
    row-for-row-on-(from,event,to,fault) comparison. This test documents
    that finding as the CURRENT expected state so a regression (a NEW,
    different divergence appearing) is caught; it is intentionally not a
    green "agrees" assertion, because the tree is not, in fact, in
    agreement on this one row."""

    def test_exactly_one_known_explicit_divergence(self, crosscheck_report):
        assert len(crosscheck_report.explicit_divergences) == 1
        d = crosscheck_report.explicit_divergences[0]
        assert d.kind == "value_mismatch"
        assert d.from_state == "STATE_FAULT"
        assert d.event == "EVENT_FAULT_RESET_PERSISTS"
        assert d.production == ("STATE_FAULT", "FAULT_NONE")
        assert d.test == ("STATE_FAULT", "FAULT_OVER_TEMP")

    def test_no_wildcard_value_divergence(self, crosscheck_report):
        assert crosscheck_report.wildcard_divergences == []

    def test_documented_ktd2_exceptions_cover_the_four_non_active_states(self, crosscheck_report):
        # 4 states outside ACTIVE_STATES (INIT, IDLE, FAULT, RUNAWAY_FAULT)
        # x 2 wildcard events = 8 documented exceptions.
        assert len(crosscheck_report.wildcard_documented_exceptions) == 8

    def test_no_codegen_drift(self, crosscheck_report):
        assert crosscheck_report.codegen_drift == []

    def test_row_counts_are_positive(self, crosscheck_report):
        assert crosscheck_report.production_row_count == 32
        assert crosscheck_report.test_row_count > 0


class TestExplicitRowComparison:
    """Scenario 2/3: deleting/mismatching a row is caught with both
    (from, event) named and both values shown."""

    def test_missing_production_row_named(self):
        production = {("STATE_IDLE", "EVENT_START_BUTTON"): ("STATE_PAN_DET", "FAULT_NONE")}
        test = {}
        divergences = crosscheck_explicit_rows(production, test)
        assert len(divergences) == 1
        d = divergences[0]
        assert d.kind == "missing_in_test"
        assert d.from_state == "STATE_IDLE"
        assert d.event == "EVENT_START_BUTTON"
        assert d.production == ("STATE_PAN_DET", "FAULT_NONE")

    def test_value_mismatch_shows_both_values(self):
        production = {("STATE_PREHEAT", "EVENT_NEAR_TARGET"): ("STATE_HEATING", "FAULT_NONE")}
        test = {("STATE_PREHEAT", "EVENT_NEAR_TARGET"): ("STATE_IDLE", "FAULT_NONE")}
        divergences = crosscheck_explicit_rows(production, test)
        assert len(divergences) == 1
        d = divergences[0]
        assert d.kind == "value_mismatch"
        assert d.production == ("STATE_HEATING", "FAULT_NONE")
        assert d.test == ("STATE_IDLE", "FAULT_NONE")

    def test_row_only_in_test_side_named(self):
        production = {}
        test = {("STATE_IDLE", "EVENT_START_BUTTON"): ("STATE_PAN_DET", "FAULT_NONE")}
        divergences = crosscheck_explicit_rows(production, test)
        assert len(divergences) == 1
        assert divergences[0].kind == "missing_in_production"

    def test_agreeing_rows_produce_no_divergence(self):
        rows = {("STATE_IDLE", "EVENT_START_BUTTON"): ("STATE_PAN_DET", "FAULT_NONE")}
        assert crosscheck_explicit_rows(dict(rows), dict(rows)) == []


class TestWildcardRowComparison:
    def test_active_state_wildcard_matches_by_default(self):
        model = build_model()
        active_states = ["STATE_PAN_DET", "STATE_PREHEAT", "STATE_HEATING", "STATE_NO_PAN", "STATE_COOLDOWN"]
        test_wildcard = {
            (s, ev): ("STATE_RUNAWAY_FAULT", "FAULT_RUNAWAY_BOUNDARY")
            for s in active_states
            for ev in ("EVENT_RUNAWAY_ABSOLUTE_TEMP", "EVENT_RUNAWAY_RISE_RATE")
        }
        divergences, exceptions = crosscheck_wildcard_rows(model, test_wildcard, active_states)
        assert divergences == []
        assert len(exceptions) == 8  # the 4 non-active states x 2 events

    def test_wildcard_value_mismatch_detected(self):
        model = build_model()
        active_states = ["STATE_PAN_DET"]
        test_wildcard = {
            ("STATE_PAN_DET", "EVENT_RUNAWAY_ABSOLUTE_TEMP"): ("STATE_FAULT", "FAULT_RUNAWAY_BOUNDARY"),
            ("STATE_PAN_DET", "EVENT_RUNAWAY_RISE_RATE"): ("STATE_RUNAWAY_FAULT", "FAULT_RUNAWAY_BOUNDARY"),
        }
        divergences, _exceptions = crosscheck_wildcard_rows(model, test_wildcard, active_states)
        assert len(divergences) == 1
        assert divergences[0].kind == "value_mismatch"
        assert divergences[0].from_state == "STATE_PAN_DET"
        assert divergences[0].event == "EVENT_RUNAWAY_ABSOLUTE_TEMP"


class TestCodegenDriftCheck:
    def test_current_tree_has_no_drift(self):
        assert crosscheck_codegen_drift() == []
