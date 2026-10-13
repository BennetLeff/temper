#!/usr/bin/env python3
"""F2 desk calculation: is a bridge shoot-through (bus short) contained by mains fuse F1 alone?

Run:  python3 -I f1_containment.py            (writes result.json next to this file)
Deterministic; stdlib + shapely (only for the copper-neck search).
See README.md for sources and assumptions.  Every datasheet number is a named constant below with
its source; every other number is computed here.
"""
import gzip, hashlib, json, math, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PS = HERE.parents[2]                      # .../power-stage-120v
COPPER = PS / "native-21/verification/native21s19b-all-copper.json.gz"
ATO_DIR = PS / "elec/src"

# ----------------------------------------------------------------------------- datasheet constants
# Littelfuse KLDR datasheet Rev 092821, p.5 "Electrical Specifications (cont.)", row KLDR025:
#   https://static.chipdip.ru/lib/254/DOC027254593.pdf (mirror of the Littelfuse PDF; Littelfuse.com/KLDR)
KLDR = {  # melt (pre-arc) I2t, total clearing I2t [A^2 s]
    "KLDR025": (226.0, 1710.0),   # F1 of record
    "KLDR030": (299.6, 1990.0),   # same table, p.5 (oversized control)
    "KLDR015": (200.5, 2248.0),   # same table: larger clearing I2t than 025 -> sensitivity row
    "KLDR005": (63.33, 84.04),    # same table (positive control: small fuse)
}
# Diodes Inc. GBJ25005-GBJ2510 datasheet DS21221 Rev.11-2 (May 2025), p.2 abs. max ratings:
#   https://www.diodes.com/assets/Datasheets/ds21221.pdf : I2t rating for fusing (t = 8.3 ms) 510 A^2s,
#   IFSM 350 A (8.3 ms), VF 1.05 V max at IF = 12.5 A.
BR1_I2T = 510.0
BR1_IFSM = 350.0
BR1_VF = 1.05
# Board constants read from the repo
C_BANK_PLAN = 18.8e-6        # RESOLUTION-PLAN F2 / aoe_04_bus_bound.py bank value
C_BANK_BOM = 2 * 9.0e-6 + 4 * 0.1e-6   # C5,C6 TDK B32676G1905K000 9 uF x2 + C(hf) a1,a2,b1,b2 B32652A0104K000 100 nF x4
C_TOL = 0.10                 # both TDK parts are 'K' = +/-10 %
L1_DCR = 4.5e-3              # elec/src/parts.ato Cmc20A docstring "~4.5 mOhm" (per winding)
L1_LEAK = 18e-6              # s19b EMI README: L1 leakage 18 uH (DM)
R5 = 1.0e-3                  # Bourns CSS2H-2512R-1L00F 1 mOhm shunt in the shoot-through return
V_LINE_NOM, V_TOL = 127.0, 0.10
V_BUS_OVP = 280.0            # U7 hardware OVP (DECISIONS item 62) / RESOLUTION-PLAN figure
V_BUS_CORNER = 286.0         # ALT-D3 / aoe_04 bus corner used by the repo
F = 60.0
# copper
CU_T = {"F.Cu": 0.070, "In1.Cu": 0.061, "In2.Cu": 0.061, "B.Cu": 0.070}   # native-21/stackup.json (mm)
CU_TM = 1083.0               # copper melting point, C
CMIL_MM2 = 5.067075e-4       # 1 circular mil in mm^2
TA_HOT = 105.0               # governing ambient before the fault (hot board); 25 C also reported
RHO_CU = 1.724e-8            # ohm m at 20 C
AREA_14AWG = 2.081e-6        # m^2

def onderdonk_i2t(area_mm2, ta):
    """Adiabatic fusing I2t [A^2 s] (Onderdonk): I = A*sqrt(log10(1+(Tm-Ta)/(234+Ta))/(33 t)), A in cmil."""
    a = area_mm2 / CMIL_MM2
    return a * a * math.log10(1 + (CU_TM - ta) / (234 + ta)) / 33.0

# ----------------------------------------------------------------------------- 1. schematic check
def schematic_check():
    txt = {p.name: p.read_text() for p in sorted(ATO_DIR.glob("*.ato"))}
    pat = re.compile(r"crowbar|catch|\bscr\b|thyristor|\bFC1\b|fc1\b|dc.?fuse|fuse", re.I)
    hits = []
    for n, t in txt.items():
        for i, l in enumerate(t.splitlines(), 1):
            if pat.search(l):
                hits.append(f"{n}:{i}: {l.strip()[:110]}")
    fuses = sorted({m.group(0) for t in txt.values() for m in re.finditer(r"new (MainsFuse25A|BranchFuseT3A15)", t)})
    # J7/J8/J9/J10 are straps: confirm no fuse part is instanced between RECT_* and BUS_P/HV_RET
    return {"fuse_instances": fuses, "catch_or_fc1_hits": [h for h in hits if re.search(r"crowbar|catch|\bscr\b|thyristor|\bFC1\b", h, re.I)],
            "no_catch_or_fc1_in_schematic": not any(re.search(r"crowbar|catch|\bscr\b|thyristor|\bFC1\b", h, re.I) for h in hits)}

# ----------------------------------------------------------------------------- 2. energy
def bus_energy():
    out = {}
    cmax = C_BANK_PLAN * (1 + C_TOL)
    vpk = V_LINE_NOM * (1 + V_TOL) * math.sqrt(2)
    for name, c in (("C_bom_nominal_18.4uF", C_BANK_BOM), ("C_plan_18.8uF", C_BANK_PLAN), ("C_plan_+10pct_20.68uF", cmax)):
        for vn, v in (("line_pk_197.6V", vpk), ("OVP_280V", V_BUS_OVP), ("corner_286V", V_BUS_CORNER)):
            out[f"{name}@{vn}"] = 0.5 * c * v * v
    return {"line_peak_V": vpk, "E_J": out, "E_worst_J": out[f"C_plan_+10pct_20.68uF@corner_286V"]}

# ----------------------------------------------------------------------------- 3. follow-on current
def simulate(r_src, l_src, r_board_extra=0.0, dt=0.2e-6, t_end=8.34e-3, i2t_melt=KLDR["KLDR025"][0]):
    """Mains -> source Z -> F1 -> L1 -> BR1 (2 diodes, 1 V0 each) -> straps -> shorted leg -> R5 -> back.
    Fault applied at line voltage crest (largest dI/dt).  i' = (|v| - 2*VF0 - R i)/L, rectified (i>=0).
    Reports the prospective (no-fuse) current and the moment the F1 melting I2t is reached."""
    vpk = V_LINE_NOM * (1 + V_TOL) * math.sqrt(2)
    r = r_src + 2 * L1_DCR + R5 + r_board_extra
    l = l_src + L1_LEAK
    vd = 2 * BR1_VF * 0.9      # diode threshold ~0.9*VF (spec VF is at 12.5 A; at kA the drop is larger, lower current -> this is the pessimistic (high-current) choice)
    i = 0.0; t = 0.0; i2t = 0.0; ipk = 0.0
    melt = None
    n = int(t_end / dt)
    for k in range(n):
        t = k * dt
        v = vpk * abs(math.cos(2 * math.pi * F * t))      # fault at the crest, rectified
        di = (v - vd - r * i) / l
        i = max(0.0, i + di * dt)
        i2t += i * i * dt
        ipk = max(ipk, i)
        if melt is None and i2t >= i2t_melt:
            melt = {"t_us": t * 1e6, "i_A": i}
    return {"R_loop_mOhm": r * 1e3, "L_loop_uH": l * 1e6, "I_pk_prospective_A": ipk,
            "free_run_I2t_8.3ms_A2s": i2t, "melt_at": melt,
            "ipk_formula_check_A": (vpk - vd) / r}

CASES = {
    # name: (R_source_ohm, L_source_H, note)
    "nominal_15m_14AWG_branch": (2 * 15.0 * RHO_CU / AREA_14AWG + 2 * 1.8 * RHO_CU / AREA_14AWG + 0.020, 3.0e-6,
                                 "15 m 14 AWG branch + 1.8 m cord + 20 mOhm service/panel; ~0.3 ohm -> ~0.46 kA at 140 V (DECISIONS 234)"),
    "cord_limited_1.8m_4.7kA": (V_LINE_NOM * 1.1 / 4700.0, 1.8e-6, "F1-RECOMMENDATION s2: 4.7 kA at 140 V, 1.8 m 14 AWG, stiff source"),
    "low_impedance_1.0m_8.4kA": (V_LINE_NOM * 1.1 / 8400.0, 1.0e-6, "F1-RECOMMENDATION s2: 8.4 kA at 140 V, 1.0 m 14 AWG, stiff source (LOW-Z CORNER)"),
    "zero_source_Z_bound": (0.0, 0.0, "ideal source: only board R/L (L1 DCR, leakage, R5, diodes)"),
}

# ----------------------------------------------------------------------------- 4. copper necks
SEGMENTS = [  # (net, terminal A ref, terminal B ref, label)
    ("ac_l_in", "J1.1", "F1.1", "J1 line -> F1 pad 1"),
    ("l_f", "F1.2", "L1.1", "F1 pad 2 -> L1 winding 1"),
    ("l_filt", "L1.4", "BR1.2", "L1 -> BR1 AC1"),
    ("n_filt", "L1.3", "BR1.3", "L1 -> BR1 AC2"),
    ("ac_n_in", "J1.2", "L1.2", "J1 neutral -> L1"),
    ("rect_p", "BR1.1", "J7.1", "BR1 + -> J7 (strap)"),
    ("rect_n", "BR1.4", "J9.1", "BR1 - -> J9 (strap)"),
    ("bus_p", "J8.1", "Q2.2", "J8 -> Q2 drain (leg A)"),
    ("bus_p", "J8.1", "Q5.2", "J8 -> Q5 drain (leg B)"),
    ("leg_ret", "Q3.3", "R5.1", "Q3 source -> shunt R5 (leg A)"),
    ("leg_ret", "Q6.3", "R5.1", "Q6 source -> shunt R5 (leg B)"),
    ("hv_ret", "R5.4", "J10.1", "shunt R5 -> J10"),
]

def copper_necks():
    from shapely.geometry import Point, LineString, Polygon
    from shapely.ops import unary_union
    raw = json.load(gzip.open(COPPER))
    sha = raw["board_sha256"]
    prims = raw["primitives"]
    def geom(p):
        k = p["kind"]
        if k == "track":
            return LineString([p["start"], p["end"]]).buffer(p["width_mm"] / 2, cap_style="round")
        if k == "via":
            return Point(p["centre"]).buffer(p["diameter_mm"] / 2)
        if k in ("zone", "pad"):
            g = Polygon(p["shell"], p.get("holes") or [])
            return g if g.is_valid else g.buffer(0)
    results = []
    cache = {}
    for net, ta, tb, label in SEGMENTS:
        ps = [p for p in prims if p["net"] == net]
        if net not in cache:
            layers = {}
            for p in ps:
                layers.setdefault(p["layer"], []).append(geom(p))
            cache[net] = ({l: unary_union(g) for l, g in layers.items()},
                          [(p["layer"], Point(p["centre"])) for p in ps if p["kind"] == "via"] +
                          [(p["layer"], Point(p["centre"])) for p in ps if p["kind"] == "pad" and p.get("drill_mm")])
        lay, links = cache[net]
        def term(ref):
            return [(p["layer"], geom(p)) for p in ps if p["kind"] == "pad" and p["ref"] == ref]
        TA, TB = term(ta), term(tb)
        assert TA and TB, (net, ta, tb)

        def comps(g):
            return list(g.geoms) if hasattr(g, "geoms") else ([g] if not g.is_empty else [])

        def connected(r, only_layer=None):
            ec = {}
            for l, g in lay.items():
                if only_layer and l != only_layer:
                    continue
                ec[l] = comps(g.buffer(-r)) if r > 0 else comps(g)
            nodes = [(l, i) for l in ec for i in range(len(ec[l]))]
            par = {n: n for n in nodes}
            def find(x):
                while par[x] != x:
                    par[x] = par[par[x]]; x = par[x]
                return x
            if not only_layer:
                for (l1, pt) in links:      # via / through-hole barrel joins same point on every layer
                    here = [(l, i) for l in ec for i, c in enumerate(ec[l]) if c.buffer(1e-6).contains(pt)]
                    for a in here[1:]:
                        par[find(a)] = find(here[0])
            def touched(T):
                s = set()
                for l, pg in T:
                    if l in ec:
                        for i, c in enumerate(ec[l]):
                            if c.intersects(pg):
                                s.add(find((l, i)))
                return s
            return bool(touched(TA) & touched(TB))

        def neck(only_layer=None):
            if not connected(0.0, only_layer):
                return None
            lo, hi = 0.0, 8.0
            for _ in range(12):
                mid = (lo + hi) / 2
                if connected(mid, only_layer): lo = mid
                else: hi = mid
            return 2 * lo           # neck width (mm), resolution ~ 4 um
        w_all = neck()
        per_layer = {l: neck(l) for l in lay}
        # conservative: best single route, thinnest copper (0.061 mm) ; parallel: independent layer routes, own thickness
        a_cons = w_all * min(CU_T.values())
        a_par = sum(w * CU_T[l] for l, w in per_layer.items() if w) or a_cons
        a_par = max(a_par, a_cons)
        results.append({"segment": label, "net": net, "from": ta, "to": tb,
                        "neck_width_best_route_mm": round(w_all, 3),
                        "neck_width_per_layer_mm": {l: (round(w, 3) if w else None) for l, w in per_layer.items()},
                        "area_conservative_mm2": a_cons, "area_parallel_layers_mm2": a_par,
                        "fuse_I2t_conservative_Ta105": onderdonk_i2t(a_cons, TA_HOT),
                        "fuse_I2t_conservative_Ta25": onderdonk_i2t(a_cons, 25.0),
                        "fuse_I2t_parallel_Ta105": onderdonk_i2t(a_par, TA_HOT)})
    return sha, results

# ----------------------------------------------------------------------------- 5. verdict
def verdict(f1_clear, br1, copper, label):
    cu_min = min(c["fuse_I2t_conservative_Ta105"] for c in copper)
    cu_min_par = min(c["fuse_I2t_parallel_Ta105"] for c in copper)
    c_br = f1_clear < 0.5 * br1
    c_cu = f1_clear < cu_min
    return {"label": label, "F1_clearing_I2t": f1_clear, "limit_0p5_BR1": 0.5 * br1,
            "margin_BR1_ratio": f1_clear / (0.5 * br1), "cond_BR1": c_br,
            "min_copper_I2t_conservative": cu_min, "min_copper_I2t_parallel": cu_min_par,
            "margin_copper_ratio": f1_clear / cu_min, "cond_copper": c_cu,
            "cond_copper_parallel_estimate": f1_clear < cu_min_par, "PASS": bool(c_br and c_cu)}

def main():
    res = {"schematic": schematic_check(), "energy": bus_energy()}
    sims = {k: dict(simulate(rs, ls), note=n) for k, (rs, ls, n) in CASES.items()}
    res["follow_on_current"] = sims
    sha, copper = copper_necks()
    assert sha.startswith("b19a4553"), sha
    res["board_sha256"] = sha
    res["copper_segments"] = copper
    f1m, f1c = KLDR["KLDR025"]
    res["F1"] = {"mpn": "KLDR025.TXP", "melt_I2t": f1m, "clearing_I2t": f1c, "BR1_I2t": BR1_I2T,
                 "BR1_half": 0.5 * BR1_I2T}
    # F1 melts in every case before the half cycle ends (check) -> clearing I2t taken as datasheet total clearing value
    res["F1"]["melts_before_8p3ms_all_cases"] = all(s["melt_at"] is not None for s in sims.values())
    main_v = verdict(f1c, BR1_I2T, copper, "F1 = KLDR025 (board of record)")
    res["verdict"] = main_v
    res["sensitivity"] = {
        "F1_melt_only_no_arc_energy": verdict(f1m, BR1_I2T, copper, "KLDR025 melting I2t only (ideal zero-arc fuse)"),
        "KLDR015_row_clearing_2248": verdict(KLDR["KLDR015"][1], BR1_I2T, copper, "table's highest 12-30 A clearing value"),
    }
    res["controls"] = {
        "oversized_KLDR030_must_FAIL": verdict(KLDR["KLDR030"][1], BR1_I2T, copper, "KLDR030"),
        "oversized_hypothetical_1e5_must_FAIL": verdict(1.0e5, BR1_I2T, copper, "hypothetical 100 kA2s fuse"),
        "small_KLDR005_BR1_condition_must_PASS": verdict(KLDR["KLDR005"][1], BR1_I2T, copper, "KLDR005 (5 A)"),
    }
    c = res["controls"]
    ctrl_ok = (not c["oversized_KLDR030_must_FAIL"]["PASS"] and not c["oversized_hypothetical_1e5_must_FAIL"]["PASS"]
               and c["small_KLDR005_BR1_condition_must_PASS"]["cond_BR1"])
    res["controls_ok"] = bool(ctrl_ok)
    (HERE / "result.json").write_text(json.dumps(res, indent=2, sort_keys=True, default=float) + "\n")

    print("schematic: fuses =", res["schematic"]["fuse_instances"], "| catch/FC1 hits =", len(res["schematic"]["catch_or_fc1_hits"]))
    e = res["energy"]
    print("bus energy: 0.5CV^2 worst = %.3f J (C=20.68uF, V=286V); at 197.6 V line crest, C=18.4uF = %.3f J"
          % (e["E_worst_J"], e["E_J"]["C_bom_nominal_18.4uF@line_pk_197.6V"]))
    for k, s in sims.items():
        m = s["melt_at"]
        print("  %-28s R=%6.1f mOhm  Ipk=%7.0f A  F1 melts at %6.1f us / %6.0f A" % (k, s["R_loop_mOhm"], s["I_pk_prospective_A"], m["t_us"], m["i_A"]))
    worst = min(copper, key=lambda x: x["fuse_I2t_conservative_Ta105"])
    print("narrowest copper: %s  neck %.2f mm  fusing I2t %.0f A2s (Ta=105C, thin-copper, best-route)" %
          (worst["segment"], worst["neck_width_best_route_mm"], worst["fuse_I2t_conservative_Ta105"]))
    v = res["verdict"]
    print("F1 clearing I2t %.0f vs 0.5*BR1 %.0f (x%.2f) | min copper %.0f (x%.2f)" %
          (v["F1_clearing_I2t"], v["limit_0p5_BR1"], v["margin_BR1_ratio"], v["min_copper_I2t_conservative"], v["margin_copper_ratio"]))
    print("controls ok:", res["controls_ok"], "(oversized FAIL, small-fuse BR1 condition PASS)")
    print("RESULT: F1-ONLY CONTAINMENT %s  (BR1 condition %s, copper condition %s)" %
          ("PASS" if v["PASS"] else "FAIL", "pass" if v["cond_BR1"] else "fail", "pass" if v["cond_copper"] else "fail"))
    return 0 if res["controls_ok"] else 2

if __name__ == "__main__":
    sys.exit(main())
