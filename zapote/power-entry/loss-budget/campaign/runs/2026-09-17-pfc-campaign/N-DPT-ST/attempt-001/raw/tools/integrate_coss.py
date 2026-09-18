#!/usr/bin/env python3
"""Parse a ngspice Coss(v) sweep log and integrate Qoss / Eoss.

Input log format (produced by coss_template_L0.cir.tmpl):
    BIAS <v>
    coss = <value>
Output: JSON with the C(v) table, Qoss(400) = int C dv, Eoss(400) = int v*C dv
(trapezoidal in v).  This is post-processing of SPICE-derived capacitance; it
introduces no device physics of its own.

Usage: integrate_coss.py <log> [vmax]
"""
import json
import re
import sys


def main() -> int:
    log, vmax = sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 400.0
    txt = open(log).read()
    pts = []
    pending = None
    for line in txt.splitlines():
        m = re.match(r"\s*BIAS\s+([-\d.eE+]+)\s*$", line)
        if m:
            pending = float(m.group(1))
            continue
        m = re.match(r"\s*coss\s*=\s*([-\d.eE+]+)\s*$", line)
        if m and pending is not None:
            c = float(m.group(1))
            if c > 0:
                pts.append((pending, c))
            pending = None
    pts = [p for p in pts if p[0] <= vmax]
    pts.sort()
    q = 0.0
    e = 0.0
    for (v0, c0), (v1, c1) in zip(pts, pts[1:]):
        dv = v1 - v0
        q += 0.5 * (c0 + c1) * dv
        e += 0.5 * (v1 * c1 + v0 * c0) * dv
    print(json.dumps({
        "vmax": vmax,
        "n_points": len(pts),
        "coss_at_0_v_f": pts[0][1],
        "coss_at_vmax_f": pts[-1][1],
        "qoss_c": q,
        "eoss_j": e,
        "coss_table": pts,
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
