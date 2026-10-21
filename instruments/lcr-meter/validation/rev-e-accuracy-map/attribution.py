#!/usr/bin/env python3
"""Which error source sets the map at its edges: E with one source enabled at a time (study.SOURCES).

    attribution.py -> results/attribution.json, table on stdout
"""
import json
import math

import numpy as np

import accuracy_map as m

s = m.s
POINTS = [(100, 1e3, 0.01), (100, 85e3, 0.01), (100, 85e3, 1.0), (100000, 85e3, 1e5),
          (100000, 1e3, 1e6), (100000, 85e3, 1e6), (100000, 1e3, 1e7)]


def e_worst(r, f, z, corner, en):
    zs = [z * complex(math.cos(t), math.sin(t)) for t in m.PHASES.values()]
    out = []
    for zt, zm in zip(zs, m.run_point(r, f, zs, corner, en=en)):
        out.append(max(m.stats(np.abs(zm) / abs(zt) - 1), m.stats(np.angle(zm / zt))))
    return max(out)


def main():
    rows = []
    for r, f, z in POINTS:
        row = dict(range=r, f=f, z=z)
        for src in list(s.SOURCES) + ["all"]:
            en = s.ALL if src == "all" else frozenset([src])
            row[src] = [e_worst(r, f, z, c, en) for c in (False, True)]
        rows.append(row)
    (m.RES / "attribution.json").write_text(json.dumps(rows, indent=1))
    cols = list(s.SOURCES) + ["all"]
    print("| Range | f | \\|Z\\| | " + " | ".join(cols) + " |")
    print("|---" * (len(cols) + 3) + "|")
    for row in rows:
        print(f"| {m.rng_label(row['range'])} | {m.flabel(row['f'])} | {m.zlabel(row['z'])} | "
              + " | ".join(f"{m.pct(row[c][0])} / {m.pct(row[c][1])}" for c in cols) + " |")


if __name__ == "__main__":
    main()
