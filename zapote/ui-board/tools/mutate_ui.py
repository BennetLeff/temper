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
    Mutant("swap_j7_sck_mosi", "swap J7 pins 4 and 6 (SCK <-> MOSI)",
           ["j7.j7_pin_map_equals_controller_c26_table", "j7.j7_pin_map_equals_controller_enclosure_handoff",
            "j7.j7_pin_map_equals_controller_frozen_netlist", "j7.j7_pin_map_equals_controller_verify_J7_MAP"],
           net=lambda t: swap_nets(t, ("J7", "4"), ("J7", "6"), "J7_SCK", "J7_MOSI")),
    Mutant("swap_j7_miso_cs_exp", "swap J7 pins 7 and 12 (MISO <-> CS_EXP#)",
           ["j7.j7_pin_map_equals_controller_c26_table"],
           net=lambda t: swap_nets(t, ("J7", "7"), ("J7", "12"), "J7_MISO", "J7_CS_EXP_N")),
    Mutant("drop_encoder_a_pullup", "remove the pull-up on encoder A (R9 loses its rail pin)",
           ["inputs.gp3_has_external_pullup_le_47k", "encoder.enc_a_pullup_10k_to_encoder_rail"],
           net=lambda t: drop(t, "R9", "1")),
    Mutant("drop_stop_button_pullup", "remove the STOP button pull-up (R5)",
           ["inputs.gp1_has_external_pullup_le_47k"],
           net=lambda t: drop(t, "R5", "1")),
    Mutant("drop_tmp_cs_pullup", "remove the TMP122 chip-select pull-up (R17)",
           ["inputs.gp7_has_external_pullup_le_47k"],
           net=lambda t: drop(t, "R17", "1")),
    Mutant("invert_buzzer_default", "buzzer gate resistor pulls up instead of down (on at reset)",
           ["buzzer.default_off_at_reset"],
           net=lambda t: move(t, "R22", "2", "V3V3")),
    Mutant("buzzer_on_5v", "buzzer supplied from V5_UI: 47 mA at 5.1 V against a 30 mA budget",
           ["power.v5_budget_le_30mA", "buzzer.buzzer_between_3v3_and_q1_drain"],
           net=lambda t: move(t, "BZ1", "1", "V5_UI")),
    Mutant("remove_expander_decoupling", "remove U1's 100 nF (C3)",
           ["decoup.u_exp_has_100nF_between_supply_and_ground"],
           net=lambda t: drop(drop(t, "C3", "1"), "C3", "2")),
    Mutant("remove_comparator_decoupling", "remove U3's 100 nF (C5)",
           ["decoup.u_cmp_has_100nF_between_supply_and_ground"],
           net=lambda t: drop(drop(t, "C5", "1"), "C5", "2")),
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
    Mutant("pullup_on_oled_dc", "a pull-up lands on OLED D/C (GPIO45 strap must read low at reset)",
           ["j7.j7_dc_has_no_resistor_or_pull"],
           net=lambda t: move(t, "R17", "2", "J7_DC")),
    Mutant("swap_encoder_a_b", "encoder A and B swapped at J2",
           ["encoder.j2_pin_map_per_grayhill_vg", "gpmap.fw_enc_a_lands_on_its_gp", "gpmap.fw_enc_b_lands_on_its_gp"],
           net=lambda t: swap_nets(t, ("J2", "4"), ("J2", "5"), "ENC_B_RAW", "ENC_A_RAW")),
    Mutant("remove_button_esd", "SRV05-4 U6 loses the START button channel",
           ["esd.every_external_facing_line_has_srv05_clamp"],
           net=lambda t: drop(t, "U6", "1")),
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
    Mutant("bad_comparator_reference", "R16 20 k: the encoder threshold rises to 2.1 V, above the encoder's worst high",
           ["encoder.comparator_high_margin_ge_0p3V"],
           resolved=lambda r: _set_value(r, "r_ref_bot", "20kohm +/- 1%")),
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
