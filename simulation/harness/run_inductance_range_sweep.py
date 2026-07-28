#!/usr/bin/env python3
"""L-range sweep at the COMMITTED, FIXED f_switching -- does the design
survive tank-coil-inductance uncertainty, or only work at the single
assumed L = 150uH?

Context (docs/evidence/2026-07-27-inductance-range-sweep.md is the full
writeup this script's evidence feeds): every electrical conclusion in
this project currently rests on an ASSUMED L = 150uH
(elec/src/modules.ato's `inductor_conn` is an unplaced Litz placeholder;
no document specifies or measures L). At L=150uH, f_sw=47kHz
(main.ato:91, F_SWITCHING_NOMINAL_HZ in run_zvs_sweep.py), the ZVS margin
is 0.84% -- see docs/evidence/2026-07-27-pan-preset-correction.md Sec 4.5.
That is tight enough that inductance uncertainty could plausibly dominate
it entirely, and the failure mode is not degraded performance but hard-
switching a 1200V IGBT half-bridge.

This script re-runs the ZVS margin / power / tank-current / tank-cap-
voltage analysis at a RANGE of L (docs/evidence/2026-07-27-inductance-
range-sweep.md Sec 1 derives [L_min, L_max]), holding F_SW FIXED at the
COMMITTED 47kHz value (main.ato:91) -- this is the physically correct
test for "does the single committed number survive coil-to-coil L
variation," since a fabricated coil's L cannot be changed after the fact
and there is no confirmed closed-loop PLL retuning implemented anywhere
in this project's simulation model (only a swept `ratio` parameter, which
requires already knowing L). A second, clearly-separated mode
(--mode ratio-track) explores the ALTERNATIVE control strategy (retune
f_sw to hold a fixed ratio over the self-consistent LOADED resonance,
reusing run_tank_coil_sweep.f_res_loaded_hz) to answer "what frequency
range would tracking require, and does that fit the declared 20-100kHz
assertion window (main.ato:92)."

Reuses run_zvs_sweep.py (PAN_PRESETS, override_params,
run_ngspice_on_text, parse_measurements, compute_point_result,
V_BUS_FULL, C_TANK_F, F_SWITCHING_NOMINAL_HZ) and
run_tank_coil_sweep.py (f_res_hz, f_res_loaded_hz) directly -- no
reimplementation, per this project's own convention (see that script's
own docstring).

Additional per-point figure not captured by either base script:
tank-capacitor peak voltage, from the .cir's own `v_ctank_max_last` /
`v_ctank_min_last` .meas lines (zvs_margin_sweep.cir, present since the
bus-capacitor-voltage-rating check was added; NOT previously surfaced by
either harness's own reporting code). `parse_measurements` already
captures every `.meas`-printed name via a blanket regex, so these two
values are already inside the returned dict -- just never read out
before this script.

Usage
-----
    uv run --no-sync python simulation/harness/run_inductance_range_sweep.py \\
        --L-list-uh 50,70,90,110,130,150,175,200,225,250 \\
        --pans cast_iron,stainless,aluminum,no_pan \\
        --mode fixed-fsw \\
        --out docs/evidence/2026-07-27-inductance-range-sweep-fixed-fsw.json

    uv run --no-sync python simulation/harness/run_inductance_range_sweep.py \\
        --L-list-uh 50,70,90,110,130,150,175,200,225,250 \\
        --pans cast_iron,stainless \\
        --mode ratio-track --ratio 1.25 \\
        --out docs/evidence/2026-07-27-inductance-range-sweep-ratio-track.json

Run in the FOREGROUND. Grid size is caller-controlled specifically so it
can be kept small (no backgrounding, per operating instructions).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_zvs_sweep as base  # noqa: E402  (reuse, not reimplement)
import run_tank_coil_sweep as tank  # noqa: E402  (reuse f_res_loaded_hz)

REPO_ROOT = base.REPO_ROOT
C_TANK_F = base.C_TANK_F
V_BUS_FULL = base.V_BUS_FULL
F_SW_COMMITTED_HZ = base.F_SWITCHING_NOMINAL_HZ  # 47kHz, main.ato:91

PAN_PRESETS_BY_NAME = {n: (k, r, l2, s) for n, k, r, l2, s in base.PAN_PRESETS}

# Tank-capacitor part rating -- committed part per elec/src/modules.ato
# (c_tank1/c_tank2, FKP1U021507E00JSSD, both lines declare
# `voltage_rating = 1600V`; modules.ato also declares a design intent
# `v_tank_peak = 400V` with `assert c_tank1.voltage_rating >= v_tank_peak
# * 1.43` i.e. a committed 572V design floor against a 1600V-rated part).
# Quoted here only for the margin comparison printed in the evidence JSON.
C_TANK_RATED_V = 1600.0  # elec/src/modules.ato:448/455 c_tank1/c_tank2.voltage_rating


def run_one_point(l_uh: float, pan_name: str, f_sw_hz: float, base_text: str) -> dict:
    pan_k, pan_rpan, pan_l2, _note = PAN_PRESETS_BY_NAME[pan_name]
    l_h = l_uh * 1e-6
    fres_unloaded = tank.f_res_hz(l_h)
    fres_loaded = tank.f_res_loaded_hz(l_h, pan_k, pan_rpan, pan_l2)
    overrides = {
        "F_SW": f_sw_hz,
        "PAN_K": pan_k,
        "PAN_RPAN": pan_rpan,
        "PAN_L1": f"{l_uh}u",
        "PAN_L2": pan_l2,
    }
    cir_text = base.override_params(base_text, overrides)
    stdout, stderr, code = base.run_ngspice_on_text(cir_text)
    point = {
        "l_uh": l_uh,
        "pan_preset": pan_name,
        "pan_k": pan_k,
        "pan_rpan_ohm": pan_rpan,
        "pan_l2_h": pan_l2,
        "f_sw_hz": round(f_sw_hz, 1),
        "f_res_unloaded_hz": round(fres_unloaded, 1),
        "f_res_loaded_hz": round(fres_loaded, 1),
        "ratio_f_sw_over_f_res_loaded": round(f_sw_hz / fres_loaded, 4),
        "ratio_f_sw_over_f_res_unloaded": round(f_sw_hz / fres_unloaded, 4),
    }
    if code != 0:
        point["measured"] = False
        point["reason"] = f"ngspice exited {code}: {stderr[-500:]}"
        return point
    try:
        meas = base.parse_measurements(stdout)
    except base.HarnessError as exc:
        point["measured"] = False
        point["reason"] = str(exc)[:1000]
        return point
    zvs = base.compute_point_result(pan_name, pan_k, pan_rpan, f_sw_hz, meas, pan_l2_h=pan_l2)
    point.update(
        {
            "measured": True,
            "margin_pct": zvs["margin_pct"],
            "worse_switch": zvs["worse_switch"],
            "label": zvs["label"],
            "converged": zvs["converged"],
            "convergence_delta_v": zvs["convergence_delta_v"],
            "i_tank_rms_a": zvs["i_tank_rms_a"],
            "i_tank_pk_a": zvs["i_tank_pk_a"],
        }
    )
    if "i_pan_rms_last" in meas:
        i_pan_rms = meas["i_pan_rms_last"]
        point["i_pan_rms_a"] = round(i_pan_rms, 4)
        point["p_pan_w"] = round(i_pan_rms * i_pan_rms * pan_rpan, 2)
    # Tank-cap peak voltage -- v_ctank_max/min_last already present in the
    # committed .cir (see module docstring); parse_measurements captures
    # them via its blanket regex even though neither base script reads
    # them out. Report both directions and the larger magnitude.
    if "v_ctank_max_last" in meas and "v_ctank_min_last" in meas:
        v_max = meas["v_ctank_max_last"]
        v_min = meas["v_ctank_min_last"]
        v_pk = max(abs(v_max), abs(v_min))
        point["v_ctank_max_v"] = round(v_max, 3)
        point["v_ctank_min_v"] = round(v_min, 3)
        point["v_ctank_pk_v"] = round(v_pk, 3)
        point["v_ctank_pk_margin_x"] = round(C_TANK_RATED_V / v_pk, 3) if v_pk else None
    return point


def run_grid(l_list_uh, pan_names, mode: str, fixed_ratio: float, base_text: str) -> list[dict]:
    results = []
    total = len(l_list_uh) * len(pan_names)
    done = 0
    for l_uh in l_list_uh:
        for pan_name in pan_names:
            done += 1
            if mode == "fixed-fsw":
                f_sw_hz = F_SW_COMMITTED_HZ
            elif mode == "ratio-track":
                pan_k, pan_rpan, pan_l2, _n = PAN_PRESETS_BY_NAME[pan_name]
                fres_loaded = tank.f_res_loaded_hz(l_uh * 1e-6, pan_k, pan_rpan, pan_l2)
                f_sw_hz = fres_loaded * fixed_ratio
            else:
                raise ValueError(f"unknown mode {mode!r}")
            print(f"[{done}/{total}] mode={mode} L={l_uh}uH pan={pan_name} f_sw={f_sw_hz:.0f}Hz ...", end=" ")
            point = run_one_point(l_uh, pan_name, f_sw_hz, base_text)
            point["mode"] = mode
            if point.get("measured"):
                extra = f" v_ctank_pk={point.get('v_ctank_pk_v', 'n/a')}V" if "v_ctank_pk_v" in point else ""
                print(
                    f"margin={point['margin_pct']:.2f}% ({point['label']}) "
                    f"i_pk={point['i_tank_pk_a']:.2f}A i_rms={point['i_tank_rms_a']:.2f}A "
                    f"P={point.get('p_pan_w', 'n/a')}W ratio={point['ratio_f_sw_over_f_res_loaded']:.3f}"
                    f"{extra}"
                )
            else:
                print(f"UNMEASURED ({point.get('reason', '')[:80]})")
            results.append(point)
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--L-list-uh", required=True, help="Comma-separated coil inductances in uH")
    ap.add_argument("--pans", required=True, help="Comma-separated pan preset names, or 'all'")
    ap.add_argument("--mode", choices=["fixed-fsw", "ratio-track"], default="fixed-fsw")
    ap.add_argument("--ratio", type=float, default=1.25, help="Only used in ratio-track mode")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    if not base.MASTER_CIR.exists():
        print(f"ERROR: netlist not found: {base.MASTER_CIR}", file=sys.stderr)
        return 1
    if shutil.which("ngspice") is None:
        print("ERROR: ngspice not found on PATH.", file=sys.stderr)
        return 1

    l_list_uh = [float(x) for x in args.L_list_uh.split(",")]
    pan_names = (
        list(PAN_PRESETS_BY_NAME.keys())
        if args.pans.strip().lower() == "all"
        else [p.strip() for p in args.pans.split(",")]
    )
    for p in pan_names:
        if p not in PAN_PRESETS_BY_NAME:
            print(f"ERROR: unknown pan preset {p!r}; valid: {list(PAN_PRESETS_BY_NAME)}", file=sys.stderr)
            return 1

    base_text = base.MASTER_CIR.read_text()

    results = run_grid(l_list_uh, pan_names, args.mode, args.ratio, base_text)
    measured = [r for r in results if r.get("measured")]
    converged = [r for r in measured if r.get("converged")]
    held = [r for r in measured if r.get("label") == "zvs_held"]
    lost = [r for r in measured if r.get("label") == "zvs_lost"]

    evidence = {
        "schema_version": 1,
        "provenance": base.collect_provenance(REPO_ROOT),
        "measurement_date": _dt.date.today().isoformat(),
        "harness": "simulation/harness/run_inductance_range_sweep.py",
        "netlist": "simulation/harness/nets/zvs_margin_sweep.cir",
        "reused_from": (
            "simulation/harness/run_zvs_sweep.py (override_params, "
            "run_ngspice_on_text, parse_measurements, compute_point_result, "
            "PAN_PRESETS, F_SWITCHING_NOMINAL_HZ); "
            "simulation/harness/run_tank_coil_sweep.py (f_res_hz, "
            "f_res_loaded_hz)"
        ),
        "mode": args.mode,
        "ratio_used_if_ratio_track": args.ratio if args.mode == "ratio-track" else None,
        "f_sw_committed_hz_if_fixed_fsw": F_SW_COMMITTED_HZ if args.mode == "fixed-fsw" else None,
        "c_tank_f": C_TANK_F,
        "c_tank_rated_v": C_TANK_RATED_V,
        "invocation_args": {"L_list_uh": l_list_uh, "pans": pan_names, "mode": args.mode, "ratio": args.ratio},
        "grid": {
            "total_points": len(results),
            "measured_points": len(measured),
            "converged_points": len(converged),
            "zvs_held_points": len(held),
            "zvs_lost_points": len(lost),
        },
        "results": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(evidence, indent=2) + "\n")
    print(f"\n{len(measured)}/{len(results)} measured, {len(converged)} converged, "
          f"{len(held)} zvs_held, {len(lost)} zvs_lost.")
    print(f"Evidence written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
