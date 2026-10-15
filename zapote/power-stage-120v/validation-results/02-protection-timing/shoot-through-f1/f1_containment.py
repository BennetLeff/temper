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
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "native-21/layout"))
import layers21  # noqa: E402
CU_T = dict(layers21.T_MM)   # copper thickness per layer, mm (stage 33: read from native-21/stackup.json)
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

BOARDS = {   # label: (file, sha prefix or None)
    "19b_record": ("native-21/verification/native21s19b-all-copper.json.gz", "b19a4553"),
    "19c": ("native-21/verification/native21s19c-all-copper.json.gz", None),
}
TERM_BUF = 1.0        # mm: terminal = pad land (hole filled) buffered outward, so the pad's own annulus is never the neck
TERM_NEAR = 2.5       # mm: a neck whose location is within this of a terminal pad is flagged terminal-limited
VIA_DRILL, VIA_PLATE = 0.30, 0.020   # mm; plating assumption for barrel I2t


def barrel_i2t(ta):
    ri = VIA_DRILL / 2
    area = math.pi * ((ri + VIA_PLATE) ** 2 - ri ** 2)
    return area, onderdonk_i2t(area, ta)


def copper_necks(label, path, sha_prefix):
    from shapely.geometry import Point, LineString, Polygon, box
    from shapely.ops import unary_union, nearest_points
    raw = json.load(gzip.open(PS / path))
    sha = raw["board_sha256"]
    if sha_prefix:
        assert sha.startswith(sha_prefix), sha
    prims = raw["primitives"]

    def fix(g):
        return g if g.is_valid else g.buffer(0)

    def geom(p):
        k = p["kind"]
        if k == "track":
            return LineString([p["start"], p["end"]]).buffer(p["width_mm"] / 2, cap_style="round")
        if k == "via":      # ring: disk minus drill
            return Point(p["centre"]).buffer(p["diameter_mm"] / 2).difference(Point(p["centre"]).buffer(p["drill_mm"] / 2))
        if k == "pad":      # copper annulus / land (drill holes removed)
            return fix(Polygon(p["shell"], p.get("holes") or []))
        return fix(Polygon(p["shell"], p.get("holes") or []))     # zone

    def comps(g):
        return list(g.geoms) if hasattr(g, "geoms") else ([g] if not g.is_empty else [])

    cache = {}
    out = []
    for net, ta, tb, seg in SEGMENTS:
        ps = [p for p in prims if p["net"] == net]
        if net not in cache:
            lay = {}
            for p in ps:
                lay.setdefault(p["layer"], []).append(geom(p))
            lay = {l: unary_union(g) for l, g in lay.items()}
            # inter-layer links: via rings and drilled pads, grouped by centre; copper on each layer
            links = {}
            for p in ps:
                if p["kind"] == "via" or (p["kind"] == "pad" and p.get("drill_mm")):
                    links.setdefault((round(p["centre"][0], 3), round(p["centre"][1], 3)), []).append((p["layer"], geom(p)))
            cache[net] = (lay, links, {})
        lay, links, ecache = cache[net]

        def term(ref):
            return [(p["layer"], fix(Polygon(p["shell"])).buffer(TERM_BUF)) for p in ps if p["kind"] == "pad" and p["ref"] == ref], \
                   [fix(Polygon(p["shell"])) for p in ps if p["kind"] == "pad" and p["ref"] == ref]
        (TA, padA), (TB, padB) = term(ta), term(tb)
        assert TA and TB, (net, ta, tb)

        def eroded(l, r):
            key = (l, round(r, 4))
            if key not in ecache:
                ecache[key] = comps(lay[l].buffer(-r)) if r > 0 else comps(lay[l])
            return ecache[key]

        def groups(r, only=None):
            ec = {l: eroded(l, r) for l in lay if (only is None or l == only)}
            nodes = [(l, i) for l in ec for i in range(len(ec[l]))]
            par = {n: n for n in nodes}
            def find(x):
                while par[x] != x:
                    par[x] = par[par[x]]; x = par[x]
                return x
            if only is None:
                for pts in links.values():
                    hit = []
                    for l, cu in pts:
                        if l in ec:
                            for i, c in enumerate(ec[l]):
                                if c.intersects(cu):
                                    hit.append((l, i))
                    for a in hit[1:]:
                        par[find(a)] = find(hit[0])
            def touched(T):
                s = set()
                for l, pg in T:
                    if l in ec:
                        for i, c in enumerate(ec[l]):
                            if c.intersects(pg):
                                s.add(find((l, i)))
                return s
            return ec, find, touched(TA), touched(TB)

        def connected(r, only=None):
            _, _, a, b = groups(r, only)
            return bool(a & b)

        def neck(only=None):
            if not connected(0.0, only):
                return None
            lo, hi = 0.0, 10.0
            for _ in range(13):
                mid = (lo + hi) / 2
                if connected(mid, only): lo = mid
                else: hi = mid
            return lo

        r_c = neck()
        w_all = 2 * r_c
        per_layer = {l: neck(l) for l in lay}
        # --- neck location: just past disconnection, where do the A-side and B-side groups come closest?
        ec, find, sa, sb = groups(r_c + 0.01)
        gA = {}; gB = {}
        for l in ec:
            for i, c in enumerate(ec[l]):
                f = find((l, i))
                if f in sa: gA.setdefault(l, []).append(c)
                if f in sb: gB.setdefault(l, []).append(c)
        best = None
        for la, ca in gA.items():
            for lb, cb in gB.items():
                d = unary_union(ca).distance(unary_union(cb))
                same = (la == lb)
                key = (d if same else d + 1e-9, 0 if same else 1)
                if best is None or key < best[0]:
                    pa, pb = nearest_points(unary_union(ca), unary_union(cb))
                    best = (key, la, lb, d, ((pa.x + pb.x) / 2, (pa.y + pb.y) / 2))
        if best is None:      # one side vanished entirely (terminal land smaller than r): terminal-limited
            loc, nl, hop, gapd = None, "terminal", False, None
        else:
            _, la, lb, gapd, loc = best
            nl = la if la == lb else f"{la}/{lb}"
            hop = la != lb
        layA = {l for l, _ in TA}; layB = {l for l, _ in TB}
        needs_hop = all(r is None for r in per_layer.values())   # no single layer joins the terminals -> current crosses a via/barrel field
        dterm = min([Point(loc).distance(p) for p in padA + padB]) if loc else 0.0
        if loc is None:
            cls = "terminal-limited (one side vanishes at the neck radius: only the terminal land is narrower; no conductor neck below %.1f mm)" % w_all
        elif dterm < TERM_NEAR:
            cls = "terminal-limited (neck within %.1f mm of a terminal pad)" % TERM_NEAR
        elif hop:
            cls = "via/barrel-limited at the neck (layer hop)"
        else:
            cls = "real conductor neck"
        # via field: if a hop is unavoidable, count vias within 6 mm of the single-layer (SMD) terminal
        n_via = 0; via_xy = []
        if needs_hop:
            smd = padA if len(layA) < len(layB) else padB
            ctr = unary_union(smd).buffer(6.0)
            vias = {(round(p["centre"][0], 3), round(p["centre"][1], 3)) for p in ps if p["kind"] == "via" and ctr.contains(Point(p["centre"]))}
            n_via = len(vias); via_xy = sorted(vias)
        a_b, i2t_b105 = barrel_i2t(TA_HOT)
        via_single = i2t_b105
        via_equal = (n_via ** 2) * i2t_b105 if n_via else None
        a_cons = w_all * min(CU_T.values())
        a_par = max(a_cons, sum(2 * r * CU_T[l] for l, r in per_layer.items() if r))
        cons = onderdonk_i2t(a_cons, TA_HOT)
        par = onderdonk_i2t(a_par, TA_HOT)
        viahop_only = needs_hop
        eff_cons = cons if via_equal is None else min(cons, via_equal)
        eff_par = par if via_equal is None else min(par, via_equal)
        out.append({"segment": seg, "net": net, "from": ta, "to": tb,
                    "neck_width_mm": round(w_all, 3),
                    "neck_location_xy_mm": [round(loc[0], 2), round(loc[1], 2)] if loc else None,
                    "neck_layer": nl, "gap_at_neck_mm": round(gapd, 3) if gapd is not None else None,
                    "classification": cls,
                    "per_layer_independent_neck_mm": {l: (round(2 * r, 3) if r else None) for l, r in per_layer.items()},
                    "conductor_I2t_conservative": cons, "conductor_I2t_parallel": par,
                    "route_needs_via_hop": needs_hop,
                    "via_field_count_within_6mm_of_SMD_terminal": n_via, "via_field_xy": via_xy, "barrel_area_mm2": a_b, "barrel_I2t_single_Ta105": via_single,
                    "via_field_I2t_equal_sharing": via_equal,
                    "I2t_conservative": eff_cons, "I2t_parallel": eff_par,
                    "I2t_conservative_Ta25": onderdonk_i2t(a_cons, 25.0)})
    return sha, out

# ----------------------------------------------------------------------------- 5. verdict
def verdict(f1_clear, br1, copper, label):
    cu_min = min(c["I2t_conservative"] for c in copper)
    cu_min_par = min(c["I2t_parallel"] for c in copper)
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
    res["boards"] = {}
    for lab, (path, pre) in BOARDS.items():
        sha, cu = copper_necks(lab, path, pre)
        res["boards"][lab] = {"file": path, "board_sha256": sha, "segments": cu}
    copper = res["boards"]["19b_record"]["segments"]
    res["board_sha256"] = res["boards"]["19b_record"]["board_sha256"]
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
    for lab, bd in res["boards"].items():
        print("--- copper necks, board %s (sha %s...)" % (lab, bd["board_sha256"][:8]))
        for c in bd["segments"]:
            print("  %-30s %5.2f mm @%-16s %-12s I2t cons %6.0f par %6.0f  %s" % (c["segment"], c["neck_width_mm"], c["neck_location_xy_mm"], c["neck_layer"], c["I2t_conservative"], c["I2t_parallel"], c["classification"].split(" (")[0]))
        res["boards"][lab]["verdict_F1"] = verdict(f1c, BR1_I2T, bd["segments"], lab)
        print("  F1 vs this board's copper: %s" % ("PASS" if res["boards"][lab]["verdict_F1"]["PASS"] else "FAIL"))
    v = res["verdict"]
    print("F1 clearing I2t %.0f vs 0.5*BR1 %.0f (x%.2f) | min copper %.0f (x%.2f) [19b record]" %
          (v["F1_clearing_I2t"], v["limit_0p5_BR1"], v["margin_BR1_ratio"], v["min_copper_I2t_conservative"], v["margin_copper_ratio"]))
    print("controls ok:", res["controls_ok"], "(oversized FAIL, small-fuse BR1 condition PASS)")
    print("RESULT: F1-ONLY CONTAINMENT %s  (BR1 condition %s, copper condition %s)" %
          ("PASS" if v["PASS"] else "FAIL", "pass" if v["cond_BR1"] else "fail", "pass" if v["cond_copper"] else "fail"))
    return 0 if res["controls_ok"] else 2

if __name__ == "__main__":
    sys.exit(main())
