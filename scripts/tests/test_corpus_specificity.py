"""Unit tests for the corpus specificity run's pure decision logic
(STRATEGY.md build order step 5) -- no kicad-cli required.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_corpus_specificity import BoardResult, specificity_ok  # noqa: E402


def _clean(board_id: str) -> BoardResult:
    return BoardResult(board_id=board_id, pcb_path=f"{board_id}.kicad_pcb")


def _finding(board_id: str) -> BoardResult:
    return BoardResult(board_id=board_id, pcb_path=f"{board_id}.kicad_pcb", containment_refs_outside=["R1"])


def _unchecked(board_id: str) -> BoardResult:
    return BoardResult(board_id=board_id, pcb_path=f"{board_id}.kicad_pcb", containment_error="open outline")


def test_empty_results_is_not_a_pass():
    assert specificity_ok([]) is False


def test_all_clean_is_a_pass():
    assert specificity_ok([_clean("a"), _clean("b")]) is True


def test_one_finding_fails():
    assert specificity_ok([_clean("a"), _finding("b")]) is False


def test_one_unchecked_board_fails_even_if_others_clean():
    # An unchecked board must never be silently folded into "clean" --
    # this is the exact bug this test guards against (found and fixed
    # while building this script: the first version caught GateError and
    # treated it as zero findings).
    assert specificity_ok([_clean("a"), _unchecked("b")]) is False


def test_finding_and_unchecked_together_still_fails():
    assert specificity_ok([_finding("a"), _unchecked("b")]) is False
