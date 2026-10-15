#!/usr/bin/env python3
"""Stage 18: RES_A to SELV/PE distances per copper layer, from a native-21 copper dump (DECISIONS item 7 / 18).

    python3 res_a_creepage18.py COPPER_DUMP.json [--json OUT.json]      # gate: exit 1 if any outer pair < 12.6 mm
    python3 res_a_creepage18.py --control S17B_COPPER_DUMP.json          # control: must find the two 17b B.Cu gaps

Basis (DECISIONS item 7, owner-items/m6m10/coil-selv-28a/): RES_A to earth is 297 V rms / 656 V pk in normal use at
28 A, so reinforced creepage at PD3 / IIIa (IEC 60335-1 Table 17 x 2, >250-400 V band) is 12.6 mm; every other HOT net
is <= 250 V rms and keeps the 8.0 mm floor.

Outer layers (F.Cu, B.Cu) are surface creepage paths: every RES_A copper item on that layer (pours, tracks, via lands,
pads on that side) against every SELV/PE item on the same layer, straight-line distance (on a slotless board the surface
path is at least this, so it is conservative). The J5 ring lug (bare ring <= 10 mm, DECISIONS 2026-10-08 M6) is added
on F.Cu as a 5.0 mm-radius disk at the stud.

Inner layers (In1.Cu, In2.Cu) are reported, not gated at 12.6 mm: copper there is embedded in the laminate, so a path
from it is through solid insulation (DECISIONS item 7). The repo's figure for reinforced solid insulation is 2 mm
thickness (IEC 60335-1 29.3, DECISIONS 2026-10-08 M11), and the plan-view all-layer barrier (barrier21.py, 8.0 mm) bounds
every through-laminate path from inner RES_A copper to any SELV/PE copper at >= 8.0 mm. Whether the core/prepreg
interface on one inner layer counts as a cemented joint is a certifier question (stated in the README).

Pads of one footprint against each other are skipped (component rating governs), as in barrier21.py.
SMD pad sides: the dump's pad "layers" field (plot_copper.py from stage 18); older dumps (17b) take them from the
evidence.json beside the dump (tools/copper_dump.py, same board).
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import nearest_points

UNIT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(UNIT / "native-21/layout"))
import rules21  # noqa: E402
from layers21 import CU, INNER, OUTER  # noqa: E402,F401  (stage 33: native-21/stackup.json)
FLOOR = rules21.RES_A_CREEPAGE      # 12.6 mm
HV = rules21.RES_A_NETS             # {"res_a"}
# CRBLEED_1 (3/4 tap of the bleed string) is 242.5 V rms with the L70 coil of record (8.0 mm band) but 255.1 V rms
# for any L 70-90 uH (tank_taps18.py): this script also holds it to 12.6 mm on the outer layers as a guard.
GUARD = {"crbleed_1"}
J5_LUG_R = 5.0                      # bare ring <= 10 mm
# 17b control: the two pairs the owner measured on stage 17b (B.Cu), reproduced to 0.01 mm
CONTROL_17B = {("B.Cu", "res_a", "line_zc_raw"): 8.14, ("B.Cu", "res_a", "v15_selv"): 9.40}
# the other tank nets, reported against their own floor (8.0 mm; crbleed_1 242.5 V rms, see README)
REPORT_ALSO = ("crbleed_1", "crbleed_2", "crbleed_3", "coil_feed", "sw_a", "sw_b")


def pad_layers_from_evidence(dump_path: Path):
    ev = dump_path.with_name("evidence.json")
    if not ev.exists():
        return None
    out = defaultdict(list)
    for it in json.loads(ev.read_text())["items"]:
        if it["kind"] == "pad":
            out[it["ref"].rsplit(".", 1)[0]].append((box(*it["box"]), it["net"], it["layers"]))
    return out


def load(dump_path: Path):
    d = json.loads(dump_path.read_text())
    ev = None
    items = []  # (geom, net, layer, ref, label)
    for z in d["zones"]:
        items.append((Polygon(z["pts"], z["holes"]).buffer(0), z["net"], z["layer"], None, "pour"))
    for t in d["tracks"]:
        items.append((LineString([t["a"], t["b"]]).buffer(t["w"] / 2), t["net"], t["layer"], None, "track"))
    for v in d["vias"]:
        g = Point(*v["at"]).buffer(v["d"] / 2)
        for lay in CU:
            items.append((g, v["net"], lay, None, "via"))
    for p in d["pads"]:
        if not p["net"]:
            continue
        g = Polygon(p["pts"]).buffer(0)
        if "layers" in p:
            lays = [lay for lay in p["layers"] if lay in CU]
        elif p["tht"]:
            lays = list(CU)
        else:
            if ev is None:
                ev = pad_layers_from_evidence(dump_path)
                if ev is None:
                    raise SystemExit("dump has no pad layers and no evidence.json beside it")
            c = g.representative_point()
            hits = [lays for b, n, lays in ev[p["ref"]] if n == p["net"] and b.buffer(0.01).contains(c)]
            if not hits:
                raise SystemExit(f"no evidence pad for {p['ref']} {p['net']}")
            lays = hits[0]
        for lay in lays:
            items.append((g, p["net"], lay, p["ref"], "pad"))
    return d, items


def measure(dump_path: Path):
    d, items = load(dump_path)
    j5 = [p for p in d["pads"] if p["ref"] == "J5" and p["net"] == "res_a"]
    if j5:
        xs = [c for p in j5 for c in p["pts"]]
        cx = (min(x for x, _ in xs) + max(x for x, _ in xs)) / 2
        cy = (min(y for _, y in xs) + max(y for _, y in xs)) / 2
        items.append((Point(cx, cy).buffer(J5_LUG_R), "res_a", "F.Cu", "J5", "J5 ring lug (r 5.0)"))
    barrier = [i for i in items if rules21.domain(i[1]) in ("SELV", "PE")]
    pairs = {}
    for g, n, lay, ref, lab in items:
        if n not in HV and n not in REPORT_ALSO:
            continue
        for h, m, lay2, ref2, lab2 in barrier:
            if lay2 != lay or (ref and ref == ref2 and lab == lab2 == "pad"):
                continue
            dist = g.distance(h)
            key = (lay, n, m)
            if key not in pairs or dist < pairs[key]["mm"]:
                a, b = nearest_points(g, h)
                pairs[key] = {"layer": lay, "hv_net": n, "barrier_net": m, "domain": rules21.domain(m),
                              "mm": round(dist, 3), "hv_item": lab, "barrier_item": lab2,
                              "at_hv": [round(a.x, 2), round(a.y, 2)], "at_barrier": [round(b.x, 2), round(b.y, 2)]}
    rows = sorted(pairs.values(), key=lambda r: (r["layer"] not in OUTER, r["hv_net"] not in HV, r["mm"]))
    for r in rows:
        floor = FLOOR if r["hv_net"] in HV | GUARD else rules21.BARRIER
        r["floor_mm"] = floor
        r["gated"] = r["layer"] in OUTER and r["hv_net"] in HV | GUARD
        r["pass"] = r["mm"] >= floor - 1e-3
    return rows


def summarize(rows):
    print(f"RES_A ({'/'.join(sorted(HV))}) to SELV/PE, floor {FLOOR} mm on outer layers")
    for lay in CU:
        sub = [r for r in rows if r["layer"] == lay and r["hv_net"] in HV]
        kind = "outer, gated" if lay in OUTER else "inner, solid insulation (reported)"
        mn = min((r["mm"] for r in sub), default=None)
        print(f"  {lay} ({kind}): min {mn} mm over {len(sub)} net pairs")
        for r in sub:
            if r["mm"] < 20.0:
                flag = "" if r["pass"] or not r["gated"] else "  < FLOOR"
                print(f"    {r['hv_net']} - {r['barrier_net']}: {r['mm']:.3f} mm ({r['hv_item']} {r['at_hv']} / "
                      f"{r['barrier_item']} {r['at_barrier']}){flag}")
    print("other tank nets (crbleed_1 12.6 mm guard, others 8.0 mm), outer-layer minimum per net:")
    for n in REPORT_ALSO:
        sub = [r for r in rows if r["hv_net"] == n and r["layer"] in OUTER]
        if sub:
            r = min(sub, key=lambda r: r["mm"])
            print(f"    {n}: {r['mm']:.3f} mm to {r['barrier_net']} on {r['layer']} {r['at_hv']}")
    return [r for r in rows if r["gated"] and not r["pass"]]


def main():
    args = sys.argv[1:]
    control = "--control" in args
    if control:
        args.remove("--control")
    out = None
    if "--json" in args:
        out = Path(args[args.index("--json") + 1])
        del args[args.index("--json"):args.index("--json") + 2]
    dump = Path(args[0])
    rows = measure(dump)
    bad = summarize(rows)
    if out:
        out.write_text(json.dumps({"dump": str(dump), "floor_mm": FLOOR, "hv_nets": sorted(HV),
                                   "violations": bad,
                                   "pairs_under_25mm": [r for r in rows if r["mm"] < 25.0]}, indent=1) + "\n")
    if control:
        found = {(r["layer"], r["hv_net"], r["barrier_net"]): r["mm"] for r in bad}
        for k, v in CONTROL_17B.items():
            assert k in found and abs(found[k] - v) < 0.01, (k, v, found.get(k))
        assert set(found) == set(CONTROL_17B), found
        print(f"CONTROL PASS: stage-17b gaps reproduced {found}")
        return
    print(f"RES_A outer-layer creepage: {len(bad)} pairs under {FLOOR} mm -> {'FAIL' if bad else 'PASS'}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
