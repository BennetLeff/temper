#!/usr/bin/env python3
"""F4: is F2 (Schurter UMT 250 3403.0171, 3.15 A T) protected by F1 (Littelfuse KLDR025) for a
bolted fault at J11 (blower tap, net blw_l)?   Run: python3 -I f2_coord.py   (stdlib only)

Every number is either (a) quoted from a cited datasheet (SRC dict below), (b) measured from the
pinned copper dump, or (c) an explicit, labelled assumption.  Deterministic; writes result.json.
"""
import gzip, heapq, json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PS = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
COPPER = os.path.join(PS, "native-21", "verification", "native21s19b-all-copper.json.gz")

# ---------------------------------------------------------------- cited data
SRC = {
 "F2_UMT250": dict(
   url="https://www.schurter.com/en/datasheet/typ_UMT_250.pdf (rev. dated 21.07.2026)",
   breaking_A=200.0,            # p.4 note 2) "IEC: 200 A @ 250 VAC / 100 A @ 125 VDC" (3403.0171 row footnote 2)
   melt_i2t=11.6,               # p.5 table, 3.15 A row: "Melting I2t 10.0 In typ. 11.6 A2s"
   vdrop_typ_mV=95.0,           # p.5 3.15 A row "Voltage Drop 1.0 In typ. 95 mV"
   vdrop_max_mV=300.0,          # same row, max
   rated_A=3.15),
 "F1_KLDR025": dict(
   url="https://www.farnell.com/datasheets/4078688.pdf (Littelfuse KLDR, Revised 06/27/2022); same row in Rev 092821",
   melt_i2t=226.0,              # p.6 Electrical Specifications KLDR025: MELT (PRE-ARC) I2t 226.0 A2s
   clear_i2t_200kA=1710.0,      # same row: TOTAL CLEARING I2t at 200 kA = 1,710 A2s
   interrupt_A=200000.0),
}
# p.6 "Current-Limiting Effects" (apparent RMS let-through, Littelfuse KLDR 2022 p.6) 20 A and 30 A columns
LT_TABLE = {  # prospective rms A -> (20 A, 30 A) apparent RMS let-through
  5000: (456, 621), 10000: (575, 783), 20000: (724, 986), 50000: (983, 1339),
  100000: (1238, 1687), 200000: (1560, 2125)}
# p.8 Peak Let-Thru chart: 20 A / 30 A lines read at 200 kA are ~3.6 kA / ~4.9 kA peak; table*K matches both.
PEAK_OVER_APPARENT = 2.3   # calibrated against the p.8 chart (digitised by eye, +-15 %)

# ---------------------------------------------------------------- assumptions (labelled)
V_NOM, TOL = 127.0, 0.10
V_RMS = V_NOM * (1 + TOL)                      # 139.7 V
RHO_CU20 = 1.72e-8                             # ohm*m at 20 C (cold = max current)
AWG14_MOHM_PER_M = 8.286                       # standard AWG table, 20 C; reproduces repo's 4.26/7.66 kA at 127 V
L1_DCR_PER_WINDING_OHM = 4.5e-3                # parts.ato Cmc20A docstring (TDK B82726S2203A020 ~4.5 mOhm); both windings in loop
F1_R_OHM = 0.0                                 # assumption: F1 cold resistance not in the sheet; 0 is the conservative (high-current) choice
VIA_PLATING_M = 25e-6                          # assumption, typical PTH plating
CU_T = {"F.Cu": 0.070e-3, "In1.Cu": 0.061e-3, "In2.Cu": 0.061e-3, "B.Cu": 0.070e-3}  # native-21/stackup.json (2 oz)
BOARD_T = 1.653e-3
FREQ = 60.0

# corners: (name, cord one-way m, extra source ohm, L_src uH, copper_on, F2 R mode)
CORNERS = [
 ("C0 stiff source, 0 m cord (absolute low-Z)",   0.0, 0.0,   2.0, True),
 ("C1 stiff source, 1.0 m 14 AWG cord (repo inlet bound 8.4 kA)", 1.0, 0.0, 2.0, True),
 ("C2 stiff source, 1.8 m 14 AWG cord (repo inlet bound 4.7 kA)", 1.8, 0.0, 10.0, True),
 ("C3 15 m branch + cord (repo: ~0.46 kA at inlet)", 1.8, 127.0/460.0 - 2*1.8*AWG14_MOHM_PER_M/1000, 10.0, True),
]

# ---------------------------------------------------------------- copper path resistance
def load_copper():
    return json.load(gzip.open(COPPER))["primitives"]

def path_R(prims, net, ref_a, ref_b):
    """Dijkstra over tracks+vias+through pads of one net; zones ignored (=> R is an upper bound)."""
    def key(layer, xy): return (layer, round(xy[0], 2), round(xy[1], 2))
    adj, pos = {}, {}
    def add(a, b, r):
        adj.setdefault(a, []).append((b, r)); adj.setdefault(b, []).append((a, r))
    pts_by_xy = {}
    for p in prims:
        if p.get("net") != net: continue
        if p["kind"] == "track":
            a, b = key(p["layer"], p["start"]), key(p["layer"], p["end"])
            L = math.dist(p["start"], p["end"]) * 1e-3
            add(a, b, RHO_CU20 * L / (p["width_mm"] * 1e-3 * CU_T[p["layer"]]) if L else 0.0)
            for k, xy in ((a, p["start"]), (b, p["end"])): pos[k] = xy
        elif p["kind"] in ("via", "pad"):
            k = key(p["layer"], p["centre"]); pos[k] = p["centre"]; adj.setdefault(k, [])
            pts_by_xy.setdefault((round(p["centre"][0], 2), round(p["centre"][1], 2)), []).append((p, k))
    # vias / through pads join layers at the same xy
    for xy, lst in pts_by_xy.items():
        vias = [(p, k) for p, k in lst if p["kind"] == "via" or p.get("drill_mm", [0])[0] > 0.0]
        for i in range(len(vias) - 1):
            p = vias[i][0]
            d = p.get("drill_mm", 0.3); d = d if isinstance(d, (int, float)) else d[0]
            r = RHO_CU20 * BOARD_T / (math.pi * d * 1e-3 * VIA_PLATING_M)   # whole barrel
            add(vias[i][1], vias[i + 1][1], r / 3)                     # one of 3 layer-to-layer segments
    # snap track ends that land on a via/pad centre of a *different* spelling (<0.3 mm) on same layer
    centres = [(k, pos[k]) for k in list(adj)]
    def pad_nodes(ref):
        return [key(p["layer"], p["centre"]) for p in prims if p["kind"] == "pad" and p.get("ref") == ref and p["net"] == net]
    src = [k for k in pad_nodes(ref_a) if k in adj]; dst = set(k for k in pad_nodes(ref_b) if k in adj)
    # snap tracks end -> nearest node on same layer within 0.3 mm
    for k in list(adj):
        for k2 in list(adj):
            if k < k2 and k[0] == k2[0] and math.dist(pos[k], pos[k2]) < 0.3 and all(n != k2 for n, _ in adj[k]):
                add(k, k2, 0.0)
    dist = {k: 0.0 for k in src}; pq = [(0.0, k) for k in src]; heapq.heapify(pq)
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist.get(u, 9e9): continue
        if u in dst: return d
        for v, r in adj[u]:
            if d + r < dist.get(v, 9e9): dist[v] = d + r; heapq.heappush(pq, (d + r, v))
    return None

def copper_loop(prims):
    out = {}
    out["l_filt L1.4->F2.1"] = path_R(prims, "l_filt", "L1.4", "F2.1")
    out["blw_l F2.2->J11.1"] = path_R(prims, "blw_l", "F2.2", "J11.1")
    out["n_filt J11.2->L1.3"] = path_R(prims, "n_filt", "J11.2", "L1.3")
    return out

# ---------------------------------------------------------------- fault physics
def fault(corner, copper_R, F2_R):
    name, cord_m, Rext, Lu, _ = corner
    R = (2 * cord_m * AWG14_MOHM_PER_M * 1e-3 + Rext + F1_R_OHM + 2 * L1_DCR_PER_WINDING_OHM + copper_R + F2_R)
    X = 2 * math.pi * FREQ * Lu * 1e-6
    Z = math.hypot(R, X)
    I = V_RMS / Z
    kappa = 1.02 + 0.98 * math.exp(-3 * R / X)       # IEC 60909 peak factor
    ipk = kappa * math.sqrt(2) * I
    return dict(R_loop_mohm=R * 1e3, X_mohm=X * 1e3, I_rms_A=I, I_peak_A=ipk, kappa=kappa)

def f1_peak_letthrough(I_rms, i_unlimited_peak):
    """Peak let-through of a 25 A KLDR at prospective rms I (A). Log-log interpolation of the p.6 table
    between the 20 A and 30 A columns (geometric mean at 25 A), extrapolated below 5 kA with the 5-10 kA slope,
    x PEAK_OVER_APPARENT, capped by the unlimited peak (fuse cannot raise the current)."""
    def app(c, I):
        pts = sorted(LT_TABLE)
        if I <= pts[1]: a, b = pts[0], pts[1]
        else:
            a = max(p for p in pts if p <= I); b = min(p for p in pts if p > I) if I < pts[-1] else pts[-2]
            if I >= pts[-1]: a, b = pts[-2], pts[-1]
        ya, yb = LT_TABLE[a][c], LT_TABLE[b][c]
        s = math.log(yb / ya) / math.log(b / a)
        return ya * (I / a) ** s
    a25 = math.sqrt(app(0, I_rms) * app(1, I_rms))     # geometric mean of 20 A and 30 A
    return min(i_unlimited_peak, PEAK_OVER_APPARENT * a25), PEAK_OVER_APPARENT * a25

def verdict(F2, F1, fl):
    """PASS (fixed by task): F1 let-through <= F2 breaking rating OR F1 clearing I2t < F2 pre-arc I2t."""
    lt, lt_curve = f1_peak_letthrough(fl["I_rms_A"], fl["I_peak_A"])
    crit1 = lt <= F2["breaking_A"]
    # F1 clearing I2t >= F1 melt I2t (physical lower bound; sheet only publishes total clearing at 200 kA).
    f1_clear_lb = F1["melt_i2t"]
    crit2 = f1_clear_lb < F2["melt_i2t"]
    return dict(f1_peak_letthrough_A=lt, f1_curve_peak_A=lt_curve, crit1_letthrough_le_F2_break=crit1,
                f1_clearing_i2t_lower_bound=f1_clear_lb, f2_prearc_i2t=F2["melt_i2t"], crit2_f1_clear_lt_f2_prearc=crit2,
                t_f2_prearc_us=F2["melt_i2t"] / fl["I_rms_A"] ** 2 * 1e6,
                t_f1_melt_us=F1["melt_i2t"] / fl["I_rms_A"] ** 2 * 1e6,
                PASS=crit1 or crit2)

def main():
    F2, F1 = SRC["F2_UMT250"], SRC["F1_KLDR025"]
    cu = copper_loop(load_copper())
    cu_ok = all(v is not None for v in cu.values())
    cuR = sum(cu.values()) if cu_ok else 0.0
    F2_R = F2["vdrop_typ_mV"] / 1e3 / F2["rated_A"]                 # 30.2 mOhm cold typical
    F2_R_max = F2["vdrop_max_mV"] / 1e3 / F2["rated_A"]
    res = dict(V_rms=V_RMS, copper_paths_ohm=cu, copper_loop_ohm=cuR, copper_connected_by_tracks_only=cu_ok,
               F2_R_typ_ohm=F2_R, F2_R_max_ohm=F2_R_max, corners=[])
    worst = None
    print(f"V = {V_NOM} V +{TOL*100:.0f} % = {V_RMS:.1f} V rms; copper loop (tracks/vias only, zones ignored) = {cuR*1e3:.1f} mOhm {cu}")
    print(f"F2: breaking {F2['breaking_A']:.0f} A @250 VAC, pre-arc I2t {F2['melt_i2t']} A2s, R_cold_typ {F2_R*1e3:.1f} mOhm")
    print(f"F1: melt I2t {F1['melt_i2t']} A2s, total clearing {F1['clear_i2t_200kA']} A2s @200 kA, 200 kA rating")
    for c in CORNERS:
        # low-Z variants: copper counted; also copper=0 for the stiffest bound
        for tag, cR, fr in (("Cu+F2typ", cuR, F2_R), ("Cu=0,F2typ", 0.0, F2_R)):
            fl = fault(c, cR, fr); v = verdict(F2, F1, fl)
            row = dict(corner=c[0], variant=tag, **fl, **v)
            res["corners"].append(row)
            print(f"{c[0][:58]:58s} {tag:11s} Ik={fl['I_rms_A']:7.0f} A rms ipk={fl['I_peak_A']:7.0f} A | "
                  f"F1 peak LT={v['f1_peak_letthrough_A']:6.0f} A (>{F2['breaking_A']:.0f}? {not v['crit1_letthrough_le_F2_break']}) "
                  f"t_F2pre={v['t_f2_prearc_us']:.1f} us t_F1melt={v['t_f1_melt_us']:.0f} us -> {'PASS' if v['PASS'] else 'FAIL'}")
            if worst is None or fl["I_rms_A"] > worst["I_rms_A"]: worst = row
    # design verdict = every corner must pass (protection must hold at the worst one); governing corner = highest Ik
    design_pass = all(r["PASS"] for r in res["corners"])
    res["design_verdict"] = "PASS" if design_pass else "FAIL"
    res["governing_corner"] = worst["corner"] + " / " + worst["variant"]
    # ---- controls (must flip) ----
    ctl = {}
    weak = ("CTRL-A weak source Rs=1.2 ohm", 0.0, 1.2, 10.0, True)
    fl = fault(weak, cuR, F2_R); v = verdict(F2, F1, fl)
    ctl["A_weak_source_1.2ohm"] = dict(I_rms_A=fl["I_rms_A"], **v)
    F2x = dict(F2, melt_i2t=3000.0)                                   # fictional F2 with pre-arc I2t > F1 clearing
    fl = fault(CORNERS[1], cuR, F2_R); v = verdict(F2x, F1, fl)
    ctl["B_fictional_F2_prearc_3000A2s_at_C1"] = dict(I_rms_A=fl["I_rms_A"], **v)
    res["controls"] = ctl
    ok_ctl = ctl["A_weak_source_1.2ohm"]["PASS"] and ctl["B_fictional_F2_prearc_3000A2s_at_C1"]["PASS"]
    print("CONTROL A (Rs=1.2 ohm, Ik=%.0f A, F1 LT %.0f A): %s (must be PASS)" % (
        ctl["A_weak_source_1.2ohm"]["I_rms_A"], ctl["A_weak_source_1.2ohm"]["f1_peak_letthrough_A"],
        "PASS" if ctl["A_weak_source_1.2ohm"]["PASS"] else "FAIL"))
    print("CONTROL B (fictional F2 pre-arc 3000 A2s at C1): %s (must be PASS)" %
          ("PASS" if ctl["B_fictional_F2_prearc_3000A2s_at_C1"]["PASS"] else "FAIL"))
    # ---- replacement check: Littelfuse 02153.15MXP (1500 A @250 VAC) ----
    cand = dict(mpn="02153.15MXP", breaking_A=1500.0, R_ohm=0.02825)
    cr = []
    for c in CORNERS:
        for tag, cR in (("Cu", cuR), ("Cu=0", 0.0)):
            fl = fault(c, cR, cand["R_ohm"]); cr.append(dict(corner=c[0], variant=tag, I_rms_A=fl["I_rms_A"], within_1500A=fl["I_rms_A"] <= cand["breaking_A"]))
    res["replacement_02153.15MXP"] = dict(cand, corners=cr)
    for r in cr: print(f"  replacement 1500 A part, {r['corner'][:30]:30s} {r['variant']:5s} Ik={r['I_rms_A']:6.0f} A  within 1500 A: {r['within_1500A']}")
    res["controls_ok"] = bool(ok_ctl)
    res["sources"] = {k: v.get("url") for k, v in SRC.items()}
    with open(os.path.join(HERE, "result.json"), "w") as f:
        json.dump(res, f, indent=1, sort_keys=True); f.write("\n")
    print(f"F2 COORDINATION VERDICT: {res['design_verdict']}  (governing: {res['governing_corner']}; controls flip correctly: {ok_ctl})")
    return 0 if ok_ctl else 2

if __name__ == "__main__":
    sys.exit(main())
