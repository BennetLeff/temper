#!/usr/bin/env python3
"""Print the frozen netlist around the C1 change requests (DECISIONS C37-C41): every net touching a
changed or new part, with the parts' MPNs and values. Review aid; the checks live in
tools/verify_controller.py.

    python3 evidence/c1-crs/dump_nets.py [path-prefix ...]
"""
import sys
from pathlib import Path

UNIT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(UNIT / "tools"))
from netlist import attach_resolved, read_netlist  # noqa: E402

PREFIXES = sys.argv[1:] or ["rtd_pan.r_s", "rtd_pan.c_s1", "rtd_pan.c_cm", "rtd_pan.c_j", "rtd_pan.d_j",
                            "rtd_pan.c_window", "rtd_pan.r_rtdin", "rtd_pan.r_window", "rtd_pan.r_low_bottom",
                            "rtd_pan.c_rtd_input", "rtd_pan.r_ref", "rtd_pan.j_rtd1", "r_runaway", "u_runaway",
                            "u_rim_trip", "r_rim_th", "j_rim", "d_rim", "u_cm", "r_cm", "c_cm", "J11"]


def main():
    nl = attach_resolved(read_netlist(UNIT / "frozen/default.net"), UNIT / "frozen/resolved-components.json")
    refs = sorted(r for r, p in nl.refs.items() if any(p.startswith(x) or r == x for x in PREFIXES))
    print(f"{len(nl.refs)} components")
    for r in refs:
        pins = sorted({p for n, nodes in nl.nets.items() for rr, p in nodes if rr == r}, key=lambda s: int(s) if s.isdigit() else 0)
        conn = ", ".join(f"{p}:{nl.net_of(r, p)}" for p in pins)
        print(f"{r:5s} {nl.refs[r]:28s} {nl.mpn.get(r, ''):22s} {nl.value.get(r) or '':18s} {conn}")


if __name__ == "__main__":
    main()
