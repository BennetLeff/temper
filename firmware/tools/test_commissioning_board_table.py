"""Tests for firmware/tools/commissioning_board_table.py.

The committed COMMISSIONING.md must match the board table rendered from the board of record, and each class
of drift the gate exists for must fail: a stale table value (the stage-15 OCP band that sat in the procedure
until stage 53), a stage-NN board claim, a resistor value the BOM does not have, a Kconfig default that the
commissioning record misstates, and a new board of record with no re-base. The home-lab overview BRING-UP.md
gets the prose rules plus a check that every COMMISSIONING step and item it points to exists.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import commissioning_board_table as cbt  # noqa: E402


@pytest.fixture(scope="module")
def rendered():
    block, findings = cbt.render()
    return block, findings


@pytest.fixture(scope="module")
def ctx():
    stage = cbt.board_of_record()["stage"]
    bom, _ = cbt.load_board()
    fw = "\n".join(p.read_text(errors="replace") for p in cbt.FW_SOURCES if p.exists())
    return stage, bom, cbt.kconfig(), fw


def _check(text, rendered, ctx):
    stage, bom, kc, fw = ctx
    return cbt.check_text(text, rendered[0], stage, bom, kc, fw)


def test_committed_doc_matches(rendered, ctx):
    assert _check(cbt.DOC.read_text(), rendered, ctx) == []


def test_cli_check_passes_and_fails_on_stale_value(tmp_path, monkeypatch):
    assert cbt.main(["--check"]) == cbt.EXIT_OK
    stale = tmp_path / "COMMISSIONING.md"
    stale.write_text(cbt.DOC.read_text().replace("71.59–114.57 A before Kelvin", "66.30–118.74 A before Kelvin"))
    monkeypatch.setattr(cbt, "DOC", stale)
    assert cbt.main(["--check"]) == cbt.EXIT_VIOLATION


def test_render_reproduces_the_records(rendered):
    block = rendered[0]
    # CT band: DECISIONS 13 / 23 (64.55-76.09 A, nominal 70.18 A) from the round-3 engine on the frozen parts
    assert "**band 64.55–76.09 A (+), 64.55–76.09 A (−)**" in block and "nominal 70.18 A" in block
    # OCP: kelvin_budget BAND_BEFORE["native21s53"] and budget-native21s53.json (DECISIONS 75: 69.18-114.57 A)
    assert "71.59–114.57 A before Kelvin" in block and "low corner after Kelvin 69.18 A" in block
    assert "**69.13 A at the bound**" in block and "nominal trip 92.59 A, U6 VCM 1.0185 V" in block
    # OVP: bands-s52.json solved rows (DECISIONS 70: 287.47 / 287.62 V)
    assert "release 272.61–287.47 V; c28 272.47–287.62 V" in block
    # dead time: c25-driver/results/dt_window.json and audit.rs dead_time_window_matches_c25 (408.3-569.0 ns)
    assert "**408.3–569.0 ns**" in block and "340–600 ns" in block
    # VBUS over-range: controller_calcs.d11_receiver bus_V_at_1210mV
    assert "1210 mV = **230.9 V**" in block
    # bank ladder stop on the prototype bank (DECISIONS 74)
    assert "B32643H8104J000: tick **H**" in block and "**24 A**" in block
    assert "| 26 A | 59.42 A | 27.3 A | 39 A | 60.42 A | **never** |" in block
    # bring-up with BR1 out (owner 2026-10-18): BR1 is the only mains-bus part, PS2.4 has no series diode,
    # and the DC supply lands on C6's leads, the pair farthest from any other net (pads.json)
    assert "only BR1 (GBJ2510-F" in block and "is v24_raw with no series diode" in block
    assert "C6.1 (bus_p) and C6.3 (hv_ret)" in block


def test_reports_the_ceiling_range_finding(rendered):
    assert any("TEMPER_POWER_TANK_CEILING_DA range allows 28 A" in f for f in rendered[1])


def test_stale_table_value_fails(rendered, ctx):
    text = cbt.DOC.read_text().replace("**69.13 A at the bound**", "**66.30 A at the bound**")
    assert any("board table differs" in e for e in _check(text, rendered, ctx))


@pytest.mark.parametrize("line", [
    "- **Board revision.** The trip numbers below are for the **stage-15** board.",
    "1. **Tank-CT comparators** (U10–U13; stage 15: R43/R46 2.21 kΩ, band 64.55–76.09 A):",
    "- Stage-15 board confirmed before a raise.",
])
def test_other_stage_board_claim_fails(rendered, ctx, line):
    text = cbt.DOC.read_text().replace("## Ground rules\n", "## Ground rules\n\n" + line + "\n", 1)
    assert any("claims a stage-15 board" in e for e in _check(text, rendered, ctx))


@pytest.mark.parametrize("line,bad", [
    ("Shunt OCP (R5 1 mΩ; R34 12.6 kΩ / R35 11.7 kΩ).", True),
    ("Dead time (R9/R17 39 kΩ).", True),
    ("The divider is R33 7.5 k / R34 16 k / R35 11 k, R5 1 mΩ, R39 3 Ω, R146 220 k.", False),
    ("The controller R12 4.7 k is not checked against the power board.", False),
])
def test_resistor_values_against_bom(rendered, ctx, line, bad):
    text = cbt.DOC.read_text().replace("## Ground rules\n", "## Ground rules\n\n" + line + "\n", 1)
    errs = [e for e in _check(text, rendered, ctx) if "frozen BOM has" in e or "not on the" in e]
    assert bool(errs) is bad, errs


def test_kconfig_default_mismatch_fails(rendered, ctx):
    text = cbt.DOC.read_text().replace("| `TANK_CEILING_DA` | 175 (17.5 A) |", "| `TANK_CEILING_DA` | 180 (18 A) |")
    assert any("TANK_CEILING_DA provisional 180 != Kconfig default 175" in e for e in _check(text, rendered, ctx))


def test_unknown_symbols_fail(rendered, ctx):
    text = cbt.DOC.read_text() + "\nSet `TEMPER_POWER_NO_SUCH_FIELD` and `N21_FAULT_NO_SUCH`.\n"
    errs = _check(text, rendered, ctx)
    assert any("Kconfig has no TEMPER_POWER_NO_SUCH_FIELD" in e for e in errs)
    assert any("`N21_FAULT_NO_SUCH`" in e for e in errs)


def test_new_board_of_record_refuses(tmp_path, monkeypatch):
    note = tmp_path / "FAB-NOTE.md"
    note.write_text(cbt.FAB_NOTE.read_text().replace("Board: native-21 stage 53,", "Board: native-21 stage 54,"))
    monkeypatch.setattr(cbt, "FAB_NOTE", note)
    with pytest.raises(cbt.GateError, match="re-base"):
        cbt.render()
    assert cbt.main(["--check"]) == cbt.EXIT_GATE_ERROR


def test_j13_drift_symbol_fails(rendered, ctx):
    """The drift that broke this gate after the J13 merge: RAIL_OK_RB left on GPIO35 in the procedure."""
    text = cbt.DOC.read_text().replace("TCA9555 P02 (`CTRL_EXP_RAIL_OK_RB`)", "GPIO35 (`CTRL_GPIO_RAIL_OK_RB`)", 1)
    assert any("`CTRL_GPIO_RAIL_OK_RB`" in e for e in _check(text, rendered, ctx))


def _check_bringup(text, ctx):
    stage, bom, kc, fw = ctx
    return cbt.check_companion(text, cbt.DOC.read_text(), stage, bom, kc, fw)


def test_committed_bringup_passes(ctx):
    assert _check_bringup(cbt.BRINGUP.read_text(), ctx) == []


@pytest.mark.parametrize("line,expect", [
    ("Run the trips (COMMISSIONING step 11).", "has no step 11"),
    ("Bulb out before step 5 item 9.", "step 5 has no item 9"),
    ("Then steps 4c and 6.", "has no step 4c"),
    ("Heat with the stage-15 board.", "claims a stage-15 board"),
    ("The CT burden R39 3.3 Ω.", "frozen BOM has R39"),
    ("RAIL_OK reads high on GPIO35 (`CTRL_GPIO_RAIL_OK_RB`).", "`CTRL_GPIO_RAIL_OK_RB`"),
    ("Set `TEMPER_POWER_NO_SUCH_FIELD`.", "Kconfig has no TEMPER_POWER_NO_SUCH_FIELD"),
])
def test_bringup_drift_fails(ctx, line, expect):
    text = cbt.BRINGUP.read_text().replace("## Records to keep\n", "## Records to keep\n" + line + "\n", 1)
    errs = _check_bringup(text, ctx)
    assert any(expect in e for e in errs), errs


def test_bringup_must_name_board_of_record(ctx):
    text = cbt.BRINGUP.read_text().replace("**stage 53**", "**the current stage**", 1)
    assert any("does not name the board of record" in e for e in _check_bringup(text, ctx))


def test_cli_check_fails_on_stale_bringup(tmp_path, monkeypatch):
    stale = tmp_path / "BRING-UP.md"
    stale.write_text(cbt.BRINGUP.read_text() + "\nSee COMMISSIONING step 12.\n")
    monkeypatch.setattr(cbt, "BRINGUP", stale)
    assert cbt.main(["--check"]) == cbt.EXIT_VIOLATION
    monkeypatch.setattr(cbt, "BRINGUP", tmp_path / "missing.md")
    assert cbt.main(["--check"]) == cbt.EXIT_GATE_ERROR


@pytest.mark.parametrize("mpn,ohms", [
    ("RT0603BRD077K5L", 7.5e3), ("RT0603BRD0716KL", 16e3), ("RT0603BRD072K21L", 2.21e3), ("RT0603BRD0749K9L", 49.9e3),
    ("RC1206FR-07470KL", 470e3), ("RC1206FR-073RL", 3.0), ("0603WAF1003T5E", 100e3), ("1206W4F1001T5E", 1e3),
    ("25121WF680JT4E", 68.0), ("TNPW060311K7BEEA", 11.7e3), ("CSS2H-2512R-1L00F", 1e-3), ("TLV3201AIDBVR", None),
])
def test_mpn_ohms(mpn, ohms):
    got = cbt.mpn_ohms(mpn)
    assert (got is None and ohms is None) or got == pytest.approx(ohms)
