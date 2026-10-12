#!/usr/bin/env python3
"""Tank-RMS alternatives study (numpy only).  Rerun:  python3 rms_alternatives.py

Writes results.json and cost.csv next to this file.  Reads lcsc-snapshot-2026-10-12.json (no network).
Simulates, for every option, the half-line-cycle tank RMS the firmware would compute
(n21_binding.c: 13 acquisition slots per half cycle at 625 us, tank_rms = sqrt(mean(slot^2)))
against the true half-cycle RMS of a synthesised series-resonant tank current.

Everything marked ASSUMED is a model parameter that no datasheet in this worktree backs; the
README lists them.  The two control asserts at the bottom must pass or the script exits non-zero.
"""
import csv
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))

# --------------------------------------------------------------------------------------------
# Constants from the design (cited in README)
# --------------------------------------------------------------------------------------------
F_LINE = 60.0
HALF = 0.5 / F_LINE                  # 8.333 ms half line cycle
FS = 2.0e6                           # simulation grid
DT = 1.0 / FS
V_PER_A = 0.015                      # ct_mon, 1:100 CT into 1.5 ohm (n21_signal.h)
RMS_V_PER_A = 0.060                  # AD8436 x gain 4 (n21_signal.h)
SLOT = 625e-6                        # acq_period_us (n21_binding.h)
FORM_FACTOR_SINE = np.pi / (2 * np.sqrt(2))   # 1.1107

# AD8436 model.  Datasheet (Rev. B Table 1, cited in controller DECISIONS C19): 1 % additional error at
# 65 kHz, 300 mV rms.  Modelled as the guaranteed bound: single pole with gain(65k) = 0.99.
AD_FC = 65e3 / np.sqrt(1.0 / 0.99 ** 2 - 1.0)
AD_TAU_AVG = 3.4e-3 / np.log(1000.0)      # DECISIONS C19: 3.4 ms to 0.1 % with CAVG = 100 nF (bench item)
AD_TAU_OUT = 16e3 * 10e-9                 # internal 16 k + 10 nF C0G on OUT
# LTC1968 (ADI product page via DECISIONS C19: 500 kHz for 1 %); treated as single pole at 500 kHz. UNVERIFIED.
LTC1968_FC = 500e3

# Tolerance stack (percent of reading), worst case, applied on top of the simulated systematic error.
# One-point gain trim at 40 kHz / 22 A removes initial gain error (COMMISSIONING step 1: rms_gain_trim).
TEMP_SPAN_K = 45.0                   # 25 C +/- 45 K  (-20..70 C inside the enclosure)  ASSUMED
TOL = {
    "A0_AD8436BRQZ": {"trim_residual": 0.10, "ic_gain_tc": 50e-6 * TEMP_SPAN_K * 100,   # ASSUMED 50 ppm/K
                      "ref_lm4040_tc": 100e-6 * TEMP_SPAN_K * 100},                       # LM4040A25 100 ppm/K max
    "A1_AD8436ARQZ": {"trim_residual": 0.10, "ic_gain_tc": 50e-6 * TEMP_SPAN_K * 100,
                      "ref_lm4040_tc": 100e-6 * TEMP_SPAN_K * 100},
    "B_FW_rectifier_TLV9062": {"trim_residual": 0.10, "resistor_match_tc": 0.20 + 50e-6 * TEMP_SPAN_K * 100,
                               "ref_lm4040_tc": 100e-6 * TEMP_SPAN_K * 100},
    "C1_ESP32_ADC_as_built_pattern": {"trim_residual": 0.10, "adc_gain_tc": 1.0, "adc_inl_residual": 0.5},   # ASSUMED
    "C2_ESP32_ADC_fs_selected": {"trim_residual": 0.10, "adc_gain_tc": 1.0, "adc_inl_residual": 0.5},
    "D_LTC1968": {"trim_residual": 0.10, "ic_gain_tc": 50e-6 * TEMP_SPAN_K * 100,
                  "ref_lm4040_tc": 100e-6 * TEMP_SPAN_K * 100},
}

# --------------------------------------------------------------------------------------------
# Waveform synthesis
# --------------------------------------------------------------------------------------------

def tank_harmonics(f, L, C, R, nmax=15):
    """Series RLC driven by a +/-1 square wave (fundamental of a full bridge): harmonic amplitudes/phases."""
    ns = np.arange(1, nmax + 1, 2)
    w = 2 * np.pi * f * ns
    z = R + 1j * (w * L - 1.0 / (w * C))
    cur = (4.0 / (np.pi * ns)) / z
    return ns, np.abs(cur), np.angle(cur)


def make_case(name, f, ns, amps, phs, iset, env="rect", note=""):
    return dict(name=name, f=f, ns=np.asarray(ns, float), amps=np.asarray(amps, float),
                phs=np.asarray(phs, float), iset=iset, env=env, note=note)


def envelope(t, kind):
    if kind == "flat":
        return np.ones_like(t)
    e = np.abs(np.sin(2 * np.pi * F_LINE * t))
    if kind == "burst":
        h = np.floor(t / HALF).astype(int)
        e = e * ((h % 8) < 4)
    return e


def carrier_scale(case):
    """Scale so the true RMS over an ON half-cycle equals iset (the firmware's 'half-cycle RMS')."""
    a2 = 0.5 * np.sum(case["amps"] ** 2)           # mean square of the carrier
    ms_env = 1.0 if case["env"] == "flat" else 0.5  # mean of |sin|^2 over the half cycle
    return case["iset"] / np.sqrt(a2 * ms_env)


def current(t, case, harm_gain=None):
    g = np.ones_like(case["ns"]) if harm_gain is None else harm_gain
    k = carrier_scale(case)
    i = np.zeros_like(t)
    for n, a, p, gg in zip(case["ns"], case["amps"], case["phs"], g):
        i += gg * k * a * np.sin(2 * np.pi * n * case["f"] * t + p)
    return i * envelope(t, case["env"])


def build_cases():
    cases = []
    C = 0.50e-6
    L = 70e-6
    for f in (31e3, 35e3, 40e3, 45e3, 50e3, 55e3):
        ns, a, p = tank_harmonics(f, L, C, 1.0)
        cases.append(make_case(f"pan_R1.0_f{int(f/1e3)}k_22A", f, ns, a, p, 22.0, "rect", "nominal pan, 70 uH / 0.5 uF"))
    for f in (35e3, 55e3):
        ns, a, p = tank_harmonics(f, L, C, 0.4)
        cases.append(make_case(f"lowR_R0.4_f{int(f/1e3)}k_28A", f, ns, a, p, 28.0, "rect", "low-R pan at the 28 A ceiling"))
    # near resonance: f = 1.05 f_res (ZVS limit), high Q (pan removal / empty coil), 22 A and a 4 A pan-detect level
    for r, i, tag in ((0.15, 22.0, "empty_coil_22A"), (0.15, 4.0, "empty_coil_4A"), (1.0, 22.0, "pan")):
        f = 38e3
        fres = f / 1.05
        Ln = 1.0 / ((2 * np.pi * fres) ** 2 * C)
        ns, a, p = tank_harmonics(f, Ln, C, r)
        cases.append(make_case(f"near_res_{tag}_f38k", f, ns, a, p, i, "rect", "f = 1.05 f_res"))
    # far above resonance (more harmonic content): small L
    ns, a, p = tank_harmonics(55e3, 35e-6, C, 1.0)
    cases.append(make_case("far_above_res_f55k_22A", 55e3, ns, a, p, 22.0, "rect", "L = 35 uH, f/f_res = 1.5"))
    # stress waveform: extra 3rd (12 %) and 5th (6 %) harmonics at arbitrary phase (dead-time notch / ringing proxy)
    ns, a, p = tank_harmonics(45e3, L, C, 1.0)
    a = a.copy()
    a[1] = 0.12 * a[0]
    a[2] = 0.06 * a[0]
    p = p.copy()
    p[1] = 1.0
    p[2] = -0.7
    cases.append(make_case("stress_h3_12pct_h5_6pct_f45k", 45e3, ns, a, p, 22.0, "rect", "synthetic distortion"))
    # pure sine drive (the COMMISSIONING step 1 trim signal) with flat envelope and with line envelope
    cases.append(make_case("sine_f40k_22A_flat", 40e3, [1], [1.0], [0.0], 22.0, "flat", "bench trim signal"))
    cases.append(make_case("sine_f40k_22A_rect", 40e3, [1], [1.0], [0.0], 22.0, "rect", "sine carrier, line envelope"))
    # burst (4 ON / 4 OFF half cycles): first and last ON half
    ns, a, p = tank_harmonics(40e3, L, C, 1.0)
    cases.append(make_case("burst_4on4off_f40k_22A", 40e3, ns, a, p, 22.0, "burst", "burst_scheduler-style gating"))
    return cases


# --------------------------------------------------------------------------------------------
# Signal-chain models
# --------------------------------------------------------------------------------------------

def lpf1(x, dt, tau, chunk=2048):
    """First-order low pass, y[n] = a y[n-1] + (1-a) x[n], block-vectorised."""
    a = np.exp(-dt / tau)
    y = np.empty_like(x)
    prev = x[0]
    k = np.arange(chunk)
    ak = a ** k
    for s in range(0, len(x), chunk):
        xb = x[s:s + chunk]
        m = len(xb)
        # y_j = a^(j+1) prev + (1-a) sum_{i<=j} a^(j-i) x_i
        # compute by recursion over the block using cumulative form with scaling by a^-i (block is short)
        inv = a ** (-k[:m])
        acc = np.cumsum(xb * inv)
        yb = (a * prev) * ak[:m] + (1 - a) * ak[:m] * acc
        # the (a*prev)*a^j term should be a^(j+1) prev
        yb = yb * 1.0
        y[s:s + m] = yb
        prev = yb[-1]
    return y


def slot_times(window_start, offset, n_slots=None):
    t = window_start + offset + SLOT * np.arange(40)
    return t[t < window_start + HALF]


def sample(sig, t_grid0, times):
    idx = np.clip(np.round((times - t_grid0) / DT).astype(int), 0, len(sig) - 1)
    return sig[idx]


def window_grid(h):
    t0 = (h - 3) * HALF
    n = int(round(4 * HALF / DT))
    return t0, t0 + DT * np.arange(n)


def true_rms(case, h):
    t0, t = window_grid(h)
    i = current(t, case)
    m = (t >= h * HALF) & (t < (h + 1) * HALF)
    return float(np.sqrt(np.mean(i[m] ** 2)))


OFFSETS = np.array([0.0, 1.3, 2.9, 4.1, 5.5]) * 1e-4      # slot-phase offsets against LINE_ZC (<625 us)


def pooled(v_adc, t0, h, fine, quant):
    """fine=False: the firmware estimator, sqrt(mean of the 13-14 slot readings^2) for several slot phases against
    LINE_ZC.  fine=True: the converter-only value, mean square of the converter output over the exact half cycle."""
    if fine:
        t = t0 + DT * np.arange(len(v_adc))
        m = (t >= h * HALF) & (t < (h + 1) * HALF)
        return np.array([np.sqrt(np.mean(v_adc[m] ** 2)) / RMS_V_PER_A])
    ests = []
    for off in OFFSETS:
        s = sample(v_adc, t0, slot_times(h * HALF, off))
        if quant:
            lsb = 3.3 / 4096.0
            s = np.round(s / lsb) * lsb
        ests.append(np.sqrt(np.mean(s ** 2)) / RMS_V_PER_A)
    return np.array(ests)


def est_AD8436(case, h, gain_err=0.0, offset_v=0.0, fc=AD_FC, tau_avg=AD_TAU_AVG, tau_out=AD_TAU_OUT,
               ref_err=0.0, quant=True, fine=False):
    """AD8436 + gain-4 buffer + MCP3202 (12 bit, ratiometric to LM4040 so ref_err is the ref's drift)."""
    t0, t = window_grid(h)
    g = 1.0 / np.sqrt(1.0 + (case["ns"] * case["f"] / fc) ** 2)
    v = current(t, case, harm_gain=g) * V_PER_A
    y2 = lpf1(v * v, DT, tau_avg)
    out = np.sqrt(np.maximum(y2, 0)) * (1 + gain_err) + offset_v
    out = lpf1(out, DT, tau_out)
    v_adc = out * 4.0 * (1 + ref_err)
    return pooled(v_adc, t0, h, fine, quant)


def est_LTC1968(case, h, **kw):
    # unity-gain RMS converter + same x4 buffer/ADC scaling for a like-for-like comparison
    return est_AD8436(case, h, fc=LTC1968_FC, **kw)


def est_FW(case, h, gbw=10e6, sr=6.5e6, vd=0.30, tau=0.2e-3, gain_err=0.0, offset_v=0.0, ref_err=0.0, quant=True,
           fine=False):
    """Precision full-wave rectifier (mean-|x|) + single-pole RC + gain 4*pi/(2 sqrt2) scaling to RMS units.

    Dead zone per zero crossing: the op-amp must slew through the diode drop open loop.  Time to reach Vd with
    the loop open and half the input at the inverting node: t_gbw = sqrt(2 Vd /(pi GBW s)) ... lost area = s t^2.
    First-order model; see README risks."""
    t0, t = window_grid(h)
    v = current(t, case) * V_PER_A
    a = np.abs(v)
    sgn = np.signbit(v)
    cross = np.nonzero(sgn[1:] != sgn[:-1])[0]
    s = np.abs(v[cross + 1] - v[cross]) / DT          # V/s at each crossing
    s = np.maximum(s, 1.0)
    t_gbw = np.sqrt(2.0 * vd / (np.pi * gbw * 0.5 * s))
    t_sl = 2.0 * vd / sr
    area = s * (t_gbw + t_sl) ** 2
    lim = a[cross] * 0 + 0.0
    a2 = a.copy()
    a2[cross] -= area / DT * 0.5
    a2[cross + 1] -= area / DT * 0.5
    y = lpf1(a2, DT, tau)
    g_out = 4.0 * FORM_FACTOR_SINE
    out = y * g_out * (1 + gain_err) + offset_v * g_out
    v_adc = out * (1 + ref_err)
    return pooled(v_adc, t0, h, fine, quant)


# ESP32-S3 continuous ADC, 80 kS/s, pattern VBUS,CT,VBUS,CT,VBUS,HS,COIL,M12,RIM (README "Sampling plan")
PATTERN_N = 9
CT_SLOTS = (1, 3)
ADC_BW = 1.0e6                   # ASSUMED effective S/H tracking bandwidth (aperture/settling not specified)
ADC_NOISE_LSB = 2.0              # ASSUMED rms noise
ADC_LSB_V = 2.9 / 4095.0         # ATTEN3 full scale 2.9 V
INL_CUBIC_V = 0.015              # ASSUMED +/-15 mV cubic bow over +/-1.25 V


def ct_sample_times(window_start, fs_adc, offset):
    tp = PATTERN_N / fs_adc
    n = int(HALF / tp) + 3
    # the DMA stream is continuous: patterns that started before the window still put samples inside it
    base = window_start - tp + (offset % tp) + tp * np.arange(n)[:, None] + (np.array(CT_SLOTS)[None, :] / fs_adc)
    t = base.ravel()
    return t[(t >= window_start) & (t < window_start + HALF)]


def lock_metric(f, fs_adc):
    """Firmware-computable and exact: for a unit sine the sampled mean square is (1 - Re(S e^{j2 phi}))/2 with
    S = mean(exp(j 4 pi f t_k)), so max over phase of the relative mean-square error is |S|."""
    ts = ct_sample_times(0.0, fs_adc, 0.0)
    # fundamental^2 lands at 2f; fundamental x 3rd/5th harmonic at 2f/4f/6f (weights ~ typical harmonic ratios)
    return float(sum(w * np.abs(np.mean(np.exp(1j * 2 * np.pi * k * f * ts))) for k, w in ((2, 1.0), (4, 0.3), (6, 0.1))))


FS_CANDIDATES = [80e3 - 125.0 * m for m in range(64)]      # 72.0 .. 80.0 kS/s; VBUS stays >= 24 kS/s (needs >= 20)


def est_ESP32(case, h, select_fs=False, rng_seed=1, return_slots=False):
    t0, t = window_grid(h)
    fs_adc = 80e3
    if select_fs:
        fs_adc = min(FS_CANDIDATES, key=lambda fs: lock_metric(case["f"], fs))
    g = 1.0 / np.sqrt(1.0 + (case["ns"] * case["f"] / ADC_BW) ** 2)
    rng = np.random.default_rng(rng_seed)
    ests, slot_max = [], []
    for off in OFFSETS:
        ts = ct_sample_times(h * HALF, fs_adc, off)
        # evaluate the current analytically at the sample instants
        k = carrier_scale(case)
        x = np.zeros_like(ts)
        for n, a, p, gg in zip(case["ns"], case["amps"], case["phs"], g):
            x += gg * k * a * np.sin(2 * np.pi * n * case["f"] * ts + p)
        x *= envelope(ts, case["env"])
        v = x * V_PER_A
        u = v / 1.25
        v = v + INL_CUBIC_V * u ** 3                  # cubic bow of the ADC transfer curve
        v = v + rng.normal(0, ADC_NOISE_LSB * ADC_LSB_V, v.shape)
        v = np.round(v / ADC_LSB_V) * ADC_LSB_V
        n_eff = len(CT_SLOTS) * fs_adc / PATTERN_N * HALF       # time-weighted: expected sample count in the window
        ests.append(np.sqrt(np.sum(v ** 2) / n_eff) / V_PER_A)
        # per-625 us slot rms (what an unchanged per-sample crest guard would see)
        slot_idx = np.floor((ts - h * HALF - off) / SLOT).astype(int)
        mx = 0.0
        for q in np.unique(slot_idx):
            vv = v[slot_idx == q]
            if len(vv) >= 6:
                mx = max(mx, np.sqrt(np.mean(vv ** 2)) / V_PER_A)
        slot_max.append(mx)
    if return_slots:
        return np.array(ests), np.array(slot_max)
    return np.array(ests)


# --------------------------------------------------------------------------------------------
# Option registry and evaluation
# --------------------------------------------------------------------------------------------
FINE_OPTIONS = {
    "A1_AD8436ARQZ": lambda c, h: est_AD8436(c, h, fine=True),
    "A0_AD8436BRQZ": lambda c, h: est_AD8436(c, h, fine=True),
    "B_FW_rectifier_TLV9062": lambda c, h: est_FW(c, h, fine=True),
    "D_LTC1968": lambda c, h: est_LTC1968(c, h, fine=True),
}
OPTIONS = {
    "A0_AD8436BRQZ": lambda c, h: est_AD8436(c, h),
    "A1_AD8436ARQZ": lambda c, h: est_AD8436(c, h),                     # systematic part identical; tolerance differs (see README)
    "B_FW_rectifier_TLV9062": lambda c, h: est_FW(c, h),
    "C1_ESP32_ADC_as_built_pattern": lambda c, h: est_ESP32(c, h, select_fs=False),
    "C2_ESP32_ADC_fs_selected": lambda c, h: est_ESP32(c, h, select_fs=True),
    "D_LTC1968": lambda c, h: est_LTC1968(c, h),
}
EXTRA_TOL = {                     # additional percent terms of A1 vs A0 (AD8436ARQZ: 0.5 % vs 0.25 % grade)
    "A1_AD8436ARQZ": {"grade_gain": 0.0},   # initial gain error is trimmed; offset 500 vs 250 uV is trimmed at idle
}


def eval_option(name, cases, trim_case, fine=False):
    fn = FINE_OPTIONS[name] if fine else OPTIONS[name]
    th = 10
    tr = true_rms(trim_case, th)
    if name.startswith("C"):
        # the trim is an analogue gain; take it with the well-conditioned sampling so a phase-locked bench frequency
        # does not poison it (the as-built pattern failure is reported separately in the lock scan)
        trim = tr / np.mean(est_ESP32(trim_case, th, select_fs=True))
    else:
        trim = tr / np.mean(fn(trim_case, th))      # one-point gain trim (COMMISSIONING step 1)
    rows = []
    for c in cases:
        hs = [8, 11] if c["env"] == "burst" else [10]
        for h in hs:
            tr = true_rms(c, h)
            e = fn(c, h) * trim
            err = (e / tr - 1.0) * 100.0
            rows.append(dict(case=c["name"], window=h, f_hz=c["f"], i_true_a=round(tr, 4),
                             err_mean_pct=round(float(np.mean(err)), 4),
                             err_min_pct=round(float(err.min()), 4), err_max_pct=round(float(err.max()), 4)))
    return trim, rows


def lock_scan(select_fs, f_lo=31e3, f_hi=55e3, step=50.0):
    """Sine 22 A flat envelope; error of the ESP32 half-cycle RMS vs frequency (trim at 40 kHz removed)."""
    out = []
    base = make_case("scan", 40e3, [1], [1.0], [0.0], 22.0, "flat")
    h = 10
    trim = true_rms(base, h) / np.mean(est_ESP32(base, h, select_fs=True))
    fs_ = np.arange(f_lo, f_hi + 1, step)
    for f in fs_:
        c = make_case("scan", f, [1], [1.0], [0.0], 22.0, "flat")
        # the true rms of a flat sine is exact; no need for the long grid
        e = est_ESP32(c, h, select_fs=select_fs) * trim
        out.append((float(f), float((e.min() / 22.0 - 1) * 100), float((e.max() / 22.0 - 1) * 100)))
    return out


def step_response():
    """Time for each converter's pre-ADC output to reach 90 / 99 / 99.9 % after a 0 -> 22 A step (40 kHz sine)."""
    n = int(30e-3 / DT)
    t = DT * np.arange(n)
    t_step = 5e-3
    i = np.where(t >= t_step, 22.0 * np.sqrt(2) * np.sin(2 * np.pi * 40e3 * t), 0.0)
    v = i * V_PER_A
    ad = lpf1(np.sqrt(np.maximum(lpf1(v * v, DT, AD_TAU_AVG), 0)), DT, AD_TAU_OUT)
    fw = lpf1(np.abs(v), DT, 0.2e-3)
    res = {}
    for nm, y in (("AD8436_chain", ad), ("FW_rectifier_RC_0.2ms", fw)):
        fin = np.mean(y[int((t_step + 20e-3) / DT):])
        r = {}
        for frac in (0.90, 0.99, 0.999):
            idx = np.nonzero(y[int(t_step / DT):] >= frac * fin)[0]
            r[f"t_{int(frac*1000)/10}pct_ms"] = round(float(idx[0] * DT * 1e3), 3) if len(idx) else None
        res[nm] = r
    res["ESP32_slot_window"] = {"note": "per-625 us slot estimate = 11 samples; latency one slot", "t_ms": 0.625}
    return res


# --------------------------------------------------------------------------------------------
# Cost
# --------------------------------------------------------------------------------------------
SNAP = json.load(open(os.path.join(HERE, "lcsc-snapshot-2026-10-12.json")))


def unit_price(code, qty):
    tiers = SNAP["parts"][code]["tiers"]
    p = tiers[0][1]
    for start, price in tiers:
        if qty >= start:
            p = price
    return p


# chain parts of the as-built design (controller.ato, signals rms_*), per board
AS_BUILT = [
    ("U14", "AD8436BRQZ", "C652840", 1, "RMS converter"),
    ("U15", "MCP3202-CI/SN", "C56997", 1, "external 12-bit ADC (CH0 RMS, CH1 LM4040 ref)"),
    ("C_rms_in,core,avg", "GRM31C5C1H104JA01L", "C97946", 3, "100 nF C0G 1206 (ac-coupling, core, CAVG)"),
    ("C_rms_ignd,vcc2,adc", "CL10A105KB8NNNC", "C15849", 3, "1 uF"),
    ("C_rms_lpf,adc", "GRM1885C1H103JA01D", "C85973", 2, "10 nF C0G"),
    ("C_rms_vcc", "CC0603KRX7R9BB104", "C14663", 1, "100 nF X7R decoupling"),
    ("R_rms_bias", "RC0603FR-0710ML", "C114606", 1, "10 Mohm"),
    ("R_rms_gf", "RT0603BRD0730KL", "C723585", 1, "30 k 0.1 %"),
    ("R_rms_gg", "RT0603BRD0710KL", "C95204", 1, "10 k 0.1 %"),
    ("R_rms_adc", "RC0603FR-071KL", "C22548", 1, "1 k"),
    ("R_adc_dout", "RC0603FR-0733RL", "C108661", 1, "33 ohm"),
    ("R_adc_cs_pu", "RC0603FR-0710KL", "C98220", 1, "10 k"),
    ("D_rms_clamp", "BAT54S-7-F", "C83574", 1, "ADC clamp"),
]


def cost_rows():
    def parts_total(parts, boards):
        tot = 0.0
        for ref, mpn, code, n, role in parts:
            tot += n * unit_price(code, boards * n)
        return tot
    # B: swap U14 for the rectifier; keep U15 chain
    keep = [p for p in AS_BUILT if p[0] in ("U15", "C_rms_ignd,vcc2,adc", "R_adc_dout", "R_adc_cs_pu")]
    B_parts = keep + [
        ("U_rect1,2", "TLV9062IDR", "C398355", 2, "dual op-amp x2: rectifier + summing, then gain/RC buffer + Vref buffer"),
        ("D_rect,clamp", "BAT54S-7-F", "C83574", 2, "rectifier diodes + ADC clamp"),
        ("R_rect_0.1pct", "RT0603BRD0710KL", "C95204", 6, "matched 10 k 0.1 % (rectifier + gain)"),
        ("R_misc", "RC0603FR-0710KL", "C98220", 3, "bias / Vref divider / filter"),
        ("C_ac_core", "GRM31C5C1H104JA01L", "C97946", 1, "ac-coupling 100 nF C0G"),
        ("C_avg_lpf", "GRM1885C1H103JA01D", "C85973", 2, "RC averaging + ADC filter (values to be chosen)"),
        ("C_dec", "CC0603KRX7R9BB104", "C14663", 2, "decoupling"),
        ("R_bias", "RC0603FR-0710ML", "C114606", 1, "10 Mohm"),
        ("R_adc", "RC0603FR-071KL", "C22548", 1, "1 k"),
    ]
    # A1: ARQZ-R7 instead of BRQZ
    A1 = [(r, "AD8436ARQZ-R7", "C495329", n, role) if r == "U14" else (r, m, c, n, role) for r, m, c, n, role in AS_BUILT]
    # D: LTC1968 in place of AD8436, no output gain buffer resistors (assume x1; ADC resolution ok), 5 V from TLV76050
    D = [p for p in AS_BUILT if p[0] not in ("U14", "R_rms_gf", "R_rms_gg", "C_rms_vcc", "C_rms_ignd,vcc2,adc")]
    D += [("U14", "LTC1968IMS8#TRPBF", "C679077", 1, "RMS converter (17 in stock; needs 5 V rail: UI TLV76050 is 30 mA, check)"),
          ("C_dec", "CL10A105KB8NNNC", "C15849", 3, "1 uF cavg/decoupling")]
    opts = [
        ("A0_AD8436BRQZ", "as built (BRQZ)", AS_BUILT),
        ("A1_AD8436ARQZ", "AD8436ARQZ-R7 0.5 % grade", A1),
        ("B_FW_rectifier_TLV9062", "precision FW rectifier + MCP3202", B_parts),
        ("C_ESP32_ADC", "no converter, no MCP3202 (ESP32 ADC1 CT_MON path)", []),
        ("D_LTC1968", "LTC1968IMS8 in place of AD8436", D),
    ]
    rows, totals = [], {}
    for key, desc, parts in opts:
        for ref, mpn, code, n, role in parts:
            st = SNAP["parts"][code]
            rows.append(dict(option=key, ref=ref, mpn=mpn, lcsc=code, qty_per_board=n, role=role,
                             stock=st["stock"], stock_fetched_utc=st["fetched_utc"],
                             unit_usd_qty4_boards=unit_price(code, 4 * n), unit_usd_qty1000_boards=unit_price(code, 1000 * n),
                             ext_usd_qty4_boards=round(n * unit_price(code, 4 * n), 4),
                             ext_usd_qty1000_boards=round(n * unit_price(code, 1000 * n), 4)))
        t4, t1k = parts_total(parts, 4), parts_total(parts, 1000)
        totals[key] = dict(description=desc, per_board_usd_qty4=round(t4, 2), per_board_usd_qty1000=round(t1k, 2),
                           parts_count=sum(p[3] for p in parts))
        rows.append(dict(option=key, ref="TOTAL", mpn=desc, lcsc="", qty_per_board=totals[key]["parts_count"], role="",
                         stock="", stock_fetched_utc="", unit_usd_qty4_boards="", unit_usd_qty1000_boards="",
                         ext_usd_qty4_boards=totals[key]["per_board_usd_qty4"],
                         ext_usd_qty1000_boards=totals[key]["per_board_usd_qty1000"]))
    # other converters considered (price/stock only)
    others = [("C679072", "LTC1967CMS8#TRPBF", "ADI; 4.5-5.5 V; bandwidth NOT verified (datasheet unreachable)"),
              ("C462623", "LTC1966CMS8#TRPBF", "ADI micropower; bandwidth NOT verified, believed far below 55 kHz"),
              ("C679075", "LTC1968CMS8#TRPBF", "ADI C-grade"),
              ("C392907", "AD637ARZ", "ADI 8 MHz, +-3..18 V, SOIC-16"),
              ("C650400", "AD637JRZ", "ADI J grade"),
              ("C95502", "OPA2354AIDGKR", "100 MHz GBW op-amp that would shrink the rectifier dead zone 10x")]
    for code, mpn, role in others:
        st = SNAP["parts"][code]
        rows.append(dict(option="other_candidates", ref="", mpn=mpn, lcsc=code, qty_per_board=1, role=role, stock=st["stock"],
                         stock_fetched_utc=st["fetched_utc"], unit_usd_qty4_boards=unit_price(code, 4),
                         unit_usd_qty1000_boards=unit_price(code, 1000), ext_usd_qty4_boards=unit_price(code, 4),
                         ext_usd_qty1000_boards=unit_price(code, 1000)))
    return rows, totals


# --------------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------------
def main():
    results = {"model_parameters": {
        "AD8436_fc_hz": float(AD_FC), "AD8436_tau_avg_ms": AD_TAU_AVG * 1e3, "AD8436_tau_out_us": AD_TAU_OUT * 1e6,
        "ESP32_ADC_bw_hz_ASSUMED": ADC_BW, "ESP32_noise_lsb_ASSUMED": ADC_NOISE_LSB, "ESP32_inl_cubic_mV_ASSUMED": INL_CUBIC_V * 1e3,
        "FW_rectifier_opamp": "TLV9062 GBW 10 MHz, SR 6.5 V/us (LCSC listing), Schottky Vd 0.30 V ASSUMED",
        "temp_span_K_ASSUMED": TEMP_SPAN_K, "tolerance_stack_pct": TOL}}

    # ---------------- control asserts ----------------
    # 1. exact form factor on a pure sine
    t = np.arange(0, 1.0, 1 / 4e6)
    s = np.sin(2 * np.pi * 1000 * t)
    ff = np.sqrt(np.mean(s ** 2)) / np.mean(np.abs(s))
    assert abs(ff - FORM_FACTOR_SINE) < 1e-6 and f"{ff:.4f}" == "1.1107", ff
    results["control_form_factor"] = {"numeric": float(ff), "pi_over_2sqrt2": float(FORM_FACTOR_SINE), "pass": True}

    # 2. AD8436 datasheet point: 300 mV rms sine at 65 kHz, 1 % additional error (flat envelope, whole pipeline)
    c300_ref = make_case("ctl1k", 1e3, [1], [1.0], [0.0], 0.300 / V_PER_A, "flat")
    c300_65 = make_case("ctl65k", 65e3, [1], [1.0], [0.0], 0.300 / V_PER_A, "flat")
    e_ref = np.mean(est_AD8436(c300_ref, 10, quant=False))
    e_65 = np.mean(est_AD8436(c300_65, 10, quant=False))
    add_err = (e_65 / e_ref - 1.0) * 100.0
    assert abs(add_err - (-1.0)) < 0.1, add_err
    results["control_ad8436_65khz_300mV"] = {
        "additional_error_pct": float(add_err), "datasheet_pct": 1.0, "model_tolerance_pct": 0.1, "pass": True,
        "note": "Single-pole model fitted to the guaranteed 1 % point; it deliberately does not reproduce the typical 1 MHz -3 dB "
                "(model is ~2x pessimistic in bandwidth)."}

    cases = build_cases()
    trim_case = [c for c in cases if c["name"] == "sine_f40k_22A_flat"][0]

    per_option = {}
    for name in OPTIONS:
        trim, rows = eval_option(name, cases, trim_case)
        fine_summary = None
        if name in FINE_OPTIONS:
            ftrim, frows = eval_option(name, cases, trim_case, fine=True)
            fine_summary = dict(trim_factor=float(ftrim), systematic_min_pct=min(r["err_min_pct"] for r in frows),
                                systematic_max_pct=max(r["err_max_pct"] for r in frows), cases=frows)
            print(f"   {name} converter-only (exact window): {fine_summary['systematic_min_pct']:+.2f}..{fine_summary['systematic_max_pct']:+.2f} %")
        errs_lo = min(r["err_min_pct"] for r in rows)
        errs_hi = max(r["err_max_pct"] for r in rows)
        tol_sum = sum(TOL[name.replace("A1_AD8436ARQZ", "A1_AD8436ARQZ")].values()) if name in TOL else 0.0
        per_option[name] = dict(trim_factor=float(trim), systematic_min_pct=errs_lo, systematic_max_pct=errs_hi,
                                tolerance_stack_pct=round(tol_sum, 3), converter_only_exact_window=fine_summary,
                                worst_low_pct=round(errs_lo - tol_sum, 3), worst_high_pct=round(errs_hi + tol_sum, 3),
                                cases=rows)
        print(f"{name}: systematic {errs_lo:+.2f}..{errs_hi:+.2f} %, tolerance +-{tol_sum:.2f} %, "
              f"worst {errs_lo - tol_sum:+.2f}..{errs_hi + tol_sum:+.2f} %")
    results["options"] = per_option

    # verdict against the pass criterion in README (stated before results): worst case within +-3 % of true half-cycle RMS
    crit = 3.0
    for name, o in per_option.items():
        fs = o["converter_only_exact_window"]
        if fs:
            lo, hi = fs["systematic_min_pct"] - o["tolerance_stack_pct"], fs["systematic_max_pct"] + o["tolerance_stack_pct"]
            o["verdict_converter_only"] = dict(worst_low_pct=round(lo, 2), worst_high_pct=round(hi, 2), passes_pm3=bool(lo >= -crit and hi <= crit))
        o["verdict_whole_chain_with_firmware_estimator"] = dict(
            worst_low_pct=o["worst_low_pct"], worst_high_pct=o["worst_high_pct"],
            passes_pm3=bool(o["worst_low_pct"] >= -crit and o["worst_high_pct"] <= crit))

    # Option C lock scan
    scans = {}
    for sel in (False, True):
        sc = lock_scan(sel)
        errs = np.array([[e0, e1] for _, e0, e1 in sc])
        worst = float(np.max(np.abs(errs)))
        bad2 = float(np.mean(np.max(np.abs(errs), axis=1) > 2.0) * 100)
        bad5 = float(np.mean(np.max(np.abs(errs), axis=1) > 5.0) * 100)
        lowest = float(errs.min())
        scans["fs_selected" if sel else "as_built_pattern"] = dict(
            step_hz=50, worst_abs_err_pct=round(worst, 2), pct_of_bins_over_2pct=round(bad2, 1), pct_of_bins_over_5pct=round(bad5, 1),
            most_negative_err_pct=round(lowest, 2),
            worst_freqs_hz=[sc[i][0] for i in np.argsort(-np.max(np.abs(errs), axis=1))[:8]])
        print(f"ESP32 lock scan sel={sel}: worst {worst:.2f} %, >2 %: {bad2:.1f} % bins, >5 %: {bad5:.1f} %, min {lowest:.2f} %")
    results["esp32_frequency_lock_scan_22A_sine"] = scans

    # crest guard exposure with per-slot ESP32 estimates (11 samples/slot)
    nom = [c for c in cases if c["name"].startswith("pan_R1.0")]
    mx = 0.0
    for c in nom:
        _, sm = est_ESP32(c, 10, select_fs=True, return_slots=True)
        mx = max(mx, float(sm.max()))
    ad = max(float(np.max(est_AD8436(c, 10))) for c in nom)
    results["crest_guard_exposure_22A"] = {
        "esp32_largest_625us_slot_estimate_a": round(mx, 2), "guard_a": 33.0,
        "note": "binding compares each slot with 1.5 x ceiling (33 A at 22 A). The AD8436 output already is the 120 Hz envelope crest "
                "(~1.41 x 22 A = 31 A): see COMMISSIONING step 6.2. A raw-sample RMS per slot has extra statistical spread."}

    results["step_response"] = step_response()
    rows, totals = cost_rows()
    results["cost_per_board_usd"] = totals
    with open(os.path.join(HERE, "cost.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)
    with open(os.path.join(HERE, "results.json"), "w") as fh:
        json.dump(results, fh, indent=1, default=float)
    print("wrote results.json and cost.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
