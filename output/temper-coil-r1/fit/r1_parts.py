"""coil-r1 parts in the R43 enclosure's world frame, for the fit study (output/temper-coil-r1/fit/).

Builds, in R43 world mm (coil axis at (0, 261), carrier top Z93, glass underside Z106):
  - the R1 former at the design bundle (Remington 260/38LITZ, OD 0.090 in = 2.29 mm max), CNC (notch +0.2) and print
    (notch +0.3, five pinned/lapped segments) variants, from cad/former.py;
  - the R1 winding solid on the R1 notch table (14.47 inner + 6.46 outer turns, bundle 2.29 on the 1 mm roof), with a
    smooth crossover (tangent-continuous cubic from the inner end at 75 deg to the outer start at 90 deg), in two states:
    R1 as tuned and as wound with the spare outer turn (7.46 outer turns, end r118.1);
  - the two lead exits as R43 routes them, re-dimensioned for the 2.29 bundle in its fibreglass sleeve: the J2 (outer)
    lead along a chord to the rim hole and straight down, the J5 (centre) lead over the inner section at Z_CROSS, along
    the gap ring and down between spokes; both end in the lug barrel top;
  - the coil NTC bead at the R1 bore (the bore moves with the last inner turn);
  - the J2/J5 ring lugs (lug.py), seated on the Wurth 7466004R terminal top.
R43 is read-only: its src/ is imported for the route filleting helper only (no bytecode written).
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
R43 = Path("/Users/bennet/Desktop/temper/output/temper-manufacturing-r43")
sys.path.insert(0, str(HERE.parent / "cad"))
sys.path.insert(0, str(R43 / "src"))

from build123d import Compound, Edge, Face, Plane, Pos, Solid, Vector, Wire  # noqa: E402

import former as F  # noqa: E402
import geom as K  # noqa: E402
from geom import G  # noqa: E402
from harness_r19 import _fillet  # noqa: E402  (R43, read-only)
from harness_r11 import _tube  # noqa: E402  (R43, read-only)

import lug as LUG  # noqa: E402

CX, CY = 0.0, 261.0
W0 = Pos(CX, CY, K.Z0_WORLD)                       # former local -> world
BUNDLE = K.BUNDLE_R1                               # 2.29 design OD (maximum per the product page)
SLEEVE_ID, SLEEVE_WALL = LUG.SLEEVE["id_mm"], LUG.SLEEVE["wall_mm"]
LEAD_OD = SLEEVE_ID + 2 * SLEEVE_WALL              # sleeved lead envelope
Z_ROOF_TOP = G.Z_ROOF[1]                           # 99.0
Z_WIND = Z_ROOF_TOP + BUNDLE / 2                   # 100.145 bundle centre
Z_WIND_TOP = Z_ROOF_TOP + BUNDLE                   # 101.29
Z_COMB_TOP = Z_ROOF_TOP + BUNDLE + 0.2             # 101.49 (cad/former.py)
Z_GLASS = G.GLASS[0]                               # 106.0
# Centre-lead crossing over the inner section. R43 held it 0.5 mm over the comb-top plane, but the -125 deg crossing ray
# runs mid-gap (combs only +/-2 mm about the -113/-149 deg spokes) and the gap-ring run has no comb, so the sleeved lead
# can rest on the turn tops: that keeps the thicker sleeved lead (3.55 mm) further from the 230-250 C glass underside.
Z_CROSS = Z_WIND_TOP + LEAD_OD / 2
Z_GAPRING = Z_ROOF_TOP + 0.3 + LEAD_OD / 2          # lead along the gap ring, over the -113 deg spoke roof
TH_J2 = math.degrees(math.atan2(K.J2[1], K.J2[0]))  # -94.3
TH_J5 = math.degrees(math.atan2(K.J5[1], K.J5[0]))  # -95.9
R_GAP_LEAD = math.hypot(*K.J5)                      # 87.9
TH_C = -125.0                                       # R43 crossing ray
J2W = (CX + K.J2[0], CY + K.J2[1])
J5W = (CX + K.J5[0], CY + K.J5[1])
J2_HOLE_R = max(K.D_LEAD / 2 + 1.0, LEAD_OD / 2 + 0.5)
assert J2_HOLE_R <= F.LEAD_HOLE_R + 1e-9, "cad/former.py LEAD_HOLE_R is smaller than the sleeved lead needs"
J2_HOLE_R = F.LEAD_HOLE_R


def P(r, th, z):
    return (CX + r * math.cos(math.radians(th)), CY + r * math.sin(math.radians(th)), z)


def spiral_xy(sp, th):
    r0, r1, th0, th1 = sp
    return r0 + (r1 - r0) * (th - th0) / (th1 - th0)


def spiral_tangent(sp, th):
    """Unit tangent (CCW) of the Archimedean spiral at angle th, world xy."""
    r0, r1, th0, th1 = sp
    r = spiral_xy(sp, th)
    drdth = (r1 - r0) / math.radians(th1 - th0)
    t = math.radians(th)
    v = (drdth * math.cos(t) - r * math.sin(t), drdth * math.sin(t) + r * math.cos(t))
    n = math.hypot(*v)
    return (v[0] / n, v[1] / n)


def spirals(state="R1"):
    spare = 1.0 if state == "spare" else 0.0
    return K.spirals(G.R1, spare)


COMB_CLEAR = 0.5           # the bundle stays tangential (in its notch) for this far past each comb strip's edge


def _hermite(a, b, ta, tb, m, n):
    pts, rmin = [], math.inf
    for i in range(n + 1):
        s = i / n
        h = (2 * s ** 3 - 3 * s ** 2 + 1, s ** 3 - 2 * s ** 2 + s, -2 * s ** 3 + 3 * s ** 2, s ** 3 - s ** 2)
        d = (6 * s ** 2 - 6 * s, 3 * s ** 2 - 4 * s + 1, -6 * s ** 2 + 6 * s, 3 * s ** 2 - 2 * s)
        e = (12 * s - 6, 6 * s - 4, -12 * s + 6, 6 * s - 2)
        f = [(a[j], ta[j] * m, b[j], tb[j] * m) for j in (0, 1)]
        x, y = (sum(c * v for c, v in zip(h, f[j])) for j in (0, 1))
        dx, dy = (sum(c * v for c, v in zip(d, f[j])) for j in (0, 1))
        ddx, ddy = (sum(c * v for c, v in zip(e, f[j])) for j in (0, 1))
        k = abs(dx * ddy - dy * ddx) / (dx * dx + dy * dy) ** 1.5
        rmin = min(rmin, 1 / k if k > 1e-12 else math.inf)
        pts.append((x, y, Z_WIND))
    return pts, rmin


def crossover_span(inner, outer):
    """Angles where the bundle leaves the last inner comb strip before the inner end and enters the first outer comb strip
    after the outer start (the notch table fixes the bundle only at the spokes; between them it is free)."""
    th_in_end, th_out0 = inner[3], outer[2]
    sp_a = max(a for a in (b + 360 * k for b in G.bar_angles() for k in range(-1, 40)) if a <= th_in_end)
    sp_b = min(a for a in (b + 360 * k for b in G.bar_angles() for k in range(-1, 40)) if a >= th_out0)
    ra, rb = spiral_xy(inner, sp_a), spiral_xy(outer, sp_b)
    tha = sp_a + math.degrees((K.COMB_W / 2 + COMB_CLEAR) / ra)
    thb = sp_b - math.degrees((K.COMB_W / 2 + COMB_CLEAR) / rb)
    return tha, thb, sp_a, sp_b


def crossover(inner, outer, n=60):
    """Cubic Hermite (tangent-continuous with both spirals) across the free span between the last inner comb strip and
    the first outer one, with the tangent scale that maximises the smallest radius of curvature. Returns sampled world
    points, that radius, the free span and, for reference, the kink a straight chord between the nominal 75/90 deg
    section ends would make."""
    tha, thb, sp_a, sp_b = crossover_span(inner, outer)
    a = P(spiral_xy(inner, tha), tha, Z_WIND)[:2]
    b = P(spiral_xy(outer, thb), thb, Z_WIND)[:2]
    ta, tb = spiral_tangent(inner, tha), spiral_tangent(outer, thb)
    chord = math.dist(a, b)
    best = max(((m, _hermite(a, b, ta, tb, m * chord, n)[1]) for m in [0.3 + 0.02 * i for i in range(86)]), key=lambda x: x[1])
    pts, rmin = _hermite(a, b, ta, tb, best[0] * chord, n)
    a0, b0 = P(inner[1], inner[3], Z_WIND)[:2], P(outer[0], outer[2], Z_WIND)[:2]
    t0, t1 = spiral_tangent(inner, inner[3]), spiral_tangent(outer, outer[2])
    c0 = math.dist(a0, b0)
    kink = dict(inner_end_deg=math.degrees(math.acos((t0[0] * (b0[0] - a0[0]) + t0[1] * (b0[1] - a0[1])) / c0)),
                outer_start_deg=math.degrees(math.acos((t1[0] * (b0[0] - a0[0]) + t1[1] * (b0[1] - a0[1])) / c0)))
    span = dict(from_deg=tha, to_deg=thb, spokes_deg=[sp_a % 360, sp_b % 360], r_from=spiral_xy(inner, tha),
                r_to=spiral_xy(outer, thb), tangent_scale=best[0])
    return pts, rmin, span, kink, (tha, thb)


def sweep(pts, d, t0=None, t1=None):
    vec = [Vector(*p) for p in pts]
    edge = Edge.make_spline(vec, tangents=[Vector(*t0), Vector(*t1)]) if t0 is not None else Edge.make_spline(vec)
    path = Wire([edge])
    prof = Wire.make_circle(d / 2, Plane(origin=pts[0], z_dir=path.tangent_at(0)))
    return Solid.sweep(Face(prof), path), path.length


def winding(state="R1"):
    inner, outer = spirals(state)
    xp, xr, xspan, kink, (tha, thb) = crossover(inner, outer)
    inner_c, outer_c = (inner[0], inner[1], inner[2], tha), (outer[0], outer[1], thb, outer[3])
    si = [P(*q) for q in [(spiral_xy(inner, th), th, Z_WIND) for th in _angles(inner_c)]]
    so = [P(*q) for q in [(spiral_xy(outer, th), th, Z_WIND) for th in _angles(outer_c)]]
    s_in, l_in = sweep(si, BUNDLE)      # splines through the sampled points (end tangents left free: OCCT scales given
    s_out, l_out = sweep(so, BUNDLE)    # unit tangents badly and the spiral came out 11 % long)
    s_x, l_x = sweep(xp, BUNDLE)
    info = dict(state=state, inner_turns=(inner[3] - inner[2]) / 360, outer_turns=(outer[3] - outer[2]) / 360,
                length_mm=l_in + l_out + l_x, inner_mm=l_in, outer_mm=l_out, crossover_mm=l_x,
                crossover_min_radius_mm=xr, crossover_span=xspan, kink_if_straight_chord_75_90_deg=kink,
                outer_end=dict(r=outer[1], th=outer[3] % 360 - 360 if outer[3] % 360 > 180 else outer[3] % 360),
                z_centre=Z_WIND, z_top=Z_WIND_TOP)
    return Compound([s_in, s_out, s_x]), info


def _angles(sp, step=6.0):
    n = max(8, int(abs(sp[3] - sp[2]) / step))
    return [sp[2] + (sp[3] - sp[2]) * i / n for i in range(n + 1)]


def lead_points(state="R1"):
    """Polylines (coil end first) of the two leads in world mm, before filleting. The J2 lead leaves the outer end along
    its tangent (one 8 deg run-out of the spiral is included so the exit bend is filleted too)."""
    inner, outer = spirals(state)
    lj = LUG.lug_geometry()
    j2_top, j5_top = lj["J2"]["barrel_top"], lj["J5"]["barrel_top"]
    th_e = outer[3]
    j2 = [P(spiral_xy(outer, th_e - 8.0 + 2.0 * i), th_e - 8.0 + 2.0 * i, Z_WIND) for i in range(5)]
    j2 += [(lj["J2"]["drop"][0], lj["J2"]["drop"][1], Z_WIND), (lj["J2"]["drop"][0], lj["J2"]["drop"][1], j2_top)]
    s0 = P(inner[0], inner[2], Z_WIND)
    j5 = [s0, P(27.6, TH_C, Z_CROSS), P(R_GAP_LEAD, TH_C, Z_CROSS), P(R_GAP_LEAD, -103.5, Z_GAPRING),
          (lj["J5"]["drop"][0], lj["J5"]["drop"][1], 96.0), (lj["J5"]["drop"][0], lj["J5"]["drop"][1], j5_top)]
    return {"J2": j2, "J5": j5}


def max_bend(points, hi=60.0):
    """Largest fillet radius every corner of the polyline can take (bisection on the R43 filleting helper)."""
    lo = 0.1
    for _ in range(40):
        mid = (lo + hi) / 2
        _, r = _fillet(points, mid)
        if r >= mid * 0.999:
            lo = mid
        else:
            hi = mid
    return lo


J2_RUNOUT = 4          # index of the spiral end in the J2 polyline (the 8 deg run-out before it is only for filleting)


def lead(points, rule_r, name=None):
    """Filleted lead. The tube starts where the lead leaves the winding (J2: the spiral end; the run-out points before it
    only shape the exit bend). The J5 lead leaves the first turn on the roof as the bare bundle and is sleeved from where
    its sleeve clears the roof top (centre Z >= roof + sleeve OD / 2)."""
    fpts, rmin = _fillet(points, rule_r)
    if name == "J2":
        end = points[J2_RUNOUT]
        i0 = min(range(len(fpts)), key=lambda i: math.dist(fpts[i], end))
        fpts = fpts[i0:]
    bare = []
    if name == "J5":
        zs = Z_ROOF_TOP + LEAD_OD / 2
        k = next(i for i, q in enumerate(fpts) if q[2] >= zs)
        bare, fpts = fpts[:k + 1], fpts[k:]
    length = sum(math.dist(a, b) for a, b in zip(bare, bare[1:])) + sum(math.dist(a, b) for a, b in zip(fpts, fpts[1:]))
    solids = list(_tube(fpts, LEAD_OD / 2).solids()) + (list(_tube(bare, BUNDLE / 2).solids()) if len(bare) > 1 else [])
    return Compound(solids), dict(developed_mm=length, tightest_bend_mm=rmin, max_achievable_bend_mm=max_bend(points),
                                  points=list(bare[:-1]) + list(fpts), bare_bundle_mm=sum(math.dist(a, b) for a, b in zip(bare, bare[1:])))


def former_world(variant="cnc"):
    if variant == "cnc":
        body, info = F.former(bundle=BUNDLE, clearance=0.2, lead_hole_r=J2_HOLE_R, min_end_tooth=F.MIN_END_TOOTH, lead_slot=F.LEAD_SLOT)
        return W0 * body, info
    body, info = F.former(bundle=BUNDLE, clearance=0.3, lead_hole_r=J2_HOLE_R, min_end_tooth=F.MIN_END_TOOTH, lead_slot=F.LEAD_SLOT)
    segs, _ = F.segments(body)
    return Compound([W0 * s for s in segs]), info


def ntc_bead(info):
    n = info["ntc"]
    c, d = n["bead_centre_xy"], n["bore_dir_xy"]
    a = (c[0] - d[0] * K.BEAD_L / 2, c[1] - d[1] * K.BEAD_L / 2, n["bead_z"])
    bead = Solid.make_cylinder(K.BEAD_D / 2, K.BEAD_L, Plane(origin=a, z_dir=(d[0], d[1], 0.0)))
    return W0 * bead


if __name__ == "__main__":
    w, wi = winding()
    print(wi)
    print({k: (v["developed_mm"], v["tightest_bend_mm"], v["max_achievable_bend_mm"]) for k, v in
           {n: lead(p, LUG.BEND_RULE_MM, n)[1] for n, p in lead_points().items()}.items()})
