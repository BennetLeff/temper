"""Bench heatsink r1: mechanics of a soldered TO-247 standing on its lead shoulders (imported by bench_tolerance.py,
bench_thermal.py and shim_select.py).

The free part of each lead is its wide section between the body and the shoulder, length L1 ([IPW] p.12), width b1 (outer
leads) or b2 (centre lead), thickness c. The lead is fixed in the solder joint at the board and in the body.
  * translation of the body (y, toward the sink) bends each lead as a guided cantilever: k = 12 E I / L^3,
    sigma = 3 E c delta / L^2;
  * rotation of the body (lean) about the board line: k_rot = E I / L, sigma = E c theta / (2 L).
E and the allowed stress are EST (bench_params.py). The elastic limits below are what the spring clamp may correct
without yielding a lead; anything larger must be taken by a shim (translation) or rejected at inspection (lean).
"""
from __future__ import annotations

import math

import itertools

import bench_params as P

T = P.TO247


def _leads(c, b1, b2):
    return [(b1, c), (b2, c), (b1, c)]          # (width, thickness) of the three leads


def corners():
    for c, L, b1, b2 in itertools.product(T["c"], T["L1"], T["b1"], T["b2"]):
        yield dict(c=c, L=L, b1=b1, b2=b2)


def stiffness(c, L, b1, b2):
    I = [w * t ** 3 / 12 for w, t in _leads(c, b1, b2)]
    return dict(k_trans=sum(12 * P.E_LEAD * i / L ** 3 for i in I),       # N/mm
                k_rot=sum(P.E_LEAD * i / L for i in I))                    # N mm / rad


def elastic_limits():
    """Smallest translation and lean the clamp may impose (over the outline corners), and the largest moment it takes."""
    d_el = min(P.SIGMA_LEAD_ALLOW * k["L"] ** 2 / (3 * P.E_LEAD * k["c"]) for k in corners())
    th_el = min(2 * P.SIGMA_LEAD_ALLOW * k["L"] / (P.E_LEAD * k["c"]) for k in corners())
    k_rot_max = max(stiffness(**k)["k_rot"] for k in corners())
    k_trans_max = max(stiffness(**k)["k_trans"] for k in corners())
    m_el = k_rot_max * th_el                      # moment to straighten the stiffest device by th_el
    lever = P.SPRING_Z - P.Z_PIVOT
    return dict(delta_el_mm=d_el, theta_el_rad=th_el, k_rot_max=k_rot_max, k_trans_max=k_trans_max,
                m_straighten_Nmm=m_el, f_loss_N=m_el / lever, lever_mm=lever)


# ------------------------------------------------------------------------------------------------ tab-plane offsets
def hole_fin():
    return (P.FET_DRILL + P.PTH_TOL[0], P.FET_DRILL + P.PTH_TOL[1])


def lead_play():
    """Half the free play of a lead in its finished hole, across the tab plane.

    MIN: the rectangle's corner meets the round hole first, so corner_play() (c60-seating-fixture). MAX: the flat form
    (D - c) / 2, which ignores the corner and so bounds a lead with rounded corners (the spread and shims use it)."""
    d = hole_fin()
    return (corner_play(d[0], T["b"][1], T["c"][1]), (d[1] - T["c"][0]) / 2)


def corner_play(d, b, c):
    """Half play of a sharp-cornered b x c lead in a round hole d, across c, centred along b."""
    return math.sqrt((d / 2) ** 2 - (b / 2) ** 2) - c / 2


def tab_offset_bound():
    """Worst |offset| of one device's tab plane at the board line from the footprint nominal (y), datasheet A1 range."""
    return P.HOLE_POS_TOL + lead_play()[1] + (T["A1"][1] - T["A1"][0]) / 2


def sink_face_range():
    """The sink face sits one strip thickness behind the most-proud tab; that tab can be anywhere in the offset bound."""
    nom = P.Y_TAB - P.PADS[P.PAD_CHOICE]["t"]
    e = tab_offset_bound()
    return (nom - e, nom, nom + e)
