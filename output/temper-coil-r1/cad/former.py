"""coil-r1 winding former: the R43 former re-cut for the R1 winding, in three build routes (README D6).

  A. CNC former (G11/FR5, 10 mm plate, 2.5D both sides): out/former_R1_cnc.step. R43's former (hub, rim, four lugs, ten
     spokes with bar channels 15.2 x 5.0 x 90.2, 1 mm roof, comb, J2 lead hole, R40 coil-NTC pad on the -41 deg spoke) with
     the comb notches moved to the R1 winding (14.47 inner + 6.46 outer turns) plus ONE SPARE outer turn of notches
     (to r118.1) for tuning up. Notch width = measured bundle OD + 0.2.
  B. Printed former: the same body in five 72 deg segments with half-lapped rim joints and pin holes, out/former_R1_print_seg{1..5}.stl
     (fits a 180 x 180 bed). Notch width = bundle + 0.3 (printed slots close up). Material sets the use limit (README D6).
  C. No printer: see template.py (1:1 drawing for an FR4 roof sheet, pencil marks + spacer cord) - no former body.

Run: .venv/bin/python cad/former.py [--bundle 2.40]   (writes cad/out/, ~1-2 min)
Also writes out/notch_table_R1.csv: every notch (spoke angle, radius, section, turn) - the QC list for any route.
"""
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

from build123d import Compound, Solid, export_step, export_stl

import geom as K
from geom import G

OUT = Path(__file__).resolve().parent / "out"
SEG_BOUNDS = [-59.0 + 72.0 * j for j in range(5)]     # mid-gaps between spokes; clear of the lugs, J2 hole and NTC pad
LAP_DEG = 6.0


def fuse(solids):
    return solids[0].fuse(*solids[1:]) if len(solids) > 1 else solids[0]


def notch_list(w, spare):
    sps = K.spirals(w, spare)
    rows = []
    for phi in G.bar_angles():
        for si, sp in enumerate(sps):
            for k, r in enumerate(K.crossings(sp, phi)):
                spare_flag = si == 1 and r > w.sections[1].r1 + 1e-6
                rows.append(dict(spoke_deg=phi, section="inner" if si == 0 else "outer", crossing=k + 1, r_mm=round(r, 3),
                                 spare=spare_flag))
    return rows


def ntc_pad_and_bore(w, comb_top, zb):
    """R40's coil-NTC mount re-derived for R1: pad on the -41 deg spoke roof in the gap ring, blind bead bore 20 deg off
    tangential with >= 2 mm of former to the last inner turn, Ø2.5 counterbore to the spoke side."""
    inner = K.spirals(w)[0]
    rc = max(K.crossings(inner, K.NTC_PHI))
    pad = K.radial_box(K.NTC_PHI, rc + K.D_LEAD / 2 + 0.05, K.GAP_R[1] - 1.0, K.SPOKE_W, K.Z_ROOF[1] - 0.01, comb_top)
    er = (math.cos(math.radians(K.NTC_PHI)), math.sin(math.radians(K.NTC_PHI)))
    et = (-er[1], er[0])
    a = math.radians(K.NTC_TILT)
    d = (-et[0] * math.cos(a) + er[0] * math.sin(a), -et[1] * math.cos(a) + er[1] * math.sin(a))
    s0 = -K.BEAD_L / 2 - 1.0
    r0 = rc + K.D_LEAD / 2 + K.NTC_WALL + 0.9 - s0 * math.sin(a)
    c = (r0 * er[0], r0 * er[1])
    t0 = c[0] * et[0] + c[1] * et[1]
    s_side = (-K.SPOKE_W / 2 - t0) / (d[0] * et[0] + d[1] * et[1])

    def cyl(sa, sb, rad):
        from build123d import Plane
        p = (c[0] + sa * d[0], c[1] + sa * d[1], zb)
        return Solid.make_cylinder(rad, sb - sa, Plane(origin=p, z_dir=(d[0], d[1], 0.0)))
    bore = cyl(s0, K.BEAD_L / 2 + 0.5, 0.9).fuse(cyl(K.BEAD_L / 2 + 0.5, s_side + 2.0, 1.25))
    return pad, bore, dict(last_inner_turn_r=rc, bead_centre_r=r0, wall_mm=K.NTC_WALL)


def former(w=G.R1, bundle=2.40, clearance=0.2, spare=G.R1_SPARE_OUTER_TURNS, ntc=True):
    comb_top = K.Z_ROOF[1] + bundle + 0.2
    zb = K.Z_ROOF[1] + bundle / 2
    parts = [K.annulus(*K.HUB_R, K.Z_BAR[0], K.Z_ROOF[1]), K.annulus(*K.RIM_R, K.Z_BAR[0], K.RIM_TOP)]
    for a in K.LUG_ANGLES:
        parts.append(K.radial_box(a, K.RIM_R[0] + 0.2, K.LUG_R1, K.LUG_W, 0.0, K.LUG_T))
    sps = K.spirals(w, spare)
    for phi in G.bar_angles():
        r1 = K.RIM_R[0] + 0.5
        walls = K.radial_box(phi, max(K.HUB_R[1] - 0.5, G.BAR_R[0] - 2), r1, K.SPOKE_W, *K.Z_BAR)
        roof = K.radial_box(phi, K.HUB_R[1] - 0.5, r1, K.SPOKE_W, *K.Z_ROOF)
        comb = K.radial_box(phi, K.COMB_R0, K.GAP_R[0], K.COMB_W, K.Z_ROOF[1], comb_top).fuse(
            K.radial_box(phi, K.GAP_R[1], r1, K.COMB_W, K.Z_ROOF[1], comb_top))
        cuts = [K.radial_box(phi, r - bundle / 2 - clearance / 2, r + bundle / 2 + clearance / 2, K.COMB_W + 2,
                             K.Z_ROOF[1] - 0.01, comb_top + 1) for sp in sps for r in K.crossings(sp, phi)]
        parts += [walls, roof, comb.cut(fuse(cuts))]
    body = fuse(parts)
    info = {}
    if ntc:
        pad, bore, info = ntc_pad_and_bore(w, comb_top, zb)
        body = body.fuse(pad)
    channels = [K.radial_box(phi, *K.BAR_CH_R, K.BAR_CH_W, K.Z_BAR[0] - 1, K.Z_BAR[1]) for phi in G.bar_angles()]
    holes = [K.zcyl(*K.P(K.LUG_R, a)[:2], -1, 10, K.LUG_HOLE / 2) for a in K.LUG_ANGLES]
    holes.append(K.zcyl(*K.J2, -1, 20.0, K.D_LEAD / 2 + 1.0))
    body = body.cut(fuse(channels + holes))
    if ntc:
        body = body.cut(bore)
    return body, dict(bundle=bundle, clearance=clearance, comb_top_z_local=comb_top, comb_top_world=comb_top + K.Z0_WORLD,
                      notch_width=bundle + clearance, spare_outer_turns=spare, ntc=info)


def segments(body):
    """Five 72 deg segments, rim half-lapped (lower half of the next segment's rim runs LAP_DEG under this one) with a
    Ø3.2 vertical pin hole (3 mm G10/bamboo pin, not metal) through a local boss at each joint."""
    zmid = K.RIM_TOP / 2
    boss_r = (K.RIM_R[0], 128.5)
    bosses, pins = [], []
    for b in SEG_BOUNDS:
        bosses.append(K.sector(b - LAP_DEG, b + LAP_DEG, boss_r[1], 0.0, K.RIM_TOP) - K.zcyl(0, 0, -1, 20, boss_r[0]))
        pins.append(K.zcyl(*K.P(125.0, b)[:2], -1, 20, 1.6))
    body = body.fuse(fuse(bosses)).cut(fuse(pins))
    segs = []
    n = len(SEG_BOUNDS)
    for j in range(n):
        a0, a1 = SEG_BOUNDS[j], SEG_BOUNDS[(j + 1) % n] + (360.0 if j == n - 1 else 0.0)
        region = K.sector(a0, a1, 140.0, -2.0, 12.0)
        # this segment keeps the lower half of the lap past a1 and gives up the lower half past a0
        lap_hi = K.sector(a1, a1 + LAP_DEG, 140.0, -2.0, zmid) - K.zcyl(0, 0, -3, 20, boss_r[0] - 0.01)
        lap_lo = K.sector(a0, a0 + LAP_DEG, 140.0, -2.0, zmid) - K.zcyl(0, 0, -3, 20, boss_r[0] - 0.01)
        region = region.fuse(lap_hi).cut(lap_lo)
        res = body.intersect(region)
        sol = list(res.solids()) if hasattr(res, "solids") else [x for r in res for x in r.solids()]
        if len(sol) != 1:
            print(f"WARNING segment {j + 1}: {len(sol)} solids (volumes {[round(x.volume) for x in sol]})")
        segs.append(Compound(sol) if len(sol) > 1 else sol[0])
    return segs, body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", type=float, default=2.40, help="MEASURED Litz bundle OD (mm); notch = bundle + clearance")
    a = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    rows = notch_list(G.R1, G.R1_SPARE_OUTER_TURNS)
    with open(OUT / "notch_table_R1.csv", "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)
    cnc, info = former(bundle=a.bundle, clearance=0.2)
    export_step(cnc, str(OUT / "former_R1_cnc.step"))
    export_stl(cnc, str(OUT / "former_R1_cnc.stl"), tolerance=0.05)
    pr, _ = former(bundle=a.bundle, clearance=0.3)
    segs, pr_full = segments(pr)
    vol = 0.0
    for j, s in enumerate(segs):
        export_stl(s, str(OUT / f"former_R1_print_seg{j + 1}.stl"), tolerance=0.05)
        bb = s.bounding_box()
        vol += s.volume
        print(f"segment {j + 1}: {bb.size.X:.1f} x {bb.size.Y:.1f} x {bb.size.Z:.1f} mm, {s.volume / 1e3:.1f} cm3")
    bb = cnc.bounding_box()
    n_in = sum(1 for r in rows if r["section"] == "inner")
    n_out = sum(1 for r in rows if r["section"] == "outer" and not r["spare"])
    n_sp = sum(1 for r in rows if r["spare"])
    print(f"CNC former: {bb.size.X:.1f} x {bb.size.Y:.1f} x {bb.size.Z:.2f} mm, {cnc.volume / 1e3:.1f} cm3; notches inner {n_in}, "
          f"outer {n_out}, spare {n_sp}; printed segments total {vol / 1e3:.1f} cm3 (full printed body {pr_full.volume / 1e3:.1f})")
    print(info)


if __name__ == "__main__":
    main()
