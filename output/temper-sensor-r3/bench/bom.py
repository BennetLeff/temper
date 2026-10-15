"""Bench-kit bill of materials with ESTIMATED prices (USD, list, not quoted; verify before ordering).

Run: python bom.py -> bom.json, prints a markdown table and the total.
"""
import json
from pathlib import Path

# (group, item, part / source, qty, est unit USD, note)
BOM = [
    ("logger", "ESP32-S3 devkit", "Espressif ESP32-S3-DevKitC-1-N8R8 (Digi-Key/Mouser)", 1, 15, ""),
    ("logger", "Pt100 converter breakout", "Adafruit 3328 (MAX31865, PT100, Rref 430 ohm)", 1, 15, "set the 4-wire jumpers"),
    ("logger", "Thermocouple converter breakout", "Adafruit 3263 (MAX31856)", 1, 18, ""),
    ("logger", "Pan reference thermocouple", "Omega 5TC-TT-K-36-36 (type K, 36 AWG, PFA), 5-pack", 1, 45, "or any fine type-K bead"),
    ("probe", "Pt100 thin-film element", "IST P0K1.202 family, class F0.15, Pt/Ni wire (e.g. P0K1.202.6W.A.007; EPS Global/Farnell)", 3, 25, "1 + 2 spares"),
    ("probe", "Contact disc, option A (C1-exact)", "Si3N4 0.32 mm substrate (e.g. Innovacera SN-90) laser-cut Ø8, lapped Ra <= 0.1 um; lot of 20", 1, 250, "quote; option B: 99.6 % polished alumina 0.254 mm Ø8, similar cost"),
    ("probe", "Bond adhesive", "EPO-TEK 930-4 (boron-nitride filled), small kit", 1, 90, "same bond as C1"),
    ("probe", "Lead wire", "PTFE-insulated 30 AWG silver-plated copper, 4 colours, + glass-fibre sleeving", 1, 25, "4-wire to the element pads"),
    ("jig", "Post stock", "PEEK rod Ø16 x 300 mm (McMaster)", 1, 40, "Vespel SP-1 if available"),
    ("jig", "Holder and plug stock", "6061 rod Ø45 x 150 mm", 1, 30, ""),
    ("jig", "Machining (post, holder, M10x1 plug)", "local shop or own lathe; jig-post.step, jig-holder.step", 1, 250, "estimate"),
    ("jig", "Compression springs", "stainless, OD ~5.5 mm, free length ~16 mm, rate 0.2-0.4 N/mm; assortment", 1, 25, "jig.json sets preload"),
    ("jig", "Balls", "Ø3 mm silicon nitride or 440C balls, 10-pack", 1, 12, ""),
    ("jig", "Plate", "4 mm glass-ceramic (cooktop replacement offcut, ~300 x 300)", 1, 80, "fallback: 6 mm calcium-silicate board"),
    ("jig", "Ø18 bore", "diamond core bit Ø18 (water-cooled) or waterjet service", 1, 40, ""),
    ("jig", "Shim stock", "stainless 0.05 / 0.1 mm assortment", 1, 20, "sets 0.60 mm proud"),
    ("cal", "Copper calibration block", "C110 50 x 50 x 20 mm", 1, 30, "paste calibration of tau_int"),
    ("cal", "Thermal paste", "Wakefield 120 silicone compound (200 C)", 1, 15, ""),
    ("measure", "Milligram scale", "50 g x 0.001 g jewellery scale", 1, 30, "disc mass (C_cap)"),
    ("measure", "Force scale", "200 g x 0.01 g scale", 1, 25, "tip force at flush"),
    ("measure", "Dial indicator + magnetic base", "0.01 mm indicator", 1, 60, "proud height, pan flatness"),
    ("measure", "Straightedge + feeler gauges", "300 mm straightedge, 0.02-1 mm feelers", 1, 35, "pan base concave/convex"),
    ("measure", "Surface roughness comparator", "machined-surface comparator plate (Ra 0.05-12.5 um)", 1, 40, "Ra class per pan"),
    ("safety", "Heat-resistant gloves", "to 250 C", 1, 20, ""),
]


def main():
    rows = [dict(group=g, item=i, part=p, qty=q, est_unit_usd=u, est_usd=q * u, note=n) for g, i, p, q, u, n in BOM]
    total = sum(r["est_usd"] for r in rows)
    by_group = {}
    for r in rows:
        by_group[r["group"]] = by_group.get(r["group"], 0) + r["est_usd"]
    out = {"scope": __doc__.strip(), "rows": rows, "by_group_usd": by_group, "total_est_usd": total,
           "excluded": "oven/hot plate, the cookware itself, a kitchen to work in"}
    Path(__file__).with_name("bom.json").write_text(json.dumps(out, indent=1) + "\n")
    print("| Group | Item | Part / source | Qty | Est. USD |\n|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['group']} | {r['item']} | {r['part']} | {r['qty']} | {r['est_usd']} |")
    print(f"\nby group: {by_group}\nTOTAL (estimate): ${total}")


if __name__ == "__main__":
    main()
