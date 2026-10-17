#!/usr/bin/env python3
"""Wall time and worker-minutes of a chain plan, from the s43 step timings in depmap.json and chain.sh's block structure.

    python3 -I estimate.py [--json OUT]       # the lanes below: full chain today, today's caches, scoped

Schedule (chain.sh): pre (plan_board_only, zone gate) + build -> d5 + probe/ERC -> parallel { fit | fab | core (barrier
in parallel with exports / DFM / bypass) -> copper_key [+ scoped decide] -> parallel { thermal: heat sources ->
task 04 -> B3 study -> ceiling sweep -> B3 ratings | Kelvin | copper gates } } -> scorecard.
Checked against the s43 chain: 1766 s modelled vs 13:15:05 -> 13:44:30 (1765 s) measured.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import scoped_lib as L  # noqa: E402

W = {s: v["wall_s"] or 0 for s, v in L.STEPS.items()}
TASK04_HIT_S = 10          # regate.sh task04 on a cache hit: key, npz hash, summarize, compare_native17 (s29 / s31 logs)
DECIDE_S = 3               # scoped decide: make_heat_sources + net_keys + step keys


def schedule(run: dict, scoped: bool, task04_hit: bool = False) -> dict:
    r = lambda s: run.get(s, True)
    t0 = (W["plan_board_only"] + W["zone_priority"] + W["build"]) if r("build") else 0
    t1 = (W["d5"] if r("d5") else 0) + W["probe_erc"]
    core = max(W["core_barrier"] if r("core_barrier") else 0, W["core_exports"] + W["core_dfm"] + W["core_bypass"])
    th = W["heat_sources"]
    if r("task04"):
        th += TASK04_HIT_S if task04_hit else W["task04"]
    if r("b3_study"):
        th += W["b3_study"] + W["ceiling_sweep"]
    if r("b3_ratings"):
        th += W["b3_ratings"]
    after_core = W["copper_key"] + (DECIDE_S if scoped else 0) + max(th, W["kelvin"], W["res_a"] + W["pi"] + W["return_path"] + W["spine_lock"])
    total = t0 + t1 + max(W["fit"], W["fab"], core + after_core) + W["card"]
    wm = 0.0
    for s, v in L.STEPS.items():
        if v["policy"] == "manual" or not r(s):
            continue
        sec = TASK04_HIT_S if (s == "task04" and task04_hit) else W[s]
        wm += sec * (v["workers"] or 1)
    return {"wall_min": round(total / 60, 1), "worker_min": round(wm / 60, 1), "critical_thermal_s": th}


def plan_run(paths: list[str], copper_changed: bool, same_board: bool) -> tuple[dict, dict]:
    keys_b = {s: "bench" for s in L.KEYED + ["necks", "ocp_pickup", "audit_rs", "core_barrier"]}
    keys_c = {s: ("cand" if copper_changed and s in L.KEYED else "bench") for s in keys_b}
    pl = L.plan(paths, keys_b, keys_c, None, rebuilt_board_differs=not same_board)
    return {s: d["do"] in ("RUN", "RUN?") for s, d in pl["steps"].items()}, pl


LANES = {
    "parts-only (MPN / value, same footprint and copper, heat unchanged)": {
        "paths": ["native-21/frozen/default.csv", "native-21/frozen/resolved-components.json", "frozen/default.csv",
                  "frozen/resolved-components.json", "native-21/verification/datasheet-ledger/ledger.json",
                  "validation-results/08-manufacturing-package/native-21/sourcing/STOCK-2026-10-13-addendum-sNN.csv"],
        "copper_changed": False, "same_board": False, "today_task04_hit": True, "today_b3_hit": True},
    "one-island layout (copper.json on a few nets)": {
        "paths": ["native-21/layout/copper.json"], "copper_changed": True, "same_board": False},
    "thermal model: B3 ratings script / firmware fan law": {
        "paths": ["validation-results/04-board-current-thermal/round5-native21/b3-ratings/b3_ratings_gate.py"],
        "copper_changed": False, "same_board": True, "today_task04_hit": True, "today_b3_hit": True},
    "thermal model: B3 solver (b3/thermal.py)": {
        "paths": ["validation-results/04-board-current-thermal/round5-native21/b3/thermal.py"],
        "copper_changed": False, "same_board": True},
    "thermal model: task-04 case runner": {
        "paths": ["validation-results/04-board-current-thermal/round5-native21/run_cases.py"],
        "copper_changed": False, "same_board": True},
    "desk / card input only (ledger row, EMI result, sourcing snapshot)": {
        "paths": ["native-21/verification/datasheet-ledger/ledger.json"], "copper_changed": False, "same_board": True,
        "today_task04_hit": True, "today_b3_hit": True},
    "gate script (return_path19.py)": {
        "paths": ["native-21/layout/gates/return_path19.py"], "copper_changed": False, "same_board": True,
        "today_task04_hit": True, "today_b3_hit": True},
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    a = ap.parse_args()
    out = {"full_chain_cold": schedule({}, False)}
    print(f"{'lane':70s} {'today':>16s} {'scoped':>16s}   (wall min / worker min)")
    print(f"{'full chain, cold caches (s43 measured 29.4 min)':70s} {out['full_chain_cold']['wall_min']:>7} / {out['full_chain_cold']['worker_min']:<6}")
    for name, ln in LANES.items():
        run, pl = plan_run(ln["paths"], ln["copper_changed"], ln["same_board"])
        sc = schedule(run, True)
        # today: chain.sh always rebuilds and reruns every gate; task 04 / B3 hit only on unchanged copper + model_key
        # (model_key covers task-04 and B3 scripts, heat, stack-up - not the ratings scripts); ratings always rerun
        today_run = {s: True for s in L.STEPS}
        today_run["b3_study"] = not ln.get("today_b3_hit", False)
        today_run["ceiling_sweep"] = today_run["b3_study"]
        td = schedule(today_run, False, task04_hit=ln.get("today_task04_hit", False))
        out[name] = {"today": td, "scoped": sc, "mode": pl["mode"],
                     "scoped_runs": sorted(s for s, v in run.items() if v and L.STEPS[s]["policy"] != "manual"),
                     "scoped_reuses": sorted(s for s, d in pl["steps"].items() if d["do"] == "REUSE")}
        print(f"{name:70s} {td['wall_min']:>7} / {td['worker_min']:<6} {sc['wall_min']:>7} / {sc['worker_min']:<6} {pl['mode']}")
    # recommendation (not in the patch): B3 legacy study + sweep beside the ratings solves instead of before them
    par = dict(W)
    th_par = W["heat_sources"] + W["task04"] + max(W["b3_study"] + W["ceiling_sweep"], W["b3_ratings"])
    t_par = (W["plan_board_only"] + W["zone_priority"] + W["build"] + W["d5"] + W["probe_erc"]
             + max(W["core_barrier"], 7) + W["copper_key"] + th_par + W["card"])
    out["full_chain_b3_parallel_to_ratings_min"] = round(t_par / 60, 1)
    print(f"{'full chain with B3 legacy + sweep in parallel with the ratings solves':70s} {out['full_chain_b3_parallel_to_ratings_min']:>7}")
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main()
