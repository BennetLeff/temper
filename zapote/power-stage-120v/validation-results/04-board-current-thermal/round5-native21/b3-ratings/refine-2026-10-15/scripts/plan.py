#!/usr/bin/env python3
"""Job lists for the thermal-refine solves (each config = c22_h10 / c28_h10 at 0.25 and 0.5 mm, unless stated).

    python3 plan.py base      -> runs/jobs-base.json   (controls, lead path, corrected heat)
    (fix_targets.py and ceilings.py build their own jobs with config())

Lead conductance corners (thermal_body.drain_lead_conductance; TO-247-3 drawing ranges, IPW65R018CFD7 p.12):
  central: mid dimensions, in-body frame 2.4 mm, k 300, joint 3 W/K
  low    : b2 2.57, c 0.38, L1 4.50, in-body 7.91, k 262, joint 1 W/K   (least coupling)
  high   : b2 3.43, c 0.89, L1 3.85, in-body 0,    k 390, joint 3 W/K   (most coupling)
Case temperature corners: sink_model.t_case (cool / central / hot).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BAYS, HEAT_DIR, MOD_CONV, PITCHES, ROUND5, RUNS  # noqa: E402
import sink_model  # noqa: E402

sys.path.insert(0, str(MOD_CONV))
import thermal_body as tb  # noqa: E402

HEAT_COMMITTED = str(ROUND5 / "b3/inputs/native21-board-heat-sources-c28.json")
HEAT_CORR = str(HEAT_DIR / "heat-c28-corrected.json")
HEAT_DSQ = str(HEAT_DIR / "heat-c28-corrected-dsq.json")
HEAT_DECK = str(HEAT_DIR / "heat-c28-corrected-deck.json")     # file of record (as-built deck gate charge, 382.6 nC)
D = tb.TO247_DRAIN_LEAD
G = {"central": tb.drain_lead_conductance(),
     "low": tb.drain_lead_conductance(D["b2_mm"][0], D["c_mm"][0], D["l1_mm"][1], D["l_int_mm"][1], D["k_w_mk"][0], D["g_joint_w_k"][0]),
     "high": tb.drain_lead_conductance(D["b2_mm"][1], D["c_mm"][1], D["l1_mm"][0], D["l_int_mm"][0], D["k_w_mk"][1], D["g_joint_w_k"][1])}
CEIL = {"c22_h10": 22.0, "c28_h10": 28.0}


def leads(ceil, g="central", corner="central", bay=55.0, t_case=None):
    if g is None:
        return None
    tc = t_case if t_case is not None else sink_model.t_case(ceil, corner)[0]
    return {"g": G[g] if isinstance(g, str) else float(g), "t_case_c": {k: round(v, 4) for k, v in tc.items()}, "bay_c": bay}


def config(name, heat, model="mod", g="central", corner="central", bay=55.0, cases=None, pitches=PITCHES,
           tank_factor=1.0, part_scale=None, t_case_by_case=None, save_field=False):
    jobs = []
    for case, ceil in (cases or CEIL).items():
        tcc = (t_case_by_case or {}).get(case)
        for p in pitches:
            jobs.append({"config": name, "case": case, "ceil": ceil, "pitch": p, "model": model, "heat": heat,
                         "tank_factor": tank_factor, "part_scale": part_scale or {},
                         "leads": leads(ceil, g, corner, bay, tcc) if model == "mod" else None})
            if save_field:
                jobs[-1]["save_field"] = True
    return jobs


def basis_a_tcase():
    """Basis-A FET loss at 60 kHz with the sink held at the firmware trip (sink_model.basis_a)."""
    out = {}
    for case, ceil in CEIL.items():
        b = sink_model.basis_a(ceil, 60e3)
        out[case] = {r: b["T_case_at_fw_trip_C"] for r in sink_model.FETS}
    return out


TANK_PARTS = ("R5", "R39", "C21", "C22", "C23", "C151", "C152", "C5", "C6")     # body_runs.TANK_ROWS
C28_ONLY = {"c28_h10": 28.0}


def base_jobs():
    """In priority order (solve.py keeps list order within a pitch)."""
    j = []
    j += config("A0_repo_committed", HEAT_COMMITTED, model="repo")                  # control: committed margins.json
    j += config("A1_mod_g0", HEAT_COMMITTED, g=0.0)                                  # control: lead code path, G = 0
    j += config("HL_central_b55", HEAT_CORR, save_field=True)                        # corrected model (both corrections)
    # superposition components on the corrected model (c28 basis; the system is linear in each source at a fixed matrix)
    j += config("SP_a4tank_half", HEAT_CORR, cases=C28_ONLY, tank_factor=0.5, save_field=True)
    j += config("SP_r5_half", HEAT_CORR, cases=C28_ONLY, part_scale={"R5": 0.5}, save_field=True)
    j += config("SP_tankparts_half", HEAT_CORR, cases=C28_ONLY, part_scale={r: 0.5 for r in TANK_PARTS}, save_field=True)
    j += config("HL_central_b61", HEAT_CORR, bay=61.0, save_field=True)
    j += config("L_central_b55", HEAT_COMMITTED, save_field=True)                    # task 1: lead path, central
    j += config("H_nolead", HEAT_CORR, g=None)                                       # task 2: corrected heat, no lead
    j += config("L_central_b61", HEAT_COMMITTED, bay=61.0, save_field=True)
    j += config("L_hot_b55", HEAT_COMMITTED, g="low", corner="hot")                  # task 1: conservative corner
    j += config("HL_hot_b55", HEAT_CORR, g="low", corner="hot")
    j += config("L_cool_b55", HEAT_COMMITTED, g="high", corner="cool")               # task 1: optimistic corner
    j += config("HLdsq_central_b55", HEAT_DSQ)                                       # sensitivity: datasheet-Q heat
    j += config("HLdsqF_central_b55", HEAT_DSQ, cases=C28_ONLY, save_field=True)     # its superposition component
    # the corrected model of record: deck-charge heat (382.6 nC) + lead path (direct solves; they also check the
    # superposition at q_deck)
    j += config("HLdeck_central_b55", HEAT_DECK)
    j += config("Hdeck_nolead", HEAT_DECK, g=None)
    j += config("HLdeck_central_b61", HEAT_DECK, bay=61.0)
    j += config("HLdeck_hot_b55", HEAT_DECK, g="low", corner="hot")
    j += config("HLdeck_cool_b55", HEAT_DECK, g="high", corner="cool")
    return j


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "base"
    jobs = {"base": base_jobs}[which]()
    RUNS.mkdir(exist_ok=True)
    path = RUNS / f"jobs-{which}.json"
    path.write_text(json.dumps(jobs, indent=1) + "\n")
    print(f"{len(jobs)} jobs -> {path}; G corners W/K: " + ", ".join(f"{k} {v:.4f}" for k, v in G.items()))


if __name__ == "__main__":
    main()
