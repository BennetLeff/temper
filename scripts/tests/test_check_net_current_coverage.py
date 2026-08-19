"""Unit tests for scripts/check_net_current_coverage.py.

Each property gets a falsifier: a mutation that MUST make the gate red.
A coverage gate that cannot go red is worse than no gate, because it
launders the absence of a check into the appearance of one -- this repo
has ``scripts/check_vacuous_gates.py`` precisely because that has happened
before.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from check_net_current_coverage import (  # noqa: E402
    Report,
    check_ghost_keys,
    check_hv_current_coverage,
    load_waivers,
    resolve_current,
    run,
)

# A minimal stand-in for the real board's net table.
BOARD = {"+170V_BUS", "DC_BUS_RTN", "ac_l", "ac_n", "SW_NODE", "gpio18", "w1_1"}
GOOD_TABLE = {
    "+170V_BUS": 22.5,
    "DC_BUS_RTN": 22.5,
    "ac_l": 15.0,
    "ac_n": 15.0,
    "SW_NODE": 22.5,
    "w1_1": 15.0,
}
HV = ["+170V_BUS", "DC_BUS_RTN", "ac_l", "ac_n", "SW_NODE", "w1_1"]


# ---------------------------------------------------------------------------
# resolve_current mirrors the Rust resolver
# ---------------------------------------------------------------------------


def test_resolve_current_exact():
    assert resolve_current("+170V_BUS", GOOD_TABLE) == 22.5


def test_resolve_current_case_insensitive_exact():
    """``AC_L`` resolves the board's ``ac_l`` -- equality, not containment."""
    assert resolve_current("AC_L", GOOD_TABLE) == 15.0


def test_resolve_current_is_not_substring():
    """The defect's mechanism must not be reachable through this helper."""
    assert resolve_current("NET_SW_NODE_1", GOOD_TABLE) is None
    assert resolve_current("DC_BUS+", GOOD_TABLE) is None


# ---------------------------------------------------------------------------
# PROPERTY 1 falsifiers
# ---------------------------------------------------------------------------


def test_property1_clean_when_every_hv_net_is_covered():
    missing, waived = check_hv_current_coverage(HV, GOOD_TABLE, {})
    assert missing == []
    assert waived == []


def test_property1_flags_an_hv_net_with_no_entry():
    """FALSIFIER: drop the DC bus from the table."""
    mutated = {k: v for k, v in GOOD_TABLE.items() if k != "+170V_BUS"}
    missing, _ = check_hv_current_coverage(HV, mutated, {})
    assert missing == ["+170V_BUS"]


def test_property1_reproduces_the_original_defect():
    """FALSIFIER: the real pre-fix table, keyed on the ghost vocabulary.

    Every one of these keys looked plausible; none is a board net.
    """
    ghost_table = {"DC_BUS+": 16.0, "AC_L": 15.0, "AC_N": 15.0, "+5V": 0.5}
    missing, _ = check_hv_current_coverage(HV, ghost_table, {})
    # AC_L/AC_N resolve ac_l/ac_n case-insensitively; the rest do not.
    assert "+170V_BUS" in missing
    assert "DC_BUS_RTN" in missing
    assert "SW_NODE" in missing
    assert "w1_1" in missing


def test_property1_waiver_suppresses_but_records():
    mutated = {k: v for k, v in GOOD_TABLE.items() if k != "w1_1"}
    missing, waived = check_hv_current_coverage(HV, mutated, {"w1_1": "reason"})
    assert missing == []
    assert waived == ["w1_1"]


# ---------------------------------------------------------------------------
# PROPERTY 2 falsifiers
# ---------------------------------------------------------------------------


def test_property2_clean_when_no_ghost_keys():
    assert check_ghost_keys(GOOD_TABLE, BOARD) == []


def test_property2_flags_a_ghost_key():
    """FALSIFIER: reintroduce ``DC_BUS+``, the key that made the table look
    like it covered a DC bus it did not cover."""
    mutated = dict(GOOD_TABLE, **{"DC_BUS+": 16.0})
    assert check_ghost_keys(mutated, BOARD) == ["DC_BUS+"]


def test_property2_does_not_flag_a_case_variant():
    """``AC_L`` genuinely resolves the board's ``ac_l``; not a ghost."""
    mutated = dict(GOOD_TABLE, **{"AC_L": 15.0})
    assert "AC_L" not in check_ghost_keys(mutated, BOARD)


# ---------------------------------------------------------------------------
# Waiver loading fails closed
# ---------------------------------------------------------------------------


def test_waiver_without_a_reason_is_rejected(tmp_path):
    """A waiver with no stated reason is an unexplained hole."""
    p = tmp_path / "w.yaml"
    p.write_text("waivers:\n  some_net: ''\n", encoding="utf-8")
    with pytest.raises(Exception, match="no reason"):
        load_waivers(p)


def test_missing_waiver_file_is_empty_not_an_error(tmp_path):
    assert load_waivers(tmp_path / "absent.yaml") == {}


# ---------------------------------------------------------------------------
# End-to-end state
# ---------------------------------------------------------------------------


def test_run_reports_violation_for_the_original_defect(tmp_path):
    ghost_table = {"DC_BUS+": 16.0, "AC_L": 15.0, "+5V": 0.5}
    state, report = run(table=ghost_table, board_nets=BOARD, waivers_path=tmp_path / "none.yaml")
    assert state == "violation"
    assert report.hv_nets_without_current
    assert "DC_BUS+" in report.ghost_table_keys
    assert "+5V" in report.ghost_table_keys


def test_run_is_clean_against_the_live_repo():
    """The gate is green on the tree as committed -- otherwise every other
    test here is measuring a fiction."""
    state, report = run()
    assert state == "clean", (
        f"missing: {report.hv_nets_without_current}, ghosts: {report.ghost_table_keys}"
    )
    assert report.hv_nets_checked == 27
    assert not report.hv_nets_waived, "no waivers should be needed today"


def test_report_defaults_are_empty():
    r = Report()
    assert r.hv_nets_without_current == []
    assert r.ghost_table_keys == []
