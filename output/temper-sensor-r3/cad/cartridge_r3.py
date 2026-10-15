"""sensor-r3 C1 pan-sensor cartridge in the R43 interfaces (build123d, millimetres, world frame).

C1 = a lapped Si3N4 contact disc (Ø8 x 0.32) with the IST Pt100 chip bonded under its centre, carried on a
thin-neck polyimide post. The post is guided by three short pads at the top of the body collar (the rocking
pivot, 0.75 mm under the disc face when a pan holds the disc flush), sealed by a sliding FFKM wiper lip on the
neck, retained upward by a bonded polyimide stop collar (up-stop) and pushed by an A-286 coil spring through an
on-axis sphere-on-cone seat. No diaphragm, no boot, no slot/pin stops, no heater, no position sensor.

The body keeps every R43 interface of the R16 cartridge it replaces: glass-datum rim r12.2-13 on the glass
underside (Z106), Ø38.2 spigot, Ø43 flange on the A-286 gap wave spring, three 60 deg bayonet lugs with the
Ø2 x 0.5 detent bump, R32 spring-gap key, R36/R40 rim-NTC rib with the Ø1.8 x 3.5 pocket at r14.5 (+Y).

Public API (R43 part-dict style):
    r3_cartridge(travel_mm, tilt_mrad=0.0, tilt_axis="x") -> list[dict(name, shape, color, group, kind, ...)]
    profiles(travel_mm) -> {part: (material_key, [(r, z) polygon, ...])}   axisymmetric sections for thermal_axisym.py
    DIM                 -> every dimension used here (budget_asbuilt.py and checks.py import it)
Travel is measured down from rest (disc 0.60 above the glass). Tilt rotates the moving parts about the land
pad pivot (X0, Y261, Z109.25) about the world X ("x") or Y ("y") axis.

Run directly to write the STEP files:  python cartridge_r3.py
"""
from __future__ import annotations

import math
from pathlib import Path

from build123d import (Axis, Box, Compound, Cylinder, Location, Plane, Polygon, Pos, Rot, Shape, Solid, export_step,
                       revolve)

HERE = Path(__file__).resolve().parent
SX, SY = 0.0, 261.0

DIM = dict(
    # R43 interfaces (read from the frozen modules in checks.py, repeated here as the design basis)
    glass_top=110.0, glass_under=106.0, bore_r=9.0,
    carrier_z=(90.0, 93.0), carrier_aperture_r=19.2,
    # contact disc (Si3N4, lapped), chip and bond
    disc_r=4.0, disc_t=0.32, disc_chamfer=0.2, disc_bot=110.28,
    bond_t=0.10, chip_w=1.8, chip_l=2.0, chip_t=0.65, chip_h2=1.1,
    # post (Vespel SP-1): neck tube, integral inner support tube, shoulder (up-stop), foot, spherical nose
    neck_ro=4.0, neck_wall=0.25, neck_bot=104.0,
    inner_ri=1.7, inner_ro=1.9,
    shoulder_r=5.2, shoulder_bot=103.2,
    foot_r=3.0, foot_cone_bot=100.5, nose_R=1.5, nose_zc=99.0, lead_bore_r=0.6,
    # body (Vespel SP-1 polyimide) bores
    bore_main_r=6.1, bore_top=107.0, relief_r=5.5, land_r=4.05, land_z=(109.0, 109.5), land_w=0.6,
    land_angles=(90.0, 210.0, 330.0), collar_r=8.0, collar_top=109.8, chamfer_top=0.2,
    body_bot=74.0, lower_r=8.0, inner_land_top=105.9, inner_land_r=9.75, gland_floor=104.9,
    rim_ri=12.2, rim_ro=13.0,
    bay_groove=(80.0, 81.0), bay_groove_r=6.8, bay_slot_w=3.2, bay_slot_angles=(60.0, 240.0),
    # stop collar (up-stop, wiper retainer) and wiper
    stop_ri=4.5, stop_bot=104.0, stop_top=105.8,
    wiper_bot=105.8, wiper_top=107.0, wiper_lip=(106.62, 106.80), wiper_lip_t=0.30,
    # sphere-on-cone seat cup, spring, bayonet spring washer with the down-stop tube
    cup_r=4.7, cup_bot=96.6, cup_top=98.1, cup_hole_r=0.8, cup_pilot_r=3.6, cup_pilot_bot=95.8,
    washer_z=(80.0, 81.0), washer_r=6.0, washer_lug_r=6.5, washer_lug_w=3.0, washer_hole_r=1.0,
    stop_tube=(1.2, 1.8), stop_tube_top=93.6,
    spring_ri=3.75, spring_ro=4.25, spring_d=0.50, spring_D=8.0,
    # O-ring gasket, 20 x 1.5 FFKM, installed in the gland r9.75-12.2 (floor Z104.9)
    oring_id=20.0, oring_cs=1.5,
    # leads, potting, cable
    sleeve_r=0.45, splice_z=(75.0, 80.0), cable_r=1.7, cable_bot=62.3, relief_z=(68.0, 75.0), relief_boss_r=3.3,
    capillary_r=0.5, capillary_z=(98.3, 108.58), foot_pot_z=(97.65, 101.5),
    connector_xyz=(135.0, 285.0, 62.0), connector_box=(11.0, 10.0, 10.0),
    ntc_xy=(0.0, 261.0 + 14.5), ntc_bead=(1.35, 3.0),
    # stroke
    proud=0.60, stroke_hard=2.2, stroke_tol=0.09,
)
D = DIM
D["z_pivot"] = sum(D["land_z"]) / 2                                  # guide-pad centre, 109.25
D["disc_top"] = D["disc_bot"] + D["disc_t"]                          # 110.60
D["chip_top"] = D["disc_bot"] - D["bond_t"]                          # 110.18
D["chip_bot_h2"] = D["chip_top"] - D["chip_h2"]                      # 109.08
D["spring_L1"] = D["cup_bot"] - D["washer_z"][1]                     # installed length at rest

AMBER, PALE, DARK, SILVER, SEAL = (.73, .44, .20), (.86, .82, .70), (.20, .22, .24), (.70, .72, .74), (.55, .18, .15)
CERAMIC, PI, FIBRE, POT = (.92, .92, .90), (.72, .45, .12), (.95, .93, .80), (.40, .40, .38)


# --------------------------------------------------------------------------- geometry helpers
def _rev(points) -> Shape:
    return Pos(SX, SY, 0) * revolve(Plane.XZ * Polygon(*points, align=None), axis=Axis.Z)


def _cyl(r, z0, z1, x=SX, y=SY) -> Shape:
    return Pos(x, y, (z0 + z1) / 2) * Cylinder(r, z1 - z0)


def _ring(ro, ri, z0, z1) -> Shape:
    return _cyl(ro, z0, z1) - _cyl(ri, z0 - 0.01, z1 + 0.01)


def _rect(r0, r1, z0, z1):
    return [(r0, z0), (r1, z0), (r1, z1), (r0, z1)]


def _radial_box(angle, r0, r1, w, z0, z1) -> Shape:
    a = math.radians(angle)
    rc = (r0 + r1) / 2
    return Pos(SX + rc * math.cos(a), SY + rc * math.sin(a), (z0 + z1) / 2) * Rot(0, 0, angle) * Box(r1 - r0, w, z1 - z0)


def _single(shape: Shape) -> Shape:
    return Compound(list(shape.solids())) if len(shape.solids()) != 1 else shape.solids()[0]


# --------------------------------------------------------------------------- axisymmetric sections (rest)
def _sphere_arc(n=10):
    d = DIM
    phi0 = math.asin(d["lead_bore_r"] / d["nose_R"])
    return [(d["nose_R"] * math.sin(p), d["nose_zc"] - d["nose_R"] * math.cos(p))
            for p in (phi0 + (math.pi / 2 - phi0) * i / n for i in range(n + 1))]


def _post_profile():
    d = DIM
    top = d["disc_bot"]
    pts = _sphere_arc()
    pts += [(d["foot_r"], d["foot_cone_bot"]), (d["foot_r"], d["shoulder_bot"]), (d["shoulder_r"], d["shoulder_bot"]),
            (d["shoulder_r"], d["neck_bot"]), (d["neck_ro"], d["neck_bot"]), (d["neck_ro"], top),
            (d["neck_ro"] - d["neck_wall"], top), (d["neck_ro"] - d["neck_wall"], d["neck_bot"]),
            (d["inner_ro"], d["neck_bot"]), (d["inner_ro"], top), (d["inner_ri"], top), (d["inner_ri"], d["neck_bot"]),
            (d["lead_bore_r"], d["neck_bot"])]
    return pts


def _disc_profile():
    d = DIM
    return [(0, d["disc_bot"]), (d["disc_r"], d["disc_bot"]), (d["disc_r"], d["disc_top"] - d["disc_chamfer"]),
            (d["disc_r"] - d["disc_chamfer"], d["disc_top"]), (0, d["disc_top"])]


def _body_outer():
    d = DIM
    return [(0, d["body_bot"]), (d["lower_r"], d["body_bot"]), (d["lower_r"], 89.5), (19.1, 89.5), (19.1, 94.0),
            (21.5, 94.0), (21.5, 97.0), (d["rim_ro"], 97.0), (d["rim_ro"], d["glass_under"]),
            (d["rim_ri"], d["glass_under"]), (d["rim_ri"], d["gland_floor"]), (d["inner_land_r"], d["gland_floor"]),
            (d["inner_land_r"], d["inner_land_top"]), (d["collar_r"], d["inner_land_top"]),
            (d["collar_r"], d["collar_top"]), (0, d["collar_top"])]


def _body_bore():
    d = DIM
    return [(0, d["body_bot"] - 0.1), (d["bore_main_r"], d["body_bot"] - 0.1), (d["bore_main_r"], d["bore_top"]),
            (d["relief_r"], d["bore_top"]), (d["relief_r"], d["collar_top"] - d["chamfer_top"]),
            (d["relief_r"] + d["chamfer_top"], d["collar_top"]),
            (d["relief_r"] + d["chamfer_top"], d["collar_top"] + 0.1), (0, d["collar_top"] + 0.1)]


def _wiper_profile():
    d = DIM
    lo, hi = d["wiper_lip"]
    return [(4.75, d["wiper_bot"]), (d["bore_main_r"], d["wiper_bot"]), (d["bore_main_r"], d["wiper_top"]),
            (4.85, d["wiper_top"]), (d["neck_ro"], hi), (d["neck_ro"], lo), (4.75, lo - 0.17)]


def _cup_profile():
    d = DIM
    apex = d["nose_zc"] - d["nose_R"] * math.sqrt(2)          # 45 deg cone tangent to the R1.5 nose: apex 2.12 below centre
    r_top = d["cup_top"] - apex
    return [(d["cup_hole_r"], d["cup_pilot_bot"]), (d["cup_pilot_r"], d["cup_pilot_bot"]), (d["cup_pilot_r"], d["cup_bot"]),
            (d["cup_r"], d["cup_bot"]), (d["cup_r"], d["cup_top"]), (r_top, d["cup_top"]),
            (d["cup_hole_r"], apex + d["cup_hole_r"])]


def _washer_profile():
    d = DIM
    z0, z1 = d["washer_z"]
    ri, ro = d["stop_tube"]
    return [(d["washer_hole_r"], z0), (d["washer_r"], z0), (d["washer_r"], z1), (ro, z1), (ro, d["stop_tube_top"]),
            (ri, d["stop_tube_top"]), (ri, z1), (d["washer_hole_r"], z1)]


def _oring_profile(n=36):
    d = DIM
    ar, az = 1.02, (d["glass_under"] - d["gland_floor"]) / 2      # installed: 1.10 high, area-conserving width 2.04
    rc, zc = d["oring_id"] / 2 + d["oring_cs"] / 2 + 0.125, (d["glass_under"] + d["gland_floor"]) / 2
    return [(rc + ar * math.cos(2 * math.pi * i / n), zc + az * math.sin(2 * math.pi * i / n)) for i in range(n)]


def _shift(poly, t):
    return [(r, z - t) for r, z in poly]


MOVING = ("disc_Si3N4", "Pt100_chip_IST_P0K1202", "chip_bond", "post_polyimide", "fibre_plug_annulus",
          "fibre_plug_core", "lead_capillary_fused_silica", "foot_potting", "seat_cup_PEEK")


def profiles(travel: float = 0.0) -> dict:
    """Axisymmetric (r, z) sections for the thermal model; moving parts shifted down by travel."""
    d = DIM
    t = travel
    chip_req = math.sqrt(d["chip_w"] * d["chip_l"] / math.pi)          # equal-area disc for the 1.8 x 2.0 chip
    out = {
        "disc_Si3N4": ("si3n4", [_shift(_disc_profile(), t)]),
        "chip_bond": ("bond", [_shift(_rect(0, chip_req, d["chip_top"], d["disc_bot"]), t)]),
        "Pt100_chip_IST_P0K1202": ("alumina", [_shift(_rect(0, chip_req, d["chip_top"] - d["chip_t"], d["chip_top"]), t)]),
        "post_polyimide": ("pi", [_shift(_post_profile(), t)]),
        "fibre_plug_annulus": ("fibre", [_shift(_rect(d["inner_ro"], d["neck_ro"] - d["neck_wall"], d["neck_bot"], d["disc_bot"]), t)]),
        "fibre_plug_core": ("fibre", [_shift(_rect(0, d["inner_ri"], d["neck_bot"], d["chip_bot_h2"] - 0.08), t)]),
        "foot_potting": ("potting", [_shift(_rect(0, d["lead_bore_r"], *d["foot_pot_z"]), t)]),
        "lead_capillary_fused_silica": ("silica", [_shift(_rect(0, d["capillary_r"], *d["capillary_z"]), t)]),
        "seat_cup_PEEK": ("peek", [_shift(_cup_profile(), t)]),
        "body_PI": ("pi", [_body_outer()]),          # bore is subtracted by the rasteriser (body_bore_void)
        "stop_collar_PI": ("pi", [_rect(d["stop_ri"], d["bore_main_r"], d["stop_bot"], d["stop_top"])]),
        "wiper_FFKM": ("ffkm", [_wiper_profile()]),
        "guide_pads_equiv_ring": ("padring", [_rect(d["land_r"], d["relief_r"], *d["land_z"])]),
        "spring_washer_bayonet_PEEK": ("peek", [_washer_profile()]),
        "spring_A286": ("spring", [_rect(d["spring_ri"], d["spring_ro"], d["washer_z"][1], d["cup_bot"] - t)]),
        "static_gasket_FFKM": ("ffkm", [_oring_profile()]),
        "splice_potting": ("potting", [_rect(0, d["bore_main_r"], d["splice_z"][0], d["splice_z"][1])]),
        "cable_strain_relief_PEEK": ("peek", [_rect(0, d["bore_main_r"], d["body_bot"], d["splice_z"][0]),
                                              _rect(0, d["relief_boss_r"], d["relief_z"][0], d["body_bot"])]),
    }
    out["_body_bore_void"] = ("void", [_body_bore()])
    return out


# --------------------------------------------------------------------------- solids
def _part(name, shape, color, kind, material, evidence, pn=None, group="sensor"):
    return dict(name="sensor_r3_" + name, shape=_single(shape), color=color, group=group, kind=kind,
                material=material, part_number=pn, evidence=evidence, subsystem="sensor_r3")


def _body() -> Shape:
    d = DIM
    body = _rev(_body_outer()) - _rev(_body_bore())
    for a in d["land_angles"]:                                       # three guide pads (the rocking pivot), not a full land
        body = body + _radial_box(a, d["land_r"], d["relief_r"] + 0.1, d["land_w"], *d["land_z"])
    body = body - _ring(d["bay_groove_r"], d["bore_main_r"] - 0.01, *d["bay_groove"])
    for a in d["bay_slot_angles"]:                                   # two axial slots let the washer lugs in from below
        body = body - _radial_box(a, d["bore_main_r"] - 0.2, d["bay_groove_r"], d["bay_slot_w"], d["body_bot"] - 0.1,
                                  d["bay_groove"][0] + 0.01)
    for a in (0, 120, 240):                                          # R16 bayonet lugs (R35: attached at Z89.5)
        body = body + _radial_box(a, 17.0, 21.5, 8.0, 86.5, 89.5)
    body = body + Pos(SX + 19.25, SY, 89.75) * Cylinder(1.0, 0.5)    # R16 detent bump on the 0 deg lug
    body = body + Pos(SX + 20.4, SY, 93.5) * Box(2.0, 1.2, 1.0)      # R32 wave-spring gap key under the flange
    nx, ny = d["ntc_xy"]
    body = body + Pos(nx, (SY + 12.8 + SY + 16.0) / 2, 101.5) * Box(3.0, 3.2, 9.0)   # R36 rim-NTC rib Z97-106
    body = body - _cyl(0.9, 102.5, 106.5, nx, ny) - _cyl(0.4, 89.0, 105.0, nx, ny)  # R40 pocket, R36 lead hole
    # NTC lead entry into the splice cup: radial Ø1.0 hole on +Y at Z77.5
    body = body - Pos(SX, SY + 7.0, 77.5) * Rot(90, 0, 0) * Cylinder(0.5, 3.2)
    return body


def r3_cartridge(travel_mm: float = 0.0, tilt_mrad: float = 0.0, tilt_axis: str = "x") -> list[dict]:
    d = DIM
    t = travel_mm
    if not 0.0 <= t <= d["stroke_hard"] + 1e-9:
        raise ValueError(f"travel must be within 0..{d['stroke_hard']} mm (hard stop)")
    out = []
    chip = Pos(SX, SY, d["chip_top"] - d["chip_h2"] / 2) * Box(d["chip_w"], d["chip_l"], d["chip_h2"])
    capillary = _cyl(d["capillary_r"], *d["capillary_z"])
    moving = {
        "disc_Si3N4": (_rev(_disc_profile()), CERAMIC, "custom", "Si3N4, laser-cut from 0.32 mm power-module substrate, top lapped",
                       "Ø8.0 (-0.04/0) x 0.32 +/-0.015 disc, 0.2 x 45 top chamfer (contact Ø7.6), top flat <= 1 um, Ra <= 0.1 um. "
                       "Bonded to the neck rim and inner-tube rim (pocket Ø3.4 over the chip) and to the chip."),
        "chip_bond": (Pos(SX, SY, d["chip_top"] + d["bond_t"] / 2) * Box(d["chip_w"], d["chip_l"], d["bond_t"]), (.85, .85, .78),
                      "consumable", "EPO-TEK 930-4 (BN epoxy, k 1.7) - continuous rating OPEN; alternate Cotronics Duralco 128",
                      "0.10 +/-0.03 bondline under the disc centre (chip footprint)."),
        "Pt100_chip_IST_P0K1202": (chip, SILVER, "purchased", "Pt thin film on alumina, Pt-clad Ni leads",
                                   "IST P0K1.202.6W.A.007 1.8 x 2.0 x 0.65; modelled as its H2 1.1 lead-weld envelope (conservative)."),
        "post_polyimide": (_rev(_post_profile()), PI, "custom", "DuPont Vespel SP-1 (unfilled polyimide), machined",
                           "Single-piece post: neck tube Ø8.0 x 0.25 wall, 6.28 long; integral inner support tube Ø3.8/Ø3.4 "
                           "(chip pocket); shoulder Ø10.4 (up-stop face Z104.0); foot Ø6; R1.5 spherical nose on axis; Ø1.2 lead bore."),
        "fibre_plug_annulus": (_ring(d["neck_ro"] - d["neck_wall"], d["inner_ro"], d["neck_bot"], d["disc_bot"]), FIBRE, "custom",
                               "alumina-silica fibre paper/felt (Alkegen Fiberfrax 970 class), die-cut rings packed before disc bond",
                               "Fills the neck/inner-tube annulus: blocks radiation and convection to the post."),
        "fibre_plug_core": (_cyl(d["inner_ri"], d["neck_bot"], d["chip_bot_h2"] - 0.08) - capillary, FIBRE, "custom",
                            "alumina-silica fibre, as the annulus", "Fills the chip pocket below the chip around the leads."),
        "lead_capillary_fused_silica": (capillary, (.85, .90, .95), "purchased",
                                        "fused silica (quartz) 4-bore capillary, OD 1.0, bores Ø0.15-0.18 on a 0.30 pitch",
                                        "Hot-zone lead insulation (PCB: >= 10 MOhm at 300 C between leads): the four bare manganin Ø0.08 "
                                        "wires run one per bore from 0.5 below the chip to the nose; S+/S- and F+/F- in adjacent bores. "
                                        "The two Kelvin joints (each IST Ni lead to its two manganin wires) sit 0.3 above the capillary top, "
                                        ">= 0.3 apart in the sealed fibre-filled post. Enamel (MW 16-C) only below the capillary (<= 210 C)."),
        "foot_potting": (_cyl(d["lead_bore_r"], *d["foot_pot_z"]) - _cyl(d["capillary_r"], d["capillary_z"][0], d["foot_pot_z"][1] + 0.1)
                         - _cyl(d["sleeve_r"], d["foot_pot_z"][0] - 0.1, d["capillary_z"][0]), POT,
                         "consumable", "Cotronics Duralco 128 (ceramic-filled, 500 F / 260 C)",
                         "Pots the capillary and the PTFE lead-sleeve end in the foot bore (lead fixing; seals the post)."),
        "seat_cup_PEEK": (_rev(_cup_profile()), PALE, "custom", "PEEK 450G (unfilled), turned",
                          "Spring seat: 90 deg cone tangent to the post's R1.5 nose (on-axis seat, contact circle r1.06), "
                          "pilot for the spring, Ø1.6 lead hole; its pilot face lands on the stop tube = hard stop at 2.2 mm."),
    }
    pivot = (SX, SY, d["z_pivot"])
    ax = Axis(pivot, (1, 0, 0) if tilt_axis == "x" else (0, 1, 0))
    for name, (shape, color, kind, material, ev) in moving.items():
        s = Pos(0, 0, -t) * shape
        if tilt_mrad:
            s = s.rotate(ax, math.degrees(tilt_mrad / 1000.0))
        pn = "P0K1.202.6W.A.007" if name.startswith("Pt100") else None
        out.append(_part(name, s, color, kind, material, ev, pn))

    fixed = [
        ("body_PI", _body(), (.78, .55, .25), "custom", "DuPont Vespel SP-1 polyimide (or equal with published continuous >= 260 C), turned + milled",
         "R43 interfaces kept (spigot, flange, 3 lugs + detent, gap key, glass-datum rim r12.2-13, NTC rib/pocket). "
         "New: collar Ø16 to Z109.8 in the Ø18 bore, Ø11.0 relief with three 0.6 wide guide pads to Ø8.10 at Z109.0-109.5 (the pivot), wiper counterbore Ø12.2, "
         "O-ring gland r9.75-12.2 x 1.10 deep, Ø12.2 sealed sump bore, bayonet groove + 2 slots, splice cup, NTC lead hole."),
        ("stop_collar_PI", _ring(d["bore_main_r"], d["stop_ri"], d["stop_bot"], d["stop_top"]), (.80, .76, .62), "custom",
         "DuPont Vespel SP-1 polyimide, turned; bonded (bond-class adhesive) at fixture height",
         "Up-stop / post retention collar: Ø12.2/Ø9.0 x 1.8, pressed up behind the wiper and bonded with its bottom face "
         "set 2.000 +/-0.02 below the rim datum by fixture. Never pin-in-slot."),
        ("wiper_FFKM", _rev(_wiper_profile()), SEAL, "custom", "Kalrez 6230 FFKM (FDA 21 CFR 177.2600), moulded",
         "Sliding wiper lip: free lip ID 7.80 +/-0.04 on the Ø8.00 +/-0.01 neck (0.075-0.125 radial interference), lip 0.30 thick, "
         "pointing up; modelled installed (line-to-line)."),
        ("spring_washer_bayonet_PEEK", _rev(_washer_profile()) + _radial_box(0, 5.9, d["washer_lug_r"], d["washer_lug_w"], *d["washer_z"])
         + _radial_box(180, 5.9, d["washer_lug_r"], d["washer_lug_w"], *d["washer_z"]), (.80, .76, .62), "custom",
         "Victrex PEEK 450G, turned + milled",
         "R32-style two-lug 60 deg bayonet washer: spring seat, Ø3.6/Ø2.4 down-stop tube (top Z93.6), Ø2.0 lead hole."),
        ("spring_A286", _ring(d["spring_ro"], d["spring_ri"], d["washer_z"][1], d["cup_bot"] - t), DARK, "purchased",
         "A-286 spring wire (AMS 5731 class, aged): non-magnetic, 538 C service (Smalley materials table), open ends not ground",
         "Custom compression spring, envelope only: d 0.50, D 8.0 mean, ~6.0 active coils, open (unclosed, unground) ends "
         "so no end turn touches its neighbour; P1 1.30 +/-0.08 N at L1 15.6, P2 1.70 +/-0.08 N at L1-2.2."),
        ("static_gasket_FFKM", _rev(_oring_profile()), SEAL, "purchased", "Kalrez 6230 FFKM O-ring 20 x 1.5",
         "Face O-ring in the gland inside the rim: free CS 1.5, gland 1.10 (26.7 % squeeze), 66 % fill. Seals body to glass underside."),
        ("rim_NTC_Semitec_104GT2", _cyl(d["ntc_bead"][0] / 2, d["glass_under"] - d["ntc_bead"][1], d["glass_under"], *d["ntc_xy"]),
         DARK, "purchased", "glass-encapsulated NTC 100 k, -50..+300 C",
         "Unchanged from R40: bead tip flush at the glass datum in the Ø1.8 x 3.5 rib pocket, outside the cap."),
        ("wave_spring_A286", _ring(21.4, 19.3, 93.0, 94.0) - _radial_box(0, 19.0, 21.7, 2.0, 92.9, 94.1), SILVER, "purchased",
         "A-286 single-turn gap wave spring", "Unchanged R16/R32: custom gap-type, 3-15 N, gap held open by the PEEK key."),
        ("splice_potting", _cyl(d["bore_main_r"], *d["splice_z"])
         + _radial_box(60, 5.9, d["bay_groove_r"], d["bay_slot_w"], d["splice_z"][0], d["splice_z"][1])
         + _radial_box(240, 5.9, d["bay_groove_r"], d["bay_slot_w"], d["splice_z"][0], d["splice_z"][1])
         - _cyl(d["sleeve_r"], 75.9, 80.1) - _cyl(d["cable_r"], 74.9, 76.0), POT, "consumable",
         "Cotronics Duralco 128", "Pots the manganin-to-cable splice and the NTC lead entry; fills the bayonet slots so the sump is sealed."),
        ("cable_strain_relief_PEEK", _cyl(d["bore_main_r"], d["body_bot"], d["splice_z"][0]) + _cyl(d["relief_boss_r"], d["relief_z"][0], d["body_bot"])
         - _cyl(d["cable_r"], d["relief_z"][0] - 0.1, d["splice_z"][0] + 0.1), (.80, .76, .62), "custom", "Victrex PEEK 450G, turned",
         "Plug in the bore mouth + Ø6.6 x 6 boss; the pigtail bundle is bonded in the Ø3.4 bore (pull-out) and the potting locks the plug."),
        ("lead_sleeve_PTFE_ALLOCATION", _cyl(d["sleeve_r"], 76.0, d["capillary_z"][0] - t), DARK, "allocation", "PTFE thin-wall tubing, AWG 24 class",
         "Carries the 4 enamelled manganin wires (twisted S+/S-, F+/F-) through the sump from the foot potting to the splice potting; flexes over the stroke."),
        ("ntc_lead_ALLOCATION", _cyl(0.4, 84.0, 89.0, *d["ntc_xy"]) + (Pos(SX, SY + 11.975, 84.0) * Rot(90, 0, 0) * Cylinder(0.4, 7.85))
         + _cyl(0.4, 77.5, 84.4, SX, SY + 8.45) + (Pos(SX, SY + 7.15, 77.5) * Rot(90, 0, 0) * Cylinder(0.4, 2.7)), DARK, "allocation",
         "104GT-2 leads in PTFE micro-tube", "From the rib lead hole under the spigot, down the body side, into the splice cup at Z77.5."),
        ("pigtail_6x_M22759_12_ALLOCATION", _cyl(d["cable_r"], d["cable_bot"], 76.0), DARK, "allocation",
         "6 x AWG26 M22759/12 (PTFE, Ni-plated Cu, 260 C, 600 V) as three twisted pairs (PCB D8)",
         "Ø3.4 bundle allocation (fits six wires up to Ø1.13 each; M22759/12-26 OD to confirm) from the splice potting through the "
         "strain-relief bore, bonded there; runs the R32 RTD route at Z62 to the inline connector."),
    ]
    for name, shape, color, kind, material, ev in fixed:
        out.append(_part(name, shape, color, kind, material, ev))
    return out


PIGTAIL_ROUTE = ((SX, SY, 62.3), (10.0, 272.0, 62.0), (40.0, 285.0, 62.0), (129.5, 285.0, 62.0))   # R32 RTD route, Z62


def harness_allocations() -> list[dict]:
    """Pigtail continuation on the R32 RTD route and the inline Micro-Fit 2x3 (PCB D8) outside the coil footprint."""
    d = DIM
    tube = None
    for a, b in zip(PIGTAIL_ROUTE, PIGTAIL_ROUTE[1:]):
        v = [b[i] - a[i] for i in range(3)]
        L = math.sqrt(sum(c * c for c in v))
        seg = Solid.make_cylinder(d["cable_r"], L, Plane(origin=a, z_dir=tuple(v)))
        tube = seg if tube is None else tube + seg + Solid.make_sphere(d["cable_r"]).moved(Location(a))
    x, y, z = d["connector_xyz"]
    box = Pos(x, y, z) * Box(*d["connector_box"])
    return [dict(name="sensor_r3_pigtail_route_ALLOCATION", shape=_single(tube), color=DARK, group="harness", kind="allocation",
                 material="6 x M22759/12-26 three twisted pairs", part_number=None, subsystem="sensor_r3",
                 evidence="From the cartridge exit along the R32 RTD route at Z62 to the inline connector."),
            dict(name="sensor_r3_inline_connector_MicroFit_2x3_ALLOCATION", shape=box, color=(.9, .9, .85), group="harness",
                 kind="allocation", material="Molex Micro-Fit 3.0 43020-0600 plug / 43025-0600 receptacle, -40..+105 C",
                 part_number="43020-0600 + 43025-0600", subsystem="sensor_r3",
                 evidence="At (135, 285, 62): r 137 from the coil axis, outside the Ø247 former footprint, in the base "
                          "compartment fed by fresh intake air (R43 airflow-r32 T_in <= 50 C).")]


def half_section(parts: list[dict]) -> list[dict]:
    """Keep the x <= 0 half (cut plane through the axis, the NTC on +Y stays visible)."""
    cutter = Pos(SX + 50, SY, 90) * Box(100, 200, 120)
    out = []
    for p in parts:
        s = p["shape"] - cutter
        if s.solids():
            out.append(dict(p, shape=s))
    return out


def main():
    rest = r3_cartridge(0.0)
    export_step(Compound(children=[p["shape"] for p in rest]), str(HERE / "C1-cartridge-assembled.step"))
    export_step(Compound(children=[p["shape"] for p in half_section(rest)]), str(HERE / "C1-cartridge-half-section.step"))
    working = r3_cartridge(DIM["proud"])
    export_step(Compound(children=[p["shape"] for p in working]), str(HERE / "C1-cartridge-at-flush-0p6.step"))
    for p in rest:
        print(f"{p['name']:48s} solids={len(p['shape'].solids())} vol={p['shape'].volume:9.3f}")


if __name__ == "__main__":
    main()
