"""Bench-kit bill of materials with ESTIMATED prices (USD, list, not quoted; verify before ordering).

Two variants:
  reference  the first kit: C1-exact Si3N4 disc lot, shop-machined jig, full metrology ($1,285)
  lean       the cheapest kit that still answers the survey question (DECISIONS.md L1-L7):
             a polished alumina disc cored from one substrate (weighed; the fit's model correction,
             already the self-test case), a distributor thin-film Pt100, JLCCNC parts, a replacement
             cooktop glass panel, and tools most people own moved to "own_or_borrow"
Run: python bom.py -> bom.json, prints both tables and the totals.
"""
import json
from pathlib import Path

# (group, item, part / source, qty, est unit USD, note)
REFERENCE = [
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


# (group, item, part / source, qty, est unit USD, note, kind)  kind: buy | own_or_borrow | optional
LEAN = [
    ("logger", "ESP32-S3 devkit", "Espressif ESP32-S3-DevKitC-1 (Digi-Key/Mouser) or any S3 devkit clone", 1, 15, "logger_fw.ino targets it", "buy"),
    ("logger", "Pt100 converter breakout", "Adafruit 3328 MAX31865, 430 ohm 0.1 % Rref (adafruit.com/product/3328)", 1, 15, "keep the genuine part: Rref sets the reading", "buy"),
    ("logger", "Thermocouple converter", "MAX31856 module (generic) or Adafruit 3263", 1, 8, "reference slope only; offset is fitted", "buy"),
    ("logger", "Pan reference thermocouple", "type-K bead, 30-36 AWG, glass or PFA insulated, 2-pack", 1, 10, "now placed inside the bore (RIG 2)", "buy"),
    ("probe", "Pt100 thin-film element", "IST P0K1.202 family, class F0.15 (as the reference kit)", 2, 25, "1 + 1 spare; the cheaper M222 class failed the self-test (DECISIONS L3)", "buy"),
    ("probe", "Disc substrate", "99.6 % alumina, thin-film grade, polished, 25.4 x 25.4 x 0.254 mm, 1-2 pcs (Valley Design / Stellar / MTI class)", 1, 20, "option B; Ra <= 0.1 um face", "buy"),
    ("probe", "Disc coring bit", "diamond core bit with 8.0-8.3 mm INSIDE diameter (often sold as 10 mm), water-cooled", 1, 8, "core 3-4 discs, keep the best", "buy"),
    ("probe", "Bond adhesive", "high-temperature conductive epoxy (e.g. Omega OB-200 class); verify >= 230 C rating", 1, 40, "survey runs 150 C, subset 230 C", "buy"),
    ("probe", "Lead wire", "PTFE-insulated 30 AWG, small spool", 1, 10, "4-wire", "buy"),
    ("jig", "Post", "PEEK, turned per jig-post.step (JLCCNC, quote online)", 1, 25, "estimate incl. setup; PEEK because it touches the disc", "buy"),
    ("jig", "Holder", "6061, per jig-holder.step (JLCCNC)", 1, 25, "estimate; under the plate, stays well below 100 C", "buy"),
    ("jig", "Spring plug", "M10 x 1 fine-thread stainless set screw (flat point)", 1, 3, "replaces the turned plug", "buy"),
    ("jig", "Compression springs", "stainless assortment incl. OD ~5.5, rate 0.2-0.4 N/mm", 1, 8, "", "buy"),
    ("jig", "Balls", "Ø3 mm 440C or chrome-steel balls, 50-pack", 1, 4, "", "buy"),
    ("jig", "Plate", "replacement glass-ceramic panel for a portable induction cooker, ~280 x 280 x 4 mm", 1, 30, "verify 4 mm; fallback porcelain tile or calcium-silicate board checked flat (plate_check.py)", "buy"),
    ("jig", "Ø18 bore bit", "18 mm diamond core bit, water-cooled", 1, 8, "", "buy"),
    ("jig", "Shim stock", "stainless 0.05 / 0.1 mm", 1, 8, "sets 0.60 mm proud", "buy"),
    ("cal", "Thermal paste", "silicone compound rated >= 200 C", 1, 6, "paste calibration on a thick-based pan", "buy"),
    ("measure", "Milligram scale", "50 g x 0.001 g jewellery scale", 1, 20, "disc mass 49 mg -> C_cap +-2 %", "buy"),
    ("cal", "Calibration block", "any thick flat copper/aluminium offcut or a heavy flat-based pan", 1, 0, "", "own_or_borrow"),
    ("measure", "Force check", "kitchen scale, 1 g resolution", 1, 0, "window 143-163 g", "own_or_borrow"),
    ("measure", "Proud height", "digital caliper, step mode (+-0.02 mm)", 1, 0, "", "own_or_borrow"),
    ("measure", "Pan flatness", "steel rule + feeler gauges", 1, 0, "", "own_or_borrow"),
    ("measure", "Drill press or drill stand", "for coring the disc and the plate bore under water", 1, 0, "or a makerspace", "own_or_borrow"),
    ("safety", "Oven mitts", "rated for 250 C pans", 1, 0, "", "own_or_borrow"),
    ("measure", "Dial indicator + base", "0.01 mm", 1, 25, "only if the caliper step reading scatters > 0.02 mm", "optional"),
    ("measure", "Surface roughness comparator", "Ra comparator plate", 1, 40, "pan Ra class is metadata; h_c is measured directly", "optional"),
]


def table(rows):
    print("| Group | Item | Part / source | Qty | Est. USD | Kind |\n|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['group']} | {r['item']} | {r['part']} | {r['qty']} | {r['est_usd']} | {r['kind']} |")


def main():
    ref = [dict(group=g, item=i, part=p, qty=q, est_unit_usd=u, est_usd=q * u, note=n, kind="buy")
           for g, i, p, q, u, n in REFERENCE]
    lean = [dict(group=g, item=i, part=p, qty=q, est_unit_usd=u, est_usd=q * u, note=n, kind=k)
            for g, i, p, q, u, n, k in LEAN]

    def groups(rows, kinds):
        by = {}
        for r in rows:
            if r["kind"] in kinds:
                by[r["group"]] = by.get(r["group"], 0) + r["est_usd"]
        return by

    out = {"scope": __doc__.strip(),
           "reference": {"rows": ref, "by_group_usd": groups(ref, {"buy"}), "total_est_usd": sum(r["est_usd"] for r in ref)},
           "lean": {"rows": lean, "by_group_usd": groups(lean, {"buy"}),
                    "must_buy_est_usd": sum(r["est_usd"] for r in lean if r["kind"] == "buy"),
                    "optional_est_usd": sum(r["est_usd"] for r in lean if r["kind"] == "optional"),
                    "assumes_owned": [r["item"] for r in lean if r["kind"] == "own_or_borrow"]},
           "excluded": "oven/hot plate, the cookware itself, a kitchen to work in"}
    # keep the old top-level keys pointing at the reference kit for anything that reads them
    out["rows"], out["by_group_usd"], out["total_est_usd"] = ref, out["reference"]["by_group_usd"], out["reference"]["total_est_usd"]
    Path(__file__).with_name("bom.json").write_text(json.dumps(out, indent=1) + "\n")
    print("## lean")
    table(lean)
    L = out["lean"]
    print(f"\nlean by group (buy): {L['by_group_usd']}\nLEAN MUST-BUY (estimate): ${L['must_buy_est_usd']}"
          f"  + optional ${L['optional_est_usd']}\nREFERENCE (estimate): ${out['reference']['total_est_usd']}")


if __name__ == "__main__":
    main()
