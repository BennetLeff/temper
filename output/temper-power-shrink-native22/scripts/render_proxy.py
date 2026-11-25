#!/usr/bin/env python3
"""Render the B3 copper masks of s53 and of a native-22 transplant proxy, layer by layer (1 mm block fill fraction).

    python3 render_proxy.py [--board native22_218]   # -> renders/proxy_copper_<board>.png
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json

import numpy as np

import common as C


def fine_of(board):
    d = C.WORK / board
    g = json.loads(gzip.open((d / "geom_path.txt").read_text().strip(), "rt").read()) if board != "s53" else C.load_geom()
    key = hashlib.sha256((g["board_sha256"] + "0.0625").encode()).hexdigest()[:16]
    return np.load(d / "cache" / f"fine_{key}.npz"), g


def blocks(a, f=16):
    nx, ny = a.shape[0] // f * f, a.shape[1] // f * f
    return a[:nx, :ny].reshape(nx // f, f, ny // f, f).mean((1, 3))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="native22_218")
    a = ap.parse_args()
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axs = plt.subplots(4, 2, figsize=(16, 17), gridspec_kw={"width_ratios": [290, 218]})
    for col, b in enumerate(("s53", a.board)):
        z, g = fine_of(b)
        terr = None
        if b != "s53":
            terr = np.load(C.WORK / b / "territory.npz")
        for row, L in enumerate(("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")):
            ax = axs[row, col]
            m = blocks(z["cu_" + L].astype(np.float32))
            w = z["board"].shape[0] * 0.0625
            h = z["board"].shape[1] * 0.0625
            ax.imshow(m.T, origin="upper", extent=(0, w, h, 0), cmap="copper_r", vmin=0, vmax=1)
            if terr is not None:
                gf = terr["gfill"]
                ax.contour((np.arange(gf.shape[0]) + 0.5) * 0.25, (np.arange(gf.shape[1]) + 0.5) * 0.25, gf.T.astype(float),
                           levels=[0.5], colors="c", linewidths=0.6)
            if b == "s53":
                ax.plot([0, 290, 290, 91, 91, 0, 0], [0, 0, 140, 140, 190, 190, 0], "k-", lw=0.8)
            ax.set_title(f"{b} {L} (1 mm block copper fraction)" + ("; cyan: gap-filled" if terr is not None else ""),
                         fontsize=9)
            ax.set_xlim(0, w); ax.set_ylim(h, 0); ax.tick_params(labelsize=7)
    fig.tight_layout()
    fig.savefig(C.RENDERS / f"proxy_copper_{a.board}.png", dpi=80)


if __name__ == "__main__":
    main()
