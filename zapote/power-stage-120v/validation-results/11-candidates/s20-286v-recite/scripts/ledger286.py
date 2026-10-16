#!/usr/bin/env python3
"""S20: re-cite the ledger's bus-OVP rows (286 V and everything derived from it) and the CST3015 volt-time row to the
s47 band tops. Writes --out (a copy or ledger.json itself; --src must differ). Integrated at ps-integrate after 651640bb7.

  python3 -I ledger286.py --src BASE/ledger.json --out PATCHED/ledger.json [--vbus 287.62] [--json RESULTS.json]

Basis (unit-relative citations; every one resolves under zapote/power-stage-120v at ps-integrate 651640bb7):
  V_OVP  287.62 V  the s47 OVP band top, the higher of the release (287.45 V, bands-s47.md:22) and c28 (287.62 V,
                   bands-s47.md:24) solved-network rows: the same "higher of release and c28" rule DECISIONS 63 used to
                   re-cite R5 at 119.09 A. 286 V was DC-LINK-CLAMP.md:28's hand estimate (REF25 2.520 V, +5 mV, no TCR),
                   carried by ALT-D3.md:60 as the "static OVP corner"; it was never a datasheet or protection limit, and
                   it already sat under round 3's 288.02 V (02-protection-timing/round3/README.md:30).
  V_EVT  the stacked no-clamp event, r2-cost bus_peak_no_clamp.py:17-22 closed form, at its worst corner
         (C 14.9 uF = 18.4 uF -19 %, 500 uH / 30 A line, Vs 198 V, E_t 0.475 J) with V0 = V_OVP. The script's own
         286 V run is the control (450.7 V).
  I_TOP  119.09 A  the s47 shunt-band top (bands-s47.md:24, c28; release 117.45 A at :22), for CST3015-200ED's
         secondary volt-time, by g04-g09 ct_options.py:36-39 (N 200, burden 3.0 + DCR 5.94 ohm, half sine at 25 kHz).
         The 118.74 A control reproduces 67.6 V-us.
"""
import sys
sys.dont_write_bytecode = True
import argparse, copy, json, math
from pathlib import Path

BANDS = "validation-results/11-candidates/c47-ref25-grade/results/bands-s47.md"
EV_OVP = f"{BANDS}:22; {BANDS}:24"
EV_EVT = f"validation-results/11-candidates/r2-cost/scripts/bus_peak_no_clamp.py:17-22; {BANDS}:24"
EV_CT = f"validation-results/11-candidates/g04-g09-tank-detect/scripts/ct_options.py:36-39; {BANDS}:24"
EV_DIV = "elec/src/power_stage_120v.ato:491-516"
TAG = "S20 (2026-10-16, ledger286.py): re-cited from the 286 V hand estimate to the s47 OVP band top"


def vpk(C, V0, L, I0, Vs=198.0, Et=0.475):          # r2-cost bus_peak_no_clamp.py:18-22, verbatim
    V1 = math.sqrt(V0 ** 2 + 2 * Et / C)
    if L == 0:
        return V1
    return Vs + math.sqrt((V1 - Vs) ** 2 + (L / C) * I0 ** 2)


def volt_time(ipk, f=25e3, N=200, burden=3.0, dcr=5.94):   # ct_options.py:36-39, CST3015-200ED row (:22)
    return ipk / N * (burden + dcr) / (math.pi * f) * 1e6


def r4(x):
    return round(x, 4)


def stress(e, name):
    hits = [s for s in e["stresses"] if s["parameter"] == name]
    assert len(hits) == 1, (e["mpn"], name, len(hits))
    return hits[0]


def rename_stress(e, old, new):
    if not any(s["parameter"] == old for s in e["stresses"]):     # already patched: idempotent
        return stress(e, new)
    s = stress(e, old)
    s["parameter"] = new
    for c in e["checks"]:
        if c["stress"] == old:
            c["stress"] = new
    return s


def recheck(e, sname, rules):
    """Recompute every check on stress `sname`; rules: check id -> rule text (callable of ratio) or None."""
    rat = {r["parameter"]: r for r in e["ratings"]}
    s = stress(e, sname)
    out = []
    for c in e["checks"]:
        if c["stress"] != sname:
            continue
        lim = rat[c["rating"]]["datasheet_limit"]
        old = c["ratio"]
        c["ratio"] = r4(s["worst_case_value"] / lim)
        if c["id"] in rules and rules[c["id"]]:
            c["rule"] = rules[c["id"]](c["ratio"], s["worst_case_value"], lim)
        out.append({"mpn": e["mpn"], "designators": e["designators"], "check": c["id"], "stress": sname,
                    "rating": c["rating"], "limit": lim, "value": s["worst_case_value"], "unit": s["unit"],
                    "ratio_old": old, "ratio_new": c["ratio"], "max_ratio": c["max_ratio"], "severity": c["severity"],
                    "crosses": c["ratio"] > c["max_ratio"] + 1e-9})
    return out


def note(e, text):
    if text not in (e.get("notes") or ""):
        e["notes"] = (e["notes"] + " " if e.get("notes") else "") + text


def patch(L, v_ovp, i_top):
    E = L["entries"]
    v_evt = round(vpk(14.9e-6, v_ovp, 500e-6, 30), 1)
    v_rms = round(v_ovp / math.sqrt(2), 2)
    vsense = r4(v_ovp * 15.8 / (4 * 470 + 15.8))
    vt = round(volt_time(i_top), 1)
    pct = lambda r, v, l: f"{100 * r:.0f} %"
    rows = []

    # --- static rows: the DC bus can sit just under the OVP band top indefinitely
    for mpn, sname, cond, rules in (
        ("B32676G1905K000", "Vbus static OVP", "s47 OVP band top (static: the bus can sit just below the trip)",
         {"Vbus static": lambda r, v, l: f"{v} <= 600 V"}),
        ("CC1206JKNPOCBN102", "Bus static OVP (continuous)", "DC bus at the s47 OVP band top",
         {"bus static OVP": lambda r, v, l: f"{v} V <= 500 V"}),
        ("30KPA150CA", "Bus static OVP", "s47 OVP band top, standoff must exceed it",
         {"standoff": lambda r, v, l: f"{v} V <= 300 V ({100 * r:.1f} %: no margin)"}),
        ("AMC1311BDWVR", "Barrier peak", "bus at the s47 OVP band top (conservative: the HOT side rides HV_RET, "
         "which is within the line peak of PE)", {"barrier": pct}),
        ("CA-IS3720HW", "Barrier peak", "bus at the s47 OVP band top", {"barrier": pct}),
        ("ISO6721FBDR", "Barrier peak", "bus at the s47 OVP band top: each HS island (SW_A for U43, SW_B for U44) "
         "swings 0..VBUS against N_LS", {"barrier": pct}),
    ):
        e = E[mpn]
        s = stress(e, sname)
        s.update(worst_case_value=v_ovp, condition=cond + f" ({v_ovp} V: c28 solved network; release 287.45 V)",
                 evidence=EV_OVP)
        rows += recheck(e, sname, rules)
        note(e, TAG + f" ({v_ovp} V).")

    e = E["RC1206FR-07220KL"]
    s = stress(e, "V per resistor static")
    s.update(worst_case_value=round(v_ovp / 2, 2), evidence=f"{EV_OVP}; elec/src/power_stage_120v.ato:351-358",
             condition=f"{v_ovp} V s47 OVP band top / 2 (R3/R4 in series BUS_P - BUSBLEED_MID - HV_RET)")
    rows += recheck(e, "V per resistor static", {"V": pct})
    e["gaps"] = [g.replace("(286 V static > 200 V working", f"({v_ovp} V static > 200 V working") for g in e["gaps"]]
    note(e, TAG + f" ({v_ovp} V).")

    e = E["RC1206FR-07470KL"]
    s = stress(e, "V per resistor, bus divider at static OVP")
    s.update(worst_case_value=round(v_ovp / 4, 2), condition=f"{v_ovp} V s47 OVP band top / 4 (R26-R29)",
             evidence=f"{EV_OVP}; elec/src/power_stage_120v.ato:493")
    rows += recheck(e, "V per resistor, bus divider at static OVP", {})
    e["gaps"] = [g.replace("<= 11 mW each at 286 V", f"<= {(v_ovp / 4) ** 2 / 470e3 * 1e3:.0f} mW each at {v_ovp} V")
                 for g in e["gaps"]]
    note(e, TAG + f" ({v_ovp} V).")

    for mpn, sname, cond in (
        ("2EDR8259XXUMA1", "Barrier rms", f"HS output side swings 0..{v_ovp} V (s47 OVP band top) square against the "
         f"input side: {v_ovp} / sqrt 2"),
        ("ISO6721FBDR", "Barrier rms", f"same square wave, {v_ovp} / sqrt 2"),
    ):
        e = E[mpn]
        s = stress(e, sname)
        s.update(worst_case_value=v_rms, condition=cond, evidence=EV_OVP)
        rows += recheck(e, sname, {"working": pct})
        if mpn == "2EDR8259XXUMA1":
            note(e, TAG + f" ({v_ovp} V; {v_rms} Vrms).")

    e = E["AMC1311BDWVR"]
    s = rename_stress(e, "VSENSE at 286 V OVP corner", "VSENSE at the OVP band top")
    s.update(worst_case_value=vsense, evidence=f"{EV_OVP}; {EV_DIV}",
             condition=f"nominal divider 15.8 k / 1,895.8 k at the s47 OVP band top {v_ovp} V")
    rows += recheck(e, "VSENSE at the OVP band top", {"input clip": lambda r, v, l:
                    f"{100 * r:.1f} % of clipping at {v_ovp} V; above 240 V the input is outside the linear range"})

    # --- stacked no-clamp event, V0 = the static band top (r2-cost closed form)
    for mpn, sname, cond, rules in (
        ("CC1206JKNPOCBN102", "Bus, worst stacked no-clamp case",
         f"static-OVP start {v_ovp} V, 500 uH / 30 A line event, C -19 %, no D3 clamp credit",
         {"bus no-clamp worst": lambda r, v, l: f"{v} V <= 500 V"}),
        ("B32676G1905K000", "Vbus worst no-clamp", f"worst stacked corner, V0 = {v_ovp} V (closed form)",
         {"Vbus worst hot": lambda r, v, l: f"{v} <= 456 V"}),
        ("B32652A0104K000", "Vbus worst no-clamp", f"worst stacked corner (V0 = {v_ovp} V static OVP top, stacked)",
         {"V": pct}),
        ("GBJ2510-F", "V reverse worst", f"bus worst stacked corner, V0 = {v_ovp} V (closed form)", {}),
        ("2EDR8259XXUMA1", "Barrier peak", f"bus worst stacked corner, V0 = {v_ovp} V (HOT-to-HOT functional here) "
         "(peak)", {}),
    ):
        e = E[mpn]
        s = stress(e, sname)
        s.update(worst_case_value=v_evt, condition=cond, evidence=EV_EVT)
        rows += recheck(e, sname, rules)
        if mpn in ("B32652A0104K000", "GBJ2510-F"):
            note(e, TAG + f" ({v_ovp} V start; stacked event {v_evt} V).")
    e = E["RC1206FR-07220KL"]
    s = stress(e, "V per resistor transient")
    s.update(worst_case_value=round(v_evt / 2, 2), condition=f"{v_evt} V worst stacked no-clamp corner / 2",
             evidence=f"{EV_EVT}; elec/src/power_stage_120v.ato:351-358")
    rows += recheck(e, "V per resistor transient", {"V transient": lambda r, v, l: f"{v} <= 400 V"})

    # --- the LM4050 entry's gap that recorded this problem
    e = E["LM4050AEM3-2.5/NOPB"]
    e["gaps"] = [g for g in e["gaps"] if "bus-OVP stresses quote 286 V" not in g]
    note(e, f"S20 closed by ledger286.py: the bus-OVP rows now cite the s47 band top {v_ovp} V.")

    # --- CST3015-200ED volt-time at the s47 shunt-band top
    e = E["CST3015-200ED"]
    s = rename_stress(e, "Volt-time at 118.74 A", "Volt-time at the shunt-band top")
    s.update(worst_case_value=vt, evidence=EV_CT,
             condition=f"secondary half-sine volt-time at the s47 shunt-band top {i_top} A, 25 kHz "
                       f"({vt / 1276 * 100:.1f} % of 1276 V-us; release top 117.45 A)")
    rows += recheck(e, "Volt-time at the shunt-band top", {"volt-time": lambda r, v, l: f"{r:.3f}"})
    note(e, f"S20 (2026-10-16, ledger286.py): volt-time re-cited from the stage-15 118.74 A top to the s47 "
            f"{i_top} A top.")
    return rows, {"V_OVP": v_ovp, "V_EVT": v_evt, "V_rms": v_rms, "VSENSE": vsense, "I_TOP": i_top, "volt_time": vt}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--vbus", type=float, default=287.62)
    ap.add_argument("--itop", type=float, default=119.09)
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    src, out = Path(a.src).resolve(), Path(a.out).resolve()
    assert src != out
    # controls: the closed form and the CT method reproduce the values being replaced
    assert round(vpk(14.9e-6, 286.0, 500e-6, 30), 1) == 450.7
    assert round(volt_time(118.74), 1) == 67.6
    L = json.loads(src.read_text())
    before = copy.deepcopy(L)
    rows, basis = patch(L, a.vbus, a.itop)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(L, indent=1) + "\n")
    changed = sorted(k for k in L["entries"] if L["entries"][k] != before["entries"][k])
    res = {"basis": basis, "src": str(src), "changed_entries": changed, "rows": rows,
           "crossing": [r for r in rows if r["crosses"]]}
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(basis))
    for r in rows:
        print(f"{r['mpn']:20s} {','.join(r['designators'])[:22]:22s} {r['check']:20s} {r['value']:>8} {r['unit']:5s} "
              f"/ {r['limit']:<7} {r['ratio_old']:.4f} -> {r['ratio_new']:.4f}  max {r['max_ratio']:.4f}"
              f"{'  CROSSES' if r['crosses'] else ''}")
    print("changed entries:", changed)


if __name__ == "__main__":
    main()
