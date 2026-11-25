"""Printed R1 former (five 72 deg segments): do they make one rigid former? Joint features, what falls on a joint, comb
teeth at the 2.29 mm bundle, and the segment solids themselves.

Checks (all on cad/former.py's geometry at bundle 2.29, print clearance 0.3 and, for reference, CNC 0.2):
  1. what lies on each joint plane: the clearance (mm, at the feature's radius) from every joint to every comb strip,
     notch, bar channel, carrier lug, the J2 lead hole and the coil-NTC pad; and the turns that cross a joint where it
     is roofed (near the hub the spoke roofs of neighbouring spokes merge, r25-31);
  2. joint features: rim half-lap + Ø3.2 pin (r125), hub boss + Ø2.2 pin (r25.5, added 2026-10-21), wall round each pin;
  3. comb teeth: the actual radial tooth between neighbouring notches on every comb strip (and the end teeth), for the
     print and CNC clearances at the 2.29 design bundle and across the assumed measured-OD band;
  4. the segments: one solid each, adjacent segments do not overlap, their volumes add up to the printed body,
     which carrier lugs each one carries, and the platform footprint.
Run: .venv/bin/python -B fit/segments_check.py  -> fit/results/segments.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "cad"))
import former as F  # noqa: E402
import geom as K  # noqa: E402
from geom import G  # noqa: E402

BUNDLE = K.BUNDLE_R1
BAND = (2.15, 2.29, 2.40, 2.45)        # assumed measured-OD band for the unserved bundle (see fit README)
OUT = HERE / "results" / "segments.json"


def angdist(a, b):
    return abs((a - b + 180.0) % 360.0 - 180.0)


def lateral(r, dphi_deg):
    """Distance from a point at radius r, dphi off a radial joint half-plane (from the axis outward), to that half-plane."""
    return r * math.sin(math.radians(dphi_deg)) if dphi_deg < 90.0 else r


def teeth(bundle, clearance):
    rows = F.notch_list(G.R1, G.R1_SPARE_OUTER_TURNS)
    w = bundle + clearance
    out = {"inner": math.inf, "outer": math.inf}
    slivers = []
    for phi in G.bar_angles():
        for sec, (lo, hi) in (("inner", (K.COMB_R0, K.GAP_R[0])), ("outer", (K.GAP_R[1], K.RIM_R[0] + 0.5))):
            rs = sorted(r["r_mm"] for r in rows if r["spoke_deg"] == phi and r["section"] == sec and lo - 2 <= r["r_mm"] <= hi + 2)
            for a, b in zip(rs, rs[1:]):
                out[sec] = min(out[sec], b - a - w)
            # the former cuts end teeth thinner than MIN_END_TOOTH away (former.notch_span): report what is left
            spans = [F.notch_span(x, w / 2, F.MIN_END_TOOTH) for x in rs]
            rs = [(sa + sb) / 2 for sa, sb in spans]
            w_ends = [(spans[0][1] - spans[0][0]), (spans[-1][1] - spans[-1][0])] if spans else [w, w]
            if rs:
                # end teeth: comb left between the first/last notch and the strip end. <= 0 is an open-ended notch (no
                # tooth); the outer strip's far end runs into the rim (r120), so only material past r120 is free there.
                ends = [(lo, rs[0] - w_ends[0] / 2 - lo), (hi, min(hi, K.RIM_R[0]) - (rs[-1] + w_ends[1] / 2))]
                for at, e in ends:
                    if 0 < e < 0.6:
                        slivers.append(dict(spoke_deg=phi, section=sec, strip_end_r=at, tooth_mm=round(e, 3)))
    out = {k: round(v, 3) for k, v in out.items()}
    out["end_slivers_under_0.6mm"] = slivers
    return out


def main():
    res = {}
    bounds = F.SEG_BOUNDS
    spokes = G.bar_angles()
    # 1. what is near each joint
    near = []
    for b in bounds:
        d_spoke = min(angdist(b, s) for s in spokes)
        row = dict(joint_deg=b % 360, nearest_spoke_deg=round(d_spoke, 2))
        row["comb_strip_mm"] = round(min(lateral(r, d_spoke) - K.COMB_W / 2 for r in (K.COMB_R0, K.RIM_R[0])), 2)
        row["bar_channel_mm"] = round(min(lateral(r, d_spoke) - K.BAR_CH_W / 2 for r in K.BAR_CH_R), 2)
        row["spoke_roof_mm_at_r31"] = round(lateral(31.0, d_spoke) - K.SPOKE_W / 2, 2)
        row["roof_merge_radius_mm"] = round(K.SPOKE_W / 2 / math.sin(math.radians(d_spoke)), 2)
        row["lug_mm"] = round(min(lateral(K.LUG_R, angdist(b, a)) - K.LUG_W / 2 for a in K.LUG_ANGLES), 2)
        th_j2 = math.degrees(math.atan2(K.J2[1], K.J2[0]))
        row["J2_hole_mm"] = round(lateral(math.hypot(*K.J2), angdist(b, th_j2)) - (K.D_LEAD / 2 + 1.0), 2)
        row["ntc_pad_mm"] = round(lateral(K.GAP_R[0], angdist(b, K.NTC_PHI)) - K.SPOKE_W / 2, 2)
        near.append(row)
    res["joints"] = near
    res["notches_on_a_joint"] = 0 if all(r["comb_strip_mm"] > 0 for r in near) else "SEE joints"
    res["bars_across_a_joint"] = 0 if all(r["bar_channel_mm"] > 0 for r in near) else "SEE joints"
    sps = K.spirals(G.R1, G.R1_SPARE_OUTER_TURNS)
    roofed = []
    for b in bounds:
        r_merge = K.SPOKE_W / 2 / math.sin(math.radians(min(angdist(b, s) for s in spokes)))
        for sp in sps:
            for r in K.crossings(sp, b):
                if r - BUNDLE / 2 < r_merge:
                    roofed.append(dict(joint_deg=b % 360, r_mm=round(r, 2)))
    res["turns_crossing_a_roofed_joint"] = roofed
    # 2. joint features
    res["joint_features"] = dict(
        rim=dict(half_lap_deg=F.LAP_DEG, pin_hole_d=3.2, pin_r=125.0, boss_r=[K.RIM_R[0], 128.5], pin="3 mm G10 rod or bamboo"),
        hub=dict(boss_deg=F.HUB_BOSS_DEG, boss_r=list(F.HUB_BOSS_R), boss_z_local=[0.0, K.Z_BAR[1]], pin_hole_d=F.HUB_PIN_D,
                 pin_r=F.HUB_PIN_R, wall_in_mm=round(F.HUB_PIN_R - F.HUB_PIN_D / 2 - F.HUB_BOSS_R[0], 2),
                 wall_out_mm=round(F.HUB_BOSS_R[1] - F.HUB_PIN_R - F.HUB_PIN_D / 2, 2),
                 boss_to_bar_channel_mm=round(K.BAR_CH_R[0] - F.HUB_BOSS_R[1], 2), pin="2 mm G10/glass-fibre rod"))
    # 3. teeth
    res["teeth_mm"] = {f"{route}_bundle{b}": teeth(b, c) for route, c in (("print", 0.3), ("cnc", 0.2)) for b in BAND}
    # 4. segments
    body, info = F.former(bundle=BUNDLE, clearance=0.3, min_end_tooth=F.MIN_END_TOOTH, lead_hole_r=F.LEAD_HOLE_R, lead_slot=F.LEAD_SLOT)
    segs, full = F.segments(body)
    nsol = [len(list(s.solids())) for s in segs]
    inter = []
    for i in range(len(segs)):
        j = (i + 1) % len(segs)
        o = segs[i].intersect(segs[j])
        v = 0.0 if o is None else (sum(x.volume for x in o) if hasattr(o, "__iter__") else o.volume)
        inter.append(round(v, 4))
    lugs_by_seg = []
    for j in range(len(bounds)):
        a0 = bounds[j]
        a1 = bounds[(j + 1) % len(bounds)] + (360 if j == len(bounds) - 1 else 0)
        lugs_by_seg.append([a for a in K.LUG_ANGLES if any(a0 <= x <= a1 for x in (a, a - 360, a + 360))])
    res["segments"] = dict(
        solids_each=nsol, adjacent_overlap_mm3=inter, volume_sum_cm3=round(sum(s.volume for s in segs) / 1e3, 3),
        printed_body_cm3=round(full.volume / 1e3, 3),
        footprint_mm=[[round(s.bounding_box().size.X, 1), round(s.bounding_box().size.Y, 1), round(s.bounding_box().size.Z, 1)] for s in segs],
        carrier_lugs_deg=lugs_by_seg)
    res["comb_top_world_z"] = info["comb_top_world"]
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
