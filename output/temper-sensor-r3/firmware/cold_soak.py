"""DECISIONS.md D-SOAK: the cold-soak Pt100 leakage check through the firmware's C sources.

The check (components/control/pan_cold_soak.c, evaluated by main/pan_control.c at
PREHEAT entry, before the first power): after the coil has been off >= 30 min,
with 15 min of flat history, the heatsink NTC VALID and <= 45 degC and the rim NTC
saturated, latch FAULT_PROBE_LEAKAGE when the heatsink exceeds the Pt100 by more
than PCS_THRESHOLD_K (19.4 K, hs-ntc.json cold_soak_budget) through the window and
now (PCS_THRESHOLD_MEASURED_K, 16.9 K, when the heatsink reading used a measured
rail at every note through the window and now; D-RAIL). Here the heatsink driver
(components/sensors/hs_ntc.c), the Pt100 conversion
(components/sensors/rtd_convert.c) and the check run in C through the cosim shim
(soak_run: one sample per second, the check evaluated every EVAL_EVERY_S as a
PREHEAT entry then would), fed by a thermal model of an idle unit:

  heatsink  the NTC lug on the heatsink: ambient + standby offset, relaxing with
            tau_h from its start value (88.6 degC after a full-power cook, the
            airflow-r1 sink setpoint; the arrival temperature after transport);
  glass     under the probe: relaxing with tau_g (408-816 s estimated, 1800 s the
            bound the flatness tests are sized for), or following a placed pan;
  Pt100     slaved to the glass through the cartridge's off-pan lag (73 s,
            screen-results.json tau_off); a leak in parallel with the element;
  rim       SATURATED while the glass is below 87.05 degC (rim-ntc.json, the
            lowest saturation temperature over the v3v3 contract).
The channel is the board as built since zapote C45: the CR-8 divider after the
follower, gain 0.855072 (the driver's HS_NTC_ADC_GAIN), so the heatsink is VALID
from -40 degC up. The channel errors are set per corner as hs_ntc.py budgets them,
but applied physically (resistances, rail, ADC error at the attenuation the driver
picks):
  false     the heatsink reads high and the Pt100 low: NTC R25 -2 % and B column,
            pull-up +1.2 %, divider gain 0.854421 (C45 low corner), ADC -50 / -10
            / -5 mV and the SAR sampling bound -3.19 mV at the pin, buffer -2 mV,
            v3v3 3.242 V read as 3.300 V, standby offset +1 K; Pt100 class -,
            Rref +0.15 %, converter -3 LSB, no off-pan self-heating;
  nominal   every term zero;
  miss      the other way (gain 0.855722), with the Pt100's off-pan self-heating
            (2.7 K at 30 degC, hs_ntc.py pt_off_pan_self_heating) and v3v3 3.367 V.
ADC noise (3 mV rms per one-shot sample) runs in every corner.
Two variants, both gated, each with the threshold the firmware itself picks:
  rail_fallback  no rail reading (rail_adc.c "rail unknown"): the driver divides by
                 3.300 V, the true rail at the contract corner (3.242 / 3.367 V);
                 the check uses PCS_THRESHOLD_K;
  rail_measured  the MCP3202 CH1 reading (rail_adc.c), off by rail_adc.py's
                 soak-band error (0.93 %: LM4040A25 tolerance, tempco, current,
                 typical drift and hysteresis, MCP3202 offset/gain/INL, half an
                 LSB, ripple) in the corner's direction; the check uses
                 PCS_THRESHOLD_MEASURED_K.
The pre-C45 network (100 R, no divider, gain 1) is no longer run: its results are
this file's output at 75e512eab (variant as_built there).

1. Threshold cross-check: the C path's steady false-corner gap over the band plus
   the soak residuals (hs-ntc.json) must not exceed PCS_THRESHOLD_K (gated).
2. Benign cold starts (gated, both variants, every corner): 0 latches at any evaluation
   time. Sets: ambient 5-40 degC from power-up; warm restart after a 250 degC cook
   (glass from 250 degC, heatsink from 88.6 degC, tau_g 408/816/1800 s x tau_h
   450/900/1800 s, evaluated every 10 s for 4 h, which includes idle 0, 10, 20,
   30, 45, 60, 90, 120 min); a hot pan (100/200 degC) placed on a soaked unit; a
   cold pan (4 / -18 degC, warming with tau 900/1800 s) placed on a soaked unit;
   transport (a unit at -20 (the storage minimum, docs/ENVIRONMENTAL_SPEC.md), 5,
   50 or 60 degC carried into a 5-40 degC room and powered up on arrival, tau_h
   450/900/1800 s, tau_g 408/816 s); and the
   existing sets' cold starts (every leak-checks.json benign kind starts from a
   unit at 25 degC, hot_glass from glass at 200 degC just after use).
   Reported, not gated (outside the assumptions, D-SOAK limits): tau_h 3600 s; a
   large pot of cold water (tau 20000 s); a pot of frozen food whose melting
   plateau holds the glass at ~2 degC for hours; a unit run in a 0 or -5 degC
   room (below the 5 degC the threshold is budgeted for; rated 10 degC).
3. Hazardous leaks (leak-checks.json, the 277 runs whose untripped T_c exceeds
   300 degC at any time, `leak_checks.hazardous`, owner 2026-10-16; 8 leak values
   300-2320 ohm) at a cold start, soaked steady at
   5-40 degC: caught before heating by the cold-soak check (FAULT_PROBE_LEAKAGE)
   or the existing C1 window (the leaky element below 84.27 ohm,
   FAULT_PROBE_SHORT), for a temperature-independent leak and an Arrhenius family
   R(T) = R_300 exp(Ea/k (1/T - 1/573.15 K)) equal to the sweep's value at 300 degC
   (Ea 0.01-0.2 eV). The sweep's leaks start mid-cook (t = 250 s); this is the
   same leak present at a cold start: a leak that was there before the cook, or
   the next cook after one developed. The miss corner adds the soak residuals
   (heatsink still 1.54 K below the room, Pt100 0.39 K above). The as-built
   nominal coverage of the temperature-independent family is gated, per variant,
   against the recorded EXPECTED_INDEP_NOMINAL (a change either way fails until
   DECISIONS.md is updated).

Writes cold-soak.json. Run: python3 cold_soak.py [--lib path]
"""
from __future__ import annotations

import argparse
import ctypes
import json
import math
import sys
import zlib
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import hs_ntc as H  # noqa: E402
import leak_checks as LC  # noqa: E402  (the bar's hazard predicate)

LIB_PATH = str(HERE / "build" / "libpantemp.so")
VERDICTS = {0: "none", 1: "pass", 2: "leak", 3: "skip_not_soaked", 4: "skip_history", 5: "skip_hs_invalid",
            6: "skip_hs_warm", 7: "skip_hs_drift", 8: "skip_pt_invalid", 9: "skip_pt_drift", 10: "skip_rim_warm"}
HS_STATES = {0: "no_data", 1: "valid", 2: "saturated", 3: "fault"}
EVAL_EVERY_S = 10
TAU_PT_S = 73.0           # cartridge off-pan lag (screen-results.json tau_off, upper)
TAU_PAN_GLASS_S = 60.0    # glass under a placed pan follows it
RIM_SAT_C = 87.05         # rim-ntc.json saturation at v3v3 3.242 V
COOK_SINK_C = H.COOK_SINK_C
COOK_GLASS_C = 250.0
AMBIENTS = H.AMBIENTS
K_B_EV = 8.617333e-5
T_ANCHOR_K = 573.15
EA_EV = (0.01, 0.02, 0.05, 0.1, 0.2)
RAIL_READ_TOL = H.RAIL_READ_TOL   # rail_adc.py soak-band error of the MCP3202 CH1 reading
# Noise: ESP32-S3 ADC1 ~3 mV rms per one-shot sample (the driver trims and averages
# 8 per step, then filters); MAX31865 +/-1 LSB (0.034 K). Assumptions; bench item.
ADC_NOISE_MV = 3.0
PT_NOISE_LSB = 1.0
CORNERS = ("false", "nominal", "miss")
VARIANTS = {"rail_fallback": {"gain": H.ADC_GAIN, "rail": False},
            "rail_measured": {"gain": H.ADC_GAIN, "rail": True}}
# As built (CR-8, C45), nominal corner, temperature-independent leaks: hazardous runs
# caught before heating (cold soak or the 84.27 ohm window) per ambient. Recorded.
EXPECTED_INDEP_NOMINAL = {
    "rail_fallback": {"5.0": 169, "15.0": 200, "25.0": 200, "30.0": 200, "35.0": 200, "40.0": 200},
    "rail_measured": {"5.0": 200, "15.0": 200, "25.0": 200, "30.0": 235, "35.0": 235, "40.0": 235},
}
IDLE_MIN = (0, 10, 20, 30, 45, 60, 90, 120)

# ---- vectorised physics --------------------------------------------------------------
_KS = np.array(sorted(H.VISHAY_104_KOHM), dtype=float)
_LNR = np.log(np.array([H.VISHAY_104_KOHM[int(k)] * 1e3 for k in _KS]))
_INV = 1.0 / (_KS + 273.15)
_BK = np.array(sorted(H.VISHAY_104_BTOL_PCT), dtype=float)
_BV = np.array([H.VISHAY_104_BTOL_PCT[int(k)] for k in _BK]) / 100.0


def ntc_r(t):
    """The table's R(T): ln R linear in 1/T between points, as hs_ntc.py r_of_t."""
    x = 1.0 / (np.asarray(t, dtype=float) + 273.15)
    return np.exp(np.interp(x, _INV[::-1], _LNR[::-1]))


def btol(t):
    return np.interp(np.asarray(t, dtype=float), _BK, _BV)


def pt_r(t):
    """IEC 60751 Pt100 resistance, with the C term below 0 degC."""
    t = np.asarray(t, dtype=float)
    a, b, c = 3.9083e-3, -5.775e-7, -4.183e-12
    r = 1.0 + a * t + b * t * t
    return 100.0 * np.where(t < 0.0, r + c * (t - 100.0) * t ** 3, r)


def corner_terms(corner: str, variant: str):
    s = {"false": -1.0, "nominal": 0.0, "miss": 1.0}[corner]
    v = VARIANTS[variant]
    rail_true = {"false": H.V3V3_MIN, "nominal": H.V3V3_NOM, "miss": H.V3V3_MAX}[corner] * 1e3
    rail_read = rail_true * (1.0 - s * RAIL_READ_TOL) if v["rail"] else -1.0   # false: read high -> hot
    gain_actual = {-1.0: H.GAIN_LO, 0.0: H.ADC_GAIN, 1.0: H.GAIN_HI}[s]
    return {
        "s": s, "rail_true_mv": rail_true, "rail_read_mv": rail_read, "gain_nom": v["gain"],
        "gain_actual": gain_actual,
        # the SAR sampling bound (hs_ntc.py sar_sampling) at the pin, in the corner's direction
        "sar_node_mv": s * H.SAR_BOUND_V * 1e3 / gain_actual,
        "rpu_scale": 1.0 - s * (H.R_PULLUP_TOL + H.R_PULLUP_TC * H.BOARD_DT_K),
        "buf_mv": s * H.BUF_VOS_V * 1e3, "standby_k": H.STANDBY_OFFSET_K if corner == "false" else 0.0,
        "rref_ohm": 430.0 * (1.0 - s * H.PT_RREF_FRAC), "offset_lsb": s * H.PT_OFFSET_LSB,
    }


def node_mv(t_hs, c):
    """HS_SENSE at true heatsink temperature t_hs (vector) for corner terms c."""
    r = ntc_r(t_hs) * (1.0 + c["s"] * H.R25_TOL) * (1.0 + c["s"] * btol(t_hs))
    rp = H.R_PULLUP * c["rpu_scale"]
    # NTC self-heating: the bead above the lug (reads high: lower R)
    p = (c["rail_true_mv"] * 1e-3 / (r + rp)) ** 2 * r
    r2 = ntc_r(t_hs + p / H.NTC_DISSIPATION_W_PER_K) * (1.0 + c["s"] * H.R25_TOL) * (1.0 + c["s"] * btol(t_hs))
    v = c["rail_true_mv"] * r2 / (r2 + rp)
    return v + c["buf_mv"] + c["sar_node_mv"]


def pt_meas_ohm(t_pt, c, corner, r_leak=None):
    t = np.asarray(t_pt, dtype=float)
    cls = np.array([H.PT_CLASS_K(x) for x in np.atleast_1d(t)]).reshape(t.shape)
    sh = np.array([H.pt_off_pan_self_heating(x) for x in np.atleast_1d(t)]).reshape(t.shape) \
        if corner == "miss" else 0.0
    r = pt_r(t + c["s"] * cls + sh)
    if r_leak is not None:
        r = r * r_leak / (r + r_leak)
    return r


# ---- C ----------------------------------------------------------------------------------
_L = None


def lib(path=None):
    global _L
    if _L is None:
        L = ctypes.CDLL(path or LIB_PATH)
        L.soak_new.restype = ctypes.c_void_p
        L.soak_free.argtypes = [ctypes.c_void_p]
        L.soak_init.argtypes = [ctypes.c_void_p] + [ctypes.c_double] * 7
        L.soak_init.restype = ctypes.c_int
        L.soak_param.argtypes = [ctypes.c_void_p, ctypes.c_int]
        L.soak_param.restype = ctypes.c_double
        dp, ip = ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_int)
        L.soak_run.argtypes = [ctypes.c_void_p, ctypes.c_int, dp, dp, ip, ip, ctypes.c_double, ctypes.c_double,
                               ctypes.c_int, dp]
        L.soak_run.restype = ctypes.c_int
        _L = L
    return _L


def run_traj(t_hs, t_pt, glass, coil, corner, variant, threshold, r_leak=None, eval_every=EVAL_EVERY_S, seed=1):
    """One trajectory through the C driver and check. Returns rows (t_s, verdict, gap, hs_state, hs_c, pt_c)."""
    L = lib()
    c = corner_terms(corner, variant)
    n = len(t_hs)
    nm = np.ascontiguousarray(node_mv(np.asarray(t_hs) + c["standby_k"], c), dtype=np.float64)
    # converter noise: a uniform +/-PT_NOISE_LSB dither before the code rounding
    rng = np.random.default_rng(seed)
    po = pt_meas_ohm(t_pt, c, corner, r_leak) + rng.uniform(-PT_NOISE_LSB, PT_NOISE_LSB, n) * H.PT_LSB_OHM
    po = np.ascontiguousarray(po, dtype=np.float64)
    co = np.ascontiguousarray(coil, dtype=np.int32)
    rs = np.ascontiguousarray(np.asarray(glass) < RIM_SAT_C, dtype=np.int32)
    out = np.zeros(6 * (n // eval_every + 2), dtype=np.float64)
    h = L.soak_new()
    try:
        # ADC error sign: false -1 (the pin reads low: a hotter heatsink)
        assert L.soak_init(h, c["gain_nom"], c["gain_actual"], c["s"], c["rail_read_mv"], threshold,
                           ADC_NOISE_MV, seed) == 0
        dp, ip = ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_int)
        rows = L.soak_run(h, n, nm.ctypes.data_as(dp), po.ctypes.data_as(dp), co.ctypes.data_as(ip),
                          rs.ctypes.data_as(ip), c["rref_ohm"], c["offset_lsb"], eval_every,
                          out.ctypes.data_as(dp))
    finally:
        L.soak_free(h)
    return out[: 6 * rows].reshape(rows, 6)


def lag(x, tau, x0=None):
    """First-order lag of a 1 s series."""
    y = np.empty_like(x)
    a = 1.0 - math.exp(-1.0 / tau)
    acc = x[0] if x0 is None else x0
    for i, v in enumerate(x):
        acc += a * (v - acc)
        y[i] = acc
    return y


def relax(n, start, final, tau):
    t = np.arange(n, dtype=float)
    return final + (start - final) * np.exp(-t / tau)


# ---- benign trajectories ----------------------------------------------------------------
def traj(kind, p):
    """(t_hs, glass, coil) at 1 s; t_pt is the glass lagged by TAU_PT_S."""
    a = p["A"]
    n = int(p["t_end"])
    coil = np.zeros(n, dtype=np.int32)
    coil[0] = 1                                   # t = 0: power-up or the end of the cook
    if kind == "ambient":
        hs, gl = np.full(n, a), np.full(n, a)
    elif kind == "warm_restart":
        hs = relax(n, COOK_SINK_C, a, p["tau_h"])
        gl = relax(n, COOK_GLASS_C, a, p["tau_g"])
    elif kind in ("hot_pan", "cold_pan", "cold_pot_large", "frozen_plateau"):
        hs = np.full(n, a)
        gl = np.full(n, a)
        t = np.arange(n, dtype=float) - p["t_place"]
        m = t >= 0
        if kind == "frozen_plateau":
            # melting contents hold the glass near 2 degC from placement to the end
            gl[m] = a + (2.0 - a) * (1.0 - np.exp(-t[m] / TAU_PAN_GLASS_S))
        else:
            gl[m] = a + (p["T_pan"] - a) * (1.0 - np.exp(-t[m] / TAU_PAN_GLASS_S)) * np.exp(-t[m] / p["tau_pan"])
    elif kind == "transport":
        hs = relax(n, p["T0"], a, p["tau_h"])
        gl = relax(n, p["T0"], a, p["tau_g"])
    else:
        raise ValueError(kind)
    x0 = gl[0]
    return hs, lag(gl, TAU_PT_S, x0), gl, coil


def benign_cases():
    gated, reported = [], []
    for a in AMBIENTS:
        gated.append(("ambient", {"A": a, "t_end": 3 * 3600}))
        for tg in (408.0, 816.0, 1800.0):
            for th in (450.0, 900.0, 1800.0):
                gated.append(("warm_restart", {"A": a, "tau_g": tg, "tau_h": th, "t_end": 4 * 3600}))
            reported.append(("warm_restart", {"A": a, "tau_g": tg, "tau_h": 3600.0, "t_end": 5 * 3600}))
        for tp in (1800.0, 3600.0):
            for th_pan in (100.0, 200.0):
                gated.append(("hot_pan", {"A": a, "T_pan": th_pan, "tau_pan": 1800.0, "t_place": tp,
                                          "t_end": int(tp + 3600)}))
            for tc in (4.0, -18.0):
                for tau in (900.0, 1800.0):
                    gated.append(("cold_pan", {"A": a, "T_pan": tc, "tau_pan": tau, "t_place": tp,
                                               "t_end": int(tp + 3 * 3600)}))
            reported.append(("cold_pot_large", {"A": a, "T_pan": 4.0, "tau_pan": 20000.0, "t_place": tp,
                                                 "t_end": int(tp + 12 * 3600)}))
            reported.append(("frozen_plateau", {"A": a, "t_place": tp, "t_end": int(tp + 3 * 3600)}))
    for a in (0.0, -5.0):
        reported.append(("ambient", {"A": a, "t_end": 3 * 3600}))
    for t0 in (-20.0, 5.0, 50.0, 60.0):
        for a in AMBIENTS:
            for th in (450.0, 900.0, 1800.0):
                for tg in (408.0, 816.0):
                    gated.append(("transport", {"A": a, "T0": t0, "tau_h": th, "tau_g": tg, "t_end": 4 * 3600}))
            reported.append(("transport", {"A": a, "T0": t0, "tau_h": 3600.0, "tau_g": 816.0, "t_end": 5 * 3600}))
    return gated, reported


def run_benign(job):
    kind, p, corner, variant, thr = job
    hs, pt, gl, coil = traj(kind, p)
    seed = zlib.crc32(repr((kind, sorted(p.items()), corner)).encode())
    rows = run_traj(hs, pt, gl, coil, corner, variant, thr, seed=seed)
    v = rows[:, 1].astype(int)
    leak = rows[v == 2]
    ran = rows[(v == 1) | (v == 2)]
    return {"kind": kind, **{k: x for k, x in p.items()}, "corner": corner, "variant": variant,
            "evaluations": int(len(rows)), "ran": int(len(ran)), "latches": int(len(leak)),
            "first_latch_s": float(leak[0, 0]) if len(leak) else None,
            "max_gap_K": round(float(np.nanmax(ran[:, 2])), 3) if len(ran) else None,
            "verdicts": dict(Counter(VERDICTS[int(x)] for x in v)),
            "at_idle_min": {m: VERDICTS[int(rows[rows[:, 0] == m * 60.0][0, 1])] for m in IDLE_MIN
                            if kind in ("ambient", "warm_restart", "transport") and m * 60 < len(hs)}}


# ---- steady soaks -----------------------------------------------------------------------
STEADY_N = 2400


def steady(a, corner, variant, thr, r_leak=None, residual=False):
    """A unit soaked at ambient a for STEADY_N s; the verdict at the end."""
    hs = np.full(STEADY_N, a - (H.residual(H.HS_FLAT_K) if residual else 0.0))
    pt = np.full(STEADY_N, a + (H.residual(H.PT_FLAT_K) if residual else 0.0))
    coil = np.zeros(STEADY_N, dtype=np.int32)
    coil[0] = 1
    rows = run_traj(hs, pt, np.full(STEADY_N, a), coil, corner, variant, thr, r_leak, eval_every=STEADY_N - 1)
    last = rows[-1]
    return {"verdict": VERDICTS[int(last[1])], "gap_K": None if math.isnan(last[2]) else round(float(last[2]), 3),
            "hs_state": HS_STATES[int(last[3])], "hs_C": round(float(last[4]), 3),
            "pt_C": None if math.isnan(last[5]) else round(float(last[5]), 3)}


def derive_threshold(variant):
    """The C path's false-corner steady gap over 5..45 degC where the check runs, plus the soak residuals."""
    rows, worst = [], -math.inf
    for a in np.arange(5.0, H.HS_MAX_C - H.STANDBY_OFFSET_K + 0.01, 0.5):
        r = steady(float(a), "false", variant, 1000.0)
        if r["verdict"] == "pass":
            worst = max(worst, r["gap_K"])
        rows.append({"A_C": float(a), **r})
    res = H.residual(H.HS_FLAT_K) + H.residual(H.PT_FLAT_K)
    band = [x["A_C"] for x in rows if x["verdict"] == "pass"]
    return {"steady_false_gap_max_K": round(worst, 3), "residuals_K": round(res, 3),
            "threshold_K": round(math.ceil((worst + res) * 10 - 1e-9) / 10, 1),
            "band_A_C": [min(band), max(band)] if band else None, "rows": rows}


def hazard_job(job):
    variant, corner, family, a, r_hot, thr = job
    ea = 0.0 if family == "independent" else float(family)
    r_amb = r_hot * math.exp(ea / K_B_EV * (1.0 / (a + 273.15) - 1.0 / T_ANCHOR_K))
    r = steady(a, corner, variant, thr, r_amb, residual=(corner == "miss"))
    short = r["pt_C"] is None
    return (variant, corner, family, a, r_hot), {"R_at_ambient_ohm": round(r_amb, 1), **r,
                                                 "caught_by": "window_84.27" if short
                                                 else ("cold_soak" if r["verdict"] == "leak" else None)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lib", default=str(HERE / "build" / "libpantemp.so"))
    ap.add_argument("--out", default=str(HERE / "cold-soak.json"))
    ap.add_argument("--jobs", type=int, default=8)
    args = ap.parse_args()
    lib(args.lib)
    gate = {}

    h = lib().soak_new()
    lib().soak_init(h, 1.0, 1.0, 0.0, -1.0, 0.0, 0.0, 1.0)
    fw = {n: lib().soak_param(h, i) for i, n in enumerate(("threshold_k", "soak_n_s", "window_s", "bucket_s",
                                                           "hs_flat_k", "pt_flat_k", "hs_max_c",
                                                           "threshold_measured_k"))}
    lib().soak_free(h)
    hs_json = json.loads((HERE / "hs-ntc.json").read_text())
    analytic = hs_json["cold_soak_budget"]
    analytic_m = hs_json["cold_soak_budget_rail_measured"]
    fw_thr = {"rail_fallback": fw["threshold_k"], "rail_measured": fw["threshold_measured_k"]}
    an_thr = {"rail_fallback": analytic["threshold_K"], "rail_measured": analytic_m["threshold_K"]}

    # 1. thresholds
    thr = {v: derive_threshold(v) for v in VARIANTS}
    for v in VARIANTS:
        gate[f"threshold_c_path_within_firmware_{v}"] = thr[v]["threshold_K"] <= fw_thr[v] + 1e-6
        gate[f"firmware_threshold_is_hs_ntc_budget_{v}"] = abs(fw_thr[v] - an_thr[v]) < 1e-6
    # the firmware picks per evaluation (0: its own two thresholds)
    use_thr = {v: 0.0 for v in VARIANTS}
    for v, d in thr.items():
        print(f"threshold {v}: C-path steady false gap {d['steady_false_gap_max_K']} K + residuals "
              f"{d['residuals_K']} K -> {d['threshold_K']} K (firmware {fw_thr[v]:.1f} K); check runs at "
              f"{d['band_A_C']} degC (false corner)")

    # 2. benign
    gated, reported = benign_cases()
    jobs = [(k, p, c, v, use_thr[v]) for (k, p) in gated for c in CORNERS for v in VARIANTS]
    rjobs = [(k, p, c, v, use_thr[v]) for (k, p) in reported for c in CORNERS for v in VARIANTS]
    with Pool(args.jobs, initializer=lib, initargs=(args.lib,)) as pool:
        ben = pool.map(run_benign, jobs, chunksize=4)
        rep = pool.map(run_benign, rjobs, chunksize=2)

    def summarize(rows):
        out = {}
        for v in VARIANTS:
            for r in (x for x in rows if x["variant"] == v):
                d = out.setdefault(v, {}).setdefault(r["kind"], {"trajectories": 0, "evaluations": 0, "ran": 0,
                                                                 "latched_trajectories": 0, "latches": 0,
                                                                 "max_gap_K": None})
                d["trajectories"] += 1
                d["evaluations"] += r["evaluations"]
                d["ran"] += r["ran"]
                d["latches"] += r["latches"]
                d["latched_trajectories"] += 1 if r["latches"] else 0
                if r["max_gap_K"] is not None:
                    d["max_gap_K"] = r["max_gap_K"] if d["max_gap_K"] is None else max(d["max_gap_K"], r["max_gap_K"])
        return out

    ben_sum = summarize(ben)
    idle = {}
    for x in ben:
        if x["variant"] == "rail_fallback" and x["at_idle_min"]:
            for m, vd in x["at_idle_min"].items():
                d = idle.setdefault(x["kind"], {}).setdefault(str(m), Counter())
                d[vd] += 1
    idle = {k: {m: dict(c) for m, c in d.items()} for k, d in idle.items()}
    rep_sum = summarize(rep)
    margin = {}
    for v in VARIANTS:
        gate[f"benign_{v}_no_latch"] = all(d["latches"] == 0 for d in ben_sum[v].values())
        gaps = [d["max_gap_K"] for d in ben_sum[v].values() if d["max_gap_K"] is not None]
        margin[v] = {"threshold_K": round(fw_thr[v], 1), "largest_benign_gap_K": max(gaps),
                     "margin_K": round(fw_thr[v] - max(gaps), 3)}
    # existing sets' cold starts (leak-checks.json benign kinds)
    lc = json.loads((HERE / "leak-checks.json").read_text())
    kinds = sorted({f"{b['set']}/{b['kind']}" for b in lc["benign_rows"]})
    existing = {}
    for k in kinds:
        if k.endswith("hot_glass"):
            existing[k] = "a pan on glass at 200 degC just after use: warm_restart, idle 0 (gated above)"
        else:
            existing[k] = {v: {c: steady(25.0, c, v, 0.0)["verdict"] for c in CORNERS} for v in VARIANTS}
    gate["existing_sets_no_latch"] = all(isinstance(e, str) or all("leak" not in d.values() for d in e.values())
                                         for e in existing.values())

    # 3. hazardous
    haz = [r for r in lc["leak_rows"] if LC.hazardous(r)]
    by_r = Counter(r["r_leak_ohm"] for r in haz)
    fams = ("independent",) + tuple(str(e) for e in EA_EV)
    hjobs = [(v, c, f, a, rr, use_thr[v]) for v in VARIANTS for c in ("nominal", "miss") for f in fams
             for a in AMBIENTS for rr in sorted(by_r)]
    with Pool(args.jobs, initializer=lib, initargs=(args.lib,)) as pool:
        hres = dict(pool.map(hazard_job, hjobs, chunksize=8))
    coverage = {}
    for v in VARIANTS:
        for c in ("nominal", "miss"):
            for f in fams:
                for a in AMBIENTS:
                    soak = sum(by_r[rr] for rr in by_r if hres[(v, c, f, a, rr)]["caught_by"] == "cold_soak")
                    win = sum(by_r[rr] for rr in by_r if hres[(v, c, f, a, rr)]["caught_by"] == "window_84.27")
                    skip = Counter(hres[(v, c, f, a, rr)]["verdict"] for rr in by_r
                                   if hres[(v, c, f, a, rr)]["caught_by"] is None)
                    coverage.setdefault(v, {}).setdefault(c, {}).setdefault(f, {})[str(a)] = {
                        "hazardous": len(haz), "caught_before_heating": soak + win, "cold_soak": soak,
                        "window_84.27_only": win, "not_caught_verdicts_by_leak_value": dict(skip)}
    base = {str(a): sum(by_r[rr] for rr in by_r
                        if hres[("rail_fallback", "nominal", "independent", a, rr)]["caught_by"] == "window_84.27")
            for a in AMBIENTS}
    indep_nom = {v: {a: coverage[v]["nominal"]["independent"][a]["caught_before_heating"] for a in
                     coverage[v]["nominal"]["independent"]} for v in VARIANTS}
    for v in VARIANTS:
        expected = EXPECTED_INDEP_NOMINAL[v]
        gate[f"hazardous_indep_nominal_as_recorded_{v}"] = expected is None or indep_nom[v] == expected
    per_value = {f"{v}/{c}/{f}/{a}/{rr}": x for (v, c, f, a, rr), x in hres.items()}

    out = {
        "scope": __doc__.strip(),
        "firmware_params": fw,
        "hs_ntc_budget_threshold_K": analytic["threshold_K"],
        "thresholds": {v: {k: x for k, x in d.items() if k != "rows"} for v, d in thr.items()},
        "threshold_rows": {v: d["rows"] for v, d in thr.items()},
        "thresholds_used": {v: fw_thr[v] for v in VARIANTS},
        "rail_read_tol_pct": round(RAIL_READ_TOL * 100, 4),
        "benign_gated": ben_sum, "benign_false_latch_margin": margin,
        "benign_gated_rail_fallback_verdicts_at_idle_min": idle,
        "benign_reported_outside_assumptions": rep_sum,
        "benign_reported_latched": [r for r in rep if r["latches"]],
        "existing_sets_cold_start_at_25C": existing,
        "hazardous": {"runs": len(haz), "by_r_leak_ohm": {str(k): n for k, n in sorted(by_r.items())},
                      "baseline_window_84.27_only_by_ambient": base,
                      "coverage": coverage, "per_leak_value": per_value},
        "gate": gate, "all_pass": all(gate.values()),
    }
    Path(args.out).write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    for v in VARIANTS:
        print(f"benign gated ({v}):", {k: (d["trajectories"], d["ran"], d["latches"])
                                       for k, d in ben_sum[v].items()})
        print(f"benign reported ({v}):", {k: (d["trajectories"], d["latched_trajectories"])
                                          for k, d in rep_sum[v].items()})
        print(f"false-latch margin ({v}):", margin[v])
    for v in VARIANTS:
        for c in ("nominal", "miss"):
            print(f"hazardous caught before heating {v}/{c}: " + "; ".join(
                f"{f}: " + " ".join(f"{a}:{coverage[v][c][f][str(a)]['caught_before_heating']}" for a in AMBIENTS)
                for f in fams))
    print("baseline 84.27 ohm window only:", base)
    for m in IDLE_MIN:
        print(f"warm restart, idle {m} min (rail fallback, all corners):",
              idle.get("warm_restart", {}).get(str(m)))
    print("indep nominal:", indep_nom)
    for k, v in gate.items():
        print(f"{'PASS' if v else 'FAIL'} {k}")
    print("ALL COLD SOAK CHECKS PASS" if out["all_pass"] else "COLD SOAK CHECK FAILURE")
    return 0 if out["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
