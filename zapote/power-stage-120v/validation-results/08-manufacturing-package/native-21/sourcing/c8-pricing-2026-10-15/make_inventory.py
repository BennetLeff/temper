#!/usr/bin/env python3
"""Per-line inventory and offline re-score of s44 / s45 (C8). Read-only against the PS tree.

    python3 -I make_inventory.py            # writes inventory-s45.{csv,md,json}, rescore-s44.json, rescore-s45.json, delta-s44-s45.json
"""
import sys
sys.dont_write_bytecode = True
import csv
import glob
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PS = Path("/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v")
sys.path.insert(0, str(HERE / "work/native-21/layout/gates"))
import bom_pricing as bp  # noqa: E402

VR = PS / "validation-results"
SRC = VR / "08-manufacturing-package/native-21/sourcing"
SNAP = SRC / "study-2026-10-15/snapshot"
BOMS = {"s44": SNAP / "s44/bom-jlcpcb.s44.csv", "s45": VR / "08-manufacturing-package/native-21/fab/bom-jlcpcb.csv"}
CARDS = {"s44": VR / "10-benchmark/scorecard-native21s44.json", "s45": VR / "10-benchmark/scorecard-native21s45.json"}


def legacy_stock():
    """scorecard.py's default --stock: sorted glob, a later file overrides an earlier row."""
    st = {}
    for p in sorted(glob.glob(str(SRC / "STOCK-2026-10-13*.csv"))):
        for r in csv.DictReader(open(p)):
            if r["board"].startswith("power"):
                st[r["mpn"].strip()] = r
    return st


def legacy_line(st, mpn, q):
    s = st.get(mpn)
    if not s:
        return None
    return {"unit5": float(s["unit_usd_at_5boards"]), "unit500": float(s["unit_usd_at_500boards"]),
            "source": s["price_source"].strip(), "date": s["check_date"], "cls": bp.survey_class(s)}


def main():
    R = bp.load_reads(SRC)
    st = legacy_stock()
    out = {}
    for tag in ("s44", "s45"):
        P = bp.price_bom(BOMS[tag], R)
        leg = {}
        for l in P["lines"]:
            leg[l["mpn"]] = legacy_line(st, l["mpn"], l["qty"])
        l5 = round(sum(leg[l["mpn"]]["unit5"] * l["qty"] for l in P["lines"]), 2)
        l500 = round(sum(leg[l["mpn"]]["unit500"] * l["qty"] for l in P["lines"]), 2)
        card = json.load(open(CARDS[tag]))["cost"]
        rs = {"tag": tag, "bom": str(BOMS[tag].relative_to(PS)), "bom_lines": len(P["lines"]),
              "new_basis": bp.card_fields(P),
              "new_totals_unrounded": {k: v for k, v in P["totals"].items() if not k.startswith("tiers")},
              "legacy_recomputed": {"parts_usd_at_5": l5, "parts_usd_at_500": l500},
              "legacy_committed_card": {"parts_usd_at_5": card["parts_usd_at_5"], "parts_usd_at_500": card["parts_usd_at_500"]},
              "legacy_lines_estimated": sum(leg[l["mpn"]]["cls"] in ("estimate", "derived", "other") for l in P["lines"])}
        Path(HERE / f"rescore-{tag}.json").write_text(json.dumps(rs, indent=1, sort_keys=True) + "\n")
        out[tag] = (P, leg, rs)

    # s44 -> s45 delta
    A = {l["mpn"]: l for l in out["s44"][0]["lines"]}
    B = {l["mpn"]: l for l in out["s45"][0]["lines"]}
    ref = json.load(open(VR / "11-candidates/c45-s16-monitor/results/cost-s44-s45.json"))
    d = {"rows": [], "cost45_card_basis_delta_500": ref["card_delta_usd_per_board"], "cost45_jlc_basis_delta_500": ref["jlc_delta_usd_per_board"]}
    for n in (5, 500):
        tot = 0.0
        for m in sorted(set(A) | set(B)):
            x = A[m][f"n{n}"]["line_usd"] if m in A else 0.0
            y = B[m][f"n{n}"]["line_usd"] if m in B else 0.0
            if abs(x - y) > 1e-12:
                tot += y - x
                if n == 500:
                    d["rows"].append({"mpn": m, "s44": round(x, 4), "s45": round(y, 4), "delta": round(y - x, 4),
                                      "tier": (A.get(m) or B.get(m))["n500"]["tier"]})
        d[f"delta_{n}"] = round(tot, 4)
    d["legacy_card_delta_500"] = round(out["s45"][2]["legacy_committed_card"]["parts_usd_at_500"] - out["s44"][2]["legacy_committed_card"]["parts_usd_at_500"], 2)
    Path(HERE / "delta-s44-s45.json").write_text(json.dumps(d, indent=1, sort_keys=True) + "\n")

    # inventory (s45)
    P, leg, rs = out["s45"]
    cols = ["line", "designators", "mpn", "lcsc", "qty_per_board", "card_source_class", "card_source", "card_date",
            "card_unit_5", "card_unit_500", "card_line_5", "card_line_500"]
    for n in (5, 500):
        cols += [f"lot_parts_{n}", f"tier_{n}", f"unit_{n}", f"line_usd_{n}", f"source_{n}", f"date_{n}", f"flags_{n}"]
    cols += ["line_delta_500_new_minus_card", "artefacts", "other_reads_500"]
    rows = []
    for l in P["lines"]:
        g = leg[l["mpn"]]
        r = {"line": l["line"], "designators": l["designators"], "mpn": l["mpn"], "lcsc": l["lcsc"], "qty_per_board": l["qty"],
             "card_source_class": "read" if g["cls"] in ("dist", "jlc") else g["cls"], "card_source": g["source"][:110], "card_date": g["date"],
             "card_unit_5": g["unit5"], "card_unit_500": g["unit500"], "card_line_5": round(g["unit5"] * l["qty"], 4),
             "card_line_500": round(g["unit500"] * l["qty"], 4)}
        for n in (5, 500):
            x = l[f"n{n}"]
            r.update({f"lot_parts_{n}": x["need"], f"tier_{n}": x["tier"], f"unit_{n}": x["unit"], f"line_usd_{n}": x["line_usd"],
                      f"source_{n}": x["source"], f"date_{n}": x["date"], f"flags_{n}": "; ".join(x["flags"])})
        r["line_delta_500_new_minus_card"] = round(l["n500"]["line_usd"] - r["card_line_500"], 4)
        arts = sorted({f"{c['source']}: {a}" for n in (5, 500) for c in l[f"n{n}"]["candidates"] for a in c["artefact"]})
        nonp = sorted({c["source"] for n in (5, 500) for c in l[f"n{n}"]["candidates"] if c["non_purchasable"]})
        r["artefacts"] = "; ".join(arts + [f"{s}: listed_no_stock, not a purchasable price" for s in nonp])
        r["other_reads_500"] = "; ".join(f"{c['source'].split(':')[0][:34]} {c['unit']}" + (f" stock {c['stock']}" if c["stock"] is not None else "")
                                         for c in l["n500"]["candidates"] if c["unit"] is not None and c["survey_class"] not in ("estimate", "derived", "other"))
        rows.append(r)
    with open(HERE / "inventory-s45.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    Path(HERE / "inventory-s45.json").write_text(json.dumps({"basis": bp.BASIS, "lines": P["lines"]}, indent=1, sort_keys=True) + "\n")

    L = ["| # | MPN | qty | card basis | card $/unit @500 | new $/unit @500 | tier @500 | new source @500 (date) | artefact / flag |",
         "|---:|---|---:|---|---:|---:|---|---|---|"]
    for r in rows:
        fl = "; ".join(x for x in (r["artefacts"].split(";")[0][:60] if r["artefacts"] else "", r["flags_500"][:40]) if x)
        L.append(f"| {r['line']} | {r['mpn']} | {r['qty_per_board']} | {r['card_source_class']} | {r['card_unit_500']} | {r['unit_500']} | "
                 f"{r['tier_500']} | {r['source_500'][:46]} ({str(r['date_500'])[:10]}) | {fl} |")
    Path(HERE / "inventory-s45.md").write_text("\n".join(L) + "\n")

    # summary numbers for the README
    cls = {}
    for r in rows:
        cls[r["card_source_class"]] = cls.get(r["card_source_class"], 0) + 1
    print("card source class counts (s45):", cls)
    for tag in ("s44", "s45"):
        rs = out[tag][2]
        print(tag, "new", rs["new_basis"]["parts_usd_at_5_v2"], rs["new_basis"]["parts_usd_at_500_v2"], "legacy recomputed",
              rs["legacy_recomputed"], "committed", rs["legacy_committed_card"], "legacy estimated lines", rs["legacy_lines_estimated"])
    print("delta", {k: v for k, v in d.items() if k != "rows"})


main()
