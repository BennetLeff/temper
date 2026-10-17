#!/usr/bin/env python3
"""Decision inputs for the 5 x KNSCHA MMK104J3DF1KN208G2 bank, from bank_air_cand.py's physics (imported, unchanged).

    python3 -I scripts/decision_inputs.py   -> results/decision_inputs.json + .md (exit 1 if the 28 A control fails)

(1) Tank-ceiling steps 18 / 20 / 22 / 24 / 26 / 28 A under the S24 design flow (jets + base; 3.07 m/s along x at the
    bank, bulk rise 3.7 K; h20 pads @61 C and h15 pads @55 C, the two declared points of bank_air_cand.py). Per step:
      vendor ratio = I_tank * s_worst / I_allow(35 kHz)                 (pure current ratio; flow does not enter)
      gate         = bank_air eff, worst over both points, positions and G_board bounds; pad heat off (producer method)
      gate + gap   = the same with the gap-channel credit (bank_air_cand.g_gap); pad heat off
    Pads at a step below 28 A, two cases:
      'pads28'  the 28 A jetmix pads unchanged (upper bound: every pad solve at lower current is cooler)
      'scaled'  pad rise above the bay scaled by the same-board B3 still-air solves c17.5 / c22 / c28 h10 (board 4876c42e),
                linear in I^2 between them (an estimate: the ratio is taken from h10, not from the jetmix flow)
    The step passes when gate <= 1.00 and T_op <= Top,max, and the vendor ratio <= 0.85.
(2) 28 A: the bank-column air velocity v along x at which the gate reaches 1.00, at each point separately, by bisection.
    Bulk rise scales as 3.7 K * 3.07 / v (same heat, flow ~ v). Pads are held at the S24 solve (3.07 m/s); above
    3.07 m/s that is conservative (more flow also cools the copper). Below 3.07 m/s it is NOT conservative and is flagged.
"""
import importlib.util
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("bac", ROOT / "scripts/bank_air_cand.py")
bac = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bac)

PS = Path("/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v")
J = "/Users/bennet/Desktop/temper/worktrees/runs-native21/s49/c49/b3-bank-air/jetmix"
REL = ("/Users/bennet/Desktop/temper/worktrees/ps-selv/zapote/power-stage-120v/validation-results/04-board-current-thermal/"
       "round5-native21/b3-ratings/runs")
STEPS = (18.0, 20.0, 22.0, 24.0, 26.0, 28.0)
H10 = (17.5, 22.0, 28.0)


def pad_rise_h10():
    out = {}
    for i in H10:
        d = json.loads(Path(f"{REL}/c{i:g}_h10_p0p25.json").read_text())
        q = {x["ref"]: x["pad_max_padmean_c"] for x in d["parts"]}
        out[i] = {"board": d.get("board_sha256", "")[:8], "bay_c": d.get("bay_c"),
                  "rise": {r: q[r] - d.get("bay_c", 61.0) for r in bac.BANK}}
    return out


def scale_factor(h10, i, ref):
    """rise(i) / rise(28) from the h10 solves, linear in I^2 between the solved currents (clamped at the ends)."""
    xs = [(k * k, h10[k]["rise"][ref]) for k in H10]
    x = i * i
    if x <= xs[0][0]:
        y = xs[0][1] * x / xs[0][0]
    else:
        y = xs[-1][1]
        for (x0, y0), (x1, y1) in zip(xs, xs[1:]):
            if x <= x1:
                y = y0 + (y1 - y0) * (x - x0) / (x1 - x0)
                break
    return y / xs[-1][1]


def main():
    enc = json.loads((PS / "validation-results/11-candidates/airflow28-2026-10-16/results/enclosure.json").read_text())
    e20 = enc["jetmix_base"]["h20"][bac.PATH]
    v0, rise0 = e20["v_turbulent_m_s"], e20["bulk_rise_K_gap10"]
    p61, _ = bac.pads_from(f"{J}/bay61/c28_h20_jet100_p0p25.json", f"{J}/bay61/c28_h20_jet100_p0p5.json", 61)
    p55, _ = bac.pads_from(f"{J}/bay55/c28_h15_jet100_p0p25.json", f"{J}/bay55/c28_h15_jet100_p0p5.json", 55)
    cands = json.loads((ROOT / "data/candidates.json").read_text())["candidates"]
    c = dict(next(x for x in cands if x["id"] == "knscha"))
    c.setdefault("gap_mm", round(c["pitch"] - c["w"], 2))
    s = bac.share(c)
    h10 = pad_rise_h10()

    def pts_at(v, pads61, pads55):
        r = rise0 * v0 / v
        return [("@61 h20", 61, v, r, pads61), ("@55 h15", 55, v, r, pads55)]

    def run(i, pts, gap):
        bac.I_TANK = i
        g, _ = bac.run_forced(c, pts, gap_credit=gap, pad_heat=False, k_pad=0.0, p_ref=0.0)
        return g

    out = {"part": c["mpn"], "n": c["n"], "worst_share": round(s, 4), "I_allow_35k_A": c["I35"],
           "flow": {"v_m_s": v0, "bulk_rise_K": rise0, "path": bac.PATH},
           "h10_scaling_solves": {f"{k:g}": {"board": v["board"], "bay_c": v["bay_c"]} for k, v in h10.items()},
           "steps": [], "velocity_28A": {}}
    for i in STEPS:
        vr = i * s / c["I35"]
        row = {"I_tank_A": i, "I_part_A": round(i * s, 3), "vendor_ratio_35k": round(vr, 3)}
        for mode in ("pads28", "scaled"):
            if mode == "pads28":
                a, b = p61, p55
            else:
                a = {r: 61 + (p61[r] - 61) * scale_factor(h10, i, r) for r in p61}
                b = {r: 55 + (p55[r] - 55) * scale_factor(h10, i, r) for r in p55}
            for gap in (False, True):
                g = run(i, pts_at(v0, a, b), gap)
                key = f"{mode}_{'gap' if gap else 'strict'}"
                row[key] = {"gate": g["eff"], "T_op_max_C": g["T_op_max_C"], "gate_pass": g["passes"],
                            "step_pass": g["passes"] and vr <= 0.85}
        out["steps"].append(row)
    for mode in ("pads28", "scaled"):
        for gap in ("strict", "gap"):
            ok = [r["I_tank_A"] for r in out["steps"] if r[f"{mode}_{gap}"]["step_pass"]]
            okg = [r["I_tank_A"] for r in out["steps"] if r[f"{mode}_{gap}"]["gate_pass"]]
            out[f"highest_step_{mode}_{gap}"] = max(ok) if ok else None
            out[f"highest_gate_only_step_{mode}_{gap}"] = max(okg) if okg else None
    out["tank_A_at_vendor_0.85"] = round(0.85 * c["I35"] / s, 2)

    # (2) velocity for gate = 1.00 at 28 A, each point alone
    for gap in (False, True):
        for label, bay, pads in (("@61 h20", 61, p61), ("@55 h15", 55, p55)):
            def gate(v):
                bac.I_TANK = 28.0
                g, _ = bac.run_forced(c, [(label, bay, v, rise0 * v0 / v, pads)], gap_credit=gap, pad_heat=False,
                                      k_pad=0.0, p_ref=0.0)
                return g["eff"] if g["passes"] else max(g["eff"], 1.0 + 1e-9)
            lo, hi = 0.3, 60.0
            res = {"gate_at_3.07": gate(v0)}
            if gate(hi) > 1.0:
                res["v_for_gate_1_m_s"] = None
                res["note"] = f"gate {gate(hi):.3f} still > 1 at {hi} m/s"
            elif gate(lo) <= 1.0:
                res["v_for_gate_1_m_s"] = f"<= {lo}"
            else:
                for _ in range(80):
                    m = math.sqrt(lo * hi)
                    lo, hi = (lo, m) if gate(m) <= 1.0 else (m, hi)
                res["v_for_gate_1_m_s"] = round(hi, 2)
                res["pads_held_at_3.07_conservative"] = hi >= v0
            out["velocity_28A"][f"{'gap' if gap else 'strict'} {label}"] = res
    bac.I_TANK = 28.0
    # control: strict 28 A with the S24 pads must equal bank_air_cand's gate (pad heat off)
    ref = json.loads((ROOT / "results/bank_air_cand.json").read_text())["candidates"]["knscha"]["bank_air_28A_35k_gate"]["eff"]
    got = out["steps"][-1]["pads28_strict"]["gate"]
    out["control"] = {"bank_air_cand_gate": ref, "here": got, "pass": abs(ref - got) <= 0.002}
    (ROOT / "results/decision_inputs.json").write_text(json.dumps(out, indent=1) + "\n")
    L = ["| tank A | I part A | vendor ratio 35 kHz | gate strict (pads28 / scaled) | gate + gap (pads28 / scaled) |",
         "|---|---|---|---|---|"]
    for r in out["steps"]:
        L.append(f"| {r['I_tank_A']:g} | {r['I_part_A']} | {r['vendor_ratio_35k']} | {r['pads28_strict']['gate']} / "
                 f"{r['scaled_strict']['gate']} | {r['pads28_gap']['gate']} / {r['scaled_gap']['gate']} |")
    L += ["", "Highest step with gate <= 1.00 and vendor <= 0.85: " + ", ".join(
        f"{m}/{g} {out[f'highest_step_{m}_{g}']}" for m in ("pads28", "scaled") for g in ("strict", "gap")),
          "Highest step, gate only: " + ", ".join(
        f"{m}/{g} {out[f'highest_gate_only_step_{m}_{g}']}" for m in ("pads28", "scaled") for g in ("strict", "gap")),
          f"Vendor ratio 0.85 is reached at tank {out['tank_A_at_vendor_0.85']} A (current only; no flow term).", "",
          "28 A velocity along x for gate 1.00 (pads held at the 3.07 m/s solve; bulk rise 3.7 K x 3.07 / v):"]
    for k, v in out["velocity_28A"].items():
        L.append(f"- {k}: gate at 3.07 m/s {v['gate_at_3.07']}, v for 1.00 = {v['v_for_gate_1_m_s']}"
                 + (f" ({'conservative' if v.get('pads_held_at_3.07_conservative') else 'BELOW 3.07: pads held, not conservative'})"
                    if "pads_held_at_3.07_conservative" in v else "") + (f" {v['note']}" if "note" in v else ""))
    L.append(f"\nControl (strict 28 A = bank_air_cand gate): {out['control']}")
    (ROOT / "results/decision_inputs.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    sys.exit(0 if out["control"]["pass"] else 1)


if __name__ == "__main__":
    main()
