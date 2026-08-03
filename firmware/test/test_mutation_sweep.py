"""
Host pytest for the transition-table mutation driver (R40, P1).

Covers firmware/test/mutate_transition_table.py:

  - manifest expansion (wildcard rows -> per-active-state instances),
  - the canonical mutation operator set (KTD2) and same-value exclusion,
  - classification: killed / live / equivalent / error (U1 test scenarios),
  - the known-kill mutation from the plan (U1 scenario 1: (STATE_PREHEAT,
    NEAR_TARGET) with target changed to STATE_FAULT must be killed),
  - byte-stability of the committed generated file after a driver run
    (U1 scenario 4),
  - sweep report shape and row coverage (U2 scenarios 1-4),
  - the live-mutant triage reason classifier (U3).

Pure-logic tests run without a C build; the integration tests build the scratch
binary once (module-scoped) under a temporary directory.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent

sys.path.insert(0, str(SCRIPT_DIR))

import mutate_transition_table as mtt  # noqa: E402

COMMITTED_GENERATED = SCRIPT_DIR / "test_transition_table_generated.c"


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def gen():
    return mtt.load_generator()


@pytest.fixture(scope="module")
def expanded(gen):
    return mtt.expand_transitions(list(gen.TRANSITIONS), gen.ACTIVE_STATES)


@pytest.fixture(scope="module")
def scratch_build(tmp_path_factory):
    """One scratch build tree shared by the integration tests."""
    scratch = tmp_path_factory.mktemp("mutation_scratch")
    g = mtt.load_generator()
    expanded_rows = mtt.expand_transitions(list(g.TRANSITIONS), g.ACTIVE_STATES)
    mtt.emit_mutated_c(g, expanded_rows, scratch)
    assert mtt.ensure_configured(scratch), "scratch cmake configure failed"
    ok, err = mtt.build_mutant(scratch)
    assert ok, f"scratch baseline build failed:\n{err}"
    ret, tail = mtt.run_mutant_binary(scratch)
    assert ret == 0, f"scratch baseline run failed:\n{tail}"
    return scratch


# ---------------------------------------------------------------------------
# U1/U2: manifest expansion and operator set
# ---------------------------------------------------------------------------

class TestExpansion:
    def test_wildcard_rows_expand_per_active_state(self, gen):
        """Each '*' row expands to one row per ACTIVE_STATES entry."""
        expanded = mtt.expand_transitions(list(gen.TRANSITIONS), gen.ACTIVE_STATES)
        wildcards = [t for t in gen.TRANSITIONS if t[0] == "*"]
        assert wildcards, "expected at least one wildcard row"
        plain_count = len(gen.TRANSITIONS) - len(wildcards)
        assert len(expanded) == plain_count + len(wildcards) * len(gen.ACTIVE_STATES)

    def test_expanded_count_matches_emitted_c_table(self, gen):
        """Expanded row count equals the number of emitted C table rows."""
        expanded = mtt.expand_transitions(list(gen.TRANSITIONS), gen.ACTIVE_STATES)
        c_text = COMMITTED_GENERATED.read_text()
        body = c_text.split("transition_table[] = {", 1)[1].split(
            "static const size_t transition_count", 1
        )[0]
        emitted = [line for line in body.splitlines()
                   if line.strip().startswith("{ STATE_")]
        assert len(expanded) == len(emitted)
        assert len(expanded) == 42  # current manifest: 32 concrete + 2*5 wildcard

    def test_every_row_mutates_to_valid_alternate(self, expanded, gen):
        """Wrong-target alternate is always a real state different from target."""
        states, _ = gen.parse_state_machine_header(
            SCRIPT_DIR.parent / "main" / "state_machine.h"
        )
        for row in expanded:
            _, _, to_s, _, _ = row
            alt = mtt.WRONG_TARGET_FAULT if to_s != mtt.WRONG_TARGET_FAULT else mtt.WRONG_TARGET_INIT
            assert alt in states
            assert alt != to_s


class TestOperatorSet:
    def test_canonical_set_per_row(self, expanded):
        """Fault rows get wrong_target+guard_swap+guard_drop; benign rows get
        wrong_target+guard_add (KTD2). Same-value mutations are excluded."""
        for row in expanded:
            ops = [op for op, mutated in mtt.canonical_mutations_for_row(row)
                   if mutated != row]
            if row[3] is None:
                assert set(ops) == {"wrong_target", "guard_add"}, row
            else:
                assert set(ops) == {"wrong_target", "guard_swap", "guard_drop"}, row

    def test_same_value_mutations_detected(self, expanded):
        """guard_drop/guard_swap on a benign row are same-value (equivalent)."""
        benign = next(row for row in expanded if row[3] is None)
        _, drop_row = next(
            (op, r) for op, r in mtt.canonical_mutations_for_row(benign)
            if op == "guard_drop"
        )
        assert drop_row == benign

    def test_wrong_target_canonical_alternate(self):
        """(STATE_PREHEAT, NEAR_TARGET) wrong target is STATE_FAULT -- the
        known-kill mutation named in the plan (U1 scenario 1)."""
        row = ("STATE_PREHEAT", "NEAR_TARGET", "STATE_HEATING", None, False)
        mutated = mtt.OPERATOR_BY_NAME["wrong_target"](row)
        assert mutated == ("STATE_PREHEAT", "NEAR_TARGET", "STATE_FAULT", None, False)

    def test_apply_mutation_only_touches_target_row(self, expanded):
        mutated_list = mtt.apply_mutation_at(expanded, 5, "wrong_target")
        assert len(mutated_list) == len(expanded)
        assert mutated_list[5][2] != expanded[5][2]
        for i, (a, b) in enumerate(zip(mutated_list, expanded, strict=True)):
            if i != 5:
                assert a == b


# ---------------------------------------------------------------------------
# U3: triage reason classifier
# ---------------------------------------------------------------------------

class TestLiveReasonClassifier:
    def test_reason_classes_are_single_label(self):
        benign = ("STATE_PREHEAT", "NEAR_TARGET", "STATE_HEATING", None, False)
        fault = ("STATE_PREHEAT", "OVER_TEMP", "STATE_FAULT", "FAULT_OVER_TEMP", False)
        reasons = {
            mtt.classify_live_reason(benign, "wrong_target", ""),
            mtt.classify_live_reason(fault, "guard_swap", ""),
            mtt.classify_live_reason(benign, "guard_add", ""),
            mtt.classify_live_reason(fault, "wrong_target", ""),
        }
        assert reasons <= {
            mtt.REASON_STUB_NEVER_FIRES, mtt.REASON_PRECONDITION_MASK,
            mtt.REASON_DRAIN_MASK, mtt.REASON_TIMING, mtt.REASON_ASSERTION_GAP,
            mtt.REASON_UNCLASSIFIED,
        }
        assert all(isinstance(r, str) and r for r in reasons)


# ---------------------------------------------------------------------------
# U1: classification (integration -- real scratch build)
# ---------------------------------------------------------------------------

class TestClassification:
    def test_known_kill_mutation_is_killed(self, gen, expanded, scratch_build):
        """U1 scenario 1: (STATE_PREHEAT, NEAR_TARGET) wrong_target ->
        STATE_FAULT must be classified killed."""
        report = mtt.run_sweep(
            gen=gen, scratch_dir=scratch_build,
            report_path=scratch_build / "report.json", build=True, rows=[5],
        )
        assert report["baseline_pass"] is True
        assert report["live"] == 0
        assert report["errors"] == 0
        row5 = report["rows"][0]
        assert row5["row_index"] == 5
        assert row5["event"] == "NEAR_TARGET"
        ops = {m["op"]: m["outcome"] for m in row5["mutations"]}
        assert ops["wrong_target"] == mtt.OUTCOME_KILLED
        assert ops["guard_add"] == mtt.OUTCOME_KILLED

    def test_committed_generated_file_byte_stable(self, gen, expanded, scratch_build):
        """U1 scenario 4: the driver leaves the committed generated file
        byte-identical after a run."""
        before = COMMITTED_GENERATED.read_bytes()
        mtt.run_sweep(
            gen=gen, scratch_dir=scratch_build,
            report_path=scratch_build / "report.json", build=True, rows=[0, 1, 41],
        )
        after = COMMITTED_GENERATED.read_bytes()
        assert before == after

    def test_error_path_is_error_not_live(self, gen, expanded, scratch_build, monkeypatch):
        """U1 scenario 3: a build failure classifies error, not live."""
        def _boom(scratch_dir):
            return False, "injected build failure"

        monkeypatch.setattr(mtt, "build_mutant", _boom)
        result = mtt.classify_mutation(
            gen, expanded, 5, "wrong_target",
            mtt.OPERATOR_BY_NAME["wrong_target"](expanded[5]),
            scratch_build, build=True,
        )
        assert result["outcome"] == mtt.OUTCOME_ERROR
        assert "injected build failure" in result["evidence"]


# ---------------------------------------------------------------------------
# U2: sweep report shape / coverage (no C build needed)
# ---------------------------------------------------------------------------

class TestSweepReport:
    def test_report_shape_and_coverage(self, gen, expanded, tmp_path):
        """U2 scenario 4: report covers every row (rows_covered == rows_total)
        when the full sweep is requested."""
        report = mtt.run_sweep(
            gen=gen, scratch_dir=tmp_path / "scratch",
            report_path=tmp_path / "report.json", build=False, rows=[],
        )
        assert report["schema_version"] == 1
        assert report["rows_total"] == len(expanded)
        assert report["rows_swept"] == 0
        assert "mutation_score" in report
        assert "generated_at" in report

        full = mtt.run_sweep(
            gen=gen, scratch_dir=tmp_path / "scratch2",
            report_path=tmp_path / "report2.json", build=False, rows=range(len(expanded)),
        )
        # build=False classifies everything as error (cannot build); the
        # structure (row coverage bookkeeping) is what we assert here.
        assert full["rows_covered"] == full["rows_total"]
        assert full["rows_swept"] == full["rows_total"]

    def test_report_json_roundtrip(self, gen, expanded, tmp_path):
        report = mtt.run_sweep(
            gen=gen, scratch_dir=tmp_path / "scratch",
            report_path=tmp_path / "report.json", build=False, rows=[],
        )
        loaded = mtt.read_report(tmp_path / "report.json")
        assert loaded == report


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
