#!/usr/bin/env python3
"""Hand / consign / THT lines of the stage-20 BOM: who can assemble them, what JLC charges, what stays in-house.

    python3 -I assembly_cost.py  ->  results/assembly_cost.json (+ a table on stdout)

Fee constants are JLC's published 'PCB Assembly Cost' table, read 2026-10-13 (URL in PROPOSALS.md section 1).
IN-HOUSE LABOUR numbers are ASSUMPTIONS (marked), not sourced: change them at the top and rerun.
Joint counts come from the stage-20 copper dump (plated holes per reference), not from a datasheet.
"""
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import R2, bom, copper, designators, stock

# ---- JLC fees (USD), https://jlcpcb.com/help/article/pcb-assembly-price, 2026-10-13 ------------------------------
JLC = {
    "std_setup_1side": 25.56, "std_stencil_1side": 8.21, "std_stencil_storage": 4.93,
    "std_feeder_per_line": 1.53,                      # Standard: every basic/extended line
    "eco_setup": 8.18, "eco_stencil": 1.53, "eco_feeder_per_ext_line": 3.07,   # Economic: extended lines only
    "smt_per_joint": 0.0016, "manual_per_joint": 0.0164, "hand_labour_per_order": 3.58,
    "confirm_placement": 0.45,
    "fixtures_1_29": 16.42, "fixtures_500_plus": 164.18,                       # Standard rigid, per order
    # consigned/loose parts (jlcpcb.com/help/article/consignment-part-terms-conditions; pages disagree, see PROPOSALS)
    "consign_per_piece": 0.142, "consign_per_pin_le5": 0.017, "consign_cap_gt5": 0.078,
    "consign_parcel_oneoff": 85.0,                    # agent/customs fee quoted as 45..85 USD per parcel
}
# ---- in-house labour: ASSUMPTIONS ---------------------------------------------------------------------------------
LABOUR = {"usd_per_hour": 45.0,
          "s_per_joint_small": 25, "s_per_joint_power": 90,    # power = TO-247, BR1, REDCUBE, film/bank caps, PS, F1 clips
          "s_insert_per_part": 30, "s_trim_per_lead": 8}       # lead trim stays in-house either way (ASSEMBLY.md)
POWER_REFS = ("Q", "BR", "J2", "J5", "J7", "J8", "J9", "J10", "C21", "C22", "C23", "C151", "C152", "C5", "C6", "C38",
              "C39", "C40", "C41", "PS", "F1", "L1", "D3", "D17", "J3", "J11", "J1")

cu = copper()
joints = collections.defaultdict(set)
smd_joints = set()
for p in cu["primitives"]:
    if p["kind"] != "pad" or p["layer"] != "F.Cu" and p["layer"] != "B.Cu":
        continue
    ref = p["ref"].split(".")[0]
    key = (p["ref"], tuple(p["centre"]))
    if p["drill_mm"] != [0.0, 0.0]:
        joints[ref].add(key)
    else:
        smd_joints.add(key)

st = stock()
lines = []
for r in bom():
    mount = r["Mount"]
    asm = r["Assembly"]
    consign = ("consign" in asm.lower()) or ("hand" in asm.lower())
    if not (mount == "THT" or consign):
        continue
    refs = designators(r)
    mpn = r["Manufacturer Part Number"].strip()
    s = st.get(mpn, {})
    nj = sum(len(joints.get(x, ())) for x in refs)
    jlc_stock = s.get("jlc_stock_per_bom(date)", "")
    try:
        stock_n = int(jlc_stock.split()[0])
    except Exception:
        stock_n = None
    lines.append({
        "refs": refs, "qty": len(refs), "mpn": mpn, "lcsc": r["LCSC Part #"], "mount": mount, "bom_assembly": asm[:40],
        "plated_joints": nj, "smd_joint_if_smd": 0 if mount == "THT" else None,
        "jlc_stock": stock_n, "unit5": s.get("unit_usd_at_5boards"), "unit500": s.get("unit_usd_at_500boards"),
        "has_lcsc": bool(r["LCSC Part #"]),
        "power": any(x.startswith(POWER_REFS) for x in refs),
    })
# the clip line that is outside the BOM
lines.append({"refs": ["F1-CLIP x2"], "qty": 2, "mpn": "01250003H", "lcsc": "C223911", "mount": "THT",
              "bom_assembly": "hand-assembly-extras.csv", "plated_joints": 4, "has_lcsc": True, "jlc_stock": None,
              "power": True, "unit5": None, "unit500": None})

n_lines = len(lines)
tht = [l for l in lines if l["mount"] == "THT"]
smd_consign = [l for l in lines if l["mount"] != "THT"]


def labour_usd(ls):
    t = 0
    for l in ls:
        if l["mount"] != "THT":
            continue
        t += l["plated_joints"] * (LABOUR["s_per_joint_power"] if l["power"] else LABOUR["s_per_joint_small"])
        t += l["qty"] * LABOUR["s_insert_per_part"] + l["plated_joints"] * LABOUR["s_trim_per_lead"]
    return t / 3600 * LABOUR["usd_per_hour"], t / 60


def trim_only(ls):
    t = sum(l["plated_joints"] * LABOUR["s_trim_per_lead"] for l in ls if l["mount"] == "THT")
    return t / 3600 * LABOUR["usd_per_hour"], t / 60


def jlc_manual_fee(ls, boards):
    j = sum(l["plated_joints"] for l in ls if l["mount"] == "THT")
    return j * JLC["manual_per_joint"], j


def consign_fee_per_board(ls):
    f = 0
    for l in ls:
        if l["has_lcsc"] and l["lcsc"] and l["lcsc"] != "":     # in JLC library: no loose-part fee
            continue
        pins = l["plated_joints"] // max(l["qty"], 1) if l["mount"] == "THT" else 0
        per = JLC["consign_per_piece"] + (JLC["consign_per_pin_le5"] * pins if 0 < pins <= 5 else JLC["consign_cap_gt5"] if pins > 5 else 0)
        f += per * l["qty"]
    return f


def stock_ok(l, boards):
    return l["jlc_stock"] is not None and l["jlc_stock"] >= l["qty"] * boards


# Lines that must stay in-house whatever JLC offers (reason, source):
KEEP_HAND = {"Q2": "seat-before-solder fixture on the M11 sink (SINK-DRAWING-NOTES.md Acceptance: coplanar 0.05 mm)",
             "BR1": "same fixture, 0.665 mm step at BR1 (SINK-DRAWING-NOTES.md)",
             "F1-CLIP x2": "plated-slot clips, cartridge inserted after cleaning (FAB-NOTE.md)"}
for l in lines:
    l["keep_hand_reason"] = next((v for k, v in KEEP_HAND.items() if k in l["refs"] or k in l["refs"][0]), "")
lcsc_lines = [l for l in tht if l["has_lcsc"] and l["lcsc"] and l["refs"] != ["F1-CLIP x2"] and not l["keep_hand_reason"]]
no_lcsc = [l for l in lines if not (l["has_lcsc"] and l["lcsc"]) or l["refs"] == ["F1-CLIP x2"]]
kept = [l["refs"] for l in lines if l["keep_hand_reason"]]
res = {"assumptions_labour": LABOUR, "jlc_fees": JLC, "lines": lines, "n_lines": n_lines}
res["keep_hand"] = {",".join(l["refs"]): l["keep_hand_reason"] for l in lines if l["keep_hand_reason"]}
res["counts"] = {"lines_total": n_lines, "tht_lines_in_bom": len([l for l in tht if l["refs"] != ["F1-CLIP x2"]]),
                 "smd_consign_lines": len(smd_consign), "tht_parts": sum(l["qty"] for l in tht if l["refs"] != ["F1-CLIP x2"]),
                 "tht_plated_joints": sum(l["plated_joints"] for l in tht),
                 "lines_with_lcsc": len(lcsc_lines), "lines_without_lcsc": len(no_lcsc)}

scen = {}
for boards in (5, 500):
    base_hand_usd, base_hand_min = labour_usd(lines)           # everything THT by hand in-house (PROTOTYPE-LOT.md)
    # S1: LCSC-coded THT go to JLC manual/wave line; the rest in-house
    s1_moved = [l for l in tht if l in lcsc_lines]
    s1_left = [l for l in lines if l not in s1_moved]
    s1_hand_usd, s1_min = labour_usd(s1_left)
    tr_usd, tr_min = trim_only(s1_moved)
    s1_hand_usd += tr_usd; s1_min += tr_min
    s1_fee, s1_j = jlc_manual_fee(s1_moved, boards)
    s1_fee += sum(JLC["std_feeder_per_line"] for _ in s1_moved) / boards
    # S1s: only the LCSC lines whose JLC stock covers this order today (2026-10-13 survey figures)
    s1s_moved = [l for l in s1_moved if stock_ok(l, boards)]
    s1s_left = [l for l in lines if l not in s1s_moved]
    a, m = labour_usd(s1s_left); t_usd, t_min = trim_only(s1s_moved)
    a += t_usd; m += t_min
    f, j = jlc_manual_fee(s1s_moved, boards)
    f += sum(JLC["std_feeder_per_line"] for _ in s1s_moved) / boards + JLC["hand_labour_per_order"] / boards
    s1s = {"lines_moved": [x["refs"] for x in s1s_moved], "joints_moved": j, "jlc_fee_per_board": round(f, 2),
           "hand_usd_per_board": round(a, 2), "hand_min_per_board": round(m, 1),
           "net_saving_per_board": round(base_hand_usd - a - f, 2)}
    # S2: everything incl. consigned THT goes to JLC
    s2_moved = [l for l in tht if not l["keep_hand_reason"]]
    s2_left = [l for l in lines if l not in s2_moved]
    s2_hand_usd, s2_min = labour_usd(s2_left)
    t_usd, t_min = trim_only(s2_moved)
    s2_hand_usd += t_usd; s2_min += t_min
    s2_fee, s2_j = jlc_manual_fee(s2_moved, boards)
    s2_fee += (consign_fee_per_board(s2_moved) + sum(JLC["std_feeder_per_line"] for _ in s2_moved) / boards
               + JLC["consign_parcel_oneoff"] / boards)
    onetime = JLC["hand_labour_per_order"] / boards
    scen[boards] = {
        "S0_all_THT_in_house": {"hand_usd_per_board": round(base_hand_usd, 2), "hand_min_per_board": round(base_hand_min, 1)},
        "S1_LCSC_THT_to_JLC": {"lines_moved": len(s1_moved), "joints_moved": s1_j, "jlc_fee_per_board": round(s1_fee + onetime, 2),
                               "hand_usd_per_board": round(s1_hand_usd, 2), "hand_min_per_board": round(s1_min, 1),
                               "net_saving_per_board": round(base_hand_usd - s1_hand_usd - s1_fee - onetime, 2),
                               "lines_without_jlc_stock": [l["refs"] for l in s1_moved if not stock_ok(l, boards)]},
        "S1s_only_lines_with_JLC_stock_today": s1s,
        "S2_all_THT_to_JLC_with_consign": {"lines_moved": len(s2_moved), "joints_moved": s2_j,
                               "jlc_fee_per_board": round(s2_fee + onetime, 2), "hand_usd_per_board": round(s2_hand_usd, 2),
                               "hand_min_per_board": round(s2_min, 1),
                               "net_saving_per_board": round(base_hand_usd - s2_hand_usd - s2_fee - onetime, 2)},
    }
res["scenarios_per_board"] = scen
res["smd_joints_total"] = len(smd_joints)
res["smt_fee_per_board"] = round(len(smd_joints) * JLC["smt_per_joint"], 2)
res["scorecard_note"] = ("scorecard.cost() counts every Mount=THT line plus hand-assembly-extras as 'hand_or_consign_lines'; "
                         "sending a THT line to JLC does not move that metric. Only deleting the line or making it SMD does.")
json.dump(res, open(R2 / "results/assembly_cost.json", "w"), indent=1)
print(json.dumps(res["counts"]), res["smd_joints_total"], res["smt_fee_per_board"])
for b, s in scen.items():
    print(b, json.dumps(s, indent=1))
for l in lines:
    print(l["refs"], l["mpn"], l["lcsc"], l["plated_joints"], "stock", l["jlc_stock"], "pow" if l["power"] else "")
