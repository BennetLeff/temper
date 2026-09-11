"""Host pytest for transition_model.py (U1).

Run: uv run python -m pytest firmware/tools/test_transition_model.py -v
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from transition_model import (
    FAULT_NONE,
    INIT_STATE,
    RUNAWAY_FAULT_CODE,
    RUNAWAY_FAULT_STATE,
    RUNAWAY_WILDCARD_EVENTS,
    STATE_MACHINE_H,
    TRANSITION_YAML,
    ModelParseError,
    build_model,
)


@pytest.fixture(scope="module")
def model():
    return build_model()


class TestHappyPath:
    """Scenario 1: reachability on the current manifest."""

    def test_all_nine_states_present(self, model):
        assert len(model.states) == 9

    def test_every_state_reachable_from_init(self, model):
        report = model.reachability_report()
        assert report.unreachable == frozenset()
        assert report.reachable == frozenset(model.states)

    def test_runaway_fault_reachable_only_via_interlock(self, model):
        report = model.reachability_report()
        assert RUNAWAY_FAULT_STATE in report.reachable
        assert RUNAWAY_FAULT_STATE in report.interlock_only
        # Every piece of evidence for entering RUNAWAY_FAULT from elsewhere
        # must be an implicit (KTD2) edge -- no declared row enters it.
        for edge in report.interlock_only[RUNAWAY_FAULT_STATE]:
            assert edge.implicit
            assert edge.to_state == RUNAWAY_FAULT_STATE
            assert edge.fault == RUNAWAY_FAULT_CODE

    def test_wildcard_interlock_present_from_every_state(self, model):
        for state in model.states:
            for event in RUNAWAY_WILDCARD_EVENTS:
                edge = model.edges[(state, event)]
                assert edge.implicit
                assert edge.to_state == RUNAWAY_FAULT_STATE
                assert edge.fault == RUNAWAY_FAULT_CODE


class TestInterlockOnlyClassification:
    """Scenario 2: a state with zero non-interlock incoming edges is
    classified as interlock-only with evidence."""

    def test_only_runaway_fault_is_interlock_only(self, model):
        interlock_only = model.interlock_only_states()
        assert set(interlock_only) == {RUNAWAY_FAULT_STATE}

    def test_normal_states_have_declared_incoming_edges(self, model):
        # STATE_IDLE has a real incoming edge (from STATE_INIT and
        # STATE_COOLDOWN, etc) -- must NOT be classified interlock-only.
        interlock_only = model.interlock_only_states()
        assert "STATE_IDLE" not in interlock_only
        assert "STATE_PREHEAT" not in interlock_only


class TestErrorPath:
    """Scenario 3: a manifest row referencing an unknown state/event fails
    parsing with the row named."""

    def _write_manifest(self, tmp_path: Path, rows: list[dict]) -> Path:
        p = tmp_path / "bad_manifest.yaml"
        p.write_text(yaml.safe_dump({"transitions": rows}))
        return p

    def test_unknown_from_state_names_row(self, tmp_path):
        bad = self._write_manifest(tmp_path, [
            {"from": "STATE_DOES_NOT_EXIST", "event": "EVENT_SELFTEST_PASS", "to": "STATE_IDLE"},
        ])
        with pytest.raises(ModelParseError) as exc_info:
            build_model(manifest_path=bad, header_path=STATE_MACHINE_H)
        assert "row 0" in str(exc_info.value)
        assert "STATE_DOES_NOT_EXIST" in str(exc_info.value)

    def test_unknown_event_names_row(self, tmp_path):
        bad = self._write_manifest(tmp_path, [
            {"from": "STATE_INIT", "event": "EVENT_NOT_A_REAL_EVENT", "to": "STATE_IDLE"},
        ])
        with pytest.raises(ModelParseError) as exc_info:
            build_model(manifest_path=bad, header_path=STATE_MACHINE_H)
        assert "row 0" in str(exc_info.value)
        assert "EVENT_NOT_A_REAL_EVENT" in str(exc_info.value)

    def test_unknown_to_state_names_row(self, tmp_path):
        bad = self._write_manifest(tmp_path, [
            {"from": "STATE_INIT", "event": "EVENT_SELFTEST_PASS", "to": "STATE_NOWHERE"},
        ])
        with pytest.raises(ModelParseError) as exc_info:
            build_model(manifest_path=bad, header_path=STATE_MACHINE_H)
        assert "row 0" in str(exc_info.value)
        assert "STATE_NOWHERE" in str(exc_info.value)

    def test_duplicate_from_event_pair_fails(self, tmp_path):
        bad = self._write_manifest(tmp_path, [
            {"from": "STATE_INIT", "event": "EVENT_SELFTEST_PASS", "to": "STATE_IDLE"},
            {"from": "STATE_INIT", "event": "EVENT_SELFTEST_PASS", "to": "STATE_FAULT"},
        ])
        with pytest.raises(ModelParseError) as exc_info:
            build_model(manifest_path=bad, header_path=STATE_MACHINE_H)
        assert "duplicate" in str(exc_info.value)


class TestCoverage:
    """Scenario 4: the report enumerates every one of the 9x25 cells
    (23 declared events + 2 KTD2 wildcard events) as declared/implicit/
    TRANSITION_INVALID."""

    def test_full_cell_space_enumerated(self, model):
        cells = model.cell_coverage()
        assert len(cells) == len(model.states) * len(model.all_cell_events())

    def test_every_cell_has_a_verdict(self, model):
        cells = model.cell_coverage()
        allowed = {"declared", "implicit", "TRANSITION_INVALID"}
        assert set(cells.values()) <= allowed

    def test_declared_count_matches_manifest_row_count(self, model):
        manifest = yaml.safe_load(TRANSITION_YAML.read_text())
        row_count = len(manifest["transitions"])
        cells = model.cell_coverage()
        declared_count = sum(1 for v in cells.values() if v == "declared")
        assert declared_count == row_count

    def test_implicit_count_is_9_states_times_2_events(self, model):
        cells = model.cell_coverage()
        implicit_count = sum(1 for v in cells.values() if v == "implicit")
        assert implicit_count == len(model.states) * len(RUNAWAY_WILDCARD_EVENTS)


class TestModelBuiltFromRealManifest:
    def test_no_wildcard_edges_when_disabled(self):
        m = build_model(add_wildcard_interlock=False)
        assert m.implicit_edges() == []

    def test_reachability_report_is_serializable(self, model):
        report = model.reachability_report()
        d = report.to_dict()
        assert d["reachable_states"]
        assert INIT_STATE in d["reachable_states"]
