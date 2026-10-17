#!/usr/bin/env python3
"""D-31 part 2: fault-source-to-gates-off timing ledger (native-19, both paths).

Every stage is tagged:
  BOUND       datasheet maximum at the stated condition (page cited)
  BOUND*      datasheet maximum at a *different* supply than the circuit uses,
              used as a bound under a stated monotonicity assumption
  ALLOCATION  a budget that a measurement must confirm (no guaranteed value)
  ESTIMATE    a calculation from typical data

Chain (FAULT-INTERFACE.md; frozen/default.net; zapote/interlock/MODEL.md):
  shunt OCP: R5 -> RC filter/comparator U6 (round-3 A5) -> NAND U8
             (SN74LVC1G10) -> ISO7710 U9 -> OR (SN74LVC1G332) -> J4.10
  tank CT:   T1 -> burden/comparators (round-3 A3) -> OR (SN74LVC1G332) -> J4.10
  then:      harness -> interlock: SN74LVC14A -> CD74HC30 -> SN74LVC14A ->
             SN74LVC1G74 CLR->Q = PERMIT -> harness -> R6/R14 100 ohm ->
             Q1/Q4 AO3400A gate (R7 100 k pull-down) -> DIS node rises via
             R8/R16 1 k to VCCI -> UCC21550 DIS response -> gate discharge.

    python3 ledger.py   ->  ledger.json, ledger.md
"""
from __future__ import annotations

import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
TI = "https://www.ti.com/lit/ds/symlink/"
AOS = "https://www.aosmd.com/sites/default/files/res/datasheets/AO3400A.pdf"

# --- passive stage estimates (AO3400A, DIS network) ---------------------------
VCC_MIN, VCC_MAX = 3.135, 3.465          # J4.3 / interlock rail contract (FAULT-INTERFACE.md)
VTH_MIN = 0.65                           # AO3400A VGS(th) min, p2
CISS = 630e-12                           # AO3400A Ciss typ, p2 (VDS=15 V); low-VDS value larger
GATE_C_ALLOC = 1.0e-9                    # allocation: Ciss plus Miller at low VDS (curve p4, unread)
R_GATE = 100 * 1.01 + 3 + 4.5            # R6/R14 +1 %, LVC1G74 output (allocation 3 ohm), AO3400A Rg max 4.5 ohm (p2)
R_PU = 1000 * 1.01                       # R8/R16 1 k +1 % (native-19)
R_PU_N20 = 330 * 1.01                    # R8/R16 330 ohm +1 % (native-20, DECISIONS.md 2026-10-05)
DIS_C_ALLOC = 270e-12                    # allocation: AO3400A Coss at 0..3 V (curve p4; 75 pF at 15 V) + DIS pin + trace
VIH_DIS_MAX = 2.3                        # UCC21550 IN/DIS high threshold max, p9

t_q_off = R_GATE * GATE_C_ALLOC * math.log(VCC_MAX / VTH_MIN)          # gate from Vcc to Vth(min)
# Datasheet-only hard bound (BOUND*): Qg <= 7 nC max at VGS 4.5 V / VDS 15 V (AO3400A p2) covers our
# <= 3.465 V gate and drain swing (Qg monotonic in both); gate current >= VTH_MIN / R_GATE until the
# gate reaches VTH_MIN, so t <= R_GATE * QG_MAX / VTH_MIN. No vendor SPICE model was reachable (AOS site).
QG_MAX = 7e-9
t_q_off_charge_bound = R_GATE * QG_MAX / VTH_MIN
t_dis = R_PU * DIS_C_ALLOC * math.log(VCC_MIN / (VCC_MIN - VIH_DIS_MAX))  # DIS from 0 to VIH max at lowest rail
t_dis_n20 = R_PU_N20 * DIS_C_ALLOC * math.log(VCC_MIN / (VCC_MIN - VIH_DIS_MAX))
I_PU_N20_MA = VCC_MAX / (330 * 0.99) * 1e3   # per leg, while PERMIT holds DIS low

STAGES = {
    # name: (min_ns, max_ns, tag, source)
    "shunt front end (R5 filter, TLV3201 at 20 mV overdrive)": (
        None, None, "ROUND-3", "validation-results/02-protection-timing/round3 (A5); see survival.py for the current reached"),
    "CT front end (crossing -> comparator OR output)": (
        71.0, 336.3, "ROUND-3", "validation-results/02-protection-timing/round3/README.md:39 (106 modelled CT rows)"),
    "NAND SN74LVC1G10 (HOT side, shunt path only)": (None, 6.4, "BOUND", TI + "sn74lvc1g10.pdf p5, 3.3 V column, worst row"),
    "ISO7710 (shunt path only)": (None, 21.0, "BOUND", TI + "iso7710.pdf pp14-15, largest of the supply cases"),
    "OR SN74LVC1G332": (None, 6.2, "BOUND", TI + "sn74lvc1g332.pdf p5, 3.3 V column, worst row"),
    "harness J4.10 out + J4.9 back (2 x 2 m, 5 ns/m)": (None, 20.0, "ALLOCATION", "cable length not fixed; D-20 O01"),
    "interlock SN74LVC14A (fault input)": (None, 8.0, "BOUND", TI + "sn74lvc14a.pdf p9, 3.3 V +-0.3 V, extended temperature"),
    "interlock CD74HC30 8-input NAND": (None, 115.0, "BOUND*", TI + "cd74hc30.pdf p6: 2 V, -40..85 C max; not specified at 3.3 V (4.5 V: 23 ns); delay decreases with VCC"),
    "interlock SN74LVC14A (ALL_GOOD)": (None, 8.0, "BOUND", TI + "sn74lvc14a.pdf p9"),
    "interlock SN74LVC1G74 CLR -> Q (= PERMIT)": (None, 7.9, "BOUND", TI + "sn74lvc1g74.pdf p7, PRE/CLR to Q, worst 3.3 V-range column"),
    "Q1/Q4 AO3400A turn-off (gate Vcc -> Vth min via 100 ohm)": (
        None, round(t_q_off * 1e9, 1), "ALLOCATION",
        AOS + f" p2 (Vth 0.65 V min, Rg 4.5 ohm max); gate C allocated {GATE_C_ALLOC*1e12:.0f} pF (Ciss 630 pF at 15 V; low-VDS curve p4)"),
    "DIS node rise to VIH (1 k pull-up)": (
        None, round(t_dis * 1e9, 1), "ALLOCATION",
        TI + f"ucc21550.pdf p9 (DIS VIH 2.3 V max); C allocated {DIS_C_ALLOC*1e12:.0f} pF (AO3400A Coss 75 pF at 15 V, larger near 0 V), lowest rail {VCC_MIN} V"),
    "UCC21550 DIS response (incl. 20 ns filter)": (27.0, 80.0, "BOUND", TI + "ucc21550.pdf p10, tPD_DIS_HL"),
}

GATE_DISCHARGE_NS = None   # from survival.py (D2 deck, loaded gate) — reported there


def total(path: str) -> dict:
    keys = [k for k in STAGES if not (
        (path == "CT" and ("shunt path only" in k or k.startswith("shunt front end"))) or
        (path == "shunt" and k.startswith("CT front end")))]
    mx = sum(STAGES[k][1] for k in keys if STAGES[k][1] is not None)
    tags = sorted({STAGES[k][2] for k in keys})
    return {"path": path, "stages": keys, "max_ns_excluding_front_end_and_gate_discharge": round(mx, 1)
            if path == "shunt" else round(mx - STAGES["CT front end (crossing -> comparator OR output)"][1], 1),
            "max_ns_including_front_end_where_known": round(mx, 1), "tags": tags}


def main() -> None:
    res = {"stages": {k: {"min_ns": v[0], "max_ns": v[1], "tag": v[2], "source": v[3]} for k, v in STAGES.items()},
           "paths": {p: total(p) for p in ("CT", "shunt")},
           "derived": {"t_q_off_ns": t_q_off * 1e9, "t_q_off_charge_bound_ns": t_q_off_charge_bound * 1e9, "t_dis_ns": t_dis * 1e9,
                       "assumptions": {"VCC_min": VCC_MIN, "VCC_max": VCC_MAX, "gate_C_alloc_pF": GATE_C_ALLOC * 1e12,
                                       "R_gate_ohm": R_GATE, "R_pu_ohm": R_PU, "DIS_C_alloc_pF": DIS_C_ALLOC * 1e12,
                                       "VIH_DIS_max": VIH_DIS_MAX}}}
    lines = ["| Stage | max ns | tag | source |", "| --- | ---: | --- | --- |"]
    for k, v in STAGES.items():
        lines.append(f"| {k} | {'' if v[1] is None else v[1]} | {v[2]} | {v[3]} |")
    for p in ("CT", "shunt"):
        t = res["paths"][p]
        lines.append(f"| **{p} path, comparator output to DIS response complete** | **{t['max_ns_excluding_front_end_and_gate_discharge']}** | {'/'.join(t['tags'])} | sum of the applicable rows (front end and gate discharge separate) |")
    d = t_dis * 1e9 - t_dis_n20 * 1e9
    res["native20"] = {"R_pu_ohm": R_PU_N20, "t_dis_ns": round(t_dis_n20 * 1e9, 1), "saving_ns": round(d, 1),
                       "pullup_current_mA_per_leg": round(I_PU_N20_MA, 2),
                       "paths_max_ns": {p: round(res["paths"][p]["max_ns_excluding_front_end_and_gate_discharge"] - d, 1)
                                        for p in ("CT", "shunt")}}
    for p in ("CT", "shunt"):
        lines.append(f"| **native-20 (R8/R16 330 Ω): {p} path** | **{res['native20']['paths_max_ns'][p]}** | as above | DIS rise {res['native20']['t_dis_ns']} ns; {res['native20']['pullup_current_mA_per_leg']} mA per leg from V3V3 while running |")
    (HERE / "ledger.json").write_text(json.dumps(res, indent=1) + "\n")
    (HERE / "ledger.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(res["paths"], indent=1))


if __name__ == "__main__":
    main()
