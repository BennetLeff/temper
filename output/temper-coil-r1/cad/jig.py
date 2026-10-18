"""Home winding jig for the coil-r1 former (README D7). All wood and plastic: no metal within ~140 mm of the coil, so L can
be measured on the jig, and the coil sits ~420 mm above the bench (a steel bench top does not load the reading).

ASSUMED TOOLS: a hand saw or jigsaw, a drill with a 25 mm spade/Forstner bit, wood glue, clamps. No 3D printer is needed
(every printed part has a plywood equivalent); a laser/CNC service can cut the DXFs instead.

Parts (jig z = 0 is the platter top = the former underside; mm):
  J1 platter          18 ply disc Ø320: spindle hole Ø25, four Ø3.5 holes at r127 matching the former lugs (M3 NYLON screws
                      + nylon wing nuts), 36 pencil/engraved ticks at 10 deg with a bold START tick at -95 deg, crank hole Ø10
  J2 hub block        2 x 18 ply 90 x 90, Ø25 hole, glued under J1 (keeps the spindle square)
  J3 spindle          Ø25 hardwood dowel x 400, glued into J1/J2; bottom end rounded and waxed
  J4 top plate        18 ply 300 x 300, Ø25.5 waxed bearing hole (or a UHMW bushing); top face at z -142 (>= 120 below coil)
  J5 legs             4 x 18 ply 80 x 243
  J6 base             18 ply 400 x 400 (the only screws in the jig are here, >= 400 mm below the coil)
  J7 thrust block     18 ply 100 x 100 with Ø25.5 hole, glued on J6; a 3 mm UHMW/PTFE disc under the spindle end
  J8 spool stand      separate, 0.5-1 m away: base 250 x 200, two cheeks 200 x 260 with U-slots for a Ø12 dowel axle
  J9 felt brake       12 ply arm 30 x 220 on a Ø8 dowel pivot, felt pad on the spool flange, rubber band to a peg: the brake acts
                      on the SPOOL, never on the wire; tension set by the band, measured with a luggage scale
  J10 guide post/arm  18 ply post 80 x 470 on J6, arm 40 x 260 with an 8 mm radial slot over the former; guide block J11
                      slides in the slot (nylon M6 wing screw) and carries a PTFE tube 4/6 mm (Bowden tube) as the wire eye
  J12 centring boss   ply ring stack (or printed) OD 43.6 x 24 high, glued on J1: centres the former's Ø44 hub; 3 mm slot at
                      -95 deg for the centre lead and a Ø8 hole for the J13 lead mast (Ø8 dowel x 200)
  J14 tamper          Ø12 dowel x 150 with a grooved nylon/UHMW tip: presses each turn into its notch (no fingernails, no metal)
  J15 pointer         18 ply 40 x 160 upright on J4 with a sharpened tip at the platter edge: reads the 10 deg ticks
  J16 crank peg       Ø10 dowel x 80 in J1 at r148
Outputs: out/jig_assembly.step (with the former + bars), out/jig_dxf/*.dxf (flat parts, 1:1 mm), out/jig_cutlist.csv,
out/centring_boss.stl (optional print). Run: .venv/bin/python cad/jig.py
"""
from __future__ import annotations

import csv
import math
from pathlib import Path

import ezdxf
from build123d import Box, Compound, Plane, Pos, Rot, Solid, export_step, export_stl

import geom as K
from geom import G

OUT = Path(__file__).resolve().parent / "out"
DXF = OUT / "jig_dxf"
T = 18.0
PLATTER_R = 160.0
Z_TOP_PLATE = -142.0
Z_BASE_TOP = -403.0


def box(x0, x1, y0, y1, z0, z1):
    return Pos((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2) * Box(x1 - x0, y1 - y0, z1 - z0)


def cyl(x, y, z0, h, d):
    return K.zcyl(x, y, z0, h, d / 2)


def parts():
    p = {}
    pl = cyl(0, 0, -T, T, 2 * PLATTER_R) - cyl(0, 0, -T - 1, T + 2, 25.0)
    for a in K.LUG_ANGLES:
        pl = pl - cyl(*K.P(K.LUG_R, a)[:2], -T - 1, T + 2, 3.5)
    pl = pl - cyl(*K.P(148.0, 0.0)[:2], -T - 1, T + 2, 10.0)
    p["J1_platter"] = pl
    p["J2_hub_block"] = box(-45, 45, -45, 45, -3 * T, -T) - cyl(0, 0, -3 * T - 1, 2 * T + 2, 25.0)
    p["J3_spindle"] = cyl(0, 0, Z_BASE_TOP + 3.0, -Z_BASE_TOP - 3.0, 25.0)
    p["J4_top_plate"] = box(-150, 150, -150, 150, Z_TOP_PLATE - T, Z_TOP_PLATE) - cyl(0, 0, Z_TOP_PLATE - T - 1, T + 2, 25.5)
    legs = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            x0 = sx * 150 - (T if sx > 0 else 0)
            y0 = sy * 110 - (80 if sy > 0 else 0)
            legs.append(box(x0, x0 + T, y0, y0 + 80, Z_BASE_TOP, Z_TOP_PLATE - T))
    p["J5_legs"] = Compound(legs)
    p["J6_base"] = box(-200, 200, -200, 200, Z_BASE_TOP - T, Z_BASE_TOP)
    p["J7_thrust_block"] = box(-50, 50, -50, 50, Z_BASE_TOP, Z_BASE_TOP + T) - cyl(0, 0, Z_BASE_TOP - 1, T + 2, 25.5)
    p["J7_thrust_disc_UHMW"] = cyl(0, 0, Z_BASE_TOP, 3.0, 25.0)
    # guide post + arm + block + PTFE tube, on the base's -X side, arm over the former along +X... at angle 180 (left)
    post_x = -200.0
    p["J10_guide_post"] = box(post_x, post_x + T, -40, 40, Z_BASE_TOP, 60.0)
    arm = box(post_x + T, -20.0, -20, 20, 60.0 - T, 60.0)
    arm = arm - (Pos(-95.0, 0, 51.0) * Box(170.0, 8.0, T + 2))           # radial slot r 10-180 along -X
    p["J10_guide_arm"] = arm
    blk_x = -110.0                                                         # over the outer section at the moment
    p["J11_guide_block"] = box(blk_x - 15, blk_x + 15, -15, 15, 60.0, 72.0)
    p["J11_PTFE_tube_4x6"] = cyl(blk_x, 0, 18.0, 54.0, 6.0) - cyl(blk_x, 0, 17.0, 56.0, 4.0)
    boss = cyl(0, 0, 0.0, 24.0, 43.6) - cyl(*K.P(12.0, 45.0)[:2], 4.0, 21.0, 8.0)
    boss = boss - (Pos(*K.P(17.0, -95.0, 14.0)) * Rot(0, 0, -95.0) * Box(14.0, 3.0, 21.0))
    p["J12_centring_boss"] = boss
    p["J13_lead_mast"] = cyl(*K.P(12.0, 45.0)[:2], 4.0, 200.0, 8.0)
    p["J15_pointer"] = Pos(*K.P(PLATTER_R + 9.0, 90.0, (Z_TOP_PLATE - 10.0) / 2)) * Rot(0, 0, 90.0) * Box(T, 40.0, -Z_TOP_PLATE + 10.0)
    p["J16_crank_peg"] = cyl(*K.P(148.0, 0.0)[:2], -T, 80.0, 10.0)
    # spool stand J8/J9, placed 600 mm away on +Y for the picture (sits on the bench at the base's level)
    oy, zb = 600.0, Z_BASE_TOP - T
    stand = [box(-125, 125, oy - 100, oy + 100, zb, zb + T)]
    for sx in (-1, 1):
        x0 = sx * 80 - (T if sx > 0 else 0)
        ch = box(x0, x0 + T, oy - 100, oy + 100, zb + T, zb + T + 260)
        ch = ch - Solid.make_cylinder(6.5, T + 2, Plane(origin=(x0 - 1, oy, zb + T + 230), z_dir=(1, 0, 0)))
        ch = ch - box(x0 - 1, x0 + T + 1, oy - 6.5, oy + 6.5, zb + T + 230, zb + T + 261)
        stand.append(ch)
    p["J8_spool_stand"] = Compound(stand)
    axle = Solid.make_cylinder(6.0, 200.0, Plane(origin=(-100, oy, zb + T + 230), z_dir=(1, 0, 0)))
    spool = Solid.make_cylinder(100.0, 120.0, Plane(origin=(-60, oy, zb + T + 230), z_dir=(1, 0, 0))) - \
        Solid.make_cylinder(80.0, 110.0, Plane(origin=(-55, oy, zb + T + 230), z_dir=(1, 0, 0)))
    p["J8_axle_and_spool"] = Compound([axle, spool])
    p["J9_felt_brake_arm"] = Pos(-70.0, oy - 60.0, zb + T + 120) * Rot(0, -60, 0) * Box(220.0, 30.0, 12.0)
    return p


def coil_on_jig():
    import former as F
    body, _ = F.former()
    bars = Compound([K.radial_box(phi, *G.BAR_R, G.BAR_W, *K.Z_BAR) for phi in G.bar_angles()])
    return body, bars


# ---- flat-part DXFs ---------------------------------------------------------------------------------------------------
def dxf_part(name, outline=None, circles=(), lines=(), rect=None, notes=""):
    doc = ezdxf.new("R2010")
    doc.units = ezdxf.units.MM
    msp = doc.modelspace()
    doc.layers.add("CUT", color=7)
    doc.layers.add("DRILL", color=1)
    doc.layers.add("MARK", color=3)
    if rect:
        x0, y0, x1, y1 = rect
        msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True, dxfattribs={"layer": "CUT"})
    if outline == "disc":
        msp.add_circle((0, 0), PLATTER_R, dxfattribs={"layer": "CUT"})
    for (x, y, d, lay) in circles:
        msp.add_circle((x, y), d / 2, dxfattribs={"layer": lay})
    for (a, b, lay) in lines:
        msp.add_line(a, b, dxfattribs={"layer": lay})
    if notes:
        msp.add_text(notes, height=4, dxfattribs={"layer": "MARK"}).set_placement((0, -PLATTER_R - 15 if outline == "disc" else -20))
    doc.saveas(DXF / f"{name}.dxf")


def write_dxfs():
    DXF.mkdir(parents=True, exist_ok=True)
    circ = [(0, 0, 25.0, "CUT")] + [(*K.P(K.LUG_R, a)[:2], 3.5, "DRILL") for a in K.LUG_ANGLES] + [(*K.P(148.0, 0)[:2], 10.0, "DRILL")]
    ticks = []
    for k in range(36):
        th = -95.0 + 10.0 * k
        r0 = PLATTER_R - (14.0 if k == 0 else 7.0 if k % 9 == 0 else 4.0)
        ticks.append((K.P(r0, th)[:2], K.P(PLATTER_R, th)[:2], "MARK"))
    dxf_part("J1_platter", outline="disc", circles=circ, lines=ticks,
             notes="J1 platter 18 ply. MARK: 10 deg ticks, long tick = START (-95 deg), wind CCW seen from above")
    dxf_part("J2_hub_block_x2", rect=(-45, -45, 45, 45), circles=[(0, 0, 25.0, "CUT")], notes="J2 x2")
    dxf_part("J4_top_plate", rect=(-150, -150, 150, 150), circles=[(0, 0, 25.5, "CUT")], notes="J4 top plate")
    dxf_part("J5_leg_x4", rect=(0, 0, 80, 243), notes="J5 x4")
    dxf_part("J6_base", rect=(-200, -200, 200, 200), notes="J6 base")
    dxf_part("J7_thrust_block", rect=(-50, -50, 50, 50), circles=[(0, 0, 25.5, "CUT")], notes="J7 + 3 mm UHMW disc Ø25")
    dxf_part("J8_spool_cheek_x2", rect=(0, 0, 200, 260), circles=[(100, 230, 13.0, "CUT")],
             lines=[((93.5, 230), (93.5, 260), "CUT"), ((106.5, 230), (106.5, 260), "CUT")], notes="J8 x2: U-slot 13 wide")
    dxf_part("J8_spool_base", rect=(0, 0, 250, 200), notes="J8 base")
    dxf_part("J9_brake_arm_12ply", rect=(0, 0, 220, 30), circles=[(15, 15, 8.0, "DRILL")], notes="J9 felt pad 30x40 at the far end")
    dxf_part("J10_guide_post", rect=(0, 0, 80, 470), notes="J10 post")
    dxf_part("J10_guide_arm", rect=(0, 0, 260, 40), lines=[((60, 16), (230, 16), "CUT"), ((60, 24), (230, 24), "CUT"),
                                                            ((60, 16), (60, 24), "CUT"), ((230, 16), (230, 24), "CUT")],
             notes="J10 arm: 8 mm slot")
    dxf_part("J11_guide_block", rect=(-15, -15, 15, 15), circles=[(0, 0, 6.0, "DRILL"), (0, 10, 6.0, "DRILL")],
             notes="J11: Ø6 for the PTFE tube, Ø6 for the nylon M6 screw")
    dxf_part("J12_centring_boss_rings_x2", outline=None, circles=[(0, 0, 43.6, "CUT"), (*K.P(12.0, 45.0)[:2], 8.0, "DRILL")],
             notes="J12 2 x 12 ply rings (or print centring_boss.stl); 3 mm lead slot at -95 deg")
    dxf_part("J15_pointer", rect=(0, 0, 40, 160), notes="J15 pointer")
    rows = [("J1", "platter", "birch ply 18", "Ø320", 1), ("J2", "hub block", "birch ply 18", "90 x 90", 2),
            ("J3", "spindle", "hardwood dowel Ø25", "400", 1), ("J4", "top plate", "birch ply 18", "300 x 300", 1),
            ("J5", "leg", "birch ply 18", "80 x 243", 4), ("J6", "base", "birch ply 18", "400 x 400", 1),
            ("J7", "thrust block", "birch ply 18", "100 x 100", 1), ("J7", "thrust disc", "UHMW-PE or PTFE 3 mm", "Ø25", 1),
            ("J8", "spool cheek", "birch ply 18", "200 x 260", 2), ("J8", "spool base", "birch ply 18", "250 x 200", 1),
            ("J8", "axle", "hardwood dowel Ø12", "260", 1), ("J9", "brake arm", "ply 12", "220 x 30", 1),
            ("J9", "pivot + band peg", "hardwood dowel Ø8", "60", 2), ("J9", "felt pad", "wool felt 5 mm", "30 x 40", 1),
            ("J10", "guide post", "birch ply 18", "80 x 470", 1), ("J10", "guide arm", "birch ply 18", "260 x 40", 1),
            ("J11", "guide block", "birch ply 18", "30 x 30", 1), ("J11", "wire eye", "PTFE tube 4 ID / 6 OD", "60", 1),
            ("J11", "clamp screw", "nylon M6 x 40 + nylon wing nut", "-", 1), ("J12", "centring boss", "ply 12 rings (or print)", "Ø43.6", 2),
            ("J13", "lead mast", "hardwood dowel Ø8", "200", 1), ("J14", "tamper", "hardwood dowel Ø12 + nylon tip", "150", 1),
            ("J15", "pointer", "birch ply 18", "40 x 160", 1), ("J16", "crank peg", "hardwood dowel Ø10", "80", 1),
            ("-", "former screws", "nylon M3 x 30 + nylon wing nuts", "-", 4),
            ("-", "tally counter", "hand tally counter (keep on the base, > 300 mm from the coil)", "-", 1),
            ("-", "luggage scale", "digital hanging scale 0-10 kg (tension check)", "-", 1)]
    with open(OUT / "jig_cutlist.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["part", "name", "material", "size_mm", "qty"])
        w.writerows(rows)


def main():
    OUT.mkdir(exist_ok=True)
    p = parts()
    write_dxfs()
    export_stl(p["J12_centring_boss"], str(OUT / "centring_boss.stl"), tolerance=0.05)
    body, bars = coil_on_jig()
    items = []
    for name, s in p.items():
        s.label = name
        items.append(s)
    body.label, bars.label = "former_R1_cnc", "ferrite_bars"
    asm = Compound(items + [body, bars])
    export_step(asm, str(OUT / "jig_assembly.step"))
    # min distance check: nothing metallic is modelled; report the closest jig part below the coil and the coil height
    print("jig parts:", ", ".join(p))
    print(f"coil plane (bundle centre) z {K.Z_WIND:.1f}; top-plate bearing at z {Z_TOP_PLATE:.0f} -> {K.Z_WIND - Z_TOP_PLATE:.0f} mm below; "
          f"base screws at z <= {Z_BASE_TOP:.0f}")


if __name__ == "__main__":
    main()
