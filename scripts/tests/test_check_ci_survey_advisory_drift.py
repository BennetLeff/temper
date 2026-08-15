"""Tests for check_ci_survey_advisory_drift.py.

Regression fixture: this gate's motivating case is real, not hypothetical.
``TestRegressionFixture`` replays the exact pre-2026-08-13-fix state of
``gate_input_registry.py``'s ``check_netclass_class_param_correspondence.py``
entry (which read "advisory (continue-on-error); currently VIOLATION on
origin/main") against the real, current ``python-tests.yml`` (which has run
that gate BLOCKING, with no ``continue-on-error``, since 2026-08-12) and
proves the gate flags exactly that drift. ``TestSyntheticCases`` proves the
detector against constructed survey/workflow pairs for the shapes a real
repo state cannot cheaply exercise (the dangerous "claims BLOCKING but is
actually advisory" direction, and "claim with zero matching invocation").
``TestRealRepoIntegration`` pins the CURRENT clean state.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_ci_survey_advisory_drift import (  # noqa: E402
    find_drift,
    invocation_advisory_states,
    load_ci_script_survey,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_REGISTRY_SRC = (
    REPO_ROOT
    / "packages"
    / "temper-placer"
    / "src"
    / "temper_placer"
    / "validation"
    / "gate_input_registry.py"
)
REAL_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "python-tests.yml"


def _blocking_step(script: str) -> str:
    return textwrap.dedent(
        f"""\
        - name: Some gate (Gate N)
          if: ${{{{ !cancelled() }}}}
          run: uv run python scripts/{script}
        """
    )


def _advisory_step(script: str) -> str:
    return textwrap.dedent(
        f"""\
        - name: Some gate (Gate N)
          if: ${{{{ !cancelled() }}}}
          continue-on-error: true
          run: uv run python scripts/{script}
        """
    )


class TestSyntheticCases:
    """Constructed survey/workflow pairs proving each drift direction."""

    def test_advisory_claim_matching_advisory_wiring_is_clean(self):
        survey = [("foo.py", "", "some gate; advisory (continue-on-error); x")]
        workflow = _advisory_step("foo.py")
        assert find_drift(survey, workflow) == []

    def test_blocking_claim_matching_blocking_wiring_is_clean(self):
        survey = [("foo.py", "", "some gate; BLOCKING as of today; x")]
        workflow = _blocking_step("foo.py")
        assert find_drift(survey, workflow) == []

    def test_advisory_claim_against_blocking_wiring_flags_stale_reason(self):
        """The exact shape found in this repo 2026-08-13: reason says
        advisory, but every real invocation runs without continue-on-error
        (a fix landed and the prose was never updated)."""
        survey = [("foo.py", "", "some gate; advisory (continue-on-error); x")]
        workflow = _blocking_step("foo.py")
        drifts = find_drift(survey, workflow)
        assert len(drifts) == 1
        assert drifts[0].script == "foo.py"
        assert drifts[0].claim == "advisory"
        assert "stale" in drifts[0].detail

    def test_blocking_claim_against_advisory_wiring_flags_dangerous_case(self):
        """The mirror, and the more dangerous direction: reason says
        BLOCKING but the step still carries continue-on-error, so a
        regression on this gate cannot fail CI even though the registry
        promises it can."""
        survey = [("foo.py", "", "some gate; BLOCKING as of today; x")]
        workflow = _advisory_step("foo.py")
        drifts = find_drift(survey, workflow)
        assert len(drifts) == 1
        assert drifts[0].claim == "blocking"
        assert "cannot fail CI" in drifts[0].detail

    def test_claim_with_no_active_invocation_is_flagged(self):
        """A commented-out step (like check_creepage_clearance_drift.py's
        'PREPARED, NOT ENABLED' block) is not an active invocation. If a
        survey entry still makes an advisory/blocking claim about a script
        with zero active invocations, that is itself worth flagging."""
        survey = [("foo.py", "", "some gate; advisory (continue-on-error); x")]
        workflow = "# - name: disabled\n#   run: uv run python scripts/foo.py\n"
        drifts = find_drift(survey, workflow)
        assert len(drifts) == 1
        assert "no active" in drifts[0].detail

    def test_entry_without_advisory_or_blocking_keyword_is_never_checked(self):
        survey = [("foo.py", "", "some gate; probe harness deferred")]
        workflow = "irrelevant text with no scripts/foo.py mention"
        assert find_drift(survey, workflow) == []

    def test_multiple_invocations_all_advisory_is_clean(self):
        survey = [("foo.py", "", "some gate; advisory (continue-on-error); x")]
        workflow = _advisory_step("foo.py") + "\n" + _advisory_step("foo.py")
        assert find_drift(survey, workflow) == []

    def test_one_of_two_invocations_missing_continue_on_error_still_advisory_clean(self):
        """An 'advisory' claim only requires AT LEAST ONE real invocation
        to be behind continue-on-error -- it does not require every
        invocation to be (a script can be advisory in one config and
        blocking in another without contradicting a general 'advisory'
        claim)."""
        survey = [("foo.py", "", "some gate; advisory (continue-on-error); x")]
        workflow = _advisory_step("foo.py") + "\n" + _blocking_step("foo.py")
        assert find_drift(survey, workflow) == []

    def test_commented_mention_does_not_count_as_invocation(self):
        survey = [("foo.py", "", "some gate; advisory (continue-on-error); x")]
        workflow = "      # run: uv run python scripts/foo.py\n"
        drifts = find_drift(survey, workflow)
        assert len(drifts) == 1
        assert "no active" in drifts[0].detail


class TestInvocationAdvisoryStates:
    def test_continue_on_error_precedes_run_within_step(self):
        text = _advisory_step("foo.py")
        assert invocation_advisory_states(text, "foo.py") == [True]

    def test_no_continue_on_error_in_step(self):
        text = _blocking_step("foo.py")
        assert invocation_advisory_states(text, "foo.py") == [False]

    def test_continue_on_error_from_a_different_prior_step_does_not_leak(self):
        """A `continue-on-error: true` belonging to an EARLIER, unrelated
        step must not be attributed to this step -- the step boundary is
        the nearest preceding `- name:` line."""
        text = _advisory_step("bar.py") + "\n" + _blocking_step("foo.py")
        assert invocation_advisory_states(text, "foo.py") == [False]


class TestRegressionFixture:
    """Replay the exact pre-fix state that motivated this gate."""

    def test_stale_advisory_reason_against_real_current_workflow_is_flagged(self):
        stale_survey = [
            (
                "check_netclass_class_param_correspondence.py",
                "pcb/temper.kicad_pro",
                "netclass scalar-parameter correspondence gate; advisory "
                "(continue-on-error); currently VIOLATION on origin/main "
                "(HighVoltage.clearance mismatch); probe harness deferred",
            )
        ]
        workflow_text = REAL_WORKFLOW.read_text()
        drifts = find_drift(stale_survey, workflow_text)
        assert len(drifts) == 1
        assert drifts[0].script == "check_netclass_class_param_correspondence.py"
        assert drifts[0].claim == "advisory"


class TestLoadCiScriptSurvey:
    def test_parses_real_registry_without_import(self):
        survey = load_ci_script_survey()
        assert isinstance(survey, list)
        assert len(survey) > 50
        scripts = {s for s, _d, _r in survey}
        assert "check_netclass_class_param_correspondence.py" in scripts

    def test_every_entry_is_a_3_tuple_of_strings(self):
        for entry in load_ci_script_survey():
            assert len(entry) == 3
            assert all(isinstance(x, str) for x in entry)


class TestRealRepoIntegration:
    def test_current_registry_matches_current_workflow(self):
        """The gate's own verdict against the real repo, post-fix: clean.
        A future PR that softens a BLOCKING gate to continue-on-error (or
        vice versa) without updating the reason text must fail this test."""
        survey = load_ci_script_survey()
        workflow_text = REAL_WORKFLOW.read_text()
        drifts = find_drift(survey, workflow_text)
        assert drifts == [], f"unexpected CI-survey advisory/blocking drift: {drifts}"
