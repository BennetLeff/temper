#!/usr/bin/env python3
"""Source-borne spurs: AD9833 harmonics/images that fold onto the fit frequency.

The excitation passes through the DUT to BOTH channels, so a source spur only
corrupts Z = Zf*A/B through the difference of the channel A and B transfer
ratios between the spur frequency fk and f (ratiometric cancellation):

  dZ/Z = W * s_k * |(Rg+Z(f))/(Rg+Z(fk))| * |Z(fk)/Z(f) - Zf(fk)/Zf(f)| * H(fk)/H(f)

with W the exact fit response at the alias (common.Fit), s_k the spur level
relative to the fundamental after the reconstruction filter, Rg = RF = 100 ohm
(100 ohm range), Zf = 100 ohm || 100 pF (C104), and H the FDA/ADC filter (and,
for the in-progress firmware, the boxcar) common to both channels.

Spur levels: (1) exact digital AD9833 model (12-bit phase truncation, 10-bit
DAC, ideal DAC levels); (2) datasheet typical wideband SFDR (-60 dBc, any spur,
no guaranteed limit for high-order harmonics); (3) an assumed -80 dBc.
Writes dds_spurs.json.
"""
from __future__ import annotations

import json
import pathlib

import numpy as np

import common as c

HERE = pathlib.Path(__file__).resolve().parent
RG = 100.0
RF = 100.0
CF = 100e-12

# DUTs on the 100-ohm range used for stage53 (docs/analog-validation-rev-c.md)
DUTS = {
    "R 15 ohm": lambda f: 15.0 + 0j * f,
    "coil 50 uH + 0.5 ohm": lambda f: 0.5 + 2j * np.pi * f * 50e-6,
    "C 100 nF": lambda f: 1 / (2j * np.pi * f * 100e-9),
    "C 500 nF": lambda f: 1 / (2j * np.pi * f * 500e-9),
    "C 9 uF": lambda f: 1 / (2j * np.pi * f * 9e-6),
}


def zf(f):
    return 1 / (1 / RF + 2j * np.pi * f * CF)


def dut_coefficient(z, f, fk):
    """|dZ/Z| per unit spur (relative to fundamental at the DUT source)."""
    zk, z1 = z(fk), z(f)
    return abs((RG + z1) / (RG + zk)) * abs(zk / z1 - zf(fk) / zf(f))


def ad9833_harmonics(kmax=260):
    """Exact digital model: phase accumulator truncated to 12 bits, sine ROM
    rounded to 10-bit offset binary, zero-order hold in phase. Returns |c_k|/|c_1|
    for k = 0..kmax (frequency k*f before MCLK/ADC aliasing)."""
    j = np.arange(4096)
    table = np.round(511.5 + 511.5 * np.sin(2 * np.pi * j / 4096))
    spec = np.fft.fft(table) / 4096
    k = np.arange(kmax + 1)
    zoh = np.abs(np.sinc(k / 4096))
    mag = np.abs(spec[k % 4096]) * zoh
    return mag / mag[1]


def image_level(f):
    """First DAC image at MCLK - f relative to the fundamental after the
    reconstruction filter and the OPA810 gain-6 stage (70 MHz GBW / 6), at the
    source buffer input. MCLK is a multiple of every fs, so it folds exactly
    onto f; this is only a level check."""
    fi = c.DDS_CLOCK_HZ - f
    zoh = abs(np.sinc(fi / c.DDS_CLOCK_HZ)) / abs(np.sinc(f / c.DDS_CLOCK_HZ))
    rc = abs(c.recon_filter(fi)) / abs(c.recon_filter(f))
    amp = 1 / abs(1 + 1j * fi / (70e6 / 6))
    return zoh * rc * amp


def analyse(hz, mode="undersample", dig=None):
    a = c.acquisition(hz)
    f, fs = a["f_dds_hz"], a["fs_hz"]
    fit = c.Fit(f, fs)
    k = np.arange(2, 201)
    fk = k * f
    al = c.alias(fk, fs)
    inlobe = np.abs(al - f) < 5 * a["bin_hz"]      # same "near" window as alias_map
    rows = []
    n = a["divider"] if mode == "boxcar" else 1
    for kk, fkk, alk in zip(k[inlobe], fk[inlobe], al[inlobe]):
        w = float(fit.response([alk])[0])
        filt = abs(c.recon_filter(fkk) / c.recon_filter(f))
        common_path = abs(c.fda_filter(fkk) / c.fda_filter(f)) * float(c.boxcar_gain(fkk, n) / c.boxcar_gain(f, n))
        coeffs = {name: dut_coefficient(z, f, fkk) for name, z in DUTS.items()}
        lv = {"digital_exact": float(dig[kk]) * filt,
              "sfdr_typ_-60dBc": 10 ** (c.AD9833["sfdr_wideband_typ_dbc"] / 20) * filt,
              "assumed_-80dBc": 1e-4 * filt}
        err = {lvl: {name: w * common_path * s * cf for name, cf in coeffs.items()}
               for lvl, s in lv.items()}
        rows.append({"k": int(kk), "spur_hz": float(fkk), "alias_hz": float(alk),
                     "offset_hz": float(alk - f), "fit_response": w,
                     "recon_rel": float(filt), "common_path_rel": float(common_path),
                     "dut_coefficient": coeffs, "spur_level_at_dut": lv, "z_error": err})
    worst = {}
    for lvl in ("digital_exact", "sfdr_typ_-60dBc", "assumed_-80dBc"):
        worst[lvl] = {name: float(np.sqrt(sum(r["z_error"][lvl][name] ** 2 for r in rows)) if rows else 0.0)
                      for name in DUTS}
        worst[lvl + "_linear_sum"] = {name: float(sum(r["z_error"][lvl][name] for r in rows)) for name in DUTS}
    return {"acquisition": a, "mode": mode, "image_rel_level": float(image_level(f)),
            "colliding": rows[:12], "n_colliding_k_le_200": len(rows), "z_error_rss": worst}


def main():
    dig = ad9833_harmonics()
    out = {"digital_model_harmonics_dbc": {str(k): float(c.db(dig[k])) for k in
                                           (2, 3, 5, 9, 11, 24, 26, 49, 51, 99, 101)},
           "frequencies": []}
    freqs = c.TEMPER_GRID + [5000.0, 10000.0, 100000.0] + [x + 500.0 for x in c.TEMPER_GRID]
    for hz in freqs:
        for mode in ("undersample", "boxcar"):
            out["frequencies"].append(analyse(hz, mode, dig))
    (HERE / "dds_spurs.json").write_text(json.dumps(out, indent=1))
    print("digital-model harmonic levels (dBc):", {k: round(v, 1) for k, v in out["digital_model_harmonics_dbc"].items()})
    for r in out["frequencies"]:
        a = r["acquisition"]
        lo = [x["k"] for x in r["colliding"]][:4]
        e = r["z_error_rss"]
        def pct(d):
            return {n.split()[0] + n.split()[1]: f"{100*v:.4f}%" for n, v in d.items()}
        print(f"{a['requested_hz']:>7.0f} Hz {r['mode']:<10} N={a['divider']:>2} first k {lo} "
              f"image {c.db(r['image_rel_level']):.0f} dBc\n   exact-digital {pct(e['digital_exact'])}\n"
              f"   -80dBc {pct(e['assumed_-80dBc'])}\n   -60dBc {pct(e['sfdr_typ_-60dBc'])}")


if __name__ == "__main__":
    main()
