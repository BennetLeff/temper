#!/usr/bin/env python3
"""Verify the captured SELV controller against its contracts.

Reads the frozen (or a fresh) atopile netlist + resolved export of this unit
and native-21's frozen netlist snapshot. Checks, each fail-closed:

  sources    ported interlock/thermal blocks equal their sources minus the
             boundary headers; shared library bytes equal the RTD source-04 set
  j4         J4 pin-for-pin against native-21's J4 net names, plus the
             controller-side obligations on each pin
  adc1       the analog channels sit on five distinct ADC1 pads, nothing
             analog on ADC2, no strap/flash/USB/SPI collision, sample budget
  trip       hardware-only path to PERMIT: structural (no MCU/expander pin can
             drive any net in PERMIT's fan-in cone except the reset request)
             and exhaustive logic simulation of the captured gates
  v3v3       current budget of every part on v3v3 on both boards, from
             datasheet maxima, with the regulator, inductor and PS1 limits
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
    "ESP32-S3-WROOM-1-N8": _ic([2], [1, 40, 41], ins=[3], outs=ESP_IO_PADS, ma=500.0,
                               basis="WROOM-1 DS v1.8 Table 5-2 IVDD >= 0.5 A supply requirement "
                                     "(TX peak 355 mA, Table 6-4)"),
    "TPS62933FDRLR": _ic([], [4], ins=[1, 2, 8], other=[3, 5, 6, 7]),
    "TPS62933DRLR": _ic([], [4], ins=[1, 2, 8], other=[3, 5, 6, 7]),
    "TPS3703A4330DSER": _ic([2], [5], ins=[1, 6], ods=[4], other=[3], ma=0.007 + 0.0015,
                            basis="SBVS249B 7.5: IDD 7 uA; ISENSE 1.5 uA", logic="free:rail_window"),
    "OPA2388IDR": _ic([8], [4], ins=[2, 3, 5, 6], outs=[1, 7], ma=2 * 2.6,
                      basis="SBOS777D 6.5: IQ 2.6 mA/amp max (5.5 V, -40..125 C)"),
    "TLV9062IDR": _ic([8], [4], ins=[2, 3, 5, 6], outs=[1, 7], ma=2 * 0.8,
                      basis="SBOS839N 7.x: IQ 0.8 mA/amp max (5.5 V, -40..125 C)"),
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
    "CD74HC30PWR": _ic([14], [7], ins=[1, 2, 3, 4, 5, 6, 11, 12], outs=[8], other=[9, 10, 13], ma=0.020,
                       basis="SCHS121E: ICC 20 uA (-40..85 C, 6 V)", logic="nand:1,2,3,4,5,6,11,12>8"),
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
                   38: 2, 39: 1}       # ESP32-S3-WROOM-1 DS v1.8 Table 3-1
ADC1_GPIO = set(range(1, 11))          # ADC1_CH0..CH9
ADC2_GPIO = set(range(11, 21))
STRAPS = {0, 3, 45, 46}


def gpio_map(nl: Netlist) -> dict[int, str]:
    mcu = [r for r, mpn in nl.mpn.items() if mpn == "ESP32-S3-WROOM-1-N8"]
    if len(mcu) != 1:
        raise ValueError(f"expected one ESP32 module, found {mcu}")
    return {g: nl.net_of(mcu[0], str(pad)) for pad, g in MODULE_PAD_GPIO.items()}


def check_j4(rep: Report, nl: Netlist, n21: Netlist):
    mine = {p: nl.net_of("J4", str(p)) for p in range(1, 17)}
    theirs = {p: n21.net_of("J4", str(p)) for p in range(1, 17)}
    rep.data("j4", "controller", mine)
    rep.data("j4", "native21", theirs)
    rep.check("j4", "same_part", nl.mpn["J4"] == n21.mpn["J4"] == "0430451612", (nl.mpn["J4"], n21.mpn["J4"]))
    for p in range(1, 17):
        rep.check("j4", f"pin{p}_{theirs[p]}", mine[p] == theirs[p] and mine[p] is not None, (mine[p], theirs[p]))
    pn = nl.pin_net()
    m = Merged(nl)
    gm = gpio_map(nl)
    # Obligations
    reg = [r for r, mp in nl.mpn.items() if mp == "TPS62933FDRLR"]
    rep.check("j4", "pin3_v3v3_is_regulator_output",
              any(nl.net_of(l, "2") == V3 for l in nl.refs if nl.mpn.get(l) == "SWPA6045S100MT") and len(reg) == 1)
    rep.check("j4", "pin1_feeds_both_bucks",
              {nl.mpn[r] for r, p in nl.nets["v15_selv"] if pin_role(nl, r, p) == "other"} >=
              {"TPS62933FDRLR", "TPS62933DRLR"})
    for net in ("pwm_ha", "pwm_la", "pwm_hb", "pwm_lb"):
        pulls = [r for r, p in nl.nets[net] if r.startswith("R")
                 and pn.get((r, "2" if p == "1" else "1"), OPEN) == GND]
        rmax = [parse_value(nl.value[r])[0] * (1 + parse_value(nl.value[r])[1]) for r in pulls]
        rep.check("j4", f"{net}_pulldown_le_10k", bool(rmax) and min(rmax) <= 10e3 * 1.0101, rmax)
        series = [r for r, p in nl.nets[net] if r.startswith("R") and r not in pulls]
        src = {pn.get((r, "2" if p == "1" else "1"), OPEN) for r, p in nl.nets[net] if r in series}
        rep.check("j4", f"{net}_driven_by_mcu_gpio", any(s in gm.values() for s in src), sorted(src))
    drivers = [(r, p, nl.mpn[r]) for r, p in nl.nets["permit"] if pin_role(nl, r, p) in ("out", "od")]
    rep.check("j4", "pin9_permit_driven_only_by_interlock_latch",
              len(drivers) == 1 and drivers[0][2] == "SN74LVC1G74DCUR" and drivers[0][1] == "5", drivers)
    il_pull = [r for r, p in nl.nets["bus_fault"] if nl.refs[r].startswith("interlock.ocp_pullup")]
    lat = [r for r, p in nl.nets["bus_fault"] if nl.mpn[r] == "SN74LVC14ADR"]
    rep.check("j4", "pin10_bus_fault_into_interlock_ocp_with_pullup", bool(il_pull) and bool(lat))
    rx = {nl.mpn[r] for r, p in nl.nets["vbus_p"] + nl.nets["vbus_n"]}
    rep.check("j4", "pins11_12_into_d11_receiver_resistors",
              rx == {"0430451612", "RT0603BRD0720KL"}, sorted(rx))
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
              "COIL_ADC": "TLV9062IDR", "M12_ADC": "TLV9062IDR"}
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
    used = [g[0] for g in where.values() if g]
    rep.check("adc1", "five_distinct_channels", len(set(used)) == 5, sorted(used))
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
    names = {"VBUS": "VBUS_ADC", "CT_MON": "CT_MON_ADC", "HS": "HS_ADC", "COIL": "COIL_ADC", "M12": "M12_ADC"}
    rep.check("adc1", "sample_pattern_covers_the_five_channels",
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
    gates, free = build_logic(nl, m, MODELS, {"ESP32-S3-WROOM-1-N8", "TCA9555PWR"},
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
    rep.check("trip", "single_latch_drives_permit",
              len(sim.dff) == 1 and sim.dff[0][2][0] == permit, [g[3] for g in sim.dff])
    cone, by_out = fan_in_cone(gates, permit)
    reset = f("IL_RESET_N")
    fw = sorted(n for n in cone if n in free and free[n].startswith("firmware"))
    rep.data("trip", "fan_in_cone_nets", sorted(cone))
    rep.data("trip", "sources_in_cone", {n: free[n] for n in sorted(cone) if n in free})
    rep.check("trip", "only_firmware_input_is_reset_request", fw == [reset], fw)
    undriven = sorted(n for n in cone if n not in by_out and n not in free and n not in pull
                      and n not in (f(GND), f(V3)))
    rep.check("trip", "every_cone_net_driven_or_pulled", not undriven, undriven)
    pd = [r for r, p in nl.nets["permit"] if r.startswith("R") and pn.get((r, "2" if p == "1" else "1"), OPEN) == GND]
    rep.check("trip", "permit_has_pulldown_at_controller", bool(pd), pd)
    bad = [(n, r, p) for n in cone - {reset, f(GND), f(V3)} for r, p in m.nodes(n)
           if nl.mpn.get(r) in ("ESP32-S3-WROOM-1-N8", "TCA9555PWR")]
    rep.check("trip", "no_mcu_or_expander_pin_in_cone_except_reset", not bad, bad)
    sources = sorted(n for n in cone if n in free and n != reset)
    unknown = [free[n] for n in sources if free[n] not in HEALTHY_LEVEL]
    rep.check("trip", "every_source_has_a_specified_healthy_level", not unknown, unknown)
    missing = sorted(set(HEALTHY_LEVEL) - {free[n] for n in sources})
    rep.check("trip", "every_specified_source_reaches_permit", not missing, missing)
    if unknown or len(sim.dff) != 1:
        return
    healthy = {n: HEALTHY_LEVEL[free[n]][0] for n in sources}
    violations, missed, unheld = exhaustive(sim, sources, reset, healthy)
    rep.data("trip", "enumerated_cases", 2 ** len(sources) * 8)
    rep.check("trip", "any_trip_source_forces_permit_low_for_every_firmware_state",
              not violations, violations[:3])
    rep.check("trip", "all_healthy_plus_fresh_reset_edge_grants_permit", not missed, missed[:3])
    rep.check("trip", "all_healthy_without_edge_holds_state", unheld == 0, unheld)
    rows = []
    for n in sources:
        a = dict(healthy)
        a[n] = 1 - a[n]
        res = {}
        for r_prev, r_now in ((1, 1), (0, 0), (1, 0), (0, 1)):
            val, q = sim.step(a, reset, r_prev, r_now, 1)
            res[f"RESET_N {r_prev}->{r_now}"] = {"PERMIT": q, "LATCHED_FAULT": 1 - q}
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
                                           "IDD 340 mA max, 3.3 V, 100 % on, factory jumper"})
    enc_ma = 30.0
    rep.data("v3v3", "encoder_allocation_mA", {"mA": enc_ma, "basis": "[UNVERIFIED] Grayhill encoder supply "
                                               "allocation; pin map and part not yet fixed"})
    peak = total_with_oled + enc_ma
    rep.data("v3v3", "peak_mA", peak)
    rep.check("v3v3", "within_tps62933_3A", peak <= 3000.0, peak)
    rep.check("v3v3", "within_inductor_irms_2p45A", peak <= 2450.0, peak)
    # PS1 (IRM-20-15, 21 W) at the controller; efficiencies are allocations.
    p3 = 3.465 * peak / 1e3 / 0.85
    pfan = 12.22 * 0.63 / 0.90
    p_total = p3 + pfan
    rep.data("v3v3", "ps1", {"p_3v3_rail_W": p3, "p_fan_W": pfan, "p_total_W": p_total, "rating_W": 21.0,
                             "basis": "efficiencies 85 % (3.3 V) / 90 % (12 V) are allocations from the "
                                      "TPS62933 typical curves; IRM-20-15 21 W rated"})
    rep.check("v3v3", "ps1_within_21W_at_peak", p_total <= 21.0, p_total)
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
