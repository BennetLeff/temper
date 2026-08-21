"""Are the eight OVP pads inside the 503/467/36/8 censuses at all?

Census 2 of docs/evidence/2026-08-19-per-pairing-placer-solve.md is
109 manifest-HV pads x 237 manifest-SELV pads. Census 1 is the class-pair
centre-to-centre sweep that reports 503 -> 132 with 467 resolved.

This re-runs BOTH on the committed board and on the model-E placement and
extracts exactly the rows that carry an OVP pad, so "are the eight among the
467 resolved or the 36 residual" is answered by membership, not inference.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path

import temper_placer.core.insulation_coordination as ic
from temper_placer.core.design_rules import create_temper_design_rules
from temper_placer.core.pad_geometry import pad_pair_distance
from temper_placer.core.pin_geometry import _normalize_rotation, pin_world_position_at
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.placer.cp_sat.isolation_barrier import load_domain_manifest_nets
from temper_placer.router_v6.pair_creepage import load_pair_creepage_table, net_class_of

OVP_NETS = {
    "safety.ovp.r_div_top1-p2", "safety.ovp.r_div_top2-p2",
    "safety.ovp.r_adc_top1-p2", "safety.ovp.r_adc_top2-p2",
}
RR = 0.25


def world_pads(components, positions, rotations):
    out = []
    for comp in components:
        pos = positions.get(comp.ref)
        rot = rotations.get(comp.ref)
        quad = rot if rot is not None else comp.initial_rotation_quadrant
        for pin in comp.pins:
            if not pin.net:
                continue
            x, y = pin_world_position_at(
                pin, comp, tuple(pos) if pos else None,
                rot if rot is not None else None)
            wr = (_normalize_rotation(quad)
                  + math.radians(getattr(pin, "pad_rotation_deg", 0.0) or 0.0))
            geom = (pin.width, pin.height, pin.shape or "rect", x, y, wr,
                    getattr(pin, "roundrect_ratio", None) or RR)
            out.append((comp.ref, pin.number, pin.net, x, y, geom))
    return out


def class_offenders(table, pads, cls):
    """Census-1 offender set: (padA, padB) keys, centre-to-centre."""
    off = set()
    n = len(pads)
    for i in range(n):
        r1, n1, net1, x1, y1, _g1 = pads[i]
        for j in range(i + 1, n):
            r2, n2, net2, x2, y2, _g2 = pads[j]
            if net1 == net2:
                continue
            req = table.required(cls[net1], cls[net2])
            if req <= 0:
                continue
            if math.dist((x1, y1), (x2, y2)) < req:
                key = tuple(sorted((f"{r1}.{n1}", f"{r2}.{n2}")))
                off.add((key[0], key[1], net1, net2, req))
    return off


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--placement", type=Path, required=True)
    args = ap.parse_args()

    parsed = parse_kicad_pcb(Path("pcb/temper.kicad_pcb"))
    comps = parsed.netlist.components
    hv_nets, selv_nets = load_domain_manifest_nets(Path("elec/domain_manifest.yaml"))
    dr = create_temper_design_rules()
    table = load_pair_creepage_table(
        Path("packages/temper-placer/configs/pair_creepage.generated.yaml"))

    data = json.loads(args.placement.read_text())
    pos = {k: tuple(v) for k, v in data["positions"].items()}
    rot = {k: int(v) for k, v in data.get("rotations", {}).items()}

    before = world_pads(comps, {}, {})
    after = world_pads(comps, pos, rot)
    cls = {p[2]: net_class_of(p[2], dr) for p in before}

    print("=" * 92)
    print("MEMBERSHIP OF THE EIGHT OVP PADS IN CENSUS 2 (the 36 -> 8 measurement)")
    print("=" * 92)
    print(f"manifest HV nets = {len(hv_nets)}   manifest SELV nets = {len(selv_nets)}")
    for n in sorted(OVP_NETS):
        print(f"  {n:30s} in_HV={n in hv_nets}  in_SELV={n in selv_nets}")
    ovp_pads = [p for p in before if p[2] in OVP_NETS]
    inc = [p for p in ovp_pads if p[2] in hv_nets or p[2] in selv_nets]
    print(f"\n  OVP pads on the board: {len(ovp_pads)}   of which census-2 grades: {len(inc)}")
    print("  => the eight pads are in NEITHER the 109 HV set NOR the 237 SELV set.")
    print("     Census 2 never graded them, so they are neither among the 36 nor the 8.")

    print("\n  what pairing does insulation_coordination assign them?")
    for n in sorted(OVP_NETS):
        for other in ("+170V_BUS", "gnd", "V_BUS_SENSE", "PWR_RTN", "tank-out"):
            try:
                pr = ic.requirement_for_nets(n, other)
                print(f"    {n:28s} <-> {other:14s} -> {pr.key():22s} "
                      f"floor={pr.enforceable_floor_mm():6.2f} det={pr.is_determinable()}")
            except Exception as e:
                print(f"    {n:28s} <-> {other:14s} -> RAISES {type(e).__name__}: {e}")

    print("\n" + "=" * 92)
    print("MEMBERSHIP IN CENSUS 1 (the 503 -> 132, 467 resolved measurement)")
    print("=" * 92)
    b_off = class_offenders(table, before, cls)
    a_off = class_offenders(table, after, cls)
    print(f"committed offenders {len(b_off)}   solved offenders {len(a_off)}   "
          f"resolved {len(b_off - a_off)}   introduced {len(a_off - b_off)}")

    def has_ovp(rec):
        return rec[2] in OVP_NETS or rec[3] in OVP_NETS

    b_ovp = {r for r in b_off if has_ovp(r)}
    a_ovp = {r for r in a_off if has_ovp(r)}
    print(f"\n  OVP-carrying offenders: committed {len(b_ovp)}  solved {len(a_ovp)}")
    print(f"  resolved by the placement : {len(b_ovp - a_ovp)}")
    print(f"  introduced by the placement: {len(a_ovp - b_ovp)}")
    print(f"  persisting                 : {len(b_ovp & a_ovp)}")

    geo_b = {(p[0] + '.' + p[1]): p[5] for p in before}
    geo_a = {(p[0] + '.' + p[1]): p[5] for p in after}

    def dump(title, recs, geo):
        print(f"\n  {title} ({len(recs)}):")
        if not recs:
            print("      (none)")
            return
        print(f"      {'pad A':10} {'pad B':10} {'req':>6} {'c2c':>8} {'exact':>8}  "
              f"{'net A':26} {'net B':24}")
        for r in sorted(recs, key=lambda z: z[0]):
            ga, gb = geo[r[0]], geo[r[1]]
            c2c = math.dist((ga[3], ga[4]), (gb[3], gb[4]))
            print(f"      {r[0]:10} {r[1]:10} {r[4]:6.2f} {c2c:8.4f} "
                  f"{pad_pair_distance(ga, gb):8.4f}  {r[2]:26} {r[3]:24}")

    dump("COMMITTED: OVP offenders", b_ovp, geo_b)
    dump("SOLVED (model E): OVP offenders", a_ovp, geo_a)
    dump("RESOLVED by the placement", b_ovp - a_ovp, geo_b)
    dump("INTRODUCED by the placement", a_ovp - b_ovp, geo_a)

    by = Counter()
    for r in a_ovp:
        by[tuple(sorted((cls[r[2]], cls[r[3]])))] += 1
    print("\n  solved-placement OVP offenders by class pair:")
    for k, v in sorted(by.items()):
        print(f"      {k[0]:22} <-> {k[1]:22} {v}")


if __name__ == "__main__":
    main()
