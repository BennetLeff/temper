#!/usr/bin/env python3
"""Lumped DC-link and node-to-PE voltage estimates for ORACLE-ANSWER.md.

Model: full-bridge series-resonant tank (L, Cr, pan R) driven by a square wave
at the instantaneous rectified bus. At turn-off all four switches open; the
body diodes present -sign(i)*Vbus to the tank and return |i| to the bus
capacitor. The rectifier diodes block while Vbus > |v_line|, so the bus only
rises. Ring-down continues until |v_Cr| <= Vbus. Ideal diodes, no stray
inductance, no snubbers: an estimate, not a bound on measured overshoot.

Node-to-PE statistics assume N at earth; the diode bounds make the result
symmetric in L and N, so reversed polarity gives the same values.
"""

from __future__ import annotations

import math

CR = 0.54e-6
CBUS = 4.5e-6  # 2 x 2.5 uF film, -10 %
DT = 2e-9


def square(t: float, period: float) -> int:
    return 1 if (t % period) < period / 2 else -1


def ringdown(i: float, vc: float, vb: float, L: float, R: float) -> tuple[float, float]:
    while True:
        if abs(i) < 1e-9:
            if abs(vc) <= vb + 1e-6:
                return vb, vc
            i = -1e-6 * math.copysign(1, vc)
        sg = 1 if i > 0 else -1
        ni = i + (-sg * vb - vc - R * i) / L * DT
        if ni * sg <= 0:
            i = 0.0
            continue
        i = ni
        vc += i / CR * DT
        vb += abs(i) / CBUS * DT


def steady_states(L: float, R: float, f: float, vb: float, cycles: int = 60):
    period = 1 / f
    i = vc = t = 0.0
    n = int(cycles * period / DT)
    last = n - int(period / DT)
    states, ipk = [], 0.0
    for k in range(n):
        i += (square(t, period) * vb - vc - R * i) / L * DT
        vc += i / CR * DT
        t += DT
        if k > last:
            states.append((i, vc))
            ipk = max(ipk, abs(i))
    return states[:: max(1, len(states) // 64)], ipk


def trip_state(L: float, R: float, vb: float, itrip: float, latency: float = 300e-9):
    f0 = 1 / (2 * math.pi * math.sqrt(L * CR))
    period = 1 / f0
    i = vc = t = 0.0
    tripped = None
    while t < 20e-3:
        i += (square(t, period) * vb - vc - R * i) / L * DT
        vc += i / CR * DT
        t += DT
        if tripped is None and abs(i) >= itrip:
            tripped = t
        if tripped is not None and t >= tripped + latency:
            return i, vc
    raise RuntimeError("current never reached trip")


def envelope_bound(L: float, itrip: float, vb: float) -> float:
    """Conservative bus bound: the at-resonance envelope can exceed the trip
    by one half-cycle step 2*Vbus/Z0, and all of 1/2 L I^2 returns to Cbus."""
    z0 = math.sqrt(L / CR)
    env = itrip + 2 * vb / z0
    return math.sqrt(vb * vb + L * env * env / CBUS)


def node_rms(vrms: float, vcr_crest: float, fsw: float = 33e3, fl: float = 60, n: int = 200_000):
    vpk = vrms * math.sqrt(2)
    acc: dict[str, float] = {}
    pk: dict[str, float] = {}
    for k in range(n):
        t = k / n / fl
        vl = vpk * math.sin(2 * math.pi * fl * t)
        vb = abs(vl)
        ret = 0.0 if vl >= 0 else vl
        busp = ret + vb
        ph = 2 * math.pi * fsw * t
        swa = busp if math.sin(ph) >= 0 else ret
        swb = ret if math.sin(ph) >= 0 else busp
        vcr = vcr_crest * (vb / vpk) * math.sin(ph - math.pi / 2)
        for name, v in (
            ("BUS_P/HV_RET/SW_x", swa),
            ("RES_A (T1 today)", swb + vcr),
            ("PS1 L input", vl),
        ):
            acc[name] = acc.get(name, 0.0) + v * v
            pk[name] = max(pk.get(name, 0.0), abs(v))
    return {name: (math.sqrt(acc[name] / n), pk[name]) for name in acc}


def main() -> None:
    vb0 = 127 * 1.10 * math.sqrt(2)
    print(f"high-line crest bus: {vb0:.0f} V; Cbus {CBUS * 1e6:.1f} uF")
    for label, L in (("70 uH", 70e-6), ("48 uH", 48e-6)):
        states, ipk = steady_states(L, 5.3, 33e3, vb0)
        worst = max(ringdown(i, v, vb0, L, 5.3) for i, v in states)
        print(f"normal shutdown {label}: Ipk {ipk:.0f} A -> Vbus {worst[0]:.0f} V, Cr left {worst[1]:.0f} V")
    for itrip in (91, 61):
        for L in (48e-6, 70e-6, 100e-6):
            i, vc = trip_state(L, 0.3, vb0, itrip)
            vb, vcr = ringdown(i, vc, vb0, L, 0.3)
            print(
                f"OCP {itrip} A at resonance, L {L * 1e6:.0f} uH: one trajectory {vb:.0f} V, "
                f"Cr left {vcr:.0f} V; envelope bound {envelope_bound(L, itrip, vb0):.0f} V"
            )
    for label, vrms, vcr in (
        ("rated 127 V, 70 uH", 127, 277),
        ("rated 127 V, 48 uH", 127, 402),
        ("127 V +10 %, 48 uH", 139.7, 442),
    ):
        print(label)
        for name, (rms, peak) in node_rms(vrms, vcr).items():
            print(f"  {name:18s} {rms:5.0f} V rms {peak:5.0f} V pk")


if __name__ == "__main__":
    main()
