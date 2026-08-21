"""FINAL: are the eight OVP protection pads compliant under the model-E placement?

Per pad, per counterparty bucket, at exact Minkowski copper-to-copper distance
(temper_placer.core.pad_geometry.pad_pair_distance -- no polygon approximation).

Three buckets, because a pad pair can clear one figure and not another:

  HV*   counterparty netclass in {HighVoltage, HighVoltageSignal,
        HighVoltageTank, HighVoltageIsolated, ACMains, GateDriveHV}
        -> FUNCTIONAL insulation. Bar = netclass_rules.yaml HighVoltage
           clearance 2.0mm. pair_creepage projection charges 0.0 (no
           creepage backstop for HV<->HV).
  LV    counterparty netclass in {Power, Default, FinePitch, Signal, ...}
        -> pair_creepage.generated.yaml charges 20.0mm, but ONLY because
           tank-out shares the HighVoltage class. Reported, not endorsed.
  SELV  counterparty declared in elec/domain_manifest.yaml's SELV domain
        -> this is the barrier crossing. The per-pairing requirement is
           NOT DERIVABLE: all four OVP nets are undeclared in
           elec/insulation_manifest.yaml and requirement_for_nets RAISES.

Also flags intra-package (same footprint) vs inter-component, because
intra-package pad distance is invariant under everything a placer can decide.

Read-only with respect to pcb/temper.kicad_pcb.
"""
from __future__ import annotations

import argparse
import json
import math
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
HV_CLASSES = {"HighVoltage", "HighVoltageSignal", "HighVoltageTank",
              "HighVoltageIsolated", "ACMains", "GateDriveHV"}
FUNCTIONAL_CLEARANCE_MM = 2.0  # netclass_rules.yaml HighVoltage.clearance
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
            lay = getattr(pin, "layer", None)
            lay = None if lay in ("*.Cu", "*", None) else frozenset([lay])
            out.append((comp.ref, pin.number, pin.net, geom, lay))
    return out


def shares_layer(a, b):
    return True if (a is None or b is None) else bool(a & b)


def bucket_of(net, cls, selv_nets):
    if net in selv_nets:
        return "SELV"
    return "HV*" if cls.get(net) in HV_CLASSES else "LV"


def scan(pads, cls, selv_nets):
    ovp = sorted((p for p in pads if p[2] in OVP_NETS), key=lambda p: p[0])
    others = [p for p in pads if p[2] not in OVP_NETS]
    rows = {}
    for ref, num, net, geom, lay in ovp:
        best = {}
        for r2, n2, net2, g2, l2 in others:
            if net2 == net or not net2 or not shares_layer(lay, l2):
                continue
            gap = pad_pair_distance(geom, g2)
            b = bucket_of(net2, cls, selv_nets)
            rec = (gap, f"{r2}.{n2}", net2, cls.get(net2, "-"), r2 == ref)
            if b not in best or gap < best[b][0]:
                best[b] = rec
            # SELV members are also netclass-bucketed; keep both views
            if b == "SELV":
                b2 = "HV*" if cls.get(net2) in HV_CLASSES else "LV"
                if b2 not in best or gap < best[b2][0]:
                    best[b2] = rec
        rows[f"{ref}.{num}"] = (net, best)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--placement", type=Path, required=True)
    args = ap.parse_args()

    parsed = parse_kicad_pcb(Path("pcb/temper.kicad_pcb"))
    comps = parsed.netlist.components
    _hv, selv_nets = load_domain_manifest_nets(Path("elec/domain_manifest.yaml"))
    dr = create_temper_design_rules()
    table = load_pair_creepage_table(
        Path("packages/temper-placer/configs/pair_creepage.generated.yaml"))

    data = json.loads(args.placement.read_text())
    pos = {k: tuple(v) for k, v in data["positions"].items()}
    rot = {k: int(v) for k, v in data.get("rotations", {}).items()}
    prov = data.get("provenance", {})

    before = world_pads(comps, {}, {})
    after = world_pads(comps, pos, rot)
    cls = {p[2]: net_class_of(p[2], dr) for p in before}

    print("=" * 118)
    print("WHICH FIGURE APPLIES TO THE FOUR OVP NETS")
    print("=" * 118)
    for n in sorted(OVP_NETS):
        try:
            ic.requirement_for_nets(n, "gnd")
            verdict = "derivable"
        except Exception as e:
            verdict = f"NOT DERIVABLE ({type(e).__name__})"
        print(f"  {n:28s} netclass(TableA)={cls[n]:12s} "
              f"in_manifest_SELV={n in selv_nets}  per-pairing: {verdict}")
    print(f"\n  pair_creepage projection: HighVoltage<->HighVoltage = "
          f"{table.required('HighVoltage', 'HighVoltage'):.1f} mm  "
          f"HighVoltage<->Power = {table.required('HighVoltage', 'Power'):.1f} mm")
    print(f"  netclass_rules.yaml HighVoltage.clearance = {FUNCTIONAL_CLEARANCE_MM} mm "
          f"(FUNCTIONAL; the only bar that applies to an HV<->HV pair)")

    b_rows = scan(before, cls, selv_nets)
    a_rows = scan(after, cls, selv_nets)

    print(f"\nplacement: status={prov.get('status')} "
          f"relaxed={prov.get('relaxed_isolator_straddle')} seed={prov.get('seed')}")

    for bucket, bar, barname in (
        ("HV*", FUNCTIONAL_CLEARANCE_MM, "2.0mm functional clearance (HV<->HV)"),
        ("SELV", None, "per-pairing barrier figure -- NOT DERIVABLE"),
        ("LV", 20.0, "20.0mm from the HighVoltage netclass projection (tank-contaminated)"),
    ):
        print("\n" + "=" * 118)
        print(f"BUCKET {bucket}  --  bar: {barname}")
        print("=" * 118)
        hdr = (f"{'pad':8} {'OVP net':26} {'committed':>10} {'counterparty':>26} "
               f"{'model-E':>9} {'counterparty':>26} {'intra?':>7}  verdict")
        print(hdr)
        print("-" * len(hdr))
        nb = na = 0
        for pad in sorted(b_rows, key=lambda k: (int(k.split('.')[0][1:]), k)):
            net, bb = b_rows[pad]
            _n, ab = a_rows[pad]
            if bucket not in bb and bucket not in ab:
                continue
            gb, idb = (bb[bucket][0], bb[bucket][2]) if bucket in bb else (float("inf"), "-")
            ga, ida, intra = ((ab[bucket][0], ab[bucket][2], ab[bucket][4])
                              if bucket in ab else (float("inf"), "-", False))
            if bar is None:
                v = "INDETERMINATE (no requirement exists)"
            else:
                nb += gb < bar
                na += ga < bar
                v = ("PASS" if ga >= bar else
                     "FAIL" + ("  [INTRA-PACKAGE]" if intra else "  [inter-component]"))
            print(f"{pad:8} {net:26} {gb:10.4f} {idb:>26} {ga:9.4f} {ida:>26} "
                  f"{str(intra):>7}  {v}")
        if bar is not None:
            print(f"\n  pads below {bar} mm:  committed {nb}/8   model-E {na}/8")


if __name__ == "__main__":
    main()
