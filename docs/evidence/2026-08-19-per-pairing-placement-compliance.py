"""Per-pairing creepage compliance of a SOLVED placement, against the
committed board, measured two independent ways.

Takes the JSON emitted by ``2026-08-19-per-pairing-placer-solve.py --emit``
and re-runs, on the solved coordinates:

  1. the **class-pair pad census** -- the same net->class resolution, the same
     ``pin_world_position``, the same centre-to-centre distance and the same
     ``PairCreepageTable.required(a, b)`` lookup that
     ``2026-08-19-per-pairing-pad-census-before-after.py`` runs on the
     committed board, where it reports **503** violating pad pairs over 107
     nets. This is what "how many of the 503 does the new placement resolve"
     means, measured identically so the two numbers are comparable.

  2. the **exact HV<->SELV copper-to-copper per-pairing census** -- every HV
     pad against every SELV pad at exact Minkowski-sum copper distance
     (``pad_pair_distance``), graded by each pad pair's OWN pairing
     (``requirement_for_nets``), three-valued. This is section 3 of
     ``2026-08-19-per-pairing-creepage-measure.py``, which reports **36**
     below-floor pairs on the committed board.

Both are run against the committed board FIRST, in the same process, so the
before number is reproduced rather than quoted.

CENTRE-TO-CENTRE IS AN UPPER BOUND on the real copper gap, so census 1's
counts are lower bounds on the real violation count -- the caveat the original
measurement states, carried forward unchanged. Census 2 has no such caveat.

A verdict on any pairing whose requirement is NOT DETERMINABLE is reported as
INDETERMINATE and is never counted as a pass. Two of the four barrier-crossing
pairings are in that state (47 kHz; IEC 60664-4 unobtained).

Read-only: `pcb/temper.kicad_pcb` is parsed, never written.

    python docs/evidence/2026-08-19-per-pairing-placement-compliance.py \\
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
from temper_placer.core.design_rules import create_temper_design_rules
from temper_placer.core.pad_geometry import pad_pair_distance
from temper_placer.core.pin_geometry import pin_world_position_at
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.placer.cp_sat.isolation_barrier import load_domain_manifest_nets
from temper_placer.router_v6.pair_creepage import load_pair_creepage_table, net_class_of

REPO = Path(__file__).resolve().parent.parent.parent
MANIFEST = REPO / "elec/domain_manifest.yaml"


def world_pads(components, positions, rotations):
    """(ref, pin, world_x, world_y) for every netted pad.

    *positions*/*rotations* override the committed placement when they carry
    the ref; a ref they do not carry keeps its committed coordinates. Passing
    two empty dicts therefore measures the committed board -- which is exactly
    how the "before" column below is produced, in this same process, rather
    than quoted from another document.
    """
    out = []
    for comp in components:
        pos = positions.get(comp.ref)
        rot = rotations.get(comp.ref)
        for pin in comp.pins:
            if not pin.net:
                continue
            x, y = pin_world_position_at(
                pin, comp, tuple(pos) if pos else None, rot if rot is not None else None
            )
            out.append((comp.ref, pin, x, y))
    return out


def pad_tuple(pin, x, y):
    return (
        pin.width,
        pin.height,
        pin.shape or "rect",
        x,
        y,
        math.radians(getattr(pin, "pad_rotation_deg", 0.0) or 0.0),
        getattr(pin, "roundrect_ratio", None) or 0.25,
    )


def class_census(table, pads, cls):
    """Census 1 -- centre-to-centre against the net-class projection."""
    pairs = 0
    nets_v: set[str] = set()
    by_class: Counter = Counter()
    offenders: set[tuple[str, str, str, str]] = set()
    n = len(pads)
    for i in range(n):
        _r1, p1, x1, y1 = pads[i]
        for j in range(i + 1, n):
            _r2, p2, x2, y2 = pads[j]
            if p1.net == p2.net:
                continue
            req = table.required(cls[p1.net], cls[p2.net])
            if req <= 0:
                continue
            if math.dist((x1, y1), (x2, y2)) < req:
                pairs += 1
                by_class[tuple(sorted((cls[p1.net], cls[p2.net])))] += 1
                nets_v |= {p1.net, p2.net}
                key = tuple(sorted((f"{_r1}.{p1.number}", f"{_r2}.{p2.number}")))
                offenders.add((key[0], key[1], p1.net, p2.net))
    return pairs, nets_v, by_class, offenders


def pairing_census(pads, hv_nets, selv_nets):
    """Census 2 -- exact copper-to-copper, graded per pairing, three-valued."""
    hv = [(r, p, pad_tuple(p, x, y)) for r, p, x, y in pads if p.net in hv_nets]
    selv = [(r, p, pad_tuple(p, x, y)) for r, p, x, y in pads if p.net in selv_nets]
    per: dict[str, list[int]] = {}
    worst: dict[str, tuple[float, str, str]] = {}
    for _ra, pa, ta in hv:
        for _rb, pb, tb in selv:
            gap = pad_pair_distance(ta, tb)
            pairing = ic.requirement_for_nets(pa.net, pb.net)
            key = pairing.key()
            bucket = per.setdefault(key, [0, 0, 0])
            bucket[0] += 1
            verdict = pairing.grade(gap)
            if verdict == "FAIL":
                bucket[1] += 1
            elif verdict == "INDETERMINATE":
                bucket[2] += 1
            if key not in worst or gap < worst[key][0]:
                worst[key] = (gap, f"{_ra}.{pa.number}", f"{_rb}.{pb.number}")
    return len(hv), len(selv), per, worst


def report_pairing(label, per, worst):
    hdr = (f"{'pairing':22} {'floor':>7} {'det':>6} {'pairs':>8} "
           f"{'FAIL':>7} {'INDET':>8} {'min gap':>9}  closest pad pair")
    print(f"\n{label}")
    print(hdr)
    print("-" * len(hdr))
    tf = ti = tp = 0
    for key in sorted(per):
        total, fail_n, indet_n = per[key]
        a, b = key.split("<->")
        pr = ic._resolution().pairing(a, b)
        g, pa, pb = worst[key]
        print(f"{key:22} {pr.enforceable_floor_mm():7.2f} "
              f"{str(pr.is_determinable()):>6} {total:8d} {fail_n:7d} {indet_n:8d} "
              f"{g:9.3f}  {pa} <-> {pb}")
        tf += fail_n
        ti += indet_n
        tp += total
    print("-" * len(hdr))
    print(f"{'TOTAL':22} {'':7} {'':6} {tp:8d} {tf:7d} {ti:8d}")
    return tf, ti


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--placement", type=Path, required=True)
    ap.add_argument("--board", type=Path, default=REPO / "pcb/temper.kicad_pcb")
    ap.add_argument(
        "--projection",
        type=Path,
        default=REPO / "packages/temper-placer/configs/pair_creepage.generated.yaml",
    )
    args = ap.parse_args(argv[1:])

    payload = json.loads(args.placement.read_text(encoding="utf-8"))
    positions = {k: tuple(v) for k, v in payload["positions"].items()}
    rotations = {k: int(v) for k, v in payload.get("rotations", {}).items()}
    prov = payload.get("provenance", {})
    print(f"placement: {args.placement}")
    print(f"  status = {prov.get('status')}   relaxed = {prov.get('relaxed_isolator_straddle')}")
    print(f"  setbacks = {prov.get('per_pairing_setbacks')}")
    print(f"  all_determinable = {prov.get('all_determinable')}")
    print(f"  {len(positions)} components repositioned\n")

    parsed = parse_kicad_pcb(args.board)
    comps = parsed.netlist.components
    hv_nets, selv_nets = load_domain_manifest_nets(MANIFEST)
    design_rules = create_temper_design_rules()
    table = load_pair_creepage_table(args.projection)

    before_pads = world_pads(comps, {}, {})
    after_pads = world_pads(comps, positions, rotations)
    cls = {p.net: net_class_of(p.net, design_rules) for _r, p, _x, _y in before_pads}
    print(f"{len(before_pads)} netted pads; projection = {args.projection.name}")

    print("\n" + "=" * 78)
    print("CENSUS 1 -- class-pair, centre-to-centre (comparable to the 503 figure)")
    print("=" * 78)
    b_pairs, b_nets, b_by, b_off = class_census(table, before_pads, cls)
    a_pairs, a_nets, a_by, a_off = class_census(table, after_pads, cls)
    print(f"committed board : {b_pairs} violating pad pairs over {len(b_nets)} nets")
    print(f"solved placement: {a_pairs} violating pad pairs over {len(a_nets)} nets")
    resolved = len(b_off - a_off)
    introduced = len(a_off - b_off)
    print(f"\n  resolved   (violating before, clean after): {resolved}")
    print(f"  introduced (clean before, violating after): {introduced}")
    print(f"  net change: {a_pairs - b_pairs:+d}  "
          f"({resolved}/{b_pairs} = {100.0 * resolved / max(b_pairs, 1):.1f}% of the "
          f"before-set resolved)")
    print("\n  per class pair (before -> after):")
    for key in sorted(set(b_by) | set(a_by)):
        b, a = b_by.get(key, 0), a_by.get(key, 0)
        if a == b:
            continue
        print(f"    {key[0]:24} <-> {key[1]:24} {b:5d} -> {a:5d}  "
              f"({'RAISED' if a > b else 'lowered'})")

    print("\n" + "=" * 78)
    print("CENSUS 2 -- exact HV<->SELV copper-to-copper, graded per pairing")
    print("=" * 78)
    nhv, nselv, b_per, b_worst = pairing_census(before_pads, hv_nets, selv_nets)
    _, _, a_per, a_worst = pairing_census(after_pads, hv_nets, selv_nets)
    print(f"HV pads {nhv}  SELV pads {nselv}  pairs {nhv * nselv}")
    bf, bi = report_pairing("COMMITTED BOARD", b_per, b_worst)
    af, ai = report_pairing("SOLVED PLACEMENT", a_per, a_worst)
    print(f"\n  below-floor pairs: {bf} -> {af}  ({af - bf:+d})")
    print(f"  indeterminate    : {bi} -> {ai}  ({ai - bi:+d})")
    print(f"  uncertifiable    : {bf + bi} -> {af + ai}")

    print("\n" + "=" * 78)
    if not prov.get("all_determinable", True):
        print("CONDITIONAL: SELV<->TANK and SELV<->SWITCHING have NO determinable")
        print("requirement (47 kHz > IEC 60664-1 cl.1.1.1's 30 kHz ceiling; cl.2.3")
        print("routes to the unobtained IEC 60664-4). Their figures above are PROVEN")
        print("FLOORS. Clearing them is not compliance and is never graded PASS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
