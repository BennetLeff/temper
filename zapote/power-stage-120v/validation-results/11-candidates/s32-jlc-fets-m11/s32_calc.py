#!/usr/bin/env python3
"""S32: can the R45 enclosure's M11 stack (shared rigid 2.0 mm AlN tiles) take JLC-soldered Q2 / Q3 / Q5 / Q6?

    python3 -I s32_calc.py            (from this folder)  -> s32-calc.json, and the tables printed to stdout

No new physics inputs where the repo has them. Imported read-only (nothing is written outside this folder):
  [SC]  owner-items/m11/stack_calc.py            grease per interface (opt TC-5622 TDS / cons TIC1000A proxy), aln(), TAB
  [BP]  bench-sink-r1/scripts/bench_params.py    TO-247 outline, FET x, tab nets, JLC hole/position tolerances, shim k,
                                                 shim step, gap-pad data (GAP PAD 5000S35), placement tolerance
  [BM]  bench-sink-r1/scripts/bench_mech.py      lead play, tab-offset bound, lead rotation stiffness
  [BT]  bench-sink-r1/scripts/bench_tolerance.py spreads(): U / R x lot / datasheet A1 (DECISIONS 87 / 89 numbers)
  [BTh] bench-sink-r1/scripts/bench_thermal.py   shim_stack() (cross-check only)
  [WR]  tools/write_rules.py                     FUNCTIONAL_CREEPAGE_MM (Table 18, PD3, >125-250 V), REINFORCED_MM
  [C60] c60-seating-fixture/seat-tolerance.json  fixture lead-corner verdicts
  [CMB] owner-items/m11-sourcing/M11-SOURCING.md comb finger: k 27.2 N/mm, preload 2.6 mm, 737 MPa at 2.6 mm,
                                                 Rm 1300 MPa, band 60-82 N over 2.2-3.0 mm (text, hard-coded below)
  [SDN] owner-items/m11/SINK-DRAWING-NOTES.md    sink face Y 244.3 +/- 1 (floats, locked after the comb); comb
                                                 acceptance 45-102 N per TO-247
  [M11] owner-items/m11/RECOMMENDATION.md        tile z 0.2-32, pedestal lower edge z 8.0, 8.0 mm reinforced paths
EST marks an engineering estimate. A "bound" in the output is only called that where every dropped term is >= 0.
"""
from __future__ import annotations

import importlib.util
import json
import math
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PS = HERE.parents[2]                                            # zapote/power-stage-120v
BENCH = PS / "validation-results/11-candidates/bench-sink-r1"
M11 = PS / "validation-results/08-manufacturing-package/native-21/owner-items/m11"
C60 = PS / "validation-results/11-candidates/c60-seating-fixture"
sys.path.insert(0, str(BENCH / "scripts"))
import bench_params as P  # noqa: E402
import bench_mech as BM  # noqa: E402
import bench_tolerance as BT  # noqa: E402
import bench_thermal as BTh  # noqa: E402

_s = importlib.util.spec_from_file_location("stack_calc", M11 / "stack_calc.py")
SC = importlib.util.module_from_spec(_s)
_s.loader.exec_module(SC)                                       # module level only; main() (which writes) is not run

WR = (PS / "tools/write_rules.py").read_text()
FUNC_CREEP = float(re.search(r"^FUNCTIONAL_CREEPAGE_MM = ([0-9.]+)", WR, re.M).group(1))
REINF = float(re.search(r"^REINFORCED_MM = ([0-9.]+)", WR, re.M).group(1))

T = P.TO247
BUDGET = 0.7                                                    # D-36: "MOSFET interface <= 0.7 C/W" (DECISIONS.md, 2026-10-06)
G = {"opt": 0.06, "cons": P.GREASE_CM2[1]}                      # C-cm2/W per greased interface ([SC] / [BP]: 0.06, 0.4129)
K_SHIM = {"Al 6061": P.K_SHIM, "Cu C110 (EST 390)": 390.0, "brass (bench bound)": P.K_SHIM_FET}
K_ALN, T_ALN = 150.0, 2.0                                       # [SC] Kyocera AN216A, 2.0 mm tile
TAB_SMALL, TAB_LARGE = P.TAB_AREA                               # 151.2 / 240.1 mm2 [T03 via BP]
HOLE = T["E1"][0] * T["D1"][0] - TAB_SMALL                      # tab hole area implied by T03's small-tab figure
PLACE = P.STRIP_PLACE_TOL                                       # 0.5 mm EST: hand placement of a loose part on the tab
TILE_SHARE = 18.0 * (32.0 - 0.2)                                # one FET pitch of tile, z 0.2-32 [M11]: spreading credit
X_PLAY = P.FET_POS_TOL + P.HOLE_POS_TOL                         # device x float in its holes + hole position [BP]
COMB = dict(k=27.2, d0=2.6, sigma_at_d0=737.0, rm=1300.0, band=(60.0, 82.0), band_d=(2.2, 3.0), tol=0.4)   # [CMB]
COMB_ACCEPT = P.CLAMP_ACCEPT_N                                  # (45, 102) N [SDN]
SINK_FLOAT = 1.0                                                # [SDN] Y 244.3 +/- 1
COMB_LEVER = 16.0                                               # [CMB] finger contact line at board z ~16
# coplanarity budget of a shimmed face, EST terms (the requirement is 0.05 mm [SDN])
COPLANAR_REQ = 0.05
COPLANAR_EST = dict(step_rounding=P.SHIM_STEP / 2, shim_thickness_tol_per_layer=0.010, extra_bond_line_var=0.010,
                    offset_measurement=0.010)


def r(area_mm2, g_cm2):
    return g_cm2 * 100.0 / area_mm2


def bulk(t_mm, k, area_mm2):
    return t_mm * 1e-3 / (k * area_mm2 * 1e-6)


def tab_area(corner):
    return TAB_SMALL if corner == "small" else TAB_LARGE


def shim_area_hot(corner):
    """Shim strictly inside the tab metal: (E1 - 2 PLACE) x (D1 - 2 PLACE) less the tab hole (no metal behind it)."""
    i = 0 if corner == "small" else 1
    return (T["E1"][i] - 2 * PLACE) * (T["D1"][i] - 2 * PLACE) - HOLE


def baseline(corner, g):
    a = tab_area(corner)
    return r(a, g) + bulk(T_ALN, K_ALN, a) + r(a, g)


# ------------------------------------------------------------------ (a1) HOT-side shim between tab and the shared tile
def a1(corner, g, k, t_s, layers, geometry):
    """tab | grease | shim (layers) | grease | AlN | grease | pedestal. The shim is the only contact, so every layer up to
    the AlN carries the heat over the shim area. geometry 'cons' = the repo's 1-D convention (no spreading credit, as
    stack_calc); 'spread' = AlN free (0) and the PE-side grease spread over a whole tile pitch (EST, generous: the 2 mm
    tile's spreading length sqrt(k t R'') is ~3.5 mm at the cons grease); 'strict' = only the tab-side greased faces and
    the shim bulk, everything after the shim dropped: a lower bound for the given grease value and shim area."""
    a = shim_area_hot(corner)
    rr = r(a, g) * (layers + 1) + bulk(t_s, k, a)
    if geometry == "cons":
        rr += bulk(T_ALN, K_ALN, a) + r(a, g)
    elif geometry == "spread":
        rr += r(TILE_SHARE, g)
    return rr                                                   # 'strict': AlN and PE-side grease dropped (>= 0)


def g_star_a1(corner, k, t_s, layers, geometry):
    """Grease value per interface (C-cm2/W) at which the a1 stack meets the 0.7 budget exactly (R is linear in g)."""
    r0, r1 = a1(corner, 0.0, k, t_s, layers, geometry), a1(corner, 1.0, k, t_s, layers, geometry)
    return (BUDGET - r0) / (r1 - r0)


# ------------------------------------------------------------------ (a2) per-FET tiles, PE-side shim behind each tile
def joint_reach(a_mm):
    """Per-device tiles: HOT->PE path at a joint = a (tab metal edge to joint) + t (down the joint) + g (under the tile
    to the PE shim) >= 8.0, so the PE shim edge stays g = 8 - t - a from the joint, i.e. g - a = 8 - t - 2a under the
    tab metal (per_device_calc.py's 'reaches ... under the tab metal')."""
    return max(0.0, REINF - T_ALN - 2 * a_mm)


def a2_cut(worst):
    """Width of tab metal (x) left over the PE shim per device; 2 mm body gaps at 18.0 pitch, 6.1 mm at Q6|Q3."""
    e_side = (T["E"][0] - T["E1"][1]) / 2                       # 0.675: plastic beside the metal
    gaps = {"Q5|Q6": 2.0, "Q6|Q3": 6.1, "Q3|Q2": 2.0, "Q2|BR1": 3.55}   # per_device_calc.py (F.Fab nominal)
    play = 2 * X_PLAY if worst else 0.0
    reach = {k: joint_reach(max(0.0, (v - (play if k != "Q2|BR1" else 0.0)) / 2) + e_side) for k, v in gaps.items()}
    cut = {"Q5": reach["Q5|Q6"], "Q6": reach["Q5|Q6"] + reach["Q6|Q3"], "Q3": reach["Q6|Q3"] + reach["Q3|Q2"],
           "Q2": reach["Q3|Q2"] + reach["Q2|BR1"]}
    return reach, cut


def a2(corner, g, k, t_s, cut_mm):
    """tab | grease | own AlN tile | grease | PE shim | grease | pedestal, the repo's 1-D convention: the tile, the two
    PE-side greased faces and the shim are taken over the tab metal that lies over the shim (no spreading credit)."""
    a = tab_area(corner)
    i = 0 if corner == "small" else 1
    a_s = a * max(0.0, T["E1"][i] - cut_mm) / T["E1"][i]       # tab metal over the shim, pro rata in x (EST)
    rr = r(a, g) + bulk(T_ALN, K_ALN, a_s) + r(a_s, g) + bulk(t_s, k, a_s) + r(a_s, g)
    return rr, a_s


# ------------------------------------------------------------------ (b) compliant layer replacing the tab-side grease
def b_rows(spreads):
    rows = []
    gp = P.GAP5000
    s_lo, s_hi = gp["strain"]
    for case, d in spreads.items():
        t0 = d / (s_hi - s_lo)                                  # pre-cut pad: the spread must fit the 10-30 % data window
        for corner in ("small", "large"):
            a = tab_area(corner)
            rest_opt = bulk(T_ALN, K_ALN, a) + r(a, G["opt"])   # AlN + PE-side grease, optimistic
            rest_cons = bulk(T_ALN, K_ALN, a) + r(a, G["cons"])
            pad_bulk = (1 - s_lo) * t0 * 1e-3 / (gp["k"] * a * 1e-6)      # max-gap device, least strain: bulk only
            pad_data = gp["z_040"][s_lo] * (t0 / (0.040 * 25.4)) * 645.16 / a   # catalogue impedance scaled with t (EST)
            fill_bulk_k5 = d * 1e-3 / (gp["k"] * a * 1e-6)                # dispensed filler at k 5: the gap alone
            k_req_free = d * 1e-3 / (a * 1e-6 * BUDGET)                   # k needed if every other layer were free
            k_req_opt = d * 1e-3 / (a * 1e-6 * (BUDGET - rest_opt))
            k_req_cons = d * 1e-3 / (a * 1e-6 * (BUDGET - rest_cons))
            rows.append(dict(case=case, spread_mm=round(d, 3), corner=corner, pad_t0_mm=round(t0, 2),
                             pad_bulk_lower_bound=round(pad_bulk, 3), pad_catalogue_est=round(pad_data, 3),
                             pad_total_lower_bound=round(pad_bulk, 3),
                             filler_k5_gap_only_lower_bound=round(fill_bulk_k5, 3),
                             k_needed_everything_else_free=round(k_req_free, 1), k_needed_opt_rest=round(k_req_opt, 1),
                             k_needed_cons_rest=round(k_req_cons, 1)))
    return rows


def main():
    out = {"inputs": {}, "controls": {}}
    sp = BT.spreads()
    spreads = {"U datasheet A1": sp["U_datasheet"], "U lot A1": sp["U_lot"], "R datasheet A1": sp["R_datasheet"],
               "R lot A1": sp["R_lot"]}
    # ---- controls: we reproduce the committed numbers we build on
    tol = json.loads((BENCH / "results/tolerance.json").read_text())
    assert abs(tol["spread"]["U_datasheet"] - sp["U_datasheet"]) < 1e-9 and abs(sp["U_datasheet"] - 2.1) < 1e-9
    stk = json.loads((M11 / "stack-calc.json").read_text())["candidates"]["AlN 2.0 mm + 2x grease (RECOMMENDED)"]
    base = {c: {gk: baseline(c, gv) for gk, gv in G.items()} for c in ("small", "large")}
    assert round(base["large"]["cons"], 3) == stk["R_cs_cons_C_per_W"][0] and round(base["small"]["cons"], 3) == stk["R_cs_cons_C_per_W"][1]
    assert round(base["small"]["opt"], 3) == stk["R_cs_opt_C_per_W"][1]
    th = json.loads((BENCH / "results/thermal.json").read_text())["shim_stack_C_per_W"]
    assert abs(BTh.shim_stack(TAB_SMALL)[0] - th["small"][0]) < 1e-9
    # a1 with the bench's own stack (full tab area, brass 2.2, 3 faces, cons) must equal bench_thermal's shim_stack
    bench_like = r(TAB_SMALL, G["cons"]) * P.SHIM_LAYERS_MAX + bulk(P.SHIM_MAX_DESIGN, P.K_SHIM_FET, TAB_SMALL)
    assert abs(bench_like - th["small"][0]) < 1e-9
    assert FUNC_CREEP == 3.2 and REINF == 8.0
    out["controls"] = dict(baseline_reproduces_stack_calc=True, bench_shim_stack_reproduced=round(th["small"][0], 3),
                           spreads_reproduce_tolerance_json=True)
    out["inputs"] = dict(budget_C_per_W=BUDGET, grease_C_cm2_per_W=G, k_shim=K_SHIM, tab_area_mm2=P.TAB_AREA,
                         hole_mm2=round(HOLE, 2), shim_place_tol_mm_EST=PLACE, shim_area_hot_mm2={c: round(shim_area_hot(c), 1) for c in ("small", "large")},
                         spreads_mm=spreads, shim_max_design_mm=P.SHIM_MAX_DESIGN, functional_creepage_mm=FUNC_CREEP,
                         reinforced_mm=REINF, x_play_mm=X_PLAY)
    print(f"Controls OK: baseline AlN 2.0 + 2 grease = {base['large']['cons']:.3f}-{base['small']['cons']:.3f} C/W cons, "
          f"{base['large']['opt']:.3f}-{base['small']['opt']:.3f} opt (stack-calc.json); bench shim stack {th['small'][0]:.3f} reproduced")
    print(f"Spreads (bench_tolerance.spreads): {', '.join(f'{k} {v:.3f}' for k, v in spreads.items())} mm")

    # ---- insulation: which tab is on which net, and the tab-to-tab metal distance over the shared tile
    xs = sorted(P.FET_X.items(), key=lambda kv: kv[1])
    pairs = []
    for (na, xa), (nb, xb) in zip(xs, xs[1:]):
        pitch = xb - xa
        nom = pitch - T["E1"][1]
        worst = nom - 2 * X_PLAY
        corner_play_x = BM.corner_play(BM.hole_fin()[1], T["c"][0], T["b"][0])   # across b: smallest lead, largest hole
        worst_corner = nom - 2 * (corner_play_x + P.HOLE_POS_TOL)
        pairs.append(dict(pair=f"{na}({P.TAB_NET[na]})-{nb}({P.TAB_NET[nb]})", pitch=round(pitch, 2),
                          metal_gap_centred_E1max=round(nom, 3), metal_gap_worst_flat_play=round(worst, 3),
                          metal_gap_worst_corner_play=round(worst_corner, 3), floor=FUNC_CREEP,
                          ok_worst=worst >= FUNC_CREEP, ok_centred=nom >= FUNC_CREEP))
    out["tab_to_tab"] = pairs
    e1_limit = 18.0 - FUNC_CREEP - 2 * X_PLAY
    out["tab_to_tab_E1_limit_mm"] = round(e1_limit, 3)
    print("\nTab-to-tab metal distance on the shared tile (E1 max 14.15; Table 18 PD3 >125-250 V floor 3.2 mm):")
    for p_ in pairs:
        print(f"  {p_['pair']:28s} pitch {p_['pitch']:5.2f}: centred {p_['metal_gap_centred_E1max']:.3f}, worst (flat play) "
              f"{p_['metal_gap_worst_flat_play']:.3f}, worst (corner play) {p_['metal_gap_worst_corner_play']:.3f}  ok_worst={p_['ok_worst']}")
    print(f"  E1 that keeps 3.2 mm at the 18.0 pitch with the flat x-play bound: <= {e1_limit:.3f} mm (datasheet {T['E1'][0]}-{T['E1'][1]})")
    w_max = T["E1"][0] - 2 * PLACE
    out["a1_shim_max_width_mm"] = round(w_max, 2)
    print(f"a1 shim width <= E1 min - 2 x {PLACE} = {w_max:.2f} mm (x) and D1 min - 2 x {PLACE} = {T['D1'][0] - 2 * PLACE:.2f} mm (z): "
          "the shim stays inside its own tab metal, so no tab-to-tab or HOT->PE distance gets shorter than without it.")

    # ---- (a1) thermal
    print("\n(a1) HOT-side shim, shared tile. R_cs per FET, C/W (budget 0.7). shim area small/large tab: "
          f"{shim_area_hot('small'):.1f} / {shim_area_hot('large'):.1f} mm2")
    a1_rows = []
    for corner in ("small", "large"):
        for gk in ("cons", "opt"):
            for mat, k in K_SHIM.items():
                for t_s, layers in ((0.025, 1), (P.SHIM_MAX_DESIGN, 1), (P.SHIM_MAX_DESIGN, 2)):
                    rc = a1(corner, G[gk], k, t_s, layers, "cons")
                    rs = a1(corner, G[gk], k, t_s, layers, "spread")
                    rb = a1(corner, G[gk], k, t_s, layers, "strict")
                    v = ("PASS" if rc <= BUDGET else "FAIL (bound)" if rb > BUDGET else "FAIL (1-D and spread est.)"
                         if rs > BUDGET else "FAIL (1-D only)")
                    a1_rows.append(dict(corner=corner, grease=gk, shim=mat, t_mm=t_s, layers=layers, R_1D=round(rc, 3),
                                        R_spread_est=round(rs, 3), R_lower_bound=round(rb, 3), margin_1D=round(BUDGET - rc, 3),
                                        verdict=v))
    for row in a1_rows:
        if row["shim"] != "brass (bench bound)":
            print(f"  tab {row['corner']:5s} grease {row['grease']:4s} {row['shim']:18s} {row['t_mm']:5.3f} mm x{row['layers']}: "
                  f"1-D {row['R_1D']:.3f}  spread est {row['R_spread_est']:.3f}  bound {row['R_lower_bound']:.3f}  "
                  f"margin {row['margin_1D']:+.3f}  {row['verdict']}")
    out["a1"] = a1_rows
    lam = math.sqrt(K_ALN * T_ALN * 1e-3 * G["cons"] * 1e-4) * 1e3
    out["a1_aln_spreading_length_mm"] = round(lam, 2)
    print(f"  AlN spreading length sqrt(k t R'') at the cons grease: {lam:.2f} mm (why the 'spread' geometry is generous)")
    gstar = {}
    for corner in ("small", "large"):
        for mat in ("Al 6061", "Cu C110 (EST 390)"):
            for layers in (1, 2):
                for geo in ("cons", "spread"):
                    gstar[f"{corner} {mat} 2.2 mm x{layers} {geo}"] = round(g_star_a1(corner, K_SHIM[mat], P.SHIM_MAX_DESIGN, layers, geo), 4)
    out["a1_grease_threshold_C_cm2_per_W"] = gstar
    print("  grease value per interface that just meets 0.7 at a 2.2 mm shim (C-cm2/W; repo opt 0.06, cons 0.413):")
    for kx, v in gstar.items():
        print(f"    {kx:40s} {v:.4f}")
    # proud device (no shim): baseline stack
    out["a1_unshimmed_device"] = {c: round(base[c]["cons"], 3) for c in base}
    # coplanarity budget
    cop1 = COPLANAR_EST["step_rounding"] + COPLANAR_EST["shim_thickness_tol_per_layer"] + COPLANAR_EST["extra_bond_line_var"] + COPLANAR_EST["offset_measurement"]
    cop2 = cop1 + COPLANAR_EST["shim_thickness_tol_per_layer"] + COPLANAR_EST["extra_bond_line_var"]
    out["a1_coplanarity_EST"] = dict(terms=COPLANAR_EST, one_layer=round(cop1, 4), two_layers=round(cop2, 4), req=COPLANAR_REQ)
    print(f"  shimmed-face coplanarity (EST, linear sum): 1 layer {cop1:.4f} mm, 2 layers {cop2:.4f} mm vs {COPLANAR_REQ} mm")
    # lean: the comb straightens it about the leads, as on the bench
    th_acc = tol["theta_accept_rad"]
    f_lean = tol["mech"]["k_rot_max"] * th_acc / COMB_LEVER
    out["a1_lean"] = dict(theta_accept_rad=th_acc, force_spent_N=round(f_lean, 1), comb_band_low_after_N=round(COMB["band"][0] - f_lean, 1))
    print(f"  lean: bench inspection limit {th_acc:.4f} rad; straightening it at a {COMB_LEVER} mm lever spends {f_lean:.1f} N of the "
          f"comb's {COMB['band'][0]:.0f} N floor -> {COMB['band'][0] - f_lean:.1f} N left (acceptance >= {COMB_ACCEPT[0]:.0f})")
    # plane position, sink float, comb deflection, BR1 gap
    e = BM.tab_offset_bound()
    out["plane"] = dict(offset_bound_mm=round(e, 3), sink_float_drawing_mm=SINK_FLOAT, sink_float_needed_toward_sink_mm=round(e, 3),
                        short_by_mm=round(max(0.0, e - SINK_FLOAT), 3))
    print(f"\nTile plane = the most-proud tab (or nominal, if every tab is recessed): 0 .. {e:.3f} mm toward the sink; "
          f"drawing float +/- {SINK_FLOAT} -> short by {max(0.0, e - SINK_FLOAT):.3f} mm on the sink side")
    d_hi = COMB["d0"] + COMB["tol"] + P.SHIM_MAX_DESIGN
    f_hi, s_hi = COMB["k"] * d_hi, COMB["sigma_at_d0"] / COMB["d0"] * d_hi
    out["comb_as_is"] = dict(deflection_max_mm=round(d_hi, 2), force_N=round(f_hi, 1), stress_MPa=round(s_hi, 0),
                             accept_N=COMB_ACCEPT, rm_MPa=COMB["rm"], ok=f_hi <= COMB_ACCEPT[1] and s_hi < COMB["rm"])
    print(f"Comb as specified (k {COMB['k']} N/mm, preload {COMB['d0']} +/- {COMB['tol']} mm): a recessed device's front sits up to "
          f"{P.SHIM_MAX_DESIGN} mm further out -> {d_hi:.1f} mm, {f_hi:.0f} N (accept <= {COMB_ACCEPT[1]:.0f}), {s_hi:.0f} MPa (Rm {COMB['rm']:.0f}): "
          f"ok = {out['comb_as_is']['ok']}")
    br1_play = (BM.corner_play(P.BR1_DRILL_FIN[0], P.GBJ["lead_w"][1], P.GBJ["lead_t"][1]), (P.BR1_DRILL_FIN[1] - P.GBJ["lead_t"][0]) / 2)
    br1_gap = (P.Y_BR1_BACK - P.Y_TAB - br1_play[1], P.Y_BR1_BACK - P.Y_TAB + e + br1_play[1])
    out["br1_gap_to_tile_mm"] = [round(v, 3) for v in br1_gap]
    print(f"BR1 back to tile B: {br1_gap[0]:.3f} .. {br1_gap[1]:.3f} mm (nominal {P.Y_BR1_BACK - P.Y_TAB:.3f}; 1.0 mm pad compresses to 0.47-0.87 in [SDN])")

    # ---- (a2) per-FET tiles, PE-side shims
    print("\n(a2) per-FET tiles, PE-side shim. Tab metal lost over the joint relief (x):")
    a2_out = {}
    for worst in (False, True):
        reach, cut = a2_cut(worst)
        lab = "worst x play" if worst else "nominal (per_device_calc)"
        a2_out[lab] = dict(reach=reach, cut=cut, rows=[])
        print(f"  {lab}: reach under tab metal per joint {', '.join(f'{k} {v:.2f}' for k, v in reach.items())}; cut per FET "
              f"{', '.join(f'{k} {v:.2f}' for k, v in cut.items())} mm")
        cmax = max(cut.values())
        for corner in ("small", "large"):
            for gk in ("cons", "opt"):
                rr, a_s = a2(corner, G[gk], P.K_SHIM, P.SHIM_MAX_DESIGN, cmax)
                a2_out[lab]["rows"].append(dict(corner=corner, grease=gk, area_over_shim=round(a_s, 1), R_1D=round(rr, 3),
                                                verdict="PASS" if rr <= BUDGET else "FAIL (1-D)"))
                print(f"    tab {corner:5s} grease {gk:4s} Al 2.2 mm: area over shim {a_s:6.1f} mm2  R_1D {rr:.3f}  "
                      f"{'PASS' if rr <= BUDGET else 'FAIL (1-D)'}")
    out["a2"] = a2_out

    # ---- (b) compliant layer
    print("\n(b) compliant layer between tab and the shared tile (replaces the tab-side grease):")
    brs = b_rows(spreads)
    out["b"] = brs
    for b in brs:
        print(f"  {b['case']:15s} {b['spread_mm']:.3f} mm tab {b['corner']:5s}: pre-cut pad t0 {b['pad_t0_mm']:5.2f} mm, pad bulk alone >= "
              f"{b['pad_bulk_lower_bound']:.3f}; dispensed k 5 gap alone >= {b['filler_k5_gap_only_lower_bound']:.3f}; k needed "
              f"(rest free / opt / cons) {b['k_needed_everything_else_free']} / {b['k_needed_opt_rest']} / {b['k_needed_cons_rest']} W/mK")
    psi = [COMB_ACCEPT[0] / (TAB_LARGE * 1e-6) / 6894.757, COMB_ACCEPT[1] / (TAB_SMALL * 1e-6) / 6894.757]
    out["b_clamp_pressure_psi"] = [round(v, 1) for v in psi]
    print(f"  clamp pressure over the tab: {psi[0]:.0f}-{psi[1]:.0f} psi (GAP PAD 5000S35 data are by strain 10-30 %, not pressure)")

    # ---- (c) fixture
    c60 = json.loads((C60 / "seat-tolerance.json").read_text())
    worst_c = c60["corners"]["D 1.72 b 1.40 c 0.89"]
    out["c"] = dict(need_mm=c60["need_mm"], worst_corner=worst_c, typical=c60["corners"]["D 1.72 b 1.20 c 0.60"],
                    R_cs=[round(base["large"]["cons"], 3), round(base["small"]["cons"], 3)], margin=round(BUDGET - base["small"]["cons"], 3))
    print(f"\n(c) c60 fixture: needs +/- {c60['need_mm']} mm; worst lead corner {worst_c['corner_ex']} (closes {worst_c['closes']}); "
          f"typical {out['c']['typical']['corner_ex']}; stack = baseline {base['small']['cons']:.3f} C/W cons (margin {BUDGET - base['small']['cons']:.3f})")

    (HERE / "s32-calc.json").write_text(json.dumps(out, indent=1, default=float) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
