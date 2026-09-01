"""Every reader of kicad-cli's DRC JSON must read the SAME set of top-level
violation arrays.

Background: ``temper_placer.validation._drc_api._parse_drc_json`` read
``violations`` and nothing else for the life of the project, silently
dropping the ``unconnected_items`` array -- 339 entries on the committed
board, all severity ``error``, 47% of the board's true error count. Every
DRC number this project ever recorded was blind to connectivity failure.

The defect is not "one function forgot one key"; it is that FIVE independent
readers of the same JSON each hardcode their own idea of which sections
exist, and nothing compared them. Three agreed (``deterministic/feedback/
drc_parser.py``, ``placer/cp_sat/gates.py``, ``temper-drc-rs``'s
``DrcReport``); two did not (``_drc_api``, and these two scripts). This test
is the comparison that was missing.

``scripts/measure_uncapped_drc.py`` was the sharpest case: its own cap table
names ``unconnected_items`` as one of the two EXTENDED_ERROR_LIMIT (499)
categories, while its counting functions never looked in that array -- so
asking it for the true uncapped count of ``unconnected_items`` returned 0,
contradicting the module's own constants.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "packages" / "temper-placer" / "src"))

import compare_drc_reports  # noqa: E402
import measure_uncapped_drc  # noqa: E402

from temper_placer.validation._drc_api import _VIOLATION_ARRAY_KEYS  # noqa: E402


def test_the_canonical_key_list_is_not_empty_or_trivially_satisfied():
    """Anti-vacuity: the assertions below would pass trivially if the
    canonical list were empty or had lost the key this whole exercise is
    about."""
    assert len(_VIOLATION_ARRAY_KEYS) >= 2
    assert "violations" in _VIOLATION_ARRAY_KEYS
    assert "unconnected_items" in _VIOLATION_ARRAY_KEYS


def test_measure_uncapped_drc_reads_the_same_arrays_as_the_parser():
    assert measure_uncapped_drc._VIOLATION_ARRAY_KEYS == _VIOLATION_ARRAY_KEYS


def test_compare_drc_reports_reads_the_same_arrays_as_the_parser():
    assert compare_drc_reports._VIOLATION_ARRAY_KEYS == _VIOLATION_ARRAY_KEYS


def test_measure_uncapped_drc_counts_unconnected_items_it_claims_to_cap():
    """The Rust cap authority and Python counter must both recognize the
    production category. Before the fix the counter returned {} here."""
    report = {
        "violations": [{"type": "clearance"}],
        "unconnected_items": [{"type": "unconnected_items"}, {"type": "unconnected_items"}],
    }
    assert measure_uncapped_drc.category_counts(report) == {
        "clearance": 1,
        "unconnected_items": 2,
    }
    assert measure_uncapped_drc.cap_for("unconnected_items") == 499


def test_compare_drc_reports_sees_a_connectivity_regression(tmp_path):
    """A board that loses 3 connections between two runs must not compare
    clean. Before the fix, this exact input produced an empty delta set."""
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    before.write_text('{"violations": [], "unconnected_items": []}')
    after.write_text(
        '{"violations": [], "unconnected_items": ['
        '{"type": "unconnected_items"},'
        '{"type": "unconnected_items"},'
        '{"type": "unconnected_items"}]}'
    )

    deltas = compare_drc_reports.compare_drc_reports(before, after)
    assert "unconnected_items" in deltas
    assert deltas["unconnected_items"].delta == 3
    assert not deltas["unconnected_items"].improvement
