#!/usr/bin/env python3
"""Stage 55, U13.A Schmitt buffer (DECISIONS 82, OPEN-ITEMS S30): the copper for U47 / C179 and the moved C167.

    python3 -I validation-results/11-candidates/c55-findings/scripts/edit55.py COPPER.json [--out OUT.json]

Poses (native-21/layout/place.py STAGE55): U47 SOT-23-5 at (31.4, 133.7, 90): VCC (30.45, 132.5625) and Y (32.35, 132.5625)
north, NC / A / GND (30.45 / 31.4 / 32.35, 134.8375) south; C179 0603 at (28.75, 133.55, 270), pad 1 (v3v3) north; C167
0603 at (32.175, 136.75, 0), pad 1 (bus_fault_flt) west.

Removed (the s54 RC node): bus_fault_flt R134.2 -> C167.1 -> U13.1, and C167.2's selv_gnd run west to the TP40 via.
Added:
- bus_fault_st: U47.4 north onto the old run's path under U13 to U13.1 (x 32.85 between U13's columns, as at s54);
- bus_fault_flt: R134.2 west under U47's body (between its pad rows) to U47.2, on south to C167.1;
- selv_gnd: U47.3 -> C167.2, a T off that run's first bend (32.35, 135.7) east to C170's selv_gnd plane via (34.25, 135.125)
  (0.60 mm from C167.1, the nearest other-net copper), C179.2 -> the TP40 via (27.675, 132.865) on the old run's last bends;
- v3v3: C179.1 -> U47.5 and a plane via at (29.9, 132.03) stubbed into U47.5, clear of the ct_zc B.Cu run (0.68 mm), TP40
  (1.17 mm centre to centre) and ct_oc_pos (0.25 mm).
Every corner is 135 degrees (no right angle; the one T is on C167.2's selv_gnd run). Idempotent: a second run changes nothing.
"""
import argparse
import json
from pathlib import Path

W = 0.25
REMOVE = [
    ("bus_fault_flt", "F.Cu", [[32.175, 133.5], [32.2, 133.395], [32.2, 131.795], [32.8, 131.195], [32.8, 129.195],
                               [32.4, 128.795], [31.698, 128.795]]),
    ("bus_fault_flt", "F.Cu", [[34.175, 133.5], [32.175, 133.5]]),
    ("selv_gnd", "F.Cu", [[30.625, 133.5], [28.225, 133.5], [27.825, 133.1], [27.825, 133.015], [27.675, 132.865]]),
    # the first s55 build's U47.3 east run: it met the south run at 90 deg on the pad (right_angle_corners 51 -> 52)
    ("selv_gnd", "F.Cu", [[32.35, 134.8375], [33.95, 134.8375], [34.25, 135.125]]),
]
ADD = [
    ("bus_fault_st", [[32.35, 132.5625], [32.35, 131.695], [32.85, 131.195], [32.85, 129.195], [32.45, 128.795],
                      [31.6975, 128.795]]),
    ("bus_fault_flt", [[34.175, 133.5], [33.975, 133.7], [31.7, 133.7], [31.4, 134.0], [31.4, 134.8375]]),
    ("bus_fault_flt", [[31.4, 134.8375], [31.4, 136.75]]),
    ("selv_gnd", [[32.35, 134.8375], [32.35, 135.7], [32.95, 136.3], [32.95, 136.75]]),
    ("selv_gnd", [[32.35, 135.7], [33.675, 135.7], [34.25, 135.125]]),
    ("selv_gnd", [[28.75, 134.325], [28.225, 133.8], [27.825, 133.4], [27.825, 133.015], [27.675, 132.865]]),
    ("v3v3", [[28.75, 132.775], [30.45, 132.5625]]),
    ("v3v3", [[29.9, 132.03], [30.2, 132.33]]),
]
VIAS = [{"net": "v3v3", "at": [29.9, 132.03], "size": 0.6, "drill": 0.3}]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("copper")
    ap.add_argument("--out")
    a = ap.parse_args()
    c = json.loads(Path(a.copper).read_text())
    gone = 0
    for net, layer, pts in REMOVE:
        hit = [t for t in c["tracks"] if t["net"] == net and t["layer"] == layer and t["points"] == pts]
        assert len(hit) <= 1, (net, pts)
        for t in hit:
            c["tracks"].remove(t)
            gone += 1
    have = {(t["net"], t["layer"], json.dumps(t["points"])) for t in c["tracks"]}
    added = 0
    for net, pts in ADD:
        if (net, "F.Cu", json.dumps(pts)) not in have:
            c["tracks"].append({"net": net, "layer": "F.Cu", "width": W, "points": pts})
            added += 1
    hv = {(tuple(v["at"]), v["net"]) for v in c["vias"]}
    nv = [v for v in VIAS if (tuple(v["at"]), v["net"]) not in hv]
    c["vias"] += nv
    Path(a.out or a.copper).write_text(json.dumps(c, indent=1) + "\n")
    print(f"stage 55: {gone} tracks removed, {added} added, {len(nv)} vias added")


if __name__ == "__main__":
    main()
