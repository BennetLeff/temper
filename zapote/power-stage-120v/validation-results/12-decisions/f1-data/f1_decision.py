#!/usr/bin/env python3
"""F1 decision matrix: which mains fuse, decided by gates on data, with the value of each missing datum.

    python3 -I validation-results/12-decisions/f1-data/f1_decision.py   # -> f1_decision.json, exit 1 if a control fails

Method
- Hard gates, each PASS / FAIL / UNKNOWN from a cited number:
  G1 interrupting rating >= 8.4 kA prospective at a voltage >= 140 VAC (F1-RECOMMENDATION.md s2 bound).
  G2 carrying: In x 0.75 x derate(50 C) >= 15 A (the repo rule, F1-FUSE-DECISION.md).
  G3 nuisance: inrush <= 22 % and surge <= 38 % of melting / pre-arc I2t (Littelfuse pulse-cycle factors for
     100,000 and 1,000 pulses; inrush <= 1.0 A2s and the 1 kA 8/20 surge 12.2 A2s, F1-RECOMMENDATION.md 3.4).
  G4 board copper survives: total clearing I2t <= the governing series neck on the CURRENT board
     (02-protection-timing/shoot-through-f1/s29_necks.json via s21_necks.py's lim(); copper at 105 C), i.e. the
     scorecard's fuse_copper_fusing_ratio >= 1.
  G5 F2 selectivity: F1 melting I2t >= 2 x F2's clearing (upstream melt > downstream total clearing, x2 because
     F2's clearing is an estimate) (F2 UMT-H 3.15 A, 67 A2s current-limiting estimate,
     11-candidates/c28-f2/bounds.py).
  G6 agency basis: UL Listed Class CC = PASS (2026-10-09 basis); UL Recognized 248-14 supplemental = UNKNOWN
     until the certifier answers F1-FUSE-DECISION.md s5 (a).
- Soft score (reported, not gated): BR1 GBJ2510 survives if clearing <= 0.5 x 510 A2s.
- Decision: the cheapest candidate with every gate PASS. If none passes, the incumbent stays (with its FAILs listed)
  until a candidate's UNKNOWNs are resolved. For each cheaper candidate blocked only by UNKNOWNs, the
  saving per board is the value of resolving those UNKNOWNs.
Data: survey.json / SURVEY.md (2026-10-14, DigiKey prices at 500). Only the Bel 25 A total I2t and the 505 2019 table
were re-read from the PDFs by the reviewer (Bel 0ADEx PDF sha256 363ec204..., p.2 "Total I2t ... measured at 500V IR
test": 470 A2s; at 140 V the arc energy is lower, so it bounds).
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
VR = HERE.parents[1]

I_PROSP, V_MIN, I_CONT = 8400.0, 140.0, 15.0
INRUSH, SURGE = 1.0, 12.2
F2_CLEAR = 67.0
BR1_I2T = 510.0

necks = json.loads((VR / "02-protection-timing/shoot-through-f1/s29_necks.json").read_text())


def lim(s):   # governing I2t per row, exactly as s21_necks.py lim() (conductor neck, or the via field when it hops)
    v = [s.get("conductor_I2t_conservative", s["I2t_conservative"]) if s.get("via_field_actual_drills") else s["I2t_conservative"]]
    if s.get("route_needs_via_hop") or s.get("via_field_actual_drills"):
        f = s.get("via_field_actual_drills", {}).get("I2t") or s.get("via_field_I2t_equal_sharing")
        if f:
            v.append(f)
    return min(v)


worst = min(necks["segments"], key=lim)
neck_min = lim(worst)
NECK_SRC = f"s29_necks.json governing I2t (s21_necks.py lim()), worst row '{worst['segment']}' {neck_min:.1f} A2s"

# name: AIR A, AIR V, melt/pre-arc I2t, total clearing I2t, derate at 50 C, agency, $ fuse at 500, $ clips (2) at 500, stock
C = {
    "KLDR025.TXP (Class CC TD, today)": dict(air=200e3, v=600, melt=226, clear=1710, der=0.90, listed=True,
                                              fuse=18.516, clips=2 * 2.057, stock=88),
    "KLKR025.T (Class CC fast)": dict(air=200e3, v=600, melt=None, clear=None, der=None, listed=True,
                                      fuse=16.407, clips=2 * 2.057, stock=15),
    "CCMR025.TXP (Class CC TD)": dict(air=200e3, v=600, melt=None, clear=None, der=0.90, listed=True,
                                      fuse=18.826, clips=2 * 2.057, stock=320),
    "0505025.MXP (6.3x32 fast)": dict(air=30e3, v=500, melt=210, clear=None, der=0.98, listed=False,
                                      fuse=3.571, clips=2 * 0.505, stock=3112),
    "Bel 0ADEC9250-BE (6.3x32 fast)": dict(air=30e3, v=500, melt=200, clear=470, der=0.96, listed=False,
                                           fuse=2.763, clips=2 * 0.505, stock=1313),
}


def gate(ok):
    return "UNKNOWN" if ok is None else ("PASS" if ok else "FAIL")


rows = {}
for n, c in C.items():
    g = {}
    g["G1_interrupting"] = gate(c["air"] >= I_PROSP and c["v"] >= V_MIN)
    g["G2_carrying"] = gate(None if c["der"] is None else 25 * 0.75 * c["der"] >= I_CONT)
    g["G3_nuisance"] = gate(None if c["melt"] is None else (INRUSH <= 0.22 * c["melt"] and SURGE <= 0.38 * c["melt"]))
    g["G4_copper"] = gate(None if c["clear"] is None else c["clear"] <= neck_min)
    g["G5_F2_selectivity"] = gate(None if c["melt"] is None else c["melt"] >= 2 * F2_CLEAR)
    g["G6_agency"] = "PASS" if c["listed"] else "UNKNOWN"
    cost = round(c["fuse"] + c["clips"], 2)
    rows[n] = dict(gates=g, cost_usd_500=cost, stock=c["stock"],
                   copper_ratio=None if c["clear"] is None else round(neck_min / c["clear"], 2),
                   br1_survives=None if c["clear"] is None else c["clear"] <= 0.5 * BR1_I2T,
                   unknowns=[k for k, v in g.items() if v == "UNKNOWN"], fails=[k for k, v in g.items() if v == "FAIL"])

INCUMBENT = "KLDR025.TXP (Class CC TD, today)"
ok = {n: r for n, r in rows.items() if not r["unknowns"] and not r["fails"]}
choice = min(ok, key=lambda n: ok[n]["cost_usd_500"]) if ok else None
ref = choice or INCUMBENT
# candidates with no FAIL, blocked only by UNKNOWNs: what resolving them is worth against the reference
voi = {n: dict(saving_usd_per_board=round(rows[ref]["cost_usd_500"] - r["cost_usd_500"], 2), blocked_by=r["unknowns"])
       for n, r in rows.items() if n != ref and not r["fails"] and r["unknowns"]}

# controls: the s29 board's committed ratio is reproduced for KLDR, and a FAIL path exists
fails = []
if abs(rows["KLDR025.TXP (Class CC TD, today)"]["copper_ratio"] - necks["min_ratio_all"]) > 0.005:
    fails.append("KLDR copper ratio does not reproduce s29_necks.json min_ratio_all")
if gate(1e3 >= I_PROSP) != "FAIL":
    fails.append("G1 negative control")

out = dict(inputs=dict(prospective_A=I_PROSP, v_min=V_MIN, i_cont=I_CONT, inrush_A2s=INRUSH, surge_A2s=SURGE,
                       neck_min_A2s=round(neck_min, 1), neck_source=NECK_SRC, f2_clearing_A2s=F2_CLEAR, br1_A2s=BR1_I2T),
           candidates=rows, decision=choice or f"none passes every gate; incumbent {INCUMBENT} stays", value_of_information=voi, control_fails=fails)
(HERE / "f1_decision.json").write_text(json.dumps(out, indent=1) + "\n")
for n, r in rows.items():
    print(f"{n:34s} ${r['cost_usd_500']:6.2f}  ratio {r['copper_ratio']}  BR1 {r['br1_survives']}  "
          f"fails {r['fails']}  unknown {r['unknowns']}")
print("decision:", out["decision"])
print("value of information:", json.dumps(voi))
print("controls:", "ok" if not fails else fails)
raise SystemExit(1 if fails else 0)
