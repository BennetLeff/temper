#!/usr/bin/env python3
"""Mutation tests for tools/verify_ui.py: each deliberate defect must fail the check that owns it.

A mutation edits a copy of the frozen netlist (or the resolved export, the BOM or the firmware
map), runs the full verification on it and requires that
  1. the unmutated design passes every check, and
  2. every named check in `expect` FAILS on the mutated copy.
Nothing in the repository is modified: mutants live in a temporary directory.

Usage: python3 tools/mutate_ui.py [--json OUT]     (exit 1 if any mutation is not caught)
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_ui as vu  # noqa: E402

UNIT = vu.UNIT
FROZEN = UNIT / "frozen"


# --------------------------------------------------------------------- netlist editing
def node(ref: str, pin: str) -> str:
    return rf'\(node \(ref "{ref}"\) \(pin "{pin}"\) \(pintype "stereo"\)\)'


def _head(net: str) -> re.Pattern:
    return re.compile(r'(\(net \(code "\d+"\) \(name "' + re.escape(net) + r'"\))')


def drop(text: str, ref: str, pin: str) -> str:
    new, n = re.subn(r"\n\s*" + node(ref, pin) + r"\)*", "", text, count=1)
    assert n == 1, (ref, pin)
    return new


def add(text: str, ref: str, pin: str, net: str) -> str:
    h = _head(net)
    assert h.search(text), net
    return h.sub(lambda m: m.group(1) + f'\n      (node (ref "{ref}") (pin "{pin}") (pintype "stereo"))', text, count=1)


def move(text: str, ref: str, pin: str, net: str) -> str:
    return add(drop(text, ref, pin), ref, pin, net)


@dataclass
class Mutant:
    name: str
    what: str
    expect: list[str]                              # checks that must fail ("section.check")
    net: Callable[[str], str] | None = None
    resolved: Callable[[dict], dict] | None = None
    bom: Callable[[dict], dict] | None = None
    firmware: Callable[[str], str] | None = None
    notes: list = field(default_factory=list)


def ref_of(nl_text: str, path: str) -> str:
    m = re.search(r'\(comp \(ref "([^"]+)"\).*?\(sheetpath \(names "[^"]*::' + re.escape(path) + r'"\)', nl_text, re.S)
    assert m, path
    return m.group(1)


def swap_nets(text: str, a: tuple[str, str], b: tuple[str, str], net_a: str, net_b: str) -> str:
    text = drop(drop(text, *a), *b)
    return add(add(text, a[0], a[1], net_b), b[0], b[1], net_a)


MUTANTS = [
    # ---- carried over from the first revision (J7, GP map, pull-ups, buzzer default, decoupling, BOM, ESD, OLED)
    Mutant("swap_j7_sck_mosi", "swap J7 pins 4 and 6 (SCK <-> MOSI)",
           ["j7.j7_pin_map_equals_controller_c26_table", "j7.j7_pin_map_equals_controller_enclosure_handoff",
            "j7.j7_pin_map_equals_controller_frozen_netlist", "j7.j7_pin_map_equals_controller_verify_J7_MAP"],
           net=lambda t: swap_nets(t, ("J7", "4"), ("J7", "6"), "J7_SCK", "J7_MOSI")),
    Mutant("swap_j7_miso_cs_exp", "swap J7 pins 7 and 12 (MISO <-> CS_EXP#)",
           ["j7.j7_pin_map_equals_controller_c26_table"],
           net=lambda t: swap_nets(t, ("J7", "7"), ("J7", "12"), "J7_MISO", "J7_CS_EXP_N")),
    Mutant("drop_stop_button_pullup", "remove the STOP button pull-up (R5)",
           ["inputs.gp1_has_external_pullup_le_47k"],
           net=lambda t: drop(t, "R5", "1")),
    Mutant("drop_tmp_cs_pullup", "remove the TMP122 select pull-up (R17): GP7 floats at reset",
           ["inputs.gp7_has_external_pullup_le_47k", "cs.tmp_cs_deselected_at_reset"],
           net=lambda t: drop(t, "R17", "1")),
    Mutant("invert_buzzer_default", "buzzer gate resistor pulls up instead of down (on at reset)",
           ["buzzer.default_off_at_reset"],
           net=lambda t: move(t, "R22", "2", "V3V3")),
    Mutant("buzzer_on_5v", "buzzer supplied from V5_UI: its current against a 30 mA budget",
           ["power.v5_budget_le_30mA", "buzzer.buzzer_between_3v3_and_q1_drain"],
           net=lambda t: move(t, "BZ1", "1", "V5_UI")),
    Mutant("remove_expander_decoupling", "remove U1's 100 nF (C3)",
           ["decoup.u_exp_has_100nF_between_supply_and_ground"],
           net=lambda t: drop(drop(t, "C3", "1"), "C3", "2")),
    Mutant("swap_gp_map", "swap GP1 and GP2 on the expander (STOP <-> BACK)",
           ["gpmap.fw_btn_stop_lands_on_its_gp", "gpmap.fw_btn_reset_lands_on_its_gp"],
           net=lambda t: swap_nets(t, ("U1", "11"), ("U1", "12"), "GP1_BTN_STOP", "GP2_BTN_BACK")),
    Mutant("firmware_map_moved", "firmware swaps START and STOP bits (the board no longer matches ui_board_map.h)",
           ["gpmap.fw_btn_start_lands_on_its_gp", "gpmap.fw_btn_stop_lands_on_its_gp"],
           firmware=lambda s: s.replace("(1u << 0) /* BTN1 */", "(1u << 9) /* BTN1 */").replace("(1u << 1) /* BTN2 */", "(1u << 0) /* BTN2 */")
           .replace("(1u << 9) /* BTN1 */", "(1u << 1) /* BTN1 */")),
    Mutant("remove_lcsc", "delete U1's LCSC code from the BOM",
           ["bom.every_part_has_an_lcsc_code"],
           bom=lambda b: _set(b, ["parts", "MCP23S08-E/SO", "lcsc"], None)),
    Mutant("zero_stock", "TMP122 stock recorded as 0",
           ["bom.stock_covers_one_board"],
           bom=lambda b: _set(b, ["parts", "TMP122AIDBVR", "jlc_stock"], 0)),
    Mutant("zero_tmag_stock", "TMAG5170 stock recorded as 0",
           ["bom.stock_covers_one_board"],
           bom=lambda b: _set(b, ["parts", "TMAG5170A1QDGKR", "jlc_stock"], 0)),
    Mutant("pullup_on_oled_dc", "a pull-up lands on OLED D/C (GPIO45 strap must read low at reset)",
           ["j7.j7_dc_has_no_resistor_or_pull"],
           net=lambda t: move(t, "R17", "2", "J7_DC")),
    Mutant("remove_button_esd", "SRV05-4 U6 loses the START button channel",
           ["esd.every_external_facing_line_has_srv05_clamp"],
           net=lambda t: drop(t, "U6", "1")),
    Mutant("remove_tab_esd", "SRV05-4 U7 loses the sensor-tab CS# channel",
           ["esd.sensor_tab_inputs_have_srv05_clamp"],
           net=lambda t: drop(t, "U7", "4")),
    Mutant("short_miso_termination", "MISO source resistor R20 shorted (no termination at the UI end)",
           ["j7.miso_source_termination_100_ohm"],
           net=lambda t: move(t, "R20", "2", "MISO_LOCAL")),
    Mutant("esd_vcc_to_gnd", "SRV05-4 U4 Vcc pin grounded (no rail steering)",
           ["j7.srv05_vcc_on_3v3_and_gnd"],
           net=lambda t: move(t, "U4", "5", "GND")),
    Mutant("remove_oled_reset_cap", "OLED RES# capacitor C12 removed (no power-on reset)",
           ["oled.res_n_rc_power_on_reset"],
           net=lambda t: drop(drop(t, "C12", "1"), "C12", "2")),
    Mutant("oled_bs0_floating", "OLED BS0 (pin 20) left open: the interface mode is undefined",
           ["oled.bs1_bs0_tied_low", "oled.nhd_4wire_spi_pin_map"],
           net=lambda t: drop(t, "J3", "20")),
    # ---- new for the owned controls: CS qualification, MISO, sensor, tact, removed parts, buzzer temperature
    Mutant("drop_qualifying_gate_tmag", "TMAG5170 CS# wired straight to GP3 (the gate is bypassed)",
           ["cs.tmag_cs_truth_table_8_of_8", "cs.miso_drivers_high_z_unless_qualified_selected",
            "gpmap.gp3_reaches_the_tmag_chip_select_only_through_the_gate"],
           net=lambda t: move(t, "U8", "4", "GP3_TMAG_SEL_N")),
    Mutant("drop_qualifying_gate_tmp", "TMP122 CS# wired straight to GP7 (the gate is bypassed)",
           ["cs.tmp_cs_truth_table_8_of_8", "cs.miso_drivers_high_z_unless_qualified_selected"],
           net=lambda t: move(t, "U2", "5", "GP7_TMP_SEL_N")),
    Mutant("wrong_gate_polarity", "BUS_BUSY gate is an AND instead of a NAND (SN74LVC1G08 in place of the 1G00)",
           ["cs.tmag_cs_truth_table_8_of_8", "cs.tmp_cs_truth_table_8_of_8", "cs.gate_parts_are_nand_and_dual_or"],
           resolved=lambda r: _set_mpn(r, "u_busy", "SN74LVC1G08DBVR")),
    Mutant("gate_ignores_cs_oled", "the NAND's CS_OLED# input is tied high: an OLED frame no longer deselects the sensor",
           ["cs.tmag_cs_truth_table_8_of_8", "cs.tmp_cs_truth_table_8_of_8", "cs.bus_busy_is_nand_of_cs_exp_and_cs_oled"],
           net=lambda t: move(t, "U9", "2", "V3V3")),
    Mutant("gate_ignores_cs_exp", "the NAND's CS_EXP# input is tied high: an expander write no longer deselects the sensor",
           ["cs.tmag_cs_truth_table_8_of_8", "cs.tmp_cs_truth_table_8_of_8", "cs.bus_busy_is_nand_of_cs_exp_and_cs_oled"],
           net=lambda t: move(t, "U9", "1", "V3V3")),
    Mutant("missing_cs_pullup_tmag", "remove the sensor's CS# pull-up (R24): CS# floats if the gate is unpowered or the harness unplugged",
           ["cs.tmag_cs_has_pullup_le_47k"],
           net=lambda t: drop(t, "R24", "1")),
    Mutant("missing_cs_pullup_tmp", "remove the TMP122's CS# pull-up (R29)",
           ["cs.tmp_cs_has_pullup_le_47k"],
           net=lambda t: drop(t, "R29", "1")),
    Mutant("tmag_select_on_wrong_gp", "the TMAG select gate input moved from GP3 to GP2 (the BACK button line)",
           ["gpmap.gp3_is_tmag_select_to_the_qualification_gate", "gpmap.tmag_select_not_on_a_fixed_gp", "cs.tmag_cs_truth_table_8_of_8"],
           net=lambda t: move(t, "U10", "1", "GP2_BTN_BACK")),
    Mutant("sensor_selected_at_reset", "GP3's pull-up becomes a pull-down: the sensor is selected whenever the bus is idle at reset",
           ["cs.tmag_cs_deselected_at_reset", "inputs.gp3_has_external_pullup_le_47k"],
           net=lambda t: move(t, "R26", "1", "GND")),
    Mutant("tmp_always_selected", "TMP122 CS# tied to GND: it drives MISO all the time",
           ["cs.miso_drivers_high_z_unless_qualified_selected", "cs.no_miso_driver_enabled_at_reset_and_idle", "cs.tmp_cs_truth_table_8_of_8"],
           net=lambda t: move(t, "U2", "5", "GND")),
    Mutant("tmag_sdo_resistor_too_small", "R28 (TMAG SDO series) replaced by 33 ohm: a double select could exceed 10 mA",
           ["cs.tmag_sdo_series_resistor_limits_double_select_below_10mA"],
           resolved=lambda r: _set_value(r, "r_sdo", "33ohm +/- 1%")),
    Mutant("tmag_test_pin_floating", "TMAG5170 TEST (pin 7) left open instead of grounded",
           ["cs.tmag5170_pin_map_and_test_grounded"],
           net=lambda t: drop(t, "U8", "7")),
    Mutant("harness_cs_alert_swapped", "J9 pins 1 and 9 swapped (CS# <-> ALERT) on the sensor tab",
           ["tab.J9_pin_map_1to1_harness"],
           net=lambda t: swap_nets(t, ("J9", "1"), ("J9", "9"), "CS_TMAG_N", "GP4_TMAG_ALERT")),
    Mutant("buzzer_too_hot", "the 70 C buzzer (GSD9605YB-3V2800) is back: no margin at the predicted body temperature",
           ["buzzer.buzzer_rating_covers_predicted_worst_case_temperature", "removed.removed_mpns_absent_from_the_netlist"],
           resolved=lambda r: _set_mpn(r, "bz", "GSD9605YB-3V2800")),
    Mutant("apem_button_returns", "SW1 is an APEM IPR3PAD2 again",
           ["removed.removed_mpns_absent_from_the_netlist", "tact.three_tact_switches_y31b13136fplfg"],
           resolved=lambda r: _set_mpn(r, "sw_start", "IPR3PAD2")),
    Mutant("encoder_socket_returns", "J8 is the Micro-MaTch encoder socket again",
           ["removed.removed_mpns_absent_from_the_netlist", "tab.harness_connectors_are_sm10b_srss"],
           resolved=lambda r: _set_mpn(r, "j_tab", "7-215079-6")),
    Mutant("wrong_tact_part", "SW2 is a KSC243G LFG (the stronger tact), not the specified KSC223G LFG",
           ["tact.three_tact_switches_y31b13136fplfg"],
           resolved=lambda r: _set_mpn(r, "sw_stop", "Y31B43136FPLFG")),
    Mutant("chassis_net_added", "the signal-ground net is bonded to the fascia (modelled by renaming GND to FASCIA_PE): discharge through signal ground",
           ["esd.no_chassis_or_pe_net_in_the_netlist_discharge_path_is_mechanical"],
           net=lambda t: t.replace('(name "GND")', '(name "FASCIA_PE")', 1) if '(name "GND")' in t else t),
    Mutant("remove_gate_decoupling", "remove U10's 100 nF (C18)",
           ["decoup.u_sel_has_100nF_between_supply_and_ground"],
           net=lambda t: drop(drop(t, "C18", "1"), "C18", "2")),
]


def _set(obj: dict, path: list, value):
    o = obj
    for k in path[:-1]:
        o = o[k]
    if value is None:
        o.pop(path[-1], None)
    else:
        o[path[-1]] = value
    return obj


def _set_mpn(resolved: dict, inst_path: str, mpn: str) -> dict:
    for c in resolved["components"]:
        if c["address"].split("::", 1)[1] == inst_path:
            c["attributes"]["mpn"] = mpn
            return resolved
    raise KeyError(inst_path)


def _set_value(resolved: dict, inst_path: str, value: str) -> dict:
    for c in resolved["components"]:
        if c["address"].split("::", 1)[1] == inst_path:
            c["attributes"]["value"] = value
            return resolved
    raise KeyError(inst_path)


def run_one(m: Mutant, tmp: Path) -> dict:
    d = tmp / m.name
    d.mkdir()
    net = (FROZEN / "default.net").read_text()
    if m.net:
        net = m.net(net)
    (d / "default.net").write_text(net)
    resolved = json.loads((FROZEN / "resolved-components.json").read_text())
    if m.resolved:
        resolved = m.resolved(copy.deepcopy(resolved))
    (d / "resolved-components.json").write_text(json.dumps(resolved))
    bom_path = d / "ui-parts.json"
    bom = json.loads((UNIT / "bom/ui-parts.json").read_text())
    if m.bom:
        bom = m.bom(copy.deepcopy(bom))
    bom_path.write_text(json.dumps(bom))
    fw = (UNIT / "inputs/firmware/ui_board_map.h").read_text()
    if m.firmware:
        fw = m.firmware(fw)
    rep = vu.build_report(d, bom_path=bom_path, fw_text=fw, with_calcs=False)
    caught = [c for c in m.expect if c in rep.failed]
    return {"name": m.name, "what": m.what, "expected_to_fail": m.expect, "caught": caught,
            "ok": len(caught) == len(m.expect), "all_failures": rep.failed}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", type=Path, default=UNIT / "evidence" / "mutations.json")
    args = ap.parse_args()
    base = vu.build_report(FROZEN)
    results = []
    with tempfile.TemporaryDirectory() as t:
        for m in MUTANTS:
            results.append(run_one(m, Path(t)))
    ok = not base.failed and all(r["ok"] for r in results)
    out = {"schema": "temper.ui-board.mutations.v1", "baseline_failed": base.failed, "mutations": len(results),
           "caught": sum(r["ok"] for r in results), "results": results}
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(out, indent=2) + "\n")
    print(f"baseline: {'PASS' if not base.failed else 'FAIL ' + str(base.failed)}")
    for r in results:
        print(f"  {'CAUGHT' if r['ok'] else 'MISSED'}  {r['name']:30s} -> {', '.join(r['caught']) or 'nothing'}"
              + ("" if r["ok"] else f"   expected {r['expected_to_fail']}; failed {r['all_failures']}"))
    print(f"MUTATIONS: {out['caught']}/{out['mutations']} caught")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
