#!/usr/bin/env python3
"""Placement / BOM-line / parts-cost deltas for the G05+G07 proposals.

    python3 -I validation-results/11-candidates/g05-g07-drive-monitor/scripts/parts_cost.py
(from zapote/power-stage-120v). Offline: reads the committed BOM, parts.json, the 2026-10-13 stock CSV and the
JLC records cached in ../evidence/jlc-raw. Writes ../results/parts_cost.json.

Two dollar columns, because they differ a lot:
  scorecard = what scorecard.py will show: STOCK-2026-10-13.csv unit_usd_at_500boards (many are class-default
              ESTIMATES, e.g. MMBT3904 0.40, ISO7710DWR 1.287 from DK) for existing parts;
  real      = JLC public price tier at (qty per board x 500 boards) for the parts in evidence/jlc-raw, else the
              scorecard figure.
Parts that are not in the stock CSV (new MPNs) use the JLC tier price in both columns.
"""
import csv, glob, json, os, sys
from collections import Counter, defaultdict

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..")
PS = os.path.abspath(os.path.join(HERE, "../../../.."))
BOM = f"{PS}/validation-results/08-manufacturing-package/native-21/fab/bom-jlcpcb.csv"
STOCK = f"{PS}/validation-results/08-manufacturing-package/native-21/sourcing/STOCK-2026-10-13.csv"
PARTS = f"{PS}/native-21/layout/parts.json"
GROUPS = f"{PS}/validation-results/11-candidates/groups.json"
RAW = f"{OUT}/evidence/jlc-raw"
BOARDS = 500

bom_rows = list(csv.DictReader(open(BOM)))
ref_row = {d.strip(): r for r in bom_rows for d in r["Designator"].split(",")}
mpn_of = {d: r["Manufacturer Part Number"].strip() for d, r in ref_row.items()}
cls_of = {}
for r in bom_rows:
    a = r["Assembly"]
    cls_of[r["Manufacturer Part Number"].strip()] = ("Extended" if "Extended" in a else "Basic" if "Basic" in a else "hand/consign")
path_of = {p["ref"]: p["path"] for p in json.load(open(PARTS))}
ref_of_path = {v: k for k, v in path_of.items()}
group_of = json.load(open(GROUPS))["assignment"]
stock = {}
for r in csv.DictReader(open(STOCK)):
    if r["board"].startswith("power"):
        stock[r["mpn"].strip()] = r

def sc_price(mpn):
    try:
        return float(stock[mpn]["unit_usd_at_500boards"])
    except Exception:
        return None

jlc = {}
for f in glob.glob(f"{RAW}/detail_*.json"):
    d = json.load(open(f))["data"]
    jlc[d["componentModelEn"].split("(")[0]] = d

def jlc_price(model, qty_per_board):
    d = jlc[model]
    q = qty_per_board * BOARDS
    best = None
    for t in d["prices"]:
        if q >= t["startNumber"]:
            best = t["productPrice"]
    return best, d["componentCode"], d["componentLibraryType"], d["stockCount"]

# real-price lookup for existing parts that have a cached JLC record (model string -> BOM MPN)
REAL = {"MMBT3904": "MMBT3904", "1N4148W": "1N4148W", "ISO7710DWR": "ISO7710DWR", "LM339BIDR": "LM339BIDR",
        "TL431AIDBZR": "TL431AIDBZR", "SN74LVC1G332DBVR": "SN74LVC1G332DBVR", "TPS70950DBVR": "TPS70950DBVR", "SN74LVC1G10DBVR": "SN74LVC1G10DBVR",
        "AO3400A": "AO3400A", "SN74LVC1G32DBVR": "SN74LVC1G32DBVR", "SN74LVC1G17DBVR": "SN74LVC1G17DBVR"}

def real_price(mpn, qpb):
    if mpn in REAL and REAL[mpn] in jlc:
        return jlc_price(REAL[mpn], qpb)[0]
    return sc_price(mpn) or 0.0

# ---------------------------------------------------------------- proposals
MON = ["monitor_ls", "bias_ha.monitor", "bias_hb.monitor"]
def mon_ref(m, part):
    return ref_of_path[f"{m}.{part}"]

NOTICE = [mon_ref(m, p) for m in MON for p in ("dnotice", "qnotice", "rnotice", "rbase")]
ISO = [mon_ref(m, "iso") for m in MON]            # U32, U33, U34
OR3 = ref_of_path["bias_or"]                       # U25

PROPOSALS = {
    "P1_notice_stage_replaced_by_one_inverter": dict(
        desc="Replace the 4-part NPN 'notice' stage per rail (D, NPN, 1 k, 10 k) by one SN74LVC1G10 (NAND3 with its three inputs tied = inverter; "
             "this MPN is already on the board as U8). ISO7710 (default HIGH) stays; audit.rs default-low rule untouched. "
             "The inverter shares the rail's existing 5 V bypass capacitor (civcc1).",
        remove=NOTICE, swap={}, add=[("SN74LVC1G10DBVR", 3)]),
    "P2_HS_monitors_via_ISO6721FB_one_reinforced_crossing": dict(
        desc="P1's notice deletion, plus: HS-A/HS-B monitors cross to the LS domain through a functional-class ISO6721FB (default low), "
             "a NAND3 on the LS 5 V rail combines the three 'good' lines, U32 (ISO7710, default high) is the only reinforced crossing of the "
             "monitor group; the SELV-side OR3 (U25) is deleted.",
        remove=NOTICE + [OR3, ref_of_path["bias_c_or"]], swap={ISO[1]: "ISO6721FBDR", ISO[2]: "ISO6721FBDR"},
        add=[("SN74LVC1G10DBVR", 1), ("CC0603KRX7R9BB104", 1)]),
    "P3_permit_DIS_stage_FET_free": dict(
        desc="Per leg: PERMIT-FET + 330 ohm pull-up + OR2 -> one NAND2 (SN74LVC1G00, SOT-23-5, same pins/footprint as the SN74LVC1G32 it replaces): "
             "DIS = NAND(permit_gate, BIAS_GOOD). U40 (Schmitt buffer after the 10 us filter) becomes the inverting SN74LVC1G14 (same footprint), "
             "so the internal net BIAS_BAD becomes BIAS_GOOD (it is not on J4). Keeps the 100 ohm, the 100 k pull-down and the 10 k DIS pull-up.",
        remove=[ref_of_path[f"{l}.{x}"] for l in ("leg_a", "leg_b") for x in ("permit_fet", "r_dis_pu")],
        swap={ref_of_path["leg_a.dis_or"]: "SN74LVC1G00DBVR", ref_of_path["leg_b.dis_or"]: "SN74LVC1G00DBVR",
              ref_of_path["u_bias_flt"]: "SN74LVC1G14DBVR"}, add=[]),
}
# model strings in evidence/jlc-raw for new MPNs
NEW_MODEL = {"SN74LVC1G00DBVR": "SN74LVC1G00DBVR", "SN74LVC1G14DBVR": "SN74LVC1G14DBVR", "ISO7710FDWR": "ISO7710FDWR", "ISO6721FBDR": "ISO6721FBDR", "SN74LVC1G10DBVR": "SN74LVC1G10DBVR"}
for m in NEW_MODEL.values():
    assert m in jlc or True

# A swapped-in variant of an existing part is assumed to carry the existing part's scorecard (DK-based) price,
# so the scorecard column shows the real change in function, not a price-source change.
SC_SAME_AS = {"ISO7710FDWR": "ISO7710DWR"}

def newprice(mpn, qpb):
    """(real JLC price, scorecard price) for a part that is added or swapped in."""
    if mpn in stock and mpn in cls_of:                      # already on the board: same price in both columns
        return real_price(mpn, qpb), sc_price(mpn) or 0.0
    real = jlc_price(NEW_MODEL.get(mpn, mpn), qpb)[0]
    sc = sc_price(SC_SAME_AS[mpn]) if mpn in SC_SAME_AS else real
    return real, sc

def evaluate(name, p):
    mp = dict(mpn_of)
    placements = len(mp)
    removed = set(p["remove"])
    for r in removed:
        mp.pop(r)
    for r, new in p["swap"].items():
        mp[r] = new
    added = []
    for mpn, n in p["add"]:
        for i in range(n):
            added.append(f"NEW{len(added)+1}")
            mp[added[-1]] = mpn
    lines_before = Counter(mpn_of.values())
    lines_after = Counter(mp.values())
    def klass(m):
        if m in cls_of:
            return cls_of[m]
        return jlc[m]["componentLibraryType"] == "base" and "Basic" or "Extended"
    ext_b = sum(1 for m in lines_before if cls_of[m] == "Extended")
    ext_a = sum(1 for m in lines_after if klass(m) == "Extended")
    sc_b = sum(sc_price(m) or 0 for m in mpn_of.values())
    def price(mpn, which):
        if mpn in cls_of and mpn in stock:
            return (sc_price(mpn) or 0) if which == "sc" else real_price(mpn, lines_before[mpn])
        qpb = lines_after[mpn]
        return jlc_price(NEW_MODEL.get(mpn, mpn), qpb)[0]
    def total(mpmap, cnt, which):
        return sum(price(m, which) for m in mpmap.values())
    # price of each retained part must come from the 'before' tier: compute per-ref delta explicitly
    d_sc = d_real = 0.0
    for r in removed:
        m = mpn_of[r]
        d_sc -= sc_price(m) or 0
        d_real -= real_price(m, lines_before[m])
    for r, new in p["swap"].items():
        old = mpn_of[r]
        d_sc -= sc_price(old) or 0
        d_real -= real_price(old, lines_before[old])
        pn, ps_ = newprice(new, lines_after[new])
        d_sc += ps_
        d_real += pn
    for mpn, n in p["add"]:
        pn, ps_ = newprice(mpn, lines_after[mpn])
        d_sc += ps_ * n
        d_real += pn * n
    gone = sorted(m for m in lines_before if m not in lines_after)
    new = sorted(m for m in lines_after if m not in lines_before)
    return dict(
        name=name, description=p["desc"],
        placements_before=placements, placements_after=len(mp), placements_delta=len(mp) - placements,
        bom_lines_before=len(lines_before), bom_lines_after=len(lines_after), bom_lines_delta=len(lines_after) - len(lines_before),
        extended_lines_before=ext_b, extended_lines_after=ext_a, extended_lines_delta=ext_a - ext_b,
        lines_removed=gone, lines_added=new,
        parts_usd_at_500_delta_scorecard=round(d_sc, 3), parts_usd_at_500_delta_real_jlc=round(d_real, 3),
        refs_removed=sorted(removed, key=lambda s: (s[0], int(s[1:]))),
        refs_swapped={r: f"{mpn_of[r]} -> {n}" for r, n in p["swap"].items()},
        groups_touched=sorted({group_of.get(r, "?") for r in list(removed) + list(p["swap"])}),
    )

if __name__ == "__main__":
    base_sc = sum(sc_price(m) or 0 for m in mpn_of.values())
    print(f"baseline: {len(mpn_of)} placements, {len(set(mpn_of.values()))} BOM lines, scorecard parts ${base_sc:.2f} at 500 (expect 231.94)")
    assert abs(base_sc - 231.94) < 0.02, base_sc
    res = [evaluate(n, p) for n, p in PROPOSALS.items()]
    for r in res:
        print()
        print(r["name"], "-", r["description"])
        for k in ("placements_delta", "bom_lines_delta", "extended_lines_delta", "lines_removed", "lines_added",
                  "parts_usd_at_500_delta_scorecard", "parts_usd_at_500_delta_real_jlc", "groups_touched"):
            print(f"   {k}: {r[k]}")
        print("   refs removed:", ", ".join(r["refs_removed"]))
        print("   swapped:", r["refs_swapped"])
    os.makedirs(f"{OUT}/results", exist_ok=True)
    json.dump(dict(baseline=dict(placements=len(mpn_of), bom_lines=len(set(mpn_of.values())), parts_usd_at_500_scorecard=round(base_sc, 2)),
                   proposals=res), open(f"{OUT}/results/parts_cost.json", "w"), indent=1)
