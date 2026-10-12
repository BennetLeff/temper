#!/usr/bin/env python3
"""Verify the captured SELV controller against its contracts.

Reads the frozen (or a fresh) atopile netlist + resolved export of this unit
and native-21's frozen netlist snapshot. Checks, each fail-closed:

  sources    ported interlock/thermal blocks equal their sources minus the
             boundary headers; shared library bytes equal the RTD source-04 set
  j4         J4 pin-for-pin against native-21's J4 net names, plus the
             controller-side obligations on each pin
  adc1       the analog channels sit on six distinct ADC1 pads, nothing
             analog on ADC2, no strap/flash/USB/SPI collision, sample budget
  trip       hardware-only path to PERMIT: structural (no MCU/expander pin can
             drive any net in PERMIT's fan-in cone except the reset request and
             RUN_EN, which enters only the PERMIT = latch AND RUN_EN gate)
             and exhaustive logic simulation of the captured gates
  v3v3       current budget of every part on v3v3 on both boards, from
             datasheet maxima, with the regulator, inductor and PS1 limits
  thermal    L3 thermal-sense comparator trips from the netlist values: 64-corner bands (a port of
             the zapote-erc thermal-sense method) against the fan-law / firmware / FET ladder
  blower     L3 blower supply on J10: pin map, FG tach path, PWM-into-FB speed control with a
             full-speed fail-safe, expander switch-off with a run-at-reset default, sizing calcs
  ui         J7 (R33 UI bus): pin map, a GND beside every signal, series R and ESD
             on every line, its own SPI host apart from the RTD / MCP3202 bus
  bom        every resolved MPN is in bom/controller-parts.json with a source
  misc       PWM pull-downs <= 10 kOhm, strap pins safe at reset

Usage:
  python3 tools/verify_controller.py [--build DIR] [--json OUT]
  DIR defaults to frozen/ (the reviewed outputs).
"""
from __future__ import annotations

import argparse
import itertools
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from netlist import Netlist, attach_resolved, parse_value, read_netlist, sha256  # noqa: E402

UNIT = Path(__file__).resolve().parents[1]
ZAPOTE = UNIT.parent
VMAX = 3.465                       # v3v3 contract maximum: every current bound uses it
GND = "selv_gnd"
V3 = "v3v3"
MCU_MPN = "ESP32-S3-WROOM-1U-N8"     # R33: WROOM-1U (U.FL) replaces the WROOM-1 (same pinout)
OPEN = "__open__"                 # the far side of a dangling resistor pin


# ============================================================ part models
# Pin roles: "in" high-impedance input; "out" push-pull output; "od" open
# drain; "vcc"/"gnd" supply; "ext" off-board; anything else is treated as a
# possible current sink (conservative). Supply currents are datasheet maxima
# per device at <= 3.6 V unless noted; "basis" is the citation.
@dataclass
class Model:
    pins: dict[str, str] = field(default_factory=dict)
    supply_ma: float = 0.0
    basis: str = ""
    logic: str | None = None        # gate model used by the trip simulation


def _ic(vcc, gnd, ins=(), outs=(), ods=(), ma=0.0, basis="", logic=None, other=()):
    pins = {str(p): "vcc" for p in vcc}
    pins.update({str(p): "gnd" for p in gnd})
    pins.update({str(p): "in" for p in ins})
    pins.update({str(p): "out" for p in outs})
    pins.update({str(p): "od" for p in ods})
    pins.update({str(p): "other" for p in other})
    return Model(pins, ma, basis, logic)


ESP_IO_PADS = [p for p in range(4, 40) if p not in (1, 2, 3, 40)]
MODELS: dict[str, Model] = {
    MCU_MPN: _ic([2], [1, 40, 41], ins=[3], outs=ESP_IO_PADS, ma=500.0,
                 basis="WROOM-1/-1U DS v1.8 Table 5-2 IVDD >= 0.5 A supply requirement "
                       "(TX peak 355 mA, Table 6-4)"),
    "SRV05-4": Model({"1": "in", "2": "gnd", "3": "in", "4": "in", "5": "vcc", "6": "in"}, 0.001,
                     "MSKSEMI SRV05-4 DS: IR 1 uA max at VRWM 5 V (Vcc pin on v3v3)"),
    "TPS62933FDRLR": _ic([], [4], ins=[1, 2, 8], other=[3, 5, 6, 7]),
    "TPS62933DRLR": _ic([], [4], ins=[1, 2, 8], other=[3, 5, 6, 7]),
    "TPS3703A4330DSERQ1": _ic([2], [5], ins=[1, 6], ods=[4], other=[3], ma=0.007 + 0.0015,
                            basis="SBVS344D: IDD 7 uA; ISENSE 1.5 uA", logic="free:rail_window"),
    "OPA2388IDR": _ic([8], [4], ins=[2, 3, 5, 6], outs=[1, 7], ma=2 * 2.6,
                      basis="SBOS777D 6.5: IQ 2.6 mA/amp max (5.5 V, -40..125 C)"),
    "TLV9062IDR": _ic([8], [4], ins=[2, 3, 5, 6], outs=[1, 7], ma=2 * 0.8,
                      basis="SBOS839N 7.x: IQ 0.8 mA/amp max (5.5 V, -40..125 C)"),
    "TLV9061IDBVR": _ic([5], [2], ins=[3, 4], outs=[1], ma=0.8,
                        basis="SBOS839N 7.x: IQ 0.8 mA/amp max (5.5 V, -40..125 C); DBV pins Table 5-1"),
    "LM4040A25IDBZR": Model({"1": "clamp", "2": "gnd", "3": "gnd"}, 0.0,
                            "SLOS456Q: shunt; current set by r_ref (counted on the resistor)"),
    "ESD5Z3.3T1G": Model({"1": "in", "2": "gnd"}, 0.0001, "onsemi ESD5Z: IR 50 nA at 3.3 V"),
    "TCA9555PWR": _ic([24], [12], ins=[2, 3, 21], ods=[1, 22, 23], outs=list(range(4, 12)) + list(range(13, 21)),
                      ma=1.3 + 0.03, basis="SCPS200E 7.5: ICC standby inputs-low 1.3 mA + operating 30 uA (3.6 V)"),
    "SN74LVC244APWR": _ic([20], [10], ins=[1, 2, 4, 6, 8, 11, 13, 15, 17, 19], outs=[3, 5, 7, 9, 12, 14, 16, 18],
                          ma=0.010, basis="SCAS414AG: ICC 10 uA (-40..85 C)", logic="buf244"),
    "SN74LVC1G14DBVR": _ic([5], [3], ins=[2], outs=[4], other=[1], ma=0.010,
                           basis="SCES218AA: ICC 10 uA", logic="inv:2>4"),
    "SN74LVC1G08DBVR": _ic([5], [3], ins=[1, 2], outs=[4], ma=0.010,
                           basis="SCES217AA: ICC 10 uA", logic="and:1,2>4"),
    "SN74LVC1G32DBVR": _ic([5], [3], ins=[1, 2], outs=[4], ma=0.010,
                           basis="SCES219W: ICC 10 uA", logic="or:1,2>4"),
    "SN74LVC1G38DBVR": _ic([5], [3], ins=[1, 2], ods=[4], ma=0.010,
                           basis="SCES538H: ICC 10 uA", logic="nand_od:1,2>4"),
    "SN74LVC14ADR": _ic([14], [7], ins=[1, 3, 5, 9, 11, 13], outs=[2, 4, 6, 8, 10, 12], ma=0.040,
                        basis="SCAS285AC: ICC 40 uA (-40..125 C)",
                        logic="inv:1>2;inv:3>4;inv:5>6;inv:9>8;inv:11>10;inv:13>12"),
    "74HC30PW,118": _ic([14], [7], ins=[1, 2, 3, 4, 5, 6, 11, 12], outs=[8], other=[9, 10, 13], ma=0.020,
                       basis="Nexperia 74HC30 (C35 swap for CD74HC30PWR, same pin table): ICC 20 uA (-40..85 C, 6 V), the SCHS121E budget", logic="nand:1,2,3,4,5,6,11,12>8"),
    "SN74LVC1G74DCUR": _ic([8], [4], ins=[1, 2, 6, 7], outs=[3, 5], ma=0.010,
                           basis="SCES794G: ICC 10 uA", logic="dff"),
    "TPS3823-33DBVR": _ic([5], [2], ins=[3, 4], outs=[1], ma=0.025,
                          basis="SLVS165O: IDD 25 uA", logic="free:wdt_ok"),
    "TLV3201AIDBVR": _ic([5], [2], ins=[3, 4], outs=[1], ma=0.065,
                         basis="SBOS561C: IQ 65 uA (-40..125 C)", logic="free:comparator"),
    "TLV9031DBVR": _ic([5], [2], ins=[3, 4], outs=[1], ma=0.035,
                       basis="SNOSDA3H: IQ 35 uA (-40..125 C)", logic="free:comparator"),
    "REF2025AIDDCR": _ic([4], [2], ins=[3], outs=[1, 5], ma=0.43,
                         basis="TI REF20xx product page: IQ < 430 uA (family)"),
    "TPS389001DSER": _ic([4], [2], ins=[1, 3], ods=[6], other=[5], ma=0.006,
                         basis="SLVSD65A: IDD 5.8 uA (3.3 V, -40..105 C)", logic="free:rtd_avdd_ok"),
    "MAX31865AAP+": Model({"1": "out", "2": "vcc", "3": "vcc", "4": "out", "5": "in", "6": "in", "7": "other",
                           "8": "other", "9": "gnd", "10": "in", "11": "in", "12": "other", "13": "gnd",
                           "14": "in", "15": "in", "16": "in", "17": "out", "18": "gnd", "19": "gnd",
                           "20": "other"},
                          3.5 + 0.4 + 5.75, "MAX31865 DS: IDD 3.5 mA + 0.4 mA (input > ref) + BIAS IOUT 5.75 mA max"),
    "2N7002": Model({"1": "in", "2": "gnd", "3": "other"}, 0.0, "CJ 2N7002"),
    # follow-up 2026-10-08: tank RMS channel, external ADC
    "AD8436ARQZ-R7": Model({"1": "other", "2": "other", "3": "in", "4": "out", "5": "in", "6": "in", "7": "other",
                         "8": "other", "9": "gnd", "10": "out", "11": "gnd", "12": "other", "13": "in",
                         "14": "in", "15": "out", "16": "vcc", "17": "vcc", "18": "vcc", "19": "other",
                         "20": "other"}, 0.0,
                        "AD8436 Rev. B Table 1: 365 + 200 + 70 uA max, all on v15_selv (not v3v3)"),
    "MCP3202-CI/SN": _ic([8], [4], ins=[1, 2, 3, 5, 7], outs=[6], ma=0.55,
                         basis="DS21034F: IDD 550 uA max (5 V, worst case used at 3.3 V)"),
    "TLV76050DBZR": Model({"1": "out", "2": "other", "3": "gnd"}, 0.0, "TLV760: on v15_selv, not v3v3"),
    "BAT54S-7-F": Model({"1": "other", "2": "other", "3": "other"}, 0.002,
                        "DS11005: IR 2 uA max (25 V); conducts into v3v3 only on a fault"),
    # native-21 parts on its v3v3 net (pins used: supply only; others conservative)
    "UCC21550BDWKR": _ic([3, 8], [4], ins=[1, 2], ma=4.8, basis="SLUSE89C 6.6: IVCCI 4.8 mA max (VIN=VCC)"),
    "AMC1311BDWVR": _ic([8], [5], ma=7.2, basis="SBAS786C 6.x: IDD2 7.2 mA max (3.0-3.6 V)"),
    "ISO7710DWR": _ic([14], [9, 15], ma=1.2, basis="SLLSER9E 5.12: ICC2 1.2 mA max DC (3.3 V)"),
    "SN74LVC1G332DBVR": _ic([5], [2], ins=[1, 3, 6], outs=[4], ma=0.010, basis="SCES489E: ICC 10 uA"),
    "SN74LVC1G17DBVR": _ic([5], [3], ins=[2], outs=[4], ma=0.010, basis="SCES351Y: ICC 10 uA"),
    "BAS116H,115": Model({"1": "other", "2": "other"}, 0.0, "clamp diode; conducts only into v3v3"),
    "AO3400A": Model({"1": "in", "2": "gnd", "3": "other"}, 0.0, "MOSFET gate is high impedance"),
}
SHORT_MPNS = {"BLM18AG121SN1D"}          # ferrite: DC pass-through
UCC_IN_PULLDOWN_MIN = 50e3              # SLUSE89C 6.6 RINxD 50 kOhm min


def is_short(nl: Netlist, ref: str) -> bool:
    if nl.mpn.get(ref, "") in SHORT_MPNS:
        return True
    if ref.startswith("R"):
        val, _ = parse_value(nl.value.get(ref))
        return val is not None and val == 0.0
    return False


def r_min(nl: Netlist, ref: str) -> float:
    val, tol = parse_value(nl.value.get(ref))
    if val is None:
        # native-21 resolved values may be bare numbers; fall back to the MPN code
        raise ValueError(f"{ref}: no parseable value ({nl.value.get(ref)!r})")
    return val * (1 - (tol or 0.05))


def pin_role(nl: Netlist, ref: str, pin: str) -> str:
    if ref.startswith(("R", "C", "L", "FB")) or nl.mpn.get(ref, "") in SHORT_MPNS:
        return "passive"
    if ref.startswith("J"):
        return "ext"
    model = MODELS.get(nl.mpn.get(ref, ""))
    if model is None:
        return "other"
    return model.pins.get(str(pin), "other")


class Merged:
    """Nets joined through 0-ohm links and ferrites (DC view)."""

    def __init__(self, nl: Netlist):
        self.nl = nl
        parent = {n: n for n in nl.nets}

        def find(x):
            if x not in parent:
                return x
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        pn = nl.pin_net()
        for ref in nl.refs:
            if is_short(nl, ref):
                a, b = pn.get((ref, "1")), pn.get((ref, "2"))
                if a and b:
                    parent[find(a)] = find(b)
        self.find = find
        self.groups: dict[str, set[str]] = {}
        for n in nl.nets:
            self.groups.setdefault(find(n), set()).add(n)

    def nodes(self, net: str) -> list[tuple[str, str]]:
        return [node for n in self.groups.get(self.find(net), ()) for node in self.nl.nets[n]]

    def same(self, a: str, b: str) -> bool:
        return self.find(a) == self.find(b)


def r_to_gnd(m: Merged, net: str, exclude: str, seen: frozenset, clamps: dict) -> float:
    """Minimum DC resistance from ``net`` to ground (0 if anything can sink)."""
    nl = m.nl
    if m.same(net, GND):
        return 0.0
    if m.find(net) in clamps:
        return 0.0
    pn = nl.pin_net()
    paths = []
    for ref, pin in m.nodes(net):
        if ref == exclude or is_short(nl, ref):
            continue
        role = pin_role(nl, ref, pin)
        if role in ("in", "passive") and not ref.startswith("R"):
            continue                      # capacitor or high-Z input
        if role == "in":
            continue
        if ref.startswith("R"):
            other = pn.get((ref, "2" if pin == "1" else "1"), OPEN)
            if m.same(other, V3) or m.find(other) in seen:
                continue
            paths.append(r_min(nl, ref) + r_to_gnd(m, other, ref, seen | {m.find(net)}, clamps))
            continue
        return 0.0                        # output, open drain, ext, other: may sink
    conductance = sum(1.0 / p for p in paths)       # every p >= r_min > 0; inf -> 0
    return float("inf") if conductance == 0 else 1.0 / conductance


def v3v3_load(nl: Netlist, label: str, clamps: dict) -> tuple[list[dict], float]:
    m = Merged(nl)
    pn = nl.pin_net()
    rows: list[dict] = []
    seen_dev: set[str] = set()
    unmodelled = []
    for ref, pin in m.nodes(V3):
        if is_short(nl, ref):
            continue
        mpn = nl.mpn.get(ref, "")
        if ref.startswith("C") or ref.startswith("J") or ref.startswith("L"):
            continue
        if ref.startswith("R"):
            other = pn.get((ref, "2" if pin == "1" else "1"), OPEN)
            if m.same(other, V3):
                continue
            rg = r_to_gnd(m, other, ref, frozenset({m.find(V3)}), clamps)
            if m.find(other) in clamps:
                i = (VMAX - clamps[m.find(other)]) / r_min(nl, ref)
                how = f"to clamp {clamps[m.find(other)]} V"
            elif rg == float("inf"):
                i, how = 0.0, "no DC return"
            else:
                i, how = VMAX / (r_min(nl, ref) + rg), f"R + {rg:.0f} ohm to gnd"
            rows.append({"board": label, "ref": ref, "path": nl.refs[ref], "mA": i * 1e3,
                         "basis": f"{nl.value.get(ref)} {how}"})
            continue
        model = MODELS.get(mpn)
        if model is None:
            unmodelled.append(f"{ref} {mpn}")
            continue
        if ref in seen_dev:
            continue
        seen_dev.add(ref)
        rows.append({"board": label, "ref": ref, "path": nl.refs[ref], "mA": model.supply_ma,
                     "basis": f"{mpn}: {model.basis}"})
    # Push-pull outputs of v3v3-powered parts driving resistors to ground.
    for net, nodes in nl.nets.items():
        drivers = [(r, p) for r, p in nodes if pin_role(nl, r, p) == "out"]
        if not drivers or m.same(net, GND) or m.same(net, V3):
            continue
        for ref, pin in nodes:
            if ref.startswith("R") and not is_short(nl, ref):
                other = pn.get((ref, "2" if pin == "1" else "1"), OPEN)
                if m.same(other, GND):
                    rows.append({"board": label, "ref": ref, "path": nl.refs[ref],
                                 "mA": VMAX / r_min(nl, ref) * 1e3,
                                 "basis": f"{nl.value.get(ref)} pull-down driven high by {drivers[0][0]}"})
    if unmodelled:
        raise ValueError(f"{label}: unmodelled parts on v3v3: {unmodelled}")
    return rows, sum(r["mA"] for r in rows)


# ============================================================ checks
class Report:
    def __init__(self):
        self.sections: dict[str, dict] = {}

    def check(self, section: str, name: str, ok: bool, detail=None):
        sec = self.sections.setdefault(section, {"checks": {}, "data": {}})
        sec["checks"][name] = {"ok": bool(ok), "detail": detail}

    def data(self, section: str, key: str, value):
        self.sections.setdefault(section, {"checks": {}, "data": {}})["data"][key] = value

    @property
    def failed(self):
        return [f"{s}.{n}" for s, v in self.sections.items() for n, c in v["checks"].items() if not c["ok"]]


def check_sources(rep: Report):
    proc = subprocess.run([sys.executable, str(UNIT / "tools/port_blocks.py"), "--check"],
                          capture_output=True, text=True)
    rep.check("sources", "ported_blocks_equal_source_minus_boundary", proc.returncode == 0, proc.stdout.strip())
    contract = json.loads((ZAPOTE / "rtd/circuit/rtd_contract.json").read_text())
    want = contract["authoritative_input"]["files"]
    for name in ("modules.ato", "components.ato", "footprints.ato"):
        got = sha256(UNIT / "elec/src" / name)
        rep.check("sources", f"library_{name}_equals_rtd_source04", got == want[f"elec/src/{name}"], got)


MODULE_PAD_GPIO = {4: 4, 5: 5, 6: 6, 7: 7, 8: 15, 9: 16, 10: 17, 11: 18, 12: 8, 13: 19, 14: 20, 15: 3,
                   16: 46, 17: 9, 18: 10, 19: 11, 20: 12, 21: 13, 22: 14, 23: 21, 24: 47, 25: 48, 26: 45,
                   27: 0, 28: 35, 29: 36, 30: 37, 31: 38, 32: 39, 33: 40, 34: 41, 35: 42, 36: 44, 37: 43,
                   38: 2, 39: 1}       # ESP32-S3-WROOM-1/-1U DS v1.8 Table 3-1
ADC1_GPIO = set(range(1, 11))          # ADC1_CH0..CH9
ADC2_GPIO = set(range(11, 21))
STRAPS = {0, 3, 45, 46}


def gpio_map(nl: Netlist) -> dict[int, str]:
    mcu = [r for r, mpn in nl.mpn.items() if mpn == MCU_MPN]
    if len(mcu) != 1:
        raise ValueError(f"expected one ESP32 module, found {mcu}")
    return {g: nl.net_of(mcu[0], str(pad)) for pad, g in MODULE_PAD_GPIO.items()}


def check_j4(rep: Report, nl: Netlist, n21: Netlist):
    mine = {p: nl.net_of("J4", str(p)) for p in range(1, 17)}
    theirs = {p: n21.net_of("J4", str(p)) for p in range(1, 17)}
    rep.data("j4", "controller", mine)
    rep.data("j4", "native21", theirs)
    # Both ends are Micro-Fit 3.0 2x8 headers (43045-16xx) mated by a 1:1 43025-1600
    # harness; R27 makes the controller end right-angle (mating +X).
    family = {"0430451600", "0430451612"}
    rep.check("j4", "micro_fit_2x8_both_ends", nl.mpn["J4"] in family and n21.mpn["J4"] in family,
              (nl.mpn["J4"], n21.mpn["J4"]))
    rep.check("j4", "controller_j4_right_angle_r27", "Horizontal" in nl.footprint.get("J4", ""),
              nl.footprint.get("J4"))
    for p in range(1, 17):
        rep.check("j4", f"pin{p}_{theirs[p]}", mine[p] == theirs[p] and mine[p] is not None, (mine[p], theirs[p]))
    pn = nl.pin_net()
    m = Merged(nl)
    gm = gpio_map(nl)
    # Obligations
    reg = [r for r, mp in nl.mpn.items() if mp == "TPS62933FDRLR"]
    rep.check("j4", "pin3_v3v3_is_regulator_output",
              any(nl.net_of(l, "2") == V3 for l in nl.refs if nl.mpn.get(l) == "SWPA6045S100MT") and len(reg) == 1)
    # Stage 16 (DECISIONS C33): J4.1 (PS1) feeds the 3.3 V buck only; the blower buck runs from
    # PS3 through J13 (check_blwin).
    on_v15 = {nl.mpn[r] for r, p in nl.nets["v15_selv"] if pin_role(nl, r, p) == "other"}
    rep.check("j4", "pin1_feeds_3v3_buck_only",
              "TPS62933FDRLR" in on_v15 and "TPS62933DRLR" not in on_v15, sorted(on_v15 & {"TPS62933FDRLR", "TPS62933DRLR"}))
    for net in ("pwm_ha", "pwm_la", "pwm_hb", "pwm_lb"):
        pulls = [r for r, p in nl.nets[net] if r.startswith("R")
                 and pn.get((r, "2" if p == "1" else "1"), OPEN) == GND]
        rmax = [parse_value(nl.value[r])[0] * (1 + parse_value(nl.value[r])[1]) for r in pulls]
        rep.check("j4", f"{net}_pulldown_le_10k", bool(rmax) and min(rmax) <= 10e3 * 1.0101, rmax)
        series = [r for r, p in nl.nets[net] if r.startswith("R") and r not in pulls]
        src = {pn.get((r, "2" if p == "1" else "1"), OPEN) for r, p in nl.nets[net] if r in series}
        rep.check("j4", f"{net}_driven_by_mcu_gpio", any(s in gm.values() for s in src), sorted(src))
    # PERMIT = latch Q AND RUN_EN (COMMISSIONING.md H1): one driver, the AND gate, whose two inputs
    # are the interlock latch Q and the firmware RUN_EN line
    drivers = [(r, p, nl.mpn[r]) for r, p in nl.nets["permit"] if pin_role(nl, r, p) in ("out", "od")]
    gate_ok = len(drivers) == 1 and drivers[0][2] == "SN74LVC1G08DBVR" and drivers[0][1] == "4"
    gate_in = {}
    if gate_ok:
        g = drivers[0][0]
        gate_in = {nl.net_of(g, "1"), nl.net_of(g, "2")}
        latch_q = {nl.net_of(r, p) for r, p in [(r, "5") for r, mp in nl.mpn.items() if mp == "SN74LVC1G74DCUR"]}
        gate_ok = gate_in == latch_q | {"RUN_EN"} and len(latch_q) == 1
        q_drivers = [(r, p) for n in latch_q for r, p in nl.nets[n] if pin_role(nl, r, p) in ("out", "od")]
        gate_ok = gate_ok and len(q_drivers) == 1
    rep.check("j4", "pin9_permit_is_latch_and_run_en_gate", gate_ok, {"drivers": drivers, "gate_inputs": sorted(gate_in)})
    il_pull = [r for r, p in nl.nets["bus_fault"] if nl.refs[r].startswith("interlock.ocp_pullup")]
    lat = [r for r, p in nl.nets["bus_fault"] if nl.mpn[r] == "SN74LVC14ADR"]
    rep.check("j4", "pin10_bus_fault_into_interlock_ocp_with_pullup", bool(il_pull) and bool(lat))
    rx = {nl.mpn[r] for r, p in nl.nets["vbus_p"] + nl.nets["vbus_n"]}
    rep.check("j4", "pins11_12_into_d11_receiver_resistors",
              rx == {nl.mpn["J4"], "RT0603BRD0720KL"}, sorted(rx))
    ct = [(r, p, nl.mpn[r]) for r, p in nl.nets["ct_mon"] if r != "J4"]
    buf_in = [x for x in ct if pin_role(nl, x[0], x[1]) == "in"]
    loads = [r for r, p, _ in ct if r.startswith("R")]
    rmin_load = min(r_min(nl, r) for r in loads) if loads else float("inf")
    rep.check("j4", "pin14_ct_mon_buffered_load_ge_1Mohm", len(buf_in) == 1 and rmin_load >= 1e6,
              {"buffer_inputs": buf_in, "dc_load_min_ohm": rmin_load})
    for net, gpio in (("ct_zc", 38), ("line_zc", 39)):
        series = [r for r, p in nl.nets[net] if r.startswith("R")]
        far = {pn.get((r, "2" if p == "1" else "1"), OPEN) for r, p in nl.nets[net] if r in series}
        rep.check("j4", f"{net}_to_gpio{gpio}", gm[gpio] in far, sorted(far))
    rep.check("j4", "returns_2_4_15_on_selv_gnd", all(mine[p] == GND for p in (2, 4, 15)))


def check_adc1(rep: Report, nl: Netlist, calcs: dict):
    gm = gpio_map(nl)
    analog = {"VBUS_ADC": "OPA2388IDR", "CT_MON_ADC": "TLV9062IDR", "HS_ADC": "TLV9062IDR",
              "COIL_ADC": "TLV9062IDR", "M12_ADC": "TLV9062IDR", "RIM_ADC": "TLV9061IDBVR"}
    pn = nl.pin_net()
    where = {}
    for net, amp in analog.items():
        gpios = [g for g, n in gm.items() if n == net]
        where[net] = gpios
        rep.check("adc1", f"{net}_on_one_adc1_gpio", len(gpios) == 1 and gpios[0] in ADC1_GPIO, gpios)
        rs = [r for r, p in nl.nets.get(net, []) if r.startswith("R")]
        src = [pn.get((r, "2" if p == "1" else "1"), OPEN) for r, p in nl.nets.get(net, []) if r in rs]
        ok = any(nl.mpn[r2] == amp and pin_role(nl, r2, p2) == "out" for s in src for r2, p2 in nl.nets.get(s, []))
        rep.check("adc1", f"{net}_driven_by_{amp}_buffer", ok, src)
    # L3 (R32 / study 06, DECISIONS C29): every NTC channel's buffer input is a series-R /
    # shunt-C node with a corner <= 1 kHz, independent of the NTC's resistance
    import math
    for net in ("HS_ADC", "COIL_ADC", "M12_ADC", "RIM_ADC"):
        rs = [r for r, p in nl.nets.get(net, []) if r.startswith("R")]
        src = [pn.get((r, "2" if p == "1" else "1"), OPEN) for r, p in nl.nets.get(net, []) if r in rs]
        amp = [(r2, p2) for s_ in src for r2, p2 in nl.nets.get(s_, []) if pin_role(nl, r2, p2) == "out"]
        f = None
        detail = {"buffer_out": src}
        if amp:
            r_amp, p_out = amp[0]
            ins = [p for p, role in MODELS[nl.mpn[r_amp]].pins.items() if role == "in"]
            # the non-inverting input is the one not tied to this output
            inp = [nl.net_of(r_amp, p) for p in ins if nl.net_of(r_amp, p) not in (src[0],)
                   and abs(int(p) - int(p_out)) <= 3]
            for n_in in inp:
                caps = [r for r, p in nl.nets.get(n_in, []) if r.startswith("C")
                        and pn.get((r, "2" if p == "1" else "1")) == GND]
                ser = [r for r, p in nl.nets.get(n_in, []) if r.startswith("R")
                       and pn.get((r, "2" if p == "1" else "1")) not in (V3, GND)]
                if caps and len(ser) == 1:
                    rv = parse_value(nl.value[ser[0]])[0]
                    cv = sum(parse_value(nl.value[c])[0] for c in caps)
                    f = 1 / (2 * math.pi * rv * cv)
                    detail.update({"input": n_in, "R": ser[0], "C": caps, "f_Hz": round(f, 1)})
        rep.check("adc1", f"{net}_input_rc_le_1kHz", f is not None and f <= 1000.0, detail)
    used = [g[0] for g in where.values() if g]
    rep.check("adc1", "six_distinct_channels", len(set(used)) == len(analog), sorted(used))
    for g in sorted(ADC1_GPIO):
        rep.data("adc1", f"GPIO{g}", gm.get(g))
    spare = [g for g in ADC1_GPIO if g not in used and g not in STRAPS]
    rep.data("adc1", "adc1_pins_not_analog", {g: gm[g] for g in sorted(spare)})
    rep.check("adc1", "no_analog_on_adc2", not any(gm[g] in analog for g in ADC2_GPIO))
    rep.check("adc1", "no_analog_on_strap", not any(gm[g] in analog for g in STRAPS))
    rtd = {10: "RTD_CS_N", 11: "RTD_SCK", 12: "RTD_SDO", 13: "RTD_SDI"}
    rep.check("adc1", "spi_10_13_to_rtd_front_end", all(gm[g] == n for g, n in rtd.items()),
              {g: gm[g] for g in rtd})
    pat = calcs["adc_pattern"]
    names = {"VBUS": "VBUS_ADC", "CT_MON": "CT_MON_ADC", "HS": "HS_ADC", "COIL": "COIL_ADC", "M12": "M12_ADC",
             "RIM": "RIM_ADC"}
    rep.check("adc1", "sample_pattern_covers_every_channel",
              {names[c] for c in pat["pattern"]} == set(analog))
    for k, ok in pat["checks"].items():
        rep.check("adc1", f"budget_{k}", ok, pat["rates_sps"])


# ------------------------------------------------------------ trip path
def check_source_wiring(rep: Report, nl: Netlist, calcs: dict | None) -> None:
    """The simulation treats comparators/supervisors as free variables, so
    their input wiring (polarity, what they observe) is checked here. Sources
    inside the ported blocks are covered by the port byte-equality check."""
    pn = nl.pin_net()

    def ends(ref):
        return {pn.get((ref, "1"), OPEN), pn.get((ref, "2"), OPEN)}
    comp = nl.ref_of("u_runaway")
    adc = nl.ref_of("rtd_pan.adc")
    inp, inn = nl.net_of(comp, "3"), nl.net_of(comp, "4")
    rtdin_p, bias = nl.net_of(adc, "10"), nl.net_of(adc, "4")
    win = nl.ref_of("rtd_pan.r_window_sense_p")
    top, bot = nl.ref_of("r_runaway_top"), nl.ref_of("r_runaway_bot")
    rep.check("trip", "runaway_inp_observes_rtdin_plus_via_window_branch", ends(win) == {rtdin_p, inp},
              {"inp": inp, "window_branch": sorted(ends(win))})
    rep.check("trip", "runaway_inn_is_bias_divider", ends(top) == {bias, inn} and ends(bot) == {inn, GND},
              {"inn": inn, "top": sorted(ends(top)), "bot": sorted(ends(bot))})
    rt, rb = parse_value(nl.value[top])[0], parse_value(nl.value[bot])[0]
    if calcs is not None:
        rep.check("trip", "runaway_ratio_matches_calcs", abs(rb / (rt + rb) - calcs["runaway"]["k_nominal"]) < 1e-9,
                  rb / (rt + rb))
    sup = nl.ref_of("u_rail")
    sense = nl.net_of(sup, "1")
    feed = [r for r, p in nl.nets.get(sense, []) if r.startswith("R")
            and pn.get((r, "2" if p == "1" else "1")) == V3 and parse_value(nl.value[r])[0] <= 1e3]
    rep.check("trip", "rail_supervisor_senses_v3v3", bool(feed) and nl.net_of(sup, "2") == V3, feed)
    wd = nl.ref_of("interlock.watchdog")
    rep.check("trip", "watchdog_wdi_is_mcu_heartbeat", nl.net_of(wd, "4") == "IL_WDI", nl.net_of(wd, "4"))


def check_trip(rep: Report, nl: Netlist, calcs: dict | None = None) -> None:
    check_source_wiring(rep, nl, calcs)
    from trip_sim import HEALTHY_LEVEL, Sim, build_logic, exhaustive, fan_in_cone
    m = Merged(nl)
    f = m.find
    gates, free = build_logic(nl, m, MODELS, {MCU_MPN, "TCA9555PWR"},
                              [("J4", "10", "j4:bus_fault")])
    pull: dict[str, int] = {}
    pn = nl.pin_net()
    for ref in nl.refs:
        if ref.startswith("R") and not is_short(nl, ref):
            a, b = pn.get((ref, "1"), OPEN), pn.get((ref, "2"), OPEN)
            if OPEN in (a, b):
                continue
            a, b = f(a), f(b)
            for x, y in ((a, b), (b, a)):
                if y == f(V3):
                    pull.setdefault(x, 1)
                elif y == f(GND):
                    pull.setdefault(x, 0)
    sim = Sim(gates, free, pull, f(GND), f(V3))
    permit = f("permit")
    latch_q = f("PERMIT_LATCH") if "PERMIT_LATCH" in nl.nets else None
    run_en = f("RUN_EN") if "RUN_EN" in nl.nets else None
    rep.check("trip", "single_latch_drives_permit_gate",
              len(sim.dff) == 1 and sim.dff[0][2][0] == latch_q, [g[3] for g in sim.dff])
    pgate = [g for g in gates if g[0] != "dff" and g[2] == permit]
    rep.check("trip", "permit_gate_is_latch_and_run_en",
              len(pgate) == 1 and pgate[0][0] == "and" and sorted(pgate[0][1]) == sorted([latch_q, run_en]),
              [(g[0], g[3]) for g in pgate])
    cone, by_out = fan_in_cone(gates, permit)
    reset = f("IL_RESET_N")
    fw = sorted(n for n in cone if n in free and free[n].startswith("firmware"))
    rep.data("trip", "fan_in_cone_nets", sorted(cone))
    rep.data("trip", "sources_in_cone", {n: free[n] for n in sorted(cone) if n in free})
    rep.check("trip", "only_firmware_inputs_are_reset_request_and_run_en", fw == sorted([reset, run_en]), fw)
    # RUN_EN enters nothing but the PERMIT gate (it cannot reach the latch or any fault input)
    run_en_loads = [g[3] for g in gates if run_en in g[1]]
    rep.check("trip", "run_en_feeds_only_the_permit_gate", run_en_loads == [pgate[0][3]] if pgate else False,
              run_en_loads)
    # RUN_EN defaults to "not permitted": pull-down to selv_gnd, no pull-up, from a GPIO with no
    # reset pull-up (ESP32-S3 DS Table 2-1, as in check_misc). Low level <= 0.8 V (LVC1G08 VIL at 3.3 V)
    ups = [r for r, p in nl.nets.get("RUN_EN", []) if r.startswith("R") and pn.get((r, "2" if p == "1" else "1")) == V3]
    downs = [r for r, p in nl.nets.get("RUN_EN", []) if r.startswith("R") and pn.get((r, "2" if p == "1" else "1")) == GND]
    rmax = max((parse_value(nl.value[r])[0] * (1 + (parse_value(nl.value[r])[1] or 0)) for r in downs), default=None)
    gm = gpio_map(nl)
    src = [g for g, n in gm.items() if n == "RUN_EN"]
    rep.check("trip", "run_en_defaults_low_with_pulldown",
              bool(downs) and not ups and rmax is not None and rmax <= 10e3 and len(src) == 1
              and src[0] not in {0, 20, 39, 43, 44} | STRAPS,
              {"pulldowns": downs, "pullups": ups, "rmax_ohm": rmax, "gpio": src})
    undriven = sorted(n for n in cone if n not in by_out and n not in free and n not in pull
                      and n not in (f(GND), f(V3)))
    rep.check("trip", "every_cone_net_driven_or_pulled", not undriven, undriven)
    pd = [r for r, p in nl.nets["permit"] if r.startswith("R") and pn.get((r, "2" if p == "1" else "1"), OPEN) == GND]
    rep.check("trip", "permit_has_pulldown_at_controller", bool(pd), pd)
    bad = [(n, r, p) for n in cone - {reset, run_en, f(GND), f(V3)} for r, p in m.nodes(n)
           if nl.mpn.get(r) in (MCU_MPN, "TCA9555PWR")]
    rep.check("trip", "no_mcu_or_expander_pin_in_cone_except_reset_and_run_en", not bad, bad)
    sources = sorted(n for n in cone if n in free and n not in (reset, run_en))
    unknown = [free[n] for n in sources if free[n] not in HEALTHY_LEVEL]
    rep.check("trip", "every_source_has_a_specified_healthy_level", not unknown, unknown)
    missing = sorted(set(HEALTHY_LEVEL) - {free[n] for n in sources})
    rep.check("trip", "every_specified_source_reaches_permit", not missing, missing)
    if unknown or len(sim.dff) != 1:
        return
    healthy = {n: HEALTHY_LEVEL[free[n]][0] for n in sources}
    violations, missed, unheld, grants = exhaustive(sim, sources, reset, healthy, permit, run_en)
    rep.data("trip", "enumerated_cases", 2 ** len(sources) * 8 * 2)
    rep.check("trip", "any_trip_source_forces_permit_low_for_every_firmware_state",
              not violations, violations[:3])
    rep.check("trip", "all_healthy_plus_fresh_reset_edge_and_run_en_grants_permit", not missed, missed[:3])
    rep.check("trip", "all_healthy_without_edge_holds_state", unheld == 0, unheld)
    rep.check("trip", "run_en_alone_cannot_assert_permit", not grants, grants[:3])
    rows = []
    for n in sources:
        a = dict(healthy)
        a[n] = 1 - a[n]
        res = {}
        for r_prev, r_now in ((1, 1), (0, 0), (1, 0), (0, 1)):
            val, q = sim.step({**a, run_en: 1}, reset, r_prev, r_now, 1)
            res[f"RESET_N {r_prev}->{r_now}"] = {"PERMIT": val.get(permit), "LATCHED_FAULT": 1 - q}
        rows.append({"source": free[n], "fault_level": a[n], "from_PERMIT_high": res,
                     "basis": HEALTHY_LEVEL[free[n]][1]})
    rep.data("trip", "single_fault_rows", rows)
    rep.data("trip", "healthy_levels", {free[n]: healthy[n] for n in sources})


def check_v3v3(rep: Report, nl: Netlist, n21: Netlist, calcs: dict):
    m = Merged(nl)
    clamps = {m.find("ref2v5") if "ref2v5" in nl.nets else m.find(nl.net_of(
        next(r for r, mp in nl.mpn.items() if mp == "LM4040A25IDBZR"), "1")): 2.5 * 0.999}
    mine, mine_total = v3v3_load(nl, "controller", clamps)
    theirs, theirs_total = v3v3_load(n21, "native21", {})
    # Cross-board: controller-driven J4 lines into native-21 loads.
    cross = []
    for net in ("pwm_ha", "pwm_la", "pwm_hb", "pwm_lb"):
        for ref, pin in n21.nets[net]:
            if n21.mpn.get(ref) == "UCC21550BDWKR":
                cross.append({"board": "native21<-controller", "ref": ref, "path": f"{net} INx pull-down",
                              "mA": VMAX / UCC_IN_PULLDOWN_MIN * 1e3, "basis": "SLUSE89C RINxD 50 kOhm min"})
    nm = Merged(n21)
    for ref, pin in n21.nets["permit"]:
        if ref.startswith("R"):
            other = n21.pin_net()[(ref, "2" if pin == "1" else "1")]
            rg = r_to_gnd(nm, other, ref, frozenset({nm.find("permit")}), {})
            cross.append({"board": "native21<-controller", "ref": ref, "path": "permit gate network",
                          "mA": VMAX / (r_min(n21, ref) + rg) * 1e3, "basis": f"R + {rg:.0f} ohm to gnd"})
    cross_total = sum(r["mA"] for r in cross)
    total = mine_total + theirs_total + cross_total
    rep.data("v3v3", "rows", sorted(mine + theirs + cross, key=lambda r: -r["mA"]))
    rep.data("v3v3", "controller_mA", mine_total)
    rep.data("v3v3", "native21_on_J4_3_mA", theirs_total + cross_total)
    rep.data("v3v3", "total_mA", total)
    oled_ma = 340.0
    total_with_oled = total + oled_ma
    rep.data("v3v3", "oled_off_board_mA", {"mA": oled_ma, "basis": "Newhaven NHD-3.12-25664UCW2 rev: "
                                           "IDD 340 mA max, 3.3 V, 100 % on, factory jumper (via J7.2, R33)"})
    ui_ma = 30.0 + 90.0
    rep.data("v3v3", "ui_board_allocation_mA", {"mA": ui_ma, "basis": "[UNVERIFIED] J7.2 allocation for the R33 "
                                                "UI board: 30 mA logic + 3.3 V encoder option (MCP23S08, TMP122) "
                                                "and 90 mA for the self-oscillating buzzer; parts not yet chosen"})
    peak = total_with_oled + ui_ma
    rep.data("v3v3", "peak_mA", peak)
    rep.check("v3v3", "within_tps62933_3A", peak <= 3000.0, peak)
    rep.check("v3v3", "within_inductor_irms_2p45A", peak <= 2450.0, peak)
    # PS1 (IRM-20-15, 21 W) at the controller; efficiencies are allocations.
    p3 = 3.465 * peak / 1e3 / 0.85
    blower = calcs["blower_supply"]["ps1_blower_input_W"]
    pfan = blower["r32_cap"]                 # R32: drive cap 0.8 (about 9 W) except in a fault
    # Loads straight on v15_selv: AD8436 (365 + 200 + 70 uA max) and the J7 +5 V
    # (TLV760 IGND 5 mA max + 30 mA UI allocation), counted as worst case even though
    # the UI allocation also sits in the v3v3 peak.
    p15 = 15.375 * (0.000635 + 0.005 + 0.030)
    # Stage 16 (DECISIONS C33): the blower buck is on PS3 (V15_BLW), so PS1 carries the logic
    # only, whatever the blower speed. pfan stays as data (what PS1 would carry without PS3).
    p_total = p3 + p15
    rep.data("v3v3", "ps1", {"p_3v3_rail_W": p3, "p_v15_direct_W": p15, "p_total_W": p_total, "rating_W": 21.0,
                             "blower_input_W_now_on_ps3": {"r32_cap": pfan, "full_typ": blower["full_typ"],
                                                            "full_max": blower["full_max"]},
                             "basis": "efficiency 85 % (3.3 V) is an allocation from the TPS62933 typical "
                                      "curves; IRM-20-15 21 W rated; blower on PS3 (check_blwin)"})
    rep.check("v3v3", "ps1_within_21W_at_full_blower", p_total <= 21.0, p_total)
    # J4.3 current and native-21 rail with the harness allocation.
    i_n21 = (theirs_total + cross_total) / 1e3
    i_v15 = p_total / (15 * 0.975)
    sys.path.insert(0, str(UNIT / "tools"))
    from controller_calcs import harness  # noqa: E402
    h = harness(i_n21, i_v15)
    reg = calcs["rail_3v3"]["vout_band_0_85C_V"]
    lo = reg[0] - h["v3v3_drop_V"] + h["ground_shift_min_V"]
    hi = reg[1] + h["ground_shift_max_V"]
    rep.data("v3v3", "native21_rail_V", {"min": lo, "max": hi, "harness": h})
    rep.check("v3v3", "native21_rail_inside_3135_3465", lo >= 3.135 and hi <= 3.465, (lo, hi))
    rep.check("v3v3", "j4_pin3_current_le_contact_rating", i_n21 <= 8.5, i_n21)


C0G_MPNS = {"GRM31C5C1H104JA01L", "GRM1885C1H103JA01D", "CL10C102JB8NNNC", "C0603C102J5GACTU"}


def check_ct_rms(rep: Report, nl: Netlist, calcs: dict) -> None:
    """True-RMS channel: ct_mon buffer -> ac coupling -> AD8436 -> gain -> clamp -> MCP3202."""
    pn = nl.pin_net()

    def ends(ref):
        return {pn.get((ref, "1"), OPEN), pn.get((ref, "2"), OPEN)}

    def caps_between(a, b):
        return [r for r in nl.refs if r.startswith("C") and ends(r) == {a, b}]
    rms = [r for r, m in nl.mpn.items() if m == "AD8436ARQZ-R7"]
    adc = [r for r, m in nl.mpn.items() if m == "MCP3202-CI/SN"]
    rep.check("ct_rms", "one_rms_converter_and_one_external_adc", len(rms) == 1 and len(adc) == 1, rms + adc)
    if len(rms) != 1 or len(adc) != 1:
        return
    u, a = rms[0], adc[0]
    net = lambda r, p: nl.net_of(r, str(p))  # noqa: E731
    buf = next(r for r in nl.refs if nl.refs[r] == "u_buf1")
    ct_buf = net(buf, 1)
    rep.check("ct_rms", "raw_ct_mon_buffer_input_is_j4_14", net(buf, 3) == "ct_mon", net(buf, 3))
    rep.check("ct_rms", "rms_input_ac_coupled_from_ct_mon_buffer", bool(caps_between(ct_buf, net(u, 6))),
              (ct_buf, net(u, 6)))
    rep.check("ct_rms", "input_buffer_unity", net(u, 4) == net(u, 5))
    rep.check("ct_rms", "core_input_ac_coupled", bool(caps_between(net(u, 4), net(u, 3))))
    supplies = {net(u, p) for p in (16, 17, 18)}
    rep.check("ct_rms", "single_supply_v15_vee_gnd", supplies == {"v15_selv"} and net(u, 11) == GND
              and net(u, 9) == GND, sorted(supplies))
    cavg = [r for r in nl.refs if r.startswith("C") and net(u, 20) in ends(r)]
    rep.check("ct_rms", "cavg_is_c0g_not_x7r", bool(cavg) and all(nl.mpn[r] in C0G_MPNS for r in cavg),
              [(r, nl.mpn[r]) for r in cavg])
    rep.check("ct_rms", "output_buffer_follows_core_out", net(u, 13) == net(u, 10))
    series = [r for r in nl.refs if r.startswith("R") and net(u, 15) in ends(r)
              and net(a, 2) in ends(r)]
    rep.check("ct_rms", "rms_output_reaches_adc_ch0_through_series_r", bool(series), series)
    clamp = [r for r, m in nl.mpn.items() if m == "BAT54S-7-F" and net(r, 3) == net(a, 2)]
    rep.check("ct_rms", "adc_ch0_clamped_to_v3v3_and_gnd",
              bool(clamp) and net(clamp[0], 1) == GND and net(clamp[0], 2) == V3, clamp)
    lm = next(r for r, m in nl.mpn.items() if m == "LM4040A25IDBZR")
    rep.check("ct_rms", "adc_ch1_is_2v5_reference", net(a, 3) == net(lm, 1), net(a, 3))
    rep.check("ct_rms", "adc_on_rtd_spi_bus", net(a, 7) == "RTD_SCK" and net(a, 5) == "RTD_SDI"
              and any(net(a, 6) in ends(r) and "RTD_SDO" in ends(r) for r in nl.refs if r.startswith("R")))
    gm = gpio_map(nl)
    cs_gpio = [g for g, n in gm.items() if n == net(a, 1)]
    rep.check("ct_rms", "adc_cs_own_gpio_not_rtd_cs", len(cs_gpio) == 1 and net(a, 1) != "RTD_CS_N", cs_gpio)
    rep.check("ct_rms", "adc_cs_pulled_up", any(ends(r) == {net(a, 1), V3} for r in nl.refs if r.startswith("R")))
    rc = calcs["rms_channel"]
    for k, ok in rc["checks"].items():
        rep.check("ct_rms", f"calc_{k}", ok)
    rep.data("ct_rms", "adc_V_at_22A_rms", rc["adc_V_at_22A_rms"])


# R33 J7 UI bus (DECISIONS C26): pin -> net, and each signal's ESP32 GPIO
J7_MAP = {1: "V5_UI", 2: V3, 3: GND, 4: "J7_SCK", 5: GND, 6: "J7_MOSI", 7: "J7_MISO", 8: GND,
          9: "J7_CS_OLED_N", 10: "J7_DC", 11: GND, 12: "J7_CS_EXP_N"}
UI_GPIO = {"J7_SCK": 40, "J7_MOSI": 41, "J7_MISO": 44, "J7_CS_OLED_N": 47, "J7_CS_EXP_N": 48, "J7_DC": 45}
RTD_BUS_GPIO = {10, 11, 12, 13, 42}     # RTD SPI CS/CLK/MISO/MOSI + MCP3202 CS (C2, C19)
UI_SERIES_OHM = (33.0, 100.0)           # coordinator: 33-100 ohm at the controller end


def check_ui_bus(rep: Report, nl: Netlist, calcs: dict | None = None) -> None:
    """J7: the 12-way UI bus to the fascia board. Exact pin map with a GND beside every
    signal; each signal reaches its GPIO through one 33-100 ohm series resistor and is
    clamped by an SRV05-4 at the connector; the bus uses its own GPIOs, disjoint from
    the RTD / MCP3202 SPI bus, and never touches that bus's nets."""
    pn = nl.pin_net()
    m = Merged(nl)
    gm = gpio_map(nl)

    def other(r, p):
        return pn.get((r, "2" if p == "1" else "1"), OPEN)
    rep.check("ui", "j7_is_b12b_xh", nl.mpn.get("J7") == "B12B-XH-A(LF)(SN)", nl.mpn.get("J7"))
    got = {p: nl.net_of("J7", str(p)) for p in range(1, 13)}
    rep.data("ui", "j7_pins", got)
    rep.check("ui", "j7_pin_map", all(got[p] is not None and m.same(got[p], n) for p, n in J7_MAP.items()),
              {p: (got[p], n) for p, n in J7_MAP.items() if got[p] != n})
    gnds = [p for p in got if got[p] and m.same(got[p], GND)]
    rep.check("ui", "j7_at_least_3_gnd", len(gnds) >= 3, gnds)
    sig_pins = [p for p, n in J7_MAP.items() if n in UI_GPIO]
    lonely = [p for p in sig_pins if not any(got.get(q) and m.same(got[q], GND) for q in (p - 1, p + 1))]
    rep.check("ui", "every_j7_signal_beside_a_gnd", not lonely, lonely)
    srv = [r for r, mp in nl.mpn.items() if mp == "SRV05-4"]
    rep.check("ui", "esd_arrays_on_v3v3_and_gnd",
              bool(srv) and all(nl.net_of(r, "5") == V3 and nl.net_of(r, "2") == GND for r in srv), srv)
    ui_nets = set()
    for net, g in UI_GPIO.items():
        nodes = nl.nets.get(net, [])
        series = [(r, p) for r, p in nodes if r.startswith("R") and other(r, p) not in (V3, GND)]
        active = [(r, p) for r, p in nodes if pin_role(nl, r, p) not in ("passive", "ext")
                  and nl.mpn.get(r) != "SRV05-4"]
        val = parse_value(nl.value.get(series[0][0]))[0] if len(series) == 1 else None
        far = other(*series[0]) if len(series) == 1 else None
        ok = (len(series) == 1 and val is not None and UI_SERIES_OHM[0] <= val <= UI_SERIES_OHM[1]
              and far == gm.get(g) and not active)
        rep.check("ui", f"{net}_series_33_100_ohm_to_gpio{g}", ok,
                  {"series": series, "ohm": val, "gpio_net": gm.get(g), "far": far, "direct_active": active})
        rep.check("ui", f"{net}_esd_clamped", any(nl.mpn.get(r) == "SRV05-4" and p in ("1", "3", "4", "6")
                                                  for r, p in nodes), net)
        ui_nets |= {m.find(net)} | ({m.find(far)} if far and far != OPEN else set())
    rtd_nets = {m.find(gm[g]) for g in RTD_BUS_GPIO if gm.get(g)}
    ui_gpio = {g for g, n in gm.items() if n and m.find(n) in ui_nets}
    rep.check("ui", "ui_bus_separate_from_rtd_adc_spi",
              not (ui_nets & rtd_nets) and not (ui_gpio & RTD_BUS_GPIO)
              and sorted(ui_gpio) == sorted(UI_GPIO.values()),
              {"ui_gpio": sorted(ui_gpio), "rtd_gpio": sorted(RTD_BUS_GPIO)})
    rtd_off_board = sorted({(n, r) for n in rtd_nets for r, _ in m.nodes(n) if r.startswith("J") and r != "J11"})
    rep.check("ui", "rtd_adc_spi_stays_on_board", not rtd_off_board, rtd_off_board)
    for net in ("J7_CS_OLED_N", "J7_CS_EXP_N"):
        gnet = gm.get(UI_GPIO[net])
        ups = [r for r, p in nl.nets.get(gnet, []) if r.startswith("R") and other(r, p) == V3]
        rep.check("ui", f"{net}_deselected_at_reset_pullup", bool(ups), ups)
    ldo = [r for r, p in nl.nets.get("V5_UI", []) if nl.mpn.get(r) == "TLV76050DBZR" and p == "1"]
    rep.check("ui", "j7_5v_from_tlv76050", len(ldo) == 1, ldo)
    if calcs is not None and "ui_5v_supply" in calcs:
        for k, ok in calcs["ui_5v_supply"]["checks"].items():
            rep.check("ui", f"ui_5v_{k}", ok)


def check_thermal(rep: Report, nl: Netlist) -> None:
    """L3 (DECISIONS C32): the ported thermal-sense comparators' trip bands, computed from the
    resistor values in this netlist (by instance path), must respect the trip ladder."""
    sys.path.insert(0, str(UNIT / "tools"))
    from controller_calcs import thermal_trips  # noqa: E402
    vals = {}
    for ch in ("hs", "coil"):
        vals[ch] = {}
        for part in ("fixed", "top", "bottom", "hyst"):
            ref = nl.ref_of(f"thermal.{ch}_{part}")
            v, tol = parse_value(nl.value[ref])
            vals[ch][part] = (v, tol or 0.05)
    res = thermal_trips(vals)
    for k, ok in res["checks"].items():
        rep.check("thermal", k, ok)
    rep.data("thermal", "values", {ch: {k: list(x) for k, x in d.items()} for ch, d in vals.items()})
    rep.data("thermal", "hs", res["hs"])
    rep.data("thermal", "coil", res["coil"])
    rep.data("thermal", "tj_at_hs_trip_high_corner_C", res["tj_at_hs_trip_high_corner_C"])


def check_blower(rep: Report, nl: Netlist, calcs: dict) -> None:
    """L3 blower supply (DECISIONS C28): J10 = +V_BLOWER / GND / FG; FG reaches GPIO3 through a
    series R with a pull-up and TVS at the connector; speed is a filtered GPIO46 PWM injected
    into the blower buck's FB (GPIO46 low = full speed, the cooling fail-safe); switch-off is the
    expander's P15 driving the EN FET, with a gate pull-down strong enough to keep the blower on
    while the expander powers up as an input with its 100 k pull-up."""
    pn = nl.pin_net()
    gm = gpio_map(nl)

    def other(r, p):
        return pn.get((r, "2" if p == "1" else "1"), OPEN)
    j10 = {p: nl.net_of("J10", str(p)) for p in (1, 2, 3)}
    rep.check("blower", "j10_pin_map", j10[1] == "V_BLOWER" and j10[2] == GND and j10[3] == "J10_FG", j10)
    fg = nl.nets.get("J10_FG", [])
    pu = [r for r, p in fg if r.startswith("R") and other(r, p) == V3]
    tvs = [r for r, p in fg if nl.mpn.get(r) == "ESD5Z3.3T1G"]
    ser = [(r, other(r, p)) for r, p in fg if r.startswith("R") and other(r, p) not in (V3, GND)]
    rep.check("blower", "fg_pullup_tvs_series_to_gpio3", bool(pu) and bool(tvs) and len(ser) == 1
              and ser[0][1] == gm.get(3), {"pullup": pu, "tvs": tvs, "series": ser, "gpio3": gm.get(3)})
    reg = [r for r, mp in nl.mpn.items() if mp == "TPS62933DRLR"]
    fb = nl.net_of(reg[0], "8") if reg else None      # TPS62933 pin 8 = FB
    pwm = gm.get(46)
    # PWM -> series R -> filter node (C to GND) -> injection R -> FB
    chain = None
    for r, p in nl.nets.get(pwm, []):
        if r.startswith("R") and other(r, p) not in (V3, GND):
            node = other(r, p)
            caps = [c for c, q in nl.nets.get(node, []) if c.startswith("C") and other(c, q) == GND]
            inj = [x for x, q in nl.nets.get(node, []) if x.startswith("R") and x != r and other(x, q) == fb]
            if caps and inj:
                chain = {"filter_R": r, "node": node, "C": caps, "inj_R": inj}
    rep.check("blower", "pwm_gpio46_filtered_into_fb", chain is not None and fb is not None, chain)
    downs = [r for r, p in nl.nets.get(pwm, []) if r.startswith("R") and other(r, p) == GND]
    ups = [r for r, p in nl.nets.get(pwm, []) if r.startswith("R") and other(r, p) == V3]
    rep.check("blower", "gpio46_low_at_reset_is_full_speed", bool(downs) and not ups, {"pulldown": downs})
    en = nl.net_of(reg[0], "2") if reg else None      # TPS62933 pin 2 = EN
    fets = [r for r, p in nl.nets.get(en, []) if nl.mpn.get(r) == "2N7002" and p == "3"]
    gate = nl.net_of(fets[0], "1") if fets else None
    drv = [(r, p) for r, p in nl.nets.get(gate, []) if nl.mpn.get(r) == "TCA9555PWR"]
    gpd = [parse_value(nl.value[r])[0] for r, p in nl.nets.get(gate, []) if r.startswith("R") and other(r, p) == GND]
    # TCA9555 power-up: input with 100 k pull-up (SCPS200E); 2N7002 VGS(th) >= 1.0 V (CJ 2N7002)
    v_gate = 3.465 * min(gpd) / (min(gpd) + 100e3) if gpd else None
    rep.check("blower", "switch_off_from_expander_runs_at_reset", bool(drv) and v_gate is not None and v_gate < 1.0,
              {"fet": fets, "gate": gate, "driver": drv, "gate_V_at_reset": v_gate})
    for k, ok in calcs["blower_supply"]["checks"].items():
        rep.check("blower", f"calc_{k}", ok)
    rep.data("blower", "vout_duty0_V", calcs["blower_supply"]["vout_duty0_V"])
    rep.data("blower", "vout_duty100_V", calcs["blower_supply"]["vout_duty100_V"])


def check_blwin(rep: Report, nl: Netlist, calcs: dict) -> None:
    """Stage 16 (DECISIONS C33): blower buck input from PS3. J13 = V15_BLW / selv_gnd; U2's VIN,
    EN-divider top and input caps on V15_BLW; a 100 uF bulk cap on V15_BLW; nothing joins
    V15_BLW to v15_selv; BLW_PG divider from V15_BLW into expander P16."""
    pn = nl.pin_net()
    BLW = "V15_BLW"

    def ends(r):
        return {pn.get((r, "1"), OPEN), pn.get((r, "2"), OPEN)}
    j13 = {p: nl.net_of("J13", str(p)) for p in (1, 2)}
    rep.check("blwin", "j13_pin_map", j13[1] == BLW and j13[2] == GND and nl.mpn.get("J13") == "B2P-VH(LF)(SN)",
              {"pins": j13, "mpn": nl.mpn.get("J13")})
    reg = [r for r, mp in nl.mpn.items() if mp == "TPS62933DRLR"]
    u2 = reg[0] if len(reg) == 1 else None
    vin = nl.net_of(u2, "3") if u2 else None          # TPS62933 pin 3 = VIN
    en = nl.net_of(u2, "2") if u2 else None           # pin 2 = EN
    en_top = [r for r in nl.refs if r.startswith("R") and ends(r) == {BLW, en}]
    caps_in = [r for r in nl.refs if r.startswith("C") and ends(r) == {BLW, GND}]
    rep.check("blwin", "u2_vin_en_caps_on_v15_blw", vin == BLW and len(en_top) == 1 and len(caps_in) >= 3,
              {"u2_vin": vin, "en_top": en_top, "caps": caps_in})
    parts_blw = {r for r, p in nl.nets.get(BLW, [])}
    parts_v15 = {r for r, p in nl.nets.get("v15_selv", [])}
    bridges = sorted(parts_blw & parts_v15)
    rep.check("blwin", "no_part_bridges_v15_blw_and_v15_selv", not bridges and BLW in nl.nets, bridges)
    bulk = [r for r in nl.refs if nl.mpn.get(r) == "EEE-FK1E101P" and nl.net_of(r, "1") == BLW
            and nl.net_of(r, "2") == GND]
    rep.check("blwin", "bulk_cap_on_v15_blw", len(bulk) == 1, bulk)
    io = [r for r, mp in nl.mpn.items() if mp == "TCA9555PWR"]
    pg = nl.net_of(io[0], "19") if io else None         # TCA9555 pin 19 = P16 (SCPS200E)
    top = [r for r in nl.refs if r.startswith("R") and ends(r) == {BLW, pg}]
    bot = [r for r in nl.refs if r.startswith("R") and ends(r) == {pg, GND}]
    vals = (parse_value(nl.value[top[0]])[0], parse_value(nl.value[bot[0]])[0]) if len(top) == 1 and len(bot) == 1 else None
    rep.check("blwin", "blw_pg_divider_into_p16", pg == "BLW_PG" and vals == (20e3, 4.7e3),
              {"p16": pg, "top": top, "bottom": bot, "values": vals})
    for blk in ("ps3_budget", "blw_pg"):
        for k, ok in calcs[blk]["checks"].items():
            rep.check("blwin", f"calc_{blk}_{k}", ok)
    rep.check("blwin", "ps3_within_rating_at_design_load", calcs["ps3_budget"]["ps3_out_W"] <= 60.0,
              calcs["ps3_budget"]["ps3_out_W"])
    rep.data("blwin", "j13", {"pin1": BLW, "pin2": GND, "part": "JST B2P-VH(LF)(SN)"})
    rep.data("blwin", "ps3_budget", {k: v for k, v in calcs["ps3_budget"].items() if k != "checks"})
    rep.data("blwin", "blw_pg", {k: v for k, v in calcs["blw_pg"].items() if k != "checks"})


def check_bom(rep: Report, nl: Netlist):
    table = json.loads((UNIT / "bom/controller-parts.json").read_text())["parts"]
    mpns = sorted(set(nl.mpn.values()))
    missing = [m for m in mpns if m not in table]
    rep.check("bom", "every_mpn_in_parts_table", not missing, missing)
    nosource = [m for m in mpns if m in table and not table[m].get("basis")]
    rep.check("bom", "every_part_has_a_basis", not nosource, nosource)
    unverified = [m for m in mpns if m in table and "UNVERIFIED" in json.dumps(table[m])]
    rep.data("bom", "unverified", unverified)
    rep.data("bom", "count", {"components": len(nl.refs), "distinct_mpns": len(mpns)})


def check_misc(rep: Report, nl: Netlist):
    gm = gpio_map(nl)
    pn = nl.pin_net()

    def pull_of(net):
        out = []
        for r, p in nl.nets.get(net, []):
            if r.startswith("R"):
                o = pn.get((r, "2" if p == "1" else "1"), OPEN)
                if o in (V3, GND):
                    out.append((o, nl.value[r]))
        return out
    rep.check("misc", "gpio0_pulled_up_for_spi_boot", any(o == V3 for o, _ in pull_of(gm[0])), pull_of(gm[0]))
    for g in (45, 46):
        ups = [o for o, _ in pull_of(gm[g]) if o == V3]
        downs = [o for o, _ in pull_of(gm[g]) if o == GND]
        rep.check("misc", f"gpio{g}_reads_0_at_reset", not ups and bool(downs), pull_of(gm[g]))
    # ESP32-S3 DS v2.2 Table 2-1 "At Reset" column and note 7: weak pull-ups
    # at reset on GPIO0, U0TXD (43), U0RXD (44); MTCK (39) after reset unless
    # EFUSE_DIS_PAD_JTAG; USB_PU on GPIO20. Table 2-2: power-up glitches on the
    # RTC GPIOs are low-level only.
    reset_pullup = {0, 20, 39, 43, 44}
    j4_pwm = {"pwm_ha", "pwm_la", "pwm_hb", "pwm_lb"}
    pwm_gpio = {g for g, n in gm.items()
                if any(pn.get((r, "2" if p == "1" else "1"), OPEN) in j4_pwm
                       for r, p in nl.nets.get(n, []) if r.startswith("R"))}
    rep.check("misc", "pwm_gpios_have_no_reset_pullup", len(pwm_gpio) == 4 and not pwm_gpio & reset_pullup,
              sorted(pwm_gpio))
    rep.check("misc", "usb_19_20_on_debug_header",
              {nl.mpn[r] for r, _ in nl.nets[gm[19]]} >= {"61300811121"})
    rep.data("misc", "gpio_map", {f"GPIO{g}": n for g, n in sorted(gm.items())})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build", type=Path, default=UNIT / "frozen")
    ap.add_argument("--json", type=Path, default=UNIT / "evidence" / "verify.json")
    args = ap.parse_args()
    args.build = args.build.resolve()
    nl = attach_resolved(read_netlist(args.build / "default.net"), args.build / "resolved-components.json")
    n21dir = UNIT / "inputs/native-21"
    prov = json.loads((n21dir / "provenance.json").read_text())
    for name, rec in prov["files"].items():
        if sha256(n21dir / name) != rec["sha256"]:
            raise SystemExit(f"native-21 snapshot {name} does not match provenance")
    n21 = attach_resolved(read_netlist(n21dir / "default.net"), n21dir / "resolved-components.json")
    calc = subprocess.run([sys.executable, str(UNIT / "tools/controller_calcs.py"), "--quiet"],
                          capture_output=True, text=True)
    calcs = json.loads((UNIT / "evidence/controller_calcs.json").read_text())
    rep = Report()
    rep.check("calcs", "controller_calcs_pass", calc.returncode == 0, calcs["failed_checks"])
    check_sources(rep)
    check_j4(rep, nl, n21)
    check_adc1(rep, nl, calcs)
    check_trip(rep, nl, calcs)
    check_v3v3(rep, nl, n21, calcs)
    check_ct_rms(rep, nl, calcs)
    check_ui_bus(rep, nl, calcs)
    check_blower(rep, nl, calcs)
    check_blwin(rep, nl, calcs)
    check_thermal(rep, nl)
    check_bom(rep, nl)
    check_misc(rep, nl)
    out = {"schema": "temper.controller.verify.v1",
           "inputs": {"netlist": str(args.build.relative_to(UNIT) / "default.net"),
                      "netlist_sha256": sha256(args.build / "default.net"),
                      "native21_commit": prov["commit"]},
           "failed": rep.failed, "sections": rep.sections}
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(out, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    for s, v in rep.sections.items():
        n_ok = sum(c["ok"] for c in v["checks"].values())
        print(f"{s:8s} {n_ok}/{len(v['checks'])}")
    print("VERIFY:", "PASS" if not rep.failed else f"FAIL {rep.failed}")
    return 1 if rep.failed else 0


if __name__ == "__main__":
    sys.exit(main())
