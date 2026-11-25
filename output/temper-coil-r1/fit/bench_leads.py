"""Bench lead lengths for coil 1 (coil on a non-conductive spacer beside the native-21 board, bench sink in place), and
what the bench leads add to L and R so the M2/M3/M5 readings and the tune loop account for them.

Layout (board frame: KiCad x right, y toward the front edge, z up from the board top; native-21 outline 290 x 140 plus
the SELV tongue x0-91 y140-190; J2 (132.0, 85.5), J5 (132.0, 70.5), DECISIONS 44 / c35 ENCLOSURE-REQUEST):
  - the bench sink (bench-sink-r1: Wakefield-Vette 511-3M, x -12..120.33 along the rear edge y0, 76.2 mm tall) stays
    on the rear edge; the coil goes in FRONT of the board, its lead exits (J2 r118.8, J5 r87.9, both near -95 deg on
    the coil) pointing at the studs;
  - placement rule (stated, senior-designer call): no part of the board, tongue included, sees more coil field than
    the board does installed in R43. Reference: the installed R1 coil's |B| at R43's under-coil check point
    (r60, Z80; study 06/09), from this study's axisymmetric model (coil_model, enclosure on). Bench field: the same
    model in free air, evaluated at every board outline point at the board-top height. Both per amp: the ratio is
    current-independent;
  - the spacer is a plywood/MDF ring support under the former's rim and four lugs (no metal; M3 nylon screws), open
    for ~70 deg over the lead exits. The leads drop straight from their R43 drop points (J2 through the rim hole, J5
    between the -113/-77 deg spokes), bend level at the run height, run straight in plan to above the lug barrels and
    bend down into them. Run height over the board: barrel top + the bend radius + 2 mm. The former underside sits
    2 x the bend radius / 0.9 + 2 mm above the run, less the winding's own 7.1 mm, so both J2 bends (off the winding, and
    level again) take the full bend radius.
Electrical (litz.py constants with the Remington 260 x 0.1007 mm strand; lay 1.03): R_dc of each lead; R_ac adds strand
proximity in the lead's own field and, where the two run together, in the neighbour's field; loop L of the paired run
L' = (mu0 / pi) ln(s / GMR) per metre (GMR = 0.7788 a, a = bundle radius; s = sleeve OD, sleeves touching), plus the
unpaired ends as pairs at their actual spacing (an upper-bound style estimate). The coil model's R_dc already counts
0.4 m of lead (coil_geometry.Winding lead_centre 250 + lead_outer 150 mm); the delta against that is reported.
Also: the tune loop's half-turn states. The J2 exit is fixed at -94.3 deg, so a half-turn trim leaves the outer end 180
deg away and the lead must run back along the rim: it then carries the current over ~171 deg (CW) or ~189 deg (CCW)
of a ring at r~118.6, and the "-0.5" state is not what tune.py lists. Estimated by adding that partial ring to the
axisymmetric model (a ring of weight -171/360 or +189/360): a coarse, stated approximation.
Run: .venv/bin/python -B fit/bench_leads.py  -> fit/results/bench_leads.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "model"))
import numpy as np  # noqa: E402

import coil_geometry as G  # noqa: E402
import coil_model as CM  # noqa: E402
import litz  # noqa: E402
import lug as LUG  # noqa: E402
import materials as M  # noqa: E402
import r1_parts as R  # noqa: E402

OUT = HERE / "results" / "bench_leads.json"
K_FREE = json.loads((HERE.parent / "model/results/compare_3d.json").read_text())["factors"]["k_free"]
N_STR, D_STR = 260, 0.1007e-3            # Remington 260/38LITZ: 5 x 52 x 38 AWG (0.1007 mm)
STUDS_B = {"J2": (132.0, 85.5), "J5": (132.0, 70.5)}
BOARD = [(0.0, 0.0), (290.0, 0.0), (290.0, 140.0), (91.0, 140.0), (91.0, 190.0), (0.0, 190.0)]
SINK = dict(x=(-12.0, 120.33), y=(-1.58, 0.0), z=(4.5, 4.5 + 76.2))    # 511-3M face near y0 (bench-sink-r1 sec. 1)
SPACER_OPEN_DEG = 70.0
FREQ = 40e3
BOXES = HERE.parents[2] / "zapote/power-stage-120v/validation-plan/enclosure-fit/native21-boxes.json"


def board_outline_pts(step=2.0):
    pts = []
    for (x0, y0), (x1, y1) in zip(BOARD, BOARD[1:] + BOARD[:1]):
        n = max(1, int(math.hypot(x1 - x0, y1 - y0) / step))
        pts += [(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n) for i in range(n)]
    return pts


def field_models():
    free = CM.build(G.R1)
    free.solve(FREQ)
    inst = CM.build(G.R1, enclosure=True)
    inst.solve(FREQ)
    return free, inst


def Bmag(m, r_mm, z_mm):
    br, bz = m.B_at(np.asarray(r_mm, float) * 1e-3, np.asarray(z_mm, float) * 1e-3)
    return np.sqrt(np.abs(br) ** 2 + np.abs(bz) ** 2) * 1e6       # uT per A (peak)


def main():
    lg = LUG.lug_geometry()
    rule = LUG.BEND_RULE_MM
    free, inst = field_models()
    b_ref = float(Bmag(inst, [60.0], [80.0])[0])
    boxes = json.loads(BOXES.read_text())["boxes"]           # native-21 component boxes (same stage-53 board)
    barrel_top = max(lg[n]["barrel_top"] for n in lg) - LUG.BOARD_TOP_Z
    z_run0 = barrel_top + rule + 2.0                           # lowest run that still bends down into the barrels

    def stack(z_run):
        # the R43 filleting helper lets two corners share at most 90 % of a segment between them
        z_fb = z_run + max(rule / 0.85, 2 * rule / 0.9 - (R.Z_WIND - 93.0)) + 2.0
        return z_fb, z_fb + (R.Z_WIND - 93.0)
    # coil frame: R43 world coil frame (centre (0, 261)); the board is placed so the stud midpoint lies on the lead-exit
    # ray u at distance D from the coil axis, board +y pointing back at the coil.
    th_u = math.radians((R.TH_J2 + R.TH_J5) / 2)
    u = (math.cos(th_u), math.sin(th_u))
    v = (-u[0], -u[1])                                         # board +y in the coil frame
    xb = (-v[1], v[0])                                         # board +x: KiCad's y runs down the page, so (x, y_kicad) is
    #                                                            left-handed with z up; this matches R43's pose (x -> +X, y -> -Y)
    mid = ((STUDS_B["J2"][0] + STUDS_B["J5"][0]) / 2, (STUDS_B["J2"][1] + STUDS_B["J5"][1]) / 2)

    def to_coil(D, s, p):
        dx, dy = p[0] - mid[0], p[1] - mid[1]
        return (R.CX + u[0] * D + xb[0] * (dx - s) + v[0] * dy, R.CY + u[1] * D + xb[1] * (dx - s) + v[1] * dy)

    def to_board(D, s, P):
        q = (P[0] - R.CX - u[0] * D, P[1] - R.CY - u[1] * D)
        return (mid[0] + q[0] * xb[0] + q[1] * xb[1] + s, mid[1] + q[0] * v[0] + q[1] * v[1])

    outline = board_outline_pts()

    def board_field(D, s, z_wind):
        rs = [math.hypot(x - R.CX, y - R.CY) for x, y in (to_coil(D, s, p) for p in outline)]
        return float(np.max(Bmag(free, rs, [R.Z_WIND - z_wind] * len(rs)))), min(rs)

    def under_runs(D, s, route, z_run):
        out = {}
        for n, rt in route.items():
            a, b = (to_board(D, s, q) for q in rt["run_coil_xy"])
            top, who = 0.0, None
            for i in range(201):
                x, y = a[0] + (b[0] - a[0]) * i / 200, a[1] + (b[1] - a[1]) * i / 200
                for bx in boxes:
                    if bx[0] - R.LEAD_OD / 2 - 2 <= x <= bx[3] + R.LEAD_OD / 2 + 2 and bx[1] - R.LEAD_OD / 2 - 2 <= y <= bx[4] + R.LEAD_OD / 2 + 2:
                        if bx[5] - 1.6 > top:
                            top, who = bx[5] - 1.6, [round(c, 1) for c in bx]
            out[n] = dict(run_board_xy=[[round(c, 1) for c in a], [round(c, 1) for c in b]], tallest_part_under_run_mm=round(top, 2),
                          box_board_local=who, lead_bottom_mm=round(z_run - R.LEAD_OD / 2, 2),
                          clearance_mm=round(z_run - R.LEAD_OD / 2 - top, 2))
        return out

    # for each lateral shift s of the board along x: the smallest D (stud midpoint to coil axis, 5 mm steps) meeting the
    # field rule, with the run raised until it clears every part under it by >= 2 mm (the coil rises with it)
    best = None
    for s in np.arange(-60.0, 120.1, 5.0):
        z_run = z_run0
        for _ in range(4):
            z_fb, z_wind = stack(z_run)
            lo, hi = 120.0, 600.0
            for _ in range(30):
                D = (lo + hi) / 2
                if board_field(D, s, z_wind)[0] <= b_ref:
                    hi = D
                else:
                    lo = D
            D = math.ceil(hi / 5.0) * 5.0
            route = routes(D, s, to_coil, lg, z_run, z_fb, rule)
            und = under_runs(D, s, route, z_run)
            need = max(r["tallest_part_under_run_mm"] for r in und.values()) + R.LEAD_OD / 2 + 2.0
            if need <= z_run + 1e-6:
                break
            z_run = need
        cand = dict(s=float(s), D=D, z_run=z_run, route=route, under=und, total_mm=sum(r["developed_mm"] for r in route.values()))
        if best is None or cand["total_mm"] < best["total_mm"] - 1e-6:
            best = cand
    D, s, z_run = best["D"], best["s"], best["z_run"]
    z_former_bottom, z_wind = stack(z_run)
    bmax, rmin = board_field(D, s, z_wind)
    for rt in best["route"].values():
        rt.pop("run_coil_xy")
    sink = [to_coil(D, s, (x, y)) for x in SINK["x"] for y in SINK["y"]]
    sink_r = min(math.hypot(x - R.CX, y - R.CY) for x, y in sink)
    b_sink = float(Bmag(free, [sink_r], [R.Z_WIND - z_wind + SINK["z"][0]])[0])
    elec = electrical(best["route"])
    trims = trim_states()
    res = dict(about=__doc__.strip(), bend_rule=LUG.BEND_RULE, lead_od_mm=R.LEAD_OD,
               field=dict(reference_installed_r60_z80_uT_per_A=b_ref, bench_board_max_uT_per_A=bmax,
                          board_nearest_to_coil_axis_mm=rmin, sink_nearest_to_coil_axis_mm=sink_r, sink_uT_per_A=b_sink,
                          free_air_coil_plane_uT_per_A={str(r): float(Bmag(free, [r], [R.Z_WIND])[0]) for r in (130, 150, 175, 200, 250, 300)}),
               layout=dict(stud_mid_to_coil_axis_mm=D, board_shift_along_x_mm=s, coil_centre_board_xy=[mid[0] + s, mid[1] + D],
                           winding_plane_above_board_top_mm=z_wind, former_underside_above_board_top_mm=z_former_bottom,
                           lead_run_height_mm=z_run, lowest_run_for_the_bends_mm=z_run0,
                           spacer=dict(kind="ring support under the rim and lugs", open_over_lead_exits_deg=SPACER_OPEN_DEG,
                                       height_above_board_top_mm=z_former_bottom, material="plywood or MDF, no metal; nylon M3 at the four former lugs")),
               leads=best["route"], under_runs=best["under"], electrical=elec, trim_states=trims)
    OUT.write_text(json.dumps(res, indent=1, default=float) + "\n")
    print(json.dumps({k: v for k, v in res.items() if k not in ("about",)}, indent=1, default=float))


def routes(D, s, to_coil, lg, z_run, z_fb, rule):
    """Each lead from the winding to its lug barrel top, in the coil frame (world Z: former underside at Z93 here)."""
    dz = 93.0 - z_fb                                            # board-frame z -> coil-frame Z offset
    out = {}
    enc = R.lead_points("R1")
    for n in ("J2", "J5"):
        pts = enc[n]
        # keep the in-coil part down to the former underside (Z93); the R43 drop continues straight down from there
        k = next(i for i, p in enumerate(pts) if p[2] <= 96.0 + 1e-6 or (i == len(pts) - 1))
        coil_part = list(pts[:k + 1]) if pts[k][2] > 93.0 else list(pts[:k])
        x0, y0 = pts[-1][0], pts[-1][1]
        r0 = math.hypot(x0 - R.CX, y0 - R.CY)
        level = (x0, y0, z_run + dz)
        sx, sy = lg[n]["drop_board"]
        dx, dy = to_coil(D, s, (sx, sy))
        above = (dx, dy, z_run + dz)
        top = (dx, dy, lg[n]["barrel_top"] - LUG.BOARD_TOP_Z + dz)
        poly = coil_part + [level, above, top]       # straight down from the last in-coil point (no collinear stops)
        poly = [p for i, p in enumerate(poly) if i == 0 or math.dist(p, poly[i - 1]) > 1e-6]
        fpts, rmin = R._fillet(poly, rule)
        if n == "J2":                                           # the run-out before the spiral end only shapes the bend
            i0 = min(range(len(fpts)), key=lambda i: math.dist(fpts[i], pts[R.J2_RUNOUT]))
            fpts = fpts[i0:]
        L = sum(math.dist(a, b) for a, b in zip(fpts, fpts[1:]))
        enc_len = R.lead(pts, rule, n)[1]["developed_mm"]
        out[n] = dict(developed_mm=L, tightest_bend_mm=rmin, enclosure_developed_mm=enc_len,
                      exit_r_mm=r0, plan_run_mm=math.dist(level[:2], above[:2]), drop_below_former_mm=93.0 - level[2],
                      run_coil_xy=[level[:2], above[:2]])
    return out


def electrical(route):
    """R and L the bench leads add, per lead, with the 40 kHz proximity terms (25 and 100 C)."""
    a = R.BUNDLE / 2 * 1e-3
    gmr = 0.7788 * a
    s = R.LEAD_OD * 1e-3
    lam_pair = M.MU0 / math.pi * math.log(s / gmr)             # H/m for the go-and-return pair
    j2, j5 = route["J2"], route["J5"]
    paired = min(j2["developed_mm"], j5["developed_mm"]) - 30.0   # both leave the groove together; ends excluded
    unpaired_j5 = j5["developed_mm"] - j2["developed_mm"]
    s_unp = 31.0e-3                                           # J5 exit r87.9 to J2 exit r118.8, and drop to drop
    lam_unp = M.MU0 / math.pi * math.log(s_unp / gmr)
    L_loop = lam_pair * paired * 1e-3 + lam_unp * max(0.0, unpaired_j5) * 1e-3 / 2
    tot_m = (j2["developed_mm"] + j5["developed_mm"]) / 1000.0
    model_m = (G.R1.lead_centre_mm + G.R1.lead_outer_mm) / 1000.0
    b2_own = litz.lead_b2(1.0, N_STR, D_STR)
    b2_pair = (M.MU0 / (2 * math.pi * s)) ** 2
    rows = {}
    for T in (25.0, 100.0):
        rdc_m = M.rho_cu(T) * litz.LAY / litz.cu_area(N_STR, D_STR)
        pr_own = litz.prox_per_m(b2_own, FREQ, T, N_STR, D_STR) * litz.LAY
        pr_pair = litz.prox_per_m(b2_pair, FREQ, T, N_STR, D_STR) * litz.LAY
        r_leads_dc = rdc_m * tot_m
        r_leads_ac = r_leads_dc * litz.skin_factor(FREQ, T, D_STR) + pr_own * tot_m + pr_pair * 2 * paired * 1e-3
        rows[f"{T:g}C"] = dict(R_dc_per_m_mohm=rdc_m * 1e3, R_leads_dc_mohm=r_leads_dc * 1e3, R_leads_ac40k_mohm=r_leads_ac * 1e3,
                               R_dc_delta_vs_model_0p4m_mohm=rdc_m * (tot_m - model_m) * 1e3,
                               R_ac_delta_vs_model_0p4m_mohm=(r_leads_ac - (rdc_m * litz.skin_factor(FREQ, T, D_STR) + pr_own) * model_m) * 1e3)
    return dict(total_lead_m=tot_m, model_lead_m=model_m, paired_run_mm=paired, unpaired_J5_mm=unpaired_j5,
                L_pair_uH_per_m=lam_pair * 1e6, L_loop_added_uH=L_loop * 1e6, by_temperature=rows,
                note="R_dc from rho_cu(T) x lay 1.03 / (260 x pi d^2 / 4); the datasheet maximum (0.00281 ohm/ft at 20 C = 9.22 mOhm/m) is ~6 % above this nominal")


class _W(G.Winding):
    extra = ()

    def rings(self):
        return super().rings() + list(self.extra)


def _L(w, extra=()):
    w2 = _W(w.sections, name=w.name)
    object.__setattr__(w2, "extra", tuple(extra))
    m = CM.build(w2)
    return m.solve(FREQ)["L"] * 1e6 * K_FREE


def trim_states():
    r_rim = 118.6
    t05 = G.trimmed(G.R1, 0.5)
    return dict(R1_uH=_L(G.R1), trim_0p5_no_lead_uH=_L(t05), trim_0p5_cw_rim_return_uH=_L(t05, [(r_rim, -171.0 / 360.0)]),
                trim_0p5_ccw_rim_run_uH=_L(t05, [(r_rim, 189.0 / 360.0)]), trim_1_uH=_L(G.trimmed(G.R1, 1.0)),
                note="2D x k_free; the partial lead ring is an axisymmetric weight, a coarse model of a 171/189 deg arc")


if __name__ == "__main__":
    main()
