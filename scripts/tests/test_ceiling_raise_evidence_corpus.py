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


def test_full_corpus_covers_all_four_scenarios():
    ok, verdicts = corpus.run_corpus(REPO_ROOT)
    assert ok, verdicts
    names = {name for name, _ok, _msg in verdicts}
    assert names == {
        "no-op-control",
        "fully-evidenced-raise-control",
        "no-march-entry",
        "dangling-commit",
    }
    assert all(class_ok for _name, class_ok, _msg in verdicts)


def test_controls_are_silent_and_injections_are_named():
    _ok, verdicts = corpus.run_corpus(REPO_ROOT)
    by_name = {name: msg for name, _ok, msg in verdicts}
    assert "raises=[] problems=[]" in by_name["no-op-control"]
    assert "problems=[]" in by_name["fully-evidenced-raise-control"]
    assert "attributed cause" in by_name["no-march-entry"]
    assert "STALE measurement" in by_name["dangling-commit"]
