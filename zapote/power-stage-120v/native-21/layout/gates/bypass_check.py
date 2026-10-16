#!/usr/bin/env python3
"""Local-bypass geometry check for the native-21 comparators, Schmitt buffers and rail monitors.

    KiCad-python native-21/layout/gates/bypass_check.py BOARD.kicad_pcb OUT.json

For each IC below, finds the nearest two-pad capacitor that joins the IC's supply net to its return net
and reports the STRAIGHT-LINE pad-centre distances (IC supply pad -> cap supply pad, IC return pad -> cap
return pad). A straight line is a lower bound on the copper loop, not a loop-inductance figure. It also
lists the nearest via on each of those nets, which is how the cap and the IC reach the In1 / In2 planes.
Stage 40 (candidate 30b): for a plane-backed row's (net, mm) pairs only a via that lands in a filled pour of that net
on an inner or back layer counts (a via that only meets tracks is not a plane connection: C161's stage-30 via was one).
Exit status 1 when a limit below is exceeded (PASS/FAIL is per IC); limits are the stage-19 acceptance values
(DECISIONS.md stage 19), not manufacturer numbers: the datasheets say "as close as possible".

Stage 19 (review N1, 2026-10-12): U10 / U11 / U40 were 17-31 mm from the nearest same-supply cap. Their
dedicated 100 nF caps existed in the source but sat in a row at x 41-75 after the ICs moved.
"""
import json
import math
import sys

import pcbnew

# ref, supply pad, return pad, supply-pad limit (mm), return-pad limit (mm, None = the return reaches a plane
# by via instead), plane-backed (net, mm) pairs (the cap's pad on that net must have a same-net via within mm), note.
# Limits are the stage-19 acceptance values (DECISIONS.md stage 19), not manufacturer numbers: the datasheets
# say "as close as possible".
# The In1 v3v3 / In2 selv_gnd pours are 0.5 mm apart; the router (not a hand layout) chose the vias, and the
# 8 mm SELV-HOT floor keeps SELV copper below y 126.7 on this row, so the nearest legal via is up to 3.6 mm away.
SELV = (("v3v3", 4.0), ("selv_gnd", 4.0))
CHECKS = [
    ("U10", "5", "2", 2.0, 4.0, SELV, "TLV3201 layout: 0.1 uF as close as possible to VCC"),
    ("U11", "5", "2", 2.0, 4.0, SELV, "TLV3201"),
    ("U12", "5", "2", 2.0, 4.0, SELV, "TLV3201 (CT zero-cross)"),
    ("U13", "5", "2", 3.0, 4.0, SELV, "SN74LVC1G332 (fault OR): mid-column supply pin"),
    ("U24", "5", "3", 2.0, 4.0, SELV, "SN74LVC1G17 s.8.3: 0.1 uF 'as close to the power pin as possible'"),
    ("U40", "5", "3", 2.0, 4.0, SELV, "SN74LVC1G17 s.8.3 (heartbeat hold-node Schmitt, stage 30)"),
    # stage 30 (DECISIONS 33): the heartbeat NAND and oscillator, both sides of the HS-A link and (stage 40, candidate
    # 30a) of HS-B's ISO6721FB link, U44, which replaced the HS-B -> SELV verdict isolator.
    # Limits are the stage-30 placement (validation-results/08-manufacturing-package/native-21/stage30-heartbeat/
    # spot_scan.py: nearest legal 0603 to each supply pin; U44 / C159 / C160 keep U34 / C141 / C142's stage-29 poses),
    # not manufacturer numbers; the datasheets say "as close as possible".
    ("U46", "5", "3", 2.0, 4.0, SELV, "SN74LVC1G132 (heartbeat NAND; A on PERMIT through R135 100 k since stage 50, v3v3 stage 40-49)"),
    # U45: until stage 40 C161's n_ls pad had no pour under it on any layer (monitor_ls-ref on F, vsense_in on In1,
    # ocp_kelvin_p on In2 and bus_fault_hot on B wall its pocket), and the limit was its measured 6.0 mm (DECISIONS 33).
    # Stage 40 (candidate 30b): the In1 n_ls LS-block plane reaches into the pocket and C161's own n_ls via at
    # (99.5, 95.035) lands in it, 0.4 mm from the pad: the standard 3.0 mm plane-backed limit applies.
    ("U45", "5", "3", 3.0, None, (("n_ls", 3.0),), "SN74LVC1G132 (heartbeat oscillator); its return reaches the In1 "
     "n_ls plane by C161's via"),
    ("U43", "1", "4", 3.0, 3.0, (), "ISO6721FB VCC1 / GND1 (HS-A monitor 5 V)"),
    ("U43", "8", "5", 3.5, 3.0, (), "ISO6721FB VCC2 / GND2 (ls_v5)"),
    ("U44", "1", "4", 3.0, 3.0, (), "ISO6721FB VCC1 / GND1 (HS-B monitor 5 V)"),
    ("U44", "8", "5", 3.0, 3.0, (), "ISO6721FB VCC2 / GND2 (ls_v5)"),
    ("U15", "5", "3", 4.5, 6.0, (("ocp_kelvin_p", 6.5),), "SN74LVC1G17 s.8.3 (hot5 / ocp_kelvin_p, HOT domain; dense block, 4.4 mm is the closest legal spot)"),
    ("U29", "3", "12", 2.5, None, (("n_ls", 6.5),), "LM339B s.8.4.1: bypass between supply and ground (v15_ls / n_ls)"),
    ("U30", "3", "12", 2.5, None, (("n_ha", 6.0),), "LM339B (p_ha / n_ha)"),
    ("U31", "3", "12", 4.5, None, (("n_hb", 4.5),), "LM339B (p_hb / n_hb); board edge leaves no room beside pin 3"),
]


def mm(v):
    return pcbnew.ToMM(v)


def pos(p):
    c = p.GetPosition()
    return (mm(c.x), mm(c.y))


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def main():
    board = pcbnew.LoadBoard(sys.argv[1])
    fps = {f.GetReference(): f for f in board.GetFootprints()}
    vias = [(t.GetNetname(), pos(t)) for t in board.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]
    pours = {}
    for z in board.Zones():
        for lay in z.GetLayerSet().Seq():
            if lay != pcbnew.F_Cu and pcbnew.IsCopperLayer(lay):
                pours.setdefault(z.GetNetname(), []).append((z, lay))

    def on_plane(net, xy):
        at = pcbnew.VECTOR2I(pcbnew.FromMM(xy[0]), pcbnew.FromMM(xy[1]))
        return any(z.HitTestFilledArea(lay, at, pcbnew.FromMM(0.31)) for z, lay in pours.get(net, ()))
    caps = []
    for ref, f in fps.items():
        pads = list(f.Pads())
        if ref.startswith("C") and len(pads) == 2:
            caps.append((ref, {p.GetNetname(): pos(p) for p in pads}))
    out, ok = {}, True
    for ref, sp, rp, lim_s, lim_r, planes, note in CHECKS:
        pads = {p.GetNumber(): p for p in fps[ref].Pads()}
        sn, rn = pads[sp].GetNetname(), pads[rp].GetNetname()
        sxy, rxy = pos(pads[sp]), pos(pads[rp])
        best = None
        for cref, cn in caps:
            if set(cn) == {sn, rn}:
                d = (dist(sxy, cn[sn]), dist(rxy, cn[rn]))
                key = d[0] + (d[1] if lim_r else 0.0)
                if best is None or key < best[0]:
                    best = (key, cref, d, cn)
        row = {"supply_net": sn, "return_net": rn, "ic_supply_pad": [round(c, 3) for c in sxy],
               "ic_return_pad": [round(c, 3) for c in rxy], "limit_supply_mm": lim_s, "limit_return_mm": lim_r,
               "datasheet": note, "nearest_cap": None}
        good = False
        if best is not None:
            _, cref, d, cn = best
            via = {}
            backed = {n for n, _ in planes}
            for n in (sn, rn):
                v = min(((dist(cn[n], vv), tuple(round(c, 3) for c in vv)) for nn, vv in vias
                         if nn == n and (n not in backed or on_plane(n, vv))), default=None)
                via[n] = None if v is None else {"mm": round(v[0], 2), "at": v[1]}
            row["nearest_cap"] = {"ref": cref, "supply_pad_to_pad_mm": round(d[0], 2),
                                  "return_pad_to_pad_mm": round(d[1], 2),
                                  "same_net_via_to_cap_pad_mm": via}
            good = d[0] <= lim_s and (lim_r is None or d[1] <= lim_r) and \
                all(via[n] is not None and via[n]["mm"] <= lim for n, lim in planes)
        row["pass"] = good
        ok &= good
        out[ref if sum(c[0] == ref for c in CHECKS) == 1 else f"{ref}.{sp}"] = row   # two-supply parts: one row per side
        c = row["nearest_cap"]
        print(f"{ref}: {sn}/{rn} nearest cap "
              + ("none" if c is None else f"{c['ref']} supply {c['supply_pad_to_pad_mm']:.2f} return "
                 f"{c['return_pad_to_pad_mm']:.2f} mm, plane vias {{"
                 + ", ".join(f"{n}: {v['mm'] if v else None}" for n, v in c['same_net_via_to_cap_pad_mm'].items()) + "}")
              + f" (limits {lim_s}/{lim_r}) {'PASS' if good else 'FAIL'}")
    json.dump({"board": sys.argv[1], "checks": out, "all_pass": ok},
              open(sys.argv[2], "w"), indent=1)
    sys.exit(0 if ok else 1)


main()
