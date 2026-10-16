#!/usr/bin/env python3
"""Stage 48 datasheet-ledger edit (S19 LDO EN dividers, Q1 grade; B13 H1 / H2 resistors): run after the s48 chain.

    python3 -I scripts/ledger48.py    -> native-21/verification/datasheet-ledger/ledger.json (in place)

Adapted from the u3-286 analysis lane's u3ledger.py (which wrote TPS70950DBVR as VIOLATION: EN tied to IN on all four
parts against SBVS186H 7.4 p.13). Stage 48 fixes the finding, so this entry PASSes:
* TPS70950DBVR -> TPS70950QDBVRQ1 (U3, U37, U38, U39), audited from TI SLVSCE6D (rev. D, Aug 2025): Table 4-1 p.3, 5.1 p.3,
  5.3 p.4, 5.4 p.4, 5.5 p.5, 7.1.1 p.17, 7.4.1 / 7.4.1.2 p.19.
* EN rows per LDO: the 100 k / 27 k divider window at IN minimum / maximum / the span-OV corner, with the same arithmetic
  and constants as audit.rs stage48_checks (1 % + 100 ppm/K x 100 K adverse and untracked, 1 uA pull-up bound).
* TJ rows for U3 from the B3 gated U3 row of this board (keyed citations into b3-ratings/margins.json); U37-U39 keep no
  junction row (they are not B3 heat sources: 5 V at < 1 mA).
* The stage-48 parts join their BOM lines' designators: R136 / R138 / R140 / R142 (0603WAF1003T5E), R137 / R139 /
  R141 / R143 (0603WAF2702T5E), R144 (RT0603BRD0763K4L), R145 (TNPW060311K7BEEA), R146 (RC1206FR-07220KL, with its
  voltage row), C176-C178 (CC0603KRX7R9BB104, the H2 transfer caps).
Re-running it on the edited ledger gives the same file.
"""
import sys as _s; _s.dont_write_bytecode = True
import json, re
from pathlib import Path

HERE = Path(__file__).resolve().parent
PS = HERE.parents[3]
LEDGER = PS / "native-21/verification/datasheet-ledger/ledger.json"
MARGINS = PS / "validation-results/04-board-current-thermal/round5-native21/b3-ratings/margins.json"
KELVIN = PS / "validation-results/02-protection-timing/kelvin/kelvin_plane.py"
OLD, MPN = "TPS70950DBVR", "TPS70950QDBVRQ1"
DS_SHA = "bd01fad0eb2defdd"
RAILS = "validation-results/11-candidates/s20-286v-recite/README-analysis.md:149-151"
CARD = "validation-results/11-candidates/c48-ldo-en-ref-watch/README.md"
# audit.rs S48_RESISTORS / S48_DT_K / S48_IEN_A / S48_LDO_IN (same numbers; audit.rs is the gate)
TOP, BOT = (100e3, 0.01, 100.0), (27e3, 0.01, 100.0)
DT_K, IEN = 100.0, 1.0e-6
LDOS = [("U3", "u_ldo", "V15_LS - OCP_KELVIN_P", "R136 / R137", 14.50, 15.46, 16.68),
        ("U37", "monitor_ls.ldo5", "LS rail span", "R138 / R139", 16.575, 17.43, 18.643),
        ("U38", "bias_ha.monitor.ldo5", "HS-A rail span", "R140 / R141", 16.575, 17.43, 18.643),
        ("U39", "bias_hb.monitor.ldo5", "HS-B rail span", "R142 / R143", 16.575, 17.43, 18.643)]
U3_P_W, U3_I_MA = 0.160, 15.1      # (15.46 - 4.89 V) x 15.1 mA: b3_ratings_gate MONITOR_SELF["tps709"]


def en_window(vin_min, vin_max, vin_corner):
    d = lambda r, s: r[0] * (1.0 + s * (r[1] + r[2] * 1e-6 * DT_K))
    lo = d(BOT, -1) / (d(BOT, -1) + d(TOP, 1))
    hi = d(BOT, 1) / (d(BOT, 1) + d(TOP, -1))
    rth = TOP[0] * (1 + TOP[1]) * BOT[0] * (1 + BOT[1]) / (TOP[0] * (1 + TOP[1]) + BOT[0] * (1 + BOT[1]))
    return (round(vin_min * lo, 3), round(vin_max * hi + IEN * rth, 3), round(vin_corner * hi + IEN * rth, 3),
            round((6.5 - IEN * rth) / hi, 1))


def b3_u3():
    """The gated B3 U3 row of this board per case; margins.json must be solved on the s48 board."""
    m = json.loads(MARGINS.read_text())
    pins = re.search(r'"native21s48": "([0-9a-f]{64})"', KELVIN.read_text())
    sha = set(m["board_sha256"].values())
    assert pins and sha == {pins.group(1)}, ("margins.json is not the s48 board", sha, pins and pins.group(1))
    out = {}
    for c, rows in m["cases"].items():
        hit = [r for r in rows if r["item"].startswith("U3: ")]
        assert len(hit) == 1 and MPN in hit[0]["item"] and hit[0]["gated"], (c, hit)
        out[c] = hit[0]
    return out, str(MARGINS.relative_to(PS)), pins.group(1), m["basis"]["cases"]


def tps709q():
    rows, rel, pin, basis = b3_u3()
    rel_case = next(c for c, v in basis.items() if v["role"] == "release")
    ratchet = [c for c, v in basis.items() if v["role"] != "release"]
    worst = max(ratchet, key=lambda c: rows[c]["est_c"])
    key = lambda c: {"file": rel, "b3_row": {"case": c, "item": " ".join(rows[c]["item"].split()[:3])},
                     "est_c": round(rows[c]["est_c"], 1)}
    t_rel, t_w = round(rows[rel_case]["est_c"], 1), round(rows[worst]["est_c"], 1)
    win = {ref: en_window(a, b, c) for ref, _, _, _, a, b, c in LDOS}
    stresses, checks = [], []
    for ref, path, vin, res, vmin, vmax, vcorner in LDOS:
        lo, hi, corner, vin_lim = win[ref]
        ev = f"audit.rs; {RAILS}" if ref == "U3" else "audit.rs; validation-results/11-candidates/s16-fmea-b-2026-10-15/scripts/bands.py:35-37"
        stresses += [
            {"parameter": f"EN voltage, {ref}, IN maximum", "worst_case_value": hi, "unit": "V",
             "condition": f"{res} 100 k / 27 k (1 % + 100 ppm/K x 100 K, adverse) from IN = {vin} max {vmax} V, plus a "
                          f"1 uA pull-up bound x Rth (IEN 300 nA typ, 5.5 p.5); EN at IN minimum {vmin} V: {lo} V >= "
                          f"VEN(HI) 0.9 V (5.5 p.5); EN reaches 6.5 V only at IN {vin_lim} V", "evidence": ev},
            {"parameter": f"EN voltage, {ref}, span-OV corner", "worst_case_value": corner, "unit": "V",
             "condition": f"IN {vcorner} V, the highest span the S16 monitor can leave undetected (DECISIONS 62)",
             "evidence": ev}]
        checks += [
            {"id": f"EN {ref} recommended", "rating": "VEN recommended max", "stress": f"EN voltage, {ref}, IN maximum",
             "max_ratio": 1.0, "severity": "violation", "rule": f"{hi} V <= 6.5 V (EN {lo}-{hi} V over IN {vmin}-{vmax} V)",
             "ratio": round(hi / 6.5, 4)},
            {"id": f"EN {ref} corner", "rating": "VEN recommended max", "stress": f"EN voltage, {ref}, span-OV corner",
             "max_ratio": 1.0, "severity": "violation", "rule": f"{corner} V <= 6.5 V at IN {vcorner} V",
             "ratio": round(corner / 6.5, 4)}]
    stresses += [
        {"parameter": "VIN, U37-U39 at the span-OV corner", "worst_case_value": 18.643, "unit": "V",
         "condition": "highest span the S16 monitor can leave undetected (DECISIONS 62); U3 sees 16.68 V there",
         "evidence": "validation-results/11-candidates/s16-fmea-b-2026-10-15/scripts/bands.py:35-37"},
        {"parameter": "U3 load current", "worst_case_value": U3_I_MA, "unit": "mA",
         "condition": "HOT5 census at its maxima incl. U9 CA-IS3720HW side A 4.1 mA (kelvin_budget CENSUS48) and IGND",
         "evidence": f"validation-results/02-protection-timing/kelvin/kelvin_budget.py; {RAILS}"},
        {"parameter": "U3 dissipation", "worst_case_value": U3_P_W, "unit": "W",
         "condition": f"PD = (VIN - VOUT) x IOUT (7.4.1.2 p.19): (15.46 - 4.89 V) x {U3_I_MA} mA; the B3 heat source "
                      "since stage 48 (was 0.1 W)",
         "evidence": "validation-results/04-board-current-thermal/round5-native21/b3/make_heat_sources.py; "
                     "validation-results/04-board-current-thermal/round5-native21/b3-ratings/b3_ratings_gate.py"},
        {"parameter": "U3 junction, release case", "worst_case_value": t_rel, "unit": "C",
         "condition": f"B3 gated U3 row (pad copper + {U3_P_W} W x psiJB 40.7 C/W, 5.4 p.4 new chip), {rel_case} at bay "
                      f"{basis[rel_case]['bay_c']:g} C; board {pin[:8]}", "evidence": [key(rel_case)]},
        {"parameter": "U3 junction, ratchet max", "worst_case_value": t_w, "unit": "C",
         "condition": f"same row, worst ratchet case ({worst}); ratchet only (release is {rel_case})",
         "evidence": [key(worst)]}]
    checks += [
        {"id": "VIN U37-U39", "rating": "VIN recommended max", "stress": "VIN, U37-U39 at the span-OV corner",
         "max_ratio": 1.0, "severity": "violation", "rule": "18.643 V <= 30 V", "ratio": round(18.643 / 30.0, 4)},
        {"id": "load", "rating": "Output current limit min", "stress": "U3 load current", "max_ratio": 0.5,
         "severity": "violation", "rule": f"{U3_I_MA} mA <= half the 200 mA current-limit minimum",
         "ratio": round(U3_I_MA / 200.0, 4)},
        {"id": "TJ release", "rating": "TJ operating max", "stress": "U3 junction, release case", "max_ratio": 1.0,
         "severity": "violation", "rule": f"{t_rel} C <= 125 C (B3 gated row)", "ratio": round(t_rel / 125.0, 4)},
        {"id": "TJ ratchet", "rating": "TJ operating max", "stress": "U3 junction, ratchet max", "max_ratio": 1.0,
         "severity": "gap", "rule": f"{t_w} C <= 125 C ({worst}, ratchet only)", "ratio": round(t_w / 125.0, 4)}]
    over = t_w > 125.0
    u3 = win["U3"]
    return {
        "mpn": MPN, "designators": ["U3", "U37", "U38", "U39"], "class": "SAFETY",
        "function": "5 V LDOs, 125 C (Q1) grade since stage 48: U3 makes HOT5 (supply of the firmware-independent OCP / OVP "
                    "trip chain: U6 / U7 TLV3201, U8 NAND, U9 CA-IS3720HW side A, U14 TPS3700 since stage 48, U15, U4 "
                    "AMC1311B VDD1, and U5's bias through R31); U37 / U38 / U39 make the LS / HS-A / HS-B rail-monitor 5 V. "
                    "Each EN from a 100 k / 27 k divider off its IN (stage 48, S19; tied to IN before)",
        "status": "PARTIAL",
        "datasheet": {
            "url": "https://www.ti.com/lit/ds/symlink/tps709-q1.pdf",
            "revision": "TI SLVSCE6D, December 2013, revised August 2025", "fetched": "2026-10-16", "repo_copy": None,
            "sha256_prefix16": DS_SHA,
            "note": "u3-286 analysis download (runs-native21/s47/u3-dl/tps709-q1.pdf), not committed. Table 4-1 p.3: DBV "
                    "IN 1, GND 2, EN 3, NC 4, OUT 5 (as SBVS186H 5 p.3), EN 'can be left floating to enable the device. "
                    "The maximum voltage must remain below 6.5 V', OUT 'a small 2.2-uF or greater ceramic capacitor'; "
                    "5.1 p.3 abs max VIN -0.3..32 V, VEN -0.3..7 V, TJ -55..150 C, TA -40..125 C; 5.3 p.4 VIN 2.7..30 V, "
                    "IOUT 0..150 mA, VEN 0..6.5 V, CIN 1 uF nom, COUT 2..47 uF, TJ -40..125 C; 5.4 p.4 DBV RthJA 210.9 "
                    "legacy / 176.5 new chip, psiJB 38.4 / 40.7 C/W; 5.5 p.5 at -40 <= TJ, TA <= 125 C: DC accuracy "
                    "+-1 % (VOUT >= 3.3 V), line 10 mV, load 50 mV (100 uA..150 mA), ICL 200 mA min, VEN(HI) 0.9 V min, "
                    "IEN 300 nA typ (EN = 1 V); 7.1.1 p.17 an input capacitor is not required for stability, 0.1..2.2 uF "
                    "good practice; 7.4.1 p.19 caps as close to the pins as possible; 7.4.1.2 p.19 PD = (VIN - VOUT) x "
                    "IOUT. LCSC C485909."},
        "ratings": [
            {"parameter": "EN abs max", "datasheet_limit": 7.0, "unit": "V", "basis": "absolute maximum",
             "source": "5.1 p.3"},
            {"parameter": "VEN recommended max", "datasheet_limit": 6.5, "unit": "V",
             "basis": "recommended operating; Table 4-1: 'must remain below 6.5 V'", "source": "5.3 p.4; Table 4-1 p.3"},
            {"parameter": "VIN recommended max", "datasheet_limit": 30.0, "unit": "V", "basis": "recommended operating "
             "(abs max 32 V)", "source": "5.3 p.4; 5.1 p.3"},
            {"parameter": "TJ operating max", "datasheet_limit": 125.0, "unit": "C", "basis": "recommended operating "
             "(abs max 150 C)", "source": "5.3 p.4"},
            {"parameter": "Output current limit min", "datasheet_limit": 200.0, "unit": "mA", "basis": "ICL min at VOUT = "
             "0.9 x VOUT(nom), over -40..125 C", "source": "5.5 p.5"}],
        "stresses": stresses,
        "derating_rule": "EN within VEN(HI) 0.9 V .. 6.5 V recommended (7 V abs max) at every IN corner incl. the span-OV "
                         "corner; VIN <= 30 V; load <= half the ICL minimum; TJ <= 125 C at the release case (ratchet "
                         "cases reported). The +-1 % HOT5 accuracy holds to TJ, TA 125 C on this grade (5.5 p.5).",
        "checks": checks,
        "layout_guidance": [
            {"item": "EN (pin 3) on its own divider tap, never on IN (pin 1): EN <= 6.5 V by divider arithmetic at the IN "
                     "maximum and the span-OV corner", "enforced_by": "audit.rs"},
            {"item": "same DBV pads and pinout as TPS70950DBVR (Table 4-1 p.3); CPL rotation evidence for C485909",
             "enforced_by": "validation-results/08-manufacturing-package/native-21/cpl-rotation-audit/audit.py"},
            {"item": "input and output capacitors as close to the pins as possible (7.4.1 p.19): U3's 100 nF input cap C25 "
                     "stays ~12 mm away on V15_LS (as at s47; the input cap is not required for stability, 7.1.1 p.17)",
             "enforced_by": "UNCHECKED"}],
        "gaps": [
            "the U3 junction is the B3 body-model estimate (pad copper + P x psiJB, hot copper, still air at the BASIS "
            "bays), not a measurement" + (f"; the ratchet case {worst} reads {t_w} C, over 125 C (ratchet only)" if over else ""),
            "U37-U39 have no junction row: they carry their monitor's 5 V (< 1 mA), and their local temperature rows of the "
            "temp-ratings 2026-10-15 run were on the TPS70950DBVR line (not re-cited onto this MPN)",
            "U3's input cap C25 is not at the pins (7.4.1 p.19 layout guidance; see layout_guidance)"],
        "finding": None,
        "notes": f"S19 (2026-10-16): the u3-286 lane's u3ledger.py VIOLATION (EN tied to IN, 15.5 / 17.4 V on a 7 V abs-max "
                 f"pin) is closed at stage 48 by the 100 k / 27 k EN dividers: U3 EN {u3[0]}-{u3[1]} V over IN 14.50-15.46 "
                 f"V ({u3[2]} V at 16.68 V); U37-U39 EN {win['U37'][0]}-{win['U37'][1]} V over 16.575-17.43 V "
                 f"({win['U37'][2]} V at 18.643 V). Floating EN (allowed by Table 4-1 p.3) was rejected: with the 300 nA "
                 f"typical pull-up, a few-megohm leakage path to GND on uncoated PD3 laminate would disable the LDO. The Q1 "
                 f"grade closes the +-1 %-to-85 C gap of SBVS186H 6.5 p.5. Card: {CARD}.",
    }


ADD = {"0603WAF1003T5E": ["R136", "R138", "R140", "R142"], "0603WAF2702T5E": ["R137", "R139", "R141", "R143"],
       "RT0603BRD0763K4L": ["R144"], "TNPW060311K7BEEA": ["R145"], "RC1206FR-07220KL": ["R146"],
       "CC0603KRX7R9BB104": ["C176", "C177", "C178"]}
ROLE = {"0603WAF1003T5E": "stage 48: R136 / R138 / R140 / R142 are the LDO EN divider tops (IN to EN)",
        "0603WAF2702T5E": "stage 48: R137 / R139 / R141 / R143 are the LDO EN divider bottoms (EN to GND)",
        "RT0603BRD0763K4L": "stage 48: R144 is the REF25 watchdog divider top (REF25 to U14 INB-)",
        "TNPW060311K7BEEA": "stage 48: R145 is the REF25 watchdog divider bottom (U14 INB- to OCP_KELVIN_P)",
        "RC1206FR-07220KL": "stage 48: R146 is the BIAS_GOOD -> J4 pin 1 readback series resistor (SELV, 3.3 V logic)",
        "CC0603KRX7R9BB104": "stage 48: C176 / C177 / C178 are v3v3 - selv_gnd transfer caps beside BIAS_GOOD's J4.1 branch "
                             "vias (3.3 V)"}
GAP48 = "[stage 48] the stage-48 designators ({}) have no local-temperature row (they post-date temp-ratings 2026-10-15)"


def resistors(E):
    for mpn, refs in ADD.items():
        e = E[mpn]
        e["designators"] = sorted(set(e["designators"]) | set(refs), key=lambda r: int(r[1:]))
        if ROLE[mpn] not in e["function"]:
            e["function"] = f"{e['function']}; {ROLE[mpn]}"
        g = GAP48.format(" / ".join(refs))
        if g not in e["gaps"]:
            e["gaps"].append(g)
    e = E["RC1206FR-07220KL"]
    if not any(s["parameter"] == "V across R146" for s in e["stresses"]):
        e["stresses"].append({"parameter": "V across R146", "worst_case_value": 3.6, "unit": "V",
                              "condition": "BIAS_GOOD high at 3.6 V (the logic-high bound audit.rs stage48 uses) with J4.1 "
                                           "shorted to selv_gnd: 16.4 uA, 0.06 mW", "evidence": "audit.rs"})
        e["checks"].append({"id": "V R146", "rating": "V working", "stress": "V across R146", "max_ratio": 0.5,
                            "severity": "violation", "rule": "3.6 V <= half the 200 V working voltage",
                            "ratio": round(3.6 / 200, 4)})


def main():
    led = json.loads(LEDGER.read_text())
    E = led["entries"]
    new = tps709q()
    out = {}
    for k, v in E.items():
        if k in (OLD, MPN):
            if MPN not in out:
                out[MPN] = new
        else:
            out[k] = v
    resistors(out)
    led["entries"] = out
    LEDGER.write_text(json.dumps(led, indent=1) + "\n")
    print("ledger: entries", len(out))
    for c in new["checks"]:
        print(f"  {c['id']:22} {c['ratio']:.4f} <= {c['max_ratio']}  {c['rule']}")


if __name__ == "__main__":
    main()
