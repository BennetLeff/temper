#!/usr/bin/env python3
"""Verify the captured UI board against its contracts, fail-closed.

Reads the frozen (or a fresh) atopile netlist + resolved export of this unit, the controller
unit's J7 contract, the firmware's expander map and the BOM. Sections:

  j7        pin map equal to the controller (DECISIONS C26 table, ENCLOSURE-HANDOFF row, frozen
            netlist, verify_controller.py J7_MAP); a GND beside every signal; ESD on every J7
            signal; MISO source termination; no pull-up on OLED D/C or the chip selects
  gpmap     MCP23S08 GP0-GP7: the fixed roles equal firmware ui_board_map.h (committed copy checked
            against git), opcode 0x40, buzzer the only firmware output; GP3 = TMAG select,
            GP4 = ALERT, GP5 spare (the encoder bits of the header are repurposed)
  inputs    every expander input has a pull-up path
  cs        CS qualification: exhaustive truth table of each gated device over (GPx, CS_EXP#,
            CS_OLED#) read from the netlist, deselected at reset, pull-ups, MISO driver table
            (high-Z unless qualified-selected), TMAG5170 pin map, SDO series resistor, timing
  tact      three KSC223G LFG tact switches on GP0-GP2
  removed   the encoder, its comparator, the APEM buttons and the 70 C buzzer are gone
  tab       the sensor-tab harness (J8 to J9) and its clamp
  buzzer    default off at reset, low-side N-FET, flyback, current in the allocation, rating
            above the predicted worst-case body temperature
  power     3V3 and V5_UI budgets from the netlist (5 V <= 30 mA, 3V3 within the controller
            allocation, headroom) and the calcs they come from
  esd       every external-facing element is clamped; no chassis net in the netlist
  oled      the 4-wire SPI pin map of the NHD-3.12-25664UCW2, unused jumper pins open, RC reset
  decoup    every IC has its own decoupling capacitor (c_<name> for u_<name>)
  bom       every MPN in the netlist has an LCSC code (one named exception), stock recorded,
            CSV equal to the JSON
  floorplan the mechanical checks of tools/floorplan.py
  calcs     tools/ui_calcs.py passes

Usage: python3 tools/verify_ui.py [--build DIR] [--json OUT]    (DIR defaults to frozen/)
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from netlist import Netlist, attach_resolved, parse_value, read_netlist, sha256  # noqa: E402
import floorplan  # noqa: E402
import ui_calcs  # noqa: E402

UNIT = Path(__file__).resolve().parents[1]
CONTROLLER = UNIT.parent / "controller"
GND, V3, V5 = "GND", "V3V3", "V5_UI"
RAILS = {GND, V3, V5}
VMAX = 3.465
V5MAX = 5.1                        # TLV76050 5 V +/- 2 % (controller ui_5v_supply)

# canonical J7 function per pin (the contract; also the order of C26's table)
J7_CANON = {1: "V5", 2: "V3V3", 3: "GND", 4: "SCK", 5: "GND", 6: "MOSI", 7: "MISO", 8: "GND",
            9: "CS_OLED", 10: "DC", 11: "GND", 12: "CS_EXP"}
NET_TO_CANON = {"V5_UI": "V5", "V3V3": "V3V3", "GND": "GND", "J7_SCK": "SCK", "J7_MOSI": "MOSI", "J7_MISO": "MISO",
                "J7_CS_OLED_N": "CS_OLED", "J7_DC": "DC", "J7_CS_EXP_N": "CS_EXP",
                # the controller's own net names
                "v3v3": "V3V3", "selv_gnd": "GND"}
TEXT_TO_CANON = [("+5 V", "V5"), ("+3V3", "V3V3"), ("GND", "GND"), ("SCK", "SCK"), ("MOSI", "MOSI"), ("MISO", "MISO"),
                 ("CS_OLED#", "CS_OLED"), ("OLED D/C", "DC"), ("CS_EXP#", "CS_EXP")]

# Firmware roles (ui_board_map.h UI_BIT_*) -> where each must land on the board. The header's ENC_A/B/SW bits (3-5) are
# repurposed by the owner's decision of 2026-10-12 (DECISIONS U19) and are checked by check_cs.
FW_ROLE_TARGET = {
    "BTN_START": ("sw_start", "1"), "BTN_STOP": ("sw_stop", "1"), "BTN_RESET": ("sw_back", "1"),
    "BUZZER": ("q_buz", "1"), "LOCAL": ("u_tmp", "5"),
}
FIXED_GP_BITS = {0, 1, 2, 6, 7}        # owner's fixed map: buttons, buzzer, TMP122 select
# NHD-3.12-25664UCW2 rev. 7 p.4, 4-wire serial; None = must be open
NHD_PINS = {1: GND, 2: V3, 3: None, 4: "J7_DC", 5: GND, 6: GND, 7: "J7_SCK", 8: "J7_MOSI", 9: None, 10: GND, 11: GND,
            12: GND, 13: GND, 14: GND, 15: None, 16: "OLED_RES_N", 17: "J7_CS_OLED_N", 18: None, 19: GND, 20: GND}
IC_POWER = {"MCP23S08-E/SO": ("18", "9"), "TMP122AIDBVR": ("3", "2"), "TMAG5170A1QDGKR": ("5", "6"),
            "SN74LVC1G00DBVR": ("5", "3"), "SN74LVC2G32DCUR": ("8", "4")}
# logic cells: mpn -> output pin -> (function, (input pins))   (TI SCES212 DBV, SCES201N DCU pin tables)
GATES = {
    "SN74LVC1G00DBVR": {"4": ("nand", ("1", "2"))},
    "SN74LVC2G32DCUR": {"7": ("or", ("1", "2")), "3": ("or", ("5", "6"))},
    "SN74LVC1G08DBVR": {"4": ("and", ("1", "2"))},          # not on the board: a wrong-polarity mutant swaps it in
    "SN74LVC1G32DBVR": {"4": ("or", ("1", "2"))},
}
GATE_FN = {"nand": lambda a, b: 1 - (a & b), "and": lambda a, b: a & b, "or": lambda a, b: a | b}
# parts that must NOT be on the board any more (DECISIONS U19, U28)
REMOVED_MPNS = {"IPR3PAD2": "APEM IPR3PAD2 button", "7-215079-6": "encoder socket J2", "TLV3202AIDR": "encoder comparator",
                "BLM18PG121SN1D": "encoder supply bead", "GSD9605YB-3V2800": "70 C buzzer (replaced, U28)"}
REMOVED_INSTANCES = {"j_enc", "u_cmp", "fb_enc", "u_esd_ctl_b", "c_enc_bulk", "c_enc_hf", "r_pu_a", "r_pu_b", "r_pu_sw", "c_nf_a", "c_nf_b",
                     "r_se_sw", "r_in_a", "r_in_b", "r_hy_a", "r_hy_b", "r_ref_top", "r_ref_bot", "c_ref", "c_cmp"}
TACT_MPN = "Y31B13136FPLFG"
# supply current per device at VMAX, from ui_calcs.py's rows
MODEL_MA = {"MCP23S08-E/SO": 8.0, "TMP122AIDBVR": 0.075, "TMAG5170A1QDGKR": ui_calcs.TMAG_MA, "SN74LVC1G00DBVR": 0.010,
            "SN74LVC2G32DCUR": 0.010, "SRV05-4": 0.001, "1N4148WS": 0.0, "AO3400A": 0.0, "PM254V-11-20-H85": ui_calcs.OLED_MA,
            "B12B-XH-A(LF)(SN)": 0.0, "SM10B-SRSS-TB(LF)(SN)": 0.0, TACT_MPN: 0.0,
            "GSD9605YB-5V2800": ui_calcs.BUZZER_MA, "GSD9605YB-3V2800": ui_calcs.BUZZER_MA}
BUZZER_MPNS = ("GSD9605YB-5V2800", "GSD9605YB-3V2800")
BUZZER_MA_AT_5V = ui_calcs.BUZZER_MA * V5MAX / 5.0     # allocation: the listed 30 mA at the 5 V rating


class Report:
    def __init__(self) -> None:
        self.sections: dict[str, dict] = defaultdict(lambda: {"checks": {}, "data": {}})
        self.failed: list[str] = []

    def check(self, section: str, name: str, ok: bool, detail=None) -> None:
        self.sections[section]["checks"][name] = {"ok": bool(ok), "detail": detail}
        if not ok:
            self.failed.append(f"{section}.{name}")

    def data(self, section: str, name: str, value) -> None:
        self.sections[section]["data"][name] = value


# ================================================================== helpers
class Net:
    """Connectivity helpers over a Netlist."""

    def __init__(self, nl: Netlist) -> None:
        self.nl = nl
        self.pn = nl.pin_net()

    def ref(self, path: str) -> str | None:
        hits = [r for r, p in self.nl.refs.items() if p == path]
        return hits[0] if len(hits) == 1 else None

    def net(self, path: str, pin: str) -> str | None:
        r = self.ref(path)
        return self.pn.get((r, str(pin))) if r else None

    def nodes(self, net: str) -> list[tuple[str, str]]:
        return self.nl.nets.get(net, [])

    def mpn(self, ref: str) -> str:
        return self.nl.mpn.get(ref, "")

    def other(self, ref: str, pin: str) -> str | None:
        return self.pn.get((ref, "2" if str(pin) == "1" else "1"))

    def passives(self, net: str, prefix: str) -> list[tuple[str, str]]:
        return [(r, p) for r, p in self.nodes(net) if r.startswith(prefix)]

    def value(self, ref: str) -> float | None:
        return parse_value(self.nl.value.get(ref))[0]

    def resistors_between(self, a: str, b: str) -> list[str]:
        out = []
        for r, p in self.passives(a, "R"):
            if self.other(r, p) == b and r not in out:
                out.append(r)
        return out

    def reach(self, start: str, hop_gate: bool = True) -> tuple[set[str], set[tuple[str, str]]]:
        """Nets reachable from `start` through series resistors and, when hop_gate, through the first input of a
        qualification OR gate (A -> Y), never through a supply rail. Returns (nets, nodes)."""
        seen, todo, nodes = set(), [start], set()
        while todo:
            n = todo.pop()
            if n in seen or n in RAILS:
                continue
            seen.add(n)
            for r, p in self.nodes(n):
                nodes.add((r, p))
                if r.startswith("R"):
                    o = self.other(r, p)
                    if o:
                        todo.append(o)
                elif hop_gate and self.mpn(r) == "SN74LVC2G32DCUR":
                    out = {"1": "7", "5": "3"}.get(p)               # the GP-side input of each OR gate
                    if out:
                        o = self.pn.get((r, out))
                        if o:
                            todo.append(o)
        return seen, nodes

    # ---- tiny logic evaluator over the netlist (used for the qualification truth tables)
    def eval_net(self, net: str, env: dict[str, int], _depth: int = 0) -> int:
        """Logic level of `net`: env (primary inputs), rails, or the output of exactly one gate on it."""
        if net in env:
            return env[net]
        if net == GND:
            return 0
        if net == V3:
            return 1
        if _depth > 6:
            raise ValueError(f"logic loop at {net}")
        drivers = [(r, p) for r, p in self.nodes(net) if p in GATES.get(self.mpn(r), {})]
        if len(drivers) != 1:
            raise ValueError(f"net {net}: {len(drivers)} gate drivers, no primary input")
        r, p = drivers[0]
        fn, (ia, ib) = GATES[self.mpn(r)][p]
        a = self.eval_net(self.pn.get((r, ia), ""), env, _depth + 1)
        b = self.eval_net(self.pn.get((r, ib), ""), env, _depth + 1)
        return GATE_FN[fn](a, b)

    def pull_level(self, net: str) -> int | None:
        """Level of an undriven (high-impedance) net set by a resistor to a rail: 1, 0 or None (floating or fought)."""
        lv = set()
        for r, p in self.passives(net, "R"):
            o = self.other(r, p)
            if o == V3:
                lv.add(1)
            elif o == GND:
                lv.add(0)
        return lv.pop() if len(lv) == 1 else None


def parse_c26_table(text: str) -> dict[int, str]:
    sec = text.split("## C26.", 1)[1].split("\n## C27.", 1)[0]
    pins: dict[int, str] = {}
    for m in re.finditer(r"^\s*\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*$", sec, re.M):
        for pin, label in ((int(m.group(1)), m.group(2)), (int(m.group(3)), m.group(4))):
            pins[pin] = _canon_text(label)
    return pins


def _canon_text(label: str) -> str:
    for needle, c in TEXT_TO_CANON:
        if label.strip().startswith(needle):
            return c
    return label.strip()


def parse_handoff_row(text: str) -> dict[int, str]:
    row = next(line for line in text.splitlines() if line.startswith("| J7 |"))
    cell = row.split("|")[6]
    pins = {}
    for m in re.finditer(r"(?<![\d.])(\d{1,2}) (\+5 V|\+3V3|GND|SCK|MOSI|MISO|CS_OLED#|OLED D/C|CS_EXP#)", cell):
        pins[int(m.group(1))] = _canon_text(m.group(2))
    return pins


def parse_controller_net_j7() -> dict[int, str]:
    nl = read_netlist(CONTROLLER / "frozen/default.net")
    pn = nl.pin_net()
    j7 = next(r for r, p in nl.refs.items() if r == "J7")
    return {p: NET_TO_CANON.get(pn.get((j7, str(p)), ""), pn.get((j7, str(p)), "?")) for p in range(1, 13)}


def parse_controller_verify_map() -> dict[int, str]:
    src = (CONTROLLER / "tools/verify_controller.py").read_text()
    m = re.search(r"J7_MAP = \{(.+?)\}\n", src, re.S)
    body = m.group(1)
    pins = {}
    for pin, tok in re.findall(r"(\d+): ([\"\w]+)", body):
        name = {"V3": "v3v3", "GND": "selv_gnd"}.get(tok, tok.strip('"'))
        pins[int(pin)] = NET_TO_CANON.get(name, name)
    return pins


def parse_firmware_map(text: str) -> dict:
    bits = {n: int(b) for n, b in re.findall(r"#define UI_BIT_(\w+)\s+\(1u << (\d)\)", text)}
    opcode = int(re.search(r"UI_EXP_OPCODE_WRITE (0x[0-9A-Fa-f]+)u", text).group(1), 16)
    iodir = re.search(r"#define UI_EXP_IODIR\s+\(\(uint8_t\)\(0xFFu & ~UI_BIT_(\w+)\)\)", text).group(1)
    gppu_body = re.search(r"#define UI_EXP_GPPU\s+\(\(uint8_t\)\((.+?)\)\)", text, re.S).group(1)
    gppu = re.findall(r"UI_BIT_(\w+)", gppu_body)
    return {"bits": bits, "opcode": opcode, "output": iodir, "gppu": gppu}


# ================================================================== checks
def check_j7(rep: Report, n: Net) -> None:
    nl = n.nl
    j7 = n.ref("j_ui")
    rep.check("j7", "j7_is_b12b_xh", j7 is not None and nl.mpn.get(j7) == "B12B-XH-A(LF)(SN)", nl.mpn.get(j7 or ""))
    got = {p: NET_TO_CANON.get(n.net("j_ui", f"{p}") or "", n.net("j_ui", f"{p}")) for p in range(1, 13)}
    rep.data("j7", "ui_pins", got)
    c26 = parse_c26_table((CONTROLLER / "DECISIONS.md").read_text())
    hand = parse_handoff_row((CONTROLLER / "ENCLOSURE-HANDOFF.md").read_text())
    cnet = parse_controller_net_j7()
    cver = parse_controller_verify_map()
    rep.data("j7", "controller_c26_table", c26)
    for name, ref in (("controller_c26_table", c26), ("controller_enclosure_handoff", hand),
                      ("controller_frozen_netlist", cnet), ("controller_verify_J7_MAP", cver), ("contract_literal", J7_CANON)):
        rep.check("j7", f"j7_pin_map_equals_{name}", got == ref, {p: (got.get(p), ref.get(p)) for p in range(1, 13) if got.get(p) != ref.get(p)})
    gnd_pins = [p for p, c in got.items() if c == "GND"]
    rep.check("j7", "j7_four_gnd", len(gnd_pins) == 4, gnd_pins)
    sig = [p for p, c in got.items() if c not in ("V5", "V3V3", "GND")]
    lonely = [p for p in sig if not any(got.get(q) == "GND" for q in (p - 1, p + 1))]
    rep.check("j7", "every_j7_signal_beside_a_gnd", not lonely, lonely)
    # ESD arrays on every J7 signal
    unclamped = []
    for p in sig:
        net = n.net("j_ui", str(p))
        if not any(nl.mpn.get(r) == "SRV05-4" and pin in ("1", "3", "4", "6") for r, pin in n.nodes(net)):
            unclamped.append((p, net))
    rep.check("j7", "every_j7_signal_has_srv05_clamp", not unclamped, unclamped)
    arrays = [r for r, m in nl.mpn.items() if m == "SRV05-4"]
    bad = [r for r in arrays if n.pn.get((r, "5")) != V3 or n.pn.get((r, "2")) != GND]
    rep.check("j7", "srv05_vcc_on_3v3_and_gnd", bool(arrays) and not bad, bad)
    # MISO is driven here: 100 ohm source termination between the chips and J7
    rs = n.resistors_between("MISO_LOCAL", "J7_MISO")
    vals = [n.value(r) for r in rs]
    rep.check("j7", "miso_source_termination_100_ohm", len(rs) == 1 and vals[0] is not None and 50 <= vals[0] <= 150, vals)
    # no pull-ups: D/C (controller GPIO45 strap) and both chip selects
    for net, allowed in (("J7_DC", {"j_ui", "u_esd_j7b", "j_oled"}), ("J7_CS_OLED_N", {"j_ui", "u_esd_j7a", "j_oled", "u_busy"}),
                         ("J7_CS_EXP_N", {"j_ui", "u_esd_j7b", "u_exp", "u_busy"})):
        owners = {nl.refs[r] for r, _ in n.nodes(net)}
        rep.check("j7", f"{net.lower()}_has_no_resistor_or_pull", owners <= allowed and not n.passives(net, "R"), sorted(owners))
    # V5_UI reaches no active pin
    rep.check("j7", "j7_5v_not_on_an_ic", all(nl.refs[r] in ("j_ui", "c_v5", "r_v5_bleed") for r, _ in n.nodes(V5)), [nl.refs[r] for r, _ in n.nodes(V5)])


def check_gpmap(rep: Report, n: Net, fw_text: str) -> None:
    nl = n.nl
    fw = parse_firmware_map(fw_text)
    committed = UNIT / "inputs/firmware/ui_board_map.h"
    prov = json.loads((UNIT / "inputs/firmware/provenance.json").read_text())
    rep.check("gpmap", "firmware_copy_matches_provenance_hash", sha256(committed) == prov["sha256"], prov["commit"])
    git = subprocess.run(["git", "show", f"{prov['commit']}:{prov['path']}"], capture_output=True, text=True, cwd=UNIT)
    if git.returncode == 0:
        rep.check("gpmap", "firmware_copy_equals_git_object", git.stdout == committed.read_text(), prov["commit"])
    else:
        rep.data("gpmap", "git_object_unavailable", git.stderr[:200])
    rep.data("gpmap", "firmware_bits", fw["bits"])
    u1 = n.ref("u_exp")
    rep.check("gpmap", "expander_is_mcp23s08", bool(u1) and nl.mpn.get(u1) == "MCP23S08-E/SO", nl.mpn.get(u1 or ""))
    rep.check("gpmap", "opcode_0x40_a1_a0_low", fw["opcode"] == 0x40 and n.net("u_exp", "4") == GND and n.net("u_exp", "5") == GND,
              {"opcode": hex(fw["opcode"]), "A1": n.net("u_exp", "4"), "A0": n.net("u_exp", "5")})
    # every firmware role must land on the GP pin the firmware names
    results = {}
    for role, bit in fw["bits"].items():
        tgt = FW_ROLE_TARGET.get(role)
        gp_net = n.net("u_exp", str(10 + bit))
        if role.startswith("ENC_"):
            results[role] = "repurposed (U19)"
            continue
        if not tgt or gp_net is None:
            results[role] = None
            continue
        _, nodes = n.reach(gp_net)
        tr = n.ref(tgt[0])
        results[role] = bool(tr and (tr, tgt[1]) in nodes)
    rep.data("gpmap", "role_on_named_gp", results)
    for role, ok in results.items():
        if role.startswith("ENC_"):
            continue
        rep.check("gpmap", f"fw_{role.lower()}_lands_on_its_gp", bool(ok), {"gp": fw['bits'][role], "gp_net": n.net("u_exp", str(10 + fw['bits'][role]))})
    # the header's ENC_A/B/SW bits (3-5) are repurposed on this board
    gp3, gp4, gp5 = (n.net("u_exp", str(10 + b)) for b in (3, 4, 5))
    _, gp3_nodes = n.reach(gp3 or "")
    _, gp4_nodes = n.reach(gp4 or "", hop_gate=False)
    rep.check("gpmap", "gp3_is_tmag_select_to_the_qualification_gate", bool(n.ref("u_sel")) and (n.ref("u_sel"), "1") in n.nodes(gp3 or ""), gp3)
    rep.check("gpmap", "gp3_reaches_the_tmag_chip_select_only_through_the_gate",
              (n.ref("u_tmag"), "4") in gp3_nodes and (n.ref("u_tmag"), "4") not in n.nodes(gp3 or ""), gp3)
    rep.check("gpmap", "gp4_is_tmag_alert_input", (n.ref("u_tmag"), "8") in gp4_nodes, gp4)
    rep.check("gpmap", "gp5_spare_has_no_load_other_than_its_pullup", {nl.refs[r] for r, _ in n.nodes(gp5 or "")} == {"u_exp", "r_gp5_pu"}, gp5)
    sel_a1 = n.net("u_sel", "1")
    fixed_nets = {n.net("u_exp", str(10 + b)) for b in FIXED_GP_BITS}
    rep.check("gpmap", "tmag_select_not_on_a_fixed_gp", sel_a1 is not None and sel_a1 not in fixed_nets, (sel_a1, sorted(x or "?" for x in fixed_nets)))
    rep.check("gpmap", "fixed_gps_0_1_2_6_not_touched_by_the_gates",
              all(n.net("u_exp", str(10 + b)) not in (n.net("u_sel", "2"), n.net("u_sel", "6"), n.net("u_busy", "4")) for b in (0, 1, 2, 6)), None)
    # buzzer: the single output; the pins firmware leaves as inputs must not be the buzzer net
    rep.check("gpmap", "buzzer_is_only_output", fw["output"] == "BUZZER", fw["output"])
    rep.check("gpmap", "gppu_never_on_buzzer_bit", "BUZZER" not in fw["gppu"], fw["gppu"])
    # STOP path: button -> expander -> SPI -> controller (software), nothing reaches J7 directly
    _, stop_nodes = n.reach(n.net("sw_stop", "1") or "")
    stop_refs = sorted({nl.refs[r] for r, _ in stop_nodes})
    rep.data("gpmap", "stop_path_instances", stop_refs)
    rep.check("gpmap", "stop_reaches_only_expander_and_clamp", set(stop_refs) <= {"sw_stop", "r_se_stop", "r_pu_stop", "u_exp", "u_esd_ctl_a"},
              stop_refs)


def check_inputs(rep: Report, n: Net, fw_text: str) -> None:
    nl = n.nl
    fw = parse_firmware_map(fw_text)
    out_bit = fw["bits"][fw["output"]]
    rows = {}
    for bit in range(8):
        if bit == out_bit:
            continue
        gp = n.net("u_exp", str(10 + bit))
        nets, _ = n.reach(gp, hop_gate=False)
        pu = []
        for net in nets:
            for r, p in n.passives(net, "R"):
                if n.other(r, p) == V3:
                    v = n.value(r)
                    if v is not None and v <= 47e3:
                        pu.append((r, v))
        rows[f"GP{bit}"] = pu
        rep.check("inputs", f"gp{bit}_has_external_pullup_le_47k", bool(pu), pu)
    rep.data("inputs", "pullups", rows)
    # other expander pins that must be biased: RESET high, chip select of the TMP122 high (GP7 covers it)
    rep.check("inputs", "expander_reset_pulled_high", any(n.other(r, p) == V3 for r, p in n.passives(n.net("u_exp", "6") or "", "R")),
              n.net("u_exp", "6"))


def check_buzzer(rep: Report, n: Net, calcs_thermal: dict) -> None:
    nl = n.nl
    q, bz, d1 = n.ref("q_buz"), n.ref("bz"), n.ref("d_buz")
    bzm = nl.mpn.get(bz or "", "")
    tw = calcs_thermal["buzzer_body_C"]["board_at_80C_design_limit"]
    rating = ui_calcs.BUZZER_RATING_C.get(bzm)
    rep.data("buzzer", "predicted_body_C", calcs_thermal["buzzer_body_C"])
    rep.check("buzzer", "buzzer_rating_covers_predicted_worst_case_temperature",
              rating is not None and rating[1] - tw >= ui_calcs.BUZZER_MARGIN_K, {"mpn": bzm, "rating_C": rating, "predicted_worst_C": tw})
    rep.check("buzzer", "q1_is_n_fet_ao3400a", bool(q) and nl.mpn.get(q) == "AO3400A", nl.mpn.get(q or ""))
    gate = n.net("q_buz", "1")
    src, drn = n.net("q_buz", "2"), n.net("q_buz", "3")
    rep.check("buzzer", "q1_low_side_source_on_gnd", src == GND, src)
    rep.check("buzzer", "buzzer_between_3v3_and_q1_drain", n.net("bz", "1") == V3 and n.net("bz", "2") == drn, (n.net("bz", "1"), n.net("bz", "2"), drn))
    rep.check("buzzer", "flyback_diode_across_buzzer", bool(d1) and n.net("d_buz", "2") == drn and n.net("d_buz", "1") == V3,
              (n.net("d_buz", "2"), n.net("d_buz", "1")))
    # reset model: GP6 is high impedance (IODIR resets to 0xFF); the gate level is set by its resistors
    pd = [(r, n.value(r)) for r, p in n.passives(gate, "R") if n.other(r, p) == GND]
    pu = [(r, n.value(r)) for r, p in n.passives(gate, "R") if n.other(r, p) in (V3, V5)]
    other_active = [nl.refs[r] for r, p in n.nodes(gate) if not r.startswith("R") and nl.refs[r] != "q_buz"]
    off = bool(pd) and not pu and not other_active and all(v is not None and v <= 220e3 for _, v in pd)
    rep.check("buzzer", "default_off_at_reset", off, {"pulldown": pd, "pullup": pu, "other_drivers": other_active})
    series = n.resistors_between(n.net("u_exp", "16") or "", gate)
    rep.check("buzzer", "gp6_drives_gate_through_series_r", len(series) == 1, series)
    # current within the controller's 90 mA buzzer allocation
    rep.check("buzzer", "buzzer_within_90mA_allocation", ui_calcs.BUZZER_MA <= 90.0, ui_calcs.BUZZER_MA)


def rail_load(n: Net, nets: tuple[str, ...], vmax: float, buz_ma: float) -> tuple[float, list, list]:
    """Worst-case current into the loads on `nets`; returns (mA, rows, unmodelled)."""
    nl = n.nl
    rows, unknown, seen = [], [], set()
    for net in nets:
        for ref, pin in n.nodes(net):
            if ref in seen:
                continue
            mpn = nl.mpn.get(ref, "")
            if ref.startswith("R"):
                v = n.value(ref)
                rows.append((nl.refs[ref], vmax / v * 1e3 if v else None))
                seen.add(ref)
            elif ref.startswith("C"):
                rows.append((nl.refs[ref], 0.001))
                seen.add(ref)
            elif mpn in BUZZER_MPNS:
                rows.append((nl.refs[ref], buz_ma))
                seen.add(ref)
            elif mpn in MODEL_MA:
                # the source connector J7 and the bead FB1 pass current, they are not loads
                if mpn in ("B12B-XH-A(LF)(SN)", "SM10B-SRSS-TB(LF)(SN)"):
                    continue
                rows.append((nl.refs[ref], MODEL_MA[mpn]))
                seen.add(ref)
            else:
                unknown.append(nl.refs[ref])
    total = sum(v for _, v in rows if v)
    return total, rows, unknown


def check_power(rep: Report, n: Net, calcs: dict) -> None:
    t3, rows3, unk3 = rail_load(n, (V3,), VMAX, ui_calcs.BUZZER_MA)
    t5, rows5, unk5 = rail_load(n, (V5,), V5MAX, BUZZER_MA_AT_5V)
    rep.data("power", "v3v3_rows_mA", [(a, round(b, 3)) for a, b in rows3 if b])
    rep.data("power", "v3v3_total_mA", round(t3, 3))
    rep.data("power", "v5_rows_mA", [(a, round(b, 3)) for a, b in rows5 if b])
    rep.data("power", "v5_total_mA", round(t5, 3))
    rep.check("power", "no_unmodelled_load_on_rails", not unk3 and not unk5, unk3 + unk5)
    rep.check("power", "v5_budget_le_30mA", t5 <= ui_calcs.V5_BUDGET_MA, round(t5, 3))
    rep.check("power", "v3v3_total_le_controller_allocation_460mA", t3 <= ui_calcs.OLED_MA + ui_calcs.UI_ALLOC_MA, round(t3, 3))
    rep.check("power", "v3v3_without_oled_le_120mA", t3 - ui_calcs.OLED_MA <= ui_calcs.UI_ALLOC_MA, round(t3 - ui_calcs.OLED_MA, 3))
    rep.check("power", "headroom_without_oled_ge_70mA", ui_calcs.UI_ALLOC_MA - (t3 - ui_calcs.OLED_MA) >= 70.0,
              round(ui_calcs.UI_ALLOC_MA - (t3 - ui_calcs.OLED_MA), 3))
    rep.data("power", "headroom_without_oled_mA", round(ui_calcs.UI_ALLOC_MA - (t3 - ui_calcs.OLED_MA), 3))
    cal = calcs["sections"]["power_budget"]["v3v3_total_mA"]
    rep.check("power", "netlist_total_within_5pct_of_calcs", abs(t3 - cal) <= 0.05 * cal, (round(t3, 3), cal))
    h = calcs["sections"]["v3v3_at_load"]
    for k, ok in h["checks"].items():
        rep.check("power", f"rail_{k}", ok)
    # the OLED is powered from 3V3 with the factory jumpers: pins 3, 15, 18 open
    rep.data("power", "oled_supply", calcs["sections"]["oled_supply_options"]["answer"])


def check_esd(rep: Report, n: Net) -> None:
    nl = n.nl
    ext = {f"{p}.{pin}": n.net(p, pin) for p, pin in (("sw_start", "1"), ("sw_stop", "1"), ("sw_back", "1"))}
    bad = {k: v for k, v in ext.items() if not any(nl.mpn.get(r) == "SRV05-4" and p in ("1", "3", "4", "6") for r, p in n.nodes(v or ""))}
    rep.check("esd", "every_external_facing_line_has_srv05_clamp", not bad, bad)
    # series resistance between each switch and its expander pin
    for name, (path, pin) in {"btn_start": ("sw_start", "1"), "btn_stop": ("sw_stop", "1"), "btn_back": ("sw_back", "1")}.items():
        net = n.net(path, pin)
        series = [r for r, p in n.passives(net, "R") if n.other(r, p) not in RAILS and n.value(r) and n.value(r) >= 1e3]
        rep.check("esd", f"{name}_series_ge_1k_to_expander", bool(series), [(r, n.value(r)) for r in series])
    # the sensor tab's four inputs toward the sensor are clamped
    tab = {"SCK": "J7_SCK", "MOSI": "J7_MOSI", "CS": "CS_TMAG_N", "ALERT": "GP4_TMAG_ALERT"}
    unc = [k for k, net in tab.items() if not any(nl.refs[r] == "u_esd_tab" and p in ("1", "3", "4", "6") for r, p in n.nodes(net))]
    rep.check("esd", "sensor_tab_inputs_have_srv05_clamp", not unc, unc)
    # contact discharge must reach the bonded fascia, never signal ground: no chassis / PE / fascia net on this board
    chassis = [k for k in nl.nets if re.search(r"(?i)chassis|\bPE\b|fascia|shield|earth", k)]
    rep.check("esd", "no_chassis_or_pe_net_in_the_netlist_discharge_path_is_mechanical", not chassis, chassis)
    for k, ok in ui_calcs.esd()["checks"].items():
        rep.check("esd", f"calc_{k}", ok)


def check_oled(rep: Report, n: Net) -> None:
    nl = n.nl
    got = {p: n.net("j_oled", str(p)) for p in range(1, 21)}
    wrong = {}
    for p, want in NHD_PINS.items():
        have = got[p]
        if want is None:
            if len(n.nodes(have or "")) > 1:
                wrong[p] = (have, "must be open")
        elif have != want:
            wrong[p] = (have, want)
    rep.check("oled", "nhd_4wire_spi_pin_map", not wrong, wrong)
    rep.check("oled", "bs1_bs0_tied_low", got[19] == GND and got[20] == GND, (got[19], got[20]))
    res = got[16]
    rs = [(r, n.value(r)) for r, p in n.passives(res, "R") if n.other(r, p) == V3]
    cs = [(r, n.value(r)) for r, p in n.passives(res, "C") if n.other(r, p) == GND]
    d = [r for r, p in n.nodes(res) if nl.mpn.get(r) == "1N4148WS" and p == "2"]
    rep.check("oled", "res_n_rc_power_on_reset", len(rs) == 1 and len(cs) == 1 and bool(d), {"R": rs, "C": cs, "D": d})
    if rs and cs and rs[0][1] and cs[0][1]:
        tau = rs[0][1] * cs[0][1]
        lo, hi = tau * 0.99 * 0.8 * 1.609 * 1e3, tau * 1.01 * 1.1 * 1.609 * 1e3
        rep.data("oled", "res_release_ms", [round(lo, 2), round(hi, 2)])
        rep.check("oled", "res_release_between_1ms_and_30ms", lo > 1.0 and hi < 30.0, [round(lo, 2), round(hi, 2)])
    for k, ok in ui_calcs.oled_reset()["checks"].items():
        rep.check("oled", f"calc_{k}", ok)


def check_tmp(rep: Report, n: Net) -> None:
    rep.check("cs", "tmp122_sio_on_miso_local_cs_from_the_gate_sck_on_bus",
              n.net("u_tmp", "6") == "MISO_LOCAL" and n.net("u_tmp", "5") == n.net("u_sel", "3") and n.net("u_sel", "5") == n.net("u_exp", "17")
              and n.net("u_tmp", "4") == "J7_SCK", (n.net("u_tmp", "6"), n.net("u_tmp", "5"), n.net("u_sel", "5"), n.net("u_tmp", "4")))
    rep.check("cs", "chip_selects_not_shared", n.net("u_exp", "7") == "J7_CS_EXP_N" and n.net("j_oled", "17") == "J7_CS_OLED_N"
              and n.net("u_exp", "7") != n.net("j_oled", "17"), None)


def check_cs(rep: Report, n: Net, calcs: dict) -> None:
    nl = n.nl
    cse, cso = "J7_CS_EXP_N", "J7_CS_OLED_N"
    gp = {"tmag": n.net("u_exp", "13"), "tmp": n.net("u_exp", "17")}
    csnet = {"tmag": n.net("u_tmag", "4"), "tmp": n.net("u_tmp", "5")}
    # --- structure of the gate network
    rep.check("cs", "gate_parts_are_nand_and_dual_or", n.mpn(n.ref("u_busy") or "") == "SN74LVC1G00DBVR" and n.mpn(n.ref("u_sel") or "") == "SN74LVC2G32DCUR",
              (n.mpn(n.ref("u_busy") or ""), n.mpn(n.ref("u_sel") or "")))
    rep.check("cs", "bus_busy_is_nand_of_cs_exp_and_cs_oled",
              {n.net("u_busy", "1"), n.net("u_busy", "2")} == {cse, cso} and bool(n.net("u_busy", "4")), (n.net("u_busy", "1"), n.net("u_busy", "2")))
    # --- exhaustive truth table per device, evaluated from the netlist
    results = {}
    for dev in ("tmag", "tmp"):
        rows, bad = [], []
        try:
            for g in (0, 1):
                for e in (0, 1):
                    for o in (0, 1):
                        env = {gp[dev]: g, cse: e, cso: o}
                        for other in gp.values():
                            env.setdefault(other, 1)                # the other device's request is idle
                        v = n.eval_net(csnet[dev], env)
                        want = ui_calcs.cs_expected(g, e, o)
                        rows.append((g, e, o, v))
                        if v != want:
                            bad.append({"GPx": g, "CS_EXP_N": e, "CS_OLED_N": o, "got": v, "want": want})
            ok = not bad
            detail = bad or "8 of 8 rows match: low only for (0,1,1)"
        except ValueError as exc:
            ok, detail, rows = False, str(exc), []
        results[dev] = rows
        rep.check("cs", f"{dev}_cs_truth_table_8_of_8", ok, detail)
    rep.data("cs", "truth_table_rows_GPx_CSEXP_CSOLED_CSdev", results)
    # --- reset: the expander pins are inputs (high-Z); the pull-up must hold the request idle, whatever the chip selects do
    for dev in ("tmag", "tmp"):
        lvl = n.pull_level(gp[dev] or "")
        ok = lvl == 1
        if ok:
            try:
                ok = all(n.eval_net(csnet[dev], {gp[dev]: 1, cse: e, cso: o, **{g: 1 for g in gp.values()}}) == 1 for e in (0, 1) for o in (0, 1))
            except ValueError as exc:
                ok = False
                lvl = str(exc)
        rep.check("cs", f"{dev}_cs_deselected_at_reset", ok, {"gp_net": gp[dev], "pull_level": lvl})
        # the device-side pull-up keeps CS# high if the gate is unpowered or the harness is unplugged
        pu = [(r, n.value(r)) for r, p in n.passives(csnet[dev] or "", "R") if n.other(r, p) == V3 and (n.value(r) or 1e9) <= 47e3]
        rep.check("cs", f"{dev}_cs_has_pullup_le_47k", bool(pu), pu)
    # --- MISO: every driver high-Z unless qualified-selected (16 rows over GP3, GP7, CS_EXP#, CS_OLED#)
    drivers = {"MCP23S08": n.net("u_exp", "7"), "TMAG5170": csnet["tmag"], "TMP122": csnet["tmp"]}
    bad_rows, multi, tbl, err = [], [], [], None
    try:
        for g3 in (0, 1):
            for g7 in (0, 1):
                for e in (0, 1):
                    for o in (0, 1):
                        env = {gp["tmag"]: g3, gp["tmp"]: g7, cse: e, cso: o}
                        en = {k: n.eval_net(net, env) == 0 for k, net in drivers.items()}
                        want = {"MCP23S08": e == 0, "TMAG5170": ui_calcs.cs_expected(g3, e, o) == 0, "TMP122": ui_calcs.cs_expected(g7, e, o) == 0}
                        tbl.append({"GP3": g3, "GP7": g7, "CS_EXP_N": e, "CS_OLED_N": o, "enabled": [k for k, v in en.items() if v]})
                        extra = [k for k in en if en[k] and not want[k]]
                        if extra or en != want:
                            bad_rows.append({"row": (g3, g7, e, o), "enabled": [k for k, v in en.items() if v], "extra": extra})
                        if sum(en.values()) > 1 and not (g3 == 0 and g7 == 0 and e == 1 and o == 1):
                            multi.append((g3, g7, e, o))
    except ValueError as exc:
        err = str(exc)
    rep.data("cs", "miso_driver_table", tbl)
    rep.check("cs", "miso_drivers_high_z_unless_qualified_selected", err is None and not bad_rows, err or bad_rows)
    rep.check("cs", "at_most_one_miso_driver_except_double_select_of_both_gps", err is None and not multi, err or multi)
    try:
        idle = {gp["tmag"]: 1, gp["tmp"]: 1, cse: 1, cso: 1}
        none_at_idle = all(n.eval_net(net, idle) == 1 for net in drivers.values())
    except ValueError:
        none_at_idle = False
    rep.check("cs", "no_miso_driver_enabled_at_reset_and_idle", none_at_idle, None)
    # --- TMAG5170 wiring (SBASAF4 p.4 Table 5-1)
    want = {"1": "J7_SCK", "2": "J7_MOSI", "4": "CS_TMAG_N", "5": V3, "6": GND, "7": GND, "8": "GP4_TMAG_ALERT"}
    got = {pin: n.net("u_tmag", pin) for pin in want}
    rep.check("cs", "tmag5170_pin_map_and_test_grounded", got == want, {k: (got[k], want[k]) for k in want if got[k] != want[k]})
    sdo = n.net("u_tmag", "3")
    rs = n.resistors_between(sdo or "", "MISO_LOCAL")
    v = n.value(rs[0]) if len(rs) == 1 else None
    need = ui_calcs.VMAX / 10e-3        # 3.465 V against the sensor's 10 mA absolute-maximum output current
    rep.check("cs", "tmag_sdo_series_resistor_limits_double_select_below_10mA", v is not None and v >= need, {"R": v, "min": round(need, 1)})
    rep.check("cs", "tmag_sdo_reaches_miso_only_through_that_resistor", len(n.nodes(sdo or "")) == 2, [nl.refs[r] for r, _ in n.nodes(sdo or "")])
    # --- timing and firmware sequence (calcs)
    for k, ok in calcs["sections"]["cs_qualification"]["checks"].items():
        rep.check("cs", f"calc_{k}", ok)
    for k, ok in calcs["sections"]["spi_timing"]["checks"].items():
        if k.startswith("tmag"):
            rep.check("cs", f"calc_{k}", ok)


def check_tact(rep: Report, n: Net, calcs: dict) -> None:
    nl = n.nl
    sws = [r for r in nl.mpn if nl.refs[r].startswith("sw_")]
    rep.check("tact", "three_tact_switches_y31b13136fplfg", len(sws) == 3 and all(nl.mpn[r] == TACT_MPN for r in sws), [(r, nl.mpn[r]) for r in sws])
    rep.check("tact", "tact_footprint_is_the_ksc2_manufacturer_pattern", all("KSC2" in nl.footprint[r] for r in sws), [nl.footprint[r] for r in sws])
    for nm, path in (("start", "sw_start"), ("stop", "sw_stop"), ("back", "sw_back")):
        a, b = n.net(path, "1"), n.net(path, "2")
        pu = [(r, n.value(r)) for r, p in n.passives(a or "", "R") if n.other(r, p) == V3 and n.value(r) == 10e3]
        rep.check("tact", f"sw_{nm}_active_low_to_gnd_with_10k_pullup", b == GND and len(pu) == 1, {"A": a, "B": b, "pullup": pu})
    for k, ok in calcs["sections"]["pullups"]["checks"].items():
        rep.check("tact", f"calc_{k}", ok)
    for k, ok in calcs["sections"]["tact_switch"]["checks"].items():
        rep.check("tact", f"calc_{k}", ok)


def check_removed(rep: Report, n: Net, bom: dict) -> None:
    nl = n.nl
    present = {m: why for m, why in REMOVED_MPNS.items() if m in set(nl.mpn.values())}
    rep.check("removed", "removed_mpns_absent_from_the_netlist", not present, present)
    inst = sorted(set(nl.refs.values()) & REMOVED_INSTANCES)
    rep.check("removed", "removed_instances_absent", not inst, inst)
    nets = [k for k in nl.nets if k.startswith("ENC_") or k == "V3V3_ENC"]
    rep.check("removed", "no_encoder_nets", not nets, nets)
    inbom = sorted(set(bom["parts"]) & set(REMOVED_MPNS))
    rep.check("removed", "removed_mpns_absent_from_the_bom", not inbom, inbom)
    text = json.dumps(bom["parts"]) + json.dumps(bom.get("off_board", []))
    rep.check("removed", "no_grayhill_or_apem_in_the_bom", not re.search(r"(?i)grayhill|apem|62VG15", text), None)
    conns = sorted(r for r in nl.refs if r.startswith("J"))
    rep.check("removed", "connectors_are_j3_j7_j8_j9_only", conns == ["J3", "J7", "J8", "J9"], conns)


def check_tab(rep: Report, n: Net) -> None:
    want = {1: "CS_TMAG_N", 2: GND, 3: "J7_SCK", 4: GND, 5: "J7_MOSI", 6: GND, 7: "MISO_LOCAL", 8: GND, 9: "GP4_TMAG_ALERT", 10: V3}
    for path, name in (("j_tab", "J8"), ("j_tabr", "J9")):
        got = {p: n.net(path, str(p)) for p in range(1, 11)}
        rep.check("tab", f"{name}_pin_map_1to1_harness", got == want, {p: (got[p], want[p]) for p in want if got[p] != want[p]})
    sig = [p for p, v in want.items() if v not in (V3, GND)]
    lonely = [p for p in sig if not any(want.get(q) == GND for q in (p - 1, p + 1))]
    rep.check("tab", "every_harness_signal_beside_a_gnd", not lonely, lonely)
    rep.check("tab", "harness_connectors_are_sm10b_srss", n.mpn(n.ref("j_tab") or "") == n.mpn(n.ref("j_tabr") or "") == "SM10B-SRSS-TB(LF)(SN)", None)


def check_decoup(rep: Report, n: Net) -> None:
    nl = n.nl
    ics = [r for r, m in nl.mpn.items() if m in IC_POWER]
    rep.data("decoup", "ics", [nl.refs[r] for r in ics])
    for ic in ics:
        vp, gp = IC_POWER[nl.mpn[ic]]
        vnet, gnet = n.pn.get((ic, vp)), n.pn.get((ic, gp))
        name = nl.refs[ic].removeprefix("u_")
        cap = n.ref(f"c_{name}")
        ok = False
        detail = None
        if cap:
            nets = {n.pn.get((cap, "1")), n.pn.get((cap, "2"))}
            v = n.value(cap)
            ok = nets == {vnet, gnet} and v is not None and v >= 100e-9 - 1e-12
            detail = (cap, v, sorted(x or "?" for x in nets))
        rep.check("decoup", f"{nl.refs[ic]}_has_100nF_between_supply_and_ground", ok, detail)
    # bulk at the J7 entry and the OLED socket
    for path in ("c_3v3_bulk", "c_oled_bulk"):
        r = n.ref(path)
        v = n.value(r) if r else None
        rep.check("decoup", f"{path}_ge_10uF_on_3v3", bool(r) and v is not None and v >= 10e-6 and {n.pn.get((r, '1')), n.pn.get((r, '2'))} == {V3, GND}, v)


def check_bom(rep: Report, n: Net, bom: dict, csv_path: Path) -> None:
    nl = n.nl
    parts = bom["parts"]
    mpns = set(nl.mpn.values())
    rep.check("bom", "every_netlist_mpn_is_in_the_bom", mpns <= set(parts), sorted(mpns - set(parts)))
    missing, exceptions = [], []
    for m in sorted(mpns & set(parts)):
        rec = parts[m]
        code = rec.get("lcsc")
        if code and re.fullmatch(r"C\d{3,}", code):
            continue
        if not code and rec.get("lcsc_exception"):
            exceptions.append(m)
        else:
            missing.append(m)
    rep.check("bom", "every_part_has_an_lcsc_code", not missing, missing)
    rep.check("bom", "only_the_tact_switches_are_off_lcsc", exceptions == [TACT_MPN], exceptions)
    nostock = [m for m in mpns & set(parts) if parts[m].get("lcsc") and not (parts[m].get("jlc_stock") and parts[m].get("jlc_stock_checked"))]
    rep.check("bom", "stock_and_check_date_recorded", not nostock, nostock)
    lowstock = [m for m in mpns & set(parts) if parts[m].get("lcsc") and (parts[m].get("jlc_stock") or 0) < sum(1 for v in nl.mpn.values() if v == m)]
    rep.check("bom", "stock_covers_one_board", not lowstock, lowstock)
    bad_lib = [m for m in mpns & set(parts) if parts[m].get("lcsc") and parts[m].get("jlc_library") not in ("basic", "extended")]
    rep.check("bom", "jlc_library_type_recorded", not bad_lib, bad_lib)
    rep.check("bom", "ext_parts_listed_basic_preferred", True, [m for m in parts if parts[m].get("jlc_library") == "extended"])
    # designators in the JSON equal the netlist
    nl_des = defaultdict(set)
    for r, m in nl.mpn.items():
        nl_des[m].add(r)
    off = {m: (sorted(nl_des[m]), parts[m].get("designators")) for m in nl_des if m in parts and sorted(nl_des[m]) != sorted(parts[m].get("designators", []))}
    rep.check("bom", "bom_designators_equal_netlist", not off, off)
    # CSV equals the JSON (per designator group)
    with csv_path.open(newline="") as fh:
        rows = {r["Comment"]: r for r in csv.DictReader(fh)}
    diff = [m for m in mpns if m in parts and (rows.get(m, {}).get("LCSC Part #", None) != (parts[m].get("lcsc") or "")
                                                or sorted(rows.get(m, {}).get("Designator", "").split(",")) != sorted(parts[m]["designators"]))]
    rep.check("bom", "csv_equals_json", not diff, diff)
    summ = bom["summary"]
    rep.data("bom", "summary", summ)
    lines = [m for m in parts if parts[m].get("designators")]
    rep.check("bom", "summary_counts_match", summ["bom_lines"] == len(lines) == len(mpns)
              and summ["basic"] == sum(1 for m in lines if parts[m].get("jlc_library") == "basic")
              and summ["extended"] == sum(1 for m in lines if parts[m].get("jlc_library") == "extended"), summ)


def check_floorplan(rep: Report) -> None:
    ck, data = floorplan.checks()
    src_present = ck.pop("enclosure_source_present")
    rep.data("floorplan", "enclosure_source", data["enclosure_source"])
    rep.check("floorplan", "enclosure_source_present_or_skipped", True, "present" if src_present else "absent: embedded numbers used")
    for k, ok in ck.items():
        rep.check("floorplan", k, ok)
    rep.data("floorplan", "enclosure_findings", data["enclosure_findings"])
    rep.data("floorplan", "numbers", {k: v for k, v in data.items() if k != "enclosure_findings"})


def check_frozen(rep: Report, build: Path) -> None:
    rcpt = UNIT / "frozen/build-receipt.json"
    if build.resolve() != (UNIT / "frozen").resolve() or not rcpt.is_file():
        return
    r = json.loads(rcpt.read_text())
    src = {str(p.relative_to(UNIT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((UNIT / "elec/src").rglob("*.ato"))}
    rep.check("frozen", "ato_sources_match_receipt", src == r["source_sha256"], [k for k in src if src.get(k) != r["source_sha256"].get(k)])
    out = {k: sha256(UNIT / "frozen" / k) for k in r["frozen_sha256"]}
    rep.check("frozen", "frozen_files_match_receipt", out == r["frozen_sha256"], None)


def check_calcs(rep: Report) -> dict:
    proc = subprocess.run([sys.executable, str(UNIT / "tools/ui_calcs.py"), "--quiet"], capture_output=True, text=True)
    calcs = json.loads((UNIT / "evidence/ui_calcs.json").read_text())
    rep.check("calcs", "ui_calcs_pass", proc.returncode == 0, calcs["failed_checks"])
    return calcs


# ================================================================== driver
def build_report(build: Path, bom_path: Path | None = None, csv_path: Path | None = None, fw_text: str | None = None,
                 with_calcs: bool = True) -> Report:
    nl = attach_resolved(read_netlist(build / "default.net"), build / "resolved-components.json")
    n = Net(nl)
    rep = Report()
    calcs = check_calcs(rep) if with_calcs else json.loads((UNIT / "evidence/ui_calcs.json").read_text())
    bom = json.loads((bom_path or UNIT / "bom/ui-parts.json").read_text())
    fw = fw_text if fw_text is not None else (UNIT / "inputs/firmware/ui_board_map.h").read_text()
    check_j7(rep, n)
    check_gpmap(rep, n, fw)
    check_inputs(rep, n, fw)
    check_buzzer(rep, n, calcs["sections"]["buzzer_thermal"])
    check_power(rep, n, calcs)
    check_esd(rep, n)
    check_oled(rep, n)
    check_tmp(rep, n)
    check_cs(rep, n, calcs)
    check_tact(rep, n, calcs)
    check_removed(rep, n, bom)
    check_tab(rep, n)
    check_decoup(rep, n)
    check_bom(rep, n, bom, csv_path or UNIT / "bom/ui-parts.csv")
    check_floorplan(rep)
    check_frozen(rep, build)
    return rep


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build", type=Path, default=UNIT / "frozen")
    ap.add_argument("--json", type=Path, default=UNIT / "evidence" / "verify.json")
    args = ap.parse_args()
    args.build = args.build.resolve()
    rep = build_report(args.build)
    total = sum(len(v["checks"]) for v in rep.sections.values())
    out = {"schema": "temper.ui-board.verify.v1", "netlist": str(args.build.relative_to(UNIT) / "default.net"),
           "netlist_sha256": sha256(args.build / "default.net"), "checks_total": total, "checks_passed": total - len(rep.failed),
           "failed": rep.failed, "sections": rep.sections}
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(out, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    for s, v in rep.sections.items():
        print(f"{s:10s} {sum(c['ok'] for c in v['checks'].values())}/{len(v['checks'])}")
    print(f"VERIFY: {'PASS' if not rep.failed else 'FAIL ' + str(rep.failed)} ({total - len(rep.failed)}/{total} checks)")
    return 1 if rep.failed else 0


if __name__ == "__main__":
    sys.exit(main())
