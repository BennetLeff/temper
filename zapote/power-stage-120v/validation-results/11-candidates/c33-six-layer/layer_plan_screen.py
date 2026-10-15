#!/usr/bin/env python3
"""Candidate 33 step 1: screen six-layer plane-role plans on the stage-32 copper before any routing.

    python3 layer_plan_screen.py COPPER_DUMP.json OUTDIR

For each plan below, the stage-32 copper dump (plot_copper.py --dump of runs-native21/s32/b2) is transformed the
way the plan would lay the board out, and native-21/layout/gates/return_path19.py runs on it under that plan's
stackup ($NATIVE21_STACKUP), so ADJ (nearest reference first) follows the plan's z.

What a transform can and cannot say:
  * "copy NET Lsrc -> Ldst" puts the FILLED stage-32 pours of NET on Lsrc onto Ldst as well. A KiCad fill of the
    same outline on an empty layer is at least that large (on Ldst it does not have to clear Lsrc's own tracks), so
    the copy under-states the new plane; it is a screen, not the board. The routed board is the evidence.
  * "move Lsrc -> Ldst" relabels every zone and track on Lsrc (plan B: today's In2 becomes In4).
  * "swap NET_a NET_b on La / Lb" exchanges two plane nets between two layers (plan A2: SELV ground under F.Cu).
Counts reported per plan: open reference changes (the scorecard's return_path_open_changes), stitched changes
(the same net referenced on both sides, with the nearest same-net via distance), wrong-reference samples on the
asserted nets (must stay 0) and the return_path19 verdict. Writes OUTDIR/<plan>.json and OUTDIR/screen.json.
"""
import copy
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIT = HERE.parents[2]
RP = UNIT / "native-21/layout/gates/return_path19.py"
S4 = UNIT / "native-21/stackup.json"
S6 = UNIT / "native-21/stackup-6L.json"
ISLANDS = ("n_ha", "n_hb", "n_ls", "ocp_kelvin_p")

PLANS = {
    "4L-s32": {"stack": S4, "ops": [], "what": "stage 32 as built (control: 18 open changes)"},
    "6L-A0": {"stack": S6, "ops": [], "what": "six layers, today's In1 / In2 roles, In3 / In4 empty"},
    "6L-A": {"stack": S6, "ops": [("copy", n, "In1.Cu", "In4.Cu") for n in ("v3v3",) + ISLANDS],
             "what": "In1 / In2 as today; In3 signal; In4 = image of In1's reference planes (v3v3 SELV, n_ha / n_hb / "
                     "n_ls / ocp_kelvin_p islands); no In4 under the switching copper"},
    "6L-A-islands": {"stack": S6, "ops": [("copy", n, "In1.Cu", "In4.Cu") for n in ISLANDS],
                     "what": "as A without the In4 v3v3 (islands only)"},
    "6L-A-selv": {"stack": S6, "ops": [("copy", "v3v3", "In1.Cu", "In4.Cu")], "what": "as A, In4 v3v3 only"},
    "6L-A2": {"stack": S6, "ops": [("swap", "v3v3", "In1.Cu", "selv_gnd", "In2.Cu")] +
              [("copy", n, "In1.Cu", "In4.Cu") for n in ("selv_gnd",) + ISLANDS],
              "what": "as A, but the SELV pair swapped: In1 selv_gnd (under F.Cu), In2 v3v3, In4 selv_gnd"},
    "6L-A3": {"stack": S6, "ops": [("copy", "selv_gnd", "In2.Cu", "In4.Cu")] +
              [("copy", n, "In1.Cu", "In4.Cu") for n in ISLANDS],
              "what": "as A, but In4 SELV = selv_gnd (B over ground, F over v3v3, as today)"},
    "6L-B": {"stack": S6, "ops": [("move", "In2.Cu", "In4.Cu")],
             "what": "PLAN.md's F / In1 plane / In2 sig / In3 sig / In4 plane / B: today's In2 (bus_p, selv_gnd) on In4"},
}


def transform(d, ops):
    d = copy.deepcopy(d)
    for op in ops:
        if op[0] == "copy":
            _, net, src, dst = op
            d["zones"] += [dict(z, layer=dst) for z in d["zones"] if z["net"] == net and z["layer"] == src]
        elif op[0] == "move":
            _, src, dst = op
            for z in d["zones"]:
                if z["layer"] == src:
                    z["layer"] = dst
            for t in d["tracks"]:
                if t["layer"] == src:
                    t["layer"] = dst
        elif op[0] == "swap":
            _, na, la, nb, lb = op
            for z in d["zones"]:
                if z["net"] == na and z["layer"] == la:
                    z["layer"] = lb
                elif z["net"] == nb and z["layer"] == lb:
                    z["layer"] = la
        else:
            raise ValueError(op)
    return d


def main():
    dump, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    base = json.loads(dump.read_text())
    screen = {"dump": str(dump), "plans": {}}
    for name, plan in PLANS.items():
        dp = out / f"{name}-dump.json"
        dp.write_text(json.dumps(transform(base, plan["ops"])))
        env = dict(os.environ, NATIVE21_STACKUP=str(plan["stack"]), PYTHONHASHSEED="0")
        r = subprocess.run([sys.executable, str(RP), str(dp), "--json", str(out / f"{name}.json")], env=env,
                           capture_output=True, text=True)
        rp = json.loads((out / f"{name}.json").read_text())
        opened, stitched, wrong = [], [], {}
        for net, s in rp["signals"].items():
            if not isinstance(s, dict) or "transitions" not in s:
                continue
            opened += [dict(o, net=net) for o in s["open_reference_changes"]]
            stitched += [dict(t["stitch"], net=net, at=t["at"]) for t in s["transitions"] if "stitch" in t]
            if s["wrong_reference_samples"]:
                wrong[net] = s["wrong_reference_samples"]
        screen["plans"][name] = {"what": plan["what"], "ops": plan["ops"], "stack": plan["stack"].name,
                                 "open_changes": len(opened), "open": opened, "stitched": len(stitched),
                                 "stitch_mm_max": max((s["mm"] or 1e9 for s in stitched), default=None),
                                 "stitched_list": stitched, "wrong_reference_samples": wrong,
                                 "pass": rp["pass"], "failures": rp["failures"]}
        dp.unlink()
        print(f"{name:14s} open {len(opened):2d}  stitched {len(stitched):2d}  wrong {sum(wrong.values()):4d} "
              f"{'PASS' if rp['pass'] else 'FAIL ' + '; '.join(rp['failures'])[:160]}")
    (out / "screen.json").write_text(json.dumps(screen, indent=1) + "\n")


if __name__ == "__main__":
    main()
