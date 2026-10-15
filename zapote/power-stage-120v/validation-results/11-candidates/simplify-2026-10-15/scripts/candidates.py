#!/usr/bin/env python3
"""Placements, BOM lines and parts cost at 500 boards for each consolidation candidate, against s43.

    python3 -I scripts/candidates.py [SNAP_PS_DIR]          -> results/candidates.json, results/candidates.md

Two price bases, both per board at 500 boards:
  jlc  : JLC 2026-10-15 snapshot price (SNAPSHOT-2026-10-15.csv jlc_unit_usd_500) for MPNs already on the BOM, and the
         JLC ladder (dl/jlc-raw detail records, tier at qty_per_board x 500) for new MPNs. This is what an order pays.
  card : the scorecard's basis (STOCK-2026-10-13*.csv merged as scorecard.cost()), with new MPNs at their JLC ladder
         price, i.e. what the next stock addendum would add. Many existing rows are class-default ESTIMATES (README).
Line counting follows scorecard.cost(): one line per MPN. A line disappears only when no designator is left on it.
"""
import sys as _s; _s.dont_write_bytecode = True  # never write .pyc next to the read-only snapshot sources
import csv, json, sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jlc  # noqa: E402
import inventory as inv  # noqa: E402

PS = Path(sys.argv[1]) if len(sys.argv) > 1 else inv.PS
inv.PS = PS

NEW = {  # new MPN -> (LCSC code, JLC class)
    "TPS3701DDCR": "C132788", "TLV3202AIDR": "C129325", "RT0603BRD0713KL": "C861121", "RT0603BRD072K74L": "C861304",
    "RT0603BRD07102KL": "C861068", "RT0603BRD0710K2L": "C515735", "RT0603BRD07453KL": "C861412",
    "RT0603BRD0744K2L": "C861410", "CL32B226KAJNNNE": "C309062", "2EDR9259XXUMA1": "C17240461",
}

R = lambda *x: list(x)
CANDIDATES = {
    "A": {"title": "G08: bus OVP onto U14's spare OV channel (INB), U14 TPS3700 -> TPS3701, NAND3 -> Schmitt NAND2",
          "remove": R("U7", "C34", "R36", "R37", "C33", "U15", "C49", "R30"),
          "replace": {"U8": "SN74LVC1G132DBVR", "U14": "TPS3701DDCR", "R48": "RT0603BRD07102KL"},
          "add": [("R30A", "RT0603BRD0713KL"), ("R30B", "RT0603BRD072K74L")]},
    "A0": {"title": "G08 fallback if A's shared die is refused: U14 TPS3700 -> TPS3701 (+ R48 105k -> 102k) only, BOM-only",
           "remove": [], "replace": {"U14": "TPS3701DDCR", "R48": "RT0603BRD07102KL"}, "add": []},
    "B": {"title": "G07: each rail monitor's TL431A + LM339B + rref + halfref -> two TPS3701 (one per window), own dividers",
          "remove": R("U17", "U19", "U21", "R59", "R63", "R65", "R79", "R80", "R97", "R98", "R112", "R113"),
          "replace": {"U29": "TPS3701DDCR", "U30": "TPS3701DDCR", "U31": "TPS3701DDCR",
                      # neg UV: 7.68k / 2.21k ; neg OV: 10.2k / 2.21k ; span UV: 453k / 11.7k ; span OV: 44.2k / 1k
                      "R81": "RT0603BRD077K68L", "R99": "RT0603BRD077K68L", "R114": "RT0603BRD077K68L",
                      "R82": "RT0603BRD072K21L", "R100": "RT0603BRD072K21L", "R115": "RT0603BRD072K21L",
                      "R83": "RT0603BRD0710K2L", "R101": "RT0603BRD0710K2L", "R116": "RT0603BRD0710K2L",
                      "R84": "RT0603BRD072K21L", "R102": "RT0603BRD072K21L", "R117": "RT0603BRD072K21L",
                      "R85": "RT0603BRD07453KL", "R103": "RT0603BRD07453KL", "R118": "RT0603BRD07453KL",
                      "R86": "TNPW060311K7BEEA", "R104": "TNPW060311K7BEEA", "R119": "TNPW060311K7BEEA",
                      "R87": "RT0603BRD0744K2L", "R105": "RT0603BRD0744K2L", "R120": "RT0603BRD0744K2L",
                      "R88": "RT0603BRD071KL", "R106": "RT0603BRD071KL", "R121": "RT0603BRD071KL"},
          "add": [("U_WIN2_LS", "TPS3701DDCR"), ("U_WIN2_HA", "TPS3701DDCR"), ("U_WIN2_HB", "TPS3701DDCR"),
                  ("C_WIN2_LS", "CC0603KRX7R9BB104"), ("C_WIN2_HA", "CC0603KRX7R9BB104"), ("C_WIN2_HB", "CC0603KRX7R9BB104")]},
    "C": {"title": "G09 CT: U10 (CT_OC_POS) + U12 (CT_ZC) -> one TLV3202 dual; U11 (CT_OC_NEG) stays single",
          "remove": R("U12", "C46"),
          "replace": {"U10": "TLV3202AIDR"}, "add": []},
    "C-hot": {"title": "(alternative, not recommended) G08: U6 (OCP) + U7 (OVP) -> one TLV3202",
              "remove": R("U7", "C34"), "replace": {"U6": "TLV3202AIDR"}, "add": []},
    "D": {"title": "G05: U1/U2 2EDR8259X (8 V UVLO) -> 2EDR9259X (15 V UVLO), monitor kept",
          "remove": [], "replace": {"U1": "2EDR9259XXUMA1", "U2": "2EDR9259XXUMA1"}, "add": []},
    "E": {"title": "G05 reservoirs: 2 x 10 uF 1210 -> 1 x 22 uF 1210 per VSS (src-n sits at ~2 V)",
          "remove": R("C91", "C93", "C95", "C97"),
          "replace": {"C90": "CL32B226KAJNNNE", "C92": "CL32B226KAJNNNE", "C94": "CL32B226KAJNNNE", "C96": "CL32B226KAJNNNE"},
          "add": []},
    "H": {"title": "G06: delete C24 (V15_LS 10 uF in parallel with the TPS7A4700's C99/C100)",
          "remove": R("C24"), "replace": {}, "add": []},
}
COMBOS = {"A+B+C": ["A", "B", "C"], "A+B+C+E+H": ["A", "B", "C", "E", "H"]}


def main():
    comps, _ = inv.load_netlist()
    mpn0 = {r: inv.load_bom()[1][r] for r in comps}
    st = inv.load_prices()
    snap = inv.load_snapshot()

    def jlc_unit(m, qpb):
        if m in snap or m in st:   # existing line: JLC where JLC lists it, else the card price (inventory.py)
            return inv.jlc_unit_existing(m, snap, st)
        det = jlc.detail(NEW[m], online=False)
        return float(jlc.price_at(det, qpb * 500))

    def card_unit(m, qpb):
        return float(st[m]["unit_usd_at_500boards"]) if m in st else jlc_unit(m, qpb)

    def apply(keys):
        bom = dict(mpn0)
        for k in keys:
            c = CANDIDATES[k]
            for r in c["remove"]:
                bom.pop(r)
            for r, m in c["replace"].items():
                bom[r] = m
            for r, m in c["add"]:
                bom[r] = m
        return bom

    def cost(bom, basis):
        q = Counter(bom.values())
        f = jlc_unit if basis == "jlc" else card_unit
        return sum(f(m, n) * n for m, n in q.items())

    base = {"placements": len(mpn0), "lines": len(set(mpn0.values())), "jlc": cost(mpn0, "jlc"), "card": cost(mpn0, "card")}
    assert abs(base["card"] - 202.32) < 0.01 and base["lines"] == 93, base
    out = {"baseline_s43": {k: round(v, 2) if isinstance(v, float) else v for k, v in base.items()}, "candidates": {}}
    rows = []
    for k in list(CANDIDATES) + list(COMBOS):
        keys = COMBOS.get(k, [k])
        bom = apply(keys)
        before, after = set(mpn0.values()), set(bom.values())
        d = {"title": CANDIDATES[k]["title"] if k in CANDIDATES else " + ".join(keys),
             "placements_delta": len(bom) - base["placements"],
             "lines_delta": len(after) - base["lines"],
             "lines_removed": sorted(before - after), "lines_added": sorted(after - before),
             "usd500_delta_jlc": round(cost(bom, "jlc") - base["jlc"], 3),
             "usd500_delta_card": round(cost(bom, "card") - base["card"], 3),
             "new_part_stock": {m: snap.get(m, {}).get("jlc_stock") or (jlc.detail(NEW[m], online=False) or {}).get("stockCount")
                                for m in sorted(after - before)}}
        cls = {m: (snap.get(m, {}).get("jlc_library") or (jlc.detail(NEW[m], online=False) or {}).get("componentLibraryType"))
               for m in sorted(after - before)}
        d["new_line_classes"] = cls
        out["candidates"][k] = d
        rows.append(f"| {k} | {d['title']} | {d['placements_delta']:+d} | {d['lines_delta']:+d} | "
                    f"{d['usd500_delta_jlc']:+.2f} | {d['usd500_delta_card']:+.2f} |")
    json.dump(out, open(HERE.parent / "results/candidates.json", "w"), indent=1)
    md = ["| Id | Change | Placements | BOM lines | $ at 500, JLC | $ at 500, card |", "|---|---|---:|---:|---:|---:|"] + rows
    md.append(f"\nBaseline s43: {base['placements']} placements, {base['lines']} lines, ${base['jlc']:.2f} (JLC basis) / "
              f"${base['card']:.2f} (card basis).")
    (HERE.parent / "results/candidates.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    for k, d in out["candidates"].items():
        print(k, "removed", d["lines_removed"], "added", d["lines_added"], d["new_part_stock"])


if __name__ == "__main__":
    main()
