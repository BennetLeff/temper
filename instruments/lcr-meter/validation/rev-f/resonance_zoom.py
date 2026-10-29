#!/usr/bin/env python3
"""Re-sweep one loop_matrix deck on a dense linear grid to resolve a narrow minimum of |1+T|.

The matrix samples 120 points per decade (1.9 % steps). The lossless 1 m coax models give line
resonances narrower than that, so a single sample can land on or beside a resonance, and the
reported min |1+T| then depends on where the grid falls. This script reruns the same deck (same
netlist, same bridge, same de-embedding as loop_matrix.rs return_ratio) with `ac lin N f0 f1`.

  python3 validation/rev-f/resonance_zoom.py DECK_BASENAME [f0_MHz f1_MHz N]
DECK_BASENAME is a matrix case name (the per-case .cir must exist: run the mode without deleting
its scratch files). Runs in validation/stability-full-chain (the deck's includes are relative)
and removes its own scratch files. Needs ngspice 45.2.
"""
from __future__ import annotations

import math
import re
import subprocess
import sys
from pathlib import Path

SFC = Path(__file__).resolve().parents[1] / 'stability-full-chain'


def main():
    name = sys.argv[1]
    f0, f1, n = (float(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4])) if len(sys.argv) > 4 else (60.0, 120.0, 6001)
    deck = (SFC / f'{name}.cir').read_text()
    bridge = float(re.search(r'^Rbridge \S+ probe_f (\S+)$', deck, re.M).group(1))
    tag = 'zoomtmp'
    deck, k = re.subn(r'^ac dec \d+ 1 1G$', f'ac lin {n} {f0}e6 {f1}e6', deck.replace(name, tag), flags=re.M)
    assert k == 2, f'expected two AC sweeps, found {k}'
    (SFC / f'{tag}.cir').write_text(deck)
    try:
        subprocess.run(['ngspice', '-b', f'{tag}.cir'], cwd=SFC, check=True, capture_output=True)
        rd = lambda s: [list(map(float, l.split())) for l in (SFC / f'{tag}_{s}.dat').read_text().splitlines()[1:]]
        e, f = rd('e'), rd('f')
    finally:
        for p in SFC.glob(f'{tag}*'):
            p.unlink()
    best = (9e9, 0.0, 0.0)
    for a, b in zip(e, f):
        z11, z21, z12, z22 = complex(a[1], a[2]), complex(a[3], a[4]), complex(b[1], b[2]), complex(b[3], b[4])
        gd = (2 / bridge) * (z11 * z22 - z12 * z21)
        t = (gd - z12 - z21) / (z11 + z22 - gd)
        d = abs(1 + t)
        if d < best[0]:
            best = (d, a[0], math.degrees(math.atan2(t.imag, t.real)))
    step = (f1 - f0) / (n - 1) * 1e3
    print(f'{name}: min |1+T| {best[0]:.4f} at {best[1] / 1e6:.4f} MHz (angle of T {best[2]:.1f} deg), '
          f'lin {n} points {f0:g}-{f1:g} MHz, step {step:.1f} kHz')


if __name__ == '__main__':
    main()
