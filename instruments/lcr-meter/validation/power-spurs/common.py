"""Shared constants and exact acquisition/fit models for the power-spur study.

Every constant cites the file (or datasheet page) it was read from. Numbers read
off datasheet curves are marked DIGITIZED and are typical (25 C) curves, not
guaranteed limits.
"""
from __future__ import annotations

import math
import numpy as np

# ---------------------------------------------------------------- acquisition
# host/src/lib.rs (HEAD and the in-progress boxcar version use the same rule)
DDS_CLOCK_HZ = 24_000_000.0
CONVERSION_RATE_HZ = 1_000_000.0       # SAMPLE_BASE_HZ at HEAD
DEFAULT_COUNT = 16_384                 # samples (output samples) per record
MAX_DIVIDER = 20
F_MIN, F_MAX = 100.0, 100_000.0
TEMPER_GRID = [1000.0, 35000.0, 40000.0, 50000.0, 60000.0]   # host/README.md


def divider_for(hz: float) -> int:
    """Exact copy of host/src/lib.rs divider_for / decimation_for."""
    n = math.floor(CONVERSION_RATE_HZ / max(hz * 10.0, 50_000.0))
    return int(min(max(n, 1), MAX_DIVIDER))


def frequency_word(hz: float) -> int:
    """host/src/lib.rs frequency_word: round(hz * 2^28 / 24 MHz)."""
    return int(round(hz * 268_435_456.0 / DDS_CLOCK_HZ))


def frequency_hz(word: int) -> float:
    return word * DDS_CLOCK_HZ / 268_435_456.0


def acquisition(hz: float) -> dict:
    w = frequency_word(hz)
    n = divider_for(hz)
    fs = CONVERSION_RATE_HZ / n
    return {"requested_hz": hz, "word": w, "f_dds_hz": frequency_hz(w), "divider": n,
            "fs_hz": fs, "record_s": DEFAULT_COUNT / fs, "bin_hz": fs / DEFAULT_COUNT}


def alias(freq_hz, fs_hz):
    """Fold a physical frequency (array ok) into [0, fs/2]."""
    a = np.mod(np.asarray(freq_hz, dtype=float), fs_hz)
    return np.where(a > fs_hz / 2, fs_hz - a, a)


def boxcar_gain(freq_hz, n: int):
    """|sum of n consecutive 1 MSPS conversions| / n for a tone (in-progress
    firmware/src/boxcar.c). n = 1 means no filtering (HEAD undersampling)."""
    x = np.asarray(freq_hz, dtype=float) / CONVERSION_RATE_HZ
    num = np.sin(np.pi * x * n)
    den = n * np.sin(np.pi * x)
    with np.errstate(invalid="ignore", divide="ignore"):
        g = np.where(np.abs(den) < 1e-15, 1.0, np.abs(num / np.where(den == 0, 1, den)))
    return g


# ------------------------------------------------------------ the host's fit
class Fit:
    """Exact least-squares DC + cos + sin estimator of host/src/lib.rs `fit`.

    response(a) returns, for a unit-amplitude real tone at aliased frequency a,
    the largest (over interferer phase) magnitude of the fitted phasor, i.e. the
    error phasor relative to a unit signal at the fit frequency. The signal
    itself gives exactly 1.
    """

    def __init__(self, f_hz: float, fs_hz: float, count: int = DEFAULT_COUNT, window: str | None = None):
        """window=None is the host's plain least squares; window='hann' is a
        Hann-weighted least squares (a proposed host change, not current code)."""
        self.f, self.fs, self.count = f_hz, fs_hz, count
        n = np.arange(count, dtype=float)
        self.n = n
        w = 2 * np.pi * f_hz / fs_hz
        basis = np.vstack([np.ones(count), np.cos(w * n), np.sin(w * n)])
        wt = np.ones(count) if window is None else 0.5 - 0.5 * np.cos(2 * np.pi * (n + 0.5) / count)
        gram = (basis * wt) @ basis.T
        self.proj = np.linalg.solve(gram, basis * wt)[1:3]   # rows: c, s estimators

    def response(self, freqs_hz, chunk: int = 256):
        a = np.atleast_1d(np.asarray(freqs_hz, dtype=float))
        out = np.empty(a.size)
        for i in range(0, a.size, chunk):
            ang = 2 * np.pi * np.outer(self.n, a[i:i + chunk]) / self.fs
            u = self.proj @ np.cos(ang)          # 2 x k
            v = self.proj @ np.sin(ang)
            # largest singular value of [[u0,-v0],[u1,-v1]] per column
            p = u[0] ** 2 + u[1] ** 2 + v[0] ** 2 + v[1] ** 2
            q = u[0] * v[1] - u[1] * v[0]
            disc = np.sqrt(np.maximum(p * p / 4 - q * q, 0))
            out[i:i + chunk] = np.sqrt(p / 2 + disc)
        return out

    def worst_in_band(self, lo_hz: float, hi_hz: float, points: int = 400):
        """Worst response for an interferer whose alias may lie anywhere in
        [lo, hi] (folded frequencies). Dense sampling plus the exact f if
        enclosed (the main-lobe peak)."""
        lo, hi = sorted((lo_hz, hi_hz))
        grid = np.linspace(lo, hi, points)
        if lo <= self.f <= hi:
            grid = np.append(grid, self.f)
        r = self.response(grid)
        k = int(np.argmax(r))
        return float(r[k]), float(grid[k])


def rect_envelope(offset_hz, record_s):
    """Rectangular-window sidelobe envelope 1/(pi*|df|*T), capped at 1."""
    d = np.abs(np.asarray(offset_hz, dtype=float)) * record_s
    return np.minimum(1.0, 1.0 / (np.pi * np.maximum(d, 1e-12)))


def db(x):
    return 20 * np.log10(np.maximum(np.asarray(x, dtype=float), 1e-30))


def interp_loglog_db(curve, f_hz):
    """Interpolate a DIGITIZED (freq, dB) curve linearly in log-frequency;
    clamp outside the digitized range (flat extrapolation)."""
    fx = np.log10([p[0] for p in curve])
    dy = [p[1] for p in curve]
    return np.interp(np.log10(np.asarray(f_hz, dtype=float)), fx, dy)


# --------------------------------------------------------- datasheet numbers
TPS65131 = {  # sources/ti/TPS65131.txt, SLVS493E section 6.5/6.6
    "fsw_min_hz": 1.25e6, "fsw_typ_hz": 1.38e6, "fsw_max_hz": 1.50e6,
    "vref": (1.200, 1.213, 1.225), "vfbp": (1.189, 1.213, 1.237),
    "vfbn": (-0.024, 0.0, 0.024), "ilim_a": (1.80, 1.95, 2.20),
    "vin_range": (2.7, 5.5), "vpos_max_rec": 15.0, "vneg_min_rec": -15.0,
    "vpos_abs_max": 17.0, "vneg_abs_min": -17.0, "vin_abs_max": 6.0,
    "outn_to_inn_abs_max": 24.0, "inp_abs_max": 17.0,
    "dmax": 0.875, "dmin": 0.125, "l_range_h": (3.3e-6, 6.8e-6),
    "cin_min_f": 4.7e-6, "cp_rec_f": 10e-9, "cn_rec_f": 4.7e-9, "cref_rec_f": 220e-9,
    "r_lower_max_ohm": 200e3,          # R2/R4 < 200 kOhm (section 8.2.2.1)
    "cff_rule_v": (6.8, 7.5),          # Eq. 11/12: C9 = 6.8 V / R1, C10 = 7.5 V / R3
    "vin_rc_min": (100.0, 100e-9),     # section 8.2.3.1
}
TPS7A49 = {  # sources/ti/TPS7A49.txt SBVS121E
    "vref": (1.176, 1.188, 1.212), "vfb_typ": 1.185, "acc_overall": 0.025,
    "cout_min_f": 2.2e-6, "esr_max_ohm": 0.200, "cnr_max_f": 10e-9, "cff_max_f": 10e-9,
    "r2_max_ohm": 237e3, "ifb_min_a": 5e-6, "vdo_150ma_max_v": 0.600,
    "headroom_curve_v": 1.0, "ilim_min_a": 0.220, "cap_max_dist_mm": 10.0,
}
TPS7A30 = {  # sources/ti/TPS7A30.txt SBVS125D
    "vref": (-1.202, -1.179, -1.166), "vfb_typ": -1.176, "acc_overall": 0.025,
    "cout_min_f": 2.2e-6, "cnr_max_f": 10e-9, "cff_max_f": 10e-9,
    "r2_max_ohm": 237e3, "ifb_min_a": 5e-6, "vdo_200ma_max_v": 0.600,
    "ilim_min_a": 0.220, "cap_max_dist_mm": 10.0,
}
# DIGITIZED typical PSRR curves (dB). LDOs: Figure 14/18 with COUT = 10 uF,
# CNR = CFF = 10 nF (TPS7A49: VOUT 5 V, VIN 6.2 V, 150 mA; TPS7A30: VOUT -5 V,
# VIN -6.2 V, 200 mA), PDF page 9 / page 10.
PSRR_TPS7A49 = [(10, 68), (100, 70), (1e3, 71), (1e4, 66), (3e4, 60), (5e4, 56),
                (1e5, 53), (2e5, 60), (2.5e5, 62), (3e5, 57), (5e5, 47), (1e6, 37),
                (2e6, 29), (3e6, 22), (5e6, 15), (1e7, 4)]
PSRR_TPS7A30 = [(10, 70), (100, 70), (1e3, 71), (1e4, 66), (3e4, 61), (5e4, 59),
                (1e5, 57), (2e5, 59), (3e5, 61), (5e5, 50), (1e6, 38), (2e6, 31),
                (3e6, 27), (5e6, 24), (1e7, 19)]
# OPA2810 Figure 55 (VS = 24 V, simulated), PDF page 23; OPA810 Figure 6-52
# (VS = 24 V, simulated), PDF page 20 -- the two curves are indistinguishable.
PSRR_OPA2810 = [(100, 110), (1e3, 105), (1e4, 87), (1e5, 67), (1e6, 47), (1e7, 27),
                (1e8, 7)]
# THS4551 Figure 7-42 (5 V, +PSRR i.e. VS+ to differential output), PDF p.19.
PSRR_THS4551_POS = [(1e3, 110), (1e5, 110), (3e5, 107), (1e6, 100), (3e6, 91),
                    (1e7, 82)]
ADS9224R_PSRR_DB = 70.0   # AVDD, 100 mVpp ripple < 100 kHz, ADS9224R.txt line ~496

AD9833 = {  # sources/new/AD9833.txt, Rev G spec table (MCLK 25 MHz)
    "thd_typ_dbc": -66.0, "thd_max_dbc": -56.0,        # fOUT = MCLK/4096
    "sfdr_wideband_typ_dbc": -60.0,                    # fOUT = MCLK/50
    "sfdr_narrowband_typ_dbc": -78.0,                  # +-200 kHz
    "snr_min_db": 55.0, "r_out_ohm": 200.0, "dac_bits": 10, "phase_bits": 12,
    "vout_max_v": 0.65,
}
USB_SOF_HZ = 1000.0
USB_SOF_TOL = 500e-6        # USB 2.0 full-speed frame period 1.000 ms +-0.0005 ms
XTAL_TOL = 60e-6            # ABM8-272-T3: +-30 ppm tolerance + +-30 ppm stability
STDIO_USB_TASK_HZ = 1000.0  # pico-sdk 2.2.0 PICO_STDIO_USB_TASK_INTERVAL_US; NOT active in this
                            # build (event-driven: TinyUSB installs a shared USBCTRL handler)


# --------------------------------------------------------------- signal path
FULL_SCALE_V = 4.096
LSB_V = FULL_SCALE_V / 32768
SIGNAL_A_MATCHED_V = 0.699     # docs/analog-validation-rev-c.md, 100 kHz matched
SIGNAL_15R_A_V = 0.18          # brief: voltage channel, 15 ohm DUT, 100 ohm range


def recon_filter(f_hz):
    """AD9833 200 ohm internal load -> R30 330 / C34 1 nF -> R31 330 / C35 1 nF
    (cad/design.json nets DDS_OUT, LP1, LP2). Returns complex V(LP2)/V_open."""
    s = 2j * np.pi * np.asarray(f_hz, dtype=float)
    r0, r1, r2, c1, c2 = 200.0, 330.0, 330.0, 1e-9, 1e-9
    z2 = r2 + 1 / (s * c2)
    z1p = 1 / (s * c1 + 1 / z2)
    v1 = z1p / (r0 + r1 + z1p)
    return v1 * (1 / (s * c2)) / z2


def fda_filter(f_hz):
    """THS4551 1k || 100 pF feedback pole and the 2 x 4.32 ohm / (3.3 nF +
    330 pF/2) differential output filter (cad/design.json A_/B_ nets).
    Identical on both channels: it cancels for source-borne interference."""
    s = 2j * np.pi * np.asarray(f_hz, dtype=float)
    p1 = 1 / (1 + s * 1e3 * 100e-12)
    p2 = 1 / (1 + s * 8.64 * (3.3e-9 + 165e-12))
    return p1 * p2
