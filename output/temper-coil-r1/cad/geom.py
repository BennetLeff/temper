"""Shared CAD helpers and the coil-r1 former geometry constants (build123d, millimetres).

Coordinates: the coil axis is the origin; z = 0 is the bar underside / carrier top (enclosure world Z93), so world
Z = z + 93 and the enclosure's lead drops J2/J5 sit at (-9, -118.5) / (-9, -87.5). Angles are degrees CCW seen from above,
in the enclosure's frame (R43 r34_world.py: the coil centre is at world (0, 261)).
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

from build123d import Box, Face, Plane, Pos, Rot, Solid, Vector, Wire

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "model"))
import coil_geometry as G  # noqa: E402

Z0_WORLD = 93.0
# stack (local z) - R43 values
Z_BAR = (G.Z_BAR[0] - Z0_WORLD, G.Z_BAR[1] - Z0_WORLD)        # 0-5
Z_ROOF = (G.Z_ROOF[0] - Z0_WORLD, G.Z_ROOF[1] - Z0_WORLD)     # 5-6
Z_WIND = G.Z_WIND_C - Z0_WORLD                                 # 7.2 bundle centre
RIM_TOP = 100.4 - Z0_WORLD                                     # 7.4 (R37: under the glass TCO)
# former (R43 r34_world.py values)
HUB_R, RIM_R = (22.0, 25.5), (120.0, 123.5)
SPOKE_W, COMB_W, COMB_R0, GAP_R = 19.2, 4.0, 32.0, (84.0, 92.0)
BAR_CH_W, BAR_CH_R = G.BAR_W + 0.2, (G.BAR_R[0] - 0.1, G.BAR_R[1] + 0.1)     # channels 15.2 x 5.0 x 90.2
LUG_ANGLES, LUG_R, LUG_W, LUG_R1, LUG_T, LUG_HOLE = (45, 135, 225, 315), 127.0, 12.0, 134.0, 2.0, 3.4
J2, J5 = (-9.0, 142.5 - 261.0), (-9.0, 173.5 - 261.0)
D_LEAD = 2.4
# R40 coil-NTC pad on the -41 deg spoke
NTC_PHI, NTC_TILT, NTC_WALL, BEAD_D, BEAD_L = -41.0, 20.0, 2.0, 1.35, 3.0


def P(r, th, z=0.0):
    return (r * math.cos(math.radians(th)), r * math.sin(math.radians(th)), z)


def radial_box(phi, r0, r1, w, z0, z1):
    return Pos(*P((r0 + r1) / 2, phi, (z0 + z1) / 2)) * Rot(0, 0, phi) * Box(r1 - r0, w, z1 - z0)


def zcyl(x, y, z0, h, rad):
    return Solid.make_cylinder(rad, h, Plane(origin=(x, y, z0)))


def annulus(r0, r1, z0, z1):
    s = zcyl(0, 0, z0, z1 - z0, r1)
    return s - zcyl(0, 0, z0 - 1, z1 - z0 + 2, r0) if r0 > 0 else s


def sector(a0, a1, r1, z0, z1, n=48):
    """Prism over the angular sector a0..a1 (deg), radius r1, z0..z1."""
    pts = [Vector(0, 0, z0)] + [Vector(*P(r1, a0 + (a1 - a0) * i / n, z0)) for i in range(n + 1)]
    return Solid.extrude(Face(Wire.make_polygon(pts, close=True)), Vector(0, 0, z1 - z0))


def spirals(w, spare_outer=0.0):
    """(r0, r1, th0, th1) per section, from the winding of record, start/end angles as R43 (R1: inner end 75 deg)."""
    inner, outer = w.sections
    th0_in = G.INNER_START_DEG
    out = [(inner.r0, inner.r1, th0_in, th0_in + 360.0 * inner.turns)]
    th1 = G.OUTER_START_DEG + 360.0 * outer.turns
    out.append((outer.r0, outer.r1 + outer.pitch * spare_outer, G.OUTER_START_DEG, th1 + 360.0 * spare_outer))
    return out


def crossings(sp, phi):
    """Radii where a spiral (r0, r1, th0, th1) crosses the ray at angle phi."""
    r0, r1, th0, th1 = sp
    out, k = [], math.floor((th0 - phi) / 360.0) - 1
    while True:
        th = phi + 360.0 * k
        k += 1
        if th < th0:
            continue
        if th > th1:
            break
        out.append(r0 + (r1 - r0) * (th - th0) / (th1 - th0))
    return out


def spiral_pts(sp, z, step=5.0):
    r0, r1, th0, th1 = sp
    n = max(8, int(abs(th1 - th0) / step))
    return [P(r0 + (r1 - r0) * i / n, th0 + (th1 - th0) * i / n, z) for i in range(n + 1)]
