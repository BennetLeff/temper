"""Attribute every residual violation in the solved placement to a cause:
INTRA-PACKAGE (no placement fixes it) or INTER-COMPONENT (a placement could).

Also cross-checks the barrier model's own pad geometry against the exact
copper-to-copper kernel, because the two disagree on this board and the
direction of the disagreement matters: `isolation_barrier.py` models a pad as
width/height/shape at a local offset and does NOT apply the pad's own
`(at x y ANGLE)` rotation, while `core.pad_geometry.pad_pair_distance` does.
For a footprint whose pads are individually rotated, the barrier model is
therefore OPTIMISTIC -- it can report a package as spanning a figure that its
real copper does not span.

Read-only. Run from the repo root:

    python docs/evidence/2026-08-19-per-pairing-residual-attribution.py \\
        --placement /path/to/placement.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

import temper_placer.core.insulation_coordination as ic
from temper_placer.core.pad_geometry import pad_pair_distance
from temper_placer.core.pin_geometry import pin_world_position_at
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.placer.cp_sat.isolation_barrier import (
    barrier_setbacks,
    evaluate_isolator_per_pairing,
    load_domain_manifest_nets,
)

REPO = Path(__file__).resolve().parent.parent.parent
MANIFEST = REPO / "elec/domain_manifest.yaml"


def wtup(pin, comp, pos, rot):
    x, y = pin_world_position_at(pin, comp, pos, rot)
    return (
        pin.width,
        pin.height,
        pin.shape or "rect",
        x,
        y,
        math.radians(getattr(pin, "pad_rotation_deg", 0.0) or 0.0),
        getattr(pin, "roundrect_ratio", None) or 0.25,
    )


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--placement", type=Path, required=True)
    ap.add_argument("--board", type=Path, default=REPO / "pcb/temper.kicad_pcb")
    args = ap.parse_args(argv[1:])

    payload = json.loads(args.placement.read_text(encoding="utf-8"))
    positions = {k: tuple(v) for k, v in payload["positions"].items()}
    rotations = {k: int(v) for k, v in payload.get("rotations", {}).items()}

    parsed = parse_kicad_pcb(args.board)
    comps = parsed.netlist.components
    hv_nets, selv_nets = load_domain_manifest_nets(MANIFEST)
    setbacks = barrier_setbacks()

    hv, selv = [], []
    for comp in comps:
        pos = positions.get(comp.ref)
        rot = rotations.get(comp.ref)
        for pin in comp.pins:
            entry = (comp.ref, pin, wtup(pin, comp, tuple(pos) if pos else None, rot))
            if pin.net in hv_nets:
                hv.append(entry)
            elif pin.net in selv_nets:
                selv.append(entry)

    print("=" * 78)
    print("RESIDUAL BELOW-FLOOR HV<->SELV PAD PAIRS IN THE SOLVED PLACEMENT")
    print("=" * 78)
    intra = Counter()
    inter = Counter()
    rows = []
    for ra, pa, ta in hv:
        for rb, pb, tb in selv:
            pairing = ic.requirement_for_nets(pa.net, pb.net)
            if pairing.grade(pad_pair_distance(ta, tb)) != "FAIL":
                continue
            gap = pad_pair_distance(ta, tb)
            kind = "INTRA-PACKAGE" if ra == rb else "inter-component"
            (intra if ra == rb else inter)[pairing.key()] += 1
            rows.append((pairing.key(), ra, pa.number, pa.net, rb, pb.number, pb.net, gap,
                         pairing.enforceable_floor_mm(), kind))
    hdr = (f"{'pairing':18} {'HV pad':14} {'SELV pad':14} {'gap':>7} {'floor':>7} "
           f"{'short':>7}  cause")
    print(hdr)
    print("-" * len(hdr))
    for key, ra, na, neta, rb, nb, netb, gap, floor, kind in sorted(rows):
        print(f"{key:18} {ra + '.' + str(na):14} {rb + '.' + str(nb):14} "
              f"{gap:7.3f} {floor:7.2f} {floor - gap:7.3f}  {kind}")
    print("-" * len(hdr))
    print(f"total {len(rows)}:  intra-package {sum(intra.values())} "
          f"(UNFIXABLE by placement), inter-component {sum(inter.values())}")
    for key in sorted(set(intra) | set(inter)):
        print(f"  {key:20} intra {intra.get(key, 0):3d}   inter {inter.get(key, 0):3d}")

    print()
    print("=" * 78)
    print("BARRIER MODEL vs EXACT COPPER KERNEL, per isolator")
    print("=" * 78)
    print("The barrier model omits each pad's own `(at .. ANGLE)` rotation; the")
    print("kernel applies it. Where they differ the barrier model is OPTIMISTIC.")
    print()
    hdr2 = (f"{'ref':5} {'group':10} {'floor':>7} {'barrier gap':>12} "
            f"{'exact min gap':>14} {'delta':>8}  exact verdict")
    print(hdr2)
    print("-" * len(hdr2))
    comp_by_ref = {c.ref: c for c in comps}
    for ref in sorted({r for r, _p, _t in hv} & {r for r, _p, _t in selv}):
        comp = comp_by_ref[ref]
        feas, _i, _s = evaluate_isolator_per_pairing(comp, hv_nets, selv_nets, setbacks)
        # Exact minimum over this package's own HV x SELV pad pairs, in world
        # coordinates at the SOLVED placement (an intra-package distance is
        # placement-invariant, so the value is a package constant either way).
        pos = positions.get(ref)
        rot = rotations.get(ref)
        own_hv = [wtup(p, comp, tuple(pos) if pos else None, rot)
                  for p in comp.pins if p.net in hv_nets]
        own_selv = [wtup(p, comp, tuple(pos) if pos else None, rot)
                    for p in comp.pins if p.net in selv_nets]
        exact = min(pad_pair_distance(a, b) for a in own_hv for b in own_selv)
        floor = feas.binding_setback_mm
        verdict = "PASS" if exact >= floor else "FAIL"
        if verdict == "PASS" and not setbacks.determinable.get(feas.binding_group, False):
            verdict = "INDETERMINATE"
        print(f"{ref:5} {feas.binding_group:10} {floor:7.2f} {feas.binding_gap_mm:12.3f} "
              f"{exact:14.3f} {exact - feas.binding_gap_mm:8.3f}  {verdict}")
    print("-" * len(hdr2))
    print("A negative delta means the barrier model over-reported the package's")
    print("real separation and its PASS for that part is not supported by copper.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
