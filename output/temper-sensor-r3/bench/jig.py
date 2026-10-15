"""sensor-r3 bench jig: surrogate post, holder and spring plug for the cookware contact survey.

Machinable geometry (STEP) for a C1-surrogate probe held under a 4 mm "glass" plate
with an Ø18 bore, like the product. z = 0 is the plate top; the pan rests on it.

  post    PEEK (or Vespel) turned part: Ø8 neck, wall 0.5, disc bonded on the top rim,
          Ø12 shoulder whose top face is the up-stop, Ø6 foot with a 90° cone for a
          Ø3 ball. The post rocks on the ball and is free in a loose guide, so the disc
          follows the pan's tilt (C1 needs >= ±5 mrad free rocking; CAD gate G5).
  holder  6061 or PEEK block, flange registered on the plate underside, 4 mm guide
          bore Ø8.3 (0.15 radial clearance), counterbore Ø12.6 for the shoulder.
          Nominal proud with no shims is PROUD_NO_SHIM; 0.05 mm shims under the
          flange set 0.60 mm.
  plug    M10x1 threaded spring seat (1 mm of preload per turn).

Run (build123d env, see ../cad/DECISIONS.md):  cadenv/bin/python jig.py  -> jig.json + jig-*.step
"""
from __future__ import annotations

import json
from pathlib import Path

from build123d import Align, Box, Cone, Cylinder, Pos, export_step

HERE = Path(__file__).parent

PLATE_T = 4.0            # glass-ceramic offcut thickness (product glass is 4.00 +- 0.03 near the bore)
DISC_T = 0.32            # Si3N4 C1-exact; 0.254 for the alumina option (post length is the same,
                         # the 0.066 mm difference is taken up in shims)
PROUD_NOM = 0.60         # C1 spec 0.60 +- 0.10
PROUD_NO_SHIM = 0.80     # built in, so shims only ever lower the disc
GUIDE_D, NECK_OD, NECK_WALL = 8.3, 8.0, 0.5
GUIDE_LEN = 4.0
SHOULDER_D, SHOULDER_H, CB_D = 12.0, 2.0, 12.6
FOOT_D, FOOT_H = 6.0, 4.0
BALL_D = 3.0
STROKE_MIN = 2.0          # >= 1.2 mm required; flush is reached at 0.6
SPRING = dict(od=5.5, free_len=16.0, rate_N_mm=0.30, solid_len=6.0)   # selection window, RIG.md
FORCE_WINDOW = (1.2, 1.8)

# derived z positions (mm), plate top = 0
z_disc_top = PROUD_NO_SHIM
z_post_top = z_disc_top - DISC_T
z_plate_bot = -PLATE_T
z_stop = z_plate_bot - GUIDE_LEN              # holder internal step = post shoulder top at rest
neck_len = z_post_top - z_stop
z_shoulder_bot = z_stop - SHOULDER_H
z_foot_bot = z_shoulder_bot - FOOT_H
cb_depth = SHOULDER_H + STROKE_MIN + 0.5
z_cavity_top = z_stop - cb_depth
HOLDER_BELOW = 30.0
z_holder_bot = z_plate_bot - HOLDER_BELOW


def post():
    neck = Pos(0, 0, z_stop) * Cylinder(NECK_OD / 2, neck_len, align=(Align.CENTER, Align.CENTER, Align.MIN))
    bore = Pos(0, 0, z_stop + 1.0) * Cylinder(NECK_OD / 2 - NECK_WALL, neck_len, align=(Align.CENTER, Align.CENTER, Align.MIN))
    shoulder = Pos(0, 0, z_shoulder_bot) * Cylinder(SHOULDER_D / 2, SHOULDER_H, align=(Align.CENTER, Align.CENTER, Align.MIN))
    foot = Pos(0, 0, z_foot_bot) * Cylinder(FOOT_D / 2, FOOT_H, align=(Align.CENTER, Align.CENTER, Align.MIN))
    lead_bore = Pos(0, 0, z_foot_bot) * Cylinder(1.5, z_stop + 1.0 - z_foot_bot, align=(Align.CENTER, Align.CENTER, Align.MIN))
    cone = Pos(0, 0, z_foot_bot) * Cone(BALL_D / 2 + 0.1, 0.0, BALL_D / 2 + 0.1, align=(Align.CENTER, Align.CENTER, Align.MIN))
    side_exit = Pos(0, SHOULDER_D / 4, z_shoulder_bot + SHOULDER_H / 2) * Box(1.2, SHOULDER_D / 2, 1.2)
    p = neck + shoulder + foot - bore - lead_bore - cone - side_exit
    return p


def holder():
    flange = Pos(0, 0, z_plate_bot - 4.0) * Cylinder(20.0, 4.0, align=(Align.CENTER, Align.CENTER, Align.MIN))
    body = Pos(0, 0, z_holder_bot) * Cylinder(15.0, HOLDER_BELOW, align=(Align.CENTER, Align.CENTER, Align.MIN))
    guide = Pos(0, 0, z_stop) * Cylinder(GUIDE_D / 2, GUIDE_LEN + 0.01, align=(Align.CENTER, Align.CENTER, Align.MIN))
    cb = Pos(0, 0, z_cavity_top) * Cylinder(CB_D / 2, cb_depth + 0.001, align=(Align.CENTER, Align.CENTER, Align.MIN))
    cavity = Pos(0, 0, z_holder_bot) * Cylinder(4.5, z_cavity_top - z_holder_bot + 0.01, align=(Align.CENTER, Align.CENTER, Align.MIN))
    lead_slot = Pos(0, 10.0, z_shoulder_bot - 1.0) * Box(2.0, 12.0, 8.0)
    h = flange + body - guide - cb - cavity - lead_slot
    for c, s in ((1, 0), (-0.5, 0.866), (-0.5, -0.866)):     # 3 x M3 clearance on PCD 34
        h -= Pos(17.0 * c, 17.0 * s, z_plate_bot - 4.0) * Cylinder(1.7, 4.01, align=(Align.CENTER, Align.CENTER, Align.MIN))
    return h


def main():
    P, H = post(), holder()
    export_step(P, str(HERE / "jig-post.step"))
    export_step(H, str(HERE / "jig-holder.step"))
    shims_to_nom = PROUD_NO_SHIM - PROUD_NOM
    # spring: cavity length from plug top to ball bottom at rest and at full stroke
    plug_top_nominal = z_holder_bot + 8.0          # plug engaged 8 mm (M10x1)
    l_rest = (z_foot_bot - BALL_D / 2) - plug_top_nominal
    l_flush = l_rest - PROUD_NOM
    l_stop = l_rest - STROKE_MIN
    k = SPRING["rate_N_mm"]
    # preload chosen so the force at the 0.6 mm (flush) position is mid-window
    f_mid = sum(FORCE_WINDOW) / 2
    compression_at_flush = f_mid / k
    free_needed = l_flush + compression_at_flush
    res = {
        "scope": __doc__.strip(),
        "z_mm": {"disc_top_no_shim": z_disc_top, "post_top": round(z_post_top, 3), "plate_bottom": z_plate_bot,
                 "up_stop": z_stop, "shoulder_bottom": z_shoulder_bot, "foot_bottom": z_foot_bot},
        "neck_len_mm": round(neck_len, 3),
        "shims_to_nominal_proud_mm": round(shims_to_nom, 3),
        "stroke_to_hard_stop_mm": STROKE_MIN + 0.5,
        "free_rocking_mrad_guide_limited": round(1000 * (GUIDE_D - NECK_OD) / 2 / GUIDE_LEN, 1),
        "spring": {**SPRING, "length_at_rest_mm": round(l_rest, 2), "length_at_flush_mm": round(l_flush, 2),
                   "length_at_stroke_mm": round(l_stop, 2),
                   "force_at_rest_N": round(f_mid - k * PROUD_NOM, 3), "force_at_flush_N": round(f_mid, 3),
                   "force_at_stroke_N": round(f_mid + k * (STROKE_MIN - PROUD_NOM), 3),
                   "free_length_needed_for_mid_window_at_flush_mm": round(free_needed, 2),
                   "plug_turns_per_0p3N": round(0.3 / k, 2)},
        "volumes_mm3": {"post": round(P.volume, 1), "holder": round(H.volume, 1)},
    }
    res["checks"] = {
        "proud_reachable_with_shims": shims_to_nom >= 0,
        "stroke_ge_1p2": res["stroke_to_hard_stop_mm"] >= 1.2,
        "rocking_ge_5mrad": res["free_rocking_mrad_guide_limited"] >= 5.0,
        "force_at_flush_in_window": FORCE_WINDOW[0] <= f_mid <= FORCE_WINDOW[1],
        "spring_not_solid_at_stroke": l_stop > SPRING["solid_len"],
    }
    (HERE / "jig.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({k: v for k, v in res.items() if k != "scope"}, indent=1))


if __name__ == "__main__":
    main()
