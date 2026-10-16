#!/usr/bin/env python3
"""OPEN-ITEMS S16: worst-case and RSS model of the native-21 s43 rail monitors, the BOM-only re-centre (option 1) and
candidate B (option 2, TPS3701 per window).

    python3 -I scripts/monitor_wc.py [--offline] [SNAP_PS_DIR]  -> results/monitor_wc.json, results/monitor_wc.md

Controls (asserted):
  C1  the P4 benchmark bands (g05-g07 tps3700_band.py assumptions: Vref 2.436..2.554, Vos 5.5 mV, 0.1 % + 25 ppm x 125 K,
      no bias current, no zKA) reproduce the simplify-2026-10-15 results/monitor_tps3701.json 'old_bands' to 1e-9;
  C2  the study's candidate B dividers under the study's assumptions reproduce its 'band_V' / 'release_band_V' to 1e-4.
Then the refined model (model.py: 60 K TCR excursion, LM339B input bias, TL431 |zKA|, rail models) is applied.
JLC look-ups are cached in dl/jlc-raw (untrusted; only named fields read).
"""
import sys as _s; _s.dont_write_bytecode = True
import csv, json, math, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import model as m  # noqa: E402
import jlc  # noqa: E402

args = [a for a in sys.argv[1:] if not a.startswith("--")]
PS = Path(args[0]) if args else Path("/Users/bennet/.claude/jobs/fbfc46b4/tmp/snap-cb48/zapote/power-stage-120v")
STUDY = Path("/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v/validation-results/"
             "11-candidates/simplify-2026-10-15/results/monitor_tps3701.json")
OUT = HERE.parent / "results"
NAMES = ("neg UV", "neg OV", "span UV", "span OV")
NEED = 1800          # 3 per board x 500 + 20 % (JLC attrition / spares)
r4 = lambda x: round(x, 4)


# ---------------------------------------------------------------------------------------------------------------- BOM
def bom():
    rows = list(csv.DictReader(open(PS / "validation-results/08-manufacturing-package/native-21/fab/bom-jlcpcb.csv")))
    snap = {r["mpn"]: r for r in csv.DictReader(open(PS / "validation-results/08-manufacturing-package/native-21/"
                                                          "sourcing/SNAPSHOT-2026-10-15.csv")) if r.get("mpn")}
    out = {}
    for r in rows:
        mpn = r["Manufacturer Part Number"]
        s = snap.get(mpn) or {}
        out[mpn] = {"designators": [d.strip() for d in r["Designator"].split(",")], "lcsc": r["LCSC Part #"],
                    "jlc_stock": int(float(s.get("jlc_stock") or 0)), "usd_500": float(s.get("jlc_unit_usd_500") or 0)}
    return out


BOM = bom()
BOM_01 = {  # 0.1 % / 25 ppm 0603 values on the s43 BOM (ohm -> MPN)
    1e3: "RT0603BRD071KL", 2.21e3: "RT0603BRD072K21L", 4.42e3: "RT0603BRD074K42L", 6.2e3: "RT0603BRD076K2L",
    7.68e3: "RT0603BRD077K68L", 10e3: "RT0603BRD0710KL", 11e3: "RT0603BRD0711KL", 11.7e3: "TNPW060311K7BEEA",
    12.6e3: "RT0603BRD0712K6L", 15.8e3: "RT0603BRD0715K8L", 49.9e3: "RT0603BRD0749K9L", 63.4e3: "RT0603BRD0763K4L",
    105e3: "RT0603BRD07105KL", 120e3: "RT0603BRD07120KL", 133e3: "ARG03BTC1333", 140e3: "RT0603BRD07140KL"}


def part(ohm, extra_qty=3):
    """Stocked 0.1 %/25 ppm 0603 for this value, or None.  On-BOM parts must cover today's use plus extra_qty/board."""
    key = min(BOM_01, key=lambda k: abs(k - ohm))
    if abs(key - ohm) < 1e-6 * ohm:
        mpn = BOM_01[key]
        b = BOM[mpn]
        need = NEED + len(b["designators"]) * 500
        return {"mpn": mpn, "lcsc": b["lcsc"], "jlc_stock": b["jlc_stock"], "on_s43_bom": True,
                "usd_500": b["usd_500"], "ok": b["jlc_stock"] >= need} if b["jlc_stock"] >= need else None
    mpn = m.yageo_rt_mpn(ohm)
    rows = [r for r in jlc.search(mpn) if r[3] == mpn]
    if not rows or (rows[0][2] or 0) < NEED:
        return None
    det = jlc.detail(rows[0][0])
    return {"mpn": mpn, "lcsc": rows[0][0], "jlc_stock": rows[0][2], "on_s43_bom": False, "class": rows[0][1],
            "usd_500": jlc.price_at(det, 1500), "fetched": jlc.fetched(rows[0][0]), "ok": True}


# ----------------------------------------------------------------------------------------------------------- controls
def controls():
    st = json.load(open(STUDY))
    e_p4 = 0.001 + 25e-6 * 125
    for n in NAMES:
        p = m.lm339_params(m.S43, n, ib=False, zka=False, e_override=e_p4)
        lo, hi = m.vertices(p, m.lm339_f)
        a, b = st["old_bands"][n]
        assert abs(lo - a) < 1e-9 and abs(hi - b) < 1e-9, ("C1", n, lo, hi, a, b)
    for n, d in st["design"].items():
        ev = m.tps_eval(d["top_k"] * 1e3, d["bottom_k"] * 1e3, "UV" if "UV" in n else "OV", e_override=e_p4)
        for got, want in ((ev["trip_wc"], d["band_V"]), (ev["release_wc"], d["release_band_V"])):
            assert all(abs(x - y) < 1e-4 for x, y in zip(got, want)), ("C2", n, got, want)
    return {"C1": "P4 benchmark bands reproduce simplify-2026-10-15 old_bands (1e-9)",
            "C2": "study candidate-B bands reproduce under the study's assumptions (1e-4)"}


# -------------------------------------------------------------------------------------------------------------- rails
def rails(dt=None):
    ls, hs = m.ls_span(), m.hs_span(dt)
    nls, nhs = m.neg_rail("LS", dt), m.neg_rail("HS", dt)
    span = (min(ls["wc"][0], hs["wc"][0]), max(ls["wc"][1], hs["wc"][1]))
    neg = (min(nls["wc"][0], nhs["wc"][0]), max(nls["wc"][1], nhs["wc"][1]))
    return {"LS span": ls, "HS span": hs, "LS neg": nls, "HS neg": nhs, "span union": span, "neg union": neg}


def joint_rss(name, ev, rl):
    """Statistical interference: (rail centre - threshold centre) less the quadrature 3-sigma of both."""
    key = "span" if "span" in name else "neg"
    if key == "span":
        cands = [(rl["LS span"]["centre"], rl["LS span"]["rss"]), (rl["HS span"]["centre"], rl["HS span"]["rss"])]
    else:
        cands = [(rl["LS neg"]["centre"], rl["LS neg"]["rss"]), (rl["HS neg"]["centre"], rl["HS neg"]["rss"])]
    if "UV" in name:   # release side vs rail
        c, h = 0.5 * sum(ev["release_rss"]), 0.5 * (ev["release_rss"][1] - ev["release_rss"][0])
        gaps = [(rc - c) - math.hypot(rh, h) for rc, rh in cands]
        z = min((rc - c) / math.hypot(rh, h) * 3 for rc, rh in cands)
    else:
        c, h = 0.5 * sum(ev["trip_rss"]), 0.5 * (ev["trip_rss"][1] - ev["trip_rss"][0])
        gaps = [(c - rc) - math.hypot(rh, h) for rc, rh in cands]
        z = min((c - rc) / math.hypot(rh, h) * 3 for rc, rh in cands)
    tail_ppm = 0.5 * math.erfc(z / math.sqrt(2)) * 1e6
    return {"margin_V": min(gaps), "z_sigma": z, "tail_ppm_per_rail_normal": tail_ppm}


def rss_vs_rail(name, ev, rl):
    """Threshold RSS band against the rails' worst-case (guaranteed) limit."""
    span = rl["span union"] if "span" in name else rl["neg union"]
    return (span[0] - ev["release_rss"][1]) if "UV" in name else (ev["trip_rss"][0] - span[1])


def evaluate(design, kind, dt=None):
    rl = rails(dt)
    evs = {}
    for n in NAMES:
        if kind == "lm339":
            evs[n] = m.lm339_eval(design, n, dt)
        else:
            rt, rb = design["taps"][n]
            evs[n] = m.tps_eval(rt, rb, "UV" if "UV" in n else "OV", dt)
    bands = {n: evs[n]["trip_wc"] for n in NAMES}
    al = m.allowed(rl["span union"], rl["neg union"], bands)
    res = {}
    for n in NAMES:
        ev = evs[n]
        res[n] = {"nominal_V": r4(ev["nominal"]), "trip_wc_V": [r4(x) for x in ev["trip_wc"]],
                  "release_wc_V": [r4(x) for x in ev["release_wc"]], "trip_rss_V": [r4(x) for x in ev["trip_rss"]],
                  "release_rss_V": [r4(x) for x in ev["release_rss"]],
                  "Q": {k: (r4(v) if isinstance(v, float) else v) for k, v in m.judge(n, ev, al[n], "Q").items()},
                  "H": {k: (r4(v) if isinstance(v, float) else v) for k, v in m.judge(n, ev, al[n], "H").items()},
                  "rss_vs_wc_rail_V": r4(rss_vs_rail(n, ev, rl)),
                  "joint_rss": {k: round(v, 4) for k, v in joint_rss(n, ev, rl).items()},
                  "rss_contrib_V": {k: round(v, 5) for k, v in sorted(ev["rss_contrib"].items(), key=lambda x: -x[1])}}
    return res, al


# ------------------------------------------------------------------------------------------------------ option search
def select(cands):
    """Tiers of candidates, best first.  1) Fits the Q basis on both corners: maximise the smaller Q margin.
    2) Fix the rail side first (S16): rail-side margin >= target and H catch side >= 0, maximise the Q catch-side margin
    (least departure from the qualified basis).  3) Maximise the rail side.  Callers take the first stocked candidate."""
    tiers = []
    q_ok = [c for c in cands if min(c["q_catch"], c["q_rail"]) >= 0]
    if q_ok:
        tiers.append((sorted(q_ok, key=lambda c: min(c["q_catch"], c["q_rail"]), reverse=True), "Q"))
    s2 = [c for c in cands if c["q_rail"] >= c["tgt"] and c["h_catch"] >= 0]
    if s2:
        tiers.append((sorted(s2, key=lambda c: c["q_catch"], reverse=True), "rail side fixed; Q catch side violated, H met"))
    tiers.append((sorted(cands, key=lambda c: c["q_rail"], reverse=True), "rail side maximised"))
    return tiers


def _cand(name, ev, al, **kw):
    q, h = m.judge(name, ev, al, "Q"), m.judge(name, ev, al, "H")
    return dict(kw, q_catch=q["catch_side_V"], q_rail=q["rail_side_V"], h_catch=h["catch_side_V"], tgt=q["target_V"])


def _span(al, name):
    return (al["lo_H"], al["hi"]) if "UV" in name else (al["lo"], al["hi_H"])


def best_lm339(ref, r79, name):
    """Top resistor of one threshold (bottom kept at the fitted 10 k) chosen by select(); stocked parts only."""
    base = {"ref": ref, "rref": 2.2e3, "r79": r79, "r80": 10e3, "taps": dict(m.S43["taps"])}
    rl = rails()
    al = m.allowed(rl["span union"], rl["neg union"])[name]
    half = 2.495 * 10e3 / (r79 + 10e3)
    lo_v, hi_v = _span(al, name)
    cands = []
    for rb in LM_BOTTOMS:
        for rt in m.e192_range(max(10.0, 0.95 * (lo_v / half - 1) * rb), 1.05 * (hi_v / half - 1) * rb):
            d = dict(base, taps=dict(base["taps"], **{name: (rt, rb)}))
            cands.append(_cand(name, m.lm339_eval(d, name), al, rt=rt, rb=rb))
    tiers = select(cands)
    for ranked, basis in tiers:
        for c in ranked[:25]:
            pt, pb = part(c["rt"]), part(c["rb"])
            if pt and pb:
                return {"top_ohm": c["rt"], "bottom_ohm": c["rb"], "selection": basis, "top_part": pt, "bottom_part": pb,
                        "unconstrained_best_ohm": [tiers[0][0][0]["rt"], tiers[0][0][0]["rb"]]}
    return {"result": "no stocked pair", "unconstrained_best_ohm": [tiers[0][0][0]["rt"], tiers[0][0][0]["rb"]]}


LM_BOTTOMS = [10e3, 11e3, 11.7e3, 12.6e3]   # the fitted 10 k plus 0.1 % values already on the BOM (same 0603 pads)


TPS_BOTTOMS = [1e3, 1.21e3, 2e3, 2.21e3, 4.42e3, 5.11e3, 6.2e3, 7.68e3, 10e3, 11e3, 11.7e3, 12.6e3, 15.8e3]  # BOM values + stocked 1.21k/2k/5.11k


def best_tps(name, rl):
    kind = "UV" if "UV" in name else "OV"
    al = m.allowed(rl["span union"], rl["neg union"])[name]
    lo_v, hi_v = _span(al, name)
    cands = []
    for rb in TPS_BOTTOMS:
        for rt in m.e192_range(0.95 * (lo_v / 0.413 - 1) * rb, 1.05 * (hi_v / 0.387 - 1) * rb):
            cands.append(_cand(name, m.tps_eval(rt, rb, kind), al, rt=rt, rb=rb))
    stocked = []
    for ranked, basis in select(cands):
        for c in ranked[:40]:
            pt, pb = part(c["rt"]), part(c["rb"])
            if pt and pb:
                stocked.append((c, pt, pb))
        if stocked:
            break
    if not stocked:
        return {"result": "no stocked pair in the top 40"}
    # tie-break: within 10 mV of the best stocked minimum margin, prefer the pair with fewer MPNs new to the BOM
    mm = lambda c: min(c["q_catch"], c["q_rail"])
    best = mm(stocked[0][0])
    pool = [x for x in stocked if mm(x[0]) >= best - 0.010]
    c, pt, pb = sorted(pool, key=lambda x: (-(x[1]["on_s43_bom"] + x[2]["on_s43_bom"]), -mm(x[0])))[0]
    return {"top_ohm": c["rt"], "bottom_ohm": c["rb"], "selection": basis + "; tie-break fewer new MPNs within 10 mV",
            "top_part": pt, "bottom_part": pb, "best_stocked_min_Q_V": r4(best),
            "unconstrained_best": [ranked[0]["rt"], ranked[0]["rb"]],
            "unconstrained_best_min_Q_V": r4(mm(ranked[0]))}


# ------------------------------------------------------------------------------------------------------------- costing
def jlc_part(mpn):
    rows = [r for r in jlc.search(mpn) if r[3] == mpn]
    if not rows:
        return None
    det = jlc.detail(rows[0][0])
    return {"mpn": mpn, "lcsc": rows[0][0], "class": rows[0][1], "jlc_stock": rows[0][2], "det": det,
            "fetched": jlc.fetched(rows[0][0])}


def price(mpn, qty_per_board):
    if mpn in BOM and BOM[mpn]["usd_500"]:
        return BOM[mpn]["usd_500"]
    p = jlc_part(mpn)
    return jlc.price_at(p["det"], qty_per_board * 500) if p else None


def line_delta(changes):
    """changes: list of (designator, old_mpn, new_mpn or None).  Returns lines removed / added and $ per board."""
    use = {k: set(v["designators"]) for k, v in BOM.items()}
    removed_cost, added_cost, added = 0.0, 0.0, {}
    for des, old, new in changes:
        if old:
            use[old].discard(des)
            removed_cost += BOM[old]["usd_500"]
        if new:
            use.setdefault(new, set()).add(des)
            added[new] = added.get(new, 0) + 1
    for new, q in added.items():
        added_cost += q * (price(new, q) or 0.0)
    gone = [k for k, v in use.items() if not v and k in BOM]
    new_lines = [k for k in added if k not in BOM]
    return {"lines_removed": gone, "lines_added": new_lines, "net_lines": len(new_lines) - len(gone),
            "usd_per_board": round(added_cost - removed_cost, 4), "usd_per_500": round(500 * (added_cost - removed_cost), 2),
            "placements_delta": sum(1 for _, o, n in changes if n and not o) - sum(1 for _, o, n in changes if o and not n)}


def changes_lm339(design, ref):
    ch = []
    for i in range(3):
        if ref != m.S43["ref"]:
            ch.append((m.DESIG["ref"][i], m.S43["ref"], ref))
        if design["r79"] != m.S43["r79"]:
            ch.append((m.DESIG["r79"][i], "RT0603BRD0710KL", BOM_01.get(design["r79"]) or m.yageo_rt_mpn(design["r79"])))
        for n in NAMES:
            (rt_old, rb_old), (rt_new, rb_new) = m.S43["taps"][n], design["taps"][n]
            pt, pb = design["parts"][n]
            if rt_old != rt_new:
                ch.append((m.DESIG[n + " top"][i], BOM_01[rt_old], pt["mpn"]))
            if rb_old != rb_new:
                ch.append((m.DESIG[n + " bot"][i], BOM_01[rb_old], pb["mpn"]))
    return ch


def changes_tps(design):
    ch = []
    for i in range(3):
        ch += [(m.DESIG["ref"][i], "TL431AIDBZR", None), (m.DESIG["cmp"][i], "LM339BIDR", "TPS3701DDCR"),
               (("U47", "U48", "U49")[i], None, "TPS3701DDCR"), (m.DESIG["rref"][i], "RC1206FR-072K2L", None),
               (m.DESIG["r79"][i], "RT0603BRD0710KL", None), (m.DESIG["r80"][i], "RT0603BRD0710KL", None),
               (("C169", "C170", "C171")[i], None, "CC0603KRX7R9BB104")]
        for n in NAMES:
            rt_old, rb_old = m.S43["taps"][n]
            rt_new, rb_new = design["taps"][n]
            pt, pb = design["parts"][n]
            if rt_old != rt_new:
                ch.append((m.DESIG[n + " top"][i], BOM_01[rt_old], pt["mpn"]))
            if rb_old != rb_new:
                ch.append((m.DESIG[n + " bot"][i], BOM_01[rb_old], pb["mpn"]))
    return ch


# ---------------------------------------------------------------------------------------------------------------- main
def main():
    out = {"controls": controls(), "basis": {
        "T_lo_C": m.T_LO, "T_hi_bound_C": m.T_HI, "T_expected_C": round(m.T_EXPECTED, 1), "TCR_excursion_K": m.DT,
        "margin_target": f"{m.MARGIN_TARGET:.1%} of the threshold",
        "droop_nominal_V": r4(m.DROOP_NOM), "droop_corner_V": r4(m.DROOP_CORNER), "neg_edge_phys_V": r4(m.NEG_EDGE_PHYS)}}
    rl = rails()
    out["rails"] = {k: ({kk: ([r4(x) for x in vv] if isinstance(vv, tuple) else (r4(vv) if isinstance(vv, float) else vv))
                         for kk, vv in v.items()} if isinstance(v, dict) else [r4(x) for x in v]) for k, v in rl.items()}
    al = m.allowed(rl["span union"], rl["neg union"])
    out["allowed_generic"] = {n: {k: r4(v) for k, v in a.items()} for n, a in al.items()}

    # today's design
    today, al_t = evaluate(m.S43, "lm339")
    out["s43"] = {"design": {"ref": m.S43["ref"], "halfref": "10k/10k", "taps_ohm": m.S43["taps"]}, "thresholds": today,
                  "allowed": {n: {k: r4(v) for k, v in a.items()} for n, a in al_t.items()}}

    # option 1 variants
    variants = [("1a", "TL431AIDBZR", 10e3), ("1b", "TL431BIDBZR", 10e3)] + \
               [(f"1c-{int(r79)}", "TL431BIDBZR", r79) for r79 in (7.68e3, 6.2e3, 4.42e3)]
    out["option1"] = {}
    for tag, ref, r79 in variants:
        picks = {n: best_lm339(ref, r79, n) for n in NAMES}
        if any("result" in p for p in picks.values()):
            out["option1"][tag] = {"ref": ref, "r79": r79, "picks": picks}
            continue
        d = {"ref": ref, "rref": 2.2e3, "r79": r79, "r80": 10e3,
             "taps": {n: (picks[n]["top_ohm"], picks[n]["bottom_ohm"]) for n in NAMES},
             "parts": {n: (picks[n]["top_part"], picks[n]["bottom_part"]) for n in NAMES}}
        res, al_d = evaluate(d, "lm339")
        out["option1"][tag] = {"ref": ref, "r79_ohm": r79, "picks": picks, "thresholds": res,
                               "allowed": {n: {k: r4(v) for k, v in a.items()} for n, a in al_d.items()},
                               "delta": line_delta(changes_lm339(d, ref))}

    # option 2: candidate B re-tuned, plus the study's own values on the refined model
    picks = {n: best_tps(n, rl) for n in NAMES}
    d2 = {"taps": {n: (picks[n]["top_ohm"], picks[n]["bottom_ohm"]) for n in NAMES},
          "parts": {n: (picks[n]["top_part"], picks[n]["bottom_part"]) for n in NAMES}}
    res2, al2 = evaluate(d2, "tps")
    out["option2"] = {"picks": picks, "thresholds": res2,
                      "allowed": {n: {k: r4(v) for k, v in a.items()} for n, a in al2.items()},
                      "delta": line_delta(changes_tps(d2))}
    st = json.load(open(STUDY))["design"]
    dst = {"taps": {n: (st[n]["top_k"] * 1e3, st[n]["bottom_k"] * 1e3) for n in NAMES}}
    out["option2_study_values"] = {"taps_ohm": dst["taps"], "thresholds": evaluate(dst, "tps")[0]}

    # feasibility: worst-case width of each window corner pair at the slot centre vs the slot (continuous values)
    feas = {}
    slots = {n: (al[n]["lo_Q"], al[n]["hi"]) if "UV" in n else (al[n]["lo"], al[n]["hi_Q"]) for n in NAMES}
    for tag, ref, r79 in [("TL431A, halfref 10k/10k", "TL431AIDBZR", 10e3), ("TL431B, halfref 10k/10k", "TL431BIDBZR", 10e3),
                          ("TL431B, R79 6.2k", "TL431BIDBZR", 6.2e3), ("TL431B, R79 4.42k", "TL431BIDBZR", 4.42e3)]:
        row = {}
        for n in NAMES:
            c = 0.5 * sum(slots[n])
            half = 2.495 * 10e3 / (r79 + 10e3)
            d = {"ref": ref, "rref": 2.2e3, "r79": r79, "r80": 10e3, "taps": dict(m.S43["taps"], **{n: ((c / half - 1) * 10e3, 10e3)})}
            ev = m.lm339_eval(d, n)
            wd = ev["trip_wc"][1] - ev["trip_wc"][0]
            row[n] = {"width_V": r4(wd), "slot_V": r4(slots[n][1] - slots[n][0]), "slack_per_side_V": r4((slots[n][1] - slots[n][0] - wd) / 2)}
        feas["LM339B + " + tag] = row
    row = {}
    for n in NAMES:
        c = 0.5 * sum(slots[n])
        kind = "UV" if "UV" in n else "OV"
        # UV: corners are trip-low and release-high; centre the pair in the slot
        rb = 6.2e3
        ev = m.tps_eval((c / 0.4055 - 1) * rb if kind == "UV" else (c / 0.400 - 1) * rb, rb, kind)
        wd = (ev["release_wc"][1] - ev["trip_wc"][0]) if kind == "UV" else (ev["trip_wc"][1] - ev["trip_wc"][0])
        row[n] = {"width_V": r4(wd), "slot_V": r4(slots[n][1] - slots[n][0]), "slack_per_side_V": r4((slots[n][1] - slots[n][0] - wd) / 2)}
    feas["TPS3701 (UV: trip-low to release-high)"] = row
    out["feasibility_Q"] = feas

    # temperature sensitivity (TCR excursion) for today and option 2
    out["sensitivity_dt"] = {}
    for dt in (39.3, 60.0, 100.0):
        t, _ = evaluate(m.S43, "lm339", dt)
        o, _ = evaluate(d2, "tps", dt)
        out["sensitivity_dt"][f"{dt:g}K"] = {
            "s43": {n: {"trip_wc_V": t[n]["trip_wc_V"], "Q_min_V": min(t[n]["Q"]["catch_side_V"], t[n]["Q"]["rail_side_V"]),
                        "H_min_V": min(t[n]["H"]["catch_side_V"], t[n]["H"]["rail_side_V"])} for n in NAMES},
            "option2": {n: {"trip_wc_V": o[n]["trip_wc_V"], "release_wc_V": o[n]["release_wc_V"],
                            "Q_min_V": min(o[n]["Q"]["catch_side_V"], o[n]["Q"]["rail_side_V"])} for n in NAMES}}

    # part records used
    out["parts"] = {}
    for mpn in ("TPS3701DDCR", "TL431BIDBZR", "CC0603KRX7R9BB104"):
        p = jlc_part(mpn)
        if p:
            out["parts"][mpn] = {"lcsc": p["lcsc"], "class": p["class"], "jlc_stock": p["jlc_stock"],
                                 "usd_at_1500": jlc.price_at(p["det"], 1500), "usd_at_3000": jlc.price_at(p["det"], 3000),
                                 "fetched": p["fetched"]}
    OUT.mkdir(exist_ok=True)
    json.dump(out, open(OUT / "monitor_wc.json", "w"), indent=1, default=str)
    report(out)


def report(o):
    L = []
    w = L.append
    w("# S16 monitor worst case (generated by scripts/monitor_wc.py; do not edit)\n")
    w(f"Controls: {o['controls']['C1']}; {o['controls']['C2']}.\n")
    b = o["basis"]
    w(f"Basis: TCR excursion {b['TCR_excursion_K']:g} K ({b['T_lo_C']:g}..{b['T_hi_bound_C']:g} C; expected local "
      f"{b['T_expected_C']} C), margin target {b['margin_target']}, droop nominal {b['droop_nominal_V']} V / corner "
      f"{b['droop_corner_V']} V.\n")
    r = o["rails"]
    w(f"Rails (worst case): LS span {r['LS span']['wc']}, HS span {r['HS span']['wc']} (vendor +-1.5 %: "
      f"{r['HS span']['vendor_1p5pct']}), union {r['span union']}; neg LS {r['LS neg']['wc']}, HS {r['HS neg']['wc']}, "
      f"union {r['neg union']}.\n")

    def table(title, res, al):
        w(f"\n## {title}\n")
        w("| Threshold | Nominal | Trip WC | Release WC | Trip RSS | Q catch / rail (V) | Q | H catch / rail (V) | H | "
          "RSS vs WC rail | joint RSS (z) |")
        w("|---|---:|---|---|---|---|---|---|---|---:|---|")
        for n in NAMES:
            t = res[n]
            w(f"| {n} | {t['nominal_V']} | {t['trip_wc_V'][0]}..{t['trip_wc_V'][1]} | {t['release_wc_V'][0]}.."
              f"{t['release_wc_V'][1]} | {t['trip_rss_V'][0]}..{t['trip_rss_V'][1]} | {t['Q']['catch_side_V']:+.3f} / "
              f"{t['Q']['rail_side_V']:+.3f} | {t['Q']['verdict']} | {t['H']['catch_side_V']:+.3f} / "
              f"{t['H']['rail_side_V']:+.3f} | {t['H']['verdict']} | {t['rss_vs_wc_rail_V']:+.3f} | "
              f"{t['joint_rss']['margin_V']:+.3f} ({t['joint_rss']['z_sigma']:.1f}) |")
        w("\nAllowed: " + "; ".join(f"{n}: " + ", ".join(f"{k} {v}" for k, v in al[n].items()) for n in NAMES))

    w("\n## Feasibility on the Q basis (worst-case width at the slot centre vs the slot)\n")
    w("| Topology | " + " | ".join(NAMES) + " |")
    w("|---|" + "---|" * len(NAMES))
    for k, row in o["feasibility_Q"].items():
        w(f"| {k} | " + " | ".join(f"{row[n]['width_V']} / {row[n]['slot_V']} ({row[n]['slack_per_side_V']:+.3f})" for n in NAMES) + " |")
    table("s43 as built (TL431A + LM339B)", o["s43"]["thresholds"], o["s43"]["allowed"])
    for tag, v in o["option1"].items():
        if "thresholds" not in v:
            w(f"\n## Option {tag}: no stocked solution\n")
            continue
        table(f"Option {tag}: {v['ref']}, R79 {v['r79_ohm']:g} ohm, top/bottom " +
              ", ".join(f"{n} {v['picks'][n]['top_ohm']:g}/{v['picks'][n]['bottom_ohm']:g}" for n in NAMES),
              v["thresholds"], v["allowed"])
        w(f"\nDelta: {v['delta']}")
    v = o["option2"]
    table("Option 2: TPS3701 per window, " + ", ".join(f"{n} {v['picks'][n]['top_ohm']:g}/{v['picks'][n]['bottom_ohm']:g}"
                                                      for n in NAMES), v["thresholds"], v["allowed"])
    w(f"\nDelta: {v['delta']}")
    table("Option 2 with the study's divider values (refined model)", o["option2_study_values"]["thresholds"],
          o["option2"]["allowed"])
    open(OUT / "monitor_wc.md", "w").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
