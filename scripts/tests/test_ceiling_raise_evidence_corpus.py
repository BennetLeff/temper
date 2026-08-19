"""End-to-end test for the ceiling-raise-evidence fault-injection corpus
(STRATEGY.md build order step 4, 2026-08-07) -- the process/provenance
constraint family, sibling to the PCB-geometry and component-value
families. Exercises the REAL ``DrcRatchet.find_ceiling_raises``/
``validate_raise_evidence`` against synthetic ceiling dicts;
``power_pcb_dataset/drc_ceiling.json`` is never read or written.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_ceiling_raise_evidence_corpus as corpus  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_full_corpus_covers_every_declared_scenario():
    ok, verdicts = corpus.run_corpus(REPO_ROOT)
    assert ok, verdicts
    # Compared against the module's own declared population, not a literal
    # copy of it: a class silently dropped from run_corpus must fail here
    # rather than being re-asserted by a duplicated list that drifts with it.
    assert tuple(name for name, _ok, _msg in verdicts) == corpus.EXPECTED_CORPUS_CLASSES
    assert all(class_ok for _name, class_ok, _msg in verdicts)


def test_controls_are_silent_and_injections_are_named():
    _ok, verdicts = corpus.run_corpus(REPO_ROOT)
    by_name = {name: msg for name, _ok, msg in verdicts}
    assert "raises=[] problems=[]" in by_name["no-op-control"]
    assert "problems=[]" in by_name["fully-evidenced-raise-control"]
    assert "attributed cause" in by_name["no-march-entry"]
    assert "does not resolve to a commit" in by_name["dangling-commit"]
    assert "STALE measurement" in by_name["stale-input-hash"]


def test_seed_provenance_is_genuinely_clean_evidence():
    """The corpus seed itself must pass ``validate_raise_evidence``.

    This is the property that was BROKEN on main until 2026-08-18: the seed
    carried ``measured_at_commit = "0"*40``, so the fully-evidenced control
    could not pass and the specificity half of R9 was never exercised. Every
    injection class is a one-field mutation of this seed, so if the seed is
    not clean, no class below measures the field it claims to -- asserted
    here directly on the seed rather than only through the control's verdict.
    """
    from temper_placer.regression.drc_ratchet import DrcRatchet

    board_hash = corpus._sha256_file(REPO_ROOT / corpus.BOARD_REL_PATH)
    commit = corpus._resolve_measurement_commit(REPO_ROOT)
    seed = corpus._base_ceiling(board_hash, commit)
    raised = corpus._raised_copy(seed, 60)
    raised["_march"]["2026-08-18-attributed"] = "clearance 50 -> 60: attributed"

    ratchet = DrcRatchet(REPO_ROOT / "power_pcb_dataset" / "drc_ceiling.json")
    assert ratchet.validate_raise_evidence(seed, raised, REPO_ROOT) == []


def test_control_bites_on_the_exact_pre_fix_defect():
    """Anti-vacuity for the repair itself: reinstate the pre-fix seed and
    the control must go red again.

    ``"0"*40`` is the literal value main carried. If a future change made
    ``validate_raise_evidence`` stop resolving ``measured_at_commit``, the
    control would silently start passing on a fabricated commit and this
    corpus would be back to proving nothing -- this test fails in that case.
    """
    from temper_placer.regression.drc_ratchet import DrcRatchet

    board_hash = corpus._sha256_file(REPO_ROOT / corpus.BOARD_REL_PATH)
    seed = corpus._base_ceiling(board_hash, "0" * 40)
    raised = corpus._raised_copy(seed, 60)
    raised["_march"]["2026-08-18-attributed"] = "clearance 50 -> 60: attributed"

    ratchet = DrcRatchet(REPO_ROOT / "power_pcb_dataset" / "drc_ceiling.json")
    problems = ratchet.validate_raise_evidence(seed, raised, REPO_ROOT)
    assert any("does not resolve to a commit" in p for p in problems), problems


def test_resolved_measurement_commit_is_a_real_commit():
    """``_resolve_measurement_commit`` must return a SHA the same verifier
    the ratchet uses agrees is a real commit -- not merely 40 hex chars."""
    from temper_placer.regression.drc_ratchet import _verify_commits_exist

    sha = corpus._resolve_measurement_commit(REPO_ROOT)
    assert _verify_commits_exist({sha}, REPO_ROOT) == {sha: True}


def test_resolve_measurement_commit_fails_closed_outside_a_repo(tmp_path):
    """No git repository -> GateError (exit 2), never a fabricated SHA."""
    import pytest

    with pytest.raises(corpus.GateError):
        corpus._resolve_measurement_commit(tmp_path)


def test_population_pin_rejects_a_shortened_corpus(monkeypatch):
    """A corpus that stops producing classes must raise, not report PASS.

    ``all()`` over an empty verdict list is vacuously True; this asserts the
    population check in ``run_corpus`` catches that before the aggregation.
    """
    import pytest

    monkeypatch.setattr(
        corpus, "EXPECTED_CORPUS_CLASSES", corpus.EXPECTED_CORPUS_CLASSES + ("class-that-never-runs",)
    )
    with pytest.raises(corpus.GateError, match="corpus population changed"):
        corpus.run_corpus(REPO_ROOT)
