#!/usr/bin/env python3
"""c54-ct-band: the tank-CT comparator band against the firmware peak trip (OPEN-ITEMS S29), native-21 stage 53.

    python3 -I scripts/ct_band.py            # writes results/ct_band.json and results/ct_band.md
    python3 -I scripts/ct_band.py --check    # exit 1 if the committed results differ from a fresh run

Read-only on the repository. Inputs (all committed):
  - frozen BOM / netlist: zapote/power-stage-120v/native-21/frozen (via firmware/tools/commissioning_board_table.py,
    the generator of COMMISSIONING.md B9 / B17, so the part set is the one the procedure uses)
  - the round-3 threshold engine: validation-results/02-protection-timing/round3/thresholds.py (exact_corners)
  - the s53 B3 BASIS run files (board 82af7bd9, chain d0095b17e): .../round5-native21/b3-ratings/runs/<case>_p0p{25,5}.json
    and the B3 ratings gate's estimator (b3_ratings_gate.est, BASIS bays)
  - firmware constants: firmware/components/power/include/tank_freq.h, n21_signal.h
  - round-6 envelope peaks (board-side-protection.csv), kelvin_budget.py FLOOR

Datasheet limits used (page = printed page):
  TLV3201 (TI SBOS561C, May 2024; round3/sources/tlv3201.pdf): VIO +/-4 mV over -40..125 C at VCM = VCC/2, p.5 (6.5) and
      p.6 (6.7); IIB 5 nA max over -40..125 C, p.5/p.6; CMRR >= 56 dB (VCC 2.7 V, p.6) / 60 dB (VCC 5 V, p.5); input
      hysteresis 1.2 mV typ (no max), p.5/p.6.
  RC1206 (Yageo RC1206 V.2, 2004; 05-resonant-tank-envelope/sources/rc1206.pdf) p.4: R <= 10 ohm +/-200 ppm/C (R39).
  RT0603BRD07 (Yageo RT, 'B' 0.1 %, 'D' +/-25 ppm/C; round3/sources/README.md row, page not re-read here): R40-R46.
  BAS116H (Nexperia Rev. 3, Table 7): 80 nA max reverse at Tj 150 C -> +/-80 uV on R42 1 k (the engine's clamp term).
  ESP32-S3 Series Datasheet v2.2, p.66 Table 5-6: ADC total error ATTEN3 (0-2900 mV) +/-50 mV (25 C, DC, 100 nF).
  TPS62933 (TI SLUSEA4D, Aug 2022) p.6: VFB 792-808 mV at TJ 25 C, 788-812 mV at TJ 0-85 C (controller v3v3 buck).
"""
from __future__ import annotations

import argparse
import importlib.util
import itertools
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
PS = STUDY.parents[2]                       # zapote/power-stage-120v
REPO = PS.parents[1]
VR = PS / "validation-results"
CBT_PATH = REPO / "firmware/tools/commissioning_board_table.py"
THR_PATH = VR / "02-protection-timing/round3/thresholds.py"
B3R = VR / "04-board-current-thermal/round5-native21/b3-ratings"
GATE_PATH = B3R / "b3_ratings_gate.py"
RUNS = B3R / "runs"
TEMP_RATINGS = B3R / "temp-ratings-2026-10-15/results.json"
KELVIN = VR / "02-protection-timing/kelvin/kelvin_budget.py"
TANK_FREQ_H = REPO / "firmware/components/power/include/tank_freq.h"
N21_SIGNAL_H = REPO / "firmware/components/power/include/n21_signal.h"
PADS = PS / "native-21/layout/pads.json"
OUT_JSON = STUDY / "results/ct_band.json"
OUT_MD = STUDY / "results/ct_band.md"

# ---- datasheet constants (see the docstring for pages)
TLV_VOS = 0.004             # V, -40..125 C, VCM = VCC/2
TLV_IB = 5e-9               # A per input, -40..125 C
TLV_CMRR_DB = 56.0          # the worse of the two supply tables
TLV_HYST_TYP = 1.2e-3       # V typ, no max: reported on the high corner only (it raises a rising trip)
CLAMP_V = 80e-6             # BAS116H leakage x R42 (the engine's term)
HOST_LOAD_A = 0.35e-6       # controller ct_mon follower 10 MOhm to 0 V (tools/ct_detector bound) through R42 1 k
R42_OHM = 1000.0
ADC_ERR_V = 0.050           # ESP32-S3 v2.2 p.66 Table 5-6, ATTEN3
VFB_25 = (0.792, 0.808)     # TPS62933 p.6, TJ 25 C
VFB_0_85 = (0.788, 0.812)   # TPS62933 p.6, TJ 0..85 C
V3V3_CTRL = (3.242, 3.367)  # zapote/controller/tools/controller_calcs.py rail_3v3 band (what J4.3 delivers)
V3V3_CONTRACT = (3.135, 3.465)
RT_TOL, RT_TCR = 0.001, 25e-6
T_COLD = -10.0              # the B9 basis cold end
RTH_0603_K_W = 46.3         # derived as thermal_body chip1206: 0.8 mm / (2 x 24 W/mK x 0.8 mm x 0.45 mm)
C_BANK_MIN = 5 * 0.1e-6 * 0.95
F_MIN_HZ = 35e3
VC_BANK_V = 1500.0          # ledger B32643H8104J000: VC at Top,max (TDK B3264*H June 2026 p.15)
ID_PULSE_A = 495.0          # ledger IPW65R018CFD7 Table 2 p.3
TLV_VCM_TOP = 0.2           # VCM <= VCC + 0.2 V (SBOS561C p.5 / p.6)

CT_REFS = ("R39", "R40", "R41", "R43", "R44", "R45", "R46")
POL_PARTS = {"pos": ("R39", "R40", "R41", "R43", "R44"), "neg": ("R39", "R40", "R41", "R45", "R46")}


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cbt = load("cbt_c54", CBT_PATH)
thr = load("thr_c54", THR_PATH)
gate = load("gate_c54", GATE_PATH)
kb = load("kb_c54", KELVIN)


def h_define(path: Path, name: str) -> float:
    return cbt.c_define(path, name)


# ------------------------------------------------------------------------------------------------ parts (as B9)

def board_parts() -> tuple[dict, dict, int]:
    """Configure thr.PARTS exactly as commissioning_board_table.render() does; return (bom, ohm, CT ratio)."""
    rec = cbt.board_of_record()
    facts = cbt.STAGE_FACTS[rec["stage"]]
    bom, _nets = cbt.load_board()
    ohm = {d: cbt.mpn_ohms(p) for d, p in bom.items()}
    over = {r: bom[r] for r in ("R5", "R32", "R33", "R34", "R35", "R39", "R43", "R46")}
    thr.validate_inputs(overrides=over)
    for r in ("R30", "R32", "R33", "R34", "R35", "R36", "R37", "R40", "R41", "R43", "R44", "R45", "R46"):
        assert bom[r].startswith("RT0603BRD07"), (r, bom[r])
        thr.PARTS[r] = (ohm[r], RT_TOL, RT_TCR)
    for r in ("R26", "R27", "R28", "R29"):
        thr.PARTS[r] = (ohm[r], *thr.PARTS[r][1:])
    thr.PARTS["R5"] = thr.SHUNT_CSS2H
    ratio = facts["ct_ratio"][bom["T1"]]
    thr.PARTS["R39"] = (ohm["R39"] * 100.0 / ratio, *thr.PARTS["R39"][1:])
    return bom, ohm, ratio, rec, facts


# ------------------------------------------------------------------------------------------------ corner engine

def limits(parts: dict, temps: dict) -> dict:
    """Adverse tolerance x |TCR (T - 25)| per part at its own temperature (thresholds.corner_values, per part)."""
    out = {}
    for name in CT_REFS:
        nom, tol, tcr = parts[name]
        drift = tcr * abs(temps[name] - 25.0)
        out[name] = (nom * (1 - tol) * (1 - drift), nom * (1 + tol) * (1 + drift))
    return out


def ct_corners(parts: dict, temps: dict, extended: bool, v3v3=V3V3_CONTRACT) -> dict:
    """Exact vertex enumeration of the CT trip, both polarities, as thresholds.exact_corners (index 1 / 2).

    Returns, per polarity, min / max of the trip in primary amps (true gain R39 / 100, engine scaling) and of the
    gain-free threshold swing in volts at ct_sense_mon relative to the bias node (the quantity the firmware's CT_MON
    reading is compared in, so R39 / T1 cancel). extended adds, aligned adverse: TLV3201 CMRR at the actual common
    mode, two more comparator inputs (U11 / U12) on the sense node through R42, and the controller follower load.
    """
    lim = limits(parts, temps)
    res = {}
    for pol, names in POL_PARTS.items():
        idx = 1 if pol == "pos" else 2
        best = {"a_min": (math.inf, None), "a_max": (-math.inf, None), "v_min": (math.inf, None), "v_max": (-math.inf, None)}
        for bits in itertools.product((0, 1), repeat=len(names)):
            p = {k: v[0] for k, v in parts.items()}
            p.update({n: lim[n][b] for n, b in zip(names, bits)})
            ibv = thr.input_bias_v(p, idx)
            for rail, vos, ibs, clamp, ext_s in itertools.product(
                    v3v3, (-TLV_VOS, TLV_VOS), (-1, 1), (-CLAMP_V, CLAMP_V), ((-1, 1) if extended else (0,))):
                bias = rail * p["R41"] / (p["R40"] + p["R41"])
                hi = rail * p["R44"] / (p["R43"] + p["R44"])
                lo = rail * p["R46"] / (p["R45"] + p["R46"])
                vref = hi if pol == "pos" else lo
                ext = 0.0
                if extended:
                    cmrr = abs(vref - rail / 2) * 10 ** (-TLV_CMRR_DB / 20)
                    ext = ext_s * (cmrr + 2 * TLV_IB * (R42_OHM + p["R39"]) + HOST_LOAD_A * R42_OHM)
                swing = (hi - bias) if pol == "pos" else (bias - lo)
                v = swing + vos + ibs * ibv + clamp + ext
                a = v / (p["R39"] / 100.0)
                case = {"bits": dict(zip(names, bits)), "v3v3": rail, "vos": vos, "ib": ibs * ibv, "clamp": clamp, "ext": ext}
                for key, val in (("a_min", a), ("v_min", v)):
                    if val < best[key][0]:
                        best[key] = (val, case)
                for key, val in (("a_max", a), ("v_max", v)):
                    if val > best[key][0]:
                        best[key] = (val, case)
        res[pol] = {k: v[0] for k, v in best.items()}
        res[pol]["a_min_corner"] = best["a_min"][1]
    return res


def band(parts: dict, temp_sets: list[dict], extended: bool) -> dict:
    """Band over several temperature sets (e.g. hot per-part and cold uniform): min of mins, max of maxes."""
    rs = [ct_corners(parts, t, extended) for t in temp_sets]
    out = {}
    for pol in ("pos", "neg"):
        out[pol] = {"a_min": min(r[pol]["a_min"] for r in rs), "a_max": max(r[pol]["a_max"] for r in rs),
                    "v_min": min(r[pol]["v_min"] for r in rs), "v_max": max(r[pol]["v_max"] for r in rs)}
    out["a_low"] = min(out[p]["a_min"] for p in ("pos", "neg"))
    out["a_high"] = max(out[p]["a_max"] for p in ("pos", "neg"))
    out["v_low"] = min(out[p]["v_min"] for p in ("pos", "neg"))
    out["v_high"] = max(out[p]["v_max"] for p in ("pos", "neg"))
    return out


def uniform(t: float) -> dict:
    return {r: t for r in CT_REFS}


# ------------------------------------------------------------------------------------------------ B3 temperatures

def ct_self_heat_w(v3v3_max: float, parts: dict) -> dict:
    """Worst static dissipation of each reference-network resistor at the v3v3 contract top."""
    p = {k: v[0] for k, v in parts.items()}
    bias = p["R40"] + p["R41"]
    hi = p["R43"] + p["R44"]
    lo = p["R45"] + p["R46"]
    i_b, i_h, i_l = v3v3_max / bias, v3v3_max / hi, v3v3_max / lo
    return {"R40": i_b ** 2 * p["R40"], "R41": i_b ** 2 * p["R41"], "R43": i_h ** 2 * p["R43"],
            "R44": i_h ** 2 * p["R44"], "R45": i_l ** 2 * p["R45"], "R46": i_l ** 2 * p["R46"]}


def b3_temps(board_sha: str, parts: dict) -> dict:
    """Per case: each CT part's B3 estimate on the s53 run files, with the gate's estimator and BASIS bay.
    R39: its body-model element (tj_c, the only CT part with a heat row). R40-R46: pad-copper probe max + P x Rth."""
    sh = ct_self_heat_w(V3V3_CONTRACT[1], parts)
    out = {}
    for case, basis in gate.BASIS.items():
        r25 = json.loads((RUNS / f"{case}_p0p25.json").read_text())
        r05 = json.loads((RUNS / f"{case}_p0p5.json").read_text())
        for r in (r25, r05):
            if r["board_sha256"] != board_sha:
                raise SystemExit(f"{case}: run file board {r['board_sha256'][:12]} is not the board of record {board_sha[:12]}")
            if r.get("copper_temp_model", {}).get("model") != "hot-iterated":
                raise SystemExit(f"{case}: run file is not on the hot-copper basis")
        bay = basis["bay_c"]
        if {r25.get("bay_c"), r05.get("bay_c")} != {bay}:
            raise SystemExit(f"{case}: run files solved at bay {r25.get('bay_c')} / {r05.get('bay_c')}, BASIS {bay}")
        row = {}
        p25 = {p["ref"]: p for p in r25["parts"]}
        p05 = {p["ref"]: p for p in r05["parts"]}
        row["R39"] = {"est_c": gate.est(p25["R39"]["tj_c"], p05["R39"]["tj_c"], bay), "what": "body element (heat row)",
                      "heat_w": p25["R39"]["watts_into_model"]}
        for ref in CT_REFS[1:]:
            pad = gate.est(r25["probes"][ref]["pad_max_cell_c"], r05["probes"][ref]["pad_max_cell_c"], bay)
            row[ref] = {"est_c": pad + sh[ref] * RTH_0603_K_W, "pad_c": pad, "self_heat_k": sh[ref] * RTH_0603_K_W,
                        "what": "pad-copper probe + P x Rth(0603)"}
        for ref in ("U10", "U11", "T1", "R42"):
            row[ref] = {"est_c": gate.est(r25["probes"][ref]["pad_max_cell_c"], r05["probes"][ref]["pad_max_cell_c"], bay),
                        "what": "pad-copper probe"}
        out[case] = {"bay_c": bay, "rows": row,
                     "laminate_peak_c": gate.est(r25["peak_1mm_block"]["temperature_c"], r05["peak_1mm_block"]["temperature_c"], bay),
                     "probes": {ref: gate.est(r25["probes"][ref]["pad_max_cell_c"], r05["probes"][ref]["pad_max_cell_c"], bay)
                                for ref in r25["probes"] if ref in r05["probes"]}}
    return out


def s52_crosscheck(b3: dict) -> dict:
    """The temp-ratings-2026-10-15 study (s52 run files, board 5e7c12c1): same estimator; s53 moved no part."""
    d = json.loads(TEMP_RATINGS.read_text())
    s52 = {}
    for line in d["lines"]:
        for p in line["per_ref"]:
            if p["ref"] in CT_REFS:
                s52[p["ref"]] = {c: (v.get("body_c") or v["est_c"]) if p["ref"] != "R39" else v.get("body_c", v["est_c"])
                                 for c, v in p["cases"].items()}
    diffs = {}
    for ref in CT_REFS[1:]:
        for c in b3:
            if ref in s52 and c in s52[ref]:
                diffs[f"{ref}@{c}"] = round(b3[c]["rows"][ref]["pad_c"] - s52[ref][c], 2)
    return {"s52_board": d["equivalence"]["run_board_sha256"], "max_abs_pad_diff_k": max(abs(v) for v in diffs.values()),
            "diffs_k": diffs}


def neighbourhood_max(b3: dict, radius_mm: float) -> dict:
    """Hottest pad-copper probe (any ref) within radius of any CT reference-network part, per case."""
    pads = json.loads(PADS.read_text())
    at = {}
    for p in pads:
        at.setdefault(p["ref"], []).append((p["x"], p["y"]))
    cen = {r: (sum(x for x, _ in v) / len(v), sum(y for _, y in v) / len(v)) for r, v in at.items()}
    net_refs = ("R40", "R41", "R43", "R44", "R45", "R46")
    out = {}
    for c, d in b3.items():
        best = (-math.inf, None)
        for ref, t in d["probes"].items():
            if ref not in cen:
                continue
            dist = min(math.dist(cen[ref], cen[n]) for n in net_refs)
            if dist <= radius_mm and t > best[0]:
                best = (t, ref)
        out[c] = {"max_c": best[0], "ref": best[1]}
    return out, {r: [round(v, 2) for v in cen[r]] for r in ("T1", "R39", "R42", "R40", "R41", "R43", "R44", "R45", "R46",
                                                             "U10", "U11")}


def break_temp(parts: dict, f, lo=25.0, hi=400.0) -> float | None:
    """Lowest uniform network temperature at which f(band) < 0 (bisection; f decreasing in T). None if never."""
    if f(band(parts, [uniform(hi), uniform(T_COLD)], True)) >= 0:
        return None
    if f(band(parts, [uniform(lo), uniform(T_COLD)], True)) < 0:
        return lo
    for _ in range(40):
        mid = (lo + hi) / 2
        if f(band(parts, [uniform(mid), uniform(T_COLD)], True)) >= 0:
            lo = mid
        else:
            hi = mid
    return round(hi, 1)


# ------------------------------------------------------------------------------------------------ firmware side

def firmware() -> dict:
    fw = {n: h_define(TANK_FREQ_H, n) for n in ("TANK_PEAK_TRIP_MAX_A", "TANK_PEAK_TRIP_CAP_A", "TANK_PEAK_PER_RMS",
                                                  "TANK_PEAK_PICKUP_A", "TANK_CEILING_MAX_A", "TANK_CEILING_DEFAULT_A")}
    fw.update({n: h_define(N21_SIGNAL_H, n) for n in ("N21_CT_MON_V_PER_A", "N21_CT_MON_BIAS_V", "N21_CT_MON_MAX_MV")})
    return fw


def trip_for(c: float, fw: dict, cap: float | None = None) -> float:
    return min(fw["TANK_PEAK_PER_RMS"] * c + fw["TANK_PEAK_PICKUP_A"], fw["TANK_PEAK_TRIP_CAP_A"] if cap is None else cap)


def fw_error_tiers(k_hi: float) -> dict:
    """Firmware CT_MON peak-reading error at ct_sense_mon, volts (adverse: the firmware reads low)."""
    drift = max(VFB_0_85[1] - VFB_25[0], VFB_25[1] - VFB_0_85[0]) / 0.8            # 2.5 %: 25 C trim -> 0..85 C use
    trimmed = drift * V3V3_CTRL[1] * k_hi                                            # bias and hi ref both move
    untrimmed = max(abs(v * 0.5 * (1 + s * 2 * RT_TOL) - 1.65) for v in V3V3_CTRL for s in (-1, 1))
    return {"E0": 0.0, "E1": ADC_ERR_V, "E1s": 2 * ADC_ERR_V, "E2": ADC_ERR_V + max(trimmed, untrimmed),
            "detail": {"adc_v": ADC_ERR_V, "v3v3_drift_frac": drift, "trimmed_drift_v": trimmed,
                       "untrimmed_zero_v": untrimmed}}


def margins(b: dict, i_fw: float, e_v: float, g_max: float, v_per_a: float) -> dict:
    """Ordering margins for a firmware trip i_fw (amps on the firmware's nominal scale).
    b17: the COMMISSIONING B17 form, CT low corner (true amps) - i_fw.
    volts form (correct): (V_low - v_per_a i_fw - E) / g_max, true primary amps at the worst (highest) CT gain."""
    return {"b17_A": b["a_low"] - i_fw, "order_A": (b["v_low"] - v_per_a * i_fw - e_v) / g_max}


# ------------------------------------------------------------------------------------------------ candidates

def candidate_parts(base: dict, change: dict) -> dict:
    p = dict(base)
    for ref, ohm in change.items():
        p[ref] = (ohm, RT_TOL, RT_TCR)
    return p


def run() -> dict:
    bom, ohm, ratio, rec, facts = board_parts()
    base = dict(thr.PARTS)
    fw = firmware()
    v_per_a = fw["N21_CT_MON_V_PER_A"]
    assert abs(ohm["R39"] / ratio - v_per_a) < 1e-12, "CT_MON scale differs from R39 / T1"
    floor_a = kb.FLOOR[rec["tag"]]
    r6 = {}
    import csv
    with (VR / "05-resonant-tank-envelope/round6-full-power/outputs/board-side-protection.csv").open() as fh:
        for r in csv.DictReader(fh):
            r6[float(r["I_max_A"])] = float(r["tank_pk_max_A"])
    bank_mpn = bom["C21"]
    stop_a = facts["bank"][bank_mpn][1]
    ladder = facts["ladder"]

    # 1. reproduce B9 exactly (engine) and check the own enumerator against it
    eng = {t: thr.exact_corners(t, 50.0) for t in (-10.0, 85.0)}
    b9 = (cbt.floor2(min(eng[t][k]["min"] for t in eng for k in ("ct_pos_a", "ct_neg_a"))),
          cbt.ceil2(max(eng[t][k]["max"] for t in eng for k in ("ct_pos_a", "ct_neg_a"))))
    own = {t: ct_corners(base, uniform(t), extended=False) for t in (-10.0, 85.0)}
    dev = max(abs(own[t][pol][m] - eng[t][f"ct_{pol}_a"][m.split("_")[1]]) for t in own for pol in ("pos", "neg")
              for m in ("a_min", "a_max"))
    assert dev < 1e-9, f"own enumerator differs from thresholds.exact_corners by {dev}"
    doc = (REPO / "firmware/components/power/COMMISSIONING.md").read_text()
    m = re.search(r"\*\*band ([0-9.]+)–([0-9.]+) A \(\+\)", doc)
    assert m and (float(m.group(1)), float(m.group(2))) == b9, (m and m.groups(), b9)
    lowc = min(((t, pol) for t in eng for pol in ("pos", "neg")), key=lambda tp: eng[tp[0]][f"ct_{tp[1]}_a"]["min"])
    b9_low_corner = eng[lowc[0]][f"ct_{lowc[1]}_a"]["min_corner"]

    # 2. temperatures
    b3 = b3_temps(rec["board"], base)
    xchk = s52_crosscheck(b3)
    per_part_max = {r: max(b3[c]["rows"][r]["est_c"] for c in b3) for r in CT_REFS}
    hottest_ct = max(per_part_max.values())
    hood, positions = neighbourhood_max(b3, 25.0)
    hood_max = max(v["max_c"] for v in hood.values())
    lam_c28 = b3["c28_h10"]["laminate_peak_c"]
    scenarios = {   # name -> (temperature sets, extended model, R39 temperature for the worst CT gain)
        "B9 basis: uniform 85 C / -10 C (engine model)": ([uniform(85.0), uniform(T_COLD)], False, 85.0),
        "B9 basis, extended model (CMRR, 3 sense inputs, host load)": ([uniform(85.0), uniform(T_COLD)], True, 85.0),
        "B3 s53 per part (worst case of c17.5 / c22 / c28) / -10 C": ([per_part_max, uniform(T_COLD)], True, per_part_max["R39"]),
        f"uniform at the hottest CT-part B3 estimate ({hottest_ct:.1f} C, R39 element c28) / -10 C":
            ([uniform(hottest_ct), uniform(T_COLD)], True, hottest_ct),
        f"uniform at the hottest probe within 25 mm of R40-R46 ({hood_max:.1f} C) / -10 C":
            ([uniform(hood_max), uniform(T_COLD)], True, max(hood_max, per_part_max["R39"])),
        f"uniform at the c28 laminate 1 mm-block peak ({lam_c28:.1f} C, board maximum) / -10 C":
            ([uniform(lam_c28), uniform(T_COLD)], True, lam_c28),
    }
    SCEN_B3 = "B3 s53 per part (worst case of c17.5 / c22 / c28) / -10 C"
    SCEN_B9 = "B9 basis: uniform 85 C / -10 C (engine model)"
    SCEN_B9X = "B9 basis, extended model (CMRR, 3 sense inputs, host load)"

    # 3. candidates
    E = {}
    reach = lambda cap, mx: [(c, trip_for(c, fw, cap)) for c in ladder if trip_for(c, fw, cap) < mx]
    cands = {
        "C0 as built (R43/R46 2.21 k, R44/R45 10 k; fw MAX 64.5 A, CAP 62 A)": ({}, fw["TANK_PEAK_TRIP_CAP_A"], fw["TANK_PEAK_TRIP_MAX_A"]),
        "C1 fw only: MAX 64.5 -> 62.5 A (= CAP 62 A + 0.5; reachable trips unchanged)": ({}, 62.0, 62.5),
        "C2 fw only: CAP 62 -> 58 A, MAX -> 58.5 A": ({}, 58.0, 58.5),
        "C3 BOM: R44/R45 10 k -> 11 k (RT0603BRD0711KL, on the BOM) + C1": ({"R44": 11e3, "R45": 11e3}, 62.0, 62.5),
        "C4 BOM: R43/R46 2.21 k -> 2.00 k (RT0603BRD072KL, new line) + C1": ({"R43": 2.0e3, "R46": 2.0e3}, 62.0, 62.5),
        "C5 BOM: R43/R46 2.21 k -> 2.10 k (RT0603BRD072K1L, new line) + C1": ({"R43": 2.1e3, "R46": 2.1e3}, 62.0, 62.5),
    }
    out_c = {}
    for name, (chg, cap, mx) in cands.items():
        p = candidate_parts(base, chg)
        pn = {k: v[0] for k, v in p.items()}
        k_hi = pn["R44"] / (pn["R43"] + pn["R44"])
        tiers = fw_error_tiers(k_hi)
        E[name] = tiers
        bands = {s: band(p, ts, ext) for s, (ts, ext, _tg) in scenarios.items()}
        nom = thr.thresholds(pn, 2.5, 0.0)[1]
        rows = {}
        steps = [(c, trip_for(c, fw, cap)) for c in ladder]
        for s, b in bands.items():
            tg = scenarios[s][2]
            g = p["R39"][0] * (1 + p["R39"][1]) * (1 + p["R39"][2] * abs(tg - 25)) / 100.0
            rows[s] = {
                "a_low": b["a_low"], "a_high": b["a_high"], "v_low": b["v_low"], "v_high": b["v_high"],
                "floor_margin_A": b["a_low"] - floor_a,
                "pickup417_floor_margin_A": b["a_low"] - (r6[28.0] + 4.17 + 2.0),
                "b17_cap_A": b["a_low"] - mx,
                "steps": {f"{c:g}": {"trip_A": t, **{k: margins(b, t, tiers[k], g, v_per_a)["order_A"] for k in ("E0", "E1", "E1s", "E2")},
                                     "b17_A": b["a_low"] - t}
                          for c, t in steps},
            }
        # upper-side constraints on the extended B9 / hottest scenarios
        bx = bands[SCEN_B9X]
        hi_node = {v: v * (pn["R44"] / (pn["R43"] + pn["R44"])) * (1 + 2 * RT_TOL) + TLV_VOS for v in (V3V3_CTRL[1], V3V3_CONTRACT[1])}
        lo_node_min = V3V3_CONTRACT[0] * pn["R46"] / (pn["R45"] + pn["R46"]) * (1 - 2 * RT_TOL) - TLV_VOS
        a_high_hyst = bx["a_high"] + TLV_HYST_TYP / 2 / (p["R39"][0] * (1 - p["R39"][1]) * (1 - p["R39"][2] * 60) / 100)
        saved = dict(thr.PARTS)                      # the B9 row as commissioning_board_table.py would render it
        thr.PARTS.update(p)
        e2 = {t: thr.exact_corners(t, 50.0) for t in (-10.0, 85.0)}
        thr.PARTS.clear()
        thr.PARTS.update(saved)
        b9_render = {k: (cbt.floor2(min(e2[t][k]["min"] for t in e2)), cbt.ceil2(max(e2[t][k]["max"] for t in e2)))
                     for k in ("ct_pos_a", "ct_neg_a")}
        out_c[name] = {
            "b9_render_A": b9_render,
            "change": {k: v for k, v in chg.items()}, "fw_cap_A": cap, "fw_max_A": mx, "nominal_A": nom, "k_hi": k_hi,
            "fw_error_v": tiers, "scenarios": rows,
            "upper": {"a_high_b9x": bx["a_high"], "a_high_b9x_plus_hyst_typ": a_high_hyst,
                      "a_high_hottest_listed": max(r["a_high"] for s, r in rows.items() if "laminate" not in s),
                      "hi_node_v_at_v3v3": hi_node, "ct_mon_max_v": fw["N21_CT_MON_MAX_MV"] / 1e3,
                      "tlv_vcm_ok": all(hv <= v + TLV_VCM_TOP for v, hv in hi_node.items()),
                      "lo_node_min_v": lo_node_min,
                      "bank_v_at_high": max(r["a_high"] for s, r in rows.items() if "laminate" not in s) / (2 * math.pi * F_MIN_HZ * C_BANK_MIN),
                      "bank_vc_v": VC_BANK_V, "fet_id_pulse_A": ID_PULSE_A,
                      # T1 secondary volt-time per half cycle at the high corner, 35 kHz sine into R39 (limit 1276 V-us,
                      # CST3015 p.1 table, ledger)
                      "t1_volt_us_at_high": max(r["a_high"] for s, r in rows.items() if "laminate" not in s) / ratio
                                            * ohm["R39"] * (2 / math.pi) * 1e6 / (2 * F_MIN_HZ)},
            "ladder_clipped": [f"{c:g}" for c in ladder if trip_for(c, fw, cap) - fw["TANK_PEAK_PICKUP_A"] < r6.get(c, 0.0)
                               and trip_for(c, fw) - fw["TANK_PEAK_PICKUP_A"] >= r6.get(c, 0.0)],
        }

    # break temperatures for C0 and C3 (uniform network, extended model)
    brk = {}
    for name in (list(cands)[0], list(cands)[3]):
        chg, cap, mx = cands[name]
        p = candidate_parts(base, chg)
        pn = {k: v[0] for k, v in p.items()}
        tiers = E[name]
        g = lambda T: p["R39"][0] * (1 + p["R39"][1]) * (1 + p["R39"][2] * abs(T - 25)) / 100.0
        brk[name] = {
            "floor_64.17": break_temp(p, lambda b: b["a_low"] - floor_a),
            "order_E1_at_cap": break_temp(p, lambda b: b["v_low"] - v_per_a * cap - tiers["E1"]),
            "order_E1_at_stop": break_temp(p, lambda b: b["v_low"] - v_per_a * trip_for(stop_a, fw, cap) - tiers["E1"]),
            "order_E2_at_stop": break_temp(p, lambda b: b["v_low"] - v_per_a * trip_for(stop_a, fw, cap) - tiers["E2"]),
        }

    return {
        "board": {"stage": rec["stage"], "sha256": rec["board"], "copper_key": rec["copper"], "bank": bank_mpn,
                  "ladder_stop_A": stop_a, "ct_ratio": ratio, "R39_ohm": ohm["R39"]},
        "reproduce": {"b9_band_A": b9, "engine_low_exact_A": min(eng[t][k]["min"] for t in eng for k in ("ct_pos_a", "ct_neg_a")),
                      "engine_high_exact_A": max(eng[t][k]["max"] for t in eng for k in ("ct_pos_a", "ct_neg_a")),
                      "low_corner_at": {"temp_c": lowc[0], "polarity": lowc[1], "case": b9_low_corner},
                      "own_vs_engine_max_dev_A": dev,
                      "b17_margin_A": b9[0] - fw["TANK_PEAK_TRIP_MAX_A"]},
        "firmware": fw, "floor_A": floor_a, "round6_peaks_A": r6,
        "temperatures": {"per_case": {c: {"bay_c": d["bay_c"], "laminate_peak_c": d["laminate_peak_c"],
                                          "rows": d["rows"]} for c, d in b3.items()},
                         "per_part_max_c": per_part_max, "s52_crosscheck": xchk, "neighbourhood_25mm": hood,
                         "positions_mm": positions},
        "scenarios": list(scenarios), "candidates": out_c, "break_temps_c": brk,
    }


# ------------------------------------------------------------------------------------------------ report

def fmt(x, n=2):
    return "—" if x is None else f"{x:.{n}f}"


def render(r: dict) -> str:
    L = ["# c54-ct-band results (generated by scripts/ct_band.py; do not edit)", ""]
    b = r["board"]
    L += [f"Board of record: native-21 stage {b['stage']}, board `{b['sha256'][:12]}`, copper key `{b['copper_key']}`; "
          f"bank {b['bank']} (ladder stop {b['ladder_stop_A']:g} A); T1 1:{b['ct_ratio']}, R39 {b['R39_ohm']:g} Ω.", ""]
    rp = r["reproduce"]
    L += ["## 1. B9 reproduced", "",
          f"- Engine (`round3/thresholds.py` exact_corners, −10 / 85 °C uniform, v3v3 3.135–3.465 V): "
          f"**{rp['b9_band_A'][0]:.2f}–{rp['b9_band_A'][1]:.2f} A** (exact {rp['engine_low_exact_A']:.4f} / {rp['engine_high_exact_A']:.4f} A); "
          f"low corner at {rp['low_corner_at']['temp_c']:g} °C, {rp['low_corner_at']['polarity']} polarity.",
          f"- This study's enumerator reproduces the engine to {rp['own_vs_engine_max_dev_A']:.1e} A.",
          f"- B17 as written: {rp['b9_band_A'][0]:.2f} − TANK_PEAK_TRIP_MAX_A {r['firmware']['TANK_PEAK_TRIP_MAX_A']:g} = "
          f"**{rp['b17_margin_A']:.2f} A**. The reachable firmware trip is min(2.17 c + 3, TANK_PEAK_TRIP_CAP_A "
          f"{r['firmware']['TANK_PEAK_TRIP_CAP_A']:g}) ≤ {r['firmware']['TANK_PEAK_TRIP_CAP_A']:g} A (`config_ok` also requires "
          f"trip ≤ tank_peak_trip_for(ceiling)), so 64.5 A is never reached.", ""]
    t = r["temperatures"]
    L += ["## 2. CT-network temperatures on the s53 B3 BASIS run files (gate estimator)", "",
          "| Ref | basis | " + " | ".join(t["per_case"]) + " | worst |", "|---|---|" + "---|" * (len(t["per_case"]) + 1)]
    for ref in CT_REFS:
        what = next(iter(t["per_case"].values()))["rows"][ref]["what"]
        L.append(f"| {ref} | {what} | " + " | ".join(f"{d['rows'][ref]['est_c']:.1f}" for d in t["per_case"].values())
                 + f" | **{t['per_part_max_c'][ref]:.1f}** |")
    for ref in ("U10", "U11", "R42", "T1"):
        L.append(f"| {ref} | pad-copper probe (context) | " + " | ".join(f"{d['rows'][ref]['est_c']:.1f}" for d in t["per_case"].values()) + " | |")
    L += ["", f"Bays: " + ", ".join(f"{c} {d['bay_c']:g} °C" for c, d in t["per_case"].items()) +
          f". Laminate 1 mm-block peak: " + ", ".join(f"{c} {d['laminate_peak_c']:.1f} °C" for c, d in t["per_case"].items()) + ".",
          f"Cross-check against temp-ratings-2026-10-15 (s52 run files, board `{t['s52_crosscheck']['s52_board'][:12]}`): "
          f"R40–R46 pad estimates differ by at most {t['s52_crosscheck']['max_abs_pad_diff_k']:.2f} K.",
          "Hottest probe within 25 mm of R40–R46: " + ", ".join(f"{c} {v['max_c']:.1f} °C ({v['ref']})" for c, v in t["neighbourhood_25mm"].items()) + ".",
          "Positions (mm, pad centroids): " + ", ".join(f"{k} ({v[0]}, {v[1]})" for k, v in t["positions_mm"].items()) + ".", ""]
    L += ["## 3. Candidates", "",
          "Margins: **b17** = CT low corner (true A) − firmware trip; **E0/E1/E2** = ordering margin in true primary amps at "
          "the highest CT gain, (V_low − 15 mV/A × trip − E) / g_max, E0 thresholds only, E1 + ESP32-S3 ADC ±50 mV, "
          "E1s the ADC error counted at both the zero trim and the trip level (2 × 50 mV), "
          "E2 = E1 + v3v3 drift since the CT_MON zero trim (TPS62933 VFB window, 2.5 %) or the untrimmed zero, the larger.", ""]
    for name, c in r["candidates"].items():
        L += [f"### {name}", "",
              f"B9 as the table tool would render it: (+) {c['b9_render_A']['ct_pos_a'][0]:.2f}–{c['b9_render_A']['ct_pos_a'][1]:.2f} A, "
              f"(−) {c['b9_render_A']['ct_neg_a'][0]:.2f}–{c['b9_render_A']['ct_neg_a'][1]:.2f} A. "
              f"Nominal trip {c['nominal_A']:.2f} A; fw cap {c['fw_cap_A']:g} A, config max {c['fw_max_A']:g} A; "
              f"E1 {c['fw_error_v']['E1'] * 1e3:.1f} mV, E2 {c['fw_error_v']['E2'] * 1e3:.1f} mV.", "",
              "| Scenario | low A | high A | floor 64.17 | pickup-4.17 floor 65.34 | b17 vs config max |", "|---|---|---|---|---|---|"]
        for s, row in c["scenarios"].items():
            L.append(f"| {s} | {row['a_low']:.2f} | {row['a_high']:.2f} | {row['floor_margin_A']:+.2f} | "
                     f"{row['pickup417_floor_margin_A']:+.2f} | {row['b17_cap_A']:+.2f} |")
        L += ["", "Ordering margin per ladder step (A), scenario 'B3 s53 per part' / 'B9 extended':", "",
              "| step A | fw trip A | b17 | E0 | E1 | E1s | E2 | E1 (B9 ext.) | E2 (B9 ext.) |", "|---|---|---|---|---|---|---|---|---|"]
        sb3 = c["scenarios"][r["scenarios"][2]]["steps"]
        sb9 = c["scenarios"][r["scenarios"][1]]["steps"]
        for k, v in sb3.items():
            L.append(f"| {k} | {v['trip_A']:.2f} | {v['b17_A']:+.2f} | {v['E0']:+.2f} | {v['E1']:+.2f} | {v['E1s']:+.2f} | {v['E2']:+.2f} | "
                     f"{sb9[k]['E1']:+.2f} | {sb9[k]['E2']:+.2f} |")
        u = c["upper"]
        L += ["", f"Upper side: high corner {u['a_high_b9x']:.2f} A (B9 ext.), {u['a_high_b9x_plus_hyst_typ']:.2f} A with "
                  f"+½ typ hysteresis, {u['a_high_hottest_listed']:.2f} A worst listed scenario (laminate-peak row excluded); "
                  f"hi-ref node {u['hi_node_v_at_v3v3'][V3V3_CTRL[1]]:.3f} V at v3v3 {V3V3_CTRL[1]} V / "
                  f"{u['hi_node_v_at_v3v3'][V3V3_CONTRACT[1]]:.3f} V at {V3V3_CONTRACT[1]} V (CT_MON over-range "
                  f"{u['ct_mon_max_v']:.2f} V; TLV3201 VCM ≤ VCC + 0.2 V: {'ok' if u['tlv_vcm_ok'] else 'NO'}); "
                  f"lo-ref node ≥ {u['lo_node_min_v']:.3f} V; bank peak at the high corner {u['bank_v_at_high']:.0f} V "
                  f"(35 kHz, 0.475 µF) vs VC {u['bank_vc_v']:.0f} V; FET I_D,pulse {u['fet_id_pulse_A']:.0f} A.",
              f"T1 secondary volt-time at the high corner: {u['t1_volt_us_at_high']:.1f} V·µs per half cycle (limit 1276).",
              f"Ladder steps newly clipped by the fw cap (loop peak limit trip − 3 A below the round-6 envelope peak): "
              f"{', '.join(c['ladder_clipped']) or 'none'}.", ""]
    L += ["## 4. Break temperatures (uniform reference network, extended model, cold end −10 °C)", "",
          "| Candidate | CT low < 64.17 A floor | E1 order < 0 at fw cap | E1 order < 0 at the ladder stop | E2 order < 0 at the ladder stop |",
          "|---|---|---|---|---|"]
    for name, v in r["break_temps_c"].items():
        L.append(f"| {name} | {fmt(v['floor_64.17'], 1)} °C | {fmt(v['order_E1_at_cap'], 1)} °C | "
                 f"{fmt(v['order_E1_at_stop'], 1)} °C | {fmt(v['order_E2_at_stop'], 1)} °C |")
    L += ["", "(25.0 °C = fails already at room temperature; — = holds to 400 °C.)", ""]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    r = run()
    js = json.dumps(r, indent=1, sort_keys=True) + "\n"
    md = render(r)
    if a.check:
        ok = OUT_JSON.exists() and OUT_JSON.read_text() == js and OUT_MD.exists() and OUT_MD.read_text() == md
        print("PASS: results reproduce" if ok else "FAIL: results differ from a fresh run")
        return 0 if ok else 1
    OUT_JSON.write_text(js)
    OUT_MD.write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
