#!/usr/bin/env python3
"""Extrapolate the leg port matrices to zero closure height; write SPICE.

Every solve measures board copper + closures (arches) at height h. The board
value is the h -> 0 limit. For each matrix entry L_ij(h) this reports:
  lin12  straight line through h = 1, 2 mm at 0:   2 L(1) - L(2)
  lsq    least-squares line through 1, 2, 3 at 0  (needs 3 heights)
  quad   parabola through 1, 2, 3 at 0:           3 L(1) - 3 L(2) + L(3)
The value used is quad when three heights exist (else lin12). The spread of
the available estimates is a METHOD spread, not an error bound (D-4 review,
P2): a higher-order term invisible at the sampled heights can move every
estimate together, and with two heights the spread is identically zero.

Gate: the extrapolated matrix must be symmetric positive definite (a
physical inductance matrix); otherwise exit nonzero.

SPICE: a subcircuit with one inductor per port (node pair Pk_a, Pk_b, the
dot at a, a = the closure's 'a' pad, current a -> b as solved) and K
statements k_ij = L_ij / sqrt(L_ii L_jj). Board copper only: component
inductance is added separately. Infineon's IPW65R018CFD7 models already
contain Ld/Ls/Lg (PACKAGE-INDUCTANCE.md), so do not add them twice.

    extrapolate.py --matrix 1 legA-h1.matrix.txt --matrix 2 legA-h2.matrix.txt [--matrix 3 ...]
                   --names P1_C38 P2_C39 P3_gate_high P4_gate_low [--spice out.lib --subckt LEGA_BOARD]
    extrapolate.py --selftest
"""
from __future__ import annotations

import argparse
import json
import math

import numpy as np


def read_matrix(path: str, names: list[str] | None = None) -> np.ndarray:
    """L (nH) from an inductance_matrix.py RESULT line, with its port order checked
    (D-4 review, P2): against `names` when the file records port identities, else
    the physical ids must be ascending (10, 11, 12, 13 = P1..P4)."""
    for line in open(path):
        if line.startswith("RESULT "):
            d = json.loads(line[7:])
            ids = d.get("port_identity")
            if ids and names and [p["name"] for p in ids] != list(names):
                raise SystemExit(f"{path}: port order {[p['name'] for p in ids]} != expected {list(names)}")
            phys = [int(p) for p in d.get("ports", [])]
            if phys and phys != sorted(phys):
                raise SystemExit(f"{path}: ports {phys} not in ascending order")
            return np.array(d["L_nH"], dtype=float)
    raise ValueError(f"no RESULT line in {path}")


def extrapolate(Ls: dict[float, np.ndarray]) -> dict:
    hs = sorted(Ls)
    est = {}
    if 1.0 in Ls and 2.0 in Ls:
        est["lin12"] = 2 * Ls[1.0] - Ls[2.0]
    if len(hs) >= 3:
        H = np.array(hs[:3])
        Y = np.stack([Ls[h] for h in hs[:3]])                    # (3, n, n)
        # least-squares line and exact parabola, evaluated at h = 0, entry-wise
        A1 = np.stack([np.ones(3), H], 1)
        A2 = np.stack([np.ones(3), H, H ** 2], 1)
        flat = Y.reshape(3, -1)
        est["lsq"] = np.linalg.lstsq(A1, flat, rcond=None)[0][0].reshape(Y.shape[1:])
        est["quad"] = np.linalg.solve(A2, flat)[0].reshape(Y.shape[1:])
    if not est:
        raise ValueError("need at least heights 1 and 2 mm")
    use = "quad" if "quad" in est else "lin12"
    stack = np.stack(list(est.values()))
    return {"method": use, "L0": est[use], "low": stack.min(0), "high": stack.max(0), "estimates": est}


def spice(L: np.ndarray, names: list[str], subckt: str, note: str) -> str:
    n = len(names)
    pins = " ".join(f"{nm}_a {nm}_b" for nm in names)
    out = [f"* {note}", "* Board copper only; add component inductance separately (see PACKAGE-INDUCTANCE.md).",
           f".SUBCKT {subckt} {pins}"]
    for i, nm in enumerate(names):
        out.append(f"L_{nm} {nm}_a {nm}_b {L[i, i]:.6g}n")
    for i in range(n):
        for j in range(i + 1, n):
            k = L[i, j] / math.sqrt(L[i, i] * L[j, j])
            out.append(f"K_{names[i]}_{names[j]} L_{names[i]} L_{names[j]} {k:.6f}")
    out.append(f".ENDS {subckt}")
    return "\n".join(out) + "\n"


def selftest() -> None:
    rng = np.random.default_rng(1)
    B = rng.normal(size=(4, 4))
    L0 = B @ B.T + 4 * np.eye(4)                                  # SPD "board" matrix
    S = rng.normal(size=(4, 4)); S = S + S.T                       # arch slope
    C = rng.normal(size=(4, 4)); C = C + C.T                       # curvature
    Ls = {h: L0 + S * h + C * h * h for h in (1.0, 2.0, 3.0)}
    r = extrapolate(Ls)
    assert r["method"] == "quad" and np.allclose(r["L0"], L0), "parabola must recover L0 exactly"
    lin = extrapolate({1.0: Ls[1.0], 2.0: Ls[2.0]})
    assert np.allclose(lin["L0"], L0 - 2 * C), "straight line misses by -2C for a parabola"
    txt = spice(L0, ["A", "B", "C", "D"], "T", "selftest")
    assert txt.count("K_") == 6 and ".SUBCKT T A_a A_b" in txt
    print("selftest ok")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--matrix", nargs=2, action="append", metavar=("H_MM", "FILE"))
    ap.add_argument("--names", nargs="+")
    ap.add_argument("--spice", default=None)
    ap.add_argument("--subckt", default="LEGA_BOARD")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
        return
    Ls = {float(h): read_matrix(f, a.names) for h, f in a.matrix}
    names = a.names
    r = extrapolate(Ls)
    L0 = r["L0"]
    sym = np.allclose(L0, L0.T)
    eig = np.linalg.eigvalsh((L0 + L0.T) / 2)
    res = {"heights_mm": sorted(Ls), "method": r["method"], "names": names,
           "L0_nH": L0.round(4).tolist(), "method_spread_low_nH": r["low"].round(4).tolist(),
           "method_spread_high_nH": r["high"].round(4).tolist(),
           "note": "method spread, not an error bound",
           "estimates_nH": {k: v.round(4).tolist() for k, v in r["estimates"].items()},
           "k0": [[round(L0[i, j] / math.sqrt(L0[i, i] * L0[j, j]), 4) for j in range(len(names))]
                  for i in range(len(names))],
           "symmetric": bool(sym), "min_eigenvalue_nH": float(eig.min())}
    print("RESULT " + json.dumps(res))
    for i, ni in enumerate(names):
        print(f"{ni:14s} L0 = {L0[i, i]:8.3f} nH  [{r['low'][i, i]:.3f} .. {r['high'][i, i]:.3f}]  "
              + "  ".join(f"h{h:g}={Ls[h][i, i]:.3f}" for h in sorted(Ls)))
    if not (sym and eig.min() > 0):
        raise SystemExit(f"extrapolated matrix is not symmetric positive definite (min eig {eig.min():.4g} nH)")
    if a.spice:
        note = f"leg port matrix extrapolated to h=0 ({r['method']}) from h = {sorted(Ls)} mm"
        open(a.spice, "w").write(spice(L0, names, a.subckt, note))


if __name__ == "__main__":
    main()
