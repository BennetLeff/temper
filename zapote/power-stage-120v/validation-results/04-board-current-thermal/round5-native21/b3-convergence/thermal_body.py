#!/usr/bin/env python3
"""Body-level source model for the 2.5-D B3 board solve (stage 19b study; no board edits).

Why this module exists (external review, "Recorded board model does not converge"): ../b3/thermal.py deposits each
part's loss into the pad cells whose *centres* fall inside its pads. The deposited area changes with the mesh, the
copper mask is binary (sub-cell traces drop out), and there is no body, junction or air path, so peaks move with the
mesh (stage 19b c28 h25: 136.0 / 182.3 / 142.8 C at 1 / 0.5 / 0.25 mm).

This module keeps the same 7-sheet finite-volume board and adds, per heat-generating part:

  * a **package thermal network**: one junction/body node per part, joined to the part's pads through the datasheet
    junction-to-board (or junction-to-exposed-pad) resistance, and to ambient through junction-to-case(top) plus a
    convective film h on the exposed body area (optionally an underside air-gap conduction path, sensitivity only);
  * **area-weighted pad coupling**: the heat of each pad is a flux distribution over the pad's *exact* geometric
    overlap with the mesh cells (shapely intersection areas), proportional to (T_junction - mean pad temperature),
    so the source does not depend on which cell centres a pad happens to hit;
  * optional **copper fill-fraction rasterisation** (cell conductivity = area-weighted Cu / FR-4 mix, from a
    0.0625 mm supersampled mask), so sub-cell traces and thin pad necks keep their conductance on coarse meshes.

Modes (legacy reproduction stays available):  copper in {"binary", "fraction"}  x  source in {"point", "network"}.
("binary", "point") is exactly ../b3/thermal.py (control 1 asserts the committed 136.0 C).

Units: SI internally for conductances, mm on the geometry side. Temperatures are rises over ambient (50 C added by
callers). Matrix is symmetric positive definite; solved by Jacobi-preconditioned CG, rtol 1e-10.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import shapely
from scipy.sparse import coo_matrix, csr_matrix
from scipy.sparse.linalg import LinearOperator, cg
from scipy.special import i0 as bessel_i0, i1 as bessel_i1, k1 as bessel_k1
from shapely.geometry import Polygon

HERE = Path(__file__).resolve().parent
ROUND5 = HERE.parent
sys.path.insert(0, str(ROUND5 / "b3"))
import thermal as T  # noqa: E402  (the committed legacy model; imported, never modified)

K_CU, K_FR4, TAMB_C = T.K_CU, T.K_FR4, T.TAMB_C
CU_INDEX = T.CU_INDEX
THK_MM = T.THICK_MM
BASE = 0.0625                      # supersampling pitch for copper fill fractions [mm]
K_AIR = 0.026                      # W/m/K, dry air near 60 C (Incropera table A.4)
# Copper TCR for the hot-copper fixed point (OPEN-ITEMS S17): the task-04 A4 fields are 20 C DC copper
# (run_board.py 'assumptions', sheet_solver temp_c=20), so each A4 heat cell is q = q20 (1 + ALPHA_CU (T - 20 C)) at its
# absolute temperature T. One value: thermal.ALPHA_CU, asserted there against sheet_solver.ALPHA_CU.
ALPHA_CU = T.ALPHA_CU
TCR_TOL_K = 1e-3                   # Picard check: max |dT| between successive solves
TCR_MAX_ITER = 50

# --------------------------------------------------------------------------------------------------------------
# Package network specifications. Every number carries its source. "derived" = computed here from handbook
# material properties because no datasheet value exists for the class; those are flagged in the README.
# --------------------------------------------------------------------------------------------------------------
RECOM_THERMAL_PINS = {"1", "2", "5", "8", "9", "10", "11", "12", "13", "14", "15", "16", "17", "18",      # PGND
                      "19", "20", "21", "22", "23", "24", "25", "26", "27", "30", "31", "36"}            # VOUT-
SPECS = {
    "recom": dict(  # U41, U42  RECOM R24C2T25/R  (36-SSOP power module)
        label="RECOM R24C2T25/R", r_pad=25.9, r_top=16.6, body_mm=(12.83, 7.5), standoff_mm=0.2,
        pad_filter=lambda n: n in RECOM_THERMAL_PINS, tj_limit=150.0,
        cite="RECOM R24C2T25/R Rev.1-2024: p.8 'junction to board 25.9 K/W', 'junction to case 16.6 K/W'; p.13 'package "
             "dissipates heat through the GNDP and VOUT- pins' and pin table (PGND 1,2,5,8-18; VOUT- 19-27,30,31,36); "
             "p.12 body 12.83 x 7.5 x 3.55 mm, standoff 0.20 +/-0.10; p.1 Tj max 150 C"),
    "rgw": dict(    # U26  TI TPS7A4700 RGW (VQFN-20, exposed pad = pad 21)
        label="TI TPS7A4700 RGW", r_pad=1.7, r_top=27.0, body_mm=(5.0, 5.0), standoff_mm=0.05,
        pad_filter=lambda n: n == "21", tj_limit=125.0,
        cite="TI SBVS204G p.5 Table 5.4: RthJC(bot) 1.7 K/W (junction to exposed pad), RthJC(top) 27 K/W, RthJB 11.9, "
             "PsiJB 11.9; p.21 sec 9.3 'junction temperature must be limited to a maximum of 125 C'; p.4 TJ -40..125"),
    "dwk14": dict(  # U1, U2  TI UCC21550 DWK (SOIC-14)
        label="TI UCC21550 DWK", r_pad=32.8, r_top=34.1, body_mm=(7.5, 10.3), standoff_mm=0.1,
        pad_filter=None, tj_limit=150.0,
        cite="TI UCC21550 p.5: DWK RthJB 32.8, RthJC(top) 34.1 K/W; p.1 junction range -40..150 C"),
    "dbv5": dict(   # U3, U37, U38, U39  TI TPS70950 DBV (SOT-23-5)
        label="TI TPS70950 DBV", r_pad=39.5, r_top=78.5, body_mm=(1.6, 2.9), standoff_mm=0.05,
        pad_filter=None, tj_limit=125.0,
        cite="TI TPS709 p.4: DBV RthJB 39.5, RthJC(top) 78.5 K/W; p.4 TJ -40..125 C"),
    "chip1206": dict(  # thick-film chip resistors, 1206 (3.2 x 1.6 x 0.6 mm alumina)
        label="1206 chip resistor", r_pad=33.0, r_top=0.0, body_mm=(3.2, 1.6), standoff_mm=0.05,
        pad_filter=None, tj_limit=155.0,
        cite="DERIVED: element-to-termination conduction through the 96 % alumina substrate, k = 24 W/mK (CoorsTek "
             "96 % alumina, handbook), path (L/2)/(2 k W t) = 1.6 mm / (2 x 24 x 1.6 mm x 0.635 mm) = 33 K/W. "
             "Rating 0.25 W at 70 C derated to 0 at 155 C is the vendor-typical 1206 curve (Yageo RC_L / UniRoyal "
             "datasheets were not retrievable from this host: NOT re-verified here)"),
    "chip2512": dict(  # thick-film chip resistors, 2512 (6.35 x 3.20 x 0.55 mm alumina): R10/R12/R18/R20 from stage 42
        label="2512 chip resistor", r_pad=37.6, r_top=0.0, body_mm=(6.35, 3.2), standoff_mm=0.05,
        pad_filter=None, tj_limit=155.0,
        cite="DERIVED as chip1206: element-to-termination conduction through the 96 % alumina substrate, k = 24 W/mK, "
             "path (L/2)/(2 k W t) = 3.175 mm / (2 x 24 x 3.20 mm x 0.55 mm) = 37.6 K/W (L 6.35, W 3.20, H 0.55 mm: "
             "UniRoyal thick-film chip resistor data sheet V.3 2019-02-12 p.4/9). Rating 1 W at 70 C derated to 0 at "
             "155 C (p.4/9 table 6, p.5/9 section 9 figure 1); operating -55..155 C (p.5/9 table 7) - candidate 39"),
    "css2h": dict(  # R5  Bourns CSS2H-2512R-1L00F
        label="Bourns CSS2H-2512R-1L00F", r_pad=20.0, r_top=0.0, body_mm=(6.35, 3.05), standoff_mm=0.05,
        pad_filter=None, tj_limit=170.0,
        cite="DERIVED from the vendor terminal derating curve recorded in ../stage17-r5/screen.py (5 W at 70 C terminal "
             "falling linearly to 0 W at 170 C terminal, Bourns CSS2H PDF p.3, bourns.com 403 from this host so "
             "NOT re-fetched): element 170 C at 0 W-headroom => (170-70)/5 W = 20 K/W element-to-terminal"),
    "film_radial": dict(  # C21-23, C151, C152 TDK B32654A1104K000 (C38-41 until 2026-10-15: see film_hf)
        label="TDK MKP radial film capacitor", r_pad=50.0, r_top=0.0, body_mm=None, standoff_mm=3.0,
        pad_filter=None, tj_limit=105.0, body_air=False,
        cite="ASSUMED class value: two 0.8 mm leads (cap doc components/B32652A0104K000), 3 mm free length, copper-clad "
             "steel k = 60 W/mK  => 2 x 99 K/W in parallel = 50 K/W. TDK datasheet was not retrievable (403): the 105 C "
             "upper category temperature and the 85 C ripple curve are the values recorded in round6-full-power/README.md"),
    "film_mmkp": dict(  # C21-23, C151, C152 from stage 49: TDK B32643B8104J000 (B3264*B MMKP, 2000 V, P22.5)
        label="TDK MMKP radial film capacitor", r_pad=50.0, r_top=0.0, body_mm=None, standoff_mm=3.0,
        pad_filter=None, tj_limit=125.0, body_air=False,
        cite="lead path as film_radial (ASSUMED 50 K/W: two 0.8 mm leads, TDK B3264*B June 2026 p.2 'B32643B lead "
             "diameter d1 0.8 +-0.05', 'parallel wire leads, lead-free tinned'; 3 mm free length, copper-clad steel k 60). "
             "Max. operating temperature 125 C (case) (p.2; Top,max +125 C, p.12). No body-to-air path, as film_radial"),
    "film_mmkp_h": dict(  # C21-23, C151, C152 from stage 52: TDK B32643H8104J000 (B3264*H MMKP, 2000 V, P22.5)
        label="TDK MMKP (B3264*H) radial film capacitor", r_pad=50.0, r_top=0.0, body_mm=None, standoff_mm=3.0,
        pad_filter=None, tj_limit=125.0, body_air=False,
        cite="lead path as film_mmkp (ASSUMED 50 K/W: two 0.8 mm leads, TDK B3264*H June 2026 p.3 'B32643H lead diameter "
             "d1 0.8 +-0.05', p.2 'parallel wire leads, lead-free tinned'; 3 mm free length, copper-clad steel k 60). Max. "
             "operating temperature 125 C (case) (p.2; Top,max +125 C as operating Top = ambient + self-heating, p.15). "
             "No body-to-air path, as film_radial"),
    "film_mmkp82": dict(  # C21-23, C151, C152 from stage 51: KNSCHA MMK104J3DF1KN208G2 (MMKP82, 2000 V, P27.5)
        label="KNSCHA MMKP82 radial film capacitor", r_pad=50.0, r_top=0.0, body_mm=None, standoff_mm=3.0,
        pad_filter=None, tj_limit=105.0, body_air=False,
        cite="lead path as film_mmkp (ASSUMED 50 K/W: two 0.8 mm leads, KNSCHA spec KNS20200505002 p.3 'd 0.8 +-0.05', "
             "CP wire (copper-clad steel) leads, p.2 structure item 4; 3 mm free length, k 60). Climatic category "
             "40/105/56 and operating range -40 .. +105 C (p.4): Top,max 105 C. No body-to-air path, as film_radial"),
    "film_hf": dict(  # C38-41 TDK B32652A0104K000 (HF bus film, gated): film_radial's lead path + a body-to-air path
        label="TDK B32652A0104K000 HF film capacitor", r_pad=50.0, r_top=0.0, body_mm=None, standoff_mm=3.0,
        pad_filter=None, tj_limit=110.0, body_air="film_fin",
        cite="lead path as film_radial (ASSUMED 50 K/W: two 0.8 mm leads, TDK B3265* June 2026 p.3 drawing A1 'B32652 "
             "lead diameter d1 0.8'; 3 mm free length; copper-clad steel k 60 - p.2 gives only 'parallel wire leads, "
             "lead-free tinned', no material). Body-to-air (b3-ratings jet-2026-10-15): body 9.0 x 17.5 x 18.0 mm "
             "(w x h x l, p.14 ordering table, B32652A0104, max dimensions), film_body_g_air(); Top,max 110 C (p.2, p.35)"),
    "film_4pin": dict(  # C5, C6 TDK B32676 (4-pin)
        label="TDK MKP 4-pin film capacitor", r_pad=25.0, r_top=0.0, body_mm=None, standoff_mm=3.0,
        pad_filter=None, tj_limit=105.0, body_air=False,
        cite="ASSUMED class value, as film_radial with four leads (25 K/W); TDK datasheet not retrievable (403)"),
    "meanwell": dict(  # PS2 MEAN WELL MPM-20-24 (stage 38; IRM-20 before), Case 219A: pins + body-to-air (S18)
        label="MEAN WELL MPM-20-24", r_pad=15.0, r_top=0.0, body_mm=None, standoff_mm=1.0,
        pad_filter=None, tj_limit=85.0, body_air="module_box",
        cite="pin path ASSUMED class value 15 K/W total (potted module, four pins 'P/N diameter:1.04', 3.5 +1/-0.5 mm, "
             "MPM-20-SPEC 2024-10-30 p.4 Case No.219A; the in-body path from the windings to the pin roots is not "
             "published). Body-to-air (OPEN-ITEMS S18): MODULE_BODY box 52.4 x 27.2 x 24 mm (p.2 DIMENSION, p.4), "
             "module_body_g_air(), air at bay + MODULE_AIR_RISE_K; the network carries the whole module loss. "
             "tj_limit 85 = p.2 'WORKING TEMP. -35 ~ +85 C (Refer to \"Derating Curve\")', an AMBIENT rating (p.3 "
             "x-axis 'AMBIENT TEMPERATURE'), not a case or pin rating: the gate rates the local air "
             "(b3_ratings_gate.MODULES), never this node"),
    "choke": dict(  # L1 TDK B82726S2203A020; stage 52: B82726S2243A020 (same sheet and drawing)
        label="TDK B82726S22*3A020 choke", r_pad=5.0, r_top=0.0, body_mm=None, standoff_mm=2.0,
        pad_filter=None, tj_limit=125.0, body_air=True,
        cite="ASSUMED: winding to pin through the wire (k_Cu, 4 mm, 4 x 1.2 mm^2 section) ~ 5 K/W lumped; TDK datasheet "
             "not retrievable (403): no rating retrieved, 125 C is the typical class-II ferrite/choke limit (UNVERIFIED)"),
}


# --------------------------------------------------------------------------------------------------------------
# FET drain-lead path to the heatsink (thermal-refine 2026-10-15). The TO-247 FETs stand on the board with the tab
# clamped to the sink; pin 2 (drain) is part of the tab lead frame, so it ties the board's drain pad to the tab at the
# case temperature. Pins 1 / 3 reach the die only through bond wires and are left out (stage 15b lead_bias.py).
# Geometry: Infineon IPW65R018CFD7 Rev.2.0 p.12, PG-TO247-3 drawing Z8B00003327 rev 06. The board seats on the lead
# shoulders (b2 >= 2.57 mm against the 1.5 mm drill, m11 RECOMMENDATION sec.1), so the exposed drain lead is the
# shoulder: width b2, thickness c, length L1 (body bottom to the seat).
# --------------------------------------------------------------------------------------------------------------
TO247_DRAIN_LEAD = dict(
    b2_mm=(2.57, 3.43), c_mm=(0.38, 0.89), l1_mm=(3.85, 4.50),       # drawing min / max
    l_int_mm=(0.0, 7.91),   # in-body lead frame, body bottom to the exposed drain metal: 0 .. D - D2 - D1 (21.50 - 0.51 - 13.08)
    k_w_mk=(262.0, 390.0),  # ASSUMED lead-frame copper class: C19400 (262) .. pure Cu (390, thermal.py K_CU); not on the datasheet
    g_joint_w_k=(1.0, 3.0), # DERIVED solder joint (SAC k 58): shoulder seat 1.9 mm^2 / 0.05 mm + barrel fill 5.3 mm^2 / 0.3 mm
    cite="Infineon IPW65R018CFD7 Rev.2.0 p.12 (PG-TO247-3, Z8B00003327 rev 06): b2 2.57-3.43, c 0.38-0.89, L1 3.85-4.50, "
         "D 20.70-21.50, D1 13.08-17.65, D2 0.51-1.35 mm; R_thJC 0.28 K/W p.4")


def drain_lead_conductance(b2_mm=3.0, c_mm=0.635, l1_mm=4.175, l_int_mm=2.4, k_w_mk=300.0, g_joint_w_k=3.0) -> float:
    """Tab-to-pad conductance [W/K] of one drain lead: shoulder (L1) + in-body frame (l_int) in series, same section
    b2 x c, plus the solder joint. Defaults = the central estimate (drawing mid values; l_int half of the nominal
    D - D2 - D1 = 4.8 mm, crediting the wider in-body frame; k mid-class)."""
    a = b2_mm * c_mm * 1e-6
    return 1.0 / ((l1_mm + l_int_mm) * 1e-3 / (k_w_mk * a) + 1.0 / g_joint_w_k)


class LeadLink:
    """A fixed-temperature node (FET tab at the case temperature, t_rise over the model ambient) tied to one pad's
    copper through g [W/K]: flux into the pad cells = g (t_rise - w.T) w, split over the pad's copper on every layer
    by overlap area (the same convention as NetPart pad groups)."""

    def __init__(self, ref, pad, g, t_rise):
        self.ref, self.pad, self.g, self.t_rise = ref, pad, g, t_rise
        self.groups = []         # (flat_ids, weights(sum 1), g_share_W_per_K, tag)
        self.shares = []         # pad-copper area share of each group (sums to 1)


def build_lead_links(board_obj, leads, nx, ny, xmin, ymin, pitch, i0, j0):
    """leads: {ref: (pad_number, g_W_per_K, t_rise_K)} -> [LeadLink]."""
    nxy = nx * ny
    out = []
    for ref, (pad, g, t_rise) in sorted(leads.items()):
        ents = []
        for layer, poly in board_obj.pads_of(ref)[pad]:
            ii, jj, a = pad_overlap(poly, xmin, ymin, pitch, i0, j0, nx, ny)
            if a.size:
                ents.append((layer, CU_INDEX[layer], ii, jj, a))
        if not ents:
            raise ValueError(f"{ref}.{pad}: no pad overlap on this mesh")
        tot = sum(e[4].sum() for e in ents)
        link = LeadLink(ref, pad, g, t_rise)
        for layer, z, ii, jj, a in ents:
            link.groups.append((z * nxy + ii * ny + jj, a / a.sum(), g * a.sum() / tot, f"lead{pad}.{layer}"))
            link.shares.append(a.sum() / tot)
        out.append(link)
    return out


# --------------------------------------------------------------------------------------------------------------
# HF film capacitor body-to-air path (b3-ratings/jet-2026-10-15). Until then C38-C41's body node was reached only
# through the 50 K/W lead path: with no other exit, the node settles at the lead-weighted pad temperature plus
# P x 50 K/W, the hottest a body heated from its leads can be (refine-2026-10-15 declared it an upper bound).
# The body is a plastic box (TDK B3265* June 2026 p.2 'Plastic case (UL 94 V-0), Epoxy resin sealing') of 9.0 x 17.5 x
# 18.0 mm (w x h x l, p.14 ordering table, B32652A0104, maximum dimensions). Its surface loses heat to the air: the
# datasheet's own self-heating terms are the heat transfer coefficient and the 'Capacitor surface area' (p.77 symbols).
# The leads join the sprayed end contacts at the two l-ends, so the heat that comes up the leads enters at the end
# faces and must cross the winding lengthwise to reach the side and top surfaces. Each half-body is taken as a straight
# fin from its end face (length l/2, adiabatic at mid-length, cross-section w x h, exposed perimeter 2h + w: the bottom
# faces the board and gets nothing), plus the end face itself at h:
#     g_air = 2 [h w h_b + sqrt(h P k A_c) tanh(m l/2)],  m = sqrt(h P / (k A_c)).
# k = 0.2 W/mK (ASSUMED lower bound: polypropylene 0.22, epoxy fill ~0.2, PBT case ~0.25 W/mK, handbook) for heat
# along the film planes. At h 10 this gives 81 % of the bare-area h A (fin efficiency 0.74); at h 100 it gives 50 %.
# No radiation credit, no credit for the bottom face, case-wall resistance neglected (~0.5 mm, ~2 % of the h-10 film).
FILM_HF_BODY = dict(w_mm=9.0, h_mm=17.5, l_mm=18.0, k_w_mk=0.2,
                    cite="TDK B3265*A/G/J/T June 2026 (MKP_B32651_658.pdf, sha256 c32e3754787fa19b...): p.14 "
                         "B32652A0104 max dimensions w x h x l 9.0 x 17.5 x 18.0 mm; p.3 drawing A1, B32652 lead "
                         "d1 0.8 mm, e 15.0 mm; p.2 plastic case, epoxy sealing; p.77 heat transfer coefficient, "
                         "capacitor surface area; k ASSUMED 0.2 W/mK")


def film_body_g_air(h: float, w_mm=FILM_HF_BODY["w_mm"], h_mm=FILM_HF_BODY["h_mm"], l_mm=FILM_HF_BODY["l_mm"],
                    k_w_mk=FILM_HF_BODY["k_w_mk"]) -> float:
    """Body-to-air conductance [W/K] of a box film capacitor heated at its two end contacts (see FILM_HF_BODY)."""
    if h <= 0:
        return 0.0
    w, hb, half = w_mm * 1e-3, h_mm * 1e-3, l_mm * 1e-3 / 2
    a_c, per = w * hb, 2 * hb + w
    m = math.sqrt(h * per / (k_w_mk * a_c))
    return 2.0 * (h * w * hb + math.sqrt(h * per * k_w_mk * a_c) * math.tanh(m * half))


# The body-to-air path makes the cap row depend on how strongly the body is tied to the board, and the two kinds of
# row want opposite ends of that: the board rows (laminate, gate resistors, R5) are conservative with a WEAK tie (less
# heat leaves the board through the cap), the cap's own Top row with a STRONG tie (the body sits at the board's
# temperature). The solve keeps the weak, assumed 50 K/W lead path (film_radial's 3 mm of copper-clad steel). The cap
# row is evaluated at the strong end, from that solve's hotter pad (film_top_bound_rise): the leads as copper,
# k 390 W/mK (TDK p.2 gives only 'tinned', not the core metal), d 0.8 mm (p.3), over the free length between the body
# and the board top in the board's own 3D model (0.62 mm: validation-plan/enclosure-fit/native21-boxes.json, C40 body
# z 2.11 mm over the board top 1.493 mm), plus air conduction across that gap under the 9.0 x 18.0 mm bottom face.
# The weak solve's pads are the hotter ones (the strong tie draws more heat out through the cap), so this bounds the
# body from above at either end of the lead range; the hotter pad stands in for the hotter end contact.
FILM_HF_STRONG = dict(lead_d_mm=0.8, lead_k_w_mk=390.0, seat_mm=0.62, n_leads=2,
                      cite="lead d1 0.8 mm TDK B3265* June 2026 p.3; copper k 390 (thermal.K_CU, the upper end for a "
                           "'tinned' wire of unstated core); seat 0.62 mm from native21-boxes.json (C40 body bottom z "
                           "2.11, board top 1.493 mm); bottom-face gap conduction K_AIR 0.026 W/mK")


# The air the cap bodies see is not bay air. They stand 17.5 mm tall on a board whose top runs ~90-120 C, inside the
# board's own natural-convection layer: upper surface of a heated horizontal plate, Nu = 0.54 Ra^1/4 with L = A/P
# (Incropera & DeWitt, Fundamentals of Heat and Mass Transfer, sec. 9.6) gives h ~ 6.5 W/m2K for the 290 x 190 mm board,
# a conduction-equivalent layer k/h ~ 4.3 mm; an exponential profile over the 17.5 mm faces averages 0.24 x the board's
# excess over the bay: ~ +9 K at the release case (C40's pad ~98 C, bay 61 C), toward +12 K with the plume from the
# 110-120 C channel beside the caps. Default: +12 K + 3 K headroom = +15 K over the bay for a film_hf body NOT credited
# by a TopRegion (sens key film_air_rise overrides it; run_basis --film-air-rise). A region-credited cap keeps the
# region's air: the jet sweeps the board's layer away. Sensitivity: b3-ratings/jet-2026-10-15/cap-air.json (release
# margin -0.11 K per K of cap-air rise).
FILM_HF_AIR_RISE_K = 15.0


# --------------------------------------------------------------------------------------------------------------
# AC-DC module body-to-air path (OPEN-ITEMS S18, PS2 MEAN WELL MPM-20-24). Until then the 'meanwell' class had pins only
# (body_air False) and the network carried half the module loss (the heat row's board_fraction 0.5; the other half,
# sink_fraction 0.5, 'convects from the case' and left the model): 0.674 W at the 60 kHz window top, all of it forced
# through the four pins, so the pin pads read 105-112 C - 34 K of it PS2's own heat (b3-ratings/ps2-thermal-2026-10-15).
# Now the body node carries the WHOLE module loss (the heat row's watts, Pout (1/eta - 1)) and the network splits it
# between the pins (r_pad, to the pads) and the case surface (to air): both paths are kept and solved.
# Body: the encapsulated module's case, 52.4 x 27.2 x 24 mm (L x W x H; MPM-20-SPEC 2024-10-30 p.2 OTHERS 'DIMENSION
# 52.4*27.2*24mm (L*W*H)', p.4 Case No.219A drawing 52.4 / 27.2 / 24, tolerance +/-0.5 mm). Exposed: the top face and the
# four sides (5246 mm^2); the bottom faces the board and gets nothing (as film_hf). The case is one isothermal node: the
# module is potted ('Encapsulated Type', p.1-p.4 header), its loss is generated inside, not brought in at two end contacts
# as in a film cap, so no fin efficiency. Not credited: radiation (B3's h 10 W/m2K is the still-air basis incl. it, audit
# README), the bottom face, a board path across the bottom-face gap (sensitivity: sens module_gap_mm).
MODULE_BODY = {"meanwell": dict(l_mm=52.4, w_mm=27.2, h_mm=24.0,
                                cite="MEAN WELL MPM-20-SPEC 2024-10-30 (sha256 24d3a6bb642d74ea...): p.2 OTHERS "
                                     "'DIMENSION 52.4*27.2*24mm (L*W*H)'; p.4 Mechanical Specification Case No.219A "
                                     "(52.4, 27.2, 24; 'P/N diameter:1.04'; pins 3.5 +1/-0.5 mm; tolerance +/-0.5 mm)")}
# The air the module sees: the same rule as the HF film-cap bodies (FILM_HF_AIR_RISE_K, one value): the body stands in the
# board's own natural-convection layer, so its air is bay + 15 K (12 K layer + plume, 3 K headroom) unless a TopRegion
# credits it. The layer estimate behind that rule, applied to PS2's 24 mm faces: layer_factor(24) = 0.178 x the board's
# excess over the bay (0.24 for the caps' 17.5 mm); b3_ratings_gate rates the larger of the two.
MODULE_AIR_RISE_K = FILM_HF_AIR_RISE_K
BOARD_LAYER_MM = 4.3          # k_air / h of the board's upper-surface layer (Incropera sec. 9.6, see FILM_HF_AIR_RISE_K)
MODULE_RING_MM = 10.0         # board ring around the body whose F.Cu excess sets the layer estimate (ps2-thermal study)


def layer_factor(h_mm: float, d_mm: float = BOARD_LAYER_MM) -> float:
    """Face-average of an exponential air-layer profile exp(-z/d) over a vertical face of height h_mm: the fraction of
    the board's excess over the bay that a body face of that height sees (0.24 at 17.5 mm, the film-cap rule's basis)."""
    return (d_mm / h_mm) * (1.0 - math.exp(-h_mm / d_mm))


def module_body_area_mm2(spec: str = "meanwell") -> float:
    """Exposed case area [mm^2] of an AC-DC module: top + four sides (the bottom faces the board)."""
    b = MODULE_BODY[spec]
    return b["l_mm"] * b["w_mm"] + 2.0 * (b["l_mm"] + b["w_mm"]) * b["h_mm"]


def module_body_g_air(h: float, spec: str = "meanwell") -> float:
    """Case-to-air conductance [W/K] of an isothermal potted module body at film coefficient h."""
    return max(h, 0.0) * module_body_area_mm2(spec) * 1e-6


def body_box_mm(fp: dict):
    """Global (x0, y0, x1, y1) of a footprint's F.Fab body box (fp 'at' + 'fab' offsets, model frame). Rotation 0 only:
    the local-to-global turn is not needed for any part using it, and a rotated part must not get a wrong box."""
    rot = fp["at"][2] if len(fp["at"]) > 2 else 0.0
    if abs(rot) > 1e-9:
        raise NotImplementedError(f"body_box_mm: rotated footprint ({rot} deg)")
    x, y = fp["at"][0], fp["at"][1]
    f = fp["fab"]
    return (x + f[0], y + f[1], x + f[2], y + f[3])


def film_strong_coupling_g(d=FILM_HF_STRONG, body=FILM_HF_BODY) -> float:
    """Body-to-board conductance [W/K] at the strong end: copper leads over the seat height + the bottom-face air gap."""
    a = math.pi * (d["lead_d_mm"] * 1e-3 / 2) ** 2
    seat = d["seat_mm"] * 1e-3
    return d["n_leads"] * d["lead_k_w_mk"] * a / seat + K_AIR * body["w_mm"] * body["l_mm"] * 1e-6 / seat


def film_top_bound_rise(t_pad_hot: float, watts: float, g_air: float, t_air: float = 0.0) -> float:
    """Upper bound of the film body rise [K]: the body tied to its hotter pad (rise t_pad_hot) through
    film_strong_coupling_g(), to air (rise t_air) through g_air, self-heating `watts`."""
    g_s = film_strong_coupling_g()
    return t_pad_hot + (watts - g_air * (t_pad_hot - t_air)) / (g_s + g_air)


def film_body_area_mm2(w_mm=FILM_HF_BODY["w_mm"], h_mm=FILM_HF_BODY["h_mm"], l_mm=FILM_HF_BODY["l_mm"]) -> float:
    """Exposed body area [mm^2]: top, two sides, two ends (the bottom faces the board)."""
    return w_mm * l_mm + 2 * h_mm * l_mm + 2 * w_mm * h_mm


# --------------------------------------------------------------------------------------------------------------
# Top-face airflow region (b3-ratings jet-2026-10-15; temper-8d airflow-r1's board_h_sweep.py made first-class).
# Cells of the TOP sheet (F.Cu, z = 0) whose centres lie in [x0, x1] x [y0, y1] (inclusive, model mm) convect at h_top to
# air at t_air_rise over the model ambient (the gate shifts the field by bay - 50, so t_air_rise = T_air - bay; 0 = air at
# the bay temperature). The bottom face and every other top cell keep the case h. Package networks whose heat-row
# centre lies in the region take body-to-air at h_top, to the same air. None = the still-air model, bit-identical.
# credit_refs: bodies credited at h_top although centred outside (a sensitivity, e.g. the HF film caps beside the jet box).
# --------------------------------------------------------------------------------------------------------------
class TopRegion:
    def __init__(self, xy_mm, h_top, t_air_rise=0.0, name="region", credit_refs=()):
        self.x0, self.x1, self.y0, self.y1 = (float(v) for v in xy_mm)
        self.h_top, self.t_air_rise, self.name = float(h_top), float(t_air_rise), name
        self.credit_refs = tuple(sorted(credit_refs))

    def contains(self, x, y):
        return self.x0 <= x <= self.x1 and self.y0 <= y <= self.y1

    def credits(self, ref, x, y):
        return self.contains(x, y) or ref in self.credit_refs

    def mask(self, x, y):
        """Cell-centre mask (len(x), len(y))."""
        x, y = np.asarray(x), np.asarray(y)
        return ((x >= self.x0) & (x <= self.x1))[:, None] & ((y >= self.y0) & (y <= self.y1))[None, :]

    def as_dict(self):
        d = {"name": self.name, "xy_mm": [self.x0, self.x1, self.y0, self.y1], "h_top": self.h_top,
             "t_air_rise_k": self.t_air_rise}
        if self.credit_refs:
            d["credit_refs"] = list(self.credit_refs)
        return d


def spec_for(ref: str, mpn: str, fp: str) -> str:
    if mpn.startswith("R24C2T25"):
        return "recom"
    if mpn.startswith("TPS7A47"):
        return "rgw"
    if mpn.startswith("UCC21550") or mpn.startswith("2EDR8259X"):   # 2EDR8259X ASSUMED DWK-class (thermal-ratings audit 2026-10-15)
        return "dwk14"
    if mpn.startswith("TPS709"):
        return "dbv5"
    if mpn.startswith("CSS2H"):
        return "css2h"
    if "R_1206" in fp:
        return "chip1206"
    if "Resistor_SMD:R_2512" in fp:     # stage 42 (candidate 39): the 68 ohm 2512 turn-on resistors
        return "chip2512"
    if mpn.startswith("B32652A0104"):     # C38-C41: body-to-air path since 2026-10-15 (jet-2026-10-15)
        return "film_hf"
    if mpn.startswith("MMK104J3DF1"):    # stage 51: the KNSCHA MMKP82 bank (Top,max 105 C)
        return "film_mmkp82"
    if mpn.startswith("B32643H"):        # stage 52: the prototype-lot bank (B3264*H, Top,max 125 C case)
        return "film_mmkp_h"
    if mpn.startswith("B32643B"):        # stage 49: the c34 bank (B3264*B, Top,max 125 C case)
        return "film_mmkp"
    if mpn.startswith("B32654") or mpn.startswith("B32652"):
        return "film_radial"
    if mpn.startswith("B32676") or mpn.startswith("B32656"):
        return "film_4pin"
    if mpn.startswith(("IRM-20", "MPM-20")):   # stage 38: MPM-20-24, same Case No. 219A body and pins (MPM-20-SPEC p.4)
        return "meanwell"
    if mpn.startswith("B82726"):
        return "choke"
    raise KeyError(f"no package spec for {ref} {mpn} {fp}")


# --------------------------------------------------------------------------------------------------------------
# geometry: supersampled copper masks and exact pad overlaps
# --------------------------------------------------------------------------------------------------------------
class Board:
    def __init__(self, geometry: Path, cache_dir: Path):
        self.path = Path(geometry)
        self.data = json.loads(gzip.open(self.path, "rt").read())
        o = self.data["outline"]
        self.outline = Polygon(o["shell"], o["holes"])
        self.xmin, self.ymin, self.xmax, self.ymax = self.outline.bounds
        self.nbx = math.ceil((self.xmax - self.xmin) / BASE)
        self.nby = math.ceil((self.ymax - self.ymin) / BASE)
        self.cache = Path(cache_dir)
        self._fine = None
        self.barrels = None
        self.pad_polys = None

    # ---- fine masks (uint8) cached on disk
    def fine(self):
        if self._fine is not None:
            return self._fine
        key = hashlib.sha256((self.data["board_sha256"] + f"{BASE}").encode()).hexdigest()[:16]
        f = self.cache / f"fine_{key}.npz"
        if f.exists():
            z = np.load(f)
            self._fine = {k: z[k] for k in z.files}
            return self._fine
        t0 = time.time()
        x = self.xmin + (np.arange(self.nbx) + 0.5) * BASE
        y = self.ymin + (np.arange(self.nby) + 0.5) * BASE
        board = np.zeros((self.nbx, self.nby), bool)
        T.raster_polygon(self.outline, x, y, board)
        cu = {n: np.zeros_like(board) for n in CU_INDEX}
        from shapely.geometry import LineString, Point
        for it in self.data["primitives"]:
            layer = it["layer"]
            if layer not in cu:
                continue
            k = it["kind"]
            if k in ("zone", "pad"):
                shape = Polygon(it["shell"], it["holes"])
            elif k == "track":
                shape = LineString((it["start"], it["end"])).buffer(it["width_mm"] / 2, 8)
            elif k == "via":
                shape = Point(it["centre"]).buffer(it["diameter_mm"] / 2, 16)
            else:
                continue
            T.raster_polygon(shape, x, y, cu[layer])
        out = {"board": board.astype(np.uint8)}
        for n, m in cu.items():
            out["cu_" + n] = (m & board).astype(np.uint8)
        self.cache.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(f, **out)
        print(f"  fine masks built in {time.time() - t0:.0f} s -> {f.name}", flush=True)
        self._fine = out
        return out

    def window_arrays(self, pitch, i0, i1, j0, j1):
        """Board mask and per-layer copper area fraction for cells [i0,i1) x [j0,j1) of the pitch-mm grid."""
        f = round(pitch / BASE)
        assert abs(f * BASE - pitch) < 1e-9, pitch
        fine = self.fine()

        def blk(a):
            nxw, nyw = i1 - i0, j1 - j0
            sub = np.zeros((nxw * f, nyw * f), np.float32)
            a0, a1 = i0 * f, min(i1 * f, a.shape[0])
            b0, b1 = j0 * f, min(j1 * f, a.shape[1])
            if a1 > a0 and b1 > b0:
                sub[:a1 - a0, :b1 - b0] = a[a0:a1, b0:b1]
            return sub.reshape(nxw, f, nyw, f).mean((1, 3))
        bfrac = blk(fine["board"])
        board = bfrac >= 0.5
        cfrac = {}
        for n in CU_INDEX:
            c = blk(fine["cu_" + n]) / np.maximum(bfrac, 1e-9)
            cfrac[n] = np.where(board, np.clip(c, 0.0, 1.0), 0.0)
        return board, cfrac

    def grid_n(self, pitch):
        return math.ceil((self.xmax - self.xmin) / pitch), math.ceil((self.ymax - self.ymin) / pitch)

    def get_barrels(self):
        if self.barrels is None:
            b = {}
            for item in self.data["primitives"]:
                if item["kind"] not in ("pad", "via") or item["layer"] not in CU_INDEX:
                    continue
                drill = item.get("drill_mm", 0)
                if isinstance(drill, list):
                    drill = drill[0] if drill[0] == drill[1] else 0
                if drill and drill > 0:
                    xy = item["centre"]
                    key = (item["kind"], round(xy[0], 6), round(xy[1], 6), round(drill, 6))
                    b.setdefault(key, {"xy_mm": xy, "drill_mm": drill, "layers": set()})["layers"].add(item["layer"])
            self.barrels = list(b.values())
        return self.barrels

    def pads_of(self, ref):
        """{pad_number: [(layer, shapely polygon)]} for one reference designator."""
        if self.pad_polys is None:
            from collections import defaultdict
            d = defaultdict(lambda: defaultdict(list))
            for it in self.data["primitives"]:
                if it["kind"] == "pad" and it["layer"] in CU_INDEX:
                    r, _, n = it["ref"].partition(".")
                    d[r][n].append((it["layer"], Polygon(it["shell"], it["holes"])))
            self.pad_polys = d
        return self.pad_polys[ref]


def pad_overlap(poly, xmin, ymin, pitch, i0, j0, nx, ny):
    """Exact overlap areas [mm^2] of a polygon with cells of a (nx, ny) window whose first cell is (i0, j0)
    of the global pitch grid. Returns (local_i, local_j, area) for cells with area > 0."""
    bx0, by0, bx1, by1 = poly.bounds
    ia = max(int(math.floor((bx0 - xmin) / pitch)) - i0, 0)
    ib = min(int(math.floor((bx1 - xmin) / pitch)) - i0, nx - 1)
    ja = max(int(math.floor((by0 - ymin) / pitch)) - j0, 0)
    jb = min(int(math.floor((by1 - ymin) / pitch)) - j0, ny - 1)
    if ib < ia or jb < ja:
        return np.zeros(0, int), np.zeros(0, int), np.zeros(0)
    ii, jj = np.meshgrid(np.arange(ia, ib + 1), np.arange(ja, jb + 1), indexing="ij")
    ii, jj = ii.ravel(), jj.ravel()
    x0 = xmin + (ii + i0) * pitch
    y0 = ymin + (jj + j0) * pitch
    boxes = shapely.box(x0, y0, x0 + pitch, y0 + pitch)
    shapely.prepare(poly)
    area = shapely.area(shapely.intersection(boxes, poly))
    keep = area > 1e-12
    return ii[keep], jj[keep], area[keep]


# --------------------------------------------------------------------------------------------------------------
# linear system
# --------------------------------------------------------------------------------------------------------------
def assemble(board, k, thk_m, h, pitch_m, links, top_region=None):
    """Conductance matrix of the 7-sheet stack as COO pieces + diagonal (same stencil as thermal.solve_stack).
    top_region: None or (mask (nx, ny), h_top) - those top-sheet cells convect at h_top instead of h."""
    nz, nx, ny = k.shape
    area = pitch_m * pitch_m
    nxy = nx * ny
    ids = np.arange(nz * nxy).reshape(nz, nx, ny)
    diag = np.zeros(nz * nxy)
    rows, cols, vals = [], [], []
    for z in range(nz):
        sheet = k[z] * thk_m[z]
        for axis in (0, 1):
            if axis == 0:
                a, b = ids[z, :-1, :], ids[z, 1:, :]
                ka, kb = sheet[:-1, :], sheet[1:, :]
                valid = board[:-1, :] & board[1:, :]
            else:
                a, b = ids[z, :, :-1], ids[z, :, 1:]
                ka, kb = sheet[:, :-1], sheet[:, 1:]
                valid = board[:, :-1] & board[:, 1:]
            g = 2 * ka * kb / (ka + kb)
            T.add_edge(rows, cols, vals, diag, a[valid], b[valid], g[valid])
    for z in range(nz - 1):
        g = area / (thk_m[z] / (2 * k[z]) + thk_m[z + 1] / (2 * k[z + 1]))
        T.add_edge(rows, cols, vals, diag, ids[z][board], ids[z + 1][board], g[board])
    for z, i, j, z2, g in links:
        if board[i, j]:
            T.add_edge(rows, cols, vals, diag, [ids[z, i, j]], [ids[z2, i, j]], [g])
    conv = h * area
    for z in (0, nz - 1):
        np.add.at(diag, ids[z][board], conv)
    if top_region is not None:
        m, h_top = top_region
        np.add.at(diag, ids[0][m & board], (h_top - h) * area)
    return rows, cols, vals, diag, ids, conv


def barrel_links(barrels, xmin, ymin, pitch, i0, j0, nx, ny, board):
    """thermal.barrel_edges for a window (cell indices local to the window)."""
    zpos = np.cumsum(THK_MM) - THK_MM / 2
    links = []
    for b in barrels:
        ix = int((b["xy_mm"][0] - xmin) // pitch) - i0
        iy = int((b["xy_mm"][1] - ymin) // pitch) - j0
        if not (0 <= ix < nx and 0 <= iy < ny and board[ix, iy]):
            continue
        zs = sorted(CU_INDEX[layer] for layer in b["layers"] if layer in CU_INDEX)
        for za, zb in zip(zs, zs[1:]):
            area = math.pi * b["drill_mm"] * 0.018 * 1e-6
            links.append((za, ix, iy, zb, K_CU * area / ((zpos[zb] - zpos[za]) * 1e-3)))
    return links


class NetPart:
    """One package network: junction node + pad groups (+ optional gap group) + air conductance."""

    def __init__(self, ref, watts, spec_key):
        self.ref, self.watts, self.spec_key = ref, watts, spec_key
        self.groups = []         # (flat_ids, weights(sum 1), g_W_per_K, tag)
        self.g_air = 0.0
        self.t_air = 0.0         # air temperature the body sees, as a rise over the model ambient (TopRegion)
        self.r_top = 0.0
        self.metrics_pads = []   # (z, i, j, area) of the reported pad copper (heated pads on the heated layer)
        self.meta = {}


def build_network_parts(board_obj, heat_json, mode, nz, nx, ny, xmin, ymin, pitch, i0, j0, h, fps, sens, inside,
                        region=None):
    """Create NetPart objects for every heat-generating part passing `inside(x_mm, y_mm)`.

    sens: dict(h_body_factor, all_pins, gap, r_scale, film_lead_only)
      film_lead_only: C38-C41 (film_hf) without their body-to-air path - the model before 2026-10-15 (a control).
      module_pins_only: PS2 (module_box) as before OPEN-ITEMS S18 - pins only, the heat row's board share - a control.
      module_air_rise: PS2 case air over the bay, K (default MODULE_AIR_RISE_K); module_gap_mm: add the bottom-face
        air-gap path to the board under the body at this gap; module_r_pad: the pin path in K/W (sensitivities).
    region: None or TopRegion - a part whose heat-row centre (x_mm, y_mm) lies in it takes body-to-air at
      region.h_top, to air at region.t_air_rise; every other part at h, to the model ambient.
    """
    data = json.loads(Path(heat_json).read_text())
    nxy = nx * ny
    parts, omitted = [], []
    for p in data["parts"]:
        ref = p["ref"]
        fr, src = p.get("board_fraction"), p.get(f"watts_{mode}")
        if fr is None or src is None or fr == 0:
            omitted.append(ref)
            continue
        watts = src * fr
        if watts == 0 or not inside(p["x_mm"], p["y_mm"]):
            continue
        fp = fps[ref]
        key = spec_for(ref, fp["mpn"] or "", fp["fp"])
        sp = SPECS[key]
        module = sp.get("body_air") == "module_box" and not sens.get("module_pins_only", False)
        if module:
            # the whole module loss goes to the body node: the heat row's board / sink split was the stand-in for the
            # case-to-air path this network now solves, so it must cover the whole loss (S18)
            if abs(fr + p.get("sink_fraction", 0.0) - 1.0) > 1e-9:
                raise ValueError(f"{ref}: module heat row board_fraction {fr} + sink_fraction "
                                 f"{p.get('sink_fraction', 0.0)} != 1: its loss is not the whole module loss")
            watts = src
        r_scale = sens.get("r_scale", 1.0)
        pads = board_obj.pads_of(ref)
        # which pad numbers carry the heat
        nums = set(p.get("pad_numbers") or [])
        if not nums:
            nums = set(pads)
            if sp["pad_filter"] is not None and not sens.get("all_pins", False):
                nums = {n for n in nums if sp["pad_filter"](n)}
        # pad entries (pin, layer) -> overlap cells
        ents = []
        for n in sorted(nums):
            for layer, poly in pads[n]:
                z = CU_INDEX[layer]
                ii, jj, a = pad_overlap(poly, xmin, ymin, pitch, i0, j0, nx, ny)
                if a.size:
                    ents.append((n, layer, z, ii, jj, a))
        if not ents:
            raise ValueError(f"{ref}: no pad overlap on this mesh")
        tot = sum(e[5].sum() for e in ents)
        np_ = NetPart(ref, watts, key)
        r_pad = sp["r_pad"] * r_scale
        if module and sens.get("module_r_pad"):      # sensitivity: the pin path's assumed 15 K/W at another value
            r_pad = float(sens["module_r_pad"])
        gtot = 1.0 / r_pad
        for n, layer, z, ii, jj, a in ents:
            share = a.sum() / tot                    # heat/conductance split by pad copper area
            ids = z * nxy + ii * ny + jj
            np_.groups.append((ids, a / a.sum(), gtot * share, f"pad{n}.{layer}"))
        np_.r_top = sp["r_top"]
        # body -> air on the exposed top of the body
        body = None                                   # body extents in the footprint's local frame (F.Fab box)
        if fp.get("fab"):
            fb = fp["fab"]
            body = (fb[2] - fb[0], fb[3] - fb[1])
        elif sp["body_mm"]:
            body = sp["body_mm"]
        use_air = sp.get("body_air", True) and (p.get("sink_fraction", 0.0) == 0.0 or sens.get("air_all", False))
        in_region = region is not None and region.credits(ref, p["x_mm"], p["y_mm"])
        h_loc = region.h_top if in_region else h
        if sp.get("body_air") == "film_fin":
            if use_air and not sens.get("film_lead_only", False):
                hb = h_loc * sens.get("h_body_factor", 1.0)
                np_.g_air = film_body_g_air(hb)
                np_.t_air = sens.get("film_air_rise", FILM_HF_AIR_RISE_K)    # board-heated air (FILM_HF_AIR_RISE_K);
                np_.meta.update(body_area_mm2=film_body_area_mm2(), body_air_model="film_fin", h_body=hb,  # a region
                                film_air_rise_k=np_.t_air)                    # credit below replaces it
        elif sp.get("body_air") == "module_box":
            if module:                    # module_pins_only: the model before S18 (pins only, half the loss): a control
                hb = h_loc * sens.get("h_body_factor", 1.0)
                np_.g_air = module_body_g_air(hb, key)
                np_.t_air = sens.get("module_air_rise", MODULE_AIR_RISE_K)
                np_.meta.update(body_area_mm2=module_body_area_mm2(key), body_air_model="module_box", h_body=hb,
                                module_air_rise_k=np_.t_air, loss_w=src, heat_row_board_fraction=fr,
                                body_box_mm=list(body_box_mm(fp)), body_h_mm=MODULE_BODY[key]["h_mm"])
                gap_mm = sens.get("module_gap_mm")
                if gap_mm:                # sensitivity: bottom face to the board under it across an air gap
                    # local conduction: one tie per F.Cu cell under the body (K_AIR a_cell / gap), not one area-mean
                    # group (a group's flux couples every cell pair: 23 k cells at 0.25 mm is a dense 5e8 block)
                    poly = shapely.box(*body_box_mm(fp))
                    ii, jj, a = pad_overlap(poly, xmin, ymin, pitch, i0, j0, nx, ny)
                    for cid, ac in zip(0 * nxy + ii * ny + jj, a):
                        np_.groups.append((np.array([cid]), np.ones(1), K_AIR * ac * 1e-6 / (gap_mm * 1e-3), "gap"))
                    np_.meta["module_gap_mm"] = gap_mm
        elif body is not None and use_air:
            a_top = body[0] * body[1] * 1e-6
            hb = h_loc * sens.get("h_body_factor", 1.0)
            r_tot = sp["r_top"] + 1.0 / (hb * a_top)
            np_.g_air = 1.0 / r_tot
            np_.meta["body_area_mm2"] = body[0] * body[1]
        if in_region and np_.g_air > 0:
            np_.t_air = region.t_air_rise          # jet air (for a film cap: the jet sweeps the board's warm layer away)
            np_.meta["region_credited"] = True
            if "film_air_rise_k" in np_.meta:
                np_.meta["film_air_rise_k"] = region.t_air_rise
            if "module_air_rise_k" in np_.meta:
                np_.meta["module_air_rise_k"] = region.t_air_rise
        if sens.get("gap") and body is not None:
            cx, cy = fp["at"][0], fp["at"][1]
            rot = math.radians(fp["at"][2]) if len(fp["at"]) > 2 else 0.0
            bw, bh = body
            if abs(math.sin(rot)) > 0.5:
                bw, bh = bh, bw
            poly = shapely.box(cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2)
            ii, jj, a = pad_overlap(poly, xmin, ymin, pitch, i0, j0, nx, ny)
            gap = max(sp["standoff_mm"], 0.02) * 1e-3
            if a.size:
                np_.groups.append((0 * nxy + ii * ny + jj, a / a.sum(), K_AIR * a.sum() * 1e-6 / gap, "gap"))
        # reported pad copper: heated pads on the F.Cu layer (legacy reporting convention)
        lay = "F.Cu" if any(e[1] == "F.Cu" for e in ents) else ents[0][1]
        np_.metrics_pads = [(CU_INDEX[lay], e[3], e[4], e[5]) for e in ents if e[1] == lay]
        np_.meta.update(label=sp["label"], r_pad=r_pad, r_top=sp["r_top"], pads=len(nums), spec=key,
                        pad_area_mm2=float(tot), tj_limit=sp["tj_limit"], x=p["x_mm"], y=p["y_mm"],
                        watts=watts, sink_fraction=p.get("sink_fraction", 0.0))
        parts.append(np_)
    return parts, omitted


def solve_system(board, k, thk_m, heat, h, pitch_m, links, parts=(), dirichlet=None, rtol=1e-10, label="", leads=(),
                 top_region=None, tcr=None):
    """Solve for rises. `heat` (nz,nx,ny) W injected into cells (point-source part heat is already in it).
    dirichlet: None or (T_bc array (nz,nx,ny)) - the outer ring of cells (all sheets) is held at T_bc.
    leads: LeadLink fixed-temperature ties (FET drain leads to the sink); their heat to the sink is lead_sink_w.
    top_region: None or (mask (nx, ny), h_top, t_air_rise) - TopRegion cells of the top sheet convect at h_top to air
    at t_air_rise; parts carry their own NetPart.t_air.
    tcr: None (heat fixed, the 20 C copper model) or {"q20": (nz,nx,ny) W, the part of `heat` that is A4 copper at 20 C,
    "alpha": 1/K, "t_abs0_c": absolute temperature of zero rise (the case's bay air)} - the hot-copper fixed point
    T = M^-1 (b + q(T)), q = q20 (1 + alpha (t_abs0 + rise - 20)), fixed current paths. q is affine in T, so the fixed
    point is the solution of the linear system with -alpha q20 on the cell diagonal (solved exactly by CG); it is then
    checked by Picard steps on the unmodified operator until max |dT| < TCR_TOL_K. A non-SPD folded operator (CG
    failure) or a Picard check that does not settle is thermal runaway: RuntimeError, never a silent result.
    Returns rise (nz,nx,ny), rise_J (len(parts)), receipt."""
    nz, nx, ny = k.shape
    nxy = nx * ny
    rows, cols, vals, diag, ids, conv = assemble(board, k, thk_m, h, pitch_m, links,
                                                 None if top_region is None else top_region[:2])
    N = nz * nxy
    if tcr is not None:
        assert dirichlet is None, "the hot-copper fixed point is solved on global meshes only"
        q20 = np.where(np.broadcast_to(board, (nz, nx, ny)), tcr["q20"], 0.0).ravel()
        a_t, off = float(tcr["alpha"]), float(tcr["t_abs0_c"]) - 20.0
        d_tcr = a_t * q20                           # dq/dT per cell [W/K]
        diag = diag - d_tcr
        heat = heat + (a_t * off) * tcr["q20"]      # q at zero rise: q20 (1 + alpha (t_abs0 - 20))
    nJ = len(parts)
    diagJ = np.zeros(nJ)
    rhs = np.zeros(N + nJ)
    rhs[:N] = heat.ravel()
    inactive = ~np.broadcast_to(board, (nz, nx, ny))
    r2, c2, v2 = [], [], []
    for s, p in enumerate(parts):
        J = N + s
        rhs[J] = p.watts
        diagJ[s] += p.g_air
        if p.t_air:
            rhs[J] += p.g_air * p.t_air
        for gids, w, g, _ in p.groups:
            onb = board.ravel()[gids % nxy]          # cells off the board outline carry no heat path: drop and renormalise
            if not onb.all():
                gids, w = gids[onb], w[onb] / w[onb].sum()
            # flux into cells = g (T_J - w.T) w   =>   M_cc' += g w w',  M_cJ = M_Jc = -g w,  M_JJ += g
            r2.append(np.repeat(gids, len(gids)))
            c2.append(np.tile(gids, len(gids)))
            v2.append((g * np.outer(w, w)).ravel())
            r2.extend((gids, np.full(len(gids), J)))
            c2.extend((np.full(len(gids), J), gids))
            v2.extend((-g * w, -g * w))
            diagJ[s] += g
    lead_groups = []
    for lk in leads:
        for gids, w, g, _ in lk.groups:
            onb = board.ravel()[gids % nxy]
            if not onb.all():
                gids, w = gids[onb], w[onb] / w[onb].sum()
            # flux into cells = g (T_s - w.T) w   =>   M_cc' += g w w',  rhs_c += g T_s w
            r2.append(np.repeat(gids, len(gids)))
            c2.append(np.tile(gids, len(gids)))
            v2.append((g * np.outer(w, w)).ravel())
            np.add.at(rhs, gids, g * lk.t_rise * w)
            lead_groups.append((gids, w, g, lk.t_rise))
    if top_region is not None and top_region[2]:
        m, h_top, t_air = top_region
        rhs[ids[0][m & board]] += h_top * pitch_m * pitch_m * t_air
    diag_full = np.concatenate([diag, diagJ])
    # outer-product blocks add to the cell diagonal: pull them out of the COO so Jacobi sees the true diagonal
    diag_extra = np.zeros(N + nJ)
    for r_, c_, v_ in zip(r2, c2, v2):
        m = r_ == c_
        if m.any():
            np.add.at(diag_extra, r_[m], v_[m])
    diag_full = diag_full + diag_extra
    diag_full[:N][ids[inactive]] = 1.0
    keep_r = [r_[r_ != c_] for r_, c_ in zip(r2, c2)]
    keep_c = [c_[r_ != c_] for r_, c_ in zip(r2, c2)]
    keep_v = [v_[r_ != c_] for r_, c_, v_ in zip(r2, c2, v2)]
    rr = np.concatenate(rows + keep_r + [np.arange(N + nJ)]) if (rows or keep_r) else np.arange(N + nJ)
    cc = np.concatenate(cols + keep_c + [np.arange(N + nJ)]) if (cols or keep_c) else np.arange(N + nJ)
    vv = np.concatenate(vals + keep_v + [diag_full]) if (vals or keep_v) else diag_full
    M = coo_matrix((vv, (rr, cc)), shape=(N + nJ, N + nJ)).tocsr()
    rhs[:N][ids[inactive]] = 0.0
    bc_flux = 0.0
    if dirichlet is None:
        iters = [0]
        pre = LinearOperator(M.shape, matvec=lambda v: v / diag_full)
        if tcr is not None and (diag_full[:N] <= 0).any():
            raise RuntimeError(f"hot-copper operator lost its diagonal (dq/dT exceeds the cell's conductance): thermal "
                               f"runaway {label}")
        x, info = cg(M, rhs, rtol=rtol, atol=1e-14, M=pre, maxiter=40000,
                     callback=lambda _: iters.__setitem__(0, iters[0] + 1))
        if info != 0:
            raise RuntimeError(f"CG failed info={info} it={iters[0]} {label}"
                               + (" (hot copper: the folded operator is not SPD - thermal runaway)" if tcr else ""))
        resid = float(np.linalg.norm(M @ x - rhs) / max(np.linalg.norm(rhs), 1e-30))
        TB = None
    else:
        ring = np.zeros((nx, ny), bool)
        ring[0, :] = ring[-1, :] = ring[:, 0] = ring[:, -1] = True
        Bmask = np.zeros(N + nJ, bool)
        Bmask[:N] = np.broadcast_to(ring, (nz, nx, ny)).ravel()
        Bidx = np.flatnonzero(Bmask)
        Uidx = np.flatnonzero(~Bmask)
        TBv = dirichlet.ravel()[Bidx]
        MUU = M[Uidx][:, Uidx]
        MUB = M[Uidx][:, Bidx]
        rhsU = rhs[Uidx] - MUB @ TBv
        dU = diag_full[Uidx]
        iters = [0]
        pre = LinearOperator(MUU.shape, matvec=lambda v: v / dU)
        xU, info = cg(MUU, rhsU, rtol=rtol, atol=1e-14, M=pre, maxiter=40000,
                      callback=lambda _: iters.__setitem__(0, iters[0] + 1))
        if info != 0:
            raise RuntimeError(f"CG failed info={info} it={iters[0]} {label}")
        x = np.zeros(N + nJ)
        x[Uidx] = xU
        x[Bidx] = TBv
        resid = float(np.linalg.norm(MUU @ xU - rhsU) / max(np.linalg.norm(rhsU), 1e-30))
        # conductive flux from interior into the ring (independent edge sum)
        S = -MUB.tocsr()
        bc_flux = float((S.sum(axis=1).A1 * xU).sum() - (S.sum(axis=0).A1 * TBv).sum())
        # interior rows in the ring-adjacent layer carry the ring's convection too: those nodes are fixed, not counted
    tcr_rec = None
    if tcr is not None:
        # Picard check on the unmodified operator M0 = M + diag(d_tcr): x_{k+1} = M0^-1 (b + q(x_k)), warm-started
        M0 = M + csr_matrix((np.concatenate([d_tcr, np.zeros(nJ)]), (np.arange(N + nJ), np.arange(N + nJ))),
                            shape=M.shape)
        d0 = diag_full + np.concatenate([d_tcr, np.zeros(nJ)])
        pre0 = LinearOperator(M0.shape, matvec=lambda v: v / d0)
        rhs0 = rhs.copy()
        steps, dmax = 0, float("inf")
        while steps < TCR_MAX_ITER:
            rhs_k = rhs0.copy()
            rhs_k[:N] += d_tcr * x[:N]
            xk, info = cg(M0, rhs_k, x0=x, rtol=rtol, atol=1e-14, M=pre0, maxiter=40000)
            if info != 0:
                raise RuntimeError(f"hot-copper Picard check: CG failed info={info} {label}")
            dmax = float(np.abs(xk[:N] - x[:N]).max())
            x = xk
            steps += 1
            if dmax < TCR_TOL_K:
                break
        else:
            raise RuntimeError(f"hot-copper fixed point did not settle (max |dT| {dmax:.3g} K after {steps} Picard "
                               f"steps): thermal runaway {label}")
        # loop gain: the Rayleigh quotient x'Dx / x'M0x of the solved field bounds rho(M0^-1 D) from below; >= 1 is a
        # runaway (the folded operator is then indefinite and its "solution" unphysical)
        gain = float((d_tcr * x[:N] ** 2).sum() / max(float(x @ (M0 @ x)), 1e-300))
        if not gain < 1.0:
            raise RuntimeError(f"hot copper: loop gain {gain:.3g} >= 1 (thermal runaway) {label}")
        q_hot = q20 * (1.0 + a_t * (off + x[:N]))
        tcr_rec = {"alpha": a_t, "t_abs0_c": float(tcr["t_abs0_c"]), "picard_steps": steps, "max_dT_k": dmax,
                   "loop_gain_rayleigh": gain,
                   "q20_w": float(q20.sum()), "q_hot_w": float(q_hot.sum())}
        heat = (heat - (a_t * off) * tcr["q20"]) + (q_hot - q20).reshape(nz, nx, ny)   # the heat actually injected
    rise = x[:N].reshape(nz, nx, ny)
    riseJ = x[N:]
    if dirichlet is None:
        conv_w = float(conv * (rise[0][board].sum() + rise[-1][board].sum()))
        live = board
    else:
        inner = board.copy()
        inner[0, :] = inner[-1, :] = inner[:, 0] = inner[:, -1] = False
        conv_w = float(conv * (rise[0][inner].sum() + rise[-1][inner].sum()))
        live = inner
    region_w = None
    if top_region is not None:
        m, h_top, t_air = top_region
        sel = m & live
        a_cell = pitch_m * pitch_m
        region_w = float(h_top * a_cell * (rise[0][sel] - t_air).sum())
        conv_w += region_w - float(conv * rise[0][sel].sum())
    if any(p.t_air for p in parts):
        air_w = float(sum(p.g_air * (riseJ[s] - p.t_air) for s, p in enumerate(parts)))
    else:
        air_w = float(sum(p.g_air * riseJ[s] for s, p in enumerate(parts)))
    lead_w = float(sum(g * (float((x[gids] * w).sum()) - ts) for gids, w, g, ts in lead_groups))   # board -> sink
    if dirichlet is None:
        src = float(heat[:, board].sum() + sum(p.watts for p in parts))
    else:
        inner = board.copy()
        inner[0, :] = inner[-1, :] = inner[:, 0] = inner[:, -1] = False
        src = float(heat[:, inner].sum() + sum(p.watts for p in parts))
    out_w = conv_w + air_w + bc_flux + lead_w
    rec = {"source_w": src, "convection_w": conv_w, "body_air_w": air_w, "boundary_flux_w": bc_flux, "lead_sink_w": lead_w,
           "balance_w": src - out_w, "balance_rel": (src - out_w) / max(abs(src), 1e-30),
           "cg_iterations": iters[0], "relative_residual": resid}
    if region_w is not None:
        rec["region_top_convection_w"] = region_w
    if tcr_rec is not None:
        rec["tcr"] = tcr_rec
    return rise, riseJ, rec


# --------------------------------------------------------------------------------------------------------------
# analytic control: uniformly heated disc on an infinite fin plate (both faces convect)
# --------------------------------------------------------------------------------------------------------------
def analytic_disc(pitch_mm=0.25, a_mm=3.0, half_mm=45.0, h=250.0, t_um=70.0, watts=1.0, r_pad=10.0):
    """Network source on one sheet: a disc pad of radius a, flux uniform over the disc.

    Exact (modified Bessel): rise(r<a) = q/(2h) [1 - m a K1(m a) I0(m r)], m^2 = 2h/(k t), q = P/(pi a^2).
    Disc-mean rise = q/(2h) [1 - 2 K1(ma) I1(ma)].  T_J = disc mean + P r_pad.
    """
    k, t = K_CU, t_um * 1e-6
    m = math.sqrt(2 * h / (k * t))
    a = a_mm * 1e-3
    q = watts / (math.pi * a * a)
    mean_exact = q / (2 * h) * (1 - 2 * bessel_k1(m * a) * bessel_i1(m * a))
    centre_exact = q / (2 * h) * (1 - m * a * bessel_k1(m * a))
    nxy = round(2 * half_mm / pitch_mm)
    board = np.ones((nxy, nxy), bool)
    kk = np.full((1, nxy, nxy), k)
    xmin = ymin = 0.0
    poly = Point_buffer(half_mm, half_mm, a_mm)
    ii, jj, area = pad_overlap(poly, xmin, ymin, pitch_mm, 0, 0, nxy, nxy)
    part = NetPart("DISC", watts, "analytic")
    part.groups.append((ii * nxy + jj, area / area.sum(), 1.0 / r_pad, "disc"))
    rise, riseJ, rec = solve_system(board, kk, np.array([t]), np.zeros((1, nxy, nxy)), h, pitch_mm * 1e-3, [], [part])
    w = area / area.sum()
    mean_num = float((rise[0][ii, jj] * w).sum())
    centre_num = float(rise[0][int(half_mm / pitch_mm) - 1:int(half_mm / pitch_mm) + 1,
                               int(half_mm / pitch_mm) - 1:int(half_mm / pitch_mm) + 1].mean())
    tj_exact = mean_exact + watts * r_pad
    return {"pitch_mm": pitch_mm, "disc_radius_mm": a_mm, "h_w_m2k": h, "fin_length_mm": 1e3 / m,
            "mean_exact_k": mean_exact, "mean_numeric_k": mean_num, "mean_rel_err": abs(mean_num - mean_exact) / mean_exact,
            "junction_exact_k": tj_exact, "junction_numeric_k": float(riseJ[0]),
            "junction_rel_err": abs(float(riseJ[0]) - tj_exact) / tj_exact,
            "centre_exact_k": centre_exact, "centre_numeric_k": centre_num,
            "centre_rel_err": abs(centre_num - centre_exact) / centre_exact, **rec}


def Point_buffer(cx, cy, r):
    from shapely.geometry import Point
    return Point(cx, cy).buffer(r, 256)


if __name__ == "__main__":
    import pprint
    pprint.pprint(analytic_disc())
