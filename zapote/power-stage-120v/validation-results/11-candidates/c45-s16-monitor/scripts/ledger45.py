#!/usr/bin/env python3
"""Stage 45 datasheet-ledger edit (S16, option 1c-4420): run once after scripts/bands45.py.

    python3 -I scripts/ledger45.py    -> native-21/verification/datasheet-ledger/ledger.json (in place)

* replaces TL431AIDBZR by TL431BIDBZR (U17 / U19 / U21) and the three tap-top lines that left the BOM
  (RT0603BRD077K68L, RT0603BRD07120KL, ARG03BTC1333) by the four new ones (750 R, 2.94 k, 90.9 k, 104 k);
* re-lists the designators of RT0603BRD074K42L (now R79 / R97 / R112), RT0603BRD0710KL and RT0603BRD0711KL;
* moves the 2EDR8259X "VDD at the span OV trip" stress to the s45 worst-case upper corner.
Every stress is read from results/bands-s45.json and cited to its line in results/bands-s45.md. Re-running it on the
edited ledger gives the same file.
"""
import sys as _s; _s.dont_write_bytecode = True
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PS = HERE.parents[3]
LEDGER = PS / "native-21/verification/datasheet-ledger/ledger.json"
RES = HERE.parent / "results"
B = json.loads((RES / "bands-s45.json").read_text())
MD = (RES / "bands-s45.md").read_text().splitlines()
MDREL = str((RES / "bands-s45.md").relative_to(PS))
S16 = "validation-results/11-candidates/s16-monitor-2026-10-15/README.md"
S16_LINES = (PS / S16).read_text().splitlines()


def cite(prefix):
    hits = [i + 1 for i, l in enumerate(MD) if l.startswith(prefix)]
    assert len(hits) == 1, (prefix, hits)
    return f"{MDREL}:{hits[0]}"


def cite_s16(needle):
    hits = [i + 1 for i, l in enumerate(S16_LINES) if needle in l]
    assert len(hits) == 1, (needle, hits)
    return f"{S16}:{hits[0]}"


ST = B["stresses"]
TEMP_GAP = ("bench / B3: no B3 probe rows at the monitor islands (U16-U21, U29-U31; OPEN-ITEMS S16 next step): the local "
            "temperature is the S16 fallback estimate 64.3 C (bay 61 C + TL431 self-heat) and the band analysis is bounded "
            "at 85 C (the TL431BI / LM339B rated maximum, 60 K TCR excursion); the parts sit 11-13 mm from U26 / U41 / U42")
FAULT_GAP = ("the fault-case span is a stated case, not a bound: V24_RAW nominal 24 V on the span (LS LDO pass short); "
             "PS2's own output tolerance / OVP and the RECOM feedback-open output are not in the ledger")
YAGEO_DS = {"url": "https://datasheet.lcsc.com/datasheet/pdf/46d7760c582640714d605308a25a220a.pdf?productCode=C95204",
            "revision": "Yageo RT series product specification V.16, May 06 2025 (LCSC copy for C95204)",
            "fetched": "2026-10-15", "repo_copy": None,
            "note": "S16 study download (11-candidates/s16-monitor-2026-10-15/results/datasheet-manifest.json); not committed. "
                    "Table 2 p.5: RT0603 1/10 W, max working 75 V, overload 150 V, -55..+155 C, 0.1 % / 25 ppm range 1 R-1 M; "
                    "p.6: rated power at 70 C, Fig. 6 linear derating to 0 at 155 C, rated voltage = sqrt(P x R) or 75 V",
            "sha256_prefix16": "0a729d144519a702"}
P70, P85 = 0.1, round(0.1 * (155 - 85) / (155 - 70), 4)


def resistor(mpn, ohm, des, role, lcsc, stock, usd):
    key = next(k for k in ST["resistors"] if k.endswith(f" top {ohm:g}"))
    cases = ST["resistors"][key]
    fault = max((c for c in cases if c != "operating"), key=lambda c: cases[c]["mW"])
    vwork = round(min((P70 * ohm) ** 0.5, 75.0), 3)
    op, fl = cases["operating"], cases[fault]
    line_op = cite(f"| {key} | operating |")
    line_fl = cite(f"| {key} | {fault} |")
    stresses = [
        {"parameter": "Voltage, operating", "worst_case_value": op["V"], "unit": "V",
         "condition": "s45 values at the operating ceiling (span at the span-OV worst-case upper corner, neg rail at its "
                      "worst-case maximum)", "evidence": line_op},
        {"parameter": "Voltage, fault", "worst_case_value": fl["V"], "unit": "V",
         "condition": ("span at V24_RAW 24 V (LDO pass short)" if "span" in role else
                       "src floating to the span or V24_RAW (R77 / TLVH431 open; an upper bound, the 4.99 k bleed holds src "
                       "below P)") + "; stated case, not a bound", "evidence": line_fl},
        {"parameter": "Power, fault", "worst_case_value": round(fl["mW"] / 1e3, 6), "unit": "W",
         "condition": "same fault case", "evidence": line_fl}]
    return {
        "mpn": mpn, "designators": des, "class": "SIGNAL",
        "function": f"{ohm:g} ohm 0.1 % 25 ppm 0603: rail-monitor {role} (stage 45, S16 option 1c-4420, DECISIONS 59)",
        "status": "PARTIAL", "datasheet": YAGEO_DS,
        "ratings": [
            {"parameter": "Rated working voltage", "datasheet_limit": vwork, "unit": "V",
             "basis": f"min(sqrt(0.1 W x {ohm:g} ohm), 75 V max working)", "source": "Table 2 p.5; p.6 RATED VOLTAGE"},
            {"parameter": "Power at 85 C", "datasheet_limit": P85, "unit": "W",
             "basis": "1/10 W at 70 C, linear derating to 0 at 155 C (Fig. 6) taken at the 85 C monitor bound",
             "source": "Table 2 p.5; p.6 Fig. 6"},
            {"parameter": "Tolerance / TCR", "datasheet_limit": 25, "unit": "ppm/C",
             "basis": "B = +-0.1 %, D = +-25 ppm/C; value inside the RT0603 0.1 % / 25 ppm range 1 R-1 M",
             "source": "p.2 ordering code; Table 2 p.5"}],
        "stresses": stresses,
        "derating_rule": "Voltage <= the rated working voltage; power <= 50 % of the 85 C derated rating.",
        "checks": [
            {"id": "voltage operating", "rating": "Rated working voltage", "stress": "Voltage, operating", "max_ratio": 1.0,
             "severity": "violation", "rule": f"{op['V']} V <= {vwork} V", "ratio": round(op["V"] / vwork, 4)},
            {"id": "voltage fault", "rating": "Rated working voltage", "stress": "Voltage, fault", "max_ratio": 1.0,
             "severity": "violation", "rule": f"{fl['V']} V <= {vwork} V", "ratio": round(fl["V"] / vwork, 4)},
            {"id": "power fault", "rating": "Power at 85 C", "stress": "Power, fault", "max_ratio": 0.5,
             "severity": "violation", "rule": f"{fl['mW']} mW <= 50 % of {P85 * 1e3:g} mW",
             "ratio": round(fl["mW"] / 1e3 / P85, 4)}],
        "layout_guidance": [{"item": "same 0603 pads as the s44 part it replaces (BOM-only stage)",
                             "enforced_by": "UNCHECKED (placement and copper unchanged from s44; c45 README)"}],
        "gaps": [TEMP_GAP, FAULT_GAP],
        "finding": None,
        "notes": f"JLC {lcsc}, extended, {stock:,} in stock 2026-10-15; ${usd} at 1,500 pcs (3 per board x 500). The band it sets "
                 f"is in {MDREL} (study 11-candidates/s16-monitor-2026-10-15, reproduced to 1e-4)."}


def tl431b():
    t = ST["TL431"]
    l45 = cite("- TL431B: VKA max")
    return {
        "mpn": "TL431BIDBZR", "designators": ["U17", "U19", "U21"], "class": "SIGNAL",
        "function": "Rail-monitor reference (REF tied to K, fed by rref 2.2 k), LS / HS-A / HS-B; B grade since stage 45 "
                    "(S16 option 1c-4420, DECISIONS 59)",
        "status": "PARTIAL",
        "datasheet": {"url": "https://www.ti.com/lit/ds/symlink/tl431.pdf",
                      "revision": "TI SLVS543S, Aug 2004, revised May 2024", "fetched": "2026-10-15", "repo_copy": None,
                      "note": "S16 study download (datasheet-manifest.json); not committed. Table 6.12 p.13 (TL431BI): Vref "
                              "2483 / 2495 / 2507 mV at 25 C, VKA = Vref, IKA 10 mA; VI(dev) 14 typ / 34 max mV (max - min "
                              "over the rated temperature range, note 1); |ZKA| 0.5 ohm max; Imin 0.7 mA max. Table 6.1 p.5 "
                              "abs max VKA 37 V, IKA -100..150 mA, TJ 150 C; Table 6.4 p.5 recommended VKA Vref..36 V, IKA "
                              "1..100 mA, TL43xxI TA -40..85 C; Table 6.3 p.5 DBZ RthJA 206 C/W; Table 5-1 p.4 DBZ pins "
                              "1 = cathode, 2 = REF, 3 = anode (same as the A grade)",
                      "sha256_prefix16": "ed2e90697de4e2c5"},
        "ratings": [
            {"parameter": "Cathode voltage, recommended max", "datasheet_limit": 36, "unit": "V",
             "basis": "recommended operating conditions", "source": "Table 6.4 p.5"},
            {"parameter": "Cathode current, recommended max", "datasheet_limit": 100, "unit": "mA",
             "basis": "recommended operating conditions (minimum 1 mA)", "source": "Table 6.4 p.5"},
            {"parameter": "Free-air temperature max", "datasheet_limit": 85, "unit": "C",
             "basis": "TL43xxI operating range -40..85 C", "source": "Table 6.4 p.5"},
            {"parameter": "Vref at 25 C, B grade", "datasheet_limit": 2.507, "unit": "V",
             "basis": "2.483-2.507 V (A grade 2.470-2.520 V, Table 6.9 p.10); the S16 band model takes this range "
                      "+- VI(dev)", "source": "Table 6.12 p.13"},
            {"parameter": "VI(dev) max", "datasheet_limit": 0.034, "unit": "V",
             "basis": "deviation over the full rated temperature range, max - min (not a TC)", "source": "Table 6.12 p.13"}],
        "stresses": [
            {"parameter": "Cathode voltage", "worst_case_value": t["vka_max_V"], "unit": "V",
             "condition": "REF tied to K: VKA = Vref <= 2.507 + 0.034 V", "evidence": l45},
            {"parameter": "Cathode current, operating max", "worst_case_value": t["ik_max_op_mA"], "unit": "mA",
             "condition": "span at the span-OV worst-case upper corner, rref -1.6 %, Vref low, halfref divider high "
                          f"(minimum {t['ik_min_mA']} mA at the span-UV lower corner, >= 1 mA)", "evidence": l45},
            {"parameter": "Cathode current, fault case", "worst_case_value": t["ik_max_fault_mA"], "unit": "mA",
             "condition": f"span at V24_RAW 24 V (LS LDO pass short; stated case, not a bound); {t['p_max_fault_mW']} mW, "
                          f"{t['self_heat_fault_K']} K self-heat at 206 C/W", "evidence": l45},
            {"parameter": "Local temperature, expected", "worst_case_value": 64.3, "unit": "C",
             "condition": "S16 fallback estimate (no B3 row): bay 61 C + self-heat; not solved",
             "evidence": cite_s16("64.3 °C expected")}],
        "derating_rule": "VKA and IKA inside the recommended operating conditions (IKA >= 1 mA); ambient <= 85 C (I grade).",
        "checks": [
            {"id": "VKA", "rating": "Cathode voltage, recommended max", "stress": "Cathode voltage", "max_ratio": 1.0,
             "severity": "violation", "rule": f"{t['vka_max_V']} V <= 36 V", "ratio": round(t["vka_max_V"] / 36, 4)},
            {"id": "IKA operating", "rating": "Cathode current, recommended max", "stress": "Cathode current, operating max",
             "max_ratio": 1.0, "severity": "violation", "rule": f"{t['ik_max_op_mA']} mA <= 100 mA",
             "ratio": round(t["ik_max_op_mA"] / 100, 4)},
            {"id": "IKA fault", "rating": "Cathode current, recommended max", "stress": "Cathode current, fault case",
             "max_ratio": 1.0, "severity": "violation", "rule": f"{t['ik_max_fault_mA']} mA <= 100 mA",
             "ratio": round(t["ik_max_fault_mA"] / 100, 4)},
            {"id": "temperature (estimate)", "rating": "Free-air temperature max", "stress": "Local temperature, expected",
             "max_ratio": 1.0, "severity": "gap", "rule": "64.3 C estimate <= 85 C; not a solved temperature",
             "ratio": round(64.3 / 85, 4)}],
        "layout_guidance": [{"item": "REF tied to K on the 'ref' net; anode on the rail's n",
                             "enforced_by": "audit_f6.rs"}],
        "gaps": [TEMP_GAP, FAULT_GAP,
                 "Vref long-term (load-life) drift is not specified (only VI(dev) over temperature); covered only by the "
                 "0.5 % margin target of the band analysis"],
        "finding": None,
        "notes": "JLC C41283, extended, 182,901 in stock 2026-10-15; $0.0467 at 500+ (1,500 pcs). Replaces TL431AIDBZR "
                 "(C23892) on the same DBZ pads: the A grade's 25 C tolerance (+-25 mV) and VI(dev) dominated the s43 / "
                 "s44 window widths (S16 rss_contrib). Bands: " + MDREL + "."}


def main():
    led = json.loads(LEDGER.read_text())
    E = led["entries"]
    new = {
        "TL431AIDBZR": [("TL431BIDBZR", tl431b())],
        "TL431BIDBZR": [("TL431BIDBZR", tl431b())],
        "RT0603BRD077K68L": [
            ("RT0603BRD07750RL", resistor("RT0603BRD07750RL", 750.0, ["R81", "R99", "R114"], "neg-UV tap top", "C861551", 2661, 0.0271)),
            ("RT0603BRD072K94L", resistor("RT0603BRD072K94L", 2940.0, ["R83", "R101", "R116"], "neg-OV tap top", "C705761", 8015, 0.0441))],
        "RT0603BRD07120KL": [
            ("RT0603BRD0790K9L", resistor("RT0603BRD0790K9L", 90900.0, ["R85", "R103", "R118"], "span-UV tap top", "C728600", 18027, 0.0331))],
        "ARG03BTC1333": [
            ("RT0603BRD07104KL", resistor("RT0603BRD07104KL", 104000.0, ["R87", "R105", "R120"], "span-OV tap top", "C861070", 8450, 0.0212))],
    }
    for k in ("RT0603BRD07750RL", "RT0603BRD072K94L"):
        new[k] = [x for x in new["RT0603BRD077K68L"] if x[0] == k]
    new["RT0603BRD0790K9L"] = new["RT0603BRD07120KL"]
    new["RT0603BRD07104KL"] = new["ARG03BTC1333"]
    out, done = {}, set()
    for k, v in E.items():
        if k in new:
            for nk, nv in new[k]:
                if nk not in done:
                    out[nk] = nv
                    done.add(nk)
        else:
            out[k] = v
    e = out["RT0603BRD074K42L"]
    e["designators"] = ["R79", "R97", "R112"]
    e["function"] = "4.42 k 0.1 %: rail-monitor halfref top (stage 45, S16 option 1c-4420; was the neg-UV tap top)"
    e = out["RT0603BRD0710KL"]
    e["designators"] = [d for d in e["designators"] if d not in
                        ("R79", "R97", "R112", "R86", "R104", "R119", "R88", "R106", "R121")]
    e = out["RT0603BRD0711KL"]
    e["designators"] = ["R61", "R93", "R86", "R88", "R104", "R106", "R119", "R121"]
    e["function"] = "11 k 0.1 %: HS module feedback bottoms (R61 / R93) and, since stage 45, the rail-monitor span-UV / " \
                    "span-OV tap bottoms (S16 option 1c-4420)"
    d = out["2EDR8259XXUMA1"]
    s = next(x for x in d["stresses"] if x["parameter"] == "VDD at the span OV trip")
    v = round(ST["2EDR8259X_VDD_at_span_OV_trip"]["V"], 2)
    s["worst_case_value"] = v
    s["condition"] = ("s45 (S16 option 1c-4420): the span-OV worst-case upper corner (nominal 18.09 V); the stage runs up "
                      "to this span before the monitor disables DIS (was 17.84 V, the c25-driver nominal trip at the old values)")
    s["evidence"] = cite("- 2EDR8259X VDD at the span-OV trip")
    c = next(x for x in d["checks"] if x["stress"] == "VDD at the span OV trip")
    c["ratio"] = round(v / 21, 4)
    c["rule"] = f"<= 21 V operating ({v} V worst-case upper corner, {v / 21:.3f})"
    led["entries"] = out
    LEDGER.write_text(json.dumps(led, indent=1) + "\n")
    print("ledger: entries", len(out))


if __name__ == "__main__":
    main()
