"""Coil geometry of record for temper-coil-r1: one source for the EM model and the CAD.

Everything is in millimetres here; the solvers convert to SI.

Baseline = enclosure R43 (frozen; `output/temper-manufacturing-r43/src/r34_world.py` with the R37 bar change):
  - 10 x MnZn bars 90 x 15 x 5 mm at -113 + 36k deg, r 29.5-119.5, Z 93-98 (in the former's channels)
  - former spoke roof Z 98-99 (1 mm of former between bars and winding)
  - Litz bundle D 2.4, single layer on Z 99-101.4
  - inner section r 27.4 -> 82.6 (bundle centre), 15.47 turns, start angle -95 deg, CCW from above
  - gap ring r 84-92 (centre lead and J5 drop), outer section r 93.4 -> 114.8, 6.46 turns
  - glass Z 106-110 (4 mm), pan base on the glass top at Z 110
  - enclosure conductors near the coil: P1 seat ring 5052 Z 101.8-105 inside 326 x 316 (inscribed r 158),
    P2 fence ring Z 105-109.1 inside 352 x 342 (r 171), base 5052 Z 8.97-11.

A section is (r_start, r_end, turns) with r the bundle-centre radius of an Archimedean spiral.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

# ---- stack (Z, mm), R43 catalogue -------------------------------------------------------------
Z_BAR = (93.0, 98.0)
Z_ROOF = (98.0, 99.0)
D_BUNDLE = 2.4
Z_WIND_BOT = 99.0
Z_WIND_C = Z_WIND_BOT + D_BUNDLE / 2      # 100.2
GLASS = (106.0, 110.0)
PAN_Z0 = 110.0

# ---- ferrite -----------------------------------------------------------------------------------
N_BARS, BAR_W, BAR_T, BAR_L = 10, 15.0, 5.0, 90.0
BAR_R = (29.5, 119.5)
BAR_ANGLE0, BAR_PITCH_DEG = -113.0, 36.0

# ---- enclosure conductors (axisymmetric equivalents) -------------------------------------------
SEAT_RING = dict(r=(158.0, 221.0), z=(101.8, 105.0))       # 5052, 0.125 in
FENCE_RING = dict(r=(171.0, 221.0), z=(105.0, 109.1))      # 5052, 0.160 in
BASE = dict(r=(0.0, 221.0), z=(8.97, 11.0))                 # 5052, 0.080 in, area-equivalent disc


@dataclass(frozen=True)
class Section:
    r0: float      # bundle-centre radius at the start (mm)
    r1: float      # bundle-centre radius at the end (mm)
    turns: float

    @property
    def pitch(self) -> float:
        return (self.r1 - self.r0) / self.turns


@dataclass(frozen=True)
class Winding:
    sections: tuple[Section, ...]
    d_bundle: float = D_BUNDLE
    z_c: float = Z_WIND_C
    lead_centre_mm: float = 250.0     # R43 build guide: centre lead about 250 mm
    lead_outer_mm: float = 150.0      # outer lead about 150 mm
    name: str = ""

    @property
    def turns(self) -> float:
        return sum(s.turns for s in self.sections)

    def rings(self):
        """Axisymmetric ring equivalent of the spirals: (r_mm, weight). A full turn of an Archimedean spiral is a ring at its
        azimuth-mean radius; the last fractional turn f is a ring of weight f at the mean radius of that part."""
        out = []
        for s in self.sections:
            p = s.pitch
            n_full = int(math.floor(s.turns + 1e-9))
            for j in range(n_full):
                out.append((s.r0 + p * (j + 0.5), 1.0))
            f = s.turns - n_full
            if f > 1e-6:
                out.append((s.r0 + p * (n_full + f / 2), f))
        return out

    def length_m(self, with_leads=True) -> float:
        """Developed length: spiral arcs (sum 2 pi r over the rings) + section crossover + leads."""
        L = sum(2 * math.pi * r * w for r, w in self.rings())
        if len(self.sections) > 1:
            L += (self.sections[1].r0 - self.sections[0].r1) * 1.2      # diagonal crossover
        L += self.sections[0].r0       # centre lead run out to the gap (part of the 250 mm lead, counted in the lead)
        if with_leads:
            L += self.lead_centre_mm + self.lead_outer_mm
        return L / 1000.0


def section_end_angle(start_deg: float, turns: float) -> float:
    return start_deg + 360.0 * turns


# R43 as built in the frozen enclosure (r34_world.INNER / OUTER after R37)
INNER_START_DEG = -95.0
INNER_END_DEG = 75.0 + 15 * 360.0
OUTER_START_DEG = 90.0
OUTER_END_DEG = 90.0 + 6 * 360.0 + ((math.degrees(math.atan2(142.5 - 261.0, -9.0)) - 9.0) % 360.0 - 90.0)
R43 = Winding(
    sections=(Section(27.4, 82.6, (INNER_END_DEG - INNER_START_DEG) / 360.0),
              Section(93.4, 114.8, (OUTER_END_DEG - OUTER_START_DEG) / 360.0)),
    name="R43 as built (15.47 + 6.46 = 21.93 turns)")


# coil-r1 winding of record (README decision D2): the R43 radial bands, start/end angles and lead routes, with the inner
# section reduced to 14.47 turns (pitch 3.815) so it still ends at 75 deg and the outer section still starts at 90 deg
# and ends 9 deg before the J2 drop. ~81 uH free-air. The former carries one SPARE outer notch turn (to r118.1) for tuning up.
R1_INNER_START_DEG = -95.0
R1_INNER_END_DEG = 75.0 + 14 * 360.0
R1 = Winding(
    sections=(Section(27.4, 82.6, (R1_INNER_END_DEG - R1_INNER_START_DEG) / 360.0),
              Section(93.4, 114.8, (OUTER_END_DEG - OUTER_START_DEG) / 360.0)),
    name="R1 (14.47 + 6.46 = 20.93 turns)")
R1_SPARE_OUTER_TURNS = 1.0


def with_spare(w: Winding, extra=R1_SPARE_OUTER_TURNS) -> Winding:
    s = w.sections[-1]
    s2 = Section(s.r0, s.r1 + s.pitch * extra, s.turns + extra)
    return replace(w, sections=w.sections[:-1] + (s2,), name=f"{w.name} + {extra:g} spare outer")


def trimmed(w: Winding, outer_turns_removed: float) -> Winding:
    """The tune-to-inductance move: remove turns from the outer end of the outer section at constant pitch."""
    s = w.sections[-1]
    n = s.turns - outer_turns_removed
    s2 = Section(s.r0, s.r0 + s.pitch * n, n)
    return replace(w, sections=w.sections[:-1] + (s2,), name=f"{w.name} trimmed -{outer_turns_removed:g} outer")


def with_turns(inner_turns: float, outer_turns: float, inner_pitch=None, outer_pitch=None, r_in0=27.4, r_out0=93.4,
               name=None) -> Winding:
    """A layout on the R43 radii: inner from r27.4, outer from r93.4, at the given pitches (default R43 pitches)."""
    ip = inner_pitch or R43.sections[0].pitch
    op = outer_pitch or R43.sections[1].pitch
    return Winding(sections=(Section(r_in0, r_in0 + ip * inner_turns, inner_turns),
                             Section(r_out0, r_out0 + op * outer_turns, outer_turns)),
                   name=name or f"{inner_turns:g} + {outer_turns:g} turns (pitch {ip:.3f} / {op:.3f})")


def bar_angles():
    return [BAR_ANGLE0 + BAR_PITCH_DEG * k for k in range(N_BARS)]


if __name__ == "__main__":
    w = R43
    print(w.name, f"turns {w.turns:.3f}")
    for s in w.sections:
        print(f"  section r{s.r0}-{s.r1}: {s.turns:.3f} turns, pitch {s.pitch:.3f} mm, gap between bundles {s.pitch - w.d_bundle:.2f} mm")
    print(f"  developed length {w.length_m(False):.2f} m winding, {w.length_m(True):.2f} m with leads")
