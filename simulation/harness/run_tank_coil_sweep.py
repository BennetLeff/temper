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
TANK_COIL_SPECIFICATION.md for the fidelity bound. PANLOAD_TRANSFORMER's
secondary inductance L2 was CORRECTED 2026-07-27 (was 1uH, provably too
small to express any coupling -- see docs/evidence/2026-07-27-coil-pan-
coupling-resolution.md Sec 2.3) to an Infineon-anchored 218uH, held
uniform across pan presets and now exposed as a PAN_L2 override, exactly
as run_zvs_sweep.py does -- see that script's PAN_PRESETS comment and
docs/evidence/2026-07-27-pan-preset-correction.md.

Sweep axis: L_TARGET is the coil's absolute inductance in uH; it is
written to the deck's PAN_L1 parameter (F_SW is also overridden, exactly
as run_zvs_sweep.py already does for both). No other .cir change was made
beyond the one .meas line described above -- this script reuses
override_params/run_ngspice_on_text/parse_measurements-style parsing from
run_zvs_sweep.py directly.

Ratio reference frequency -- CORRECTED 2026-07-27
--------------------------------------------------
Before the PAN_PRESETS correction, `ratio_f_sw_over_f_res` was computed
against the UNLOADED tank resonance (f_res_hz(), L1/C_TANK only) because
the broken K=0.15-0.5/L2=1uH presets barely loaded the tank at all --
loaded and unloaded resonance were within a fraction of a percent of each
other, so the distinction didn't matter numerically.

That is no longer true for the corrected K=0.79 presets (cast_iron/
stainless): docs/evidence/2026-07-27-coil-pan-coupling-resolution.md
Sec 2.1 shows the loaded resonance is a SELF-CONSISTENT quantity --
L_apparent/L1 depends on omega (via x=omega*L2), which is itself what
you're solving for -- and docs/evidence/2026-07-27-pan-model-correction.md
Sec 4 found this self-consistent point sits ~60% above the unloaded
figure. Continuing to compute ratio against the unloaded resonance would
silently reintroduce the exact bug this whole correction pass exists to
fix (a ratio that means "at resonance" for the numbers actually swept,
but doesn't for the physically loaded tank) -- confirmed empirically: a
grid run at ratio=1.02 against the OLD (unloaded) reference put every
cast_iron point at ~100.6% zvs_lost (deep in hard-switching territory,
NOT near resonance) once PAN_L2 was corrected.

f_res_loaded_hz() below iterates the exact (non-approximated) T-model
relation from the resolution doc to a fixed point, and `ratio_f_sw_over_
f_res` is now computed against THAT per-(L, pan_preset) value. The old
unloaded figure is still reported, as `f_res_unloaded_hz`, for
transparency and backward comparison against pre-correction evidence.

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
C_TANK_F = base.C_TANK_F  # 300nF, committed and fixed. Realised as 3 x 100nF
                          # in parallel (c_tank1..c_tank3) since 2026-07-29;
                          # the total is unchanged, only the part count.

PAN_PRESETS_BY_NAME = {n: (k, r, l2, s) for n, k, r, l2, s in base.PAN_PRESETS}


def f_res_hz(l_henries: float) -> float:
    """UNLOADED resonance (L1/C_TANK only, no pan coupling). Retained for
    backward comparison against pre-2026-07-27-preset-correction evidence;
    no longer used to set F_SW from ratio -- see f_res_loaded_hz()."""
    return 1.0 / (2 * math.pi * math.sqrt(l_henries * C_TANK_F))


def f_res_loaded_hz(
    l_henries: float, pan_k: float, pan_rpan: float, pan_l2_h: float,
    tol: float = 1e-6, max_iter: int = 200,
) -> float:
    """Self-consistent LOADED resonance -- fixed-point iteration of the
    exact T-model relation (docs/evidence/2026-07-27-coil-pan-coupling-
    resolution.md Sec 2.1):

        L_apparent / L1 = 1 - K^2 * x^2 / (RPAN^2 + x^2),   x = omega*L2

    `omega` (what f_sw should be set to, at ratio=1.0) depends on
    L_apparent, which itself depends on omega via x -- so this cannot be
    solved in closed form for the general case and is iterated to a fixed
    point starting from the unloaded resonance. Converges in a handful of
    iterations for every (L, preset) combination this harness has been run
    on (K<=0.79); not proven to converge for arbitrary K.
    """
    f = f_res_hz(l_henries)
    for _ in range(max_iter):
        omega = 2 * math.pi * f
        x = omega * pan_l2_h
        ratio = 1.0 - (pan_k * pan_k) * x * x / (pan_rpan * pan_rpan + x * x)
        l_apparent = l_henries * ratio
        f_new = f_res_hz(l_apparent)
        if abs(f_new - f) < tol * f_new:
            return f_new
        f = f_new
    return f


def run_grid(l_list_uh, ratio_list, pan_names, base_text):
    results = []
    total = len(l_list_uh) * len(ratio_list) * len(pan_names)
    done = 0
    for l_uh in l_list_uh:
        l_h = l_uh * 1e-6
        fres_unloaded = f_res_hz(l_h)
        for pan_name in pan_names:
            pan_k, pan_rpan, pan_l2, _note = PAN_PRESETS_BY_NAME[pan_name]
            # LOADED resonance depends on the pan preset (K, RPAN, L2), not
            # just L -- see f_res_loaded_hz() docstring and the module
            # docstring's "Ratio reference frequency" section. Computed
            # once per (L, pan) rather than per (L, pan, ratio) since it
            # does not depend on ratio.
            fres_loaded = f_res_loaded_hz(l_h, pan_k, pan_rpan, pan_l2)
            for ratio in ratio_list:
                f_sw = fres_loaded * ratio
                done += 1
                # override_params does a literal ".param NAME = value" replace;
                # ngspice needs a unit suffix on PAN_L1 (it's declared "80u" in
                # the deck) or a fully-expanded float. Use an explicit
                # micro-suffixed string so this matches the deck's own style.
                # PAN_L2 is passed as a plain (non-suffixed) float in henries
                # -- Python's str() of a value like 218e-6 renders as
                # "0.000218", a fully-expanded float per the same rule, so no
                # unit-suffix ambiguity exists there (unlike PAN_L1 above,
                # which is overridden with bare integers like "70" that WOULD
                # be ambiguous without a suffix).
                overrides = {
                    "F_SW": f_sw,
                    "PAN_K": pan_k,
                    "PAN_RPAN": pan_rpan,
                    "PAN_L1": f"{l_uh}u",
                    "PAN_L2": pan_l2,
                }
                cir_text = base.override_params(base_text, overrides)
                stdout, stderr, code = base.run_ngspice_on_text(cir_text)
                point = {
                    "l_uh": l_uh,
                    "f_res_loaded_hz": round(fres_loaded, 1),
                    "f_res_unloaded_hz": round(fres_unloaded, 1),
                    "ratio_f_sw_over_f_res": ratio,
                    "f_sw_hz": round(f_sw, 1),
                    "pan_preset": pan_name,
                    "pan_k": pan_k,
                    "pan_rpan_ohm": pan_rpan,
                    "pan_l2_h": pan_l2,
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
                zvs = base.compute_point_result(pan_name, pan_k, pan_rpan, f_sw, meas, pan_l2_h=pan_l2)
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
        "ratio_reference_frequency_note": (
            "CORRECTED 2026-07-27: ratio_f_sw_over_f_res is now computed "
            "against f_res_loaded_hz (a self-consistent, per-(L,pan) fixed "
            "point of the exact T-model relation, f_res_loaded_hz() in "
            "this script), NOT the unloaded f_res_unloaded_hz (L1/C_TANK "
            "only) used before the PAN_PRESETS correction. For the old "
            "K=0.15-0.5/L2=1uH presets these were within a fraction of a "
            "percent of each other; for the corrected K=0.79 presets "
            "(cast_iron/stainless) f_res_loaded_hz is ~60% above "
            "f_res_unloaded_hz (see docs/evidence/2026-07-27-pan-preset-"
            "correction.md), so continuing to reference the unloaded "
            "figure would put ratio=1.02 deep in zvs_lost territory "
            "instead of near resonance -- confirmed empirically before "
            "this fix (every cast_iron point at ratio=1.02-vs-unloaded "
            "measured ~100.6% margin, not the near-ZVS-boundary value the "
            "ratio label implies)."
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
