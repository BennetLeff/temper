"""Scale measurements from Impulse teardown stills, plus the coil-design inference.

Pixel picks are in DISPLAY coordinates of the 2000-px-wide preview of each 4K
frame (x 0-2000, y 0-1125); they were picked by eye (about +-10 px) from the
frames named below, which live under ~/temper-media/Sue70X7ZeS0/frames/
(NOT in the repo). Re-pick them against the same frames to check. Every output
carries its scale assumption; treat lengths as +-15-25 %.

Scale references:
  - coil: the winding OD is "a 9-inch coil... all the way out to the edge"
    [said 32:48] -> 228.6 mm across the winding (rim inner edge);
  - drive board: TO-247 body width 15.9 mm (JEDEC TO-247 nominal, 15.5-16.1),
    devices sitting side by side under per-device clips.

Coil inference: Impulse's patent example runs a full bridge from ~115 V DC at
up to 10 kW per coil [patent US12712433B1 FIG. 3]. For the same pan and coil
geometry the reflected resistance scales with N^2, so turns are scaled from
temper's coil (21.9 turns, ~18.7 A rms line-average tank current at ~1.71 kW
input, POWER-SECTION.md section 2) to the impedance a 10 kW / 115 V full
bridge needs. Run: python3 measure_frames.py -> measure_frames.json
"""
import json
from math import pi, sqrt
from pathlib import Path

PICKS = {
    # frame coil_f0971.25.jpg (16:11, prototype "2024-ish" coil, underside, camera tilted about the x axis)
    "proto_coil": {
        "rim_outer_x": (640, 1500), "rim_outer_y": (293, 905),       # outer edge of the black carrier rim
        "winding_od_x": (695, 1445),                                  # rim inner edge = winding OD (horizontal = unforeshortened)
        "centre_x": 1070,
        "bar_right_x": (1192, 1423),                                  # radial extent of the right-hand ferrite bar (horizontal)
        "bar_right_width_y": 53,                                      # vertical extent of that bar (foreshortened)
    },
    # frame drive_f0208.75.jpg (03:28, DVT drive board, right board in the frame)
    "drive": {
        "clip_group_x": (1118, 1305), "clip_count": 4,               # four side-by-side TO-247 under clips
        "film_caps_x": (1505, 1770), "film_cap_count": 3,            # three grey box caps (nearer the camera: over-reads)
    },
}

TEMPER = {"turns": 21.9, "tank_irms_A": 18.7, "input_W": 1710.0, "eff": 0.90,
          "litz_strands": 270, "strand_mm": 0.10}
IMPULSE = {"vbus_V": 115.0, "power_W": 10000.0}


def main():
    c = PICKS["proto_coil"]
    mm_px = 228.6 / (c["winding_od_x"][1] - c["winding_od_x"][0])
    tilt = (c["rim_outer_y"][1] - c["rim_outer_y"][0]) / (c["rim_outer_x"][1] - c["rim_outer_x"][0])
    coil = {
        "mm_per_px": round(mm_px, 3),
        "view_foreshortening_minor_over_major": round(tilt, 2),
        "carrier_rim_OD_mm": round((c["rim_outer_x"][1] - c["rim_outer_x"][0]) * mm_px, 0),
        "ferrite_bar_r_inner_mm": round((c["bar_right_x"][0] - c["centre_x"]) * mm_px, 0),
        "ferrite_bar_r_outer_mm": round((c["bar_right_x"][1] - c["centre_x"]) * mm_px, 0),
        "ferrite_bar_length_mm": round((c["bar_right_x"][1] - c["bar_right_x"][0]) * mm_px, 0),
        "ferrite_bar_width_mm": round(c["bar_right_width_y"] / tilt * mm_px, 0),
        "note": "8 radial bars (count from 16:11 and 03:40 frames); the width pick may span two side-by-side bars",
    }
    d = PICKS["drive"]
    pitch_px = (d["clip_group_x"][1] - d["clip_group_x"][0]) / (d["clip_count"] - 0.0)
    drive = {
        "clip_pitch_px": round(pitch_px, 1),
        "assumed_device_pitch_mm": "15.9 body + 2-5 gap = 18-21",
        "film_cap_length_mm_range": [round((d["film_caps_x"][1] - d["film_caps_x"][0]) / d["film_cap_count"] / pitch_px * p, 0)
                                     for p in (18.0, 21.0)],
        "note": "caps are nearer the camera than the clips, so the cap length over-reads",
    }
    # coil inference
    p_pan_t = TEMPER["input_W"] * TEMPER["eff"]
    r_eq_t = p_pan_t / TEMPER["tank_irms_A"] ** 2
    v1_i = 2 * sqrt(2) / pi * IMPULSE["vbus_V"]               # fundamental rms of a +-Vbus full-bridge square wave
    r_eq_i = v1_i ** 2 / IMPULSE["power_W"]                  # at resonance (unity power factor): the most turns it could have
    n_i = TEMPER["turns"] * sqrt(r_eq_i / r_eq_t)
    i_i = IMPULSE["power_W"] / v1_i
    a_t = TEMPER["litz_strands"] * pi * (TEMPER["strand_mm"] / 2) ** 2
    j_t = TEMPER["tank_irms_A"] / a_t
    infer = {
        "temper_R_eq_ohm": round(r_eq_t, 2), "impulse_V1_rms_V": round(v1_i, 1), "impulse_R_eq_ohm_max": round(r_eq_i, 2),
        "impulse_turns_upper_estimate": round(n_i, 1), "impulse_coil_I_rms_A_min": round(i_i, 0),
        "temper_litz_mm2": round(a_t, 2), "temper_J_A_per_mm2": round(j_t, 1),
        "impulse_litz_mm2_at_temper_J": round(i_i / j_t, 1),
        "impulse_bundle_dia_mm_at_0p5_fill": round(sqrt(i_i / j_t / 0.5 * 4 / pi), 1),
        "note": "upper-bound turns (unity pf at resonance); a lagging pf for ZVS lowers R_eq and the turn count. "
                "Production frames show orange-served bundles ~3.5-4 mm wide at a ~6-8 mm pitch, consistent with ~10-12 turns "
                "of heavier litz run at a higher current density than temper's.",
    }
    out = {"scope": __doc__.strip(), "picks": PICKS, "coil": coil, "drive": drive, "coil_inference": infer}
    Path(__file__).with_name("measure_frames.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({"coil": coil, "drive": drive, "coil_inference": infer}, indent=1))


if __name__ == "__main__":
    main()
