"""Tests for scripts/phase5_batch1_mutations.py's ``campaign_passed``.

Closes scripts/check_vacuous_gates.py's finding at
phase5_batch1_mutations.py:180 (``return 0 if all(s == "KILLED" for _, s, _
in results) else 1``): ``all()`` over an empty ``results`` is vacuously True,
which would report a clean campaign even if zero mutations ran. Two things
are pinned here:

1. An empty ``results`` is a hard failure (``AssertionError``), not a silent
   pass -- ``MUTATIONS`` is a non-empty literal today, but nothing prevented
   a future edit (or a refactor of the driving loop) from making ``results``
   empty and having that read as success.
2. The real bug caught while fixing the vacuous ``all()``: the original
   comparison was a bare ``status == "KILLED"``, which ignored ``EXPECTED``
   entirely -- so a fully-successful campaign where M6 SURVIVED exactly as
   designed (it is a documented EQUIVALENT mutant) would have reported
   failure. ``campaign_passed`` compares against ``expected`` instead.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from phase5_batch1_mutations import campaign_passed  # noqa: E402


def test_empty_results_is_a_hard_failure_not_a_vacuous_pass():
    """The real repo defect: `all()` over `results=[]` is vacuously True."""
    with pytest.raises(AssertionError, match="no mutations were run"):
        campaign_passed([], {})


def test_all_killed_matching_expected_passes():
    expected = {"M1": "KILLED", "M2": "KILLED"}
    results = [("M1", "KILLED", ""), ("M2", "KILLED", "")]
    assert campaign_passed(results, expected) is True


def test_equivalent_mutant_surviving_as_expected_still_passes():
    """The bug this fix caught: EXPECTED-aware, not bare `== "KILLED"`.

    M6 (or any mutation marked EQUIVALENT in EXPECTED) is *designed* to
    survive. A campaign where it does exactly that -- and everything else is
    killed -- is a fully successful run and must report success.
    """
    expected = {"M1": "KILLED", "M6": "EQUIVALENT"}
    results = [("M1", "KILLED", ""), ("M6", "SURVIVED", "")]
    assert campaign_passed(results, expected) is True


def test_unexpected_survivor_fails():
    expected = {"M1": "KILLED", "M2": "KILLED"}
    results = [("M1", "KILLED", ""), ("M2", "SURVIVED", "")]
    assert campaign_passed(results, expected) is False


def test_error_status_fails_even_if_expected_would_be_killed():
    expected = {"M1": "KILLED"}
    results = [("M1", "ERROR", "rebuild failed: ...")]
    assert campaign_passed(results, expected) is False


def test_real_expected_table_shape():
    """Sanity check against the actual MUTATIONS/EXPECTED tables in the
    module: M6 is EQUIVALENT, everything else expects KILLED."""
    from phase5_batch1_mutations import EXPECTED, MUTATIONS

    assert EXPECTED["M6 distance: x*x instead of pow(x, 2.0)"] == "EQUIVALENT"
    non_m6_labels = [
        label for label, *_ in MUTATIONS if not label.startswith("M6 ")
    ]
    assert non_m6_labels, "expected other mutations besides M6 to exist"
    assert all(EXPECTED[label] == "KILLED" for label in non_m6_labels)

    # A fully-successful real-shaped campaign passes: every KILLED-expected
    # mutation actually KILLED, the EQUIVALENT one (M6) actually SURVIVED.
    verdict_to_status = {"KILLED": "KILLED", "EQUIVALENT": "SURVIVED"}
    results = [
        (label, verdict_to_status[EXPECTED[label]], "") for label, *_ in MUTATIONS
    ]
    assert campaign_passed(results, EXPECTED) is True
