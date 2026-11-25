#!/usr/bin/env python3
"""Stage 56 scope: which of the 2026-11-24 plan's power-board items are better on every count (desk, no copper).

    python3 -I validation-results/11-candidates/c56-s56-scope/scripts/s56_scope.py [--check]

Run from zapote/power-stage-120v. Rail ranges and resistor tolerances come from the pin gate's registry, thermal margins from
the B3 margins of board s55, the R5-trip window from c53-r5-trip. Module limits: RECOM R24C2T25/R Rev. 1-2024 (VIN 21-27 V and
abs max 32 V, UVLO rising <= 21 V, p.2; CTRL 0-5.5 V, on >= 2.1 V, pin current <= 10 uA, p.7; abs max 7 V, p.2).
--check: exit 1 if results/s56-scope.json differs from a fresh run.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
OUT = HERE / "results/s56-scope.json"
reg = json.loads(Path("native-21/layout/gates/pin_absmax_registry.json").read_text())
v24 = reg["nets"]["v24_raw"]
tol = {k: v["tol"] for k, v in reg["resistor_tolerance"].items()}
LO, HI, FAULT = v24["lo"], v24["hi"], v24["fault"]["hi"]
VIN_MIN, VIN_ABS, CTRL_REC, CTRL_ABS, CTRL_ON, I_CTRL = 21.0, 32.0, 5.5, 7.0, 2.1, 10e-6
TOP, T_TOP = 100e3, tol["0603WAF"]


def ctrl(bot, t_bot):
    def v(vin, up, pin):
        s = 1 if up else -1
        rt, rb = TOP * (1 - s * T_TOP), bot * (1 + s * t_bot)
        return vin * rb / (rt + rb) - pin * rt * rb / (rt + rb)
    r = {"V_min_at_rail_min": v(LO, False, I_CTRL), "V_max_at_rail_max": v(HI, True, 0), "V_max_at_PS2_clamp": v(FAULT, True, 0)}
    r["inside_recommended_5V5_in_the_fault"] = r["V_max_at_PS2_clamp"] <= CTRL_REC
    r["headroom_to_abs_max_V"] = CTRL_ABS - r["V_max_at_PS2_clamp"]
    r["over_enable_threshold_V"] = r["V_min_at_rail_min"] - CTRL_ON
    return r


divs = {"27k fitted (0603WAF2702T5E)": ctrl(27e3, tol["0603WAF"]), "16k (RT0603BRD0716KL, R34's line)": ctrl(16e3, tol["RT0603BRD07"])}

# two series rectifiers ahead of U41 / U42 only (1 A silicon, datasheet VF <= 1.1 V at 1 A, the only guaranteed figure)
VF_MAX = 1.1
diodes = {"input_margin_now_V": LO - VIN_MIN, "input_margin_with_two_diodes_V": LO - 2 * VF_MAX - VIN_MIN,
          "over_abs_max_at_PS2_clamp_now_V": FAULT - VIN_ABS,
          "drop_needed_in_the_fault_V": FAULT - VIN_ABS,
          "drop_guaranteed_in_the_fault_V": 0.0,
          "note": "no datasheet guarantees a minimum VF at the fault current (modules off on OVLO: <= 0.7 mA standby each)"}

m = json.loads(Path("validation-results/04-board-current-thermal/round5-native21/b3-ratings/margins.json").read_text())
rel = [r for r in m["cases"]["c17.5_h10"] if r.get("gated")]
rel.sort(key=lambda r: r["margin_k"])
u26 = {c: next(r["margin_k"] for r in rows if r["item"].startswith("U26: TJ")) for c, rows in m["cases"].items()}
I_U26 = 0.129
dropper = {"R_ohm": 20, "moved_W": 20 * I_U26 ** 2, "release_margin_K": rel[0]["margin_k"], "release_bound_by": rel[0]["item"],
           "gated_rows_at_or_below_U26": [r["item"][:40] for r in rel if r["margin_k"] <= u26["c17.5_h10"]], "U26_margin_K": u26,
           "V_in_U26_min": LO - 20 * I_U26 * 1.0}

b = json.loads(Path("validation-results/11-candidates/c53-r5-trip/results-budget.json").read_text())
trip = {"low_corner_over_highest_hold_pct": b["margin_over_highest_hold_low_corner_pct"],
        "worst_case_high_corner_under_15A_cap": b["under_15A_cap_high_corner_worst"],
        "rss_high_corner_under_15A_cap": b["under_15A_cap_high_corner_rss"]}
res = {"board": m["board_sha256"], "ctrl_divider": divs, "series_diodes": diodes, "u26_dropper": dropper, "r5_trip": trip}


def rnd(o):
    return {k: rnd(v) for k, v in o.items()} if isinstance(o, dict) else round(o, 4) if isinstance(o, float) else o


text = json.dumps(rnd(res), indent=1) + "\n"
if "--check" in sys.argv:
    sys.exit(0 if OUT.read_text() == text else "results/s56-scope.json is stale")
OUT.write_text(text)
print(text)
