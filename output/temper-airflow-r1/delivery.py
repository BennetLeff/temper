#!/usr/bin/env python3
"""Delivery path for the board-face air (temper-airflow-r1, step 2): a jet bleed from the existing push hood.

    python3 delivery.py          # seconds; reads board-h-sweep.json -> delivery.json

Network: the R43 two-branch blower model (evidence/airflow-r32/coil_thermal.py, imported read-only from the frozen
R43 folder: Delta BFB1012VH-F00, digitised datasheet curve, min-corner fan = 0.9 x speed, common inlet / louver / door
legs carrying the total flow) gains a THIRD branch from the push hood to the exhaust plenum:
    hood wall hole -> F3 feed duct (G11, 12 x 12 mm inside) -> jet manifold over native-21's FET / film-cap channel ->
    N round jets (Cd 0.65) onto the board top -> bay -> bay vent in the exhaust plenum's X-22 wall -> plenum.
Sink and coil branches are coil_thermal's, unchanged (S8 sink; K1 = study 11's skived/bonded-fin contingency, its
sink_dp_R copied below because importing sink150.py runs it).
Board-face h: Martin (1977) round-nozzle arrays, as coil_thermal.martin_h, with the jet cell = jet pitch along the
channel x the 16.5 mm channel width. The jets run at Re 300-900, below Martin's validated Re >= 2000 (as the R32 coil
jets do), so the DESIGN value is Martin x 0.6 (coil_thermal's own lower case) and Martin x 1.0 is reported as the
estimate. No radiation and no natural convection are added on top (the duct shades the board), so h_top = max(10, h).
Bay air with through-flow: R33 study 14's lumped bay (UA 1.308 W/K; 20.2 W expected, 27.9 W at c28) plus the jet air
leaving through the vent: T_bay = (Q + UA T_k + m cp T_jet) / (UA + m cp), T_jet = 50 C (D-18 hood air basis).
Blower power: study 10's fan-law estimate P = P_12V x drive^3 (typical 17.04 W, Delta max 32.4 W). Noise: coil_thermal's
58.0 + 50 log10(drive) dB(A) (datasheet free-air basis, an estimate; the bench measures it).
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
R43 = REPO / "output/temper-manufacturing-r43"
AIR = R43 / "evidence/airflow-r32"
sys.path.insert(0, str(AIR))
import system_curve_r32 as sc  # noqa: E402
import coil_thermal as ct  # noqa: E402

RHO, CP, CFM, NU, K_AIR, PR = ct.RHO, ct.CP, ct.CFM, ct.NU_AIR, ct.K_AIR, ct.PR
FLOOR = 5.5 / 12

# ------------------------------------------------------------------ the board branch (the change set's geometry)
JET = {"D_mm": 3.0, "N": 8, "pitch_x_mm": 11.0, "row_y_model_mm": 14.0, "x_model_mm": [5.5 + 11.0 * k for k in range(8)],
       "H_mm": 6.0, "channel_w_mm": 16.5, "Cd": 0.65}
FEED = {"w_mm": 12.0, "h_mm": 12.0, "L_m": 0.11, "K": 1.5 + 2 * 0.9 + 1.0}   # entry + two 90 deg bends + manifold turn
MANIFOLD = {"w_mm": 10.5, "h_mm": 7.0}                                          # inside the jet box, over the jets
VENT = {"w_mm": 30.0, "h_mm": 25.0, "K": 1.5}                                   # bay -> exhaust plenum, X-22 wall
JET_AIR_C = 50.0


def dp_board(q, jet=JET):
    if q <= 0:
        return 0.0
    a_f = FEED["w_mm"] * FEED["h_mm"] * 1e-6
    v = q / a_f
    dh = 4 * a_f / (2 * (FEED["w_mm"] + FEED["h_mm"]) * 1e-3)
    re = v * dh / NU
    fd = 64 / re if re < 2300 else 0.316 / re ** 0.25
    a_j = jet["N"] * math.pi / 4 * (jet["D_mm"] * 1e-3) ** 2
    return ((FEED["K"] + fd * FEED["L_m"] / dh) * RHO * v ** 2 / 2 + RHO / 2 * (q / (a_j * jet["Cd"])) ** 2
            + VENT["K"] * RHO / 2 * (q / (VENT["w_mm"] * VENT["h_mm"] * 1e-6)) ** 2)


def q_board(dp, jet=JET):
    lo, hi = 0.0, 0.02
    for _ in range(60):
        m = (lo + hi) / 2
        lo, hi = (m, hi) if dp_board(m, jet) < dp else (lo, m)
    return (lo + hi) / 2


def h_board(q, jet=JET):
    """Martin (1977) round-nozzle array, area-averaged over the jet cells (pitch x channel width)."""
    if q <= 0:
        return {"h_est": 0.0, "h_design": 0.0, "v_jet": 0.0, "Re": 0, "f": None}
    d = jet["D_mm"] * 1e-3
    a_j = jet["N"] * math.pi / 4 * d ** 2
    v = q / a_j
    f = math.pi / 4 * jet["D_mm"] ** 2 / (jet["pitch_x_mm"] * jet["channel_w_mm"])
    hd = jet["H_mm"] / jet["D_mm"]
    re = v * d / NU
    K = (1 + (hd / (0.6 / math.sqrt(f))) ** 6) ** -0.05
    G = 2 * math.sqrt(f) * (1 - 2.2 * math.sqrt(f)) / (1 + 0.2 * (hd - 6) * math.sqrt(f))
    h = K * G * re ** (2 / 3) * PR ** 0.42 * K_AIR / d
    return {"h_est": round(h, 1), "h_design": round(0.6 * h, 1), "v_jet": round(v, 2), "Re": round(re), "f": round(f, 4)}


# ------------------------------------------------------------------ sinks: S8 (R43) and K1 (study 11)
def sink_k1(q_cfm):
    """study 11 sink150.py sink_dp_R for "K1: skived/bonded 1.0/2.5" (8, 40, 67.5, 117, 1.0, 2.5, 0.030), verbatim."""
    base, dep, H, L, t, s, spread = 8, 40, 67.5, 117, 1.0, 2.5, 0.030
    q = q_cfm * CFM
    m = sc.sink_model(L, dep, H, q_cfm, t=t, s=s)
    extra = (base - 4) * 1e-3 / (200 * L * 1e-3 * H * 1e-3)
    dp = (sc.dyn(q, 48 * H, 0.3) + m["dp_Pa"] + sc.dyn(q, (m["fins"] - 1) * s * dep * 1.1, 1.2)
          + sc.dyn(q, (m["fins"] - 1) * s * 81, 1.0))
    return dp, m["R_C_per_W"] - 0.03 + spread + extra


SINKS = {"S8": ct.dp_sink, "K1": sink_k1}


def branch_q(fn_dp, dp, hi=60.0):
    lo = 0.0
    for _ in range(50):
        m = (lo + hi) / 2
        lo, hi = (m, hi) if fn_dp(m) < dp else (lo, m)
    return (lo + hi) / 2


def op3(drive, sink="S8", board=True, jet=JET):
    """Operating point with three parallel branches between the hood and the exhaust plenum. Flows in CFM."""
    speed = drive * 0.9
    dps = lambda qc: SINKS[sink](qc)[0]
    lo, hi = 0.0, 400.0
    for _ in range(60):
        dpb = (lo + hi) / 2
        qs = branch_q(dps, dpb)
        qc = branch_q(lambda x: ct.dp_coil(x * CFM), dpb, 20.0)
        qb = q_board(dpb, jet) / CFM if board else 0.0
        qt = qs + qc + qb
        lo, hi = (dpb, hi) if sc.fan_p(ct.CURVE, qt, speed) > ct.dp_common(qt) + dpb else (lo, dpb)
    dpb = (lo + hi) / 2
    qs = branch_q(dps, dpb)
    qc = branch_q(lambda x: ct.dp_coil(x * CFM), dpb, 20.0)
    qb = q_board(dpb, jet) / CFM if board else 0.0
    hb = h_board(qb * CFM, jet)
    return {"drive": round(drive, 3), "branch_dp_Pa": round(dpb, 1), "total_cfm": round(qs + qc + qb, 3),
            "sink_cfm": round(qs, 3), "coil_cfm": round(qc, 3), "board_cfm": round(qb, 3),
            "R_SA": round(SINKS[sink](qs)[1], 4), "board_h_design": max(10.0, hb["h_design"]),
            "board_h_est": max(10.0, hb["h_est"]), "jet": hb,
            "noise_dBA_est": round(58.0 + 50 * math.log10(drive), 1),
            "blower_W_typ": round(17.04 * drive ** 3, 1), "blower_W_max": round(32.4 * drive ** 3, 1)}


def bay_air(q_into_bay_w, board_cfm, t_k=40.0, ua=1.308, t_jet=JET_AIR_C):
    mcp = RHO * CP * board_cfm * CFM
    return (q_into_bay_w + ua * t_k + mcp * t_jet) / (ua + mcp)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    sweep = json.loads((HERE / "board-h-sweep.json").read_text())
    req = {k: v["h_top_required"] for k, v in sweep["required_h_top"].items()}
    drives = [round(FLOOR, 3)] + [round(0.5 + 0.05 * i, 2) for i in range(11)]
    out = {"scope": __doc__.strip(), "jet": JET, "feed": FEED, "manifold": MANIFOLD, "vent": VENT,
           "inputs_sha256": {str(p.relative_to(REPO)): sha(p) for p in (AIR / "coil_thermal.py", AIR / "system_curve_r32.py",
                                                                         AIR / "fan-curves.json", HERE / "board-h-sweep.json")},
           "h_top_required": req}
    # 1. operating points with and without the board branch
    tab = {}
    for sink in SINKS:
        tab[sink] = {"with_board": [op3(d, sink) for d in drives], "without_board": [op3(d, sink, board=False) for d in drives]}
    out["operating_points"] = tab
    # 2. minimum drive for the board requirement (design basis h x 0.6, then estimate)
    need = {}
    for case, h in req.items():
        row = {"h_top_required": h}
        for basis in ("board_h_design", "board_h_est"):
            first = next((r for r in tab["S8"]["with_board"] if h is not None and r[basis] >= h), None)
            row[f"min_drive_{basis}"] = first["drive"] if first else None
            row[f"at_min_{basis}"] = first
        need[case] = row
    out["board_min_drive"] = need
    # the alternative rejected in DECISIONS D2: air blown ALONG the board face (no jets). Flat plate over the 90 mm channel,
    # laminar average 0.664 Re^0.5 Pr^1/3 and fully turbulent 0.037 Re^0.8 Pr^1/3 (both from the leading edge, an
    # estimate: component wakes add some), and the flow through a 16.5 x 15 mm channel at that velocity.
    L = 0.090
    par = {}
    for case, h in req.items():
        re_lam = (h * L / (0.664 * K_AIR * PR ** (1 / 3))) ** 2
        re_turb = (h * L / (0.037 * K_AIR * PR ** (1 / 3))) ** 1.25
        v_l, v_t = re_lam * NU / L, re_turb * NU / L
        par[case] = {"h": h, "v_laminar_m_s": round(v_l, 1), "v_turbulent_m_s": round(v_t, 1),
                     "cfm_at_turbulent_v": round(v_t * 16.5e-3 * 15e-3 / CFM, 1),
                     "channel_dp_Pa_at_turbulent_v": round(1.5 * RHO * v_t ** 2 / 2, 0)}
    out["parallel_flow_alternative"] = par
    # ceiling the board reaches at each drive (board_h_sweep ceiling_by_h, linear in h between swept points)
    cmap = sweep["ceiling_by_h"]
    hs_ = sorted({float(k.split("_h")[1]) for k in cmap})

    def ceil_at(bay, h):
        h = min(max(h, hs_[0]), hs_[-1])
        for ha, hb in zip(hs_, hs_[1:]):
            if ha <= h <= hb:
                ca, cb = (cmap[f"bay{bay}_h{int(x)}"]["all_gated_ceiling_A"] for x in (ha, hb))
                return round(ca + (cb - ca) * (h - ha) / (hb - ha), 1)
    out["ceiling_by_drive"] = {f"{r['drive']}": {"h_design": r["board_h_design"], "h_est": r["board_h_est"],
                                                 "bay55_A_design": ceil_at(55, r["board_h_design"]),
                                                 "bay61_A_design": ceil_at(61, r["board_h_design"]),
                                                 "bay61_A_est": ceil_at(61, r["board_h_est"])}
                               for r in tab["S8"]["with_board"]}
    # 3. what the board branch costs the sink and the coil
    i28 = 1.05 * 28.0
    p_ls = 6.78 * (i28 / 21.47) ** 2 + 0.33
    sink_w = {"basis_B_28A (fet_case)": 2 * (p_ls - 0.07) + 2 * p_ls + 2 * 1.05 * 0.9 * 11.1, "basis_A_28A (study 11)": 150.0}
    cost = {}
    for sink in SINKS:
        for name, w in sink_w.items():
            r_need = (ct.SINK_SET - 50.0) / w - ct.R_PED
            first_w = next((r["drive"] for r in tab[sink]["with_board"] if r["R_SA"] <= r_need), None)
            first_wo = next((r["drive"] for r in tab[sink]["without_board"] if r["R_SA"] <= r_need), None)
            cost[f"{sink}_{name}"] = {"sink_W": round(w, 1), "R_SA_needed": round(r_need, 4),
                                      "min_drive_without_board": first_wo, "min_drive_with_board": first_w}
        full_w, full_wo = tab[sink]["with_board"][-1], tab[sink]["without_board"][-1]
        cost[f"{sink}_full_speed"] = {"sink_cfm": [full_wo["sink_cfm"], full_w["sink_cfm"]],
                                      "R_SA": [full_wo["R_SA"], full_w["R_SA"]],
                                      "coil_cfm": [full_wo["coil_cfm"], full_w["coil_cfm"]], "board_cfm": full_w["board_cfm"]}
    k = 1 + 0.00393 * 75
    coils = {"expected R_ac 0.136 @100C": 0.136 / k, "acceptance 196 W @28A": 196 / 28 ** 2 / k}
    for name, r25 in coils.items():
        for label, key in (("without_board", False), ("with_board", True)):
            first = None
            for d in drives:
                o = op3(d, "K1", board=key)
                c = ct.coil_temp(28.0, r25, 110.0, 50.0, o["coil_cfm"])
                cl = ct.coil_temp(28.0, r25, 110.0, 50.0, o["coil_cfm"], 0.6)
                if c and cl and "T_winding_C" in c and "T_winding_C" in cl and c["T_winding_C"] <= 150 and c["T_ferrite_C_est"] <= 140:
                    first = {"drive": d, "Tw_C": c["T_winding_C"], "Tw_hx0.6_C": cl["T_winding_C"], "coil_cfm": o["coil_cfm"]}
                    break
            cost[f"coil_28A_{name}_{label}"] = first
        o_w, o_wo = op3(1.0, "K1"), op3(1.0, "K1", board=False)
        cost[f"coil_28A_{name}_full_speed_Tw_C"] = [ct.coil_temp(28.0, r25, 110.0, 50.0, o_wo["coil_cfm"])["T_winding_C"],
                                                     ct.coil_temp(28.0, r25, 110.0, 50.0, o_w["coil_cfm"])["T_winding_C"]]
    out["cost_to_sink_and_coil"] = cost
    # 4. bay air (and the C1 connector, which sits in it) with the jet through-flow
    bays = {}
    for name, q in (("expected 40 C kitchen (20.2 W)", 20.2), ("28 A worst, B3 heat only (27.9 W)", 27.9),
                    ("28 A + 22 W allowances (49.9 W)", 49.9)):
        bays[name] = {f"{r['drive']}": round(bay_air(q, r["board_cfm"]), 1) for r in tab["K1"]["with_board"]}
        bays[name]["still_air"] = round(bay_air(q, 0.0), 1)
    out["bay_air_C_by_drive"] = bays
    # 5. heat the vent carries into the plenum -> door exhaust rise at the governing drive
    gov = json.loads((AIR / "coil-thermal.json").read_text())["governing_points"]
    door = {}
    for d in (FLOOR, 0.8, 1.0):
        r = op3(d, "K1")
        t_b = bay_air(27.9, r["board_cfm"])
        w = RHO * CP * r["board_cfm"] * CFM * (t_b - JET_AIR_C)
        door[f"{round(d, 3)}"] = {"board_cfm": r["board_cfm"], "bay_air_C": round(t_b, 1), "heat_into_plenum_W": round(w, 1),
                                  "door_exhaust_rise_K": round(w / (RHO * CP * r["total_cfm"] * CFM), 2)}
    out["door_exhaust"] = {"with_board": door, "r43_governing_door_exhaust_C": {k: v["door_exhaust_C"] for k, v in gov.items()}}
    (HERE / "delivery.json").write_text(json.dumps(out, indent=1) + "\n")
    print("h_top required:", req)
    print("drive  dp   total  sink  coil  board  h_des  h_est  vjet  Re   R_SA(S8)  dB(A)  W_typ/max")
    for r in tab["S8"]["with_board"]:
        print(f"{r['drive']:.3f} {r['branch_dp_Pa']:5.1f} {r['total_cfm']:6.2f} {r['sink_cfm']:5.2f} {r['coil_cfm']:5.2f} "
              f"{r['board_cfm']:5.2f} {r['board_h_design']:6.1f} {r['board_h_est']:6.1f} {r['jet']['v_jet']:5.2f} {r['jet']['Re']:4d} "
              f"{r['R_SA']:.4f}  {r['noise_dBA_est']:5.1f}  {r['blower_W_typ']}/{r['blower_W_max']}")
    print(json.dumps({k: (v["min_drive_board_h_design"], v["min_drive_board_h_est"]) for k, v in need.items()}))
    print(json.dumps(out["ceiling_by_drive"]))
    print(json.dumps(par))
    print(json.dumps(cost, indent=1))
    print(json.dumps(bays, indent=1))
    print(json.dumps(door, indent=1))


if __name__ == "__main__":
    main()
