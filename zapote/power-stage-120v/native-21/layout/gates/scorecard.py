#!/usr/bin/env python3
"""Benchmark scorecard for a native-21 candidate board (stage 19c onward).

    python3 scorecard.py TAG BUILDDIR [--bom BOM.csv] [--stock STOCK.csv] [--json OUT.json]
                         [--audit PASS|FAIL] [--compare BENCH.json] [--strict-basis]
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
  Buildability (added 2026-10-15, sourcing study; --snapshot, a SNAPSHOT-*.csv from build_snapshot.py): lines no single
  source holds for 5 / 500 boards, the share JLC can place from its own stock or via Global Sourcing, consign-only lines,
  and the build lead (max factory lead among lines short everywhere). A snapshot is dated: re-take it before comparing.
  Price basis v2 (added for OPEN-ITEMS C8, gates/bom_pricing.py): parts_usd_at_5_v2 / parts_usd_at_500_v2 price every line
  from the best dated read (JLC ladder at the true lot quantity, then authorised distributor, then survey read) and take a
  class-default estimate only where no read exists (price_estimated_lines). The legacy parts_usd_at_5 / _500 keep their
  2026-10-13 stock-survey meaning (58 of 94 lines were estimates there) so old cards stay comparable; --compare uses the v2
  keys when both cards carry the same price_basis, otherwise it compares the legacy keys and says so (--strict-basis: refuse).

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
    # 2026-10-15 (thermal-ratings audit): the legacy single-cell B3 peaks (b3_c28_h25_peak_C, b3_nominal_h10_peak_C) stay
    # on the card for reference but are no longer compared: they are point-deposit artefacts that move 50-80 K with the
    # mesh (b3-convergence README section 1). Compared instead: margins of the body-level model to the laminate's UL
    # temperature and to the hot parts' datasheet limits at the declared basis (b3-ratings/b3_ratings_gate.py).
    "b3_laminate_margin_K": ("higher", 1.0),
    "b3_rated_part_margin_K": ("higher", 1.0),
    # added 2026-10-15 (after DECISIONS 55): worst gated margin at the release case (c17.5_h10 since DECISIONS 61, c18_h10 before: the release ceiling's
    # 1.05 x trip, bay 61 C, still air, I_line 13.5 A) - the margin behind the b3_ratings release gate, ratcheted like the
    # two above (which stay on c22 / c28 at bay 55 C so cards remain comparable). Cards before s42's re-score lack it and
    # are skipped by compare().
    "b3_release_margin_K": ("higher", 1.0),
    "emi_min_margin_dB": ("higher", 0.5),
    "leakage_touch_mA": ("lower", 0.0),
    "cmti_gate_ratio_min": ("higher", 0.0),
    "fuse_copper_fusing_ratio": ("higher", 0.0),
    "bank_ratio_tdk_28A_40k": ("lower", 0.0),     # added 2026-10-13 (stage 20): DECISIONS item 21 / 23 thermal margin
    "bank_ratio_tdk_28A_35k": ("lower", 0.0),     # added 2026-10-14: DECISIONS 37, worst legal frequency (c34-bank-margin)
    # PROPOSED (bank28): the bank's 28 A metric becomes a physical self-heating check in the 0.5 mm-gap column under the
    # DECLARED airflow (DECISIONS 66 design flow): sqrt(dT_column / (dT_lim F_T(T_A)^2)), TDK GTI p.25 / p.27 / p.30 and
    # the family pages, conservative correlation. <= 1.00 meets TDK's own limit. The two vendor-curve ratios above stay
    # as informational (an isolated part in still air at T_A 85 C).
    "bank_air_ratio_28A_35k": ("lower", 0.0),
    "ocp_pickup_stack_pan60_A": ("lower", 0.1),   # added 2026-10-13 (stage 21b): F8, any-phase +50 % stack, gate 6.5 A
    # added 2026-10-13 (after stage 26): datasheet-ratings ledger (native-21/verification/datasheet-ledger) as a ratchet - a
    # candidate may not add a rating violation, a BOM line missing from the ledger, or an unaudited SAFETY/POWER line
    "ledger_violations": ("lower", 0),
    "ledger_unaudited_safety_power": ("lower", 0),
    # added 2026-10-15 (DECISIONS 43): track-geometry hygiene (gates/track_geometry.py). Acute corners and fold-backs are
    # defects (strict ratchet); right angles and any-angle length are tracked with a small allowance for new routes
    "track_acute_corners": ("lower", 0),
    "track_fold_backs": ("lower", 0),
    "track_right_angle_corners": ("lower", 5),
    "track_any_angle_mm": ("lower", 25.0),
}


def jload(p):
    p = Path(p)
    return json.loads(p.read_text()) if p.exists() else None


def b3_ratings(b):
    """b3-ratings/margins.json (b3_ratings_gate.py via run_basis.py), only if every case was solved on this build's board."""
    br = jload(VR / "04-board-current-thermal/round5-native21/b3-ratings/margins.json")
    sha = (jload(b / "barrier-gate-rust.json") or {}).get("board_sha256")
    if not br or not sha or set((br.get("board_sha256") or {}).values()) != {sha}:
        return None
    return br


# Release gates: absolute pass / fail at the declared basis. Reported on the card, but not part of the candidate-vs-
# benchmark rule while the benchmark itself fails them; their margins are ratcheted in PERF instead (DECISIONS 46).
# b3_ratings is decided on the release case alone since 2026-10-15 (c17.5_h10 at bay 61 C since DECISIONS 61, b3_ratings_gate.BASIS).
# pin_absmax (gates/pin_absmax.py) joined 2026-10-15 with the four TPS70950 EN violations on the benchmark itself and sat here
# until stage 48 (c48-ldo-en-ref-watch) fixed them; pin_absmax_expected.json is empty since, so from s48 on `pin_absmax` is an
# ordinary gate: a candidate with any pin over its absolute maximum is rejected.
RELEASE_GATES = {"b3_ratings"}
# OCP low-corner floor since stage 15 (28 A ceiling): 59.17 A envelope peak + 3.0 A coil-pickup stack (DECISIONS
# item 9) + 2 A margin; kelvin_budget.py FLOOR carries the same figure per tag.
KELVIN_FLOOR_MIN_A = 64.17


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
    ct = jload(b / "cu-temp-basis.json")           # gates/cu_temp_basis.py, written by chain.sh (S17); older builds lack it
    if ct:
        g["cu_temp_basis"] = not ct["errors"]
        src["cu_temp_basis"] = str(b / "cu-temp-basis.json")
    pa = jload(b / "pin-absmax.json")              # gates/pin_absmax.py, written by chain.sh; older builds lack it
    if pa:
        g["pin_absmax"] = not pa["failures"] and not pa["errors"]       # True only with no failure at all, expected or not
        src["pin_absmax"] = str(b / "pin-absmax.json")
    d5 = jload(UNIT / "native-21/verification/d5-audit.json")
    if d5:
        g["d5"] = bool(d5["verdict_pcb"])
    fit = jload(UNIT / "validation-plan/enclosure-fit/native21-body-collisions.json")
    r4 = jload(UNIT / "validation-plan/enclosure-fit/native21-in-r4.json")
    if fit and r4:
        g["enclosure_fit"] = fit.get("unattributed", 1) == 0 and not fit.get("part_overlaps") and not r4.get("hits")
    # jet strip: nothing over 4 mm under the airflow jet box (OPEN-ITEMS S2; jet_strip_height.py)
    js = jload(UNIT / "validation-plan/enclosure-fit/native21-jet-strip.json")
    if js:
        g["jet_strip_height"] = js["pass"]
    if audit:
        g["audit_rs"] = audit == "PASS"
    # OCP Kelvin floor (RETURN-PATHS.md S2): the band's low corner after the Kelvin shift must clear the floor at the
    # bound. kelvin_budget.py falls back to the pre-stage-15 44 A floor for a tag missing from its FLOOR table, so the
    # floor itself is held to the stage-15 basis too. Budgets from before stage 15 carry no verdict and are skipped.
    kb = jload(VR / f"02-protection-timing/kelvin/budget-{tag}.json")
    if kb and "meets_floor_at_bound" in kb:
        g["kelvin_floor"] = bool(kb["meets_floor_at_bound"]) and kb.get("floor_A", 0) >= KELVIN_FLOOR_MIN_A
    # B3 ratings gate: laminate (KB-6164 UL MOT 130 C) and datasheet-limited parts at the release case (c17.5_h10: the
    # 18.0 A release ceiling of DECISIONS 55 at its 1.05 x trip, still air h 10, bay 61 C, I_line 13.5 A); every gated
    # row must pass there. The file is written by b3-ratings/b3_ratings_gate.py --out (via run_basis.py). margins.json
    # files from before 2026-10-15 have no release case; their pass is over c22 / c28 at bay 55.
    br = b3_ratings(b)
    if br:
        g["b3_ratings"] = bool(br["pass"])
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
            # stage 33: same-net stitches (six layers) are judged like reference changes (return_path19)
            for c in s["reference_changes"] + s.get("stitches", []):
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
    br = b3_ratings(b)
    if br:
        m["b3_laminate_margin_K"] = br["metrics"]["b3_laminate_margin_K"]
        m["b3_rated_part_margin_K"] = br["metrics"]["b3_rated_part_margin_K"]
        if br["metrics"].get("b3_release_margin_K") is not None:
            m["b3_release_margin_K"] = br["metrics"]["b3_release_margin_K"]
        src["b3_ratings"] = (f"04-board-current-thermal/round5-native21/b3-ratings/margins.json {br['basis']} "
                             f"worst {br['metrics']['worst_gated']}"
                             + (f"; release worst {br['metrics']['release_worst_gated']}"
                                if br["metrics"].get("release_worst_gated") else ""))
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
    bank_mpn = None
    for r in csv.DictReader(open(FAB / "bom-jlcpcb.csv")):
        if r["Manufacturer Part Number"].startswith(("B32654A1104", "B32643B8104")) and "C21" in r["Designator"]:
            bank_mpn = r["Manufacturer Part Number"]
    if bo:
        grade = None
        if bank_mpn and bank_mpn.startswith("B32654A1104"):
            grade = bank_mpn[-4]                                   # K or J
        if grade in ("K", "J"):
            m["bank_ratio_tdk_28A_40k"] = bo["baseline"][{"K": "5x100nF_K(+-10%)", "J": "5x100nF_J(+-5%)"}[grade]]["ratio_to_curve_28A_40k"]
            src["bank"] = f"11-candidates/g04-g09-tank-detect/results/bank_options.json baseline {grade}"
        # same, at the 35 kHz window floor, the worst legal frequency for every TDK 1600 V curve (DECISIONS 37)
        bm = jload(VR / "11-candidates/c34-bank-margin/results/bank_margin.json")
        if bm and grade in ("K", "J"):
            m["bank_ratio_tdk_28A_35k"] = bm["basis_comparison"][f"{grade}_at_35k"]
            src["bank_35k"] = f"11-candidates/c34-bank-margin/results/bank_margin.json basis_comparison {grade}_at_35k"
    # PROPOSED (bank28): candidate 34's bank (5 x B32643B8104J000) on the vendor curve, from the same c34 table
    bm = jload(VR / "11-candidates/c34-bank-margin/results/bank_margin.json")
    if bm and bank_mpn and bank_mpn.startswith("B32643B8104"):
        row = next((b for b in bm["banks"] if b.get("bank", "").startswith("5 x B32643B8104J")), None)
        if row:
            m["bank_ratio_tdk_28A_40k"] = row["ratio_40k"]
            m["bank_ratio_tdk_28A_35k"] = row["ratio_35k"]
            src["bank"] = src["bank_35k"] = "11-candidates/c34-bank-margin/results/bank_margin.json banks '5 x B32643B8104J'"
    # PROPOSED (bank28): physical check under the declared airflow, by the fitted MPN (producer bank_air_metric.py)
    ba = jload(VR / "11-candidates/bank28-air/results/bank_air_metric.json")
    if ba and bank_mpn and bank_mpn in ba["by_mpn"]:
        r = ba["by_mpn"][bank_mpn]
        m["bank_air_ratio_28A_35k"] = r["bank_air_ratio_28A_35k"]
        src["bank_air"] = (f"11-candidates/bank28-air/results/bank_air_metric.json {bank_mpn} (declared {ba['declared_set']}; "
                           f"pads from B3 runs on board {str(r.get('board_sha256_of_pad_runs'))[:8]})")
    # F8 coil-field pickup into the OCP Kelvin / comparator loops: 60 kHz, 59.2 A pk, pan, conservative closure (base_A),
    # one script (02-protection-timing/coil-pickup/s21b/run_ocp.py) run on each stage's copper
    pk = jload(VR / f"02-protection-timing/coil-pickup/s21b/result-{tag.replace('native21', '')}.json")
    if pk:
        m["ocp_pickup_stack_pan60_A"] = round(pk["rows"]["f60|pan_bars_31kHz_45Apk|base_A|cluster_drawn"]["stack_any_phase_x1p5_A"], 2)
        src["ocp_pickup"] = f"02-protection-timing/coil-pickup/s21b/result-{tag.replace('native21', '')}.json"
    # datasheet-ratings ledger against the frozen BOM (the gate exits 1 while J1 / F2 are open: the counts are the metric)
    led = UNIT / "native-21/verification/datasheet-ledger"
    if (led / "gate.py").exists():
        import subprocess, tempfile
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(["python3", "-I", str(led / "gate.py"), "--report", f"{td}/r.json"], capture_output=True)
            r = json.loads(Path(f"{td}/r.json").read_text())
        if r.get("errors"):
            raise SystemExit(f"datasheet ledger errors: {r['errors'][:3]}")
        m["ledger_violations"] = len(r["violations"])
        m["ledger_unaudited_safety_power"] = len(r["unaudited_safety_power"]) + len(r["missing_from_ledger"])
        src["ledger"] = f"native-21/verification/datasheet-ledger: {r['totals']}"
    ex = b / "native21-all-copper.json.gz"
    if ex.exists():
        import importlib.util
        spec = importlib.util.spec_from_file_location("track_geometry", Path(__file__).resolve().parent / "track_geometry.py")
        tg = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tg)
        geo = tg.measure(tg.load(ex))
        m["track_acute_corners"], m["track_fold_backs"] = geo["acute_corners"], geo["fold_backs"]
        m["track_right_angle_corners"], m["track_any_angle_mm"] = geo["right_angle_corners"], geo["any_angle_mm"]
        src["track_geometry"] = "gates/track_geometry.py on BUILDDIR/native21-all-copper.json.gz"
    return m, src


def _bom_pricing():
    import importlib.util
    spec = importlib.util.spec_from_file_location("bom_pricing", Path(__file__).resolve().parent / "bom_pricing.py")
    bp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bp)
    return bp


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
    # r2-dfm P4: hand_or_consign_lines counts every THT line, so a THT line moved to JLC assembly never shows; this one
    # counts only lines with no LCSC code (consigned or hand-sourced whatever the mount)
    c["consign_lines"] = sum(not r.get("LCSC Part #", "").strip() for r in rows)
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
    # price basis v2 (C8): best dated read per line, estimate only where none exists; independent of the legacy stock survey
    bp = _bom_pricing()
    c.update(bp.card_fields(bp.price_bom(bom_path, bp.load_reads())))
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


def _bom_tier(r, n):
    """jlc: JLC library + JLC stock >= need; global: one authorised distributor holds need (JLC Global Sourcing);
    consign: stock exists only split / at brokers; short: no source. Same rule as sourcing/scripts/buildability.py."""
    need = int(r["qty_per_board"]) * n
    js, ab = float(r["jlc_stock"] or 0), float(r["auth_best_stock"] or 0)
    if r["jlc_library"] in ("basic", "extended") and js >= need:
        return "jlc"
    if ab >= need:
        return "global"
    tot = js + float(r["auth_total_stock"] or 0) + float(r.get("unauth_max_stock") or 0)
    return "consign" if tot >= need else "short"


def buildability(bom_path, snap_path):
    """Lines of BOM joined by MPN to the snapshot; a BOM line the snapshot lacks counts as short with unknown lead."""
    if not snap_path or not Path(snap_path).exists():
        return {}
    snap = {r["mpn"].strip(): r for r in csv.DictReader(open(snap_path))}
    rows = list(csv.DictReader(open(bom_path)))
    b = {}
    for n in (5, 500):
        tiers, leads, unknown = [], [], 0
        for r in rows:
            s = snap.get(r["Manufacturer Part Number"].strip())
            t = _bom_tier(s, n) if s else "short"
            tiers.append(t)
            if t == "short":
                lw = (s or {}).get("factory_lead_wk", "")
                if lw in ("", None):
                    unknown += 1
                else:
                    leads.append(float(lw))
        b[f"lines_short_for_{n}"] = sum(t in ("short", "consign") for t in tiers)
        b[f"jlc_assemblable_share_{n}"] = round(sum(t in ("jlc", "global") for t in tiers) / len(rows), 3)
        b[f"consign_lines_{n}"] = sum(t == "consign" for t in tiers)
        b[f"build_lead_wk_{n}"] = max(leads) if leads else 0
        b[f"short_lead_unknown_{n}"] = unknown
    return b


def _parts_key(ca, cb, notes, reasons, strict):
    """The parts-cost key to compare: v2 only when both cards carry it on the same price_basis. A card on the new basis
    against an old-basis benchmark (or the reverse) falls back to the legacy keys and says so; strict refuses."""
    v2 = "parts_usd_at_500_v2"
    if v2 in ca and v2 in cb and ca.get("price_basis") == cb.get("price_basis"):
        return v2
    if v2 in ca or v2 in cb:
        why = (f"price basis differs: card {ca.get('price_basis', 'legacy 2026-10-13 stock survey')} vs benchmark "
               f"{cb.get('price_basis', 'legacy 2026-10-13 stock survey')}")
        if strict:
            reasons.append(why + "; parts cost not comparable (--strict-basis); re-score the benchmark with bom_pricing.py")
        else:
            notes.append(why + ": parts cost compared on the LEGACY parts_usd_at_500 (class-default estimates on most lines); "
                         "the v2 totals are not compared")
    return "parts_usd_at_500"


def compare(cur, bench, notes=None, strict_basis=False):
    reasons, better = [], []
    notes = [] if notes is None else notes
    for k, ok in cur["gates"].items():
        if not ok and k not in RELEASE_GATES:
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
    pk = _parts_key(ca, cb, notes, reasons, strict_basis)
    cheaper = [k for k in (pk, "bom_lines", "placements", "jlc_extended_lines", "hand_or_consign_lines",
                           "consign_lines", "zero_stock_lines", "lines_short_for_500", "lines_short_for_5", "build_lead_wk_500")
               if k in ca and k in cb and ca[k] < cb[k]]
    dearer = [k for k in (pk, "bom_lines", "jlc_extended_lines", "hand_or_consign_lines", "consign_lines",
                          "lines_short_for_500", "lines_short_for_5", "build_lead_wk_500")
              if k in ca and k in cb and ca[k] > cb[k]]
    for k in ("jlc_assemblable_share_500", "jlc_assemblable_share_5"):     # higher is better
        if k in ca and k in cb:
            (cheaper if ca[k] > cb[k] else dearer if ca[k] < cb[k] else []).append(k)
    if dearer and not better:
        reasons.append(f"costlier on {dearer} with no performance gain")
    if not cheaper and not better:
        reasons.append("neither cheaper/simpler nor better than the benchmark")
    return (not reasons), reasons, cheaper, better


def bench_card(path):
    """A benchmark card must come from the full chain: a scoped card (gates/scoped, key "scoped") is never a benchmark."""
    c = jload(path)
    if c is None:
        raise SystemExit(f"{path}: no such card")
    if "scoped" in c:
        raise SystemExit(f"{path} is a scoped card ({c['scoped'].get('mode')}); benchmarks come from the full chain.sh")
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tag", nargs="?")
    ap.add_argument("build", nargs="?")
    ap.add_argument("--card", help="a saved scorecard to compare instead of computing one")
    ap.add_argument("--bom", default=str(FAB / "bom-jlcpcb.csv"))
    ap.add_argument("--stock", default=",".join(str(p) for p in sorted((VR / "08-manufacturing-package/native-21/sourcing").glob("STOCK-2026-10-13*.csv"))),
                    help="comma-separated stock CSVs; addenda (STOCK-2026-10-13-addendum-*.csv) add rows for new MPNs")
    snaps = sorted((VR / "08-manufacturing-package/native-21/sourcing").glob("SNAPSHOT-*.csv"))
    ap.add_argument("--snapshot", default=str(snaps[-1]) if snaps else "",
                    help="dated stock snapshot (build_snapshot.py) for the buildability metrics; latest by name")
    ap.add_argument("--audit")
    ap.add_argument("--json")
    ap.add_argument("--compare")
    ap.add_argument("--strict-basis", action="store_true",
                    help="refuse (REJECT) when the card and the benchmark are on different parts-price bases")
    a = ap.parse_args()
    if a.card:
        card = jload(a.card)
        notes = []
        ok, reasons, cheaper, better = compare(card, bench_card(a.compare), notes, a.strict_basis)
        for n in notes:
            print("NOTE: " + n)
        sc = card.get("scoped")
        if sc and sc.get("stale"):        # a scoped card with stale entries cannot be accepted yet
            ok = False
            reasons.append("scoped card not final, stale: " + ", ".join(sorted(sc["stale"])))
        print(("ACCEPT" if ok else "REJECT") + f" {card['tag']} vs {a.compare}: cheaper {cheaper}, better {better}"
              + ("" if ok else "; " + "; ".join(reasons))
              + (f" [scoped {sc.get('mode')}: {len(sc.get('reused', {}))} entries reused by key; full chain still due at merge]" if sc else ""))
        raise SystemExit(0 if ok else 1)
    b = Path(a.build)
    perf, src = performance(b, a.tag)
    card = {"tag": a.tag, "build": str(b), "board_sha256": (jload(b / "barrier-gate-rust.json") or {}).get("board_sha256"),
            "gates": gates(b, a.tag, a.audit), "performance": perf, "cost": cost(b, Path(a.bom), a.stock),
            "sources": src}
    card["cost"].update(buildability(Path(a.bom), a.snapshot))
    card["sources"]["bom_pricing"] = ("gates/bom_pricing.py " + card["cost"]["price_basis"] + " over the 2026-10-15 JLC / DigiKey / "
                                      "Octopart snapshots and the STOCK-2026-10-13*.csv survey reads (sourcing/)")
    if a.snapshot:
        sp = Path(a.snapshot).resolve()
        card["sources"]["buildability"] = str(sp.relative_to(UNIT)) if sp.is_relative_to(UNIT) else str(sp)
    for grp in ("gates", "performance", "cost"):
        print(f"[{grp}]")
        for k, v in card[grp].items():
            print(f"  {k}: {v if not isinstance(v, list) else (len(v), v[:6])}")
    if a.json:
        Path(a.json).write_text(json.dumps(card, indent=1))
    if a.compare:
        notes = []
        ok, reasons, cheaper, better = compare(card, bench_card(a.compare), notes, a.strict_basis)
        for n in notes:
            print("NOTE: " + n)
        print(("ACCEPT" if ok else "REJECT") + f" vs {a.compare}: cheaper {cheaper}, better {better}"
              + ("" if ok else "; " + "; ".join(reasons)))
        raise SystemExit(0 if ok else 1)
    raise SystemExit(0 if all(card["gates"].values()) else 1)


main()
