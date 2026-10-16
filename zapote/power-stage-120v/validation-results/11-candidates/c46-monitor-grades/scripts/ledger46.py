#!/usr/bin/env python3
"""Stage 46 datasheet-ledger edit (the 125 C monitor grades): run after scripts/bands46.py and the s46 chain.

    python3 -I scripts/ledger46.py    -> native-21/verification/datasheet-ledger/ledger.json (in place)

* TL431BIDBZR -> TL431BQDBZR (U17 / U19 / U21): the Q temperature grade, TA -40..125 C (SLVS543S 6.4 p.5), Vref and
  VI(dev) from Table 6.13 p.14; stresses at the s46 125 C band basis (results/bands-s46.md); the local temperature is the
  B3 hot-copper gated row of this board (b3-ratings/margins.json, solved on the s46 board).
* LM339BIDR (UNAUDITED) -> LM2901BIDR (U29 / U30 / U31), audited: SLCS006Z 6.1 p.5, 6.4 p.6, 6.6 p.6, 6.8 p.8.
* 2EDR8259XXUMA1 "VDD at the span OV trip" -> the s46 span-OV worst-case upper corner (125 C basis).
Every stress is cited to its line in results/bands-s46.md or to the B3 margins row. Re-running it on the edited ledger
gives the same file.
"""
import sys as _s; _s.dont_write_bytecode = True
import json, re
from pathlib import Path

HERE = Path(__file__).resolve().parent
PS = HERE.parents[3]
LEDGER = PS / "native-21/verification/datasheet-ledger/ledger.json"
RES = HERE.parent / "results"
B = json.loads((RES / "bands-s46.json").read_text())
MD = (RES / "bands-s46.md").read_text().splitlines()
MDREL = str((RES / "bands-s46.md").relative_to(PS))
MARGINS = PS / "validation-results/04-board-current-thermal/round5-native21/b3-ratings/margins.json"
KELVIN = PS / "validation-results/02-protection-timing/kelvin/kelvin_plane.py"
ST = B["stresses_125C"]
TL_DS_SHA = "ed2e90697de4e2c5"
LM_DS_SHA = "406e7bd1ab1f2fb1"


def cite(prefix):
    hits = [i + 1 for i, l in enumerate(MD) if l.startswith(prefix)]
    assert len(hits) == 1, (prefix, hits)
    return f"{MDREL}:{hits[0]}"


def b3_rows(refs):
    """The gated B3 monitor rows of this board: {ref: {case: (est C, limit C, item)}}; margins.json must be solved on
    the s46 board (the kelvin_plane.py pin the chain writes for native21s46)."""
    pin = re.search(r'"native21s46": "([0-9a-f]{64})"', KELVIN.read_text()).group(1)
    m = json.loads(MARGINS.read_text())
    assert set(m["board_sha256"].values()) == {pin}, ("margins.json is not the s46 board", m["board_sha256"], pin)
    out = {r: {} for r in refs}
    for c, rows in m["cases"].items():
        for it in rows:
            ref = it["item"].split(":")[0]
            if ref in out:
                out[ref][c] = (round(it["est_c"], 1), it["limit_c"], it["item"])
    rel = str(MARGINS.relative_to(PS))
    return out, rel, pin, m["basis"]["cases"]


def temp_stress_check(rows, refs, rel, pin, basis, lim):
    rel_case = next(c for c, v in basis.items() if v["role"] == "release")
    worst_rel = max(refs, key=lambda r: rows[r][rel_case][0])
    worst_all = max(((r, c) for r in refs for c in rows[r]), key=lambda x: rows[x[0]][x[1]][0])
    t_rel, t_all = rows[worst_rel][rel_case][0], rows[worst_all[0]][worst_all[1]][0]
    stresses = [
        {"parameter": "Local temperature, release case", "worst_case_value": t_rel, "unit": "C",
         "condition": f"B3 hot-copper gated row (pad-copper max + P x RthJA), {rel_case} at bay "
                      f"{basis[rel_case]['bay_c']:g} C, worst of {' / '.join(refs)} ({worst_rel}); board {pin[:8]}",
         "evidence": f"{rel} cases.{rel_case} '{worst_rel}:' row"},
        {"parameter": "Local temperature, BASIS max", "worst_case_value": t_all, "unit": "C",
         "condition": f"same rows, worst over the BASIS cases ({worst_all[0]} at {worst_all[1]})",
         "evidence": f"{rel} cases.{worst_all[1]} '{worst_all[0]}:' row"}]
    checks = [
        {"id": "temperature, release case", "rating": "Free-air temperature max", "stress": "Local temperature, release case",
         "max_ratio": 1.0, "severity": "violation", "rule": f"{t_rel} C <= {lim:g} C (B3 gate row)", "ratio": round(t_rel / lim, 4)},
        {"id": "temperature, BASIS max", "rating": "Free-air temperature max", "stress": "Local temperature, BASIS max",
         "max_ratio": 1.0, "severity": "violation", "rule": f"{t_all} C <= {lim:g} C", "ratio": round(t_all / lim, 4)}]
    return stresses, checks


FAULT_GAP = ("the fault-case span is a stated case, not a bound: V24_RAW nominal 24 V on the span (LS LDO pass short); "
             "PS2's own output tolerance / OVP and the RECOM feedback-open output are not in the ledger")
B3_GAP = ("the local temperature is the B3 body-model estimate (pad copper as the die / ambient proxy, hot copper, "
          "still air at the BASIS bays), not a measurement; the band analysis is bounded at the 125 C rated maximum "
          f"({MDREL})")


def tl431bq(rows, rel, pin, basis):
    t = ST["TL431"]
    l46 = cite("- TL431BQ: VKA max")
    refs = ["U17", "U19", "U21"]
    ts, tc = temp_stress_check(rows, refs, rel, pin, basis, 125.0)
    return {
        "mpn": "TL431BQDBZR", "designators": refs, "class": "SIGNAL",
        "function": "Rail-monitor reference (REF tied to K, fed by rref 2.2 k), LS / HS-A / HS-B; B grade since stage 45 "
                    "(S16 option 1c-4420, DECISIONS 59), Q temperature grade since stage 46 (S17 hot copper)",
        "status": "PARTIAL",
        "datasheet": {"url": "https://www.ti.com/lit/ds/symlink/tl431.pdf",
                      "revision": "TI SLVS543S, Aug 2004, revised May 2024", "fetched": "2026-10-15", "repo_copy": None,
                      "note": "S16 study download, copied to runs-native21/s46/dl; not committed. Table 6.13 p.14 "
                              "(TL431BQ): Vref 2483 / 2495 / 2507 mV at 25 C, VKA = Vref, IKA 10 mA; VI(dev) 14 typ / 34 "
                              "max mV (max - min over the rated temperature range, note 1); |ZKA| 0.5 ohm max; Imin 0.7 mA "
                              "max (the BI row's numbers, Table 6.12 p.13, over the wider range). Table 6.1 p.5 abs max VKA "
                              "37 V, IKA -100..150 mA, TJ 150 C; Table 6.4 p.5 recommended VKA Vref..36 V, IKA 1..100 mA, "
                              "TL43xxQ TA -40..125 C; Table 6.3 p.5 DBZ RthJA 206 C/W; p.4 DBZ pins 1 = cathode, 2 = REF, "
                              "3 = anode (all grades); orderable TL431BQDBZR p.39, -40 to 125 C",
                      "sha256_prefix16": TL_DS_SHA},
        "ratings": [
            {"parameter": "Cathode voltage, recommended max", "datasheet_limit": 36, "unit": "V",
             "basis": "recommended operating conditions", "source": "Table 6.4 p.5"},
            {"parameter": "Cathode current, recommended max", "datasheet_limit": 100, "unit": "mA",
             "basis": "recommended operating conditions (minimum 1 mA)", "source": "Table 6.4 p.5"},
            {"parameter": "Free-air temperature max", "datasheet_limit": 125, "unit": "C",
             "basis": "TL43xxQ operating range -40..125 C (TL43xxI: 85 C)", "source": "Table 6.4 p.5"},
            {"parameter": "Vref at 25 C, B grade", "datasheet_limit": 2.507, "unit": "V",
             "basis": "2.483-2.507 V; the S16 band model takes this range +- VI(dev)", "source": "Table 6.13 p.14"},
            {"parameter": "VI(dev) max", "datasheet_limit": 0.034, "unit": "V",
             "basis": "deviation over the full rated temperature range (-40..125 C for the Q grade), max - min (not a TC)",
             "source": "Table 6.13 p.14"}],
        "stresses": [
            {"parameter": "Cathode voltage", "worst_case_value": t["vka_max_V"], "unit": "V",
             "condition": "REF tied to K: VKA = Vref <= 2.507 + 0.034 V", "evidence": l46},
            {"parameter": "Cathode current, operating max", "worst_case_value": t["ik_max_op_mA"], "unit": "mA",
             "condition": "span at the span-OV worst-case upper corner (125 C basis), rref -2 %, Vref low, halfref divider "
                          f"high (minimum {t['ik_min_mA']} mA at the span-UV lower corner, >= 1 mA)", "evidence": l46},
            {"parameter": "Cathode current, fault case", "worst_case_value": t["ik_max_fault_mA"], "unit": "mA",
             "condition": f"span at V24_RAW 24 V (LS LDO pass short; stated case, not a bound); {t['p_max_fault_mW']} mW, "
                          f"{t['self_heat_fault_K']} K self-heat at 206 C/W", "evidence": l46}] + ts,
        "derating_rule": "VKA and IKA inside the recommended operating conditions (IKA >= 1 mA); ambient <= 125 C (Q grade).",
        "checks": [
            {"id": "VKA", "rating": "Cathode voltage, recommended max", "stress": "Cathode voltage", "max_ratio": 1.0,
             "severity": "violation", "rule": f"{t['vka_max_V']} V <= 36 V", "ratio": round(t["vka_max_V"] / 36, 4)},
            {"id": "IKA operating", "rating": "Cathode current, recommended max", "stress": "Cathode current, operating max",
             "max_ratio": 1.0, "severity": "violation", "rule": f"{t['ik_max_op_mA']} mA <= 100 mA",
             "ratio": round(t["ik_max_op_mA"] / 100, 4)},
            {"id": "IKA fault", "rating": "Cathode current, recommended max", "stress": "Cathode current, fault case",
             "max_ratio": 1.0, "severity": "violation", "rule": f"{t['ik_max_fault_mA']} mA <= 100 mA",
             "ratio": round(t["ik_max_fault_mA"] / 100, 4)}] + tc,
        "layout_guidance": [{"item": "REF tied to K on the 'ref' net; anode on the rail's n", "enforced_by": "audit_f6.rs"}],
        "gaps": [B3_GAP, FAULT_GAP,
                 "Vref long-term (load-life) drift is not specified (only VI(dev) over temperature); covered only by the "
                 "0.5 % margin target of the band analysis"],
        "finding": None,
        "notes": "JLC C190245, extended, 17,789 in stock 2026-10-15; $0.0744 at 500+ (1,500 pcs). Replaces TL431BIDBZR "
                 "(C41283) on the same DBZ pads: at the c18 @ 61 release case the I grade read -7.7 / +3.1 / -0.5 K on the "
                 "s42 board (b3-ratings/monitor-probes-2026-10-15). Bands at the 125 C basis: " + MDREL + "."}


def lm2901b(rows, rel, pin, basis):
    refs = ["U29", "U30", "U31"]
    ts, tc = temp_stress_check(rows, refs, rel, pin, basis, 125.0)
    span_hi, span_lo = ST["basis"]["span_op_max_V"], ST["basis"]["span_op_min_V"]
    l_span = cite("- LM2901B: supply = span")
    l_ovw = cite("| span OV | 17.5692")
    vivr = round(span_lo - 2.0, 3)
    # largest comparator input in operation: the span-OV tap at the span-OV upper corner, 11 k / 115 k (bands-s46 values)
    rt, rb = B["values"]["taps"]["span OV"]
    vin = round(span_hi * rb / (rt + rb), 3)
    i_sink = round(5.0 / (10e3 * 0.99) * 1e3, 3)     # rpull 0603WAF1002T5E 10 k 1 % from the 5 V LDO (one per wired-AND)
    return {
        "mpn": "LM2901BIDR", "designators": refs, "class": "SIGNAL",
        "function": "Rail-monitor quad comparator (four windows wired-AND onto 'good', no hysteresis), LS / HS-A / HS-B; "
                    "the 125 C grade since stage 46 (S17 hot copper; LM339BIDR before)",
        "status": "PARTIAL",
        "datasheet": {"url": "https://www.ti.com/lit/ds/symlink/lm339b.pdf",
                      "revision": "TI SLCS006Z, Oct 1979, revised May 2025", "fetched": "2026-10-15", "repo_copy": None,
                      "note": "S16 study download, copied to runs-native21/s46/dl; not committed. 6.1 p.5 (LM339B and "
                              "LM2901B) abs max supply 38 V, inputs -0.3..38 V, output pin 38 V, output sink 25 mA, TJ "
                              "150 C; 6.4 p.6 recommended supply 2..36 V, LM2901B TA -40..125 C, input range (V-) - 0.1 .. "
                              "(V+) - 2.0 V; 6.6 p.6 D (SOIC) RthJA 111.2 C/W; 6.8 p.8 (LM2901B) VIO +-3.5 mV at 25 C, "
                              "+-5.5 mV over -40..125 C, IB <= 50 nA, VOL <= 550 mV at 4 mA over temperature, IQ <= 1.6 mA "
                              "at 36 V; Table 5-1 p.4 D pinout (one table for LM339B and LM2901B); orderable LM2901BIDR "
                              "p.28, SOIC (D) 14, -40 to 125 C",
                      "sha256_prefix16": LM_DS_SHA},
        "ratings": [
            {"parameter": "Supply voltage, recommended max", "datasheet_limit": 36, "unit": "V",
             "basis": "recommended operating conditions (2..36 V)", "source": "6.4 p.6"},
            {"parameter": "Free-air temperature max", "datasheet_limit": 125, "unit": "C",
             "basis": "LM2901B TA -40..125 C (LM339B: 85 C)", "source": "6.4 p.6"},
            {"parameter": "Input voltage range max at the lowest operating span", "datasheet_limit": vivr, "unit": "V",
             "basis": f"(V+) - 2.0 V at V+ = {span_lo} V, the span-UV worst-case lower corner (only one input of a pair "
                      "needs to be in range, 6.7 / 6.8 note 1)", "source": "6.4 p.6; 6.8 p.8 note 1"},
            {"parameter": "Output sink current, abs max", "datasheet_limit": 25, "unit": "mA",
             "basis": "absolute maximum", "source": "6.1 p.5"},
            {"parameter": "VIO over temperature", "datasheet_limit": 0.0055, "unit": "V",
             "basis": "-40..125 C, VS 5..36 V; used by the band analysis", "source": "6.8 p.8"}],
        "stresses": [
            {"parameter": "Supply voltage, operating max", "worst_case_value": span_hi, "unit": "V",
             "condition": "V+ - V- = the span, at the span-OV worst-case upper corner (125 C basis); the 24 V V24_RAW fault "
                          "case is 0.667 of 36 V", "evidence": l_span},
            {"parameter": "Input voltage, operating max", "worst_case_value": vin, "unit": "V",
             "condition": f"span-OV tap at the span-OV upper corner ({span_hi} V x {rb:g} / {rt + rb:g}); halfref <= 1.76 V, "
                          "the neg taps <= 1.61 V", "evidence": l_ovw},
            {"parameter": "Output sink current", "worst_case_value": i_sink, "unit": "mA",
             "condition": "fault state: the 10 k 1 % pull-up (rpull) from the 5 V LDO into the wired-AND outputs",
             "evidence": "elec/src/f6_bias.ato RailMonitor rpull / ldo5"}] + ts,
        "derating_rule": "Supply and inputs inside the recommended operating conditions; output sink under the abs max; "
                         "ambient <= 125 C.",
        "checks": [
            {"id": "VS", "rating": "Supply voltage, recommended max", "stress": "Supply voltage, operating max", "max_ratio": 1.0,
             "severity": "violation", "rule": f"{span_hi} V <= 36 V", "ratio": round(span_hi / 36, 4)},
            {"id": "VIN", "rating": "Input voltage range max at the lowest operating span", "stress": "Input voltage, operating max",
             "max_ratio": 1.0, "severity": "violation", "rule": f"{vin} V <= {vivr} V", "ratio": round(vin / vivr, 4)},
            {"id": "IOL", "rating": "Output sink current, abs max", "stress": "Output sink current", "max_ratio": 1.0,
             "severity": "violation", "rule": f"{i_sink} mA <= 25 mA", "ratio": round(i_sink / 25, 4)}] + tc,
        "layout_guidance": [{"item": "same SOIC-14 pads and nets as the LM339BIDR (BOM-only stage)",
                             "enforced_by": "audit.rs (IDENTITY) and prototype-closure/pcb/pin_functions21.py (supply / output net check)"}],
        "gaps": [B3_GAP, FAULT_GAP,
                 "fault states where src floats to P (R77 / TLVH431 open) put the UV tap above (V+) - 2 V; the paired input "
                 "(halfref) stays in range, which the datasheet note 1 (6.8 p.8) says is sufficient"],
        "finding": None,
        "notes": "JLC C22427890, extended, 1,966 in stock 2026-10-15 against 1,500 for 500 boards (buy early); $0.1266 at "
                 "500+ (1,500 pcs). Replaces LM339BIDR (C22416291) on the same SOIC-14 pads: at the c18 @ 61 release case "
                 "the LM339B read -17.9 / -11.6 / -16.5 K on the s42 board (b3-ratings/monitor-probes-2026-10-15). "
                 "Bands at the 125 C basis: " + MDREL + "."}


def main():
    led = json.loads(LEDGER.read_text())
    E = led["entries"]
    rows, rel, pin, basis = b3_rows(["U17", "U19", "U21", "U29", "U30", "U31"])
    new = {"TL431BIDBZR": ("TL431BQDBZR", tl431bq(rows, rel, pin, basis)),
           "TL431BQDBZR": ("TL431BQDBZR", tl431bq(rows, rel, pin, basis)),
           "LM339BIDR": ("LM2901BIDR", lm2901b(rows, rel, pin, basis)),
           "LM2901BIDR": ("LM2901BIDR", lm2901b(rows, rel, pin, basis))}
    out, done = {}, set()
    for k, v in E.items():
        if k in new:
            nk, nv = new[k]
            if nk not in done:
                out[nk] = nv
                done.add(nk)
        else:
            out[k] = v
    d = out["2EDR8259XXUMA1"]
    s = next(x for x in d["stresses"] if x["parameter"] == "VDD at the span OV trip")
    v = round(ST["2EDR8259X_VDD_at_span_OV_trip"]["V"], 2)
    s["worst_case_value"] = v
    s["condition"] = ("s46 (S16 option 1c-4420 values on the 125 C grades, band at -10..125 C): the span-OV worst-case upper "
                      "corner (nominal 18.09 V); the stage runs up to this span before the monitor disables DIS (s45 at the "
                      "85 C basis: 18.60 V; was 17.84 V, the c25-driver nominal trip at the pre-s45 values)")
    s["evidence"] = cite("- 2EDR8259X VDD at the span-OV trip")
    c = next(x for x in d["checks"] if x["stress"] == "VDD at the span OV trip")
    c["ratio"] = round(v / 21, 4)
    c["rule"] = f"<= 21 V operating ({v} V worst-case upper corner, {v / 21:.3f})"
    led["entries"] = out
    LEDGER.write_text(json.dumps(led, indent=1) + "\n")
    print("ledger: entries", len(out))


if __name__ == "__main__":
    main()
