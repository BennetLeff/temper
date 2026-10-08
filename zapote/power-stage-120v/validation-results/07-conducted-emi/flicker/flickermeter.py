#!/usr/bin/env python3
"""120 V / 60 Hz IEC 61000-4-15:2010 numerical flickermeter, blocks 1–5.

Fixed-frequency, uniformly sampled instantaneous voltage input; no hardware
anti-aliasing or Class F1 qualification. See out-D35/README.md for validation.
Requires numpy/scipy. Public API retains filter state within a complete record;
prepend >=180 s settling before the requested 600 s evaluation interval.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from scipy import signal

Array = NDArray[np.float64]
K = 1.6357
LAMBDA, W1, W2, W3, W4 = 2 * np.pi * np.array([4.167375, 9.077169, 2.939902, 1.394468, 17.31512])
WEIGHT_B = np.array([K * W1 / W2, K * W1, 0]) * W3 * W4
WEIGHT_A = np.polymul([1, 2 * LAMBDA, W1**2], np.polymul([1, W3], [1, W4]))


def gain() -> float:
    """Analog scale calibration at 8.8 Hz, Table 1a dU/U=.321% peak-to-peak.

    Block 2 at unit peak carrier has modulation amplitude d/2. Block 4's
    peak includes the residual double-modulation ripple of its 300 ms filter.
    This one calibration point does not tune any frequency-response parameter.
    """
    w = 2 * math.pi * 8.8
    h = abs(np.polyval(WEIGHT_B, 1j * w) / np.polyval(WEIGHT_A, 1j * w))
    h *= w / abs(1j * w + 2 * math.pi * .05)
    h *= 1 / math.sqrt(1 + (8.8 / 42)**12)
    peak = (.00321 * h / 2)**2 / 2 * (1 + 1 / math.sqrt(1 + (2 * w * .3)**2))
    return 1 / peak


def pinst(voltage: Array, fs: int = 4800) -> Array:
    """Process instantaneous volts; fs must be an integer multiple of 120."""
    v = np.asarray(voltage, dtype=float)
    if fs < 2400 or fs % 120 or v.ndim != 1 or len(v) < fs or not np.isfinite(v).all():
        raise ValueError("finite 1-D voltage >=1 s; fs>=2400, multiple of 120 required")
    half = fs // 120
    if len(v) % half:
        raise ValueError("record must contain whole half-cycles")
    # Block 1: 27.3 s adaptation of measured half-cycle RMS (clause 5.3).
    rms = np.sqrt(np.mean(v.reshape(-1, half)**2, axis=1))
    if np.any(rms < 1):
        raise ValueError("voltage interruption outside this tool's validated envelope")
    alpha = -math.expm1(-1 / (120 * 27.3))
    adapted, _ = signal.lfilter([alpha], [1, -(1 - alpha)], rms, zi=[rms[0] * (1 - alpha)])
    # Causal previous-half-cycle adaptation. At startup use first RMS estimate.
    divisor = np.repeat(np.r_[adapted[0], adapted[:-1]], half)
    demodulated = (v / (math.sqrt(2) * divisor))**2  # block 2
    hp = signal.butter(1, .05, "highpass", fs=fs, output="sos")
    lp = signal.butter(6, 42, fs=fs, output="sos")
    b, a = signal.bilinear(WEIGHT_B, WEIGHT_A, fs)
    weighted = signal.sosfilt(np.vstack([hp, lp, signal.tf2sos(b, a)]), demodulated)
    b, a = signal.bilinear([1], [.3, 1], fs)
    return signal.lfilter(b, a, weighted**2) * gain()  # block 4


def pst(inst: Array) -> float:
    """Block 5: exact empirical exceedance percentiles, avoiding histogram bins."""
    p = np.asarray(inst, dtype=float)
    if not len(p) or not np.isfinite(p).all() or np.min(p) < 0:
        raise ValueError("finite nonnegative Pinst required")
    percentages = [.1, .7, 1, 1.5, 2.2, 3, 4, 6, 8, 10, 13, 17, 30, 50, 80]
    q = dict(zip(percentages, np.percentile(p, [100 - x for x in percentages])))
    return math.sqrt(.0314 * q[.1] + .0525 * np.mean([q[x] for x in (.7, 1, 1.5)])
                     + .0657 * np.mean([q[x] for x in (2.2, 3, 4)])
                     + .28 * np.mean([q[x] for x in (6, 8, 10, 13, 17)])
                     + .08 * np.mean([q[x] for x in (30, 50, 80)]))


def plt(values: list[float]) -> float:
    if len(values) != 12 or not all(math.isfinite(v) and v >= 0 for v in values):
        raise ValueError("Plt requires twelve consecutive valid 10-minute Pst values")
    return (sum(v**3 for v in values) / 12)**(1 / 3)


def modulation(kind: str, frequency: float, depth_pct: float, seconds: int = 600,
               fs: int = 4800, warmup: int = 180) -> Array:
    """Centered peak-to-peak modulation, phase zero at first modulation edge."""
    t = np.arange((warmup + seconds) * fs, dtype=float) / fs - warmup
    if kind == "sine":
        m = np.sin(2 * np.pi * frequency * t)
    elif kind == "square":
        m = np.where((t * frequency) % 1 < .5, 1., -1.)
    else:
        raise ValueError("modulation kind must be sine or square")
    m[t < 0] = 0
    return 120 * math.sqrt(2) * (1 + depth_pct / 200 * m) * np.sin(2 * np.pi * 60 * t)


def measure(voltage: Array, fs: int = 4800, warmup: int = 180) -> dict[str, float]:
    if warmup < 180 or len(voltage) != (warmup + 600) * fs:
        raise ValueError("measurement requires >=180 s warmup and exactly 600 s afterward")
    inst = pinst(voltage, fs)[warmup * fs:]
    return {"Pst": pst(inst), "Pinst_max": float(np.max(inst))}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("voltage_npy", type=Path)
    parser.add_argument("--fs", type=int, default=4800)
    parser.add_argument("--warmup", type=int, default=180)
    args = parser.parse_args()
    print(json.dumps(measure(np.load(args.voltage_npy, allow_pickle=False), args.fs, args.warmup), indent=2))


if __name__ == "__main__":
    main()
