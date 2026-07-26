#!/usr/bin/env python3
"""L x f_sw x pan sweep for tank-coil inductance specification.

Extends simulation/harness/run_zvs_sweep.py (imported, not reimplemented)
for docs/hardware/TANK_COIL_SPECIFICATION.md. run_zvs_sweep.py's own grid
only ever swept f_sw, holding the coil inductance fixed at pan_load.sub's
80uH default -- because elec/src/modules.ato's ResonantTank does not
specify a coil inductance at all (`inductor_conn` is an unplaced Litz
placeholder). This script adds L (pan_load.sub's PAN_L1 parameter, which
IS the coil inductance in this model -- there is no separate "coil"
component) as a second swept axis, and adds a POWER measurement the
original sweep did not need for its ZVS-only question.

Power measurement
------------------
zvs_margin_sweep.cir was extended (one .meas line, see its own comment)
to report i_pan_rms_last: the RMS current through pan_load.sub's
PANLOAD_TRANSFORMER secondary loop (L_sec -> R_pan -> V_short, all in
series, same current throughout), read via ngspice's subcircuit-internal
branch-current naming (`v.x_pan.v_short#branch`), verified empirically
against a standalone probe deck (not by assumption -- ngspice's
`i(x_pan.v_short)` syntax does NOT work, see the .cir comment for the
error). R_pan is the only dissipative element in that loop, so:

    P_pan_w = i_pan_rms_last^2 * RPAN

is the real power delivered into the pan-load model. This is reported as
"power delivered to the pan" throughout -- it is a MODEL quantity, not a
calibrated wall-power or induction-heating figure; see
TANK_COIL_SPECIFICATION.md for the fidelity bound (PANLOAD_TRANSFORMER's
secondary inductance L2 has no per-material documentation in pan_load.sub
and is left at its own 1uH default, exactly as run_zvs_sweep.py did).

Sweep axis: L_TARGET is the coil's absolute inductance in uH; it is
written to the deck's PAN_L1 parameter (F_SW is also overridden, exactly
as run_zvs_sweep.py already does for both). No other .cir change was made
beyond the one .meas line described above -- this script reuses
override_params/run_ngspice_on_text/parse_measurements-style parsing from
run_zvs_sweep.py directly.

Usage
-----
    uv run python simulation/harness/run_tank_coil_sweep.py \\
        --L-list-uh 70,80,90,100,110,120,130,140,150 \\
        --ratio-list 1.00,1.02,1.05,1.08,1.12,1.20,1.30 \\
        --pans cast_iron \\
        --out docs/evidence/<date>-tank-coil-L-sweep-phase1.json

    uv run python simulation/harness/run_tank_coil_sweep.py \\
        --L-list-uh 90,100,110 \\
        --ratio-list 1.00,1.03,1.06,1.10,1.15,1.25 \\
        --pans cast_iron,stainless,aluminum,no_pan \\
        --out docs/evidence/<date>-tank-coil-L-sweep-phase2.json

Run in the FOREGROUND. Grid size is caller-controlled specifically so it
can be kept small per operating instructions (no backgrounding).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_zvs_sweep as base  # noqa: E402  (reuse, not reimplement)

REPO_ROOT = base.REPO_ROOT
C_TANK_F = base.C_TANK_F  # 300nF, committed and fixed (modules.ato:391,398)

PAN_PRESETS_BY_NAME = {n: (k, r, s) for n, k, r, s in base.PAN_PRESETS}


def f_res_hz(l_henries: float) -> float:
    return 1.0 / (2 * math.pi * math.sqrt(l_henries * C_TANK_F))


def run_grid(l_list_uh, ratio_list, pan_names, base_text):
    results = []
    total = len(l_list_uh) * len(ratio_list) * len(pan_names)
    done = 0
    for l_uh in l_list_uh:
        l_h = l_uh * 1e-6
        fres = f_res_hz(l_h)
        for ratio in ratio_list:
            f_sw = fres * ratio
            for pan_name in pan_names:
                pan_k, pan_rpan, _note = PAN_PRESETS_BY_NAME[pan_name]
                done += 1
                # override_params does a literal ".param NAME = value" replace;
                # ngspice needs a unit suffix on PAN_L1 (it's declared "80u" in
                # the deck) or a fully-expanded float. Use an explicit
                # micro-suffixed string so this matches the deck's own style.
                overrides = {
                    "F_SW": f_sw,
                    "PAN_K": pan_k,
                    "PAN_RPAN": pan_rpan,
                    "PAN_L1": f"{l_uh}u",
                }
                cir_text = base.override_params(base_text, overrides)
                stdout, stderr, code = base.run_ngspice_on_text(cir_text)
                point = {
                    "l_uh": l_uh,
                    "f_res_hz": round(fres, 1),
                    "ratio_f_sw_over_f_res": ratio,
                    "f_sw_hz": round(f_sw, 1),
                    "pan_preset": pan_name,
                    "pan_k": pan_k,
                    "pan_rpan_ohm": pan_rpan,
                }
                print(
                    f"[{done}/{total}] L={l_uh}uH ratio={ratio} f_sw={f_sw:.0f}Hz "
                    f"pan={pan_name} ...",
                    end=" ",
                )
                if code != 0:
                    point["measured"] = False
                    point["reason"] = f"ngspice exited {code}: {stderr[-500:]}"
                    print("UNMEASURED (ngspice nonzero exit)")
                    results.append(point)
                    continue
                try:
                    meas = base.parse_measurements(stdout)
                except base.HarnessError as exc:
                    point["measured"] = False
                    point["reason"] = str(exc)[:1000]
                    print("UNMEASURED (parse/convergence failure)")
                    results.append(point)
                    continue
                # i_pan_rms_last requires the extended .cir; treat its
                # absence as UNMEASURED rather than crash the whole grid.
                if "i_pan_rms_last" not in meas:
                    point["measured"] = False
                    point["reason"] = (
                        "i_pan_rms_last missing from ngspice output -- "
                        "the .cir does not have the pan-power .meas line"
                    )
                    print("UNMEASURED (no power measurement)")
                    results.append(point)
                    continue
                zvs = base.compute_point_result(pan_name, pan_k, pan_rpan, f_sw, meas)
                i_pan_rms = meas["i_pan_rms_last"]
                p_pan_w = i_pan_rms * i_pan_rms * pan_rpan
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
                        "i_pan_rms_a": round(i_pan_rms, 4),
                        "p_pan_w": round(p_pan_w, 2),
                    }
                )
                results.append(point)
                print(
                    f"margin={point['margin_pct']:.1f}% ({point['label']}) "
                    f"P_pan={point['p_pan_w']:.0f}W conv={point['converged']}"
                )
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--L-list-uh", required=True, help="Comma-separated coil inductances in uH")
    ap.add_argument("--ratio-list", required=True, help="Comma-separated f_sw/f_res ratios")
    ap.add_argument("--pans", required=True, help="Comma-separated pan preset names, or 'all'")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    if not base.MASTER_CIR.exists():
        print(f"ERROR: netlist not found: {base.MASTER_CIR}", file=sys.stderr)
        return 1
    import shutil

    if shutil.which("ngspice") is None:
        print("ERROR: ngspice not found on PATH.", file=sys.stderr)
        return 1

    l_list_uh = [float(x) for x in args.L_list_uh.split(",")]
    ratio_list = [float(x) for x in args.ratio_list.split(",")]
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
    if "i_pan_rms_last" not in base_text:
        print(
            "ERROR: master .cir does not contain the i_pan_rms_last .meas "
            "line this script depends on.",
            file=sys.stderr,
        )
        return 1

    results = run_grid(l_list_uh, ratio_list, pan_names, base_text)
    measured = [r for r in results if r.get("measured")]
    converged = [r for r in measured if r.get("converged")]

    evidence = {
        "schema_version": 1,
        "provenance": base.collect_provenance(REPO_ROOT),
        "measurement_date": _dt.date.today().isoformat(),
        "harness": "simulation/harness/run_tank_coil_sweep.py",
        "netlist": "simulation/harness/nets/zvs_margin_sweep.cir (extended with i_pan_rms_last .meas)",
        "reused_from": "simulation/harness/run_zvs_sweep.py (override_params, run_ngspice_on_text, parse_measurements, compute_point_result, PAN_PRESETS)",
        "c_tank_f": C_TANK_F,
        "c_tank_source": "modules.ato:391,398 -- c_tank1 (150nF) + c_tank2 (150nF) in parallel; COMMITTED, fixed",
        "invocation_args": {
            "L_list_uh": l_list_uh,
            "ratio_list": ratio_list,
            "pans": pan_names,
        },
        "power_definition": (
            "p_pan_w = i_pan_rms_last^2 * RPAN, where i_pan_rms_last is the "
            "RMS current through pan_load.sub's PANLOAD_TRANSFORMER "
            "secondary loop (L_sec-R_pan-V_short, series, same current "
            "throughout), read via ngspice's subcircuit-internal branch "
            "name v.x_pan.v_short#branch (verified against a standalone "
            "probe deck; i(x_pan.v_short) is not valid ngspice syntax). "
            "This is the model's power delivered to the pan-load "
            "equivalent circuit, NOT a calibrated induction-heating power "
            "figure -- see TANK_COIL_SPECIFICATION.md fidelity bounds."
        ),
        "grid": {
            "total_points": len(results),
            "measured_points": len(measured),
            "converged_points": len(converged),
        },
        "results": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(evidence, indent=2) + "\n")
    print(f"\n{len(measured)}/{len(results)} measured, {len(converged)} converged.")
    print(f"Evidence written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
