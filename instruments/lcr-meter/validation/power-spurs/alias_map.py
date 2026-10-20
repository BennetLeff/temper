#!/usr/bin/env python3
"""Task 2: alias map of every identified spur source against the host fit.

For each measurement frequency the host can request (100 Hz - 100 kHz, DDS
quantized, divider from host divider_for, 16384-sample record), fold every spur
(over its frequency tolerance band) into [0, fs/2] and evaluate the exact
least-squares DC+cos+sin fit response at the alias.

Geometry only: amplitudes are applied in ripple_chain.py and dds_spurs.py.
Writes alias_map.json. Run: python3 alias_map.py
Bring-up: python3 alias_map.py --fsw <measured Hz> [f1,f2,...]
"""
from __future__ import annotations

import json
import math
import pathlib

import numpy as np

import common as c

HERE = pathlib.Path(__file__).resolve().parent
NEAR_BINS = 5          # "near the main lobe": |alias - f| < 5 fit bins
SW_HARMONICS = 40      # TPS65131 harmonics considered (to 60 MHz)
COMB_HARMONICS = 300   # 1 kHz combs: harmonics to 300 kHz
DDS_HARMONICS = 200


def fold_band(lo: float, hi: float, fs: float):
    """Folded alias set of the physical band [lo, hi] as intervals in [0, fs/2]."""
    if hi - lo >= fs / 2:
        return [(0.0, fs / 2)]
    a = lo % fs
    raw = [(a, a + (hi - lo))] if a + (hi - lo) < fs else [(a, fs), (0.0, a + (hi - lo) - fs)]
    out = []
    for p, q in raw:
        if p < fs / 2:
            out.append((p, min(q, fs / 2)))
        if q > fs / 2:
            out.append((fs - q, fs - max(p, fs / 2)))
    return out


def band_distance(intervals, f: float) -> float:
    d = math.inf
    for p, q in intervals:
        d = 0.0 if p <= f <= q else min(d, abs(p - f), abs(q - f))
    return d


def band_hits(fit: c.Fit, bands, f: float, bin_hz: float):
    """bands: list of (label, lo, hi). Returns hits within NEAR_BINS with the
    worst exact fit response over the reachable part near f."""
    hits = []
    for label, lo, hi in bands:
        iv = fold_band(lo, hi, fit.fs)
        d = band_distance(iv, f)
        if d < NEAR_BINS * bin_hz:
            win_lo, win_hi = f - NEAR_BINS * bin_hz, f + NEAR_BINS * bin_hz
            worst, at = 0.0, None
            for p, q in iv:
                lo2, hi2 = max(p, win_lo), min(q, win_hi)
                if lo2 <= hi2:
                    r, x = fit.worst_in_band(lo2, hi2, points=max(3, int((hi2 - lo2) / bin_hz * 20)))
                    if r > worst:
                        worst, at = r, x
            hits.append({"source": label, "distance_bins": d / bin_hz,
                         "worst_fit_response": worst,
                         "worst_alias_hz": at, "reach": "main lobe" if d < bin_hz else "near"})
    return hits


def spur_bands(f_dds: float, fs: float):
    """Every spur family as (label, physical lo, physical hi)."""
    sw = c.TPS65131
    bands = []
    for m in range(1, SW_HARMONICS + 1):
        bands.append((f"TPS65131 fsw x{m}", m * sw["fsw_min_hz"], m * sw["fsw_max_hz"]))
    e = c.USB_SOF_TOL + c.XTAL_TOL       # host frame clock relative to board time
    for h in range(1, COMB_HARMONICS + 1):
        g = h * c.USB_SOF_HZ
        bands.append((f"USB SOF x{h}", g * (1 - e), g * (1 + e)))
        # Board-clock 1 kHz comb: hypothetical (pico-sdk 2.2.0 stdio_usb uses its
        # periodic 1 ms timer only when USBCTRL_IRQ has no shared handler; TinyUSB
        # dcd_rp2040 installs one, so this build is event-driven). Kept so any
        # future 1 ms periodic firmware activity is covered.
        bands.append((f"board-clock 1 kHz comb x{h}", g, g))
    for k in range(2, DDS_HARMONICS + 1):
        bands.append((f"DDS harmonic {k}", k * f_dds, k * f_dds))
    # Crystal-derived clocks: every one is an integer multiple of fs = 1 MHz/N.
    for label, fx in [("XOSC 12 MHz", 12e6), ("DDS MCLK 24 MHz", 24e6),
                      ("USB PLL 48 MHz", 48e6), ("sys 120 MHz", 120e6),
                      ("PIO SCLK 30 MHz/N", 30e6 / (c.CONVERSION_RATE_HZ / fs)),
                      ("CONVST fs", fs)]:
        bands.append((label, fx, fx))
    return bands


def coherent_clock_check():
    """Every crystal-derived clock is an integer multiple of every fs, so it
    aliases to exactly DC, which the fit's DC term absorbs (response 0)."""
    rows = []
    for n in range(1, c.MAX_DIVIDER + 1):
        fs = c.CONVERSION_RATE_HZ / n
        for label, fx in [("12 MHz", 12e6), ("24 MHz", 24e6), ("48 MHz", 48e6),
                          ("120 MHz", 120e6), ("SCLK", 30e6 / n)]:
            ratio = fx / fs
            rows.append(abs(ratio - round(ratio)) < 1e-9)
    return all(rows)


def analyse(hz: float):
    a = c.acquisition(hz)
    fit = c.Fit(a["f_dds_hz"], a["fs_hz"])
    hits = band_hits(fit, spur_bands(a["f_dds_hz"], a["fs_hz"]), a["f_dds_hz"], a["bin_hz"])
    hits = [h for h in hits if not h["source"].startswith(("XOSC", "DDS MCLK", "USB PLL", "sys ", "PIO", "CONVST"))]
    a["hits"] = hits
    return a


def dds_collision_order(f_dds: float, fs: float, record_s: float, kmax=DDS_HARMONICS):
    """Lowest harmonic k whose alias lies within 1 fit bin of f (main lobe)."""
    k = np.arange(2, kmax + 1)
    off = np.abs(c.alias(k * f_dds, fs) - f_dds)
    inside = k[off < 1.0 / record_s]
    return int(inside[0]) if inside.size else None


def sweep():
    """1 Hz sweep of the whole host range: which frequencies put a low-order
    DDS harmonic or a 1 kHz comb line in the fit main lobe."""
    hz = np.arange(100, 100001, 1, dtype=float)
    words = np.round(hz * 268_435_456.0 / c.DDS_CLOCK_HZ)
    f = words * c.DDS_CLOCK_HZ / 268_435_456.0
    n = np.clip(np.floor(c.CONVERSION_RATE_HZ / np.maximum(hz * 10, 50_000)), 1, 20)
    fs = c.CONVERSION_RATE_HZ / n
    T = c.DEFAULT_COUNT / fs
    lowest = np.full(hz.size, 10**9)
    for k in range(DDS_HARMONICS, 1, -1):
        off = np.abs(c.alias(k * f, fs) - f)
        lowest = np.where(off < 1.0 / T, k, lowest)
    comb = np.full(hz.size, 10**9)   # board-coherent 1 kHz comb, lowest order
    for h in range(COMB_HARMONICS, 0, -1):
        off = np.abs(c.alias(h * 1000.0, fs) - f)
        comb = np.where(off < 1.0 / T, h, comb)
    res = {"frequencies": int(hz.size)}
    for kk in (10, 20, 50):
        res[f"dds_harmonic_le_{kk}_in_main_lobe"] = int(np.sum(lowest <= kk))
    res["comb_1khz_le_300_in_main_lobe"] = int(np.sum(comb <= COMB_HARMONICS))
    res["comb_direct_in_main_lobe"] = int(np.sum((comb <= COMB_HARMONICS) & (comb * 1000.0 < fs / 2)))
    worst = []
    for k in (3, 5, 7, 9, 11):
        sel = hz[lowest == k]
        worst.append({"k": k, "count": int(sel.size), "examples_hz": [int(x) for x in sel[:8]]})
    res["lowest_order_examples"] = worst
    return res


def main():
    out = {"assumptions": {
        "record": c.DEFAULT_COUNT, "near_bins": NEAR_BINS,
        "fsw_band_hz": [c.TPS65131["fsw_min_hz"], c.TPS65131["fsw_max_hz"]],
        "sof_relative_tolerance": c.USB_SOF_TOL + c.XTAL_TOL,
        "harmonics": {"switcher": SW_HARMONICS, "comb": COMB_HARMONICS, "dds": DDS_HARMONICS}},
        "coherent_clocks_alias_to_dc": coherent_clock_check()}
    freqs = c.TEMPER_GRID + [100.0, 5000.0, 10000.0, 100000.0] + [x + 500.0 for x in c.TEMPER_GRID]
    out["frequencies"] = []
    for hz in freqs:
        a = analyse(hz)
        a["dds_collision_order"] = dds_collision_order(a["f_dds_hz"], a["fs_hz"], a["record_s"])
        out["frequencies"].append(a)
    out["sweep_1hz"] = sweep()
    (HERE / "alias_map.json").write_text(json.dumps(out, indent=1))
    # compact console table
    print(f"coherent clocks alias to DC for every divider: {out['coherent_clocks_alias_to_dc']}")
    for a in out["frequencies"]:
        sw = [h for h in a["hits"] if h["source"].startswith("TPS")]
        sof = [h for h in a["hits"] if h["source"].startswith("USB") and h["reach"] == "main lobe"]
        task = [h for h in a["hits"] if h["source"].startswith("board") and h["reach"] == "main lobe"]
        dds = [h for h in a["hits"] if h["source"].startswith("DDS") and h["reach"] == "main lobe"]
        print(f"{a['requested_hz']:>8.0f} Hz N={a['divider']:>2} fs={a['fs_hz']/1e3:7.2f}k bin={a['bin_hz']:6.2f}Hz "
              f"| SW harmonics reachable(<{NEAR_BINS} bins): {[h['source'].split('x')[-1] for h in sw]} "
              f"| SOF main-lobe: {[(h['source'].split('x')[-1], round(h['worst_fit_response'],3)) for h in sof]} "
              f"| board 1 kHz comb (hypothetical): {[(h['source'].split('x')[-1], round(h['worst_fit_response'],3)) for h in task]} "
              f"| DDS k in lobe: {[(h['source'].split()[-1], round(h['worst_fit_response'],4)) for h in dds]}")
    print(json.dumps(out["sweep_1hz"], indent=1))


def check_measured_fsw(fsw_hz: float, freqs, threshold=0.01):
    """Bring-up helper: with the switching frequency measured on SW_P, list the
    switcher harmonics whose alias gives a fit response above `threshold`."""
    for hz in freqs:
        a = c.acquisition(hz)
        fit = c.Fit(a["f_dds_hz"], a["fs_hz"])
        m = np.arange(1, SW_HARMONICS + 1)
        r = fit.response(c.alias(m * fsw_hz, a["fs_hz"]))
        bad = [(int(mm), round(float(rr), 4)) for mm, rr in zip(m, r) if rr > threshold]
        print(f"{hz:>9.1f} Hz (N={a['divider']}): harmonics with fit response > {threshold}: {bad or 'none'}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2 and sys.argv[1] == "--fsw":
        grid = [float(x) for x in sys.argv[3].split(",")] if len(sys.argv) > 3 else c.TEMPER_GRID
        check_measured_fsw(float(sys.argv[2]), grid)
    else:
        main()
