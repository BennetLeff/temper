#!/usr/bin/env python3
"""Which outer-layer tracks run over HSB_GOOD's inner leg, per candidate layer (DECISIONS 33).

    python3 -I inner_leg_overlap.py COPPER_DUMP.json

An inner track slots the plane it is cut into; a track on the adjacent outer layer that runs along it then loses that
reference locally (return_path19 looks through to the other SELV plane). For each candidate leg (the two routes the
router found from U44.13's via to (44.5, 129.0); the In2 one is the one authored in patches21.add_stage30) this sums
the length of every outer track of the adjacent layer (F over In1, B over In2) within the leg's half-width + 0.3 mm
pour clearance + 0.2 mm, by net, and the part of it on return_path19's asserted nets.
"""
import json
import sys

from shapely.geometry import LineString

ASSERTED = {"pwm_hb", "pwm_lb", "pwm_ha", "pwm_la", "ct_zc", "bus_fault_hot"}   # return_path19 ASSERT_PLANE
LEGS = {
    "In1.Cu": [[30.875, 109.765], [31.1, 110.0], [34.5, 113.4], [35.3, 113.4], [36.3, 114.4], [36.3, 122.4],
               [41.9, 128.0], [43.7, 128.0], [44.5, 128.8], [44.5, 129.0]],
    "In2.Cu": [[30.875, 109.765], [31.1, 110.0], [34.1, 113.0], [34.1, 120.2], [41.9, 128.0], [43.7, 128.0],
               [44.5, 128.8], [44.5, 129.0]],
}
OUTER = {"In1.Cu": "F.Cu", "In2.Cu": "B.Cu"}

d = json.load(open(sys.argv[1]))
for inner, pts in LEGS.items():
    zone = LineString(pts).buffer(0.125 + 0.3 + 0.2)
    by = {}
    for t in d["tracks"]:
        if t["layer"] != OUTER[inner] or t["net"] == "hsb_good":
            continue
        ln = LineString([t["a"], t["b"]]).intersection(zone).length
        if ln > 0:
            by[t["net"]] = by.get(t["net"], 0.0) + ln
    asserted = sum(v for n, v in by.items() if n in ASSERTED)
    print(f"{inner} leg {LineString(pts).length:.1f} mm; under it on {OUTER[inner]}: "
          + ", ".join(f"{n} {v:.2f}" for n, v in sorted(by.items(), key=lambda x: -x[1]))
          + f"; asserted {asserted:.2f} mm")
