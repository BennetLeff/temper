"""How much does a switching-frequency dither lower a CISPR band-A (9-150 kHz) reading?

Impulse's US12712433B1 describes spread-spectrum modulation of the PWM carrier
so the EMI filter can stay small. Temper's binding conducted-EMI lines sit in
band A (the tank fundamental and the 2fs bus-ripple line, 47 CFR 18.307 QP
limit; worst ~60-70 kHz, `emi_split_cap.json`), so a firmware dither is the
cheapest possible lever. This script measures the reading reduction for a
narrowband line whose frequency is swept with a triangular dither, against
the same line held still, through a CISPR 16-1-1 band-A receiver model:

  - IF filter: Gaussian, 200 Hz 6 dB bandwidth (band A RBW);
  - quasi-peak detector: 45 ms charge, 500 ms discharge, 160 ms meter
    (critically damped 2nd order, as two 1st-order 80 ms stages - an
    approximation of the mechanical meter);
  - average detector: linear envelope through the same meter.

The receiver is tuned across the dithered span and the worst (highest)
reading is reported, as a scan would find it. `harmonic` scales the deviation
(the 2fs bus-ripple line moves twice as far as fs).

This is a model of the measuring receiver only. It does not include the line
cycle's own amplitude modulation (which also lowers AV/QP) and is not a
compliance number. Run: python3 dither_qp.py -> dither_qp.json
"""
import json
from pathlib import Path

import numpy as np
from scipy.signal import lfilter

FS = 8000.0           # complex-baseband sample rate, Hz (span <= +-3.5 kHz)
T = 4.0               # simulated seconds; readings use the last 1 s, after the 500 ms QP discharge settles
RBW = 200.0
TAU_C, TAU_D, TAU_M = 45e-3, 500e-3, 160e-3


def gaussian_if(rbw):
    sigma_f = rbw / 2 / np.sqrt(2 * np.log(2))          # |H| = exp(-f^2/(2 s^2)) = 0.5 at f = rbw/2
    sigma_t = 1 / (2 * np.pi * sigma_f)
    t = np.arange(-4 * sigma_t, 4 * sigma_t, 1 / FS)
    h = np.exp(-t**2 / (2 * sigma_t**2))
    return h / h.sum()


def detectors(env):
    dt = 1 / FS
    q = 0.0
    qp = np.empty_like(env)
    ac, ad = dt / TAU_C, dt / TAU_D
    for i, e in enumerate(env):          # QP charge/discharge (diode detector)
        q += (e - q) * ac if e > q else -q * ad
        qp[i] = q
    def meter(x):
        a = dt / (TAU_M / 2)
        y = lfilter([a], [1, -(1 - a)], x)
        return lfilter([a], [1, -(1 - a)], y)
    tail = slice(int((T - 1.0) * FS), None)
    return meter(qp)[tail].max(), meter(env)[tail].max()


def reading(dev_hz, rate_hz, tune_hz, h):
    t = np.arange(0, T, 1 / FS)
    if dev_hz == 0:
        f = np.zeros_like(t)
    else:
        tri = 2 * np.abs(2 * ((t * rate_hz) % 1.0) - 1) - 1          # triangle, -1..1
        f = h * dev_hz * tri
    phase = 2 * np.pi * np.cumsum(f - tune_hz) / FS
    y = np.convolve(np.exp(1j * phase), gaussian_if(RBW), mode="same")
    return detectors(np.abs(y))


def main():
    rows = []
    ref_qp, ref_av = reading(0, 1, 0, 1)
    for h in (1, 2):
        for dev in (250.0, 500.0, 1000.0, 1500.0):
            for rate in (50.0, 120.0, 200.0, 1000.0):
                if h * dev > 3500:
                    continue
                tunes = np.linspace(-h * dev, h * dev, 9)
                qp, av = max(reading(dev, rate, tu, h) for tu in tunes)
                rows.append({"harmonic": h, "fs_dev_pm_Hz": dev, "dither_rate_Hz": rate,
                             "QP_reduction_dB": round(20 * np.log10(ref_qp / qp), 1),
                             "AV_reduction_dB": round(20 * np.log10(ref_av / av), 1)})
                print(rows[-1], flush=True)
    out = {"scope": __doc__.strip(), "receiver": {"RBW_Hz": RBW, "QP_charge_s": TAU_C, "QP_discharge_s": TAU_D,
                                                  "meter_s": TAU_M}, "rows": rows}
    Path(__file__).with_name("dither_qp.json").write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main()
