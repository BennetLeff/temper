# provenance: commit=6bffbf4a72f03ae89cc48e85b1555d5fa1fd562d dirty=false
"""INDEPENDENT cross-check of the HV<->HV census geometry.

Reads ``pcb/temper.kicad_pcb`` with its OWN regex parser and shares no code
with ``temper_placer`` -- not ``pad_world``, not ``pad_geometry``, not
``kicad_parser`` -- beyond the standard library and Shapely. It builds each pad
from first principles under the settled convention:

    world_centre     = (FX, FY) + R(-THETA) . (LX, LY)
    world_body_angle = PAD_ANGLE, taken ABSOLUTE, exactly as the file writes it

and reports ``polygon.distance()``. The point is that a wrong composition moves
figures by MILLIMETRES (19 640 of 25 833 cross-domain distances changed when
``41c8d5272`` corrected it), so an agreement at 1e-4 across several rotations
is a real check on the convention and not a tautology.

TWO PAIRS ARE EXPECTED TO DISAGREE, IN ONE DIRECTION ONLY. This file models a
``roundrect`` pad as a full rectangle. A rectangle is strictly MORE copper than
the roundrect it bounds, so this file must report a SMALLER gap than the census
for any roundrect pair, by at most the corner radius. A disagreement in the
other direction, or larger than the radius, would be a real defect.

Read-only. Run from the repo root:

    python docs/evidence/2026-08-20-hv-hv-geometry-independent-check.py
"""
import math
import re
from pathlib import Path

from shapely.affinity import rotate, translate
from shapely.geometry import Point, box

TEXT = Path("pcb/temper.kicad_pcb").read_text(encoding="utf-8")

pads = {}
for block in TEXT.split("\n  (footprint ")[1:]:
    ref_m = re.search(r'\(property "Reference" "([^"]+)"', block)
    at_m = re.search(r"\n    \(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)", block)
    if not ref_m or not at_m:
        continue
    ref = ref_m.group(1)
    fx, fy = float(at_m.group(1)), float(at_m.group(2))
    ftheta = float(at_m.group(3) or 0.0)
    for pm in re.finditer(
        r'\(pad "([^"]*)" \S+ (\S+) \(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)'
        r" \(size ([-\d.]+) ([-\d.]+)\)",
        block,
    ):
        num, shape = pm.group(1), pm.group(2)
        lx, ly = float(pm.group(3)), float(pm.group(4))
        pang = float(pm.group(5) or 0.0)   # ABSOLUTE per the settled convention
        w, h = float(pm.group(6)), float(pm.group(7))
        # world centre: R(-theta) applied to the local offset
        t = math.radians(-ftheta)
        wx = fx + lx * math.cos(t) - ly * math.sin(t)
        wy = fy + lx * math.sin(t) + ly * math.cos(t)
        if shape == "circle":
            poly = Point(0, 0).buffer(w / 2.0, 64)
        elif shape == "oval":
            r = min(w, h) / 2.0
            poly = box(-w / 2 + r, -h / 2 + r, w / 2 - r, h / 2 - r).buffer(r, 64)
        else:  # rect / roundrect -- roundrect only ADDS copper at the corners,
               # so a plain rect is the conservative (never-larger) body
            poly = box(-w / 2, -h / 2, w / 2, h / 2)
        poly = translate(rotate(poly, pang, origin=(0, 0), use_radians=False), wx, wy)
        pads.setdefault((ref, num), []).append(poly)

CHECKS = [
    (("R30", "1"), ("R30", "2"), 5.000),
    (("R5", "1"), ("R9", "2"), 4.479),
    (("C22", "1"), ("C22", "2"), 0.650),
    (("C23", "1"), ("C23", "2"), 0.650),
    (("K3", "1"), ("K3", "3"), 3.040),
    (("K2", "4"), ("K2", "1"), 3.040),
    (("R4", "1"), ("R4", "2"), 4.700),
    (("C17", "2"), ("R30", "1"), 0.790),
    (("K1", "13"), ("K1", "14"), 0.000),
]
print(f"{'pair':26} {'independent':>12} {'census':>9}  delta")
for a, b, expect in CHECKS:
    if a not in pads or b not in pads:
        print(f"{a}<->{b}: MISSING")
        continue
    d = min(pa.distance(pb) for pa in pads[a] for pb in pads[b])
    print(f"{a[0]}.{a[1]:<4}<-> {b[0]}.{b[1]:<8} {d:12.4f} {expect:9.3f}  {d-expect:+.4f}")
