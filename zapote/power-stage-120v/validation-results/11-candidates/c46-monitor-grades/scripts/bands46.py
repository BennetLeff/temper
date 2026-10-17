#!/usr/bin/env python3
"""Stage 46: the S16 rail-monitor window bands on the 125 C grades (TL431BQDBZR, LM2901BIDR), at the hot-copper
temperature of the monitor islands.

    python3 -I scripts/bands46.py [--grades REF_MPN,CMP_MPN] [PS_DIR]   -> results/bands-s46.json, results/bands-s46.md

The divider values (1c-4420, DECISIONS 60) and the reference / comparator MPNs are read from PS_DIR/frozen/
resolved-components.json (all three rails, asserted identical) through c45's bands45.frozen_design. --grades overrides
the two MPNs (the pre-build analysis, run on the s45 freeze). The S16 study's model.py / monitor_wc.py are imported
unchanged; this script only adds the two new grades' datasheet rows and evaluates at a wider temperature range:

  * TL431BQ (SLVS543S 6.13 p.14): Vref 2.483-2.507 V at 25 C, VI(dev) 34 mV max over the rated range, |zKA| 0.5 ohm -
    the same numbers as the BI row (6.12 p.13), now over -40..125 C (6.4 p.5, TL43xxQ).
  * LM2901B (SLCS006Z 6.8 p.8): VIO +-5.5 mV and IB 50 nA over -40..125 C - the LM339B's numbers (6.7 p.7) over its
    wider range (6.4 p.6, TA -40..125 C).
  * Temperature: T_HI = 125 C, the rated maximum of both grades (so every datasheet limit above holds over the whole
    range), which bounds the hot-copper B3 estimates at the monitor islands (b3-ratings/monitor-probes-2026-10-15:
    ICs <= 102.9 C at c18 @ 61 and <= 106.0 C over the BASIS, dividers <= ~88 C) by >= 19 K. The thin-film TCR
    excursion becomes max(25 - (-10), 125 - 25) = 100 K (0.1 % + 25 ppm/K x 100 K = 0.35 % per resistor), against
    S16's 60 K.

Judged twice:
  A (the brief's basis): thresholds at 100 K against the S16 allowed table (monitor_wc.md: rails at the study's 60 K),
    plus the 19 V hot-load ceiling on span OV;
  B (sensitivity): rails at 100 K too (the HS-span and neg-rail feedback dividers equally hot).
Controls (asserted): R1 the s45 frozen values at 60 K reproduce c45's bands-s45.json to 1e-4; R2 the study's s43 values
at 100 K reproduce its own sensitivity_dt['100K'] bands to 1e-4 (so the 100 K path is the study's own).
"""
import sys as _s; _s.dont_write_bytecode = True
import copy, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
args = [a for a in sys.argv[1:] if not a.startswith("--")]
GRADES = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--grades=")), None)
PS = Path(args[0]).resolve() if args else HERE.parents[3]
C45 = PS / "validation-results/11-candidates/c45-s16-monitor"
STUDY = PS / "validation-results/11-candidates/s16-monitor-2026-10-15"
OUT = HERE.parent / "results"
sys.path.insert(0, str(C45 / "scripts"))
_argv = sys.argv
sys.argv = ["bands45.py", str(PS)]
import bands45 as b45      # noqa: E402  (imports the study's model / monitor_wc unchanged; main() not run)
sys.argv = _argv
m, w = b45.m, b45.w
NAMES = w.NAMES
TOL = 1e-4

# ---- the 125 C grades (datasheet rows; the I-grade rows stay as the study wrote them)
m.TL431["TL431BQDBZR"] = {"v25": (2.483, 2.507), "videv": 0.034, "zka": 0.5,
                          "cite": "SLVS543S Table 6.13 p.14 (TL431BQ; TA -40..125 C, 6.4 p.5)"}
COMPARATORS = {
    "LM339BIDR": {"vos": 5.5e-3, "ib": 50e-9, "ta_max": 85.0, "cite": "SLCS006Z 6.7 p.7, TA -40..85 C (6.4 p.6)"},
    "LM2901BIDR": {"vos": 5.5e-3, "ib": 50e-9, "ta_max": 125.0, "cite": "SLCS006Z 6.8 p.8, TA -40..125 C (6.4 p.6)"},
}
REF_TA_MAX = {"TL431AIDBZR": 85.0, "TL431BIDBZR": 85.0, "TL431BQDBZR": 125.0}   # SLVS543S 6.4 p.5
T_LO = m.T_LO
B3_MONITOR_MAX = {"c18_h10@61 ICs": 102.9, "BASIS ICs (c28_h10@55, U29)": 106.0, "dividers (R59 worst)": 87.0}
HOT19 = 19.0   # out-D33/rail-hot-19V/hot-load.json (DECISIONS 59 integration note; c45 README section 2)


def comparator_mpns():
    res = json.loads((PS / "frozen/resolved-components.json").read_text())
    parts = {c["address"].split("::")[1]: c["attributes"] for c in res["components"]}
    got = {rail: parts[f"{base}.monitor"] for rail, base in b45.RAILS.items()}
    mpns = {a["mpn"] for a in got.values()}
    assert len(mpns) == 1, got
    return mpns.pop(), {r: a["designator"] for r, a in got.items()}, got["LS"]["footprint"]


def thresholds(design, dt_thr, dt_rail):
    """monitor_wc.evaluate, with the threshold and the rail temperature excursions separable."""
    rl = w.rails(dt_rail)
    evs = {n: m.lm339_eval(design, n, dt_thr) for n in NAMES}
    al = m.allowed(rl["span union"], rl["neg union"], {n: evs[n]["trip_wc"] for n in NAMES})
    r4 = w.r4
    res = {}
    for n in NAMES:
        ev = evs[n]
        res[n] = {"nominal_V": r4(ev["nominal"]), "trip_wc_V": [r4(x) for x in ev["trip_wc"]],
                  "trip_rss_V": [r4(x) for x in ev["trip_rss"]],
                  "Q": {k: (r4(v) if isinstance(v, float) else v) for k, v in m.judge(n, ev, al[n], "Q").items()},
                  "H": {k: (r4(v) if isinstance(v, float) else v) for k, v in m.judge(n, ev, al[n], "H").items()},
                  "rss_vs_wc_rail_V": r4(w.rss_vs_rail(n, ev, rl)),
                  "joint_rss": {k: round(v, 4) for k, v in w.joint_rss(n, ev, rl).items()}}
    rails = {k: [r4(x) for x in rl[k]] for k in ("span union", "neg union")}
    rails.update({k: [r4(x) for x in rl[k]["wc"]] for k in ("LS span", "HS span", "LS neg", "HS neg")})
    return res, {n: {k: r4(v) for k, v in a.items()} for n, a in al.items()}, rails


def close(a, b, path=""):
    if isinstance(a, dict):
        for k in a:
            close(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, (list, tuple)):
        assert len(a) == len(b), path
        for i, (x, y) in enumerate(zip(a, b)):
            close(x, y, f"{path}[{i}]")
    elif isinstance(a, (int, float)) and not isinstance(a, bool):
        assert abs(a - b) <= TOL, (path, a, b)
    else:
        assert a == b, (path, a, b)


def main():
    d, per_rail = b45.frozen_design()
    cmp_mpn, cmp_des, cmp_fp = comparator_mpns()
    frozen = {"reference": d["ref"], "comparator": cmp_mpn}
    if GRADES:
        d["ref"], cmp_mpn = GRADES.split(",")
    assert d["ref"] in REF_TA_MAX and cmp_mpn in COMPARATORS, (d["ref"], cmp_mpn)
    assert d["r79"] == 4.42e3 and d["r80"] == 10e3 and d["rref"] == 2.2e3, d          # 1c-4420 kept (DECISIONS 60)
    assert d["taps"] == {"neg UV": (750.0, 10e3), "neg OV": (2940.0, 10e3), "span UV": (90900.0, 11e3),
                         "span OV": (104000.0, 11e3)}, d["taps"]
    c = COMPARATORS[cmp_mpn]
    assert (c["vos"], c["ib"]) == (m.LM339B["vos"], m.LM339B["ib"]), "model.lm339_params reads m.LM339B"
    t_hi = min(REF_TA_MAX[d["ref"]], c["ta_max"])
    dt_hot = max(m.T_REF - T_LO, t_hi - m.T_REF)

    # R1: s45 values at the study's 60 K reproduce c45's committed bands
    d45 = dict(copy.deepcopy(d), ref="TL431BIDBZR")
    s45_json = json.loads((C45 / "results/bands-s45.json").read_text())["s45"]
    s45, al60, rails60 = thresholds(d45, None, None)
    for n in NAMES:
        close({k: s45[n][k] for k in ("nominal_V", "trip_wc_V", "trip_rss_V", "Q", "H", "rss_vs_wc_rail_V", "joint_rss")},
              {k: s45_json[n][k] for k in ("nominal_V", "trip_wc_V", "trip_rss_V", "Q", "H", "rss_vs_wc_rail_V", "joint_rss")},
              f"R1.{n}")
    # R2: the study's own 100 K sensitivity on its s43 values
    sens = json.loads((STUDY / "results/monitor_wc.json").read_text())["sensitivity_dt"]["100K"]["s43"]
    s43_100, _, _ = thresholds(m.S43, 100.0, 100.0)
    for n in NAMES:
        close(s43_100[n]["trip_wc_V"], sens[n]["trip_wc_V"], f"R2.{n}")
        close(min(s43_100[n]["Q"]["catch_side_V"], s43_100[n]["Q"]["rail_side_V"]), sens[n]["Q_min_V"], f"R2.{n}.Q")
    assert dt_hot == 100.0

    a_res, a_al, _ = thresholds(d, dt_hot, None)            # A: thresholds hot, S16 allowed table
    b_res, b_al, rails_hot = thresholds(d, dt_hot, dt_hot)  # B: rails hot too
    out = {"controls": {"R1": "s45 frozen values at 60 K reproduce c45 results/bands-s45.json to 1e-4",
                        "R2": "study s43 values at 100 K reproduce the study's sensitivity_dt['100K'] to 1e-4"},
           "frozen_mpns": frozen, "evaluated_mpns": {"reference": d["ref"], "comparator": cmp_mpn},
           "comparator_designators": cmp_des, "comparator_footprint": cmp_fp,
           "datasheet_rows": {"reference": m.TL431[d["ref"]]["cite"], "comparator": c["cite"]},
           "temperature_basis": {"T_lo_C": T_LO, "T_hi_C": t_hi, "TCR_excursion_K": dt_hot,
                                 "b3_monitor_max_C": B3_MONITOR_MAX, "s45_basis": "-10..85 C, 60 K"},
           "values": {"r79": d["r79"], "r80": d["r80"], "rref": d["rref"], "taps": d["taps"]},
           "s45_85C": {"thresholds": s45, "allowed": al60, "rails": rails60},
           "s46_125C_A": {"thresholds": a_res, "allowed": a_al},
           "s46_125C_B_rails_hot": {"thresholds": b_res, "allowed": b_al, "rails": rails_hot},
           "span_OV_19V": {"s45_85C": round(HOT19 - s45["span OV"]["trip_wc_V"][1], 4),
                           "s46_125C": round(HOT19 - a_res["span OV"]["trip_wc_V"][1], 4)},
           "verdict": {}}
    # ledger stresses at the s46 corners: c45's bands45.stresses on the s46 band, with the model's TCR excursion at the
    # 125 C basis (rref 1 % + 100 ppm/K x 100 K, the thin films 0.35 %)
    dt0 = m.DT
    m.DT = dt_hot
    try:
        out["stresses_125C"] = b45.stresses(d, a_res)
    finally:
        m.DT = dt0
    for n in NAMES:
        worst = min(a_res[n]["Q"]["rail_side_V"], b_res[n]["Q"]["rail_side_V"], a_res[n]["H"]["catch_side_V"])
        out["verdict"][n] = {"rail_side_A_V": a_res[n]["Q"]["rail_side_V"], "rail_side_B_V": b_res[n]["Q"]["rail_side_V"],
                             "Q_A": a_res[n]["Q"]["verdict"], "H_A": a_res[n]["H"]["verdict"],
                             "clears_rails_and_H": worst >= 0}
    out["verdict"]["span OV vs 19 V"] = out["span_OV_19V"]["s46_125C"] >= 0
    out["verdict"]["all_clear"] = all(v["clears_rails_and_H"] for k, v in out["verdict"].items() if k in NAMES) and \
        out["verdict"]["span OV vs 19 V"]
    OUT.mkdir(exist_ok=True)
    tag = "" if not GRADES else "-pre"
    (OUT / f"bands-s46{tag}.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    report(out, OUT / f"bands-s46{tag}.md")
    return 0 if out["verdict"]["all_clear"] else 1


def report(o, path):
    L = []
    a = L.append
    a("# Stage 46 rail-monitor bands on the 125 C grades (generated by scripts/bands46.py; do not edit)\n")
    a(f"Controls: {o['controls']['R1']}; {o['controls']['R2']}.\n")
    a(f"MPNs in the freeze: {o['frozen_mpns']}; evaluated: {o['evaluated_mpns']} "
      f"({o['datasheet_rows']['reference']}; {o['datasheet_rows']['comparator']}).\n")
    t = o["temperature_basis"]
    a(f"Temperature: {t['T_lo_C']:g}..{t['T_hi_C']:g} C, TCR excursion {t['TCR_excursion_K']:g} K (s45: {t['s45_basis']}). "
      f"B3 hot-copper estimates at the monitor islands: {t['b3_monitor_max_C']}.\n")
    a("Divider values unchanged (1c-4420): " + ", ".join(f"{n} {v[0]:g}/{v[1]:g}" for n, v in o["values"]["taps"].items()) +
      f"; halfref {o['values']['r79']:g}/{o['values']['r80']:g}.\n")
    a("## Bands: s45 (TL431BI + LM339B, -10..85 C) against s46 (TL431BQ + LM2901B, -10..125 C)\n")
    a("Rail margins against the S16 allowed table (monitor_wc.md; UV judged on its release corner, OV on its trip corner).\n")
    a("| Threshold | s45 worst case | s45 RSS | s46 worst case | s46 RSS | rail limit | rail margin WC s45 -> s46 | "
      "rail margin RSS s45 -> s46 | s46 rail margin WC, rails hot too |")
    a("|---|---|---|---|---|---:|---:|---:|---:|")
    s, n6, b = o["s45_85C"]["thresholds"], o["s46_125C_A"]["thresholds"], o["s46_125C_B_rails_hot"]["thresholds"]
    for n in o["s45_85C"]["thresholds"]:
        a(f"| {n} | {s[n]['trip_wc_V'][0]}..{s[n]['trip_wc_V'][1]} | {s[n]['trip_rss_V'][0]}..{s[n]['trip_rss_V'][1]} | "
          f"{n6[n]['trip_wc_V'][0]}..{n6[n]['trip_wc_V'][1]} | {n6[n]['trip_rss_V'][0]}..{n6[n]['trip_rss_V'][1]} | "
          f"{n6[n]['Q']['lim_rail']} | {s[n]['Q']['rail_side_V']:+.4f} -> {n6[n]['Q']['rail_side_V']:+.4f} | "
          f"{s[n]['rss_vs_wc_rail_V']:+.4f} -> {n6[n]['rss_vs_wc_rail_V']:+.4f} | {b[n]['Q']['rail_side_V']:+.4f} |")
    a("\n## Catch side and verdicts (Q = committed F6 qualification basis, H = hard ratings; target 0.5 % of the threshold)\n")
    a("| Threshold | Q catch s45 -> s46 | H catch s45 -> s46 | Q / H s45 | Q / H s46 | joint RSS s45 -> s46 (z) |")
    a("|---|---:|---:|---|---|---|")
    for n in s:
        a(f"| {n} | {s[n]['Q']['catch_side_V']:+.4f} -> {n6[n]['Q']['catch_side_V']:+.4f} | "
          f"{s[n]['H']['catch_side_V']:+.4f} -> {n6[n]['H']['catch_side_V']:+.4f} | {s[n]['Q']['verdict']} / {s[n]['H']['verdict']} | "
          f"{n6[n]['Q']['verdict']} / {n6[n]['H']['verdict']} | {s[n]['joint_rss']['margin_V']:+.3f} ({s[n]['joint_rss']['z_sigma']:.1f}) -> "
          f"{n6[n]['joint_rss']['margin_V']:+.3f} ({n6[n]['joint_rss']['z_sigma']:.1f}) |")
    v = o["span_OV_19V"]
    a(f"\nSpan OV upper corner against the 19 V hot-load campaign ceiling: s45 {v['s45_85C']:+.4f} V -> s46 {v['s46_125C']:+.4f} V.\n")
    r = o["s46_125C_B_rails_hot"]["rails"]
    a(f"Rails hot too (sensitivity B): span union {r['span union']} (LS {r['LS span']}, HS {r['HS span']}), "
      f"neg union {r['neg union']}; S16 table: span {o['s45_85C']['rails']['span union']}, neg {o['s45_85C']['rails']['neg union']}.\n")
    a(f"Verdict: rails and hard ratings clear on every threshold, and span OV under 19 V: **{o['verdict']['all_clear']}**.\n")
    st = o["stresses_125C"]
    a("## Ledger stresses (125 C basis)\n")
    a(f"- 2EDR8259X VDD at the span-OV trip upper corner: {st['2EDR8259X_VDD_at_span_OV_trip']['V']} V = "
      f"{st['2EDR8259X_VDD_at_span_OV_trip']['ratio_of_21V']} of the 21 V operating maximum.")
    t = st["TL431"]
    a(f"- TL431BQ: VKA max {t['vka_max_V']} V (REF tied to K); IK {t['ik_min_mA']}..{t['ik_max_op_mA']} mA over the "
      f"operating span {st['basis']['span_op_min_V']}..{st['basis']['span_op_max_V']} V; {t['ik_max_fault_mA']} mA, "
      f"{t['p_max_fault_mW']} mW ({t['self_heat_fault_K']} K at 206 C/W) at the {st['basis']['span_fault_V']} V fault case.")
    a(f"- LM2901B: supply = span <= {st['basis']['span_op_max_V']} V operating, {st['basis']['span_fault_V']} V fault case "
      f"(recommended 36 V, SLCS006Z 6.4 p.6).")
    path.write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    sys.exit(main())
