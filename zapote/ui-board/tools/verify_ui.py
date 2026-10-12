#!/usr/bin/env python3
"""Verify the captured UI board against its contracts, fail-closed.

Reads the frozen (or a fresh) atopile netlist + resolved export of this unit, the controller
unit's J7 contract, the firmware's expander map and the BOM. Sections:

  j7        pin map equal to the controller (DECISIONS C26 table, ENCLOSURE-HANDOFF row, frozen
            netlist, verify_controller.py J7_MAP); a GND beside every signal; ESD on every J7
            signal; MISO source termination; no pull-up on OLED D/C or the chip selects
  gpmap     MCP23S08 GP0-GP7 equal to firmware ui_board_map.h (committed copy checked against
            git), opcode 0x40, buzzer the only output
  inputs    every expander input has a pull-up path, and the encoder levels reach the expander
  buzzer    default off at reset, low-side N-FET, flyback, current in the allocation
  power     3V3 and V5_UI budgets from the netlist (5 V <= 30 mA, 3V3 within the controller
            allocation) and the calcs they come from
  esd       every external-facing element is clamped
  oled      the 4-wire SPI pin map of the NHD-3.12-25664UCW2, unused jumper pins open, RC reset
  encoder   J2 pin map per the Grayhill drawing; comparator thresholds recomputed from the
            netlist values
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
GND, V3, V3E, V5 = "GND", "V3V3", "V3V3_ENC", "V5_UI"
RAILS = {GND, V3, V3E, V5}
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

# Firmware roles (ui_board_map.h UI_BIT_*) -> where each must land on the board
FW_ROLE_TARGET = {
    "BTN_START": ("sw_start", "1"), "BTN_STOP": ("sw_stop", "1"), "BTN_RESET": ("sw_back", "1"),
    "ENC_A": ("j_enc", "5"), "ENC_B": ("j_enc", "4"), "ENC_SW": ("j_enc", "3"),
    "BUZZER": ("q_buz", "1"), "LOCAL": ("u_tmp", "5"),
}
GRAYHILL_J2 = {1: GND, 2: GND, 3: "ENC_SW_RAW", 4: "ENC_B_RAW", 5: "ENC_A_RAW", 6: V3E}   # Grayhill 62AG/VG p.3 (VG style)
# NHD-3.12-25664UCW2 rev. 7 p.4, 4-wire serial; None = must be open
NHD_PINS = {1: GND, 2: V3, 3: None, 4: "J7_DC", 5: GND, 6: GND, 7: "J7_SCK", 8: "J7_MOSI", 9: None, 10: GND, 11: GND,
            12: GND, 13: GND, 14: GND, 15: None, 16: "OLED_RES_N", 17: "J7_CS_OLED_N", 18: None, 19: GND, 20: GND}
IC_POWER = {"MCP23S08-E/SO": ("18", "9"), "TMP122AIDBVR": ("3", "2"), "TLV3202AIDR": ("8", "4")}
# supply current per device at VMAX, from ui_calcs.py's rows
MODEL_MA = {"MCP23S08-E/SO": 8.0, "TMP122AIDBVR": 0.075, "TLV3202AIDR": 0.120, "SRV05-4": 0.001,
            "BLM18PG121SN1D": 0.0, "1N4148WS": 0.0, "AO3400A": 0.0, "PM254V-11-20-H85": ui_calcs.OLED_MA,
            "7-215079-6": 30.0, "B12B-XH-A(LF)(SN)": 0.0, "IPR3PAD2": 0.0,
            "GSD9605YB-3V2800": 30.0 * VMAX / 3.3}
BUZZER_MA_AT_5V = 30.0 * V5MAX / 3.3          # the buzzer's operating range is 2-5 V; linear scaling [ALLOCATION]


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

    def reach(self, start: str, hop_comparator: bool = True) -> tuple[set[str], set[tuple[str, str]]]:
        """Nets reachable from `start` through series resistors and the comparator channels
        (OUT->IN+), never through a supply rail. Returns (nets, nodes)."""
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
                elif hop_comparator and self.mpn(r) == "TLV3202AIDR":
                    pair = {"1": "3", "7": "5", "3": "1", "5": "7"}.get(p)
                    if pair:
                        o = self.pn.get((r, pair))
                        if o:
                            todo.append(o)
        return seen, nodes


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
    for net, allowed in (("J7_DC", {"j_ui", "u_esd_j7b", "j_oled"}), ("J7_CS_OLED_N", {"j_ui", "u_esd_j7a", "j_oled"}),
                         ("J7_CS_EXP_N", {"j_ui", "u_esd_j7b", "u_exp"})):
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
        if not tgt or gp_net is None:
            results[role] = None
            continue
        _, nodes = n.reach(gp_net)
        tr = n.ref(tgt[0])
        results[role] = bool(tr and (tr, tgt[1]) in nodes)
    rep.data("gpmap", "role_on_named_gp", results)
    for role, ok in results.items():
        rep.check("gpmap", f"fw_{role.lower()}_lands_on_its_gp", bool(ok), {"gp": fw['bits'][role], "gp_net": n.net("u_exp", str(10 + fw['bits'][role]))})
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
        nets, _ = n.reach(gp)
        pu = []
        for net in nets:
            for r, p in n.passives(net, "R"):
                if n.other(r, p) in (V3, V3E):
                    v = n.value(r)
                    if v is not None and v <= 47e3:
                        pu.append((r, v))
        rows[f"GP{bit}"] = pu
        rep.check("inputs", f"gp{bit}_has_external_pullup_le_47k", bool(pu), pu)
    rep.data("inputs", "pullups", rows)
    # other expander pins that must be biased: RESET high, chip select of the TMP122 high (GP7 covers it)
    rep.check("inputs", "expander_reset_pulled_high", any(n.other(r, p) == V3 for r, p in n.passives(n.net("u_exp", "6") or "", "R")),
              n.net("u_exp", "6"))
    # the encoder levels (low <= 1.0 V, high >= 2.0 V) must be restored by the comparator
    for ch, (out_pin, in_pin) in {"A": ("1", "3"), "B": ("7", "5")}.items():
        out_net, in_net = n.net("u_cmp", out_pin), n.net("u_cmp", in_pin)
        gp = n.net("u_exp", str(10 + fw["bits"][f"ENC_{ch}"]))
        rep.check("inputs", f"enc_{ch.lower()}_reaches_gp_through_comparator", out_net == gp and out_net != in_net, (out_net, gp))


def check_buzzer(rep: Report, n: Net) -> None:
    nl = n.nl
    q, bz, d1 = n.ref("q_buz"), n.ref("bz"), n.ref("d_buz")
    rep.check("buzzer", "q1_is_n_fet_ao3400a", bool(q) and nl.mpn.get(q) == "AO3400A", nl.mpn.get(q or ""))
    gate = n.net("q_buz", "1")
    src, drn = n.net("q_buz", "2"), n.net("q_buz", "3")
    rep.check("buzzer", "q1_low_side_source_on_gnd", src == GND, src)
    rep.check("buzzer", "buzzer_between_3v3_and_q1_drain", n.net("bz", "1") == V3 and n.net("bz", "2") == drn, (n.net("bz", "1"), n.net("bz", "2"), drn))
    rep.check("buzzer", "flyback_diode_across_buzzer", bool(d1) and n.net("d_buz", "2") == drn and n.net("d_buz", "1") == V3,
              (n.net("d_buz", "2"), n.net("d_buz", "1")))
    # reset model: GP6 is high impedance (IODIR resets to 0xFF); the gate level is set by its resistors
    pd = [(r, n.value(r)) for r, p in n.passives(gate, "R") if n.other(r, p) == GND]
    pu = [(r, n.value(r)) for r, p in n.passives(gate, "R") if n.other(r, p) in (V3, V3E, V5)]
    other_active = [nl.refs[r] for r, p in n.nodes(gate) if not r.startswith("R") and nl.refs[r] != "q_buz"]
    off = bool(pd) and not pu and not other_active and all(v is not None and v <= 220e3 for _, v in pd)
    rep.check("buzzer", "default_off_at_reset", off, {"pulldown": pd, "pullup": pu, "other_drivers": other_active})
    series = n.resistors_between(n.net("u_exp", "16") or "", gate)
    rep.check("buzzer", "gp6_drives_gate_through_series_r", len(series) == 1, series)
    # current within the controller's 90 mA buzzer allocation
    rep.check("buzzer", "buzzer_within_90mA_allocation", MODEL_MA["GSD9605YB-3V2800"] <= 90.0, MODEL_MA["GSD9605YB-3V2800"])


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
            elif mpn == "GSD9605YB-3V2800":
                rows.append((nl.refs[ref], buz_ma))
                seen.add(ref)
            elif mpn in MODEL_MA:
                # the source connector J7 and the bead FB1 pass current, they are not loads
                if mpn == "B12B-XH-A(LF)(SN)" or mpn == "BLM18PG121SN1D":
                    continue
                rows.append((nl.refs[ref], MODEL_MA[mpn]))
                seen.add(ref)
            else:
                unknown.append(nl.refs[ref])
    total = sum(v for _, v in rows if v)
    return total, rows, unknown


def check_power(rep: Report, n: Net, calcs: dict) -> None:
    t3, rows3, unk3 = rail_load(n, (V3, V3E), VMAX, MODEL_MA["GSD9605YB-3V2800"])
    t5, rows5, unk5 = rail_load(n, (V5,), V5MAX, BUZZER_MA_AT_5V)
    rep.data("power", "v3v3_rows_mA", [(a, round(b, 3)) for a, b in rows3 if b])
    rep.data("power", "v3v3_total_mA", round(t3, 3))
    rep.data("power", "v5_rows_mA", [(a, round(b, 3)) for a, b in rows5 if b])
    rep.data("power", "v5_total_mA", round(t5, 3))
    rep.check("power", "no_unmodelled_load_on_rails", not unk3 and not unk5, unk3 + unk5)
    rep.check("power", "v5_budget_le_30mA", t5 <= ui_calcs.V5_BUDGET_MA, round(t5, 3))
    rep.check("power", "v3v3_total_le_controller_allocation_460mA", t3 <= ui_calcs.OLED_MA + ui_calcs.UI_ALLOC_MA, round(t3, 3))
    rep.check("power", "v3v3_without_oled_le_120mA", t3 - ui_calcs.OLED_MA <= ui_calcs.UI_ALLOC_MA, round(t3 - ui_calcs.OLED_MA, 3))
    cal = calcs["sections"]["power_budget"]["v3v3_total_mA"]
    rep.check("power", "netlist_total_within_5pct_of_calcs", abs(t3 - cal) <= 0.05 * cal, (round(t3, 3), cal))
    h = calcs["sections"]["v3v3_at_load"]
    for k, ok in h["checks"].items():
        rep.check("power", f"rail_{k}", ok)
    # the OLED is powered from 3V3 with the factory jumpers: pins 3, 15, 18 open
    rep.data("power", "oled_supply", calcs["sections"]["oled_supply_options"]["answer"])


def check_esd(rep: Report, n: Net) -> None:
    nl = n.nl
    ext = {f"{p}.{pin}": n.net(p, pin) for p, pin in (("sw_start", "1"), ("sw_stop", "1"), ("sw_back", "1"),
                                                      ("j_enc", "3"), ("j_enc", "4"), ("j_enc", "5"))}
    bad = {k: v for k, v in ext.items() if not any(nl.mpn.get(r) == "SRV05-4" and p in ("1", "3", "4", "6") for r, p in n.nodes(v or ""))}
    rep.check("esd", "every_external_facing_line_has_srv05_clamp", not bad, bad)
    # series resistance between each external line and its first active input
    for name, (path, pin) in {"btn_start": ("sw_start", "1"), "btn_stop": ("sw_stop", "1"), "btn_back": ("sw_back", "1"),
                              "enc_sw": ("j_enc", "3")}.items():
        net = n.net(path, pin)
        series = [r for r, p in n.passives(net, "R") if n.other(r, p) not in RAILS and n.value(r) and n.value(r) >= 1e3]
        rep.check("esd", f"{name}_series_ge_1k_to_expander", bool(series), [(r, n.value(r)) for r in series])
    for ch in ("A", "B"):
        net = n.net("j_enc", "5" if ch == "A" else "4")
        series = [r for r, p in n.passives(net, "R") if n.other(r, p) not in RAILS and (n.value(r) or 0) >= 10e3]
        rep.check("esd", f"enc_{ch.lower()}_series_ge_10k_to_comparator", bool(series), series)
    rep.check("esd", "grayhill_noise_cap_below_1nF", all((n.value(r) or 0) < 1e-9 for r, _ in
              [p for net in (n.net("j_enc", "4"), n.net("j_enc", "5")) for p in n.passives(net, "C")]), None)
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


def check_encoder(rep: Report, n: Net) -> None:
    got = {p: n.net("j_enc", str(p)) for p in range(1, 7)}
    rep.check("encoder", "j2_pin_map_per_grayhill_vg", got == GRAYHILL_J2, {p: (got[p], GRAYHILL_J2[p]) for p in got if got[p] != GRAYHILL_J2[p]})
    # supply through the bead, 10 k pull-ups on A, B and the switch to the encoder rail
    for name, net in (("A", "ENC_A_RAW"), ("B", "ENC_B_RAW"), ("SW", "ENC_SW_RAW")):
        pu = [(r, n.value(r)) for r, p in n.passives(net, "R") if n.other(r, p) == V3E]
        rep.check("encoder", f"enc_{name.lower()}_pullup_10k_to_encoder_rail", len(pu) == 1 and pu[0][1] == 10e3, pu)
    fb = [r for r, m in n.nl.mpn.items() if m == "BLM18PG121SN1D"]
    rep.check("encoder", "encoder_rail_from_3v3_through_bead",
              len(fb) == 1 and {n.pn.get((fb[0], "1")), n.pn.get((fb[0], "2"))} == {V3, V3E}, fb)
    # recompute the comparator thresholds from the netlist values
    vals = {k: n.value(n.ref(p) or "") for k, p in {"rt": "r_ref_top", "rb": "r_ref_bot", "ri_a": "r_in_a", "ri_b": "r_in_b",
                                                    "rh_a": "r_hy_a", "rh_b": "r_hy_b"}.items()}
    if all(vals.values()):
        worst = {"down_margin": 9e9, "up_margin": 9e9, "hyst": 9e9}
        import itertools
        for vs, ts, ch in itertools.product((3.175, 3.425), (-0.01, 0.01), ("a", "b")):
            for off in (-0.006, 0.006):
                up, down = ui_calcs._thresholds(vs, vals["rt"] * (1 + ts), vals["rb"] * (1 - ts), vals["ri_" + ch], vals["rh_" + ch], off)
                worst["down_margin"] = min(worst["down_margin"], down - 1.0)
                worst["up_margin"] = min(worst["up_margin"], 2.0 - up)
                worst["hyst"] = min(worst["hyst"], up - down)
        rep.data("encoder", "comparator_margins_V", {k: round(v, 4) for k, v in worst.items()})
        rep.check("encoder", "comparator_low_margin_ge_0p3V", worst["down_margin"] >= 0.3, round(worst["down_margin"], 4))
        rep.check("encoder", "comparator_high_margin_ge_0p3V", worst["up_margin"] >= 0.3, round(worst["up_margin"], 4))
        rep.check("encoder", "comparator_hysteresis_positive", worst["hyst"] > 0, round(worst["hyst"], 4))
    else:
        rep.check("encoder", "comparator_values_readable", False, vals)
    for k, ok in ui_calcs.encoder_comparator()["checks"].items():
        rep.check("encoder", f"calc_{k}", ok)


def check_tmp(rep: Report, n: Net) -> None:
    rep.check("encoder", "tmp122_sio_on_miso_local_cs_on_gp7_sck_on_bus",
              n.net("u_tmp", "6") == "MISO_LOCAL" and n.net("u_tmp", "5") == n.net("u_exp", "17") and n.net("u_tmp", "4") == "J7_SCK",
              (n.net("u_tmp", "6"), n.net("u_tmp", "5"), n.net("u_tmp", "4")))
    rep.check("encoder", "chip_selects_not_shared", n.net("u_exp", "7") == "J7_CS_EXP_N" and n.net("j_oled", "17") == "J7_CS_OLED_N"
              and n.net("u_exp", "7") != n.net("j_oled", "17"), None)


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
    rep.check("bom", "only_the_panel_buttons_are_off_lcsc", exceptions == ["IPR3PAD2"], exceptions)
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
    check_buzzer(rep, n)
    check_power(rep, n, calcs)
    check_esd(rep, n)
    check_oled(rep, n)
    check_encoder(rep, n)
    check_tmp(rep, n)
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
