#!/usr/bin/env python3
"""Deterministic bias bound from AD9833 harmonics/spurs that alias onto the test frequency.

The capture undersamples: fs = 1 MSPS / divider_for(f).  A source harmonic at n*f0 lands on
+/-f0 whenever (n -/+ 1) f0 is close to a multiple of fs, which happens at low order when fs/f0
is a small rational (50 kHz: fs/f0 = 10, so n = 9 and 11).  The harmonic passes the chain with
the DUT impedance at n*f0, so it does not cancel in A/B and the three-standard calibration cannot
remove it.  Bias (worst phase) per spur of relative level eps at the DDS output:
    |dZ/Z| = eps * leak(dF) * |B(n f0)/B(f0)| * |hA(n f0)/A0 - hB(n f0)/B0|
leak = |sinc(dF*T)| for a residual offset dF from the fitted frequency over the record T;
B = boxcar decimator response (1 for the current firmware).

Spur levels: AD9833 wideband SFDR -60 dBc (datasheet; largest spur 0..Nyquist, a bound) and an
ESTIMATE of -80 dBc for harmonic orders >= 9.  OPA810/OPA2810 distortion is < -100 dBc and ignored.
    spur_alias.py -> results/spur_alias.json
"""
import json
import math

import numpy as np

import vi_model as vm
from noise_budget import TARGET_POINTS, boxcar_resp


def bound(dut, hz, boxcar=False, nmax=200, eps_db=(-60.0, -80.0), config="base"):
    tr = vm.transfer(config)
    word = vm.frequency_word(hz)
    f0 = vm.frequency_hz(word)
    div = vm.divider_for(hz)
    fs = vm.SAMPLE_BASE_HZ / div
    T = vm.DEFAULT_COUNT / fs
    D = div if boxcar else 1
    z0 = dut.z(f0)
    HA0, HB0 = tr.H([f0], [z0], names=["dds"])
    A0, B0 = HA0[0, 0], HB0[0, 0]
    bx0 = boxcar_resp(np.array([f0]), D)[0]
    hits = []
    for n in range(2, nmax + 1):
        fn = n * f0
        alias = (fn + fs / 2) % fs - fs / 2          # folded to (-fs/2, fs/2]
        d = min(abs(alias - f0), abs(alias + f0))
        leak = abs(np.sinc(d * T))
        if leak < 1e-3:
            continue
        HA, HB = tr.H([fn], [dut.z(fn)], names=["dds"])
        g = abs(HA[0, 0] / A0 - HB[0, 0] / B0) * abs(boxcar_resp(np.array([fn]), D)[0] / bx0)
        hits.append(dict(n=n, offset_hz=d, leak=leak, gain=g))
    worst = max([h["leak"] * h["gain"] for h in hits], default=0.0)
    out = dict(dut=dut.name, hz=hz, divider=div, boxcar=boxcar, z=[float(np.real(z0)), float(np.imag(z0))],
               hits=hits, worst_gain=worst)
    for e in eps_db:
        rel = 10 ** (e / 20) * worst
        out[f"rel_z_at_{int(-e)}dBc"] = rel
        out[f"abs_z_ohm_at_{int(-e)}dBc"] = rel * abs(z0)
    return out


def main():
    res = []
    for dn, f in TARGET_POINTS:
        for box in (False, True):
            res.append(bound(vm.DUTS[dn], f, box))
    # frequency-choice mitigation: 49 kHz instead of 50 kHz (fs/f0 no longer a small rational)
    for dn in ("coil_nopan", "coil_pan", "cap100n", "bank500n"):
        res.append(bound(vm.DUTS[dn], 49000.0, False))
    (vm.HERE / "results/spur_alias.json").write_text(json.dumps(res, indent=1))
    for r in res:
        ns = ",".join(str(h["n"]) for h in r["hits"]) or "-"
        print(f"{r['dut']:13s} {r['hz']:7.0f} box={int(r['boxcar'])} orders {ns:12s} worst gain {r['worst_gain']:.3g} "
              f"|dZ| @-60dBc {r['abs_z_ohm_at_60dBc']*1e3:8.3f} mohm  @-80dBc {r['abs_z_ohm_at_80dBc']*1e3:7.3f} mohm")


if __name__ == "__main__":
    main()
