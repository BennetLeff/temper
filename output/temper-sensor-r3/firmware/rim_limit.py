"""DECISIONS.md D-RIMLIM: a setpoint-relative rim limit against element-parallel Pt100 leakage (candidate A).

Question. D-LEAK's rule needs a cross-check suspect, and the cross-check needs
the reading 25 K below the rim: with the reading held at 250 degC that is a
pan up to ~331 degC. A leak holds the *reading* at the setpoint; the glass
under the rim NTC follows the *pan*. So the rim can be compared with the
temperature the glass could reach if the pan were where the loop thinks it
is, and a rim above that is a pan hotter than the loop thinks.

1. The glass envelope (derived here, cited):
   The glass under the bead is modelled as a weighted mean of the pan and
   the coil-eye air, Tg = w T_pan + (1 - w) T_eye, which fits both sources
   to 0.01 in w:
   - cad/thermal-axisym.json (G8, 260 degC pan, glass underside at the rim
     NTC radius r14.5): flat pan w = 0.955, 0.5 mm warp w = 0.830/0.831, for
     both eye states (full_22A air 130.0, fry_hold_12.7A air 139.7 degC);
   - study 08 (output/temper-r33-studies/08-undrilled-glass-sensor,
     undrilled-thermal.json steady_offsets_B; not in this tree, numbers
     below verbatim): an underside sensor 20.39-59.67 K below a 250 degC pan
     and +5.17..+10.63 K above a 100 degC pan, w = 0.709-0.83, eye air 45
     (low_hold_EST) to 139.7 degC (fry_hold_12.7A).
   Benign upper envelope (hottest glass for a pan at T): max over
   w in [W_LO, W_HI] with the hottest eye, T_EYE_HI. Leak lower envelope
   (coolest glass for a pan at T): W_LO with the coolest eye, T_EYE_LO.
2. The rule (components/control/pan_rim_limit.c, D-RIMLIM): T_ref is a
   decaying maximum of max(setpoint, t_hat) (tau_dec: the glass cannot cool
   faster than its own lag); lim = Tg_max(T_ref) + tol + margin, tol the
   rim channel's hot stack (bead 10.2 K, rail 4.37 K, self-heating 4.53 K:
   19.1 K, D-RIM); the rim VALID, above lim, and not falling (rim now >=
   rim W s ago - fall_k) for sustain_s latches.
3. Sets, all through the C loop (leak_checks.run_case, every latch passive):
   - sweep: leak_checks.py's 624 leak runs (owner's metric);
   - benign: leak_checks.py's 548 benign runs;
   - stress_benign: the hot side of every model input: glass at the benign
     envelope (w W_HI and W_LO with T_EYE_HI), the rim hot stack (bead hot,
     v3v3 3242 mV while the driver assumes 3300, +4.53 K self-heating),
     tau_g 18/60/106 s (study 08 B t63 range; 60 s is xcheck_cosim's
     assumption), kinds: a 1800 s hold at the 250 degC maximum, the setpoint
     lowered 250 -> 150 at 900 s, a cold pan on glass at 245.1 degC (the
     envelope's hottest for a 250 degC hold), a preheated
     pan (250 degC) on cold glass, food, and food batches;
   - stress_leak: the leak sweep's 3 frying pans x 13 R x 3 onsets at the
     cold side: glass at the leak envelope (w W_LO, T_EYE_LO; and flat W_HI,
     T_EYE_LO), the rim cold stack (bead cold, 3367 mV), tau_g 106 s.
   The rule variants are evaluated offline on 0.5 s traces of the same runs
   (the rule is passive, so the trajectory does not depend on it), giving
   the trade-off curve: margin vs hazardous leaks latched before T_c first
   exceeds 300 degC vs false latches. The chosen variant is then run in C
   by leak_checks.py (step 3d of run.sh), which is the gated result.
4. CR-5: the hardware rim trip band (pcb/DECISIONS.md D6, 262.3-288.1 degC
   true glass, includes 1.7 K self-heating) lowered by X K: hazardous runs
   whose glass reaches the band top - X before T_c passes 300, against the
   benign glass maximum (sets above) and the band low edge - X.

Writes rim-limit.json. Run: python3 rim_limit.py [--lib path]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cosim  # noqa: E402
import leak_checks as LC  # noqa: E402
import ref  # noqa: E402
import xcheck_cosim as X  # noqa: E402
from ref import es, screen  # noqa: E402

AXISYM = HERE.parent / "cad" / "thermal-axisym.json"
FW_CONTROL = HERE.parent.parent.parent / "firmware" / "components" / "control"
# study 08 steady_offsets_B (sensor minus pan, K), verbatim: (env eye air degC, gap mm, hold degC, offset)
STUDY08_B = [(45.0, 0.0, 250.0, -34.84), (45.0, 0.5, 250.0, -59.67), (130.0, 0.0, 250.0, -20.39),
             (130.0, 0.5, 250.0, -35.1), (130.0, 0.0, 100.0, 5.17), (130.0, 0.5, 100.0, 10.63)]
T_EYE_HI, T_EYE_LO = 139.7, 45.0   # fry_hold_12.7A eye air; low_hold_EST eye air (study 02 via 08)
TOL_HOT_K = 10.2 + 4.37 + 4.53     # D-RIM stack: bead (pcb D5), rail, still-air self-heating
# The same stack as a function of the rim temperature (tol_hot_table): the
# bead's hot corner (xcheck_cosim CORNERS, scaled to pcb D5's 10.2 K at
# 250 degC), the rail error with v3v3 at 3242 mV while the driver assumes
# 3300 mV, and 4.53 K self-heating. D-RIM's 19.1 K adds the rail's worst
# (near the saturation end) to the bead's worst (250 degC); at 250 degC the
# rail costs 1.25 K.
TOL_T = (90.0, 100.0, 150.0, 200.0, 250.0, 300.0, 350.0)
RAIL_LO_MV, SELF_HEAT_K, PCB_BEAD_250_K = 3242.0, 4.53, 10.2
TRACE_DT = 0.5
TAU_GS = (18.0, 60.0, 106.0)
CR5_BAND = X.CR5_BAND

# rule grid (offline)
MARGINS = (-10.0, -5.0, -2.5, -1.0, 0.0, 1.0, 2.5, 5.0, 10.0)
TAU_DECS = (60.0, 120.0, 300.0)
SUSTAIN_S = 5.0
FALL_W_S, FALL_K = 30.0, 1.0
# the variant the firmware implements (pan_rim_limit.h defaults)
CHOSEN = {"margin": 0.0, "tau_dec": 300.0, "fall": True, "tol": "table"}


def envelope():
    """w per axisym case and per study-08 row; the envelope constants."""
    ax = json.loads(AXISYM.read_text())
    eye = ax["eye_states"]
    rows, seen = [], set()
    for c in ax["cases"]:
        if (c["eye"], c["glass"]) in seen:   # the contact does not move the glass
            continue
        seen.add((c["eye"], c["glass"]))
        tg = c["parts"]["glass_underside_at_rim_NTC_r14.5"]["mean"]
        te = eye[c["eye"]][1]
        rows.append({"src": "axisym", "case": f"{c['eye']} | {c['glass']}", "T_pan": ax["T_pan_C"], "T_eye": te,
                     "Tg": tg, "w": round((tg - te) / (ax["T_pan_C"] - te), 4)})
    for te, gap, hold, off in STUDY08_B:
        rows.append({"src": "study08_B", "case": f"eye {te} gap {gap}", "T_pan": hold, "T_eye": te,
                     "Tg": hold + off, "w": round((hold + off - te) / (hold - te), 4)})
    ws = [r["w"] for r in rows]
    # the coolest glass for a hot pan: the lowest w among holds >= 200 degC
    return {"rows": rows, "w_hi": max(ws), "w_lo": min(ws),
            "w_lo_hot": min(r["w"] for r in rows if r["T_pan"] >= 200.0)}


ENV = envelope()
W_HI, W_LO, W_LO_HOT = ENV["w_hi"], ENV["w_lo"], ENV["w_lo_hot"]


def tg_max(t):
    """Benign upper envelope: the hottest glass for a pan at t."""
    return np.maximum(W_HI * t + (1 - W_HI) * T_EYE_HI, W_LO * t + (1 - W_LO) * T_EYE_HI)


def _rim_err(t, corner, rail=3300.0):
    """Rim reading error (K) at a true bead temperature t: the driver's R-T over a node at a corner."""
    from scipy.optimize import brentq
    mv = X.node_mv(t, corner) * rail / 3300.0
    x = mv / 3300.0
    r = 1000.0 * x / (1.0 - x)
    return brentq(lambda u: X.r_ntc(u) - r, -40.0, 450.0) - t


def tol_hot_table():
    k250 = PCB_BEAD_250_K / _rim_err(250.0, "hot")
    out = []
    for t in TOL_T:
        bead = _rim_err(t, "hot")
        rail = _rim_err(t, "hot", RAIL_LO_MV) - bead
        out.append(round(bead * k250 + rail + SELF_HEAT_K, 2))
    return out


TOL_K = tol_hot_table()


def tol_at(t):
    return np.interp(t, TOL_T, TOL_K)


def tg_min(t):
    return W_LO_HOT * t + (1 - W_LO_HOT) * T_EYE_LO


# ---- cases --------------------------------------------------------------
def _tr(cases):
    return [dict(c, trace_dt=TRACE_DT) for c in cases]


def stress_benign():
    screen.apply(ref.C1)
    spread = screen.h_spread(ref.C1)
    out, i = [], 0
    for pan, (lo, hi) in spread.items():
        h = (lo * hi) ** 0.5
        water = pan == "disc_pot_water_1l5"
        sp1, sp2 = es.PANS[pan]["sp"]
        top = sp2 if water else LC.SP_FRY
        for gw in (W_HI, W_LO):
            for tau in TAU_GS:
                base = dict(set="stress_benign", pan=pan, h=h, delta=0.0, glass_w=gw, t_eye=T_EYE_HI,
                            corner="hot_stack", tau_g=tau, seed=40_000 + i)
                i += 1
                prof = [(0.0, sp1), (es.SP_STEP_T, top)]
                out.append(dict(base, kind="hold_max", sp_profile=prof, t_end=1800.0))
                out.append(dict(base, kind="sp_down", sp_profile=prof + [(900.0, top - 100.0)], t_end=1500.0))
                # glass left at the envelope's hottest for a 250 degC hold (245.1 degC)
                out.append(dict(base, kind="hot_glass", sp_profile=prof, glass0=round(float(tg_max(250.0)), 1),
                                t_end=900.0))
                out.append(dict(base, kind="hot_pan", sp_profile=[(0.0, top)], t_hot=top, t_end=900.0))
                if not water:
                    out.append(dict(base, kind="food", sp_profile=prof, food_at=cosim.FOOD_T, t_end=900.0))
                    out.append(dict(base, kind="food_batches", sp_profile=prof, food_at=cosim.FOOD_T,
                                    food_batches_at=tuple(cosim.FOOD_T + d for d in LC.BATCH_GAPS_S),
                                    t_end=900.0))
    return out


def stress_leak():
    screen.apply(ref.C1)
    spread = screen.h_spread(ref.C1)
    out, i = [], 0
    for pan, (lo, hi) in spread.items():
        if pan == "disc_pot_water_1l5":
            continue
        for gw, name in ((W_LO_HOT, "leak_envelope"), (W_HI, "flat_cool_eye")):
            for onset, ramp in LC.ONSETS.items():
                for r in LC.R_LEAKS:
                    out.append(dict(kind="leak", set="stress_leak", glass=name, pan=pan, h=(lo * hi) ** 0.5,
                                    seed=60_000 + i, delta=0.0, glass_w=gw, t_eye=T_EYE_LO, tau_g=106.0,
                                    corner="cold_stack", r_leak=r, sp2=LC.SP_FRY, t_end=LC.T_END_LEAK,
                                    onset=onset, ramp_s=ramp))
                    i += 1
    return out


# ---- the rule, offline ---------------------------------------------------
def _windows_all(b, n):
    """b[k] and the n - 1 samples before it are all true."""
    c = np.convolve(b.astype(np.int32), np.ones(n, dtype=np.int32))[:len(b)]
    return c >= n


def rule_latches(tr, vs, sustain_s=SUSTAIN_S, tol=TOL_HOT_K):
    """First latch time (s) of the rim limit on one trace, for every variant (None: no latch)."""
    t, sp, y, th, st, rim = (tr[:, j].astype(np.float64) for j in range(6))
    u = np.where(np.isfinite(th), np.maximum(sp, th), sp)
    nw = int(round(FALL_W_S / TRACE_DT))
    ns = int(round(sustain_s / TRACE_DT))
    valid = st == X.RIM_VALID
    rim_v = np.where(valid, rim, np.nan)
    prev = np.full_like(rim_v, np.nan)
    prev[nw:] = rim_v[:-nw]
    not_falling = _windows_all(valid, nw + 1) & (rim_v >= prev - FALL_K)
    refs = {}
    for td in {v["tau_dec"] for v in vs}:
        a = math.exp(-TRACE_DT / td)
        r_ = np.empty_like(u)
        acc = -1e9
        for k in range(len(u)):
            acc = max(u[k], u[k] + (acc - u[k]) * a)
            r_[k] = acc
        refs[td] = tg_max(r_)
    out = []
    for v in vs:
        g = refs[v["tau_dec"]]
        lim = g + (tol_at(g) if v["tol"] == "table" else tol)
        ok = valid & (rim_v > lim + v["margin"])
        if v["fall"]:
            ok &= not_falling
        hit = np.nonzero(_windows_all(ok, ns))[0]
        out.append(float(t[hit[0]]) if len(hit) else None)
    return out


def headroom(tr, v, sustain_s=SUSTAIN_S):
    """max over the run of the sustained (rim - lim) where the rule looks (VALID, not falling):
    the margin by which the chosen limit could fall before this run trips (negative: it never comes close)."""
    t, sp, y, th, st, rim = (tr[:, j].astype(np.float64) for j in range(6))
    u = np.where(np.isfinite(th), np.maximum(sp, th), sp)
    nw, ns = int(round(FALL_W_S / TRACE_DT)), int(round(sustain_s / TRACE_DT))
    valid = st == X.RIM_VALID
    rim_v = np.where(valid, rim, np.nan)
    prev = np.full_like(rim_v, np.nan)
    prev[nw:] = rim_v[:-nw]
    look = _windows_all(valid, nw + 1) & (rim_v >= prev - FALL_K) if v["fall"] else valid
    a = math.exp(-TRACE_DT / v["tau_dec"])
    r_ = np.empty_like(u)
    acc = -1e9
    for k in range(len(u)):
        acc = max(u[k], u[k] + (acc - u[k]) * a)
        r_[k] = acc
    g = tg_max(r_)
    lim = g + (tol_at(g) if v["tol"] == "table" else TOL_HOT_K) + v["margin"]
    d = np.where(look, rim_v - lim, -1e9)
    if len(d) < ns:
        return -1e9
    roll = np.lib.stride_tricks.sliding_window_view(d, ns).min(axis=1)
    return float(roll.max())


def variants():
    for m in MARGINS:
        for td in TAU_DECS:
            for fall in (True, False):
                for tol in ("const", "table"):
                    yield {"margin": m, "tau_dec": td, "fall": fall, "tol": tol}


def _eval(args):
    return rule_latches(*args)


# the latches before D-RIMLIM (the C rim limit's own mark is what the offline variants model)
EXISTING = tuple(k for k in LC.LATCHES if k != "rim_limit")


def first_existing(r):
    ts = [r["first"][k]["t_s"] for k in EXISTING if k in r["first"]]
    return min(ts) if ts else None


def score(leak, benign_sets, latches):
    """latches: {id(row): t or None} for the rule; leak rows; benign rows by set."""
    haz = [r for r in leak if r["T_c_steady"] > LC.T_BAR]
    before = after = never = 0
    rule_first = 0
    missed = []
    for r in haz:
        t300 = r["first"].get("T_c_over_300", {}).get("t_s")
        te = first_existing(r)
        tr_ = latches[r["_i"]]
        ts = [x for x in (te, tr_) if x is not None]
        fl = min(ts) if ts else None
        if fl is not None and (t300 is None or fl < t300):
            before += 1
            rule_first += tr_ is not None and (te is None or tr_ < te)
        else:
            missed.append((r["r_leak"], r["T_c_steady"], r["pan"], r.get("delta"), r.get("corner"), r["onset"]))
            if fl is None:
                never += 1
            else:
                after += 1
    worst = min(missed, key=lambda m: m[0], default=None)
    out = {"hazardous": len(haz), "latched_before_300": before, "latched_after_300": after, "never": never,
           "rule_first_before_300": rule_first,
           "largest_not_latched_before_300": None if worst is None else
           {"r_leak_ohm": round(worst[0], 1), "T_c_steady": worst[1], "pan": worst[2], "delta": worst[3],
            "corner": worst[4], "onset": worst[5]},
           "false_latch_before_leak": sum(latches[r["_i"]] is not None and latches[r["_i"]] < LC.LEAK_AT
                                          for r in leak)}
    for name, rows in benign_sets.items():
        out[f"false_{name}"] = sum(latches[r["_i"]] is not None for r in rows)
    return out


def never_latched(leak, latches):
    res = []
    for r in leak:
        if r["T_c_steady"] > LC.T_BAR and first_existing(r) is None and latches[r["_i"]] is None:
            res.append((round(r["r_leak"], 1), r["T_c_steady"]))
    return sorted(res)


def cr5_study(leak, benign_rows):
    """Hardware rim trip lowered by X K, on the true glass."""
    out = []
    g_benign = max(float(np.max(r["trace"][:, 7])) for r in benign_rows)
    haz = [r for r in leak if r["T_c_steady"] > LC.T_BAR]
    for x in (0.0, 4.0, 8.0, 12.0, 16.0):
        top = CR5_BAND[1] - x
        n = 0
        for r in haz:
            tr = r["trace"]
            over = np.nonzero(tr[:, 6] > LC.T_BAR)[0]
            k300 = over[0] if len(over) else len(tr)
            n += bool(np.any(tr[:k300, 7] >= top))
        out.append({"lower_by_K": x, "band_C": [round(CR5_BAND[0] - x, 1), round(top, 1)],
                    "hazardous_trip_at_band_top_before_300": n, "of": len(haz),
                    "benign_glass_max_C": round(g_benign, 1),
                    "benign_margin_to_band_low_K": round(CR5_BAND[0] - x - g_benign, 1)})
    return out


def firmware_constants():
    """The firmware's envelope and tolerance constants against this derivation (gated)."""
    import re
    h = (FW_CONTROL / "pan_rim_limit.h").read_text()
    c = (FW_CONTROL / "pan_rim_limit.c").read_text()

    def arr(name):
        m = re.search(r"#define " + name + r" \{([^}]*)\}", h)
        return [float(x.strip().rstrip("f")) for x in m.group(1).split(",")]

    def dflt(field):
        m = re.search(r"p->" + field + r" = ([0-9.]+)f;", c)
        return float(m.group(1))

    fw = {"tol_T": arr("PRL_TOL_T_C"), "tol_K": arr("PRL_TOL_K"), "w_hi": dflt("w_hi"), "w_lo": dflt("w_lo"),
          "t_eye_hi_c": dflt("t_eye_hi_c"), "margin_k": dflt("margin_k"), "tau_dec_s": dflt("tau_dec_s"),
          "tol_table": re.search(r"p->tol_table = (true|false);", c).group(1) == "true"}
    want = {"tol_T": list(TOL_T), "tol_K": TOL_K, "w_hi": W_HI, "w_lo": W_LO, "t_eye_hi_c": T_EYE_HI,
            "margin_k": CHOSEN["margin"], "tau_dec_s": CHOSEN["tau_dec"], "tol_table": CHOSEN["tol"] == "table"}
    ok = all(abs(a - b) < 0.006 for a, b in zip(fw["tol_K"], want["tol_K"])) and fw["tol_T"] == want["tol_T"] \
        and all(abs(fw[k] - want[k]) < 1e-4 for k in ("w_hi", "w_lo", "t_eye_hi_c", "margin_k", "tau_dec_s")) \
        and fw["tol_table"] == want["tol_table"]
    return {"firmware": fw, "derived": want, "match": ok}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lib", default=cosim.LIB_PATH)
    ap.add_argument("--out", default=str(HERE / "rim-limit.json"))
    args = ap.parse_args()
    cosim.LIB_PATH = args.lib
    sets = {"sweep": _tr(LC.leak_cases()), "benign": _tr(LC.benign_cases(LC.N_SEEDS)),
            "stress_benign": _tr(stress_benign()), "stress_leak": _tr(stress_leak())}
    allc = [c for v in sets.values() for c in v]
    with Pool(min(10, os.cpu_count() or 1), initializer=X._init, initargs=(args.lib,)) as pool:
        rows = pool.map(LC.run_case, allc, chunksize=1)
        for i, r in enumerate(rows):
            r["_i"] = i
        by = {}
        k = 0
        for name, cs in sets.items():
            by[name] = rows[k:k + len(cs)]
            k += len(cs)
        vs = list(variants())
        per_run = pool.map(_eval, [(r["trace"], vs) for r in rows], chunksize=4)
    curve = []
    for j, v in enumerate(vs):
        lat = {i: per_run[i][j] for i in range(len(rows))}
        s_sweep = score(by["sweep"], {"benign": by["benign"], "stress_benign": by["stress_benign"]}, lat)
        s_stress = score(by["stress_leak"], {}, lat)
        row = {**v, "sweep": s_sweep, "stress_leak": {k_: s_stress[k_] for k_ in
                                                      ("hazardous", "latched_before_300", "never",
                                                       "largest_not_latched_before_300")}}
        if v == CHOSEN:
            row["never_latched_sweep"] = never_latched(by["sweep"], lat)
            row["false_latch_rows"] = [(r["set"], r["kind"], r["pan"], r.get("glass_w"), r.get("tau_g"),
                                        r.get("corner"), lat[r["_i"]]) for r in by["benign"] + by["stress_benign"]
                                       if lat[r["_i"]] is not None]
        curve.append(row)
        print(f"m {v['margin']:6.1f} tau {v['tau_dec']:5.0f} fall {int(v['fall'])} tol {v['tol']:5s}: "
              f"sweep before300 "
              f"{s_sweep['latched_before_300']}/{s_sweep['hazardous']} never {s_sweep['never']} "
              f"false benign {s_sweep['false_benign']} stress {s_sweep['false_stress_benign']} "
              f"pre-leak {s_sweep['false_latch_before_leak']} | stress_leak "
              f"{s_stress['latched_before_300']}/{s_stress['hazardous']}", flush=True)
    base = score(by["sweep"], {}, {r["_i"]: None for r in rows})
    base_stress = score(by["stress_leak"], {}, {r["_i"]: None for r in rows})
    benign_all = by["benign"] + by["stress_benign"]
    head = {name: max(headroom(r["trace"], CHOSEN) for r in by[name]) for name in ("benign", "stress_benign")}
    res = {"scope": __doc__.strip(),
           "envelope": {"w_hi": W_HI, "w_lo": W_LO, "w_lo_hot": W_LO_HOT, "t_eye_hi_C": T_EYE_HI, "t_eye_lo_C": T_EYE_LO,
                        "tol_hot_K": TOL_HOT_K, "tol_table_T_C": TOL_T, "tol_table_K": TOL_K,
                        "rows": ENV["rows"],
                        "tg_max_C": {str(t): round(float(tg_max(t)), 1) for t in (100, 150, 200, 230, 250)},
                        "tg_min_C_at_pan_300": round(float(tg_min(300.0)), 1),
                        "rule_lim_C_at_margin0": {str(t): round(float(tg_max(t) + tol_at(tg_max(t))), 1)
                                                  for t in (100, 150, 200, 230, 250)}},
           "runs": {k: len(v) for k, v in by.items()},
           "baseline_existing_latches": {"sweep": base, "stress_leak": {k_: base_stress[k_] for k_ in
                                                                        ("hazardous", "latched_before_300",
                                                                         "never")}},
           "chosen_benign_closest_approach_K": {k: round(v, 2) for k, v in head.items()},
           "chosen": CHOSEN, "curve": curve,
           "cr5": cr5_study(by["sweep"], benign_all),
           "firmware_constants": firmware_constants()}
    chosen = [c for c in curve if all(c[k] == v for k, v in CHOSEN.items())][0]
    res["gate"] = {"firmware_constants_match": res["firmware_constants"]["match"],
                   "chosen_no_false_latch": chosen["sweep"]["false_benign"] == 0
                   and chosen["sweep"]["false_stress_benign"] == 0 and chosen["sweep"]["false_latch_before_leak"] == 0}
    res["all_pass"] = all(res["gate"].values())
    Path(args.out).write_text(json.dumps(res, indent=1, default=float) + "\n")
    print("baseline", base)
    print("chosen variant, benign closest approach to the limit (K, sustained, not falling):",
          res["chosen_benign_closest_approach_K"])
    for c in res["cr5"]:
        print("CR5", c)
    print("GATE", res["gate"])
    print("RIM LIMIT STUDY PASS" if res["all_pass"] else "RIM LIMIT STUDY FAILURE")
    return 0 if res["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
