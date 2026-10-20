#!/usr/bin/env python3
"""Apply the c54 desk pass to the datasheet ledger (idempotent; stdlib only).

    python3 -I validation-results/11-candidates/c54-ledger-desk/scripts/net_stress.py
    python3 -I validation-results/11-candidates/c54-ledger-desk/scripts/signal_audit.py
    python3 -I validation-results/11-candidates/c54-ledger-desk/scripts/cx_current.py
    python3 -I validation-results/11-candidates/c54-ledger-desk/scripts/apply_ledger.py
    python3 -I native-21/verification/datasheet-ledger/gate.py

What it does to native-21/verification/datasheet-ledger/ledger.json:
  1. merges results/signal_audit.json (51 SIGNAL lines): datasheet record where the line had none, electrical ratings /
     stresses (replace by parameter), checks (replace by id; ratio = stress / limit, recomputed here), derating rule,
     function text where given, new gaps; drops the 'Not audited (outside SAFETY/POWER).' and the temp-ratings 'only
     the temperature rating is audited' gaps; SN74LVC1G132 loses its +5 % VCC stand-in (the registry bounds the LS
     5 V at 5.11 V) and the gap that carried it;
  2. drops the stale 'Not audited' gap from RT0603BRD077K5L / RT0603BRD0716KL (they already carry V / P checks);
  3. works the eight 'desk:' gaps (R5 mesh correction, bank F_T chord and approval basis, C5/C6 footprint name, L1
     digitisation and ALT-D3 stray, C1/C2 ripple current, R1/R2 surge Vc) and the S21 record fixes (30KPA150CA maker,
     TPS7A4700 text);
  4. recomputes each touched entry's status by the gate's rule (failing violation check -> VIOLATION; any gap or
     failing gap check -> PARTIAL; else VERIFIED) and writes datasheets/records.json (sha re-verified on the local
     copies) and results/apply_log.md.
"""
import datetime
import hashlib
import json
import math
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
LANE = HERE.parent
UNIT = HERE.parents[3]
LEDGER = UNIT / "native-21/verification/datasheet-ledger/ledger.json"
REL = "validation-results/11-candidates/c54-ledger-desk"
TAG = "c54 (2026-10-18"
MARGINS = "validation-results/04-board-current-thermal/round5-native21/b3-ratings/margins.json"
B3 = "validation-results/04-board-current-thermal/round5-native21/b3-ratings"

DROP = ("Not audited (outside SAFETY/POWER).",
        "[temp-ratings 2026-10-15] only the temperature rating is audited")
log = []


def md_line(name, prefix):
    for i, t in enumerate((LANE / "results" / name).read_text().splitlines(), 1):
        if t.startswith(prefix):
            return f"{REL}/results/{name}:{i}"
    raise SystemExit(f"{name}: no line starting {prefix!r}")


def set_by(lst, key, item):
    for i, x in enumerate(lst):
        if x.get(key) == item[key]:
            lst[i] = item
            return
    lst.append(item)


def ratio_of(e, chk):
    r = next(x for x in e["ratings"] if x["parameter"] == chk["rating"])
    s = next(x for x in e["stresses"] if x["parameter"] == chk["stress"])
    assert r["unit"] == s["unit"], (e["mpn"], chk["id"])
    return round(s["worst_case_value"] / r["datasheet_limit"], 4)


def add_check(e, chk):
    chk = dict(chk)
    chk["ratio"] = ratio_of(e, chk)
    set_by(e["checks"], "id", chk)


def add_gap(e, g):
    if g not in e["gaps"]:
        e["gaps"].append(g)


def replace_gap(e, startswith, new):
    for i, g in enumerate(e["gaps"]):
        if g.startswith(startswith) or g == new:
            e["gaps"][i] = new
            return
    raise SystemExit(f"{e['mpn']}: no gap starting {startswith!r}")


def note(e, text):
    cur = e.get("notes") or ""
    if TAG not in cur:
        e["notes"] = (cur + " " if cur else "") + text


def status(e):
    fails_v = fails_g = False
    for c in e["checks"]:
        if c["ratio"] > c["max_ratio"] + 1e-9:
            fails_v |= c["severity"] == "violation"
            fails_g |= c["severity"] == "gap"
    if fails_v:
        return "VIOLATION"
    if e["gaps"] or fails_g:
        return "PARTIAL"
    return "VERIFIED"


def sha16(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]
    except OSError:
        return None


# ---------------------------------------------------------------------------------------------------------------
# 1. SIGNAL lines from signal_audit.json
# ---------------------------------------------------------------------------------------------------------------
def merge_signal(L, audit, records):
    for mpn, a in audit.items():
        e = L[mpn]
        ds = a["datasheet"]
        got = sha16(ds["local"])
        rec = records.setdefault(a["datasheet_key"], {
            "url": ds["url"], "revision": ds["revision"], "sha256_prefix16": ds["sha"], "local_copy": ds["local"],
            "sha_reverified_2026_10_18": got == ds["sha"], "file_date": None, "lines": [], "pages_used": set()})
        if got != ds["sha"]:
            raise SystemExit(f"{mpn}: local copy sha {got} != recorded {ds['sha']}")
        rec["file_date"] = datetime.date.fromtimestamp(Path(ds["local"]).stat().st_mtime).isoformat()
        rec["lines"].append(mpn)
        for r in a["ratings"]:
            for p in re.findall(r"(?:p\.|sheet)\s?(\d+)", r["source"]):
                rec["pages_used"].add(int(p))
        if e["datasheet"] is None:
            e["datasheet"] = {"url": ds["url"], "revision": ds["revision"], "fetched": rec["file_date"],
                              "repo_copy": None, "sha256_prefix16": ds["sha"],
                              "note": f"c54 desk pass: electrical ratings read from the local copy {ds['local']} (outside "
                                      f"the repo; sha256 prefix re-verified 2026-10-18; 'fetched' is that file's date). "
                                      f"Page numbers are PDF page indices. Record: {REL}/datasheets/records.json."}
        if mpn == "SN74LVC1G132DBVR":  # the +5 % stand-in is replaced by the registry's 5.11 V
            e["checks"] = [c for c in e["checks"] if c["id"] != "VCC"]
            e["stresses"] = [s for s in e["stresses"] if not (s["parameter"] == "VCC" and "+5 %" in s["condition"])]
            e["gaps"] = [g for g in e["gaps"] if not g.startswith("The LS 5 V tolerance (TPS70950")]
        for r in a["ratings"]:
            set_by(e["ratings"], "parameter", r)
        for s in a["stresses"]:
            set_by(e["stresses"], "parameter", s)
        for c in a["checks"]:
            add_check(e, c)
        if a["derating_rule"] and a["derating_rule"] not in e["derating_rule"]:
            e["derating_rule"] = (e["derating_rule"] + " " if e["derating_rule"] else "") + "Electrical (c54): " + a["derating_rule"]
        if a.get("function"):
            e["function"] = a["function"]
        e["gaps"] = [g for g in e["gaps"] if not g.startswith(DROP)]
        for g in a["add_gaps"]:
            add_gap(e, g)
            if g.startswith("finding"):
                e["finding"] = g
        extra = ""
        if mpn == "SN74LVC1G132DBVR":
            extra = (" The VCC stress is now the pin_absmax registry's LS 5 V maximum, 5.11 V (TPS70950-Q1 +/-1 % + line "
                     "+ load), replacing the +5 % stand-in and its gap; the oscillator period range 0.42-2.09 us that was "
                     "worked at +/-5 % is a superset of the 4.89-5.11 V band.")
        note(e, f"{TAG}, {REL}): electrical ratings and worst-case stresses added (signal_audit.md; stresses from the "
                f"pin_absmax net model, scripts/net_stress.py); the 'Not audited' / 'only the temperature rating is "
                f"audited' gaps are closed by them.{extra}")
        log.append(f"{mpn}: merged {len(a['ratings'])} ratings, {len(a['stresses'])} stresses, {len(a['checks'])} checks; "
                   f"+{len(a['add_gaps'])} gaps")


# ---------------------------------------------------------------------------------------------------------------
# 3. desk gaps and record fixes
# ---------------------------------------------------------------------------------------------------------------
def desk_r5(e):
    for s in e["stresses"]:
        if s["parameter"] == "T element c17.5 (release)":
            s["condition"] = ("release case c17.5_h10, bay 61 C (B3 gate estimate; R5's element converges slowly, p ~ 0.2, "
                              "and the gate under-corrects it, b3_ratings_gate.py:21-23; see the mesh-corrected row)")
            s["evidence"] = [x if not isinstance(x, str) else re.sub(r"b3_ratings_gate\.py:21(?![-0-9])", "b3_ratings_gate.py:21-23", x)
                             for x in s["evidence"]]
    set_by(e["stresses"], "parameter", {
        "parameter": "T element c17.5 (release), worst audited mesh correction", "worst_case_value": 130.1, "unit": "C",
        "condition": "B3 element 124.1 C at the release case (c17.5_h10, bay 61 C) + 6 K, the largest under-correction of "
                     "R5's element the B3 audit measured (gate_control G6: 4-6 K low at c22 / c28 h10, where the mesh "
                     "increment is larger than at the release case)",
        "evidence": [{"file": MARGINS, "b3_row": {"case": "c17.5_h10", "item": "R5: element max"}, "est_c": 124.1},
                     f"{B3}/audit-2026-10-15/README.md:130-131", f"{B3}/b3_ratings_gate.py:21-23"]})
    add_check(e, {"id": "element c17.5 (release), mesh-corrected", "rating": "T operating max",
                  "stress": "T element c17.5 (release), worst audited mesh correction", "max_ratio": 0.85,
                  "severity": "violation", "rule": "130.1 C <= 85 % of 170 C (144.5 C) with the worst audited +6 K"})
    replace_gap(e, "desk: the B3 element estimate",
                "B3-estimate: R5's element temperature is the B3 body-model estimate, not a measurement. With the largest "
                "mesh under-correction the B3 audit measured (+6 K, G6) it is 130.1 C at the release case, 0.765 of "
                "170 C (85 % rule 0.85); that correction was measured at c22 / c28 only. Closing test (bench): "
                "thermocouple or IR on R5 at the 18.375 A release trip, still air, bay 61 C (or scaled from a measured bay).")


def desk_bank(e):
    ft60 = 11.03 / 9.17
    ta = 67.48
    ft = ft60 + (1.0 - ft60) * (ta - 60.0) / 25.0
    allow = round(20.0 * ft * ft, 2)
    set_by(e["ratings"], "parameter", {
        "parameter": "Self-heating allowance at T_A (24 A step, table chord)", "datasheet_limit": allow, "unit": "K",
        "basis": f"20 K x F_T(67.48 C)^2 with F_T on the straight chord between the two IRMS table points: F_T(60 C) = "
                 f"11.03 / 9.17 = {ft60:.4f}, F_T(85 C) = 1.000, so F_T(67.48 C) = {ft:.4f} and the allowance {allow} K. "
                 f"Lower than the digitised p.22 curve (1.160, 26.92 K) and than a straight line between the table's own "
                 f"self-heating limits (30 K at 60 C, 20 K at 85 C: 27.0 K)",
        "source": "TDK B3264*H June 2026 p.14 ordering table (IRMS,max 100 kHz 11.03 A at TA 60 C, dT <= 30 C; 9.17 A at "
                  "85 C, dT <= 20 C); p.22 F_T(TA)"})
    add_check(e, {"id": "self-heating 24 A, declared airflow (table chord)",
                  "rating": "Self-heating allowance at T_A (24 A step, table chord)",
                  "stress": "Self-heating 24 A, declared airflow", "max_ratio": 1.0, "severity": "violation",
                  "rule": f"20.01 K <= {allow} K (F_T on the chord of the two published table points; no curve digitisation)"})
    replace_gap(e, "desk: the F_T credit",
                f"owner (maker question): F_T between the published table points. The 24 A step holds on the straight chord "
                f"between the two IRMS table points ({allow} K, ratio {20.01 / allow:.3f}) and on the digitised p.22 curve "
                f"(26.92 K, 0.743); with no interpolation credit at all (F_T = 1, the 85 C value) it is 20.01 / 20 K = 1.0005. "
                f"Closing answer: TDK confirms F_T(67.5 C) >= {ft:.2f} (or the allowed self-heating at TA 67.5 C); the bench "
                f"single-part rise test above settles it too.")
    replace_gap(e, "desk: approval basis",
                "certifier: approval basis. HOT-side resonant-tank part with no UL / ENEC component file (none is listed or "
                "normally needed for a tank film cap): case UL 94 V-0 (p.2); AEC-Q200D and IEC 60384-16:2019 (p.15); THB "
                "85 C / 85 % RH 1000 h (p.24). Closing answer: the certifier accepts it under the end-product evaluation "
                "(abnormal-operation tests with the bank in circuit).")


def desk_c5c6(e):
    replace_gap(e, "desk: the footprint is named",
                "owner (library record): the C5 / C6 footprint is named temper:TDK_B32656G0275J000_4Pin_P37.50_P20.30_"
                "ReviewOnly (native-21/frozen/default.csv:10; elec/src/parts.ato:211) after the superseded 2.7 uF part; "
                "the pads (P37.5 / P20.3 four-pin) match B32676G (TDK p.10). Closing answer: rename the library footprint at "
                "the next layout revision (record only, no copper change).")


def desk_l1(e):
    iop = 24.0 * (0.9928 - 0.03)
    replace_gap(e, "desk: derating curve digitised",
                f"bench (merged with the L1 local-air gap above): the p.5 derating curve is digitised (+/-3 % of full scale, "
                f"boundary +/-2 C). It does not move the release check: with Iop/IR at 61 C read 3 % low ({iop:.2f} A) 15 A "
                f"is {15 / iop:.3f} of Iop (0.630 as read). It moves only the 82.5 C boundary of the local-air gap, which the "
                f"same bench measurement (L1 local air at the release case) closes.")
    replace_gap(e, "desk: the ALT-D3 surge model",
                "model-estimate: the ALT-D3 surge model carries the CMC's 18 uH DM stray inside a 250-500 uH line-inductance "
                "range; this part's 8 uH lowers the loop inductance by at most 10 / 268 = 3.7 % (at 250 uH), i.e. about "
                "2-4 % more surge current (I ~ L^-1/2 to L^-1). Not re-run: ALT-D3's surge.py / cwg_fit.py are not "
                "committed in the repo. Closing: commit ALT-D3's surge model and re-run it at 8 uH (owner), or the surge-lab "
                "capture of the RV1 / D3 currents.")


def desk_cx(e):
    cx = json.loads((LANE / "results/cx_current.json").read_text())["worst"]
    rel = cx["x2 pan_18.375A board alone"]["irms_line_cycle_A"]
    rel_m = cx["x2 pan_18.375A with module"]["irms_line_cycle_A"]
    rel = max(rel, rel_m)
    c28 = max(cx["x2 pan_28A board alone"]["irms_line_cycle_A"], cx["x2 pan_28A with module"]["irms_line_cycle_A"])
    c1 = max(cx[f"x1 {c} with module"]["irms_line_cycle_A"] for c in ("pan_18.375A", "pan_22A", "nopan_22A"))
    c1_28 = cx["x1 pan_28A with module"]["irms_line_cycle_A"]
    i70 = 1.5
    th = 92.4
    ith = round(i70 * math.sqrt((110.0 - th) / 40.0), 3)
    th_lim = 110.0 - 40.0 * (rel / i70) ** 2
    l_rel = [md_line("cx_current.md", "worst x2 pan_18.375A with module"), md_line("cx_current.md", "worst x2 pan_18.375A board alone")]
    l_28 = [md_line("cx_current.md", "worst x2 pan_28A with module"), md_line("cx_current.md", "worst x2 pan_28A board alone")]
    l_c1 = [md_line("cx_current.md", f"worst x1 {c} with module") for c in ("pan_18.375A", "pan_22A", "nopan_22A")]
    src = f"{REL}/scripts/cx_current.py"
    set_by(e["ratings"], "parameter", {
        "parameter": "Irms max 35-100 kHz, Th <= 70 C", "datasheet_limit": i70, "unit": "A",
        "basis": "Maximum current vs frequency, sinusoidal, Th <= 70 C, 22.5 mm lead spacing: the two upper traces read "
                 "about 1.5-1.6 A and 1.9-2.0 A over 35-100 kHz and the leader lines do not attribute the 1 uF trace "
                 "unambiguously, so the lower (1.5 A) is taken (c54 reading of the repo copy, 2026-10-18)",
        "source": "KEMET F3095_R46_X2_310_110C (2026-05-13) p.8, Lead Spacing 22.5 mm graph"})
    set_by(e["ratings"], "parameter", {
        "parameter": f"Irms max 35-100 kHz, Th {th} C", "datasheet_limit": ith, "unit": "A",
        "basis": f"1.5 A x sqrt(dTlim(Th) / 20 K): the p.6 'Maximum Irms vs Th' curve equals sqrt(dTlim / 20 K) of the "
                 f"p.6 'Maximum overtemperature dTlim vs Th' line (20 K up to 70 C, 0 at 110 C; 78 % at 85 C, 50 % at "
                 f"100 C on both); at Th {th} C (the L1 body beside C1 / C2 at the release case, used as Th) dTlim = 8.8 K",
        "source": "KEMET F3095_R46_X2_310_110C p.6 (Maximum Irms vs Th; Maximum Overtemperature dTlim vs Th); p.8"})
    set_by(e["stresses"], "parameter", {
        "parameter": "C2 ripple current, release (line-cycle RMS)", "worst_case_value": round(rel, 4), "unit": "A",
        "condition": "35-90 kHz current through C2 (the X2 cap at BR1's AC input, in parallel with the DC link while BR1 "
                     "conducts) at the 18.375 A release trip, pan present, Vc 198 V, worst fs and variant (inlet module or "
                     "not; L1 stray 8 / 18 uH; DC-link ESR 2.55 / 20 mOhm): the s19b network on the native-21 L1 and DC "
                     "link, crest RMS / sqrt 2 + 60 Hz (model estimate, crest condition: bridge always conducting, no trace "
                     "inductance between C2 and the DC link, both high-side)",
        "evidence": [src] + l_rel})
    set_by(e["stresses"], "parameter", {
        "parameter": "C2 ripple current, c28 (line-cycle RMS)", "worst_case_value": round(c28, 4), "unit": "A",
        "condition": "context: the same at the 28 A Kconfig ceiling (pan_28A)", "evidence": [src] + l_28})
    set_by(e["stresses"], "parameter", {
        "parameter": "C1 ripple current with the inlet module (line-cycle RMS)", "worst_case_value": round(max(c1, c1_28), 4),
        "unit": "A",
        "condition": "C1 (line side of L1) with the declared inlet module, worst of the release / 22 A / no-pan / 28 A "
                     "cases (board alone, a bench-only bypass at <= 300 W, it is 1.6-2.4 A at full power: the module is "
                     "required for C1 as well as for EMI)",
        "evidence": [src] + l_c1 + [md_line("cx_current.md", "worst x1 pan_28A with module")]})
    add_check(e, {"id": "C2 ripple, release, Th <= 70 C", "rating": "Irms max 35-100 kHz, Th <= 70 C",
                  "stress": "C2 ripple current, release (line-cycle RMS)", "max_ratio": 1.0, "severity": "gap",
                  "rule": f"{rel:.3f} A <= 1.5 A holds only while C2's Th <= 70 C (not evidenced); model estimate"})
    add_check(e, {"id": f"C2 ripple, release, Th {th} C", "rating": f"Irms max 35-100 kHz, Th {th} C",
                  "stress": "C2 ripple current, release (line-cycle RMS)", "max_ratio": 1.0, "severity": "gap",
                  "rule": f"{rel:.3f} A <= {ith} A at the L1-body Th: fails; the release case needs Th <= {th_lim:.1f} C"})
    add_check(e, {"id": "C2 ripple, c28, Th <= 70 C", "rating": "Irms max 35-100 kHz, Th <= 70 C",
                  "stress": "C2 ripple current, c28 (line-cycle RMS)", "max_ratio": 1.0, "severity": "gap",
                  "rule": f"airflow / ceiling route: {c28:.3f} A > 1.5 A at any Th"})
    add_check(e, {"id": f"C1 ripple with module, Th {th} C", "rating": f"Irms max 35-100 kHz, Th {th} C",
                  "stress": "C1 ripple current with the inlet module (line-cycle RMS)", "max_ratio": 1.0,
                  "severity": "violation", "rule": f"{max(c1, c1_28):.3f} A <= {ith} A"})
    finding = (f"{TAG}), model estimate, not a VIOLATION by the ledger rules (model stress, Th not evidenced): C2's 35-90 kHz "
               f"ripple current is {rel:.2f} A line-cycle RMS at the release ceiling and {c28:.2f} A at 28 A "
               f"(results/cx_current.md). KEMET's 22.5 mm limit is >= 1.5 A at Th <= 70 C (p.8, lower candidate trace), "
               f"derated by sqrt(dTlim / 20 K) above 70 C (p.6): the release case passes only while C2's Th (ambient or "
               f"hottest lead track) stays at or below {th_lim:.1f} C, and the 28 A case exceeds the rating at any Th. "
               f"Beside L1 (92.4 C body at the release case) the release case reads {rel / ith:.2f} of the rating.")
    e["finding"] = finding
    replace_gap(e, "desk: the 35-60 kHz differential-mode current",
                f"bench: C2 ripple current and Th. scripts/cx_current.py is a linear crest-condition estimate that reads "
                f"high (bridge always conducting, no trace inductance between C2 and the DC link): {rel:.2f} A line-cycle "
                f"RMS at the release trip against 1.5 A x sqrt((110 - Th) / 40 K) (KEMET p.6 / p.8), i.e. it needs Th <= "
                f"{th_lim:.1f} C. Closing test: current probe on a C2 lead plus a thermocouple on C2's leads / body at the "
                f"release ceiling and at every commissioned ladder step; pass if the measured RMS <= 1.5 A x sqrt((110 - "
                f"Th) / 40) at the measured Th.")
    add_gap(e, f"owner (28 A route): C2's modelled ripple at 28 A ({c28:.2f} A line-cycle RMS) is above the 22.5 mm 1 uF "
               f"rating (1.5 A at Th <= 70 C) at any Th. Before a ladder step above the release ceiling is commissioned: "
               f"measure it (bench gap above), or fit a higher-current X2 / a 27.5 mm part (p.8: >= 2 A) or add series "
               f"impedance between C2 and BR1 (layout change).")
    replace_gap(e, "bench: body temperature next to L1 / BR1",
                "bench: C1 / C2 body temperature next to L1 / BR1 is not evidenced: B3 has no C1 / C2 row; its L1 body is "
                "92.4 C at the release case (c17.5_h10, bay 61 C) and 87.8 / 90.4 C at c22 / c28 (bay 55 C), "
                f"{MARGINS} rows 'L1: B82726 climatic' (keyed); limit 110 C, and the ripple rating above derates from 70 C. "
                "Closing test: thermocouple on C1 / C2 at the release ceiling.")


def desk_r1r2(e):
    replace_gap(e, "desk: the pair voltage at 245-750 A",
                "bench: the R1 / R2 pair voltage at 245-750 A through RV1 (ALT-D3.md:119) is not in the repo; only Vc 455 V "
                "at 100 A is, and the overload check holds while Vc < 790 V. RV1's Figure 4 (Rev 10/01/19 p.3, 20 mm parts) "
                "is too dense to attribute a 750 A reading to the 175 V curve (re-read 2026-10-18, no value taken). Closing "
                "test: surge-lab capture of the RV1 voltage at the 1-2 kV combination wave (or Littelfuse's Vc at 750 A "
                "for TMOV20RP175E).")


def fix_30kpa(e):
    lf = ("Second source checked (c54, 2026-10-18): Littelfuse 30KPA Series, Revised BA.08/27/20 (LCSC C19111562 copy, "
          "sha256 1fe25d7c0973063d): p.2 row 30KPA150CA is identical to Good-Ark's (VR 150 V, VBR 167.60-184.36 V at 5 mA, "
          "IPP 129.8 A, IR 2 uA, VC 233.4 V); p.1 PPPM 30 kW (10/1000 us), IFSM 400 A, TJ / TSTG -55..175 C, RthJL 8.0 / "
          "RthJA 40 C/W typical, agency approval E230531 (UL), VBR(TJ) = VBR(25 C) x (1 + aT (TJ - 25)) with aT 0.1 %/C "
          "typical. The source (elec/src/parts.ato:233, manufacturer 'Good-Ark Semiconductor') and the consign record "
          "(sourcing/STOCK-2026-10-18-consign-r1.csv line 7: 'Global Sourcing (Good-Ark)', C19111562) name Good-Ark; LCSC's "
          "page carries Littelfuse's sheet. The ledger binds on Good-Ark (TJ 150 C); every electrical value is the same.")
    if "Second source checked (c54" not in e["datasheet"]["note"]:
        e["datasheet"]["note"] += " " + lf
    for r in e["ratings"]:
        if r["parameter"] == "Temperature rating (TJ)":
            r["basis"] = ("Operating junction and storage TJ, TSTG -55..+150 C (Good-Ark, the maker in the source and the "
                          "consign record); Littelfuse's identical-row 30KPA150CA (the sheet LCSC shows for C19111562, Rev "
                          "BA.08/27/20, sha 1fe25d7c0973063d) rates -55..175 C, RthJA 40 K/W typ; the lower is used "
                          "[temp-ratings 2026-10-15; maker record c54]")
    for i, g in enumerate(e["gaps"]):
        if g.startswith("[temp-ratings 2026-10-15] the local temperature") and "maker ambiguity" in g:
            e["gaps"][i] = g.split("; maker ambiguity")[0]
        if g.startswith("bench: hot clamp.") and "aT 0.1" not in g:
            e["gaps"][i] = g + (" Littelfuse's identical part gives aT 0.1 %/C typical (p.1): at a 100 C junction that is "
                                "+7.5 %, a 502 V string clamp, typical only, so the pulse qualification stays the closing test.")
    add_gap(e, "owner (maker record): the delivered maker is not recorded (Good-Ark in the source and the consign line; "
               "LCSC's C19111562 page shows Littelfuse's sheet). Closing answer: the maker on the delivered reel / CoC. If "
               "Littelfuse, TJ 175 C and UL E230531 apply and no check changes (identical electrical row).")


# ---------------------------------------------------------------------------------------------------------------
def main():
    doc = json.loads(LEDGER.read_text())
    L = doc["entries"]
    import subprocess
    head = subprocess.run(["git", "-C", str(UNIT), "show", "HEAD:./native-21/verification/datasheet-ledger/ledger.json"],
                          capture_output=True, text=True)
    base = json.loads(head.stdout)["entries"] if head.returncode == 0 else L
    before = {m: e["status"] for m, e in base.items()}  # the committed ledger (HEAD), so a re-run logs the same counts
    audit = json.loads((LANE / "results/signal_audit.json").read_text())
    records = {}
    merge_signal(L, audit, records)
    for m in ("RT0603BRD077K5L", "RT0603BRD0716KL"):
        L[m]["gaps"] = [g for g in L[m]["gaps"] if not g.startswith(DROP)]
        note(L[m], f"{TAG}, {REL}): the stale 'Not audited' gap is dropped; this line's V / P checks were already in place.")
    desk_r5(L["CSS2H-2512R-1L00F"])
    desk_bank(L["B32643H8104J000"])
    desk_c5c6(L["B32676G1905K000"])
    desk_l1(L["B82726S2243A020"])
    desk_cx(L["R463N410050N1K"])
    desk_r1r2(L["1206W4F1003T5E"])
    fix_30kpa(L["30KPA150CA"])
    for m, t in (("CSS2H-2512R-1L00F", "R5 element mesh-corrected row (+6 K) and check; desk gap -> B3-estimate"),
                 ("B32643H8104J000", "F_T table-chord allowance and check; desk gaps -> owner (maker question) / certifier"),
                 ("B32676G1905K000", "footprint-name desk gap -> owner (library record)"),
                 ("B82726S2243A020", "digitisation desk gap -> bench (merged); ALT-D3 stray desk gap -> model-estimate"),
                 ("R463N410050N1K", "X2 ripple-current ratings (KEMET p.6 / p.8), stresses from scripts/cx_current.py, "
                                    "checks and finding; desk gap -> bench + owner; L1-body citation refreshed to s52"),
                 ("1206W4F1003T5E", "RV1 Vc(750 A) desk gap -> bench (Figure 4 re-read, not attributable)"),
                 ("30KPA150CA", "maker record fixed (Littelfuse sheet recorded; Good-Ark binding; owner maker-record gap)")):
        note(L[m], f"{TAG}, {REL}): {t}.")
    for m in L:
        st = status(L[m])
        if st != L[m]["status"]:
            log.append(f"status {m}: {L[m]['status']} -> {st}")
            L[m]["status"] = st
    LEDGER.write_text(json.dumps(doc, indent=1) + "\n")
    for r in records.values():
        r["pages_used"] = sorted(r["pages_used"])
    recs = {"generated_by": f"{REL}/scripts/apply_ledger.py", "note": "Datasheet records for the c54 SIGNAL audit. Local "
            "copies are untrusted downloads kept outside the repo; sha256 prefixes re-verified on 2026-10-18; "
            "'file_date' is the local copy's modification date (the fetch date of the lane that downloaded it). "
            "pages_used are PDF page indices cited by the ratings' sources.", "records": records,
            "extra": {"30KPA150CA Littelfuse": {"revision": "Revised BA.08/27/20", "sha256_prefix16": "1fe25d7c0973063d",
                                                "local_copy": str(UNIT.parents[2] / "runs-native21/s47/temp-ratings-dl/semis-a/30kpa-littelfuse/30KPA_littelfuse_lcsc_C19111562.pdf"),
                                                "pages_used": [1, 2]},
                      "KEMET R46 X2 (repo copy)": {"repo_copy": "validation-results/07-conducted-emi/sources/KEM_F3095_R46_X2_310_110C.pdf",
                                                   "sha256_prefix16": "5a3131ce8de74451", "pages_used": [6, 8]}}}
    lf = Path(recs["extra"]["30KPA150CA Littelfuse"]["local_copy"])
    recs["extra"]["30KPA150CA Littelfuse"]["sha_reverified_2026_10_18"] = sha16(lf) == "1fe25d7c0973063d"
    recs["extra"]["KEMET R46 X2 (repo copy)"]["sha_reverified_2026_10_18"] = sha16(UNIT / recs["extra"]["KEMET R46 X2 (repo copy)"]["repo_copy"]) == "5a3131ce8de74451"
    (LANE / "datasheets").mkdir(exist_ok=True)
    (LANE / "datasheets/records.json").write_text(json.dumps(recs, indent=1) + "\n")
    after = {m: e["status"] for m, e in L.items()}
    from collections import Counter
    hdr = [f"# apply_log.md (generated by scripts/apply_ledger.py; do not edit)",
           f"before: {dict(Counter(before.values()))}", f"after: {dict(Counter(after.values()))}", ""]
    (LANE / "results/apply_log.md").write_text("\n".join(hdr + log) + "\n")
    print("\n".join(hdr[1:3]))


if __name__ == "__main__":
    main()
