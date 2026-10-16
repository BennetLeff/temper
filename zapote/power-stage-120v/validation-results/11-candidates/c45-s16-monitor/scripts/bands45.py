#!/usr/bin/env python3
"""Stage 45 (S16, option 1c-4420): re-derive the four rail-monitor window bands from the values actually frozen.

    python3 -I scripts/bands45.py [PS_DIR]   -> results/bands-s45.json, results/bands-s45.md

PS_DIR defaults to the power-stage unit that holds this file. The values are read from PS_DIR/frozen/
resolved-components.json (MPN and value of every monitor part, all three rails), cross-checked against the Yageo RT
part-number rule, and fed to the S16 study's own model (11-candidates/s16-monitor-2026-10-15/scripts: model.py and
monitor_wc.evaluate, imported unchanged). Controls (asserted):
  R1  the s44 values (= the study's s43, the monitor is unchanged since) reproduce the study's s43 table to 1e-4;
  R2  the frozen s45 values reproduce the study's option 1c-4420 table to 1e-4 (nominal, worst case, RSS, margins).
It also writes the stresses the datasheet ledger cites (TL431B cathode current / voltage, resistor voltage and power,
the 2EDR8259X VDD at the span-OV trip upper corner).
"""
import sys as _s; _s.dont_write_bytecode = True
import json, math, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PS = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else HERE.parents[3]
STUDY = PS / "validation-results/11-candidates/s16-monitor-2026-10-15"
OUT = HERE.parent / "results"
sys.path.insert(0, str(STUDY / "scripts"))
sys.argv = ["monitor_wc.py", "--offline", str(PS)]      # monitor_wc reads its PS / offline flags from argv at import
import model as m          # noqa: E402
import monitor_wc as w     # noqa: E402  (import only: main() is not run, nothing in the study is written)

NAMES = w.NAMES
RAILS = {"LS": "monitor_ls", "HS-A": "bias_ha.monitor", "HS-B": "bias_hb.monitor"}
ROLES = {"rref": "rref", "r79": "rhalf_top", "r80": "rhalf_bot",
         "neg UV": ("ruv_top", "ruv_bot"), "neg OV": ("rov_top", "rov_bot"),
         "span UV": ("rspanuv_top", "rspanuv_bot"), "span OV": ("rspanov_top", "rspanov_bot")}
TOL = 1e-4


def ohms(v):
    """atopile value string ('4.42kohm', '750ohm') -> ohm."""
    g = re.fullmatch(r"([0-9.]+)\s*(k|M)?ohm", v)
    assert g, v
    return float(g.group(1)) * {None: 1.0, "k": 1e3, "M": 1e6}[g.group(2)]


def frozen_design():
    res = json.loads((PS / "frozen/resolved-components.json").read_text())
    parts = {c["address"].split("::")[1]: c["attributes"] for c in res["components"]}
    per_rail = {}
    for rail, base in RAILS.items():
        p = lambda k: parts[f"{base}.{k}"]
        ref = p("reference")["mpn"]
        assert ref in m.TL431, ref
        vals, rows = {}, []
        for role, key in ROLES.items():
            for k in (key if isinstance(key, tuple) else (key,)):
                a = p(k)
                r = ohms(a["value"])
                if a["mpn"].startswith("RT0603BRD07"):     # Yageo RT global part number encodes the value (RT V.16 p.2)
                    assert m.yageo_rt_mpn(r) == a["mpn"], (k, a)
                rows.append({"part": f"{base}.{k}", "designator": a["designator"], "mpn": a["mpn"], "ohm": r,
                             "footprint": a["footprint"]})
                vals[k] = r
        d = {"ref": ref, "rref": vals["rref"], "r79": vals["rhalf_top"], "r80": vals["rhalf_bot"],
             "taps": {n: (vals[t], vals[b]) for n, (t, b) in ((n, ROLES[n]) for n in NAMES)}}
        per_rail[rail] = {"design": d, "parts": rows, "reference": {"designator": p("reference")["designator"],
                                                                   "mpn": ref, "footprint": p("reference")["footprint"]}}
    designs = [json.dumps(v["design"], sort_keys=True) for v in per_rail.values()]
    assert len(set(designs)) == 1, "the three rail monitors differ"
    return per_rail["LS"]["design"], per_rail


def close(a, b, path=""):
    """Every number in a (computed, rounded as the study rounds) equals b (the study's JSON) within TOL."""
    if isinstance(a, dict):
        for k in a:
            if k in ("rss_contrib_V",):      # 5-decimal diagnostic, not part of the table
                continue
            close(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, (list, tuple)):
        assert len(a) == len(b), path
        for i, (x, y) in enumerate(zip(a, b)):
            close(x, y, f"{path}[{i}]")
    elif isinstance(a, (int, float)) and not isinstance(a, bool):
        assert abs(a - b) <= TOL, (path, a, b)
    else:
        assert a == b, (path, a, b)


def stresses(d, res):
    """Datasheet-ledger stresses at the s45 values (worst case over the stated corners)."""
    span_hi = res["span OV"]["trip_wc_V"][1]          # the monitor lets the stage run up to this span
    span_lo = res["span UV"]["trip_wc_V"][0]
    raw = 24.0                                         # V24_RAW nominal (PS2 MPM-20-24): LDO-pass-short case, NOT a bound
    neg_hi = w.rails()["neg union"][1]
    tl = m.TL431[d["ref"]]
    er = m.e_of(m.THICK_1_100)
    vref_lo, vref_hi = tl["v25"][0] - tl["videv"], tl["v25"][1] + tl["videv"]
    e = m.e_of(m.THIN_01_25)
    div_min = vref_lo / ((d["r79"] + d["r80"]) * (1 + e))
    div_max = vref_hi / ((d["r79"] + d["r80"]) * (1 - e))
    ik = lambda vs, vr, s: (vs - vr) / (d["rref"] * (1 + s * er))
    ik_min = ik(span_lo, vref_hi, +1) - div_max
    ik_max_op = ik(span_hi, vref_lo, -1) - div_min
    ik_max_raw = ik(raw, vref_lo, -1) - div_min
    out = {"basis": {"span_op_max_V": span_hi, "span_op_min_V": span_lo, "neg_rail_max_V": round(neg_hi, 4),
                     "span_fault_V": raw,
                     "span_fault_note": "V24_RAW nominal 24 V on the span (LS LDO pass short); PS2's own tolerance / OVP "
                                        "is not in the ledger, so this is a stated case, not a bound"},
           "TL431": {"vka_max_V": round(vref_hi, 4), "ik_min_mA": round(ik_min * 1e3, 3),
                     "ik_max_op_mA": round(ik_max_op * 1e3, 3), "ik_max_fault_mA": round(ik_max_raw * 1e3, 3),
                     "p_max_fault_mW": round(vref_hi * ik_max_raw * 1e3, 2),
                     "self_heat_fault_K": round(vref_hi * ik_max_raw * 206, 2)},
           "resistors": {},
           "2EDR8259X_VDD_at_span_OV_trip": {"V": round(span_hi, 4), "ratio_of_21V": round(span_hi / m.VDD_OP_MAX, 4)}}
    for n in NAMES:
        rt, rb = d["taps"][n]
        rows = []
        if "span" in n:
            rows = [("operating", span_hi), ("fault", raw)]
        else:      # the neg taps hang on src; an R77 open / TLVH431 open lets src float to P (S16 README section 2)
            rows = [("operating", neg_hi), ("fault", span_hi), ("fault_raw", raw)]
        for case, v in rows:
            vt, vb = v * rt / (rt + rb), v * rb / (rt + rb)
            out["resistors"].setdefault(f"{n} top {rt:g}", {})[case] = {"V": round(vt, 3), "mW": round(vt * vt / rt * 1e3, 3)}
            out["resistors"].setdefault(f"{n} bottom {rb:g}", {})[case] = {"V": round(vb, 3), "mW": round(vb * vb / rb * 1e3, 3)}
    return out


def main():
    study = json.loads((STUDY / "results/monitor_wc.json").read_text())
    d45, per_rail = frozen_design()
    old, _ = w.evaluate(m.S43, "lm339")
    close(old, study["s43"]["thresholds"])                                         # R1
    new, al = w.evaluate(d45, "lm339")
    ref = study["option1"]["1c-4420"]
    want = {"ref": ref["ref"], "r79": ref["r79_ohm"],
            "taps": {n: (ref["picks"][n]["top_ohm"], ref["picks"][n]["bottom_ohm"]) for n in NAMES}}
    assert d45["ref"] == want["ref"] and d45["r79"] == want["r79"] and d45["r80"] == 10e3 and d45["rref"] == 2.2e3, d45
    assert all(tuple(d45["taps"][n]) == tuple(want["taps"][n]) for n in NAMES), (d45["taps"], want["taps"])
    close(new, ref["thresholds"])                                                  # R2
    hot19 = PS / "validation-results/01-switching-parasitics/round17/delegation/out-D33/rail-hot-19V/hot-load.json"
    assert hot19.is_file()
    out = {"controls": {"R1": "s44 (= study s43) monitor values reproduce study s43 thresholds to 1e-4",
                        "R2": "frozen s45 values reproduce study option 1c-4420 thresholds to 1e-4"},
           "frozen_values": {r: v for r, v in per_rail.items()},
           "s44": old, "s45": new, "allowed": {n: {k: round(x, 4) for k, x in a.items()} for n, a in al.items()},
           "span_OV_qualified_ceiling_V": {"value": 19.0, "evidence": str(hot19.relative_to(PS)),
                                           "s45_margin_V": round(19.0 - new["span OV"]["trip_wc_V"][1], 4)},
           "stresses": stresses(d45, new)}
    OUT.mkdir(exist_ok=True)
    (OUT / "bands-s45.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    report(out)


def report(o):
    L = []
    a = L.append
    a("# Stage 45 rail-monitor bands (generated by scripts/bands45.py; do not edit)\n")
    a(f"Controls: {o['controls']['R1']}; {o['controls']['R2']}.\n")
    a("Values read from `frozen/resolved-components.json` (identical on LS / HS-A / HS-B):\n")
    a("| Part | LS / HS-A / HS-B | MPN | Value |")
    a("|---|---|---|---:|")
    fv = o["frozen_values"]
    a(f"| reference | {' / '.join(fv[r]['reference']['designator'] for r in RAILS)} | {fv['LS']['reference']['mpn']} | |")
    for i, row in enumerate(fv["LS"]["parts"]):
        des = " / ".join(fv[r]["parts"][i]["designator"] for r in RAILS)
        a(f"| {row['part'].split('.')[-1]} | {des} | {row['mpn']} | {row['ohm']:g} ohm |")
    a("\n## Bands, s44 (TL431A, halfref 10 k / 10 k) against s45 (TL431B, 4.42 k / 10 k, 1c-4420 taps)\n")
    a("| Threshold | s44 nominal | s44 worst case | s44 RSS | s45 nominal | s45 worst case | s45 RSS | rail limit | "
      "s44 rail margin WC | s45 rail margin WC | s45 rail margin RSS |")
    a("|---|---:|---|---|---:|---|---|---:|---:|---:|---:|")
    for n in NAMES:
        s, t = o["s44"][n], o["s45"][n]
        a(f"| {n} | {s['nominal_V']} | {s['trip_wc_V'][0]}..{s['trip_wc_V'][1]} | {s['trip_rss_V'][0]}..{s['trip_rss_V'][1]} | "
          f"{t['nominal_V']} | {t['trip_wc_V'][0]}..{t['trip_wc_V'][1]} | {t['trip_rss_V'][0]}..{t['trip_rss_V'][1]} | "
          f"{t['Q']['lim_rail']} | {s['Q']['rail_side_V']:+.4f} | {t['Q']['rail_side_V']:+.4f} | {t['rss_vs_wc_rail_V']:+.4f} |")
    a("\n## Catch side and verdicts (Q = committed F6 qualification basis, H = hard ratings)\n")
    a("| Threshold | s44 Q catch | s44 Q / H | s45 Q catch | s45 H catch | s45 Q / H | s45 joint RSS (z) |")
    a("|---|---:|---|---:|---:|---|---|")
    for n in NAMES:
        s, t = o["s44"][n], o["s45"][n]
        a(f"| {n} | {s['Q']['catch_side_V']:+.4f} | {s['Q']['verdict']} / {s['H']['verdict']} | {t['Q']['catch_side_V']:+.4f} | "
          f"{t['H']['catch_side_V']:+.4f} | {t['Q']['verdict']} / {t['H']['verdict']} | "
          f"{t['joint_rss']['margin_V']:+.3f} ({t['joint_rss']['z_sigma']:.1f}) |")
    q = o["span_OV_qualified_ceiling_V"]
    a(f"\nThe study's Q basis puts the span-OV ceiling at 18.0 V (the original hot-load span). The out-D33 hot-load campaign "
      f"was re-run at a 19 V span (`{q['evidence']}`, 128 / 128); against that 19.0 V ceiling the s45 span-OV upper corner "
      f"has {q['s45_margin_V']:+.4f} V.\n")
    st = o["stresses"]
    a("## Ledger stresses\n")
    a(f"- 2EDR8259X VDD at the span-OV trip upper corner: {st['2EDR8259X_VDD_at_span_OV_trip']['V']} V = "
      f"{st['2EDR8259X_VDD_at_span_OV_trip']['ratio_of_21V']} of the 21 V operating maximum.")
    t = st["TL431"]
    a(f"- TL431B: VKA max {t['vka_max_V']} V (REF tied to K); IK {t['ik_min_mA']}..{t['ik_max_op_mA']} mA over the "
      f"operating span {st['basis']['span_op_min_V']}..{st['basis']['span_op_max_V']} V; {t['ik_max_fault_mA']} mA, "
      f"{t['p_max_fault_mW']} mW ({t['self_heat_fault_K']} K at 206 C/W) at the {st['basis']['span_fault_V']} V fault case.")
    a(f"- Fault case: {st['basis']['span_fault_note']}.")
    a("\n| Resistor | case | V | mW |")
    a("|---|---|---:|---:|")
    for k, cases in st["resistors"].items():
        for c, v in cases.items():
            a(f"| {k} | {c} | {v['V']} | {v['mW']} |")
    (OUT / "bands-s45.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
