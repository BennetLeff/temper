#!/usr/bin/env python3
"""S16 shared model: datasheet inputs, rail ranges, allowed bands and the two monitor topologies.

Every number here carries its source (datasheet page from dl/, or repo file:line in the cb48 snapshot).
Imported by monitor_wc.py; it has no side effects.
"""
import itertools, math

# ----------------------------------------------------------------------------------------------------------------
# Temperature basis (README "Temperature").
#   B3 margins.json (s43) has no rows for U16-U21 / U29-U31 (searched); fallback = bay 61 C (b3-ratings basis c18_h10)
#   + TL431 self-heat (2.5 V x 6.5 mA x 206 C/W DBZ, SLVS543S p.5) = 64.3 C expected.  The parts sit 11-13 mm from
#   U26 (TJ 119.1 C) and U41/U42 (129.5 / 133.6 C), so the analysis is bounded at 85 C, the TL431AI / LM339B rated
#   maximum (SLVS543S p.5, SLCS006Z p.6).  Cold end -10 C (task-02 round-3 threshold basis, thresholds.py:241).
T_LO, T_HI, T_REF = -10.0, 85.0, 25.0
T_EXPECTED = 61.0 + 2.495 * 6.5e-3 * 206
DT = max(T_REF - T_LO, T_HI - T_REF)                       # 60 K TCR excursion from the 25 C tolerance point

# ----------------------------------------------------------------------------------------------------------------
# Resistors: tolerance + TCR x DT (worst case, independent per part)
THIN_01_25 = (0.001, 25e-6)   # Yageo RT0603BRD07 (B = 0.1 %, D = 25 ppm/K, RT V.16 p.2; 1 R..1 M at 0.1 %/25 ppm p.5),
                              # Viking ARG03BTC (B 0.1 %, C 25 ppm, ARG rev A3 p.2), Vishay TNPW..BE (E = 25 ppm/K, p.4)
THICK_1_100 = (0.01, 100e-6)  # Yageo RC1206FR (F = 1 %); 100 ppm/K assumed (RC datasheet not fetched; rref only moves
                              # the TL431 cathode current, <= 0.2 mV of Vref through |zKA|)


def e_of(kind, dt=None):
    tol, tcr = kind
    return tol + tcr * (DT if dt is None else dt)


# ----------------------------------------------------------------------------------------------------------------
# References
TL431 = {   # SLVS543S: Vref at 25 C, VKA = Vref, IKA = 10 mA; VI(dev) = max - min over -40..85 C (SOT23-3); |zKA| <= 0.5
    "TL431AIDBZR": {"v25": (2.470, 2.520), "videv": 0.034, "zka": 0.5, "cite": "SLVS543S Table 6.9 p.10"},
    "TL431BIDBZR": {"v25": (2.483, 2.507), "videv": 0.034, "zka": 0.5, "cite": "SLVS543S Table 6.12 p.13"},
}
TL431_IK_TEST = 10e-3
TLVH431BQ = {"vref_full": (1.221, 1.265),      # full range -40..125 C, VKA = VREF, IK = 10 mA (SLVS555N Table 5.7 p.8)
             "dvka_mV_per_V": (-2.7, 0.0),    # max -2.7 (typ -1.5), min unspecified -> 0
             "iref": (0.0, 1.0e-6),           # 0.5 uA max at 25 C + Iref(dev) 0.5 uA (BQ) -> <= 1.0 uA
             "zka": 0.4, "cite": "SLVS555N Table 5.7 p.8"}

# Comparators
LM339B = {"vos": 5.5e-3, "ib": 50e-9, "cite": "SLCS006Z Table 6.7 p.7 (-40..85 C): VIO +-5.5 mV, IB <= 50 nA out of pin"}
TPS3701 = {"uv_trip": (0.397, 0.403), "uv_rel": (0.400, 0.413), "ov_trip": (0.397, 0.403), "ov_rel": (0.387, 0.400),
           "iin": 25e-9, "cite": "SBVS240C Table 6.5 p.5 (TJ -40..125 C, VDD 1.8..36 V)"}

# ----------------------------------------------------------------------------------------------------------------
# s43 monitor circuit (elec/src/f6_bias.ato:112-227; values identical in all three monitors; designators from
# frozen/default.net, MPNs from frozen/default.csv)
S43 = {"ref": "TL431AIDBZR", "rref": 2.2e3, "r79": 10e3, "r80": 10e3,
       "taps": {"neg UV": (4.42e3, 10e3), "neg OV": (7.68e3, 10e3), "span UV": (120e3, 10e3), "span OV": (133e3, 10e3)}}
DESIG = {  # (LS, HS-A, HS-B)
    "ref": ("U17", "U19", "U21"), "cmp": ("U29", "U30", "U31"), "rref": ("R59", "R63", "R65"),
    "r79": ("R79", "R97", "R112"), "r80": ("R80", "R98", "R113"),
    "neg UV top": ("R81", "R99", "R114"), "neg UV bot": ("R82", "R100", "R115"),
    "neg OV top": ("R83", "R101", "R116"), "neg OV bot": ("R84", "R102", "R117"),
    "span UV top": ("R85", "R103", "R118"), "span UV bot": ("R86", "R104", "R119"),
    "span OV top": ("R87", "R105", "R120"), "span OV bot": ("R88", "R106", "R121"),
    "cap neg UV": ("C66", "C76", "C83"), "cap neg OV": ("C67", "C77", "C84"),
    "cap span UV": ("C68", "C78", "C85"), "cap span OV": ("C69", "C79", "C86"),
    "split ref": ("U16", "U18", "U20"), "split top": ("R77", "R95", "R110"), "split bot": ("R78", "R96", "R111"),
}


def vertices(params, f):
    """True worst case: f is monotonic in each parameter, so its extremes lie on the vertices of the box."""
    names = list(params)
    vals = [f(**dict(zip(names, combo))) for combo in itertools.product(*(params[n] for n in names))]
    return min(vals), max(vals)


def rss(params, f):
    """Statistical figure: every limit treated as 3 sigma; centre at the box midpoint; half-range effects in quadrature.
    Returns (centre, 3-sigma half-width, per-parameter half-range effects)."""
    mid = {n: 0.5 * (lo + hi) for n, (lo, hi) in params.items()}
    c = f(**mid)
    contrib = {}
    for n, (lo, hi) in params.items():
        a, b = dict(mid), dict(mid)
        a[n], b[n] = lo, hi
        contrib[n] = abs(f(**b) - f(**a)) / 2
    return c, math.sqrt(sum(v * v for v in contrib.values())), contrib


def box(nom, e):
    return (nom * (1 - e), nom * (1 + e))


# ----------------------------------------------------------------------------------------------------------------
# Rails
def ls_span():
    """TPS7A4700 ANY-OUT 17.0 V (f6_bias.ato:63), overall accuracy +-2.5 % over line, load, TJ -40..125 C and lot
    (SBVS204G Table 5.5 p.6, defined in 7.2.2.3), valid for VI >= VO + 1.0 V = 18 V (PS2 is 24 V)."""
    return {"wc": (17.0 * 0.975, 17.0 * 1.025), "centre": 17.0, "rss": 17.0 * 0.025,
            "cite": "SBVS204G Table 5.5 p.6 overall accuracy +-2.5 %"}


def hs_span(dt=None):
    """RECOM R24C2T25/R: VFB 2.4675..2.533 V 'VOUT+ to VOUT- in regulation', FB hysteresis 9..12.3 mV, accuracy
    +-1.5 % with 0.1 % FB resistors, all at TAMB 25 C (Rev 1-2024 p.2; no over-temperature figure).  Set point
    2.5 x (1 + 63.4 k / 11 k) (R92/R94 63.4 k, R93/R61 11 k, RT0603BRD07 0.1 %, DECISIONS.md:444).  Ripple = half the
    maximum FB hysteresis x the divider gain, added at both ends."""
    e = e_of(THIN_01_25, dt)
    gain_nom = 1 + 63.4 / 11.0
    rip = 0.0123 / 2 * gain_nom
    p = {"vfb": (2.4675, 2.533), "rt": box(63.4e3, e), "rb": box(11e3, e), "rip": (-rip, rip)}
    f = lambda vfb, rt, rb, rip: vfb * (1 + rt / rb) + rip
    lo, hi = vertices(p, f)
    c, h, _ = rss(p, f)
    vend = (2.5 * gain_nom * 0.985, 2.5 * gain_nom * 1.015)
    return {"wc": (lo, hi), "centre": c, "rss": h, "vendor_1p5pct": vend, "ripple_pk": rip,
            "cite": "R24C2T25/R Rev 1-2024 p.2 (VFB, hysteresis, +-1.5 %); 25 C only"}


IK_DC = {"LS": (1.5e-3, 35e-3), "HS": (1.5e-3, 5e-3)}
# DC shunt current: bleed (P-src)/4.99 k = 2.9..3.1 mA (f6_bias.ato:51-54) minus <= 0.5 mA of src loads; LS adds up to
# 30 mA of HOT protection load through the shared midpoint (out-D33 qualification-summary.json hot_load_current_mA).


def neg_rail(dom, dt=None):
    """SRC-N from the TLVH431BQ split: (VREF + dVKA + zKA*dIK)(1 + R77/R78) + Iref*R77, R77 6.2 k, R78 10 k 0.1 %."""
    e = e_of(THIN_01_25, dt)
    t = TLVH431BQ
    ik = IK_DC[dom]
    zk_lo, zk_hi = t["zka"] * min(0.0, ik[0] - 10e-3), t["zka"] * max(0.0, ik[1] - 10e-3)
    p = {"vref": t["vref_full"], "dvka": (t["dvka_mV_per_V"][0] * 1e-3 * 0.77, 0.0), "iref": t["iref"],
         "zk": (zk_lo, zk_hi), "rt": box(6.2e3, e), "rb": box(10e3, e)}
    f = lambda vref, dvka, iref, zk, rt, rb: (vref + dvka + zk) * (1 + rt / rb) + iref * rt
    lo, hi = vertices(p, f)
    c, h, _ = rss(p, f)
    return {"wc": (lo, hi), "centre": c, "rss": h}


# ----------------------------------------------------------------------------------------------------------------
# Allowed bands (README section 2).  Q = inside the committed F6 qualification evidence; H = hard ratings / physics.
D33_EDGE_SPAN = 15.5        # out-D33 qualification-summary.json edge_span_V ("below the monitor's normal enable window")
D33_HOT_SPAN = 18.0         # out-D33 qualification-summary.json hot_load_span_V (upper shunt-current case)
D33_SWITCH_NEG = 2.4        # out-D33 edge-current-2.4V/results.json: 26/26 switching cases pass at -2.4 V
F6_EDGE_LIMIT = 1.6         # DECISIONS.md:117 / :127 (rail more negative than -1.6 V through every partner edge)
D33_NOM_STATIC = 1.24 * (1 + 6120 / 10000)   # rail_qualification.py:27-28 RTOP 6120, Corner.ref 1.24 (nominal)
D33_NOM_EDGE = 1.844578     # qualification-summary.json rail-qualified/edge-screen.json least_negative (nominal parts)
D33_CORNER_STATIC = 1.2188 * (1 + 6120 * 0.999 / (10000 * 1.001))   # corner ref 1.2188, worst 0.1 % directions
D33_CORNER_EDGE = 1.678614  # qualification-summary.json rail-deep-bias/edge-corners.json least_negative
DROOP_NOM = D33_NOM_STATIC - D33_NOM_EDGE
DROOP_CORNER = D33_CORNER_STATIC - D33_CORNER_EDGE
OFFGATE_SCREEN, OFFGATE_AT_1P6, OFFGATE_SLOPE = 1.9, 1.589109, 1.25   # out-D33 README:53 (physical 1 ohm, -1.6 V),
                                                                      # DECISIONS.md:117 (+1.25 V per volt lost)
NEG_EDGE_PHYS = F6_EDGE_LIMIT - (OFFGATE_SCREEN - OFFGATE_AT_1P6) / OFFGATE_SLOPE
VDD_OP_MAX = 21.0           # 2EDR8259X Table 11 p.12 (8 V UVLO option, operating 8.5..21 V); abs max 22 V Table 9 p.10
VDD_OP_MIN = 8.5            # Table 11 p.12; UVLO on <= 8.5 V Table 15 p.13
VGS_STATIC_MAX = 20.0       # IPW65R018CFD7 Table 2 p.3
VGS_RDSON = 10.0            # IPW65R018CFD7 Table 4 p.5 (RDS(on) specified at VGS = 10 V)
MARGIN_TARGET = 0.005       # judgment: 0.5 % of the threshold (unmodelled drift, dynamic dips, model error)


def allowed(span_rail, neg_rail_wc, design_bands=None):
    """Allowed corners per threshold.  design_bands (optional) supplies the coupled hard limits (Vgs = span - neg)."""
    neg_ov_hi = design_bands["neg OV"][1] if design_bands else D33_SWITCH_NEG
    neg_uv_lo = design_bands["neg UV"][0] if design_bands else F6_EDGE_LIMIT
    return {
        "span UV": {"lo_Q": D33_EDGE_SPAN, "lo_H": max(VDD_OP_MIN, VGS_RDSON + neg_ov_hi), "hi": span_rail[0]},
        "span OV": {"lo": span_rail[1], "hi_Q": D33_HOT_SPAN, "hi_H": min(VDD_OP_MAX, VGS_STATIC_MAX + neg_uv_lo)},
        "neg UV": {"lo_Q": F6_EDGE_LIMIT + DROOP_NOM, "lo_H": NEG_EDGE_PHYS + DROOP_NOM,
                   "lo_corner_infeasible": F6_EDGE_LIMIT + DROOP_CORNER, "hi": neg_rail_wc[0]},
        "neg OV": {"lo": neg_rail_wc[1], "hi_Q": D33_SWITCH_NEG, "hi_H": D33_EDGE_SPAN - VGS_RDSON},
    }


# ----------------------------------------------------------------------------------------------------------------
# Topology 1: TL431 -> halfref divider -> LM339B (no hysteresis: trip = release)
def lm339_params(design, name, dt=None, ib=True, zka=True, vref_override=None, e_override=None):
    ref = TL431[design["ref"]]
    e = e_override if e_override is not None else e_of(THIN_01_25, dt)
    er = e_of(THICK_1_100, dt)
    rt, rb = design["taps"][name]
    r79, r80 = design["r79"], design["r80"]
    p = {}
    if vref_override:
        p["v25"] = vref_override
        p["dev"] = (0.0, 0.0)
    else:
        p["v25"] = ref["v25"]
        p["dev"] = (-ref["videv"], ref["videv"])
    if zka:   # cathode current at any span 15..19.5 V vs the 10 mA test point; |zKA| in [0, 0.5]
        vr = 2.495
        ik = [(vs - vr) / (design["rref"] * (1 + s * er)) - vr / (r79 + r80) for vs in (15.0, 19.5) for s in (-1, 1)]
        d = [i - TL431_IK_TEST for i in ik]
        p["zk"] = (ref["zka"] * min(0.0, min(d)), ref["zka"] * max(0.0, max(d)))
    else:
        p["zk"] = (0.0, 0.0)
    p["r79"], p["r80"], p["rt"], p["rb"] = box(r79, e), box(r80, e), box(rt, e), box(rb, e)
    p["vos"] = (-LM339B["vos"], LM339B["vos"])
    p["ibh"] = (0.0, 4 * LM339B["ib"] if ib else 0.0)
    p["ibt"] = (0.0, LM339B["ib"] if ib else 0.0)
    return p


def lm339_f(v25, dev, zk, r79, r80, rt, rb, vos, ibh, ibt):
    half = (v25 + dev + zk) * r80 / (r79 + r80) + ibh * (r79 * r80 / (r79 + r80))
    return (half + vos - ibt * (rt * rb / (rt + rb))) * (rt + rb) / rb


def lm339_nominal(design, name):
    rt, rb = design["taps"][name]
    return 2.495 * design["r80"] / (design["r79"] + design["r80"]) * (rt + rb) / rb


def lm339_eval(design, name, dt=None, **kw):
    p = lm339_params(design, name, dt, **kw)
    lo, hi = vertices(p, lm339_f)
    c, h, contrib = rss(p, lm339_f)
    return {"nominal": lm339_nominal(design, name), "trip_wc": (lo, hi), "release_wc": (lo, hi),
            "trip_rss": (c - h, c + h), "release_rss": (c - h, c + h), "rss_centre": c, "rss_3sigma": h,
            "rss_contrib": contrib}


# ----------------------------------------------------------------------------------------------------------------
# Topology 2: one TPS3701 per window, each threshold on its own two-resistor divider (candidate B)
def tps_params(rt, rb, vit, dt=None, e_override=None):
    e = e_override if e_override is not None else e_of(THIN_01_25, dt)
    return {"vit": vit, "rt": box(rt, e), "rb": box(rb, e), "iin": (-TPS3701["iin"], TPS3701["iin"])}


def tps_f(vit, rt, rb, iin):
    return (vit + iin * (rt * rb / (rt + rb))) * (rt + rb) / rb


def tps_eval(rt, rb, kind, dt=None, e_override=None):
    trip_v, rel_v = (TPS3701["uv_trip"], TPS3701["uv_rel"]) if kind == "UV" else (TPS3701["ov_trip"], TPS3701["ov_rel"])
    pt, pr = tps_params(rt, rb, trip_v, dt, e_override), tps_params(rt, rb, rel_v, dt, e_override)
    t, r = vertices(pt, tps_f), vertices(pr, tps_f)
    ct, ht, contrib = rss(pt, tps_f)
    cr, hr, _ = rss(pr, tps_f)
    return {"nominal": 0.400 * (rt + rb) / rb, "trip_wc": t, "release_wc": r, "trip_rss": (ct - ht, ct + ht),
            "release_rss": (cr - hr, cr + hr), "rss_centre": ct, "rss_3sigma": ht, "rss_contrib": contrib}


# ----------------------------------------------------------------------------------------------------------------
def judge(name, ev, al, basis):
    """Margins (V) of a threshold's corners against its allowed band.  UV: refuse-to-start side uses the release
    (rising) corner; catch side uses the falling trip corner.  OV: nuisance side and catch side both use the rising
    trip corner; 'recovery' (release falling corner vs rail max) is reported, not judged (fail-safe direction)."""
    tgt = MARGIN_TARGET * ev["nominal"]
    if "UV" in name:
        lo_lim = al["lo_" + basis]
        m_catch = ev["trip_wc"][0] - lo_lim
        m_rail = al["hi"] - ev["release_wc"][1]
        out = {"catch_side_V": m_catch, "rail_side_V": m_rail, "lim_catch": lo_lim, "lim_rail": al["hi"]}
    else:
        hi_lim = al["hi_" + basis]
        m_rail = ev["trip_wc"][0] - al["lo"]
        m_catch = hi_lim - ev["trip_wc"][1]
        out = {"catch_side_V": m_catch, "rail_side_V": m_rail, "lim_catch": hi_lim, "lim_rail": al["lo"],
               "recovery_V": ev["release_wc"][0] - al["lo"]}
    mn = min(out["catch_side_V"], out["rail_side_V"])
    out["target_V"] = tgt
    out["verdict"] = "FAIL" if mn < 0 else ("MARGINAL" if mn < tgt else "PASS")
    return out


E192 = [1.00, 1.01, 1.02, 1.04, 1.05, 1.06, 1.07, 1.09, 1.10, 1.11, 1.13, 1.14, 1.15, 1.17, 1.18, 1.20, 1.21, 1.23, 1.24,
        1.26, 1.27, 1.29, 1.30, 1.32, 1.33, 1.35, 1.37, 1.38, 1.40, 1.42, 1.43, 1.45, 1.47, 1.49, 1.50, 1.52, 1.54, 1.56,
        1.58, 1.60, 1.62, 1.64, 1.65, 1.67, 1.69, 1.72, 1.74, 1.76, 1.78, 1.80, 1.82, 1.84, 1.87, 1.89, 1.91, 1.93, 1.96,
        1.98, 2.00, 2.03, 2.05, 2.08, 2.10, 2.13, 2.15, 2.18, 2.21, 2.23, 2.26, 2.29, 2.32, 2.34, 2.37, 2.40, 2.43, 2.46,
        2.49, 2.52, 2.55, 2.58, 2.61, 2.64, 2.67, 2.71, 2.74, 2.77, 2.80, 2.84, 2.87, 2.91, 2.94, 2.98, 3.01, 3.05, 3.09,
        3.12, 3.16, 3.20, 3.24, 3.28, 3.32, 3.36, 3.40, 3.44, 3.48, 3.52, 3.57, 3.61, 3.65, 3.70, 3.74, 3.79, 3.83, 3.88,
        3.92, 3.97, 4.02, 4.07, 4.12, 4.17, 4.22, 4.27, 4.32, 4.37, 4.42, 4.48, 4.53, 4.59, 4.64, 4.70, 4.75, 4.81, 4.87,
        4.93, 4.99, 5.05, 5.11, 5.17, 5.23, 5.30, 5.36, 5.42, 5.49, 5.56, 5.62, 5.69, 5.76, 5.83, 5.90, 5.97, 6.04, 6.12,
        6.19, 6.26, 6.34, 6.42, 6.49, 6.57, 6.65, 6.73, 6.81, 6.90, 6.98, 7.06, 7.15, 7.23, 7.32, 7.41, 7.50, 7.59, 7.68,
        7.77, 7.87, 7.96, 8.06, 8.16, 8.25, 8.35, 8.45, 8.56, 8.66, 8.76, 8.87, 8.98, 9.09, 9.20, 9.31, 9.42, 9.53, 9.65,
        9.76, 9.88]


def e192_range(lo, hi):
    return [round(m * d, 6) for d in (1, 10, 100, 1e3, 1e4, 1e5) for m in E192 if lo <= m * d <= hi]


def yageo_rt_mpn(ohm):
    """ohm -> Yageo RT0603BRD07 global part number (RT V.16 p.2 resistance code rule)."""
    if ohm >= 1e6:
        s = f"{ohm / 1e6:g}"; u = "M"
    elif ohm >= 1e3:
        s = f"{ohm / 1e3:g}"; u = "K"
    else:
        s = f"{ohm:g}"; u = "R"
    code = s.replace(".", u) if "." in s else s + u
    return "RT0603BRD07" + code + "L"
