#!/usr/bin/env python3
"""Analytic noise budget: per-conversion noise on each ADC channel (all analog bandwidth folds,
because the capture undersamples with no decimation filter), channel correlation, full-scale use,
and the resulting 1-sigma noise of the fitted impedance, broken down by source group.

Fitted-phasor noise: for a stationary noise with folded one-sided density S1(f0) at the test
frequency, the DC+cos+sin fit over T = N/fs gives E|dP|^2 = 2 S1(f0) / T.  Per alias the A and B
contributions come from the same random amplitude, so the impedance error per source is
    dZ/Z = dA/A - dB/B,  |g| = |hA/A0 - hB/B0|  (conjugates for mirrored aliases),
summed over every alias m*fs +/- f0 up to 200 MHz.  Channel-common terms (sample-clock jitter,
shared reference) cancel in A/B.  Boxcar mode weights each alias by the decimator response.
sigma(R) = sigma(X) = |Z| * sqrt(E|dZ/Z|^2 / 2).

    noise_budget.py            -> results/noise_budget.json, results/noise_budget.csv
"""
import csv
import json
import math
from dataclasses import replace

import numpy as np

import vi_model as vm
from mc import FREQS, F0_NOPAN, F0_PAN

GROUPS = {
    "DDS (AD9833)": ["dds"],
    "OPA810 gain stage + recon/coupling R": ["en_x5", "nr_R30", "nr_R31", "nr_R32", "nr_R33", "nr_R34"],
    "source buffer U6A": ["en_x6a"],
    "HIGH/LOW followers": ["en_x6b", "en_x7b"],
    "TIA U7A + RG/RF/R_iso": ["en_x7a", "in_x7a_m", "nr_RG", "nr_RF", "nr_Risolo"],
    "FDA A (THS4551 + R)": ["en_xa", "in_xa_p", "in_xa_m", "nr_Rai1", "nr_Rai2", "nr_Raf1", "nr_Raf2",
                            "nr_Raint1", "nr_Raint2", "nr_Raiso1", "nr_Raiso2"],
    "FDA B (THS4551 + R)": ["en_xb", "in_xb_p", "in_xb_m", "nr_Rbi1", "nr_Rbi2", "nr_Rbf1", "nr_Rbf2",
                            "nr_Rbint1", "nr_Rbint2", "nr_Rbiso1", "nr_Rbiso2"],
    "DUT thermal": ["dut"],
}


def boxcar_resp(f, d):
    if d == 1:
        return np.ones_like(f)
    x = np.pi * f / vm.SAMPLE_BASE_HZ
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.sin(x * d) / (d * np.sin(x))
    return np.where(np.abs(np.sin(x)) < 1e-12, 1.0, r)


def phasor_noise(config, dut, hz, o=vm.NoiseOpts(), acq=vm.Acq(), count=vm.DEFAULT_COUNT):
    o = replace(o, src_scale=acq.amp_scale)
    tr = vm.transfer(config)
    word = vm.frequency_word(hz)
    f0 = vm.frequency_hz(word)
    div = vm.divider_for(hz)
    fs = vm.SAMPLE_BASE_HZ / div
    D = div if acq.boxcar else 1
    T = count / fs
    z0 = dut.z(f0)
    HA0, HB0 = tr.H([f0], [z0], names=["dds"])
    amp = o.dds_amp_v * acq.amp_scale
    A0, B0 = amp * HA0[0, 0], amp * HB0[0, 0]
    bx0 = boxcar_resp(np.array([f0]), D)[0]
    M = int(vm.FMAX / fs) + 1
    var_src = np.zeros(len(tr.names))
    for mirror in (False, True):
        m = np.arange(1, M + 1) if mirror else np.arange(0, M + 1)
        f = m * fs - f0 if mirror else m * fs + f0
        f = f[(f > 0) & (f < vm.FMAX)]
        zf = dut.z(f)
        HA, HB = tr.H(f, zf)
        S = vm.densities(tr, f, zf, o)
        if mirror:
            g = np.conj(HA) / A0 - np.conj(HB) / B0
        else:
            g = HA / A0 - HB / B0
        w = (boxcar_resp(f, D) / bx0) ** 2
        var_src += (2 / T) * (S * np.abs(g) ** 2 * w).sum(1)
    sig_adc2 = (o.adc_lsb_rms * vm.LSB_V) ** 2 + vm.LSB_V ** 2 / 12
    n_conv = count * D
    var_adc = 4 * sig_adc2 / n_conv * (1 / abs(A0 * bx0) ** 2 + 1 / abs(B0 * bx0) ** 2)
    w0 = 2 * math.pi * f0
    var_jit = 2 * 4 * ((w0 * o.aperture_jitter_s) ** 2 + (o.ref_indep_ppm * 1e-6) ** 2) / 2 / n_conv
    groups = {g: float(sum(var_src[tr.names.index(n)] for n in ns if n in tr.names)) for g, ns in GROUPS.items()}
    groups["ADC thermal + quantization"] = float(var_adc)
    groups["aperture jitter + per-channel reference"] = float(var_jit)
    tot = sum(groups.values())
    sig_z = abs(z0) * math.sqrt(tot / 2)
    sa, sb, rho = vm.per_sample_noise(tr, dut, o)
    return dict(config=config, dut=dut.name, hz=hz, f_actual=f0, divider=div, boxcar=bool(acq.boxcar),
                amp_scale=acq.amp_scale, z_true=[float(np.real(z0)), float(np.imag(z0))],
                a_peak_v=abs(A0), b_peak_v=abs(B0), a_fs_fraction=abs(A0) / 4.096, b_fs_fraction=abs(B0) / 4.096,
                analog_sigma_a_uv=sa * 1e6, analog_sigma_b_uv=sb * 1e6, analog_rho=rho,
                adc_sigma_uv=math.sqrt(sig_adc2) * 1e6,
                sigma_rel_z=math.sqrt(tot), sigma_r_ohm=sig_z, sigma_x_ohm=sig_z,
                var_groups={k: v / tot for k, v in groups.items()})


TARGET_POINTS = [("coil_nopan", f) for f in (35e3, 40e3, 50e3, 60e3)] + \
    [("coil_pan", f) for f in (35e3, 40e3, 50e3, 60e3)] + [("coil_pan_lowR", 40e3)] + \
    [("cap100n", f) for f in (35e3, 50e3, 60e3)] + [("bank500n", f) for f in (35e3, 50e3, 60e3)] + \
    [("bus9u", 1e3), ("tank_nopan", float(F0_NOPAN)), ("tank_pan", float(F0_PAN))]


WHATIF = [  # name, transfer config, acquisition
    ("base", "base", vm.Acq()),
    ("a_r33_buf634", "r33", vm.Acq()),
    ("a_r33_20mA", "r33", vm.Acq(amp_scale=0.367)),
    ("b1_fda_gain2", "gain2", vm.Acq()),
    ("b2_source_x2", "base", vm.Acq(amp_scale=2.0)),
    ("b3_chA_gain4", "again4", vm.Acq()),
    ("c_boxcar", "base", vm.Acq(boxcar=True)),
    ("b1+c", "gain2", vm.Acq(boxcar=True)),
    ("d_riso22", "riso22", vm.Acq()),
    ("d_base_c200", "base_c200", vm.Acq()),
    ("d_riso22_c200", "riso22_c200", vm.Acq()),
]


def sigma_in_units(q, unit, r, dut, hz):
    z = complex(*r["z_true"])
    sx = r["sigma_x_ohm"]
    if q == "L":
        return sx / abs(z.imag)
    if q == "R":
        return sx if unit == "ohm" else sx / z.real
    if q in ("C", "tand"):
        return sx / abs(z.imag)
    if q == "Q":
        return sx / z.real
    if q == "f0":
        d = vm.DUTS[dut]
        dxdf = (d.z(hz * 1.0001).imag - d.z(hz * 0.9999).imag) / (hz * 0.0002)
        return sx / dxdf / hz
    raise KeyError(q)


def whatif_analytic():
    from summarize import TARGETS
    rows = []
    for t in TARGETS:
        tid, dn, freqs, q, tol, unit, _ = t
        row = dict(target=tid, tolerance=tol)
        for name, cfg, acq in WHATIF:
            worst = 0.0
            for hz in freqs:
                r = phasor_noise(cfg, vm.DUTS[dn], hz, acq=acq)
                worst = max(worst, sigma_in_units(q, unit, r, dn, hz))
            row[name] = worst
        rows.append(row)
    with open(vm.HERE / "results/whatif_analytic.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow({k: (f"{v:.3g}" if isinstance(v, float) else v) for k, v in r.items()})
    # signal levels per configuration at representative points
    lv = []
    for name, cfg, acq in WHATIF:
        for dn, hz in (("coil_nopan", 40e3), ("coil_pan", 40e3), ("bank500n", 50e3), ("tank_pan", float(F0_PAN)),
                       ("short", 40e3), ("std100", 40e3)):
            r = phasor_noise(cfg, vm.DUTS[dn], hz, acq=acq)
            tr = vm.transfer(cfg)
            p = tr.meta["params"]
            rg = p["rg"] + 0.0
            i_short = 0.3 * acq.amp_scale * 6 / rg  # nominal source amplitude / RG
            lv.append(dict(whatif=name, dut=dn, hz=hz, a_fs=r["a_fs_fraction"], b_fs=r["b_fs_fraction"],
                           sigma_rel_z=r["sigma_rel_z"], short_circuit_peak_ma=i_short * 1e3))
    with open(vm.HERE / "results/whatif_levels.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(lv[0].keys()))
        w.writeheader()
        for r in lv:
            w.writerow({k: (f"{v:.4g}" if isinstance(v, float) else v) for k, v in r.items()})
    return rows


def main():
    whatif_analytic()
    out = []
    for dn, f in TARGET_POINTS:
        for cfg, acq in (("base", vm.Acq()), ("base", vm.Acq(boxcar=True))):
            out.append(phasor_noise(cfg, vm.DUTS[dn], f, acq=acq))
    # DDS at its minimum SNR (55 dB) for the baseline
    for dn, f in TARGET_POINTS:
        r = phasor_noise("base", vm.DUTS[dn], f, o=vm.NoiseOpts(dds_snr_db=55.0, opa_scale=1.5))
        r["corner"] = "DDS SNR 55 dB, amplifier noise x1.5"
        out.append(r)
    (vm.HERE / "results").mkdir(exist_ok=True)
    (vm.HERE / "results/noise_budget.json").write_text(json.dumps(out, indent=1))
    keys = ["config", "dut", "hz", "divider", "boxcar", "a_fs_fraction", "b_fs_fraction", "analog_sigma_a_uv",
            "analog_sigma_b_uv", "analog_rho", "adc_sigma_uv", "sigma_rel_z", "sigma_r_ohm"]
    with open(vm.HERE / "results/noise_budget.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(keys + ["corner", "dominant_group", "dominant_share"])
        for r in out:
            dom = max(r["var_groups"], key=r["var_groups"].get)
            w.writerow([r[k] if not isinstance(r[k], float) else f"{r[k]:.5g}" for k in keys] +
                       [r.get("corner", ""), dom, f"{r['var_groups'][dom]:.3f}"])
    for r in out[:2 * len(TARGET_POINTS)]:
        dom = max(r["var_groups"], key=r["var_groups"].get)
        print(f"{r['dut']:14s} {r['hz']:7.0f} box={int(r['boxcar'])} A {r['a_fs_fraction']*100:5.1f}%FS "
              f"B {r['b_fs_fraction']*100:5.1f}%FS sA {r['analog_sigma_a_uv']:6.1f} sB {r['analog_sigma_b_uv']:6.1f} "
              f"rho {r['analog_rho']:+.2f} sig|dZ/Z| {r['sigma_rel_z']:.2e} sigR {r['sigma_r_ohm']*1e6:7.1f} uohm "
              f"dom {dom} {r['var_groups'][dom]:.2f}")


if __name__ == "__main__":
    main()
