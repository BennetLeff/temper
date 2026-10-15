"""sensor-r3 C1 cartridge: every HANDOFF section A gate (G1-G12) in one rerunnable script -> checks.json.

Geometric gates run here on the build123d solids of cartridge_r3.py against the frozen R43 interfaces
(interfaces.py: glass, carrier, coil former, Litz winding, ferrite bars, coil leads). The thermal, budget,
tilt and field gates call their own scripts (thermal_axisym.py, budget_asbuilt.py, tilt_follow.py,
field_screen.py), which also write their own JSON. Overlap threshold for a collision: 1e-3 mm3 (line-to-line
contacts and bonded faces read ~0); documented compliant pairs carry their accepted maximum.
Run: python checks.py   (about 40 min; exits 1 if a gate is FAIL)
     python checks.py --only G1 G10 G11   (recompute those geometric gates into the existing checks.json)
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build123d import Axis, Box, Cylinder, Pos  # noqa: E402

import cartridge_r3 as C  # noqa: E402
import interfaces as IF  # noqa: E402

D = C.DIM
TOL = 1e-3
PFX = "sensor_r3_"
COMPLIANT = {   # (moving, fixed): max accepted overlap mm3, reason
    ("wiper_FFKM", "post_polyimide"): (0.5, "FFKM lip modelled line-to-line; tilt pushes the neck <= 0.013 mm into the 0.07-0.13 interference lip"),
    ("post_polyimide", "stop_collar_PI"): (0.3, "travel 0 only: the shoulder is seated on the up-stop face, so a 5 mrad tilt rocks "
                                                "it about the shoulder edge (0.026 mm at r5.2) instead of the pad pivot; with no pan on "
                                                "the disc there is no tilting load at travel 0, and from travel 0.03 the shoulder is clear"),
    ("seat_cup_PEEK", "spring_A286"): (1.0, "spring envelope is drawn vertical; its top coil follows the cup's 5 mrad tilt"),
}
G11_REQ = dict(clearance=3.0, creepage=8.0, solid=2.0)   # pcb/DECISIONS.md "For the CAD agent"


def vol(a, b):
    ba, bb = a.bounding_box(), b.bounding_box()
    if (ba.max.X < bb.min.X or bb.max.X < ba.min.X or ba.max.Y < bb.min.Y or bb.max.Y < ba.min.Y
            or ba.max.Z < bb.min.Z or bb.max.Z < ba.min.Z):
        return 0.0
    c = a & b
    return 0.0 if c is None else sum(s.volume for s in c.solids())


def short(n):
    return n.replace(PFX, "")


_LOCAL = {}


def ctx_fixed():
    """R43 interface solids clipped to a 64 x 64 mm box round the sensor axis (Z50-120): every cartridge part, at any
    tilt or bayonet angle, lies inside r 22, so the clip changes no overlap and makes each boolean ~50x faster."""
    if not _LOCAL:
        c = IF.context()
        clip = Pos(C.SX, C.SY, 85.0) * Box(64.0, 64.0, 70.0)
        for k, n in (("glass", "glass"), ("carrier", "carrier"), ("former", "coil_former"), ("winding", "coil_winding"),
                     ("ferrite", "ferrite_bars")):
            s = c[k] & clip
            _LOCAL[n] = s if s is not None and s.solids() else None
    return {k: v for k, v in _LOCAL.items() if v is not None}


# --------------------------------------------------------------------------- G1
def g1():
    fixed_ctx = ctx_fixed()
    rows, single, worst = [], [], {}
    states = [(t, 0.0, "x") for t in (0.0, 0.6, 1.2)]
    states += [(t, m, ax) for t in (0.0, 0.6, 1.2) for m in (-5.0, 5.0) for ax in ("x", "y")]
    for t, m, ax in states:
        parts = C.r3_cartridge(t, m, ax)
        mov = [p for p in parts if short(p["name"]) in C.MOVING]
        fix = [p for p in parts if short(p["name"]) not in C.MOVING and p["kind"] != "allocation"]
        hits = []
        for a in mov:
            for b in fix:
                v = vol(a["shape"], b["shape"])
                key = (short(a["name"]), short(b["name"]))
                lim = COMPLIANT.get(key, COMPLIANT.get((key[1], key[0]), (TOL, "")))[0]
                if v > TOL:
                    hits.append(dict(moving=key[0], fixed=key[1], volume_mm3=round(v, 4), accepted=v <= lim))
            for n, s in fixed_ctx.items():
                v = vol(a["shape"], s)
                if v > TOL:
                    hits.append(dict(moving=short(a["name"]), fixed=n, volume_mm3=round(v, 4), accepted=False))
        rows.append(dict(travel_mm=t, tilt_mrad=m, axis=ax, overlaps=hits, pass_=all(h["accepted"] for h in hits)))
        print(f"G1 travel {t} tilt {m} {ax}: {len(hits)} overlaps, {'ok' if rows[-1]['pass_'] else 'FAIL'}", flush=True)
    # fixed cartridge parts against each other and the R43 interfaces (rest), moving parts against each other (bonded)
    parts = C.r3_cartridge(0.0)
    rigid = [p for p in parts if p["kind"] != "allocation"]
    pair = []
    for i, a in enumerate(rigid):
        for b in rigid[i + 1:]:
            v = vol(a["shape"], b["shape"])
            if v > TOL:
                key = (short(a["name"]), short(b["name"]))
                lim = COMPLIANT.get(key, COMPLIANT.get((key[1], key[0]), (TOL, "")))[0]
                pair.append(dict(a=key[0], b=key[1], volume_mm3=round(v, 4), accepted=v <= lim))
        for n, s in fixed_ctx.items():
            v = vol(a["shape"], s)
            if v > TOL:
                pair.append(dict(a=short(a["name"]), b=n, volume_mm3=round(v, 4), accepted=False))
    for p in parts + C.harness_allocations():
        single.append(dict(part=short(p["name"]), solids=len(p["shape"].solids()), valid=p["shape"].is_valid))
    # allocations at nominal: the lead sleeve and cable must not cut rigid parts except where potted/bonded
    alloc_hits = []
    for p in [q for q in parts if q["kind"] == "allocation"]:
        for b in rigid:
            v = vol(p["shape"], b["shape"])
            if v > TOL:
                alloc_hits.append(dict(allocation=short(p["name"]), part=short(b["name"]), volume_mm3=round(v, 4)))
    ok = all(r["pass_"] for r in rows) and all(p_["accepted"] for p_ in pair) and all(s["solids"] == 1 and s["valid"] for s in single)
    return dict(states=rows, rest_pairwise=pair, single_body=single, allocation_overlaps_at_rest=alloc_hits,
                compliant_pairs={f"{k[0]}|{k[1]}": v for k, v in COMPLIANT.items()},
                pivot={"z": D["z_pivot"], "tilt_axes": ["world X", "world Y"], "about": "guide-pad centre on the axis"},
                status="PASS" if ok else "FAIL")


# --------------------------------------------------------------------------- G2
def g2():
    glass = ctx_fixed()["glass"]
    rest = {short(p["name"]): p["shape"] for p in C.r3_cartridge(0.0)}
    disc_top = rest["disc_Si3N4"].bounding_box().max.Z
    glass_bb = glass.bounding_box()
    # the bore from the shape: section the glass at mid-thickness through the sensor axis
    bore = None
    for r in [x / 100 for x in range(880, 960)]:
        probe = Pos(C.SX + r, C.SY, 108.0) * Box(0.005, 0.005, 0.005)
        if vol(probe, glass) > 0:
            bore = r
            break
    chain = [  # (item, nominal mm, +/- mm, sign) in the direction rim datum -> disc top, minus the glass
        ("stop-collar face below the rim datum (fixture-bonded)", 2.000, 0.020, -1),
        ("post: shoulder face to neck top (one turning setup)", 6.270, 0.015, +1),
        ("disc-to-neck glue line (0.00-0.02)", 0.010, 0.010, +1),
        ("Si3N4 disc thickness (lapped)", 0.320, 0.015, +1),
        ("glass thickness at the bore (RFQ requirement, see DECISIONS)", 4.000, 0.030, -1),
    ]
    nom = sum(s * n for _, n, _, s in chain)
    tol = sum(t for _, _, t, _ in chain)
    tol_cart = sum(t for i, _, t, _ in chain if "glass" not in i)
    stroke_chain = [
        ("stop-collar face (fixture)", 0.020), ("post shoulder face to nose sphere centre", 0.020),
        ("cup cone to pilot underside", 0.020), ("washer seat to stop-tube top", 0.020), ("body: rim datum to groove floor", 0.010),
    ]
    st_tol = sum(t for _, t in stroke_chain)
    worst_proud = nom + tol
    out = dict(
        glass_top=glass_bb.max.Z, glass_underside=glass_bb.min.Z, glass_bore_radius_from_shape=bore,
        disc_top_at_rest=round(disc_top, 3), protrusion_cad=round(disc_top - glass_bb.max.Z, 3),
        chain=[dict(item=i, nominal=n, tol=t, sign=s) for i, n, t, s in chain],
        protrusion_nominal=round(nom, 3), protrusion_worst=[round(nom - tol, 3), round(nom + tol, 3)],
        cartridge_only_tol=round(tol_cart, 3),
        stroke_to_hard_stop_nominal=D["stroke_hard"], stroke_chain=stroke_chain, stroke_tol=round(st_tol, 3),
        stroke_min=round(D["stroke_hard"] - st_tol, 3),
        disc_at_hard_stop_below_glass_worst=round(D["stroke_hard"] - st_tol - worst_proud, 3),
        up_stop="post shoulder face Z104.0 against the stop-collar face at rest; spring P1 1.30 N holds it",
        notes="CAD shows the disc line-to-line on a 6.28 neck (= 6.27 neck + 0.01 mean glue line).",
    )
    ok = (abs(nom - 0.60) < 1e-6 and nom - tol >= 0.50 - 1e-9 and nom + tol <= 0.70 + 1e-9 and abs(out["protrusion_cad"] - 0.6) < 1e-6
          and out["stroke_min"] >= 1.2 and out["disc_at_hard_stop_below_glass_worst"] > 0 and bore is not None and abs(bore - 9.0) < 0.02)
    out["status"] = "PASS" if ok else "FAIL"
    out["condition"] = "glass thickness 4.00 +/-0.03 within Ø40 of the bore must go on the glass RFQ (interface change)"
    return out


# --------------------------------------------------------------------------- G9
def g9():
    t = D["stroke_hard"]
    parts = C.r3_cartridge(t)
    region = Pos(C.SX, C.SY, (D["washer_z"][1] + D["wiper_bot"]) / 2) * Cylinder(
        D["bore_main_r"], D["wiper_bot"] - D["washer_z"][1])
    occupied = 0.0
    for p in parts:
        occupied += vol(region, p["shape"])
    free = region.volume - occupied
    body = next(p["shape"] for p in parts if short(p["name"]) == "body_PI")
    seals = [
        "top: FFKM wiper lip on the neck (the only intended inlet), wiper OD press-sealed in the Ø12.2 counterbore",
        "side: one-piece polyimide body bore (no through holes between Z81 and Z105.8; the NTC lead hole is outside at r14.5)",
        "stop collar: bonded round its OD (liquid passes its 0.5 mm bore gap into the sump, by design)",
        "post: closed by the bonded disc on top and the foot potting at the nose; fibre and leads stay dry",
        "bottom: bayonet washer on the groove floor; the splice potting fills Z75-80 and both bayonet slots",
        "leads through the sump: inside the PTFE sleeve, potted at both ends",
    ]
    hole_check = vol(body, region)
    ok = free >= 2000.0 and hole_check < 1e-3
    return dict(sump_region="Ø12.2 bore from the washer top Z81.0 to the wiper underside Z105.8, post at full 2.2 mm stroke",
                sump_free_volume_mm3=round(free, 1), required_mm3=2000.0, body_intrusion_mm3=round(hole_check, 4),
                seal_boundaries=seals,
                no_path=["coil: the sump wall is the body; the eye side of the body sees only the glass-sealed O-ring gland",
                         "leads: sealed sleeve + potting; carrier electronics: below the potted body bottom"],
                status="PASS" if ok else "FAIL")


# --------------------------------------------------------------------------- G10
def g10():
    fixed = {k: v for k, v in ctx_fixed().items() if k != "glass"}
    parts = C.r3_cartridge(0.0)
    # R43 check_assembly_sequence 'bayonet' poses: drop with the lugs in the notches at +60 deg, then turn at Z0 (the hand holds
    # the cartridge down 0.5 on the wave spring while turning, so the detent bump clears the carrier underside)
    poses = [(0, 0, z, 60) for z in (60, 40, 25, 15, 10, 8, 6, 4, 3, 2, 1, 0.5, 0)] + [(0, 0, 0, a) for a in range(55, -1, -5)]
    axis = Axis((C.SX, C.SY, 0), (0, 0, 1))
    steps = []
    for dx, dy, dz, ang in poses:
        hits = []
        for p in parts:
            s = Pos(dx, dy, dz) * p["shape"].rotate(axis, ang)
            for n, f in fixed.items():
                v = vol(s, f)
                if v > TOL:
                    hits.append(dict(part=short(p["name"]), fixed=n, volume_mm3=round(v, 4)))
        steps.append(dict(lift_mm=dz, rotation_deg=ang, collisions=hits))
        print(f"G10 lift {dz} rot {ang}: {len(hits)}", flush=True)
    # cover off: wave spring lifts the body 0.5, lugs on the carrier underside, detent bump in the dimple
    carrier = fixed["carrier"]
    body = next(p["shape"] for p in parts if short(p["name"]) == "body_PI")
    lifted = Pos(0, 0, 0.5) * body
    bump = Pos(C.SX + 19.25, C.SY, 90.25) * Cylinder(1.0, 0.5)
    detent = dict(bump_in_carrier_overlap_mm3=round(vol(bump, carrier), 4), lifted_body_carrier_overlap_mm3=round(vol(lifted, carrier), 4))
    # if the hand lets go mid-turn, the wave spring lifts the body 0.5: the only interference is then the detent bump riding on the
    # carrier underside (the detent action itself), checked by removing the bump from the body
    ride = []
    no_bump = body - Pos(C.SX + 19.25, C.SY, 89.75) * Cylinder(1.05, 0.55)
    for ang in (45, 30, 15, 5):
        s = Pos(0, 0, 0.5) * body.rotate(axis, ang)
        s2 = Pos(0, 0, 0.5) * no_bump.rotate(axis, ang)
        ride.append(dict(rotation_deg=ang, body_with_bump_mm3=round(vol(s, carrier), 4), body_without_bump_mm3=round(vol(s2, carrier), 4)))
    detent["turn_released_0p5_lift"] = ride
    detent["bump_volume_mm3"] = round(math.pi * 1.0 ** 2 * 0.5, 3)
    # cover on: glass lowered over the lifted cartridge until it meets the rim, then pushes it down 0.5
    glass = ctx_fixed()["glass"]
    cover = []
    for gz in (30, 15, 8, 4, 2, 1, 0.5):
        hits = []
        g = Pos(0, 0, gz) * glass
        for p in parts:
            v = vol(Pos(0, 0, 0.5) * p["shape"], g)
            if v > TOL:
                hits.append(dict(part=short(p["name"]), volume_mm3=round(v, 4)))
        cover.append(dict(glass_raised_mm=gz, cartridge_raised_mm=0.5, collisions=hits))
    ok = (all(not s["collisions"] for s in steps) and detent["bump_in_carrier_overlap_mm3"] < TOL
          and detent["lifted_body_carrier_overlap_mm3"] < TOL and all(not c["collisions"] for c in cover)
          and all(r["body_without_bump_mm3"] < TOL for r in ride))
    return dict(bayonet_sweep=steps, cover_off_detent=detent, cover_on_glass_lowering=cover,
                final_state="travel-0 assembly = G1 rest state (glass seated on the rim, body pushed down 0.5 onto the wave spring)",
                method="R43 check_assembly_sequence 'bayonet' path: drop with the lugs in the notches (+60 deg), then turn to 0",
                status="PASS" if ok else "FAIL")


# --------------------------------------------------------------------------- G11
def coil_leads():
    import r34_world as R
    from build123d import Plane, Solid
    shapes = []
    for name, pts in R.lead_points().items():
        for a, b in zip(pts, pts[1:]):
            v = [b[i] - a[i] for i in range(3)]
            L = math.sqrt(sum(c * c for c in v))
            if L > 1e-6:
                shapes.append(Solid.make_cylinder(R.D_LEAD / 2, L, Plane(origin=a, z_dir=tuple(v))))
    out = shapes[0]
    for s in shapes[1:]:
        out = out + s
    return out


X_PD3 = 1.5   # IEC/UL 60664-1 creepage "X" for pollution degree 3: a floating-part gap narrower than X is not counted


def g11():
    c = IF.context()
    tank = {"coil_winding": c["winding"], "coil_leads (polyline tubes)": coil_leads(), "ferrite_bars": c["ferrite"]}
    parts = {short(p["name"]): p["shape"] for p in C.r3_cartridge(0.0) + C.harness_allocations()}
    selv = ["Pt100_chip_IST_P0K1202", "lead_capillary_fused_silica", "rim_NTC_Semitec_104GT2", "ntc_lead_ALLOCATION",
            "lead_sleeve_PTFE_ALLOCATION", "splice_potting", "pigtail_6x_M22759_12_ALLOCATION", "pigtail_route_ALLOCATION",
            "inline_connector_MicroFit_2x3_ALLOCATION"]
    floating = ["spring_A286", "wave_spring_A286"]
    rows = []
    for s in selv + floating:
        for n, tsh in tank.items():
            dmin = parts[s].distance_to(tsh)
            row = dict(cartridge_part=s, kind="SELV conductor envelope" if s in selv else "floating metal", tank_part=n,
                       clearance_mm=round(dmin, 2), clearance_ok=dmin >= G11_REQ["clearance"])
            if s in selv:
                row.update(creepage_lower_bound_mm=round(dmin, 2), creepage_ok=dmin >= G11_REQ["creepage"],
                           creepage_basis="straight distance (any surface path is longer)")
            else:
                d2 = {q: parts[s].distance_to(parts[q]) for q in selv}
                q, dq = min(d2.items(), key=lambda kv: kv[1])
                series = dmin + dq
                row.update(direct_mm=round(dmin, 2), nearest_selv=q, float_to_selv_mm=round(dq, 2), series_path_mm=round(series, 2),
                           creepage_lower_bound_mm=round(max(dmin, series if min(dmin, dq) >= X_PD3 else dmin), 2),
                           creepage_ok=dmin >= G11_REQ["creepage"] or (series >= G11_REQ["creepage"] and min(dmin, dq) >= X_PD3),
                           creepage_basis="direct distance if >= 8 (part treated as a SELV conductor), else the series path "
                                          "tank -> floating part -> nearest SELV conductor with both legs >= X")
            rows.append(row)
    worst_clear = min(rows, key=lambda r: r["clearance_mm"])
    worst_creep = min(rows, key=lambda r: r["creepage_lower_bound_mm"])
    ok = all(r["clearance_ok"] and r["creepage_ok"] for r in rows)
    return dict(requirement=G11_REQ, source="pcb/DECISIONS.md (reinforced, 242 V rms / 640 V pk, PD3, group III; ferrite as tank; "
                                            "floating spring metal counted as a conductor)",
                rows=rows, worst_clearance=worst_clear, worst_creepage=worst_creep,
                method="3-D minimum distance between solids. SELV parts: the straight distance bounds both clearance and creepage "
                       "from below. Floating metal (main spring, wave spring): it touches no SELV conductor, so the tank-to-SELV "
                       "path through it is the sum of its two legs (60664-1 floating-part rule, legs narrower than X = 1.5 mm at "
                       "PD3 not counted); its direct distance to the tank must still meet the 3.0 clearance. No solid insulation "
                       "is credited. Allocations (leads, pigtail, splice potting, connector) are conductor envelopes.",
                status="PASS" if ok else "FAIL")


# --------------------------------------------------------------------------- G12
P1_RULES = ["flexible diaphragm or boot receiving the sensor", "slot in the sensor with a flange in it", "pins in side slots as stops",
            "plunger inner column + outer cap with the spring nested between", "compliant bumper under the sensor holder",
            "sliding ramp clamp", "heater or deliberate self-heating", "second temperature sensor under the cap",
            "plunger position sensor", "actuator that moves the sensor", "counterbore in the glass to seat the probe"]
P1_TABLE = [
    ("disc_Si3N4", "Passive ceramic contact disc; no sheet-metal cap (Impulse dep. 16 not met: ceramic, not nonferrous sheet).", []),
    ("Pt100_chip_IST_P0K1202", "The one under-cap sensor; biased only by the MAX31865's continuous measuring current (PCB D7), never "
     "pulsed or used as a heater.", []),
    ("chip_bond", "Adhesive layer.", []),
    ("post_polyimide", "Single-piece post. Its inner support tube is integral and the spring is NOT between it and the neck "
     "(the spring is below the foot) -> not the column/cap/spring nest. Rocking comes from the three rigid guide pads.", []),
    ("fibre_plug_annulus / fibre_plug_core", "Passive insulation, not compliant support (the post is rigid; nothing rests on fibre).", []),
    ("lead_capillary_fused_silica", "Lead insulator only.", []),
    ("foot_potting / splice_potting", "Lead fixing.", []),
    ("seat_cup_PEEK", "Rigid sphere-on-cone seat: a spring seat, not a compliant bumper; it does not grip the post.", []),
    ("body_PI", "Rigid body; three fixed guide pads (no slots, no ramps). Glass-datum rim on the flat underside; the glass is "
     "a plain Ø18 through bore (R43 study 08), no counterbore.", []),
    ("stop_collar_PI", "Up-stop is a flat shoulder on the post against a bonded collar - a stop collar, not a pin or a slot/flange.", []),
    ("wiper_FFKM", "Sliding wiper lip: the neck slides through it; the lip neither flexes to give the stroke nor carries the "
     "sensor (counsel item on US11378463B2 'flexible diaphragm' stays open).", []),
    ("spring_washer_bayonet_PEEK", "Fixed seat and hard stop; bayonet lugs are on the washer into a groove (assembly), not "
     "pins running in slots as stroke stops.", []),
    ("spring_A286", "Plain coil spring under the foot; no actuator.", []),
    ("static_gasket_FFKM", "Static O-ring between rigid body and glass underside; does not receive the sensor.", []),
    ("rim_NTC_Semitec_104GT2", "Outside the cap, in the body rib on the glass (US10278238B2: only the Pt100 is under the cap).", []),
    ("wave_spring_A286", "Body float (R16), not on the sensor.", []),
    ("cable_strain_relief_PEEK / allocations", "Passive.", []),
]


def g12():
    return dict(rules=P1_RULES, table=[dict(part=p, finding=f, rules_hit=h) for p, f, h in P1_TABLE],
                not_present=["no plunger position sensor of any kind", "no heater", "no actuator", "no glass counterbore"],
                status="PASS" if all(not h for _, _, h in P1_TABLE) else "FAIL")


# --------------------------------------------------------------------------- G8 ratings
RATINGS = [  # part key in thermal-axisym worst_by_part, material, continuous rating C, source, UL RTI, RTI source
    ("disc_Si3N4", "Si3N4 ceramic", 1000, "inorganic; sintered Si3N4 substrate (no polymer)", None, "n/a (ceramic)"),
    ("Pt100_chip_IST_P0K1202", "IST P0K1.202 Pt100", 600, "IST datasheet P0K1.202.6W.A.007 (-200..+600 C), quoted in R43 sensor_coil_r5", None, "n/a"),
    ("chip_bond", "EPO-TEK 930-4", None, "EPO-TEK 930-4 TDS (Sept 2024): '< 325 C (Intermittent)', Tg >= 90 C; NO continuous rating -> OPEN. "
     "Alternate Cotronics Duralco 128: 'Max. Temperature 500 F' (260 C), 10^15 ohm-cm, 30 BTU in/ft2 h F", None, "n/a (consumable)"),
    ("post_top_1mm", "DuPont Vespel SP-1", 288, "288 C continuous (Par Group Vespel rod listing; DuPont SP-1 sheet gives no continuous figure) -> "
     "confirm with DuPont", None, "UL file E530329 exists for SP-1 DF; RTI values unread -> OPEN"),
    ("body_collar_in_bore", "DuPont Vespel SP-1", 288, "as post", None, "as post -> OPEN"),
    ("stop_collar_PI", "DuPont Vespel SP-1", 288, "as post", None, "as post -> OPEN"),
    ("guide_pads_equiv_ring", "DuPont Vespel SP-1 (body pads)", 288, "as post", None, "as post -> OPEN"),
    ("wiper_lip_tip", "Kalrez 6230 FFKM (FDA 21 CFR 177.2600)", 260, "DuPont Kalrez 6230 product page: maximum application temperature 260 C", None,
     "elastomer, not insulation (SELV) -> not required"),
    ("static_gasket_FFKM", "Kalrez 6230 FFKM", 260, "as wiper", None, "not insulation -> not required"),
    ("fibre_plug_annulus", "alumina-silica fibre", 1260, "Fiberfrax 970 class, 2300 F (retailer listing; Alkegen A-5264 brochure)", None, "n/a (inorganic)"),
    ("lead_capillary_fused_silica", "fused silica", 1000, "fused quartz, softening > 1600 C; 7e7 ohm-cm at 350 C (UQG Optics sheet, lowest found)", None, "n/a"),
    ("foot_potting", "Cotronics Duralco 128", 260, "Duralco sheet: Max. Temperature 500 F", None, "consumable"),
    ("seat_cup_PEEK", "Victrex PEEK 450G", 240, "Victrex 450G TDS: RTI mech w/o impact 240, w/ impact 180, elec 260", 240, "Victrex 450G TDS (UL 746B)"),
    ("spring_washer_bayonet_PEEK", "Victrex PEEK 450G", 240, "as cup", 240, "as cup"),
    ("cable_strain_relief_PEEK", "Victrex PEEK 450G", 240, "as cup", 240, "as cup"),
    ("splice_potting", "Cotronics Duralco 128", 260, "Duralco sheet", None, "consumable"),
    ("spring_A286", "A-286 spring wire", 538, "Smalley materials table (R43 design/r16/parts-research.md)", None, "n/a (metal)"),
    ("cable", "M22759/12 PTFE pigtail (PCB D8)", 260, "MIL-W-22759/12: 260 C (PCB DECISIONS)", 180, "UL 746B Table 7.1 generic PTFE 180 (informational)"),
    ("glass_underside_at_rim_NTC_r14.5", "Semitec 104GT-2", 300, "Semitec GT-2 sheet via R40: -50..+300 C", None, "n/a"),
]


def g8():
    th = json.loads((HERE / "thermal-axisym.json").read_text())["worst_by_part"]
    rows, opens = [], []
    for key, mat, rating, src, rti, rti_src in RATINGS:
        t = th[key]["max"]
        if rating is None:
            status = "OPEN"
            opens.append(key)
        else:
            status = "PASS" if t <= rating else "FAIL"
        rti_flag = None if rti is None else ("OK" if t <= rti else "EXCEEDED")
        if "OPEN" in rti_src:
            rti_flag = "OPEN"
            opens.append(f"{key}: UL RTI")
        rows.append(dict(part=key, material=mat, T_max_C=t, case=th[key]["case"], continuous_rating_C=rating, rating_source=src,
                         UL_RTI_C=rti, RTI_source=rti_src, RTI_check=rti_flag, status=status))
    wiper = th["wiper_FFKM"]["max"]
    choice = dict(wiper_T_max_C=wiper, rule="PTFE if <= 250 C else FFKM (HANDOFF)",
                  decision="FFKM Kalrez 6230: modelled 243.5 C max leaves PTFE allowed by the letter, but an unenergised PTFE lip "
                           "takes a permanent set at ~240-250 C and no metal energiser is allowed in the eye (G7); see DECISIONS D5")
    status = "FAIL" if any(r["status"] == "FAIL" for r in rows) else ("OPEN" if opens else "PASS")
    return dict(T_pan_C=260, rows=rows, open_items=opens, wiper_material=choice,
                inline_connector=dict(location=list(D["connector_xyz"]), air_C=50,
                                      basis="base compartment fed by fresh intake air: R43 evidence/airflow-r32/coil_thermal.py "
                                            "T_in 35-50 C (50 C-room cases); not in the 2-D model; bench EM2 thermocouple to confirm",
                                      rating_C=105, required_air_C=85, status="PASS"),
                status=status)


def rerun(names):
    """Recompute only the named geometric gates (e.g. G1 G10 G11) into the existing checks.json."""
    out = json.loads((HERE / "checks.json").read_text())
    fn = {"G1": ("G1 collisions", g1), "G2": ("G2 protrusion and stroke", g2), "G8": ("G8 temperatures and ratings", g8),
          "G9": ("G9 spill", g9), "G10": ("G10 assembly", g10), "G11": ("G11 insulation geometry", g11), "G12": ("G12 P1 audit", g12)}
    for n in names:
        key, f = fn[n]
        out["gates"][key] = f()
        out["summary"][key] = out["gates"][key]["status"]
    (HERE / "checks.json").write_text(json.dumps(out, indent=1, default=lambda o: float(o) if hasattr(o, "__float__") else str(o)) + "\n")
    for k, v in out["summary"].items():
        print(f"{v:5s} {k}")
    sys.exit(1 if "FAIL" in out["summary"].values() else 0)


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--only":
        rerun(sys.argv[2:])
    t0 = time.time()
    import budget_asbuilt
    import field_screen
    import thermal_axisym
    import tilt_follow
    th = thermal_axisym.main()
    bud = budget_asbuilt.main()
    tf = tilt_follow.main()
    fs = field_screen.main()
    gates = {}
    gates["G1 collisions"] = g1()
    gates["G2 protrusion and stroke"] = g2()
    gates["G3 heat capacity"] = dict(C_cap_mJ_K=bud["results"]["C_cap_mJ_per_K"], effusivity_estimate=bud["results"]["C_cap_effusivity_estimate_mJ_per_K"],
                                     limit=45.0, status="PASS" if bud["gate_pass"]["G3 C_cap (budget method)"] else "FAIL")
    gates["G4 cold leak"] = dict(G_cold_mW_K=bud["results"]["G_cold_gated_mW_per_K"], G_hot_mW_K=bud["results"]["G_hot_to_collar_and_pan_side_mW_per_K"],
                                 hand_calc_into_post=bud["results"]["G_into_post_hand_upper_bound_mW_per_K"], limit=0.8,
                                 status="PASS" if bud["gate_pass"]["G4 cold leak (FV split, worst incl. sensitivity)"] else "FAIL")
    gates["G5 tilt follow, spring, friction"] = dict(worst_residual_tilt_mrad=tf["worst_residual_tilt_mrad"], M_total_Nmm=tf["M_total_Nmm"],
                                                     capacity_Nmm=tf["righting_capacity_Nmm_F_min_x_r_contact"], pivot=tf["geometry_mm"],
                                                     spring=tf["spring"], wiper=tf["lip"],
                                                     status="PASS" if (tf["pass_G5"] and tf["spring"]["pass_force"] and tf["spring"]["pass_stress"]
                                                                       and tf["lip"]["pass_friction_le_0.3N"] and tf["lip"]["pass_contact_positive"]) else "FAIL")
    gates["G6 disc strength"] = dict(stress_MPa=bud["results"]["disc_stress_MPa_over_pocket"], SF_20N=bud["results"]["disc_SF_at_20N"],
                                     pocket_d_mm=2 * D["inner_ri"], ball_drop=bud["results"]["ball_drop"],
                                     status="PASS" if bud["gate_pass"]["G6 disc strength over the pocket"] and bud["gate_pass"]["G6 ball drop ends on the glass"] else "FAIL")
    gates["G7 field"] = dict(geometry=fs["geometry"], at_FEM_field=fs["at_study06_FEM_field"], sweep_extreme_dT_K=fs["spring_dT_K_at_sweep_extreme"],
                             capillary_pickup=fs["capillary_pair_pickup"], flag=fs["flag"],
                             status="PASS" if fs["pass_geometry"] and fs["pass_heating"] else "FAIL")
    gates["G8 temperatures and ratings"] = g8()
    gates["G9 spill"] = g9()
    gates["G10 assembly"] = g10()
    gates["G11 insulation geometry"] = g11()
    gates["G12 P1 audit"] = g12()
    summary = {k: v["status"] for k, v in gates.items()}
    out = {"scope": __doc__.strip(), "summary": summary, "gates": gates, "runtime_s": round(time.time() - t0, 1)}
    (HERE / "checks.json").write_text(json.dumps(out, indent=1, default=lambda o: float(o) if hasattr(o, "__float__") else str(o)) + "\n")
    for k, v in summary.items():
        print(f"{v:5s} {k}")
    sys.exit(1 if "FAIL" in summary.values() else 0)


if __name__ == "__main__":
    main()
