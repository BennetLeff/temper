"""Round 6 shared model: round 4's load basis, solver and ngspice deck (imported unchanged), round 5's
coupling factors (snapshotted into outputs/coupling-factors.json by snapshot_inputs.py), and the limits
this round sweeps. ASSUMED / pre-measurement throughout.

Load model (round 4, scripts/basis.py; round 5 pan_params):
    L_eq(f) = L0 * kl' * (f/40k)^beta          kl'  = 1 - (1 - kl40) * f_k   (round-5 FEM ratio, mu 100)
    R_eq(f) = R_ac40 * (f/40k)^gamma + L0 * r40' * (f/40k)^alpha              r40' = r40 * f_r
L0 is the INSTALLED no-pan inductance; R_ac40 is the coil's absolute AC resistance at 40 kHz.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "outputs"
R4 = ROOT.parent / "round4-assumed-basis" / "scripts"
sys.path.insert(0, str(R4))
import run_grid as RG  # noqa: E402  (round 4, unchanged: solve(), sim(), fha(), f_res())
import basis as B4  # noqa: E402

# ---- envelope (round 4/5 unless swept here)
F_MIN, F_MAX, ZVS = 35e3, 60e3, 1.05
I_PS_HOLD, ETA = 11.1, 0.93
C_BANK = 0.50e-6
C_TOL = 0.10
L_TOL = 0.10
R_AC40 = {"low": 0.168, "nom": 0.21, "high": 0.25}   # round 5; spec R_ac <= 0.25 ohm at 40 kHz, 100 C
R_AC_MC = (0.168, 0.25)
# free-air design value -> installed (enclosure R33 study 09 follow-up: 70 uH -> 66.5 installed; round 5 addendum: 80 -> 76)
L_INSTALLED = {70: 66.5, 80: 76.0, 90: 85.5}
CEILINGS = [22.0, 24.0, 26.0, 28.0, 30.0]
PAN_D = [180, 220, 260]
LINES = [108.0, 120.0, 140.0]
P_REQ = 1710.0
GEOM = "d228_gap84"           # R34 as modelled by the enclosure (gap at r 84-92); round 5 addendum
GEOM_ALT = "d228_2sec"        # R34 r 26-68 / 76-114 (round 5 main)

# ---- protection and parts (sources in the README)
SHUNT_BAND = (47.33, 97.77)   # stage-13 Kelvin OCP band, A peak (brief; DECISIONS 2026-10-09: 47.32 low corner)
CT_BAND = (50.56, 60.01)      # CT comparator band, A peak
FW_PEAK = 45.0                # n21_binding.c tank_peak_trip_a; config_ok() caps it below 50.9
CT_RATED_A = 88.0             # T1 thermal reference
R5_OHM = 1.0 / 31.6 ** 2      # DECISIONS 2026-10-08: R5 (1 W) good to 31.6 A RMS -> 1.0 mOhm
R5_RATED_W = 1.0


def coupling(geom: str, pan_d: int) -> tuple[float, float]:
    d = json.loads((OUT / "coupling-factors.json").read_text())
    r = d["factors"][geom][str(pan_d)]
    return r["f_k"], r["f_r"]


def pan_params(pan: dict, which: str, l0: float, fk: float, fr: float, r_ac40: float | None = None) -> dict:
    i = {"nom": 0, "low": 1, "high": 2}[which]
    kl = 1 - (1 - pan["kl40"][i]) * fk
    rac = R_AC40[which] if r_ac40 is None else r_ac40
    return {"L0U": l0, "KL40": kl, "BETA": B4.COIL["beta_kl"][0], "Q40": rac / l0,
            "GAMMA": B4.COIL["gamma_coil"][0], "R40": pan["r40"][i] * fr, "ALPHA": pan["alpha"]}


def solve_case(case: dict) -> dict:
    """Round-4 RG.solve with this case's tank ceiling (the module global is set in the worker)."""
    RG.I_TANK_MAX = case["imax"]
    r = RG.solve(case)
    r["imax_a"] = case["imax"]
    return r


# ---- TDK B32654 (1600 V DC / 500 V AC) permissible I_RMS vs f at T_A <= 85 C, dT <= 20 K (data sheet p.57),
# digitized by scripts/digitize_tdk_p57.py -> outputs/tdk-p57-1600v.csv. Loaded lazily.
_TDK = None


def tdk_limit(c_nf: int, f_hz: float) -> float:
    global _TDK
    if _TDK is None:
        import csv
        rows = list(csv.DictReader(open(OUT / "tdk-p57-1600v.csv")))
        _TDK = {int(k[2:-2]): [(float(r["f_hz"]), float(r[k])) for r in rows] for k in rows[0] if k.startswith("I_")}
    pts = _TDK[c_nf]
    lf = math.log(f_hz)
    for (f0, i0), (f1, i1) in zip(pts, pts[1:]):
        if f0 <= f_hz <= f1:
            t = (lf - math.log(f0)) / (math.log(f1) - math.log(f0))
            return math.exp(math.log(i0) + t * (math.log(i1) - math.log(i0)))
    raise ValueError(f_hz)


def worst_share(n: int, c_part: float, others: list[float] | None = None) -> float:
    """Current share of one part at +10 % with all the others at -10 % (K tolerance)."""
    others = others if others is not None else [c_part] * (n - 1)
    return c_part * 1.1 / (c_part * 1.1 + sum(o * 0.9 for o in others))
