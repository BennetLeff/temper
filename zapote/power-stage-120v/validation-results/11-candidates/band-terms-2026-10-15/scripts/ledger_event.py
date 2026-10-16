#!/usr/bin/env python3
"""Ledger patch for the stacked bus-event rows (S20 follow-up), applied to a COPY of PS's ledger.json.

    python3 -I ledger_event.py --src COPY_IN --out COPY_OUT --variant strict|reformed [--landed REL_DIR]
    (run bus_event.py first; every number is read from ../results/bus_event.json)

What changes (both variants): the stacked event stress is re-based from 451.6 V (E_t 0.475 J from the stage-13b
97.77 A band, V0 at the OVP top with no trip delay) to the current tank state:
    E_t 0.897 J  = max tank energy at gate-off on the committed bank-ov grid at the s47 shunt top 119.09 A
                   (I_off <= 155.7 A; L 73.15 uH / C 0.55 uF corner, 280 V bus)
    V0 / I0      = 323.04 V / 25.95 A: gate-off T_D 2.267 us after the U7 filter (tau max 16.47 us) crosses the
                   287.62 V band top on the 500 uH / 30 A line ring (the ring carries 30 A at the band top)
    Vpk          = 512.4 V (closed form, C 14.9 uF, no clamp; R3/R4 share 256.2 V)
Variant 'strict' keeps every check and its severity: C12/C13/C19/C20 (0.512 > 0.5) and C5/C6 hot (0.899 > 0.8) fail,
so those two entries become VIOLATION and the gate fails.
Variant 'reformed' takes two decisions (for the integrator; DECISIONS item text in results.md):
  1. C12 family: D3 / D17 are fitted, so the 50 % rule is held on the bus WITH the clamp at its published point:
     466.8 V string at <= 129.8 A (Good-Ark p.3), x (1 + 0.1 %/K x 48 K) to 73 C (typical tempco, Littelfuse
     30KPA p.1; D3 B3 temperature row) = 489.2 V (0.489). The modelled clamp current on V-I lines through the published
     points is 66-72 A (<= IPP). The no-clamp check stays as a gap (0.512).
  2. C5/C6 hot: the event (< 0.3 ms) is held against TDK's transient overvoltage allowance, 1.5 x Vop for 30 ms,
     1000 times per life (p.14 NOTE 1), at the 105 C derated Vop 570 V (p.13: 1.2 %/C from 85 C) = 855 V (0.599,
     max 0.8). The continuous-Vop check stays as a gap (0.899 no clamp; 0.858 at the published clamp; 0.769 on the
     hot straight-line clamp model 438.4 V; bench T1 of ALT-D3 s5 closes it).
D3 gains the event pulse-power stress (near-ideal-clamp bound 27.7 kW per device against its 34 kW rating).
"""
import argparse
import copy
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RES = json.loads((HERE.parent / "results/bus_event.json").read_text())
KEY = "max (R +1 % / +0.1 %, C27 +5 %) | E_t at 119.09 A"
ST = RES["stacked_with_ovp_delay"][KEY]
V_EV = round(ST["coherent_ring_Vpk_V"], 1)
E_T = ST["E_t_J"]
OD = RES["ovp_delay"]["max (R +1 % / +0.1 %, C27 +5 %)"]
TANK = RES["tank_at_gate_off"]["s47 shunt top 119.09 A (bands-s47.md:24)"]
V_CLAMP_PUB = RES["clamp_bound_published_25C"]["hot_assumed_+0.1%/K_at_73C_V"]
TD = RES["time_domain_event"]
TD_HOT = TD[f"max-E run at 119.09 A | V0 {OD['V0_gate_off_V']} V, I0 {OD['I0_gate_off_A']} A (OVP delay) | clamp high line hot, x(1 + 0.1 %/K x 48 K) at 73 C"]
TD_IDEAL = TD[f"max-E run at 119.09 A | V0 {OD['V0_gate_off_V']} V, I0 {OD['I0_gate_off_A']} A (OVP delay) | clamp near-ideal at VBR min -10 C, 323 V, 129.8 A at 329.5 V (bounds the clamp current)"]
P_IDEAL = round(TD_IDEAL["pulse_check"]["P_peak_W_upper"], 0)
I_LINES = [v["clamp_I_peak_A"] for k, v in TD.items() if k.startswith("max-E run at 119.09") and "line" in k]
DATE = "2026-10-16"

EV_BASE = ("validation-results/02-protection-timing/bank-ov-double-fault/bank_ov_double_fault.py; "
           "validation-results/11-candidates/r2-cost/scripts/bus_peak_no_clamp.py:17-22; "
           "validation-results/11-candidates/c47-ref25-grade/results/bands-s47.md:24; "
           "validation-results/02-protection-timing/stage15-28A/fault_check.py; elec/src/power_stage_120v.ato:505-516")
COND = (f"stacked closed form on the current tank state: E_t {E_T:.3f} J (max tank energy at gate-off, bank-ov grid at the "
        f"s47 shunt top 119.09 A, I_off <= {TANK['max_I_off_A']:.1f} A), gate-off at V0 {OD['V0_gate_off_V']} V / "
        f"I0 {OD['I0_gate_off_A']} A (500 uH / 30 A line ring through the U7 sense filter, tau {OD['tau_us']} us, "
        f"+ T_D 2.267 us after the 287.62 V band top), C -19 %, no D3 clamp credit "
        f"(band-terms bus_event; was 451.6 V on E_t 0.475 J, V0 287.62 V)")
NOTE = (f" S20b ({DATE}, band-terms ledger_event): the stacked event re-based to the current tank state, 451.6 -> "
        f"{V_EV} V (E_t 0.475 -> {E_T:.3f} J at the 119.09 A shunt top; OVP-delay gate-off {OD['V0_gate_off_V']} V).")


def set_stress(e, param, value, cond=COND, ev=EV_BASE):
    s = next(x for x in e["stresses"] if x["parameter"] == param)
    s["worst_case_value"] = value
    s["condition"] = cond
    s["evidence"] = ev
    return s


def recompute(e):
    r = {x["parameter"]: x for x in e["ratings"]}
    s = {x["parameter"]: x for x in e["stresses"]}
    for c in e["checks"]:
        c["ratio"] = round(s[c["stress"]]["worst_case_value"] / r[c["rating"]]["datasheet_limit"], 4)


def chk(e, cid):
    return next(c for c in e["checks"] if c["id"] == cid)


def patch(d, variant, landed):
    ev = EV_BASE + (f"; {landed}/scripts/bus_event.py; {landed}/results/bus_event.json" if landed else "")
    E = d["entries"]
    if any(x["parameter"] == "Pulse power, gate-off event (per device)" for x in E["30KPA150CA"]["stresses"]):
        raise SystemExit("already patched: run on the unpatched ledger")
    # ---- re-base the event stress everywhere it is used
    c12 = E["CC1206JKNPOCBN102"]
    set_stress(c12, "Bus, worst stacked no-clamp case", V_EV, ev=ev)
    chk(c12, "bus no-clamp worst")["rule"] = f"{V_EV} V <= 500 V"
    c56 = E["B32676G1905K000"]
    set_stress(c56, "Vbus worst no-clamp", V_EV, ev=ev)
    chk(c56, "Vbus worst hot")["rule"] = f"{V_EV} <= 456 V"
    c38 = E["B32652A0104K000"]
    set_stress(c38, "Vbus worst no-clamp", V_EV, ev=ev)
    br1 = E["GBJ2510-F"]
    set_stress(br1, "V reverse worst", V_EV, ev=ev)
    drv = E["2EDR8259XXUMA1"]
    set_stress(drv, "Barrier peak", V_EV, cond=COND + " (HOT-to-HOT functional here) (peak)", ev=ev)
    r34 = E["RC1206FR-07220KL"]
    set_stress(r34, "V per resistor transient", round(V_EV / 2, 1), cond=f"{V_EV} V stacked event / 2 (R3 / R4 in series); " + COND,
               ev=ev + "; elec/src/power_stage_120v.ato:351-358")
    chk(r34, "V transient")["rule"] = f"{round(V_EV / 2, 1)} <= 400 V"
    # ---- D3: event pulse power (bounded by a near-ideal 323 V clamp)
    d3 = E["30KPA150CA"]
    d3["stresses"].append({
        "parameter": "Pulse power, gate-off event (per device)", "worst_case_value": P_IDEAL, "unit": "W",
        "condition": (f"stacked gate-off event above (E_t {E_T:.3f} J, OVP-delay gate-off), time-domain: bounded by a "
                      f"near-ideal clamp at the -10 C VBR min (323 V string): {TD_IDEAL['clamp_I_peak_A']} A x "
                      f"{TD_IDEAL['Vbus_peak_V']} V / 2, {TD_IDEAL['clamp_t_above_half_peak_us']} us above half peak, "
                      f"{TD_IDEAL['clamp_energy_J'] / 2:.2f} J per device; V-I lines through the published points give "
                      f"{min(I_LINES):.0f}-{max(I_LINES):.0f} A and about 15 kW (band-terms bus_event)"),
        "evidence": ev + "; validation-results/08-manufacturing-package/native-21/sourcing/alt-circuits-2026-10-09/ALT-D3.md:154-165"})
    d3["checks"].append({"id": "pulse power, gate-off event", "rating": "PPP at 49 us rectangular",
                         "stress": "Pulse power, gate-off event (per device)", "max_ratio": 1.0, "severity": "violation",
                         "rule": f"{P_IDEAL / 1e3:.1f} kW <= 34 kW (49 us rectangular, 85 C derated; the event is ~26 us at 73 C)"})
    if variant == "reformed":
        # 1. C12 family on the bus with the D3 clamp at its published point
        c12["stresses"].append({
            "parameter": "Bus, worst stacked case with the D3 clamp", "worst_case_value": V_CLAMP_PUB, "unit": "V",
            "condition": (f"D3 + D17 string VC max 466.8 V at IPP 129.8 A (Good-Ark p.3) x (1 + 0.1 %/K x 48 K) to the D3 "
                          f"73 C B3 row (typical tempco, Littelfuse 30KPA p.1; Good-Ark publishes none); the event clamp "
                          f"current on V-I lines through the published points is {min(I_LINES):.0f}-{max(I_LINES):.0f} A "
                          f"(<= IPP), and a stiffer clamp holds the bus lower (band-terms bus_event)"),
            "evidence": ev + "; validation-results/08-manufacturing-package/native-21/sourcing/alt-circuits-2026-10-09/ALT-D3.md:60"})
        c12["checks"].append({"id": "bus worst with D3", "rating": "Rated voltage DC",
                              "stress": "Bus, worst stacked case with the D3 clamp", "max_ratio": 0.5,
                              "severity": "violation", "rule": f"{V_CLAMP_PUB} V <= 500 V (D3 fitted)"})
        chk(c12, "bus no-clamp worst")["severity"] = "gap"
        chk(c12, "bus no-clamp worst")["rule"] = f"no D3 credit: {V_EV} V > 500 V; with D3 at its published point 0.489 (check 'bus worst with D3')"
        c12["gaps"].append(f"bench: without the D3 / D17 clamp the stacked gate-off event reaches {V_EV} V (0.512 of 1 kV, "
                           f"over the 50 % rule); the 50 % rule holds only with D3 credit (489.2 V). ALT-D3 s5 T1 measures it.")
        # 2. C5/C6: the event against TDK's transient overvoltage allowance
        c56["ratings"].append({"parameter": "Transient overvoltage at 105 C (1.5 x Vop, 30 ms, 1000 per life)",
                               "datasheet_limit": 855.0, "unit": "V",
                               "basis": "1.5 x Vop for 30 ms, permitted 1000 times during life (NOTE 1), applied to the 105 C derated Vop 570 V",
                               "source": "p.14 Overvoltage table NOTE 1; p.13 Vop derating 1.2 %/C from 85 to 105 C"})
        c56["checks"].append({"id": "Vbus event vs transient rating", "rating": "Transient overvoltage at 105 C (1.5 x Vop, 30 ms, 1000 per life)",
                              "stress": "Vbus worst no-clamp", "max_ratio": 0.8, "severity": "violation",
                              "rule": f"{V_EV} V (< 0.3 ms) <= 684 V"})
        h = chk(c56, "Vbus worst hot")
        h["severity"] = "gap"
        h["rule"] = (f"continuous-Vop screen: {V_EV} V > 456 V with no clamp; 0.858 at the published D3 point; "
                     f"0.769 on the hot straight-line clamp model ({TD_HOT['Vbus_peak_V']} V). The event is transient: "
                     f"check 'Vbus event vs transient rating' (TDK p.14)")
        c56["gaps"].append(f"bench: the stacked gate-off event ({V_EV} V no clamp) exceeds 80 % of the 105 C continuous Vop "
                           f"(456 V); it is held against TDK's 30 ms transient allowance (p.14 NOTE 1). The number of such "
                           f"events over life (<= 1000) is a firmware / FMEA count; D3's clamp at the event current "
                           f"(ALT-D3 s5 T1) would bring the bus under 456 V ({TD_HOT['Vbus_peak_V']} V on the hot "
                           f"straight-line model).")
    else:
        for e, cid, why in ((c12, "bus no-clamp worst", f"{V_EV} V stacked gate-off event with no D3 credit is 0.512 of the 1 kV rating (rule 0.5)"),
                            (c56, "Vbus worst hot", f"{V_EV} V stacked gate-off event with no D3 credit is 0.899 of the 105 C Vop 570 V (rule 0.8)")):
            e["status"] = "VIOLATION"
            e["finding"] = f"S20b {DATE}: {why} (band-terms bus_event; E_t {E_T:.3f} J at the 119.09 A shunt top)"
    for e in (c12, c56, c38, br1, drv, r34, d3):
        recompute(e)
        e["notes"] = (e["notes"] or "") + NOTE
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--variant", choices=("strict", "reformed"), required=True)
    ap.add_argument("--landed", default=None, help="unit-relative folder holding band-terms scripts/ and results/ once committed")
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    src = json.loads(Path(a.src).read_text())
    d = patch(copy.deepcopy(src), a.variant, a.landed)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n")
    rows = []
    for k in ("CC1206JKNPOCBN102", "B32676G1905K000", "B32652A0104K000", "GBJ2510-F", "2EDR8259XXUMA1", "RC1206FR-07220KL", "30KPA150CA"):
        old = {c["id"]: c for c in src["entries"][k]["checks"]}
        for c in d["entries"][k]["checks"]:
            o = old.get(c["id"])
            if o is None or o["ratio"] != c["ratio"] or o["severity"] != c["severity"]:
                rows.append({"entry": k, "check": c["id"], "old_ratio": o["ratio"] if o else None, "new_ratio": c["ratio"],
                             "max_ratio": c["max_ratio"], "severity": c["severity"],
                             "old_severity": o["severity"] if o else None, "status": d["entries"][k]["status"]})
    if a.json:
        Path(a.json).write_text(json.dumps({"variant": a.variant, "V_event_V": V_EV, "E_t_J": E_T, "rows": rows}, indent=1) + "\n")
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
