#!/usr/bin/env python3
"""Candidate-B FMEA: threshold bands for V0 / V1 / V2, reference-drift analysis, single-threshold offset faults, and the
C5 (open bottom resistor) overstress check with its fix re-checked against the S16 worst-case bands.

    python3 -I scripts/bands.py      -> results/bands.json, results/bands.md ; exit 1 if a control or invariant fails

Uses scripts/model.py, a verbatim copy of s16-monitor-2026-10-15/scripts/model.py (sha256 2e239bd8...), so every
datasheet input (TL431 / LM339B / TPS3701 limits, resistor tolerance + TCR over 60 K, rail models) is the S16 study's.

Variants
  V0  s43 as built: TL431AIDBZR, halfref 10k/10k, taps 4.42k/10k, 7.68k/10k, 120k/10k, 133k/10k
  V1  option 1c-4420: TL431BIDBZR, R79 4.42k, taps 750/10k, 2.94k/10k, 90.9k/11k, 104k/11k
  V2  candidate B (S16 option 2): one TPS3701 per window, taps 15.8k/4.42k, 28.4k/6.2k, 240k/6.2k, 86.6k/2.0k

Control: the three variants' worst-case trip / release bands reproduce the committed S16 results/monitor_wc.json
(copied to inputs/s16_monitor_wc.json from ee0698899) to 1e-4 V.
"""
import sys as _s; _s.dont_write_bytecode = True
import csv, itertools, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import model as m  # noqa: E402

ROOT = os.path.join(HERE, "..")
OUT = os.path.join(ROOT, "results")
NAMES = ("neg UV", "neg OV", "span UV", "span OV")
r4 = lambda x: round(x, 4)

V0 = dict(m.S43)
V1 = {"ref": "TL431BIDBZR", "rref": 2.2e3, "r79": 4.42e3, "r80": 10e3,
      "taps": {"neg UV": (750.0, 10e3), "neg OV": (2940.0, 10e3), "span UV": (90900.0, 11e3), "span OV": (104000.0, 11e3)}}
V2 = {"taps": {"neg UV": (15800.0, 4420.0), "neg OV": (28400.0, 6200.0), "span UV": (240000.0, 6200.0),
               "span OV": (86600.0, 2000.0)}}

# Rails (S16 model, worst case over LS and HS): span 16.575..17.425 V, neg (SRC-N) 1.9654..2.0757 V
SPAN = (16.575, 17.425)
NEG = (m.neg_rail("LS")["wc"][0], m.neg_rail("LS")["wc"][1])
RAIL = {"neg UV": NEG, "neg OV": NEG, "span UV": SPAN, "span OV": SPAN}
# Limits.  H = hard ratings / physics (S16 README section 2).  Q = inside the committed qualification evidence; the
# span-OV Q ceiling is 19.0 V since the out-D33 hot-load re-run at 19 V (S16 README "Decision"); S16's own search used 18.0.
H = {"neg UV": m.NEG_EDGE_PHYS + m.DROOP_NOM, "neg OV": m.D33_EDGE_SPAN - m.VGS_RDSON,
     "span UV": m.VGS_RDSON + m.D33_SWITCH_NEG, "span OV": m.VDD_OP_MAX}
Q = {"neg UV": m.F6_EDGE_LIMIT + m.DROOP_NOM, "neg OV": m.D33_SWITCH_NEG, "span UV": m.D33_EDGE_SPAN, "span OV": 19.0}


# ------------------------------------------------------------------------------------------------- control: bands
def bands():
    out = {}
    for tag, d in (("V0", V0), ("V1", V1)):
        out[tag] = {n: m.lm339_eval(d, n) for n in NAMES}
    out["V2"] = {n: m.tps_eval(*V2["taps"][n], "UV" if "UV" in n else "OV") for n in NAMES}
    return out


def control(b):
    ref = json.load(open(os.path.join(ROOT, "inputs", "s16_monitor_wc.json")))
    want = {"V0": ref["s43"]["thresholds"], "V1": ref["option1"]["1c-4420"]["thresholds"], "V2": ref["option2"]["thresholds"]}
    bad = []
    for tag in want:
        for n in NAMES:
            for key in ("trip_wc", "release_wc"):
                got, w = b[tag][n][key], want[tag][n][key + "_V"]
                if any(abs(x - y) > 1e-4 for x, y in zip(got, w)):
                    bad.append((tag, n, key, got, w))
    return bad


# ------------------------------------------------------------------------------- shared-reference drift analysis
def lm_parts(design, name):
    """Per-threshold (non-shared) parameter box of the LM339B topology: G = (rt+rb)/rb and the input offset term
    a = vos - ibt*(rt||rb).  The shared halfref (TL431 Vref incl. tolerance, VI(dev), zKA, R79/R80, 4 x IB into halfref)
    is the quantity that drifts, so it is left out: it cancels in the analysis below."""
    p = m.lm339_params(design, name)
    return {"rt": p["rt"], "rb": p["rb"], "vos": p["vos"], "ibt": p["ibt"]}


def lm_ga(rt, rb, vos, ibt):
    return (rt + rb) / rb, vos - ibt * (rt * rb / (rt + rb))


def drift_lm(design):
    """TL431 (or R79/R80) drift moves the halfref H of all four comparators together; T_i = (H + a_i) * G_i.
    Drift UP: a UV comparator trips (announced) once T_uv > rail, i.e. H > V/G_uv - a_uv.  The largest H that stays
    dormant is min over the two UV announcers of (V_max/G - a); the OV thresholds at that H are the most a TL431 drift can
    raise them without announcing.  Drift DOWN: the OV comparators announce once T_ov < rail; the lowest dormant H is
    max over the OV announcers of (V_min/G - a).  Exact extremes come from the vertex enumeration (every function here
    is monotonic in each parameter for fixed ordering of the min / max, and all orderings are enumerated)."""
    res = {}
    for direction, ann, tgt in (("up", ("span UV", "neg UV"), ("span OV", "neg OV")),
                                ("down", ("span OV", "neg OV"), ("span UV", "neg UV"))):
        for t in tgt:
            boxes = {f"{n}.{k}": v for n in ann + (t,) for k, v in lm_parts(design, n).items()}
            keys = list(boxes)
            best, best_v = None, None
            for combo in itertools.product(*(boxes[k] for k in keys)):
                v = dict(zip(keys, combo))
                hs = []
                for n in ann:
                    g, a = lm_ga(v[n + ".rt"], v[n + ".rb"], v[n + ".vos"], v[n + ".ibt"])
                    hs.append(RAIL[n][1] / g - a if direction == "up" else RAIL[n][0] / g - a)
                h = min(hs) if direction == "up" else max(hs)
                g, a = lm_ga(v[t + ".rt"], v[t + ".rb"], v[t + ".vos"], v[t + ".ibt"])
                th = (h + a) * g
                if best is None or (th > best if direction == "up" else th < best):
                    best, best_v = th, h
            # drift magnitude at the announcement point, relative to the unit's own undrifted halfref (shared box)
            sh = m.lm339_params(design, t)
            hvals = [((v25 + dev + zk) * r80 / (r79 + r80) + ibh * r79 * r80 / (r79 + r80))
                     for v25 in sh["v25"] for dev in sh["dev"] for zk in sh["zk"] for r79 in sh["r79"] for r80 in sh["r80"]
                     for ibh in sh["ibh"]]
            res[f"{direction}: {t}"] = {"worst_dormant_threshold_V": r4(best), "announcer": " / ".join(ann),
                                        "drift_at_announcement_pct": [r4(100 * (best_v / max(hvals) - 1)),
                                                                      r4(100 * (best_v / min(hvals) - 1))]}
    return res


def drift_tps(taps=None):
    """TPS3701: one internal reference serves INA and INB (SBVS240C 7.3.1 p.11).  A reference drift scales both
    thresholds of one IC: T = (VIT*s + iin*Rth) * G.  Up: the window's own UV announces (falling trip VIT-(INA) while
    running; rising release VIT+(INA) after the next power-up).  Down: the window's own OV announces (rising VIT+(INB))."""
    taps = taps or V2["taps"]
    res = {}
    wins = {"neg": ("neg UV", "neg OV"), "span": ("span UV", "span OV")}
    for w, (uv, ov) in wins.items():
        rail = RAIL[uv]
        for mode, vuv in (("running", m.TPS3701["uv_trip"]), ("after restart", m.TPS3701["uv_rel"])):
            # up: UV announcer, OV masked
            best = None
            for vu, vo, rtu, rbu, rto, rbo, iu, io in itertools.product(
                    vuv, m.TPS3701["ov_trip"],
                    m.box(taps[uv][0], m.e_of(m.THIN_01_25)), m.box(taps[uv][1], m.e_of(m.THIN_01_25)),
                    m.box(taps[ov][0], m.e_of(m.THIN_01_25)), m.box(taps[ov][1], m.e_of(m.THIN_01_25)),
                    (-m.TPS3701["iin"], m.TPS3701["iin"]), (-m.TPS3701["iin"], m.TPS3701["iin"])):
                gu, ru = (rtu + rbu) / rbu, rtu * rbu / (rtu + rbu)
                go, ro = (rto + rbo) / rbo, rto * rbo / (rto + rbo)
                s = (rail[1] / gu - iu * ru) / vu
                th = (vo * s + io * ro) * go
                if best is None or th > best[0]:
                    best = (th, s)
            res[f"up ({mode}): {ov}"] = {"worst_dormant_threshold_V": r4(best[0]), "announcer": uv,
                                         "drift_at_announcement_pct": r4(100 * (best[1] - 1))}
        # down: OV announcer (rising trip), UV masked (falling trip VIT-(INA))
        best = None
        for vu, vo, rtu, rbu, rto, rbo, iu, io in itertools.product(
                m.TPS3701["uv_trip"], m.TPS3701["ov_trip"],
                m.box(taps[uv][0], m.e_of(m.THIN_01_25)), m.box(taps[uv][1], m.e_of(m.THIN_01_25)),
                m.box(taps[ov][0], m.e_of(m.THIN_01_25)), m.box(taps[ov][1], m.e_of(m.THIN_01_25)),
                (-m.TPS3701["iin"], m.TPS3701["iin"]), (-m.TPS3701["iin"], m.TPS3701["iin"])):
            gu, ru = (rtu + rbu) / rbu, rtu * rbu / (rtu + rbu)
            go, ro = (rto + rbo) / rbo, rto * rbo / (rto + rbo)
            s = (rail[0] / go - io * ro) / vo
            th = (vu * s + iu * ru) * gu
            if best is None or th < best[0]:
                best = (th, s)
        res[f"down: {uv}"] = {"worst_dormant_threshold_V": r4(best[0]), "announcer": ov,
                              "drift_at_announcement_pct": r4(100 * (best[1] - 1))}
    return res


def judge_drift(d):
    out = {}
    for k, v in d.items():
        name = k.split(": ")[1]
        th = v["worst_dormant_threshold_V"]
        if "OV" in name:
            v["vs_H_V"], v["vs_Q_V"] = r4(H[name] - th), r4(Q[name] - th)
        else:
            v["vs_H_V"], v["vs_Q_V"] = r4(th - H[name]), r4(th - Q[name])
        v["H_limit"], v["Q_limit"] = r4(H[name]), r4(Q[name])
        v["silent_mask_vs_H"] = v["vs_H_V"] < 0
        v["outside_Q_while_dormant"] = v["vs_Q_V"] < 0
        out[k] = v
    return out


# ------------------------------------------------------------------ single-threshold faults (comparator offset)
def offset_to_limits():
    """Input-referred shift (mV) that moves one nominal threshold onto its H / Q limit, and that shift as a fraction of
    the comparator's own reference level (halfref for the LM339B, 400 mV for the TPS3701).  A per-comparator
    out-of-specification fault (LM339B 30 %, TPS3700-Q1 proxy 40 % of FMD) is not bounded by any companion threshold."""
    out = {}
    for tag, d in (("V0", V0), ("V1", V1), ("V2", V2)):
        row = {}
        for n in NAMES:
            rt, rb = d["taps"][n]
            g = (rt + rb) / rb
            lvl = 0.400 if tag == "V2" else 2.495 * d["r80"] / (d["r79"] + d["r80"])
            t = lvl * g
            row[n] = {"nominal_V": r4(t), "ref_level_V": r4(lvl),
                      "to_H_mV": r4(1e3 * (H[n] - t) / g), "to_Q_mV": r4(1e3 * (Q[n] - t) / g),
                      "to_H_pct_of_ref": r4(100 * (H[n] - t) / g / lvl), "to_Q_pct_of_ref": r4(100 * (Q[n] - t) / g / lvl)}
        out[tag] = row
    return out


# --------------------------------------------------------------------------------------------- C5 overstress
def c5():
    """Bottom resistor of each divider open: the pin rises to the divider's top node (no current flows unless the pin
    has an internal clamp, and SBVS240C rates none).  Report the open-circuit pin voltage (rail max) and, for a clamp
    assumed at 0 V or at the 7 V rating, the current the top resistor would push (bounds, not a clamp model)."""
    out = {}
    raw_ls = 24.0     # PS2 raw rail: an LDO pass short puts it on P (S16 README section 2)
    for tag, d, lim in (("V0", V0, 38.0), ("V1", V1, 38.0), ("V2", V2, 7.0)):
        row = {}
        for n in NAMES:
            rt, rb = d["taps"][n]
            top = RAIL[n][1]
            row[n] = {"pin_open_circuit_V": r4(top), "abs_max_V": lim, "over_abs_max": top > lim,
                      "I_if_clamped_at_7V_uA": r4(max(0.0, top - 7.0) / rt * 1e6),
                      "I_if_clamped_at_0V_uA": r4(top / rt * 1e6),
                      "pin_V_healthy_at_raw_24V": r4((raw_ls if "span" in n else RAIL[n][1]) * rb / (rt + rb))}
        out[tag] = row
    return out


# --------------------------------------------------------------- C5 fix: split each span bottom into two in parallel
def snapshot():
    rows = {}
    for r in csv.DictReader(open(os.path.join(ROOT, "inputs", "SNAPSHOT-2026-10-15.csv"))):
        if r.get("mpn"):
            rows[r["mpn"]] = r
    return rows


ONBOM = {  # 0.1 % / 25 ppm 0603 values on the s43 BOM (s16 monitor_wc.py BOM_01) plus the four V2 adds (S16 option 2)
    1e3: "RT0603BRD071KL", 2.21e3: "RT0603BRD072K21L", 4.42e3: "RT0603BRD074K42L", 6.2e3: "RT0603BRD076K2L",
    7.68e3: "RT0603BRD077K68L", 10e3: "RT0603BRD0710KL", 11e3: "RT0603BRD0711KL", 11.7e3: "TNPW060311K7BEEA",
    12.6e3: "RT0603BRD0712K6L", 15.8e3: "RT0603BRD0715K8L", 49.9e3: "RT0603BRD0749K9L", 63.4e3: "RT0603BRD0763K4L",
    105e3: "RT0603BRD07105KL", 120e3: "RT0603BRD07120KL", 133e3: "ARG03BTC1333", 140e3: "RT0603BRD07140KL",
    2.0e3: "RT0603BRD072KL", 28.4e3: "RT0603BRD0728K4L", 86.6e3: "RT0603BRD0786K6L", 240e3: "RT0603BRD07240KL"}
V2_ADDED_STOCK = {2.0e3: 14213, 28.4e3: 1967, 86.6e3: 10896, 240e3: 5139}   # S16 README option-2 parts table (JLC 2026-10-15)


def fix_split():
    """F2: each span-window bottom resistor becomes two equal resistors in parallel (one more 0603 per tap).  A single
    open now leaves the other half: the tap at most doubles (pin ~0.8 V, inside the 6.5 V recommended range) and the
    threshold halves: span UV catches only a deep collapse (still a partial mask), span OV trips at once (announced).
    Values: bottoms Rp/2 with Rp on the BOM (stock >= need), tops E192; S16 judge() on the Q basis, with the span-OV
    ceiling at the 19.0 V now qualified (the S16 option-2 row is re-judged on the same basis for comparison)."""
    snap = snapshot()
    rl_span = SPAN
    al = m.allowed(rl_span, NEG)
    al["span OV"] = dict(al["span OV"], hi_Q=Q["span OV"])   # span OV judged on the 19.0 V qualified ceiling
    res = {}
    for n in ("span UV", "span OV"):
        kind = "UV" if "UV" in n else "OV"
        base = m.tps_eval(*V2["taps"][n], kind)
        jb = m.judge(n, base, al[n], "Q")
        cands = []
        for rp, mpn in sorted(ONBOM.items()):
            stock = int(float(snap[mpn]["jlc_stock"] or 0)) if mpn in snap else V2_ADDED_STOCK.get(rp)
            rb = rp / 2
            tgt = base["nominal"]
            rt_ideal = rb * (tgt / 0.400 - 1)
            for rt in m.e192_range(0.97 * rt_ideal, 1.03 * rt_ideal):
                ev = m.tps_eval(rt, rb, kind)
                j = m.judge(n, ev, al[n], "Q")
                mm = min(j["catch_side_V"], j["rail_side_V"])
                cands.append({"bottom_pair_ohm": rp, "bottom_mpn": mpn, "bottom_stock": stock, "top_ohm": rt,
                              "top_on_bom": rt in ONBOM, "min_Q_margin_V": r4(mm),
                              "catch_V": r4(j["catch_side_V"]), "rail_V": r4(j["rail_side_V"]),
                              "trip_wc_V": [r4(x) for x in ev["trip_wc"]], "release_wc_V": [r4(x) for x in ev["release_wc"]]})
        # prefer: margin within 10 mV of the best; then both parts on the BOM; then bottom stock
        best = max(c["min_Q_margin_V"] for c in cands)
        pool = [c for c in cands if c["min_Q_margin_V"] >= best - 0.010 and (c["bottom_stock"] or 0) >= 1800 + 1500]
        pool.sort(key=lambda c: (-(c["top_on_bom"]), -(c["bottom_stock"] or 0), -c["min_Q_margin_V"]))
        pick = pool[0] if pool else None
        res[n] = {"S16_option2": {"taps_ohm": V2["taps"][n], "catch_V": r4(jb["catch_side_V"]), "rail_V": r4(jb["rail_side_V"]),
                                  "trip_wc_V": [r4(x) for x in base["trip_wc"]], "release_wc_V": [r4(x) for x in base["release_wc"]]},
                  "pick": pick, "best_any_margin_V": best}
        if pick:
            rb_single = pick["bottom_pair_ohm"]
            v_pin = rl_span[1] * rb_single / (pick["top_ohm"] + rb_single)
            thr = 0.400 * (pick["top_ohm"] + rb_single) / rb_single
            pick["after_one_half_opens"] = {"pin_V_at_rail_max": r4(v_pin), "threshold_nominal_V": r4(thr),
                                            "effect": ("span UV now trips only below ~%.1f V: partial mask, no overstress" % thr)
                                            if kind == "UV" else ("span OV threshold %.1f V < rail: trips at once (announced)" % thr)}
            pick["S16_basis_18V_catch_V"] = r4(18.0 - pick["trip_wc_V"][1]) if kind == "OV" else None
    return res


def main():
    b = bands()
    bad = control(b)
    out = {"control_bands_vs_s16": "reproduced to 1e-4 V" if not bad else bad,
           "rails": {"span": [r4(x) for x in SPAN], "neg": [r4(x) for x in NEG]},
           "limits": {"H": {k: r4(v) for k, v in H.items()}, "Q": {k: r4(v) for k, v in Q.items()}},
           "bands": {t: {n: {"trip_wc_V": [r4(x) for x in b[t][n]["trip_wc"]], "release_wc_V": [r4(x) for x in b[t][n]["release_wc"]],
                             "nominal_V": r4(b[t][n]["nominal"])} for n in NAMES} for t in b}}
    out["drift"] = {"V0": judge_drift(drift_lm(V0)), "V1": judge_drift(drift_lm(V1)), "V2": judge_drift(drift_tps())}
    out["offset_to_limits"] = offset_to_limits()
    out["c5"] = c5()
    out["c5_fix_split_bottom"] = fix_split()
    fx = out["c5_fix_split_bottom"]
    v2f = dict(V2["taps"], **{n: (fx[n]["pick"]["top_ohm"], fx[n]["pick"]["bottom_pair_ohm"] / 2) for n in ("span UV", "span OV")})
    out["V2F_taps_ohm"] = {n: list(v) for n, v in v2f.items()}
    out["drift"]["V2+F2"] = judge_drift(drift_tps(v2f))
    os.makedirs(OUT, exist_ok=True)
    json.dump(out, open(os.path.join(OUT, "bands.json"), "w"), indent=1, sort_keys=True)

    L = ["# Bands, reference drift, offsets and C5 (generated by scripts/bands.py)", "",
         f"Control: V0 / V1 / V2 bands vs committed S16 monitor_wc.json: {out['control_bands_vs_s16']}.", "",
         f"Rails: span {out['rails']['span']} V, neg (SRC-N) {out['rails']['neg']} V. Limits H {out['limits']['H']}; "
         f"Q {out['limits']['Q']} (span-OV Q = 19.0 V after the 19 V hot-load re-run).", "",
         "## Shared-reference drift: the worst threshold a drift can reach while every companion stays quiet", "",
         "| variant | drift / masked threshold | announcer | drift at announcement (%) | worst dormant threshold (V) | margin to H (V) | margin to Q (V) | silent mask vs H |",
         "|---|---|---|---|---:|---:|---:|:-:|"]
    for t in ("V0", "V1", "V2", "V2+F2"):
        for k, v in out["drift"][t].items():
            L.append(f"| {t} | {k} | {v['announcer']} | {v['drift_at_announcement_pct']} | {v['worst_dormant_threshold_V']} | "
                     f"{v['vs_H_V']:+.3f} | {v['vs_Q_V']:+.3f} | {'YES' if v['silent_mask_vs_H'] else 'no'} |")
    L += ["", "## One comparator out of specification: input-referred shift that puts one threshold on its limit", "",
          "| variant | threshold | nominal V | reference level V | to H: mV (% of ref) | to Q: mV (% of ref) |", "|---|---|---:|---:|---:|---:|"]
    for t, row in out["offset_to_limits"].items():
        for n, v in row.items():
            L.append(f"| {t} | {n} | {v['nominal_V']} | {v['ref_level_V']} | {v['to_H_mV']:+.1f} ({v['to_H_pct_of_ref']:+.1f} %) | "
                     f"{v['to_Q_mV']:+.1f} ({v['to_Q_pct_of_ref']:+.1f} %) |")
    L += ["", "## C5: bottom resistor open", "",
          "| variant | threshold | pin open-circuit V | abs max V | over? | I if clamped at 7 V (uA) | I if clamped at 0 V (uA) |",
          "|---|---|---:|---:|:-:|---:|---:|"]
    for t, row in out["c5"].items():
        for n, v in row.items():
            L.append(f"| {t} | {n} | {v['pin_open_circuit_V']} | {v['abs_max_V']} | {'YES' if v['over_abs_max'] else 'no'} | "
                     f"{v['I_if_clamped_at_7V_uA']} | {v['I_if_clamped_at_0V_uA']} |")
    L += ["", "## C5 fix F2: split each span bottom resistor into two in parallel (S16 bands re-checked)", ""]
    for n, v in out["c5_fix_split_bottom"].items():
        s, p = v["S16_option2"], v["pick"]
        L.append(f"- **{n}**: S16 option 2 {s['taps_ohm']} -> trip {s['trip_wc_V']}, release {s['release_wc_V']}, Q catch "
                 f"{s['catch_V']:+.3f} / rail {s['rail_V']:+.3f} V.")
        if p:
            L.append(f"  F2 pick: top {p['top_ohm']:g} ohm ({'on BOM' if p['top_on_bom'] else 'new line'}), bottom 2 x "
                     f"{p['bottom_pair_ohm']:g} ohm {p['bottom_mpn']} (JLC stock {p['bottom_stock']}) -> trip {p['trip_wc_V']}, "
                     f"release {p['release_wc_V']}, Q catch {p['catch_V']:+.3f} / rail {p['rail_V']:+.3f} V"
                     + (f" (span OV judged on 19.0 V; against S16's 18.0 V basis the catch is {p['S16_basis_18V_catch_V']:+.3f} V)" if p['S16_basis_18V_catch_V'] is not None else "") + ".")
            L.append(f"  One half open: pin {p['after_one_half_opens']['pin_V_at_rail_max']} V; {p['after_one_half_opens']['effect']}.")
    open(os.path.join(OUT, "bands.md"), "w").write("\n".join(L) + "\n")
    print("\n".join(L))

    inv = list(bad)
    for t in ("V0", "V1", "V2", "V2+F2"):
        for k, v in out["drift"][t].items():
            if v["silent_mask_vs_H"]:
                inv.append(f"note: {t} {k} silent vs H")   # reported, and also fails the run so the README cannot miss it
    print("invariants:", inv if inv else "all hold")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
