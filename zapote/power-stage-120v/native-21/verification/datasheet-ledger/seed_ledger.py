#!/usr/bin/env python3
"""One-time seeder for ledger.json (2026-10-13).  Run `python3 -I seed_ledger.py` to regenerate the
seed; after that ledger.json is the source of truth and is edited by hand (see README.md).
Re-running overwrites ledger.json, so do not run it once entries have been edited.

Every fully audited entry lists its datasheet (url + revision + fetch date, or a repo copy), the
ratings with their approval basis, the repo worst-case stresses with file:line, the derating rule and
the computed stress/limit ratio.  The stored ratio is recomputed by gate.py.
"""
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
U = HERE.parents[2]
FETCHED = "2026-10-13"

D = "DECISIONS.md"
FIND = "validation-results/13-external-review-2026-10-13/FINDINGS.md"
SRC = "validation-results/08-manufacturing-package/native-21/sourcing"
ALTC5 = SRC + "/alt-circuits-2026-10-09/ALT-C5C6.md"
ALTD3 = SRC + "/alt-circuits-2026-10-09/ALT-D3.md"
ALTBIAS = SRC + "/alt-circuits-2026-10-09/ALT-BIAS.md"
F1J3 = SRC + "/F1-J3-PARTS.md"
CMTI = "validation-results/06-controller-interface/cmti/README.md"
F2C = "validation-results/02-protection-timing/f2-coordination/README.md"
R6 = "validation-results/05-resonant-tank-envelope/round6-full-power/README.md"
R2COST = "validation-results/11-candidates/r2-cost/PROPOSALS.md"
PARTS = "elec/src/parts.ato"
D5 = "native-21/verification/d5_audit.py"
GATES = "native-21/layout/gates"
SC = GATES + "/scorecard.py"
KELVIN = "validation-results/02-protection-timing/kelvin/kelvin_budget.py"
PI = "validation-results/08-manufacturing-package/native-21/stage19-pi-si/pi_distances19.py"
RES_A = "validation-results/08-manufacturing-package/native-21/stage18-res-a-creepage/res_a_creepage18.py"
BARRIER = "native-21/layout/barrier_gate21.py"
LEAK = "validation-results/07-conducted-emi/leakage/README.md"


def R(parameter, limit, unit, basis, source):
    return {"parameter": parameter, "datasheet_limit": limit, "unit": unit, "basis": basis, "source": source}


def S(parameter, value, unit, condition, evidence):
    return {"parameter": parameter, "worst_case_value": value, "unit": unit, "condition": condition,
            "evidence": evidence}


def C(cid, rating, stress, max_ratio, severity, rule):
    return {"id": cid, "rating": rating, "stress": stress, "max_ratio": max_ratio, "severity": severity,
            "rule": rule}


def L(item, enforced_by):
    return {"item": item, "enforced_by": enforced_by}


def DS(url=None, revision=None, fetched=None, repo_copy=None, note=None, sha256_16=None):
    return {"url": url, "revision": revision, "fetched": fetched, "repo_copy": repo_copy, "note": note,
            "sha256_prefix16": sha256_16}


def finish(e):
    """Fill the computed ratio of every check."""
    ratings = {r["parameter"]: r for r in e["ratings"]}
    stresses = {s["parameter"]: s for s in e["stresses"]}
    for c in e["checks"]:
        c["ratio"] = round(stresses[c["stress"]]["worst_case_value"] / ratings[c["rating"]]["datasheet_limit"], 4)
    return e


def entry(mpn, cls, function, status, datasheet=None, ratings=(), stresses=(), rule="", checks=(),
          layout=(), gaps=(), finding=None, notes=None):
    return {"mpn": mpn, "designators": [], "class": cls, "function": function, "status": status,
            "datasheet": datasheet, "ratings": list(ratings), "stresses": list(stresses),
            "derating_rule": rule, "checks": list(checks), "layout_guidance": list(layout),
            "gaps": list(gaps), "finding": finding, "notes": notes}


E = {}

# ----------------------------------------------------------------------------------------- J1
E["1711725"] = entry(
    "1711725", "SAFETY", "Mains inlet terminal (L/N), Phoenix MKDS 3/2-5,08", "VIOLATION",
    DS("https://docs.rs-online.com/7382/0900766b81380186.pdf",
       "Phoenix Contact data sheet generated 2025-03-21 (10 pp), RS Components copy; Phoenix site not fetched",
       FETCHED, note="Same copy as FINDINGS #4. The nominal 24 A is an IEC figure.", sha256_16="88008f659b038fc3"),
    [R("I_cont IEC", 24, "A", "IEC 60664-1, 400 V (III/2) nominal current", "p.1 Technical data, 'Nominal current IN 24 A'"),
     R("I_cont cULus group B", 15, "A", "cULus Recognized E60425, use group B, 300 V, screw connection", "p.8 Approvals"),
     R("I_cont cULus group D", 10, "A", "cULus Recognized E60425, use group D, 300 V", "p.8 Approvals"),
     R("I_cont CSA group B", 10, "A", "CSA 13631, use group B and D, 300 V", "p.8 Approvals")],
    [S("I inlet regulated", 13.5, "A", "fullbridge_adapter regulates reported inlet current at inlet_target_a <= 13.5 A", D + ":182"),
     S("I inlet trip", 15, "A", "adapter trip; owner cap: total RMS mains current <= 15 A", D + ":168-182"),
     S("I inlet envelope", 16.5, "A", "earlier recorded RMS input envelope (superseded by the 15 A cap but still the L/N copper and J1 envelope in the notes)", F1J3 + ":56")],
    "North-American (NEMA 5-15) product: continuous current <= 100% of the lowest applicable UL/CSA approval rating of the terminal; "
    "the IEC 24 A is not the basis. Anything above the cULus/CSA group-B rating needs an end-product temperature-rise test.",
    [C("cULus-B at regulated", "I_cont cULus group B", "I inlet regulated", 1.0, "violation", "<= 100% of cULus B"),
     C("cULus-B at trip", "I_cont cULus group B", "I inlet trip", 1.0, "violation", "<= 100% of cULus B (zero margin at the trip)"),
     C("CSA-B at regulated", "I_cont CSA group B", "I inlet regulated", 1.0, "violation", "<= 100% of CSA 13631 group B"),
     C("cULus-B at 16.5 A envelope", "I_cont cULus group B", "I inlet envelope", 1.0, "gap", "<= 100%; envelope superseded by the 15 A cap")],
    [L("creepage/clearance of J1 L/N pads (line voltage)", D5 + " (D5 audit)"),
     L("copper at J1 pins carries 13.5-15 A", D + ":841 (task-04 DC run at 15 A)")],
    gaps=["Lab has not ruled whether cULus covers Canada (CSA 13631 10 A is then the binding figure).",
          "No line-current hardware sensing: the 15 A limit is a firmware estimate with unqualified error (FINDINGS #11)."],
    finding="J1 is rated 24 A only on the IEC basis. On the North-American approval basis it is 15 A cULus use group B "
            "(10 A group D) and 10 A CSA. The design carries 13.5 A regulated (1.35x the CSA 10 A, 90% of cULus), "
            "15 A at the trip (100%, no margin) and a 16.5 A recorded envelope (110%). parts.ato and the F1 note still cite the "
            "IEC 24 A (FINDINGS #4). Fix: record 15 A, then a >= 20 A UL group-B terminal at the next re-spin or an "
            "end-product temperature-rise test at 13.5-15 A and maximum ambient.")

# ----------------------------------------------------------------------------------------- F1
E["KLDR025.TXP"] = entry(
    "KLDR025.TXP", "SAFETY", "Mains inlet fuse F1, Class CC 25 A time-delay, held in 2 x Littelfuse 01250003H clips", "PARTIAL",
    DS("https://static.chipdip.ru/lib/254/DOC027254593.pdf", "Littelfuse KLDR Rev: 092821 (distributor copy; littelfuse.com asset URL returned 403)",
       FETCHED, note="Repo cites the same revision (parts.ato). Repo also read a 06/27/2022 revision (f2-coordination README).",
       sha256_16="4502be84f47400d2"),
    [R("I_rated", 25, "A", "UL 248-4 Class CC, 25 A", "p.1 ratings"),
     R("V_rated AC", 600, "V", "UL 248-4", "p.1 ratings"),
     R("I_cont derated", 16.9, "A", "25 A x 0.75 (continuous) x 0.90 (about 10% re-rating at 50 C; curve read by the repo)", "Electrical Specifications p.5-6 and Temperature Derating Curve p.6, as read in parts.ato"),
     R("I2t melting", 226, "A2s", "typical pre-arc", "Electrical Specifications table, KLDR025 row"),
     R("AIR AC", 200000, "A", "200 kA rms symmetrical at 600 Vac", "p.1 / Electrical Specifications table")],
    [S("I inlet trip", 15, "A", "owner cap 15 A, firmware trip", D + ":168-182"),
     S("I2t plug-in inrush", 4.0, "A2s", "lossless 2 uH, 630 A peak at 140 V, C5/C6 9 uF", ALTC5 + ":143-148"),
     S("Prospective fault", 7660, "A", "127 V +10%, 14 AWG cord 1.0 m, zero source impedance", F1J3 + ":52")],
    "Continuous <= 100% of the 25% + temperature re-rated current; fault current <= interrupting rating; inrush I2t <= 10% of melting I2t.",
    [C("continuous at trip", "I_cont derated", "I inlet trip", 1.0, "violation", "15 A <= 16.9 A"),
     C("inrush I2t", "I2t melting", "I2t plug-in inrush", 0.1, "violation", "<= 10% of 226 A2s"),
     C("fault vs AIR", "AIR AC", "Prospective fault", 0.5, "violation", "<= 50% of 200 kA")],
    [L("every series neck of rectifier/bus/return copper clears >= 2 x F1 clearing I2t (3,420 A2s)", SC + " (fuse_copper_fusing_ratio)"),
     L("clip land and creepage at F1 (line voltage)", D5)],
    gaps=["Clip (Littelfuse 01250003H, 30 A) datasheet not fetched or committed; clip and Recognized-component acceptance is a certifier item.",
          "F1 never interrupts 15-25 A through J1 (a 25 A UL 248 fuse carries its rating indefinitely): overload coordination with J1 rests on firmware plus the branch breaker (FINDINGS #11).",
          "Derating curve value (~90% at 50 C) is the repo's reading of a plot, not a tabulated figure."])

# ----------------------------------------------------------------------------------------- F2
E["3403.0171"] = entry(
    "3403.0171", "SAFETY", "Blower-supply branch fuse F2 (3.15 A T) after the EMI filter, feeds J11 -> PS3", "VIOLATION",
    DS("https://www.schurter.com/en/datasheet/typ_UMT_250.pdf", "Schurter UMT 250 data sheet dated 21.07.2026 (5 pp)", FETCHED,
       sha256_16="0d3996fc6f13305f"),
    [R("Breaking capacity IEC 250 VAC", 200, "A", "IEC 60127-4, 250 VAC (footnote 2 of the UMT 250 table)", "Description + table footnote 2"),
     R("I2t melting", 11.6, "A2s", "10 x In typ, 3.15 A row", "Ratings table, 3403.0171 row"),
     R("I_rated", 3.15, "A", "time-lag T, 250 VAC / 125 VDC, UL 248-14", "Ratings table")],
    [S("Prospective fault at J11", 3567, "A", "bolted fault at J11, stiff source, cord 0 m, copper set to 0 (upper corner); F1 cannot back F2 (F2 melts 19.5x sooner)", F2C),
     S("Prospective fault, weakest corner", 373, "A", "15 m branch, copper counted", F2C)],
    "Breaking capacity >= prospective fault current at the fuse location (IEC 60127 rating; UL 248-14 ratings not read).",
    [C("break vs worst fault", "Breaking capacity IEC 250 VAC", "Prospective fault at J11", 1.0, "violation", "fault <= breaking capacity"),
     C("break vs weakest fault", "Breaking capacity IEC 250 VAC", "Prospective fault, weakest corner", 1.0, "violation", "fault <= breaking capacity")],
    [L("F2 sits upstream of J11; fault path copper l_filt/blw_l/n_filt", F2C)],
    gaps=["UL 248-14 breaking capacity at 125/250 VAC not read; IEC 200 A used."],
    finding="F2 (UMT 250, 200 A @ 250 VAC IEC) has a prospective fault of 373-3,567 A at J11 and melts 19.5x sooner than F1, so it "
            "must interrupt alone: exceeded 1.9x-18x (DECISIONS.md:843, F4 FAIL). Open decision: >= 1,500 A 5x20 ceramic "
            "fuse (candidate 02153.15MXP, datasheet figure unverified) or drop the PS3 mains tap.")

# ----------------------------------------------------------------------------------------- BR1
E["GBJ2510-F"] = entry(
    "GBJ2510-F", "POWER", "Mains bridge rectifier BR1 (25 A, 1000 V) on the main heatsink (AlN tile B)", "PARTIAL",
    DS("https://www.diodes.com/assets/Datasheets/GBJ2501-GBJ2510.pdf", "Diodes DS21221 Rev.11-2 (2025)", "repo copy",
       repo_copy="validation-results/03-loss-thermal-budget/round3/sources/gbj2510.pdf",
       note="Repo copy only; URL not re-fetched."),
    [R("IF(AV)", 25, "A", "with heatsink (Note 4), TJ = 150 C", "Maximum ratings table"),
     R("VRRM", 1000, "V", "GBJ2510", "Maximum ratings table"),
     R("I2t", 510, "A2s", "8.3 ms, rating for fusing", "Maximum ratings table"),
     R("IFSM", 350, "A", "8.3 ms half sine", "Maximum ratings table"),
     R("TJ max", 150, "C", "operating", "Maximum ratings table")],
    [S("I line trip", 15, "A", "28.4 W at 15 A; case about 82.5 C on the AlN tile", FIND + ":23"),
     S("V reverse worst", 451, "V", "bus worst stacked corner, script", R2COST + ":89"),
     S("I2t inrush", 4.0, "A2s", "plug-in 630 A peak, 2 uH lossless", ALTC5 + ":143-148"),
     S("I2t shoot-through", 1710, "A2s", "F1 total clearing I2t in a shoot-through; BR1 is sacrificial", D + ":840")],
    "Current <= 80% of IF(AV) (heatsinked); VRRM >= 1.25x peak reverse; I2t of any fault <= 0.5 x rating unless declared sacrificial.",
    [C("I at trip", "IF(AV)", "I line trip", 0.8, "violation", "<= 80% IF(AV)"),
     C("V reverse", "VRRM", "V reverse worst", 0.8, "violation", "<= 80% VRRM"),
     C("inrush I2t", "I2t", "I2t inrush", 0.1, "violation", "<= 10% of 510"),
     C("shoot-through I2t", "I2t", "I2t shoot-through", 0.5, "gap", "F1 clears 3.35x BR1's I2t: sacrificial by decision")],
    [L("thermal interface (1.0 mm gap pad, ~0.37 K/W) to the AlN tile", "UNCHECKED (mechanical; bench thermocouple on BR1 case pending)"),
     L("series necks survive F1 clearing (copper fusing ratio)", SC),
     L("creepage line-to-PE", D5)],
    gaps=["BR1 I2t 510 A2s < F1 clearing 1,710 A2s: BR1 is sacrificial in a shoot-through, a repair item accepted at DECISIONS.md:840 (departs from D-31).",
          "Junction temperature not computed; case 82.5 C is a model (RthJC 1.0 C/W per element); bench thermocouple pending.",
          "Datasheet not re-fetched this session (repo copy)."])

# ----------------------------------------------------------------------------------------- Q
E["IPW65R018CFD7"] = entry(
    "IPW65R018CFD7", "POWER", "Full-bridge switches Q2/Q3/Q5/Q6, 650 V CoolMOS CFD7, TO-247", "PARTIAL",
    DS("https://www.infineon.com/dgdl/Infineon-IPW65R018CFD7-DataSheet-v02_00-EN.pdf", "Infineon Rev.2.0, 2021-04-19", "repo copy",
       repo_copy="validation-results/03-loss-thermal-budget/round3/sources/ipw65r018cfd7.pdf"),
    [R("V(BR)DSS", 650, "V", "VGS=0, ID=1 mA, Tj=25 C", "Table 3, p.4"),
     R("ID cont Tc=100C", 67, "A", "Tc=100 C, limited by Tj max", "Table 2, p.3"),
     R("ID pulse", 495, "A", "Tc=25 C", "Table 2, p.3"),
     R("Tj max", 150, "C", "operating junction", "Table 2, p.3"),
     R("Tj design", 125, "C", "repo thermal requirement (D-18 sink sizing)", D + ":470"),
     R("dv/dt MOSFET", 120, "V/ns", "VDS=0..400 V", "Table 2, p.3"),
     R("IAS", 8.3, "A", "single-pulse avalanche", "Table 2, p.3")],
    [S("VDS die worst", 490, "V", "F6 decks 252/252 per leg, worst die VDS (520 V screen)", D + ":197"),
     S("I tank RMS", 29.4, "A", "28 A ceiling, 29.4 A firmware trip tank current, per switch conducts the tank current", D + ":824"),
     S("Tj worst K1 basis A", 128.7, "C", "K1 sink contingency, 50 kHz, 28 A, basis A (S8 baseline Tj not recorded)", D + ":614"),
     S("dv/dt hard edge", 95, "V/ns", "modelled S4/S5 hard turn-on edge", CMTI + ":8")],
    "VDS <= 80% of 650 V (the 520 V screen); ID <= 80% of the Tc=100 C rating; Tj <= 125 C design (150 C absolute); dv/dt <= 80% of ruggedness.",
    [C("VDS", "V(BR)DSS", "VDS die worst", 0.8, "violation", "490 V <= 520 V"),
     C("ID", "ID cont Tc=100C", "I tank RMS", 0.8, "violation", "<= 80%"),
     C("Tj design", "Tj design", "Tj worst K1 basis A", 1.0, "gap", "Tj <= 125 C; 50 kHz basis A on K1 is 128.7 C"),
     C("dv/dt", "dv/dt MOSFET", "dv/dt hard edge", 0.8, "violation", "<= 80% of 120 V/ns")],
    [L("gate-drive loop inductance, off-gate and die VDS", D + ":197 (F6 decks; F7 loop re-extraction open)"),
     L("TO-247 tab (drain potential) creepage/clearance to PE and sink", D5),
     L("clamp-stack force and tab coplanarity", "UNCHECKED (mechanical; comb acceptance 45-102 N per DECISIONS.md:473)")],
    gaps=["Switching loss, S4/S5 dv/dt and VDS are not measured (bench).",
          "Tj at 28 A / 50 kHz exceeds the 125 C design value on the K1 contingency sink (128.7 C); S8 baseline Tj not recorded.",
          "F7 loop re-extraction open (FINDINGS #1)."])

# ----------------------------------------------------------------------------------------- U1/U2
E["UCC21550BDWKR"] = entry(
    "UCC21550BDWKR", "SAFETY", "Isolated dual gate drivers U1/U2 (HS/LS per leg), reinforced barrier", "PARTIAL",
    DS("https://www.ti.com/lit/ds/symlink/ucc21550.pdf", "TI SLUSE89C May 2023, revised Aug 2024", "repo copy",
       repo_copy="validation-results/01-switching-parasitics/round5/bench-plan/sources/ti-ucc21550-revc.pdf"),
    [R("VDD abs max", 30, "V", "VDDA/B to VSS", "5.1 Absolute Maximum Ratings"),
     R("VIORM", 2121, "V", "VDE 0884-17 reinforced, DW package", "6.x Insulation specifications"),
     R("VIOWM", 1500, "Vrms", "TDDB", "Insulation specifications"),
     R("CMTI min", 125, "V/ns", "Table 5.9", CMTI + ":18"),
     R("Tj max", 150, "C", "operating", "5.1")],
    [S("VDD", 16.91, "V", "RECOM module output 2.5 V x (1 + 63.4/11)", D + ":442-444"),
     S("Barrier peak", 451, "V", "bus worst stacked corner (barrier is HOT-to-HOT functional here)", R2COST + ":89"),
     S("CMTI edge", 95, "V/ns", "modelled hard edge, rule: CMTI >= 1.5x", CMTI + ":8"),
     S("Tj converged", 79, "C", "28 A, 29.4 A tank, h25", D + ":826")],
    "VDD <= 80% abs max; barrier peak <= 50% VIORM; CMTI >= 1.5x modelled edge; Tj <= 125 C.",
    [C("VDD", "VDD abs max", "VDD", 0.8, "violation", "<= 24 V"),
     C("barrier", "VIORM", "Barrier peak", 0.5, "violation", "<= 50%"),
     C("CMTI", "CMTI min", "CMTI edge", 1 / 1.5, "gap", "CMTI >= 1.5x edge (RESOLUTION-PLAN F6): 1.32x"),
     C("Tj", "Tj max", "Tj converged", 0.83, "violation", "Tj <= 125 C (83% of 150)")],
    [L("100 nF + >= 1 uF within 2 mm of VDD/VSS (straddle stack)", "UNCHECKED (hand placed per DECISIONS.md:189; bypass_check.py does not list U1/U2)"),
     L("barrier creepage >= 8 mm DW footprint", BARRIER)],
    gaps=["CMTI 125 V/ns min vs modelled 95 V/ns hard edge is 1.32x, short of the 1.5x rule (DECISIONS.md:845 F6 FAIL); bench measures S4/S5 dv/dt, above 83 V/ns raise turn-on R.",
          "Zero distributor stock until 2027-06 (DECISIONS.md:846 F13)."])

# ----------------------------------------------------------------------------------------- C5/C6
E["B32676G1905K000"] = entry(
    "B32676G1905K000", "POWER", "DC-link bulk film C5/C6, 9 uF 750 VDC, 4-pin radial MKP", "PARTIAL",
    DS("https://www.tdk-electronics.tdk.com/inf/20/20/db/fc_2009/MKP_B32674_678.pdf", "TDK B3267*D/G/J/T, June 2026", FETCHED,
       sha256_16="9af4b66292b23461"),
    [R("VR 85C DC", 750, "V", "VR,85C = 750 V DC; Vop 70C = 900 V DC", "p.9 ordering table, B32676G1905+000 row (header 'VR,85 C = 750 V DC')"),
     R("IRMS max 70C 10kHz", 19.5, "A", "70 C, 10 kHz", "p.9 ordering table"),
     R("ESL typ", 12, "nH", "typical", "p.9 ordering table"),
     R("ripple dT allowance", 1.0, "fraction", "TDK permitted self-heating at 85 C ambient (1.0 = the allowance)", "TDK permissible-ripple curves, as used in ALT-C5C6")],
    [S("Vbus static OVP", 286, "V", "static OVP corner", ALTD3 + ":60"),
     S("Vbus worst no-clamp", 451, "V", "worst stacked corner (script)", R2COST + ":89"),
     S("ripple dT use at 22 A", 0.80, "fraction", "I_tank <= 22 A, 85 C cap ambient", ALTC5 + ":32"),
     S("ripple dT use at 26 A (scaled)", 1.12, "fraction", "THIS LEDGER's extrapolation: 0.80 x (26/22)^2 for the commissioned ceiling; not a repo number", D + ":563"),
     S("ripple dT use at 28 A (scaled)", 1.30, "fraction", "THIS LEDGER's extrapolation: 0.80 x (28/22)^2; not a repo number", D + ":824")],
    "Bus DC voltage <= 80% VR(85 C); ripple self-heating <= 100% of TDK's allowance at the case ambient.",
    [C("Vbus static", "VR 85C DC", "Vbus static OVP", 0.8, "violation", "<= 600 V"),
     C("Vbus worst", "VR 85C DC", "Vbus worst no-clamp", 0.8, "violation", "<= 600 V transient"),
     C("ripple 22 A", "ripple dT allowance", "ripple dT use at 22 A", 1.0, "violation", "<= 1.0"),
     C("ripple 26 A", "ripple dT allowance", "ripple dT use at 26 A (scaled)", 1.0, "gap", "commissioned ceiling (extrapolated)"),
     C("ripple 28 A", "ripple dT allowance", "ripple dT use at 28 A (scaled)", 1.0, "gap", "design ceiling (extrapolated)")],
    [L("ESL / bulk path inductance (F6 decks)", ALTC5 + ":188"),
     L("pad pattern 37.5 x 20.3 mm matches TDK 4-pin drawing", FIND + ":28")],
    gaps=["Ripple self-heating was only evaluated at I_tank <= 22 A (80% of the allowance). The commissioned ceiling is 26 A and the design ceiling 28 A: a pure I^2 scale puts both above the allowance. Rerun ripple.py at 26/28 A and measure case temperature at first power.",
          "Footprint is named TDK_B32656G0275J000 (stale name, geometry correct)."])

# ----------------------------------------------------------------------------------------- bank
E["B32654A1104J000"] = entry(
    "B32654A1104J000", "POWER", "Resonant tank bank C21-C23/C151/C152, 5 x 100 nF +/-5 %, 1600 VDC MKP", "PARTIAL",
    DS("https://cdn.eicom.ru/media/PDF/3973480.pdf", "TDK B32651...B32658, November 2019 (distributor copy; 61 pp)", FETCHED,
       note="The repo cites 'TDK p.57' current curve from its own revision; page 57 of this copy is the symbols table, so the page number does not transfer.",
       sha256_16=None),
    [R("VR DC", 1600, "V", "B32654A1104: 1600 VDC / 500 VAC", "B32654 ordering-code table, lead spacing 27.5 mm (pp.18-19)"),
     R("I tank allowed @35kHz", 26.8, "A", "worst-share part (+/-10 %), 85 C, TDK current curve; repo digitisation after K->J change", D + ":853"),
     R("dV/dt", 1000, "V/us", "1600 V / 27.5 mm", "Pulse handling capability table (page not recorded)")],
    [S("V peak normal", 640, "V", "peak across C_res at the design point", PARTS + ":486"),
     S("I tank commissioned", 26, "A", "commissioned ceiling", D + ":563"),
     S("I tank design", 28, "A", "design ceiling; 1.022x TDK curve at 40 kHz", D + ":853"),
     S("V third fault", 1683, "V", "F3 third-fault case, outside IEC 60335-1 19.11 one-fault analysis", D + ":853")],
    "AC voltage <= 80% VR; tank RMS current <= 100% of the TDK curve for the worst-share part at 85 C.",
    [C("V normal", "VR DC", "V peak normal", 0.8, "violation", "<= 1280 V"),
     C("I commissioned", "I tank allowed @35kHz", "I tank commissioned", 1.0, "violation", "26 A <= 26.8 A"),
     C("I design", "I tank allowed @35kHz", "I tank design", 1.0, "gap", "28 A exceeds 26.8 A by 4.5 % (repo: ratio 1.022 at 40 kHz)"),
     C("V third fault", "VR DC", "V third fault", 1.0, "gap", "1,683 V > 1,600 VDC in the third-fault case")],
    [L("hot-spot rise <= 20 K before running at 22 A (bodies 0.55-0.8 mm apart)", "UNCHECKED (bench; DECISIONS.md:371-374)"),
     L("pad pattern / mains-side separation", D5)],
    gaps=["The 28 A design ceiling is 4.5 % above the repo's digitised TDK current curve (ratio 1.022 at 40 kHz); only the 26 A commissioned ceiling is inside.",
          "TDK p.57 curve is digitised by the repo ('digitise TDK p.57 properly' is still an open item, DECISIONS.md:373).",
          "Third-fault voltage 1,683 V exceeds the 1,600 VDC rating (covered only by the 35 kHz floor and a third independent fault)."])

# ----------------------------------------------------------------------------------------- C38-41
E["B32652A0104K000"] = entry(
    "B32652A0104K000", "POWER", "Local bus decoupling film C38-C41, 100 nF 1000 VDC", "PARTIAL",
    DS("https://cdn.eicom.ru/media/PDF/3973480.pdf", "TDK B32651...B32658, November 2019 (distributor copy)", FETCHED,
       note="B32652A0104: 1000 VDC / 250 VAC, 15 mm pitch (ordering table)."),
    [R("VR DC", 1000, "V", "B32652A0104", "ordering table, B32652 section"),
     R("IRMS 85C 100kHz", 5.4, "A", "per parts.ato docstring (value not re-read in the datasheet copy)", PARTS + ":164-167")],
    [S("Vbus worst no-clamp", 451, "V", "worst stacked corner", R2COST + ":89")],
    "DC voltage <= 80% VR; RMS current share <= 80% of the 85 C / 100 kHz rating.",
    [C("V", "VR DC", "Vbus worst no-clamp", 0.8, "violation", "<= 800 V")],
    [L("nanosecond commutation spikes carried by C38-C41", ALTD3 + ":125")],
    gaps=["Per-part RMS current share is unknown ('local current sharing needs measurement', parts.ato).",
          "Current rating taken from the parts.ato docstring, not re-read."])

# ----------------------------------------------------------------------------------------- RV1
E["TMOV20RP175E"] = entry(
    "TMOV20RP175E", "SAFETY", "Mains surge varistor RV1 (thermally protected MOV, 175 Vrms)", "PARTIAL",
    DS(None, "Littelfuse TMOV series; datasheet not retrieved (littelfuse.com 403, alldatasheet Cloudflare)", None,
       note="Ratings below come from the DigiKey product listing (175 Vac max, 225 Vdc, 10 kA, 135 J) and parts.ato (Vc 455 V). Not a datasheet."),
    [R("Vac max continuous", 175, "Vrms", "distributor listing (DigiKey), not datasheet", "DigiKey TMOV20RP175E listing, 2026-10-13 search"),
     R("Energy", 135, "J", "distributor listing", "DigiKey listing"),
     R("Surge", 10000, "A", "distributor listing", "DigiKey listing")],
    [S("Line high corner", 139.7, "Vrms", "127 V +10 %", D + ":306"),
     S("MOV surge current", 750, "A", "mains surge (1-2 kV combination wave) through RV1", ALTD3 + ":119")],
    "Continuous AC <= 80% of the MCOV; surge current <= 10% of the rated 8/20 us surge.",
    [C("MCOV", "Vac max continuous", "Line high corner", 0.8, "violation", "139.7 <= 140 Vrms"),
     C("surge", "Surge", "MOV surge current", 0.1, "violation", "<= 1 kA")],
    [L("thermal element adjacency to the body, lead forming (offset lead)", "UNCHECKED (footprint provisional, FINDINGS table row RV1; FOOTPRINTS F4)")],
    gaps=["Manufacturer datasheet not obtained; limits are distributor-listed.",
          "MCOV margin is 0.2 Vrms (140 vs 139.7): 80 % rule met only just; the 140 V line corner was never run against the TMOV datasheet leakage/aging curves.",
          "UL 1449 type and thermal-disconnect rating not read."])

# ----------------------------------------------------------------------------------------- C1/C2
E["R463N410050N1K"] = entry(
    "R463N410050N1K", "SAFETY", "X2 across-the-line capacitors C1/C2, 1 uF 310 VAC", "PARTIAL",
    DS("https://www.kemet.com/en/us/capacitors/film/emi-suppression/r46.html", "KEMET/YAGEO F3095_R46_X2_310_110C (2026-05-13)", "repo copy",
       repo_copy="validation-results/07-conducted-emi/sources/KEM_F3095_R46_X2_310_110C.pdf"),
    [R("V rated AC", 310, "Vrms", "IEC 60384-14 class X2, 50/60 Hz", "p.1 features / p.5 table"),
     R("Category T max", 110, "C", "R46 110 C series", "p.1")],
    [S("Line high corner", 139.7, "Vrms", "127 V +10 %", D + ":306")],
    "AC voltage <= 50% of the X2 rating for continuous line; discharge < 34 V in 1 s at the plug.",
    [C("V", "V rated AC", "Line high corner", 0.5, "violation", "<= 155 V")],
    [L("lead trim to 4 mm and footprint P22.5", FIND + ":28")],
    gaps=["Body temperature next to L1/BR1 and the 1-2 kV surge pulse (X2 pulse/dV/dt limits) not compared to the datasheet.",
          "Bleed (R1/R2) is itself UNAUDITED; plug-pin discharge < 34 V in 1 s asserted by FINDINGS #10 only."])

# ----------------------------------------------------------------------------------------- C3/C4
E["DE1E3RA222MA4BP01F"] = entry(
    "DE1E3RA222MA4BP01F", "SAFETY", "Y1 line-to-PE capacitors C3/C4, 2.2 nF", "PARTIAL",
    DS(None, "Murata DE1 series; datasheet for this exact suffix not retrieved (murata.com returned 500)", None,
       note="Sibling DE1E3RA222MA4BN01F is listed by Farnell as X1 440 V / Y1 250 V; a BP01F-suffix part may carry a different Y rating."),
    [R("Y1 rating (sibling BN01F)", 250, "Vrms", "distributor listing of a different suffix, not this MPN", "Farnell listing 2858797")],
    [S("Line high corner to PE", 139.7, "Vrms", "127 V +10 %", D + ":306"),
     S("Touch current PE open, 132 V", 0.974, "mA", "all Y capacitance incl. inlet module and three IRM modules", LEAK + ":7")],
    "Y capacitance sized so touch current with PE open <= the applicable limit (UL 1026 0.5 mA for portable appliances, clause unconfirmed).",
    [C("V", "Y1 rating (sibling BN01F)", "Line high corner to PE", 0.8, "violation", "<= 200 V"),
     ],
    [L("PE branch via J6; Y-cap footprint pad 1.5 mm, P10", FIND + ":28")],
    gaps=["Exact-MPN datasheet not retrieved: Y1 voltage rating and approvals unverified.",
          "Product leakage FAIL (F5): 0.974 mA touch current vs UL 1026 0.5 mA (clause unconfirmed, DECISIONS.md:844). If confirmed this is a VIOLATION of the approval basis; fix is total Y <= 5.0 nF per line.",
          "Murata BP01F ratings may be 300 Vac, not 250 Vac (search listing); verify."])

# ----------------------------------------------------------------------------------------- L1
E["B82726S2203A020"] = entry(
    "B82726S2203A020", "SAFETY", "Mains common-mode choke L1, 20 A 1.6 mH", "PARTIAL",
    DS(None, "TDK B82726S2*3A020 data sheet (5/26) as cited in parts.ato; no retrievable copy found 2026-10-13", None),
    [R("I_rated", 20, "A", "per parts.ato docstring (TDK data sheet 5/26), temperature basis not recorded", PARTS + ":90-98")],
    [S("I inlet trip", 15, "A", "owner cap", D + ":168-182"),
     S("Copper neck L1 -> BR1 AC1 I2t", 1747, "A2s", "lowest conductor neck, 1.02x F1 clearing", D + ":907")],
    "Continuous current <= 80% of the rated current at the worst ambient; rated voltage >= line high corner.",
    [C("I", "I_rated", "I inlet trip", 0.8, "violation", "15 A <= 16 A")],
    [L("windings 1-4 and 2-3, pins 10 mm x 25 mm per TDK drawing", FIND + ":28")],
    gaps=["Datasheet not retrieved: temperature derating, rated voltage (a distributor listing of sibling TDK B827x chokes shows 48 VAC / 80 VDC; confirm B82726S2203A020 is rated >= 140 Vrms) and saturation are unchecked.",
          "Core stock zero, 29 weeks (DECISIONS.md:846)."])

# ----------------------------------------------------------------------------------------- R5
E["CSS2H-2512R-1L00F"] = entry(
    "CSS2H-2512R-1L00F", "POWER", "Bus/OCP shunt R5, 1 mOhm Bourns CSS2H-2512 Kelvin", "PARTIAL",
    DS("https://sy-dep-epc-lpc.web.cern.ch/components/datasheets/epc-lpc%20(converters)/CSS2H-2512R-Shunt-Bourns.pdf", "Bourns CSS2H-2512 REV. 06/17/20 (CERN-hosted copy; bourns.com returned 403)", FETCHED,
       sha256_16="ae54630a6a212aae"),
    [R("P rated @ terminal 70C", 5, "W", "terminal temperature 70 C", "p.1 electrical table"),
     R("P rated @ terminal 130C", 3, "W", "terminal temperature 130 C", "p.1 electrical table"),
     R("T operating max", 170, "C", "-55..+170 C", "p.1")],
    [S("P shunt", 0.784, "W", "28 A RMS x 1.000 mOhm (computed here; bus-return current approximated by the tank current)", D + ":824"),
     S("T element converged", 140, "C", "28 A, h25, converged model", D + ":823"),
     S("T terminal max", 129.5, "C", "terminal hottest, 18.8 K to the 20 %-power terminal bound", D + ":823")],
    "Power <= 30% of the rating at the actual terminal temperature (3 W at 130 C); element <= 85% of Tmax.",
    [C("P at terminal 130C", "P rated @ terminal 130C", "P shunt", 0.3, "violation", "0.78 W <= 0.9 W"),
     C("T element", "T operating max", "T element converged", 0.85, "gap", "140 C of 170 C = 0.82")],
    [L("Kelvin pads 2/3 separate from current pads 1/4, paired Kelvin return", KELVIN),
     L("R5.4 via field and copper necks survive F1 clearing", SC)],
    gaps=["Peak/pulse rating (Maximum Pulse Power/Energy charts) vs the 71 A OCP trip transient is not compared.",
          "Stress P uses the tank current as the shunt current; actual bus-return RMS is not separately evidenced.",
          "Zero stock (DECISIONS.md:846 F13)."])

# ----------------------------------------------------------------------------------------- T1
E["CST3015-200ED"] = entry(
    "CST3015-200ED", "SAFETY", "Tank current transformer T1, 1:200, reinforced barrier SW_A end", "PARTIAL",
    DS("https://www.coilcraft.com/getmedia/df31d5fe-b3af-4586-82a7-7b773ac9f838/cst3015.pdf", "Coilcraft Document 1608-1, revised 09/08/25", "repo copy",
       repo_copy="validation-results/05-resonant-tank-envelope/sources/cst3015.pdf"),
    [R("I primary sensed", 87, "A", "DC through the primary giving a 40 K rise at 25 C ambient; 'reference only, not absolute maximum'", "p.1 table note 5"),
     R("Volt-time secondary", 1276, "V-us", "secondary, pins 4-3", "p.1 table"),
     R("Isolation test", 5000, "Vrms", "one minute between windings; reinforced, >= 8 mm creepage/clearance", "p.1 features"),
     R("T part max", 165, "C", "ambient + temperature rise", "p.1")],
    [S("I primary tank trip", 29.4, "A", "28 A ceiling, 29.4 A firmware trip tank current", D + ":824"),
     S("Volt-time at 118.74 A", 67.6, "V-us", "5.3 % of limit at the shunt-band top (computed 0.053 x 1276)", D + ":851"),
     S("Working voltage", 198, "V", "SW_A end of the coil, 99 Vrms / 198 Vpk", D + ":757")],
    "Primary RMS <= 50% of the 40 K-rise current; volt-time <= 50% of limit; barrier working voltage must be rated by the maker.",
    [C("I", "I primary sensed", "I primary tank trip", 0.5, "violation", "0.34"),
     C("volt-time", "Volt-time secondary", "Volt-time at 118.74 A", 0.5, "violation", "0.053")],
    [L("no footprint joins RES_A and SELV/PE; RES_A to SELV/PE 12.6 mm", RES_A),
     L("pad map P1/P2/S1/S2 = 1/2/3/4", PARTS + ":404-408")],
    gaps=["Coilcraft states reinforced / 5 kV rms but gives no working voltage, CTI or HF / partial-discharge rating at 198 Vpk, 31+ kHz: a Coilcraft question (DECISIONS.md:757).",
          "Temperature-rise curve vs actual coil-side ambient not evaluated.",
          "Cww unspecified (CMTI README:70)."])

# ----------------------------------------------------------------------------------------- PS1/PS2
E["IRM-20-15"] = entry(
    "IRM-20-15", "SAFETY", "Controller supply PS1, Mean Well IRM-20-15, Class II, mains-fed", "PARTIAL",
    DS("https://www.meanwell.com/Upload/PDF/IRM-20/IRM-20-SPEC.PDF", "Mean Well IRM-20 SPEC (repo reads the 2025-11-21 issue)", "repo copy",
       repo_copy="validation-results/03-loss-thermal-budget/round3/sources/irm20.pdf"),
    [R("Pout allowed @ 78C bay air", 5.4, "W", "output derating curve at 78 C ambient (repo reading)", D + ":675"),
     R("Vin max", 305, "Vac", "85-305 Vac universal input", "p.1/p.2"),
     R("T working max", 85, "C", "-30..+85 C with derating curve", "p.2")],
    [S("Pout controller", 4.83, "W", "controller verify ps1.p_total_W", D + ":675"),
     S("Vin high corner", 139.7, "Vac", "127 V +10 %", D + ":306"),
     S("T case model", 86, "C", "model case temperature vs 85 C AMBIENT rating (judge against measured local air)", D + ":834")],
    "Output <= 90% of the derated power at the worst local air; input voltage <= 80% of the max.",
    [C("Pout", "Pout allowed @ 78C bay air", "Pout controller", 0.9, "violation", "89 %"),
     C("Vin", "Vin max", "Vin high corner", 0.8, "violation", "46 %")],
    [L("isolation: Class II 4.2 kVac I/O, mains only side", BARRIER),
     L("blower start/stall cannot brown out PS1 (separate PS3)", D + ":617")],
    gaps=["Bay air of 78 C is modelled; only 11 % margin to the derating curve. Bench soak at 40 C / 28 A required (DECISIONS.md:675).",
          "Model case 86 C vs the 85 C ambient rating: must be judged against measured local air (DECISIONS.md:834).",
          "Input current 0.6 A typ at 115 Vac per the datasheet is counted in I_aux = 1.3 A (DECISIONS.md:171)."])

E["IRM-20-24"] = entry(
    "IRM-20-24", "SAFETY", "Bias/gate supply PS2 (TCO-switched), Mean Well IRM-20-24, Class II", "PARTIAL",
    DS("https://www.meanwell.com/Upload/PDF/IRM-20/IRM-20-SPEC.PDF", "Mean Well IRM-20 SPEC (repo reads the 2025-11-21 issue)", "repo copy",
       repo_copy="validation-results/03-loss-thermal-budget/round3/sources/irm20.pdf"),
    [R("P rated", 21.6, "W", "24 V 0.9 A rated, 25 C", "p.2 spec table"),
     R("Vin max", 305, "Vac", "85-305 Vac", "p.1/p.2")],
    [S("P bias allocation", 9.59, "W", "R24C2T25 modules etc. at 80 kHz (9.59 W allocation)", ALTBIAS + ":52"),
     S("Vin high corner", 139.7, "Vac", "127 V +10 %", D + ":306")],
    "Output <= 50% of nameplate until the temperature derating at the measured local air is read; input <= 80% of max.",
    [C("P", "P rated", "P bias allocation", 0.5, "violation", "44 %"),
     C("Vin", "Vin max", "Vin high corner", 0.8, "violation", "46 %")],
    [L("TCO loop clearance at J3 (line voltage across pins)", D5)],
    gaps=["Derating at the real local air not read: model case 98 C vs the 85 C ambient rating (DECISIONS.md:834); judge against measured air.",
          "Leakage current of the IRM modules (0.43 mA total for three at datasheet maximum) is inside the F5 leakage FAIL (DECISIONS.md:844)."])

# ----------------------------------------------------------------------------------------- U41/U42
E["R24C2T25/R-R"] = entry(
    "R24C2T25/R-R", "POWER", "High-side isolated gate-bias modules U41/U42 (RECOM), HOT-to-HOT functional barrier", "PARTIAL",
    DS("https://www.simpex.ch/wp-content/uploads/2023/12/RxxC2Txx.pdf", "RECOM RxxC2Txx 'Rev. PRELIMINARY' (Swiss distributor mirror, 2023-12); the repo read 'Rev.1-2024'", FETCHED,
       note="recom-power.com datasheet URL returned 404. Mirror says functional isolation only (850 Vrms working / 1.2 kVp); the repo cites reinforced 5 kVAC / 1.4 kVDC from the 2024 revision, not committed.",
       sha256_16="e9259f103f1b0eca"),
    [R("VIORM functional", 1200, "V", "repetitive peak isolation voltage, bipolar (preliminary mirror)", "p.7 Isolation capabilities"),
     R("CMTI", 150, "V/ns", "+/-150 V/ns", "p.6 CMTI"),
     R("Pout avg 82C", 2.0, "W", "2 W average to 82 C on RECOM 50x50 mm 70 um EVM; 2.5 W for 5 s", "p.3 derating graph, notes 4-6")],
    [S("Barrier peak functional", 520, "V", "required functional barrier 0.52 kVpk", ALTBIAS + ":159"),
     S("CMTI edge", 95, "V/ns", "modelled hard edge", CMTI + ":23"),
     S("Pout at 80 kHz", 1.71, "W", "allocation at 80 kHz F6 (typ 1.7 W dissipation each)", ALTBIAS + ":164"),
     S("Tj converged", 105, "C", "28 A, h25 (45 K margin)", D + ":824")],
    "Barrier peak <= 50% of VIORM; CMTI >= 1.5x edge; output power <= 90% of the derated power at the measured local air.",
    [C("barrier", "VIORM functional", "Barrier peak functional", 0.5, "violation", "43 %"),
     C("CMTI", "CMTI", "CMTI edge", 1 / 1.5, "violation", "63 %"),
     C("Pout", "Pout avg 82C", "Pout at 80 kHz", 0.9, "violation", "85.5 % of the 2 W knee")],
    [L("output caps between VOUT+ and VOUT- close to the IC (RECOM p.13): <= 3 mm", PI),
     L("heat-spread pours; U42 In1/In2 under its primary", D + ":541")],
    gaps=["The retrieved datasheet is PRELIMINARY and says 850 Vrms / 1.2 kVp functional only; the repo relies on a reinforced 5 kVAC / 1.4 kVDC claim from a revision not committed. Use is functional, so the 0.52 kVpk stress passes either way, but the claim must be reconciled.",
          "Power is the 80 kHz allocation (1.71 W vs 2 W knee); 2 W knee is at 82 C ambient on an EVM; local enclosure air not evidenced (DECISIONS.md:836 bench IR).",
          "Start-up (6-13 ms vs 16 ms timeout) and 10-16 MHz spread-spectrum emissions are bench items (DECISIONS.md:442-448)."])

# ----------------------------------------------------------------------------------------- J3/J11
E["B2P3-VH(LF)(SN)"] = entry(
    "B2P3-VH(LF)(SN)", "SAFETY", "Mains tap headers J3 (PS2 TCO loop) and J11 (blower tap), JST VH", "PARTIAL",
    DS("https://www.jst-mfg.com/product/pdf/eng/eVH.pdf", "JST VH connector catalogue (eVH.pdf)", FETCHED, sha256_16="d51e669c597988b2"),
    [R("I rated", 10, "A", "10 A AC/DC (datasheet page header), 250 V AC/DC", "p.1"),
     R("V rated", 250, "V", "250 V AC/DC", "p.1")],
    [S("I J11 bounded by F2", 3.15, "A", "F2 3.15 A T upstream", D + ":629"),
     S("I J3 (PS2 input)", 0.6, "A", "IRM-20 AC current typ at 115 Vac", D + ":171"),
     S("V line high", 139.7, "V", "127 V +10 %", D + ":306")],
    "Current <= 80% of the connector rating; voltage <= 80% of rating; UL/CSA file rating read before reliance.",
    [C("I J11", "I rated", "I J11 bounded by F2", 0.8, "violation", "32 %"),
     C("I J3", "I rated", "I J3 (PS2 input)", 0.8, "violation", "6 %"),
     C("V", "V rated", "V line high", 0.8, "violation", "56 %")],
    [L("J3 copper gap with 2.7 mm pads is 5.22 mm at line voltage", D5)],
    gaps=["The retrieved JST catalogue defers UL/CSA ratings to a website list; the NA approval basis (UL E60389-class file, 10 A/250 V) was not read, so 'applicable approval basis' is unverified.",
          "J11 bounded by F2 which itself fails its breaking capacity (see 3403.0171)."])

# ----------------------------------------------------------------------------------------- J6
E["1704004"] = entry(
    "1704004", "SAFETY", "PE branch terminal J6 (chassis PE stud branch to board), Phoenix KDS 3", "VERIFIED",
    DS("https://docs.rs-online.com/4f1f/0900766b813ab43f.pdf", "Phoenix Contact 1704004 PDF generated 15/02/2015 (RS copy; Phoenix site not fetched)", FETCHED, sha256_16="846f6349ddeda202"),
    [R("I IEC", 24, "A", "IEC nominal 24 A / 400 V", "p.1-2"),
     R("I CSA", 10, "A", "CSA, 24-12 AWG, 300 V", "p.3"),
     R("I cULus group B", 15, "A", "UL Recognized use group B, 250 V (group D 10 A / 300 V)", "p.4")],
    [S("I PE branch (leakage)", 0.000974, "A", "Y-cap leakage with PE open at 132 V: 0.974 mA; the branch carries leakage only, the cord PE bonds directly to the chassis, J6 and R38 are never in series with the primary PE bond", D + ":161")],
    "Current <= 100% of the lowest NA approval rating (CSA 10 A); the terminal is not a protective bond.",
    [C("leakage vs CSA", "I CSA", "I PE branch (leakage)", 1.0, "violation", "1e-4 of 10 A")],
    [L("PE track thin by design (leakage only); no series protective role", D5)],
    gaps=[], notes="A shorted Y capacitor would put line-to-PE fault current through this branch until F1 clears; Y1 capacitors are fail-safe by design and that case is not credited here.")

# ----------------------------------------------------------------------------------------- D3/D17
E["30KPA150CA"] = entry(
    "30KPA150CA", "SAFETY", "Bus clamp D3/D17, two Good-Ark 30KPA150CA bidirectional TVS in series", "PARTIAL",
    DS(None, "Good-Ark 30KPA150CA data sheet p.3, as cited in ALT-D3.md; no Good-Ark copy retrievable 2026-10-13 (search found only the Littelfuse 30KPA, another vendor)", None),
    [R("Standoff string", 300, "V", "2 x 150 V, per ALT-D3 citing Good-Ark p.3", ALTD3 + ":19"),
     R("VBR min string", 335, "V", "2 x 167.5 V", PARTS + ":174-181"),
     R("Vc max string", 466.8, "V", "2 x 233.4 V at 129.8 A, 10/1000 us", ALTD3 + ":19")],
    [S("Bus static OVP", 286, "V", "static OVP corner, standoff must exceed it", ALTD3 + ":60"),
     S("Plug-in overshoot", 384, "V", "362-384 V with the required >= 100 uH inlet module", FIND + ":60"),
     S("Clamp current", 109, "A", "1 kV differential surge", ALTD3 + ":19")],
    "Standoff >= static OVP; clamp (Vc at the sizing current) <= 520 V screen; no published tempco so hot clamp is unverified.",
    [C("standoff", "Standoff string", "Bus static OVP", 1.0, "violation", "286 V <= 300 V (95 %: no margin)"),
     C("plug-in vs VBR", "VBR min string", "Plug-in overshoot", 1.0, "gap", "384 V exceeds VBR min 335 V: clamp conducts ~0.4 J (FINDINGS O1)")],
    [L("P600 lead bend: hole centre 1.8 mm from the body end (needs ~3.4-4.6 mm straight)", "UNCHECKED (FINDINGS #8: check a formed sample before ordering)"),
     L("clamp loop, midpoint to BUSBLEED_MID", D + ":460-462")],
    gaps=["No Good-Ark datasheet copy; figures from ALT-D3 citing p.3; Good-Ark/Littelfuse publish no tempco (hot clamp open, ALT-D3:134).",
          "Bench pulse qualification (ALT-D3 5) open; until then the bench bus stays <= 150 V DC (DECISIONS.md:461).",
          "Standoff margin 4.7 % to the 286 V OVP corner; 384 V plug-in overshoot exceeds the string VBR min so the TVS conducts at every plug-in at the crest.",
          "Lead-bend stress on the P600 body unverified (FINDINGS #8)."])

# ----------------------------------------------------------------------------------------- ISO7710
E["ISO7710DWR"] = entry(
    "ISO7710DWR", "SAFETY", "Reinforced digital isolators U9 (bus_fault) and U32/U33/U34 (rail monitors)", "PARTIAL",
    DS("https://www.ti.com/lit/ds/symlink/iso7710.pdf", "TI SLLSER9E, November 2016, revised December 2024", FETCHED, sha256_16="42fc3c704c9ca0c4"),
    [R("VIORM", 2121, "V", "VDE 0884-17, DW-16", "Insulation specifications table"),
     R("VIOWM", 1500, "Vrms", "TDDB, DW-16", "Insulation specifications table"),
     R("CMTI min", 85, "V/ns", "85 kV/us min, 100 kV/us typ", "Electrical characteristics (5-V / 3.3-V supply)"),
     R("CLR/CPG", 8, "mm", "DW-16 external clearance/creepage", "Insulation specifications table")],
    [S("Barrier peak", 286, "V", "bus static OVP corner", ALTD3 + ":60"),
     S("CMTI edge", 95, "V/ns", "modelled hard edge", CMTI + ":19")],
    "Barrier peak <= 50% VIORM; CMTI >= 1.5x modelled edge unless filtered.",
    [C("barrier", "VIORM", "Barrier peak", 0.5, "violation", "13 %"),
     C("CMTI", "CMTI min", "CMTI edge", 1 / 1.5, "gap", "min 85 < 95 V/ns modelled: ratio 1.12; U32-34 pass through the 10 us filter, U9 unfiltered")],
    [L("reinforced creepage/clearance >= 8 mm DW footprint", BARRIER),
     L("default-HIGH output on input-side power loss asserts BAD (fail-safe)", FIND + ":26")],
    gaps=["CMTI min 85 V/ns is below the modelled 95 V/ns hard edge. U32/U33/U34 are protected by the 10 us BIAS_BAD filter; U9 (OCP_KELVIN_P) is unfiltered and OPEN: a false HIGH is a nuisance bus_fault (CMTI README:20).",
          "Zero distributor stock, 12 weeks (DECISIONS.md:846)."])

# ----------------------------------------------------------------------------------------- AMC1311
E["AMC1311BDWVR"] = entry(
    "AMC1311BDWVR", "SAFETY", "Isolated bus-voltage amplifier U4 (reinforced)", "PARTIAL",
    DS("https://www.ti.com/lit/ds/symlink/amc1311.pdf", "TI SBAS786C (cited by the repo)", None,
       note="URL cited by the repo (CMTI README); not fetched in this task."),
    [R("CMTI min", 100, "V/ns", "B grade, SBAS786C 7.9 (as recorded in the repo)", CMTI + ":21"),
     R("VIORM", 2121, "V", "reinforced, as recorded in DECISIONS.md:757", D + ":757")],
    [S("CMTI edge", 95, "V/ns", "OCP_KELVIN_P crossing", CMTI + ":21"),
     S("Barrier peak", 286, "V", "bus static OVP corner", ALTD3 + ":60")],
    "CMTI >= 1.5x modelled edge; barrier peak <= 50% VIORM.",
    [C("CMTI", "CMTI min", "CMTI edge", 1 / 1.5, "gap", "1.05x"),
     C("barrier", "VIORM", "Barrier peak", 0.5, "violation", "13 %")],
    [L("reinforced creepage", BARRIER)],
    gaps=["Datasheet not fetched this session; limits are the repo's recorded values.",
          "CMTI margin 1.05x vs 1.5x rule: a spurious VBUS sample, no gate command (CMTI README:21 OPEN)."])

# ----------------------------------------------------------------------------------------- VOL628A
E["VOL628A-2X001T"] = entry(
    "VOL628A-2X001T", "SAFETY", "Line zero-cross optocoupler U36 (mains L/N to SELV), LSOP-4 long creepage", "PARTIAL",
    DS("https://www.vishay.com/docs/82401/vol628a.pdf", "Vishay 82401 Rev. 1.9, 10-Feb-2023", FETCHED, sha256_16="86b23c8c1723580a"),
    [R("VIORM", 1050, "V", "DIN EN 60747-5-5", "p.4 safety table"),
     R("VIOTM", 8000, "V", "transient", "p.4"),
     R("VISO", 5000, "Vrms", "UL1577 1 min", "p.4"),
     R("CTI", 275, "V", "insulation group IIIa", "p.4"),
     R("IF abs max", 60, "mA", "+/-60 mA input", "p.2 absolute maximum ratings")],
    [S("Line crest", 197.6, "V", "127 V +10 % x sqrt2", D + ":306")],
    "Barrier peak <= 50% VIORM; creepage and clearance >= 8 mm; material group per D5 basis.",
    [C("barrier", "VIORM", "Line crest", 0.5, "violation", "19 %")],
    [L("8.0 mm creepage/clearance, footprint verified 2026-10-08 independent review", FIND + ":50"),
     L("zero-cross pulse width / 50-60 Hz window validated in firmware", "UNCHECKED (firmware; CTR bin -2 widens the pulse 1.6x, bench check 300 us)")],
    gaps=["Input LED current at the mains peak is not evidenced against IF +/-60 mA / Pdiss 100 mW.",
          "CTI 275 (group IIIa) vs the material-group assumed in the D5 basis not compared.",
          "No CMTI published for the part (CMTI README:22): false zero-cross edge handled in firmware."])

# ----------------------------------------------------------------------------------------- HV resistors
E["RC1206FR-07220KL"] = entry(
    "RC1206FR-07220KL", "SAFETY", "Bus bleed R3/R4 (two 220 k in series, midpoint to D3/D17)", "PARTIAL",
    DS("https://www.yageo.com/en/Product/Index/ChipResistorSurfaceMount", "Yageo RC1206 product specification Sep 03, 2004 V.2 (series-level repo copy; the RC1206FR-07 'RC_L' series sheet was not fetched)", "repo copy",
       repo_copy="validation-results/05-resonant-tank-envelope/sources/rc1206.pdf"),
    [R("V working", 200, "V", "RC1206 1/4 W maximum working voltage", "p.4 Characteristics table"),
     R("P rated", 0.25, "W", "at 70 C", "p.4")],
    [S("V per resistor static", 143, "V", "286 V static OVP / 2", ALTD3 + ":60"),
     S("P per resistor static", 0.093, "W", "143 V^2 / 220 kOhm", ALTD3 + ":60")],
    "Working voltage <= 80% of the maximum; power <= 50% at 70 C.",
    [C("V", "V working", "V per resistor static", 0.8, "violation", "72 %"),
     C("P", "P rated", "P per resistor static", 0.5, "violation", "37 %")],
    [L("RES_A/bus creepage across a 1206 body", RES_A)],
    gaps=["Series spec from 2004 used; confirm the RC1206FR-07 maximum working voltage (200 V) and overload (400 V) against the current Yageo RC_L sheet.",
          "Transient 451 V no-clamp corner would be 225 V per resistor, above the 200 V working figure but below the 400 V overload."])

E["RC1206FR-07470KL"] = entry(
    "RC1206FR-07470KL", "SAFETY", "Bus divider and resonant-bank bleed string R22-R29 (470 k, 4 in series)", "PARTIAL",
    DS("https://www.yageo.com/en/Product/Index/ChipResistorSurfaceMount", "Yageo RC1206 product specification Sep 03, 2004 V.2 (series-level repo copy)", "repo copy",
       repo_copy="validation-results/05-resonant-tank-envelope/sources/rc1206.pdf"),
    [R("V working", 200, "V", "RC1206 1/4 W maximum working voltage", "p.4 Characteristics table")],
    [S("V peak per resistor (bank bleed)", 160, "V", "640 V peak across C_res / 4", PARTS + ":486"),
     S("V per resistor (bus divider)", 50, "V", "198 V bus / 4", PARTS + ":486")],
    "Working voltage <= 80% of the maximum (peak counted against an RMS rating, conservative).",
    [C("bank", "V working", "V peak per resistor (bank bleed)", 0.8, "violation", "80 % exactly"),
     C("divider", "V working", "V per resistor (bus divider)", 0.8, "violation", "25 %")],
    [L("resistor-to-resistor creepage in the string", D5)],
    gaps=["Series spec from 2004; confirm against the current Yageo RC_L sheet.", "Pulse behaviour in the double-fault bank over-voltage case not compared to the pulse-voltage curves."])

# ----------------------------------------------------------------------------------------- J2/J5
E["74650074"] = entry(
    "74650074", "POWER", "Resonant-tank coil terminals J2/J5, Wuerth REDCUBE THR M4", "PARTIAL",
    DS(None, "Wuerth WP-THRBU 74650074; datasheet not fetched; limit is the parts.ato docstring", None),
    [R("I max @ 20C", 50, "A", "50 A max at 20 C, 1.2 N m torque (parts.ato docstring)", PARTS + ":21-28")],
    [S("I tank trip", 29.4, "A", "28 A ceiling, 29.4 A trip", D + ":824")],
    "Current <= 50% of the 20 C rating at the worst terminal temperature (no derating curve read).",
    [C("I", "I max @ 20C", "I tank trip", 0.6, "violation", "59 % of a 20 C figure; derated at hot ambient it is higher")],
    [L("four same-number pads are one terminal; copper to the terminal", D + ":841")],
    gaps=["Datasheet not fetched: temperature derating of the 50 A rating at the operating ambient is unknown; no voltage rating (PCB/lug spacing governs).",
          "Terminal contact temperature at 28 A not evidenced; bench IR list covers J2/J5 window only."])

# ----------------------------------------------------------------------------------------- unaudited power/safety
E["GRM31A5C3A102JW01D"] = entry("GRM31A5C3A102JW01D", "POWER", "Drain-source snubber capacitors C12/C13/C19/C20, 1 nF 1 kV C0G 1206", "UNAUDITED",
    gaps=["Not audited: 1 kV rating, DC-bias and dV/dt pulse current vs the 95 V/ns edge, no datasheet cited."])
E["1206W4F1003T5E"] = entry("1206W4F1003T5E", "SAFETY", "X-capacitor bleed R1/R2 (two 100 k in series across the mains)", "UNAUDITED",
    gaps=["Not audited: UNI-ROYAL 1206 working voltage and pulse rating vs 140 Vrms line and 1-2 kV surge; bleed time claim (FINDINGS #10) uses it."])

# ------------------------------------------------------------------------------------ minor functions
FN = {
 "CC0603KRX7R9BB104": "100 nF X7R 0603 decoupling/filter",
 "0603WAF1000T5E": "100 R 0603 permit/gate series", "0603WAF1003T5E": "100 k 0603 pull", "RT0603BRD0749K9L": "49.9 k dead-time resistor R9/R17",
 "CC0805KRX7R9BB104": "100 nF 0805 driver VDD decoupling", "CL21B105KBFNNNE": "1 uF 0805 driver straddle cap",
 "UMK325AB7106KM-T": "10 uF 1210 reservoirs", "GRM21BZ71E106KE15L": "10 uF 0805 bias reservoir", "GRM188R71E105KA12D": "1 uF 0603 bypass",
 "CL05B104KB54PNC": "100 nF 0402 bypass", "RL1206FR-070R68L": "0.68 R 1206 rail reservoir resistors", "6SVPC220MV": "220 uF polymer reservoir",
 "0603WAF4991T5E": "4.99 k 0603", "SN74LVC1G00DBVR": "NAND, DIS = NAND(PERMIT, BIAS_GOOD)", "0603WAF1002T5E": "10 k 0603",
 "RC1206FR-073R9L": "3.9 R gate resistors R10/R12/R18/R20 (gate loop, Tj 107 C vs 155 C class, unverified)", "C0603C102J5GACTU": "1 nF C0G 0603",
 "PMEG6030EP,115": "Schottky D6-D9 (negative gate bias)", "1206W4F100KT5E": "100 k 1206", "RC1206FR-072K2L": "2.2 k 1206", "SN74LVC1G17DBVR": "Schmitt buffer",
 "TPS70950DBVR": "5 V LDO (HOT5)", "RT0603BRD0715K8L": "15.8 k 0.1 % bus divider bottom", "LM4040A25IDBZR": "2.5 V reference", "RT0603BRD0710KL": "10 k 0.1 %",
 "CL10C101JB8NNNC": "100 pF 0603", "RT0603BRD0712K6L": "12.6 k 0.1 % OCP threshold", "TNPW060311K7BEEA": "11.7 k 0.1 % OCP threshold", "TLV3201AIDBVR": "40 ns comparators",
 "RT0603BRD07140KL": "140 k 0.1 % OVP", "SN74LVC1G10DBVR": "3-input NAND", "0430451612": "Molex Micro-Fit controller connector J4 (low-voltage SELV signals)",
 "0603WAF0000T5E": "0 R link R38 (PE to SELV GND, functional)", "RC1206FR-073RL": "3.0 R CT burden", "GRM31C5C1H104JA01L": "100 nF C0G 1206",
 "RT0603BRD071KL": "1 k 0.1 %", "1206W4F1001T5E": "1 k 1206", "BAS116H,115": "low-leakage diode", "RT0603BRD072K21L": "2.21 k", "SN74LVC1G332DBVR": "OR gate",
 "0603WAF1001T5E": "1 k 0603", "TPS3700DDCR": "HOT5 window supervisor", "RT0603BRD07105KL": "105 k 0.1 %", "TPS7A4700RGWR": "low-noise LDO U26 (V15_LS), Tj 89 C, 36 K margin (DECISIONS.md:825)",
 "TLVH431BQDBZR": "adjustable shunt", "RT0603BRD076K2L": "6.2 k", "TL431AIDBZR": "adjustable shunt", "RT0603BRD074K42L": "4.42 k", "RT0603BRD077K68L": "7.68 k",
 "RT0603BRD07120KL": "120 k", "ARG03BTC1333": "133 k", "LM339BIDR": "quad comparator", "1N4148W": "signal diode", "MMBT3904": "NPN",
 "0603WAF2702T5E": "27 k", "CL10C331JB8NNNC": "330 pF", "RT0603BRD0763K4L": "63.4 k", "RT0603BRD0711KL": "11 k", "SN74LVC1G14DBVR": "Schmitt inverter",
 "RC1206FR-0716K5L": "16.5 k 1206", "0603WAF3302T5E": "33 k", "RT0603BRD0710KL ": "",
}
CLS = {}  # everything not set above is SIGNAL


def main():
    bom = {}
    with open(U / "native-21/frozen/default.csv", newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            bom.setdefault(row["LCSC"].strip(), []).extend(d.strip() for d in row["Designator"].split(",") if d.strip())
    entries = {}
    for mpn, des in bom.items():
        e = E.get(mpn)
        if e is None:
            e = entry(mpn, CLS.get(mpn, "SIGNAL"), FN.get(mpn, "passive/IC, role per schematic"), "UNAUDITED",
                      gaps=["Not audited (outside SAFETY/POWER)."])
        e["designators"] = des
        e["class"] = CLS.get(mpn, e["class"])
        entries[mpn] = finish(e)
    out = {"schema": 1, "seeded": FETCHED, "unit_root": "zapote/power-stage-120v",
           "statuses": ["VERIFIED", "PARTIAL", "UNAUDITED", "VIOLATION"], "entries": entries}
    (HERE / "ledger.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    unknown = sorted(set(E) - set(bom))
    print(f"{len(entries)} entries written; ledger-only keys: {unknown}")


if __name__ == "__main__":
    main()
