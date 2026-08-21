"""Census 2 of 2026-08-19-per-pairing-placer-solve.md, recomputed with the
pad's WORLD rotation instead of Pin.pad_rotation_deg alone.

The committed harness builds each pad tuple with
``math.radians(pin.pad_rotation_deg)``. The parser stores that field RELATIVE
to the footprint (0.0 for every 1206 on this board, though the file writes
``(at -1.4625 0 90)`` inside a footprint that is itself ``(at ... 90)``), and
``pin_world_position_at`` rotates pin POSITIONS by the component quadrant
while the pad rectangle stays axis-aligned. The pad's copper is therefore
modelled in the wrong orientation whenever the component is not at quadrant 0.

Falsifiable consequence: intra-package pad distance is provably invariant
under component rotation, so any drift proves the composition is wrong.
Both variants are run and the drift is reported.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import temper_placer.core.insulation_coordination as ic
from temper_placer.core.pad_geometry import pad_pair_distance
from temper_placer.core.pin_geometry import _normalize_rotation, pin_world_position_at
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.placer.cp_sat.isolation_barrier import load_domain_manifest_nets

RR = 0.25


def world_pads(components, positions, rotations, *, compose):
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
            pr = math.radians(getattr(pin, "pad_rotation_deg", 0.0) or 0.0)
            wr = (_normalize_rotation(quad) + pr) if compose else pr
            out.append((comp.ref, pin.number, pin.net,
                        (pin.width, pin.height, pin.shape or "rect", x, y, wr,
                         getattr(pin, "roundrect_ratio", None) or RR)))
    return out


def census(pads, hv_nets, selv_nets):
    hv = [p for p in pads if p[2] in hv_nets]
    selv = [p for p in pads if p[2] in selv_nets]
    per = {}
    worst = {}
    for ra, na, neta, ga in hv:
        for rb, nb, netb, gb in selv:
            gap = pad_pair_distance(ga, gb)
            pr = ic.requirement_for_nets(neta, netb)
            k = pr.key()
            b = per.setdefault(k, [0, 0, 0])
            b[0] += 1
            v = pr.grade(gap)
            if v == "FAIL":
                b[1] += 1
            elif v == "INDETERMINATE":
                b[2] += 1
            if k not in worst or gap < worst[k][0]:
                worst[k] = (gap, f"{ra}.{na}", f"{rb}.{nb}")
    return per, worst


def show(title, per, worst):
    print(f"\n{title}")
    print(f"  {'pairing':22} {'pairs':>7} {'FAIL':>6} {'min gap':>9}  closest")
    tot = 0
    for k in sorted(per):
        t, f, _i = per[k]
        g, a, b = worst[k]
        print(f"  {k:22} {t:7d} {f:6d} {g:9.3f}  {a} <-> {b}")
        tot += f
    print(f"  {'TOTAL FAIL':22} {'':7} {tot:6d}")
    return tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--placement", type=Path, required=True)
    args = ap.parse_args()
    parsed = parse_kicad_pcb(Path("pcb/temper.kicad_pcb"))
    comps = parsed.netlist.components
    hv, selv = load_domain_manifest_nets(Path("elec/domain_manifest.yaml"))
    data = json.loads(args.placement.read_text())
    pos = {k: tuple(v) for k, v in data["positions"].items()}
    rot = {k: int(v) for k, v in data.get("rotations", {}).items()}

    for compose in (False, True):
        tag = ("COMPOSED world rotation (correct)" if compose
               else "pad_rotation_deg ONLY (as the committed harness does)")
        b = world_pads(comps, {}, {}, compose=compose)
        a = world_pads(comps, pos, rot, compose=compose)
        print("\n" + "=" * 88)
        print(tag)
        print("=" * 88)
        # intra-package invariance probe
        gb = {(r, n): g for r, n, _q, g in b}
        ga = {(r, n): g for r, n, _q, g in a}
        drift = 0
        worst_drift = (0.0, None)
        for comp in comps:
            pins = [p for p in comp.pins if p.net]
            for i in range(len(pins)):
                for j in range(i + 1, len(pins)):
                    ka, kb = (comp.ref, pins[i].number), (comp.ref, pins[j].number)
                    if ka not in gb or kb not in gb:
                        continue
                    d = abs(pad_pair_distance(gb[ka], gb[kb])
                            - pad_pair_distance(ga[ka], ga[kb]))
                    if d > 1e-9:
                        drift += 1
                        if d > worst_drift[0]:
                            worst_drift = (d, f"{comp.ref}.{pins[i].number}<->{pins[j].number}")
        print(f"intra-package pairs whose distance DRIFTS under re-placement: {drift}"
              f"   worst drift {worst_drift[0]:.4f} mm ({worst_drift[1]})")
        tb = show("COMMITTED BOARD", *census(b, hv, selv))
        ta = show("MODEL-E PLACEMENT", *census(a, hv, selv))
        print(f"\n  below-floor: {tb} -> {ta}")


if __name__ == "__main__":
    main()
