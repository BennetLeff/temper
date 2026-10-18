"""temper nameplate study: does the inlet (line) current limit or the tank-current ceiling bind?

ESTIMATE / pre-measurement throughout. No coil or pan has been measured; this re-uses the power-stage
session's own tank model (task 05 round 6, ASSUMED basis), imported READ-ONLY:

  worktrees/ps-integrate/zapote/power-stage-120v/validation-results/05-resonant-tank-envelope/
    round6-full-power/scripts/fha6.py   pi_at() (FHA: line-cycle tank RMS i = 0.9 V/|Z|, P = i^2 R), fres(),
                                        draws(), power_at_ceiling() (lowest legal f meeting both limits)
    round6-full-power/scripts/common6.py F_MIN/F_MAX 35/60 kHz, ZVS 1.05, C_BANK 0.50 uF, L_INSTALLED 66.5 uH,
                                        R_AC_MC 0.168-0.25 ohm, coupling(d228_gap84, pan_d)
    round4-assumed-basis/scripts/basis.py PANS / SUPPLEMENTAL (kl40, r40, alpha per pan class)
    round6-full-power/outputs/calibration6.json  kp, ki (ngspice/FHA), kpk peak/RMS fit

The power-stage commit and the sha256 of every imported file are recorded in nameplate.json.

Limits (codex/power-stage-integration b7ff4a857, read-only):
  inlet: firmware input_limits.c:62-67  P_inv/eta_min/V * (1 + est_error) + aux <= inlet_target
         -> tank power target P_tgt = (inlet_target - aux) / (1 + e) * 0.93 * V, capped at max_power_w 1800
            (n21_binding.c:15). Aux = blower_aux worst corner after the applied patch (blower full 0.887 A,
            mid 0.597 A, off 0.31 A at 108 V).
  tank:  line-cycle tank RMS ceiling. 18 A = the still-air release request until candidate 39 (DECISIONS item
         46, OPEN-ITEMS S2); 21 A ~ still-air C40 ceiling 21.1 A after c39 and the 45 A peak trip (~21 A);
         22 A = firmware tank_limit_a (input_limits.c:13); 24 / 26 / 28 A = enclosure-airflow routes
         (28 A needs board-face airflow, OCP, copper and coil changes: round-6 README).
  It assumes the round-6 per-pan frequency rule (lowest legal f, closed loop). The firmware today still has a
  single commissioned frequency (round-6 verdict 1), which delivers far less than either limit.

Thermal side (boil, heat-up):
  2 L boil: energy to take 2 L from 20 to 100 C plus a 1.2 kg clad pan. P_loss is backed out of the
  Control Freak's measured 10:55 (yt:BcSqJ7sZiAQ 04:40; 1800 W input) for an assumed CF input-to-pan
  efficiency eta_CF 0.80-0.90, then held fixed (same pot, same water) - the output/temper-mining-r3
  boil_time.py method, but fed with temper's modelled PAN power (coil loss removed) instead of input x eta.
  Caveat: the CF may not have run at its full 1800 W in that test (temperature-mode heat-up), which makes
  P_loss an upper bound and the comparison pessimistic for temper.
  Empty-pan heat-up 25 -> 200 C: lumped pan (heat capacity, area and emissivity from output/temper-sensor-r2
  PANS), convection 10 W/m2K + radiation from top and walls, 15 W/m2K under the base. The mapping of the
  power-stage electrical classes onto thermal pans is an inference (see PAN_THERMAL).

Run: python3 nameplate.py   -> nameplate.json (about 30 s)
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from math import pi
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
PS = REPO / "worktrees" / "ps-integrate"
R6 = PS / "zapote/power-stage-120v/validation-results/05-resonant-tank-envelope/round6-full-power"
sys.dont_write_bytecode = True
sys.path.insert(0, str(R6 / "scripts"))
import common6 as M  # noqa: E402
import fha6  # noqa: E402

CAL = json.loads((R6 / "outputs/calibration6.json").read_text())
KP, KI = CAL["kp_median"], CAL["ki_median"]

ETA_MIN = 0.93           # input_limits.c:12 eta_min
MAX_POWER_W = 1800.0     # n21_binding.c:15 max_power_w
AUX = {"blower_full": 0.887, "blower_mid": 0.597, "blower_off": 0.31}   # blower_aux worst, 108 V (b7ff4a857)
LINES = (108.0, 120.0, 132.0)
CEILINGS = (18.0, 21.0, 22.0, 24.0, 26.0, 28.0)
PAN_D = (180, 220)
N_MC = 4000

# Nameplate options: (inlet target A, estimate error)
OPTIONS = {
    "12 A nameplate, estimated (e 10 %)": (12.0, 0.10),
    "13.5 A target, estimated (e 10 %) - today": (13.5, 0.10),
    "13.5 A target, measured (AMC1301, e 2.5 %)": (13.5, 0.025),
    "15 A nameplate, estimated (e 10 %)": (15.0, 0.10),
    "15 A nameplate, measured (AMC1301, e 2.5 %)": (15.0, 0.025),
}

CLASSES = {**M.B4.PANS, "small_or_offset_pan": M.B4.SUPPLEMENTAL["offset_or_small_pan_SYNTHETIC"]}

# Electrical class -> thermal pan (output/temper-sensor-r2/estimator_study.py PANS); INFERENCE.
SR2 = {
    "cast_iron_26": dict(R=0.105, rct=7200 * 460 * 5e-3, eps=0.8, wall_H=0.05, wall_rct=7200 * 460 * 4.5e-3),
    "carbon_steel_28": dict(R=0.100, rct=7850 * 470 * 2e-3, eps=0.7, wall_H=0.05, wall_rct=7850 * 470 * 2e-3),
    "triply_clad_24": dict(R=0.090, rct=4.0e6 * 1.0e-3 + 2.43e6 * 1.6e-3, eps=0.15, wall_H=0.06,
                           wall_rct=4.0e6 * 1.0e-3 + 2.43e6 * 1.6e-3),
}
PAN_THERMAL = {"cast_iron": "cast_iron_26", "enamelled_steel": "carbon_steel_28",
               "thin_stainless_single_ply": "carbon_steel_28", "aluminium_clad_multiply": "triply_clad_24",
               "ss1810_ferromagnetic_base": "triply_clad_24", "small_or_offset_pan": "carbon_steel_28"}

# Boil (output/temper-mining-r3/boil_time.py constants)
E_BOIL = 2.0 * 4186.0 * 80.0 + 600.0 * 80.0
CF_T, CF_P_IN = 655.0, 1800.0
ETA_CF = (0.80, 0.85, 0.90)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def pan_power(d, V, p_tgt, imax):
    """Delivered tank power under both limits, the pan's share of it, and which limit binds."""
    p, i, f, fr = fha6.power_at_ceiling(d, V, p_tgt, imax, KP, KI)
    L, R = fha6.lr(d, f)
    r_pan = d["L0"] * d["r40"] * (f / 40e3) ** d["alpha"]
    p_pan = p * r_pan / R
    inlet = p >= 0.99 * p_tgt
    tank = (~inlet) & (i >= 0.99 * imax)
    floor = (~inlet) & (~tank)
    return p, p_pan, i, f, inlet, tank, floor


def heat_up_s(pan_key: str, p_pan: float, t_end=200.0) -> float:
    """Lumped empty-pan heat-up 25 -> t_end C; inf if losses exceed power first."""
    p = SR2[pan_key]
    base = pi * p["R"] ** 2
    wall = 2 * pi * p["R"] * p["wall_H"]
    C = p["rct"] * base + p["wall_rct"] * wall
    a_top = base + 2 * wall
    T, t, dt = 25.0, 0.0, 0.05
    while T < t_end:
        loss = (a_top * (10 * (T - 25) + p["eps"] * 5.670e-8 * ((T + 273.15) ** 4 - 298.15 ** 4))
                + base * 15 * (T - 25))
        dT = (p_pan - loss) / C
        if dT <= 1e-4:
            return float("inf")
        T += dT * dt
        t += dt
        if t > 7200:
            return float("inf")
    return t


def fmt(t: float) -> str:
    return "never" if not np.isfinite(t) else f"{int(t // 60)}:{int(t % 60):02d}"


def main():
    rng_seed = 20261015
    rows, summary = [], {}
    for ci, (cls, pan) in enumerate(CLASSES.items()):
        for pj, pd in enumerate(PAN_D):
            fk, frr = M.coupling(M.GEOM, pd)
            rng = np.random.default_rng(rng_seed + 10 * ci + pj)
            d = fha6.draws(pan, N_MC, rng, M.L_INSTALLED[70], fk, frr, M.C_BANK)
            for V in LINES:
                for opt, (tgt, e) in OPTIONS.items():
                    for blower, aux in AUX.items():
                        if blower == "blower_off" and "today" not in opt and "15 A nameplate, measured" not in opt:
                            continue
                        i_ps = (tgt - aux) / (1 + e)
                        p_tgt = min(MAX_POWER_W, i_ps * ETA_MIN * V)
                        for imax in CEILINGS:
                            p, ppan, i, f, inl, tk, fl = pan_power(d, V, np.full(N_MC, p_tgt), imax)
                            rows.append({
                                "pan_class": cls, "pan_d_mm": pd, "line_v": V, "option": opt, "blower": blower,
                                "i_ps_hold_a": round(i_ps, 3), "p_tank_target_w": round(p_tgt, 1),
                                "tank_ceiling_a": imax,
                                "p_pan_median_w": round(float(np.median(ppan)), 1),
                                "p_pan_p10_w": round(float(np.percentile(ppan, 10)), 1),
                                "frac_inlet_limited": round(float(inl.mean()), 3),
                                "frac_tank_limited": round(float(tk.mean()), 3),
                                "frac_floor_limited": round(float(fl.mean()), 3)})
    # Boil and heat-up on the median pan power, 120 V, blower full (worst aux at high power), 220 mm
    # (180 mm for the 2 L pot classes as a second case).
    thermo = []
    for r in rows:
        if r["line_v"] != 120.0 or r["blower"] != "blower_full":
            continue
        pp = r["p_pan_median_w"]
        boil = {}
        for eta in ETA_CF:
            p_loss = eta * CF_P_IN - E_BOIL / CF_T
            net = pp - p_loss
            boil[f"{eta:.2f}"] = round(E_BOIL / net, 1) if net > 0 else None
        hu = heat_up_s(PAN_THERMAL[r["pan_class"]], pp)
        thermo.append({**{k: r[k] for k in ("pan_class", "pan_d_mm", "option", "tank_ceiling_a",
                                              "p_pan_median_w", "frac_inlet_limited", "frac_tank_limited")},
                       "boil_2L_s_by_eta_cf": boil, "heatup_200C_s": None if not np.isfinite(hu) else round(hu, 1)})
    cf = {}
    for eta in ETA_CF:
        cf[f"{eta:.2f}"] = {k: (lambda h: None if not np.isfinite(h) else round(h, 1))(heat_up_s(k, eta * CF_P_IN))
                            for k in SR2}
    # Compact limit map: 120 V, blower full, 220 mm, per class x ceiling, for today and 15 A measured.
    lmap = {}
    for r in rows:
        if r["line_v"] == 120.0 and r["blower"] == "blower_full" and r["pan_d_mm"] == 220:
            lmap.setdefault(r["option"], {}).setdefault(r["pan_class"], {})[str(r["tank_ceiling_a"])] = {
                "p_pan_median_w": r["p_pan_median_w"], "inlet": r["frac_inlet_limited"],
                "tank": r["frac_tank_limited"], "floor": r["frac_floor_limited"]}
    # Pooled summary (robust to the boil-loss calibration): the five measured-anchor classes at 220 mm,
    # blower full; median over classes of each class's median pan power, its ratio to the Control Freak's
    # pan power (eta_CF x 1800 W, eta_CF 0.85 central), and the pooled inlet-limited fraction.
    pooled = {}
    for r in rows:
        if r["pan_d_mm"] != 220 or r["blower"] != "blower_full" or r["pan_class"] not in M.B4.PANS:
            continue
        k = (r["line_v"], r["option"], r["tank_ceiling_a"])
        pooled.setdefault(k, []).append(r)
    pooled_out = {}
    for (V, opt, c), rs in pooled.items():
        pw = float(np.median([x["p_pan_median_w"] for x in rs]))
        pooled_out.setdefault(f"{V:.0f}V", {}).setdefault(opt, {})[f"{c:.0f}A"] = {
            "p_pan_w": round(pw, 0), "vs_CF_eta085": round(pw / (0.85 * CF_P_IN), 2),
            "vs_CF_eta080_090": [round(pw / (0.90 * CF_P_IN), 2), round(pw / (0.80 * CF_P_IN), 2)],
            "frac_inlet_limited": round(float(np.mean([x["frac_inlet_limited"] for x in rs])), 2)}
    head = subprocess.run(["git", "-C", str(PS), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    srcs = {str(p.relative_to(PS)): sha(p) for p in [
        R6 / "scripts/fha6.py", R6 / "scripts/common6.py", R6 / "outputs/calibration6.json",
        R6 / "outputs/coupling-factors.json",
        R6.parent / "round4-assumed-basis/scripts/basis.py",
        PS / "firmware/components/power/input_limits.c", PS / "firmware/components/power/blower_aux.c",
        PS / "firmware/components/power/n21_binding.c"]}
    out = {"scope": __doc__.strip(), "power_stage_commit": head, "source_sha256_16": srcs,
           "constants": {"eta_min": ETA_MIN, "max_power_w": MAX_POWER_W, "aux_a": AUX, "kp": KP, "ki": KI,
                         "n_mc": N_MC, "seed": rng_seed, "options": OPTIONS, "ceilings_a": CEILINGS,
                         "pan_thermal_map_inferred": PAN_THERMAL},
           "pooled_220mm_blower_full": pooled_out,
           "limit_map_120V_220mm_blower_full": lmap, "thermal_120V_blower_full": thermo,
           "control_freak_heatup_s_by_eta": cf, "rows": rows}
    Path(__file__).with_name("nameplate.json").write_text(json.dumps(out, indent=1) + "\n")

    # Console summary
    print("power-stage commit", head)
    for opt in ("13.5 A target, estimated (e 10 %) - today", "15 A nameplate, measured (AMC1301, e 2.5 %)"):
        print(f"\n== {opt}  (120 V, 220 mm, blower full): median pan W  [inlet/tank/floor-limited fraction]")
        print(f"{'class':28s}" + "".join(f"{c:>20.0f}A" for c in CEILINGS))
        for cls in CLASSES:
            cells = lmap[opt][cls]
            print(f"{cls:28s}" + "".join(
                f"{cells[str(c)]['p_pan_median_w']:7.0f} [{cells[str(c)]['inlet']:.2f}/{cells[str(c)]['tank']:.2f}/"
                f"{cells[str(c)]['floor']:.2f}]" for c in CEILINGS))
    print("\n== 2 L boil (eta_CF 0.85) and empty heat-up to 200 C, 120 V, 220 mm, blower full")
    for cls in ("ss1810_ferromagnetic_base", "aluminium_clad_multiply", "cast_iron", "thin_stainless_single_ply"):
        for c in (18.0, 21.0, 28.0):
            line = f"{cls:26s} {c:4.0f} A:"
            for opt in OPTIONS:
                t = next(x for x in thermo if x["pan_class"] == cls and x["pan_d_mm"] == 220
                         and x["option"] == opt and x["tank_ceiling_a"] == c)
                b = t["boil_2L_s_by_eta_cf"]["0.85"]
                line += f"  {fmt(b if b else float('inf')):>6s}/{fmt(t['heatup_200C_s'] or float('inf')):>5s}"
            print(line)
    print("\n== pooled (5 classes, 220 mm, blower full): pan W / ratio to CF (eta 0.85) / inlet-limited fraction")
    for V in ("108V", "120V"):
        for opt in OPTIONS:
            print(f"{V} {opt:44s}" + "".join(
                f"  {c}: {pooled_out[V][opt][c]['p_pan_w']:5.0f} W {pooled_out[V][opt][c]['vs_CF_eta085']:.2f}x"
                f" {pooled_out[V][opt][c]['frac_inlet_limited']:.2f}" for c in ("18A", "21A", "22A", "24A", "28A")))
    print("options:", list(OPTIONS))
    print("CF heat-up to 200 C (eta_CF 0.85):", {k: fmt(v or float('inf')) for k, v in cf["0.85"].items()})


if __name__ == "__main__":
    main()
