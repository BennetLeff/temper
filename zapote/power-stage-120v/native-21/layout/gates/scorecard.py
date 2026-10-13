#!/usr/bin/env python3
"""Benchmark scorecard for a native-21 candidate board (stage 19c onward).

    python3 scorecard.py TAG BUILDDIR [--bom BOM.csv] [--stock STOCK.csv] [--json OUT.json]
                         [--audit PASS|FAIL] [--compare BENCH.json]
    python3 scorecard.py --card CANDIDATE.json --compare BENCH.json      # saved card against saved card

Score a candidate immediately after its own `chain.sh` run and save the card (--json): the D5 audit, B3 summary
and enclosure-fit files are repo-level and hold the latest chain's results, so a card computed later for an older
build would mix boards. Comparisons are card against card.

Reads the outputs `chain.sh` leaves in BUILDDIR (drc.json, barrier-gate-rust.json, jlc-dfm.json, return-path.json,
bypass-check.json, pi-distances.json, res-a-creepage.json, copper-dump.json) plus the repo files the chain refreshes
(D5 audit, Kelvin budget for TAG, B3 summary, enclosure-fit results) and the desk studies (EMI, leakage, F2, F1
containment, CMTI). Every metric names its source file. Three groups:

* gates: hard pass / fail. A candidate with any gate failing is not a candidate.
* performance: margins, each with a direction ("higher" or "lower" is better).
* cost: parts, lines, JLC extended lines, hand / consigned lines, parts cost at 5 and 500 boards (joined to the
  stock survey by MPN; lines it lacks count as unpriced), vias, board area, zero-stock and single-source lines.

--compare BENCH.json applies the acceptance rule fixed on 2026-10-13 (RESOLUTION-PLAN / benchmark README) against a
benchmark's scorecard: every gate passes; no performance metric is worse than the benchmark beyond its tolerance;
and cost is lower (parts cost at 500, or line count, strictly lower with neither higher) or performance strictly
better on at least one metric at equal-or-lower cost. It prints ACCEPT / REJECT with the reasons.
"""
import argparse
import csv
import json
import math
from pathlib import Path

UNIT = Path(__file__).resolve().parents[3]          # zapote/power-stage-120v
VR = UNIT / "validation-results"
FAB = VR / "08-manufacturing-package/native-21/fab"

# performance metric -> (direction, tolerance before it counts as worse)
PERF = {
    "d5_hot_selv_mm": ("higher", 0.0),
    "d5_hot_pe_mm": ("higher", 0.0),
    "res_a_outer_min_mm": ("higher", 0.0),
    "return_path_open_changes": ("lower", 0),
    "return_path_worst_asserted_mm": ("lower", 0.2),
    "kelvin_band_low_A": ("higher", 0.5),
    "b3_c28_h25_peak_C": ("lower", 1.0),
    "b3_nominal_h10_peak_C": ("lower", 1.0),
    "emi_min_margin_dB": ("higher", 0.5),
    "leakage_touch_mA": ("lower", 0.0),
    "cmti_gate_ratio_min": ("higher", 0.0),
    "fuse_copper_fusing_ratio": ("higher", 0.0),
    "bank_ratio_tdk_28A_40k": ("lower", 0.0),     # added 2026-10-13 (stage 20): DECISIONS item 21 / 23 thermal margin
}


def jload(p):
    p = Path(p)
    return json.loads(p.read_text()) if p.exists() else None


def gates(b, tag, audit):
    g, src = {}, {}
    drc = jload(b / "drc.json")
    if drc:
        errs = [v for v in drc["violations"] if v["severity"] == "error"]
        g["drc_errors_0"] = not errs
        g["drc_unconnected_0"] = not drc.get("unconnected_items")
        g["drc_parity_0"] = not drc.get("schematic_parity")
        src["drc"] = str(b / "drc.json")
    rust = jload(b / "barrier-gate-rust.json")
    if rust:
        g["barrier_8mm"] = rust["violations"] == 0 and rust.get("cross_layer", 0) == 0
        g["res_a_outer_12p6mm"] = rust.get("res_a_outer_violations", 1) == 0
    dfm = jload(b / "jlc-dfm.json")
    if dfm:
        g["jlc_dfm"] = dfm["status"] == "PASS"
    rp = jload(b / "return-path.json")
    if rp:
        g["return_path19"] = rp["pass"]
    by = jload(b / "bypass-check.json")
    if by:
        g["bypass"] = by["all_pass"]
    pi = jload(b / "pi-distances.json")
    if pi:
        g["pi_distances"] = pi["pass"]
    ra = jload(b / "res-a-creepage.json")
    if ra:
        g["res_a_creepage18"] = not ra["violations"]
    d5 = jload(UNIT / "native-21/verification/d5-audit.json")
    if d5:
        g["d5"] = bool(d5["verdict_pcb"])
    fit = jload(UNIT / "validation-plan/enclosure-fit/native21-body-collisions.json")
    r4 = jload(UNIT / "validation-plan/enclosure-fit/native21-in-r4.json")
    if fit and r4:
        g["enclosure_fit"] = fit.get("unattributed", 1) == 0 and not fit.get("part_overlaps") and not r4.get("hits")
    if audit:
        g["audit_rs"] = audit == "PASS"
    return g


def performance(b, tag):
    m, src = {}, {}
    d5 = jload(UNIT / "native-21/verification/d5-audit.json")
    if d5:
        m["d5_hot_selv_mm"] = d5["copper"]["HOT-SELV"]["min_mm"]
        m["d5_hot_pe_mm"] = d5["copper"]["HOT-PE"]["min_mm"]
        src["d5"] = "native-21/verification/d5-audit.json"
    rust = jload(b / "barrier-gate-rust.json")
    ra = jload(b / "res-a-creepage.json")
    if ra and ra.get("pairs_under_25mm"):
        ds = [p["mm"] for p in ra["pairs_under_25mm"] if isinstance(p, dict) and p.get("gated")]
        ds = [x for x in ds if isinstance(x, (int, float))]
        if ds:
            m["res_a_outer_min_mm"] = round(min(ds), 3)
    rp = jload(b / "return-path.json")
    if rp:
        opened, worst = 0, 0.0
        asserted = set(rp["asserted"]["transfer"])
        for net, s in rp["signals"].items():
            if not isinstance(s, dict) or "reference_changes" not in s:
                continue
            for c in s["reference_changes"]:
                mm = c.get("mm")
                if mm is None or mm > 3.0:
                    opened += 1
                if net in asserted and mm is not None:
                    worst = max(worst, mm)
        m["return_path_open_changes"] = opened
        m["return_path_worst_asserted_mm"] = round(worst, 2)
    kb = jload(VR / f"02-protection-timing/kelvin/budget-{tag}.json")
    if kb:
        band = kb.get("band_after_A")
        m["kelvin_band_low_A"] = band[0] if isinstance(band, list) else band
        src["kelvin"] = f"02-protection-timing/kelvin/budget-{tag}.json"
    b3 = jload(VR / "04-board-current-thermal/round5-native21/b3/outputs/summary.json")
    if b3:
        m["b3_c28_h25_peak_C"] = round(b3["runs"]["c28_h25_p1p0"]["peak"]["temperature_c"], 1)
        m["b3_nominal_h10_peak_C"] = round(b3["runs"]["nominal_h10_p1p0"]["peak"]["temperature_c"], 1)
    emi = jload(VR / "07-conducted-emi/s19b/results.json")
    if emi:
        def margins(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    if k == "margin_dB" and isinstance(v, (int, float)):
                        yield v
                    else:
                        yield from margins(v)
        ms = list(margins(emi.get("scenarios", {}).get("nominal", {})))
        if ms:
            m["emi_min_margin_dB"] = round(min(ms), 1)
            src["emi"] = "07-conducted-emi/s19b/results.json scenarios.nominal (min margin_dB)"
    lk = jload(VR / "07-conducted-emi/leakage/result.json")
    if lk:
        d = [r for r in lk.get("results", []) if r.get("label", "").startswith("DESIGN")]
        if d:
            m["leakage_touch_mA"] = round(d[0]["governing_touch_mA"], 3)
            src["leakage"] = "07-conducted-emi/leakage/result.json DESIGN row"
    tagged = jload(VR / f"02-protection-timing/shoot-through-f1/{tag.replace('native21s', 's')}_necks.json")
    f1 = jload(VR / "02-protection-timing/shoot-through-f1/result.json")
    if tagged:          # stage-specific neck run (s21_necks.py onward): min over every series row, actual via drills
        m["fuse_copper_fusing_ratio"] = tagged["min_ratio_all"]
        src["fuse_copper"] = f"02-protection-timing/shoot-through-f1/{tag.replace('native21s', 's')}_necks.json (min_ratio_all)"
    elif f1 and isinstance(f1.get("verdict"), dict):
        v = f1["verdict"]
        m["fuse_copper_fusing_ratio"] = round(v["min_copper_I2t_conservative"] / v["F1_clearing_I2t"], 3)
        src["fuse_copper"] = "02-protection-timing/shoot-through-f1/result.json (min copper fusing I2t / F1 clearing I2t)"
    cm = VR / "06-controller-interface/cmti/cmti.csv"
    if cm.exists():
        rows = [r for r in csv.DictReader(open(cm)) if r.get("cls") == "GATE" and r.get("ratio_hard") and r["ref"] != "CTRL"]
        if rows:
            m["cmti_gate_ratio_min"] = min(float(r["ratio_hard"]) for r in rows)
            src["cmti"] = "06-controller-interface/cmti/cmti.csv (GATE rows, ratio at 95 V/ns)"
    # resonant bank at 28 A, 40 kHz: ratio of the predicted per-cap current to TDK's curve, by the fitted part's
    # tolerance grade (11-candidates/g04-g09-tank-detect/scripts/bank_options.py; lower is better)
    bo = jload(VR / "11-candidates/g04-g09-tank-detect/results/bank_options.json")
    if bo:
        grade = None
        for r in csv.DictReader(open(FAB / "bom-jlcpcb.csv")):
            if r["Manufacturer Part Number"].startswith("B32654A1104"):
                grade = r["Manufacturer Part Number"][-4]          # K or J
        if grade in ("K", "J"):
            m["bank_ratio_tdk_28A_40k"] = bo["baseline"][{"K": "5x100nF_K(+-10%)", "J": "5x100nF_J(+-5%)"}[grade]]["ratio_to_curve_28A_40k"]
            src["bank"] = f"11-candidates/g04-g09-tank-detect/results/bank_options.json baseline {grade}"
    return m, src


def cost(b, bom_path, stock_path):
    c = {}
    rows = list(csv.DictReader(open(bom_path)))
    c["bom_lines"] = len(rows)
    c["placements"] = sum(len([d for d in r["Designator"].split(",") if d.strip()]) for r in rows)
    c["jlc_extended_lines"] = sum("Extended" in r.get("Assembly", "") for r in rows)
    c["jlc_basic_lines"] = sum("Basic" in r.get("Assembly", "") for r in rows)
    c["hand_or_consign_lines"] = sum(("consign" in r.get("Assembly", "").lower() or "hand" in r.get("Assembly", "").lower()
                                      or r.get("Mount") == "THT") for r in rows)
    c["tht_lines"] = sum(r.get("Mount") == "THT" for r in rows)
    extras = bom_path.parent / "hand-assembly-extras.csv"
    if extras.exists():
        c["hand_or_consign_lines"] += sum(1 for _ in csv.DictReader(open(extras)))
    paths = [Path(x) for x in str(stock_path).split(",")] if stock_path else []
    if paths and all(x.exists() for x in paths):
        st = {}
        for sp in paths:                  # later files (addenda for new MPNs) override earlier rows
            for r in csv.DictReader(open(sp)):
                if r["board"].startswith("power"):
                    st[r["mpn"].strip()] = r
        c5 = c500 = 0.0
        unpriced, zero, single = [], [], []
        for r in rows:
            mpn = r["Manufacturer Part Number"].strip()
            q = len([d for d in r["Designator"].split(",") if d.strip()])
            s = st.get(mpn)
            if not s:
                unpriced.append(mpn)
                continue
            try:
                c5 += float(s["unit_usd_at_5boards"]) * q
                c500 += float(s["unit_usd_at_500boards"]) * q
            except ValueError:
                unpriced.append(mpn)
            fl = s.get("flags", "")
            if "ZERO" in fl:
                zero.append(mpn)
            if "SINGLE_SOURCE" in fl:
                single.append(mpn)
        c["parts_usd_at_5"] = round(c5, 2)
        c["parts_usd_at_500"] = round(c500, 2)
        c["unpriced_lines"] = unpriced
        c["zero_stock_lines"] = len(zero)
        c["single_source_lines"] = len(single)
    dfm = jload(b / "jlc-dfm.json")
    if dfm:
        c["vias"] = dfm["vias"]
    dump = jload(b / "copper-dump.json")
    if dump and dump.get("edges"):
        xs = [v for e in dump["edges"] for v in (e[0], e[2])]
        ys = [v for e in dump["edges"] for v in (e[1], e[3])]
        if xs:
            c["board_bbox_mm2"] = round((max(xs) - min(xs)) * (max(ys) - min(ys)), 0)
    return c


def compare(cur, bench):
    reasons, better = [], []
    for k, ok in cur["gates"].items():
        if not ok:
            reasons.append(f"gate {k} fails")
    for k, (direction, tol) in PERF.items():
        a, b = cur["performance"].get(k), bench["performance"].get(k)
        if a is None or b is None:
            continue
        worse = (a < b - tol) if direction == "higher" else (a > b + tol)
        if worse:
            reasons.append(f"{k} worse: {a} vs benchmark {b} (tolerance {tol})")
        elif (a > b) if direction == "higher" else (a < b):
            better.append(k)
    ca, cb = cur["cost"], bench["cost"]
    cheaper = [k for k in ("parts_usd_at_500", "bom_lines", "placements", "jlc_extended_lines", "hand_or_consign_lines",
                           "zero_stock_lines") if k in ca and k in cb and ca[k] < cb[k]]
    dearer = [k for k in ("parts_usd_at_500", "bom_lines", "jlc_extended_lines", "hand_or_consign_lines")
              if k in ca and k in cb and ca[k] > cb[k]]
    if dearer and not better:
        reasons.append(f"costlier on {dearer} with no performance gain")
    if not cheaper and not better:
        reasons.append("neither cheaper/simpler nor better than the benchmark")
    return (not reasons), reasons, cheaper, better


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tag", nargs="?")
    ap.add_argument("build", nargs="?")
    ap.add_argument("--card", help="a saved scorecard to compare instead of computing one")
    ap.add_argument("--bom", default=str(FAB / "bom-jlcpcb.csv"))
    ap.add_argument("--stock", default=",".join(str(p) for p in sorted((VR / "08-manufacturing-package/native-21/sourcing").glob("STOCK-2026-10-13*.csv"))),
                    help="comma-separated stock CSVs; addenda (STOCK-2026-10-13-addendum-*.csv) add rows for new MPNs")
    ap.add_argument("--audit")
    ap.add_argument("--json")
    ap.add_argument("--compare")
    a = ap.parse_args()
    if a.card:
        card = jload(a.card)
        ok, reasons, cheaper, better = compare(card, jload(a.compare))
        print(("ACCEPT" if ok else "REJECT") + f" {card['tag']} vs {a.compare}: cheaper {cheaper}, better {better}"
              + ("" if ok else "; " + "; ".join(reasons)))
        raise SystemExit(0 if ok else 1)
    b = Path(a.build)
    perf, src = performance(b, a.tag)
    card = {"tag": a.tag, "build": str(b), "board_sha256": (jload(b / "barrier-gate-rust.json") or {}).get("board_sha256"),
            "gates": gates(b, a.tag, a.audit), "performance": perf, "cost": cost(b, Path(a.bom), a.stock),
            "sources": src}
    for grp in ("gates", "performance", "cost"):
        print(f"[{grp}]")
        for k, v in card[grp].items():
            print(f"  {k}: {v if not isinstance(v, list) else (len(v), v[:6])}")
    if a.json:
        Path(a.json).write_text(json.dumps(card, indent=1))
    if a.compare:
        ok, reasons, cheaper, better = compare(card, jload(a.compare))
        print(("ACCEPT" if ok else "REJECT") + f" vs {a.compare}: cheaper {cheaper}, better {better}"
              + ("" if ok else "; " + "; ".join(reasons)))
        raise SystemExit(0 if ok else 1)
    raise SystemExit(0 if all(card["gates"].values()) else 1)


main()
