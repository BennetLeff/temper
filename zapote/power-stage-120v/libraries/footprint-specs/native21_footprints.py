#!/usr/bin/env python3
"""Generate the three native-21 footprints from manufacturer land patterns.

    python3 libraries/footprint-specs/native21_footprints.py

Writes libraries/temper.pretty/{VOL628A_LSOP4,WE_750320775_EP7HV,WE_74404064101_6x6}_ReviewOnly.kicad_mod.
Dimensions (mm) are copied from the cited drawings; pads use the manufacturer's
recommended land pattern exactly. Courtyard = max(body, pads) + 0.25 mm.
"""
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "temper.pretty"

PARTS = {
    "VOL628A_LSOP4_ReviewOnly": {
        "source": "Vishay VOL628A rev 1.9 (doc 82401) p.8 'Possible footprint': pads 1.30 x 0.90, rows 8.20 inner / 10.80 outer, pitch 2.54; body 7.50 x 4.10 max; creepage/clearance >= 8 mm (p.3)",
        # pin: (x, y, w, h)  pins 1/2 on one side, 3/4 opposite (top view: 1 bottom-left, 4 top-left)
        # counter-clockwise from the top (KiCad y down): 1 top-left, 2 bottom-left, 3 bottom-right, 4 top-right
        "pads": {"1": (-4.75, -1.27, 1.30, 0.90), "2": (-4.75, 1.27, 1.30, 0.90),
                 "3": (4.75, 1.27, 1.30, 0.90), "4": (4.75, -1.27, 1.30, 0.90)},
        "body": (7.50, 4.10), "height": 2.30,
    },
    "WE_750320775_EP7HV_ReviewOnly": {
        "source": "Wurth Elektronik 750320775 rev 001.002 p.1 'Recommended Land Pattern': two columns 11.06 c-c, pitch 2.50, pads 2.50 x 1.29; body 13.40 x 11.46 max, 11.94 max high; left column top->bottom 4,3,2,1, right 5,6,7,8 (as the land-pattern view; the dimension view shows the vertical mirror, which is electrically harmless: 1<->4 and 5<->8 are symmetric push-pull ends, 2+3 and 6+7 are tied); tie 2+3 and 6+7 on PCB",
        "pads": {"4": (-5.53, -3.75, 2.50, 1.29), "3": (-5.53, -1.25, 2.50, 1.29), "2": (-5.53, 1.25, 2.50, 1.29),
                 "1": (-5.53, 3.75, 2.50, 1.29), "5": (5.53, -3.75, 2.50, 1.29), "6": (5.53, -1.25, 2.50, 1.29),
                 "7": (5.53, 1.25, 2.50, 1.29), "8": (5.53, 3.75, 2.50, 1.29)},
        "body": (13.40, 11.46), "height": 11.94,
    },
    "WE_74404064101_6x6_ReviewOnly": {
        "source": "Wurth Elektronik 74404064101 (WE-LQS 6045) rev 002.003 p.1 'Recommended Land Pattern': pads 1.8 x 5.7, gap 2.8; body 6.0 x 6.0, 4.5 max high",
        "pads": {"1": (-2.30, 0.0, 1.80, 5.70), "2": (2.30, 0.0, 1.80, 5.70)},
        "body": (6.0, 6.0), "height": 4.5,
    },
}


def rect(layer, x0, y0, x1, y1, width):
    return (f'\t(fp_rect (start {x0:.3f} {y0:.3f}) (end {x1:.3f} {y1:.3f})\n'
            f'\t\t(stroke (width {width}) (type solid)) (fill no) (layer "{layer}"))\n')


def footprint(name, spec):
    bw, bh = spec["body"]
    xs = [abs(x) + w / 2 for x, y, w, h in spec["pads"].values()] + [bw / 2]
    ys = [abs(y) + h / 2 for x, y, w, h in spec["pads"].values()] + [bh / 2]
    cx, cy = max(xs) + 0.25, max(ys) + 0.25
    s = [f'(footprint "{name}"\n\t(version 20241229)\n\t(generator "native21_footprints.py")\n\t(layer "F.Cu")\n',
         f'\t(descr "{spec["source"]}")\n\t(attr smd)\n',
         f'\t(property "Reference" "REF**" (at 0 {-cy - 1.2:.3f} 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))\n',
         f'\t(property "Value" "{name}" (at 0 {cy + 1.2:.3f} 0) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))\n',
         rect("F.Fab", -bw / 2, -bh / 2, bw / 2, bh / 2, 0.1),
         rect("F.CrtYd", -cx, -cy, cx, cy, 0.05),
         rect("F.SilkS", -bw / 2 - 0.12, -bh / 2 - 0.12, bw / 2 + 0.12, bh / 2 + 0.12, 0.12)]
    p1 = spec["pads"]["1"]
    s.append(f'\t(fp_circle (center {p1[0] - p1[2] / 2 - 0.6:.3f} {p1[1]:.3f}) (end {p1[0] - p1[2] / 2 - 0.35:.3f} {p1[1]:.3f})\n'
             f'\t\t(stroke (width 0.12) (type solid)) (fill yes) (layer "F.SilkS"))\n')
    for num, (x, y, w, h) in spec["pads"].items():
        s.append(f'\t(pad "{num}" smd roundrect (at {x:.3f} {y:.3f}) (size {w:.3f} {h:.3f}) '
                 f'(layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.15))\n')
    s.append(")\n")
    return "".join(s)


if __name__ == "__main__":
    for name, spec in PARTS.items():
        (OUT / f"{name}.kicad_mod").write_text(footprint(name, spec))
        print("wrote", name, len(spec["pads"]), "pads")
