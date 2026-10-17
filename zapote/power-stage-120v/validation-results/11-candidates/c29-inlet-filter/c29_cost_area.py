#!/usr/bin/env python3 -I
"""C29 cost, placements and board-area estimate: separate D-22 inlet module vs the same function on the power board.

Rerun: python3 -I c29_cost_area.py   (stdlib; reads board_area.json from board_area.py; writes c29_cost_area.json)
Every price is USD per board at 500 boards.  'est' = engineering allowance with no price source (flagged in the JSON).

Sources
  D-22 parts at 500 : 08-manufacturing-package/native-21/sourcing/STOCK-2026-10-13.csv:204-210 (DK tiers, fetched 2026-10-13)
  carrier allowance : 01-switching-parasitics/round17/delegation/out-D22/budget.py:66 ($15 carrier/terminals/cover)
  harness allowance : 11-candidates/r3-split/scripts/cost_model.py:59 ($3.00, 300 mm 12 AWG + PE, est)
  SC-20-201         : 11-candidates/g01-mains/PROPOSALS.md:24 (DigiKey FR EUR 5.37 at 510, x1.16 USD/EUR assumed)
  KEMET SCF39XV-200-Z2R1A012JH 3.6 mH 20 A nanocrystalline: element14.cn, CNY 176.39 at 108+ excl. GST, 37 wk lead,
                      fetched 2026-10-13 (https://www.element14.cn/en-CN/kemet/scf39xv-200-z2r1a012jh/common-mode-3-6mh-20a/dp/4199926);
                      CNY->USD at 7.10 (assumed)
  PCB area rate     : r3-split cost_model.json fab mid at 500: (6.03 - 4.93) USD / (55100 - 44935) mm2
  labour            : $45/h (r3-split cost_model.py LAB_MIN basis); minutes are est.
"""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
CNY_USD = 7.10
EUR_USD = 1.16
PCB_USD_PER_MM2 = (6.03 - 4.93) / (55100 - 44935)
LAB_USD_PER_MIN = 45 / 60

d22_parts = {  # STOCK-2026-10-13.csv:204-210, line cost at 500
    "TDK B82726S2203A020 CM choke 1.6 mH": 9.813,
    "TDK B32923C3225K000 2.2 uF X2 (input)": 0.90,
    "2x TDK B32924D3475K000 4.7 uF X2 (output + damping)": 3.243,
    "2x TDK B32021A3472M000 4.7 nF Y2": 0.628,
    "2x TDK B32021A3222M000 2.2 nF Y2": 0.56,
    "Vishay AC05 3.9 ohm 5 W damping": 0.484,
    "2x Vishay PR02 15 k bleed": 0.273,
}
module_removed = {
    "D-22 parts (above)": sum(d22_parts.values()),
    "D-22 carrier PCB / terminals / cover allowance (budget.py:66)": 15.00,
    "module-to-board harness L/N/PE (r3 allowance, est)": 3.00,
    "enclosure: folded 5052 stand, 8x PEM CLA-M4-1, 8x M4x12, 1x M3x6 (est, unpriced in R43)": 4.00,
}
# 2 x 41 uH discrete DM inductors: required by DECISIONS item 20 in BOTH plans, no MPN, unpriced -> excluded from both sides.

choke_3p6 = 176.39 / CNY_USD
choke_sc201 = 5.37 * EUR_USD
onboard = {
    "B (recommended): Y 2.2 nF/line = C3/C4 only, stage-1 3.6 mH nanocrystalline": {
        "KEMET SCF39XV-200-Z2R1A012JH 3.6 mH 20 A": choke_3p6,
        "TDK B32923C3225K000 2.2 uF X2": 0.90,
        "2x TDK B32924D3475K000 4.7 uF X2": 3.243,
        "Vishay AC05 3.9 ohm": 0.484,
        "2x Vishay PR02 15 k": 0.273,
        "C3/C4 unchanged (2.2 nF Y1)": 0.0,
    },
    "A (cheaper choke, thin leakage margin): Y 3.3 nF/line, stage-1 SC-20-201 2 mH": {
        "KEMET SC-20-201 2.0 mH 20 A": choke_sc201,
        "TDK B32923C3225K000 2.2 uF X2": 0.90,
        "2x TDK B32924D3475K000 4.7 uF X2": 3.243,
        "Vishay AC05 3.9 ohm": 0.484,
        "2x Vishay PR02 15 k": 0.273,
        "C3/C4 2.2 -> 3.3 nF Y1 (est delta)": 0.05,
    },
    "C (cheapest passing set): Y 2.7 nF/line (C3/C4 2.2 nF + 470 pF Y1 pair), L1 and stage-1 both SC-20-201 (g01 P1)": {
        "KEMET SC-20-201 2.0 mH 20 A (stage 1)": choke_sc201,
        "L1 TDK B82726S2203A020 -> SC-20-201 (g01 P1: $9.88 -> $6.2)": choke_sc201 - 9.88484,
        "TDK B32923C3225K000 2.2 uF X2": 0.90,
        "2x TDK B32924D3475K000 4.7 uF X2": 3.243,
        "Vishay AC05 3.9 ohm": 0.484,
        "2x Vishay PR02 15 k": 0.273,
        "2x 470 pF Y1 disc (est $0.15 each)": 0.30,
    },
}
EXTRA = {"C (cheapest passing set): Y 2.7 nF/line (C3/C4 2.2 nF + 470 pF Y1 pair), L1 and stage-1 both SC-20-201 (g01 P1)": (2, 1)}
# placements / BOM lines added to the power board (same for A and B): choke 1, X 2.2u 1, X 4.7u 2, R damp 1, R bleed 2,
# DM inductors 2 (no MPN).  Lines: choke, X2.2u, X4.7u, Rdamp, Rbleed, LDM = 6.  All THT -> hand/consign lines.
placements_added = 1 + 1 + 2 + 1 + 2 + 2
lines_added = 6

# ---- area: body footprints (mm), courtyard x1.15, then the board's own courtyard occupancy (board_area.json)
ba = json.load(open(os.path.join(HERE, "board_area.json")))
occ = ba["occupied_fraction"]
bodies = {
    "stage-1 CM choke 3.6-5.7 mH nanocrystalline (SCF31X class 45 x 31, listing)": 45 * 31,
    "X2 2.2 uF 26.5 x 14.5 (PARTS.md)": 26.5 * 14.5,
    "2x X2 4.7 uF 31.5 x 21 (PARTS.md)": 2 * 31.5 * 21,
    "AC05 3.9 ohm, 18 x 7.5 body on 28 mm lead span (est)": 28 * 8,
    "2x PR02 15 k on 15 mm span (est)": 2 * 15 * 4,
}
dm = {"2x DM inductor 41 uH / 20 A, no MPN: assumed toroid 33 mm dia (est)": 2 * 33 * 33}
cy = lambda b: 1.15 * sum(b.values())
area = {
    "courtyard_mm2_without_DM": cy(bodies),
    "courtyard_mm2_with_DM": cy({**bodies, **dm}),
    "board_occupancy_fraction_s27": occ,
    "board_area_needed_mm2_without_DM": cy(bodies) / occ,
    "board_area_needed_mm2_with_DM": cy({**bodies, **dm}) / occ,
    "D-22 module envelope (no DM inductors) mm2": 110 * 80,
    "board area s27 mm2": ba["board_area_mm2"],
}
pcb_add = area["board_area_needed_mm2_with_DM"] * PCB_USD_PER_MM2
lab = {"on-board: hand-solder 9 THT parts, 0.5 min each (est)": 9 * 0.5 * LAB_USD_PER_MIN,
       "module plan: build module (11 parts, 3 terminal blocks), mount 4 screws, 2 harness ends (est 15 min)": 15 * LAB_USD_PER_MIN}

res = dict(module_removed=module_removed, d22_parts=d22_parts, module_removed_total=sum(module_removed.values()),
           placements_added=placements_added, lines_added=lines_added, area=area, pcb_area_cost_added=pcb_add,
           labour=lab, variants={})
print(f"D-22 module parts at 500: ${sum(d22_parts.values()):.2f}; removed with carrier, harness, enclosure hw: "
      f"${sum(module_removed.values()):.2f} (DM inductors excluded from both sides)")
print(f"area: courtyard {area['courtyard_mm2_without_DM']:.0f} mm2 (+DM {area['courtyard_mm2_with_DM']:.0f}); at the s27 "
      f"occupancy {occ:.3f} -> board area {area['board_area_needed_mm2_without_DM']:.0f} / {area['board_area_needed_mm2_with_DM']:.0f} mm2 "
      f"(= {100*area['board_area_needed_mm2_with_DM']/ba['board_area_mm2']:.0f} % of the board); PCB +${pcb_add:.2f}")
for name, parts in onboard.items():
    add = sum(parts.values()) + pcb_add
    net = add - sum(module_removed.values())
    net_lab = net + lab["on-board: hand-solder 9 THT parts, 0.5 min each (est)"] - lab[
        "module plan: build module (11 parts, 3 terminal blocks), mount 4 screws, 2 harness ends (est 15 min)"]
    board_parts_delta = sum(parts.values())
    ep, el = EXTRA.get(name, (0, 0))
    res["variants"][name] = dict(parts=parts, added_incl_pcb=add, net_system_material=net, net_system_with_labour=net_lab,
                                 scorecard_parts_usd_at_500_delta_board_only=board_parts_delta,
                                 scorecard_parts_usd_at_500_new=221.82 + board_parts_delta,
                                 placements_new=349 + placements_added + ep, bom_lines_new=91 + lines_added + el)
    print(f"\n{name}\n  added ${add:.2f} (parts ${board_parts_delta:.2f} + PCB ${pcb_add:.2f}); net system material "
          f"{net:+.2f}; with labour est {net_lab:+.2f}")
    print(f"  board-only scorecard parts_usd_at_500: 221.82 -> {221.82 + board_parts_delta:.2f} (+{board_parts_delta:.2f}, "
          f"DM inductors unpriced); placements 349 -> {349 + placements_added + ep}; bom_lines 91 -> {91 + lines_added + el}")
json.dump(res, open(os.path.join(HERE, "c29_cost_area.json"), "w"), indent=1)
