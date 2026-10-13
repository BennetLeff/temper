#!/usr/bin/env python3 -I
"""Fabrication, parts and assembly deltas for S1 / S2-A / S2-B vs the stage-20 single board, at 5 and 500 boards.
    python3 -I cost_model.py -> ../results/cost_model.json (+ prints a summary)
SOURCED inputs: JLC 4-layer board charge 70.6 USD/m2 (jlcpcb.com/news/discount-on-quality-4-layer-pcbs, 2024-03; 'standard
base rate' restated in jlcpcb.com/news/jlcpcb-fr4-pcb-price-adjustment-august2026); assembly fee table and labour model from
r2-dfm (jlcpcb.com/help/article/pcb-assembly-price, read 2026-10-13); part ladders from the JLC component API (raw/jlc/).
ASSUMPTIONS, all labelled UNVERIFIED in the output: heavy-copper / ENIG / POFV multipliers (third-party 1.15-1.30, r2-dfm grid),
2-layer rate factor, design (engineering) fee per added design, board density for area estimates, stand-off / wire allowances,
labour minutes. A JLC instant quote on the real Gerbers replaces all of them."""
import csv, json, math, sys
sys.dont_write_bytecode = True
from pathlib import Path
HERE = Path(__file__).resolve().parent; OUT = HERE.parent; PS = HERE.parents[3]
sys.path.insert(0, str(HERE))
import netparse, jlc_lib
part = json.load(open(OUT/"results/partition.json"))
fp = netparse.footprints()
A2 = json.load(open(PS/"validation-results/11-candidates/r2-dfm/results/assembly_cost.json"))
F = A2["jlc_fees"]
bom = list(csv.DictReader(open(PS/"validation-results/08-manufacturing-package/native-21/fab/bom-jlcpcb.csv")))
LABOUR_USD_H = 45.0           # r2-dfm assumption
res = {"assumptions": {}}

# ------------------------------------------------------------------ assembly fee model (r2-dfm jlc_order_model.py, per board design)
KS, KT = 1.0, 1.0      # joint-count calibration to r2-dfm (961 SMD / 96 THT joints), set below
def jlc_order(refs, boards):
    """JLC Standard order for the JLC-routed lines present on this board (r2-dfm routing: every row whose Assembly starts 'JLC')."""
    rs = set(refs); lines = 0; smd = 0; tht = 0
    for row in bom:
        ds = [d.strip() for d in row["Designator"].split(",")]
        on = [d for d in ds if d in rs]
        if not on or not row["Assembly"].startswith("JLC"): continue
        lines += 1
        for d in on:
            if d in fp:
                smd += fp[d]["smd"]*KS; tht += (fp[d]["tht"]*KT if row["Mount"] == "THT" else 0)
    if lines == 0: return dict(lines=0, total=0.0, per_board=0.0, smd=0, tht=0)
    fix = F["fixtures_1_29"] if boards < 30 else F["fixtures_500_plus"]
    stencil = F["std_stencil_1side"] + F["std_stencil_storage"] if smd else 0.0
    tot = (F["std_setup_1side"] + stencil + F["std_feeder_per_line"]*lines + fix + F["confirm_placement"] + F["hand_labour_per_order"]
           + boards*(smd*F["smt_per_joint"] + tht*F["manual_per_joint"]))
    return dict(lines=lines, total=round(tot, 2), per_board=round(tot/boards, 2), smd=smd, tht=tht)
def all_refs(): return set(fp)
_raw = jlc_order(all_refs(), 5)
KS, KT = 961/_raw["smd"], 96/_raw["tht"]       # my pad counts give 833/80 in JLC lines; r2-dfm counted 961/96 joints
res["joint_calibration"] = dict(KS=round(KS, 4), KT=round(KT, 4))
base = {n: jlc_order(all_refs(), n) for n in (5, 500)}
res["baseline_assembly_check"] = dict(mine=base, r2_dfm={"5": 203.23, "500": 1891.43})

# ------------------------------------------------------------------ parts adders (JLC ladder at qty boards x pins/pcs)
def jp(code, qty):   # unit price at qty pieces
    return jlc_lib.price_at(code, qty)
ADD = {}
def add(opt, name, code, per_board, note, price_override=None, src=None):
    ADD.setdefault(opt, []).append(dict(name=name, code=code, qty=per_board, note=note, price_override=price_override, src=src))
EST = "UNVERIFIED engineering allowance (no price source)"
# S1: second mains terminal (module cord inlet); harness wire; PE lug; standoffs
add("S1", "Phoenix 1711725 5.08 mm 2-pos terminal, 24 A / 400 V (J_in on inlet module; J1 stays as harness input)", "C89120", 1, "JLC ext, 1986 pcs")
add("S1", "harness 2x 12 AWG UL1015 + PE 14 AWG, 300 mm, 5 ferrules, strain relief", None, 1, EST, price_override=3.00)
add("S1", "PE ring lug + M4 screw/washer at module", None, 1, EST, price_override=0.60)
add("S1", "4x M3 stand-offs + screws + cover fixings for module", None, 1, EST, price_override=1.20)
# S2-A: J_SELV 2x10 + J_HOT 2x5 (2.54 mm) board-to-board pairs, 4 stand-offs
for o in ("S2A",):
    add(o, "2.54 mm 2x10 pin header HanElectricity 2541WV-2x10P (D board) - SELV signals", "C5383109", 1, "JLC ext")
    add(o, "2.54 mm 2x10 female header HanElectricity 2541FV-2x10P (P board)", "C18722936", 1, "JLC ext")
    add(o, "2.54 mm 2x5 pin header CJT A2541WV-2x5P (D) - HOT sense, >= 8 mm from J_SELV", "C225520", 1, "JLC ext")
    add(o, "2.54 mm 2x5 female header CJT A2541HWV-2x5P (P)", "C239345", 1, "JLC ext")
    add(o, "4x M3 stand-offs 11 mm + screws (stack, 8 mm HOT/SELV air gap)", None, 1, EST, price_override=1.20)
# S2-L: SELV-only interface board: one 2x10 pair
add("S2L", "2.54 mm 2x10 pin header 2541WV-2x10P (D)", "C5383109", 1, "JLC ext")
add("S2L", "2.54 mm 2x10 female header 2541FV-2x10P (P)", "C18722936", 1, "JLC ext")
add("S2L", "4x M3 stand-offs + screws", None, 1, EST, price_override=1.20)
# S2-B: gate/sw/bias 2x20 x2 + SELV 2x10 + HOT-sense 2x5
add("S2B", "2.54 mm 2x20 pin header HanElectricity 2541WV-2x20P x2 (D)", "C25503140", 2, "JLC ext")
add("S2B", "2.54 mm 2x20 female header HanElectricity 2541FV-2x20P-B x2 (P)", "C25503128", 2, "JLC ext")
add("S2B", "2.54 mm 2x10 pin header 2541WV-2x10P (D) - SELV", "C5383109", 1, "JLC ext")
add("S2B", "2.54 mm 2x10 female header 2541FV-2x10P (P)", "C18722936", 1, "JLC ext")
add("S2B", "2.54 mm 2x5 pin header A2541WV-2x5P (D) - HOT sense", "C225520", 1, "JLC ext")
add("S2B", "2.54 mm 2x5 female header A2541HWV-2x5P (P)", "C239345", 1, "JLC ext")
add("S2B", "6x M3 stand-offs 11 mm + screws", None, 1, EST, price_override=1.80)
# low-L alternative for the gate connectors (S2-B 'Samtec'): 0.8 mm ERM8/ERF8-020 x2 pairs instead of the 2x20 pairs
add("S2B_low_L", "Samtec ERM8-020-09.0-L-DV-K-TR (JLC C6244310, stock 92) x2", "C6244310", 2, "stock 92 < 500 boards x2: not buyable at volume from JLC")
add("S2B_low_L", "Samtec ERF8-020-05.0-L-DV-K-TR (JLC C3650951, stock 50) x2", "C3650951", 2, "stock 50")
def parts_cost(opt, boards):
    tot = 0.0; rows = []
    for a in ADD.get(opt, []):
        if a["price_override"] is not None: u = a["price_override"]
        else: u = jp(a["code"], a["qty"]*boards)
        rows.append(dict(a, unit=u, ext=round(u*a["qty"], 3))); tot += u*a["qty"]
    return round(tot, 2), rows

# ------------------------------------------------------------------ fabrication model
RATE4 = 70.6                      # USD/m2, SOURCED (see header)
CU = (1.15, 1.30)                 # 2 oz all layers vs basic: third-party range (r2-dfm), UNVERIFIED
FIN = (1.0, 1.25, 1.5)            # ENIG+epoxy-filled/capped (POFV) adder on the 4-layer board: r2-dfm sensitivity grid, UNVERIFIED
F2 = 0.6                          # 2-layer rate / 4-layer rate, UNVERIFIED (no JLC 2-layer rate found)
ENG = (0.0, 35.7)                 # design fee per added design at 5 boards: 0 .. (2024 example total 106.30 - board 70.60), UNVERIFIED
DENS = 0.40                       # courtyard / board area for a re-laid block (board average here is 0.42, see below)
def board_area_mm2(courtyard_mm2, extra_mm2=0.0, density=DENS): return courtyard_mm2/density + extra_mm2
MAIN = dict(area=55100.0)         # bbox of the current 290x190 board, billed area (scorecard board_bbox_mm2)
cur_courtyard = sum(part["S1"][s]["courtyard_mm2"] for s in "IM")
res["current_courtyard_mm2"] = cur_courtyard; res["current_density_vs_bbox"] = round(cur_courtyard/55100, 3)
def fab(area_mm2, layers, mult, boards, eng):
    rate = RATE4*(1.0 if layers == 4 else F2)
    return round(area_mm2*1e-6*rate*mult + eng/boards, 2)
fab_rows = {}
def fabs(label, area, layers, copper_oz, fin_mult):
    """return per-board fab cost at 5 and 500 for low / mid / high multiplier scenarios"""
    out = {}
    cm = {"low": CU[0] if copper_oz == 2 else 1.0, "mid": (CU[0]+CU[1])/2 if copper_oz == 2 else 1.0, "high": CU[1] if copper_oz == 2 else 1.0}
    fm = {"low": fin_mult[0], "mid": fin_mult[1], "high": fin_mult[2]}
    for sc in ("low", "mid", "high"):
        m = cm[sc]*fm[sc]
        out[sc] = {n: fab(area, layers, m, n, ENG[0] if sc == "low" else ENG[1]) for n in (5, 500)}
    return dict(area_mm2=round(area), layers=layers, copper_oz=copper_oz, fin_mult=fin_mult, usd_per_board=out)
MAIN_FIN = FIN                    # (low, mid, high)
D_FIN = (1.0, 1.1, 1.25)          # drive board: ENIG optional, no POFV needed (passive-pad vias in pad by convention only, r2-dfm)
cases = {}
cases["current"] = {"main": fabs("main", MAIN["area"], 4, 2, MAIN_FIN)}
# S1: inlet module 2-layer 2 oz, area from courtyards of G01 (minus BR1) plus the D-22 module parts, density as the D-22 envelope
d22_courtyard = 45*25.5 + 26.5*14.5 + 2*31.5*21 + 2*13*5 + 2*13*4 + 18*7.5 + 2*10*4      # PARTS.md body sizes (mm), the 2 bleed R sized 10x4 (assumed)
res["d22_courtyard_mm2"] = round(d22_courtyard)
mod_court = part["S1"]["I"]["courtyard_mm2"] + d22_courtyard - 2*(4.3*1.6)*0          # R1/R2 are 1206 SMD: negligible
mod_area = board_area_mm2(mod_court, density=0.375)           # 0.375 = 3304 / (110x80), the D-22 envelope density
res["S1_module"] = dict(courtyard_mm2=round(mod_court), area_mm2=round(mod_area), approx_side_mm=round(math.sqrt(mod_area)))
# main board after S1: outline reclaim scenarios
freed = part["S1"]["I"]["courtyard_mm2"]/res["current_density_vs_bbox"]
cases["S1"] = {"main_reclaim0": fabs("main", MAIN["area"], 4, 2, MAIN_FIN),
               "main_reclaim100": fabs("main", MAIN["area"]-freed, 4, 2, MAIN_FIN),
               "module": fabs("module", mod_area, 2, 2, (1.0, 1.0, 1.0))}
res["S1_freed_area_mm2_if_fully_reclaimed"] = round(freed)
for opt in ("S2A", "S2B", "S2L"):
    dcourt = part[opt]["D"]["courtyard_mm2"]
    conn_area = {"S2A": 400.0, "S2B": 900.0, "S2L": 250.0}[opt]           # connector bodies + 8 mm HOT/SELV keepout strip + mounting holes (assumed)
    darea = board_area_mm2(dcourt, conn_area)
    pfreed = dcourt/res["current_density_vs_bbox"]
    cases[opt] = {"power_reclaim0": fabs("power", MAIN["area"], 4, 2, MAIN_FIN),
                  "power_reclaim100": fabs("power", MAIN["area"]-pfreed, 4, 2, MAIN_FIN),
                  "drive": fabs("drive", darea, 4, 1, D_FIN)}
    res[opt+"_dims"] = dict(drive_courtyard_mm2=dcourt, drive_area_mm2=round(darea), approx_side_mm=round(math.sqrt(darea)), power_freed_mm2_if_reclaimed=round(pfreed))
res["fab_cases"] = cases

# ------------------------------------------------------------------ assembly + totals
def tot_fab(opt, key, sc, n):
    c = cases[opt]
    if opt == "current": return c["main"]["usd_per_board"][sc][n]
    if opt == "S1": return c[key]["usd_per_board"][sc][n] + c["module"]["usd_per_board"][sc][n]
    return c[key]["usd_per_board"][sc][n] + c["drive"]["usd_per_board"][sc][n]
summary = {}
LAB_MIN = {"S1": 8.0, "S2A": 4.0, "S2B": 5.0, "S2L": 3.0}     # minutes of in-house work per set: harness make/fit (S1), stack+mate+screws (S2): UNVERIFIED
summary["current"] = {n: dict(fab_low=tot_fab("current", None, "low", n), fab_mid=tot_fab("current", None, "mid", n), fab_high=tot_fab("current", None, "high", n),
                              asm_jlc=base[n]["per_board"], parts_added=0.0, labour_added=0.0) for n in (5, 500)}
S1_M = [r for r in part["S1"]["refs"]["M"]]; S1_I = part["S1"]["refs"]["I"]
for opt in ("S1", "S2A", "S2B", "S2L"):
    refsP = part[opt]["refs"]["M" if opt == "S1" else "P"]; refsD = part[opt]["refs"]["I" if opt == "S1" else "D"]
    summary[opt] = {}
    for n in (5, 500):
        pc, rows = parts_cost(opt, n)
        if opt == "S1":
            asm = jlc_order(refsP, n)["per_board"]            # module is THT only: assembled in house (labour already in the baseline)
            asm_extra = 0.0
        else:
            aP = jlc_order(refsP, n); aD = jlc_order(refsD, n); asm = aP["per_board"]+aD["per_board"]
            asm_extra = aD["total"]
        lab = LAB_MIN[opt]/60*LABOUR_USD_H
        summary[opt][n] = dict(fab_low=tot_fab(opt, "reclaim0" if opt == "S1" else "power_reclaim0", "low", n) if False else None)
        k0 = "main_reclaim0" if opt == "S1" else "power_reclaim0"; k1 = "main_reclaim100" if opt == "S1" else "power_reclaim100"
        summary[opt][n] = dict(
            fab_reclaim0={sc: tot_fab(opt, k0, sc, n) for sc in ("low", "mid", "high")},
            fab_reclaim100={sc: tot_fab(opt, k1, sc, n) for sc in ("low", "mid", "high")},
            asm_jlc=round(asm, 2), asm_jlc_second_order=round(asm_extra/n, 2) if opt != "S1" else 0.0,
            parts_added=pc, labour_added=round(lab, 2), parts_rows=rows)
res["summary_per_board"] = summary
# deltas vs current (reclaim0 = outline unchanged; reclaim100 = freed area fully reclaimed)
delta = {}
for opt in ("S1", "S2A", "S2B", "S2L"):
    delta[opt] = {}
    for n in (5, 500):
        s = summary[opt][n]; c = summary["current"][n]
        d = {}
        for tag in ("reclaim0", "reclaim100"):
            for sc in ("low", "mid", "high"):
                d[f"fab_{tag}_{sc}"] = round(s[f"fab_{tag}"][sc] - c[f"fab_{sc}"], 2)
        d["asm_jlc"] = round(s["asm_jlc"] - c["asm_jlc"], 2); d["parts"] = s["parts_added"]; d["labour"] = s["labour_added"]
        d["total_excl_fab"] = round(d["asm_jlc"] + d["parts"] + d["labour"], 2)
        delta[opt][n] = d
res["delta_vs_current_per_board_usd"] = delta
# S1 against the PLAN (board + separate D-22 module with a 15 USD carrier/terminal/cover allowance, PARTS.md)
vs_plan = {}
for n in (5, 500):
    mf = {sc: cases["S1"]["module"]["usd_per_board"][sc][n] for sc in ("low", "mid", "high")}
    pc = summary["S1"][n]["parts_added"]
    vs_plan[n] = {sc: round(mf[sc] + pc - 15.0, 2) for sc in mf}
res["S1_vs_plan_usd_per_board"] = dict(formula="module PCB fab + added parts - 15.00 carrier allowance (labour: plan also needs a harness, so not counted)", values=vs_plan)
json.dump(res, open(OUT/"results/cost_model.json", "w"), indent=1)
print(json.dumps(res["S1_vs_plan_usd_per_board"]))
print(json.dumps({k: res[k] for k in ("baseline_assembly_check", "S1_module", "S2A_dims", "S2B_dims", "current_density_vs_bbox")}, indent=1))
print(json.dumps(delta, indent=1))
