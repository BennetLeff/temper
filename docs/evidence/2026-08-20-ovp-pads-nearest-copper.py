"""Exact copper-to-copper separation of the eight OVP protection pads.

Measures each of the eight pads on the four OVP-01 mid-chain protection nets
  safety.ovp.r_div_top1-p2, r_div_top2-p2, r_adc_top1-p2, r_adc_top2-p2
against EVERY foreign copper item on the board (pads, vias, track segments),
at exact Minkowski copper-to-copper distance (pad_pair_distance), on the
committed placement and on a solved placement JSON.

Geometry, all exact -- no polygon approximation anywhere:
  pad     -> (w, h, shape, cx, cy, rot_rad, rr)                as parsed
  via     -> (d, d, 'circle', x, y, 0, rr)                     circle = pt (+) D_(d/2)
  segment -> (L+W, W, 'oval', mx, my, atan2, rr)               stadium = seg (+) D_(W/2)
              (pad_core_half_extents(L+W, W, 'oval') == (L/2, 0), verified)

Read-only with respect to pcb/temper.kicad_pcb.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from temper_placer.core.design_rules import create_temper_design_rules
from temper_placer.core.pad_geometry import pad_pair_distance
from temper_placer.core.pin_geometry import _normalize_rotation, pin_world_position_at
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.placer.cp_sat.isolation_barrier import load_domain_manifest_nets
from temper_placer.router_v6.pair_creepage import load_pair_creepage_table, net_class_of

OVP_NETS = [
    "safety.ovp.r_div_top1-p2",
    "safety.ovp.r_div_top2-p2",
    "safety.ovp.r_adc_top1-p2",
    "safety.ovp.r_adc_top2-p2",
]
RR = 0.25


def layers_of(tok):
    if tok in ("*.Cu", "*", None):
        return None  # all copper layers
    return frozenset([tok]) if isinstance(tok, str) else frozenset(tok)


def shares_layer(a, b):
    if a is None or b is None:
        return True
    return bool(a & b)


def pad_tuple(pin, x, y, world_rot_rad):
    """Pad geometry in WORLD frame.

    ``world_rot_rad`` MUST be the pad's total world rotation: the component's
    rotation quadrant composed with the pad's own intrinsic angle. The
    parser stores ``Pin.pad_rotation_deg`` RELATIVE to the footprint (it is
    0.0 for R53's pads even though the board file writes ``(at -1.4625 0
    90)``, because the footprint itself is ``(at ... 90)``), and
    ``pin_world_position_kernel`` rotates pin POSITIONS by the quadrant but
    knows nothing about pad shape. Passing ``pad_rotation_deg`` alone leaves
    the pad rectangle unrotated while its centre moves -- which makes
    intra-package pad distance vary with component rotation, though it is
    provably rotation-invariant. Self-checked below.
    """
    return (
        pin.width, pin.height, pin.shape or "rect", x, y, world_rot_rad,
        getattr(pin, "roundrect_ratio", None) or RR,
    )


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
                rot if rot is not None else None,
            )
            world_rot = (_normalize_rotation(quad)
                         + math.radians(getattr(pin, "pad_rotation_deg", 0.0) or 0.0))
            lay = layers_of(getattr(pin, "layer", None))
            out.append((comp.ref, pin.number, pin.net,
                        pad_tuple(pin, x, y, world_rot), lay))
    return out


def selfcheck_rotation_invariance(comps, positions, rotations):
    """Intra-package pad-pair distance cannot depend on component rotation.

    Rotating a footprint rotates every pad AND every pad position together.
    Any instrument that reports a different intra-package gap before and
    after a re-placement is mis-composing the pad angle. Hard-fails.
    """
    a = {(r, n): g for r, n, _net, g, _l in world_pads(comps, {}, {})}
    b = {(r, n): g for r, n, _net, g, _l in world_pads(comps, positions, rotations)}
    bad = []
    for comp in comps:
        pins = [p for p in comp.pins if p.net]
        for i in range(len(pins)):
            for j in range(i + 1, len(pins)):
                ka = (comp.ref, pins[i].number)
                kb = (comp.ref, pins[j].number)
                if ka not in a or kb not in b:
                    continue
                da = pad_pair_distance(a[ka], a[kb])
                db = pad_pair_distance(b[ka], b[kb])
                if abs(da - db) > 1e-9:
                    bad.append((comp.ref, pins[i].number, pins[j].number, da, db))
    print(f"\nSELF-CHECK intra-package rotation invariance: "
          f"{'PASS' if not bad else f'FAIL ({len(bad)} pairs drift)'}")
    for row in bad[:8]:
        print(f"    {row[0]}.{row[1]}<->{row[0]}.{row[2]}  before={row[3]:.4f} after={row[4]:.4f}")
    return not bad


def routed_items(parsed):
    """(kind, ident, net, geom, layers) for every via and track segment."""
    items = []
    for v in parsed.vias:
        d = v.diameter
        items.append((
            "via", f"via@({v.position[0]:.3f},{v.position[1]:.3f})", v.net,
            (d, d, "circle", v.position[0], v.position[1], 0.0, RR),
            frozenset(v.layers),
        ))
    for i, t in enumerate(parsed.traces):
        (x1, y1), (x2, y2) = t.start, t.end
        L = math.dist((x1, y1), (x2, y2))
        W = t.width
        items.append((
            "trace", f"trk#{i}@{t.layer}", t.net,
            (L + W, W, "oval", (x1 + x2) / 2.0, (y1 + y2) / 2.0,
             math.atan2(y2 - y1, x2 - x1), RR),
            frozenset([t.layer]),
        ))
    return items


def measure(pads, routed, include_routed, hv_nets, selv_nets):
    ovp = [p for p in pads if p[2] in OVP_NETS]
    others = [p for p in pads if p[2] not in OVP_NETS]
    rows = []
    for ref, num, net, geom, lay in sorted(ovp, key=lambda p: (p[2], p[0], p[1])):
        best = None
        per_dom = {}
        cands = [("pad", f"{r2}.{n2}", net2, g2, l2)
                 for r2, n2, net2, g2, l2 in others]
        if include_routed:
            cands += [c for c in routed if c[2] not in OVP_NETS]
        for kind, ident, net2, g2, l2 in cands:
            if net2 == net or not net2:
                continue
            if not shares_layer(lay, l2):
                continue
            gap = pad_pair_distance(geom, g2)
            rec = (gap, kind, ident, net2)
            if best is None or gap < best[0]:
                best = rec
            dom = ("HV" if net2 in hv_nets
                   else "SELV" if net2 in selv_nets else "unclassified")
            if dom not in per_dom or gap < per_dom[dom][0]:
                per_dom[dom] = rec
        rows.append((ref, num, net, best, per_dom))
    return rows


def report(label, rows, hv_nets, selv_nets, cls):
    print("\n" + "=" * 104)
    print(label)
    print("=" * 104)
    hdr = (f"{'pad':10} {'net':28} {'gap mm':>9}  {'kind':6} "
           f"{'nearest foreign item':26} {'its net':24} {'its class':18} dom")
    print(hdr)
    print("-" * len(hdr))
    for ref, num, net, best, _pd in rows:
        gap, kind, ident, net2 = best
        dom = ("HV" if net2 in hv_nets else "SELV" if net2 in selv_nets else "unclf")
        print(f"{ref + '.' + num:10} {net:28} {gap:9.4f}  {kind:6} {ident:26} "
              f"{net2:24} {cls.get(net2, '-'):18} {dom}")
    print("\n  nearest counterparty per domain (gap mm, net):")
    for ref, num, _net, _b, per_dom in rows:
        bits = "   ".join(f"{d}={per_dom[d][0]:.4f} [{per_dom[d][3]}]"
                          for d in sorted(per_dom))
        print(f"    {ref + '.' + num:10} {bits}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--placement", type=Path)
    ap.add_argument("--board", type=Path, default=Path("pcb/temper.kicad_pcb"))
    ap.add_argument(
        "--projection", type=Path,
        default=Path("packages/temper-placer/configs/pair_creepage.generated.yaml"))
    args = ap.parse_args()

    parsed = parse_kicad_pcb(args.board)
    comps = parsed.netlist.components
    hv_nets, selv_nets = load_domain_manifest_nets(Path("elec/domain_manifest.yaml"))
    design_rules = create_temper_design_rules()
    load_pair_creepage_table(args.projection)

    before = world_pads(comps, {}, {})
    cls = {p[2]: net_class_of(p[2], design_rules) for p in before}
    routed = routed_items(parsed)

    print(f"board pads={len(before)}  vias={len(parsed.vias)}  traces={len(parsed.traces)}")
    print("\nOVP net classification:")
    for n in OVP_NETS:
        dom = ("HV" if n in hv_nets else "SELV" if n in selv_nets
               else "NOT IN domain_manifest.yaml")
        print(f"  {n:30s} netclass={cls.get(n, '?'):14s} manifest_domain={dom}")

    configs = [
        ("A. COMMITTED BOARD -- pads + vias + traces (all foreign copper)", before, True),
        ("B. COMMITTED BOARD -- foreign PADS only (placement-determined)", before, False),
    ]
    if args.placement:
        data = json.loads(args.placement.read_text())
        pos = {k: tuple(v) for k, v in data["positions"].items()}
        rot = {k: int(v) for k, v in data.get("rotations", {}).items()}
        prov = data.get("provenance", {})
        print(f"\nplacement: status={prov.get('status')} "
              f"relaxed={prov.get('relaxed_isolator_straddle')} seed={prov.get('seed')}")
        after = world_pads(comps, pos, rot)
        selfcheck_rotation_invariance(comps, pos, rot)
        configs.append(
            ("C. MODEL-E PLACEMENT -- foreign PADS only (placement-determined)",
             after, False))
        configs.append(
            ("D. MODEL-E PLACEMENT -- pads + the committed board's STALE vias/traces "
             "(NOT a valid board; diagnostic only)", after, True))

    for label, pads, inc in configs:
        report(label, measure(pads, routed, inc, hv_nets, selv_nets),
               hv_nets, selv_nets, cls)


if __name__ == "__main__":
    main()
